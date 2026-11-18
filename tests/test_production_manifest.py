from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from test_production_export import database


def fixture_policy(tmp_path, *, sizing_policy="ALLOCATION_OVER_LIVE_NAV"):
    from copytrade_pm.production_export import export_metadata
    from copytrade_pm.production_manifest import digest, sign

    db = database(tmp_path)
    metadata = export_metadata(db, "A", "2026-11-04T06:00:00+00:00", sizing_policy=sizing_policy)
    reviewer, source = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    created = metadata["asof_ms"]
    members, attestations = [], []
    for item in metadata["members"]:
        member = {
            **item,
            "allocation": "2000",
            "account_scope": [item["source_identity"]],
            "allowed_markets": ["BTC", "ETH"],
            "sizing_policy": "ALLOCATION_OVER_LIVE_NAV",
        }
        members.append(member)
        attestations.append(
            sign(
                {
                    "schema": "source_scope_attestation_v1",
                    "source_identity": item["source_identity"],
                    "account_scope": member["account_scope"],
                    "nav": "10000",
                    "known_at_ms": created,
                    "scope_complete": True,
                    "book_complete": True,
                    "source_mode": "SYNTHETIC",
                },
                source,
                "source-observer",
            )
        )
    body = {
        "schema": "production_release_policy_v1",
        "metadata_export_sha256": metadata["export_sha256"],
        "generation": 1,
        "created_at_ms": created,
        "expires_at_ms": created + 86400000,
        "account_binding": "fixture-account",
        "risk_policy_sha": digest("fixture risk"),
        "rulebook_sha": digest("fixture rules"),
        "source_mode": "SYNTHETIC",
        "members": members,
        "source_attestations": attestations,
    }
    return db, metadata, sign(body, reviewer, "research-release-policy"), reviewer, source


def test_sqlite_sealed_policy_produces_repeatable_signed_consumer_contract(tmp_path):
    from copytrade_pm.production_manifest import build_manifest, store_policy, verify

    db, metadata, policy, reviewer, source = fixture_policy(tmp_path)
    store_policy(db, "A", metadata, policy, reviewer.public_key())
    args = dict(
        db=db,
        portfolio_id="A",
        asof="2026-11-04T06:00:00+00:00",
        reviewer=reviewer.public_key(),
        source_observer=source.public_key(),
        release_signer=reviewer,
        now_ms=metadata["asof_ms"],
    )
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
        build_manifest(
            db=db,
            portfolio_id="A",
            asof="2026-11-04T06:00:00+00:00",
            reviewer=reviewer.public_key(),
            source_observer=source.public_key(),
            release_signer=reviewer,
            now_ms=metadata["asof_ms"],
        )


def build_sizing_fixture(
    tmp_path, *, mode="FIXED_K_NATIVE_QUANTITY", nav=None, k="0.04", scope_complete=True
):
    from copytrade_pm.production_manifest import build_manifest, sign, store_policy

    db, metadata, envelope, reviewer, source = fixture_policy(tmp_path, sizing_policy=mode)
    policy = envelope["payload"]
    for member in policy["members"]:
        member["sizing_policy"] = mode
        if mode == "FIXED_K_NATIVE_QUANTITY":
            member["k"] = k
    for index, envelope in enumerate(policy["source_attestations"]):
        proof = envelope["payload"]
        proof["nav"] = nav
        proof["scope_complete"] = scope_complete
        policy["source_attestations"][index] = sign(proof, source, "source-observer")
    store_policy(
        db, "A", metadata, sign(policy, reviewer, "research-release-policy"), reviewer.public_key()
    )
    return build_manifest(
        db=db,
        portfolio_id="A",
        asof="2026-11-04T06:00:00+00:00",
        reviewer=reviewer.public_key(),
        source_observer=source.public_key(),
        release_signer=reviewer,
        now_ms=metadata["asof_ms"],
    )


def test_fixed_k_signed_handoff_accepts_absent_leader_nav(tmp_path):
    manifest = build_sizing_fixture(tmp_path)
    assert all(m["k"] == "0.04" for m in manifest["payload"]["members"])
    assert all(
        m["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY" for m in manifest["payload"]["members"]
    )


@pytest.mark.parametrize("k", ["0", "-0.01", "11", "NaN", "Infinity", "", "invalid"])
def test_fixed_k_handoff_rejects_invalid_signed_k(tmp_path, k):
    with pytest.raises(ValueError, match="FIXED_K_INVALID"):
        build_sizing_fixture(tmp_path, k=k)


def test_fixed_k_still_requires_complete_source_scope(tmp_path):
    with pytest.raises(ValueError, match="SOURCE_SCOPE_UNVERIFIED"):
        build_sizing_fixture(tmp_path, scope_complete=False)


def test_explicit_legacy_handoff_still_requires_nav(tmp_path):
    with pytest.raises(ValueError, match="SOURCE_NAV_INVALID"):
        build_sizing_fixture(tmp_path, mode="ALLOCATION_OVER_LIVE_NAV")


def test_no_sealed_allocation_policy_is_a_specific_blocker(tmp_path):
    from copytrade_pm.production_manifest import build_manifest

    db, metadata, policy, reviewer, source = fixture_policy(tmp_path)
    with pytest.raises(ValueError, match="SEALED_PRODUCTION_POLICY_MISSING"):
        build_manifest(
            db=db,
            portfolio_id="A",
            asof="2026-11-04T06:00:00+00:00",
            reviewer=reviewer.public_key(),
            source_observer=source.public_key(),
            release_signer=reviewer,
            now_ms=metadata["asof_ms"],
        )


def fixture_v2_args(tmp_path, *, mixed_nav=False, markets=None, dexes=None):
    from copytrade_pm.production_manifest import digest, sign, store_policy

    db, metadata, envelope, reviewer, source = fixture_policy(
        tmp_path, sizing_policy="FIXED_K_NATIVE_QUANTITY"
    )
    policy = envelope["payload"]
    markets = list(
        markets or ["hyperliquid/mainnet:perp:default/BTC", "hyperliquid/mainnet:perp:default/ETH"]
    )
    dexes = list(dexes or ["default"])
    for idx, member in enumerate(policy["members"]):
        member["allowed_markets"] = list(markets)
        if mixed_nav and idx == 0:
            member["sizing_policy"] = "ALLOCATION_OVER_LIVE_NAV"
            continue
        member["sizing_policy"] = "FIXED_K_NATIVE_QUANTITY"
        member["k"] = "0.04"
        proof = {**policy["source_attestations"][idx]["payload"], "nav": None}
        policy["source_attestations"][idx] = sign(proof, source, "source-observer")
    store_policy(
        db, "A", metadata, sign(policy, reviewer, "research-release-policy"), reviewer.public_key()
    )
    checkpoint_policy = {
        "name": "cwsa_utc_5m_v3",
        "limits": {
            "max_state_age_ms": 4000,
            "max_acquisition_ms": 3000,
            "max_dex_skew_ms": 2000,
            "publication_grace_ms": 5000,
        },
        "measurement_sha": digest("fixture-cwsa-measurement"),
    }
    checkpoint_scopes = {
        member["source_identity"]: {
            "schema_version": 3,
            "source_id": member["source_identity"],
            "account_sha": digest(f"acct:{member['source_identity']}"),
            "generation": digest(f"gen:{member['source_identity']}"),
            "selection_sha": digest(f"sel:{member['source_identity']}"),
            "dexes": list(dexes),
        }
        for member in policy["members"]
    }
    policy_epoch = digest(checkpoint_policy)
    mandates = [
        {
            "schema": "copy_mandate_v1",
            "mandate_id": f"mandate-{member['pod_id']}",
            "generation": 1,
            "source_id": member["source_identity"],
            "source_scope_generation": checkpoint_scopes[member["source_identity"]]["generation"],
            "source_account_sha": checkpoint_scopes[member["source_identity"]]["account_sha"],
            "account_id": policy["account_binding"],
            "pod_id": member["pod_id"],
            "k": "0.04",
            "allowed_markets": list(markets),
            "policy_epoch": policy_epoch,
            "risk_policy_sha": policy["risk_policy_sha"],
            "rulebook_sha": policy["rulebook_sha"],
            "effective_from_ms": policy["created_at_ms"],
            "effective_until_ms": policy["expires_at_ms"],
            "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
            "entry_policy": "ONE_SHOT_CHECKPOINT_V3",
            "exit_policy": "NATIVE_SAFE_CROSS_OR_REDUCE_V3",
        }
        for member in policy["members"]
    ]
    return {
        "db": db,
        "portfolio_id": "A",
        "asof": "2026-11-04T06:00:00+00:00",
        "reviewer": reviewer.public_key(),
        "source_observer": source.public_key(),
        "release_signer": reviewer,
        "now_ms": metadata["asof_ms"],
        "checkpoint_policy": checkpoint_policy,
        "checkpoint_scopes": checkpoint_scopes,
        "mandates": mandates,
    }


def test_build_manifest_v2_deterministic_fixed_k_without_nav(tmp_path):
    from copytrade_pm.production_manifest import build_manifest, build_manifest_v2, verify

    args = fixture_v2_args(tmp_path)
    first = build_manifest_v2(**args)
    assert first == build_manifest_v2(**args)
    payload = verify(first, args["reviewer"], "approver")
    assert payload["schema"] == "portfolio_release_v2"
    assert (
        payload["mandate_authority_sha"]
        == sha256(args["release_signer"].public_key().public_bytes_raw()).hexdigest()
    )
    assert payload["checkpoint_policy"] == args["checkpoint_policy"]
    assert payload["checkpoint_scopes"] == args["checkpoint_scopes"]
    assert payload["mandates"] == args["mandates"]
    assert all(m["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY" for m in payload["members"])
    v1 = build_manifest(
        db=args["db"],
        portfolio_id=args["portfolio_id"],
        asof=args["asof"],
        reviewer=args["reviewer"],
        source_observer=args["source_observer"],
        release_signer=args["release_signer"],
        now_ms=args["now_ms"],
    )
    assert v1["payload"]["schema"] == "portfolio_release_v1"


def test_build_manifest_v2_round_trips_lowercase_symbol_susd(tmp_path):
    from copytrade_pm.pm_copy_mandate import CopyMandate
    from copytrade_pm.production_manifest import build_manifest_v2, canonical, verify

    markets = ["hyperliquid/mainnet:perp:default/BTC", "hyperliquid/mainnet:perp:default/sUSD"]
    args = fixture_v2_args(tmp_path, markets=markets)
    manifest = build_manifest_v2(**args)
    payload = verify(manifest, args["reviewer"], "approver")
    assert payload["mandates"][0]["allowed_markets"] == markets
    assert CopyMandate.model_validate_json(canonical(payload["mandates"][0])).allowed_markets == (
        tuple(markets)
    )


@pytest.mark.parametrize(
    ("case", "pattern"),
    [
        ("k_drift", "MANDATE_RELEASE_MEMBER_DRIFT"),
        ("scope_generation_drift", "MANDATE_RELEASE_SCOPE"),
        ("policy_epoch_drift", "MANDATE_RELEASE_SCOPE"),
        ("effective_until_past_expiry", "MANDATE_RELEASE_SCOPE"),
        ("mandate_expired_at_now", "MANDATE_ALREADY_EXPIRED"),
        ("mandate_expired_before_now", "MANDATE_ALREADY_EXPIRED"),
        ("duplicate_account_pod", "MANDATE_RELEASE_OPENING_OVERLAP"),
        ("duplicate_account_mandate", "MANDATE_RELEASE_DUPLICATE_ID"),
        ("mixed_nav_member", "MANDATE_RELEASE_MEMBER_DRIFT"),
        ("invalid_grace_limit", "CWSA_POLICY_LIMIT"),
        ("missing_default_dex", "CWSA_PINNED_DEX_SCOPE"),
        ("unpinned_dex", "MANDATE_DEX_NOT_IN_SCOPE"),
        ("int_k_in_mandate", "MANDATE_K_TYPE"),
        ("float_k_in_mandate", "MANDATE_K_TYPE"),
        ("float_in_mandate", "CANONICAL_FLOAT_OR_TYPE"),
    ],
)
def test_build_manifest_v2_rejects_drift_overlap_and_mixed_nav(tmp_path, case, pattern):
    from copytrade_pm.production_manifest import build_manifest_v2

    args = fixture_v2_args(
        tmp_path,
        mixed_nav=(case == "mixed_nav_member"),
        markets=["hyperliquid/mainnet:perp:otherdex/BTC"] if case == "unpinned_dex" else None,
        dexes=["default", "xyz"] if case == "unpinned_dex" else None,
    )
    if case == "k_drift":
        args["mandates"][0]["k"] = "0.05"
    elif case == "scope_generation_drift":
        args["mandates"][0]["source_scope_generation"] = "0" * 64
    elif case == "policy_epoch_drift":
        args["mandates"][0]["policy_epoch"] = "0" * 64
    elif case == "effective_until_past_expiry":
        args["mandates"][0]["effective_until_ms"] += 1
    elif case == "mandate_expired_at_now":
        args["now_ms"] += 1000
        args["mandates"][0]["effective_until_ms"] = args["now_ms"]
    elif case == "mandate_expired_before_now":
        args["now_ms"] += 1000
        args["mandates"][0]["effective_until_ms"] = args["now_ms"] - 1
    elif case == "duplicate_account_pod":
        args["mandates"][1] = {**args["mandates"][0], "mandate_id": "mandate-duplicate"}
    elif case == "duplicate_account_mandate":
        args["mandates"][1]["mandate_id"] = args["mandates"][0]["mandate_id"]
    elif case == "invalid_grace_limit":
        args["checkpoint_policy"]["limits"]["publication_grace_ms"] = 300_000
    elif case == "missing_default_dex":
        first_source = next(iter(args["checkpoint_scopes"]))
        args["checkpoint_scopes"][first_source]["dexes"] = ["xyz"]
    elif case == "int_k_in_mandate":
        args["mandates"][0]["k"] = 1
    elif case == "float_k_in_mandate":
        args["mandates"][0]["k"] = 0.04
    elif case == "float_in_mandate":
        args["mandates"][0]["generation"] = 1.5
    with pytest.raises(ValueError, match=pattern):
        build_manifest_v2(**args)
