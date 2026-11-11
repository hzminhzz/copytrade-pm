"""Independent full-audit anchors and indexed bounded suffix verification."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm_forward_stream_anchor import (
    advance_anchor,
    anchor_file_bytes,
    full_audit_anchor,
    load_anchor,
    verify_suffix,
    _reader,
    publish_anchor,
)
from test_v4_source_export import ADDRESSES, observer, source_event


def _offline_snapshot(path, tmp_path):
    target = tmp_path / "offline-audit.sqlite3"
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as clone:
        source.backup(clone)
    return target


def _seal(tmp_path, envelope, key):
    directory = tmp_path / "private-anchor"
    directory.mkdir(mode=0o700, exist_ok=True)
    raw = anchor_file_bytes(envelope)
    path = directory / (sha256(raw).hexdigest() + ".json")
    path.write_bytes(raw)
    path.chmod(0o600)
    return load_anchor(
        path,
        sha256(raw).hexdigest(),
        key.public_key(),
        expected_auditor_public_key_sha256=sha256(key.public_key().public_bytes_raw()).hexdigest(),
    )


def test_initial_full_audit_and_bounded_incremental_proof(tmp_path):
    journal, source = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="OFFLINE_SNAPSHOT_REQUIRED"):
        full_audit_anchor(
            _offline_snapshot(journal.path, tmp_path),
            alias="S035",
            account=ADDRESSES["S035"],
            auditor=auditor,
        )
    starting = full_audit_anchor(
        _offline_snapshot(journal.path, tmp_path),
        alias="S035",
        account=ADDRESSES["S035"],
        auditor=auditor,
        offline_snapshot_confirmed=True,
    )
    trusted = _seal(tmp_path, starting, auditor)
    assert trusted.payload["parent_anchor_sha256"] is None
    source_event(source, 10, 20)
    with closing(_reader(journal.path)) as db:
        verified = verify_suffix(db, trusted, alias="S035", account=ADDRESSES["S035"])
    assert verified["stream_cursor"] == trusted.payload["stream_cursor"] + 1
    assert len(verified["rows"]) == 1
    assert verified["status"] == "INDEPENDENT_FULL_AUDIT_ANCHORED_SUFFIX_VERIFIED"
    renewed = advance_anchor(
        journal.path,
        trusted,
        alias="S035",
        account=ADDRESSES["S035"],
        auditor=auditor,
    )
    successor = _seal(tmp_path, renewed, auditor)
    assert successor.payload["parent_anchor_sha256"] == trusted.seal_file_sha256
    with closing(_reader(journal.path)) as db:
        new = verify_suffix(db, successor, alias="S035", account=ADDRESSES["S035"])
    assert new["rows"] == []
    source_event(source, 20, 25)
    with closing(_reader(journal.path)) as db:
        new = verify_suffix(db, successor, alias="S035", account=ADDRESSES["S035"])
    assert len(new["rows"]) == 1
    assert new["trading_authorized"] is False


def test_forged_anchor_and_unpinned_auditor_rejected(tmp_path):
    journal, _ = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    envelope = full_audit_anchor(
        _offline_snapshot(journal.path, tmp_path),
        alias="S035",
        account=ADDRESSES["S035"],
        auditor=auditor,
        offline_snapshot_confirmed=True,
    )
    trusted = _seal(tmp_path, envelope, auditor)
    file_sha = trusted.seal_file_sha256
    path = tmp_path / "private-anchor" / (file_sha + ".json")
    with pytest.raises(ValueError, match="INDEPENDENT_AUDITOR_PIN_REQUIRED"):
        load_anchor(
            path,
            file_sha,
            auditor.public_key(),
            expected_auditor_public_key_sha256=sha256(
                other.public_key().public_bytes_raw()
            ).hexdigest(),
        )
    with pytest.raises(ValueError, match="MANIFEST_SIGNATURE"):
        load_anchor(
            path,
            file_sha,
            other.public_key(),
            expected_auditor_public_key_sha256=sha256(
                other.public_key().public_bytes_raw()
            ).hexdigest(),
        )
    with pytest.raises(ValueError, match="AUDITOR_ROTATION_NOT_APPROVED"):
        advance_anchor(
            journal.path, trusted, alias="S035", account=ADDRESSES["S035"], auditor=other
        )
    tampered = json.loads(path.read_bytes())
    tampered["payload"]["stream_chain_sha"] = "a" * 64
    path.write_bytes(json.dumps(tampered).encode())
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        load_anchor(
            path,
            file_sha,
            auditor.public_key(),
            expected_auditor_public_key_sha256=trusted.auditor_key_sha256,
        )


def test_bound_cursor_scope_and_stream_payload_tamper(tmp_path):
    journal, source = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    trusted = _seal(
        tmp_path,
        full_audit_anchor(
            _offline_snapshot(journal.path, tmp_path),
            alias="S035",
            account=ADDRESSES["S035"],
            auditor=auditor,
            offline_snapshot_confirmed=True,
        ),
        auditor,
    )
    source_event(source, 10, 20)
    with closing(_reader(journal.path)) as db:
        with pytest.raises(ValueError, match="SELECTION_MISMATCH"):
            verify_suffix(db, trusted, alias="OTHER", account=ADDRESSES["S035"])
        with pytest.raises(ValueError, match="STREAM_SUFFIX_LIMIT"):
            verify_suffix(db, trusted, alias="S035", account=ADDRESSES["S035"], target_cursor=999)
        with closing(sqlite3.connect(":memory:")) as empty:
            with pytest.raises(ValueError, match="READ_TRANSACTION_REQUIRED"):
                verify_suffix(empty, trusted, alias="S035", account=ADDRESSES["S035"])
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "UPDATE observer_stream_events SET payload=? WHERE stream_id=? AND seq=?",
            ("{}", "account:S035", trusted.payload["stream_cursor"] + 1),
        )
        db.commit()
    with closing(_reader(journal.path)) as db:
        with pytest.raises(ValueError):
            verify_suffix(db, trusted, alias="S035", account=ADDRESSES["S035"])


def test_changed_receipt_and_missing_old_anchor_row_fail(tmp_path):
    journal, source = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    trusted = _seal(
        tmp_path,
        full_audit_anchor(
            _offline_snapshot(journal.path, tmp_path),
            alias="S035",
            account=ADDRESSES["S035"],
            auditor=auditor,
            offline_snapshot_confirmed=True,
        ),
        auditor,
    )
    source_event(source, 10, 20)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "UPDATE source_receipts SET receipt_sha=? WHERE source_id=? AND seq=(SELECT MAX(seq) FROM source_receipts WHERE source_id=?)",
            ("f" * 64, "S035", "S035"),
        )
        db.commit()
    with closing(_reader(journal.path)) as db:
        with pytest.raises(ValueError, match="RECEIPT_CHAIN_DIVERGENCE"):
            verify_suffix(db, trusted, alias="S035", account=ADDRESSES["S035"])


def test_immutable_anchor_publication_crash_replay_and_tamper(tmp_path):
    journal, _ = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    seal = full_audit_anchor(
        _offline_snapshot(journal.path, tmp_path),
        alias="S035",
        account=ADDRESSES["S035"],
        auditor=auditor,
        offline_snapshot_confirmed=True,
    )
    root = tmp_path / "source-audit-anchors"
    root.mkdir(mode=0o700)
    first_path, first_sha = publish_anchor(root, seal)
    replay_path, replay_sha = publish_anchor(root, seal)
    assert first_path == replay_path
    assert first_sha == replay_sha
    assert first_path.stat().st_mode & 0o777 == 0o600
    assert len(list(root.iterdir())) == 1
    audit = load_anchor(
        first_path,
        first_sha,
        auditor.public_key(),
        expected_auditor_public_key_sha256=sha256(
            auditor.public_key().public_bytes_raw()
        ).hexdigest(),
    )
    assert audit.payload["stream_cursor"] > 0
    first_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="PINNED_SHA_MISMATCH"):
        publish_anchor(root, seal)
    other = tmp_path / "arbitrary-directory"
    other.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="OUTPUT_DIRECTORY_UNSAFE"):
        publish_anchor(other, seal)


def test_suffix_explicit_bound_prevents_runaway_full_scan(tmp_path, monkeypatch):
    from copytrade_pm import pm_forward_stream_anchor as module

    journal, source = observer(tmp_path / "journal")
    auditor = Ed25519PrivateKey.generate()
    trusted = _seal(
        tmp_path,
        full_audit_anchor(
            _offline_snapshot(journal.path, tmp_path),
            alias="S035",
            account=ADDRESSES["S035"],
            auditor=auditor,
            offline_snapshot_confirmed=True,
        ),
        auditor,
    )
    source_event(source, 10, 20)
    monkeypatch.setattr(module, "MAX_SUFFIX_EVENTS", 0)
    with closing(_reader(journal.path)) as db:
        with pytest.raises(ValueError, match="STREAM_SUFFIX_LIMIT"):
            verify_suffix(db, trusted, alias="S035", account=ADDRESSES["S035"])
