"""Cost, latency and stop stress on one immutable synthetic candidate census."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.trader_intelligence import ObservationSnapshot, WalletEvent, WalletIdentity
from copytrade_pm.trader_intelligence_research import FollowerPolicy, MinuteBar
from copytrade_pm.trader_intelligence_stress import replay_follower_sensitivities

NOW = datetime(2026, 10, 12, 10, tzinfo=UTC)
MARKET = "hyperliquid/mainnet:perp:default/BTC"
SHA = sha256(b"synthetic-only").hexdigest()


def snapshot(*, book=True):
    return ObservationSnapshot(
        "predeclared-research",
        (NOW - timedelta(days=1)).isoformat(),
        (WalletIdentity("w1", SHA, cluster="group-a"),),
        (
            WalletEvent(
                event_id="sample-open",
                wallet="w1",
                instrument=MARKET,
                event_at=NOW.isoformat(),
                first_known_at=NOW.isoformat(),
                origin="PROSPECTIVE_OBSERVED",
                position_before="0",
                position_after="1",
                book_complete=book,
                source_equity_usd="1000" if book else None,
                strategy_style="DIRECTIONAL" if book else "UNKNOWN",
            ),
        ),
        "PROSPECTIVE_OBSERVED",
    )


def bars():
    return tuple(
        MinuteBar(
            MARKET,
            (NOW + timedelta(minutes=i)).isoformat(),
            str(100 - i / 10),
            str(100 - i / 10),
            str(100 - i / 10),
            str(100 - i / 10),
            "10000",
        )
        for i in range(40)
    )


def policy():
    return FollowerPolicy(
        delay_seconds=300,
        horizons_minutes=(5, 15),
        stop_distance_bps="100",
        entry_fee_bps="5",
        exit_fee_bps="5",
        entry_slippage_bps="2",
        exit_slippage_bps="2",
        spread_bps="2",
        required_notional_usd="100",
        max_prior_minute_participation="0.01",
        funding_rate_fraction_per_8h="0",
    )


def test_source_winner_follower_loser_and_two_x_cost_is_worse():
    report = replay_follower_sensitivities(
        snapshot(), bars(), policy(), source_pnl_by_event={"sample-open": "200"}
    )
    assert report.original_event_count == 1
    assert len(report.rows) == 2
    row = report.rows[0]
    assert row.source_pnl_usd == "200"
    assert tuple(x.case for x in row.scenarios) == (
        "BASE_300S",
        "DOUBLE_EXECUTION_COST",
        "DELAY_600S",
        "STOP_OR_HORIZON",
    )
    assert float(row.scenarios[0].net_r) < 0
    assert float(row.scenarios[1].net_r) < float(row.scenarios[0].net_r)
    assert row.scenarios[2].entry_at == (NOW + timedelta(minutes=10)).isoformat().replace(
        "+00:00", "Z"
    )
    assert report.economic_evidence_status == "UNATTESTED_HYPOTHETICAL_RESEARCH_ONLY"
    assert report.as_wire()["report_sha256"] == report.report_sha256


def test_funding_credit_never_improves_short_under_doubled_execution_fees():
    original = snapshot()
    short = replace(original.events[0], position_after="-1")
    report = replay_follower_sensitivities(
        replace(original, events=(short,)),
        bars(),
        replace(policy(), funding_rate_fraction_per_8h="0.008"),
    )
    base, double_cost = report.rows[0].scenarios[:2]
    assert float(double_cost.net_r) < float(base.net_r)
    assert float(double_cost.cost_r) > float(base.cost_r)


def test_stop_stress_is_a_separate_hypothetical_exit_rule():
    report = replay_follower_sensitivities(snapshot(), bars(), policy())
    stop = report.rows[1].scenarios[3]
    base = report.rows[1].scenarios[0]
    assert stop.policy_sha256 != base.policy_sha256
    assert stop.status == "STOP_PROXY_FILLED"
    assert stop.exit_at < base.exit_at


def test_missing_book_or_market_is_never_zero_pnl():
    blocked = replay_follower_sensitivities(snapshot(book=False), bars(), policy())
    for row in blocked.rows:
        assert all(s.status == "INCOMPLETE_OR_UNKNOWN_BOOK" for s in row.scenarios)
        assert all(s.net_r is None for s in row.scenarios)
    missing_market = replay_follower_sensitivities(snapshot(), (), policy())
    assert all(
        s.net_r is None and s.status == "MISSING_FOLLOWER_ENTRY"
        for row in missing_market.rows
        for s in row.scenarios
    )


def test_restart_ordering_and_market_digest():
    shuffled = tuple(reversed(bars()))
    initial = replay_follower_sensitivities(snapshot(), bars(), policy())
    repeated = replay_follower_sensitivities(snapshot(), shuffled, policy())
    assert initial == repeated
    new = list(bars())
    new[-1] = replace(new[-1], base_volume="9999")
    modified = replay_follower_sensitivities(snapshot(), new, policy())
    assert modified.market_input_sha256 != initial.market_input_sha256


def test_base_contract_and_duplicate_market_bars_fail_closed():
    with pytest.raises(ValueError, match="BASELINE_REQUIRES_FIXED_HORIZON_300_SECONDS"):
        replay_follower_sensitivities(snapshot(), bars(), replace(policy(), delay_seconds=1200))
    first = bars()[0]
    duplicate = replace(first, start_at=first.start_at.replace("+00:00", "Z"))
    with pytest.raises(ValueError, match="DUPLICATE_SENSITIVITY_MARKET_BAR"):
        replay_follower_sensitivities(snapshot(), (*bars(), duplicate), policy())
