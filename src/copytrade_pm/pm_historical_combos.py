"""Q3 three-wallet historical replay: source-equity sizing required by default.

Only directly observed flat-to-flat instrument chains are available for Q3.
Without independently reconciled source equity, the correct output is an
explicit equity-denominator blocker and null PnL, not a gross-normalized proxy.
The old non-equity run is opt-in and retained only as immutable prior research.
Even with real historical equity the source path is a hindsight-selected,
incomplete wallet oracle, not prospective trading evidence. PM03 owns cash.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

from .pm03_account import Account, Instrument, Rulebook
from .pm03_execution import _allocate
from .pm_fill_replay import _coins, _market_instrument, _same_position, _source_fills
from .pm_historical_equity import HistoricalEquity, load_equity
from .pm_hyperx_overlay_audit import examine
from .pm_portfolio_e0 import PORTFOLIOS
from .pm_propr_scope import SCOPE_STRICT, SCOPE_TENTATIVE, classify_coin
from .pm_research import _write_private_evidence
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource
from .pm_sources import load_cohort

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)
HOLDOUT_START = datetime(2026, 9, 1, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
WAIT = timedelta(minutes=5)
ZERO = D("0")
CASH = D("10000")
TRAINING_PEAK_WALLET_GROSS_BUDGET = D("2000")
# Research sizing grid only, NOT an exchange lot-size assertion. Prevents
# non-associative repeating-Decimal arithmetic from breaking PM03 exact books.
QUANTITY_GRID = D("0.000000000001")
POD_GROSS_CAP = D("3000")
ACCOUNT_GROSS_CAP = D("9000")
INSTRUMENT_GROSS_CAP = D("5000")
MAX_PARTICIPATION = D("0.05")
FEE_BPS = D("5")
FULL_SPREAD_BPS = D("3")
SLIPPAGE_BPS = D("5")
FUNDING_ABS_BPS_PER_8H = D("1")
SCHEMA = "copytrade_q3_conditional_observed_chains_v1"
EQUITY_SCHEMA = "copytrade_q3_equity_weight_conditional_chains_v1"
POD_CAPITAL_USD = D("2000")
ALL_WALLETS = tuple(dict.fromkeys(wallet for trio in PORTFOLIOS.values() for wallet in trio))


@dataclass(frozen=True)
class Episode:
    wallet: str
    coin: str
    events: tuple[tuple, ...]

    @property
    def start(self) -> datetime:
        return self.events[0][0]

    @property
    def end(self) -> datetime:
        return self.events[-1][0]


def _minute_at_or_after(t: datetime) -> datetime:
    return VerifiedHyperliquidMinuteSource._minute(t)


def _source_episodes(wallet: str, fills: list[tuple]) -> tuple[list[Episode], dict]:
    """Zero-before -> zero-after, contiguous source chain. No assumed prior flat."""
    grouped = defaultdict(list)
    for row in fills:
        grouped[row[2]].append(row)
    found: list[Episode] = []
    counts: Counter = Counter()
    for coin, rows in sorted(grouped.items()):
        active: list[tuple] = []
        prev: D | None = None
        for row in rows:
            _, _, _, before, after, _, _ = row
            if prev is not None and not _same_position(prev, before):
                counts["source_chain_breaks"] += 1
                if active:
                    counts["interrupted_open_episodes"] += 1
                active = []
            prev = after
            if not active:
                if before == ZERO and after != ZERO:
                    active = [row]
                elif before != ZERO:
                    counts["left_censored_observation_rows"] += 1
                continue
            if before == ZERO or (before * after < ZERO):
                counts["unsupported_cross_through_or_restart"] += 1
                active = []
                continue
            active.append(row)
            if after == ZERO:
                counts["total_completed_episodes"] += 1
                if START <= active[0][0] and active[-1][0] < END:
                    found.append(Episode(wallet, coin, tuple(active)))
                else:
                    counts["completed_outside_q3"] += 1
                active = []
        if active:
            counts["open_at_cache_cutoff"] += 1
    found.sort(key=lambda e: (e.start, e.coin))
    counts["q3_completed_episodes"] = len(found)
    return found, dict(counts)


def _native_pm(coin: str) -> Instrument:
    native = _market_instrument(coin)
    parts = native.split(":")
    if len(parts) != 5:
        raise ValueError("NON_NATIVE_COIN")
    return Instrument("hyperliquid", f"mainnet:perp:{parts[3]}", parts[4])


def _quote(market: VerifiedHyperliquidMinuteSource, inst: Instrument, when: datetime):
    parts = inst.market.split(":")
    native = f"{inst.venue}:{parts[0]}:{parts[1]}:{parts[2]}:{inst.symbol}"
    return market.get(native, when)


def _verified_interval(
    episode: Episode, market: VerifiedHyperliquidMinuteSource
) -> tuple[bool, str | None, int]:
    """Entire potential marked holding interval must have exact SHA-backed 1m opens.

    This preselection is ex-post and must NEVER be called a causal portfolio
    selection. Missing one minute removes the entire episode, not a losing bar.
    """
    try:
        inst = _native_pm(episode.coin)
    except MarketDataBlocked as exc:
        return False, str(exc), 0
    begin = _minute_at_or_after(episode.start + WAIT)
    final = _minute_at_or_after(episode.end + WAIT)
    if final >= END:
        return False, "DELAYED_EXIT_OUTSIDE_Q3", 0
    when = begin
    verified = 0
    while when <= final:
        try:
            _quote(market, inst, when)
        except MarketDataBlocked as exc:
            return False, str(exc).split(":", 1)[0], verified
        # Zero-volume 1m opens can still mark an already-held position. Only
        # execution requires positive capacity at the precise order minute.
        verified += 1
        when += MINUTE
    return True, None, verified


def _training_peak_gross(fills: list[tuple]) -> D:
    """Conservative first-62d observed source-book gross, using fill prices.

    Historical trade prices are stale between events; unknown instruments stay
    unknown. Only a sizing reference, NOT a reconstructed wallet NAV or mark.
    """
    book: dict[str, tuple[D, D]] = {}
    peak = ZERO
    for time, _, coin, _, after, _, px in fills:
        if time >= HOLDOUT_START:
            break
        if px <= ZERO:
            continue
        book[coin] = (after, px)
        if time >= START:
            peak = max(peak, sum((abs(q * last_px) for q, last_px in book.values()), ZERO))
    return peak


def _source_inputs(
    root: Path, market: VerifiedHyperliquidMinuteSource, generations: tuple[Path, ...]
):
    entries, fingerprints = load_cohort(root)
    additions: dict[str, list[tuple]] = {}
    overlay_sha: str | None = None
    if generations:
        overlay, additions = examine(root, generations)
        if not overlay["original_vendor_cache_intact"] or overlay["wallet_count"] != 36:
            raise ValueError("INVALID_VERIFIED_HYPERX_OVERLAY")
        overlay_sha = sha256(json.dumps(overlay, sort_keys=True).encode()).hexdigest()
    snapshot_path = root / "PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json"
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    if (
        snapshot.get("schema") != "propr_public_universe_browser_snapshot_v1"
        or snapshot.get("not_proof_of_historical_availability") is not True
    ):
        raise ValueError("INVALID_PUBLIC_DISPLAY_SNAPSHOT")
    by_alias = {entry.alias: entry for entry in entries}
    admitted: dict[str, list[Episode]] = {}
    audits: dict[str, dict] = {}
    scales: dict[str, D | None] = {}
    all_identifiers: set[str] = set()
    for wallet in ALL_WALLETS:
        entry = by_alias[wallet]
        coins = _coins(root, wallet)
        fills, issues = _source_fills(
            root, wallet, entry.address, coins, additional_events=additions.get(wallet)
        )
        fatal = [reason for reason in issues if not reason.endswith(":POSITION_DISCONTINUITY")]
        if fatal:
            admitted[wallet] = []
            scales[wallet] = None
            audits[wallet] = {
                "status": "BLOCKED_SOURCE_CACHE",
                "fatal_reasons": fatal,
                "observed_vendor_coins": len(coins),
            }
            continue
        episodes, counts = _source_episodes(wallet, fills)
        candidates = [
            ep
            for ep in episodes
            if classify_coin(ep.coin, snapshot) in (SCOPE_STRICT, SCOPE_TENTATIVE)
        ]
        excluded = Counter()
        selected = []
        verified_minute_checks = 0
        for ep in candidates:
            ok, why, checks = _verified_interval(ep, market)
            verified_minute_checks += checks
            if ok:
                selected.append(ep)
                all_identifiers.add(_native_pm(ep.coin).key)
            else:
                excluded[str(why)] += 1
        # A single wallet-wide multiplier calibrated on July-August ONLY.
        # Use observed source gross, not a new factor per position or episode.
        # July/August historical trade prices are approximations, not NAV.
        training_peak = _training_peak_gross(fills)
        scales[wallet] = (
            TRAINING_PEAK_WALLET_GROSS_BUDGET / training_peak if training_peak > ZERO else None
        )
        first_seen = {}
        for row in fills:
            if row[0] >= END:
                continue
            first_seen.setdefault(row[2], row[0])
        q3_first_seen = sum(first_seen.get(coin, END) >= START for coin in coins)
        outside = sorted(
            coin
            for coin in coins
            if classify_coin(coin, snapshot) not in (SCOPE_STRICT, SCOPE_TENTATIVE)
        )
        audits[wallet] = {
            "status": "CONDITIONAL_CHAINS_ONLY",
            "vendor_listed_instruments": len(coins),
            "source_fill_count_before_cutoff": len(fills),
            "source_fills_in_q3": sum(START <= row[0] < END for row in fills),
            "vendor_instruments_first_observed_after_q3_start": q3_first_seen,
            "full_book_at_q3_start_proven": q3_first_seen == 0 and not issues,
            "source_gaps": issues,
            "chain_counts": counts,
            "q3_completed_candidate_episodes": len(candidates),
            "accepted_episode_count": len(selected),
            "excluded_episode_count": len(candidates) - len(selected),
            "excluded_reasons": dict(sorted(excluded.items())),
            "excluded_out_of_display_instruments_count": len(outside),
            "native_display_eligibility_historical": "UNKNOWN_OCT30_SNAPSHOT_ONLY",
            "sha_verified_minute_checks": verified_minute_checks,
            "training_62d_observed_source_peak_gross_fill_price_proxy_usd": str(training_peak),
            "source_peak_scope": "KNOWN_VENDOR_COIN_GROSS_WITH_STALE_TRADE_PRICE_PROXY",
            "fixed_source_quantity_multiplier": str(scales[wallet]) if scales[wallet] else None,
            "source_equity_usd": None,
            "historical_receipt_at": None,
            "real_source_book_complete": False,
        }
        admitted[wallet] = selected
    return (
        admitted,
        audits,
        scales,
        {
            "source_manifests_sha256": fingerprints,
            "public_snapshot_sha256": sha256(raw).hexdigest(),
            "verified_overlay_report_sha256": overlay_sha,
            "market_instruments": sorted(all_identifiers),
            "market_days_verified_by_source": dict(sorted(market.source_days.items())),
        },
    )


def _batched_actions(
    episodes: dict[str, list[Episode]], trio: tuple[str, str, str], scales: dict[str, D | None]
):
    """For each wallet wait 5m after its first source event, collapse all interim updates."""
    out = defaultdict(dict)
    for wallet in trio:
        rows = sorted(
            (
                (event[0], event[1], ep.coin, event[4])
                for ep in episodes[wallet]
                for event in ep.events
            ),
            key=lambda x: (x[0], x[1], x[2]),
        )
        if not rows or scales[wallet] is None:
            continue
        qty: dict[Instrument, D] = {}
        i = 0
        while i < len(rows):
            due = _minute_at_or_after(rows[i][0] + WAIT)
            while i < len(rows) and rows[i][0] < due:
                _, _, coin, after = rows[i]
                inst = _native_pm(coin)
                if after:
                    qty[inst] = (after * scales[wallet]).quantize(QUANTITY_GRID)
                else:
                    qty.pop(inst, None)
                i += 1
            if due < END:
                out[due][wallet] = dict(qty)
    return sorted(out.items())


def _batched_actions_equity(
    episodes: dict[str, list[Episode]],
    trio: tuple[str, str, str],
    equity: HistoricalEquity,
    *,
    pod_capital_usd: D = POD_CAPITAL_USD,
):
    """Recompute quantities from source position/equity at *each decision*.

    Historical-only source clock. At a given minute, a missed follower trade
    does NOT change source book or create a new independent trade budget.
    """
    if pod_capital_usd <= ZERO:
        raise ValueError("INVALID_POD_CAPITAL")
    out = defaultdict(dict)
    for wallet in trio:
        rows = sorted(
            (
                (event[0], event[1], ep.coin, event[4])
                for ep in episodes[wallet]
                for event in ep.events
            ),
            key=lambda row: (row[0], row[1], row[2]),
        )
        # Event-driven source quantity snapshots, already batched for five
        # minutes as before. These are retrospective vendor events, not
        # prospective receipts.
        source_batches: dict[datetime, dict[Instrument, D]] = {}
        observed_book: dict[Instrument, D] = {}
        index = 0
        while index < len(rows):
            due = _minute_at_or_after(rows[index][0] + WAIT)
            while index < len(rows) and rows[index][0] < due:
                _, _, coin, after = rows[index]
                instrument = _native_pm(coin)
                if after:
                    observed_book[instrument] = after
                else:
                    observed_book.pop(instrument, None)
                index += 1
            if due < END:
                source_batches[due] = dict(observed_book)
        # A source wallet changes effective leverage when equity changes even
        # if it submits zero new fills. Include genuine equity observations as
        # independent sizing ticks, but NEVER manufacture intermediate equity.
        # Prior to the first reconstructed source book, NAV-only events cannot
        # establish the missing source positions and must not generate orders.
        equity_due = {
            _minute_at_or_after(point.at + timedelta(microseconds=1) + WAIT)
            for point in equity.points.get(wallet, ())
            if START <= point.at < END
        }
        book: dict[Instrument, D] = {}
        initialized = False
        for due in sorted(set(source_batches) | equity_due):
            if due >= END:
                continue
            if due in source_batches:
                initialized = True
                book = source_batches[due]
            if not initialized:
                continue
            if not book:
                # A directly observed zero-after close needs no equity
                # denominator. Do not request idle NAV updates as orders.
                if due in source_batches:
                    out[due][wallet] = {}
                continue
            source_equity = equity.asof(wallet, due)
            scale = pod_capital_usd / source_equity
            out[due][wallet] = {
                inst: (qty * scale).quantize(QUANTITY_GRID) for inst, qty in sorted(book.items())
            }
    return sorted(out.items())


def _synthetic_rulebook(instruments: set[Instrument]) -> Rulebook:
    return Rulebook(
        program="RESEARCH_CLASSIC_1STEP_PROXY",
        stage="evaluation",
        source="HISTORICAL_ORACLE_SIMULATED_ASSUMPTIONS",
        observed_at="2026-11-02T00:00:00+00:00",
        version="exploratory-q3-v1",
        timezone="UTC",
        initial_balance=CASH,
        profit_target=D("1000"),
        daily_loss=None,
        daily_loss_rate=D("0.03"),
        static_loss=D("600"),
        trailing_loss=None,
        permitted=tuple(sorted(instruments)),
        confirmed=True,  # explicit synthetic fixture only; NOT account permission
        account_terms_confirmed=False,
    )


def _rebalance(
    account: Account,
    desired: dict[str, dict[Instrument, D]],
    prices: dict[Instrument, D],
    bars: dict[Instrument, object],
    counters: Counter,
    *,
    risk_limits: tuple[D, D, D] | None = None,
    cost_multiplier: D = D("1"),
    execution_minute: datetime | None = None,
    capacity_enforced: bool = False,
    prior_closed_quote_volume: dict[Instrument, D] | None = None,
):
    """Net across three virtual PM books in the existing sole PM03 account."""
    if capacity_enforced and prior_closed_quote_volume is None:
        raise ValueError("MISSING_PRIOR_CLOSED_MINUTE_CAPACITY")
    pod_cap, account_cap, instrument_cap = risk_limits or (
        POD_GROSS_CAP,
        ACCOUNT_GROSS_CAP,
        INSTRUMENT_GROSS_CAP,
    )
    if min(pod_cap, account_cap, instrument_cap, cost_multiplier) <= ZERO:
        raise ValueError("INVALID_RESEARCH_SCENARIO")
    pods = sorted(set(desired) | set(account.pm_quantities))
    all_inst = {inst for book in desired.values() for inst in book}
    all_inst |= {inst for book in account.pm_quantities.values() for inst in book}
    new_net = {
        inst: sum((desired.get(p, {}).get(inst, ZERO) for p in pods), ZERO) for inst in all_inst
    }
    # These are explicit synthetic account risk ceilings. Never silently
    # rescale the source wallet. When exceeded, veto new risk but permit all
    # source reductions; a veto must not prevent an existing pod from exiting.
    if (
        any(
            sum((abs(q * prices[inst]) for inst, q in desired.get(p, {}).items()), ZERO) > pod_cap
            for p in pods
        )
        or sum((abs(q * prices[inst]) for inst, q in new_net.items()), ZERO) > account_cap
        or any(abs(q * prices[inst]) > instrument_cap for inst, q in new_net.items())
    ):
        counters["risk_budget_rejected_batches"] += 1
        reduced: dict[str, dict[Instrument, D]] = {}
        for pod in pods:
            prior = account.pm_quantities.get(pod, {})
            reduced[pod] = {}
            for inst in set(prior) | set(desired.get(pod, {})):
                old = prior.get(inst, ZERO)
                new = desired.get(pod, {}).get(inst, ZERO)
                if not old or (new * old > ZERO and abs(new) > abs(old)):
                    approved = old  # no new risk
                elif old * new < ZERO:
                    approved = ZERO  # flatten instead of reversal
                else:
                    approved = new  # only reduce or hold
                if approved:
                    reduced[pod][inst] = approved
        desired = reduced
        counters["risk_overlay_reduce_only_batches"] += 1
    for inst in sorted(all_inst):
        if execution_minute is not None and bars[inst].timestamp != execution_minute:
            # The last verified quote can support an explicit stale mark for
            # exploratory holding PnL, but it is NOT an executable order bar.
            counters["skipped_orders_stale_market_mark"] += 1
            continue
        changes = {
            p: desired.get(p, {}).get(inst, ZERO) - account.pm_quantities.get(p, {}).get(inst, ZERO)
            for p in pods
        }
        buys = {p: q for p, q in changes.items() if q > ZERO}
        sells = {p: -q for p, q in changes.items() if q < ZERO}
        for buyer in sorted(buys):
            for seller in sorted(sells):
                crossed = min(buys[buyer], sells[seller])
                if crossed:
                    account.internal_cross(inst, buyer, seller, crossed, prices[inst])
                    buys[buyer] -= crossed
                    sells[seller] -= crossed
                    counters["internal_crosses"] += 1
        pending = {p: v for p, v in buys.items() if v > ZERO}
        if not pending:
            pending = {p: -v for p, v in sells.items() if v > ZERO}
        net = sum(pending.values(), ZERO)
        if not net:
            continue
        bar = bars[inst]
        # Only the volume of the PREVIOUS completed minute can be used to
        # decide an order at this minute's open. Using the current minute's
        # final volume is lookahead. Legacy non-enforced diagnostics retain
        # their same-minute metric to preserve earlier historical evidence.
        volume = (
            prior_closed_quote_volume.get(inst, ZERO) if capacity_enforced else bar.quote_volume
        )
        cap_qty = volume / bar.open * MAX_PARTICIPATION
        if cap_qty <= ZERO or abs(net) > cap_qty:
            counters["orders_above_5pct_minute_volume_or_zero_volume"] += 1
            if capacity_enforced:
                counters["capacity_blocked_orders"] += 1
                continue
        side = D(1) if net > ZERO else D(-1)
        exec_px = prices[inst] * (
            D(1) + side * cost_multiplier * (FULL_SPREAD_BPS / 2 + SLIPPAGE_BPS) / D("10000")
        )
        fee = abs(net * exec_px) * FEE_BPS * cost_multiplier / D("10000")
        alloc = _allocate(net, pending)
        try:
            account.simulate_fill(inst, net, exec_px, fee, accepted=True, allocated=alloc)
        except ValueError as exc:
            recorded = account.quantities.get(inst, ZERO)
            virtual = sum((b.get(inst, ZERO) for b in account.pm_quantities.values()), ZERO)
            raise ValueError(
                f"REPLAY_ACCOUNT_RECONCILIATION:{inst.key}:external={recorded}:"
                f"virtual={virtual}:delta={net}:allocation={alloc}:cause={exc}"
            ) from exc
        counters["hypothetical_net_orders"] += 1
        counters["hypothetical_order_notional_usd"] += abs(net * prices[inst])
        counters["fees_usd"] += fee
    # The PM03 financial ledger keeps zero keys for audit parity. They must be
    # removed from the active simulation mark set only after its own verification;
    # nonzero opposing pod books remain and continue to receive 1m marks.
    for inst, qty in list(account.quantities.items()):
        if not qty:
            del account.quantities[inst]
    for book in account.pm_quantities.values():
        for inst, qty in list(book.items()):
            if not qty:
                del book[inst]
    account.verify()


def _has_exposure(account: Account) -> bool:
    return any(account.quantities.values()) or any(
        q for book in account.pm_quantities.values() for q in book.values()
    )


def _run_combo(
    name: str,
    trio: tuple[str, str, str],
    episodes: dict[str, list[Episode]],
    scales: dict[str, D | None],
    market: VerifiedHyperliquidMinuteSource,
    *,
    actions_override: list[tuple] | None = None,
    risk_limits: tuple[D, D, D] | None = None,
    cost_multiplier: D = D("1"),
    measure_tracking: bool = False,
    capacity_enforced: bool = False,
    start_at: datetime = START,
    end_at: datetime = END,
    holdout_at: datetime | None = HOLDOUT_START,
    pod_loss_limit: D | None = None,
) -> dict:
    if pod_loss_limit is not None and pod_loss_limit <= ZERO:
        raise ValueError("INVALID_POD_LOSS_LIMIT")
    if start_at >= end_at or start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("INVALID_REPLAY_INTERVAL")
    actions = (
        actions_override
        if actions_override is not None
        else _batched_actions(episodes, trio, scales)
    )
    if any((actions_override is None and scales[w] is None) or not episodes[w] for w in trio):
        return {
            "name": name,
            "wallets": list(trio),
            "status": "NO_THREE_WALLET_OBSERVABLE_INPUT",
            "accepted_episodes": {w: len(episodes[w]) for w in trio},
            "pnl_usd": None,
        }
    instruments = {_native_pm(ep.coin) for wallet in trio for ep in episodes[wallet]}
    account = Account.start(_synthetic_rulebook(instruments), start_at.isoformat())
    latest: dict[str, dict[Instrument, D]] = {w: {} for w in trio}
    counters = Counter()
    per_wallet_tracking = defaultdict(Counter)
    suspended_pods: set[str] = set()
    curve = []
    peak = CASH
    max_dd = ZERO
    worst_day_usd = ZERO
    holdout_start_equity = None
    daily_floor_min: D | None = None
    reason = None
    i = 0
    current = start_at
    last_day = start_at.date()
    prior_equity = CASH
    while current < end_at:
        if i >= len(actions) and not _has_exposure(account):
            # Finished the last observed episode; a flat book has no mark PnL.
            current = end_at
            break
        if not _has_exposure(account) and i < len(actions) and current < actions[i][0]:
            current = actions[i][0]
        if current >= end_at:
            break
        pending = actions[i][1] if i < len(actions) and actions[i][0] == current else {}
        insts = {inst for inst, q in account.quantities.items() if q}
        insts |= {inst for b in account.pm_quantities.values() for inst, q in b.items() if q}
        insts |= {inst for b in pending.values() for inst in b}
        bars = {}
        prices = {}
        try:
            for inst in sorted(insts):
                bars[inst] = _quote(market, inst, current)
                prices[inst] = bars[inst].open
        except MarketDataBlocked as exc:
            reason = "MISSING_ACTIVE_OR_TARGET_MARK:" + str(exc).split(":", 1)[0]
            counters["blocked_mark_minutes"] += 1
            break
        account.mark(prices, current.isoformat())
        if account.breached:
            reason = "CONTRACTUAL_DRAWDOWN_BREACH"
        if account.stage_passed:
            reason = "SIMULATED_STAGE_TARGET_REACHED"
        if holdout_at is not None and current >= holdout_at and holdout_start_equity is None:
            holdout_start_equity = account.equity
        current_day = current.date()
        if current_day != last_day:
            curve.append({"date": last_day.isoformat(), "equity_usd": str(prior_equity)})
            last_day = current_day
        prior_equity = account.equity
        peak = max(peak, account.equity)
        max_dd = max(max_dd, peak - account.equity)
        worst_day_usd = min(worst_day_usd, account.equity - account.daily_start_balance)
        floor, _ = account.floor()
        if floor is not None:
            daily_floor_min = (
                min(daily_floor_min, account.equity - floor)
                if daily_floor_min is not None
                else account.equity - floor
            )
        if reason:
            break
        newly_suspended = set()
        if pod_loss_limit is not None:
            for pod, pnl in account.pm_equity_pnl().items():
                if pod in trio and pod not in suspended_pods and pnl <= -pod_loss_limit:
                    newly_suspended.add(pod)
                    counters["pod_fixed_loss_stop_latched"] += 1
            suspended_pods.update(newly_suspended)
        if pending or newly_suspended:
            latest.update(pending)
            # Always retain source intent independently from stop/veto decisions.
            desired = {p: ({} if p in suspended_pods else book) for p, book in latest.items()}
            if any(inst not in prices for b in desired.values() for inst in b):
                # Existing portfolio active legs already have current marks;
                # on unchanged source targets acquire their exact minute quote.
                try:
                    for inst in sorted({k for b in desired.values() for k in b} - set(prices)):
                        bars[inst] = _quote(market, inst, current)
                        prices[inst] = bars[inst].open
                except MarketDataBlocked as exc:
                    reason = "MISSING_REQUESTED_MARK:" + str(exc).split(":", 1)[0]
                    break
                # These positions were present in the latest source targets
                # but not in current holdings or this minute's new messages.
                # Their marks were fetched after the initial account.mark().
                # Re-mark explicitly before PM03 internal crosses; NEVER pass
                # a fresh price while leaving an earlier cached mark active.
                account.mark(prices, current.isoformat())
                if account.breached:
                    reason = "CONTRACTUAL_DRAWDOWN_BREACH"
                    break
                if account.stage_passed:
                    reason = "SIMULATED_STAGE_TARGET_REACHED"
                    break
            prior_closed_quote_volume = None
            if capacity_enforced:
                # Use only a finished t-1 market bar for the capacity proxy.
                # Never use the t bar's final volume to decide at its open.
                prior_closed_quote_volume = {}
                native = getattr(market, "native", market)
                for inst in set(prices):
                    try:
                        prior_bar = _quote(native, inst, current - MINUTE)
                    except MarketDataBlocked:
                        counters["capacity_prior_minute_unavailable"] += 1
                        prior_closed_quote_volume[inst] = ZERO
                    else:
                        prior_closed_quote_volume[inst] = (
                            prior_bar.quote_volume
                            if prior_bar.timestamp == current - MINUTE
                            else ZERO
                        )
                        if prior_bar.timestamp != current - MINUTE:
                            counters["capacity_prior_minute_unavailable"] += 1
            _rebalance(
                account,
                desired,
                prices,
                bars,
                counters,
                risk_limits=risk_limits,
                cost_multiplier=cost_multiplier,
                execution_minute=current,
                capacity_enforced=capacity_enforced,
                prior_closed_quote_volume=prior_closed_quote_volume,
            )
            counters["wallet_batch_actions"] += len(pending)
            if measure_tracking:
                for wallet, target in latest.items():
                    actual = account.pm_quantities.get(wallet, {})
                    insts_for_wallet = set(target) | set(actual)
                    missing_quote = 0
                    for inst in sorted(insts_for_wallet - set(prices)):
                        try:
                            prices[inst] = _quote(market, inst, current).open
                        except MarketDataBlocked:
                            missing_quote += 1
                    priced = insts_for_wallet & set(prices)
                    intended = sum(
                        (abs(target.get(inst, ZERO) * prices[inst]) for inst in priced),
                        ZERO,
                    )
                    actual_gross = sum(
                        (abs(actual.get(inst, ZERO) * prices[inst]) for inst in priced),
                        ZERO,
                    )
                    error = sum(
                        (
                            abs(target.get(inst, ZERO) - actual.get(inst, ZERO)) * prices[inst]
                            for inst in priced
                        ),
                        ZERO,
                    )
                    stats = per_wallet_tracking[wallet]
                    stats["unpriced_target_instrument_samples"] += missing_quote
                    stats["intended_gross_usd_sum"] += intended
                    stats["actual_gross_usd_sum"] += actual_gross
                    stats["tracking_error_usd_sum"] += error
                    stats["samples"] += 1
            if pending:
                i += 1
        # Fixed conservative funding debit proxy at eight-hour settlement.
        if current.minute == 0 and current.hour in (0, 8, 16) and account.quantities:
            distribution: dict[str, D] = {}
            for pod, book in account.pm_quantities.items():
                gross = sum((abs(q * prices[inst]) for inst, q in book.items()), ZERO)
                if gross:
                    distribution[pod] = (
                        -gross * FUNDING_ABS_BPS_PER_8H * cost_multiplier / D("10000")
                    )
            if distribution:
                fee = sum(distribution.values(), ZERO)
                account.post_funding(fee, distribution)
                counters["funding_debit_usd"] += -fee
        peak = max(peak, account.equity)
        max_dd = max(max_dd, peak - account.equity)
        worst_day_usd = min(worst_day_usd, account.equity - account.daily_start_balance)
        current += MINUTE
    if holdout_at is not None and holdout_start_equity is None and current >= end_at:
        # Flat-account fast-forward across Sep 1 has no hidden PnL.
        holdout_start_equity = account.equity
    if current >= end_at and _has_exposure(account):
        reason = "UNCLOSED_FOLLOWER_BOOK_AT_Q3_END"
    if curve and curve[-1]["date"] == last_day.isoformat():
        curve[-1]["equity_usd"] = str(account.equity)
    else:
        curve.append({"date": last_day.isoformat(), "equity_usd": str(account.equity)})
    account.verify()
    eligible_full = reason is None
    tracking = None
    if measure_tracking:
        tracking = {
            wallet: {
                "intended_gross_usd_sum": str(stats["intended_gross_usd_sum"]),
                "actual_gross_usd_sum": str(stats["actual_gross_usd_sum"]),
                "tracking_error_usd_sum": str(stats["tracking_error_usd_sum"]),
                "action_count": stats["samples"],
                **(
                    {"unpriced_target_instrument_samples": stats["unpriced_target_instrument_samples"]}
                    if pod_loss_limit is not None or stats["unpriced_target_instrument_samples"]
                    else {}
                ),
                "action_weighted_tracking_error_fraction": (
                    str(stats["tracking_error_usd_sum"] / stats["intended_gross_usd_sum"])
                    if stats["intended_gross_usd_sum"] and not stats["unpriced_target_instrument_samples"]
                    else None
                ),
            }
            for wallet, stats in sorted(per_wallet_tracking.items())
        }
    return {
        "name": name,
        "wallets": list(trio),
        "status": "CONDITIONAL_EPISODE_REPLAY_FULL_Q3"
        if eligible_full
        else "PARTIAL_CONDITIONAL_REPLAY",
        "stop_reason": reason,
        "observed_through": min(current, end_at).isoformat(),
        "model_start": start_at.isoformat(),
        "model_end_exclusive": end_at.isoformat(),
        "accepted_episodes": {w: len(episodes[w]) for w in trio},
        "equity_usd": str(account.equity),
        "pnl_usd": str(account.equity - CASH),
        "max_observed_drawdown_usd": str(max_dd),
        "max_observed_drawdown_pct_start": str(max_dd / CASH * 100),
        "worst_observed_day_pnl_usd": str(worst_day_usd),
        "holdout_start_equity_usd": str(holdout_start_equity)
        if holdout_start_equity is not None
        else None,
        "holdout_end_delta_usd": str(account.equity - holdout_start_equity)
        if holdout_start_equity is not None and current >= end_at
        else None,
        "breached_floor": account.breached,
        "stage_passed": account.stage_passed,
        "per_wallet_pnl_usd": {k: str(v) for k, v in account.pm_equity_pnl().items()},
        **(
            {"pod_loss_limit_usd": str(pod_loss_limit), "suspended_pods": sorted(suspended_pods)}
            if pod_loss_limit is not None
            else {}
        ),
        "counters": {k: (str(v) if isinstance(v, D) else v) for k, v in sorted(counters.items())},
        "daily_curve": curve,
        "economic_classification": "HISTORICAL_ORACLE_CONDITIONAL_EPISODES_NOT_WALLET_EQUITY_OR_VERIFIED_FOLLOWER",
        "source_and_realized_cost_fidelity": False,
        **({"action_weighted_exposure_tracking": tracking} if measure_tracking else {}),
    }


def study_legacy_proxy(
    root: Path, market_root: Path, generations: tuple[Path, ...], *, mixed: bool = True
) -> dict:
    market = VerifiedHyperliquidMinuteSource(market_root)
    episodes, audits, scales, provenance = _source_inputs(root, market, generations)
    results = []
    for name, trio in PORTFOLIOS.items():
        results.append(_run_combo(name, trio, episodes, scales, market))
    if mixed:
        for trio in combinations(ALL_WALLETS, 3):
            if trio in PORTFOLIOS.values():
                continue
            label = "MIX_" + "_".join(trio)
            results.append(_run_combo(label, trio, episodes, scales, market))
    complete = [r for r in results if r["status"] == "CONDITIONAL_EPISODE_REPLAY_FULL_Q3"]
    ranking = sorted(
        complete, key=lambda r: (D(r["pnl_usd"]), -D(r["max_observed_drawdown_usd"])), reverse=True
    )
    # No ranking may be interpreted as whole-wallet combo preference.
    return {
        "schema": SCHEMA,
        "study_start": START.isoformat(),
        "study_end_exclusive": END.isoformat(),
        "train_end_holdout_start": HOLDOUT_START.isoformat(),
        "initial_usd": str(CASH),
        "portfolio_membership": {k: list(v) for k, v in PORTFOLIOS.items()},
        "wallet_audit": audits,
        "source_quantity_scale_by_wallet": {
            w: str(v) if v is not None else None for w, v in scales.items()
        },
        "assumptions": {
            "source_reconstruction": "ONLY_EXPOST_COMPLETED_FLAT_TO_FLAT_PER_INSTRUMENT_EPISODES",
            "historical_event_time_as_first_known": False,
            "source_decision_clock": "HINDSIGHT_ORACLE_ONLY",
            "delay": "FIRST_SIGNAL_WALLET_BATCH_5_MINUTES_THEN_EXACT_1M_OPEN",
            "per_wallet_scale": "FIXED_FROM_JUL_AUG_OBSERVED_VENDOR_GROSS_PEAK_2000_USD_NOT_EQUITY",
            "research_quantity_grid": str(QUANTITY_GRID),
            "source_equity_at_decision": "UNKNOWN",
            "netting": "PM03_SINGLE_ACCOUNT_PM_BOOKS_WITH_INTERNAL_CROSSES",
            "fee_bps": str(FEE_BPS),
            "full_spread_bps": str(FULL_SPREAD_BPS),
            "slippage_bps": str(SLIPPAGE_BPS),
            "conservative_funding_debit_bps_per_8h": str(FUNDING_ABS_BPS_PER_8H),
            "max_minute_volume_share_diagnostic_only": str(MAX_PARTICIPATION),
            "execution_capacity_gate": "NOT_ENFORCED_EXPLORATORY_OPEN_PRICE_PROXY",
            "fills_are_executable": False,
            "pod_gross_cap_usd": str(POD_GROSS_CAP),
            "account_gross_cap_usd": str(ACCOUNT_GROSS_CAP),
            "instrument_gross_cap_usd": str(INSTRUMENT_GROSS_CAP),
            "contract": "SYNTHETIC_CLASSIC_1STEP_3PCT_DAILY_6PCT_STATIC_10PCT_TARGET",
            "propr_display": "OCT30_SNAPSHOT_NOT_HISTORICAL_ORDER_ALLOWLIST",
            "missing_mark": "INVALIDATES_SCENARIO_PREFIX_NO_INTERPOLATION",
            "source_gross_peak_calibration_usd": str(TRAINING_PEAK_WALLET_GROSS_BUDGET),
        },
        "provenance": {
            **{k: v for k, v in provenance.items() if k != "market_days_verified_by_source"},
            "sha_checked_market_day_count": len(market.source_days),
            "sha_checked_market_day_digests_sha256": sha256(
                json.dumps(market.source_days, sort_keys=True).encode()
            ).hexdigest(),
        },
        "portfolio_results": results,
        "conditional_rank_names": [r["name"] for r in ranking],
        "fully_faithful_whole_wallet_replays": 0,
        "valid_full_wallet_combo_ranking_available": False,
        "scientifically_qualified": False,
        "broker_trading_authorized": False,
    }


def _named_combinations(mixed: bool):
    for name, trio in PORTFOLIOS.items():
        yield name, trio
    if mixed:
        for trio in combinations(ALL_WALLETS, 3):
            if trio not in PORTFOLIOS.values():
                yield "MIX_" + "_".join(trio), trio


def study(
    root: Path,
    market_root: Path,
    generations: tuple[Path, ...],
    *,
    mixed: bool = True,
    source_equity_ledger: Path | None = None,
    legacy_gross_proxy: bool = False,
) -> dict:
    """Source-EQUITY sizing by default. An old gross-normalized run is opt-in.

    Q3 fill pages are not source equity. Without independently retained
    historical equity, do not run 84 fake-sized PnL paths. Explicitly preserve
    every scenario as BLOCKED_HISTORICAL_SOURCE_EQUITY instead.
    """
    if legacy_gross_proxy:
        if source_equity_ledger is not None:
            raise ValueError("CONFLICTING_HISTORICAL_SIZING_MODES")
        return study_legacy_proxy(root, market_root, generations, mixed=mixed)

    entries, fingerprints = load_cohort(root)
    identities = {e.alias: e.address_sha256 for e in entries if e.alias in ALL_WALLETS}
    if len(identities) != len(ALL_WALLETS):
        raise ValueError("HISTORICAL_EQUITY_UNKNOWN_WALLET_COHORT")
    names = list(_named_combinations(mixed))
    preflight = {
        "schema": EQUITY_SCHEMA,
        "status": "BLOCKED_HISTORICAL_SOURCE_EQUITY"
        if source_equity_ledger is None
        else "HISTORICAL_EQUITY_ORACLE_RESEARCH",
        "study_start": START.isoformat(),
        "study_end_exclusive": END.isoformat(),
        "initial_cash_usd": str(CASH),
        "pod_capital_usd_each": str(POD_CAPITAL_USD),
        "sizing_equation": "source_signed_qty * pod_capital_usd / asof_source_equity_usd",
        "source_event_time_is_not_first_known": True,
        "source_equity_evidence": "UNAVAILABLE_FOR_Q3"
        if source_equity_ledger is None
        else "EXTERNALLY_DECLARED_RECONCILED_STILL_HINDSIGHT",
        "source_identity_manifests_sha256": fingerprints,
        "source_equity_ledger_sha256": None,
        "wallets_with_predecision_equity_evidence": 0,
        "full_wallet_book_reconstructed": False,
        "legacy_gross_proxy_pnl_is_not_wallet_weight_replication": True,
        "portfolio_membership": {k: list(v) for k, v in PORTFOLIOS.items()},
        "fully_faithful_whole_wallet_replays": 0,
        "valid_full_wallet_combo_ranking_available": False,
        "conditional_rank_names": [],
        "scientifically_qualified": False,
        "broker_trading_authorized": False,
        "portfolio_results": [],
    }
    if source_equity_ledger is None:
        preflight["portfolio_results"] = [
            {
                "name": name,
                "wallets": list(trio),
                "status": "BLOCKED_HISTORICAL_SOURCE_EQUITY",
                "source_equity_usd": None,
                "pnl_usd": None,
                "reason": "NO_AUTHENTIC_Q3_WALLET_EQUITY_SERIES",
            }
            for name, trio in names
        ]
        return preflight

    equity = load_equity(source_equity_ledger, identities=identities)
    preflight["source_equity_ledger_sha256"] = equity.ledger_sha256
    preflight["wallets_with_predecision_equity_evidence"] = sum(
        bool(equity.points[w] and equity.points[w][0].at < END) for w in ALL_WALLETS
    )
    market = VerifiedHyperliquidMinuteSource(market_root)
    episodes, audits, _, source = _source_inputs(root, market, generations)
    for audit in audits.values():
        # No fixed July-Aug gross scalar is used anywhere in equity mode.
        audit.pop("fixed_source_quantity_multiplier", None)
        audit.pop("training_62d_observed_source_peak_gross_fill_price_proxy_usd", None)
        audit.pop("source_peak_scope", None)
        audit["source_equity_at_decision"] = "REQUIRES_ASOF_LEDGER_LOOKUP"
    for name, trio in names:
        try:
            actions = _batched_actions_equity(episodes, trio, equity)
        except ValueError as exc:
            preflight["portfolio_results"].append(
                {
                    "name": name,
                    "wallets": list(trio),
                    "status": "BLOCKED_HISTORICAL_SOURCE_EQUITY",
                    "reason": str(exc),
                    "pnl_usd": None,
                }
            )
            continue
        result = _run_combo(
            name,
            trio,
            episodes,
            {w: D("1") for w in trio},
            market,
            actions_override=actions,
        )
        result["source_equity_weight_sizing"] = True
        result["evidence_class"] = "HINDSIGHT_PARTIAL_EPISODE_ORACLE_NOT_COMPLETE_WALLET"
        preflight["portfolio_results"].append(result)
    preflight["status"] = "PARTIAL_EQUITY_WEIGHTED_RESEARCH_NOT_WALLET_QUALIFICATION"
    preflight["wallet_audit"] = audits
    preflight["market_sha_checked_days"] = len(market.source_days)
    preflight["source"] = {
        "public_snapshot_sha256": source["public_snapshot_sha256"],
        "verified_overlay_report_sha256": source["verified_overlay_report_sha256"],
    }
    return preflight


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hyperx-generations", nargs="*", type=Path, default=[])
    parser.add_argument("--no-mixed", action="store_true")
    parser.add_argument("--source-equity-ledger", type=Path)
    parser.add_argument("--legacy-gross-proxy", action="store_true")
    args = parser.parse_args()
    report = study(
        args.research_root,
        args.market_root,
        tuple(args.hyperx_generations),
        mixed=not args.no_mixed,
        source_equity_ledger=args.source_equity_ledger,
        legacy_gross_proxy=args.legacy_gross_proxy,
    )
    path, digest = _write_private_evidence(args.out, report)
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "full_wallet_faithful": 0,
                "conditional_complete_combinations": len(report["conditional_rank_names"]),
                "source_equity_replay_status": report.get("status", "LEGACY_GROSS_PROXY_EXPLICIT"),
                "portfolios": [
                    {k: row[k] for k in ("name", "status", "pnl_usd") if k in row}
                    for row in report["portfolio_results"]
                    if row["name"] in PORTFOLIOS
                ],
                "report": str(path),
                "sha256": digest,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
