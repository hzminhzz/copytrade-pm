"""The Grafana start fast path cannot label container liveness as health."""

import os
from pathlib import Path
import subprocess

from test_obscura_cdp import fake_cdp  # noqa: F401


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + text)
    path.chmod(0o700)


def test_live_grafana_with_dead_publisher_reports_degraded_without_restart(tmp_path):
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "ops/grafana-phase1/production.sh"
    target.parent.mkdir(parents=True)
    target.write_bytes((root / "ops/grafana-phase1/production.sh").read_bytes())
    executable(target.parent / "stage.sh", "echo UNAUTHORIZED_RESTART\nexit 99\n")
    commands = tmp_path / "commands"
    executable(commands / "tailscale", "echo unix:/run/copytrade-grafana-phase1/serve.sock\n")
    executable(commands / "docker", "echo true\n")
    executable(
        commands / "python3",
        'echo \'{"status":"DEGRADED","reasons":["PUBLISHER_NOT_RUNNING"]}\'\nexit 3\n',
    )
    result = subprocess.run(
        ["bash", str(target), "start"],
        env={**os.environ, "PATH": f"{commands}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 3
    assert "DEGRADED" in result.stdout
    assert "healthy" not in result.stdout.lower()
    assert "UNAUTHORIZED_RESTART" not in result.stdout


def test_cf08_stale_publisher_ack_and_target_disconnect_remain_independent(tmp_path, request):
    socket = request.getfixturevalue("fake_cdp")
    from copy import deepcopy
    from datetime import timedelta
    import json
    import pytest
    from copytrade_pm.dashboard import evidence_plane as ep
    from copytrade_pm.dashboard.grafana_health import assess
    from copytrade_pm.dashboard.notifications import acknowledge, process_once, dashboard_status
    from test_dashboard_final_audit import owner
    from test_grafana_projection import produce, T0
    from test_obscura_cdp import Browser

    evidence = tmp_path / "evidence"
    produce(evidence)
    observed = owner(at=T0)
    original = deepcopy(observed)

    class FailingDelivery:
        def send(self, incident):
            raise OSError("synthetic_delivery_failure")

    state = tmp_path / "notifications.json"
    status = process_once(state, observed, delivery=FailingDelivery(), now=T0)
    incident = status["incidents"][0]
    assert incident["delivery_status"] == "RETRY"
    assert acknowledge(state, incident["id"])
    stale = ep.read_generation(evidence, now=T0 + timedelta(seconds=60))
    health = assess(
        stale, {"grafana": True, "projection": True, "ingress": True, "publisher": False}
    )
    assert health.status == "DEGRADED"
    assert not health.authentic_publication_fresh
    status = dashboard_status(state, now=T0 + timedelta(seconds=60))
    assert status["incidents"][0]["active"] is True
    assert status["incidents"][0]["acknowledged"] is True
    assert status["incidents"][0]["delivery_status"] == "RETRY"
    browser = Browser(timeout=0.05)
    socket.fail_methods.add("Target.closeTarget")
    socket.replies.append(
        json.dumps({"method": "Target.targetDestroyed", "params": {"targetId": "page-fake"}})
    )
    with pytest.raises(RuntimeError, match="CDP_TARGET_DISCONNECTED"):
        browser.eval("document.readyState")
    assert socket.closed
    with pytest.raises(RuntimeError, match="CDP_CONNECTION_CLOSED"):
        browser.eval("1")
    assert observed == original
    assert observed["data"]["halts"] == ["BROKER_STALE"]
    assert health.trading_authorized is False


def test_fresh_synthetic_fixture_cannot_pass_authentic_health(tmp_path):
    from copytrade_pm.dashboard.grafana_health import assess, COMPONENTS
    from copytrade_pm.dashboard import evidence_plane as ep
    from test_grafana_projection import T0

    ep.publish_atomic(
        tmp_path,
        ep.encode_generation(ep.fixture_projection(now=T0), now=T0),
        name="fixture-states.json",
    )
    fixture = ep.read_generation(tmp_path, name="fixture-states.json", now=T0)
    report = assess(fixture, dict.fromkeys(COMPONENTS, True))
    assert report.status == "DEGRADED"
    assert report.authentic_publication_fresh is False
