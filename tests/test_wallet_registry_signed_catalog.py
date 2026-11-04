"""Future Gemini selections are data-only, signed, research-only, and immutable."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_catalog as catalog
from copytrade_pm import wallet_registry_signed_catalog as signed
from test_wallet_registry_catalog import WHALE, _v2_snapshot


def _signed_source(
    tmp_path: Path,
    *,
    role: str = "PRIMARY_FORWARD_PAPER_RESEARCH",
    duplicate_manager: bool = False,
    replace_e6: bool = False,
) -> tuple[Path, Path, Path, str]:
    tmp_path.chmod(0o700)
    manifest = {
        "schema": signed.SCHEMA,
        "scope": signed.SCOPE,
        "trading_authorized": False,
        "definitions": {
            "gemini.phase4/E6" if replace_e6 else "gemini.phase7/E12": {
                "members": ["W083", "S053-HYPE"] if duplicate_manager else ["ACT04", "S053-HYPE"]
            },
            "gemini.phase7/E13": {"members": ["W080", "CM-002"]},
        },
        "selections": [
            {
                "portfolio_id": "gemini.phase4/E6" if replace_e6 else "gemini.phase7/E12",
                "role": role,
                "priority": 1,
            },
            {"portfolio_id": "gemini.phase7/E13", "role": "RESEARCH_CONTROL", "priority": 2},
        ],
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    root = tmp_path / "signed-private"
    root.mkdir(mode=0o700, exist_ok=True)
    source = root / "signed_selection.json"
    signature = root / "signed_selection.sig"
    key_path = root / "operator.pub"
    source.write_bytes(raw)
    signature.write_text(key.sign(raw).hex())
    key_path.write_bytes(public)
    for path in (source, signature, key_path):
        path.chmod(0o600)
    return source, signature, key_path, sha256(public).hexdigest()


def test_data_only_signed_future_portfolio_import_and_asof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, datetime.now(timezone.utc).isoformat())
    source, signature, public, fingerprint = _signed_source(tmp_path)
    args = [
        "--db",
        str(db),
        "signed-selection",
        "--manifest",
        str(source),
        "--signature",
        str(signature),
        "--trusted-public-key",
        str(public),
        "--trusted-key-sha256",
        fingerprint,
    ]
    assert registry.cli(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["stored"] is False
    assert preview["trading_authorized"] is False
    assert preview["definitions"] == 2

    before = "2026-11-04T09:06:33+00:00"
    assert registry.cli(args + ["--apply"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["stored"] is True
    assert applied["backup_verified"] is True
    with closing(registry.connect(db, False)) as con:
        current = catalog.list_selection(con, datetime.now(timezone.utc).isoformat())
        assert current["selection_state"] == "SIGNATURE_CHECKED_RESEARCH_ONLY"
        assert [p["portfolio_id"] for p in current["portfolios"]] == [
            "gemini.phase7/E12",
            "gemini.phase7/E13",
        ]
        assert current["portfolios"][0]["alias_resolution_complete"] is True
        assert current["portfolios"][0]["trading_authorized"] is False
        earlier = catalog.list_selection(con, before)
        assert earlier["selection_state"] == "OWNER_APPROVED_RESEARCH_ONLY"
        assert con.execute("SELECT COUNT(*) FROM research_selection_proofs").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    # Reimport is idempotent and does not retroactively move first-known.
    assert registry.cli(args + ["--apply"]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["unchanged"] is True


def test_unsigned_future_selection_or_bad_review_key_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    source, signature, public, fingerprint = _signed_source(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="reviewed public key fingerprint"):
        signed.inspect(
            source,
            signature,
            public,
            expected_public_key_sha256="0" * 64,
            first_known_at=now,
        )
    signature.write_text("00" * 64)
    with pytest.raises(ValueError, match="invalid signed research selection signature"):
        signed.inspect(
            source,
            signature,
            public,
            expected_public_key_sha256=fingerprint,
            first_known_at=now,
        )


def test_signed_selection_cannot_embed_trading_authority_or_modify_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    source, signature, public, fingerprint = _signed_source(
        tmp_path,
        role="TRADING_AUTHORIZED",
    )
    with pytest.raises(ValueError, match="unknown signed portfolio selection"):
        signed.inspect(
            source,
            signature,
            public,
            expected_public_key_sha256=fingerprint,
            first_known_at=datetime.now(timezone.utc).isoformat(),
        )
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, "2026-11-05T00:00:00+00:00")
    # Import a real synthetic signed fixture, then reject any mutation.
    source, signature, public, fingerprint = _signed_source(tmp_path)
    record = signed.inspect(
        source,
        signature,
        public,
        expected_public_key_sha256=fingerprint,
        first_known_at=datetime.now(timezone.utc).isoformat(),
    )
    with closing(registry.connect(db, True)) as con, con:
        signed.store(con, record)
    with closing(registry.connect(db, True)) as con:
        with pytest.raises(sqlite3.IntegrityError, match="immutable signed"):
            con.execute(
                "UPDATE research_selection_proofs SET source_json='{}' WHERE source_sha256=?",
                (record["source_sha256"],),
            )
    # Import is still NOT a positive scientific decision or a paper run.
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM portfolio_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM qualification_decisions").fetchone()[0] == 0


def test_signed_update_to_existing_e6_does_not_rewrite_v2_asof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, datetime.now(timezone.utc).isoformat())
    source, signature, public, fingerprint = _signed_source(tmp_path, replace_e6=True)
    record = signed.inspect(
        source,
        signature,
        public,
        expected_public_key_sha256=fingerprint,
        first_known_at=datetime.now(timezone.utc).isoformat(),
    )
    with closing(registry.connect(db, True)) as con, con:
        signed.store(con, record)
    with closing(registry.connect(db, False)) as con:
        newest = catalog.list_selection(con, datetime.now(timezone.utc).isoformat())
        assert newest["portfolios"][0]["portfolio_id"] == "gemini.phase4/E6"
        assert newest["portfolios"][0]["version"] == 2
        historic = catalog.list_selection(con, "2026-11-04T09:06:33+00:00")
        assert historic["portfolios"][0]["version"] == 1
        assert historic["portfolios"][0]["members"] == [
            "ACT04",
            "CM-002",
            "S051-BTC",
            "S053-HYPE",
            "Whale_0x5f94",
        ]


def test_signed_import_rejects_two_aliases_for_one_canonical_wallet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, datetime.now(timezone.utc).isoformat())
    source, signature, public, fingerprint = _signed_source(tmp_path, duplicate_manager=True)
    record = signed.inspect(
        source,
        signature,
        public,
        expected_public_key_sha256=fingerprint,
        first_known_at=datetime.now(timezone.utc).isoformat(),
    )
    with closing(registry.connect(db, True)) as con:
        with pytest.raises(ValueError, match="duplicate canonical wallet"):
            with con:
                signed.store(con, record)
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM research_selection_proofs").fetchone()[0] == 0
        assert (
            catalog.list_selection(con, datetime.now(timezone.utc).isoformat())["selection_state"]
            == "OWNER_APPROVED_RESEARCH_ONLY"
        )
