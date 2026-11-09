"""Real native artifact/SQLite crash cuts; synthetic private registry only."""

from contextlib import closing
from hashlib import sha256
import multiprocessing
import os
from pathlib import Path
import stat

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_native as native
from test_wallet_registry_native import NOW, manifest, seed


def prepared(tmp_path):
    db, _, initial = seed(tmp_path)
    locked = native.lock_legacy_import(db, expected=initial, apply=True, now=NOW)
    source = manifest(tmp_path)
    return db, source, locked["inventory_sha256"]


def test_native_artifact_namespace_is_durable_before_sqlite_commit(tmp_path, monkeypatch):
    db, source, baseline = prepared(tmp_path)
    synced = set()
    fsync, connect = os.fsync, registry.connect

    def observe_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced.add(Path(os.readlink(f"/proc/self/fd/{fd}")))
        return fsync(fd)

    def guarded_connect(path, writable):
        if Path(path) == db and writable:
            assert {
                db.parent,
                db.parent / "evidence",
                db.parent / "evidence/native-cohorts",
            } <= synced
        return connect(path, writable)

    monkeypatch.setattr(os, "fsync", observe_sync)
    monkeypatch.setattr(registry, "connect", guarded_connect)
    result = native.register_cohort(db, source, expected=baseline, apply=True, now=NOW)
    assert result["applied"]
    assert registry.db_authority_health(db)["database_integrity"] == "VERIFIED"


@pytest.mark.parametrize(
    "cut",
    [
        "before_file_sync",
        "after_file_sync",
        "after_link",
        "after_directory_sync",
        "before_sql_commit",
        "after_sql_commit",
    ],
)
def test_native_artifact_and_metadata_crash_recovery_preserves_one_version(tmp_path, cut):
    db, source, baseline = prepared(tmp_path)
    original = source.read_bytes()
    target = db.parent / "evidence/native-cohorts" / (sha256(original).hexdigest() + ".json")
    initial_status = registry.db_status(db)

    def child():
        fsync, link, connect = os.fsync, os.link, registry.connect

        def fault_sync(fd):
            path = Path(os.readlink(f"/proc/self/fd/{fd}"))
            partial = path.parent == target.parent and path.suffix == ".partial"
            if partial and cut == "before_file_sync":
                os._exit(42)
            result = fsync(fd)
            if partial and cut == "after_file_sync":
                os._exit(42)
            if path == target.parent and cut == "after_directory_sync":
                os._exit(42)
            return result

        def fault_link(a, b, **kwargs):
            result = link(a, b, **kwargs)
            if Path(b) == target and cut == "after_link":
                os._exit(42)
            return result

        class Connection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, key):
                return getattr(self.connection, key)

            def __enter__(self):
                self.connection.__enter__()
                return self

            def __exit__(self, typ, value, traceback):
                if typ is None and cut == "before_sql_commit":
                    os._exit(42)
                result = self.connection.__exit__(typ, value, traceback)
                if typ is None and cut == "after_sql_commit":
                    os._exit(42)
                return result

        def fault_connect(path, writable):
            result = connect(path, writable)
            return Connection(result) if Path(path) == db and writable else result

        os.fsync, os.link, registry.connect = fault_sync, fault_link, fault_connect
        native.register_cohort(db, source, expected=baseline, apply=True, now=NOW)

    process = multiprocessing.get_context("fork").Process(target=child)
    process.start()
    process.join(15)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail("native crash child timed out")
    assert process.exitcode == 42
    health = registry.db_authority_health(db)
    assert health["database_integrity"] == "VERIFIED"
    if cut != "after_sql_commit":
        assert health["inventory_sha256"] == baseline
        assert registry.db_status(db) == initial_status
    else:
        assert health["inventory_sha256"] != baseline
    if target.exists():
        assert target.read_bytes() == original
    retried = native.register_cohort(
        db, source, expected=health["inventory_sha256"], apply=True, now=NOW
    )
    assert retried.get("version", 1) == 1
    assert target.read_bytes() == original
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute("SELECT COUNT(*) FROM cohorts WHERE cohort_id='native-wave'").fetchone()[0]
            == 1
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM evidence_versions WHERE source_key='sqlite_primary:native-wave'"
            ).fetchone()[0]
            == 1
        )
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert (
        registry.db_status(db)["counts"]["current_research_selection"]
        == initial_status["counts"]["current_research_selection"]
    )
    assert source.read_bytes() == original


def test_unreferenced_conflicting_archive_never_promotes_native_metadata(tmp_path):
    db, source, baseline = prepared(tmp_path)
    root = db.parent / "evidence"
    root.mkdir(mode=0o700)
    category = root / "native-cohorts"
    category.mkdir(mode=0o700)
    target = category / (sha256(source.read_bytes()).hexdigest() + ".json")
    target.write_bytes(b"partial or conflicting orphan")
    target.chmod(0o600)
    with pytest.raises(ValueError, match="NATIVE_EVIDENCE_CONFLICT"):
        native.register_cohort(db, source, expected=baseline, apply=True, now=NOW)
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline
    assert target.read_bytes() == b"partial or conflicting orphan"


def test_competing_nonprivate_archive_cannot_commit_metadata(tmp_path, monkeypatch):
    db, source, baseline = prepared(tmp_path)
    link = os.link

    def untrusted_race(partial, target, **kwargs):
        if Path(target).parent.name != "native-cohorts":
            return link(partial, target, **kwargs)
        Path(target).write_bytes(Path(partial).read_bytes())
        Path(target).chmod(0o644)
        raise FileExistsError("synthetic competing publication")

    monkeypatch.setattr(os, "link", untrusted_race)
    with pytest.raises(ValueError, match="NATIVE_EVIDENCE_CONFLICT"):
        native.register_cohort(db, source, expected=baseline, apply=True, now=NOW)
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline
