"""CF04/CF13: real producer files and separately owned offline Guardian code.

Requires the reviewed V4 consumer src/tests on PYTHONPATH. All journals, release
floors, keys and FakeBroker objects are temporary fixtures; no protected runtime
is opened and no real broker is reachable.
"""

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
import multiprocessing
import os
import sqlite3

import pytest

from copytrade_pm import v4_source_spool as spool
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.production_manifest import sign, verify
from copytrade_pm.v4_source_export import export_signed_events
from test_pydantic_publication import _crash_capture
from test_pm_forward_observed_paper import ADDRESSES
from test_v4_source_export import observer, source_event
from test_v4_source_spool import provision

pytest.importorskip("prop_production.v4_source_receiver", reason="Required V4 cross-repo gate")
from prop_production.v4_source_receiver import SourcePacketReceiver
from test_pydantic_crossrepo_contracts import accepted_release


def child_exit(fn, expected):
    process = multiprocessing.get_context("fork").Process(target=fn)
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail("fault subprocess did not terminate")
    assert process.exitcode == expected


@pytest.mark.parametrize(
    "cut",
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
def test_cf04_spool_crash_then_consumer_commit_lost_ack_is_idempotent(tmp_path, monkeypatch, cut):
    monkeypatch.setattr(spool, "selected_parents", lambda *a, **k: {"S035": ADDRESSES["S035"]})
    journal, source = observer(tmp_path)
    root, key, seed, pin = provision(tmp_path)
    args = dict(
        registry_db=tmp_path / "registry.sqlite",
        journal_db=journal.path,
        root=root,
        signing_key=seed,
        public_key=pin,
        portfolios=("P1",),
    )
    spool.capture_once(**args)
    bootstrap = next((root / "outbox").glob("*.json")).read_bytes()
    source_event(source, 10, 20)
    exported = export_signed_events(
        journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key, after={"S035": 2}
    )
    book = verify(exported["events"]["S035"][0]["book"], key.public_key(), "source-observer")
    release = accepted_release(book, key)
    known = book["known_at_ms"]
    path = tmp_path / "receiver.sqlite"
    receiver = SourcePacketReceiver(path, release=release, source_key=key.public_key())
    receiver.ingest(bootstrap, now_ms=known - 1)
    receiver.close()
    child_exit(lambda: _crash_capture(args, cut), 42)
    spool.capture_once(**args)
    packets = [
        p
        for p in sorted((root / "outbox").glob("*.json"))
        if json.loads(p.read_bytes())["events"]["S035"]
    ]
    assert packets
    exact = {p: p.read_bytes() for p in packets}

    def consumed_without_ack():
        resumed = SourcePacketReceiver(path, release=release, source_key=key.public_key())
        resumed.ingest(packets[0].read_bytes(), now_ms=known)
        os._exit(96)

    child_exit(consumed_without_ack, 96)
    receiver = SourcePacketReceiver(path, release=release, source_key=key.public_key())
    assert receiver.ingest(packets[0].read_bytes(), now_ms=known + 1)["state"] == "DUPLICATE"
    for packet in packets[1:]:
        receiver.ingest(packet.read_bytes(), now_ms=known + 1)
    assert receiver.due(now_ms=known + 299999) == []
    actions = receiver.due(now_ms=known + 300000)
    assert len(actions) == 1
    assert actions[0]["first_known_ms"] == known
    assert actions[0]["trading_authorized"] is False
    receiver.close()
    receiver = SourcePacketReceiver(path, release=release, source_key=key.public_key())
    assert receiver.due(now_ms=known + 300001) == []
    receiver.close()
    assert all(p.read_bytes() == raw for p, raw in exact.items())


def test_cf13_packet_selection_repin_restart_cannot_clear_independent_guardian_halt(
    tmp_path, monkeypatch
):
    from prop_production.journal import Journal
    from prop_production.release import VerifiedRelease
    from prop_production.evidence import canonical, digest as protected_digest
    from test_v4_guardian_shadow import guardian_and_projection, NATIVE
    from test_v4_timing import IDENTITY

    guardian, old_projection, key, broker, finance, floor = guardian_and_projection(tmp_path)
    old_projection.close()
    root, _, seed, pin = provision(tmp_path)
    seed.write_bytes(key.private_bytes_raw())
    pin.write_bytes(key.public_key().public_bytes_raw())
    journal = PaperJournal(tmp_path / "source")
    source = PersistentAccount(
        journal=journal,
        alias="pod-a",
        address=IDENTITY,
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="pod-a",
        scope_sha=digest(["scope", IDENTITY]),
    )

    def iso(ms):
        return datetime.fromtimestamp(ms / 1000, UTC).isoformat()

    def observe(ms, quantity):
        positions = (
            []
            if quantity == 0
            else [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": str(quantity),
                        "positionValue": str(quantity * 100),
                    }
                }
            ]
        )
        frame = {
            "channel": "allDexsClearinghouseState",
            "data": {
                "user": IDENTITY,
                "clearinghouseStates": [
                    [
                        "",
                        {
                            "marginSummary": {
                                "accountValue": "1000",
                                "totalNtlPos": "2000",
                                "totalMarginUsed": "10",
                            },
                            "assetPositions": positions,
                            "time": ms - 1,
                        },
                    ]
                ],
            },
        }
        raw = json.dumps(frame, separators=(",", ":"))
        source.observe(frame, iso(ms), raw_sha=sha256(raw.encode()).hexdigest(), raw_text=raw)

    source.begin(iso(100))
    observe(101, 0)
    selected = {"pod-a": IDENTITY}
    monkeypatch.setattr(spool, "selected_parents", lambda *a, **k: selected)
    args = dict(
        registry_db=tmp_path / "registry.sqlite",
        journal_db=journal.path,
        root=root,
        signing_key=seed,
        public_key=pin,
        portfolios=("P1",),
    )
    spool.capture_once(**args)
    bootstrap = next((root / "outbox").glob("*.json")).read_bytes()
    path = tmp_path / "receiver.sqlite"
    receiver = SourcePacketReceiver(path, release=guardian.release, source_key=key.public_key())
    receiver.ingest(bootstrap, now_ms=150)
    receiver.close()
    finance.halt("CF13_FINANCIAL_HALT", 151)
    halted = finance.snapshot()
    observe(200, 20)
    spool.capture_once(**args)
    packet_path = sorted((root / "outbox").glob("*.json"))[-1]
    original = packet_path.read_bytes()

    # A separately represented new release is deliberately not activated.
    # The old receiver must reject the changed release before source consumption.
    changed = deepcopy(guardian.release.payload)
    changed["generation"] += 1
    changed["members"][0]["k"] = "0.05"
    proposed = VerifiedRelease(canonical(changed), protected_digest(changed), "approver")
    # The separately pinned consumer opens a handle before rejecting a release
    # mismatch. Retain only test-owned handles for cleanup, without suppressing
    # warnings or changing the consumer authority/validation code.
    rejected_handles = []
    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        rejected_handles.append(connection)
        return connection

    with monkeypatch.context() as cleanup:
        cleanup.setattr(sqlite3, "connect", tracked_connect)
        try:
            with pytest.raises(ValueError, match="RELEASE_OR_CUTOFF_CHANGED"):
                SourcePacketReceiver(path, release=proposed, source_key=key.public_key())
        finally:
            for connection in rejected_handles:
                connection.close()
    receiver = SourcePacketReceiver(path, release=guardian.release, source_key=key.public_key())
    rebound = json.loads(original)
    binding = rebound["batch_envelope"]["payload"]
    binding["selected"] = {"renamed": IDENTITY}
    rebound["batch_envelope"] = sign(binding, key, "source-observer-v4-batch")
    with pytest.raises(ValueError, match="HEAD_SCHEMA|SELECTION|ALIAS"):
        receiver.ingest(canonical(rebound), now_ms=200)
    assert finance.snapshot() == halted
    assert receiver.ingest(original, now_ms=200)["events"] == 1
    receiver.close()
    receiver = SourcePacketReceiver(path, release=guardian.release, source_key=key.public_key())
    assert receiver.ingest(original, now_ms=201)["state"] == "DUPLICATE"
    assert receiver.due(now_ms=300199) == []
    action = receiver.due(now_ms=300200)[0]
    finance.close()
    restarted_finance = Journal(tmp_path / "account.sqlite", "fixture-account")
    guardian.journal = restarted_finance
    decision = guardian.preview_v4(
        receiver.projector,
        action["action_id"],
        {NATIVE: {"bid": "10000", "ask": "10030", "known_at_ms": 300200}},
        300200,
    )
    assert decision.data["status"] == "BLOCKED"
    assert "CF13_FINANCIAL_HALT" in decision.data["reasons"]
    with pytest.raises(ValueError, match="RESERVATION_NOT_PERMITTED"):
        guardian.reserve(decision.data["decision_id"], 300200)
    assert restarted_finance.snapshot()["halts"] == halted["halts"]
    assert not restarted_finance.snapshot()["intents"]
    assert not restarted_finance.snapshot()["reservations"]
    assert not broker.audit()
    assert packet_path.read_bytes() == original
    receiver.close()
    restarted_finance.close()
    broker.close()
    floor.close()
