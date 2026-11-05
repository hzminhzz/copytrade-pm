"""Falsification tests: $10k filtered source-fill follower sensitivity is not live PnL."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("polars")

from scripts import phase7_major4_10k_filtered_follow as s  # noqa: E402


def row(
    ms: int,
    action: str,
    side: str,
    *,
    coin: str = "BTC",
    size: float = 1.0,
    start: float | None = None,
) -> dict:
    return {
        "ms": ms,
        "coin": coin,
        "size": size,
        "price": 100.0,
        "side": side,
        "dir": action,
        "start": start,
        "row_order": 0,
        "source_tid": None,
        "alias": "TEST",
    }


def bars(n: int) -> dict:
    return {
        coin: {
            "open": np.full(n, 100.0, dtype=np.float64),
            "close": np.full(n, 100.0, dtype=np.float64),
            "high": np.full(n, 101.0, dtype=np.float64),
            "low": np.full(n, 99.0, dtype=np.float64),
        }
        for coin in s.MAJORS
    }


def test_raw_same_ms_chain_restored_without_trusting_trade_id_order() -> None:
    ms = s.START_MS + 500
    first = row(ms, "Open Long", "B", size=2, start=0)
    second = row(ms, "Open Long", "B", size=1, start=2)
    first["row_order"], first["source_tid"] = 99, 500000
    second["row_order"], second["source_tid"] = 1, 1
    sorted_events, audit = s._recover_anchored_timestamp_order([second, first])
    assert [x["start"] for x in sorted_events] == [0, 2]
    assert audit["restored_same_ms_groups"] == 1
    assert audit.get("between_timestamp_source_position_gaps", 0) == 0


def test_raw_missing_same_ms_chain_fails_instead_of_inventing_order() -> None:
    ms = s.START_MS + 500
    first = row(ms, "Open Long", "B", size=2, start=0)
    unrelated = row(ms, "Open Long", "B", size=1, start=20)
    with pytest.raises(ValueError, match="AMBIGUOUS_SAME_MS_SOURCE_POSITION_GRAPH"):
        s._recover_anchored_timestamp_order([first, unrelated])


def test_raw_between_timestamp_position_gap_fails_closed() -> None:
    a = row(s.START_MS + 500, "Open Long", "B", size=1, start=0)
    b = row(s.START_MS + 60500, "Close Long", "A", size=1, start=5)
    with pytest.raises(ValueError, match="RAW_FILL_POSITION_CHAIN_NOT_CONTINUOUS"):
        s._recover_anchored_timestamp_order([a, b])


def test_unknown_opening_book_close_is_not_new_short() -> None:
    audit = s.Counter()
    unknown = row(s.START_MS + 1000, "Close Long", "A", size=3)
    assert s._source_update(0, unknown, audit, source_mode="anchored_or_episode") == 0
    assert audit["unknown_preexisting_close_or_unmatched_side"] == 1
    opened = row(s.START_MS + 2000, "Open Long", "B", size=2)
    assert s._source_update(0, opened, audit, source_mode="anchored_or_episode") == 2
    assert s._source_update(2, unknown, audit, source_mode="anchored_or_episode") == 0
    assert audit["overclosing_unanchored_episode"] == 1


def test_raw_start_position_takes_precedence_over_flat_inference() -> None:
    audit = s.Counter()
    ev = row(s.START_MS + 1000, "Close Long", "A", size=1, start=4)
    assert s._source_update(0, ev, audit, source_mode="anchored_or_episode") == 3
    assert s._source_update(0, ev, s.Counter(), source_mode="signed_delta") == -1
    assert audit["anchored_events"] == 1


def test_delayed_next_open_and_post_delay_market_rally(monkeypatch) -> None:
    n = 32
    monkeypatch.setattr(s, "N", n)
    info = bars(n)
    info["BTC"]["open"][6:] = 101
    info["BTC"]["close"][6:] = 101
    info["BTC"]["open"][8:] = 105
    info["BTC"]["close"][8:] = 105
    info["BTC"]["open"][13:] = 105
    info["BTC"]["close"][13:] = 105
    events = [
        row(s.START_MS + 1_000, "Open Long", "B"),
        row(s.START_MS + 7 * 60_000 + 1_000, "Close Long", "A"),
    ]
    result = s.model_wallet(events, info, delay_minutes=5)
    # open at index 6, close at index 13 (after event+5m)
    assert result["audit"]["execution_batches"] == 2
    assert result["turnover_per_budget_usd"][6] == pytest.approx(1)
    assert result["turnover_per_budget_usd"][13] > 0
    assert sum(result["pnl_delta_per_budget_usd"]) == pytest.approx(4 / 101)
    assert result["pnl_delta_per_budget_usd"][:6].sum() == 0


def test_no_leader_trade_after_end_is_executed(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 12)
    events = [row(s.START_MS + 10 * 60_000, "Open Long", "B")]
    result = s.model_wallet(events, bars(12))
    assert result["audit"]["unexecuted_tail_source_events"] == 1
    assert result["turnover_per_budget_usd"].sum() == 0


def test_five_minute_batch_grid_waits_and_collapses_source_fills(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 25)
    market = bars(25)
    market["BTC"]["open"][12:] = 105
    market["BTC"]["close"][12:] = 105
    events = [
        row(s.START_MS + 1_000, "Open Long", "B", size=1),
        row(s.START_MS + 1 * 60_000 + 1_000, "Open Long", "B", size=1),
        row(s.START_MS + 7 * 60_000 + 1_000, "Close Long", "A", size=2),
    ]
    report = s.model_wallet(events, market, delay_minutes=5, batch_minutes=5)
    assert report["audit"]["execution_batches"] == 2
    assert report["turnover_per_budget_usd"][6] == 0
    assert report["turnover_per_budget_usd"][10] == pytest.approx(1)
    assert report["turnover_per_budget_usd"][15] > 0
    assert report["pnl_delta_per_budget_usd"].sum() == pytest.approx(5 / 100)


def test_csv_exact_duplicate_sensitivity_keeps_first_and_never_discards_tid() -> None:
    duplicate = row(s.START_MS + 1_000, "Open Long", "B")
    original = {**duplicate, "source_tid": 125}
    rows = [duplicate, {**duplicate, "row_order": 3}, original]
    reduced = s._remove_csv_exact_duplicates(rows)
    assert len(reduced) == 2
    assert reduced[0] is duplicate
    assert reduced[1] is original


def test_zero_delay_is_still_next_full_minute(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 12)
    events = [row(s.START_MS, "Open Long", "B")]
    result = s.model_wallet(events, bars(12), delay_minutes=0)
    assert result["turnover_per_budget_usd"][0] == 0
    assert result["turnover_per_budget_usd"][1] > 0


def test_utc_day_equity_refs_and_recovered_intraday_loss(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 2 * 1440)
    monkeypatch.setattr(s, "N_DAYS", 2)
    pnl = np.zeros(s.N)
    worst = np.zeros(s.N)
    turn = np.zeros(s.N)
    pnl[50] = -500
    pnl[150] = 600
    worst[:] = pnl
    report = s._metrics(pnl, worst, turn, cost_bps=20)
    assert report["net_pnl_usd"] == 100
    assert report["ending_equity_usd"] == 10100
    assert report["max_drawdown_close_only_usd"] == 500
    assert report["worst_worst_bar_day_from_utc_start_usd"] == -500
    assert report["days_worst_bar_daily_loss_at_least_450"] == 1
    assert report["earliest_model_reference_breach_minute"] == 50


def test_more_costs_reduce_net_returns_and_all_costs_are_two_sided(monkeypatch) -> None:
    monkeypatch.setattr(s, "N", 1440)
    monkeypatch.setattr(s, "N_DAYS", 1)
    pnl = np.zeros(s.N)
    turn = np.zeros(s.N)
    worst = np.zeros(s.N)
    pnl[20] = 25
    turn[15] = 250
    turn[-1] = 250
    low = s._metrics(pnl, worst, turn, cost_bps=10)
    high = s._metrics(pnl, worst, turn, cost_bps=30)
    assert low["net_pnl_usd"] == pytest.approx(24.5)
    assert high["net_pnl_usd"] == pytest.approx(23.5)
    assert high["modeled_composite_cost_usd"] == 1.5


def test_source_fill_input_requires_valid_side_and_start_position() -> None:
    raw = {
        "coin": "BTC",
        "time": s.START_MS + 1000,
        "sz": "1",
        "px": "100",
        "side": "B",
        "dir": "Open Long",
        "tid": 10,
        "startPosition": "0.0",
    }
    event = s.parse_fill(raw, alias="TEST", raw=True, row_index=0)
    assert event["start"] == 0
    bad = {**raw, "side": "A"}
    with pytest.raises(ValueError, match="SOURCE_DIR_AND_SIDE_CONFLICT"):
        s.parse_fill(bad, alias="TEST", raw=True, row_index=0)


def test_zero_start_cross_without_book_is_ignored() -> None:
    audit = s.Counter()
    ev = row(s.START_MS, "Short > Long", "B", size=3)
    assert s._source_update(0, ev, audit, source_mode="anchored_or_episode") == 0
    assert audit["unknown_preexisting_close_or_unmatched_side"] == 1
