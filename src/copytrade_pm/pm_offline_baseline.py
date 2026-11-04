"""Read-only baseline for frozen PM-01 source reconstruction and oracle replay.

This harness benchmarks the *existing* historical implementation. It never
asserts first-known receipt, realistic liquidity, or PM-03 certification.
Generated source pages live only in an isolated temporary directory.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import resource
import shutil
import tempfile
from time import perf_counter

from .pm_fill_replay import _source_fills, replay_wallet
from .pm_shadow import MinuteBar
from .pm_sources import CohortEntry

ORIGIN = datetime(2026, 10, 20, tzinfo=UTC)
ADDRESS = "0x" + "1" * 40
SCHEMA = "pm_offline_baseline_v1"


class FixedMarket:
    """Explicitly synthetic unlimited constant-price minute oracle."""

    def get(self, instrument: str, action_at: datetime) -> MinuteBar:
        minute = action_at.replace(second=0, microsecond=0)
        if minute != action_at:
            minute += timedelta(minutes=1)
        return MinuteBar(minute, Decimal("100"), Decimal("1000000"), "a" * 64)


def _payload(count: int) -> bytes:
    if not 2 <= count <= 1000:
        raise ValueError("FIXTURE_COUNT_OUT_OF_BOUNDS")
    rows = []
    for index in range(count):
        rows.append(
            {
                "user": ADDRESS,
                "coin": "BTC",
                "tid": index + 1,
                "time": int((ORIGIN + timedelta(minutes=index)).timestamp() * 1000),
                "side": "B" if index % 2 == 0 else "A",
                "sz": "1",
                "px": "100",
                "start_position": str(index % 2),
            }
        )
    return json.dumps(
        {"page": 1, "page_size": 2000, "has_more": False, "fills": rows[::-1]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _fixture(folder: Path, payload: bytes) -> None:
    location = folder / "slow_pod_data_v1/hyperx_fills_cache_v1/pages/W001/BTC"
    location.mkdir(parents=True, exist_ok=True)
    (location / "page-00001.json.gz").write_bytes(gzip.compress(payload, mtime=0))
    (location / "page-00001.meta.json").write_text(
        json.dumps(
            {"alias": "W001", "coin": "BTC", "page": 1, "sha256": sha256(payload).hexdigest()},
            sort_keys=True,
        )
    )


def _proc_io() -> dict[str, int] | None:
    """Linux counters; read_bytes is actual process physical I/O, not logical Parquet I/O."""
    try:
        values = {}
        for line in Path("/proc/self/io").read_text().splitlines():
            key, value = line.split(": ", 1)
            if key in {"rchar", "read_bytes", "syscr"}:
                values[key] = int(value)
        return values if len(values) == 3 else None
    except OSError, ValueError:
        return None


def benchmark(*, count: int = 120, iterations: int = 2) -> dict:
    if not 2 <= iterations <= 10:
        raise ValueError("ITERATIONS_OUT_OF_BOUNDS")
    payload = _payload(count)
    source_sha = sha256(payload).hexdigest()
    entry = CohortEntry(
        "W001",
        "original",
        ADDRESS,
        sha256(ADDRESS.encode()).hexdigest(),
        "VENDOR_ROSTER_CACHED_HISTORICAL_ONLY",
        1,
        10,
    )
    samples = []
    with tempfile.TemporaryDirectory(prefix="copytrade-baseline-") as temp:
        root = Path(temp)
        _fixture(root, payload)
        source_file = (
            root / "slow_pod_data_v1/hyperx_fills_cache_v1/pages/W001/BTC/page-00001.json.gz"
        )
        compressed_bytes = source_file.stat().st_size
        disk_free_bytes = shutil.disk_usage(root).free
        for run in range(iterations):
            cpu_before = resource.getrusage(resource.RUSAGE_SELF)
            io_before = _proc_io()
            start = perf_counter()
            fills, errors = _source_fills(root, "W001", ADDRESS, ["BTC"])
            parse_seconds = perf_counter() - start
            if errors or len(fills) != count:
                raise RuntimeError("BASELINE_INPUT_INTEGRITY_FAILURE")
            result = replay_wallet(
                root,
                entry,
                FixedMarket(),
                5,
                prepared=(fills, errors, ["BTC"]),
            )
            elapsed = perf_counter() - start
            io_after = _proc_io()
            cpu_after = resource.getrusage(resource.RUSAGE_SELF)
            logical_io = (
                {key: io_after[key] - io_before[key] for key in io_before}
                if io_before is not None and io_after is not None
                else None
            )
            # Runtime measurements are excluded from the logical digest.
            logical = {
                "status": result["status"],
                "source_fills": result["source_fills"],
                "latency_minutes": result["latency_minutes"],
                "pnl": str(result.get("pnl")),
                "blocked_reasons": result.get("blocked_reasons"),
                "oracle_hindsight": result["oracle_hindsight"],
            }
            samples.append(
                {
                    "run": run,
                    "cache_label": "cold_fixture" if run == 0 else "warm_os_cache",
                    "wall_seconds": round(elapsed, 6),
                    "parse_seconds": round(parse_seconds, 6),
                    "cpu_user_seconds": round(cpu_after.ru_utime - cpu_before.ru_utime, 6),
                    "cpu_system_seconds": round(cpu_after.ru_stime - cpu_before.ru_stime, 6),
                    "process_io_counters_bytes": logical_io,
                    "maxrss_kib_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "result_sha256": sha256(
                        json.dumps(logical, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "status": result["status"],
                }
            )
    if len({s["result_sha256"] for s in samples}) != 1:
        raise RuntimeError("NONDETERMINISTIC_BASELINE")
    return {
        "schema": SCHEMA,
        "clock_basis": "HISTORICAL_ORACLE",
        "source_payload_sha256": source_sha,
        "source_fill_count": count,
        "compressed_fixture_bytes": compressed_bytes,
        "scratch_free_bytes_before": disk_free_bytes,
        "persistent_cache_hit_count": 0,
        "synthetic_market": True,
        "python": platform.python_version(),
        "polars": _polars_version(),
        "samples": samples,
        "limitations": [
            "Synthetic constant-price oracle, not native market Parquet or real venue capacity",
            "Warm label reflects OS cache only; replay constructs new in-memory state",
            "Peak RSS is process high-water, not per-iteration incremental memory",
            "Process physical read_bytes is not a reliable cold-disk estimate without cache purge",
            "No repeated full-market scanning or event-tape cache in this original PM01 fixture",
            "Not PM-03 accounting, not prospective first-known, not a performance speedup claim",
        ],
    }


def _polars_version() -> str | None:
    try:
        import polars
    except ImportError:
        return None
    return polars.__version__


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fills", type=int, default=120)
    parser.add_argument("--iterations", type=int, default=2)
    args = parser.parse_args()
    print(
        json.dumps(
            benchmark(count=args.fills, iterations=args.iterations), sort_keys=True, indent=2
        )
    )


if __name__ == "__main__":
    main()
