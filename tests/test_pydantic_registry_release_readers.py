"""Concurrent read-only release readers cannot observe a mixed trusted generation."""

from hashlib import sha256
import multiprocessing
import os

import pytest

from test_wallet_registry_release import release


def configured(tmp_path, monkeypatch):
    control = tmp_path / "owner/release-control"
    control.parent.mkdir(mode=0o700)
    control.mkdir(mode=0o700)
    releases = control / "releases"
    releases.mkdir(mode=0o700)
    old, new = "a" * 40, "b" * 40
    states = {}
    for revision in (old, new):
        folder = releases / revision
        folder.mkdir(mode=0o700)
        raw = revision.encode()
        (folder / "synthetic.py").write_bytes(raw)
        states[revision] = {"current": revision, "files": {"synthetic.py": sha256(raw).hexdigest()}}
    pointer, active = release.atomic_current, release.active_revision
    monkeypatch.setattr(release, "CONTROL", control)
    monkeypatch.setattr(release, "STATE", control / "release-state.json")
    monkeypatch.setattr(release, "RELEASES", releases)
    monkeypatch.setattr(
        release, "atomic_current", lambda revision: pointer(revision, control=control)
    )
    monkeypatch.setattr(release, "active_revision", lambda: active(control))
    # Only source fingerprint, pointer, state and real OS locking are under test.
    # This never calls an installed CLI or any live services.
    monkeypatch.setattr(release, "_installed_doctor", lambda _: None)
    monkeypatch.setattr(release, "readonly_source_health", lambda: {"synthetic_fixture": True})
    release.atomic_current(old)
    release._write_json_atomic(release.STATE, states[old])
    return old, new, states


def test_concurrent_reader_blocks_during_pointer_metadata_switch(tmp_path, monkeypatch):
    old, new, states = configured(tmp_path, monkeypatch)
    assert release.verify()["revision"] == old
    context = multiprocessing.get_context("fork")
    switched, resume = context.Event(), context.Event()

    def child():
        def pause():
            switched.set()
            if not resume.wait(10):
                os._exit(43)

        with release.release_lock():
            release.commit_release(new, states[new], after_switch=pause)

    process = context.Process(target=child)
    process.start()
    try:
        assert switched.wait(10)
        with pytest.raises(RuntimeError, match="already in progress"):
            release.verify()
        # Direct metadata/pointer reads disagree during this interval; the
        # supported reader must never report either as a coherent release.
        assert release.active_revision() == new
        assert release._json(release.STATE)["current"] == old
    finally:
        resume.set()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
    assert process.exitcode == 0
    assert release.verify()["revision"] == new


def test_crash_after_release_metadata_commit_preserves_new_coherent_generation(
    tmp_path, monkeypatch
):
    _, new, states = configured(tmp_path, monkeypatch)

    def child():
        with release.release_lock():
            release.commit_release(new, states[new])
            os._exit(42)

    process = multiprocessing.get_context("fork").Process(target=child)
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail("release child timed out")
    assert process.exitcode == 42
    assert release.verify()["revision"] == new
    assert release.repair()["result"] == "NO_POINTER_DIVERGENCE"
