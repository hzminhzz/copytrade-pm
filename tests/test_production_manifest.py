from hashlib import sha256
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm.production_export import export_metadata
from copytrade_pm.production_manifest import build_manifest, digest, sign, store_policy, verify
from copytrade_pm.roster import ReleaseBinding, RosterStore, select_sealed_book
from roster_fixture import AT, MS, WALLETS, add_account

MARKETS = ["hyperliquid/mainnet:perp:default/BTC", "hyperliquid/mainnet:perp:default/ETH"]


def release_fixture(
    tmp_path, *, markets=None, dexes=None, source_mode="SYNTHETIC", attestation_mode=None
):
    attestation_mode = attestation_mode or source_mode
    markets = tuple(markets or MARKETS)
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
    wallets = dict(zip(("seat_1", "seat_2", "seat_3"), WALLETS[:3], strict=True))
    checkpoint_scopes = {
        identity: {
            "schema_version": 3,
            "source_id": identity,
            "account_sha": digest(f"acct:{identity}"),
            "generation": digest(f"gen:{identity}"),
            "selection_sha": digest(f"sel:{identity}"),
            "dexes": list(dexes or ["default"]),
        }
        for identity in wallets.values()
    }
    binding = ReleaseBinding(
        account_id="A",
        generation=1,
        research_commit="a" * 40,
        decision_sha=digest("synthetic decision"),
        selection_known_at_ms=MS,
        source_mode=source_mode,
        risk_policy_sha=digest("fixture risk"),
        rulebook_sha=digest("fixture rules"),
        checkpoint_policy=checkpoint_policy,
        checkpoint_scopes=checkpoint_scopes,
        allowed_markets={seat: markets for seat in wallets},
        created_ms=MS,
        expires_at_ms=MS + 86400000,
    )
    db = tmp_path / "roster.sqlite"
    with RosterStore(db, create=True) as store:
        book = add_account(store, "A", wallets, epoch=binding.policy_epoch)
        store.record_release_binding(binding, recorded_ms=MS)
    metadata = export_metadata(db, "A", AT)
    reviewer, source = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    members, attestations = [], []
    for item in metadata["members"]:
        identity = item["source_identity"]
        members.append(
            {
                "pod_id": item["pod_id"],
                "source_identity": identity,
                "identity_known_at_ms": item["identity_known_at_ms"],
                "allocation": "200",
                "account_scope": [identity],
                "allowed_markets": list(markets),
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "k": "0.04",
            }
        )
        attestations.append(
            sign(
                {
                    "schema": "source_scope_attestation_v1",
                    "source_identity": identity,
                    "account_scope": [identity],
                    "known_at_ms": MS,
                    "scope_complete": True,
                    "book_complete": True,
                    "source_mode": attestation_mode,
                },
                source,
                "source-observer",
            )
        )
    policy = {
        "schema": "production_release_policy_v1",
        "metadata_export_sha256": metadata["export_sha256"],
        "generation": 1,
        "created_at_ms": MS,
        "expires_at_ms": binding.expires_at_ms,
        "account_binding": "A",
        "risk_policy_sha": binding.risk_policy_sha,
        "rulebook_sha": binding.rulebook_sha,
        "source_mode": source_mode,
        "members": members,
        "source_attestations": attestations,
    }
    return db, metadata, policy, reviewer, source, book, binding


def fixture_policy(tmp_path, *, sizing_policy="FIXED_K_NATIVE_QUANTITY"):
    if sizing_policy != "FIXED_K_NATIVE_QUANTITY":
        raise ValueError("SIZING_POLICY")
    db, metadata, body, reviewer, source, _, _ = release_fixture(tmp_path)
    return db, metadata, sign(body, reviewer, "research-release-policy"), reviewer, source


def test_sqlite_sealed_policy_produces_repeatable_signed_consumer_contract(tmp_path):
    db, metadata, envelope, reviewer, source = fixture_policy(tmp_path)
    store_policy(db, "A", metadata, envelope, reviewer.public_key())
    assert export_metadata(db, "A", AT) == metadata
    args = dict(
        db=db,
        portfolio_id="A",
        asof=AT,
        reviewer=reviewer.public_key(),
        source_observer=source.public_key(),
        release_signer=reviewer,
        now_ms=MS,
    )
    first = build_manifest(**args)
    assert first == build_manifest(**args)
    payload = verify(first, reviewer.public_key(), "approver")
    assert payload["schema"] == "portfolio_release_v1"
    assert payload["batch_seconds"] == 300
    assert [member["pod_id"] for member in payload["members"]] == ["seat_1", "seat_2", "seat_3"]
    assert payload["members"][0]["allocation"] == "200"
    with RosterStore(db) as store:
        selection = select_sealed_book(
            store, "A", MS, reviewer=reviewer.public_key(), source_observer=source.public_key()
        )
    assert selection.attested and not selection.trading_authorized


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "SELECTION_ATTESTATION_MISSING"),
        ("wrong_reviewer", "SELECTION_ATTESTATION_MISSING"),
        ("wrong_observer", "SELECTION_ATTESTATION_MISSING"),
        ("no_scope", "SELECTION_ATTESTATION_MISSING"),
        ("old_proof", "SELECTION_ATTESTATION_MISSING"),
        ("future_policy", "SELECTION_ATTESTATION_MISSING"),
        ("wrong_generation", "SELECTION_ATTESTATION_MISSING"),
        ("expiry", "SELECTION_ATTESTATION_MISSING"),
        ("wallet", "SELECTION_MEMBER_DRIFT"),
        ("identity_clock", "SELECTION_MEMBER_DRIFT"),
        ("fixed_k", "SELECTION_MEMBER_DRIFT"),
    ],
)
def test_attestations_fail_closed(tmp_path, case, code):
    db, _, policy, reviewer, source, _, _ = release_fixture(tmp_path)
    known_at = MS + 1 if case == "future_policy" else MS
    if case in {"no_scope", "old_proof"}:
        proof = policy["source_attestations"][0]["payload"]
        proof["scope_complete"] = case != "no_scope"
        proof["known_at_ms"] = MS - 600001 if case == "old_proof" else MS
        policy["source_attestations"][0] = sign(proof, source, "source-observer")
    if case == "wallet":
        policy["members"][0]["source_identity"] = WALLETS[7]
    if case == "identity_clock":
        policy["members"][0]["identity_known_at_ms"] -= 1
    if case == "fixed_k":
        policy["members"][0]["k"] = "0.05"
    with RosterStore(db, writable=True) as store:
        if case != "missing":
            store.seal_policy(
                "A",
                generation=2 if case == "wrong_generation" else 1,
                known_at_ms=known_at,
                envelope=sign(policy, reviewer, "research-release-policy"),
            )
        with pytest.raises(ValueError, match=code):
            select_sealed_book(
                store,
                "A",
                policy["expires_at_ms"] if case == "expiry" else MS,
                reviewer=(
                    Ed25519PrivateKey.generate() if case == "wrong_reviewer" else reviewer
                ).public_key(),
                source_observer=(
                    Ed25519PrivateKey.generate() if case == "wrong_observer" else source
                ).public_key(),
            )


def fixture_v2_args(tmp_path, *, mixed_nav=False, markets=None, dexes=None):
    from copytrade_pm.roster import build_release_proposal

    db, metadata, policy, reviewer, source, book, binding = release_fixture(
        tmp_path, markets=markets, dexes=dexes
    )
    if mixed_nav:
        member = policy["members"][0]
        member.pop("k")
        member["sizing_policy"] = "ALLOCATION_OVER_LIVE_NAV"
        proof = {**policy["source_attestations"][0]["payload"], "nav": "10000"}
        policy["source_attestations"][0] = sign(proof, source, "source-observer")
    store_policy(
        db, "A", metadata, sign(policy, reviewer, "research-release-policy"), reviewer.public_key()
    )
    proposal = build_release_proposal(
        book, binding, inventory_sha=digest("inventory"), plan_sha=digest("plan")
    )
    return dict(
        db=db,
        portfolio_id="A",
        asof=AT,
        reviewer=reviewer.public_key(),
        source_observer=source.public_key(),
        release_signer=reviewer,
        now_ms=MS,
        checkpoint_policy=dict(binding.checkpoint_policy),
        checkpoint_scopes=dict(binding.checkpoint_scopes),
        mandates=proposal.payload_json["mandates"],
    )


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
    from copytrade_pm.pm_mandate import SignedMandate
    from copytrade_pm.production_manifest import build_manifest_v2, verify

    markets = ["hyperliquid/mainnet:perp:default/BTC", "hyperliquid/mainnet:perp:default/sUSD"]
    args = fixture_v2_args(tmp_path, markets=markets)
    manifest = build_manifest_v2(**args)
    payload = verify(manifest, args["reviewer"], "approver")
    assert payload["mandates"][0]["allowed_markets"] == markets
    assert SignedMandate.parse(payload["mandates"][0]).allowed_markets == tuple(markets)


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
        ("mixed_nav_member", "SELECTION_MEMBER_DRIFT"),
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


def test_staged_release_requires_exact_reviewed_checkpoint_pins(tmp_path):
    from dataclasses import replace

    from copytrade_pm.roster import build_release_proposal, verify_staged_selection

    db, metadata, policy, reviewer, source, book, binding = release_fixture(tmp_path)
    with RosterStore(db, writable=True) as store:
        proposal = build_release_proposal(
            book, binding, inventory_sha=store.inventory_sha(), plan_sha=digest("plan")
        )
        store.stage_proposal(proposal)
        args = dict(now_ms=MS, reviewer=reviewer.public_key(), source_observer=source.public_key())
        with pytest.raises(ValueError, match="SELECTION_ATTESTATION_MISSING"):
            verify_staged_selection(store, proposal, **args)
        store_policy(
            db,
            "A",
            metadata,
            sign(policy, reviewer, "research-release-policy"),
            reviewer.public_key(),
        )
        assert verify_staged_selection(store, proposal, **args).attested
        altered = proposal.payload_json
        altered["checkpoint_policy"]["limits"]["max_state_age_ms"] += 1
        with pytest.raises(ValueError, match="SELECTION_MEMBER_DRIFT"):
            verify_staged_selection(store, replace(proposal, payload=altered), **args)


def test_staged_prospective_selection_requires_matching_attestations(tmp_path):
    from copytrade_pm.roster import build_release_proposal, verify_staged_selection

    db, metadata, policy, reviewer, source, book, binding = release_fixture(
        tmp_path, source_mode="PROSPECTIVE"
    )
    assert binding.source_mode == "PROSPECTIVE"
    with RosterStore(db, writable=True) as store:
        proposal = build_release_proposal(
            book, binding, inventory_sha=store.inventory_sha(), plan_sha=digest("plan")
        )
        assert proposal.payload_json["source_mode"] == "PROSPECTIVE"
        store.stage_proposal(proposal)
        # The exact staged PROSPECTIVE selection is unapproved until a reviewer
        # policy covering it is sealed.
        with pytest.raises(ValueError, match="SELECTION_ATTESTATION_MISSING"):
            verify_staged_selection(
                store,
                proposal,
                now_ms=MS,
                reviewer=reviewer.public_key(),
                source_observer=source.public_key(),
            )
        store_policy(
            db,
            "A",
            metadata,
            sign(policy, reviewer, "research-release-policy"),
            reviewer.public_key(),
        )
        assert verify_staged_selection(
            store,
            proposal,
            now_ms=MS,
            reviewer=reviewer.public_key(),
            source_observer=source.public_key(),
        ).attested


def test_prospective_selection_refuses_synthetic_mode_source_attestations(tmp_path):
    from copytrade_pm.roster import build_release_proposal, verify_staged_selection

    db, metadata, policy, reviewer, source, book, binding = release_fixture(
        tmp_path, source_mode="PROSPECTIVE", attestation_mode="SYNTHETIC"
    )
    with RosterStore(db, writable=True) as store:
        proposal = build_release_proposal(
            book, binding, inventory_sha=store.inventory_sha(), plan_sha=digest("plan")
        )
        store.stage_proposal(proposal)
        store_policy(
            db,
            "A",
            metadata,
            sign(policy, reviewer, "research-release-policy"),
            reviewer.public_key(),
        )
        # Observer evidence signed for the wrong source mode cannot approve a
        # prospective release, even when the reviewer policy is well formed.
        with pytest.raises(ValueError, match="SELECTION_ATTESTATION_MISSING"):
            verify_staged_selection(
                store,
                proposal,
                now_ms=MS,
                reviewer=reviewer.public_key(),
                source_observer=source.public_key(),
            )


# --- the whole staged body must be derived, not merely well formed ----------
#
# Each entry rewrites exactly one claim of the unsigned body with a value the
# producer would never derive (well-formed digests, a plausible clock, one extra
# field). A schema check cannot catch these; only re-deriving the entire body
# from independently validated inputs can.
BODY_TAMPERS = (
    ("definition_sha", lambda body: body.__setitem__("definition_sha", "0" * 64)),
    ("inventory_sha", lambda body: body.__setitem__("inventory_sha", "0" * 64)),
    ("source_sha", lambda body: body.__setitem__("source_sha", "0" * 64)),
    ("batch_seconds", lambda body: body.__setitem__("batch_seconds", 301)),
    (
        "member_allocation",
        lambda body: body["members"][0].__setitem__("allocation", "300"),
    ),
    ("mandate_k", lambda body: body["mandates"][0].__setitem__("k", "0.05")),
    ("extra_field", lambda body: body.__setitem__("order_route", "NONE")),
)
BODY_TAMPER_IDS = [name for name, _ in BODY_TAMPERS]
# The four fields the pre-sign check used to skip are exercised through the CLI
# too, because they are the ones a valid envelope could previously carry.
CLI_TAMPER_IDS = {"definition_sha", "inventory_sha", "source_sha", "batch_seconds"}


def stage_release(tmp_path, mutate=None):
    """Stage one exact body through the public API and seal its approval.

    ``mutate`` rewrites the payload *before* it is staged, so the stored row and
    the file agree with each other: only the body's derivation from the verified
    book, binding and inventory pin can expose the inconsistency.
    """
    from copytrade_pm.roster import ReleaseProposal, build_release_proposal

    db, metadata, policy, reviewer, source, book, binding = release_fixture(tmp_path)
    with RosterStore(db, writable=True) as store:
        proposal = build_release_proposal(
            book, binding, inventory_sha=store.inventory_sha(), plan_sha=digest("plan")
        )
        payload = proposal.payload_json
        if mutate is not None:
            mutate(payload)
        staged = ReleaseProposal(
            account_id=proposal.account_id,
            day=proposal.day,
            generation=proposal.generation,
            plan_sha=proposal.plan_sha,
            book_sha=proposal.book_sha,
            binding_sha=proposal.binding_sha,
            payload=payload,
            created_ms=proposal.created_ms,
        )
        assert store.stage_proposal(staged) == staged.sha
        inventory_pin = store.inventory_sha()
    store_policy(
        db, "A", metadata, sign(policy, reviewer, "research-release-policy"), reviewer.public_key()
    )
    return db, staged, reviewer, source, book, binding, inventory_pin


def sign_via_cli(tmp_path, monkeypatch, capsys, staged, reviewer, source):
    """Drive the real `release sign --apply`; report every path `os.open` saw."""
    from copytrade_pm.pm_operations import cli

    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(staged.data))
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "release.key"
    key_path.write_bytes(key.private_bytes_raw())
    key_path.chmod(0o600)
    reviewer_pub = tmp_path / "reviewer.pub"
    reviewer_pub.write_bytes(reviewer.public_key().public_bytes_raw())
    observer_pub = tmp_path / "observer.pub"
    observer_pub.write_bytes(source.public_key().public_bytes_raw())
    output = tmp_path / "release.json"
    opened: list[Path] = []
    real_open = os.open

    def spy(path, *args, **kwargs):
        opened.append(Path(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    code = cli(
        [
            "release",
            "sign",
            "--store",
            str(tmp_path / "roster.sqlite"),
            "--proposal",
            str(proposal_path),
            "--release-signing-key",
            str(key_path),
            "--reviewer-public",
            str(reviewer_pub),
            "--source-observer-public",
            str(observer_pub),
            "--now-ms",
            str(MS),
            "--out",
            str(output),
            "--apply",
        ]
    )
    out = capsys.readouterr().out
    return code, json.loads(out[out.index("{") :]), key, key_path, output, opened


def test_staged_body_digests_are_derived_from_the_sealed_book(tmp_path):
    from copytrade_pm.roster import verify_staged_selection

    db, proposal, reviewer, source, book, binding, inventory_pin = stage_release(tmp_path)
    with RosterStore(db) as store:
        selection = verify_staged_selection(
            store,
            proposal,
            now_ms=MS,
            reviewer=reviewer.public_key(),
            source_observer=source.public_key(),
        )
    assert selection.attested and not selection.trading_authorized
    body = proposal.payload_json
    assert body["definition_sha"] == digest(body["members"])
    assert body["inventory_sha"] == digest(
        {"roster": inventory_pin, "book": book.sha, "policy_epoch": binding.policy_epoch}
    )
    assert body["source_sha"] == digest(
        {
            key: body[key]
            for key in (
                "research_commit",
                "decision_sha",
                "inventory_sha",
                "definition_sha",
                "selection_known_at_ms",
            )
        }
    )
    assert body["batch_seconds"] == 300
    assert proposal.book_sha == book.sha
    assert selection.definition_sha256 == digest(
        {
            "schema": "roster_sealed_selection_v1",
            "book_sha": book.sha,
            "leases": [
                digest(lease.data) for lease in sorted(book.leases, key=lambda item: item.seat_id)
            ],
        }
    )


@pytest.mark.parametrize("field,mutate", BODY_TAMPERS, ids=BODY_TAMPER_IDS)
def test_staged_body_matching_the_row_is_refused_when_not_derived(tmp_path, field, mutate):
    from copytrade_pm.roster import verify_staged_selection

    db, staged, reviewer, source, _, _, _ = stage_release(tmp_path, mutate)
    # The tampered body is the stored row and the file byte-for-byte; only the
    # derivation from the verified book/binding/inventory pin can refuse it.
    with RosterStore(db) as store:
        assert store.proposal(staged.sha) == staged
        with pytest.raises(ValueError, match="RELEASE_PROPOSAL_BODY_DRIFT"):
            verify_staged_selection(
                store,
                staged,
                now_ms=MS,
                reviewer=reviewer.public_key(),
                source_observer=source.public_key(),
            )


@pytest.mark.parametrize(
    "field,mutate",
    [case for case in BODY_TAMPERS if case[0] in CLI_TAMPER_IDS],
    ids=[name for name in BODY_TAMPER_IDS if name in CLI_TAMPER_IDS],
)
def test_release_sign_refuses_an_underived_staged_body_before_the_key(
    tmp_path, capsys, monkeypatch, field, mutate
):
    db, staged, reviewer, source, _, _, _ = stage_release(tmp_path, mutate)
    code, receipt, _, key_path, output, opened = sign_via_cli(
        tmp_path, monkeypatch, capsys, staged, reviewer, source
    )
    assert code == 2 and receipt["error_code"] == "RELEASE_PROPOSAL_BODY_DRIFT"
    assert receipt["state"] == "BLOCKED" and receipt["trading_authorized"] is False
    assert key_path not in opened
    assert not output.exists()


def test_release_sign_still_signs_the_derived_staged_body(tmp_path, capsys, monkeypatch):
    from copytrade_pm.production_manifest import verify

    db, staged, reviewer, source, _, _, _ = stage_release(tmp_path)
    code, receipt, key, key_path, output, opened = sign_via_cli(
        tmp_path, monkeypatch, capsys, staged, reviewer, source
    )
    assert code == 0 and receipt["state"] == "SIGNED_METADATA_RELEASE"
    assert key_path in opened and output.exists()
    payload = verify(json.loads(output.read_text()), key.public_key(), "approver")
    # Canonical signing bytes are unchanged: the envelope covers the staged body
    # plus only the signer-derived authority field.
    assert {
        name: value for name, value in payload.items() if name != "mandate_authority_sha"
    } == staged.payload_json
    with RosterStore(db) as store:
        assert store.proposals("A")[-1].sha == staged.sha


def test_flat_preserves_original_mandate_until_signed_retire(tmp_path):
    from copytrade_kernel import KnownAtTs
    from copytrade_pm.pm_forward_journal import PaperJournal
    from copytrade_pm.pm_mandate import SignedMandate, state_sha
    from copytrade_pm.roster import (
        OperatorVeto,
        build_release_proposal,
        mandate_id,
        reconcile_roster,
    )

    db, _, _, _, _, book, binding = release_fixture(tmp_path)
    proposal = build_release_proposal(
        book, binding, inventory_sha=digest("inventory"), plan_sha=digest("plan")
    )
    first = SignedMandate.parse(proposal.payload_json["mandates"][0])
    successor = SignedMandate.from_fields(
        **(
            first.data
            | {
                "generation": 2,
                "mandate_id": mandate_id(first.account_id, first.pod_id, 2),
                "effective_from_ms": MS + 300_000,
            }
        )
    )
    journal = PaperJournal(tmp_path / "paper")
    key = Ed25519PrivateKey.generate()
    previous = journal.activate_copy_mandate(
        sign(first.data, key, "copy-mandate-v1"), key.public_key(), account_id="A", at_ms=MS
    )
    stamp = MS + 1000
    with RosterStore(db, writable=True) as store:
        flat = reconcile_roster(
            current=book,
            as_of=KnownAtTs(stamp),
            vetoes=[OperatorVeto(wallet, "fixture", "synthetic", stamp) for wallet in book.wallets],
        )
        store.commit_plan(flat, committed_ms=stamp, with_proposal=False)
        assert flat.mode == "FLAT"
        with pytest.raises(ValueError, match="SELECTION_FLAT_NO_OCCUPIED_SEATS"):
            select_sealed_book(store, "A", stamp, require_attestation=False)
    signed_successor = sign(successor.data, key, "copy-mandate-v1")
    with pytest.raises(ValueError, match="MANDATE_OPENING_INTERVAL_OVERLAP"):
        journal.activate_copy_mandate(
            signed_successor, key.public_key(), account_id="A", at_ms=stamp
        )
    assert journal.copy_mandate_state(first.owner) == previous
    control = {
        "schema": "copy_mandate_control_v1",
        "owner": first.owner,
        "mandate_sha": first.sha,
        "predecessor_sha": state_sha(previous),
        "event": "RETIRE",
        "issued_ms": stamp,
        "expires_ms": stamp + 1000,
        "nonce": digest("retires fixture lease"),
    }
    other = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="MANDATE_CONTROL_AUTHORITY"):
        journal.control_copy_mandate(
            sign(control, other, "copy-mandate-control-v1"), other.public_key(), at_ms=stamp
        )
    retired = journal.control_copy_mandate(
        sign(control, key, "copy-mandate-control-v1"), key.public_key(), at_ms=stamp
    )
    assert retired.phase == "RETIRED"
    pending = journal.activate_copy_mandate(
        signed_successor, key.public_key(), account_id="A", at_ms=stamp
    )
    assert pending.phase == "AWAITING_BASELINE"
    reopened = PaperJournal(journal.root)
    assert reopened.copy_mandate_state(first.owner) == retired
    assert reopened.copy_mandate_state(successor.owner) == pending
