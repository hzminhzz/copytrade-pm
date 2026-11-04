"""Read-only provenance inventory for local historical Hyperliquid source files.

This never treats static wallet equity as point-in-time NAV, never fabricates
first-known receipt timestamps, and never writes into the source repository.
All public output is aggregate and excludes wallet addresses and filenames.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re

from .pm_offline_manifest import ManifestBlocked, ManifestInvalid
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource

GROUPS = (
    "wallet_fills_90d",
    "broader_active_inventory_fills_90d",
    "nansen_smart_money_fills_90d",
)
SHA = re.compile(r"^[a-f0-9]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
MAX_SOURCE_FILE = 32 * 1024 * 1024
MAX_FILES = 250
MAX_WINDOW_DAYS = 120
MAX_FILLS = 1_000_000


def _hash_file(path: Path) -> str:
    checksum = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def native_instrument(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ManifestInvalid("INVALID_SOURCE_INSTRUMENT")
    if ":" in raw:
        dex, symbol = raw.split(":", 1)
    else:
        dex, symbol = "default", raw
    instrument = f"hyperliquid:mainnet:perp:{dex}:{symbol}"
    try:
        VerifiedHyperliquidMinuteSource._family(instrument)
    except MarketDataBlocked as exc:
        raise ManifestInvalid("UNSUPPORTED_SOURCE_INSTRUMENT") from exc
    return instrument


def _clock(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ManifestInvalid("INVALID_WINDOW_CLOCK") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ManifestInvalid("NAIVE_WINDOW_CLOCK")
    return dt.astimezone(UTC)


def _source_files(source_root: Path) -> list[Path]:
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ManifestInvalid("UNSAFE_OR_MISSING_RESEARCH_SOURCE_ROOT")
    paths: list[Path] = []
    for group in GROUPS:
        directory = root / group
        if directory.is_symlink() or not directory.is_dir():
            raise ManifestBlocked(f"MISSING_SOURCE_GROUP_{group.upper()}")
        candidates = sorted(directory.glob("*.json"))
        if not candidates:
            raise ManifestBlocked(f"EMPTY_SOURCE_GROUP_{group.upper()}")
        paths.extend(candidates)
    if len(paths) > MAX_FILES:
        raise ManifestBlocked("TOO_MANY_SOURCE_FILES")
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_FILE:
            raise ManifestBlocked("UNSAFE_OR_OVERSIZED_SOURCE_FILE")
    return paths


def _market_day(
    root: Path,
    instrument: str,
    day: datetime,
    *,
    verify_sha: bool,
) -> tuple[str, int]:
    try:
        family = VerifiedHyperliquidMinuteSource._family(instrument)
    except MarketDataBlocked:
        return "UNSUPPORTED_INSTRUMENT", 0
    folder = root / family / (f"year={day.year:04d}/month={day.month:02d}/day={day.day:02d}")
    data = folder / "data.parquet"
    meta_file = folder / "source.json"
    if not data.is_file() or not meta_file.is_file():
        return "MISSING_NATIVE_DAY", 0
    if data.is_symlink() or meta_file.is_symlink():
        return "SYMLINK_NATIVE_DAY", 0
    try:
        if meta_file.stat().st_size > 1024 * 1024:
            return "OVERSIZED_NATIVE_METADATA", 0
        meta = json.loads(meta_file.read_text())
        dex, symbol = instrument.split(":")[3:]
        expected_symbol = symbol if dex == "default" else f"{dex}:{symbol}"
        if (
            meta.get("exchange") not in {"hyperliquid_futures", "hyperliquid", "HYPERLIQUID"}
            or meta.get("source_symbol") != expected_symbol
            or meta.get("source_type") not in {"trades", "candles"}
            or not isinstance(meta.get("sha256"), str)
            or not SHA.fullmatch(meta["sha256"])
        ):
            return "INVALID_NATIVE_METADATA", 0
        rows = meta.get("bars")
        if type(rows) is not int or not 0 <= rows <= 1440:
            return "INVALID_NATIVE_BAR_COUNT", 0
        if verify_sha and _hash_file(data) != meta["sha256"]:
            return "NATIVE_PARQUET_SHA_MISMATCH", 0
        if rows != 1440:
            return "PARTIAL_NATIVE_DAY", rows
        return ("VERIFIED_NATIVE_DAY" if verify_sha else "DECLARED_NATIVE_DAY"), rows
    except ValueError, OSError, TypeError:
        return "MALFORMED_NATIVE_METADATA", 0


def inspect_repository(
    source_root: Path,
    market_root: Path,
    *,
    start: str,
    end: str,
    verify_market_sha: bool = False,
) -> dict:
    """Return privacy-safe aggregate audit; untrusted/unknown inputs never certify PnL."""
    begin, finish = _clock(start), _clock(end)
    if (
        begin >= finish
        or begin.time() != datetime.min.time()
        or finish.time() != datetime.min.time()
        or (finish - begin).days != (finish - begin).total_seconds() / 86400
        or not 1 <= (finish - begin).days <= MAX_WINDOW_DAYS
    ):
        raise ManifestInvalid("INVALID_AUDIT_WINDOW")
    market_root = Path(market_root)
    if market_root.is_symlink() or not market_root.is_dir():
        raise ManifestInvalid("UNSAFE_OR_MISSING_MARKET_ROOT")
    files = _source_files(source_root)
    digest_parts = []
    seen_wallets: set[str] = set()
    seen_source_fills: set[tuple[str, str, str]] = set()
    coins: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    source_rows = 0
    in_window = 0
    duplicate_source_tids = 0
    first_known_observations = 0
    source_equity_snapshots_with_time = 0
    for path in files:
        digest_parts.append(_hash_file(path))
        try:
            doc = json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            raise ManifestBlocked("MALFORMED_SOURCE_JSON") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("fills"), list):
            raise ManifestBlocked("INVALID_SOURCE_SCHEMA")
        address = doc.get("address")
        if not isinstance(address, str) or not ADDRESS.fullmatch(address):
            raise ManifestBlocked("INVALID_SOURCE_ACCOUNT_IDENTITY")
        unique = address.lower()
        if unique in seen_wallets:
            reasons["DUPLICATE_ACCOUNT_SOURCE_FILES"] += 1
        seen_wallets.add(unique)
        nav = doc.get("equity")
        try:
            equity = Decimal(str(nav))
        except InvalidOperation, ValueError, TypeError:
            reasons["MISSING_CURRENT_EQUITY"] += 1
        else:
            if equity <= 0 or not equity.is_finite():
                reasons["INVALID_CURRENT_EQUITY"] += 1
            # The single scalar equity has NO as-of source timestamp.
            if doc.get("equity_first_known_at") is not None:
                source_equity_snapshots_with_time += 1
        for event in doc["fills"]:
            source_rows += 1
            if source_rows > MAX_FILLS:
                raise ManifestBlocked("SOURCE_EVENT_BUDGET_EXCEEDED")
            if not isinstance(event, dict):
                reasons["MALFORMED_FILL_ROW"] += 1
                continue
            raw_clock = event.get("time")
            if type(raw_clock) is not int or raw_clock <= 0:
                reasons["MISSING_SOURCE_EVENT_MS"] += 1
                continue
            time = datetime.fromtimestamp(raw_clock / 1000, UTC)
            if not begin <= time < finish:
                reasons["OUTSIDE_FROZEN_WINDOW"] += 1
                continue
            try:
                instrument = native_instrument(event.get("coin"))
            except ManifestInvalid:
                reasons["UNSUPPORTED_COIN_IN_WINDOW"] += 1
                continue
            tid = event.get("tid")
            if not isinstance(tid, int) and not isinstance(tid, str):
                reasons["MISSING_EVENT_TID"] += 1
                continue
            key = (unique, instrument, str(tid))
            if key in seen_source_fills:
                duplicate_source_tids += 1
                continue
            seen_source_fills.add(key)
            if event.get("first_known_at") is not None:
                first_known_observations += 1
            if event.get("startPosition", event.get("start_position")) is None:
                reasons["MISSING_START_POSITION"] += 1
            coins[instrument] += 1
            in_window += 1
    day_count = (finish - begin).days
    market_status: Counter[str] = Counter()
    eligible_native_instruments = 0
    all_days_covered_instruments = 0
    native_day_rows = 0
    for instrument in sorted(coins):
        available = 0
        for offset in range(day_count):
            day = begin + timedelta(days=offset)
            status, bars = _market_day(market_root, instrument, day, verify_sha=verify_market_sha)
            market_status[status] += 1
            native_day_rows += bars
            if status in {"DECLARED_NATIVE_DAY", "VERIFIED_NATIVE_DAY"}:
                available += 1
        if available:
            eligible_native_instruments += 1
        if available == day_count:
            all_days_covered_instruments += 1
    lineage = sha256(json.dumps(sorted(digest_parts), separators=(",", ":")).encode()).hexdigest()
    # These vendor snapshots do not supply complete historical first-known
    # receipts, whole-account equity series or atomic opening hedge books.
    return {
        "schema": "pm_offline_repository_inventory_v1",
        "status": "HISTORICAL_SOURCE_AND_NATIVE_MARKET_INVENTORY",
        "window_start_utc": begin.isoformat(),
        "window_end_utc_exclusive": finish.isoformat(),
        "source_file_count": len(files),
        "source_account_count": len(seen_wallets),
        "source_rows_all_time": source_rows,
        "source_rows_in_window_valid_unique": in_window,
        "source_duplicate_tid_count": duplicate_source_tids,
        "source_error_counts": dict(sorted(reasons.items())),
        "source_collection_sha256": lineage,
        "observed_native_instruments": len(coins),
        "instruments_with_any_complete_native_day": eligible_native_instruments,
        "instruments_with_every_complete_native_day": all_days_covered_instruments,
        "market_status_instrument_days": dict(sorted(market_status.items())),
        "market_claimed_bar_rows": native_day_rows,
        "market_day_hashes_verified": verify_market_sha,
        "independent_first_known_receipt_count": 0,
        "vendor_unverified_first_known_fields": first_known_observations,
        "equity_snapshots_with_asof": source_equity_snapshots_with_time,
        "whole_account_atomic_initial_book_verified": False,
        "clock_basis": "HISTORICAL_ORACLE",
        "contractual_follower_pnl": "BLOCKED_MISSING_HISTORICAL_NAV_AND_WHOLE_BOOK",
        "scientifically_qualified": False,
        "source_data_mutated": False,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--verify-market-sha", action="store_true")
    args = parser.parse_args()
    result = inspect_repository(
        args.source_root,
        args.market_root,
        start=args.start,
        end=args.end,
        verify_market_sha=args.verify_market_sha,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
