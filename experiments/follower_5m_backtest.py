"""Follower-wallet backtest for three research portfolios, 5-minute sizing policy.

Portfolios (current SQLite registry identities, k = 1 native quantity per member):
  regime.macro/TriadA v2   ACT04 ACT08 ACT09
  gemini.phase4/E3   v1    ACT04 CM-002 S053-HYPE
  Combo2             v2    CA-008 W015 W028

Policy A (the current practice): sample the PORTFOLIO NET per symbol at every
5-minute checkpoint and trade the follower to it at that checkpoint's minute open.
Members are netted before any order is sized, so offsetting members do not trade.

Evidence
  fills   vike hl_wallet_activity view=fills, 2026-09-01..2026-11-11, paged to
          cursor exhaustion, cached in data/private/backtest_20261112/fills/
  anchor  vike hl_archive positions 2026-09-29, state_ts 2026-09-29T23:52:34Z;
          the position at START is the anchor minus every fill in [START, anchor]
  prices  ml4t-data 1m Hyperliquid OHLCV (local store)

Scope: main-DEX perp assets only (fills with dex_name == 'HL'). Spot-style
symbols (@NNN, #NNN, PURR/USDC) and perps with no/insufficient local 1m bars are
excluded and reported per portfolio. Costs: 4.5 bps taker fee + 2 bps slippage
on traded notional. The final open position is marked at the last close with no
exit charge.

This is a modeled replication, not follower PnL evidence: k = 1 is the
sizing-agnostic mirror, and no signed k exists for these three portfolios.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

FILLS_DIR = "data/private/backtest_20261112/fills"
VIKE_BARS = "data/private/backtest_20261112/bars_vike"
ANCHOR_PARQUET = "data/private/registry_archive_slice/registry_archive_positions_20260929.parquet"
STORE = "/home/quant/dev/quant/ml4t-data/.data/store"
DEFAULT_REGISTRY_DB = Path.home() / ".local/share/copytrade/registry/wallet_registry.sqlite"
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 11, 11, tzinfo=UTC)  # exclusive: last bar is 2026-11-10T23:59
FEE_BPS = 4.5
SLIP_BPS = 2.0
MAX_BAR_GAP_MIN = 180  # 3 h of stale mark is the limit; a 1m bar exists only if a trade happened
MIN_BAR_COVERAGE = 0.30
MS = pl.Datetime("ms", "UTC")

PORTFOLIO_SPECS: list[tuple[str, int, tuple[str, ...]]] = [
    ("regime.macro/TriadA", 2, ("ACT04", "ACT08", "ACT09")),
    ("gemini.phase4/E3", 1, ("ACT04", "CM-002", "S053-HYPE")),
    ("Combo2", 2, ("CA-008", "W015", "W028")),
]


def _resolve_portfolio_wallets(
    registry_db: Path = DEFAULT_REGISTRY_DB,
) -> dict[str, dict[str, str]]:
    """Resolve member wallet addresses from the private SQLite registry at runtime."""
    db_path = Path(os.environ.get("COPYTRADE_WALLET_REGISTRY_DB", str(registry_db)))
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite wallet registry not found at {db_path}; set COPYTRADE_WALLET_REGISTRY_DB."
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        resolved: dict[str, dict[str, str]] = {}
        for portfolio_id, version, expected_aliases in PORTFOLIO_SPECS:
            rows = conn.execute(
                """
                SELECT pm.member_alias, lower(w.address)
                FROM portfolio_memberships pm
                JOIN wallets w ON pm.wallet_id = w.wallet_id
                WHERE pm.portfolio_id = ? AND pm.version = ?
                """,
                (portfolio_id, version),
            ).fetchall()
            members = {str(alias): str(addr) for alias, addr in rows}
            missing = [a for a in expected_aliases if a not in members]
            if missing:
                raise RuntimeError(
                    f"Missing members {missing} for {portfolio_id} v{version} in {db_path}"
                )
            resolved[portfolio_id] = {a: members[a] for a in expected_aliases}
        return resolved
    finally:
        conn.close()


PORTFOLIOS = _resolve_portfolio_wallets()


def load_fills() -> dict[str, pl.DataFrame]:
    out = {}
    for path in glob.glob(f"{FILLS_DIR}/0x*.json"):
        addr = os.path.basename(path)[:-5]
        rows = []
        for f in json.load(open(path)):
            if f["dex_name"] != "HL":
                continue
            rows.append(
                (
                    datetime.fromisoformat(f["ts"]),
                    f["symbol"],
                    1 if f["side"] == "buy" else -1,
                    float(f["size_token"]),
                    float(f["price"]),
                    float(f["closed_pnl"]),
                )
            )
        out[addr] = pl.DataFrame(
            rows, schema=["ts", "coin", "sign", "size", "px", "closed_pnl"], orient="row"
        ).with_columns(pl.col("ts").cast(MS))
    return out


def load_anchor() -> tuple[dict[str, dict[str, float]], datetime]:
    df = pl.read_parquet(ANCHOR_PARQUET)
    ts = df["state_ts"].max()
    book: dict[str, dict[str, float]] = {}
    for r in df.filter(pl.col("state_ts") == ts).iter_rows(named=True):
        if r["dex_name"] != "HL":
            continue
        book.setdefault(r["wallet"], {})[r["asset"]] = r["direction"] * r["size_token"]
    return book, ts


def load_bars(coin: str, first_fill: datetime | None) -> tuple[pl.DataFrame | None, float, int]:
    """ml4t-data 1m store where it has bars, vike 1m fills rollup for the rest.

    The store stops ingesting most non-major symbols after 2026-10-14, so the
    vike rollup (same venue, same fills) closes that hole. Where both exist the
    store wins; on the 2026-10-14 overlap the two agree to within 0.4 % on the
    worst symbol and exactly on the majors.
    """
    paths = []
    for m in (9, 10, 11):
        paths += glob.glob(
            f"{STORE}/crypto_futures_ohlcv_1m_HYPERLIQUID_{coin}_PERP/year=2026/month={m:02d}/day=*/data.parquet"
        )
    frames = []
    for path in paths:
        try:
            frames.append(
                pl.read_parquet(path)
                .select("timestamp", "open", "close")
                .with_columns(pl.col("timestamp").cast(MS))
            )
        except Exception:
            continue
    vike = f"{VIKE_BARS}/{coin}.parquet"
    if os.path.exists(vike):
        frames.append(
            pl.read_parquet(vike).select(
                pl.from_epoch("ts_ms", time_unit="ms")
                .dt.replace_time_zone("UTC")
                .cast(MS)
                .alias("timestamp"),
                "open",
                "close",
            )
        )
    if not frames:
        return None, 0.0, 0
    raw = (
        pl.concat(frames)
        .unique("timestamp", keep="first")
        .filter((pl.col("timestamp") >= START) & (pl.col("timestamp") < END))
        .sort("timestamp")
    )
    lo = raw["timestamp"].min()
    if first_fill is not None and first_fill < lo:
        return None, 0.0, 0  # a fill precedes the first bar: a real hole, not a listing
    grid = pl.DataFrame(
        {"timestamp": pl.datetime_range(lo, END - timedelta(minutes=1), "1m", eager=True)}
    ).with_columns(pl.col("timestamp").cast(MS))
    coverage = raw.height / grid.height
    max_gap = int(raw["timestamp"].diff().dt.total_minutes().drop_nulls().max() or 0)
    if coverage < MIN_BAR_COVERAGE or max_gap > MAX_BAR_GAP_MIN:
        return None, coverage, max_gap
    bars = grid.join(raw, on="timestamp", how="left")
    bars = bars.with_columns(pl.col("close").forward_fill().backward_fill())
    bars = bars.with_columns(pl.col("open").fill_null(pl.col("close").shift(1)).backward_fill())
    return bars, coverage, max_gap


def leader_net(bars: pl.DataFrame, st: pl.DataFrame, start_pos: float) -> pl.DataFrame:
    """The leader's net position as known at the start of each minute."""
    return (
        bars.select("timestamp")
        .join_asof(st, left_on="timestamp", right_on="ts", strategy="backward")
        .with_columns(pl.col("pos").fill_null(start_pos))
    )


def target_a(bars: pl.DataFrame, st: pl.DataFrame, start_pos: float) -> pl.Series:
    """Leader net as of each 5-minute checkpoint, held until the next one."""
    ck = (
        leader_net(bars, st, start_pos)
        .filter(pl.col("timestamp").dt.minute() % 5 == 0)
        .select("timestamp", "pos")
    )
    return (
        bars.select("timestamp")
        .join_asof(ck, on="timestamp", strategy="backward")
        .with_columns(pl.col("pos").fill_null(start_pos))["pos"]
    )


def minute_net(bars: pl.DataFrame, pos: pl.Series, start_pos: float) -> pl.DataFrame:
    first = pl.lit(float(start_pos))
    return (
        bars.with_columns(pos.alias("pos"))
        .with_columns(
            prev_pos=pl.col("pos").shift(1).fill_null(first),
            prev_close=pl.col("close").shift(1).fill_null(pl.col("open")),
            delta=pl.col("pos") - pl.col("pos").shift(1).fill_null(first),
        )
        .with_columns(
            gross=pl.col("prev_pos") * (pl.col("open") - pl.col("prev_close"))
            + pl.col("pos") * (pl.col("close") - pl.col("open")),
            cost=pl.col("delta").abs() * pl.col("open") * (FEE_BPS + SLIP_BPS) / 10000,
        )
        .with_columns(net=pl.col("gross") - pl.col("cost"))
    )


def self_check() -> None:
    """Offsetting members: A +2 then B -1 at the same instant -> net 1, one order."""
    start = datetime(2026, 3, 2, tzinfo=UTC)
    px = [100.0 + i for i in range(40)]
    bars = pl.DataFrame(
        {
            "timestamp": pl.datetime_range(start, start + timedelta(minutes=39), "1m", eager=True),
            "open": px,
            "close": px,
        }
    ).with_columns(pl.col("timestamp").cast(MS))
    st = pl.DataFrame(
        {"ts": [start + timedelta(minutes=2, seconds=30)], "pos": [1.0]}
    ).with_columns(pl.col("ts").cast(MS))
    c = minute_net(bars, target_a(bars, st, 0.0), 0.0)
    trades = c.filter(pl.col("delta").abs() > 1e-12).select("timestamp", "delta").rows()
    assert [r[0].minute for r in trades] == [5] and trades[0][1] == 1.0, trades
    # a state change inside a checkpoint interval is not traded until the next mark
    st2 = pl.DataFrame({"ts": [start + timedelta(minutes=6)], "pos": [3.0]}).with_columns(
        pl.col("ts").cast(MS)
    )
    c2 = minute_net(bars, target_a(bars, st2, 0.0), 0.0)
    trades2 = c2.filter(pl.col("delta").abs() > 1e-12).select("timestamp", "delta").rows()
    assert [r[0].minute for r in trades2] == [10], trades2
    print("self-check OK")


def main() -> None:
    self_check()
    fills = load_fills()
    anchor, anchor_ts = load_anchor()
    print(
        f"anchor state_ts={anchor_ts.isoformat()} window={START.date()}..{(END - timedelta(days=1)).date()}"
    )

    first_fill: dict[str, datetime] = {}
    for f in fills.values():
        for coin, ts in f.group_by("coin").agg(pl.col("ts").min()).rows():
            first_fill[coin] = min(first_fill.get(coin, ts), ts)

    bars_cache: dict[str, tuple[pl.DataFrame | None, float, int]] = {}
    rows, per_coin_rows = [], []
    for pid, members in PORTFOLIOS.items():
        coins = sorted(
            {c for a in members.values() for c in fills[a]["coin"].unique().to_list()}
            | {c for a in members.values() for c in anchor.get(a, {})}
        )
        frames, excluded, coin_stats = [], [], []
        for coin in coins:
            if coin not in bars_cache:
                bars_cache[coin] = load_bars(coin, first_fill.get(coin))
            bars, coverage, max_gap = bars_cache[coin]
            if bars is None:
                excluded.append((coin, round(coverage, 3)))
                continue
            base = 0.0
            for a in members.values():
                p = anchor.get(a, {}).get(coin, 0.0)
                f = fills[a].filter(pl.col("coin") == coin)
                pre = f.filter((pl.col("ts") >= START) & (pl.col("ts") <= anchor_ts))
                base += p - float((pre["sign"] * pre["size"]).sum())
            ev = []
            for a in members.values():
                f = fills[a].filter(pl.col("coin") == coin)
                ev += [(r["ts"], r["sign"] * r["size"]) for r in f.iter_rows(named=True)]
            ev.sort()
            out, pos, i = [(START, base)], base, 0
            while i < len(ev):
                t = ev[i][0]
                while i < len(ev) and ev[i][0] == t:
                    pos += ev[i][1]
                    i += 1
                out.append((t, pos))
            st = pl.DataFrame(out, schema=["ts", "pos"], orient="row").with_columns(
                pl.col("ts").cast(MS)
            )
            df = minute_net(bars, target_a(bars, st, base), base)
            df_l = minute_net(bars, leader_net(bars, st, base)["pos"], base)
            frames.append(
                df.select("timestamp", "gross", "cost", "net", "delta", "open", "pos").with_columns(
                    pl.lit("A").alias("policy")
                )
            )
            frames.append(
                df_l.select(
                    "timestamp", "gross", "cost", "net", "delta", "open", "pos"
                ).with_columns(pl.lit("L").alias("policy"))
            )
            coin_stats.append(
                {
                    "coin": coin,
                    "coverage": round(coverage, 4),
                    "max_gap_min": max_gap,
                    "net": round(df["net"].sum(), 2),
                    "net_l": round(df_l["net"].sum(), 2),
                    "trades": int((df["delta"].abs() > 1e-12).sum()),
                    "traded_notional": round(float((df["delta"].abs() * df["open"]).sum()), 2),
                    "start_pos": round(base, 6),
                    "end_pos": round(float(df["pos"][-1]), 6),
                }
            )
        if not frames:
            print(f"{pid}: no tradable symbols")
            continue
        agg = (
            pl.concat(frames)
            .filter(pl.col("policy") == "A")
            .group_by("timestamp")
            .agg(
                pl.col("gross").sum(),
                pl.col("cost").sum(),
                pl.col("net").sum(),
                (pl.col("delta").abs() > 1e-12).sum().alias("trades"),
                (pl.col("delta").abs() * pl.col("open")).sum().alias("traded_notional"),
            )
            .sort("timestamp")
        )
        eq = agg["net"].cum_sum()
        peak = eq.cum_max()
        dd = float((eq - peak).min())
        agg_l = (
            pl.concat(frames)
            .filter(pl.col("policy") == "L")
            .group_by("timestamp")
            .agg(pl.col("net").sum())
            .sort("timestamp")
        )
        eq_l = agg_l["net"].cum_sum()
        dd_l = float((eq_l - eq_l.cum_max()).min())
        rows.append(
            {
                "portfolio": pid,
                "members": len(members),
                "symbols": len(coin_stats),
                "excluded": len(excluded),
                "leader_realized": round(
                    float(sum(float(fills[a]["closed_pnl"].sum()) for a in members.values())),
                    2,
                ),
                "net_l": round(float(agg_l["net"].sum()), 2),
                "max_drawdown_l": round(dd_l, 2),
                "net": round(float(agg["net"].sum()), 2),
                "gross": round(float(agg["gross"].sum()), 2),
                "cost": round(float(agg["cost"].sum()), 2),
                "trades": int(agg["trades"].sum()),
                "traded_notional": round(float(agg["traded_notional"].sum()), 2),
                "max_drawdown": round(dd, 2),
                "excluded_symbols": ",".join(f"{c}({v})" for c, v in excluded),
            }
        )
        for s in sorted(coin_stats, key=lambda r: r["net"]):
            per_coin_rows.append({"portfolio": pid, **s})
        agg.write_parquet(
            f"data/private/backtest_20261112/{pid.replace('/', '_')}_5m_minute.parquet"
        )

    summary = pl.DataFrame(rows)
    print()
    print(
        summary.select(
            "portfolio",
            "members",
            "symbols",
            "excluded",
            "leader_realized",
            "net",
            "net_l",
            "gross",
            "cost",
            "trades",
            "traded_notional",
            "max_drawdown",
            "max_drawdown_l",
        )
    )
    for r in rows:
        print(f"{r['portfolio']}: excluded {r['excluded_symbols'] or 'none'}")
    print()
    print(pl.DataFrame(per_coin_rows).sort(["portfolio", "net"]))
    summary.write_parquet("data/private/backtest_20261112/portfolios_5m_summary.parquet")
    pl.DataFrame(per_coin_rows).write_parquet(
        "data/private/backtest_20261112/portfolios_5m_by_coin.parquet"
    )


if __name__ == "__main__":
    main()
