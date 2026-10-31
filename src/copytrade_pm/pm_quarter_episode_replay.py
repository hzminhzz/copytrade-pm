"""Per-wallet 2026Q3 independently anchored, flat-to-flat episode replay.

Each observed per-instrument flat-to-flat path is evaluated independently on
real venue-identical SHA-checked 1m data. A 5/15/60m modeled follower can be
computed for such a path without inventing the rest of the wallet book.
This is NOT a whole-wallet follower, shared portfolio equity, or qualified
first-known copy signal; no use of source market-fill as receipt timestamps.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

from .pm_fill_replay import _market_instrument, _same_position
from .pm_quarter_fill_audit import (
    START,
    END,
    EconomicFill,
    wallet_fills,
    save_private_artifact,
)
from .pm_hyperx_overlay_audit import examine
from .pm_shadow import (
    MarketDataBlocked,
    Scenario,
    VerifiedHyperliquidMinuteSource,
    _VirtualBook,
)
from .pm_sources import load_cohort


D = Decimal
ZERO = D(0)
DELAYS = (5, 15, 60)
RESEARCH_GROSS_NOTIONAL_PER_EPISODE = D("100")
SCHEMA = "pm36_2026q3_independent_completed_episode_replay_v1"


@dataclass(frozen=True)
class Episode:
    wallet: str
    coin: str
    rows: tuple[EconomicFill, ...]

    @property
    def opened_at(self) -> datetime:
        return self.rows[0].timestamp

    @property
    def closed_at(self) -> datetime:
        return self.rows[-1].timestamp


def closed_episodes(alias: str, fills: list[EconomicFill]) -> tuple[list[Episode], Counter]:
    """Use confirmed zero inventory, never infer a flat book from a missing record."""
    by_coin: dict[str, list[EconomicFill]] = defaultdict(list)
    for row in fills:
        by_coin[row.coin].append(row)
    episodes = []
    stats: Counter = Counter()
    for coin, rows in sorted(by_coin.items()):
        # Preserve verified PM-01 same-ms position continuity ordering.
        if any(b.timestamp < a.timestamp for a, b in zip(rows, rows[1:])):
            raise ValueError("NONCHRONOLOGICAL_VERIFIED_COIN_CHAIN")
        last: D | None = None
        active: list[EconomicFill] = []
        established_flat = False
        for event in rows:
            if last is not None and not _same_position(last, event.before):
                stats["position_chain_gaps"] += 1
                active = []
                established_flat = False
            last = event.after
            if not established_flat:
                # A source-reported zero-before trade can anchor this instrument.
                # If the first observed position was already open, we wait
                # until a later directly observed zero-after event.
                if event.before == ZERO:
                    established_flat = True
                elif event.after == ZERO:
                    established_flat = True
                    continue
                else:
                    continue
            if not active:
                if event.before != ZERO:
                    established_flat = False
                    continue
                if event.after == ZERO:
                    continue
                active = [event]
                continue
            if event.before == ZERO or event.before * event.after < 0:
                # Cross-through zero requires a split-fill attribution that
                # this conservative episode experiment does not invent.
                stats["unsupported_flip_or_restart"] += 1
                active = []
                established_flat = event.after == ZERO
                continue
            active.append(event)
            if event.after == ZERO:
                stats["source_episodes_closed_all_times"] += 1
                if START <= active[0].timestamp and active[-1].timestamp < END:
                    episodes.append(Episode(alias, coin, tuple(active)))
                else:
                    stats["completed_episodes_outside_frozen_quarter"] += 1
                active = []
        if active:
            stats["censored_open_segments_at_source_cutoff"] += 1
    episodes.sort(key=lambda e: (e.opened_at, e.wallet, e.coin))
    stats["valid_flat_to_flat_episodes_in_quarter"] = len(episodes)
    return episodes, stats


def _baseline_scenario(lag: int) -> Scenario:
    return Scenario(
        "OBSERVED_EPISODE_HINDSIGHT_ORACLE_NOT_PIT",
        lag,
        D("100000"),
        D("0.001"),
        max_minute_participation=D("0.05"),
    )


def replay_episode(
    episode: Episode,
    market: VerifiedHyperliquidMinuteSource,
    lag: int,
    *,
    per_episode_gross_cap: D = RESEARCH_GROSS_NOTIONAL_PER_EPISODE,
) -> dict:
    if lag not in DELAYS or per_episode_gross_cap <= ZERO:
        raise ValueError("INVALID_HISTORICAL_EPISODE_POLICY")
    if (
        not episode.rows
        or episode.opened_at < START
        or episode.closed_at >= END
        or episode.rows[0].before != ZERO
        or episode.rows[-1].after != ZERO
    ):
        raise ValueError("UNANCHORED_OR_OUT_OF_WINDOW_EPISODE")
    try:
        instrument = _market_instrument(episode.coin)
    except MarketDataBlocked:
        return {"status": "BLOCKED_UNRESOLVED_EXCHANGE_INSTRUMENT"}
    grouped: dict[datetime, list[EconomicFill]] = defaultdict(list)
    for row in episode.rows:
        action_at = VerifiedHyperliquidMinuteSource._minute(row.timestamp + timedelta(minutes=lag))
        if action_at >= END:
            return {"status": "BLOCKED_ACTION_AFTER_QUARTER_END"}
        grouped[action_at].append(row)

    follower = _VirtualBook()
    always_long = _VirtualBook()
    model = _baseline_scenario(lag)
    source_qty = ZERO
    scale: D | None = None
    last_at = None
    executions = 0
    peak_notional = ZERO

    for action_at, rows in sorted(grouped.items()):
        for event in rows:
            if not _same_position(source_qty, event.before):
                return {"status": "BLOCKED_EPISODE_SOURCE_CONTINUITY"}
            source_qty = event.after
        try:
            quote = market.get(instrument, action_at)
        except MarketDataBlocked as ex:
            return {"status": "BLOCKED_MARKET_DATA", "reason": str(ex)}
        if scale is None:
            if source_qty == ZERO:
                # Entry and exit canceled in same delayed minute: no
                # independently executable episode, don't count as flat win.
                return {"status": "BLOCKED_NO_EXECUTABLE_ENTRY"}
            scale = per_episode_gross_cap / abs(source_qty * quote.open)
        wanted = source_qty * scale
        if abs(wanted * quote.open) > per_episode_gross_cap:
            wanted = (D(1) if wanted > ZERO else D(-1)) * (per_episode_gross_cap / quote.open)
        desired = {instrument: wanted} if wanted else {}
        control = {instrument: abs(wanted)} if wanted else {}
        for book, target in ((follower, desired), (always_long, control)):
            current = book.positions.get(instrument, ZERO)
            delta = target.get(instrument, ZERO) - current
            if delta != ZERO:
                if quote.quote_volume <= ZERO or abs(delta * quote.open) > (
                    quote.quote_volume * model.max_minute_participation
                ):
                    return {"status": "BLOCKED_INSTRUMENT_MINUTE_PARTICIPATION"}
        if last_at is not None:
            elapsed = action_at - last_at
            follower.accrue_funding({instrument: quote.open}, elapsed, model)
            always_long.accrue_funding({instrument: quote.open}, elapsed, model)
        before = follower.fills
        follower.rebalance(desired, {instrument: quote}, model)
        always_long.rebalance(control, {instrument: quote}, model)
        executions += follower.fills - before
        peak_notional = max(peak_notional, abs(wanted * quote.open))
        last_at = action_at

    if follower.positions or always_long.positions or source_qty != ZERO or executions < 2:
        return {"status": "BLOCKED_UNCLOSED_OR_UNEXECUTED_EPISODE"}
    pnl = follower.flows.get(instrument, ZERO)
    baseline = always_long.flows.get(instrument, ZERO)
    return {
        "status": "HINDSIGHT_EPISODE_SIMULATED_ONLY",
        "hypothetical_net_pnl_usdc": str(pnl),
        "market_only_long_pnl_usdc": str(baseline),
        "incremental_vs_long_control_usdc": str(pnl - baseline),
        "modeled_fees_usdc": str(follower.fees),
        "modeled_spread_slippage_usdc": str(follower.impact),
        "modeled_funding_usdc": str(follower.funding),
        "total_traded_notional_usdc_proxy": str(follower.turnover),
        "max_live_gross_episode_notional_usdc": str(peak_notional),
        "simulated_rebalance_fill_count": executions,
        "source_earliest_action_at": episode.opened_at.isoformat(),
        "source_latest_action_at": episode.closed_at.isoformat(),
        "first_known_signal_at": None,
        "copyability_qualified": False,
    }


def wallet_episodes(
    alias: str,
    episodes: list[Episode],
    stats: Counter,
    market: VerifiedHyperliquidMinuteSource,
) -> dict:
    results = {}
    outcomes: dict[int, list[dict]] = {}
    for lag in DELAYS:
        counts = Counter()
        rows_for_lag: list[dict] = []
        pnl = ZERO
        control = ZERO
        by_month: dict[str, dict[str, D | int]] = defaultdict(lambda: {"pnl": ZERO, "count": 0})
        represented_days = set()
        for episode in episodes:
            row = replay_episode(episode, market, lag)
            rows_for_lag.append(row)
            counts[row["status"]] += 1
            if row["status"] == "HINDSIGHT_EPISODE_SIMULATED_ONLY":
                pnl += D(row["hypothetical_net_pnl_usdc"])
                control += D(row["market_only_long_pnl_usdc"])
                day = episode.opened_at.date()
                represented_days.add(day)
                month = episode.opened_at.strftime("%Y-%m")
                by_month[month]["pnl"] += D(row["hypothetical_net_pnl_usdc"])
                by_month[month]["count"] += 1
        outcomes[lag] = rows_for_lag
        completed_episodes = [
            episode
            for episode, result in zip(episodes, rows_for_lag)
            if result["status"] == "HINDSIGHT_EPISODE_SIMULATED_ONLY"
        ]
        results[str(lag)] = {
            "completed_observable_flat_to_flat_episodes": counts[
                "HINDSIGHT_EPISODE_SIMULATED_ONLY"
            ],
            "blocked_episodes": len(episodes) - counts["HINDSIGHT_EPISODE_SIMULATED_ONLY"],
            "blockers": dict(
                sorted((k, v) for k, v in counts.items() if k != "HINDSIGHT_EPISODE_SIMULATED_ONLY")
            ),
            "completed_episode_source_entry_days": len(represented_days),
            "first_completed_source_episode_at": (
                min(x.opened_at for x in completed_episodes).isoformat()
                if completed_episodes
                else None
            ),
            "last_completed_source_episode_at": (
                max(x.closed_at for x in completed_episodes).isoformat()
                if completed_episodes
                else None
            ),
            "sum_independent_episode_pnl_not_wallet_pnl_usdc": str(pnl),
            "sum_matching_long_only_episode_pnl_usdc": str(control),
            "sum_incremental_episode_pnl_usdc": str(pnl - control),
            "source_entry_months": {
                month: {
                    "completed_episodes": info["count"],
                    "hypothetical_pnl_usdc": str(info["pnl"]),
                }
                for month, info in sorted(by_month.items())
            },
        }
    paired_indices = [
        i
        for i in range(len(episodes))
        if all(outcomes[lag][i]["status"] == "HINDSIGHT_EPISODE_SIMULATED_ONLY" for lag in DELAYS)
    ]
    paired = {
        str(lag): {
            "sum_hypothetical_pnl_usdc": str(
                sum(
                    (D(outcomes[lag][i]["hypothetical_net_pnl_usdc"]) for i in paired_indices), ZERO
                )
            ),
            "sum_incremental_vs_long_control_usdc": str(
                sum(
                    (
                        D(outcomes[lag][i]["incremental_vs_long_control_usdc"])
                        for i in paired_indices
                    ),
                    ZERO,
                )
            ),
        }
        for lag in DELAYS
    }
    return {
        "wallet": alias,
        "paired_same_episodes_all_5_15_60m": {
            "count": len(paired_indices),
            "by_lag": paired,
            "hindsight_only": True,
        },
        "eligible_fully_observed_flat_to_flat_source_episodes": len(episodes),
        "extraction_diagnostics": dict(stats),
        "by_lag": results,
        "entire_portfolio_or_account_replayed": False,
        "vendor_future_instrument_census_complete_asof_july": False,
        "copyable_prospective_signal_known": False,
    }


def study(
    root: Path,
    market_root: Path,
    *,
    generations: tuple[Path, ...] = (),
) -> dict:
    entries, manifests = load_cohort(root)
    overlay = None
    additions: dict[str, list[tuple]] = {}
    if generations:
        overlay, additions = examine(root, generations)
        if overlay["wallet_count"] != 36 or not overlay["original_vendor_cache_intact"]:
            raise ValueError("UNTRUSTED_SOURCE_OVERLAY")
    market = VerifiedHyperliquidMinuteSource(market_root)
    rows = []
    for entry in entries:
        fills, _ = wallet_fills(
            root,
            entry,
            generations=generations,
            verified_additions=additions.get(entry.alias, []),
        )
        episodes, stats = closed_episodes(entry.alias, fills)
        rows.append(wallet_episodes(entry.alias, episodes, stats, market))
    if len(rows) != 36 or len({r["wallet"] for r in rows}) != 36:
        raise ValueError("INCOMPLETE_36_WALLET_RESEARCH")
    totals = {}
    for lag in DELAYS:
        used = sum(
            row["by_lag"][str(lag)]["completed_observable_flat_to_flat_episodes"] for row in rows
        )
        blocked = sum(row["by_lag"][str(lag)]["blocked_episodes"] for row in rows)
        totals[str(lag)] = {
            "completed_independent_episodes": used,
            "blocked_independent_episodes": blocked,
            "wallets_with_some_completed_episodes": sum(
                row["by_lag"][str(lag)]["completed_observable_flat_to_flat_episodes"] > 0
                for row in rows
            ),
        }
    return {
        "schema": SCHEMA,
        "source": "AUTHENTICATED_HYPERX_HISTORICAL_FILLS_AND_SHA_VERIFIED_NATIVE_HL_1M",
        "start_inclusive": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "calendar_days": (END - START).days,
        "wallet_count": len(rows),
        "source_manifests_sha256": manifests,
        "overlay_source_generation_sha256": (overlay["private_generations"] if overlay else []),
        "market_consumed_day_shas": dict(sorted(market.source_days.items())),
        "market_consumed_day_count": len(market.source_days),
        "historical_episodes_considered": sum(
            r["eligible_fully_observed_flat_to_flat_source_episodes"] for r in rows
        ),
        "per_lag_totals": totals,
        "same_episodes_paired_5_15_60m": {
            "count": sum(r["paired_same_episodes_all_5_15_60m"]["count"] for r in rows),
            "by_lag": {
                str(lag): {
                    "sum_pnl_usdc_not_whole_wallet": str(
                        sum(
                            (
                                D(
                                    r["paired_same_episodes_all_5_15_60m"]["by_lag"][str(lag)][
                                        "sum_hypothetical_pnl_usdc"
                                    ]
                                )
                                for r in rows
                            ),
                            ZERO,
                        )
                    ),
                    "sum_incremental_vs_long_control_usdc": str(
                        sum(
                            (
                                D(
                                    r["paired_same_episodes_all_5_15_60m"]["by_lag"][str(lag)][
                                        "sum_incremental_vs_long_control_usdc"
                                    ]
                                )
                                for r in rows
                            ),
                            ZERO,
                        )
                    ),
                }
                for lag in DELAYS
            },
            "note": "PAIRED_ONLY_PARTIAL_EPISODES_HINDSIGHT_NO_PORTFOLIO",
        },
        "risk_assumption": {
            "gross_usdc_cap_per_independent_episode": str(RESEARCH_GROSS_NOTIONAL_PER_EPISODE),
            "cross_wallet_shared_volume_accounted": False,
            "cross_episode_concurrent_account_gross_cap_accounted": False,
            "source_fill_observation_clock": "UNKNOWN_HISTORICAL",
            "fees_spread_slippage_and_funding": "PM01_STRESSED_MODELED",
        },
        "wallets": rows,
        "qualified_prospective_followers": 0,
        "qualified_wallet_portfolio_combinations": 0,
        "quarter_completeness": "PARTIAL_CLOSED_EPISODES_ONLY_NOT_WHOLE_MANAGER",
        "statistically_valid_challenge_pass_probability": None,
        "live_risk_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--hyperx-generations", type=Path, nargs="*", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = study(
        args.research_root,
        args.market_root,
        generations=tuple(args.hyperx_generations),
    )
    path, digest = save_private_artifact(args.out, result, "episodes")
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "wallets": result["wallet_count"],
                "calendar_days": result["calendar_days"],
                "completed_source_episodes": result["historical_episodes_considered"],
                "per_lag_totals": result["per_lag_totals"],
                "market_sha_verified_days": result["market_consumed_day_count"],
                "qualified_prospective_followers": 0,
                "sha256": digest,
                "artifact": str(path),
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
