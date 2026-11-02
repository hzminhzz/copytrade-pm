"""Sparse but real-history source-equity portfolio oracle research regressions."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal as D
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm03_account import Account
from copytrade_pm.pm_historical_combos import (
    START,
    Episode,
    _native_pm,
    _rebalance,
    _synthetic_rulebook,
)
from copytrade_pm.pm_shadow import MarketDataBlocked, MinuteBar
from copytrade_pm.pm_sparse_equity_portfolio import (
    BoundedCarryMinuteMarket,
    SparseEquity,
    SparsePoint,
    _private_history,
    source_actions,
)

BTC = "BTC"
BTC_INST = _native_pm(BTC)
SHA = "a" * 64


def fill(at, before, after, tid=1):
    return at, tid, BTC, D(before), D(after), D(after) - D(before), D("100000")


def source_nav(wallet="W028", *, zero=False):
    return SparseEquity(
        {
            wallet: (
                SparsePoint(START, D("100000")),
                SparsePoint(START + timedelta(minutes=15), D("0") if zero else D("120000")),
            )
        },
        {wallet: SHA},
        {wallet: {"q3_points": 2}},
        {wallet: "2026-11-02T00:00:00+00:00"},
    )


def test_past_only_nav_not_interpolated_and_zero_is_unknown():
    nav = source_nav(zero=True)
    at = START + timedelta(minutes=10)
    value, status, age = nav.asof("W028", at, max_age=timedelta(days=8))
    assert value == D("100000")
    assert status == "OBSERVED_SPARSE_SOURCE_EQUITY"
    assert age == timedelta(minutes=10)
    later, cause, _ = nav.asof("W028", START + timedelta(minutes=20), max_age=timedelta(days=8))
    assert later is None and cause == "NONPOSITIVE_SOURCE_EQUITY"
    unknown, cause, _ = nav.asof("W028", START - timedelta(seconds=1), max_age=timedelta(days=8))
    assert unknown is None and cause == "BEFORE_FIRST_SOURCE_EQUITY"
    stale, cause, _ = nav.asof("W028", START + timedelta(days=9), max_age=timedelta(days=8))
    assert stale is None and cause == "SOURCE_EQUITY_TOO_OLD"


def test_equity_reweights_native_size_without_new_trade_and_skips_unknown():
    first = START + timedelta(minutes=1, seconds=5)
    end = first + timedelta(minutes=25)
    ep = Episode(
        "W028",
        BTC,
        (
            fill(first, "0", "3", 1),
            fill(end, "3", "0", 2),
        ),
    )
    rows, audit = source_actions({"W028": [ep]}, ("W028",), source_nav())
    output = {time: updates["W028"] for time, updates in rows}
    assert output[START + timedelta(minutes=7)][BTC_INST] == D(".06")
    assert output[START + timedelta(minutes=21)][BTC_INST] == D(".05")
    assert output[START + timedelta(minutes=32)] == {}
    assert audit["W028"]["counters"]["equity_only_rebalance_actions"] == 1

    zero_rows, zero_audit = source_actions({"W028": [ep]}, ("W028",), source_nav(zero=True))
    zero_targets = {time: updates["W028"] for time, updates in zero_rows}
    assert START + timedelta(minutes=21) not in zero_targets
    # Source closure is still observed; non-positive NAV cannot block exiting.
    assert zero_targets[START + timedelta(minutes=32)] == {}
    assert zero_audit["W028"]["counters"]["skipped_sizing_decisions_NONPOSITIVE_SOURCE_EQUITY"] == 1


def test_immutable_a_b_equity_source_sha_and_alias_bound(tmp_path):
    ab = tmp_path / "g20261102source"
    raw_dir = ab / "raw" / "W028"
    meta_dir = ab / "metadata" / "W028"
    raw_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    stamp = int(START.timestamp() * 1000)
    raw = json.dumps(
        [
            [
                "perpAllTime",
                {
                    "accountValueHistory": [
                        [stamp - 120_000, "100000"],
                        [stamp + 3_600_000, "95000"],
                    ],
                },
            ],
        ]
    ).encode()
    (raw_dir / "portfolio.json").write_bytes(raw)
    metadata = {
        "wallet": "W028",
        "wallet_identity_sha256": SHA,
        "raw_sha256": sha256(raw).hexdigest(),
        "received_at": "2026-11-02T00:00:00+00:00",
    }
    (meta_dir / "portfolio.json").write_text(json.dumps(metadata))
    points, info, digest, received = _private_history(ab, "W028", expected_sha=SHA, source="AB")
    assert len(points) == 2
    assert info["q3_points"] == 1
    assert digest == sha256(raw).hexdigest()
    assert received.startswith("2026-11-02")
    metadata["wallet"] = "W042"
    (meta_dir / "portfolio.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="WALLET_IDENTITY_MISMATCH"):
        _private_history(ab, "W028", expected_sha=SHA, source="AB")


def test_carried_verified_old_price_is_never_order_execution(monkeypatch, tmp_path):
    class FakeNative:
        def __init__(self, _root):
            self.source_days = {}
            self.called = 0

        def get(self, _inst, t):
            self.called += 1
            if self.called > 1:
                raise MarketDataBlocked("MISSING_EXACT_1M_BAR")
            return MinuteBar(t, D("100000"), D("1000000"), SHA)

    monkeypatch.setattr(
        "copytrade_pm.pm_sparse_equity_portfolio.VerifiedHyperliquidMinuteSource",
        FakeNative,
    )
    m = BoundedCarryMinuteMarket(tmp_path, max_minutes=3)
    when = START
    first = m.get("hyperliquid:mainnet:perp:default:BTC", when)
    last = m.get("hyperliquid:mainnet:perp:default:BTC", when + timedelta(minutes=1))
    assert first.timestamp == last.timestamp == when
    assert m.diagnostics["stale_open_price_proxy_bars"] == 1
    with pytest.raises(MarketDataBlocked):
        m.get("hyperliquid:mainnet:perp:default:BTC", when + timedelta(minutes=4))

    account = Account.start(_synthetic_rulebook({BTC_INST}), START.isoformat())
    desired = {"W028": {BTC_INST: D(".06")}}
    counters = Counter()
    _rebalance(
        account,
        desired,
        {BTC_INST: D("100000")},
        {BTC_INST: last},
        counters,
        execution_minute=when + timedelta(minutes=1),
        risk_limits=(D("6000"), D("18000"), D("9000")),
    )
    assert account.quantities.get(BTC_INST, D("0")) == 0
    assert counters["skipped_orders_stale_market_mark"] == 1
    _rebalance(
        account,
        desired,
        {BTC_INST: D("100000")},
        {BTC_INST: first},
        counters,
        execution_minute=when,
        risk_limits=(D("6000"), D("18000"), D("9000")),
    )
    assert account.quantities[BTC_INST] == D(".06")
    account.verify()


def test_capacity_veto_records_missed_follower_delta_and_preserves_account():
    """A thin minute must not be called an executable order."""
    account = Account.start(_synthetic_rulebook({BTC_INST}), START.isoformat())
    target = {"W028": {BTC_INST: D(".06")}}
    counters = Counter()
    # Current minute volume looks ample but is not available at its OPEN.
    current_bar = MinuteBar(START, D("100000"), D("10000000"), SHA)
    _rebalance(
        account,
        target,
        {BTC_INST: D("100000")},
        {BTC_INST: current_bar},
        counters,
        execution_minute=START,
        risk_limits=(D("6000"), D("18000"), D("9000")),
        capacity_enforced=True,
        prior_closed_quote_volume={BTC_INST: D("100")},
    )
    assert account.quantities.get(BTC_INST, D("0")) == 0
    assert counters["capacity_blocked_orders"] == 1
    assert counters["hypothetical_net_orders"] == 0
    account.verify()

    # A later fresh follower quote can catch up to the same source target.
    ample = MinuteBar(START + timedelta(minutes=1), D("100000"), D("10000000"), SHA)
    _rebalance(
        account,
        target,
        {BTC_INST: D("100000")},
        {BTC_INST: ample},
        counters,
        execution_minute=START + timedelta(minutes=1),
        risk_limits=(D("6000"), D("18000"), D("9000")),
        capacity_enforced=True,
        prior_closed_quote_volume={BTC_INST: D("10000000")},
    )
    assert account.quantities[BTC_INST] == D(".06")
    assert counters["hypothetical_net_orders"] == 1
    account.verify()


def test_capacity_stress_cannot_use_same_minute_volume_without_prior_bar():
    account = Account.start(_synthetic_rulebook({BTC_INST}), START.isoformat())
    current_bar = MinuteBar(START, D("100000"), D("10000000"), SHA)
    with pytest.raises(ValueError, match="MISSING_PRIOR_CLOSED_MINUTE_CAPACITY"):
        _rebalance(
            account,
            {"W028": {BTC_INST: D(".06")}},
            {BTC_INST: D("100000")},
            {BTC_INST: current_bar},
            Counter(),
            execution_minute=START,
            capacity_enforced=True,
        )


def test_invalid_exploratory_policy_bounds():
    with pytest.raises(ValueError, match="BOUNDED_CARRY"):
        BoundedCarryMinuteMarket("/tmp", max_minutes=1441)
    with pytest.raises(ValueError, match="INVALID_EXPLORATORY"):
        source_actions({"W028": []}, ("W028",), source_nav(), max_age_days=30)
