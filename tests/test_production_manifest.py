from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from test_production_export import database


def fixture_policy(tmp_path):
    from copytrade_pm.production_export import export_metadata
    from copytrade_pm.production_manifest import digest, sign
    db = database(tmp_path)
    metadata = export_metadata(db, "A", "2026-11-04T06:00:00+00:00")
    reviewer, source = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    created = metadata["asof_ms"]
    members, attestations = [], []
    for item in metadata["members"]:
        member = {**item, "allocation": "2000", "account_scope": [item["source_identity"]],
                  "allowed_markets": ["BTC", "ETH"], "sizing_policy": "ALLOCATION_OVER_LIVE_NAV"}
        members.append(member)
        attestations.append(sign({"schema": "source_scope_attestation_v1",
            "source_identity": item["source_identity"], "account_scope": member["account_scope"],
            "nav": "10000", "known_at_ms": created, "scope_complete": True, "book_complete": True,
            "source_mode": "SYNTHETIC"}, source, "source-observer"))
    body = {"schema": "production_release_policy_v1", "metadata_export_sha256": metadata["export_sha256"],
            "generation": 1, "created_at_ms": created, "expires_at_ms": created + 86400000,
            "account_binding": "fixture-account", "risk_policy_sha": digest("fixture risk"),
            "rulebook_sha": digest("fixture rules"), "source_mode": "SYNTHETIC",
            "members": members, "source_attestations": attestations}
    return db, metadata, sign(body, reviewer, "research-release-policy"), reviewer, source


def test_sqlite_sealed_policy_produces_repeatable_signed_consumer_contract(tmp_path):
    from copytrade_pm.production_manifest import build_manifest, store_policy, verify
    db, metadata, policy, reviewer, source = fixture_policy(tmp_path)
    store_policy(db, "A", metadata, policy, reviewer.public_key())
    args = dict(db=db, portfolio_id="A", asof="2026-11-04T06:00:00+00:00",
                reviewer=reviewer.public_key(), source_observer=source.public_key(),
                release_signer=reviewer, now_ms=metadata["asof_ms"])
    first = build_manifest(**args)
    assert first == build_manifest(**args)
    payload = verify(first, reviewer.public_key(), "approver")
    assert payload["schema"] == "portfolio_release_v1"
    assert payload["batch_seconds"] == 300
    assert len(payload["members"]) == 3
    assert payload["members"][0]["allocation"] == "2000"


def test_tampering_missing_scope_and_unapproved_allocations_are_rejected(tmp_path):
    from copytrade_pm.production_manifest import build_manifest, sign, store_policy
    db, metadata, policy, reviewer, source = fixture_policy(tmp_path)
    policy["payload"]["members"][0]["allocation"] = "999999"
    with pytest.raises(ValueError):
        store_policy(db, "A", metadata, policy, reviewer.public_key())
    policy = sign(policy["payload"], reviewer, "research-release-policy")
    policy["payload"]["source_attestations"][0]["payload"]["scope_complete"] = False
    policy = sign(policy["payload"], reviewer, "research-release-policy")
    store_policy(db, "A", metadata, policy, reviewer.public_key())
    with pytest.raises(ValueError):
        build_manifest(db=db, portfolio_id="A", asof="2026-11-04T06:00:00+00:00",
                       reviewer=reviewer.public_key(), source_observer=source.public_key(),
                       release_signer=reviewer, now_ms=metadata["asof_ms"])


def test_no_sealed_allocation_policy_is_a_specific_blocker(tmp_path):
    from copytrade_pm.production_manifest import build_manifest
    db, metadata, policy, reviewer, source = fixture_policy(tmp_path)
    with pytest.raises(ValueError, match="SEALED_PRODUCTION_POLICY_MISSING"):
        build_manifest(db=db, portfolio_id="A", asof="2026-11-04T06:00:00+00:00",
                       reviewer=reviewer.public_key(), source_observer=source.public_key(),
                       release_signer=reviewer, now_ms=metadata["asof_ms"])
