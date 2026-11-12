"""Chapter 2 projection never fabricates finance or merges evidence basis."""

from datetime import UTC, datetime
import pytest

from copytrade_pm.pm_cwsa_chapter2_projection import SCHEMA, project
from copytrade_pm.pm_cwsa_six_paper import PORTFOLIO_CONFIGS


def facts():
    return {
        "source_count": 14,
        "head_sha256": "d" * 64,
        "latest_checkpoint_ms": 1794470000000,
        "policy_grace_ms": 180000,
        "latest_kinds": {
            member: "BASELINE" for cfg in PORTFOLIO_CONFIGS.values() for member in cfg["members"]
        },
    }


def test_six_blocked_paper_records_never_claim_zero_pnl():
    result = project(
        source=facts(),
        papers={},
        verified_finance=set(),
        qualified_k=set(),
        release_sha="a" * 40,
        epoch="epoch2",
        generated_at=datetime(2026, 11, 12, tzinfo=UTC),
    )
    assert result["schema"] == SCHEMA
    assert set(result["portfolios"]) == set(PORTFOLIO_CONFIGS)
    assert result["source_wallet_count"] == 14
    assert result["historical_v4"] is None
    assert result["native_broker"] is None
    assert not result["trading_authorized"]
    for row in result["portfolios"].values():
        assert row["financial_admission"] == "BLOCKED_EVIDENCE"
        assert row["current_equity_usd"] is None
        assert row["realized_pnl_usd"] is None
        assert row["total_costs_usd"] is None
        assert row["drawdown_usd"] is None
        assert "UNQUALIFIED_K" in row["blockers"]


def test_missing_source_and_unmodeled_baseline_are_explicit():
    f = facts()
    f["latest_kinds"]["W028"] = "UNAVAILABLE"
    base = {
        "cursor": 3,
        "modeled_effects": 0,
        "current_equity": "10000",
        "realized_pnl": "0",
        "costs": "0",
        "wave_count": 1,
    }
    result = project(
        source=f,
        papers={"A": base},
        verified_finance={"A"},
        qualified_k={"A"},
        release_sha="b" * 40,
        epoch="epoch2",
    )
    a = result["portfolios"]["A"]
    assert a["source_coverage_complete"] is False
    assert "W028" in a["missing_sources"]
    assert a["realized_pnl_usd"] is None
    assert a["financial_admission"] == "BLOCKED_EVIDENCE"
    assert "NO_PROVEN_MODELED_FINANCIAL_EFFECT" in a["blockers"]


def test_modeled_pnl_requires_verified_replay_proof():
    base = {
        "cursor": 4,
        "modeled_effects": 1,
        "current_equity": "10001",
        "realized_pnl": "-1",
        "costs": "2",
        "positions_count": 1,
    }
    result = project(
        source=facts(),
        papers={"A": base},
        verified_finance={"A"},
        qualified_k={"A"},
        release_sha="c" * 40,
        epoch="epoch2",
    )
    assert result["portfolios"]["A"]["realized_pnl_usd"] == "-1"
    assert result["portfolios"]["A"]["financial_admission"] == "PROSPECTIVE_MODELED_PAPER"
    assert result["portfolios"]["B"]["realized_pnl_usd"] is None
    assert result["portfolios"]["A"]["model_financial_basis"] == "CWSA_5M_PROSPECTIVE"


def test_source_or_portfolio_lineage_drift_fails_closed():
    f = facts()
    f["source_count"] = 13
    with pytest.raises(ValueError, match="ROSTER"):
        project(
            source=f,
            papers={},
            verified_finance=set(),
            qualified_k=set(),
            release_sha="c" * 40,
            epoch="epoch2",
        )
    with pytest.raises(ValueError, match="UNRECOGNIZED"):
        project(
            source=facts(),
            papers={"UNKNOWN": {}},
            verified_finance=set(),
            qualified_k=set(),
            release_sha="c" * 40,
            epoch="epoch2",
        )
