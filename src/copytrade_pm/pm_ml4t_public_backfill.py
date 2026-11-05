"""Bounded official /info raw-fill recovery for ML4T-66 missing addresses.

This acquires historical PUBLIC fills only; no HyperX paid calls, broker route,
source NAV, retrospective first-known receipts, or SQLite mutations.
Writes immutable raw pages and derived source manifests to private 0700 roots.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError

from .pm_e4_prospective import _guarded_info
from .pm_hyperx_account_triage import _write_immutable_private
from .pm_ml4t_batch_recovery import local_sources, roster

PAGE_SIZE = 2000
MAX_CALLS = 12
MAX_PAGES = 4
MAX_WALLETS = 5
MIN_INTERVAL = 3.0


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _validate(rows: object, *, address: str, start_ms: int, end_ms: int, limit: int) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError("UNTRUSTED_PUBLIC_FILLS_PAGE")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_PUBLIC_FILL")
        if "user" in row and str(row["user"]).lower() != address:
            raise ValueError("PUBLIC_FILL_ADDRESS_MISMATCH")
        ts = row.get("time")
        if type(ts) is not int or not start_ms <= ts <= end_ms:
            raise ValueError("PUBLIC_FILL_OUTSIDE_STUDY_WINDOW")
        if type(row.get("tid")) is not int or row.get("side") not in ("A", "B"):
            raise ValueError("MISSING_PUBLIC_FILL_TID_OR_SIDE")
        if not isinstance(row.get("coin"), str) or not row["coin"]:
            raise ValueError("MISSING_PUBLIC_FILL_COIN")
        try:
            if float(row.get("px")) <= 0 or float(row.get("sz")) <= 0:
                raise ValueError("INVALID_PUBLIC_FILL_PRICE_SIZE")
        except (ValueError, TypeError) as exc:
            raise ValueError("INVALID_PUBLIC_FILL_PRICE_SIZE") from exc
    return rows


def acquire(
    *,
    db: Path,
    source_root: Path,
    out: Path,
    start_ms: int,
    end_ms: int,
    max_calls: int = MAX_CALLS,
    pages_per_wallet: int = 3,
    min_interval: float = MIN_INTERVAL,
    transport=None,
    page_size: int = PAGE_SIZE,
    sleep=None,
) -> dict:
    """Bounded serial call plan, current missing wallets only.

    Each response is stored *before* the next request, including an incomplete
    page. Pagination repeats the boundary timestamp to avoid dropping ties.
    """
    if not 1 <= max_calls <= MAX_CALLS or not 1 <= pages_per_wallet <= MAX_PAGES:
        raise ValueError("UNSAFE_API_CALL_BUDGET")
    if min_interval < MIN_INTERVAL or not 1 <= page_size <= PAGE_SIZE:
        raise ValueError("UNSAFE_PROVIDER_PAGE_OR_INTERVAL")
    if not 0 < start_ms < end_ms:
        raise ValueError("INVALID_STUDY_WINDOW")
    identities, cohort_sha = roster(db)
    existing, _ = local_sources(source_root, identities)
    needed = sorted((addr for addr, record in existing.items() if not record["events"]))
    if not needed or len(needed) > MAX_WALLETS:
        raise ValueError("NO_BOUNDED_MISSING_WALLET_SET")
    if out.exists():
        raise ValueError("IMMUTABLE_API_GENERATION_ALREADY_EXISTS")
    out.mkdir(parents=True, mode=0o700)
    if out.is_symlink() or out.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_SOURCE_OUTPUT_REQUIRED")
    provider = transport or _guarded_info
    wait = sleep or time.sleep
    report = {
        "schema": "ml4t66_public_info_fill_recovery_v1",
        "cohort_sha256": cohort_sha,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "wallets_requested": len(needed),
        "max_calls": max_calls,
        "requests": 0,
        "source": "OFFICIAL_HL_INFO_USERFILLSBYTIME_RETROSPECTIVE",
        "historical_first_known_proven": False,
        "whole_wallet_equity_proven": False,
        "trading_authorized": False,
        "wallets": [],
    }
    for address in needed:
        if report["requests"] >= max_calls:
            report["wallets"].append(
                {"alias": identities[address]["alias"], "status": "BLOCKED_CALL_BUDGET"}
            )
            continue
        identity_sha = sha256(address.encode()).hexdigest()[:18]
        seen: dict[tuple[str, str], dict] = {}
        pages = 0
        page_shas = []
        cursor_start, cursor_end = start_ms, end_ms
        order = None
        blocker = None
        while pages < pages_per_wallet and report["requests"] < max_calls:
            query = {
                "type": "userFillsByTime",
                "user": address,
                "startTime": cursor_start,
                "endTime": cursor_end,
            }
            request_at = datetime.now(UTC)
            if report["requests"]:
                wait(min_interval)
            report["requests"] += 1
            try:
                payload, raw, page_sha = provider(query)
                received_at = datetime.now(UTC)
                rows = _validate(
                    payload,
                    address=address,
                    start_ms=cursor_start,
                    end_ms=cursor_end,
                    limit=page_size,
                )
            except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError) as exc:
                blocker = "PROVIDER_OR_SCHEMA_" + type(exc).__name__
                break
            page_path = out / "raw" / identity_sha / f"page-{pages:03d}.json"
            _write_immutable_private(page_path, raw)
            _write_immutable_private(
                page_path.with_suffix(".meta.json"),
                _canonical(
                    {
                        "page_sha256": page_sha,
                        "requested_at_utc": request_at.isoformat(),
                        "received_at_utc": received_at.isoformat(),
                        "request_start_ms": cursor_start,
                        "request_end_ms": cursor_end,
                        "rows": len(rows),
                        "historical_first_known_proven": False,
                    }
                ),
            )
            page_shas.append(page_sha)
            pages += 1
            if not rows:
                break
            distinct = 0
            for row in rows:
                key = (row["coin"], str(row["tid"]))
                prior = seen.get(key)
                if prior is not None and prior != row:
                    blocker = "PUBLIC_FILL_CONFLICTING_TID"
                    break
                if prior is None:
                    seen[key] = row
                    distinct += 1
            if blocker:
                break
            if len(rows) < page_size:
                break
            times = [row["time"] for row in rows]
            direction = (
                "ascending"
                if times == sorted(times)
                else ("descending" if times == sorted(times, reverse=True) else None)
            )
            if direction is None:
                blocker = "PUBLIC_FILL_PAGINATION_ORDER_UNKNOWN"
                break
            if order is not None and order != direction:
                blocker = "PUBLIC_FILL_PAGINATION_ORDER_CHANGED"
                break
            order = direction
            if distinct == 0:
                blocker = "PUBLIC_FILL_CURSOR_STALLED"
                break
            if direction == "ascending":
                new_cursor = max(times)
                if new_cursor <= cursor_start:
                    blocker = "PUBLIC_FILL_CURSOR_STALLED"
                    break
                cursor_start = new_cursor
            else:
                new_cursor = min(times)
                if new_cursor >= cursor_end:
                    blocker = "PUBLIC_FILL_CURSOR_STALLED"
                    break
                cursor_end = new_cursor
        if blocker is None and pages >= pages_per_wallet and len(rows) == page_size:
            blocker = "PUBLIC_FILL_PAGE_CAP_UNEXHAUSTED"
        if blocker is None and report["requests"] >= max_calls and len(rows) == page_size:
            blocker = "PUBLIC_FILL_CALL_CAP_UNEXHAUSTED"
        if blocker is None and seen:
            # Raw, immutable pages remain primary; this is merely a normalized
            # index to allow the existing SQLite-address source scanner to
            # inspect recovered fills without interpreting filenames.
            data = {
                "alias": identities[address]["alias"],
                "address": address,
                "equity": None,
                "fills": sorted(seen.values(), key=lambda x: (x["time"], x["coin"], x["tid"])),
                "source_page_shas": page_shas,
                "source": "OFFICIAL_HL_INFO_HISTORICAL_NOT_PIT",
                "source_account_equity_complete": False,
                "historical_first_known_proven": False,
            }
            _write_immutable_private(out / "normalized" / f"{identity_sha}.json", _canonical(data))
        report["wallets"].append(
            {
                "alias": identities[address]["alias"],
                "address": address,
                "rows": len(seen),
                "pages": pages,
                "page_sha256s": page_shas,
                "status": blocker or "RETROSPECTIVE_SOURCE_ONLY",
            }
        )
    _write_immutable_private(out / "report.json", _canonical(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS)
    parser.add_argument("--pages-per-wallet", type=int, default=3)
    parser.add_argument("--min-interval", type=float, default=MIN_INTERVAL)
    args = parser.parse_args()
    report = acquire(
        db=args.db,
        source_root=args.source_root,
        out=args.output_root,
        start_ms=args.start_ms,
        end_ms=args.end_ms,
        max_calls=args.max_calls,
        pages_per_wallet=args.pages_per_wallet,
        min_interval=args.min_interval,
    )
    print(
        json.dumps(
            {
                "status": "BOUNDED_PUBLIC_READ_ONLY_RECOVERY",
                "api_requests": report["requests"],
                "wallet_results": [
                    {
                        "alias": r["alias"],
                        "rows": r.get("rows", 0),
                        "pages": r.get("pages", 0),
                        "status": r["status"],
                    }
                    for r in report["wallets"]
                ],
                "normalized_wallet_files": len(
                    list((args.output_root / "normalized").glob("*.json"))
                ),
                "report_path": str(args.output_root / "report.json"),
                "report_sha256": sha256(
                    (args.output_root / "report.json").read_bytes()
                ).hexdigest(),
                "whole_wallet_economics": "BLOCKED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
