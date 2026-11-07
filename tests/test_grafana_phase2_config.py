"""Reproducible Grafana Phase 2 read-only provisioning contracts."""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "grafana-phase1"
DASHBOARDS = {
    "risk-command.json": "copytrade-risk-command-v1",
    "portfolios.json": "copytrade-pods-portfolio-v1",
    "execution.json": "copytrade-execution-v1",
    "health.json": "copytrade-health-incidents-v1",
    "wallets.json": "copytrade-wallet-explorer-v1",
}


def test_dashboard_inventory_and_allowed_datasource():
    for filename, uid in DASHBOARDS.items():
        value = json.loads((OPS / "dashboards" / filename).read_text())
        assert value["uid"] == uid
        assert value["editable"] is False
        assert value["timezone"] == "utc"
        assert len(value["panels"]) >= 4
        for panel in value["panels"]:
            for query in panel.get("targets", []):
                assert query["url"] == "http://projection:17800/v1/account-risk"
                assert query["url_options"]["method"] == "GET"
                assert query["parser"] == "backend"
                assert query["datasource"]["uid"] == "risk-projection-v1"
                assert not query.get("filters")
        assert not value["templating"]["list"]


def test_alerts_are_browser_independent_and_fail_closed():
    config = json.loads((OPS / "provisioning" / "alerting" / "operational.json").read_text())
    assert config["apiVersion"] == 1
    assert len(config["groups"]) == 1
    group = config["groups"][0]
    assert group["folder"] == "copytrade-risk-v1"
    assert len(group["rules"]) == 3
    for rule in group["rules"]:
        assert rule["noDataState"] == "Alerting"
        assert rule["execErrState"] == "Alerting"
        assert rule["isPaused"] is False
        assert rule["condition"] == "B"
        assert rule["data"][0]["datasourceUid"] == "risk-projection-v1"
        assert rule["data"][0]["model"]["parser"] == "backend"
        assert rule["data"][1]["datasourceUid"] == "__expr__"
        assert rule["labels"]["authority"] == "presentation-only"


def test_versioned_source_bundle_rejects_bad_release_and_restores_baseline(tmp_path):
    release = runpy.run_path(str(OPS / "release_verify.py"))
    verify = release["verify"]
    files = release["SOURCES"]
    expected = verify(ROOT)
    assert len(expected["files"]) == len(files)
    assert len(expected["sha256"]) == 64
    assert expected["configuration_owner"] == "git_file_provisioning_only"
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    assert verify(tmp_path)["sha256"] == expected["sha256"]
    broken = tmp_path / "ops/grafana-phase1/dashboards/execution.json"
    raw = json.loads(broken.read_text())
    raw["uid"] = "bad-release-incompatible"
    broken.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="INCOMPATIBLE_DASHBOARD"):
        verify(tmp_path)
    assert verify(ROOT)["sha256"] == expected["sha256"]


def test_projection_image_and_staging_config_retain_isolation():
    projection = (OPS / "Dockerfile.projection").read_text()
    assert "grafana_capabilities.py" in projection
    assert "dashboard/adapter.py" not in projection
    assert "wallet_registry.py" not in projection
    compose = (OPS / "compose.yaml").read_text()
    assert "network_mode: none" in compose
    assert "evidence:/evidence:ro" in compose
    assert "internal: true" in compose
    assert "8443" not in compose
    assert 'restart: "no"' in compose
    stage = (OPS / "stage.sh").read_text()
    assert "REFUSE: HTTPS 8444 has a preexisting Serve configuration." in stage
    assert "tailscale_root serve --https=8444 off" in stage
