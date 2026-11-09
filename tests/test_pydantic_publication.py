"""Crash faults at the real signed-publication and writer boundaries."""

import asyncio
import json
import multiprocessing
import os
import stat
import threading

import pytest

from copytrade_pm.pm_forward_continuous_transport import SerialWriter
from copytrade_pm.production_manifest import verify
from copytrade_pm.v4_source_export import _atomic_private_output
from copytrade_pm.v4_source_spool import capture_once
from test_pm_forward_observed_paper import ADDRESSES
from test_v4_source_export import observer, source_event
from test_v4_source_spool import provision


def test_final_packet_is_not_visible_until_file_fsync_completes(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "packet.json"
    original = os.fsync
    observed = []

    def fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            observed.append(target.exists())
            assert not target.exists(), "PARTIAL_FINAL_PACKET_VISIBLE"
        return original(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    _atomic_private_output(target, b'{"complete":true}')
    assert observed == [False]
    assert target.read_bytes() == b'{"complete":true}'


def test_repeated_submitter_cancellation_drains_admitted_commit():
    async def run():
        entered, release, complete = threading.Event(), threading.Event(), threading.Event()

        def commit():
            entered.set()
            assert release.wait(2)
            complete.set()
            return "durable"

        async with SerialWriter() as writer:
            submit = asyncio.create_task(writer.submit(commit))
            await asyncio.to_thread(entered.wait, 1)
            submit.cancel()
            await asyncio.sleep(0)
            submit.cancel()
            await asyncio.sleep(0)
            assert not submit.done(), "CANCELED_BEFORE_DURABLE_COMMIT"
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await submit
            assert complete.is_set()

    asyncio.run(run())


def test_cancel_before_admission_has_no_effect():
    async def run():
        committed = []
        async with SerialWriter() as writer:
            submit = asyncio.create_task(writer.submit(lambda: committed.append("unexpected")))
            submit.cancel()
            with pytest.raises(asyncio.CancelledError):
                await submit
        assert committed == []

    asyncio.run(run())


def _crash_capture(kwargs, point):
    from copytrade_pm import v4_source_spool as spool

    real_fsync, real_link = os.fsync, os.link
    real_output = spool._atomic_private_output

    def fsync(fd):
        is_file = stat.S_ISREG(os.fstat(fd).st_mode)
        if is_file and point == "before_file_fsync":
            os._exit(42)
        real_fsync(fd)
        if (is_file and point == "after_file_fsync") or (
            not is_file and point == "after_directory_fsync"
        ):
            os._exit(42)

    def link(src, dst, **options):
        if point == "before_publish":
            os._exit(42)
        real_link(src, dst, **options)
        if point == "after_publish":
            os._exit(42)

    def output(path, payload, **options):
        if path.name == "cursor.json" and point == "before_cursor":
            os._exit(42)
        real_output(path, payload, **options)
        if path.name == "cursor.json" and point == "after_cursor":
            os._exit(42)

    os.fsync, os.link, spool._atomic_private_output = fsync, link, output
    capture_once(**kwargs)
    os._exit(0)


@pytest.mark.parametrize(
    "point",
    [
        "before_file_fsync",
        "after_file_fsync",
        "before_publish",
        "after_publish",
        "after_directory_fsync",
        "before_cursor",
        "after_cursor",
    ],
)
def test_cf04_real_process_crashes_never_publish_partial_or_skip_event(
    tmp_path, monkeypatch, point
):
    from copytrade_pm import v4_source_spool as spool

    monkeypatch.setattr(spool, "selected_parents", lambda *a, **k: {"S035": ADDRESSES["S035"]})
    journal, source = observer(tmp_path)
    root, key, seed, pin = provision(tmp_path)
    kwargs = dict(
        registry_db=tmp_path / "registry.sqlite",
        journal_db=journal.path,
        root=root,
        signing_key=seed,
        public_key=pin,
        portfolios=("P1",),
    )
    capture_once(**kwargs)
    previous_cursor = json.loads((root / "cursor.json").read_bytes())["cursors"]["S035"]
    source_event(source, 10, 20)
    process = multiprocessing.get_context("fork").Process(
        target=_crash_capture, args=(kwargs, point)
    )
    process.start()
    process.join(5)
    assert not process.is_alive()
    assert process.exitcode == 42
    packets = list((root / "outbox").glob("*.json"))
    for path in packets:
        packet = json.loads(path.read_bytes())
        assert verify(packet["batch_envelope"], key.public_key(), "source-observer-v4-batch")
    cursor = json.loads((root / "cursor.json").read_bytes())["cursors"]["S035"]
    assert cursor in (previous_cursor, previous_cursor + 1)
    if cursor > previous_cursor:
        assert any(json.loads(p.read_bytes())["events"]["S035"] for p in packets)
    capture_once(**kwargs)
    assert json.loads((root / "cursor.json").read_bytes())["cursors"]["S035"] == previous_cursor + 1
    all_events = [
        e
        for p in (root / "outbox").glob("*.json")
        for e in json.loads(p.read_bytes())["events"]["S035"]
    ]
    assert all_events
    assert {e["proof"]["payload"]["stream_cursor"] for e in all_events} == {previous_cursor + 1}
    assert len({e["proof"]["sha256"] for e in all_events}) == 1
    assert capture_once(**kwargs)["state"] == "NO_NEW_VERIFIED_EVENTS"


@pytest.mark.parametrize("point", ["after_publish", "before_cursor"])
def test_bootstrap_crash_recovers_signed_cutoff_without_backfilling(tmp_path, monkeypatch, point):
    from copytrade_pm import v4_source_spool as spool

    monkeypatch.setattr(spool, "selected_parents", lambda *a, **k: {"S035": ADDRESSES["S035"]})
    journal, source = observer(tmp_path)
    source_event(source, 10, 20)
    root, key, seed, pin = provision(tmp_path)
    kwargs = dict(
        registry_db=tmp_path / "registry.sqlite",
        journal_db=journal.path,
        root=root,
        signing_key=seed,
        public_key=pin,
        portfolios=("P1",),
    )
    process = multiprocessing.get_context("fork").Process(
        target=_crash_capture, args=(kwargs, point)
    )
    process.start()
    process.join(5)
    assert process.exitcode == 42
    assert not (root / "cursor.json").exists()
    assert capture_once(**kwargs)["state"] == "NO_NEW_VERIFIED_EVENTS"
    assert json.loads((root / "cursor.json").read_bytes())["cursors"]["S035"] == 3
    source_event(source, 20, 21)
    assert capture_once(**kwargs)["events"] == 1
    for path in (root / "outbox").glob("*.json"):
        packet = json.loads(path.read_bytes())
        assert verify(packet["batch_envelope"], key.public_key(), "source-observer-v4-batch")
        assert all(e["proof"]["payload"]["stream_cursor"] == 4 for e in packet["events"]["S035"])


def test_bootstrap_signature_or_identity_tampering_is_not_recovery(tmp_path, monkeypatch):
    from copytrade_pm import v4_source_spool as spool
    from copytrade_pm.production_manifest import canonical
    from hashlib import sha256

    monkeypatch.setattr(spool, "selected_parents", lambda *a, **k: {"S035": ADDRESSES["S035"]})
    journal, _source = observer(tmp_path)
    root, _key, seed, pin = provision(tmp_path)
    kwargs = dict(
        registry_db=tmp_path / "registry.sqlite",
        journal_db=journal.path,
        root=root,
        signing_key=seed,
        public_key=pin,
        portfolios=("P1",),
    )
    capture_once(**kwargs)
    (root / "cursor.json").unlink()
    path = next((root / "outbox").glob("*.json"))
    packet = json.loads(path.read_bytes())
    packet["head_cursors"]["S035"] += 10
    payload = canonical(packet)
    tampered = path.with_name(
        path.name.split("-")[0] + "-" + sha256(payload).hexdigest()[:16] + ".json"
    )
    path.unlink()
    tampered.write_bytes(payload)
    tampered.chmod(0o600)
    with pytest.raises(ValueError):
        capture_once(**kwargs)
    assert not (root / "cursor.json").exists()


def test_cancelled_observer_commit_has_no_orphaned_receipt(tmp_path, monkeypatch):
    from copytrade_pm.pm_forward_stream_journal import verify_streams
    from test_pm_forward_persistent_source import account, shifted, T

    source, journal = account(tmp_path)
    entered, release = threading.Event(), threading.Event()
    append = journal.append_source_receipt

    def gated(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return append(*args, **kwargs)

    monkeypatch.setattr(journal, "append_source_receipt", gated)

    async def run():
        async with SerialWriter() as writer:
            job = asyncio.create_task(
                writer.submit(lambda: source.observe(shifted(0, "20"), T.isoformat()))
            )
            await asyncio.to_thread(entered.wait, 1)
            job.cancel()
            await asyncio.sleep(0)
            job.cancel()
            await asyncio.sleep(0)
            assert not job.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await job
        assert source.progress.head["cursor"] == 2
        assert journal.source_status("test")["cursor"] == 1
        assert source.observe(shifted(0, "20"), T.isoformat())["classification"] == "DUPLICATE"
        assert verify_streams(journal.path)["integrity"] == "VERIFIED"

    asyncio.run(run())
