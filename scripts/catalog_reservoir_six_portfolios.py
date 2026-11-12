"""Read-only catalog for the six-portfolio, two-DEX Reservoir research backfill.

The catalog indexes SHA-verified private source Parquet without copying it into
the canonical wallet store. It DOES NOT establish prospective first-known,
whole-wallet completeness, follower economics, paper admission, or trade rights.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import polars as pl
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.pilot_reservoir_wallet_scoped import (  # noqa: E402
    OUTPUT as ORIGINAL_MAIN_PILOT,
    ALLOWED_DEXES,
    exclusive_bytes,
    jdump,
    scope_from_registry,
    validate_fills,
    verify_artifact,
)

PRIVATE_RESEARCH_ROOT = Path("/home/quant/.local/share/copytrade/research")
CATALOG_ROOT = PRIVATE_RESEARCH_ROOT / "reservoir-six-20260701-20261111"
MONITORED_CATALOG_ROOT = PRIVATE_RESEARCH_ROOT / "reservoir-monitored-plus-six-20260701-20261111"
START, END = date(2026, 7, 1), date(2026, 11, 11)


def historical_windows() -> tuple[tuple[str, date, date], ...]:
    """Bounded seven-day, non-overlapping windows before the existing catalog."""
    result = []
    day = date(2026, 7, 1)
    cutoff = date(2026, 10, 11)
    while day <= cutoff:
        end = min(day + timedelta(days=6), cutoff)
        result.append((f"{day:%Y%m%d}-{end:%Y%m%d}", day, end))
        day = end + timedelta(days=1)
    return tuple(result)


WEEKLY = historical_windows() + (
    ("20261012-14", date(2026, 10, 12), date(2026, 10, 14)),
    ("20261015-21", date(2026, 10, 15), date(2026, 10, 21)),
    ("20261022-28", date(2026, 10, 22), date(2026, 10, 28)),
    ("20261029-1104", date(2026, 10, 29), date(2026, 11, 4)),
    ("20261105-11", date(2026, 11, 5), date(2026, 11, 11)),
)


def days_between(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def monitored_windows() -> tuple[tuple[str, date, date], ...]:
    begin = START
    result = []
    while begin <= END:
        last = min(begin + timedelta(days=6), END)
        result.append((f"{begin:%Y%m%d}-{last:%Y%m%d}", begin, last))
        begin = last + timedelta(days=1)
    return tuple(result)


def window_sources(cohort: str = "sealed_six") -> dict[tuple[str, str], Path]:
    if cohort == "sealed_six":
        windows_to_index = WEEKLY
    elif cohort == "monitored_plus_six":
        windows_to_index = monitored_windows()
    else:
        raise ValueError("UNAPPROVED_COHORT")
    roots = {}
    for token, start, end in windows_to_index:
        for dex in sorted(ALLOWED_DEXES):
            root = (
                ORIGINAL_MAIN_PILOT
                if cohort == "sealed_six" and token == "20261105-11" and dex == "hyperliquid"
                else PRIVATE_RESEARCH_ROOT
                / (
                    f"reservoir-six-{dex}-{token}"
                    if cohort == "sealed_six"
                    else f"reservoir-monitored-plus-six-{dex}-{token}"
                )
            )
            for day in days_between(start, end):
                k = (dex, day)
                if k in roots:
                    raise ValueError("DUPLICATE_DEX_DAY_ROOT")
                roots[k] = root
    return roots


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("MISSING_OR_SYMLINKED_EVIDENCE")
    return json.loads(path.read_text())


def build_index(cohort: str = "sealed_six") -> dict[str, Any]:
    wallets, selected = scope_from_registry(cohort)
    roster_sha = selected["wallet_set_sha256"]
    expected_days = days_between(START, END)
    sources = window_sources(cohort)
    if set(sources) != {(d, day) for d in ALLOWED_DEXES for day in expected_days}:
        raise ValueError("WINDOW_COVERAGE_INCOMPLETE")
    entries: list[dict[str, Any]] = []
    summary: dict[str, Counter[str]] = {dex: Counter() for dex in ALLOWED_DEXES}
    state_by_date: dict[str, dict[str, tuple[int, int]]] = {d: {} for d in expected_days}
    for day in expected_days:
        for dex in sorted(ALLOWED_DEXES):
            root = sources[(dex, day)]
            if root != ORIGINAL_MAIN_PILOT and not root.resolve().is_relative_to(
                PRIVATE_RESEARCH_ROOT.resolve()
            ):
                raise ValueError("EVIDENCE_ROOT_ESCAPE")
            prepath = root / "preflight.json"
            pre = read_manifest(prepath)
            if pre["scope"]["wallet_set_sha256"] != roster_sha:
                raise ValueError("FROZEN_SELECTED_WALLET_SET_CHANGED")
            if pre["scope"].get("cohort", "sealed_six") != cohort:
                raise ValueError("RESEARCH_COHORT_DRIFT")
            if cohort == "monitored_plus_six" and pre["scope"] != selected:
                raise ValueError("MONITORED_ROSTER_PROVENANCE_DRIFT")
            if pre["scope"]["portfolio_versions"] != selected["portfolio_versions"]:
                raise ValueError("FROZEN_PORTFOLIO_SELECTION_CHANGED")
            if pre.get("dex", "hyperliquid") != dex:
                raise ValueError("DEX_SOURCE_MISMATCH")
            expected_snapshot_scope = (
                "global" if cohort == "sealed_six" and root == ORIGINAL_MAIN_PILOT else "dex"
            )
            if pre.get("snapshot_scope", "global") != expected_snapshot_scope:
                raise ValueError("SNAPSHOT_SOURCE_SCOPE_MISMATCH")
            if day not in pre["days"]:
                raise ValueError("MISSING_DAY_PREFLIGHT")
            artifacts = []
            for kind in ("fills", "position_snapshot"):
                matches = [
                    x for x in pre["objects"] if x["type"] == kind and f"date={day}/" in x["key"]
                ]
                if len(matches) != 1:
                    raise ValueError("MISSING_OR_MULTIPLE_FROZEN_OBJECT")
                source = matches[0]
                folder = root / kind / f"day={day}"
                provenance = verify_artifact(folder, source["etag"], roster_sha)
                if provenance is None:
                    raise ValueError("MISSING_STAGED_SOURCE_ARTIFACT")
                data_path = folder / "data.parquet"
                if data_path.is_symlink():
                    raise ValueError("SYMLINKED_PRIVATE_DATA")
                if source["key"] != provenance["source_key"]:
                    raise ValueError("SOURCE_KEY_PROVENANCE_MISMATCH")
                if pq.read_metadata(data_path).num_rows != provenance["rows"]:
                    raise ValueError("ROW_COUNT_SHA_OR_FOOTER_MISMATCH")
                table = pq.read_table(data_path)
                if kind == "fills":
                    row_checks = validate_fills(table, set(wallets), day, dex=dex)
                    if row_checks["rows"] != provenance["rows"]:
                        raise ValueError("REVALIDATION_ROW_COUNT_MISMATCH")
                    subset_count = table.num_rows
                    summary[dex]["fills"] += subset_count
                    if subset_count == 0:
                        summary[dex]["zero_fill_days_unknown"] += 1
                else:
                    rows = table.select(
                        ["wallet", "market", "state_block", "state_ts_ms"]
                    ).to_pylist()
                    if any(r["wallet"] not in wallets for r in rows):
                        raise ValueError("SNAPSHOT_WALLET_SCOPE_MISMATCH")
                    if root != ORIGINAL_MAIN_PILOT and any(
                        (":" in r["market"])
                        if dex == "hyperliquid"
                        else not r["market"].startswith("xyz:")
                        for r in rows
                    ):
                        raise ValueError("DEX_SNAPSHOT_MARKET_SCOPE_MISMATCH")
                    # The original main pilot used a source global snapshot.
                    # Reuse only its main-DEX rows; xyz data is separately
                    # acquired from the per-DEX xyz snapshot object.
                    filtered = (
                        [r for r in rows if (":" not in r["market"]) if dex == "hyperliquid"]
                        if dex == "hyperliquid"
                        else rows
                    )
                    subset_count = len(filtered)
                    summary[dex]["snapshot_position_rows"] += subset_count
                    if not rows:
                        # Original source's state is pinned in the manifest
                        # even when the selected wallet rows are empty.
                        summary[dex]["empty_snapshot_days_unknown"] += 1
                    for r in rows:
                        if (
                            r["state_block"] != source["block"]
                            or r["state_ts_ms"] != source["state_ts_ms"]
                        ):
                            raise ValueError("SOURCE_SNAPSHOT_STATE_ID_MISMATCH")
                    state_by_date[day][dex] = (source["block"], source["state_ts_ms"])
                artifacts.append(
                    {
                        "kind": kind,
                        "path": str(data_path),
                        "parquet_sha256": provenance["sha256"],
                        "source_key": source["key"],
                        "source_etag": source["etag"],
                        "source_object_bytes": source["bytes"],
                        "source_state_block": source.get("block"),
                        "source_state_ts_ms": source.get("state_ts_ms"),
                        "rows_staged": table.num_rows,
                        "rows_within_scope": subset_count,
                        "empty_not_inactivity": table.num_rows == 0,
                    }
                )
            entries.append(
                {
                    "day": day,
                    "dex": dex,
                    "preflight_sha256": sha256(prepath.read_bytes()).hexdigest(),
                    "artifacts": artifacts,
                }
            )

    mismatched = {
        day: state
        for day, state in state_by_date.items()
        if set(state) != ALLOWED_DEXES or state["hyperliquid"] != state["xyz"]
    }
    if mismatched:
        raise ValueError("CROSS_DEX_STATE_BLOCK_OR_TIME_MISMATCH")
    for dex in sorted(ALLOWED_DEXES):
        summary[dex]["verified_dates"] = len(expected_days)

    return {
        "schema": "reservoir_two_dex_catalog_v3",
        "cohort": cohort,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "scope": selected,
        "allowed_dexes": sorted(ALLOWED_DEXES),
        "start": str(START),
        "end": str(END),
        "dates": expected_days,
        "entries": entries,
        "counts": {d: dict(c) for d, c in summary.items()},
        "source_status": "HISTORICAL_SELECTED_WALLET_STAGED_ONLY",
        "historical_first_known": False,
        "scientifically_qualified": False,
        "paper_admitted": False,
        "trading_authorized": False,
        "limitations": [
            "EX_POST_SELECTED_COHORT",
            "NATIVE_SAME_MILLISECOND_ORDER_UNRESOLVED",
            "ONLY_HYPERLIQUID_AND_XYZ_DEXES",
            "ZERO_WALLET_FILLS_DOES_NOT_PROVE_INACTIVITY",
            "SNAPSHOTS_ARE_ONCE_PER_DAY_NOT_FIVE_MINUTES",
        ],
    }


def write_catalog(folder: Path, index: dict[str, Any]) -> str:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "catalog.json"
    if path.exists():
        saved = read_manifest(path)
        for key in ("scope", "entries", "counts", "dates", "allowed_dexes"):
            if saved[key] != index[key]:
                raise ValueError("CATALOG_DRIFT_VERSION_REQUIRED")
        return sha256(path.read_bytes()).hexdigest()
    return exclusive_bytes(path, (jdump(index) + "\n").encode())


def _verified_paths(
    index: dict[str, Any],
    dex: str,
    start: date | None,
    end: date | None,
    kind: str,
) -> list[str]:
    if kind not in ("fills", "position_snapshot"):
        raise ValueError("UNAPPROVED_RESEARCH_DATASET")
    if dex not in ALLOWED_DEXES or dex not in index["allowed_dexes"]:
        raise ValueError("SOURCE_DEX_NOT_APPROVED")
    first, last = start or START, end or END
    if not (START <= first <= last <= END):
        raise ValueError("OUTSIDE_VERIFIED_DATE_WINDOW")
    matches = [
        e
        for e in index["entries"]
        if e["dex"] == dex and first.isoformat() <= e["day"] <= last.isoformat()
    ]
    if len(matches) != (last - first).days + 1:
        raise ValueError("INCOMPLETE_REQUESTED_DATE_WINDOW")
    paths = []
    for entry in matches:
        artifact = next(a for a in entry["artifacts"] if a["kind"] == kind)
        path = Path(artifact["path"])
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(PRIVATE_RESEARCH_ROOT.resolve())
        ):
            raise ValueError("BACKTEST_SOURCE_PATH_NOT_VERIFIED")
        if sha256(path.read_bytes()).hexdigest() != artifact["parquet_sha256"]:
            raise ValueError("BACKTEST_SOURCE_SHA_MISMATCH")
        paths.append(str(path))
    return paths


def scan_fills(
    index: dict[str, Any],
    dex: str,
    start: date | None = None,
    end: date | None = None,
) -> pl.LazyFrame:
    """Load only SHA-verified, historical selected-wallet fill rows."""
    paths = _verified_paths(index, dex, start, end, "fills")
    return pl.scan_parquet(paths, hive_partitioning=False)


def scan_snapshots(
    index: dict[str, Any],
    dex: str,
    start: date | None = None,
    end: date | None = None,
) -> pl.LazyFrame:
    """Load SHA-verified snapshots filtered to the exact approved DEX.

    The original 2026-11-05..11-11 main-DEX pilot used global snapshots;
    this reader excludes all HIP-3 rows from that preserved source.
    """
    paths = _verified_paths(index, dex, start, end, "position_snapshot")
    frame = pl.scan_parquet(paths, hive_partitioning=False)
    selector = (
        ~pl.col("market").str.contains(":")
        if dex == "hyperliquid"
        else pl.col("market").str.starts_with("xyz:")
    )
    return frame.filter(selector)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify", "counts"))
    parser.add_argument(
        "--cohort", choices=("sealed_six", "monitored_plus_six"), default="sealed_six"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.out is None:
        args.out = MONITORED_CATALOG_ROOT if args.cohort == "monitored_plus_six" else CATALOG_ROOT
    index = build_index(args.cohort)
    if args.mode in ("build", "verify"):
        if args.mode == "build":
            digest = write_catalog(args.out, index)
        else:
            path = args.out / "catalog.json"
            if not path.is_file():
                raise ValueError("CATALOG_MISSING")
            saved = read_manifest(path)
            for key in ("scope", "entries", "counts", "dates", "allowed_dexes"):
                if saved[key] != index[key]:
                    raise ValueError("CATALOG_INTEGRITY_MISMATCH")
            digest = sha256(path.read_bytes()).hexdigest()
        print(
            jdump(
                {
                    "status": "STAGED_SOURCE_CATALOG_" + args.mode.upper() + "_PASS",
                    "catalog_sha256": digest,
                    "wallets": index["scope"]["wallet_count"],
                    "dates": len(index["dates"]),
                    "counts": index["counts"],
                    "scientifically_qualified": False,
                    "paper_admitted": False,
                }
            )
        )
    else:
        print(
            jdump(
                {
                    "status": "HISTORICAL_SOURCE_ONLY",
                    "start": index["start"],
                    "end": index["end"],
                    "counts": index["counts"],
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Errors may originate in private data. Print type only.
        print(jdump({"status": "BLOCKED", "reason_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
