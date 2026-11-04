"""Owner-signed, append-only future *research* portfolio selections.

There is deliberately no broker, live-risk, or paper-admission interface here.
A valid signature only proves possession of a reviewer/operator key; selection
does not imply scientific qualification, authorization, or worker activity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "copytrade_signed_research_selection_v1"
SCOPE = "NEW_FORWARD_PAPER_RESEARCH"
ID = re.compile(r"[a-z][a-z0-9._-]{1,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_ROLES = frozenset(
    (
        "PRIMARY_FORWARD_PAPER_RESEARCH",
        "THREE_POD_FORWARD_PAPER_CHALLENGER",
        "OPTIONAL_DEFENSIVE_RESEARCH_RESERVE",
        "INCUMBENT_HISTORICAL_BASELINE_NO_NEW_PROMOTION",
        "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER",
        "SEPARATE_PHASE5_COMPARISON_NOT_SELECTED",
        "RESEARCH_CANDIDATE",
        "RESEARCH_CONTROL",
    )
)
DDL = """
CREATE TABLE IF NOT EXISTS research_selection_proofs(
    source_sha256 TEXT PRIMARY KEY,
    source_json TEXT NOT NULL,
    signature_hex TEXT NOT NULL,
    public_key_hex TEXT NOT NULL,
    trusted_key_sha256 TEXT NOT NULL,
    first_known_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS guard_research_selection_proof_update
BEFORE UPDATE ON research_selection_proofs
BEGIN SELECT RAISE(ABORT,'immutable signed research selection'); END;
CREATE TRIGGER IF NOT EXISTS guard_research_selection_proof_delete
BEFORE DELETE ON research_selection_proofs
BEGIN SELECT RAISE(ABORT,'immutable signed research selection'); END;
"""
# Independent signed selection is its own source of evidence. No malformed
# foreign key to the composite-key evidence_versions table is permitted.


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate signed catalog JSON key")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict:
    if len(raw) > 65536:
        raise ValueError("oversized signed research manifest")
    doc = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(doc, dict) or set(doc) != {
        "schema",
        "scope",
        "definitions",
        "selections",
        "trading_authorized",
    }:
        raise ValueError("invalid signed research manifest keys")
    if (
        doc["schema"] != SCHEMA
        or doc["scope"] != SCOPE
        or doc["trading_authorized"] is not False
        or type(doc["definitions"]) is not dict
        or type(doc["selections"]) is not list
        or not (1 <= len(doc["definitions"]) <= 30)
        or not (1 <= len(doc["selections"]) <= 30)
    ):
        raise ValueError("invalid signed research-only manifest")
    for pid, item in doc["definitions"].items():
        if not isinstance(pid, str) or not ID.fullmatch(pid):
            raise ValueError("portfolio identifier requires a namespace")
        if type(item) is not dict or set(item) != {"members"}:
            raise ValueError("unrecognized signed portfolio definition")
        names = item["members"]
        if (
            type(names) is not list
            or not (1 <= len(names) <= 20)
            or any(type(a) is not str or not ALIAS.fullmatch(a) for a in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("invalid signed portfolio members")
    refs = set()
    active_ranks = set()
    for choice in doc["selections"]:
        if type(choice) is not dict or set(choice) != {"portfolio_id", "role", "priority"}:
            raise ValueError("invalid signed selection fields")
        pid, role, rank = choice["portfolio_id"], choice["role"], choice["priority"]
        if pid in refs or pid not in doc["definitions"] or role not in ALLOWED_ROLES:
            raise ValueError("duplicate or unknown signed portfolio selection")
        if rank is not None and (type(rank) is not int or not 1 <= rank <= 30):
            raise ValueError("invalid signed priority")
        if rank is not None and rank in active_ranks:
            raise ValueError("repeated signed selection priority")
        if rank is not None:
            active_ranks.add(rank)
        refs.add(pid)
    if refs != set(doc["definitions"]):
        raise ValueError("unsigned or unselected research definition")
    if active_ranks != set(range(1, len(active_ranks) + 1)):
        raise ValueError("noncontiguous signed research priorities")
    return doc


def _read_private(path: Path, limit: int) -> bytes:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("linked private signed evidence")
    if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise PermissionError("signed evidence must reside in a private 0700 directory")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_size > limit
        ):
            raise PermissionError("signed evidence must be owner-private 0600")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            return stream.read(limit + 1)
    finally:
        if fd >= 0:
            os.close(fd)


def inspect(
    source_path: Path,
    signature_path: Path,
    public_key_path: Path,
    *,
    expected_public_key_sha256: str,
    first_known_at: str,
) -> dict:
    """Validate independent operator inputs without touching SQLite."""
    if not HEX64.fullmatch(expected_public_key_sha256):
        raise ValueError("untrusted key fingerprint")
    observed = datetime.fromisoformat(first_known_at)
    current = datetime.now(timezone.utc)
    if observed.tzinfo is None or observed > current or observed < current - timedelta(minutes=3):
        raise ValueError("invalid local first-known clock")
    raw = _read_private(source_path, 65536)
    signature_text = _read_private(signature_path, 128).strip().decode("ascii")
    key = _read_private(public_key_path, 32)
    if len(key) != 32 or sha256(key).hexdigest() != expected_public_key_sha256:
        raise ValueError("reviewed public key fingerprint mismatch")
    if len(signature_text) != 128:
        raise ValueError("invalid signature byte count")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(bytes.fromhex(signature_text), raw)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("invalid signed research selection signature") from exc
    document = _parse(raw)
    return {
        "source_sha256": sha256(raw).hexdigest(),
        "source_json": raw.decode("utf-8"),
        "signature_hex": signature_text,
        "public_key_hex": key.hex(),
        "trusted_key_sha256": expected_public_key_sha256,
        "first_known_at": first_known_at,
        "document": document,
    }


def verified_record(row: tuple) -> dict:
    """Verify stored signature, source digest and research-only schema on every read."""
    source_sha, raw, signature, key_hex, key_sha, known_at = row
    raw_bytes = raw.encode()
    if sha256(raw_bytes).hexdigest() != source_sha:
        raise ValueError("signed selection stored source SHA drift")
    key = bytes.fromhex(key_hex)
    if len(key) != 32 or sha256(key).hexdigest() != key_sha:
        raise ValueError("signed selection trusted key fingerprint drift")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(bytes.fromhex(signature), raw_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("signed selection stored signature drift") from exc
    return {
        "source_sha256": source_sha,
        "source_json": raw,
        "signature_hex": signature,
        "public_key_hex": key_hex,
        "trusted_key_sha256": key_sha,
        "first_known_at": known_at,
        "document": _parse(raw_bytes),
    }


def load(con: sqlite3.Connection, source_sha256: str) -> dict:
    row = con.execute(
        "SELECT source_sha256,source_json,signature_hex,public_key_hex,"
        "trusted_key_sha256,first_known_at FROM research_selection_proofs "
        "WHERE source_sha256=?",
        (source_sha256,),
    ).fetchone()
    if row is None:
        raise ValueError("unverified research selection provenance")
    return verified_record(row)


def definition(record: dict, pid: str) -> tuple[dict, str]:
    from .wallet_registry_catalog import _json_sha

    if pid not in record["document"]["definitions"]:
        raise ValueError("signed portfolio absent from immutable source")
    payload = {
        "schema": "wallet_portfolio_definition_signed_v1",
        "portfolio_id": pid,
        "aliases": record["document"]["definitions"][pid]["members"],
        "source_commit": "SIGNED:" + record["source_sha256"],
        "source_doc_sha256": record["source_sha256"],
        "selection_known_at": record["first_known_at"],
        "status": "RESEARCH_SELECTION_ONLY",
        "sizing_contract": "NON_EXECUTABLE_SIGNED_RESEARCH",
        "source_identity_proven": False,
        "order_route": "NONE",
    }
    return payload, _json_sha(payload)


def store(con: sqlite3.Connection, record: dict) -> dict:
    """One transaction called beneath the pre-existing single-writer private lock."""
    record = verified_record(
        tuple(
            record[k]
            for k in (
                "source_sha256",
                "source_json",
                "signature_hex",
                "public_key_hex",
                "trusted_key_sha256",
                "first_known_at",
            )
        )
    )
    old = con.execute(
        "SELECT source_sha256,source_json,signature_hex,public_key_hex,"
        "trusted_key_sha256,first_known_at FROM research_selection_proofs "
        "WHERE source_sha256=?",
        (record["source_sha256"],),
    ).fetchone()
    if old is not None:
        previous = verified_record(old)
        if any(
            previous[key] != record[key]
            for key in (
                "source_sha256",
                "source_json",
                "signature_hex",
                "public_key_hex",
                "trusted_key_sha256",
            )
        ):
            raise ValueError("signed manifest import differs from immutable source")
        # Reimport never moves the original first-known boundary.
        return {"source_sha256": record["source_sha256"], "unchanged": True}
    con.execute(
        "INSERT OR IGNORE INTO schema_migrations VALUES(8,?)",
        (record["first_known_at"],),
    )
    con.execute(
        "INSERT INTO research_selection_proofs VALUES(?,?,?,?,?,?)",
        tuple(
            record[k]
            for k in (
                "source_sha256",
                "source_json",
                "signature_hex",
                "public_key_hex",
                "trusted_key_sha256",
                "first_known_at",
            )
        ),
    )
    for pid in sorted(record["document"]["definitions"]):
        payload, seal = definition(record, pid)
        previous = con.execute(
            "SELECT MAX(version) FROM portfolio_versions WHERE portfolio_id=?", (pid,)
        ).fetchone()[0]
        version = (previous or 0) + 1
        con.execute(
            "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
            (
                pid,
                version,
                "RESEARCH_SELECTION_ONLY",
                "SIGNED:" + record["source_sha256"],
                record["first_known_at"],
                "NON_EXECUTABLE_SIGNED_RESEARCH",
            ),
        )
        resolved_ids: set[int] = set()
        members = []
        for alias in payload["aliases"]:
            existing = con.execute(
                "SELECT DISTINCT wallet_id FROM wallet_aliases WHERE alias=? "
                "AND known_at<=? LIMIT 2",
                (alias, record["first_known_at"]),
            ).fetchall()
            if len(existing) > 1:
                raise ValueError("signed portfolio alias identity conflict")
            ident = existing[0][0] if existing else None
            if ident is not None:
                if ident in resolved_ids:
                    raise ValueError("signed portfolio contains duplicate canonical wallet")
                resolved_ids.add(ident)
            members.append((pid, version, alias, ident))
        con.executemany("INSERT INTO portfolio_memberships VALUES(?,?,?,?)", members)
        con.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?,?,?)",
            (
                pid,
                version,
                seal,
                record["source_sha256"],
                "SIGNED:" + record["source_sha256"],
                record["first_known_at"],
            ),
        )
        selected = next(c for c in record["document"]["selections"] if c["portfolio_id"] == pid)
        con.execute(
            "INSERT INTO research_selections VALUES(?,?,?,?,?,?,?)",
            (
                record["source_sha256"],
                SCOPE,
                pid,
                version,
                selected["role"],
                selected["priority"],
                record["first_known_at"],
            ),
        )
    return {"source_sha256": record["source_sha256"], "unchanged": False}
