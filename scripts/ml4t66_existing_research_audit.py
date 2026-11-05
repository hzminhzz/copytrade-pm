"""Cross-check historical ML4T-66 scorecard against SQLite and original fills.

No broker/API access, no new economic estimator, no registry writes.
Contrasts static precomputed rankings and their advertised diversification against
the actual trade-instrument inventory and supported same-coin source intervals.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import os
from statistics import median
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path

from copytrade_pm.pm_ml4t_batch_recovery import local_sources, roster

BASE = Path("/home/quant/dev/copytrade-pm")
SUPPLEMENTAL = Path(
    "/home/quant/.local/share/copytrade/reports/ml4t66-public-fills-g20261105-01/normalized"
)
TOP_COMBOS = [
    ("M52", "M56", "M10"),  # old precomputed leader; must test its hidden HYPE overlap
    ("M33", "M42", "M53"),  # earlier Sprint shortlist; overlapping BTC shorts/longs
    ("M10", "M42", "M53"),  # swing structural alternative
    ("M52", "M33", "M10"),
    ("M10", "M33", "M53"),  # 3 multi-session/swing verified-span hypothesis
    ("M52", "M42", "M53"),  # ETH/BTC/SOL fill-notional diversification hypothesis
]


def _numeric(value: object) -> float | None:
    try:
        val = float(value)
    except TypeError, ValueError:
        return None
    return val if math.isfinite(val) else None


def known_intervals(fills: list[dict]) -> tuple[dict[str, list[tuple[int, int, int]]], dict]:
    """Graph-order same-ms fills (as Phase 7), then validate adjacent positions.

    A unique before->after trail is required. Unresolved same-ms groups are
    quarantined; only bounded, supported post-fill intervals are counted.
    This is NOT an atomic initial account book or real follower receipt.
    """
    by_coin = defaultdict(lambda: defaultdict(list))
    stats = Counter()
    for event in fills:
        ms = event.get("time")
        position = _numeric(event.get("startPosition", event.get("start_position")))
        size = _numeric(event.get("sz"))
        if (
            type(ms) is int
            and ms > 0
            and position is not None
            and size is not None
            and size > 0
            and event.get("side") in ("A", "B")
        ):
            # Integers scaled to 1e8 ensure consistent edge identity with
            # decimal source position precision; no chronological TID sort.
            before = round(position * 100_000_000)
            after = round((position + size * (1 if event["side"] == "B" else -1)) * 100_000_000)
            if before != after:
                by_coin[event["coin"]][ms].append((before, after))
    output = defaultdict(list)
    for coin, minutes in by_coin.items():
        grouped = []
        for ms, edges in sorted(minutes.items()):
            if len(edges) == 1:
                grouped.append((ms, edges[0][0], edges[0][1], True))
                continue
            from_counts = Counter(a for a, _ in edges)
            to_counts = Counter(b for _, b in edges)
            start = [
                k for k in set(from_counts) | set(to_counts) if from_counts[k] - to_counts[k] == 1
            ]
            end = [
                k for k in set(from_counts) | set(to_counts) if to_counts[k] - from_counts[k] == 1
            ]
            if (
                len(start) != 1
                or len(end) != 1
                or any(
                    abs(from_counts[k] - to_counts[k]) > 1
                    for k in set(from_counts) | set(to_counts)
                )
            ):
                stats["unresolved_same_timestamp_groups"] += 1
                grouped.append((ms, 0, 0, False))
                continue
            adjacency = defaultdict(list)
            for a, b in edges:
                adjacency[a].append(b)
            stack = [start[0]]
            walk = []
            while stack:
                top = stack[-1]
                if adjacency[top]:
                    stack.append(adjacency[top].pop())
                else:
                    walk.append(stack.pop())
            walk.reverse()
            if len(walk) != len(edges) + 1 or walk[0] != start[0] or walk[-1] != end[0]:
                stats["unresolved_same_timestamp_groups"] += 1
                grouped.append((ms, 0, 0, False))
                continue
            stats["resolved_same_timestamp_groups"] += 1
            grouped.append((ms, start[0], end[0], True))
        for earlier, later in zip(grouped, grouped[1:]):
            ms, _, after, valid = earlier
            next_ms, next_before, _, next_valid = later
            if not valid or not next_valid:
                stats["unanchored_group_boundary"] += 1
                continue
            if after != next_before:
                stats["position_discontinuities"] += 1
                continue
            if after == 0:
                continue
            output[coin].append((ms, next_ms, 1 if after > 0 else -1))
            stats["verified_between_fill_intervals"] += 1
            stats["interval_ms"] += next_ms - ms
    return dict(output), dict(stats)


def supported_position_spans(intervals: dict[str, list[tuple[int, int, int]]]) -> dict:
    """Descriptive uninterrupted same-direction segments, not certified full trades."""
    spans: list[float] = []
    for leg in intervals.values():
        previous: tuple[int, int, int] | None = None
        for start, end, direction in sorted(leg):
            if previous is not None and previous[1] == start and previous[2] == direction:
                previous = (previous[0], end, direction)
            else:
                if previous is not None:
                    spans.append((previous[1] - previous[0]) / 3_600_000)
                previous = (start, end, direction)
        if previous is not None:
            spans.append((previous[1] - previous[0]) / 3_600_000)
    spans.sort()
    return {
        "supported_same_side_spans": len(spans),
        "median_supported_span_hours": round(median(spans), 2) if spans else None,
        "p75_supported_span_hours": round(spans[int((len(spans) - 1) * 0.75)], 2)
        if spans
        else None,
        "spans_at_least_24h": sum(s >= 24 for s in spans),
        "spans_at_least_48h": sum(s >= 48 for s in spans),
        "verified_position_hours_sum_by_leg": round(sum(spans), 2),
        "whole_wallet_hold_times_verified": False,
    }


def overlap(
    a: dict[str, list[tuple[int, int, int]]], b: dict[str, list[tuple[int, int, int]]]
) -> dict:
    same = opposite = 0
    coins = []
    for coin in sorted(a.keys() & b.keys()):
        left, right = a[coin], b[coin]
        i = j = 0
        equal_ms = opposite_ms = 0
        while i < len(left) and j < len(right):
            p, q = left[i], right[j]
            width = max(0, min(p[1], q[1]) - max(p[0], q[0]))
            if p[2] == q[2]:
                equal_ms += width
            else:
                opposite_ms += width
            if p[1] <= q[1]:
                i += 1
            else:
                j += 1
        if equal_ms or opposite_ms:
            coins.append(
                {
                    "market": coin,
                    "same_direction_hours": round(equal_ms / 3_600_000, 2),
                    "opposite_direction_hours": round(opposite_ms / 3_600_000, 2),
                }
            )
        same += equal_ms
        opposite += opposite_ms
    return {
        "common_markets_with_overlap": coins,
        "observed_same_hours": round(same / 3_600_000, 2),
        "observed_opposite_hours": round(opposite / 3_600_000, 2),
        "observed_opposite_fraction": round(opposite / (same + opposite), 5)
        if same + opposite
        else None,
    }


def historical_source_cash_diagnostic(fills: list[dict], equity: str | None) -> dict:
    """Retrospective source closedPnL, NOT a follower replay or MTM curve.

    Exact user k formula is applied to a static scalar without an observation
    timestamp; it cannot establish point-in-time follower sizing.
    """
    if equity is None:
        return {"status": "UNKNOWN_SOURCE_EQUITY_SCALAR"}
    source_equity = Decimal(equity)
    if source_equity <= 0:
        return {"status": "INVALID_SOURCE_EQUITY_SCALAR"}
    k = (Decimal(1) / Decimal(3)) * min(Decimal("0.35"), Decimal(10000) / source_equity)
    amount = Decimal(0)
    fees = Decimal(0)
    turnover = Decimal(0)
    known = 0
    for event in fills:
        closed = event.get("closed_pnl", event.get("closedPnl"))
        if closed is None or event.get("fee") is None:
            continue
        amount += Decimal(str(closed))
        fees += Decimal(str(event["fee"]))
        turnover += Decimal(str(event["px"])) * Decimal(str(event["sz"]))
        known += 1
    if known != len(fills):
        return {"status": "PARTIAL_SOURCE_CLOSED_PNL_MISSING", "missing_rows": len(fills) - known}
    # Original source closedPnL and fees are retrospective, not independently
    # matched to executable follower prices. No missing funding/MTM filled.
    return {
        "status": "LEADER_HINDSIGHT_ONLY",
        "static_equity_scalar_usd": str(round(source_equity, 2)),
        "reference_weight_per_pod": "1/3",
        "k_effective_static": str(round(k, 8)),
        "leader_closed_pnl_usd": str(round(amount, 2)),
        "leader_reported_fees_usd": str(round(fees, 2)),
        "static_k_scaled_leader_closed_minus_reported_fee_usd": str(round((amount - fees) * k, 2)),
        "raw_turnover_after_static_k_usd": str(round(turnover * k, 2)),
        "raw_6bps_round_side_cost_proxy_usd": str(round(turnover * k * Decimal("0.0006"), 2)),
        "source_pnl_after_6bps_raw_turnover_proxy_usd": str(
            round((amount - turnover * Decimal("0.0006")) * k, 2)
        ),
        "source_only_not_follower_net_mtm": True,
        "cost_proxy_uses_unbatched_leader_price_not_future_native_execution": True,
    }


def run(db: Path, source: Path, docs: Path, supplement: Path = SUPPLEMENTAL) -> dict:
    identities, cohort_sha = roster(db)
    stores, local = local_sources(source, identities, extra_source_dirs=(supplement,))
    scorepath = docs / "ML4T_66_MASTER_SCORECARD.csv"
    profilepath = docs / "ML4T_66_STRUCTURAL_PROFILES.csv"
    combopath = docs / "ML4T_66_TOP20_PRECOMPUTED_ENSEMBLES.csv"
    corrpath = docs / "ML4T_66_CORRELATION_MATRIX_TOP25.csv"
    conflictpath = docs / "ML4T_66_DIRECTIONAL_CONFLICT_MATRIX.csv"
    with scorepath.open(newline="") as handle:
        scores = list(csv.DictReader(handle))
    with profilepath.open(newline="") as handle:
        profiles = {x["address"].lower(): x for x in csv.DictReader(handle)}
    with combopath.open(newline="") as handle:
        combos = list(csv.DictReader(handle))
    with conflictpath.open(newline="") as handle:
        conflicts = list(csv.DictReader(handle))
    with corrpath.open(newline="") as handle:
        corr = list(csv.DictReader(handle))
    by_alias = {details["alias"]: (address, details) for address, details in identities.items()}
    if len(by_alias) != len(identities):
        raise ValueError("SQLITE_ALIAS_COLLISION_IN_COHORT")
    mismatches = []
    missing = []
    score_alias = set()
    for row in scores:
        alias = row["alias"]
        addr = row["address"].lower()
        if alias not in by_alias or by_alias[alias][0] != addr:
            mismatches.append({"alias": alias, "reason": "NOT_CURRENT_SQLITE_ALIAS_ADDRESS"})
            continue
        score_alias.add(alias)
        n = len(stores[addr]["events"])
        claimed = int(row["total_fills"])
        if claimed != n:
            mismatches.append(
                {
                    "alias": alias,
                    "scorecard_fills": claimed,
                    "source_unique_fills": n,
                    "reason": "PRECOMPUTED_FILL_COUNT_OUTDATED",
                }
            )
    for alias in sorted(by_alias):
        if alias not in score_alias:
            missing.append(alias)
    focus = {}
    intervals = {}
    for alias in sorted(set(sum((list(c) for c in TOP_COMBOS), []))):
        addr = by_alias[alias][0]
        fills = list(stores[addr]["events"].values())
        agg = Counter()
        for event in fills:
            px, qty = _numeric(event.get("px")), _numeric(event.get("sz"))
            if px is not None and qty is not None:
                agg[event["coin"]] += px * qty
        positions, stats = known_intervals(fills)
        intervals[alias] = positions
        profile = profiles.get(addr, {})
        focus[alias] = {
            "address": addr,
            "source_realized_cash_diagnostic": historical_source_cash_diagnostic(
                fills,
                stores[addr]["equity_values"][0]
                if len(set(stores[addr]["equity_values"])) == 1
                else None,
            ),
            "actual_fills": len(fills),
            "claimed_style": profile.get("style"),
            "claimed_primary_coin": profile.get("primary_coin"),
            "top_native_turnover_markets": [
                {"coin": c, "gross_leader_notional_share": round(v / sum(agg.values()), 4)}
                for c, v in agg.most_common(8)
            ]
            if agg
            else [],
            "all_traded_market_count": len(agg),
            "position_chain": stats,
            "supported_position_spans": supported_position_spans(positions),
            "asof_source_equity_verified": False,
            "historical_first_known_verified": False,
        }
    pairs = {}
    for combo in TOP_COMBOS:
        for index, a in enumerate(combo):
            for b in combo[index + 1 :]:
                key = "+".join(sorted((a, b)))
                pairs[key] = overlap(intervals[a], intervals[b])
    high_rank = [row["pod_combination"] for row in combos[:3]]
    conditional_combos = []
    for candidate in TOP_COMBOS:
        cash = [focus[alias]["source_realized_cash_diagnostic"] for alias in candidate]
        valid = all(x.get("status") == "LEADER_HINDSIGHT_ONLY" for x in cash)
        conditional_combos.append(
            {
                "members": candidate,
                "status": "RETROSPECTIVE_SOURCE_CLOSED_PNL_ONLY"
                if valid
                else "BLOCKED_SOURCE_ACCOUNT",
                "sum_static_scaled_leader_closed_minus_fees_usd": (
                    str(
                        sum(
                            Decimal(x["static_k_scaled_leader_closed_minus_reported_fee_usd"])
                            for x in cash
                        )
                    )
                    if valid
                    else None
                ),
                "sum_static_scaled_leader_closed_minus_raw_6bps_proxy_usd": (
                    str(
                        sum(
                            Decimal(x["source_pnl_after_6bps_raw_turnover_proxy_usd"]) for x in cash
                        )
                    )
                    if valid
                    else None
                ),
                "portfolio_net_mtm_usd": None,
                "portfolio_intraday_drawdown_usd": None,
                "full_contract_pass": None,
                "historical_first_known": False,
            }
        )
    return {
        "schema": "ml4t66_readonly_existing_research_document_audit_v1",
        "source": "SQLITE_ADDRESS_AND_SHA_AUDITED_LOCAL_SOURCE",
        "cohort_source_sha256": cohort_sha,
        "scorecard_sha256": sha256(scorepath.read_bytes()).hexdigest(),
        "precomputed_ensembles_sha256": sha256(combopath.read_bytes()).hexdigest(),
        "profile_sha256": sha256(profilepath.read_bytes()).hexdigest(),
        "scorecard_entries": len(scores),
        "scorecard_distinct_aliases": len(score_alias),
        "scorecard_missing_current_sqlite_aliases": missing,
        "stale_scorecard_rows": mismatches,
        "stale_scorecard_row_count": len(mismatches),
        "local_source": local,
        "precomputed_top_three": high_rank,
        "illustrative_hindsight_source_cash_combinations": conditional_combos,
        "precomputed_conflict_matrix_rows": len(conflicts),
        "precomputed_conflict_matrix_nonzero_rows": sum(
            _numeric(x["opposite_hold_pct"]) not in (None, 0) for x in conflicts
        ),
        "precomputed_correlation_matrix_rows": len(corr),
        "rechecked_focus_wallets": focus,
        "empirical_pairwise_known_chain_overlap": pairs,
        "scientific_qualified": False,
        "reliable_portfolio_return_or_dd": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--docs", type=Path, required=True)
    p.add_argument("--supplement", type=Path, default=SUPPLEMENTAL)
    p.add_argument("--private-output", type=Path)
    args = p.parse_args()
    report = run(args.db, args.source_root, args.docs, args.supplement)
    if args.private_output is not None:
        target = args.private_output
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.is_symlink() or target.parent.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_AUDIT_DIRECTORY_REQUIRED")
        raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        print("AUDIT_REPORT", str(target), "SHA256", sha256(raw).hexdigest())
    compact = {
        "scorecard_entries": report["scorecard_entries"],
        "stale_rows": report["stale_scorecard_rows"],
        "source_wallet_count": report["local_source"]["wallets_with_fills"],
        "top_three_pods": report["precomputed_top_three"],
        "precomputed_conflict_nonzero_rows": report["precomputed_conflict_matrix_nonzero_rows"],
        "observed_pair_overlaps": report["empirical_pairwise_known_chain_overlap"],
        "wallets": report["rechecked_focus_wallets"],
        "status": "PRECOMPUTED_ARTIFACTS_UNQUALIFIED",
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
