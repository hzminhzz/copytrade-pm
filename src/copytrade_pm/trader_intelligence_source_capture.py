"""Bounded read-only all-DEX P1 source snapshot using existing E4 parsers.

One observed state is not a continuous PIT book or reconciled equity. The
private 90-day alias filenames are locator hints, NOT an independently
attested roster. No fill API, order client, signing key or service is used.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable

from .pm_e4_prospective import (
    _account_state,
    _dex_universe,
    _guarded_info,
    _safe_dir,
    _subaccount_roster,
)
from .pm_hyperx_account_triage import _write_immutable_private

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
ALIAS = re.compile(r"[A-Za-z0-9_-]{2,70}\Z")
MAX_PARENTS = 5
MAX_CAPTURE_INFO_CALLS = 80  # 1 catalog, <=5 parents, <=5*(11 dex+spot+subaccounts)


def _locate(source: Path, alias: str) -> tuple[str, str]:
    if not ALIAS.fullmatch(alias) or source.is_symlink() or not source.is_dir():
        raise ValueError("INVALID_PRIVATE_SOURCE_ROSTER")
    candidates = list(source.glob(f"{alias}_0x*.json"))
    if len(candidates) != 1:
        raise ValueError("AMBIGUOUS_OR_MISSING_PRIVATE_WALLET_ALIAS")
    path = candidates[0]
    if path.is_symlink() or not path.is_file():
        raise ValueError("UNTRUSTED_PRIVATE_ROSTER_SYMLINK")
    address = path.stem.removeprefix(f"{alias}_")
    if not ADDRESS.fullmatch(address):
        raise ValueError("INVALID_SOURCE_WALLET_ADDRESS")
    return address.lower(), sha256(path.read_bytes()).hexdigest()


def collect(
    source_root: Path,
    generation: Path,
    aliases: tuple[str, ...],
    *,
    info: Callable = _guarded_info,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """Take one current snapshot; persist each raw provider reply off Git.

    Cap the *entire* discovery+state query budget before requesting accounts.
    Unknown/missing responses fail the capture rather than making equity zero.
    """
    if not 1 <= len(aliases) <= MAX_PARENTS or len(set(aliases)) != len(aliases):
        raise ValueError("INVALID_BOUNDED_SOURCE_ROSTER")
    if len(aliases) != len({x.lower() for x in aliases}):
        raise ValueError("CASE_DUPLICATE_SOURCE_ROSTER")
    known = clock or (lambda: datetime.now(UTC))
    roster = {alias: _locate(source_root, alias) for alias in aliases}
    if len({address for address, _ in roster.values()}) != len(roster):
        raise ValueError("DUPLICATE_SOURCE_WALLET_ADDRESS")
    _safe_dir(generation)
    calls = 0

    def fetch(relative: str, payload: dict) -> object:
        nonlocal calls
        if calls >= MAX_CAPTURE_INFO_CALLS:
            raise ValueError("SOURCE_CAPTURE_PROVIDER_BUDGET_EXCEEDED")
        requested = known()
        body, raw, response_sha = info(payload)
        received = known()
        if requested.tzinfo is None or received.tzinfo is None or received < requested:
            raise ValueError("INVALID_SOURCE_SNAPSHOT_LOCAL_CLOCK")
        _write_immutable_private(generation / "raw" / relative, raw)
        calls += 1
        return body, {
            "requested_at": requested.astimezone(UTC).isoformat(),
            "received_at": received.astimezone(UTC).isoformat(),
            "source_sha256": response_sha,
            "bytes_sha256": sha256(raw).hexdigest(),
            "type": payload["type"],
        }

    catalog, catalog_receipt = fetch("perpDexs.json", {"type": "perpDexs"})
    dexs = _dex_universe(catalog)
    subjects: dict[str, tuple[str, str]] = {}
    provenance: dict[str, dict] = {}
    for alias, (address, historical_file_sha) in roster.items():
        sub, receipt = fetch(f"{alias}/subAccounts.json", {"type": "subAccounts", "user": address})
        members = _subaccount_roster(sub, address)
        provenance[alias] = {
            "private_historical_file_sha256": historical_file_sha,
            "source_identity_sha256": sha256(address.encode()).hexdigest(),
            "subaccount_count": len(members),
            "subaccount_discovery": receipt,
            "master_account_scope_only": False,
        }
        subjects[alias] = (alias, address)
        for idx, member in enumerate(members):
            subjects[f"{alias}-sub{idx:02d}"] = (alias, member.lower())
    if len(subjects) != len({address for _, address in subjects.values()}):
        raise ValueError("DUPLICATE_PARENT_OR_SUBACCOUNT")
    # allDexsClearinghouseState is a WebSocket-only subscription. HTTP /info
    # supports per-DEX clearinghouseState. Multiple REST observations do NOT
    # constitute an atomic simultaneous source book.
    if calls + len(subjects) * (len(dexs) + 1) > MAX_CAPTURE_INFO_CALLS:
        raise ValueError("SOURCE_SNAPSHOT_TOO_MANY_DISCOVERED_SUBACCOUNTS")

    books: dict[str, dict] = {}
    for subject, (parent_alias, address) in subjects.items():
        states = []
        dex_receipts = {}
        for dex in sorted(dexs):
            requested_dex = "" if dex == "default" else dex
            state, receipt = fetch(
                f"{subject}/perp-{dex}.json",
                {"type": "clearinghouseState", "user": address, "dex": requested_dex},
            )
            if not isinstance(state, dict):
                raise ValueError("INVALID_PER_DEX_SOURCE_RESPONSE")
            states.append([requested_dex, state])
            dex_receipts[dex] = receipt
        parsed = _account_state(
            {"user": address, "clearinghouseStates": states},
            address,
            expected_dexs=dexs,
        )
        spot, spot_receipt = fetch(
            f"{subject}/spot.json",
            {"type": "spotClearinghouseState", "user": address},
        )
        if not isinstance(spot, dict):
            raise ValueError("INVALID_SPOT_SOURCE_RESPONSE")
        books[subject] = {
            "parent_alias": parent_alias,
            "subject_identity_sha256": sha256(address.encode()).hexdigest(),
            "all_dexs": parsed,
            "per_dex_receipts": dex_receipts,
            "atomic_cross_dex_snapshot": False,
            "spot_receipt": spot_receipt,
            "spot_source_present_not_reconciled": True,
            "complete_historical_book": False,
            "independent_equity_attested": False,
        }
    report = {
        "schema": "ti_source_native_snapshot_v1",
        "source": "OFFICIAL_HYPERLIQUID_INFO_READ_ONLY",
        "captured_at": known().astimezone(UTC).isoformat(),
        "catalog_receipt": catalog_receipt,
        "official_dex_count": len(dexs),
        "provider_calls": calls,
        "parent_wallets": provenance,
        "accounts": books,
        "roster_provenance": "PRIVATE_HISTORICAL_FILENAME_LOCATOR_NOT_INDEPENDENT_PIT_ROSTER",
        "whole_wallet_equity_reconciled": False,
        "continuous_prospective_capture_proven": False,
        "follower_outcome_attested": False,
        "scientific_qualification": "NOT_QUALIFIED",
        "research_only": True,
        "trading_authorized": False,
    }
    _write_immutable_private(
        generation / "snapshot.json",
        (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    return {
        "schema": report["schema"],
        "generation": str(generation),
        "aliases": list(aliases),
        "accounts_observed": len(books),
        "official_dex_count": len(dexs),
        "provider_calls": calls,
        "snapshot_sha256": sha256((generation / "snapshot.json").read_bytes()).hexdigest(),
        "scientific_qualification": "NOT_QUALIFIED",
        "trading_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source-files", required=True, type=Path)
    parser.add_argument("--generation", required=True, type=Path)
    parser.add_argument(
        "--aliases", required=True, help="Comma-separated existing private alias names"
    )
    args = parser.parse_args()
    aliases = tuple(x.strip() for x in args.aliases.split(","))
    print(json.dumps(collect(args.private_source_files, args.generation, aliases), sort_keys=True))


if __name__ == "__main__":
    main()
