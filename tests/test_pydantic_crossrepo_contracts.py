"""Real candidate producer against separately supplied, unchanged consumer code.

Run with the reviewed prop-production src directory on PYTHONPATH. These tests
use temporary identities/keys and never access a protected runtime or broker.
"""

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.production_manifest import build_manifest, sign, store_policy, verify
from copytrade_pm.v4_source_export import export_signed_events
from test_production_manifest import fixture_policy
from test_v4_source_export import observer, source_event
from test_pm_forward_observed_paper import ADDRESSES, at

pytest.importorskip("prop_production", reason="Required cross-repo acceptance environment")


def exported(tmp_path):
    journal, source = observer(tmp_path)
    source_event(source, 10, 20)
    key = Ed25519PrivateKey.generate()
    packet = export_signed_events(
        journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key, after={"S035": 2}
    )
    return journal, packet["events"]["S035"][0], key


def accepted_release(book, key):
    from prop_production.evidence import digest
    from prop_production.release import ReleaseVerifier, fixture_release

    body = fixture_release()
    known = book["known_at_ms"]
    body.update(
        created_at_ms=known - 1,
        selection_known_at_ms=known - 2,
        expires_at_ms=known + 900000,
        source_mode="PROSPECTIVE",
    )
    body["members"][0].update(
        source_identity=book["source_identity"],
        identity_known_at_ms=known - 3,
        account_scope=book["scope"],
        allowed_markets=[leg["market"] for leg in book["positions"]],
        sizing_policy="FIXED_K_NATIVE_QUANTITY",
        k="0.025",
    )
    body["definition_sha"] = digest(body["members"])
    body["source_sha"] = digest(
        {
            field: body[field]
            for field in (
                "research_commit",
                "decision_sha",
                "inventory_sha",
                "definition_sha",
                "selection_known_at_ms",
            )
        }
    )
    return ReleaseVerifier(
        key.public_key(),
        "approver",
        "fixture-account",
        body["risk_policy_sha"],
        body["rulebook_sha"],
    ).verify(sign(body, key, "approver"), now_ms=known)


def test_candidate_signed_book_preserves_raw_clock_and_fixed_k_optional_nav(tmp_path):
    from prop_production.planner import compile_pods

    journal, record, key = exported(tmp_path)
    before = journal.path.read_bytes()
    book = verify(record["book"], key.public_key(), "source-observer")
    proof = verify(record["proof"], key.public_key(), "source-observer-v4")
    assert book["known_at_ms"] == int(datetime.fromisoformat(at(11)).timestamp() * 1000)
    assert book["known_at_ms"] == proof["first_known_ms"]
    assert proof["source_book_sha"] == record["book"]["sha256"]
    assert proof["trading_authorized"] is False
    release = accepted_release(book, key)
    outputs = []
    for nav in (None, "1", "999999999"):
        diagnostic = {**book, "nav": nav}
        receipt = {
            "envelope": sign(diagnostic, key, "source-observer"),
            "local_known_ms": book["known_at_ms"],
        }
        outputs.append(
            compile_pods(
                [receipt],
                release,
                key.public_key(),
                book["known_at_ms"] + 300000,
            )[0]["requested_notionals"]
        )
    assert outputs == [{book["positions"][0]["market"]: "50.000"}] * 3
    assert journal.path.read_bytes() == before
    assert release.trading_authorized is False


@pytest.mark.parametrize(
    "damage",
    [
        "schema",
        "cash",
        "scope",
        "identity",
        "bool_clock",
        "future_clock",
        "backdated_clock",
        "dex",
        "order_identity",
        "quantity",
        "signature",
    ],
)
def test_critical_candidate_source_damage_fails_consumer(tmp_path, damage):
    from prop_production.planner import compile_pods

    _, record, key = exported(tmp_path)
    original = verify(record["book"], key.public_key(), "source-observer")
    release = accepted_release(original, key)
    book = deepcopy(original)
    if damage == "schema":
        book["schema"] = "source_book_v999"
    elif damage == "cash":
        book["cash"] = "1000000"
    elif damage == "scope":
        book["scope"] = ["unselected"]
    elif damage == "identity":
        book["source_identity"] = "unselected"
    elif damage == "bool_clock":
        book["known_at_ms"] = True
    elif damage == "future_clock":
        book["source_event_ms"] = book["known_at_ms"] + 1
    elif damage == "backdated_clock":
        book["known_at_ms"] = release.payload["selection_known_at_ms"] - 1
    elif damage == "dex":
        book["positions"][0]["market"] = "hyperliquid/mainnet:perp:xyz/BTC"
    elif damage == "order_identity":
        book["positions"][0]["order_id"] = "fabricated-permit"
    elif damage == "quantity":
        book["positions"][0]["quantity"] = True
    envelope = sign(book, key, "source-observer")
    if damage == "signature":
        envelope["payload"]["positions"][0]["quantity"] = "999"
    with pytest.raises(ValueError):
        compile_pods(
            [{"envelope": envelope, "local_known_ms": original["known_at_ms"]}],
            release,
            key.public_key(),
            original["known_at_ms"] + 300000,
        )


@pytest.mark.parametrize("mode", ["ALLOCATION_OVER_LIVE_NAV", "FIXED_K_NATIVE_QUANTITY"])
def test_candidate_real_sqlite_release_matches_existing_schema(tmp_path, mode):
    from prop_production.release import ReleaseVerifier

    db, metadata, policy, reviewer, source = fixture_policy(tmp_path, sizing_policy=mode)
    if mode == "FIXED_K_NATIVE_QUANTITY":
        body = policy["payload"]
        for member in body["members"]:
            member.update(sizing_policy=mode, k="0.04")
        for index, envelope in enumerate(body["source_attestations"]):
            proof = {**envelope["payload"], "nav": None}
            body["source_attestations"][index] = sign(proof, source, "source-observer")
        policy = sign(body, reviewer, "research-release-policy")
    store_policy(db, "A", metadata, policy, reviewer.public_key())
    candidate = build_manifest(
        db=db,
        portfolio_id="A",
        asof="2026-11-04T06:00:00+00:00",
        reviewer=reviewer.public_key(),
        source_observer=source.public_key(),
        release_signer=reviewer,
        now_ms=metadata["asof_ms"],
    )
    body = candidate["payload"]
    verifier = ReleaseVerifier(
        reviewer.public_key(),
        "approver",
        "fixture-account",
        body["risk_policy_sha"],
        body["rulebook_sha"],
    )
    accepted = verifier.verify(candidate, now_ms=metadata["asof_ms"])
    assert accepted.payload["batch_seconds"] == 300
    assert accepted.trading_authorized is False
    wrong_version = {**body, "schema": "portfolio_release_v999"}
    with pytest.raises(ValueError, match="SCHEMA"):
        verifier.verify(sign(wrong_version, reviewer, "approver"), now_ms=metadata["asof_ms"])


def test_current_candidate_cannot_silently_replace_the_pinned_checkout():
    from prop_production.research_bridge import verify_checkout

    with pytest.raises(ValueError, match="RESEARCH_REVISION_NOT_PINNED"):
        verify_checkout(Path(__file__).resolve().parents[1])
