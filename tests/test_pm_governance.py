"""Protected decisions need bound independent review; research remains unblocked."""

from datetime import UTC, datetime
from hashlib import sha256
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm.pm_governance import REVIEW_SCHEMA, canonical, check, run

POLICY = "a" * 64
COMMIT = "b" * 40
ACTION = "MATERIAL_POLICY_CHANGE"


def case(tmp_path):
    signer = Ed25519PrivateKey.generate()
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(
        canonical({"schema": "proposed_policy_diff_v1", "summary": "guard change"})
    )
    key = tmp_path / "trusted.pub"
    key.write_bytes(
        signer.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    review = tmp_path / "review.json"
    payload = {
        "schema": REVIEW_SCHEMA,
        "operation": ACTION,
        "evidence_sha256": sha256(evidence.read_bytes()).hexdigest(),
        "policy_sha256": POLICY,
        "source_commit_sha": COMMIT,
        "verdict": "APPROVE",
        "reviewer": "synthetic-independent-reviewer",
        "reviewed_at": datetime(2026, 11, 4, tzinfo=UTC).isoformat(),
        "rationale_sha256": "c" * 64,
    }

    def save_review(data, signing_key=signer):
        data = dict(data)
        data["signature"] = signing_key.sign(canonical(data)).hex()
        review.write_bytes(canonical(data))

    save_review(payload)
    return evidence, review, key, payload, save_review


def approved(evidence, review, key, **kwargs):
    return check(
        operation=kwargs.get("operation", ACTION),
        evidence=evidence,
        policy_sha256=kwargs.get("policy_sha256", POLICY),
        source_commit_sha=kwargs.get("source_commit_sha", COMMIT),
        review=review,
        trusted_reviewer_public_key=key,
    )


def test_signed_review_check_is_explicit_read_only_and_not_owner_approval(tmp_path):
    evidence, review, key, _payload, _save = case(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = approved(evidence, review, key)
    assert result["status"] == "REVIEW_SIGNATURE_VERIFIED_NOT_AUTHORIZED"
    assert result["review_sha256"] == sha256(review.read_bytes()).hexdigest()
    assert result["evidence_sha256"] == sha256(evidence.read_bytes()).hexdigest()
    assert result["scientifically_qualified"] is False
    assert result["owner_authorization_verified"] is False
    assert result["live_trading_authorized"] is False
    assert (
        run(
            [
                "--operation",
                ACTION,
                "--evidence",
                str(evidence),
                "--policy-sha256",
                POLICY,
                "--source-commit-sha",
                COMMIT,
                "--review",
                str(review),
                "--trusted-reviewer-public-key",
                str(key),
            ]
        )
        == result
    )
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("action", ["FROZEN_ROSTER_PROMOTION", "PERMANENT_ROSTER_DELETION"])
def test_every_protected_action_requires_an_exact_review(tmp_path, action):
    evidence, review, key, payload, save = case(tmp_path)
    with pytest.raises(ValueError, match="OPERATION_OR_VERDICT"):
        approved(evidence, review, key, operation=action)
    payload["operation"] = action
    save(payload)
    assert approved(evidence, review, key, operation=action)["operation"] == action


def test_missing_review_is_fail_closed_without_affecting_evidence(tmp_path):
    evidence, review, key, _payload, _save = case(tmp_path)
    with pytest.raises(ValueError, match="REVIEW_REQUIRED"):
        approved(evidence, None, None)
    with pytest.raises(ValueError, match="REVIEW_REQUIRED"):
        approved(evidence, review, None)
    assert evidence.is_file() and review.is_file() and key.is_file()


def test_evidence_policy_and_commit_revisions_invalidate_review(tmp_path):
    evidence, review, key, _payload, _save = case(tmp_path)
    evidence.write_bytes(canonical({"schema": "proposed_policy_diff_v1", "summary": "changed"}))
    with pytest.raises(ValueError, match="STALE_OR_MISMATCHED"):
        approved(evidence, review, key)
    evidence, review, key, _payload, _save = case(tmp_path)
    with pytest.raises(ValueError, match="STALE_OR_MISMATCHED"):
        approved(evidence, review, key, policy_sha256="d" * 64)
    with pytest.raises(ValueError, match="STALE_OR_MISMATCHED"):
        approved(evidence, review, key, source_commit_sha="e" * 40)


def test_forged_verdict_or_changed_reviewer_or_wrong_trust_key_rejected(tmp_path):
    evidence, review, key, payload, save = case(tmp_path)
    bad = dict(payload)
    bad["verdict"] = "REJECT"
    save(bad)
    with pytest.raises(ValueError, match="OPERATION_OR_VERDICT"):
        approved(evidence, review, key)
    bad = dict(payload)
    bad["reviewer"] = "other-reviewer"
    save(bad)
    bad["reviewer"] = "forged-reviewer"
    obj = json.loads(review.read_bytes())
    obj["reviewer"] = bad["reviewer"]  # Signature is for the old reviewer.
    review.write_bytes(canonical(obj))
    with pytest.raises(ValueError, match="INVALID_INDEPENDENT_REVIEW_SIGNATURE"):
        approved(evidence, review, key)
    save(payload)
    other = Ed25519PrivateKey.generate().public_key()
    key.write_bytes(other.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    with pytest.raises(ValueError, match="INVALID_INDEPENDENT_REVIEW_SIGNATURE"):
        approved(evidence, review, key)


def test_malformed_review_and_inputs_rejected(tmp_path):
    evidence, review, key, payload, save = case(tmp_path)
    save({**payload, "reviewed_at": "2026-11-04"})
    with pytest.raises(ValueError, match="NAIVE_REVIEW_CLOCK"):
        approved(evidence, review, key)
    save({**payload, "extra_field": True})
    with pytest.raises(ValueError, match="INVALID_REVIEW_SCHEMA"):
        approved(evidence, review, key)
    save(payload)
    key.write_bytes(b"bad")
    with pytest.raises(ValueError, match="INVALID_REVIEW_TRUST_ROOT"):
        approved(evidence, review, key)
    with pytest.raises(ValueError, match="UNKNOWN_PROTECTED_OPERATION"):
        approved(evidence, review, key, operation="ROUTINE_QUERY")
    with pytest.raises(ValueError, match="INVALID_REVIEW_BINDING_HASH"):
        approved(evidence, review, key, policy_sha256="short")
    link = tmp_path / "link.json"
    link.symlink_to(evidence)
    with pytest.raises(ValueError, match="UNSAFE_OR_MISSING"):
        approved(link, review, key)


def test_scientific_qualification_cannot_be_forged_by_review(tmp_path):
    evidence, review, key, _payload, _save = case(tmp_path)
    evidence.write_bytes(
        canonical(
            {
                "schema": "ti_prospective_evidence_readiness_v1",
                "status": "NOT_SCIENTIFICALLY_QUALIFIED",
            }
        )
    )
    with pytest.raises(ValueError, match="SCIENTIFIC_EVIDENCE_NOT_QUALIFIED"):
        approved(evidence, review, key, operation="SCIENTIFIC_QUALIFICATION")
    evidence.write_bytes(
        canonical(
            {
                "schema": "ti_prospective_evidence_readiness_v1",
                "status": "SCIENTIFICALLY_QUALIFIED",
            }
        )
    )
    with pytest.raises(ValueError, match="INDEPENDENT_SCIENTIFIC_SIGNOFF_NOT_IMPLEMENTED"):
        approved(evidence, review, key, operation="SCIENTIFIC_QUALIFICATION")
