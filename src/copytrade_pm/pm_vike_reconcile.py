"""Read-only, SHA-verified Vike/HyperX historical wallet-fill reconciliation.

No provider data is imported into SQLite, financial positions or prospective
journals. Native trade IDs are kept exact (never parsed via JS Number).
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3


def _ms(iso_timestamp: str) -> int:
    stamp = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("TIMESTAMP_NOT_UTC_AWARE")
    delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _num(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("FILL_NUMERIC_INVALID") from exc
    if not number.is_finite():
        raise ValueError("FILL_NUMERIC_NONFINITE")
    return number


def _id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("NATIVE_TRADE_ID_INVALID")
    return value


def _key(symbol: object, tid: object) -> tuple[str, int]:
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("FILL_SYMBOL_INVALID")
    return (symbol, _id(tid))


def wallet_from_registry(db: Path, *, namespace: str, alias: str) -> str:
    """Read identity ONLY; this never attests full registry/signed selections."""
    if not db.is_file():
        raise ValueError("REGISTRY_FILE_NOT_FOUND")
    with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("REGISTRY_PHYSICAL_INTEGRITY_FAILED")
        rows = con.execute(
            "SELECT DISTINCT w.address FROM wallet_aliases a "
            "JOIN wallets w ON w.wallet_id=a.wallet_id "
            "WHERE a.alias=? AND a.namespace=?",
            (alias, namespace),
        ).fetchall()
    if len(rows) != 1:
        raise ValueError("REGISTRY_WALLET_IDENTITY_UNRESOLVED")
    addr = rows[0][0]
    if not isinstance(addr, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", addr) is None:
        raise ValueError("REGISTRY_WALLET_ADDRESS_INVALID")
    return addr.lower()


def load_vike(parts_dir: Path, *, stem: str = "vike_w028_part_") -> tuple[dict, dict]:
    paths = sorted(parts_dir.glob(f"{stem}*.json"))
    if not paths:
        raise ValueError("VIKE_RAW_CHUNKS_ABSENT")
    records: dict[tuple[str, int], dict] = {}
    seen_parts: set[int] = set()
    payload_shas: list[str] = []
    wallet: str | None = None
    total: int | None = None
    query: dict | None = None
    for path in paths:
        raw = path.read_bytes()
        payload_shas.append(sha256(raw).hexdigest())
        payload = json.loads(raw)
        if payload.get("schema") != "vike_mcp_unmodified_fill_items_chunk_v1":
            raise ValueError("VIKE_RAW_CHUNK_SCHEMA_UNRECOGNIZED")
        if payload.get("retrospective_first_known_at", False) is not None:
            raise ValueError("VIKE_RETROSPECTIVE_KNOWN_AT_FORGED")
        if wallet is not None and payload.get("wallet") != wallet:
            raise ValueError("VIKE_CHUNK_WALLET_DRIFT")
        wallet = payload.get("wallet")
        if not isinstance(wallet, str) or not wallet.startswith("0x"):
            raise ValueError("VIKE_CHUNK_WALLET_INVALID")
        if query is not None and payload.get("query") != query:
            raise ValueError("VIKE_CHUNK_QUERY_DRIFT")
        query = payload.get("query")
        if not isinstance(query, dict) or "start" not in query or "end" not in query:
            raise ValueError("VIKE_CHUNK_QUERY_INVALID")
        if total is not None and payload.get("total_parts") != total:
            raise ValueError("VIKE_CHUNK_TOTAL_DRIFT")
        total = payload.get("total_parts")
        index = payload.get("part")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index in seen_parts
        ):
            raise ValueError("VIKE_CHUNK_SEQUENCE_COLLISION")
        seen_parts.add(index)
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("VIKE_CHUNK_ITEMS_INVALID")
        for row in items:
            if not isinstance(row, dict):
                raise ValueError("VIKE_FILL_ROW_INVALID")
            key = _key(row.get("symbol"), row.get("trade_id"))
            if key in records:
                raise ValueError("VIKE_NATIVE_TRADE_ID_DUPLICATED")
            ts = _ms(row["ts"])
            if ts < _ms(query["start"]) or ts >= _ms(query["end"]):
                raise ValueError("VIKE_FILL_OUT_OF_DECLARED_WINDOW")
            _num(row["size_token"])
            _num(row["price"])
            records[key] = row
    if seen_parts != set(range(total or 0)):
        raise ValueError("VIKE_CHUNK_SEQUENCE_GAP")
    return records, {
        "wallet": wallet,
        "source_sha256": sha256("\n".join(payload_shas).encode()).hexdigest(),
        "chunks": len(paths),
        "count": len(records),
        "query": query,
        "first_known_at": "UNKNOWN_RETROSPECTIVE",
    }


def archive_vike_chunks(parts_dir: Path, destination_root: Path, *, alias: str) -> dict:
    """Copy SHA-verified MCP evidence into a private, immutable archive.

    Original staged JSON chunks are never changed, and archival publication
    requires a manifest as its final marker.
    """
    records, source = load_vike(parts_dir)
    paths = sorted(parts_dir.glob("vike_w028_part_*.json"))
    if len(paths) != source["chunks"]:
        raise ValueError("VIKE_ARCHIVE_CHUNK_COUNT_DRIFT")
    if not alias or not all(c.isascii() and (c.isalnum() or c in "-_") for c in alias):
        raise ValueError("VIKE_ARCHIVE_ALIAS_INVALID")
    destination_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = destination_root / f"{alias}-raw-{source['source_sha256'][:20]}"
    target.mkdir(mode=0o700, exist_ok=False)
    files = []
    for path in paths:
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        dest = target / path.name
        descriptor = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        files.append({"file": path.name, "sha256": digest, "bytes": len(raw)})
    manifest = {
        "schema": "copytrade_vike_mcp_raw_chunks_archive_v1",
        "alias": alias,
        "wallet_address_in_private_chunks": True,
        "source_sha256": source["source_sha256"],
        "fill_count": len(records),
        "first_known_at": None,
        "restored_prospective_knowledge": False,
        "order_route": "NONE",
        "files": files,
    }
    raw_manifest = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    descriptor = os.open(target / "manifest.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw_manifest)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "directory": str(target),
        "manifest_sha256": sha256(raw_manifest).hexdigest(),
        "source_sha256": source["source_sha256"],
        "fill_count": len(records),
    }


def load_hyperx(cache: Path, *, alias: str, wallet: str) -> tuple[dict, dict]:
    journal = cache / "append_only_page_journal.jsonl"
    if not journal.is_file():
        raise ValueError("HYPERX_SOURCE_JOURNAL_MISSING")
    records: dict[tuple[str, int], dict] = {}
    observed_pages: set[tuple[str, int]] = set()
    page_shas: list[str] = []
    from urllib.parse import quote

    for line in journal.read_text().splitlines():
        if not line.strip():
            raise ValueError("HYPERX_SOURCE_JOURNAL_BLANK_LINE")
        info = json.loads(line)
        if info.get("alias") != alias:
            continue
        coin = info["coin"]
        page = info["page"]
        page_key = (coin, page)
        if page_key in observed_pages:
            raise ValueError("HYPERX_DUPLICATE_JOURNAL_PAGE")
        observed_pages.add(page_key)
        folder = cache / "pages" / alias / quote(coin, safe="")
        raw_path = folder / f"page-{page:05d}.json.gz"
        sidecar_path = folder / f"page-{page:05d}.meta.json"
        if not raw_path.is_file() or not sidecar_path.is_file():
            raise ValueError("HYPERX_SOURCE_PAGE_MISSING")
        if json.loads(sidecar_path.read_text()) != info:
            raise ValueError("HYPERX_SIDECAR_JOURNAL_DRIFT")
        original = gzip.decompress(raw_path.read_bytes())
        raw_sha = sha256(original).hexdigest()
        if raw_sha != info.get("sha256"):
            raise ValueError("HYPERX_RAW_SHA_MISMATCH")
        page_shas.append(f"{coin}|{page}|{raw_sha}")
        payload = json.loads(original)
        if payload.get("page") != page or payload.get("page_size") != 2000:
            raise ValueError("HYPERX_PAGINATION_CONTRACT_DRIFT")
        rows = payload.get("fills")
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError("HYPERX_FILL_PAGE_INVALID")
        for row in rows:
            if row.get("user", "").lower() != wallet.lower():
                raise ValueError("HYPERX_WALLET_IDENTITY_DRIFT")
            if row.get("coin") != coin:
                raise ValueError("HYPERX_INSTRUMENT_IDENTITY_DRIFT")
            key = _key(coin, row.get("tid"))
            if key in records:
                raise ValueError("HYPERX_NATIVE_TRADE_ID_DUPLICATED")
            if isinstance(row.get("time"), bool) or not isinstance(row.get("time"), int):
                raise ValueError("HYPERX_FILL_TIME_INVALID")
            _num(row["sz"])
            _num(row["px"])
            records[key] = row
    if not observed_pages:
        raise ValueError("HYPERX_WALLET_SOURCE_EMPTY")
    return records, {
        "wallet_alias": alias,
        "source_sha256": sha256("\n".join(sorted(page_shas)).encode()).hexdigest(),
        "pages_verified": len(observed_pages),
        "count": len(records),
    }


def reconcile(vike: dict, hyperx: dict, vike_meta: dict, hyperx_meta: dict) -> dict:
    """Pair ONLY native IDs, classify temporal/source gaps; no inferred fill repairs."""
    if (
        vike_meta["wallet"].lower()
        != hyperx_meta.get("wallet_address", vike_meta["wallet"]).lower()
    ):
        raise ValueError("VENDOR_WALLET_IDENTITY_CONFLICT")
    left, right = set(hyperx), set(vike)
    joined = left & right
    hx_span: dict[str, tuple[int, int]] = {}
    for row in hyperx.values():
        coin, stamp = row["coin"], row["time"]
        lower, upper = hx_span.get(coin, (stamp, stamp))
        hx_span[coin] = (min(lower, stamp), max(upper, stamp))
    oldest = min(r["time"] for r in hyperx.values())
    latest = max(r["time"] for r in hyperx.values())
    vike_only = Counter()
    examples = []
    interior_examples = []
    period_gap_candidates = []
    all_vike_only_candidates = []
    for sym, tid in sorted(right - left):
        stamp = _ms(vike[(sym, tid)]["ts"])
        span = hx_span.get(sym)
        if stamp > latest:
            classification = "AFTER_HYPERX_GLOBAL_CUTOFF"
        elif stamp < oldest:
            classification = "BEFORE_HYPERX_GLOBAL_EARLIEST"
        elif span is None:
            classification = "SYMBOL_NOT_IN_HYPERX_CACHE_WITHIN_GLOBAL_SPAN"
        elif stamp > span[1]:
            classification = "AFTER_HYPERX_LATEST_FOR_SYMBOL"
        elif stamp < span[0]:
            classification = "BEFORE_HYPERX_EARLIEST_FOR_SYMBOL"
        else:
            classification = "WITHIN_HYPERX_OBSERVED_SYMBOL_RANGE_UNRESOLVED"
        vike_only[classification] += 1
        item = {
            "coin": sym,
            "trade_id": str(tid),
            "class": classification,
            "ts": vike[(sym, tid)]["ts"],
        }
        if len(examples) < 12:
            examples.append(item)
        all_vike_only_candidates.append(item)
        if (
            classification != "AFTER_HYPERX_GLOBAL_CUTOFF"
            and classification != "BEFORE_HYPERX_GLOBAL_EARLIEST"
        ):
            period_gap_candidates.append(item)
        if classification == "WITHIN_HYPERX_OBSERVED_SYMBOL_RANGE_UNRESOLVED":
            interior_examples.append(item)
    conflicts = Counter()
    for key in joined:
        h, v = hyperx[key], vike[key]
        if _ms(v["ts"]) != h["time"]:
            conflicts["timestamp_ms"] += 1
        mapped = {"A": "sell", "B": "buy"}.get(h["side"])
        if mapped != v["side"]:
            conflicts["side"] += 1
        if _num(h["sz"]) != _num(v["size_token"]):
            conflicts["quantity"] += 1
        if _num(h["px"]) != _num(v["price"]):
            conflicts["price"] += 1
    if not hyperx:
        raise ValueError("HYPERX_SOURCE_EMPTY")
    rest = vike_meta["query"]
    within_query_hyperx = {
        k for k, r in hyperx.items() if _ms(rest["start"]) <= r["time"] < _ms(rest["end"])
    }
    hyperx_only_within_query = len(within_query_hyperx - right)
    status = (
        "BLOCKED_FILL_CONFLICT"
        if conflicts or hyperx_only_within_query
        else "PARTIAL_RECONCILIATION_UNQUALIFIED"
    )
    return {
        "schema": "copytrade_vike_hyperx_native_fill_reconciliation_v1",
        "alias": hyperx_meta["wallet_alias"],
        "status": status,
        "historical_backfill_not_local_receipt": True,
        "order_route": "NONE",
        "source": {
            "vike_chunks": vike_meta["chunks"],
            "vike_source_sha256": vike_meta["source_sha256"],
            "hyperx_pages_verified": hyperx_meta["pages_verified"],
            "hyperx_source_sha256": hyperx_meta["source_sha256"],
        },
        "counts": {
            "vike": len(vike),
            "hyperx": len(hyperx),
            "matched_trade_ids": len(joined),
            "hyperx_only_in_vike_window": hyperx_only_within_query,
            "vike_only": len(right - left),
            "vike_only_classes": dict(sorted(vike_only.items())),
            "matched_conflicts": dict(sorted(conflicts.items())),
        },
        "hyperx_observed_span_utc": {
            "oldest": datetime.fromtimestamp(oldest / 1000, timezone.utc).isoformat(),
            "latest": datetime.fromtimestamp(latest / 1000, timezone.utc).isoformat(),
        },
        "unverified_vike_only_examples": examples,
        "interior_gap_candidates": interior_examples,
        "period_gap_candidates": period_gap_candidates,
        "all_vike_only_candidates": all_vike_only_candidates,
        "missing_data_auto_inserted": 0,
        "source_nav_reconciled": False,
        "prospective_known_at_reconstructed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vike-dir", type=Path, required=True)
    parser.add_argument("--hyperx-cache", type=Path, required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--wallet", help="Explicit wallet address, never printed")
    parser.add_argument("--registry-db", type=Path, help="Read-only SQLite identity source")
    parser.add_argument("--namespace", default="frozen_pm01")
    parser.add_argument("--archive-to", type=Path, help="Explicit immutable private archive root")
    args = parser.parse_args()
    if (args.wallet is None) == (args.registry_db is None):
        parser.error("provide exactly one of --wallet and --registry-db")
    wallet = (
        args.wallet
        if args.wallet is not None
        else wallet_from_registry(args.registry_db, namespace=args.namespace, alias=args.alias)
    )
    vike, vike_meta = load_vike(args.vike_dir)
    if vike_meta["wallet"].lower() != wallet.lower():
        raise SystemExit("VIKE_WALLET_IDENTITY_MISMATCH")
    hyperx, hyperx_meta = load_hyperx(args.hyperx_cache, alias=args.alias, wallet=wallet)
    hyperx_meta["wallet_address"] = wallet
    report = reconcile(vike, hyperx, vike_meta, hyperx_meta)
    if args.archive_to is not None:
        report["private_raw_archive"] = archive_vike_chunks(
            args.vike_dir, args.archive_to, alias=args.alias
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
