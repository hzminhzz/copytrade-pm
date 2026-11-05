"""Doctor must expose source divergence without weakening its fail-closed gate."""

from __future__ import annotations

import json
import sys

from copytrade_pm import wallet_registry as registry


def test_doctor_reports_specific_extra_cohort_mismatch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["copytrade-wallet-registry", "doctor"])
    monkeypatch.setattr(registry, "collect", lambda *args: {})
    monkeypatch.setattr(
        registry,
        "status",
        lambda _: {
            "research_unique": 158,
            "desired": 264,
            "subscribed": 264,
            "owner_excluded": 22,
            "research_owner_excluded_overlap": 0,
            "research_desired_overlap": 131,
            "research_subscribed_overlap": 131,
            "source_shas": {"a": "b"},
        },
    )
    monkeypatch.setattr(
        registry,
        "db_status",
        lambda _: {
            "counts": {
                "research_unique": 164,
                "desired": 264,
                "subscribed": 264,
                "owner_excluded": 22,
                "research_owner_excluded_overlap": 0,
                "research_desired_overlap": 131,
                "research_subscribed_overlap": 131,
            },
            "source_shas": {"a": "b"},
            "freshness": "CURRENT",
        },
    )
    assert registry.cli() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["counts_match"] is False
    assert result["source_sha_match"] is True
    assert result["count_mismatches"] == {
        "research_unique": {"stored": 164, "source": 158}
    }
