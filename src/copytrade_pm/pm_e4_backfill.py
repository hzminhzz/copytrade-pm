"""Bounded official Hyperliquid funding/collateral Q3 source backfill.

Historical data are retrospectively obtained in October. Each page is
immutable and locally timestamped; no first-known July event claims.
No broker or trading actions.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from .pm_e4_prospective import PODS, _canonical, _guarded_info, _safe_dir
from .pm_hyperx_account_triage import _write_immutable_private
from .pm_sources import load_cohort

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)
PAGE_SIZE = 500
MAX_PAGES_PER_SERIES = 60
MAX_HTTP_CALLS = 3 * 2 * MAX_PAGES_PER_SERIES


def _validate_rows(rows: object, *, start: int, end: int) -> tuple[int | None, int | None]:
    if not isinstance(rows, list) or len(rows) > PAGE_SIZE:
        raise ValueError("E4_UNTRUSTED_BACKFILL_PAGE")
    times = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("time")) is not int:
            raise ValueError("E4_INVALID_BACKFILL_EVENT_CLOCK")
        at = row["time"]
        if at < start or at > end:
            raise ValueError("E4_BACKFILL_OUTSIDE_REQUESTED_RANGE")
        times.append(at)
    if times != sorted(times):
        raise ValueError("E4_NONCHRONOLOGICAL_PROVIDER_BACKFILL")
    return (min(times), max(times)) if times else (None, None)


async def collect_historical(
    research_root: Path,
    generation: Path,
    *,
    pages_per_series: int = 35,
    interval_seconds: float = 3.0,
) -> dict:
    if not (1 <= pages_per_series <= MAX_PAGES_PER_SERIES):
        raise ValueError("E4_UNBOUNDED_BACKFILL_PAGINATION")
    if interval_seconds < 3.0:
        raise ValueError("E4_UNSAFE_PROVIDER_QUERY_INTERVAL")
    entries, fingerprints = load_cohort(research_root)
    roster = {e.alias: e for e in entries if e.alias in PODS}
    if set(roster) != set(PODS):
        raise ValueError("E4_UNKNOWN_WALLET")
    _safe_dir(generation)
    start = int(START.timestamp() * 1000)
    end = int(END.timestamp() * 1000) - 1
    report = {
        "schema": "e4_q3_hyperliquid_account_ledger_backfill_v1",
        "source": "OFFICIAL_HYPERLIQUID_INFO_HISTORICAL_NOT_PIT",
        "start_inclusive": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "cohort_sha256": fingerprints,
        "request_bound": MAX_HTTP_CALLS,
        "requests": 0,
        "wallets": [],
        "original_q3_first_known_receipts_recovered": False,
        "propr_broker_qualified": False,
    }
    for alias in PODS:
        entry = roster[alias]
        totals = {}
        for tag, request_type in (
            ("funding", "userFunding"),
            ("collateral", "userNonFundingLedgerUpdates"),
        ):
            offset = start
            next_advance = 0
            pages = 0
            unique: set[str] = set()
            last_page_count = 0
            boundary_ambiguous = False
            issue = None
            first_row_at = None
            last_row_at = None
            while pages < pages_per_series and offset <= end:
                if report["requests"] >= MAX_HTTP_CALLS:
                    issue = "CALL_BUDGET_EXHAUSTED"
                    break
                data_request = {
                    "type": request_type,
                    "user": entry.address,
                    "startTime": offset,
                    "endTime": end,
                }
                requested_at = datetime.now(UTC)
                report["requests"] += 1
                try:
                    data, raw, signature = await asyncio.to_thread(_guarded_info, data_request)
                    received_at = datetime.now(UTC)
                    earliest, latest = _validate_rows(data, start=offset, end=end)
                except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as exc:
                    issue = "PROVIDER_OR_SCHEMA_" + type(exc).__name__
                    break
                archive = generation / "raw" / alias / tag / f"page-{pages:03d}.json"
                _write_immutable_private(archive, raw)
                new = 0
                for event in data:
                    event_sha = sha256(_canonical(event)).hexdigest()
                    if event_sha not in unique:
                        unique.add(event_sha)
                        new += 1
                _write_immutable_private(
                    generation / "metadata" / alias / tag / f"page-{pages:03d}.json",
                    _canonical(
                        {
                            "source": "OFFICIAL_HL_INFO",
                            "kind": request_type,
                            "query_window_start_ms": offset,
                            "query_window_end_ms": end,
                            "locally_requested_at": requested_at.isoformat(),
                            "first_locally_received_at": received_at.isoformat(),
                            "sha256": signature,
                            "rows": len(data),
                            "new_unique_rows": new,
                            "first_row_ms": earliest,
                            "last_row_ms": latest,
                            "historical_first_known": False,
                        }
                    ),
                )
                pages += 1
                last_page_count = len(data)
                if earliest is not None and first_row_at is None:
                    first_row_at = earliest
                if latest is not None:
                    last_row_at = latest
                if len(data) < PAGE_SIZE:
                    break
                if latest is None or latest == offset or new == 0:
                    boundary_ambiguous = True
                    issue = "NO_PROGRESS_OR_SAME_TIMESTAMP_PAGE_OVERFLOW"
                    break
                # Inclusive overlap retains same-millisecond source records.
                # If the next page still saturates at the same timestamp,
                # stop rather than silently discarding tied events.
                next_advance = latest
                if next_advance <= offset:
                    boundary_ambiguous = True
                    issue = "NO_MONOTONIC_CURSOR_ADVANCE"
                    break
                offset = next_advance
                await asyncio.sleep(interval_seconds)
            complete = (
                issue is None
                and not boundary_ambiguous
                and last_page_count < PAGE_SIZE
                and pages > 0
            )
            totals[tag] = {
                "source_pages": pages,
                "unique_source_events": len(unique),
                "first_event_ms": first_row_at,
                "last_event_ms": last_row_at,
                "source_interval_complete": complete,
                "boundary_ambiguous": boundary_ambiguous,
                "stop_reason": issue or ("COMPLETE" if complete else "PAGE_BUDGET_EXHAUSTED"),
            }
        report["wallets"].append(
            {
                "alias": alias,
                "source_identity_sha256": entry.address_sha256,
                "funding": totals["funding"],
                "collateral": totals["collateral"],
                "retrospective_only": True,
            }
        )
    report["completed_at"] = datetime.now(UTC).isoformat()
    _write_immutable_private(generation / "backfill-report.json", _canonical(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--pages-per-series", type=int, default=35)
    parser.add_argument("--interval", type=float, default=3.0)
    a = parser.parse_args()
    report = asyncio.run(
        collect_historical(
            a.research_root,
            a.generation,
            pages_per_series=a.pages_per_series,
            interval_seconds=a.interval,
        )
    )
    raw = (a.generation / "backfill-report.json").read_bytes()
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "report_sha256": sha256(raw).hexdigest(),
                "path": str(a.generation / "backfill-report.json"),
                "official_requests": report["requests"],
                "wallets": [
                    {k: v for k, v in row.items() if k != "source_identity_sha256"}
                    for row in report["wallets"]
                ],
                "historic_first_known": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
