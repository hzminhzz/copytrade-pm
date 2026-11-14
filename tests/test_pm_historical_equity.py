"""Historical equity denominator custody and no-proxy fallback tests."""

from datetime import timedelta
from decimal import Decimal as D
import json

import pytest

from copytrade_pm import pm_historical_combos as replay
from copytrade_pm.pm_historical_combos import START, Episode, _batched_actions_equity
from copytrade_pm.pm_historical_equity import (
    DEFINITION,
    SCHEMA,
    EquityPoint,
    HistoricalEquity,
    load_equity,
)

BTC = "BTC"
SHA = "a" * 64


def event(when, before, after, tid):
    return when, tid, BTC, D(before), D(after), D(after) - D(before), D("100000")


def equity(wallet, timeline):
    return HistoricalEquity(
        ledger_sha256=SHA,
        scope={wallet: "master:all-dex"},
        points={wallet: tuple(EquityPoint(at, D(amount), SHA) for at, amount in timeline)},
    )


def test_equity_batched_action_matches_300pct_position_and_variable_equity():
    first = START + timedelta(minutes=1, seconds=5)
    second = first + timedelta(minutes=20)
    close = first + timedelta(minutes=40)
    episode = Episode(
        "W028",
        BTC,
        (
            event(first, "0", "3", 1),
            event(second, "3", "3.6", 2),
            event(close, "3.6", "0", 3),
        ),
    )
    e = equity(
        "W028",
        [
            (START, "100000"),
            (START + timedelta(minutes=15), "120000"),
            (START + timedelta(minutes=38), "120000"),
        ],
    )
    rows = _batched_actions_equity({"W028": [episode]}, ("W028",), e)
    inst = replay._native_pm("BTC")
    assert rows[0][0] == START + timedelta(minutes=7)
    assert rows[0][1]["W028"][inst] == D(".06")  # 3 BTC * (2000/100000)
    # Equity changed at minute 15, so resize the *unchanged 3 BTC*
    # exposure without waiting for a new source fill.
    assert rows[1][0] == START + timedelta(minutes=21)
    assert rows[1][1]["W028"][inst] == D(".05")
    assert rows[2][0] == START + timedelta(minutes=27)
    assert rows[2][1]["W028"][inst] == D(".06")  # 3.6 BTC /120k
    assert rows[-1][1]["W028"] == {}  # explicit source close


def test_skipped_observation_before_next_snapshot_not_assumed_zero():
    t = START + timedelta(minutes=1)
    episode = Episode(
        "W028",
        BTC,
        (
            event(t, "0", "3", 1),
            event(t + timedelta(minutes=10), "3", "5", 2),
            event(t + timedelta(minutes=20), "5", "0", 3),
        ),
    )
    e = equity("W028", [(START, "100000")])
    actions = _batched_actions_equity({"W028": [episode]}, ("W028",), e)
    inst = replay._native_pm("BTC")
    assert [a["W028"].get(inst, D("0")) for _, a in actions] == [D(".06"), D(".1"), D("0")]


def test_equity_asof_never_looks_forward_or_uses_stale_value():
    e = equity("W028", [(START + timedelta(minutes=10), "100000")])
    with pytest.raises(ValueError, match="EQUITY_PRIOR_SNAPSHOT"):
        e.asof("W028", START + timedelta(minutes=5))
    assert e.asof("W028", START + timedelta(minutes=11)) == D("100000")
    with pytest.raises(ValueError, match="EQUITY_SNAPSHOT_STALE"):
        e.asof("W028", START + timedelta(hours=2))
    with pytest.raises(ValueError, match="EQUITY_WALLET_HISTORY_MISSING"):
        e.asof("W042", START + timedelta(minutes=11))


def _ledger(aliases):
    return {
        "schema": SCHEMA,
        "wallets": [
            {
                "wallet": w,
                "wallet_identity_sha256": SHA,
                "account_scope": "master:all-dex",
                "points": [
                    {
                        "source_event_at": START.isoformat(),
                        "equity_usd": "100000",
                        "equity_definition": DEFINITION,
                        "source_sha256": "b" * 64,
                        "reconciled_funding_transfers": True,
                    }
                ],
            }
            for w in aliases
        ],
    }


def test_equity_ledger_loads_asof_and_pins_wallet_cohort(tmp_path):
    path = tmp_path / "source-equity.json"
    path.write_text(json.dumps(_ledger(("W028", "W042"))))
    e = load_equity(path, identities={"W028": SHA, "W042": SHA})
    assert e.asof("W028", START + timedelta(minutes=1)) == D("100000")
    assert len(e.ledger_sha256) == 64
    assert len(e.points) == 2


@pytest.mark.parametrize(
    "corrupt,reason",
    [
        (
            lambda doc: doc["wallets"][0].update(wallet_identity_sha256="f" * 64),
            "EQUITY_LEDGER_SOURCE_IDENTITY",
        ),
        (lambda doc: doc["wallets"][0]["points"][0].update(equity_usd="0"), "INVALID_E0_NUMBER"),
        (
            lambda doc: doc["wallets"][0]["points"][0].update(reconciled_funding_transfers=False),
            "EQUITY_FUNDING_TRANSFERS",
        ),
        (
            lambda doc: doc["wallets"][0]["points"][0].update(equity_definition="MARGIN"),
            "EQUITY_DEFINITION",
        ),
        (
            lambda doc: doc["wallets"][0]["points"].append(doc["wallets"][0]["points"][0]),
            "EQUITY_HISTORY_OUT_OF_ORDER",
        ),
    ],
)
def test_equity_ledger_rejects_identity_equity_and_bad_clock(tmp_path, corrupt, reason):
    path = tmp_path / "invalid.json"
    data = _ledger(("W028",))
    corrupt(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=reason):
        load_equity(path, identities={"W028": SHA})


def test_equity_mode_study_uses_synthetic_asof_ledger_without_gross_proxy(tmp_path, monkeypatch):
    """Fixture proves wiring only; no real Q3 economic or scientific evidence."""
    from copytrade_pm.pm_shadow import MinuteBar, VerifiedHyperliquidMinuteSource

    class Entry:
        def __init__(self, alias):
            self.alias = alias
            self.address_sha256 = SHA

    class FlatMarket:
        _minute = staticmethod(VerifiedHyperliquidMinuteSource._minute)
        minute = staticmethod(VerifiedHyperliquidMinuteSource.minute)

        def __init__(self, _root):
            self.source_days = {}

        def get(self, _market, when):
            return MinuteBar(when, D("100000"), D("100000000"), SHA)

    aliases = replay.ALL_WALLETS
    monkeypatch.setattr(
        replay,
        "load_cohort",
        lambda _root: (tuple(Entry(alias) for alias in aliases), {"manifest": SHA}),
    )
    monkeypatch.setattr(replay, "VerifiedHyperliquidMinuteSource", FlatMarket)
    opened_at = START + timedelta(minutes=1, seconds=5)
    closed_at = START + timedelta(minutes=23, seconds=5)
    episodes = {
        wallet: [
            Episode(
                wallet,
                "BTC",
                (
                    event(opened_at, "0", "0.3", 1),
                    event(closed_at, "0.3", "0", 2),
                ),
            )
        ]
        for wallet in aliases
    }
    monkeypatch.setattr(
        replay,
        "_source_inputs",
        lambda _root, _market, _generations: (
            episodes,
            {wallet: {"status": "TEST_FIXTURE"} for wallet in aliases},
            {wallet: D("99999") for wallet in aliases},
            {"public_snapshot_sha256": SHA, "verified_overlay_report_sha256": None},
        ),
    )
    ledger = _ledger(aliases)
    output = tmp_path / "equity.json"
    output.write_text(json.dumps(ledger))
    report = replay.study(tmp_path, tmp_path, (), source_equity_ledger=output)
    assert report["schema"] == replay.EQUITY_SCHEMA
    assert report["status"] == "PARTIAL_EQUITY_WEIGHTED_RESEARCH_NOT_WALLET_QUALIFICATION"
    assert report["source_equity_ledger_sha256"] != SHA
    assert report["wallets_with_predecision_equity_evidence"] == 9
    assert report["fully_faithful_whole_wallet_replays"] == 0
    assert report["scientifically_qualified"] is False
    assert len(report["portfolio_results"]) == 84
    first = report["portfolio_results"][0]
    assert first["source_equity_weight_sizing"] is True
    assert first["name"] == "A"
    assert first["status"] == "CONDITIONAL_EPISODE_REPLAY_FULL_Q3"
    assert D(first["pnl_usd"]) < 0
    assert all(not row["source_and_realized_cost_fidelity"] for row in report["portfolio_results"])


def test_default_replay_produces_no_dollar_pnl_without_real_source_equity(monkeypatch):
    # No raw private vendor file is needed to prove the fail-closed default.
    class Entry:
        def __init__(self, alias):
            self.alias, self.address_sha256 = alias, SHA

    monkeypatch.setattr(
        replay,
        "load_cohort",
        lambda _root: (tuple(Entry(alias) for alias in replay.ALL_WALLETS), {"frozen": SHA}),
    )
    results = replay.study("not-used", "not-used", ())
    assert results["status"] == "BLOCKED_HISTORICAL_SOURCE_EQUITY"
    assert len(results["portfolio_results"]) == 84
    assert {row["pnl_usd"] for row in results["portfolio_results"]} == {None}
    assert all(
        row["status"] == "BLOCKED_HISTORICAL_SOURCE_EQUITY" for row in results["portfolio_results"]
    )
    assert results["valid_full_wallet_combo_ranking_available"] is False
