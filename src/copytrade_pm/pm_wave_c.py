"""Wave C: versioned two-wallet source intake beside the frozen PM-01 cohort.

Read-only. Vendor pages stay owner-private; only aliases, counts and hashes
enter Git. The frozen 6+10+20 manifests are never rewritten: Wave C is a
separate cohort (6+10+20+2 = 38) with its own generation manifest, private
identity map and independent integrity artifact.

Wave C wallets are historically vendor-covered only. Nothing here creates a
first-known clock, a follower PnL or trading authority.
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, defaultdict
from datetime import UTC, datetime
from decimal import Decimal as D
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote

from .pm_fill_replay import _market_instrument
from .pm_market_audit import _audit_partition
from .pm_portfolio import validate_38_wallet_cohort
from .pm_research import _write_private_evidence
from .pm_sources import CohortEntry, _load, _private_map, load_cohort


TARGETS = "WAVE_C_2_TARGETS_20261031.json"
IDENTITY = "PRIVATE_WAVE_C_ALIAS_MAPPING_20261031.json"
MANIFEST = "generation_manifest.json"
GENERATION_ROOT = "slow_pod_data_v1/wave_c_v1"
PROPR_UNIVERSE = "PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json"
COHORT = "waveC"
ACCEPTED = "ACCEPTED_FOR_IN_WINDOW_REPLAY"
# Native 1m lake begins 2025-09-29 and has no verified source day for
# 2026-03-01..2026-04-07 (every coin) or XMR 2026-04-10; 2025 vendor chains
# also carry unresolved breaks. Replay therefore starts after those gaps.
REPLAY_WINDOW_START = datetime(2026, 4, 11, tzinfo=UTC)
REPLAY_WINDOW_REASON = (
    "NATIVE_1M_LAKE_GAP_20260301_20260407_AND_XMR_20260410;"
    "2025_VENDOR_CHAIN_BREAKS_PRE_WINDOW"
)
MAX_PAGES = 4


def _pages(directory: Path, alias: str, coin: str) -> list[dict]:
    pages = []
    for n in range(1, MAX_PAGES + 1):
        archive = directory / f"page-{n:05d}.json.gz"
        meta = directory / f"page-{n:05d}.meta.json"
        if not archive.exists() and not meta.exists():
            break
        if not archive.is_file() or not meta.is_file():
            raise ValueError("PARTIAL_SOURCE_PAGE_PAIR")
        raw = gzip.decompress(archive.read_bytes())
        sidecar = json.loads(meta.read_text(encoding="utf-8"))
        if sha256(raw).hexdigest() != sidecar.get("sha256"):
            raise ValueError("SOURCE_PAGE_HASH_MISMATCH")
        if (
            sidecar.get("alias") != alias
            or sidecar.get("coin") != coin
            or sidecar.get("page") != n
        ):
            raise ValueError("SOURCE_PAGE_IDENTITY_DRIFT")
        document = json.loads(raw)
        if document.get("page") != n or document.get("page_size") != 2000:
            raise ValueError("UNVERIFIED_SOURCE_PAGINATION")
        pages.append({"document": document, "sidecar": sidecar})
    if (directory / f"page-{MAX_PAGES + 1:05d}.json.gz").exists():
        raise ValueError("UNBOUNDED_SOURCE_PAGES_NOT_SUPPORTED")
    return pages


def _pairs(generation: Path) -> dict[str, dict[str, list[dict]]]:
    pairs: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for alias_dir in sorted(p for p in generation.iterdir() if p.is_dir()):
        for coin_dir in sorted(p for p in alias_dir.iterdir() if p.is_dir()):
            pairs[alias_dir.name][unquote(coin_dir.name)] = _pages(
                coin_dir, alias_dir.name, unquote(coin_dir.name)
            )
    return dict(pairs)


def build_manifest(generation: Path) -> dict:
    """Index the immutable generation bytes; never fetches, never rewrites pages."""
    summary = json.loads((generation / "run-summary.json").read_text(encoding="utf-8"))
    if summary.get("schema") != "wavec_hyperx_fills_generation_v1":
        raise ValueError("UNEXPECTED_WAVE_C_GENERATION_SUMMARY")
    if summary.get("no_live_orders") is not True or summary.get("no_trading_api") is not True:
        raise ValueError("WAVE_C_GENERATION_NOT_RESEARCH_ONLY")
    pairs: dict[str, dict[str, dict]] = {}
    for alias, coins in sorted(_pairs(generation).items()):
        pairs[alias] = {}
        for coin, pages in sorted(coins.items()):
            if not pages:
                raise ValueError("EMPTY_SOURCE_PAIR")
            fills = [f for page in pages for f in page["document"]["fills"]]
            addresses = {str(page["document"].get("address", "")).lower() for page in pages}
            if len(addresses) != 1 or not next(iter(addresses)):
                raise ValueError("SOURCE_PAIR_ADDRESS_DRIFT")
            address = next(iter(addresses))
            if sha256(address.encode("ascii")).hexdigest() != pages[0]["sidecar"].get(
                "address_sha256"
            ):
                raise ValueError("SOURCE_PAIR_ADDRESS_HASH_MISMATCH")
            times = [int(fill["time"]) for fill in fills]
            pairs[alias][coin] = {
                "pages": len(pages),
                "rows": len(fills),
                "unique_trade_ids": len({int(fill["tid"]) for fill in fills}),
                "pagination_exhausted": pages[-1]["document"].get("has_more") is False,
                "page_sha256": [page["sidecar"]["sha256"] for page in pages],
                "address_sha256": pages[0]["sidecar"]["address_sha256"],
                "first_fill_ms": min(times),
                "last_fill_ms": max(times),
            }
    return {
        "schema": "wave_c_generation_manifest_v1",
        "cohort": COHORT,
        "generation": generation.name,
        "adapter_sha256": summary["adapter_sha256"],
        "created_at_utc": summary["created_at_utc"],
        "no_live_orders": True,
        "no_trading_api": True,
        "wallet_count": len(pairs),
        "coin_pair_count": sum(len(coins) for coins in pairs.values()),
        "source_fills": sum(p["rows"] for coins in pairs.values() for p in coins.values()),
        "pairs": pairs,
    }


def _chain_breaks(fills: list[dict]) -> list[dict]:
    """Position-linked, same-millisecond tolerant fill chain."""
    groups: dict[int, list[dict]] = OrderedDict()
    for fill in sorted(fills, key=lambda r: (int(r["time"]), int(r["tid"]))):
        groups.setdefault(int(fill["time"]), []).append(fill)
    breaks: list[dict] = []
    previous: D | None = None
    for when, group in groups.items():
        pending = list(group)
        while pending:
            pick = None
            if previous is None:
                pick = pending[0]
            else:
                pick = next(
                    (r for r in pending if D(str(r["start_position"])) == previous), None
                )
            if pick is None:
                breaks.append(
                    {
                        "time_ms": when,
                        "expected_before": str(previous),
                        "observed_before": pending[0]["start_position"],
                    }
                )
                pick = pending[0]
            pending.remove(pick)
            size = D(str(pick["sz"]))
            previous = D(str(pick["start_position"])) + (
                size if pick["side"] == "B" else -size
            )
    return breaks


def _propr_symbols(root: Path) -> set[str]:
    universe = _load(root, PROPR_UNIVERSE)
    if universe.get("schema") != "propr_public_universe_browser_snapshot_v1":
        raise ValueError("PROPR_PUBLIC_UNIVERSE_SCHEMA_CHANGED")
    return set(universe["market_symbols"]["crypto"])


def audit_generation(generation: Path, research_root: Path, market_root: Path) -> dict:
    """Independent, read-only verification of one Wave C generation."""
    generation = generation.resolve()
    manifest_path = generation / MANIFEST
    if not manifest_path.is_file():
        raise ValueError("MISSING_WAVE_C_GENERATION_MANIFEST")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rebuilt = build_manifest(generation)
    if manifest != rebuilt:
        raise ValueError("WAVE_C_GENERATION_MANIFEST_DRIFT")
    manifest_sha = sha256(manifest_path.read_bytes()).hexdigest()
    propr = _propr_symbols(research_root)
    cutoff = int(REPLAY_WINDOW_START.timestamp() * 1000)
    status_cache: dict[tuple[str, str], str] = {}
    wallets = []
    for alias, coins in sorted(_pairs(generation).items()):
        duplicate_tids = 0
        fills: list[dict] = []
        breaks: list[dict] = []
        exhausted = True
        for coin, pages in sorted(coins.items()):
            seen: set[int] = set()
            for page in pages:
                for fill in page["document"]["fills"]:
                    tid = int(fill["tid"])
                    if tid in seen:
                        duplicate_tids += 1
                    seen.add(tid)
                    if fill.get("coin") != coin:
                        raise ValueError("FILL_INSTRUMENT_MISMATCH")
                    fills.append(fill)
            exhausted = exhausted and pages[-1]["document"].get("has_more") is False
            breaks.extend({"coin": coin, **row} for row in _chain_breaks(
                [f for page in pages for f in page["document"]["fills"]]
            ))
        in_window = [f for f in fills if int(f["time"]) >= cutoff]
        instrument_days = sorted(
            {
                (
                    fill["coin"],
                    datetime.fromtimestamp(int(fill["time"]) / 1000, UTC).date().isoformat(),
                )
                for fill in in_window
            }
        )
        statuses = Counter()
        for coin, day in instrument_days:
            key = (coin, day)
            if key not in status_cache:
                status_cache[key] = _audit_partition(
                    market_root,
                    _market_instrument(coin),
                    datetime.fromisoformat(day + "T12:00:00+00:00"),
                )
            statuses[status_cache[key]] += 1
        uncovered = sum(
            count for status, count in statuses.items() if status != "SOURCE_DAY_SHA_VERIFIED"
        )
        breaks_in_window = [b for b in breaks if b["time_ms"] >= cutoff]
        wallets.append(
            {
                "alias": alias,
                "address_sha256": manifest["pairs"][alias][next(iter(coins))][
                    "address_sha256"
                ],
                "coin_pairs": len(coins),
                "source_fills": len(fills),
                "fills_in_window": len(in_window),
                "fills_before_window": len(fills) - len(in_window),
                "cross_page_duplicate_tids": duplicate_tids,
                "pagination_exhausted": exhausted,
                "page_sha256_mismatches": 0,
                "chain_breaks_total": len(breaks),
                "chain_breaks_in_window": len(breaks_in_window),
                "chain_breaks_before_window": [
                    {
                        **b,
                        "time_utc": datetime.fromtimestamp(b["time_ms"] / 1000, UTC).isoformat(),
                    }
                    for b in breaks
                    if b["time_ms"] < cutoff
                ],
                "instrument_days_in_window": sum(statuses.values()),
                "instrument_days_verified": statuses.get("SOURCE_DAY_SHA_VERIFIED", 0),
                "instrument_days_uncovered": uncovered,
                "market_day_status": dict(statuses),
                "outside_propr_universe": sorted(
                    {coin for coin in coins if coin not in propr}
                ),
            }
        )
    blockers = []
    for wallet in wallets:
        alias = wallet["alias"]
        if wallet["cross_page_duplicate_tids"]:
            blockers.append(f"{alias}:DUPLICATE_TIDS")
        if not wallet["pagination_exhausted"]:
            blockers.append(f"{alias}:PAGINATION_INCOMPLETE")
        if wallet["chain_breaks_in_window"]:
            blockers.append(f"{alias}:CHAIN_BREAK_IN_WINDOW")
        if wallet["instrument_days_uncovered"]:
            blockers.append(f"{alias}:UNVERIFIED_NATIVE_MARKET_DAY")
        if wallet["outside_propr_universe"]:
            blockers.append(f"{alias}:COIN_OUTSIDE_PROPR_PUBLIC_UNIVERSE")
    if len(wallets) != 2:
        blockers.append("WAVE_C_WALLET_COUNT_NOT_TWO")
    return {
        "schema": "wave_c_source_integrity_v1",
        "cohort": COHORT,
        "research_only": True,
        "no_live_orders": True,
        "generation": generation.name,
        "generation_manifest_sha256": manifest_sha,
        "adapter_sha256": manifest["adapter_sha256"],
        "replay_window_start": REPLAY_WINDOW_START.isoformat(),
        "replay_window_reason": REPLAY_WINDOW_REASON,
        "source_fills": sum(w["source_fills"] for w in wallets),
        "source_fills_in_window": sum(w["fills_in_window"] for w in wallets),
        "source_fills_before_window": sum(w["fills_before_window"] for w in wallets),
        "frozen_cohort_rewritten": False,
        "prospective_first_known": "UNKNOWN",
        "scientifically_qualified": False,
        "verdict": ACCEPTED if not blockers else "BLOCKED",
        "blockers": blockers,
        "wallets": wallets,
    }


def _write_manifest(generation: Path) -> Path:
    target = generation / MANIFEST
    raw = (json.dumps(build_manifest(generation), sort_keys=True, indent=2) + "\n").encode()
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("EXISTING_WAVE_C_GENERATION_MANIFEST_CONFLICT")
        return target
    fd, temp = tempfile.mkstemp(prefix=".pending-wave-c-", dir=generation)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target


def load_wave_c(
    root: Path, frozen: tuple[CohortEntry, ...] | None = None
) -> tuple[tuple[CohortEntry, ...], dict[str, str]]:
    """Require exactly two independently audited, non-colliding Wave C wallets."""
    root = root.resolve()
    targets = _load(root, TARGETS)
    if targets.get("schema") != "wave_c_cohort_targets_v1" or targets.get("cohort") != COHORT:
        raise ValueError("Wave C cohort targets schema changed")
    if targets.get("count") != 2:
        raise ValueError("Wave C cohort must be exactly 2 wallets")
    if targets.get("replay_window_start") != REPLAY_WINDOW_START.isoformat():
        raise ValueError("Wave C replay window changed: re-audit required")
    rows = targets.get("targets") or []
    aliases = [row.get("alias") for row in rows]
    if len(rows) != 2 or len(set(aliases)) != 2:
        raise ValueError("Wave C duplicate/omitted aliases")
    identities = _private_map(root, IDENTITY)
    generation = root / str(targets["generation"])
    manifest_path = generation / MANIFEST
    manifest_sha = sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_sha != targets.get("generation_manifest_sha256"):
        raise ValueError("Wave C generation manifest lineage mismatch")
    manifest = _load(root, str(targets["generation"]) + "/" + MANIFEST)
    if manifest.get("schema") != "wave_c_generation_manifest_v1":
        raise ValueError("Wave C generation manifest schema changed")
    if manifest.get("wallet_count") != 2 or manifest.get("coin_pair_count") != sum(
        len(row.get("coins") or []) for row in rows
    ):
        raise ValueError("Wave C generation pair roster drifted")
    integrity = _load(root, str(targets["integrity_result"]))
    if integrity.get("schema") != "wave_c_source_integrity_v1":
        raise ValueError("Wave C integrity schema changed")
    if integrity.get("generation_manifest_sha256") != manifest_sha:
        raise ValueError("Wave C integrity does not cover this generation")
    if integrity.get("replay_window_start") != REPLAY_WINDOW_START.isoformat():
        raise ValueError("Wave C integrity window mismatch")
    if integrity.get("verdict") != ACCEPTED:
        raise ValueError("Wave C source not independently accepted")
    audited = {row["alias"]: row for row in integrity.get("wallets", [])}
    frozen_addresses = {entry.address for entry in frozen or ()}
    frozen_aliases = {entry.alias for entry in frozen or ()}
    entries: list[CohortEntry] = []
    for row in rows:
        alias = row["alias"]
        if alias in frozen_aliases:
            raise ValueError(f"Wave C alias collides with frozen cohort: {alias}")
        address = identities.get(alias)
        if address is None:
            raise ValueError(f"missing Wave C identity for {alias}")
        if sha256(address.encode("ascii")).hexdigest() != row.get("address_sha256"):
            raise ValueError(f"Wave C identity hash mismatch: {alias}")
        if address in frozen_addresses:
            raise ValueError(f"Wave C address collides with frozen cohort: {alias}")
        audit = audited.get(alias)
        if audit is None:
            raise ValueError(f"Wave C wallet not audited: {alias}")
        for key in (
            "page_sha256_mismatches",
            "cross_page_duplicate_tids",
            "chain_breaks_in_window",
            "instrument_days_uncovered",
        ):
            if audit.get(key) != 0:
                raise ValueError(f"Wave C unresolved {key}: {alias}")
        if audit.get("pagination_exhausted") is not True:
            raise ValueError(f"Wave C vendor pagination incomplete: {alias}")
        if audit.get("outside_propr_universe"):
            raise ValueError(f"Wave C coin outside Propr universe: {alias}")
        pairs = manifest["pairs"].get(alias) or {}
        if sorted(pairs) != sorted(row.get("coins") or []):
            raise ValueError(f"Wave C coin roster drifted: {alias}")
        entries.append(
            CohortEntry(
                alias,
                COHORT,
                address,
                row["address_sha256"],
                "FRESH_WAVE_C_VENDOR_PAGINATION_EXHAUSTED_HISTORICAL_ONLY",
                sum(pair["pages"] for pair in pairs.values()),
                sum(pair["rows"] for pair in pairs.values()),
            )
        )
    fingerprints = {
        "wave_c_targets": sha256((root / TARGETS).read_bytes()).hexdigest(),
        "wave_c_identity": sha256((root / IDENTITY).read_bytes()).hexdigest(),
        "wave_c_generation_manifest": manifest_sha,
        "wave_c_integrity": sha256((root / str(targets["integrity_result"])).read_bytes()).hexdigest(),
    }
    return tuple(entries), fingerprints


def load_research_cohort(
    root: Path,
) -> tuple[tuple[CohortEntry, ...], dict[str, str]]:
    """Frozen 36 + Wave C 2, validated as one 38-wallet research cohort."""
    root = root.resolve()
    frozen, fingerprints = load_cohort(root)
    wave_c, wave_fingerprints = load_wave_c(root, frozen)
    entries = frozen + wave_c
    validate_38_wallet_cohort(entry.wallet for entry in entries)
    if len({entry.address for entry in entries}) != 38:
        raise ValueError("alias collision: 38 distinct address identities required")
    return entries, {**fingerprints, **wave_fingerprints}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("manifest", help="index an immutable Wave C generation")
    manifest.add_argument("--generation", type=Path, required=True)
    audit = sub.add_parser("audit", help="independently verify a Wave C generation")
    audit.add_argument("--research-root", type=Path, required=True)
    audit.add_argument("--generation", type=Path, required=True)
    audit.add_argument("--market-root", type=Path, required=True)
    audit.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "manifest":
        print(_write_manifest(args.generation.resolve()))
        return
    result = audit_generation(args.generation, args.research_root, args.market_root)
    path, digest = _write_private_evidence(args.out, result, prefix="wave-c-integrity")
    print(json.dumps({"evidence_path": str(path), "sha256": digest,
                      "verdict": result["verdict"], "blockers": result["blockers"]}, indent=2))


if __name__ == "__main__":
    main()
