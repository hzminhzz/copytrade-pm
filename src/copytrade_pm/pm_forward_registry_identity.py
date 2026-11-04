"""Read-only P1/P14 registry/owner-private source identity reconciliation.

Historical filename + address is a locator, not scientific or paper admission.
This inspector never writes the registry, promotes an unresolved wallet_id,
changes frozen portfolio membership, downloads fills, or starts a service.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

P1 = ("S035-ENA", "S051-BTC", "S053-HYPE")
P14 = (*P1, "S064-xyz:BRENTOIL", "Whale_0x5f94")
_HEX = re.compile(r"0x[0-9a-fA-F]{40}\Z")


def _private_locator(
    alias: str, *, primary_dir: Path, secondary_dir: Path
) -> tuple[Path, str, str]:
    if alias == "Whale_0x5f94":
        files = list(secondary_dir.glob("HL Perps Whale_0x5f94*.json"))
    elif alias in set(P14):
        files = list(primary_dir.glob(alias + "_0x*.json"))
    else:
        raise ValueError("PORTFOLIO_ALIAS_NOT_APPROVED")
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ValueError("MISSING_OR_AMBIGUOUS_PRIVATE_ALIAS_LOCATOR")
    path = files[0]
    payload = json.loads(path.read_bytes())
    address = payload.get("address")
    if not isinstance(address, str) or _HEX.fullmatch(address) is None:
        raise ValueError("PRIVATE_ALIAS_ADDRESS_NOT_VERIFIABLE")
    if alias == "Whale_0x5f94":
        truncated = path.stem.rsplit("_", 1)[-1].lower()
        if re.fullmatch(r"0x[0-9a-f]{8}", truncated) is None or not address.lower().startswith(
            truncated
        ):
            raise ValueError("PRIVATE_WHALE_ADDRESS_PREFIX_MISMATCH")
    elif not path.stem.endswith(address):
        raise ValueError("PRIVATE_ALIAS_FILENAME_ADDRESS_MISMATCH")
    return path, address.lower(), sha256(path.read_bytes()).hexdigest()


def audit_frozen_member_resolution(
    *,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    portfolio_id: str,
) -> dict:
    if portfolio_id not in ("P1", "P14"):
        raise ValueError("UNKNOWN_APPROVED_PORTFOLIO")
    expected = P1 if portfolio_id == "P1" else P14
    db_path = Path(registry_db)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("REGISTRY_NOT_TRUSTED_FILE")
    uri = "file:" + str(db_path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as conn:
        conn.execute("PRAGMA query_only=ON")
        row = conn.execute(
            "SELECT max(version) FROM portfolio_memberships WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchone()
        if row is None or row[0] is None:
            raise ValueError("PORTFOLIO_NOT_IN_REGISTRY")
        version = row[0]
        members = conn.execute(
            "SELECT member_alias,wallet_id FROM portfolio_memberships "
            "WHERE portfolio_id=? AND version=? ORDER BY member_alias",
            (portfolio_id, version),
        ).fetchall()
        if len(members) != len(expected) or {alias for alias, _ in members} != set(expected):
            raise ValueError("FROZEN_PORTFOLIO_MEMBER_CENSUS_DRIFT")
        seal = conn.execute(
            "SELECT definition_sha256,doc_sha256,selection_known_at FROM portfolio_seals "
            "WHERE portfolio_id=? AND version=?",
            (portfolio_id, version),
        ).fetchone()
        if seal is None:
            raise ValueError("FROZEN_PORTFOLIO_REGISTRY_SEAL_MISSING")
        sealed_at = datetime.fromisoformat(seal[2])
        if sealed_at.tzinfo is None:
            raise ValueError("FROZEN_PORTFOLIO_SELECTION_CLOCK_UNTRUSTED")
        manifest = []
        for alias, assigned_id in members:
            _path, addr, file_sha = _private_locator(
                alias, primary_dir=primary_dir, secondary_dir=secondary_dir
            )
            found = conn.execute(
                "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                "AND lower(address)=? ORDER BY wallet_id",
                (addr,),
            ).fetchall()
            if len(found) > 1:
                raise ValueError("DUPLICATE_NATIVE_ADDRESS_IN_REGISTRY")
            matched_id = found[0][0] if found else None
            if assigned_id is not None and matched_id != assigned_id:
                raise ValueError("FROZEN_WALLET_ID_CONFLICT")
            bound_by_seal = False
            if assigned_id is not None:
                records = conn.execute(
                    "SELECT known_at FROM wallet_aliases WHERE alias=? AND wallet_id=? LIMIT 129",
                    (alias, assigned_id),
                ).fetchall()
                if len(records) > 128:
                    raise ValueError("FROZEN_ALIAS_PROVENANCE_TOO_MANY_RECORDS")
                for (at,) in records:
                    known = datetime.fromisoformat(at)
                    if known.tzinfo is None:
                        raise ValueError("FROZEN_ALIAS_PROVENANCE_CLOCK_UNTRUSTED")
                    if known <= sealed_at:
                        bound_by_seal = True
            manifest.append(
                {
                    "alias": alias,
                    "address_sha256": sha256(addr.encode()).hexdigest(),
                    "historical_locator_sha256": file_sha,
                    "matched_registry_wallet": matched_id is not None,
                    "frozen_wallet_id_resolved": bound_by_seal,
                    "binding_known_by_original_seal": bound_by_seal,
                    "status": (
                        "REGISTRY_BINDING_PIT_COMPATIBLE_ONLY"
                        if bound_by_seal
                        else "BLOCKED_POST_SEAL_BINDING"
                        if assigned_id is not None
                        else "BLOCKED_UNSEALED_WALLET_IDENTITY"
                    ),
                    "historical_locator_not_first_known_admission": True,
                }
            )
    unresolved = [row["alias"] for row in manifest if not row["frozen_wallet_id_resolved"]]
    post_seal = [row["alias"] for row in manifest if row["status"] == "BLOCKED_POST_SEAL_BINDING"]
    return {
        "schema": "paper_portfolio_identity_resolution_audit_v1",
        "portfolio_id": portfolio_id,
        "registry_version": version,
        "registry_definition_sha256": seal[0],
        "source_document_sha256": seal[1],
        "selection_known_at": seal[2],
        "member_count": len(manifest),
        "members": manifest,
        "unresolved_aliases": unresolved,
        "post_seal_binding_aliases": post_seal,
        "status": "BLOCKED" if unresolved else "PIT_IDENTITY_RESOLVED_ONLY",
        "source_wallet_equity_attested": False,
        "registry_mutated": False,
        "paper_admitted": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--portfolio", choices=("P1", "P14"), required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            audit_frozen_member_resolution(
                registry_db=args.registry,
                primary_dir=args.primary_dir,
                secondary_dir=args.secondary_dir,
                portfolio_id=args.portfolio,
            ),
            indent=2,
            sort_keys=True,
        )
    )
