"""Versioned SQLite release approvals and immutable Ed25519 portfolio manifests.

The namespace extension is installed only by explicit store_policy, never by a
read or startup. It leaves registry schema v8 and all existing authority rows
unchanged. No broker library or broker credential is used.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import wallet_registry as registry
from .production_export import export_metadata


def canonical(value: object) -> bytes:
    def check(item):
        if isinstance(item, dict):
            if not all(isinstance(k, str) for k in item):
                raise ValueError("CANONICAL_KEYS")
            for v in item.values():
                check(v)
        elif isinstance(item, (list, tuple)):
            for v in item:
                check(v)
        elif type(item) not in (str, int, bool, type(None)):
            raise ValueError("CANONICAL_FLOAT_OR_TYPE")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def sign(payload: dict, key: Ed25519PrivateKey, authority: str) -> dict:
    message = b"prop-production/evidence/v1\x00" + authority.encode() + b"\x00" + canonical(payload)
    return {"payload": json.loads(canonical(payload)), "authority": authority, "sha256": digest(payload),
            "signature": base64.b64encode(key.sign(message)).decode()}


def verify(envelope: dict, key: Ed25519PublicKey, authority: str) -> dict:
    if (set(envelope) != {"payload", "authority", "sha256", "signature"}
            or envelope["authority"] != authority or envelope["sha256"] != digest(envelope["payload"])):
        raise ValueError("MANIFEST_SIGNATURE_OR_DIGEST")
    message = b"prop-production/evidence/v1\x00" + authority.encode() + b"\x00" + canonical(envelope["payload"])
    try:
        key.verify(base64.b64decode(envelope["signature"], validate=True), message)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("MANIFEST_SIGNATURE") from exc
    return json.loads(canonical(envelope["payload"]))


def _positive_decimal(value: object, reason: str) -> Decimal:
    try:
        if not isinstance(value, str):
            raise ValueError(reason)
        parsed = Decimal(value)
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError(reason)
        return parsed
    except ArithmeticError as exc:
        raise ValueError(reason) from exc


def store_policy(db: Path, portfolio_id: str, metadata: dict, envelope: dict,
                 reviewer: Ed25519PublicKey) -> str:
    """Explicit immutable metadata mutation; never called against the live DB automatically."""
    policy = verify(envelope, reviewer, "research-release-policy")
    if policy["metadata_export_sha256"] != metadata["export_sha256"]:
        raise ValueError("APPROVAL_METADATA_MISMATCH")
    if type(policy["generation"]) is not int or policy["generation"] < 1:
        raise ValueError("POLICY_GENERATION")
    from datetime import datetime, timezone
    asof = datetime.fromtimestamp(metadata["asof_ms"] / 1000, timezone.utc).isoformat()
    with closing(registry.connect(db, True)) as con:
        con.execute("BEGIN IMMEDIATE")
        current = export_metadata(db, portfolio_id, asof, version=metadata["version"],
                                  sizing_policy=metadata["sizing_policy"], _connection=con)
        if current["export_sha256"] != metadata["export_sha256"]:
            raise ValueError("REGISTRY_CHANGED_SINCE_APPROVAL")
        con.execute(
            "CREATE TABLE IF NOT EXISTS production_portfolio_policies ("
            "portfolio_id TEXT NOT NULL,version INTEGER NOT NULL,generation INTEGER NOT NULL,"
            "known_at_ms INTEGER NOT NULL,sha TEXT NOT NULL,envelope TEXT NOT NULL,"
            "PRIMARY KEY(portfolio_id,version,generation),"
            "FOREIGN KEY(portfolio_id,version) REFERENCES portfolio_versions(portfolio_id,version))"
        )
        con.execute("CREATE TRIGGER IF NOT EXISTS production_policy_no_update "
                    "BEFORE UPDATE ON production_portfolio_policies BEGIN "
                    "SELECT RAISE(ABORT,'IMMUTABLE_PRODUCTION_POLICY'); END")
        con.execute("CREATE TRIGGER IF NOT EXISTS production_policy_no_delete "
                    "BEFORE DELETE ON production_portfolio_policies BEGIN "
                    "SELECT RAISE(ABORT,'IMMUTABLE_PRODUCTION_POLICY'); END")
        rows = con.execute(
            "SELECT generation,sha FROM production_portfolio_policies "
            "WHERE portfolio_id=? AND version=? ORDER BY generation DESC",
            (portfolio_id, metadata["version"]),
        ).fetchall()
        policy_sha = digest(policy)
        if rows and policy["generation"] <= rows[0][0]:
            if (policy["generation"], policy_sha) in rows:
                return policy_sha
            raise ValueError("POLICY_ROLLBACK_OR_EQUIVOCATION")
        con.execute("INSERT INTO production_portfolio_policies VALUES(?,?,?,?,?,?)",
                    (portfolio_id, metadata["version"], policy["generation"],
                     policy["created_at_ms"], policy_sha, canonical(envelope).decode()))
        con.commit()
        return policy_sha


def build_manifest(*, db: Path, portfolio_id: str, asof: str, reviewer: Ed25519PublicKey,
                   source_observer: Ed25519PublicKey, release_signer: Ed25519PrivateKey,
                   now_ms: int) -> dict:
    with closing(registry.connect(db, False)) as con:
        con.execute("BEGIN")
        metadata = export_metadata(db, portfolio_id, asof, _connection=con)
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                           "AND name='production_portfolio_policies'").fetchone():
            raise ValueError("SEALED_PRODUCTION_POLICY_MISSING")
        row = con.execute(
            "SELECT sha,envelope FROM production_portfolio_policies "
            "WHERE portfolio_id=? AND version=? AND known_at_ms<=? ORDER BY generation DESC LIMIT 1",
            (portfolio_id, metadata["version"], now_ms),
        ).fetchone()
        if row is None:
            raise ValueError("SEALED_PRODUCTION_POLICY_MISSING")
        policy = verify(json.loads(row[1]), reviewer, "research-release-policy")
        if policy["metadata_export_sha256"] != metadata["export_sha256"]:
            # Existing approvals bind the original legacy export. Recompute it
            # from the same snapshot; never rewrite or relax a signed digest.
            metadata = export_metadata(db, portfolio_id, asof,
                                       sizing_policy="ALLOCATION_OVER_LIVE_NAV", _connection=con)
    if row[0] != digest(policy) or policy["metadata_export_sha256"] != metadata["export_sha256"]:
        raise ValueError("POLICY_OR_INVENTORY_DRIFT")
    required = {"schema", "metadata_export_sha256", "generation", "created_at_ms", "expires_at_ms",
                "account_binding", "risk_policy_sha", "rulebook_sha", "source_mode",
                "members", "source_attestations"}
    if set(policy) != required or policy["schema"] != "production_release_policy_v1":
        raise ValueError("POLICY_SCHEMA")
    if (type(now_ms) is not int or not metadata["selection_known_at_ms"] <= policy["created_at_ms"]
            <= now_ms < policy["expires_at_ms"] or policy["source_mode"] not in {"SYNTHETIC", "PROSPECTIVE"}):
        raise ValueError("POLICY_CLOCK_OR_MODE")
    selected = {m["pod_id"]: m for m in metadata["members"]}
    if set(selected) != {m["pod_id"] for m in policy["members"]} or len(selected) != len(policy["members"]):
        raise ValueError("SEALED_MEMBERSHIP_DRIFT")
    proofs = {}
    for envelope in policy["source_attestations"]:
        proof = verify(envelope, source_observer, "source-observer")
        identity = proof["source_identity"]
        if identity in proofs:
            raise ValueError("DUPLICATE_SOURCE_ATTESTATION")
        proofs[identity] = proof
    for member in policy["members"]:
        expected = selected[member["pod_id"]]
        if (not expected["source_identity"] or
                any(member[k] != expected[k] for k in ("source_identity", "identity_known_at_ms"))):
            raise ValueError("MEMBER_IDENTITY_UNKNOWN_AT_SEAL")
        proof = proofs.get(member["source_identity"])
        if (not proof or proof["schema"] != "source_scope_attestation_v1"
                or proof["scope_complete"] is not True or proof["book_complete"] is not True
                or proof["account_scope"] != member["account_scope"]
                or member["source_identity"] not in member["account_scope"]
                or proof["source_mode"] != policy["source_mode"]
                or not 0 <= policy["created_at_ms"] - proof["known_at_ms"] <= 600000):
            raise ValueError("SOURCE_SCOPE_UNVERIFIED")
        _positive_decimal(member["allocation"], "ALLOCATION_INVALID")
        fields = {"pod_id", "source_identity", "identity_known_at_ms", "account_scope",
                  "allocation", "sizing_policy", "allowed_markets"}
        if member["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY":
            fields.add("k")
            if _positive_decimal(member.get("k"), "FIXED_K_INVALID") > 10:
                raise ValueError("FIXED_K_INVALID")
        elif member["sizing_policy"] == "ALLOCATION_OVER_LIVE_NAV":
            _positive_decimal(proof.get("nav"), "SOURCE_NAV_INVALID")
        else:
            raise ValueError("SIZING_POLICY")
        if (set(member) != fields or not member["allowed_markets"]
                or len(set(member["account_scope"])) != len(member["account_scope"])):
            raise ValueError("SIZING_OR_SCOPE")
    for name in ("risk_policy_sha", "rulebook_sha"):
        if len(policy[name]) != 64 or any(c not in "0123456789abcdef" for c in policy[name]):
            raise ValueError("APPROVED_POLICY_DIGEST")
    payload = {
        "schema": "portfolio_release_v1", "generation": policy["generation"],
        "account_binding": policy["account_binding"], "created_at_ms": policy["created_at_ms"],
        "expires_at_ms": policy["expires_at_ms"],
        "selection_known_at_ms": metadata["selection_known_at_ms"],
        "members": policy["members"], "definition_sha": digest(policy["members"]),
        "inventory_sha": digest({"registry": metadata["registry_inventory_sha256"],
                                 "approved_policy": digest(policy)}),
        "decision_sha": metadata["decision_sha256"], "research_commit": metadata["research_commit"],
        "risk_policy_sha": policy["risk_policy_sha"], "rulebook_sha": policy["rulebook_sha"],
        "batch_seconds": 300, "source_mode": policy["source_mode"],
    }
    payload["source_sha"] = digest({k: payload[k] for k in
        ("research_commit", "decision_sha", "inventory_sha", "definition_sha", "selection_known_at_ms")})
    return sign(payload, release_signer, "approver")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--portfolio", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--now-ms", required=True, type=int)
    parser.add_argument("--reviewer-public", required=True, type=Path)
    parser.add_argument("--source-public", required=True, type=Path)
    parser.add_argument("--release-signing-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if (args.release_signing_key.is_symlink() or args.release_signing_key.stat().st_mode & 0o077
                or args.output.exists() or args.output.parent.stat().st_mode & 0o077):
            raise ValueError("PRIVATE_KEY_OR_OUTPUT_PERMISSIONS")
        manifest = build_manifest(
            db=args.db, portfolio_id=args.portfolio, asof=args.asof, now_ms=args.now_ms,
            reviewer=Ed25519PublicKey.from_public_bytes(args.reviewer_public.read_bytes()),
            source_observer=Ed25519PublicKey.from_public_bytes(args.source_public.read_bytes()),
            release_signer=Ed25519PrivateKey.from_private_bytes(args.release_signing_key.read_bytes()))
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"state": "SIGNED_METADATA_RELEASE", "release_sha": manifest["sha256"],
                          "trading_authorized": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print('{"state":"BLOCKED","reason":"RELEASE_EVIDENCE_OR_PERMISSION","trading_authorized":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
