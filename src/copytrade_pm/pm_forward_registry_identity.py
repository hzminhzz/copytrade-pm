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


def private_locator(alias: str, *, primary_dir: Path, secondary_dir: Path) -> tuple[Path, str, str]:
    return _private_locator(alias, primary_dir=primary_dir, secondary_dir=secondary_dir)


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


def preview_prospective_reseal(
    *,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    portfolio_id: str,
    as_of: str | None = None,
) -> dict:
    """Read-only PIT identity preflight for a NEW signed research selection.

    This does not repair an original P1/P14 seal. An operator's separate
    Ed25519 signature plus an independently reviewed key is still required.
    """
    from datetime import UTC, timezone

    from . import wallet_registry_signed_catalog as signed

    if portfolio_id not in ("P1", "P14"):
        raise ValueError("UNKNOWN_APPROVED_PORTFOLIO")
    cutoff = datetime.fromisoformat(as_of) if as_of is not None else datetime.now(UTC)
    if cutoff.tzinfo is None or cutoff > datetime.now(UTC):
        raise ValueError("PROSPECTIVE_PREVIEW_CLOCK_INVALID")
    cutoff_utc = cutoff.astimezone(timezone.utc).isoformat()
    # Independently audit and preserve the original sealed portfolio's
    # membership/canonical private-address evidence, including historical
    # post-seal warnings. It is deliberately not overwritten or promoted.
    historical = audit_frozen_member_resolution(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        portfolio_id=portfolio_id,
    )
    if cutoff < datetime.fromisoformat(historical["selection_known_at"]):
        raise ValueError("PROSPECTIVE_CUTOFF_PRECEDES_ORIGINAL_SELECTION")
    members = P1 if portfolio_id == "P1" else P14
    db_path = Path(registry_db)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("REGISTRY_NOT_TRUSTED_FILE")
    rows = []
    seen_ids: set[int] = set()
    with closing(sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        for alias in members:
            _, address, locator_sha = _private_locator(
                alias, primary_dir=primary_dir, secondary_dir=secondary_dir
            )
            observed = conn.execute(
                "SELECT a.wallet_id,a.known_at,w.venue,w.address "
                "FROM wallet_aliases a JOIN wallets w ON w.wallet_id=a.wallet_id "
                "WHERE a.alias=? ORDER BY a.known_at,a.wallet_id LIMIT 257",
                (alias,),
            ).fetchall()
            if len(observed) > 256:
                raise ValueError("PROSPECTIVE_ALIAS_PROVENANCE_UNBOUNDED")
            eligible = []
            for ident, known_raw, venue, observed_addr in observed:
                known = datetime.fromisoformat(known_raw)
                if known.tzinfo is None:
                    raise ValueError("PROSPECTIVE_ALIAS_CLOCK_UNTRUSTED")
                if known <= cutoff:
                    eligible.append((ident, known.astimezone(timezone.utc), venue, observed_addr))
            canonical_ids = {ident for ident, _, _, _ in eligible}
            if len(canonical_ids) > 1:
                raise ValueError("PROSPECTIVE_ALIAS_IDENTITY_CONFLICT")
            known_id = next(iter(canonical_ids)) if canonical_ids else None
            if known_id is not None and (
                any(
                    venue != "hyperliquid" or found_addr.lower() != address
                    for _, _, venue, found_addr in eligible
                )
                or known_id in seen_ids
            ):
                raise ValueError("PROSPECTIVE_ALIAS_ADDRESS_OR_DUPLICATE_WALLET")
            if known_id is not None:
                seen_ids.add(known_id)
            rows.append(
                {
                    "alias": alias,
                    "status": "PIT_ALIAS_ADDRESS_MATCH_ONLY"
                    if known_id is not None
                    else "BLOCKED_NO_ASOF_ALIAS",
                    "alias_known_by_asof": known_id is not None,
                    "alias_first_known_at": min(
                        (known.isoformat() for _, known, _, _ in eligible), default=None
                    ),
                    "historical_locator_sha256": locator_sha,
                    "address_sha256": sha256(address.encode()).hexdigest(),
                    "real_account_scope_attested": False,
                }
            )
        conn.execute("ROLLBACK")
    identity_complete = len(rows) == len(members) and all(
        item["alias_known_by_asof"] for item in rows
    )
    # Unlike P1/P14 originals, this is an entirely NEW namespace-qualified
    # unsigned research suggestion. Signed catalog assigns the actual first-
    # known timestamp at private verified import, never this preview timestamp.
    proposal_id = (
        "paper.prospective/"
        + portfolio_id
        + "-"
        + cutoff.astimezone(timezone.utc).strftime("%Y%m%d")
    )
    unsigned = {
        "schema": signed.SCHEMA,
        "scope": signed.SCOPE,
        "definitions": {proposal_id: {"members": list(members)}},
        "selections": [
            {"portfolio_id": proposal_id, "role": "RESEARCH_CANDIDATE", "priority": None}
        ],
        "trading_authorized": False,
    }
    if identity_complete:
        signed._parse(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode())
    return {
        "schema": "paper_prospective_identity_reseal_preflight_v1",
        "portfolio_id": portfolio_id,
        "as_of": cutoff_utc,
        "original_selection_known_at": historical["selection_known_at"],
        "original_definition_sha256": historical["registry_definition_sha256"],
        "original_aliases_post_seal": historical["post_seal_binding_aliases"],
        "member_count": len(members),
        "members": rows,
        "identity_asof_complete": identity_complete,
        "status": "SIGNER_REVIEW_REQUIRED" if identity_complete else "BLOCKED_IDENTITY_INCOMPLETE",
        "unsigned_candidate": unsigned if identity_complete else None,
        "signed_proof_provided": False,
        "operator_approved_new_selection": False,
        "source_nav_attested": False,
        "market_execution_attested": False,
        "paper_admitted": False,
        "trading_authorized": False,
        "order_route": "NONE",
        "registry_mutated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--portfolio", choices=("P1", "P14"), required=True)
    parser.add_argument(
        "--prospective-reseal-preview",
        action="store_true",
        help="Read-only PIT identity check and unsigned candidate; NOT a seal or paper authorization",
    )
    parser.add_argument("--as-of", help="UTC-offset observation cutoff (audit only)")
    args = parser.parse_args()
    if args.as_of and not args.prospective_reseal_preview:
        parser.error("--as-of requires --prospective-reseal-preview")
    common = dict(
        registry_db=args.registry,
        primary_dir=args.primary_dir,
        secondary_dir=args.secondary_dir,
        portfolio_id=args.portfolio,
    )
    report = (
        preview_prospective_reseal(**common, as_of=args.as_of)
        if args.prospective_reseal_preview
        else audit_frozen_member_resolution(**common)
    )
    print(json.dumps(report, indent=2, sort_keys=True))
