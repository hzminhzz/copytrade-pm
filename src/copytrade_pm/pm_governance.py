"""Explicit evidence-bound independent-review check for protected research decisions.

No judge calls, registry writes, scientific promotion, live orders or authorization.
A verified review is an input to a separately controlled owner decision, not permission.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REVIEW_SCHEMA = "pm_governance_independent_review_v1"
RESULT_SCHEMA = "pm_governance_review_check_v1"
ACTIONS = frozenset(
    {
        "SCIENTIFIC_QUALIFICATION",
        "FROZEN_ROSTER_PROMOTION",
        "PERMANENT_ROSTER_DELETION",
        "MATERIAL_POLICY_CHANGE",
    }
)
REVIEW_FIELDS = frozenset(
    {
        "schema",
        "operation",
        "evidence_sha256",
        "policy_sha256",
        "source_commit_sha",
        "verdict",
        "reviewer",
        "reviewed_at",
        "rationale_sha256",
        "signature",
    }
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hash(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError("INVALID_REVIEW_BINDING_HASH")
    return value


def _file(path: Path, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("UNSAFE_OR_MISSING_GOVERNANCE_FILE")
    size = path.stat().st_size
    if size == 0 or size > max_bytes:
        raise ValueError("OVERSIZED_OR_EMPTY_GOVERNANCE_FILE")
    data = path.read_bytes()
    if len(data) != size:
        raise ValueError("GOVERNANCE_FILE_CHANGED_DURING_READ")
    return data


def check(
    *,
    operation: str,
    evidence: Path,
    policy_sha256: str,
    source_commit_sha: str,
    review: Path | None,
    trusted_reviewer_public_key: Path | None,
) -> dict:
    """Check a separately obtained, signed review against exact frozen evidence.

    This is deliberately not a publication, registry, qualification or order API.
    Both the trusted public key and owner authorization must be established outside
    this process; passing a caller-supplied key is not proof of reviewer independence.
    """
    if operation not in ACTIONS:
        raise ValueError("UNKNOWN_PROTECTED_OPERATION")
    _hash(policy_sha256)
    _hash(source_commit_sha, 40)
    evidence_bytes = _file(evidence, 25_000_000)
    try:
        document = json.loads(evidence_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_GOVERNANCE_EVIDENCE_JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("GOVERNANCE_EVIDENCE_MUST_BE_OBJECT")

    # No positive scientific-signoff producer exists in this repository. The TI
    # readiness command always reports NOT_SCIENTIFICALLY_QUALIFIED; PM02 rankings
    # are research proposals. A forged positive status cannot create that producer.
    if operation == "SCIENTIFIC_QUALIFICATION":
        if document.get("status") != "SCIENTIFICALLY_QUALIFIED":
            raise ValueError("SCIENTIFIC_EVIDENCE_NOT_QUALIFIED")
        raise ValueError("INDEPENDENT_SCIENTIFIC_SIGNOFF_NOT_IMPLEMENTED")

    if review is None or trusted_reviewer_public_key is None:
        raise ValueError("INDEPENDENT_REVIEW_REQUIRED")
    review_bytes = _file(review, 64_000)
    key_bytes = _file(trusted_reviewer_public_key, 32)
    if len(key_bytes) != 32:
        raise ValueError("INVALID_REVIEW_TRUST_ROOT")
    try:
        obj = json.loads(review_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_REVIEW_JSON") from exc
    if not isinstance(obj, dict) or set(obj) != REVIEW_FIELDS or obj["schema"] != REVIEW_SCHEMA:
        raise ValueError("INVALID_REVIEW_SCHEMA")
    if obj["operation"] != operation or obj["verdict"] != "APPROVE":
        raise ValueError("REVIEW_OPERATION_OR_VERDICT_MISMATCH")
    if (
        obj["evidence_sha256"] != sha256(evidence_bytes).hexdigest()
        or obj["policy_sha256"] != policy_sha256
        or obj["source_commit_sha"] != source_commit_sha
    ):
        raise ValueError("STALE_OR_MISMATCHED_REVIEW")
    _hash(obj["rationale_sha256"])
    if not isinstance(obj["reviewer"], str) or not obj["reviewer"].strip():
        raise ValueError("INVALID_REVIEWER_ID")
    if not isinstance(obj["reviewed_at"], str):
        raise ValueError("INVALID_REVIEW_CLOCK")
    try:
        reviewed_at = datetime.fromisoformat(obj["reviewed_at"])
    except ValueError as exc:
        raise ValueError("INVALID_REVIEW_CLOCK") from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("NAIVE_REVIEW_CLOCK")
    try:
        signature = bytes.fromhex(_hash(obj["signature"], 128))
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(
            signature, canonical({k: v for k, v in obj.items() if k != "signature"})
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("INVALID_INDEPENDENT_REVIEW_SIGNATURE") from exc

    return {
        "schema": RESULT_SCHEMA,
        "operation": operation,
        "evidence_sha256": sha256(evidence_bytes).hexdigest(),
        "policy_sha256": policy_sha256,
        "source_commit_sha": source_commit_sha,
        "review_sha256": sha256(review_bytes).hexdigest(),
        "trusted_reviewer_public_key_sha256": sha256(key_bytes).hexdigest(),
        "status": "REVIEW_SIGNATURE_VERIFIED_NOT_AUTHORIZED",
        "owner_authorization_verified": False,
        "scientifically_qualified": False,
        "live_trading_authorized": False,
    }


def run(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True, choices=sorted(ACTIONS))
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--trusted-reviewer-public-key", type=Path)
    args = parser.parse_args(argv)
    return check(
        operation=args.operation,
        evidence=args.evidence,
        policy_sha256=args.policy_sha256,
        source_commit_sha=args.source_commit_sha,
        review=args.review,
        trusted_reviewer_public_key=args.trusted_reviewer_public_key,
    )


def main() -> None:
    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
