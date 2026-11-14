"""Independent native Hyperliquid checks for bounded Vike-only historical fills.

Research-only. Public /info userFillsByTime is a third source, not an execution
feed, a point-in-time follower receipt, or whole-account NAV evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from time import sleep
from typing import Callable
from urllib import error, request

from .pm_e4_prospective import INFO_ENDPOINT
from .pm_vike_reconcile import (
    _ms,
    _num,
    load_hyperx,
    load_vike,
    reconcile,
    wallet_from_registry,
)

USER_AGENT = "OpenAI File Downloader, XaiImageApiFetch/1.0"
MAX_DAYS = 10
MAX_ROWS_PER_DAY = 2000


def fetch_native_day(
    wallet: str,
    day: str,
    *,
    timeout: int = 25,
) -> tuple[list[dict], str]:
    start = _ms(day + "T00:00:00Z")
    payload = json.dumps(
        {
            "type": "userFillsByTime",
            "user": wallet,
            "startTime": start,
            "endTime": start + 86_400_000 - 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    http = request.Request(
        INFO_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with request.urlopen(http, timeout=timeout) as res:
            raw = res.read(10_000_001)
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise ValueError(f"NATIVE_API_FETCH_FAILED:{type(exc).__name__}") from exc
    if len(raw) > 10_000_000:
        raise ValueError("NATIVE_RESPONSE_TOO_LARGE")
    body = json.loads(raw)
    if not isinstance(body, list):
        raise ValueError("NATIVE_RESPONSE_NOT_FILL_LIST")
    if len(body) >= MAX_ROWS_PER_DAY:
        # The API caps records; cannot prove a particular fill is absent.
        raise ValueError("NATIVE_DAY_RESULT_POSSIBLY_TRUNCATED")
    return body, sha256(raw).hexdigest()


def validate_candidates(
    candidates: list[dict],
    vike_rows: dict,
    wallet: str,
    *,
    fetch: Callable[[str, str], tuple[list[dict], str]] = fetch_native_day,
    max_days: int = MAX_DAYS,
) -> dict:
    """Bound daily queries, verify native IDs *and* economic fields.

    Native absence is UNKNOWN, not evidence of a false Vike fill.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["ts"][:10]].append(candidate)
    if not 0 < len(grouped) <= min(MAX_DAYS, max_days):
        raise ValueError("NATIVE_DAY_BUDGET_EXCEEDED")
    classified = []
    provider_hashes = {}
    tally = Counter()
    for day in sorted(grouped):
        if datetime.fromisoformat(day).date() > datetime.now(timezone.utc).date():
            raise ValueError("NATIVE_FUTURE_DAY_REFUSED")
        native_rows, provider_sha = fetch(wallet, day)
        if len(native_rows) >= MAX_ROWS_PER_DAY:
            raise ValueError("NATIVE_DAY_RESULT_POSSIBLY_TRUNCATED")
        provider_hashes[day] = provider_sha
        index = {}
        for r in native_rows:
            if not isinstance(r, dict):
                raise ValueError("NATIVE_ROW_INVALID")
            tid, coin = r.get("tid"), r.get("coin")
            if isinstance(tid, bool) or not isinstance(tid, int) or not isinstance(coin, str):
                raise ValueError("NATIVE_TRADE_ID_OR_SYMBOL_INVALID")
            key = (coin, tid)
            if key in index:
                raise ValueError("NATIVE_DUPLICATE_ID_IN_DAY")
            index[key] = r
        for candidate in grouped[day]:
            key = (candidate["coin"], int(candidate["trade_id"]))
            v = vike_rows.get(key)
            if not isinstance(v, dict):
                raise ValueError("VIKE_CANDIDATE_SOURCE_MISSING")
            n = index.get(key)
            if n is None:
                state = "NOT_FOUND_IN_BOUNDED_NATIVE_DAY"
            elif (
                n.get("time") == _ms(v["ts"])
                and n.get("coin") == v["symbol"]
                and {"A": "sell", "B": "buy"}.get(n.get("side")) == v["side"]
                and _num(n.get("px")) == _num(v["price"])
                and _num(n.get("sz")) == _num(v["size_token"])
            ):
                state = "NATIVE_CONFIRMED_EXACT"
            else:
                state = "NATIVE_FIELD_CONFLICT"
            tally[state] += 1
            classified.append(
                {
                    "coin": key[0],
                    "trade_id": str(key[1]),
                    "event_ts": v["ts"],
                    "classification": candidate["class"],
                    "native_status": state,
                    "native_raw_record": n,
                }
            )
        sleep(0.15)
    return {
        "schema": "copytrade_native_confirm_vike_only_fills_v1",
        "status": "NATIVE_CONFIRMED_ALL"
        if tally == {"NATIVE_CONFIRMED_EXACT": len(candidates)}
        else "PARTIAL_OR_CONFLICT",
        "wallet_address_reported": False,
        "historical_known_at": None,
        "follower_first_known": None,
        "auto_mutations": 0,
        "days_queried": len(grouped),
        "rows_checked": len(candidates),
        "native_status_counts": dict(sorted(tally.items())),
        "native_response_sha256": dict(sorted(provider_hashes.items())),
        "candidates": classified,
        "source_nav_attested": False,
    }


def write_verified_overlay(root: Path, alias: str, native: dict, vike_rows: dict) -> dict:
    """Publish new versioned evidence, never mutate the frozen HyperX source.

    A directory has exactly one immutable publication marker, manifest.json.
    The manifest is written last; incomplete directories are not admissible.
    """
    if native.get("status") != "NATIVE_CONFIRMED_ALL":
        raise ValueError("OVERLAY_REQUIRES_ALL_NATIVE_CONFIRMED")
    if native.get("historical_known_at", False) is not None:
        raise ValueError("OVERLAY_CANNOT_FORGE_FIRST_KNOWN")
    candidates = native.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("OVERLAY_CANDIDATES_EMPTY")
    if len(candidates) != native.get("rows_checked"):
        raise ValueError("OVERLAY_CANDIDATES_COUNT_MISMATCH")
    if any(x.get("native_status") != "NATIVE_CONFIRMED_EXACT" for x in candidates):
        raise ValueError("OVERLAY_CONTAINS_UNCONFIRMED_FILL")
    source_shas = native.get("research_sources_sha256")
    if not isinstance(source_shas, dict) or set(source_shas) != {"vike", "hyperx"}:
        raise ValueError("OVERLAY_SOURCE_HASHES_MISSING")
    if not all(isinstance(v, str) and len(v) == 64 for v in source_shas.values()):
        raise ValueError("OVERLAY_SOURCE_HASHES_INVALID")
    fingerprint = sha256(
        json.dumps(
            {
                "sources": source_shas,
                "native": native["native_response_sha256"],
                "candidates": candidates,
                "candidate_scope": native.get("candidate_scope", "WITHIN_HYPERX_GLOBAL_SPAN_ONLY"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:20]
    if not alias or "/" in alias or "\\\\" in alias:
        raise ValueError("OVERLAY_ALIAS_INVALID")
    prepared = []
    seen_ids = set()
    for row in sorted(candidates, key=lambda x: (x["coin"], int(x["trade_id"]))):
        key = (row["coin"], int(row["trade_id"]))
        if key in seen_ids:
            raise ValueError("OVERLAY_DUPLICATE_NATIVE_ID")
        seen_ids.add(key)
        source_row = vike_rows.get(key)
        if not isinstance(source_row, dict):
            raise ValueError("OVERLAY_SOURCE_FILL_MISSING")
        native_raw = row.get("native_raw_record")
        if not isinstance(native_raw, dict):
            raise ValueError("OVERLAY_NATIVE_RAW_RECORD_MISSING")
        if native_raw.get("tid") != key[1] or native_raw.get("coin") != key[0]:
            raise ValueError("OVERLAY_NATIVE_RAW_IDENTITY_MISMATCH")
        prepared.append(
            {
                "wallet_alias": alias,
                "source_event_ts": source_row["ts"],
                "local_first_known_at": None,
                "is_retrospective": True,
                "source": "VIKE_RAW_AND_NATIVE_HYPERLIQUID_CONFIRMED",
                "native_trade_id": str(key[1]),
                "raw_vike": source_row,
                "raw_native": native_raw,
                "research_only": True,
                "follower_eligible": False,
            }
        )
    rows_raw = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in prepared
    ).encode()
    file_sha = sha256(rows_raw).hexdigest()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / f"{alias}-{fingerprint}"
    target.mkdir(mode=0o700, exist_ok=False)
    rows_path = target / "native_confirmed_missing_fills.jsonl"
    descriptor = os.open(rows_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(rows_raw)
        handle.flush()
        os.fsync(handle.fileno())

    manifest = {
        "schema": "copytrade_vike_w028_research_recovery_v2",
        "alias": alias,
        "native_confirmed_fills": len(prepared),
        "independent_native_raw_records_preserved": True,
        "candidate_scope": native.get("candidate_scope", "WITHIN_HYPERX_GLOBAL_SPAN_ONLY"),
        "derived_rows_sha256": file_sha,
        "derivation_source_sha256": source_shas,
        "native_response_sha256": native["native_response_sha256"],
        "as_of_classification": "RETROSPECTIVE_RESEARCH_ONLY",
        "first_known_at": None,
        "frozen_hyperx_overwritten": False,
        "sqlite_registry_mutated": False,
        "order_route": "NONE",
        "whole_account_nav_attested": False,
    }
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(target / "manifest.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(manifest_raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "directory": str(target),
        "manifest_sha256": sha256(manifest_raw).hexdigest(),
        "rows_sha256": file_sha,
        "rows": len(prepared),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vike-dir", type=Path, required=True)
    p.add_argument("--hyperx-cache", type=Path, required=True)
    p.add_argument("--alias", required=True)
    p.add_argument("--wallet", help="Explicit wallet address, never printed")
    p.add_argument("--registry-db", type=Path, help="Read-only SQLite identity source")
    p.add_argument("--namespace", default="frozen_pm01")
    p.add_argument("--max-days", type=int, default=MAX_DAYS)
    p.add_argument("--output-root", type=Path)
    p.add_argument("--include-after-cutoff", action="store_true")
    a = p.parse_args()
    if (a.wallet is None) == (a.registry_db is None):
        p.error("provide exactly one of --wallet and --registry-db")
    wallet = (
        a.wallet
        if a.wallet is not None
        else wallet_from_registry(a.registry_db, namespace=a.namespace, alias=a.alias)
    )
    vike, vm = load_vike(a.vike_dir)
    if vm["wallet"].lower() != wallet.lower():
        raise SystemExit("VIKE_WALLET_IDENTITY_MISMATCH")
    hyperx, hm = load_hyperx(a.hyperx_cache, alias=a.alias, wallet=wallet)
    hm["wallet_address"] = wallet
    report = reconcile(vike, hyperx, vm, hm)
    candidates = (
        report["all_vike_only_candidates"]
        if a.include_after_cutoff
        else report["period_gap_candidates"]
    )
    result = validate_candidates(candidates, vike, wallet, max_days=a.max_days)
    result["candidate_scope"] = (
        "ALL_VIKE_ONLY_IN_QUERY" if a.include_after_cutoff else "WITHIN_HYPERX_GLOBAL_SPAN_ONLY"
    )
    result["research_sources_sha256"] = {
        "vike": vm["source_sha256"],
        "hyperx": hm["source_sha256"],
    }
    if a.output_root is not None and result["status"] == "NATIVE_CONFIRMED_ALL":
        result["published_overlay"] = write_verified_overlay(a.output_root, a.alias, result, vike)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "NATIVE_CONFIRMED_ALL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
