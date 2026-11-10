"""Operator view is read-only and cannot bypass evidence gateway."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_dashboard_uses_fixed_read_only_projection():
    path = ROOT / "ops/grafana-phase1/dashboards/strategy-health.json"
    document = json.loads(path.read_text())
    assert document["uid"] == "copytrade-strategy-health-v2"
    assert document["editable"] is False
    assert "NO TRADE" in document["panels"][0]["options"]["content"]
    assert len(document["panels"]) == 2
    target = document["panels"][1]["targets"][0]
    assert target["url"] == "http://projection:17800/v1/strategy-health"
    assert target["url_options"]["method"] == "GET"
    assert target["datasource"]["uid"] == "risk-projection-v1"
    assert document["panels"][1]["transformations"] == []
    allowed = {
        "source_availability",
        "opportunity_count",
        "unknown_gap_intervals",
        "evidence_class",
        "assessability",
        "economic_advisory_status",
        "portfolio_contribution_status",
        "operational_priority",
        "published_at",
    }
    assert {x["selector"] for x in target["columns"]} == allowed
    assert all("address" not in x["selector"] for x in target["columns"])
