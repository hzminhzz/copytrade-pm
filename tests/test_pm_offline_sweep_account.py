"""PM-03 Decimal account remains the sole financial authority."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Instrument, Rulebook
from copytrade_pm.pm03_execution import CostModel
from copytrade_pm.pm_offline_account import replay_fixture
from copytrade_pm.pm_offline_manifest import ManifestBlocked

T = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"


def rules():
    return Rulebook(
        program="SYNTHETIC",
        stage="TEST",
        source="synthetic-fixture",
        observed_at="2026-10-19T00:00:00+00:00",
        version="1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=D("800"),
        trailing_cap=D("10000"),
        confirmed=True,
        permitted=(Instrument("hyperliquid", "perp", "BTC"),),
        max_gross_leverage=D("2"),
    )


def costs():
    return CostModel(
        fee_bps=D("0"),
        full_spread_bps=D("0"),
        slippage_bps=D("0"),
        impact_bps_at_full_participation=D("0"),
        max_participation=D("0.5"),
        max_age_seconds=60,
        latency_seconds=0,
    )


def minute(index, price="100", updates=None, volume="1000"):
    return {
        "at": T + timedelta(minutes=index),
        "prices": {BTC: price},
        "prior_volume": {BTC: volume},
        "updates": [] if updates is None else updates,
    }


def update(pm="a", qty="1", price="100", nav="1000"):
    return {
        "manager": pm,
        "source_equity": nav,
        "book": {BTC: qty},
        "leader_prices": {BTC: price},
        "verified_whole_book": True,
    }


def test_exact_equity_sizing_and_minute_marks():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update()]), minute(1, "110")],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
    )
    assert result["financial_authority"] == "PM03_ACCOUNT_DECIMAL"
    assert D(result["ledger"]["positions"]["hyperliquid/perp/BTC"]) == D("1")
    assert D(result["ledger"]["equity"]) == D("10010")
    assert result["status"] == "SYNTHETIC_PM03_OPEN"
    assert result["scientifically_qualified"] is False


def test_breach_halt_persists_across_recovery_mark():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[
            minute(0, updates=[update()]),
            minute(1, "40"),
            minute(2, "130"),
        ],
        costs=costs(),
        k_by_manager={"a": D("1")},
    )
    assert result["status"] == "SYNTHETIC_PM03_BREACH"
    assert result["ledger"]["breached"]
    assert result["ledger"]["risk"] == "HALT"
    assert result["ledger"]["events"][-1]["status"] == "HALT_PERSISTENT"


def test_missing_required_minute_mark_blocks():
    with pytest.raises(ManifestBlocked, match="GAP_IN_REQUIRED_MINUTE_MARKS"):
        replay_fixture(
            rulebook=rules(),
            minutes=[minute(0, updates=[update()]), minute(2)],
            costs=costs(),
            k_by_manager={"a": D("0.1")},
        )


def test_missing_other_manager_book_blocks():
    with pytest.raises(ManifestBlocked, match="MISSING_MANAGER_WHOLE_BOOK"):
        replay_fixture(
            rulebook=rules(),
            minutes=[minute(0, updates=[update()])],
            costs=costs(),
            k_by_manager={"a": D("0.1"), "b": D("0.1")},
        )


def test_equal_opposing_pods_do_not_fake_external_fill():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update("a", "1"), update("b", "-1")])],
        costs=costs(),
        k_by_manager={"a": D("0.1"), "b": D("0.1")},
    )
    assert result["ledger"]["positions"] == {}
    assert result["ledger"]["equity"] == "10000"
    assert len(result["ledger"]["events"][0]["execution"]["internal_crosses"]) == 1


def test_unknown_capacity_causes_unfilled_residual():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update()], volume="0.1")],
        costs=costs(),
        k_by_manager={"a": D("1")},
    )
    execution = result["ledger"]["events"][0]["execution"]
    assert execution["remaining"] != {}
    assert D(result["ledger"]["equity"]) == D("10000")
