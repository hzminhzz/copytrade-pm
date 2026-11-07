"""Adversarial Phase 1 acceptance through REAL owner-scoped Tailscale ingress.

No production service, trading state, Guardian journal or deployment routes touched.
Run only with an already-active *isolated* staging stack.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from urllib.parse import urlparse

import httpx

HOST = os.environ["GRAFANA_TAILNET_HOST"]
ROOT = f"https://{HOST}:8444"
DS = "risk-projection-v1"
REGULAR = "http://projection:17800/v1/account-risk"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print("PASS", label)


def query(
    client: httpx.Client,
    url: str,
    *,
    method: str = "GET",
    allow_query_failure: bool = False,
) -> dict:
    params = {
        "queries": [
            {
                "refId": "A",
                "datasource": {"uid": DS},
                "type": "json",
                "source": "url",
                "url": url,
                "parser": "backend",
                "format": "table",
                "root_selector": "metrics",
                "url_options": {"method": method},
                "columns": [
                    {"selector": "metric", "text": "Metric", "type": "string"},
                    {"selector": "grade", "text": "Grade", "type": "string"},
                ],
            }
        ],
        "from": "1762510000000",
        "to": "1762530000000",
    }
    reply = client.post(ROOT + "/api/ds/query", json=params)
    check(
        reply.status_code in ({200, 400} if allow_query_failure else {200}),
        "Viewer Grafana query API transport",
    )
    return reply.json()["results"]["A"]


def docker_output(*args: str) -> str:
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.STDOUT, timeout=22
    ).strip()


def main() -> None:
    assert urlparse(ROOT).scheme == "https"
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        # The container health endpoint can become healthy slightly before
        # Grafana has finished auth-proxy provisioning. Gate on the real owner
        # session rather than trusting container liveness.
        user = None
        for _ in range(20):
            try:
                candidate = client.get(ROOT + "/api/user")
                if (
                    candidate.status_code == 200
                    and candidate.json().get("login") == "risk-observer"
                ):
                    user = candidate
                    break
            except httpx.TransportError, ValueError:
                pass
            time.sleep(1)
        check(user is not None, "Real Tailscale owner mapped to dedicated observer identity")
        check(user.json().get("isGrafanaAdmin") is False, "Owner is not a Grafana admin")
        orgs = client.get(ROOT + "/api/user/orgs")
        check(
            orgs.status_code == 200 and any(o["role"] == "Viewer" for o in orgs.json()),
            "Mapped operator is Grafana Viewer",
        )
        for path in ("/api/admin/settings", "/api/users"):
            forbidden = client.get(ROOT + path)
            check(forbidden.status_code == 403, "Viewer denied " + path)
        for uid, count in (("copytrade-risk-command-v1", 10), ("copytrade-synthetic-qa-v1", 11)):
            response = client.get(ROOT + "/api/dashboards/uid/" + uid)
            check(
                response.status_code == 200
                and len(response.json()["dashboard"]["panels"]) == count,
                "Provisioned native Grafana dashboard " + uid,
            )
        forged_origin = client.get(
            ROOT + "/api/user",
            headers={
                "Origin": "https://attacker.invalid",
            },
        )
        check(forged_origin.status_code == 403, "Spoofed Origin denied by owner gateway")
        legitimate = query(client, REGULAR)
        check(
            legitimate.get("status") == 200
            and len(legitimate["frames"][0]["data"]["values"][0]) == 7,
            "Seven bounded live-status rows through actual Infinity backend",
        )
        check(
            "UNAVAILABLE" in str(legitimate["frames"][0]["data"]["values"]),
            "Missing protected evidence remains UNAVAILABLE",
        )
        attacker = query(
            client, "http://127.0.0.1:3000/api/admin/settings", allow_query_failure=True
        )
        check(
            "requested URL not allowed" in str(attacker.get("error", "")),
            "Infinity cannot query arbitrary localhost administrative URL",
        )
        for url, method, label in (
            ("http://projection:17800/etc/passwd", "GET", "private file path"),
            (
                "http://projection:17800/v1/account-risk?path=/etc/passwd",
                "GET",
                "arbitrary query/path",
            ),
            (REGULAR, "POST", "financial mutation method"),
        ):
            result = query(client, url, method=method, allow_query_failure=True)
            check(result.get("status") != 200, "Viewer denied " + label)
    for network in ("copytrade-grafana-phase1_data", "copytrade-grafana-phase1_viewer"):
        data = json.loads(docker_output("network", "inspect", network))[0]
        check(data["Internal"] is True, "Internal-only Docker network " + network)
    route = docker_output(
        "exec",
        "copytrade-grafana-phase1-grafana-1",
        "sh",
        "-c",
        "grep -c '^00000000' /proc/net/route || true",
    )
    check(route == "0", "Grafana has no default route")
    absent = subprocess.run(
        [
            "docker",
            "exec",
            "copytrade-grafana-phase1-projection-1",
            "test",
            "-e",
            "/opt/readonly/copytrade_pm/dashboard/adapter.py",
        ],
        capture_output=True,
        timeout=15,
    )
    check(absent.returncode != 0, "Projection image cannot import native reader")
    # The host quant UID lacks direct access to the root-only socket directory.
    denied = False
    unix = socket.socket(socket.AF_UNIX)
    unix.settimeout(2)
    try:
        unix.connect("/run/copytrade-grafana-phase1/serve.sock")
    except PermissionError, FileNotFoundError:
        denied = True
    finally:
        unix.close()
    check(denied, "Non-privileged direct Unix-socket ingress denied")
    print("Phase 1 staging HTTP/network/identity acceptance VERIFIED")


if __name__ == "__main__":
    main()
