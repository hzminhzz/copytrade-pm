"""Read-only P1/P14 multi-source forward-paper readiness without false admission.

Uses canonical WR-06 registry, official parent-only Hyperliquid source receipts
and CCXT Pro public market quote tapes. It NEVER creates a paper account,
replays historical fills or submits an order. Sources/quotes may be present
yet a complete wallet NAV and executable capacity are still UNKNOWN.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from .pm03_account import clock, digest
from .pm_forward_admission import admit_source_book
from .pm_fixed_k_source_scope import assess_selected_parent_perp_scope
from .pm_forward_journal import PaperJournal
from .pm_forward_registry_identity import (
    P1,
    P14,
    audit_frozen_member_resolution,
)

_ALIAS = {
    "S035-ENA": "S035",
    "S051-BTC": "S051",
    "S053-HYPE": "S053",
    "S064-xyz:BRENTOIL": "S064",
    "Whale_0x5f94": "Whale_0x5f94",
}


def _read_db(path: Path) -> sqlite3.Connection:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("PAPER_EVIDENCE_DB_MISSING_OR_SYMLINK")
    uri = "file:" + str(path.resolve()) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=0)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _source(db: sqlite3.Connection, alias: str) -> dict:
    rows = db.execute(
        "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
        "FROM source_receipts WHERE source_id=? ORDER BY seq",
        (alias,),
    ).fetchall()
    prior = "0" * 64
    last = None
    latest_by_account: dict[str, dict] = {}
    for expected, (seq, receipt_id, raw, sha, previous, chain) in enumerate(rows, 1):
        receipt = json.loads(raw)
        if (
            expected != seq
            or receipt.get("source_id") != alias
            or digest(receipt) != sha
            or previous != prior
            or chain != digest([alias, seq, receipt_id, prior, sha])
        ):
            raise ValueError("PAPER_SOURCE_READONLY_TAPE_DIVERGENCE")
        book = receipt.get("source_book")
        if (
            not isinstance(book, dict)
            or receipt.get("payload_sha") != book.get("snapshot_sha")
            or book.get("snapshot_sha")
            != digest({k: v for k, v in book.items() if k != "snapshot_sha"})
        ):
            raise ValueError("PAPER_SOURCE_READONLY_BOOK_TAMPERED")
        account = book.get("account_id")
        if not isinstance(account, str) or len(account) != 64:
            raise ValueError("PAPER_SOURCE_READONLY_ACCOUNT_ID_INVALID")
        # A wallet tape may carry a parent plus one or more subaccounts.
        # Keep each account's latest first-known receipt separately rather
        # than falsely choosing the newest child as the parent NAV.
        latest_by_account[account] = receipt
        prior = chain
        last = receipt
    return {
        "cursor": len(rows),
        "receipt": last,
        "account_receipts": latest_by_account,
        "head_sha": prior,
    }


def _collateral(db: sqlite3.Connection, account_sha: str) -> dict:
    """Verify optional diagnostic-only SHA chain; never authorize equity."""
    try:
        rows = db.execute(
            "SELECT seq,receipt_id,payload,payload_sha,prior_sha,chain_sha "
            "FROM source_scope_receipts WHERE account_sha=? ORDER BY seq",
            (account_sha,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return {
            "cursor": 0,
            "head_sha": "0" * 64,
            "last_spot_known_at": None,
            "last_vault_known_at": None,
            "status": "SCHEMA_NOT_AVAILABLE",
        }
    prior = "0" * 64
    spot_known = vault_known = None
    mode = None
    mode_known_at = None
    mode_status = "NOT_CAPTURED"
    copy_scope = "LEGACY_PUBLIC_COLLATERAL_DIAGNOSTIC"
    vault_status = "NOT_CAPTURED"
    for expected, (seq, receipt_id, raw, sha, old, chain) in enumerate(rows, 1):
        report = json.loads(raw)
        PaperJournal._check_collateral_diagnostic(report)
        if (
            seq != expected
            or receipt_id != sha
            or digest(report) != sha
            or report.get("account_address_sha256") != account_sha
            or old != prior
            or chain != digest([account_sha, seq, sha, prior])
        ):
            raise ValueError("PAPER_COLLATERAL_READONLY_CHAIN_DIVERGENCE")
        latest = {row["scope"]: row for row in report["observations"]}
        spot_known = latest["spotClearinghouseState"]["first_known_at"]
        vault_known = latest["userVaultEquities"]["first_known_at"]
        vault_status = latest["userVaultEquities"]["status"]
        copy_scope = report.get("copy_scope") or "LEGACY_PUBLIC_COLLATERAL_DIAGNOSTIC"
        account_mode = report.get("account_abstraction")
        mode_status = (
            account_mode.get("status") if isinstance(account_mode, dict) else "NOT_CAPTURED"
        )
        mode = account_mode.get("mode") if isinstance(account_mode, dict) else None
        mode_known_at = (
            account_mode.get("first_known_at") if isinstance(account_mode, dict) else None
        )
        prior = chain
    return {
        "cursor": len(rows),
        "head_sha": prior,
        "last_spot_known_at": spot_known,
        "last_vault_known_at": vault_known,
        "vault_scope_status": vault_status,
        "copy_scope": copy_scope,
        "last_account_mode": mode,
        "last_account_mode_known_at": mode_known_at,
        "account_mode_status": mode_status,
        "status": "DIAGNOSTIC_ONLY_NOT_NAV" if rows else "NOT_CAPTURED",
    }


def _market(db: sqlite3.Connection, instrument: str) -> dict:
    rows = db.execute(
        "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
        "FROM market_quote_receipts WHERE instrument=? ORDER BY seq",
        (instrument,),
    ).fetchall()
    head = db.execute(
        "SELECT cursor,event_at,known_at,chain_sha FROM market_quote_heads WHERE instrument=?",
        (instrument,),
    ).fetchone()
    previous = "0" * 64
    last = None
    last_source = last_known = None
    for expected, (seq, qid, raw, sha, prior, chain, at, known) in enumerate(rows, 1):
        quote = json.loads(raw)
        PaperJournal._validate_market_quote(quote)
        if (
            expected != seq
            or quote.get("instrument") != instrument
            or digest(quote) != sha
            or qid != sha
            or prior != previous
            or chain != digest([instrument, seq, sha, prior])
            or quote.get("source_event_at") != at
            or quote.get("first_known_at") != known
            or (last_source and clock(at) < clock(last_source))
            or (last_known and clock(known) < clock(last_known))
        ):
            raise ValueError("PAPER_MARKET_READONLY_TAPE_DIVERGENCE")
        previous, last, last_source, last_known = chain, quote, at, known
    if (head is None and rows) or (
        head is not None and head != (len(rows), last_source, last_known, previous)
    ):
        raise ValueError("PAPER_MARKET_READONLY_HEAD_DIVERGENCE")
    return {"cursor": len(rows), "quote": last, "head_sha": previous}


def audit_live_paper_readiness(
    *,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    source_db: Path,
    market_db: Path,
    portfolio_id: str,
    as_of: str,
    max_source_age_seconds: float = 180,
    max_quote_age_seconds: float = 30,
    sizing_policy: str = "FIXED_K_NATIVE_QUANTITY",
) -> dict:
    if sizing_policy not in ("FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV"):
        raise ValueError("UNSUPPORTED_SOURCE_SIZING_POLICY")
    fixed_k = sizing_policy == "FIXED_K_NATIVE_QUANTITY"
    now = clock(as_of)
    identity = audit_frozen_member_resolution(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        portfolio_id=portfolio_id,
    )
    if identity["status"] != "PIT_IDENTITY_RESOLVED_ONLY":
        identity_blockers = ["UNSEALED_FROZEN_MEMBER_WALLET_IDS"]
    else:
        identity_blockers = []
    expected = P1 if portfolio_id == "P1" else P14
    identity_sha = {item["alias"]: item["address_sha256"] for item in identity["members"]}
    sources = []
    required_market: set[str] = set()
    with closing(_read_db(source_db)) as db:
        for member in expected:
            alias = _ALIAS[member]
            source = _source(db, alias)
            collateral = _collateral(db, identity_sha[member])
            reasons: list[str] = []
            # Collateral is always independently SHA-checked by _collateral,
            # but is diagnostic-only for signed fixed-k native quantities.
            if not fixed_k and collateral["cursor"] == 0:
                reasons.append("COLLATERAL_DIAGNOSTICS_MISSING")
            elif not fixed_k:
                mode_known = collateral["last_account_mode_known_at"]
                if (
                    collateral["account_mode_status"] != "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED"
                    or mode_known is None
                    or not 0 <= (now - clock(mode_known)).total_seconds() <= max_source_age_seconds
                ):
                    reasons.append("OFFICIAL_ACCOUNT_ABSTRACTION_MISSING_OR_STALE")
                elif collateral["last_account_mode"] in ("unifiedAccount", "portfolioMargin"):
                    reasons.append("SHARED_COLLATERAL_MODE_BLOCKS_PER_DEX_NAV_SUM")
                elif collateral["last_account_mode"] in ("default", "dexAbstraction"):
                    reasons.append("ACCOUNT_MODE_NAV_ADDIVITY_UNRESOLVED")
                # Vault investments are not follower positions or required
                # risk inputs for a perpetuals-only mirror. In unified mode,
                # the spot quote balance still supports perp margin and MUST
                # be read; the missing vault scope must not be called a feed
                # failure when it was deliberately excluded.
                required_clocks = ("last_spot_known_at",)
                if collateral.get("copy_scope") != "PERPETUALS_ONLY":
                    required_clocks += ("last_vault_known_at",)
                for field in required_clocks:
                    known = collateral[field]
                    if (
                        known is None
                        or not 0 <= (now - clock(known)).total_seconds() <= max_source_age_seconds
                    ):
                        reasons.append("COLLATERAL_SCOPE_STALE_OR_MISSING")
                reasons.append("COLLATERAL_SCOPE_NOT_ATOMIC_NAV")
            receipt = source["account_receipts"].get(identity_sha[member])
            child_receipts = {
                key: row
                for key, row in source["account_receipts"].items()
                if key != identity_sha[member]
            }
            # Parent roster is first-known metadata, not immutable. Compare
            # the observed per-account tapes to the parent's latest roster;
            # never silently discard missing/extra child exposure.
            declared_children = (
                set(receipt["source_book"].get("subaccounts", [])) if receipt else set()
            )
            observed_children = set(child_receipts)
            missing_children = declared_children - observed_children
            extra_children = observed_children - declared_children
            if not fixed_k:
                if missing_children:
                    reasons.append("DISCOVERED_SUBACCOUNT_POSITION_SCOPE_MISSING")
                if extra_children:
                    reasons.append("UNMATCHED_SUBACCOUNT_SOURCE_RECEIPT")
                if child_receipts:
                    reasons.append("NON_ATOMIC_SUBACCOUNT_OBSERVATIONS")
            if receipt is None:
                reasons.append("NO_FIRST_LOCAL_WALLET_RECEIPT")
                source_event = None
            else:
                source_event = receipt["first_known_at"]
                age = (now - clock(source_event)).total_seconds()
                if age < 0 or age > max_source_age_seconds:
                    reasons.append("SOURCE_NOT_FRESH_AS_OF")
                book = receipt["source_book"]
                if book.get("account_id") != identity_sha[member]:
                    reasons.append("SOURCE_REGISTRY_ADDRESS_IDENTITY_MISMATCH")
                if fixed_k:
                    scope = assess_selected_parent_perp_scope(
                        book, decision_at=as_of, max_age_seconds=max_source_age_seconds
                    )
                    reasons.extend(scope["reasons"])
                    # Public per-account evidence is observable, not an
                    # independent signed source execution authorization.
                    reasons.append("SELECTED_SCOPE_REAL_EXECUTION_ATTESTATION_PENDING")
                else:
                    gate = admit_source_book(book, decision_at=as_of, fill_at=as_of)
                    reasons.extend(gate.reason_codes)
                    if receipt.get("status") == "BLOCKED_INCOMPLETE_WHOLE_WALLET":
                        reasons.append("PARENT_ONLY_ACCOUNT_SCOPE")
                if isinstance(book.get("positions"), dict):
                    required_market.update(book["positions"].keys())
            # Distinct child accounts must contribute their signed exposure
            # instruments to the requested market universe, even if those
            # per-account receipts cannot be assembled into atomic NAV.
            if not fixed_k:
                for child in child_receipts.values():
                    required_market.update(child["source_book"]["positions"])
            sources.append(
                {
                    "member": member,
                    "observed_distinct_account_count": len(source["account_receipts"]),
                    "observed_subaccount_receipt_count": len(child_receipts),
                    "declared_subaccount_count": len(declared_children),
                    "matched_subaccount_receipt_count": len(declared_children & observed_children),
                    "missing_subaccount_receipt_count": len(missing_children),
                    "unmatched_subaccount_receipt_count": len(extra_children),
                    "parent_receipt_present": receipt is not None,
                    "first_local_receipts": source["cursor"],
                    "last_first_known_at": source_event,
                    "head_sha": source["head_sha"],
                    "collateral_diagnostics": collateral,
                    "admitted": not reasons and not fixed_k,
                    "selected_parent_scope_research_only": fixed_k,
                    "source_nav_required": not fixed_k,
                    "reason_codes": sorted(set(reasons)),
                }
            )
    market = []
    with closing(_read_db(market_db)) as db:
        for native in sorted(required_market):
            quote = _market(db, native)
            reasons: list[str] = []
            row = quote["quote"]
            if row is None:
                reasons.append("MISSING_FOLLOWER_MARKET_QUOTE")
                known = None
            else:
                known = row["first_known_at"]
                age = (now - clock(known)).total_seconds()
                if age < 0 or age > max_quote_age_seconds:
                    reasons.append("MARKET_QUOTE_STALE_AS_OF")
                if row.get("session_trust") == "UNKNOWN_HIP3_SESSION":
                    reasons.append("HIP3_TRADING_SESSION_NOT_ATTESTED")
                if row.get("volume_status") == "UNKNOWN_BOOK_DEPTH_NOT_TRADED_VOLUME":
                    reasons.append("EXECUTABLE_VOLUME_COVERAGE_UNKNOWN")
            market.append(
                {
                    "instrument": native,
                    "quote_cursor": quote["cursor"],
                    "last_known_at": known,
                    "reason_codes": sorted(set(reasons)),
                }
            )
    reasons = (
        identity_blockers
        + [reason for item in sources for reason in item["reason_codes"]]
        + [reason for item in market for reason in item["reason_codes"]]
    )
    reasons.append("PROTECTED_PAPER_WORKER_NOT_ATTESTED")
    if not fixed_k:
        reasons.append("INDEPENDENT_PARENT_SUBACCOUNT_NAV_NOT_RECONCILED")
    return {
        "schema": "paper_live_readiness_v1",
        "portfolio": portfolio_id,
        "as_of": as_of,
        "status": "BLOCKED_NO_TRADE",
        "reason_codes": sorted(set(reasons)),
        "registry": {
            "frozen_version": identity["registry_version"],
            "member_count": identity["member_count"],
            "unresolved_aliases": identity["unresolved_aliases"],
            "registry_mutated": False,
        },
        "source": sources,
        "market": market,
        "needed_native_market_count": len(required_market),
        "source_wallet_equity_attested": False,
        "source_nav_required": not fixed_k,
        "sizing_policy": sizing_policy,
        "selected_account_scope": "PARENT_PERPS_ONLY" if fixed_k else "WHOLE_WALLET",
        "trade_volume_complete": False,
        "paper_observed": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only P1/P14 live source/market readiness")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--portfolio", choices=("P1", "P14"), required=True)
    parser.add_argument("--as-of", default=datetime.now(UTC).isoformat())
    parser.add_argument(
        "--sizing-policy",
        choices=("FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV"),
        default="FIXED_K_NATIVE_QUANTITY",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            audit_live_paper_readiness(
                registry_db=args.registry,
                primary_dir=args.primary_dir,
                secondary_dir=args.secondary_dir,
                source_db=args.source_db,
                market_db=args.market_db,
                portfolio_id=args.portfolio,
                as_of=args.as_of,
                sizing_policy=args.sizing_policy,
            ),
            indent=2,
            sort_keys=True,
        )
    )
