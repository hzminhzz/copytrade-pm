"""E4 whole-wallet source fidelity and PM-04 common-account integration.

Synthetic examples are not real wallet accounts or historical authorization.
"""

from datetime import timedelta
from decimal import Decimal as D
import json
from pathlib import Path

import pytest

from copytrade_pm.pm36_e4 import (
    E4_SCHEMA,
    E4_SOURCE_SCOPE,
    END,
    PODS,
    START,
    compare_wallet_ratios,
    e4_size,
    to_pm04_manifest,
    validate_full_book_manifest,
)
from copytrade_pm.pm_portfolio_c_driver import run_one
from copytrade_pm.pm_shadow import MinuteBar

CL = "hyperliquid/mainnet:perp:xyz/CL"
XYZ = "hyperliquid/mainnet:perp:xyz/XYZ100"
OTHER = "hyperliquid/mainnet:perp:another/ETH"


def snapshot(at, known, seq, positions, *, equity="10000"):
    return {
        "source_event_at": at,
        "first_known_at": known,
        "account_event_sequence": seq,
        "source_evidence_sha256": "a" * 64,
        "all_dex_instrument_census_confirmed": True,
        "account_equity_reconciled": True,
        "collateral_and_funding_reconciled": True,
        "continuous_position_event_feed_confirmed": True,
        "wallet_equity_usd": equity,
        "positions": positions,
    }


def whole_books():
    t = START
    initial = (t - timedelta(seconds=40)).isoformat()
    known = (t - timedelta(seconds=39)).isoformat()
    second = (t + timedelta(minutes=4, seconds=10)).isoformat()
    second_known = (t + timedelta(minutes=4, seconds=20)).isoformat()
    final = (t + timedelta(minutes=14, seconds=10)).isoformat()
    final_known = (t + timedelta(minutes=14, seconds=20)).isoformat()
    wallets = []
    for pod in PODS:
        if pod == "CO-001":
            stream = [
                snapshot(initial, known, 8, {CL: "10", XYZ: "1"}),
                snapshot(second, second_known, 9, {CL: "8", XYZ: "1.5"}, equity="11000"),
                snapshot(final, final_known, 10, {CL: "0", XYZ: "0"}, equity="11500"),
            ]
        else:
            stream = [snapshot(initial, known, 50, {})]
        wallets.append(
            {
                "pod": pod,
                "wallet_identity_sha256": "b" * 64,
                "snapshots": stream,
            }
        )
    return {
        "schema": E4_SCHEMA,
        "source_scope": E4_SOURCE_SCOPE,
        "research_only": True,
        "broker_authorized": False,
        "start": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "pods": list(PODS),
        "wallets": wallets,
    }


def test_e4_keeps_cross_instrument_ratios_and_exposure_signs():
    book = {CL: D("100"), XYZ: D("-10")}
    marks = {CL: D("100"), XYZ: D("100")}
    shocks = {CL: D("0.07"), XYZ: D("0.05")}
    target, scalar, reason = e4_size(
        book,
        marks,
        source_equity=D("20000"),
        capital_usd=D("2000"),
        shock=shocks,
        cost_rate=D("0.001"),
    )
    assert reason == "POD_STRESS_COMMON_SCALAR"
    assert scalar > D(0)
    assert target[CL] > 0 and target[XYZ] < 0
    assert abs(abs(target[CL] / target[XYZ]) - D("10")) < D("0.000000001")
    compare_wallet_ratios(book, target)
    assert sum(
        (abs(target[k] * marks[k]) * (shocks[k] + D("0.001")) for k in book),
        D(0),
    ) <= D("57")


def test_e4_preserves_wallet_leverage_when_risk_does_not_bind():
    book = {CL: D("5"), XYZ: D("-1")}
    target, scalar, reason = e4_size(
        book,
        {CL: D("100"), XYZ: D("100")},
        source_equity=D("10000"),
        capital_usd=D("2000"),
        shock={CL: D("0.07"), XYZ: D("0.05")},
        cost_rate=D("0.001"),
    )
    assert reason == "SOURCE_EQUITY_CAPITAL_SHARE"
    assert scalar == D("0.2")
    assert target == {CL: D("1.000000000000"), XYZ: D("-0.200000000000")}


@pytest.mark.parametrize(
    "defect,reason",
    [
        ("equity", "E4_NONFINITE_OR_NONPOSITIVE"),
        ("census", "E4_UNVERIFIED_SOURCE_ALL_DEX_INSTRUMENT_CENSUS_CONFIRMED"),
        ("funding", "E4_UNVERIFIED_SOURCE_COLLATERAL_AND_FUNDING_RECONCILED"),
        ("event", "E4_MISSING_INTERMEDIATE_ACCOUNT_EVENTS"),
        ("time", "E4_NONCAUSAL_OR_NONMONOTONIC_SOURCE_CLOCK"),
        ("no_history", "E4_NO_PIT_BOOK_AT_QUARTER_START"),
        ("unknown_hedge", "E4_UNKNOWN_NATIVE_INSTRUMENT"),
    ],
)
def test_e4_rejects_incomplete_wallet_account(defect, reason):
    data = whole_books()
    first = data["wallets"][0]["snapshots"][0]
    second = data["wallets"][0]["snapshots"][1]
    if defect == "equity":
        first["wallet_equity_usd"] = "0"
    elif defect == "census":
        first["all_dex_instrument_census_confirmed"] = False
    elif defect == "funding":
        first["collateral_and_funding_reconciled"] = False
    elif defect == "event":
        second["account_event_sequence"] = 100
    elif defect == "time":
        first["first_known_at"] = (START - timedelta(minutes=1)).isoformat()
    elif defect == "no_history":
        first["first_known_at"] = (START + timedelta(seconds=1)).isoformat()
    elif defect == "unknown_hedge":
        first["positions"]["bybit/perp/BTC"] = "1"
    with pytest.raises(ValueError, match=reason):
        validate_full_book_manifest(data)


def test_e4_does_not_erase_off_universe_hedges():
    data = whole_books()
    data["wallets"][0]["snapshots"][0]["positions"][OTHER] = "-5"
    with pytest.raises(ValueError, match="E4_UNMAPPED_OR_UNAUTHORIZED_HEDGE"):
        to_pm04_manifest(data, allowed_market_ids={CL, XYZ})


def test_e4_avoids_mixed_snapshot_minute():
    data = whole_books()
    data["wallets"][0]["snapshots"][1]["source_event_at"] = (
        START - timedelta(seconds=20)
    ).isoformat()
    data["wallets"][0]["snapshots"][1]["first_known_at"] = (
        START - timedelta(seconds=19)
    ).isoformat()
    with pytest.raises(ValueError, match="E4_SAME_MINUTE_MULTIPLE_SOURCE_BOOKS"):
        to_pm04_manifest(data)


def test_e4_rejects_malformed_episode_based_input():
    with pytest.raises(ValueError, match="E4_REJECTS_EPISODE_OR_UNSUPPORTED_MANIFEST"):
        validate_full_book_manifest({"schema": "pm_c_historical_oracle_input_v1"})


def test_e4_micro_hedge_and_missing_prices_fail_closed():
    book = {CL: D("10"), XYZ: D("0.00000000000000001")}
    with pytest.raises(ValueError, match="E4_UNREPRESENTABLE_SOURCE_MICROHEDGE"):
        e4_size(
            book,
            {CL: D("100"), XYZ: D("200")},
            source_equity=D("10000"),
            shock={CL: D(".07"), XYZ: D(".05")},
            cost_rate=D(".001"),
        )
    with pytest.raises(ValueError, match="E4_INCOMPLETE_OR_EXTRA_HEDGE_MARKS"):
        e4_size(
            book,
            {CL: D("100")},
            source_equity=D("10000"),
            shock={CL: D(".07"), XYZ: D(".05")},
            cost_rate=D(".001"),
        )


class SyntheticMarket:
    def __init__(self, root):
        self.root = root

    def get(self, native: str, at):
        if native not in ("hyperliquid:mainnet:perp:xyz:CL", "hyperliquid:mainnet:perp:xyz:XYZ100"):
            raise ValueError("UNKNOWN_SOURCE_SYMBOL")
        px = D("100") if native.endswith(":CL") else D("200")
        return MinuteBar(at, px, D("10000000"), "a" * 64)


@pytest.mark.parametrize("method", ["E4"])
def test_e4_account_replay_proportional_intended_books_and_readonly_ledger(
    tmp_path, monkeypatch, method
):
    import copytrade_pm.pm_portfolio_c_driver as driver

    monkeypatch.setattr(driver, "VerifiedHyperliquidMinuteSource", SyntheticMarket)
    manifest = to_pm04_manifest(whole_books(), allowed_market_ids={CL, XYZ})
    manifest["market_day_shas"]["synthetic"] = "a" * 64
    # The changed manifest must be recompiled from its original source; no
    # hand-edits to its derived contract, even to add a synthetic day SHA.
    with pytest.raises(ValueError, match="E4_COMPLETE_SOURCE_CONTRACT_SHA_OR_EVENT_DRIFT"):
        run_one(
            manifest,
            "a" * 64,
            tmp_path,
            tmp_path / "tamper",
            method=method,
            execution="IMMEDIATE",
            cost_multiplier=1,
        )
    manifest = to_pm04_manifest(whole_books(), allowed_market_ids={CL, XYZ})
    results = run_one(
        manifest,
        "a" * 64,
        tmp_path,
        tmp_path / "valid",
        method=method,
        execution="IMMEDIATE",
        cost_multiplier=1,
    )
    report = json.loads(Path(results["result"]).read_bytes())
    assert report["ledger_replay_verified"] is True
    assert report["e4_proportional_intent_verified_count"] >= 3
    assert report["e4_original_account_book_independently_verified"] is False
    assert report["source_classification"] == "E4_FULL_BOOK_CONTRACT_NOT_EXTERNAL_ECONOMIC_PROOF"
    assert report["broker_executable"] is False
    assert report["source_provenance_binding_sha256"] == manifest["source_contract_sha256"]
    assert report["e4_tracking_samples"] > 0
    assert len(report["e4_tracking_at_source_events"]) == 5
    assert not report["remaining_account_positions"]
    from copytrade_pm.pm_portfolio_c_stress import stress_scenario

    stress = stress_scenario(manifest, "a" * 64, Path(results["result"]))
    assert stress["account_ledger_verified"] is True
    assert stress["qualification"] == "E4_FULL_BOOK_EVIDENCE_CONTRACT_NOT_INDEPENDENTLY_VERIFIED"


def test_e4_is_not_compatible_with_old_episode_runner(tmp_path):
    with pytest.raises(ValueError, match="E4_REQUIRES_ATOMIC_WHOLE_WALLET_BOOKS_NOT_EPISODES"):
        run_one(
            {"schema": "pm_c_historical_oracle_input_v1"},
            "a" * 64,
            tmp_path,
            tmp_path / "refused",
            method="E4",
            execution="IMMEDIATE",
            cost_multiplier=1,
        )
