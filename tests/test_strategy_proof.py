"""Track C original-only proof reference and adversarial SHA/clock verification."""

from contextlib import closing
from datetime import datetime
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.strategy_census import assess_verified_packet
from copytrade_pm.strategy_finance import inspect_pm03_original
from copytrade_pm.strategy_health import (
    FollowerEconomics,
    StrategyAssessment,
    ZERO_SHA,
    seal,
)
from copytrade_pm.strategy_matched_pm04 import compare_candidate
from copytrade_pm.strategy_proof import (
    MarketQuoteReference,
    create_reference,
    publish_reference,
    read_reference,
    seal_reference,
    verify_originals_for_track_c,
)
from copytrade_pm.strategy_source_verify import verify_packet
from copytrade_pm.v4_source_export import export_signed_events
from test_pm_forward_ccxt_tape import quotes
from test_strategy_matched_pm04 import _input
from test_strategy_health_v2 import ADDRESSES, NOW, campaign, observer, scope, source_event


def _original_bundle(tmp_path):
    journal, src = observer(tmp_path / "observer")
    source_event(src, 10, 20)
    key = Ed25519PrivateKey.generate()
    selected = {"S035": ADDRESSES["S035"]}
    packet = export_signed_events(
        journal.path,
        selected=selected,
        signer=key,
        after={"S035": 2},
    )
    report = assess_verified_packet(
        packet,
        key.public_key(),
        selected=selected,
        source_after={"S035": 2},
        source_journal=journal.path,
        scope=scope(),
        campaign=campaign(),
        as_of=NOW,
        created_at=NOW,
    )
    report = seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "follower_economics": FollowerEconomics(evidence_class="RESEARCH_SYNTHETIC"),
            }
        )
    )
    compare_candidate(_input(), tmp_path / "compared")
    pm03_dir = tmp_path / "compared" / "runs" / "tbv2-matched-with"
    original = inspect_pm03_original(pm03_dir, as_of=NOW)
    tape = PaperJournal(tmp_path / "quotes")
    first, _ = quotes()
    tape.append_market_quote(first)
    market = MarketQuoteReference(
        instrument=first["instrument"],
        original_quote_id=digest(first),
        quote_payload_sha256=digest(first),
        source_known_at=datetime.fromisoformat(first["first_known_at"]),
        consumed_at=datetime.fromisoformat(first["first_known_at"]),
    )
    source = verify_packet(
        packet,
        key.public_key(),
        selected=selected,
        original_journal=journal.path,
        after={"S035": 2},
        as_of=NOW,
        policy_version="k1",
        frozen_k="0.125",
    )
    ref = create_reference(
        report,
        original_source_journal=journal.path,
        original_source_head_sha256=source["verified_original_journal_sha256"],
        source_after_cursor=2,
        original_market_journal=tape.path,
        market_quote_refs=(market,),
        original_pm03_root=pm03_dir,
        original_pm03_head_sha256=original["ledger_head_sha256"],
        original_pm03_manifest_sha256=original["manifest_sha256"],
    )
    params = {
        "signed_packet": packet,
        "source_public_key": key.public_key(),
        "selected": selected,
        "pinned_source_journal": journal.path,
        "pinned_market_journal": tape.path,
        "pinned_pm03_root": pm03_dir,
    }
    return report, ref, params, tape


def test_reference_sha_and_original_verifier_read_only_distinct(tmp_path):
    report, ref, params, tape = _original_bundle(tmp_path)
    root = tmp_path / "private-references"
    root.mkdir(mode=0o700)
    path = root / "proof.json"
    original_source = params["pinned_source_journal"].read_bytes()
    original_pm03 = (params["pinned_pm03_root"] / "events.jsonl").read_bytes()
    publish_reference(ref, path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert read_reference(path) == ref
    response = verify_originals_for_track_c(ref, report, **params)
    assert response["source_original_reverified"] is True
    assert response["pm03_original_replay_verified"] is True
    assert response["market_original_receipts_verified"] == 1
    assert response["research_finance_window_admitted"] is False
    assert response["independent_follower_economics_qualified"] is False
    assert "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED" in response["blockers"]
    assert "RUNTIME_RELEASE_CONSUMER_NOT_VERSION_AWARE" in response["blockers"]
    assert params["pinned_source_journal"].read_bytes() == original_source
    assert (params["pinned_pm03_root"] / "events.jsonl").read_bytes() == original_pm03
    assert not response["trading_authorized"]
    assert not response["active_k_changed"]


def test_forged_self_consistent_ref_report_and_source_original_fail(tmp_path):
    report, ref, params, tape = _original_bundle(tmp_path)
    original = ref.model_copy(
        update={
            "ref_sha256": ZERO_SHA,
            "original_source_head_sha256": "b" * 64,
        }
    )
    forged = seal_reference(original)
    assert forged.ref_sha256 != ref.ref_sha256
    with pytest.raises(ValueError, match="ORIGINAL_SOURCE_HEAD_DIVERGED"):
        verify_originals_for_track_c(forged, report, **params)
    mismatched = report.model_copy(
        update={
            "report_sha256": ZERO_SHA,
            "strategy": report.strategy.model_copy(update={"k_version": "k2"}),
        }
    )
    forged_report = seal(mismatched)
    with pytest.raises(ValueError, match="REPORT_STRATEGY_POLICY_DRIFT"):
        verify_originals_for_track_c(ref, forged_report, **params)
    packet = json.loads(json.dumps(params["signed_packet"]))
    packet["events"]["S035"][0]["proof"]["payload"]["first_known_ms"] += 1
    with pytest.raises(ValueError):
        verify_originals_for_track_c(ref, report, **{**params, "signed_packet": packet})


def test_reference_file_hash_tamper_and_market_original_divergence(tmp_path):
    report, ref, params, tape = _original_bundle(tmp_path)
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    path = root / "ref.json"
    publish_reference(ref, path)
    raw = json.loads(path.read_text())
    raw["original_pm03_head_sha256"] = "b" * 64
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="HASH_INVALID"):
        read_reference(path)
    with pytest.raises(ValueError, match="ORIGINAL_PATH_NOT_OPERATOR_PINNED"):
        verify_originals_for_track_c(
            ref,
            report,
            **{**params, "pinned_market_journal": tmp_path / "swapped.db"},
        )
    import sqlite3

    with closing(sqlite3.connect(tape.path)) as db, db:
        db.execute("UPDATE market_quote_receipts SET payload_sha=?", ("f" * 64,))
    with pytest.raises(ValueError, match="ORIGINAL_MARKET_CHAIN_DIVERGENCE"):
        verify_originals_for_track_c(ref, report, **params)
