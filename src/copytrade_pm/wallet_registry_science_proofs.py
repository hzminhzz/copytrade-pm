"""Independent negative scientific-evidence import; never a qualification producer.

The existing independent PM-02 receipt/outcome reviewer remains authoritative.
This registry accepts a cryptographically verifiable negative/blocked review
only when its evidence file, policy digest, wallet identity, signer and clocks
are explicit. No positive scientific or trading authorization is supported.

A signature proves possession of the public-key counterpart, *not* that its
holder or purported economic measurements have been independently audited.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "wallet_registry_independent_negative_v1"
VERDICTS = frozenset(("UNQUALIFIED", "BLOCKED", "NOT_ESTABLISHED"))
HEX = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
FIELDS = frozenset(
    (
        "schema",
        "decision_id",
        "wallet",
        "policy_version",
        "policy_sha256",
        "evidence_sha256",
        "verdict",
        "decision_at",
        "reviewed_at",
        "reviewer_id",
        "reviewer_role",
        "scientifically_qualified",
        "trading_authorized",
        "scope",
    )
)
DDL = """
CREATE TABLE IF NOT EXISTS qualification_proofs(
    decision_id TEXT PRIMARY KEY,
    attestation_json TEXT NOT NULL,
    attestation_sha256 TEXT NOT NULL,
    reviewer_public_key_sha256 TEXT NOT NULL,
    signature_hex TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES qualification_decisions(decision_id)
);
CREATE TRIGGER IF NOT EXISTS qualification_proof_no_update
BEFORE UPDATE ON qualification_proofs
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_INDEPENDENT_NEGATIVE_PROOF');
END;
CREATE TRIGGER IF NOT EXISTS qualification_proof_no_delete
BEFORE DELETE ON qualification_proofs
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_INDEPENDENT_NEGATIVE_PROOF');
END;
CREATE TRIGGER IF NOT EXISTS qualification_proof_decision_no_update
BEFORE UPDATE ON qualification_decisions
WHEN EXISTS (
    SELECT 1 FROM qualification_proofs p WHERE p.decision_id=OLD.decision_id
)
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_INDEPENDENT_NEGATIVE_DECISION');
END;
CREATE TRIGGER IF NOT EXISTS qualification_proof_decision_no_delete
BEFORE DELETE ON qualification_decisions
WHEN EXISTS (
    SELECT 1 FROM qualification_proofs p WHERE p.decision_id=OLD.decision_id
)
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_INDEPENDENT_NEGATIVE_DECISION');
END;
"""


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate attestation JSON key")
        result[key] = value
    return result


def _safe_file(path: Path, *, max_bytes: int) -> bytes:
    """Read an owner-private regular file once, without symlink-following TOCTOU."""
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("insecure private evidence directory")
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise ValueError("evidence directory must be private 0700")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise ValueError("unsigned or linked source file") from exc
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode):
            raise ValueError("unsigned or linked source file")
        if stat.S_IMODE(actual.st_mode) != 0o600 or actual.st_uid != os.getuid():
            raise ValueError("evidence files must be private 0600")
        if actual.st_size > max_bytes:
            raise ValueError("oversized independent evidence file")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("oversized independent evidence file")
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing independent knowledge clock")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("scientific evidence clock lacks UTC offset")
    return result.astimezone(timezone.utc)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _record(*, attestation: dict, signature_hex: str, public_key: bytes, now: datetime) -> dict:
    if set(attestation) != FIELDS or attestation.get("schema") != SCHEMA:
        raise ValueError("unsupported signed negative evidence schema")
    if attestation["verdict"] not in VERDICTS:
        raise ValueError("no positive scientific verdicts without independent signoff")
    if (
        attestation.get("trading_authorized") is not False
        or attestation.get("scientifically_qualified") is not False
        or attestation.get("scope") != "RESEARCH_ONLY"
        or attestation.get("reviewer_role") != "INDEPENDENT_REVIEWER"
    ):
        raise ValueError("research negative cannot authorize or qualify")
    for key in ("decision_id", "policy_version", "reviewer_id"):
        value = attestation[key]
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            raise ValueError("invalid attestation identifier")
    for key in ("evidence_sha256", "policy_sha256"):
        value = attestation[key]
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError("invalid evidence or policy digest")
    decision, reviewed = _utc(attestation["decision_at"]), _utc(attestation["reviewed_at"])
    if not decision <= reviewed <= now:
        raise ValueError("scientific decision clocks are unverified or future-dated")
    # An imported attestation never invents its own first-known time. It is
    # indexed at the local import clock, not backdated to the review timestamp.
    if len(public_key) != 32 or not isinstance(signature_hex, str) or len(signature_hex) != 128:
        raise ValueError("invalid independent reviewer key/signature")
    try:
        signature = bytes.fromhex(signature_hex)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _canonical(attestation))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("independent reviewer signature verification failed") from exc
    return {
        "decision_id": attestation["decision_id"],
        "wallet": attestation["wallet"],
        "policy_version": attestation["policy_version"],
        "policy_sha256": attestation["policy_sha256"],
        "evidence_sha256": attestation["evidence_sha256"],
        "verdict": attestation["verdict"],
        "attestation_json": _canonical(attestation).decode(),
        "attestation_sha256": sha256(_canonical(attestation)).hexdigest(),
        "reviewer_public_key_sha256": sha256(public_key).hexdigest(),
        "signature_hex": signature_hex,
        "known_at": now.isoformat(),
        "scientifically_qualified": False,
        "trading_authorized": False,
        "reviewer_independence": "NOT_ESTABLISHED_BY_SIGNATURE_ALONE",
    }


def inspect_negative(
    attestation_file: Path,
    evidence_file: Path,
    public_key_file: Path,
    *,
    now: datetime | None = None,
) -> dict:
    """Read all three owner-private sources; never sign or backdate a verdict."""
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("import clock must have an offset")
    checked_at = checked_at.astimezone(timezone.utc)
    raw = _safe_file(attestation_file, max_bytes=65_536)
    envelope = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(envelope, dict) or set(envelope) != {"attestation", "signature_hex"}:
        raise ValueError("invalid signed reviewer envelope")
    attestation = envelope["attestation"]
    if not isinstance(attestation, dict):
        raise ValueError("invalid signed reviewer attestation")
    key = _safe_file(public_key_file, max_bytes=32)
    result = _record(
        attestation=attestation,
        signature_hex=envelope["signature_hex"],
        public_key=key,
        now=checked_at,
    )
    if (
        sha256(_safe_file(evidence_file, max_bytes=4 * 1024 * 1024)).hexdigest()
        != result["evidence_sha256"]
    ):
        raise ValueError("independent source evidence SHA mismatch")
    # Require a native Hyperliquid address, without importing wallet identity
    # from private aliases or creating a new wallet behind the registry.
    from .wallet_registry import normalize

    result["wallet"] = normalize(result["wallet"])
    result["_auditor_public_key"] = key
    result["_evidence_file"] = evidence_file
    return result


def store_negative(con: sqlite3.Connection, record: dict) -> dict:
    """Store an immutable signed *negative* result in caller's SQLite transaction.

    The caller must verify the private files again under the registry writer
    lock immediately before this call. Never import a positive verdict here.
    """
    if record.get("verdict") not in VERDICTS:
        raise ValueError("unsupported scientific promotion")
    # A direct library caller cannot bypass the signed-review verification
    # with a forged record dictionary.
    try:
        attestation = json.loads(record["attestation_json"], object_pairs_hook=_object)
        key = record["_auditor_public_key"]
        evidence = record["_evidence_file"]
        imported_at = datetime.now(timezone.utc)
        checked = _record(
            attestation=attestation,
            signature_hex=record["signature_hex"],
            public_key=key,
            now=imported_at,
        )
        if sha256(_safe_file(evidence, max_bytes=4 * 1024 * 1024)).hexdigest() != checked[
            "evidence_sha256"
        ] or any(
            record.get(name) != checked[name]
            for name in (
                "decision_id",
                "wallet",
                "policy_version",
                "policy_sha256",
                "evidence_sha256",
                "verdict",
                "attestation_json",
                "attestation_sha256",
                "reviewer_public_key_sha256",
                "signature_hex",
                "scientifically_qualified",
                "trading_authorized",
            )
        ):
            raise ValueError("independent negative proof changed before commit")
    except (KeyError, TypeError, InvalidSignature, ValueError) as exc:
        raise ValueError("unsigned or changed independent review") from exc
    row = con.execute(
        "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' AND network='mainnet' "
        "AND address=?",
        (record["wallet"],),
    ).fetchone()
    if row is None:
        raise ValueError("audited wallet not in canonical private registry")
    wallet_id = row[0]
    existing = con.execute(
        "SELECT q.wallet_id,q.policy_version,q.evidence_sha256,q.verdict,"
        "p.attestation_sha256,p.reviewer_public_key_sha256,p.signature_hex,p.policy_sha256,"
        "q.known_at "
        "FROM qualification_decisions q JOIN qualification_proofs p USING(decision_id) "
        "WHERE q.decision_id=?",
        (record["decision_id"],),
    ).fetchone()
    values = (
        wallet_id,
        record["policy_version"],
        record["evidence_sha256"],
        record["verdict"],
        record["attestation_sha256"],
        record["reviewer_public_key_sha256"],
        record["signature_hex"],
        record["policy_sha256"],
    )
    if existing is not None:
        if existing[:8] != values:
            raise ValueError("conflicting immutable independent negative decision")
        return {
            "stored": False,
            "decision_sha256": record["attestation_sha256"],
            "known_at": existing[8],
        }
    if con.execute(
        "SELECT 1 FROM qualification_decisions WHERE decision_id=?",
        (record["decision_id"],),
    ).fetchone():
        raise ValueError("decision ID already exists without independent proof")
    last = con.execute(
        "SELECT MAX(known_at) FROM qualification_decisions WHERE wallet_id=? AND policy_version=?",
        (wallet_id, record["policy_version"]),
    ).fetchone()[0]
    # Use the actual transaction-side local clock. A direct library caller
    # cannot backdate a decision by modifying a verified record dictionary.
    known_at = imported_at.isoformat()
    if last is not None and _utc(last) > imported_at:
        raise ValueError("scientific review known-at clock moved backwards")
    con.execute(
        "INSERT INTO qualification_decisions VALUES(?,?,?,?,?,?)",
        (
            record["decision_id"],
            wallet_id,
            record["policy_version"],
            record["evidence_sha256"],
            known_at,
            record["verdict"],
        ),
    )
    con.execute(
        "INSERT INTO qualification_proofs VALUES(?,?,?,?,?,?,?,?)",
        (
            record["decision_id"],
            record["attestation_json"],
            record["attestation_sha256"],
            record["reviewer_public_key_sha256"],
            record["signature_hex"],
            record["policy_sha256"],
            record["evidence_sha256"],
            known_at,
        ),
    )
    return {
        "stored": True,
        "decision_sha256": record["attestation_sha256"],
        "known_at": known_at,
    }


def public_result(record: dict) -> dict:
    """Only SHA fingerprints and non-positive verdicts leave private DB context."""
    return {
        "schema": SCHEMA,
        "attestation_sha256": record["attestation_sha256"],
        "reviewer_key_sha256": record["reviewer_public_key_sha256"],
        "verdict": record["verdict"],
        "policy_version": record["policy_version"],
        "known_at": record["known_at"],
        "scientifically_qualified": False,
        "trading_authorized": False,
        "signature_verified": True,
        "evidence_sha256_verified": True,
        "independence": "NOT_ESTABLISHED_BY_SIGNATURE_ALONE",
    }
