"""Adversarial review fixes for SQLite portfolio sealing and safe rollback.

Never access production DBs or modify running services.
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import importlib.util
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_catalog as catalog
from copytrade_pm import wallet_registry_portfolios as portfolios
from test_wallet_registry_catalog import AFTER, WHALE, _private_file, _v2_snapshot

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "registry_release.py"
SPEC = importlib.util.spec_from_file_location("registry_review_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_sealed_membership_read_rejects_valid_alternative_wallet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, False)) as con:
        accepted = catalog.list_selection(con, AFTER)
        assert accepted["portfolios"][0]["alias_resolution_complete"] is True
    with closing(reg.connect(db, True)) as con, con:
        # Bypass DB-level guards *only in the disposable test database*.
        for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'guard_sealed_membership_%'"
        ):
            con.execute(f'DROP TRIGGER "{name}"')
        replacement = catalog.resolve_alias(con, "W016", AFTER)
        assert replacement is not None
        con.execute(
            "UPDATE portfolio_memberships SET member_alias='W016',wallet_id=? "
            "WHERE portfolio_id='gemini.phase4/E6' AND member_alias='ACT04'",
            (replacement,),
        )
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    with closing(reg.connect(db, False)) as con:
        with pytest.raises(ValueError, match="sealed portfolio membership"):
            portfolios.select_asof(con, "gemini.phase4/E6", AFTER)
        with pytest.raises(ValueError, match="sealed portfolio membership"):
            catalog.list_selection(con, AFTER)


def test_sealed_membership_sql_mutation_is_forbidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, True)) as con:
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            con.execute(
                "UPDATE portfolio_memberships SET member_alias='W016' "
                "WHERE portfolio_id='gemini.phase4/E6' AND member_alias='ACT04'"
            )


def test_whale_prefix_is_not_a_full_identity_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = catalog.WHALE_ADDRESS_SHA256
    path = _private_file(tmp_path / "phase4.csv")
    v2 = catalog.read_v2(Path(__file__).resolve().parents[1], observed_at=AFTER)
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", original)
    with pytest.raises(ValueError, match="full.*whale|whale.*digest"):
        catalog.read_private_identities(path, v2)
    assert WHALE.startswith("0x5f94")


def test_selection_references_exact_sealed_version_after_new_version_is_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, True)) as con, con:
        con.execute(
            "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
            (
                "gemini.phase4/E6",
                2,
                "RESEARCH_SELECTION_ONLY",
                catalog.V2_FILE,
                "2026-11-05T12:00:00+00:00",
                "GEMINI_REFERENCE_K_NOT_EXECUTABLE",
            ),
        )
        con.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?,?,?)",
            (
                "gemini.phase4/E6",
                2,
                "d" * 64,
                catalog.V2_SHA256,
                catalog.V2_COMMIT,
                "2026-11-05T12:00:00+00:00",
            ),
        )
    with closing(reg.connect(db, False)) as con:
        selection = catalog.list_selection(con, "2026-11-06T00:00:00+00:00")
        assert selection["portfolios"][0]["version"] == 1
        assert selection["portfolios"][0]["portfolio_id"] == "gemini.phase4/E6"


def test_rollback_refuses_previous_release_with_failed_doctor_before_pointer_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "release-control"
    root.mkdir(mode=0o700)
    previous, current = "a" * 40, "b" * 40
    for sha in (previous, current):
        folder = root / "releases" / sha
        folder.mkdir(parents=True)
        (folder / "check.py").write_text(sha)
    (root / "releases").chmod(0o700)
    fingerprint = {
        sha: {"check.py": sha256(sha.encode()).hexdigest()} for sha in (previous, current)
    }
    state = root / "release-state.json"
    import json

    expected = {
        "current": current,
        "previous": previous,
        "files": fingerprint[current],
        "release_files": fingerprint,
    }
    state.write_text(json.dumps(expected))
    state.chmod(0o600)
    release.atomic_current(current, control=root)
    original_current = release.active_revision
    original_atomic = release.atomic_current
    monkeypatch.setattr(release, "CONTROL", root)
    monkeypatch.setattr(release, "STATE", state)
    monkeypatch.setattr(release, "RELEASES", root / "releases")
    monkeypatch.setattr(release, "active_revision", lambda: original_current(root))
    monkeypatch.setattr(
        release, "atomic_current", lambda revision: original_atomic(revision, control=root)
    )
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"active": "active", "pid": "77"}})

    def old_doctor(directory: Path) -> None:
        if directory.name == previous:
            raise ValueError("pinned-release doctor did not prove source parity")

    monkeypatch.setattr(release, "_installed_doctor", old_doctor)
    with pytest.raises(ValueError, match="rollback target fails current registry"):
        release.rollback()
    assert original_current(root) == current
    assert json.loads(state.read_text()) == expected
