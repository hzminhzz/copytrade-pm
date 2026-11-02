"""Execute retrospective A/B/C equity-weight *proxy*, without manufactured hourly NAV.

Uses previously observed official perps account-value points (sparse, obtained
after Q3), with strictly previous-observation carry and an explicit age ceiling.
This is NOT the strict pm_historical_equity contract: no pretend cash-flow
reconciliation, continuous wallet book, or July first-local receipt.

Every action is the entire observed source-position vector scaled by
pod_capital / the latest prior observed positive source equity. Missing follower
trades do not become new source signals; blocked NAV events do not zero source
inventory. Exact PM03 account owns financial bookkeeping, including PM risk.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

from .pm_historical_combos import (
    ALL_WALLETS,
    END,
    POD_CAPITAL_USD,
    PORTFOLIOS,
    QUANTITY_GRID,
    START,
    WAIT,
    _minute_at_or_after,
    _native_pm,
    _run_combo,
    _source_inputs,
)
from .pm_historical_portfolio_equity import inspect_portfolio
from .pm_research import _write_private_evidence
from .pm_shadow import MarketDataBlocked, MinuteBar, VerifiedHyperliquidMinuteSource
from .pm_sources import load_cohort

ZERO = D("0")
SCHEMA = "pm_q3_sparse_equity_weight_three_pod_oracle_v1"
PORTFOLIO_GROSS_CAPS = (D("6000"), D("18000"), D("9000"))


@dataclass(frozen=True)
class SparsePoint:
    at: datetime
    equity_usd: D


@dataclass
class SparseEquity:
    points: dict[str, tuple[SparsePoint, ...]]
    source_hashes: dict[str, str]
    metadata: dict[str, dict]
    observed_at: dict[str, str]

    def asof(self, wallet: str, when: datetime, *, max_age: timedelta):
        points = self.points[wallet]
        pos = bisect_right([p.at for p in points], when) - 1
        if pos < 0:
            return None, "BEFORE_FIRST_SOURCE_EQUITY", None
        sample = points[pos]
        age = when - sample.at
        if age > max_age:
            return None, "SOURCE_EQUITY_TOO_OLD", age
        if sample.equity_usd <= ZERO:
            return None, "NONPOSITIVE_SOURCE_EQUITY", age
        return sample.equity_usd, "OBSERVED_SPARSE_SOURCE_EQUITY", age


class BoundedCarryMinuteMarket:
    """No invented bar; carry a verified previous-minute price with known age."""

    def __init__(
        self,
        root: Path,
        *,
        max_minutes: int = 2,
        native_source: VerifiedHyperliquidMinuteSource | None = None,
    ):
        if not 0 <= max_minutes <= 1440:
            raise ValueError("BOUNDED_CARRY_MINUTES_OUT_OF_RANGE")
        self.native = (
            native_source if native_source is not None else VerifiedHyperliquidMinuteSource(root)
        )
        self.max_minutes = max_minutes
        self.last_seen: dict[str, MinuteBar] = {}
        self.diagnostics = Counter()
        self.failures: list[dict] = []
        self.max_carried_age_seconds = 0.0

    @property
    def source_days(self):
        return self.native.source_days

    def get(self, instrument: str, when: datetime) -> MinuteBar:
        try:
            bar = self.native.get(instrument, when)
        except MarketDataBlocked as exc:
            # Data-integrity violations, missing full days and wrong markets
            # are never bridged by a last price.
            if str(exc) != "MISSING_EXACT_1M_BAR":
                self.failures.append(
                    {"instrument": instrument, "when": when.isoformat(), "error": str(exc)}
                )
                raise
            last = self.last_seen.get(instrument)
            age = (when - last.timestamp).total_seconds() if last else None
            if last is None or age is None or not 0 < age <= self.max_minutes * 60:
                self.failures.append(
                    {
                        "instrument": instrument,
                        "when": when.isoformat(),
                        "error": str(exc),
                        "last_observed": last.timestamp.isoformat() if last else None,
                        "age_seconds": age,
                    }
                )
                raise
            self.max_carried_age_seconds = max(self.max_carried_age_seconds, age)
            self.diagnostics["stale_open_price_proxy_bars"] += 1
            return MinuteBar(last.timestamp, last.open, ZERO, last.source_sha256)
        self.last_seen[instrument] = bar
        return bar


def _private_history(
    root: Path,
    wallet: str,
    *,
    expected_sha: str,
    source: str,
) -> tuple[tuple[SparsePoint, ...], dict, str, str]:
    raw_path = root / "raw" / wallet / "portfolio.json"
    meta_path = root / "metadata" / wallet / "portfolio.json"
    if source == "C":
        raw_path = root / "info_raw" / wallet / "portfolio.json"
        meta_path = root / "info_metadata" / wallet / "portfolio.json"
    raw = raw_path.read_bytes()
    meta = json.loads(meta_path.read_bytes())
    digest = sha256(raw).hexdigest()
    advertised = meta.get("raw_sha256") if source == "AB" else meta.get("sha256")
    if advertised != digest:
        raise ValueError("PORTFOLIO_EQUITY_SOURCE_SHA_MISMATCH")
    if source == "AB" and (
        meta.get("wallet") != wallet or meta.get("wallet_identity_sha256") != expected_sha
    ):
        raise ValueError("PORTFOLIO_EQUITY_WALLET_IDENTITY_MISMATCH")
    inspected = inspect_portfolio(json.loads(raw))
    if inspected["q3_points"] < 1:
        raise ValueError("NO_RETROSPECTIVE_Q3_SOURCE_EQUITY")
    # Include the most recent pre-July anchor ONLY if independently present.
    parts = dict(json.loads(raw))
    vals = parts["perpAllTime"]["accountValueHistory"]
    points = tuple(
        SparsePoint(datetime.fromtimestamp(ms / 1000, UTC), D(str(value)))
        for ms, value in vals
        if ms < int(END.timestamp() * 1000)
    )
    if not points:
        raise ValueError("SOURCE_EQUITY_HISTORY_EMPTY")
    return points, inspected, digest, meta["received_at"]


def load_sparse_equity(root: Path, ab_root: Path, c_root: Path) -> SparseEquity:
    cohort, _ = load_cohort(root)
    identities = {entry.alias: entry.address_sha256 for entry in cohort}
    if any(wallet not in identities for wallet in ALL_WALLETS):
        raise ValueError("SPARSE_EQUITY_ALIAS_NOT_IN_FROZEN_COHORT")
    points = {}
    details = {}
    hashes = {}
    receipts = {}
    for wallet in ALL_WALLETS:
        source = "C" if wallet in PORTFOLIOS["C"] else "AB"
        history, audit, digest, received = _private_history(
            ab_root if source == "AB" else c_root,
            wallet,
            expected_sha=identities[wallet],
            source=source,
        )
        points[wallet] = history
        details[wallet] = {
            **audit,
            "wallet_id_scope": "SINGLE_MASTER_PERP_HISTORY_NOT_CONSOLIDATED_SUBACCOUNTS",
            "local_alias_binding": (
                "FROZEN_SHA_VERIFIED"
                if source == "AB"
                else "EXISTING_E4_COLLECTOR_ALIAS_UNDER_FROZEN_COHORT"
            ),
            "source_observations_retrieved_after_study": True,
        }
        hashes[wallet] = digest
        receipts[wallet] = received
    return SparseEquity(points, hashes, details, receipts)


def source_actions(
    episodes: dict[str, list],
    trio: tuple[str, str, str],
    equity: SparseEquity,
    *,
    max_age_days: int = 8,
    pod_capital: D = POD_CAPITAL_USD,
) -> tuple[list[tuple], dict]:
    if not 1 <= max_age_days <= 21 or pod_capital <= ZERO:
        raise ValueError("INVALID_EXPLORATORY_EQUITY_SCENARIO")
    actions = defaultdict(dict)
    audit: dict[str, dict] = {}
    for wallet in trio:
        counters = Counter()
        ages: list[float] = []
        source_rows = sorted(
            (
                (row[0], row[1], episode.coin, row[4])
                for episode in episodes[wallet]
                for row in episode.events
            ),
            key=lambda item: (item[0], item[1], item[2]),
        )
        index = 0
        book = {}
        updates: dict[datetime, dict] = {}
        while index < len(source_rows):
            due = _minute_at_or_after(source_rows[index][0] + WAIT)
            while index < len(source_rows) and source_rows[index][0] < due:
                _, _, coin, after = source_rows[index]
                native = _native_pm(coin)
                if after:
                    book[native] = after
                else:
                    book.pop(native, None)
                counters["source_fill_transition_events"] += 1
                index += 1
            if due < END:
                updates[due] = dict(book)
                counters["source_snapshot_decisions"] += 1
        # Official NAV is a real retrospective observation. Its timestamp
        # becomes an independent *sizing* tick, not a fabricated source fill.
        nav_ticks = {
            _minute_at_or_after(point.at + WAIT + timedelta(microseconds=1))
            for point in equity.points[wallet]
            if START <= point.at < END
        }
        initialized = False
        book = {}
        for due in sorted(set(updates) | nav_ticks):
            if due >= END:
                continue
            if due in updates:
                book = updates[due]
                initialized = True
            if not initialized:
                counters["equity_tick_without_reconstructed_source_book"] += 1
                continue
            if not book:
                # A verified source position closure is not a new-risk trade.
                if due in updates:
                    actions[due][wallet] = {}
                    counters["explicit_source_flat_target"] += 1
                continue
            nav, status, age = equity.asof(wallet, due, max_age=timedelta(days=max_age_days))
            if nav is None:
                # Skip the follower sizing UPDATE, not its previously held
                # book. Record tracking unknown and reconcile next NAV.
                counters["skipped_sizing_decisions_" + status] += 1
                continue
            if age is not None:
                ages.append(age.total_seconds() / 3600)
                if age > timedelta(hours=1):
                    counters["sizing_using_nav_older_than_1h"] += 1
            targets = {
                inst: (qty * pod_capital / nav).quantize(QUANTITY_GRID)
                for inst, qty in sorted(book.items())
            }
            if not targets:
                continue
            actions[due][wallet] = targets
            counters["equity_weight_target_actions"] += 1
            if due in nav_ticks:
                counters["equity_only_rebalance_actions"] += 1
        audit[wallet] = {
            "accepted_episodes": len(episodes[wallet]),
            "source_event_count": len(source_rows),
            "source_rebalance_batches": len(updates),
            "official_q3_nav_samples": equity.metadata[wallet]["q3_points"],
            "max_forward_carried_nav_hours": max(ages) if ages else None,
            "median_forward_carried_nav_hours": sorted(ages)[len(ages) // 2] if ages else None,
            "source_nav_follower_first_known_q3": False,
            "counters": dict(counters),
        }
    return sorted(actions.items()), audit


def _scenario(
    name: str,
    trio: tuple[str, str, str],
    episodes: dict,
    equity: SparseEquity,
    root: Path,
    *,
    max_age_days: int,
    costs_x: D,
    max_stale_mark_minutes: int = 180,
    native_market: VerifiedHyperliquidMinuteSource | None = None,
    capacity_enforced: bool = False,
) -> dict:
    actions, sizing = source_actions(
        episodes,
        trio,
        equity,
        max_age_days=max_age_days,
    )
    market = BoundedCarryMinuteMarket(
        root,
        max_minutes=max_stale_mark_minutes,
        native_source=native_market,
    )
    result = _run_combo(
        name,
        trio,
        episodes,
        {wallet: D(1) for wallet in trio},
        market,
        actions_override=actions,
        risk_limits=PORTFOLIO_GROSS_CAPS,
        cost_multiplier=costs_x,
        measure_tracking=True,
        capacity_enforced=capacity_enforced,
    )
    result["equity_sizing"] = sizing
    result["size_method"] = "SOURCE_SIGNED_QTY_TIMES_2000_DIV_LATEST_PREVIOUS_OFFICIAL_NAV"
    result["source_equity_clock"] = "RETROSPECTIVE_VENDOR_EVENT_ORACLE_NOT_FIRST_KNOWN"
    result["missing_equity_action"] = "SKIP_DECISION_KEEP_PREVIOUS_FOLLOWER_POSITION"
    result["max_prior_nav_age_days"] = max_age_days
    result["costs_multiplier"] = str(costs_x)
    result["capacity_enforced"] = capacity_enforced
    result["capacity_volume_reference"] = (
        "PRIOR_COMPLETED_1MIN_BAR_AT_ORDER_OPEN"
        if capacity_enforced
        else "CURRENT_1MIN_FINAL_VOLUME_DIAGNOSTIC_ONLY_NONCAUSAL"
    )
    result["carried_native_minute_proxy_count"] = market.diagnostics["stale_open_price_proxy_bars"]
    result["max_carried_price_age_seconds"] = market.max_carried_age_seconds
    result["max_allowed_stale_price_minutes"] = max_stale_mark_minutes
    result["market_failure"] = market.failures[-1] if market.failures else None
    result["native_market_day_hashes_used"] = len(market.source_days)
    result["performance_comparable_full_quarter"] = False
    result["executable_follower_pnl_verified"] = False
    return result


def study(
    source_root: Path,
    market_root: Path,
    ab_root: Path,
    c_root: Path,
    *,
    mixed: bool = False,
    max_stale_mark_minutes: int = 180,
    mixed_offset: int = 0,
    mixed_count: int | None = None,
    only_mixed: bool = False,
    custom_trio: tuple[str, str, str] | None = None,
    only_custom: bool = False,
) -> dict:
    if mixed_offset < 0 or mixed_count is not None and mixed_count < 1:
        raise ValueError("INVALID_MIXED_PORTFOLIO_BATCH")
    if only_mixed and not mixed:
        raise ValueError("MIXED_BATCH_REQUIRED")
    if only_custom and custom_trio is None:
        raise ValueError("CUSTOM_TRIO_REQUIRED")
    if custom_trio is not None and (
        len(custom_trio) != 3
        or len(set(custom_trio)) != 3
        or not set(custom_trio).issubset(ALL_WALLETS)
    ):
        raise ValueError("CUSTOM_TRIO_MUST_BE_THREE_FROZEN_WALLETS")
    equity = load_sparse_equity(source_root, ab_root, c_root)
    # Only source fills and existing immutable native-market data. No
    # mutation, no wallet-fill API call, no live order route.
    market = VerifiedHyperliquidMinuteSource(market_root)
    episodes, audits, _, source = _source_inputs(source_root, market, ())
    results = []
    scenarios = (
        ("BASE_8D_1X", 8, D("1"), False),
        ("NAV_16D_1X", 16, D("1"), False),
        ("COST_8D_2X", 8, D("2"), False),
        ("CAPACITY_8D_1X", 8, D("1"), True),
    )
    for label, days, costs, capacity in [] if only_mixed or only_custom else scenarios:
        for name, trio in PORTFOLIOS.items():
            results.append(
                _scenario(
                    name,
                    trio,
                    episodes,
                    equity,
                    market_root,
                    max_age_days=days,
                    costs_x=costs,
                    max_stale_mark_minutes=max_stale_mark_minutes,
                    native_market=market,
                    capacity_enforced=capacity,
                )
                | {"scenario": label}
            )
    if custom_trio is not None:
        for label, days, costs, capacity in scenarios:
            results.append(
                _scenario(
                    "CUSTOM_" + "_".join(custom_trio),
                    custom_trio,
                    episodes,
                    equity,
                    market_root,
                    max_age_days=days,
                    costs_x=costs,
                    max_stale_mark_minutes=max_stale_mark_minutes,
                    native_market=market,
                    capacity_enforced=capacity,
                )
                | {"scenario": label}
            )
    if mixed:
        frozen = set(PORTFOLIOS.values())
        all_mixed = [trio for trio in combinations(ALL_WALLETS, 3) if trio not in frozen]
        chosen = all_mixed[mixed_offset : (mixed_offset + mixed_count) if mixed_count else None]
        for trio in chosen:
            results.append(
                _scenario(
                    "MIX_" + "_".join(trio),
                    trio,
                    episodes,
                    equity,
                    market_root,
                    max_age_days=8,
                    costs_x=D(1),
                    max_stale_mark_minutes=max_stale_mark_minutes,
                    native_market=market,
                )
                | {"scenario": "BASE_8D_1X"}
            )
    return {
        "schema": SCHEMA,
        "status": "EXECUTED_SPARSE_NAV_EQUITY_WEIGHT_PROXY",
        "source_window_inclusive_start": START.isoformat(),
        "source_window_exclusive_end": END.isoformat(),
        "account_initial_usd": "10000",
        "pod_capital_usd": str(POD_CAPITAL_USD),
        "study_days": (END - START).days,
        "portfolio_membership": {k: list(v) for k, v in PORTFOLIOS.items()},
        "source_account_nav_audit": equity.metadata,
        "source_account_raw_sha256": equity.source_hashes,
        "source_account_retrieved_at": equity.observed_at,
        "source_fill_manifests": source["source_manifests_sha256"],
        "propr_browser_scope_sha256": source["public_snapshot_sha256"],
        "source_episode_eligibility": {
            w: {
                "candidates": v.get("q3_completed_candidate_episodes"),
                "admitted": v.get("accepted_episode_count"),
                "excluded_reasons": v.get("excluded_reasons"),
                "source_gaps": v.get("source_gaps"),
            }
            for w, v in audits.items()
        },
        "custom_trio": list(custom_trio) if custom_trio is not None else None,
        "mixed_batch": {
            "offset": mixed_offset,
            "count_requested": mixed_count,
            "total_mixed_available": 81,
            "executed_mixed_count": sum(r["name"].startswith("MIX_") for r in results),
            "only_mixed": only_mixed,
        },
        "scenarios": [
            {
                "name": label,
                "nav_prior_max_days": days,
                "cost_multiplier": str(costs),
                "capacity_enforced": capacity,
            }
            for label, days, costs, capacity in scenarios
        ],
        "risk_caps_usd": {
            "pod_gross": str(PORTFOLIO_GROSS_CAPS[0]),
            "account_gross": str(PORTFOLIO_GROSS_CAPS[1]),
            "instrument_gross": str(PORTFOLIO_GROSS_CAPS[2]),
        },
        "execution": {
            "wait_seconds": 300,
            "market": "SHA_CHECKED_NATIVE_HL_1M_EXPLORATORY_OPEN",
            "minute_gap": "HOLD_LAST_VERIFIED_NATIVE_BAR_OPEN_FOR_MARK_ONLY_NO_ORDER_WHILE_STALE",
            "max_stale_mark_minutes": max_stale_mark_minutes,
            "fees_spread_slippage_funding": "MODEL_ASSUMPTIONS_NOT_REAL_BROKER",
            "volume_capacity": "DIAGNOSTIC_ONLY_NO_EXECUTABILITY_PROOF",
        },
        "limitations": [
            "NAV observations typically weekly, sampled retrospectively with up to 16d past-only carry; not actual as-of NAV",
            "Master-only perp account-value history, potentially separate subaccount funds and positions",
            "Completed flat-to-flat episode filtering and Oct30 Propr display selection are ex-post biased",
            "Missing source fills and unsupported markets may remove hedges; no complete historical book",
            "No Q3 source first-known follower receipt; five-minute modeled event-time execution is a hindsight oracle",
            "Source equity zero or stale means skip target update and retain previous follower inventory, not a true wallet book",
            "Shared account uses PM03 modeled risk floors and conservative hypothetical costs",
        ],
        "results": results,
        "valid_90day_wallet_combo_selection": False,
        "actual_source_equity_normalized_full_portfolios": 0,
        "broker_authorized": False,
        "scientifically_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--ab-equity-root", type=Path, required=True)
    parser.add_argument("--c-equity-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mixed", action="store_true")
    parser.add_argument("--max-stale-mark-minutes", type=int, default=180)
    parser.add_argument("--mixed-offset", type=int, default=0)
    parser.add_argument("--mixed-count", type=int)
    parser.add_argument("--only-mixed", action="store_true")
    parser.add_argument("--combo", nargs=3, metavar=("WALLET1", "WALLET2", "WALLET3"))
    parser.add_argument("--only-combo", action="store_true")
    args = parser.parse_args()
    report = study(
        args.research_root,
        args.market_root,
        args.ab_equity_root,
        args.c_equity_root,
        mixed=args.mixed,
        max_stale_mark_minutes=args.max_stale_mark_minutes,
        mixed_offset=args.mixed_offset,
        mixed_count=args.mixed_count,
        only_mixed=args.only_mixed,
        custom_trio=tuple(args.combo) if args.combo else None,
        only_custom=args.only_combo,
    )
    path, digest = _write_private_evidence(args.out, report)
    print(
        json.dumps(
            {
                "report": str(path),
                "sha256": digest,
                "schema": SCHEMA,
                "results": [
                    {
                        "scenario": r["scenario"],
                        "portfolio": r["name"],
                        "status": r["status"],
                        "stop_reason": r.get("stop_reason"),
                        "pnl_usd_partial": r.get("pnl_usd"),
                        "observed_through": r.get("observed_through"),
                        "source_batches_with_equity": sum(
                            q["counters"].get("equity_weight_target_actions", 0)
                            for q in r["equity_sizing"].values()
                        ),
                    }
                    for r in report["results"]
                    if r["name"] in PORTFOLIOS or (args.combo and r["wallets"] == args.combo)
                ],
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
