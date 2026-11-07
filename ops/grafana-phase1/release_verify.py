"""Read-only reproducible Grafana source bundle manifest and compatibility check.

The SHA is an integrity fingerprint for source/configuration, not a financial
authority signature or proof that the corresponding release is installed.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "ops/grafana-phase1/Dockerfile.grafana",
    "ops/grafana-phase1/Dockerfile.publisher",
    "ops/grafana-phase1/Dockerfile.projection",
    "ops/grafana-phase1/compose.yaml",
    "ops/grafana-phase1/nginx/serve.conf.template",
    "ops/grafana-phase1/provisioning/dashboards/account-risk.yaml",
    "ops/grafana-phase1/provisioning/datasources/account-risk.yaml",
    "ops/grafana-phase1/provisioning/alerting/operational.json",
    "ops/grafana-phase1/dashboards/risk-command.json",
    "ops/grafana-phase1/dashboards/portfolios.json",
    "ops/grafana-phase1/dashboards/execution.json",
    "ops/grafana-phase1/dashboards/health.json",
    "ops/grafana-phase1/dashboards/wallets.json",
    "src/copytrade_pm/dashboard/evidence_plane.py",
    "src/copytrade_pm/dashboard/grafana_projection.py",
    "src/copytrade_pm/dashboard/grafana_capabilities.py",
)
EXPECTED_UIDS = {
    "risk-command": "copytrade-risk-command-v1",
    "portfolios": "copytrade-pods-portfolio-v1",
    "execution": "copytrade-execution-v1",
    "health": "copytrade-health-incidents-v1",
    "wallets": "copytrade-wallet-explorer-v1",
}


def verify(root: Path = ROOT) -> dict:
    files = {}
    for name in SOURCES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("MISSING_OR_SYMLINK_RELEASE_SOURCE:" + name)
        files[name] = sha256(path.read_bytes()).hexdigest()
    for file, uid in EXPECTED_UIDS.items():
        data = json.loads((root / f"ops/grafana-phase1/dashboards/{file}.json").read_text())
        if data["uid"] != uid or data.get("editable") is not False:
            raise ValueError("INCOMPATIBLE_DASHBOARD:" + file)
    alerts = json.loads(
        (root / "ops/grafana-phase1/provisioning/alerting/operational.json").read_text()
    )
    if len(alerts["groups"][0]["rules"]) != 3:
        raise ValueError("INCOMPATIBLE_ALERT_RELEASE")
    compose = (root / "ops/grafana-phase1/compose.yaml").read_text()
    if "network_mode: none" not in compose or "internal: true" not in compose:
        raise ValueError("UNSAFE_DOCKER_RELEASE")
    if "evidence:/evidence:ro" not in compose:
        raise ValueError("PROJECTION_WRITE_MOUNT")
    digest = sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "copytrade_grafana_source_bundle_v1",
        "configuration_owner": "git_file_provisioning_only",
        "evidence_schema": "copytrade_evidence_generation_v1",
        "capability_schema": "grafana_operational_capabilities_v1",
        "sha256": digest,
        "files": files,
        "financially_authoritative": False,
        "production_deployed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify(args.root.resolve())
    revision = subprocess.run(
        ["git", "-C", str(args.root.resolve()), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    result["git_commit"] = revision.stdout.strip() if revision.returncode == 0 else None
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
