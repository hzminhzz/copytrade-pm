"""Blocked Phase6B matrix must never silently claim scenario survival."""

import json

import polars as pl
import pytest

from copytrade_pm.pm_phase6b import WALLETS, fingerprint
from copytrade_pm.pm_phase6b_blocked import SCENARIOS, POLICIES, run


def test_blocked_scenario_contract(tmp_path):
    coverage = tmp_path / "coverage.json"
    minute = tmp_path / "minute.json"
    coverage.write_text(
        json.dumps(
            {
                "schema": "phase6b_source_coverage_v1",
                "market_day_inventory": {"BTC": {}},
                "portfolios": [
                    {"portfolio": name, "faithful_equity_account_pnl": None} for name in WALLETS
                ],
            }
        )
    )
    minute.write_text(
        json.dumps(
            {
                "original_coverage_sha256": fingerprint(coverage),
                "instruments": {"BTC": {"verified_minutes": 0}},
            }
        )
    )
    dest = tmp_path / "sealed"
    result = run(coverage, minute, dest)
    assert result["scenarios"] == len(WALLETS) * len(POLICIES) * len(SCENARIOS)
    assert result["attempted_stresses"] == 0
    rows = (dest / "scenario_results.csv").read_text().splitlines()
    assert len(rows) == 181
    assert all("BLOCKED_NOT_RUN" in x for x in rows[1:])
    for name in ("portfolio_equity.parquet", "pod_attribution.parquet", "kill_events.parquet"):
        assert pl.read_parquet(dest / name).is_empty()
    assert run(coverage, minute, dest) == result


def test_blocked_scenario_refuses_changed_market_provenance(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(
        json.dumps(
            {
                "schema": "phase6b_source_coverage_v1",
                "market_day_inventory": {},
                "portfolios": [
                    {"portfolio": k, "faithful_equity_account_pnl": None} for k in WALLETS
                ],
            }
        )
    )
    b.write_text(json.dumps({"original_coverage_sha256": "0" * 64, "instruments": {}}))
    with pytest.raises(ValueError, match="MARKET_COVERAGE_SOURCE_MISMATCH"):
        run(a, b, tmp_path / "out")
