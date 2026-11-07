"""Exploratory, read-only seven-day wallet screening; no economic certification."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

DATA = Path("/tmp/vike7d_432.json")
DB = "file:/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite?mode=ro"
CUTOFF = datetime(2026, 11, 7, 1, 9, 35, tzinfo=timezone.utc)


def numeric(v: object) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def load() -> pl.DataFrame:
    raw = json.loads(DATA.read_text())
    rows = []
    for address, d in raw.items():
        if not isinstance(d, dict):
            continue
        m = d.get("metrics") or {}
        e = d.get("equity") or {}
        lt = d.get("lifetime") or {}
        op = d.get("open_positions") or {}
        rows.append({
            "address": address.lower(),
            "has_metrics": bool(d.get("has_metrics")),
            "equity": numeric(e.get("account_value")),
            "pnl7": numeric(m.get("total_realized_pnl")),
            "trades7": numeric(m.get("trade_count")),
            "win_rate": numeric(m.get("win_rate")),
            "pf": numeric(m.get("profit_factor")),
            "dd7": numeric(m.get("max_drawdown_pct")),
            "current_dd7": numeric(m.get("current_drawdown_pct")),
            "duration_h": (numeric(m.get("avg_duration_seconds")) or 0) / 3600,
            "roi7_pct": numeric(m.get("pnl_pct")),
            "volume7": numeric(m.get("total_volume")),
            "fees7": numeric(m.get("total_fee")),
            "long_pnl7": numeric(m.get("long_pnl")),
            "short_pnl7": numeric(m.get("short_pnl")),
            "open_unreal": numeric(op.get("unrealized_pnl")),
            "gross_exposure": numeric(op.get("equity_exposure")),
            "last_fill": lt.get("last_fill_ts"),
            "metric_updated": d.get("metrics_updated_at"),
        })
    return pl.DataFrame(rows)


def main() -> None:
    sha = hashlib.sha256(DATA.read_bytes()).hexdigest()
    db = sqlite3.connect(DB, uri=True)
    excluded = {r[0].lower() for r in db.execute(
        "select distinct w.address from exclusions x join wallets w on w.wallet_id=x.wallet_id"
    )}
    aliases = {}
    for a, n, namespace, known in db.execute(
        "select w.address,wa.alias,wa.namespace,wa.known_at "
        "from wallet_aliases wa join wallets w on wa.wallet_id=w.wallet_id"
    ):
        if datetime.fromisoformat(known.replace("Z","+00:00")) <= CUTOFF:
            aliases.setdefault(a.lower(), []).append((namespace, n))
    registry = {r[0].lower() for r in db.execute("select address from wallets")}
    existing = set()
    latest = {}
    for pid, version, alias in db.execute(
        "select portfolio_id,version,member_alias from portfolio_memberships"
    ):
        if pid not in latest or version > latest[pid][0]:
            latest[pid] = (version, [])
        if version == latest[pid][0]:
            latest[pid][1].append(alias)
    for _, members in latest.values():
        existing.add(tuple(sorted(members)))
    df = load().with_columns(
        pl.col("address").is_in(list(excluded)).alias("excluded"),
        pl.col("address").is_in(list(registry)).alias("registered"),
        pl.col("address").is_in(list(aliases)).alias("aliased"),
        pl.col("last_fill").str.to_datetime(strict=False, time_zone="UTC").alias("last_dt"),
        pl.col("metric_updated").str.to_datetime(strict=False, time_zone="UTC").alias("metric_dt"),
    )
    gates = [
        ("registry_not_excluded_aliased", pl.col("registered") & ~pl.col("excluded") & pl.col("aliased")),
        ("seven_day_valid", pl.col("has_metrics") & (pl.col("equity") >= 1000)),
        ("fast_active_positive", (pl.col("trades7") >= 5) & (pl.col("pnl7") > 0) & (pl.col("duration_h") > 0) & (pl.col("duration_h") <= 24)),
        ("fresh", (pl.col("last_dt") >= CUTOFF - __import__("datetime").timedelta(hours=72)) & (pl.col("metric_dt") >= CUTOFF - __import__("datetime").timedelta(hours=72))),
        ("historical_dd", pl.col("dd7") <= 25),
        ("current_dd", pl.col("current_dd7") <= 20),
        ("gross", pl.col("gross_exposure") <= 8),
    ]
    cumulative = pl.lit(True)
    for label, expr in gates:
        cumulative = cumulative & expr
        print("FUNNEL", label, df.filter(cumulative).height)
    print("ALL_REGISTRY_SEVEN_DAY_SCREEN")
    full = df.filter(pl.col("registered") & ~pl.col("excluded") & pl.col("has_metrics") & (pl.col("equity") >= 1000)
        & (pl.col("trades7") >= 5) & (pl.col("pnl7") > 0)
        & (pl.col("duration_h") > 0) & (pl.col("duration_h") <= 24))
    print(full.select([
        pl.len().alias("fast_winners"), pl.col("aliased").sum().alias("aliased"),
        (pl.col("dd7") <= 25).sum().alias("dd25"),
        (pl.col("dd7") <= 40).sum().alias("dd40"),
        (pl.col("current_dd7") <= 20).sum().alias("curdd20"),
        (pl.col("gross_exposure") <= 8).sum().alias("lev8"),
        (pl.col("last_dt") >= CUTOFF - __import__("datetime").timedelta(hours=72)).sum().alias("recent72"),
    ]).to_dicts())
    print("ALL_FULL_SURVIVORS", full.filter((pl.col("dd7") <= 25) & (pl.col("current_dd7") <= 20)).height)
    print("SURVIVORS",full.filter((pl.col("dd7") <= 25) & (pl.col("current_dd7") <= 20)).sort("pnl7",descending=True).select(["address","trades7","pnl7","duration_h","dd7","current_dd7","gross_exposure","open_unreal","aliased"]).to_dicts())
    print("TOP_ALL_FAST", full.sort("pnl7", descending=True).select(["address","trades7","pnl7","duration_h","dd7","current_dd7","gross_exposure","aliased"]).head(25).to_dicts())
    print("REASON_DISTRIBUTION_FAST")
    fast = df.filter(pl.col("registered") & ~pl.col("excluded") & pl.col("aliased") & pl.col("has_metrics") & (pl.col("equity") >= 1000) & (pl.col("trades7") >= 5) & (pl.col("pnl7") > 0) & (pl.col("duration_h") > 0) & (pl.col("duration_h") <= 24))
    print(fast.select([
        pl.len().alias("count"),
        pl.col("dd7").median().alias("median_dd"),
        pl.col("current_dd7").median().alias("median_current_dd"),
        (pl.col("dd7") <= 25).sum().alias("dd25"),
        (pl.col("dd7") <= 40).sum().alias("dd40"),
        (pl.col("current_dd7") <= 20).sum().alias("curdd20"),
        (pl.col("gross_exposure") <= 8).sum().alias("lev8"),
        (pl.col("duration_h") <= 12).sum().alias("duration12"),
        (pl.col("trades7") >= 10).sum().alias("trades10"),
    ]).to_dicts())
    max_age_h = 72
    eligible = (
        df.filter(
            (pl.col("registered"))
            & (~pl.col("excluded"))
            & pl.col("aliased")
            & pl.col("has_metrics")
            & (pl.col("equity") >= 1000)
            & (pl.col("trades7") >= 5)
            & (pl.col("pnl7") > 0)
            & (pl.col("duration_h") > 0)
            & (pl.col("duration_h") <= 24)
            & (pl.col("last_dt") >= CUTOFF - __import__("datetime").timedelta(hours=max_age_h))
            & (pl.col("metric_dt") >= CUTOFF - __import__("datetime").timedelta(hours=max_age_h))
            & (pl.col("dd7") <= 25)
            & (pl.col("current_dd7") <= 20)
            & (pl.col("gross_exposure") <= 8)
        )
        .with_columns(
            pl.col("trades7").log1p().alias("trade_activity"),
            (pl.col("pnl7") / pl.col("equity") * 100).alias("realized_on_current_equity_pct"),
            pl.col("open_unreal").fill_null(0).alias("open_unreal0"),
        )
        .with_columns(
            (pl.col("trade_activity") * 1.6
             + pl.col("realized_on_current_equity_pct").clip(-5, 30) * 0.45
             + pl.col("win_rate").fill_null(0).clip(0, 1) * 2.0
             - pl.col("current_dd7").fill_null(25) * 0.2
             - pl.col("dd7").fill_null(25) * 0.07
             - (pl.col("duration_h") / 24) * 2
             - (pl.col("gross_exposure").fill_null(0) - 3).clip(0, 10) * 0.4
             - ((-pl.col("open_unreal0")).clip(0, 10000000) / pl.col("equity")).clip(0, 1) * 5
            ).alias("screen_score")
        )
        .sort("screen_score", descending=True)
    )
    print("DATA_SHA", sha)
    print("CUT_OFF", CUTOFF.isoformat())
    print("COUNTS", json.dumps({
        "vendor_rows": df.height,
        "registry_intersection": df.filter(pl.col("registered")).height,
        "metrics_present": df.filter(pl.col("has_metrics")).height,
        "short_profitable_5trades": df.filter(
            pl.col("has_metrics") & (pl.col("pnl7") > 0) & (pl.col("trades7") >= 5)
            & (pl.col("duration_h") > 0) & (pl.col("duration_h") <= 24)
        ).height,
        "strict_eligible": eligible.height,
        "saved_latest_portfolios": len(latest),
        "saved_distinct_combinations": len(existing),
    }))
    result = []
    for item in eligible.iter_rows(named=True):
        opts = aliases[item["address"]]
        preference = {"sqlite_primary": 0, "ml4t_strict": 1, "research_v2": 2, "frozen_pm01": 3}
        opts.sort(key=lambda v: (preference.get(v[0], 9), v[1]))
        item["alias"] = opts[0][1]
        item.pop("address")
        result.append(item)
    print("TOP_WALLETS")
    for i, row in enumerate(result[:36], 1):
        print(json.dumps({
            "rank": i, "alias": row["alias"], "score": round(row["screen_score"], 2),
            "trades7": row["trades7"], "pnl7": round(row["pnl7"], 2),
            "equity": round(row["equity"], 2), "win_rate": row["win_rate"],
            "dd7": row["dd7"], "current_dd7": row["current_dd7"],
            "duration_h": round(row["duration_h"], 2),
            "open_unreal": round(row["open_unreal"] or 0, 2),
            "realized_equity_pct": round(row["realized_on_current_equity_pct"], 2),
            "last_fill": row["last_fill"],
        }, default=str))
    # One-time candidate combinations, not backtests. Cap reused managers to diversify.
    pool = result[:min(24, len(result))]
    scored = []
    for combo in itertools.combinations(pool, 3):
        mem = tuple(sorted(v["alias"] for v in combo))
        if mem in existing or len(set(mem)) < 3:
            continue
        scored.append((sum(v["screen_score"] for v in combo)
                       - 0.08 * (max(v["screen_score"] for v in combo) -
                                 min(v["screen_score"] for v in combo)), mem))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = []
    use = Counter()
    for score, mem in scored:
        if max(use[x] for x in mem) >= 5:
            continue
        chosen.append((round(score, 2), mem))
        use.update(mem)
        if len(chosen) >= 17:
            break
    print("PROPOSED_SEVENTEEN", json.dumps(chosen))
    print("LIMITATIONS vendor_summary_not_full_PIT_fills,mean_duration_not_median,leader_realized_not_follower_net,drawdown_provider_semantics_unverified,seven_day_selection_is_in_sample,no_follower_backtests,not_registered")


if __name__ == "__main__":
    main()
