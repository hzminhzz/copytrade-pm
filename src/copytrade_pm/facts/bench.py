"""Cross-sectional scan benchmark for the fact store.

Generates a synthetic store (no private data, no network) and measures the
deterministic ``250 wallets x 200 days`` scan shape the design calls for:

    FactStore.scan("fills", wallets=<250>, start_day=..., end_day=..., as_of_ms=...)

Reported numbers are aggregate only: wallet count, day count, rows, files,
latency percentiles and throughput. No address is printed, ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import statistics
import time
from typing import Any

try:  # pragma: no cover - the core CI leg runs without the `market` extra
    import polars as pl  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    pl = None  # type: ignore[assignment]

from .repair import RepairStats
from .schemas import column_names, schema_for
from . import manifest as mf
from .store import FactStore, PreparedDay

COINS = ("BTC", "ETH", "SOL", "HYPE", "ARB", "OP", "AVAX", "LINK")
START_DAY = "2026-05-01"


@dataclass(frozen=True, slots=True)
class SyntheticPlan:
    wallets: int
    days: int
    rows_per_wallet_day: int
    start_day: str = START_DAY

    @property
    def rows(self) -> int:
        return self.wallets * self.days * self.rows_per_wallet_day

    def wallet(self, index: int) -> str:
        return f"0x{index:040x}"

    def day(self, offset: int) -> str:
        start = datetime.fromisoformat(self.start_day).replace(tzinfo=UTC)
        return (start + timedelta(days=offset)).date().isoformat()


def build_synthetic_store(root: Path | str, plan: SyntheticPlan) -> FactStore:
    """Write a deterministic synthetic store; returns an open :class:`FactStore`."""
    if pl is None:  # pragma: no cover
        raise RuntimeError("POLARS_REQUIRED: install the `market` extra")
    store = FactStore(root, create=True)
    store.connect()
    base = datetime.fromisoformat(plan.start_day).replace(tzinfo=UTC)
    for offset in range(plan.days):
        day = plan.day(offset)
        day_ms = int((base + timedelta(days=offset)).timestamp() * 1000)
        wallets: list[str] = []
        coins: list[str] = []
        stamps: list[int] = []
        for wallet_index in range(plan.wallets):
            address = plan.wallet(wallet_index)
            for row_index in range(plan.rows_per_wallet_day):
                wallets.append(address)
                coins.append(COINS[(wallet_index + row_index) % len(COINS)])
                stamps.append(day_ms + row_index * 1000 + (wallet_index % 500))
        frame = pl.DataFrame(
            {
                "wallet": wallets,
                "coin": coins,
                "dex": ["hyperliquid"] * len(wallets),
                "dex_raw": ["hyperliquid"] * len(wallets),
                "provider": [None] * len(wallets),
                "side": ["buy" if index % 2 == 0 else "sell" for index in range(len(wallets))],
                "size": [str((index % 17) + 1) for index in range(len(wallets))],
                "price": ["100.5"] * len(wallets),
                "fee": ["0.01"] * len(wallets),
                "fee_token": ["USDC"] * len(wallets),
                "size_usd": ["100.5"] * len(wallets),
                "start_position": [str(index % 5) for index in range(len(wallets))],
                "closed_pnl": ["0"] * len(wallets),
                "trade_id": [f"t{index}" for index in range(len(wallets))],
                "order_id": [None] * len(wallets),
                "direction": [None] * len(wallets),
                "is_liquidation": [False] * len(wallets),
                "is_maker": [None] * len(wallets),
                "crossed": [None] * len(wallets),
                "exchange_ts": [stamp for stamp in stamps],
                "event_ts_ms": stamps,
                "source_ts": [str(stamp) for stamp in stamps],
                "first_known_at_ms": [day_ms + 86_400_000] * len(wallets),
                "known_at_basis": ["partition_fetch_clock"] * len(wallets),
                "arrival_seq": [index % plan.rows_per_wallet_day for index in range(len(wallets))],
                "source_id": ["synthetic"] * len(wallets),
                "source_rank": [0] * len(wallets),
                "batch_sha16": [""] * len(wallets),
            }
        )
        canonical = frame.with_columns(
            [
                pl.col("exchange_ts").cast(pl.Datetime("ms", "UTC")),
                *[
                    pl.col(name).cast(pl.Decimal(38, 12), strict=False)
                    for name in (
                        "size",
                        "price",
                        "fee",
                        "size_usd",
                        "start_position",
                        "closed_pnl",
                    )
                ],
            ]
        ).select(column_names("fills"))
        prepared = PreparedDay(kind="fills", day=day, frame=canonical, repair_stats=RepairStats())
        write = store.write_day(prepared)
        mf.record_day(
            store.connect(),
            batch=mf.DayBatch(
                kind="fills",
                day=day,
                batch_sha16=write.batch_sha16,
                path=str(write.path),
                rows=write.rows,
                file_sha256=write.file_sha256,
                inputs_fingerprint=f"synthetic:{plan.start_day}:{offset}",
            ),
            source_ids=("synthetic",),
            bytes_count=write.bytes_count,
            inputs=[
                mf.InputRecord(
                    kind="fills",
                    day=day,
                    source_id="synthetic",
                    rel_path=f"day={day}/data.parquet",
                    input_sha256=write.file_sha256,
                    rows_read=write.rows,
                    rows_kept=write.rows,
                    rows_duplicate_within=0,
                    rows_duplicate_cross=0,
                    rows_conflicting_values=0,
                    rows_rejected=0,
                    rows_null_key=0,
                    first_known_at_ms=day_ms + 86_400_000,
                )
            ],
            first_known_min_ms=day_ms + 86_400_000,
            first_known_max_ms=day_ms + 86_400_000,
            closed_at=datetime.now(tz=UTC).isoformat(),
        )
    return store


def select_wallets(store: FactStore, limit: int, *, first_day: str, last_day: str) -> list[str]:
    """Choose a deterministic cohort from the entire benchmark window."""
    window = store.scan("fills", start_day=first_day, end_day=last_day)
    if not window.files:
        raise RuntimeError("BENCHMARK_EMPTY_WINDOW")
    return (
        window.frame.select("wallet")
        .unique()
        .sort("wallet")
        .head(limit)
        .collect()["wallet"]
        .to_list()
    )


def run_benchmark(
    store: FactStore,
    *,
    wallets: int,
    days: int,
    repeats: int = 3,
    day_end: str | None = None,
) -> dict[str, Any]:
    """Measure one cross-sectional scan; returns aggregate metrics only."""
    coverage = store.coverage("fills")
    if not coverage.days_present:
        raise RuntimeError("BENCHMARK_EMPTY_STORE")
    last_day = day_end or coverage.days_present[-1]
    first_day = (datetime.fromisoformat(last_day) - timedelta(days=days - 1)).date().isoformat()
    selected = select_wallets(store, wallets, first_day=first_day, last_day=last_day)
    as_of_ms = int(
        (datetime.fromisoformat(last_day) + timedelta(days=1)).replace(tzinfo=UTC).timestamp()
        * 1000
    )
    timings: list[float] = []
    rows = 0
    files = 0
    for _ in range(max(repeats, 1)):
        started = time.perf_counter()
        slice_ = store.scan(
            "fills",
            wallets=selected,
            start_day=first_day,
            end_day=last_day,
        )
        frame = slice_.collect()
        timings.append(time.perf_counter() - started)
        rows = frame.height
        files = slice_.files
    ordered = sorted(timings)

    # Point-in-time pass over the same cohort and window. Reported separately
    # because archive-only rows carry no clock and are invisible by design, so a
    # smaller (or zero) count here is correct, not a missing-data bug.
    pit_started = time.perf_counter()
    pit_rows = (
        store.scan(
            "fills",
            wallets=selected,
            start_day=first_day,
            end_day=last_day,
            as_of_ms=as_of_ms,
        )
        .collect()
        .height
    )
    pit_seconds = time.perf_counter() - pit_started

    def percentile(fraction: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
        return ordered[index]

    total_bytes = 0
    con = store.connect()
    for batch in mf.day_batches(con, "fills", start_day=first_day, end_day=last_day):
        path = Path(batch.path)
        if path.is_file():
            total_bytes += path.stat().st_size
    return {
        "wallets": len(selected),
        "days": days,
        "window": [first_day, last_day],
        "rows_returned": rows,
        "pit_rows_returned": pit_rows,
        "pit_seconds": round(pit_seconds, 4),
        "files_scanned": files,
        "parquet_bytes": total_bytes,
        "repeats": len(timings),
        "seconds_p50": round(statistics.median(ordered), 4),
        "seconds_p95": round(percentile(0.95), 4),
        "seconds_min": round(ordered[0], 4),
        "seconds_max": round(ordered[-1], 4),
        "rows_per_second": round(rows / ordered[0], 1) if ordered[0] > 0 else 0.0,
        "mb_per_second": round(total_bytes / 1e6 / ordered[0], 2) if ordered[0] > 0 else 0.0,
        "schema_columns": len(schema_for("fills")),
    }
