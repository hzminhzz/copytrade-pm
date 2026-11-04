"""PM-03 Decimal account remains the sole financial authority."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Instrument, Rulebook
from copytrade_pm.pm03_execution import CostModel
from copytrade_pm.pm03_risk import RiskPolicy
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
    assert result["contractual_real_verdict"] == "UNKNOWN"
    assert result["certification"]["verdict"] == "UNKNOWN"


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


def test_independently_calculated_two_pod_cash_equity_fee_funding_golden():
    # Two source pods: +2 BTC and -1 BTC, equity 1000 each.
    # k=0.1, follower equity 10000, leader/follower marks 100:
    #   pod A +2 BTC, pod B -1 BTC, one internal BTC cross,
    #   one *external* +1 BTC; fee = 1 * 100 * 10bps = 0.1.
    # At 110: net MTM gain = 10. Funding -1.25.
    # Independently calculated final cash 9898.65, equity 10008.65.
    priced_costs = replace(costs(), fee_bps=D("10"))
    funding_at = T + timedelta(minutes=1)
    second = minute(1, price="110")
    second["funding"] = [
        {
            "amount": "-1.25",
            "allocated": {"a": "-1.25"},
            "first_known_at": funding_at,
        }
    ]
    result = replay_fixture(
        rulebook=rules(),
        minutes=[
            minute(0, updates=[update("a", "2"), update("b", "-1")]),
            second,
        ],
        costs=priced_costs,
        k_by_manager={"a": D("0.1"), "b": D("0.1")},
        funding_evidence_complete=True,
    )
    ledger = result["ledger"]
    first = ledger["events"][0]["execution"]
    assert len(first["internal_crosses"]) == 1
    assert len(first["fills"]) == 1
    assert D(first["fills"][0]["quantity"]) == D("1")
    assert D(ledger["fees"]) == D("0.1")
    assert D(ledger["funding"]) == D("-1.25")
    assert D(ledger["cash"]) == D("9898.65")
    assert D(ledger["equity"]) == D("10008.65")
    assert D(ledger["unrealized_pnl"]) == D("10")
    assert D(ledger["positions"]["hyperliquid/perp/BTC"]) == D("1")
    assert D(ledger["pm_quantities"]["a"]["hyperliquid/perp/BTC"]) == D("2")
    assert D(ledger["pm_quantities"]["b"]["hyperliquid/perp/BTC"]) == D("-1")
    assert result["contractual_real_verdict"] == "UNKNOWN"


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


def test_unmodified_manager_target_is_not_repriced_on_other_manager_signal():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[
            minute(0, updates=[update("a"), update("b")]),
            minute(1, "110", updates=[update("b", price="110")]),
        ],
        costs=costs(),
        k_by_manager={"a": D("0.1"), "b": D("0.1")},
    )
    books = result["ledger"]["pm_quantities"]
    assert D(books["a"]["hyperliquid/perp/BTC"]) == D("1")
    assert D(books["b"]["hyperliquid/perp/BTC"]) > D("1")


def test_funding_posted_on_pm03_ledger_with_known_receipt():
    at = T + timedelta(minutes=1)
    second = minute(1)
    second["funding"] = [
        {
            "amount": "-1.25",
            "allocated": {"a": "-1.25"},
            "first_known_at": at,
        }
    ]
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update()]), second],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
    )
    assert D(result["ledger"]["funding"]) == D("-1.25")
    assert D(result["ledger"]["equity"]) == D("9998.75")
    assert result["ledger"]["events"][1]["funding"][0]["amount"] == "-1.25"


def test_future_known_funding_is_rejected():
    at = T + timedelta(minutes=2)
    second = minute(1)
    second["funding"] = [
        {
            "amount": "1",
            "allocated": {"a": "1"},
            "first_known_at": at,
        }
    ]
    with pytest.raises(ManifestBlocked, match="FUTURE_KNOWN_FUNDING"):
        replay_fixture(
            rulebook=rules(),
            minutes=[minute(0, updates=[update()]), second],
            costs=costs(),
            k_by_manager={"a": D("0.1")},
        )


def test_leader_follower_price_difference_changes_quantity():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update(price="200")])],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
    )
    assert D(result["ledger"]["positions"]["hyperliquid/perp/BTC"]) == D("2")


def test_gross_before_net_cap_vetoes_opposing_pod_hedges():
    # External net exposure is zero, but two separately allocated pods each
    # carry 1000 gross notional. A net-only cap would incorrectly permit this.
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update("a", qty="1"), update("b", qty="-1")])],
        costs=costs(),
        k_by_manager={"a": D("1"), "b": D("1")},
        risk_policy=RiskPolicy(max_gross_leverage=D("0.1")),
        scenario_shocks=({BTC: D("-0.02")}, {BTC: D("0.02")}),
        hedge_break_loss=D("10"),
        stressed_liquidity_loss=D("1"),
    )
    decision = result["ledger"]["events"][0]["pretrade"]
    assert decision["allowed"] is False
    assert "GROSS_BEFORE_NET_OR_POD_CONCENTRATION" in decision["reasons"]
    assert result["ledger"]["positions"] == {}
    assert result["ledger"]["risk"] == "RED"


def test_portfolio_stress_requires_frozen_shocks():
    with pytest.raises(ManifestBlocked, match="MISSING_FROZEN_PORTFOLIO_STRESS"):
        replay_fixture(
            rulebook=rules(),
            minutes=[minute(0, updates=[update()])],
            costs=costs(),
            k_by_manager={"a": D("0.1")},
            risk_policy=RiskPolicy(),
        )


def test_exact_target_first_time_is_recorded():
    result = replay_fixture(
        rulebook=rules(),
        minutes=[minute(0, updates=[update(qty="1")]), minute(1, "200")],
        costs=costs(),
        k_by_manager={"a": D("1")},
    )
    assert result["ledger"]["first_target_at"] == (T + timedelta(minutes=1)).isoformat()
    assert result["ledger"]["first_breach_at"] is None


def test_exact_synthetic_target_with_confirmed_terms_is_fixture_only():
    rule = replace(rules(), account_terms_confirmed=True)
    result = replay_fixture(
        rulebook=rule,
        minutes=[
            minute(0, updates=[update()]),
            minute(1, price="1200"),
        ],
        costs=costs(),
        k_by_manager={"a": D("1")},
        funding_evidence_complete=True,
    )
    assert result["ledger"]["stage_passed"] is True
    assert result["certification"]["verdict"] == "PASS"
    assert result["certification"]["certified"] is True
    assert result["certification"]["synthetic_fixture_only"] is True
    assert result["contractual_real_verdict"] == "UNKNOWN"


def test_synthetic_right_censor_prevents_fixture_target_pass():
    rule = replace(rules(), account_terms_confirmed=True)
    result = replay_fixture(
        rulebook=rule,
        minutes=[minute(0, updates=[update()]), minute(1, price="1200")],
        costs=costs(),
        k_by_manager={"a": D("1")},
        right_censored_source=True,
        funding_evidence_complete=True,
    )
    assert result["ledger"]["stage_passed"] is True
    assert result["certification"]["verdict"] == "UNKNOWN"
    assert result["certification"]["reason"] == "OPEN_RISK_OR_UNMATURED_EVENTS"


def test_missing_funding_evidence_prevents_synthetic_target_certification():
    rule = replace(rules(), account_terms_confirmed=True)
    result = replay_fixture(
        rulebook=rule,
        minutes=[minute(0, updates=[update()]), minute(1, price="1200")],
        costs=costs(),
        k_by_manager={"a": D("1")},
        funding_evidence_complete=False,
    )
    assert result["ledger"]["stage_passed"] is True
    assert result["certification"]["verdict"] == "UNKNOWN"
    assert result["certification"]["status"] == "INSUFFICIENT_ACCOUNT_EVIDENCE"
    assert result["contractual_real_verdict"] == "UNKNOWN"


def test_screen_only_never_produces_certified_contract_result():
    rule = replace(rules(), account_terms_confirmed=True)
    result = replay_fixture(
        rulebook=rule,
        minutes=[minute(0, updates=[update()]), minute(1, price="1200")],
        costs=costs(),
        k_by_manager={"a": D("1")},
        mode="SCREEN_ONLY",
    )
    assert result["certification"]["verdict"] == "UNKNOWN"
    assert result["certification"]["certified"] is False


def test_daily_reset_uses_realized_balance_not_unrealized_equity():
    first = minute(0, updates=[update()])
    first["at"] = T.replace(hour=23, minute=59)
    second = minute(1, price="110")
    second["at"] = first["at"] + timedelta(minutes=1)
    result = replay_fixture(
        rulebook=rules(),
        minutes=[first, second],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
    )
    assert result["ledger"]["daily_key"] == "2026-10-21"
    assert D(result["ledger"]["equity"]) == D("10010")
    assert D(result["ledger"]["daily_start_balance"]) == D("10000")


def test_source_known_clock_after_simulated_decision_fails_closed():
    late = update()
    late["source_known_at"] = (T + timedelta(minutes=1)).isoformat()
    with pytest.raises(ManifestBlocked, match="FUTURE_KNOWN_SOURCE_BOOK"):
        replay_fixture(
            rulebook=rules(),
            minutes=[minute(0, updates=[late])],
            costs=costs(),
            k_by_manager={"a": D("0.1")},
        )


def test_pm03_snapshot_resume_equity_and_halt_parity():
    from copytrade_pm.pm03_account import Account, Instrument

    rule = rules()
    inst = Instrument("hyperliquid", "perp", "BTC")
    account = Account.start(rule, T.isoformat())
    account.mark({inst: D("100")}, T.isoformat())
    account.simulate_fill(inst, D("10"), D("100"), D("1"), accepted=True, allocated={"a": D("10")})
    snap = account.snapshot()
    restored = Account.from_snapshot(rule, snap)
    assert restored.snapshot() == snap
    later = (T + timedelta(minutes=1)).isoformat()
    account.mark({inst: D("40")}, later)
    restored.mark({inst: D("40")}, later)
    assert account.breached and restored.breached
    assert account.snapshot() == restored.snapshot()
    with pytest.raises(ValueError, match="CONTRACTUAL_BREACH_PERMANENT"):
        restored.simulate_fill(
            inst, D("1"), D("40"), D("0"), accepted=True, allocated={"a": D("1")}
        )


def test_partial_reduction_remains_open_and_uncertified():
    rule = replace(rules(), account_terms_confirmed=True)
    result = replay_fixture(
        rulebook=rule,
        minutes=[
            minute(0, updates=[update(qty="1")]),
            minute(1, updates=[update(qty="0")], volume="0.25"),
        ],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
        funding_evidence_complete=True,
    )
    assert D(result["ledger"]["positions"]["hyperliquid/perp/BTC"]) == D("0.875")
    assert result["ledger"]["events"][1]["execution"]["status"] == "PARTIAL"
    assert result["ledger"]["events"][1]["execution"]["remaining"] == {
        "hyperliquid/perp/BTC": "-0.875"
    }
    assert result["certification"]["verdict"] == "UNKNOWN"
    assert result["contractual_real_verdict"] == "UNKNOWN"


def test_funding_across_day_rollover_is_exact_and_attributed_to_pod():
    dayend = T.replace(hour=23, minute=59)
    funding = {
        "amount": "-0.375",
        "allocated": {"a": "-0.375"},
        "first_known_at": dayend + timedelta(minutes=1),
    }
    result = replay_fixture(
        rulebook=rules(),
        minutes=[
            {**minute(0, updates=[update()]), "at": dayend},
            {
                **minute(1),
                "at": dayend + timedelta(minutes=1),
                "funding": [funding],
            },
        ],
        costs=costs(),
        k_by_manager={"a": D("0.1")},
        funding_evidence_complete=True,
    )
    assert D(result["ledger"]["funding"]) == D("-0.375")
    assert D(result["ledger"]["equity"]) == D("9999.625")
    assert result["ledger"]["daily_key"] == "2026-10-21"
    assert D(result["ledger"]["daily_start_balance"]) == D("10000")


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
