"""Three independent wallet pods -> one research-only account with 5m netting.

A historical *oracle* study on partial independently flat-to-flat episodes,
not evidence that a source HyperX fill was observable at that instant.
Replays minute-open equity over full Jul-Sep 2026, including flat intervals.
All source venue/book/missing data exceptions are explicit evidence blockers.
No broker adapter, no live orders, no source account ROI claim.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .pm_fill_replay import _market_instrument
from .pm_hyperx_overlay_audit import examine
from .pm_propr_scope import SCOPE_STRICT, classify_coin
from .pm_quarter_episode_replay import closed_episodes
from .pm_quarter_fill_audit import END, START, save_private_artifact, wallet_fills
from .pm_shadow import (
    MarketDataBlocked,
    MarketSource,
    MinuteBar,
    Scenario,
    VerifiedHyperliquidMinuteSource,
    _VirtualBook,
)
from .pm_sources import load_cohort


D = Decimal
ZERO = D("0")
ONE = D("1")
CAPITAL = D("100000")
PODS = ("W028", "W042", "W030")
POLICIES = ("IMMEDIATE", "FIXED_5M", "BATCH_5M", "ASYMMETRIC_5M")
SCHEMA = "pm36_three_pod_2026q3_historical_oracle_v1"
WAIT = timedelta(minutes=5)
ONE_MINUTE = timedelta(minutes=1)
# Explicit noncontractual research approximations only:
DAILY_LIMIT = D("0.03")
TOTAL_LIMIT = D("0.06")
TARGET = D("0.10")
HEADROOM = D("0.90")  # Keep 10% buffer before the hard notional ceilings.


@dataclass(frozen=True)
class Signal:
    observed_earliest_at: datetime
    source_at: datetime
    wallet: str
    instrument: str
    episode_index: int
    relative_units_per_usdc: D

    def __post_init__(self) -> None:
        if (
            self.wallet not in PODS
            or self.observed_earliest_at.tzinfo is None
            or self.source_at.tzinfo is None
            or self.observed_earliest_at <= self.source_at
            or self.observed_earliest_at >= END
            or not self.relative_units_per_usdc.is_finite()
        ):
            raise ValueError("INVALID_HINDSIGHT_SOURCE_EVENT")


def minute_after(source_at: datetime) -> datetime:
    """Never fill before or at an unknown source-trade clock."""
    return VerifiedHyperliquidMinuteSource._minute(source_at + timedelta(microseconds=1))


def prepare_signals(
    source_episodes: dict[str, list],
    market: MarketSource,
    public_snapshot: dict,
    *,
    extra_mark_minutes: int = 5,
) -> tuple[list[Signal], dict]:
    """Require continuous native 1m opens through *entire* episode and delay.

    This historical complete-episode filter is selection-biased, must never
    be represented as causal prospective observation or whole-manager NAV.
    """
    if set(source_episodes) != set(PODS) or extra_mark_minutes < 0:
        raise ValueError("THREE_POD_EXACT_COHORT_REQUIRED")
    if public_snapshot.get("not_proof_of_historical_availability") is not True:
        raise ValueError("POSTPERIOD_PROPR_SCOPE_NOT_DISCLAIMED")
    counters: dict[str, Counter] = {pod: Counter() for pod in PODS}
    events = []
    for pod in PODS:
        for index, episode in enumerate(source_episodes[pod]):
            stat = counters[pod]
            stat["all_completed_source_episodes"] += 1
            if episode.wallet != pod or not episode.rows:
                raise ValueError("EPISODE_WALLET_IDENTITY_CHANGED")
            if classify_coin(episode.coin, public_snapshot) != SCOPE_STRICT:
                stat["excluded_not_strict_native_propr_display_match"] += 1
                continue
            try:
                instrument = _market_instrument(episode.coin)
            except MarketDataBlocked:
                stat["excluded_unmapped_instrument"] += 1
                continue
            first = episode.rows[0]
            last = episode.rows[-1]
            if (
                first.before != ZERO
                or first.after == ZERO
                or first.price <= ZERO
                or last.after != ZERO
                or first.timestamp < START
                or last.timestamp >= END
            ):
                raise ValueError("UNANCHORED_OR_OUT_OF_Q3_SOURCE_EPISODE")
            begin = minute_after(first.timestamp)
            final = minute_after(last.timestamp) + timedelta(minutes=extra_mark_minutes)
            if final >= END:
                stat["excluded_delayed_exit_beyond_quarter"] += 1
                continue
            mark = begin
            block = None
            while mark <= final:
                try:
                    market.get(instrument, mark)
                except MarketDataBlocked as exc:
                    block = str(exc).split(":", 1)[0]
                    break
                mark += ONE_MINUTE
            if block is not None:
                stat["excluded_missing_exact_continuous_market"] += 1
                stat["market_block_" + block] += 1
                continue
            reference_qty = abs(first.after)
            ref_px = first.price
            if reference_qty == ZERO:
                raise ValueError("ZERO_SOURCE_FIRST_POSITION")
            for event in episode.rows:
                timestamp = minute_after(event.timestamp)
                if timestamp > final:
                    raise ValueError("SOURCE_EPISODE_MARK_RANGE_BROKEN")
                relative = event.after / (reference_qty * ref_px)
                events.append(Signal(timestamp, event.timestamp, pod, instrument, index, relative))
            stat["included_flat_to_flat_episodes"] += 1
            stat["included_raw_source_fills"] += len(episode.rows)
    events.sort(
        key=lambda x: (
            x.observed_earliest_at,
            x.source_at,
            x.wallet,
            x.instrument,
            x.episode_index,
        )
    )
    return events, {
        "per_pod": {pod: dict(counters[pod]) for pod in PODS},
        "included_source_events": len(events),
        "distinct_source_event_minutes": len({e.observed_earliest_at for e in events}),
        "instruments": sorted({e.instrument for e in events}),
        "source_timestamp_is_not_first_known": True,
        "episode_filter_requires_future_close_and_full_market_coverage": True,
    }


def target_quantities(
    states: dict[tuple[str, str], D],
    marks: dict[str, D],
    *,
    per_episode_notional: D,
    per_pod_cap: D,
    global_gross_cap: D,
    single_instrument_cap: D,
) -> dict[str, D]:
    """Virtual pod positions first, shared net positions second.

    No forward PnL, no source equity assumption; never give a pod an
    unbounded number of independent entry tickets.
    """
    if not (
        ZERO < per_episode_notional <= per_pod_cap
        and per_pod_cap.is_finite()
        and global_gross_cap.is_finite()
        and global_gross_cap > ZERO
        and ZERO < single_instrument_cap <= global_gross_cap
    ):
        raise ValueError("INVALID_PORTFOLIO_CAPS")
    by_pod = defaultdict(dict)
    for (pod, symbol), rel in states.items():
        if pod not in PODS or symbol not in marks or not marks[symbol].is_finite():
            raise ValueError("UNKNOWN_POD_OR_UNPRICED_POSITION")
        if marks[symbol] <= ZERO:
            raise ValueError("INVALID_TARGET_PRICE")
        if rel:
            by_pod[pod][symbol] = rel * per_episode_notional
    desired = defaultdict(lambda: ZERO)
    for pod, positions in by_pod.items():
        gross = sum((abs(q * marks[s]) for s, q in positions.items()), ZERO)
        fraction = min(ONE, per_pod_cap / gross) if gross else ONE
        for symbol, qty in positions.items():
            desired[symbol] += qty * fraction
    for symbol, qty in list(desired.items()):
        allowed = single_instrument_cap / marks[symbol]
        if abs(qty) > allowed:
            desired[symbol] = (ONE if qty > ZERO else -ONE) * allowed
    gross = sum((abs(qty * marks[symbol]) for symbol, qty in desired.items()), ZERO)
    if gross > global_gross_cap:
        scalar = global_gross_cap / gross
        desired = {symbol: qty * scalar for symbol, qty in desired.items()}
    return {symbol: qty for symbol, qty in desired.items() if qty != ZERO}


def _risk_is_reducing(current: D, requested: D) -> bool:
    return current != ZERO and (requested * current <= ZERO or abs(requested) < abs(current))


def _account_equity(book: _VirtualBook, marks: dict[str, D]) -> D:
    return (
        CAPITAL
        + sum(book.flows.values(), ZERO)
        + sum((qty * marks[symbol] for symbol, qty in book.positions.items()), ZERO)
    )


def replay_policy(
    events: list[Signal],
    market: MarketSource,
    *,
    policy: str,
    per_episode_notional: D,
    per_pod_cap: D,
    global_gross_cap: D,
    single_instrument_cap: D,
    end_at: datetime = END,
    taker_fee_bps: D = D("5"),
    spread_bps: D = D("3"),
    slippage_bps: D = D("5"),
) -> dict:
    if policy not in POLICIES:
        raise ValueError("UNKNOWN_EXECUTION_POLICY")
    if end_at.tzinfo is None or not START < end_at <= END or (end_at - START) % ONE_MINUTE:
        raise ValueError("INVALID_EVALUATION_INTERVAL")
    if any(b.observed_earliest_at < a.observed_earliest_at for a, b in zip(events, events[1:])):
        raise ValueError("NONMONOTONIC_SOURCE_ARRIVAL")
    target_quantities(
        {},
        {},
        per_episode_notional=per_episode_notional,
        per_pod_cap=per_pod_cap,
        global_gross_cap=global_gross_cap,
        single_instrument_cap=single_instrument_cap,
    )
    model = Scenario(
        "RESEARCH_" + policy,
        5,
        CAPITAL,
        D("0.001"),
        max_gross_leverage=D("1"),
        taker_fee_bps=taker_fee_bps,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        funding_abs_bps_per_8h=D("1"),
        max_minute_participation=D("0.05"),
    )
    # Available signals may be deferred by FIXED_5M, but all other policies
    # see only source events at or before each evaluation minute.
    scheduled: dict[datetime, list[Signal]] = defaultdict(list)
    for ev in events:
        receive = ev.observed_earliest_at + (WAIT if policy == "FIXED_5M" else timedelta())
        if receive >= end_at:
            raise ValueError("SIGNAL_AFTER_STUDY_END")
        scheduled[receive].append(ev)
    latest: dict[tuple[str, str], D] = {}
    pending: dict[str, datetime] = {}
    urgent_reduction: set[str] = set()
    book = _VirtualBook()
    counters = Counter()
    peak = CAPITAL
    max_drawdown = ZERO
    max_daily_loss = ZERO
    maximum_gross = ZERO
    day_start_equity = CAPITAL
    day = START.date()
    end_equity = CAPITAL
    decision_at = None
    status = "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
    daily_equity: dict[str, str] = {}
    first_order_at = None
    last_order_at = None
    previous = None
    price_gap_reason = None
    last_at = None
    for index in range(int((end_at - START) / ONE_MINUTE)):
        at = START + timedelta(minutes=index)
        last_at = at
        source = scheduled.get(at, [])
        required_symbols = (
            {s for _, s in latest}
            | set(book.positions)
            | urgent_reduction
            | {e.instrument for e in source}
        )
        quotes = {}
        try:
            for symbol in sorted(required_symbols):
                quotes[symbol] = market.get(symbol, at)
        except MarketDataBlocked as exc:
            price_gap_reason = str(exc).split(":", 1)[0]
            status = "BLOCKED_ACTIVE_MARKET_DATA"
            decision_at = at.isoformat()
            break
        marks = {symbol: bar.open for symbol, bar in quotes.items()}
        if previous is not None and book.positions:
            book.accrue_funding(marks, ONE_MINUTE, model)
        previous = at
        pre_equity = _account_equity(book, marks)
        current_gross = sum((abs(q * marks[s]) for s, q in book.positions.items()), ZERO)
        maximum_gross = max(maximum_gross, current_gross)
        if current_gross > global_gross_cap:
            counters["marked_global_gross_overcap_minutes"] += 1
        if at.date() != day:
            # PM-03 contract requires independent balance evidence. This
            # research-only proxy resets at UTC midnight minute-open equity.
            day_start_equity = pre_equity
            day = at.date()
        peak = max(peak, pre_equity)
        max_drawdown = max(max_drawdown, peak - pre_equity)
        max_daily_loss = max(max_daily_loss, day_start_equity - pre_equity)
        if pre_equity <= max(
            CAPITAL * (ONE - TOTAL_LIMIT),
            day_start_equity - CAPITAL * DAILY_LIMIT,
        ):
            status = "SAMPLED_CHALLENGE_LOSS_FLOOR_TOUCH"
            decision_at = at.isoformat()
            end_equity = pre_equity
            break
        if pre_equity >= CAPITAL * (ONE + TARGET):
            status = "SAMPLED_CHALLENGE_PROFIT_TARGET_TOUCH"
            decision_at = at.isoformat()
            end_equity = pre_equity
            break
        changed = set()
        for ev in source:
            key = (ev.wallet, ev.instrument)
            if ev.relative_units_per_usdc == ZERO:
                latest.pop(key, None)
            else:
                latest[key] = ev.relative_units_per_usdc
            changed.add(ev.instrument)
            counters["processed_source_fills"] += 1
        desired = (
            target_quantities(
                latest,
                marks,
                per_episode_notional=per_episode_notional,
                per_pod_cap=per_pod_cap,
                global_gross_cap=global_gross_cap * HEADROOM,
                single_instrument_cap=single_instrument_cap * HEADROOM,
            )
            if changed or pending or urgent_reduction
            else {}
        )
        requests = {}
        if policy in ("IMMEDIATE", "FIXED_5M"):
            requests = {symbol: desired.get(symbol, ZERO) for symbol in changed}
        else:
            for symbol in changed:
                pending.setdefault(symbol, at + WAIT)
            due = {symbol for symbol, deadline in pending.items() if deadline <= at}
            requests.update({symbol: desired.get(symbol, ZERO) for symbol in due})
            for symbol in due:
                if desired.get(symbol, ZERO) == book.positions.get(symbol, ZERO):
                    counters["canceled_or_unneeded_batch"] += 1
                del pending[symbol]
            if policy == "ASYMMETRIC_5M":
                for symbol in changed:
                    current = book.positions.get(symbol, ZERO)
                    goal = desired.get(symbol, ZERO)
                    if _risk_is_reducing(current, goal):
                        if goal * current < ZERO:
                            # Close now, stage opposite-side NEW risk later.
                            requests[symbol] = ZERO
                            pending[symbol] = at + WAIT
                            counters["immediate_reversal_flatten"] += 1
                        else:
                            requests[symbol] = goal
                            pending.pop(symbol, None)
                        counters["immediate_risk_reduction"] += 1
        # A previous reduction that lacked enough minute volume is never
        # silently marked complete. Retry its unfilled remainder at the
        # next independently observed minute open, before accepting new risk.
        for symbol in list(urgent_reduction):
            current = book.positions.get(symbol, ZERO)
            wanted = desired.get(symbol, ZERO)
            if not _risk_is_reducing(current, wanted):
                urgent_reduction.remove(symbol)
            else:
                requests[symbol] = wanted
        # Gross caps apply to *marked current inventory*, not just the
        # next source update. A price rally can push live notional beyond
        # a target sized under earlier prices; force a reduction each minute.
        if current_gross > global_gross_cap or any(
            abs(q * marks[s]) > single_instrument_cap for s, q in book.positions.items()
        ):
            global_fraction = min(ONE, global_gross_cap / current_gross) if current_gross else ONE
            for symbol, current in book.positions.items():
                allowed = current * global_fraction
                max_qty = single_instrument_cap / marks[symbol]
                if abs(allowed) > max_qty:
                    allowed = (ONE if allowed > ZERO else -ONE) * max_qty
                desired_now = requests.get(symbol, current)
                if abs(allowed) < abs(current) and (
                    desired_now * current < ZERO or abs(desired_now) > abs(allowed)
                ):
                    requests[symbol] = ZERO if desired_now * current < ZERO else allowed
                    counters["forced_marked_gross_risk_reductions"] += 1
        updates = {}
        for symbol, goal in requests.items():
            if goal != book.positions.get(symbol, ZERO):
                updates[symbol] = goal
            elif symbol in changed:
                counters["net_zero_order"] += 1
        if updates:
            # The full volume of minute t is not available at open(t).
            # Use the just-completed t-1 quote volume as a *capacity proxy*
            # while executing at open(t), with no future-minute access.
            execution_quotes = {}
            for symbol in list(updates):
                try:
                    previous_bar = market.get(symbol, at - ONE_MINUTE)
                except MarketDataBlocked as exc:
                    if _risk_is_reducing(book.positions.get(symbol, ZERO), updates[symbol]):
                        price_gap_reason = "PREVIOUS_COMPLETE_MINUTE_VOLUME_MISSING:" + str(exc)
                        status = "BLOCKED_REDUCTION_CAPACITY_EVIDENCE"
                        decision_at = at.isoformat()
                        break
                    counters["skipped_new_risk_missing_prior_volume"] += 1
                    del updates[symbol]
                    continue
                execution_quotes[symbol] = MinuteBar(
                    at,
                    quotes[symbol].open,
                    previous_bar.quote_volume,
                    quotes[symbol].source_sha256,
                )
            if status.startswith("BLOCKED"):
                end_equity = pre_equity
                break
            # Pretrade participation is capped against lagged observed
            # minute volume. Risk reductions may split over later minutes.
            for symbol in list(updates):
                delta = updates[symbol] - book.positions.get(symbol, ZERO)
                order_notional = abs(delta * marks[symbol])
                if execution_quotes[symbol].quote_volume <= ZERO or order_notional > (
                    execution_quotes[symbol].quote_volume * model.max_minute_participation
                ):
                    current = book.positions.get(symbol, ZERO)
                    goal = updates[symbol]
                    if _risk_is_reducing(current, goal):
                        remaining_qty = abs(goal - current)
                        usable_quote = max(
                            ZERO,
                            execution_quotes[symbol].quote_volume * model.max_minute_participation,
                        )
                        # Decimal division can round a volume-edge quantity
                        # *above* the exact 5% limit when multiplied back.
                        # Leave a deterministic conservative capacity buffer.
                        max_qty = usable_quote * D("0.9999") / marks[symbol]
                        if current * goal < ZERO:
                            # A cross-through-zero order would mix immediate
                            # exit with new risk. Exit first; the new side
                            # requires its own later approval and timer.
                            remaining_qty = abs(current)
                            goal = ZERO
                            counters["reversal_new_risk_withheld"] += 1
                        fill_qty = min(remaining_qty, max_qty)
                        if fill_qty <= ZERO:
                            del updates[symbol]
                            urgent_reduction.add(symbol)
                            counters["zero_volume_exit_retry_minutes"] += 1
                            continue
                        direction = ONE if goal > current else -ONE
                        next_qty = current + direction * fill_qty
                        updates[symbol] = next_qty
                        if next_qty != goal:
                            urgent_reduction.add(symbol)
                            counters["partial_exit_rebalance_orders"] += 1
                        else:
                            urgent_reduction.discard(symbol)
                    else:
                        counters["skipped_new_risk_liquidity"] += 1
                        del updates[symbol]
                else:
                    urgent_reduction.discard(symbol)
            if updates:
                book.rebalance(
                    {
                        **book.positions,
                        **{s: q for s, q in updates.items() if q != ZERO},
                        **{s: ZERO for s, q in updates.items() if q == ZERO},
                    },
                    execution_quotes,
                    model,
                )
                counters["executed_trade_minutes"] += 1
                if first_order_at is None:
                    first_order_at = at.isoformat()
                last_order_at = at.isoformat()
        next_equity = _account_equity(book, marks)
        end_equity = next_equity
        peak = max(peak, next_equity)
        max_drawdown = max(max_drawdown, peak - next_equity)
        max_daily_loss = max(max_daily_loss, day_start_equity - next_equity)
        maximum_gross = max(
            maximum_gross,
            sum((abs(q * marks[s]) for s, q in book.positions.items()), ZERO),
        )
        if next_equity <= max(
            CAPITAL * (ONE - TOTAL_LIMIT),
            day_start_equity - CAPITAL * DAILY_LIMIT,
        ):
            status = "SAMPLED_CHALLENGE_LOSS_FLOOR_TOUCH"
            decision_at = at.isoformat()
            break
        if next_equity >= CAPITAL * (ONE + TARGET):
            status = "SAMPLED_CHALLENGE_PROFIT_TARGET_TOUCH"
            decision_at = at.isoformat()
            break
        if at + ONE_MINUTE == end_at or (at + ONE_MINUTE).date() != at.date():
            daily_equity[at.date().isoformat()] = str(next_equity)
    if status.startswith("COMPLETE") and (book.positions or latest or pending or urgent_reduction):
        status = "BLOCKED_NONFLAT_AT_QUARTER_CUTOFF"
    return {
        "policy": policy,
        "per_episode_notional_usdc": str(per_episode_notional),
        "per_pod_cap_usdc": str(per_pod_cap),
        "global_gross_cap_usdc": str(global_gross_cap),
        "single_instrument_cap_usdc": str(single_instrument_cap),
        "status": status,
        "first_execution_at": first_order_at,
        "last_execution_at": last_order_at,
        "event_or_end_at": decision_at or last_at.isoformat(),
        "terminal_equity_usdc": str(end_equity),
        "net_pnl_usdc": str(end_equity - CAPITAL),
        "sampled_max_drawdown_usdc": str(max_drawdown),
        "sampled_max_daily_loss_usdc": str(max_daily_loss),
        "max_observed_gross_usdc": str(maximum_gross),
        "hypothetical_market_order_count": book.fills,
        "modeled_turnover_usdc": str(book.turnover),
        "modeled_fees_usdc": str(book.fees),
        "modeled_spread_slippage_usdc": str(book.impact),
        "modeled_funding_usdc": str(book.funding),
        "event_counts": dict(counters),
        "data_blocker": price_gap_reason,
        "unresolved_risk_reduction_instruments": len(urgent_reduction),
        "daily_sampled_equity_usdc": daily_equity,
        "source_clock_is_hindsight_oracle": True,
        "risk_floors_are_1m_open_only": True,
        "execution_volume_uses_only_previously_completed_minute": True,
        "marked_gross_cap_can_temporarily_overshoot_before_partial_reduction": True,
        "daily_reset_is_equity_proxy_not_official_balance": True,
        "missing_hedges_and_unclosed_episodes_not_modeled": True,
        "pass_probability": None,
        "broker_executed": False,
    }


def run(
    root: Path,
    market_root: Path,
    snapshot: Path,
    *,
    generations: tuple[Path, ...],
    budgets: tuple[D, ...],
) -> dict:
    if budgets != (D("100"), D("500"), D("2000")):
        raise ValueError("UNAPPROVED_RESEARCH_SIZING_GRID")
    public = json.loads(snapshot.read_bytes())
    if (
        public.get("schema") != "propr_public_universe_browser_snapshot_v1"
        or public.get("retrieved_on_utc_date") != "2026-10-30"
        or public.get("not_proof_of_historical_availability") is not True
    ):
        raise ValueError("INVALID_POSTPERIOD_MARKET_SNAPSHOT")
    entries, manifests = load_cohort(root)
    cohort = {entry.alias: entry for entry in entries}
    if not set(PODS).issubset(cohort) or len(entries) != 36:
        raise ValueError("COHORT_NOT_FROZEN_36_WALLETS")
    overlay, verified = examine(root, generations)
    if overlay["wallet_count"] != 36 or not overlay["original_vendor_cache_intact"]:
        raise ValueError("UNVERIFIED_OVERLAY")
    episodes = {}
    source_diagnostics = {}
    for pod in PODS:
        rows, _ = wallet_fills(
            root,
            cohort[pod],
            generations=generations,
            verified_additions=verified.get(pod, []),
        )
        episodes[pod], detail = closed_episodes(pod, rows)
        source_diagnostics[pod] = dict(detail)
    market = VerifiedHyperliquidMinuteSource(market_root)
    signals, coverage = prepare_signals(episodes, market, public)
    scenarios = []
    for budget in budgets:
        for policy in POLICIES:
            scenarios.append(
                replay_policy(
                    signals,
                    market,
                    policy=policy,
                    per_episode_notional=budget,
                    per_pod_cap=budget * D("5"),
                    global_gross_cap=min(CAPITAL * D("0.5"), budget * D("15")),
                    single_instrument_cap=budget * D("6"),
                )
            )
    scenarios_by_key = {(x["per_episode_notional_usdc"], x["policy"]): x for x in scenarios}
    # Cost stress (fees, spread and slippage): do not silently select a
    # delay on a single optimistic commission/slippage estimate.
    stressed = []
    for multiplier in (D("2"), D("3")):
        for budget in budgets:
            for policy in POLICIES:
                outcome = replay_policy(
                    signals,
                    market,
                    policy=policy,
                    per_episode_notional=budget,
                    per_pod_cap=budget * D("5"),
                    global_gross_cap=min(CAPITAL * D("0.5"), budget * D("15")),
                    single_instrument_cap=budget * D("6"),
                    taker_fee_bps=D("5") * multiplier,
                    spread_bps=D("3") * multiplier,
                    slippage_bps=D("5") * multiplier,
                )
                stressed.append(
                    {
                        "cost_multiplier": str(multiplier),
                        "budget_usdc": str(budget),
                        "policy": policy,
                        "status": outcome["status"],
                        "net_pnl_usdc": outcome["net_pnl_usdc"],
                        "hypothetical_market_order_count": outcome[
                            "hypothetical_market_order_count"
                        ],
                        "sampled_max_drawdown_usdc": outcome["sampled_max_drawdown_usdc"],
                    }
                )
    comparisons = []
    for budget in budgets:
        baseline = scenarios_by_key[(str(budget), "IMMEDIATE")]
        for policy in POLICIES[1:]:
            challenger = scenarios_by_key[(str(budget), policy)]
            comparable = (
                baseline["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
                and challenger["status"] == "COMPLETE_HISTORICAL_ORACLE_NO_TARGET"
            )
            comparisons.append(
                {
                    "budget_usdc": str(budget),
                    "reference": "IMMEDIATE",
                    "challenger": policy,
                    "full_quarter_comparison_valid": comparable,
                    "delta_net_pnl_usdc": (
                        str(D(challenger["net_pnl_usdc"]) - D(baseline["net_pnl_usdc"]))
                        if comparable
                        else None
                    ),
                    "order_count_reduction_pct": (
                        str(
                            (
                                ONE
                                - D(challenger["hypothetical_market_order_count"])
                                / D(baseline["hypothetical_market_order_count"])
                            )
                            * D("100")
                        )
                        if comparable and baseline["hypothetical_market_order_count"]
                        else None
                    ),
                }
            )
    return {
        "schema": SCHEMA,
        "study_start_inclusive": START.isoformat(),
        "study_end_exclusive": END.isoformat(),
        "study_days": (END - START).days,
        "source_cohort_wallet_count": len(entries),
        "selected_pods": list(PODS),
        "wallet_selection": "POST_HOC_EXPLORATORY_2026Q3_SELECTION_NO_HOLDOUT",
        "source_contract_shas": manifests,
        "verified_generation_provenance": overlay["private_generations"],
        "propr_postperiod_display_sha256": sha256(snapshot.read_bytes()).hexdigest(),
        "source_episode_diagnostics": source_diagnostics,
        "research_eligible_event_gate": coverage,
        "market_verified_instrument_days": len(market.source_days),
        "market_consumed_day_shas": dict(sorted(market.source_days.items())),
        "scenario_results": scenarios,
        "policy_comparisons": comparisons,
        "execution_cost_stress": stressed,
        "research_contract": {
            "account_start_usdc": str(CAPITAL),
            "taker_fee_bps": "5",
            "spread_bps": "3",
            "slippage_bps": "5",
            "funding_abs_bps_per_8h": "1",
            "minute_volume_cap": "0.05",
            "target_notional_headroom_fraction": str(HEADROOM),
            "volume_proxy": "PREVIOUS_COMPLETED_1M_QUOTE_VOLUME_NOT_ORDER_BOOK_DEPTH",
            "cost_stress": "1x_BASE_2x_3x_FEES_SPREAD_SLIPPAGE_FUNDING_FIXED",
            "illustrative_daily_loss": str(DAILY_LIMIT),
            "illustrative_total_loss": str(TOTAL_LIMIT),
            "illustrative_profit_target": str(TARGET),
            "source_event_clock_available": "NO_HISTORICAL_ORACLE_ONLY",
            "propr_market_scope_asof_q3": "UNKNOWN_POST_PERIOD_DISPLAY_MATCH_ONLY",
            "whole_wallet_source_book": "NOT_RECONSTRUCTED",
            "intraminute_breach_certified": False,
            "real_market_orders": False,
        },
        "qualified_portfolio": None,
        "qualified_challenge_pass_probability": None,
        "live_risk_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--propr-postperiod-snapshot", required=True, type=Path)
    parser.add_argument("--hyperx-generations", nargs="+", type=Path, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = run(
        args.research_root,
        args.market_root,
        args.propr_postperiod_snapshot,
        generations=tuple(args.hyperx_generations),
        budgets=(D("100"), D("500"), D("2000")),
    )
    path, digest = save_private_artifact(args.out, result, "threepod")
    print(
        json.dumps(
            {
                "selected_pods": list(PODS),
                "eligible_episodes": {
                    pod: result["research_eligible_event_gate"]["per_pod"][pod].get(
                        "included_flat_to_flat_episodes", 0
                    )
                    for pod in PODS
                },
                "scenarios": [
                    {
                        k: x[k]
                        for k in (
                            "policy",
                            "per_episode_notional_usdc",
                            "status",
                            "net_pnl_usdc",
                            "hypothetical_market_order_count",
                            "sampled_max_drawdown_usdc",
                            "data_blocker",
                        )
                    }
                    for x in result["scenario_results"]
                ],
                "comparisons": result["policy_comparisons"],
                "artifact": str(path),
                "sha256": digest,
                "trading_authorized": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
