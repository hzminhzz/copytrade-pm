"""SQLite is the authoritative wallet metadata ledger, even with additive cohorts.

These tests never touch the owner's registry, service units or private artifacts.
"""

from __future__ import annotations

from contextlib import closing, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as registry
from test_wallet_registry import fixture

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "registry_release.py"
SPEC = importlib.util.spec_from_file_location("registry_authority_release", SCRIPT)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def _with_extra_cohort(tmp_path: Path) -> Path:
    _root, snapshot = fixture(tmp_path)
    db = tmp_path / "registry" / "test.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    with closing(registry.connect(db, True)) as con:
        wallet = con.execute("SELECT wallet_id FROM wallets ORDER BY wallet_id LIMIT 1").fetchone()[
            0
        ]
        con.execute(
            "INSERT INTO cohorts VALUES (?,?,?)",
            ("ml4t-top6", 1, "ml4t_institutional_screen_20261105"),
        )
        con.execute(
            "INSERT INTO cohort_memberships VALUES (?,?,?,?)",
            ("ml4t-top6", 1, wallet, "2026-11-05T00:00:00+00:00"),
        )
        con.commit()
    return db


def test_sqlite_authority_keeps_additive_non_csv_cohorts(tmp_path: Path) -> None:
    db = _with_extra_cohort(tmp_path)
    authority = registry.db_authority_health(db)
    assert authority["database_integrity"] == "VERIFIED"
    assert authority["authority"] == "SQLITE"
    assert authority["schema_version"] >= 8
    assert authority["research_cohorts"]["ml4t-top6"] == 1
    assert authority["unverified_cohort_import_provenance"] == ["ml4t-top6"]
    assert not authority["scientifically_qualified"]
    assert len(authority["inventory_sha256"]) == 64


def test_doctor_does_not_require_legacy_import_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _with_extra_cohort(tmp_path)

    def must_not_collect(*_a, **_k):
        raise AssertionError("legacy importer must not gate authoritative doctor")

    monkeypatch.setattr(registry, "collect", must_not_collect)
    output = io.StringIO()
    with redirect_stdout(output):
        code = registry.cli(["--db", str(db), "doctor"])
    report = json.loads(output.getvalue())
    assert code == 0
    assert report["database_integrity"] == "VERIFIED"
    assert report["legacy_inputs"]["status"] == "NOT_REQUESTED"
    assert report["indexed_research_unique"] == registry.db_status(db)["counts"]["research_unique"]
    assert report["unverified_cohort_import_provenance"] == ["ml4t-top6"]
    assert report["inventory_sha256"] == registry.db_authority_health(db)["inventory_sha256"]


def test_authoritative_inventory_sha_changes_with_additive_membership(tmp_path: Path) -> None:
    db = _with_extra_cohort(tmp_path)
    first = registry.db_authority_health(db)
    # Adding a distinct real registry cohort is an independent new generation,
    # regardless of whether the last import-file manifest was updated.
    with closing(registry.connect(db, True)) as con:
        wallet = con.execute(
            "SELECT wallet_id FROM wallets ORDER BY wallet_id DESC LIMIT 1"
        ).fetchone()[0]
        con.execute("INSERT INTO cohorts VALUES (?,?,?)", ("additional", 1, "a" * 64))
        con.execute(
            "INSERT INTO cohort_memberships VALUES (?,?,?,?)",
            ("additional", 1, wallet, "2026-11-05T00:00:00+00:00"),
        )
        con.commit()
    later = registry.db_authority_health(db)
    assert later["inventory_sha256"] != first["inventory_sha256"]
    assert later["last_legacy_import_sha256"] == first["last_legacy_import_sha256"]


def test_dynamic_sqlite_only_cohort_discovery(tmp_path: Path) -> None:
    db = _with_extra_cohort(tmp_path)
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = registry.cli(["--db", str(db), "cohort", "ml4t-top6"])
    view = json.loads(stream.getvalue())
    assert code == 0
    assert view["registered"] is True
    assert view["count"] == 1
    assert view["authority"] == "SQLITE"
    assert view["provenance"] == "UNVERIFIED_IMPORT_LABEL"
    assert not view["scientifically_qualified"]


def test_database_integrity_failure_is_terminal_for_doctor(tmp_path: Path) -> None:
    db = _with_extra_cohort(tmp_path)
    with closing(sqlite3.connect(db)) as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("DELETE FROM wallets WHERE wallet_id=(SELECT MIN(wallet_id) FROM wallets)")
        con.commit()
    with pytest.raises(ValueError, match="FOREIGN_KEYS_FAILED"):
        registry.db_authority_health(db)
    stream = io.StringIO()
    with redirect_stdout(stream):
        result = registry.cli(["--db", str(db), "doctor"])
    assert result == 2
    assert json.loads(stream.getvalue())["database_integrity"] == "FAILED"


def test_release_preview_consults_database_not_legacy_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _with_extra_cohort(tmp_path)
    monkeypatch.setattr(registry, "DB", db)

    def blocked_legacy(*_a, **_k):
        raise AssertionError("release must not consult CSV as authority")

    monkeypatch.setattr(registry, "collect", blocked_legacy)
    report = release.readonly_source_health()
    assert report["authority"] == "SQLITE"
    assert report["database_integrity"] == "VERIFIED"
    assert report["unverified_cohort_import_provenance"] == ["ml4t-top6"]
    assert report["inventory_sha256"] == registry.db_authority_health(db)["inventory_sha256"]


def test_optional_legacy_audit_does_not_overrule_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _with_extra_cohort(tmp_path)

    def legacy_unavailable(*_a, **_k):
        raise FileNotFoundError("legacy-only fixture unavailable")

    monkeypatch.setattr(registry, "collect", legacy_unavailable)
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = registry.cli(["--db", str(db), "doctor", "--legacy-audit"])
    result = json.loads(stream.getvalue())
    assert code == 0
    assert result["database_integrity"] == "VERIFIED"
    assert result["legacy_inputs"]["status"] == "UNAVAILABLE"
    assert result["unverified_cohort_import_provenance"] == ["ml4t-top6"]


def test_release_inventory_parity_detects_concurrent_sqlite_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "readonly_source_health", lambda: {"inventory_sha256": "b" * 64})
    with pytest.raises(RuntimeError, match="inventory changed"):
        release.inventory_parity({"inventory_sha256": "a" * 64})
    release.inventory_parity({"inventory_sha256": "b" * 64})


def test_emergency_deactivation_is_pointer_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = tmp_path / "owner" / "release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    releases = control / "releases"
    releases.mkdir(mode=0o700)
    previous = "a" * 40
    pinned = releases / previous
    pinned.mkdir(mode=0o700)
    (pinned / "src.py").write_text("read-only")
    from hashlib import sha256

    files = {"src.py": sha256(b"read-only").hexdigest()}
    pointer = release.atomic_current
    resolve = release.active_revision
    pointer(previous, control=control)
    metadata = control / "release-state.json"
    metadata.write_text(
        json.dumps(
            {
                "current": previous,
                "previous": None,
                "files": files,
                "release_files": {previous: files},
            }
        )
    )
    metadata.chmod(0o600)
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "RELEASES", releases)
    monkeypatch.setattr(release, "STATE", metadata)
    monkeypatch.setattr(release, "atomic_current", lambda rev: pointer(rev, control=control))
    monkeypatch.setattr(release, "active_revision", lambda: resolve(control))
    monkeypatch.setattr(release, "services", lambda: {"tracker": {"active": "active", "pid": "57"}})
    before = metadata.read_bytes()
    report = release.deactivate()
    assert report["result"] == "READ_ONLY_POINTER_DEACTIVATED"
    assert report["registry_db_untouched"] is True
    assert resolve(control) is None
    assert not (control / "current").exists()
    assert pinned.exists()
    assert json.loads(metadata.read_text())["previous"] == previous
    assert metadata.read_bytes() != before


def test_doctor_fails_closed_without_sqlite(tmp_path: Path) -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        code = registry.cli(["--db", str(tmp_path / "absent.sqlite"), "doctor"])
    report = json.loads(output.getvalue())
    assert code == 2
    assert report["database_integrity"] == "FAILED"
