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
        prior = chain
        last = receipt
    return {"cursor": len(rows), "receipt": last, "head_sha": prior}


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
) -> dict:
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
            reasons: list[str] = []
            receipt = source["receipt"]
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
                gate = admit_source_book(book, decision_at=as_of, fill_at=as_of)
                reasons.extend(gate.reason_codes)
                required_market.update(book["positions"].keys())
                # A strictly parent-only snapshot cannot create whole-wallet NAV.
                if receipt.get("status") == "BLOCKED_INCOMPLETE_WHOLE_WALLET":
                    reasons.append("PARENT_ONLY_ACCOUNT_SCOPE")
            sources.append(
                {
                    "member": member,
                    "first_local_receipts": source["cursor"],
                    "last_first_known_at": source_event,
                    "head_sha": source["head_sha"],
                    "admitted": not reasons,
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
    reasons.extend(
        [
            "PROTECTED_PAPER_WORKER_NOT_ATTESTED",
            "INDEPENDENT_PARENT_SUBACCOUNT_NAV_NOT_RECONCILED",
        ]
    )
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
            ),
            indent=2,
            sort_keys=True,
        )
    )
