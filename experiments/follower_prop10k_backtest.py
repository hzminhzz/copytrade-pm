"""$10,000 prop-challenge follower backtest with portfolio k sizing.

Same evidence and engine as experiments/follower_5m_backtest.py (5-minute
checkpoint policy A, portfolio-net-first, 4.5 bps + 2 bps costs, main-DEX
perps). The difference is sizing: each member is scaled by the portfolio's own
k instead of 1.

k sources, checked against the registry, the signed selection proof and the
private eligibility file:

  gemini.phase4/E3   PUBLISHED. data/private/gemini_phase3_phase4_eligibility_20261104.json
                     k_factors_reported_100k, scaled 0.1 for a $10,000 account
                     per docs/V4-SIXTEEN-PAPER-20261109.md:
                     ACT04 0.00428, W083/S053-HYPE 0.04708, CM-002 0.00384.
                     Published 2026-11-04, after the backtest window starts, so
                     the path is descriptive and in-sample.
  regime.macro/TriadA  BLOCKED: NO K. The live supervisor config is $10,000 with
                     nominal_risk $600 / pod_risk $200 and contract
                     NON_EXECUTABLE_SIGNED_RESEARCH; the signed selection proof
                     carries members only.
  Combo2             BLOCKED: NO K. The live supervisor config is $5,000 with
                     nominal_risk $300 / pod_risk $100 and contract
                     COMBO2_VIRTUAL_5000_USD_ACCOUNT_NOT_BROKER, an
                     equity-scaled policy, not fixed k.

k itself is carried by a signed copy mandate (copy_mandate_heads); the active
supervisor's mandate table is empty and its portfolios report BLOCKED_EVIDENCE.
That status does not distinguish a missing mandate from a missing run, so the
claim here is only that admission is blocked and no signed k is available.

No k is derived, fitted or inferred here. A k solved from this window's own
worst loss would be hindsight and is not a sizing policy.

What this does and does not model: it prices the leader books at the given k on
a $10,000 account and reports the realised daily and trailing drawdown against
the challenge floors. It does NOT implement pod stops, floor-triggered HALT,
margin, headroom, funding or PM-03/04 finance, so a breach reported here is a
breach of the modelled mark-to-market path, not a verified challenge failure.

Challenge rulebooks
  standard     daily 5% ($500), trailing 10% ($1,000).
               docs/RISK-BUDGETED-K-SIZING-20261106.md.
  propr-1step  daily 3% ($300), total 6% ($600). docs/COMBO2-PAPER.md.

A $200 stop is a trigger, not a guaranteed maximum loss.
"""

from __future__ import annotations

import sys

import polars as pl

sys.path.insert(0, "experiments")
import follower_5m_backtest as base  # noqa: E402

ACCOUNT = 10_000.0
RULEBOOKS = {
    "standard": {"daily": 0.05, "trailing": 0.10},
    "propr-1step": {"daily": 0.03, "trailing": 0.06},
}
POLICY_K: dict[str, dict[str, float] | None] = {
    "regime.macro/TriadA": None,
    "gemini.phase4/E3": {
        "ACT04": 0.00428,
        "CM-002": 0.00384,
        "S053-HYPE": 0.04708,
    },
    "Combo2": None,
}


def run(
    members: dict[str, str],
    ks: dict[str, float],
    cache: dict,
    anchor: dict,
    anchor_ts,
    fills: dict,
    first_fill: dict,
) -> pl.DataFrame:
    """Portfolio minute series at the given per-member k."""
    frames = []
    coins = sorted(
        {c for a in members.values() for c in fills[a]["coin"].unique().to_list()}
        | {c for a in members.values() for c in anchor.get(a, {})}
    )
    for coin in coins:
        if coin not in cache:
            cache[coin] = base.load_bars(coin, first_fill.get(coin))
        bars, _cov, _gap = cache[coin]
        if bars is None:
            continue
        ev, start = [], 0.0
        for name, a in members.items():
            k = ks[name]
            f = fills[a].filter(pl.col("coin") == coin)
            pre = f.filter((pl.col("ts") >= base.START) & (pl.col("ts") <= anchor_ts))
            start += k * (
                anchor.get(a, {}).get(coin, 0.0) - float((pre["sign"] * pre["size"]).sum())
            )
            ev += [(r["ts"], k * r["sign"] * r["size"]) for r in f.iter_rows(named=True)]
        st = pl.DataFrame([(base.START, start)] + sorted(ev), schema=["ts", "pos"], orient="row")
        st = st.with_columns(pl.col("ts").cast(base.MS))
        st = st.with_columns(pl.col("pos").cum_sum().alias("pos")).select("ts", "pos")
        frames.append(base.minute_net(bars, base.target_a(bars, st, start), start))
    return (
        pl.concat(frames)
        .group_by("timestamp")
        .agg(
            pl.col("net").sum(),
            pl.col("cost").sum(),
            (pl.col("delta").abs() * pl.col("open")).sum().alias("traded"),
        )
        .sort("timestamp")
    )


def challenge(agg: pl.DataFrame) -> dict:
    eq = ACCOUNT + agg["net"].cum_sum()
    trailing = float((eq - eq.cum_max()).min())
    daily = (
        agg.with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("day")
        .agg(pl.col("net").sum())["net"]
    )
    worst_day = float(daily.min())
    return {
        "net": round(float(agg["net"].sum()), 2),
        "final_equity": round(float(eq[-1]), 2),
        "cost": round(float(agg["cost"].sum()), 2),
        "traded_notional": round(float(agg["traded"].sum()), 2),
        "worst_day": round(worst_day, 2),
        "best_day": round(float(daily.max()), 2),
        "max_trailing_dd": round(trailing, 2),
        # Both losses scale with k, so their ratio does not. The floors are fixed
        # dollars, so a small enough k always satisfies both; what the ratio
        # fixes is which floor binds first. At the largest k the trailing floor
        # allows, the worst day uses only rulebook_ratio / dd_ratio of the daily
        # allowance.
        "dd_ratio": round(trailing / worst_day, 3) if worst_day else 0.0,
        "daily_allowance_used": round(
            min(r["trailing"] / r["daily"] for r in RULEBOOKS.values()) / (trailing / worst_day),
            3,
        )
        if worst_day
        else 0.0,
        "daily_breach": {n: worst_day <= -ACCOUNT * r["daily"] for n, r in RULEBOOKS.items()},
        "trailing_breach": {n: trailing <= -ACCOUNT * r["trailing"] for n, r in RULEBOOKS.items()},
    }


def main() -> None:
    base.self_check()
    fills = base.load_fills()
    anchor, anchor_ts = base.load_anchor()
    first_fill: dict = {}
    for f in fills.values():
        for coin, ts in f.group_by("coin").agg(pl.col("ts").min()).rows():
            first_fill[coin] = min(first_fill.get(coin, ts), ts)
    cache: dict = {}

    rows = []
    for pid, members in base.PORTFOLIOS.items():
        unit = challenge(
            run(members, {m: 1.0 for m in members}, cache, anchor, anchor_ts, fills, first_fill)
        )
        ks = POLICY_K[pid]
        row = {
            "portfolio": pid,
            "k_status": "PUBLISHED" if ks else "BLOCKED_NO_K",
            "unit_worst_day": unit["worst_day"],
            "unit_max_trailing_dd": unit["max_trailing_dd"],
            "unit_dd_ratio": unit["dd_ratio"],
            "unit_daily_allowance_used": unit["daily_allowance_used"],
        }
        if ks:
            agg = run(members, ks, cache, anchor, anchor_ts, fills, first_fill)
            row.update(challenge(agg))
            agg.write_parquet(
                f"data/private/backtest_20261112/{pid.replace('/', '_')}_prop10k_minute.parquet"
            )
        rows.append(row)

    pl.Config.set_tbl_cols(30)
    pl.Config.set_tbl_width_chars(260)
    df = pl.DataFrame(rows)
    print()
    print(
        df.select(
            "portfolio",
            "k_status",
            "net",
            "final_equity",
            "worst_day",
            "max_trailing_dd",
            "dd_ratio",
            "cost",
            "traded_notional",
        )
    )
    for r in rows:
        if r["k_status"] == "PUBLISHED":
            print(
                f"{r['portfolio']}: daily breach {r['daily_breach']}  "
                f"trailing breach {r['trailing_breach']}  "
                f"dd/worst-day ratio {r['dd_ratio']:.2f} (rulebook 2.00) -> at the "
                f"largest k the trailing floor allows, the worst day uses only "
                f"{r['daily_allowance_used']:.0%} of the daily allowance"
            )
        else:
            print(
                f"{r['portfolio']}: BLOCKED_NO_K. At k=1 the unit book has a worst day of "
                f"{r['unit_worst_day']:,.0f} and a max trailing drawdown of "
                f"{r['unit_max_trailing_dd']:,.0f} on a $10,000 account; no challenge "
                f"sizing can be stated without a published k. Unit dd/worst-day ratio "
                f"{r['unit_dd_ratio']:.2f} (rulebook 2.00) -> at the largest k the "
                f"trailing floor allows, the worst day uses only "
                f"{r['unit_daily_allowance_used']:.0%} of the daily allowance."
            )
    df.write_parquet("data/private/backtest_20261112/prop10k_summary.parquet")


if __name__ == "__main__":
    main()
