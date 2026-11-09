"""CF09: an orphan artifact, concurrent release reader and independent science."""

from datetime import timedelta
from hashlib import sha256
import multiprocessing
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_pydantic_registry_lifecycle import prepared, registry, native, NOW
from test_pydantic_registry_release_readers import configured, release
from test_pm_prospective_audit import setup_receipt, signature
from test_pm_prospective_ledger import IMPORTED
from test_pm02_whole_account_outcomes import whole
from test_trader_intelligence_qualification import readiness


def test_cf09_artifact_crash_release_reader_and_scientific_predicates(tmp_path, monkeypatch):
    registry_root, release_root, science_root = (
        tmp_path / "registry",
        tmp_path / "release",
        tmp_path / "science",
    )
    for folder in (registry_root, release_root, science_root):
        folder.mkdir()
    db, source, original_inventory = prepared(registry_root)
    original = source.read_bytes()
    artifact = db.parent / "evidence/native-cohorts" / (sha256(original).hexdigest() + ".json")
    initial = registry.db_status(db)
    ctx = multiprocessing.get_context("fork")

    def crash_after_artifact():
        link = os.link

        def crash(a, b, **kwargs):
            result = link(a, b, **kwargs)
            if Path(b) == artifact:
                os._exit(91)
            return result

        os.link = crash
        native.register_cohort(db, source, expected=original_inventory, apply=True, now=NOW)

    crashed = ctx.Process(target=crash_after_artifact)
    crashed.start()
    crashed.join(10)
    assert crashed.exitcode == 91
    assert artifact.read_bytes() == original
    assert registry.db_status(db) == initial
    old, new, states = configured(release_root, monkeypatch)
    switched, resume = ctx.Event(), ctx.Event()

    def switching_release():
        def pause():
            switched.set()
            if not resume.wait(10):
                os._exit(92)

        with release.release_lock():
            release.commit_release(new, states[new], after_switch=pause)

    switching = ctx.Process(target=switching_release)
    switching.start()
    try:
        assert switched.wait(10)
        assert release.active_revision() == new
        assert release._json(release.STATE)["current"] == old
        with pytest.raises(RuntimeError, match="already in progress"):
            release.verify()
        ledger, signer, audit, now = setup_receipt(science_root)
        now[0] = IMPORTED + timedelta(minutes=6)
        unsigned_audit = whole(ledger, "0" * 64)
        with pytest.raises(ValueError, match="NO_INDEPENDENT_AUDITED_RECEIPT"):
            ledger.record_matched_outcome(unsigned_audit, signature(signer, unsigned_audit))
        head = ledger.audit_receipt(audit, signature(signer, audit))
        valid = whole(ledger, head)
        premature = {**valid, "outcome_known_at": (IMPORTED + timedelta(minutes=1)).isoformat()}
        with pytest.raises(ValueError, match="HORIZON_NOT_MATURE"):
            ledger.record_matched_outcome(premature, signature(signer, premature))
        with pytest.raises(ValueError, match="INVALID_OUTCOME_SIGNATURE"):
            ledger.record_matched_outcome(valid, signature(Ed25519PrivateKey.generate(), valid))
        assert readiness(ledger).eligible_whole_account_outcomes == 0
    finally:
        resume.set()
        switching.join(10)
        if switching.is_alive():
            switching.kill()
            switching.join()
    assert switching.exitcode == 0
    assert release.verify()["revision"] == new
    native.register_cohort(db, source, expected=original_inventory, apply=True, now=NOW)
    assert (
        registry.db_status(db)["counts"]["current_research_selection"]
        == initial["counts"]["current_research_selection"]
    )
    assert source.read_bytes() == artifact.read_bytes() == original
    ledger.record_matched_outcome(valid, signature(signer, valid))
    report = readiness(ledger)
    assert report.eligible_whole_account_outcomes == 1
    assert report.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert "PREDECLARED_INDEPENDENT_HOLDOUT_NOT_ESTABLISHED" in report.reasons
