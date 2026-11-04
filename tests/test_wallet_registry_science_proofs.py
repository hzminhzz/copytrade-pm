"""Only cryptographically checked, source-backed NEGATIVE reviews may be indexed."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_qualification as qual
from copytrade_pm import wallet_registry_science_proofs as science
from test_wallet_registry import address, fixture


def _files(tmp_path: Path, *, wallet: str | None = None) -> tuple[Path, Path, Path, dict]:
    root = tmp_path / "signed"
    root.mkdir(mode=0o700)
    evidence = root / "matched-outcomes.bin"
    evidence.write_bytes(b"synthetic fixture only: not real matched outcomes")
    evidence.chmod(0o600)
    key = Ed25519PrivateKey.generate()
    public = root / "reviewer.key.pub"
    public.write_bytes(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    public.chmod(0o600)
    t = datetime.now(timezone.utc)
    att = {
        "schema": science.SCHEMA,
        "decision_id": "audited-negative-v1",
        "wallet": wallet or address(1),
        "policy_version": "pm02_whole_account_v2",
        "policy_sha256": "a" * 64,
        "evidence_sha256": sha256(evidence.read_bytes()).hexdigest(),
        "verdict": "BLOCKED",
        "decision_at": (t - timedelta(minutes=3)).isoformat(),
        "reviewed_at": (t - timedelta(minutes=2)).isoformat(),
        "reviewer_id": "external-reviewer-test-fixture",
        "reviewer_role": "INDEPENDENT_REVIEWER",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "scope": "RESEARCH_ONLY",
    }
    signed = root / "signed.json"
    envelope = {
        "attestation": att,
        "signature_hex": key.sign(science._canonical(att)).hex(),
    }
    signed.write_text(json.dumps(envelope))
    signed.chmod(0o600)
    return signed, evidence, public, {"att": att, "key": key, "root": root}


def _db(tmp_path: Path) -> Path:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "db" / "private.sqlite"
    registry.apply(db, snapshot, datetime.now(timezone.utc).isoformat())
    return db


def _resign(signed: Path, fields: dict, key: Ed25519PrivateKey) -> None:
    signed.write_text(
        json.dumps(
            {
                "attestation": fields,
                "signature_hex": key.sign(science._canonical(fields)).hex(),
            }
        )
    )
    signed.chmod(0o600)


def test_source_sha_and_independent_ed25519_negative_are_immutable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path)
    signed, evidence, public, data = _files(tmp_path)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 8
    args = [
        "--db",
        str(db),
        "qualification",
        "--attestation-file",
        str(signed),
        "--evidence-file",
        str(evidence),
        "--auditor-public-key-file",
        str(public),
    ]
    assert registry.cli(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["stored"] is False
    assert preview["scientifically_qualified"] is False
    assert preview["trading_authorized"] is False
    assert address(1) not in json.dumps(preview)
    assert data["att"]["reviewer_id"] not in json.dumps(preview)
    assert str(evidence) not in json.dumps(preview)
    assert registry.cli([*args, "--apply"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["stored"] is True
    assert registry.cli([*args, "--apply"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["stored"] is False
    with closing(registry.connect(db, False)) as con:
        assert qual.status(con)["signed_negative_proofs_indexed"] == 1
        assert qual.status(con)["scientifically_qualified"] == "NOT_ESTABLISHED"
        assert qual.status(con)["trading_authorized"] is False
        value = con.execute("SELECT known_at FROM qualification_decisions").fetchone()[0]
        assert datetime.fromisoformat(value) > datetime.fromisoformat(data["att"]["reviewed_at"])
    with closing(registry.connect(db, True)) as con:
        for statement in (
            "UPDATE qualification_decisions SET verdict='UNQUALIFIED'",
            "DELETE FROM qualification_decisions",
            "UPDATE qualification_proofs SET signature_hex='fake'",
            "DELETE FROM qualification_proofs",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_INDEPENDENT"):
                with con:
                    con.execute(statement)
    assert registry.db_status(db)["counts"]["scientifically_qualified"] == "NOT_ESTABLISHED"
    assert registry.db_status(db)["counts"]["trading_authorized"] == "NOT_ESTABLISHED"


def test_unsigned_or_bad_source_never_imports(tmp_path: Path) -> None:
    signed, evidence, public, data = _files(tmp_path)
    db = _db(tmp_path)
    arguments = [signed, evidence, public]
    result = science.inspect_negative(*arguments)
    assert result["verdict"] == "BLOCKED"
    with closing(registry.connect(db, True)) as con, con:
        # Even direct library callers must pass cryptographic verification.
        with pytest.raises(ValueError, match="changed independent"):
            science.store_negative(con, {**result, "signature_hex": "f" * 128})
        assert con.execute("SELECT COUNT(*) FROM qualification_decisions").fetchone()[0] == 0
    evidence.write_bytes(b"tampered after reviewer signed original source")
    with pytest.raises(ValueError, match="source evidence SHA"):
        science.inspect_negative(*arguments)
    with closing(registry.connect(db, True)) as con, con:
        with pytest.raises(ValueError, match="changed independent"):
            science.store_negative(con, result)
    evidence.write_bytes(b"synthetic fixture only: not real matched outcomes")
    wrong = Ed25519PrivateKey.generate()
    public.write_bytes(wrong.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    with pytest.raises(ValueError, match="signature verification failed"):
        science.inspect_negative(*arguments)
    public.write_bytes(data["key"].public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert science.inspect_negative(*arguments)["verdict"] == "BLOCKED"
    signed.chmod(0o644)
    with pytest.raises(ValueError, match="private 0600"):
        science.inspect_negative(*arguments)
    signed.chmod(0o600)
    data["root"].chmod(0o755)
    with pytest.raises(ValueError, match="directory must be private"):
        science.inspect_negative(*arguments)
    data["root"].chmod(0o700)
    signed.unlink()
    signed.symlink_to(evidence)
    with pytest.raises(ValueError, match="linked"):
        science.inspect_negative(*arguments)


def test_positive_or_future_claims_and_unknown_wallet_rejected(tmp_path: Path) -> None:
    signed, evidence, public, data = _files(tmp_path)
    wallet = _db(tmp_path)
    for updates in (
        {"verdict": "QUALIFIED", "scientifically_qualified": True},
        {"trading_authorized": True},
        {"scope": "LIVE"},
        {"policy_sha256": "wrong"},
        {"decision_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    ):
        changed = {**data["att"], **updates}
        _resign(signed, changed, data["key"])
        with pytest.raises(ValueError):
            science.inspect_negative(signed, evidence, public)
    _resign(signed, {**data["att"], "wallet": address(299)}, data["key"])
    with pytest.raises(ValueError, match="not registered"):
        registry.cli(
            [
                "--db",
                str(wallet),
                "qualification",
                "--attestation-file",
                str(signed),
                "--evidence-file",
                str(evidence),
                "--auditor-public-key-file",
                str(public),
                "--apply",
            ]
        )
    with closing(registry.connect(wallet, True)) as con:
        with pytest.raises(ValueError, match="canonical private registry"):
            with con:
                science.store_negative(con, science.inspect_negative(signed, evidence, public))


def test_schema_v6_upgrade_is_additive_and_idempotent(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "db" / "private.sqlite"
    known = datetime.now(timezone.utc).isoformat()
    registry.apply(db, snapshot, known)
    baseline = registry.db_status(db)
    with closing(registry.connect(db, True)) as con, con:
        con.executescript("""
            DROP TRIGGER qualification_proof_decision_no_update;
            DROP TRIGGER qualification_proof_decision_no_delete;
            DROP TRIGGER qualification_proof_no_update;
            DROP TRIGGER qualification_proof_no_delete;
            DROP TABLE qualification_proofs;
            DELETE FROM schema_migrations WHERE version IN (6,7,8);
        """)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 5
    result = registry.apply(db, snapshot, datetime.now(timezone.utc).isoformat())
    assert result["unchanged"] is True
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 8
        assert con.execute("SELECT COUNT(*) FROM qualification_proofs").fetchone()[0] == 0
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    after = registry.db_status(db)
    assert after["source_shas"] == baseline["source_shas"]
    assert after["counts"]["scientifically_qualified"] == "NOT_ESTABLISHED"


def test_direct_library_import_cannot_fake_policy_or_known_at(tmp_path: Path) -> None:
    db = _db(tmp_path)
    signed, evidence, public, _ = _files(tmp_path)
    record = science.inspect_negative(signed, evidence, public)
    with closing(registry.connect(db, True)) as con:
        with pytest.raises(ValueError, match="changed independent"):
            with con:
                science.store_negative(con, {**record, "policy_version": "forged-policy"})
        with con:
            result = science.store_negative(
                con,
                {
                    **record,
                    "known_at": "2000-01-01T00:00:00+00:00",
                },
            )
            assert result["stored"] is True
    with closing(registry.connect(db, False)) as con:
        observed = con.execute(
            "SELECT known_at FROM qualification_decisions WHERE decision_id=?",
            ("audited-negative-v1",),
        ).fetchone()[0]
        assert datetime.fromisoformat(observed) > datetime(2026, 11, 3, tzinfo=timezone.utc)


def test_altered_review_payload_rejected_and_no_stale_import_clock(tmp_path: Path) -> None:
    signed, evidence, public, data = _files(tmp_path)
    record = science.inspect_negative(signed, evidence, public)
    envelope = json.loads(signed.read_text())
    envelope["attestation"]["policy_version"] = "tampered"
    signed.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="signature verification failed"):
        science.inspect_negative(signed, evidence, public)
    _resign(signed, data["att"], data["key"])
    reconstructed = science.inspect_negative(signed, evidence, public)
    assert reconstructed["attestation_sha256"] == record["attestation_sha256"]
    assert datetime.fromisoformat(reconstructed["known_at"]) >= datetime.fromisoformat(
        data["att"]["reviewed_at"]
    )
