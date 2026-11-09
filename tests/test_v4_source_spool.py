"""Source signed packet spool must preserve selected scope and replay cutoff."""

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.production_manifest import digest, verify
from copytrade_pm.v4_source_spool import capture_once
from test_pm_forward_observed_paper import ADDRESSES
from test_v4_source_export import observer, source_event


def provision(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    seed = root / "seed"
    pin = root / "public"
    seed.write_bytes(key.private_bytes_raw())
    pin.write_bytes(key.public_key().public_bytes_raw())
    seed.chmod(0o600)
    pin.chmod(0o600)
    return root, key, seed, pin


def test_first_source_packet_is_signed_no_retroactive_entry(tmp_path, monkeypatch):
    from copytrade_pm import v4_source_spool as spool

    monkeypatch.setattr(
        spool,
        "selected_parents",
        lambda *args, **kwargs: {"S035": ADDRESSES["S035"]},
    )
    journal, source = observer(tmp_path)
    source_event(source, 10, 20)
    root, key, seed, pin = provision(tmp_path)

    def capture():
        return capture_once(
            registry_db=tmp_path / "registry.sqlite",
            journal_db=journal.path,
            root=root,
            signing_key=seed,
            public_key=pin,
            portfolios=("P1",),
        )

    assert capture()["events"] == 0
    first = list((root / "outbox").iterdir())
    assert len(first) == 1
    packet = json.loads(first[0].read_bytes())
    proof = verify(packet["batch_envelope"], key.public_key(), "source-observer-v4-batch")
    assert proof["events_sha"] == digest(packet["events"])
    assert proof["selected"] == {"S035": ADDRESSES["S035"]}
    assert packet["events"]["S035"] == []
    assert json.loads((root / "cursor.json").read_bytes())["cursors"]["S035"] == 3

    source_event(source, 20, 25)
    assert capture()["events"] == 1
    packets = sorted((root / "outbox").iterdir())
    assert len(packets) == 2
    second = json.loads(packets[-1].read_bytes())
    assert (
        second["events"]["S035"][0]["proof"]["payload"]["classification"] == "OBSERVED_STATE_CHANGE"
    )
    assert verify(second["batch_envelope"], key.public_key(), "source-observer-v4-batch")
    assert capture()["state"] == "NO_NEW_VERIFIED_EVENTS"
    assert len(list((root / "outbox").iterdir())) == 2


def test_spool_rejects_missing_cursor_with_history_and_changed_key(tmp_path, monkeypatch):
    from copytrade_pm import v4_source_spool as spool

    monkeypatch.setattr(
        spool,
        "selected_parents",
        lambda *args, **kwargs: {"S035": ADDRESSES["S035"]},
    )
    journal, source = observer(tmp_path)
    root, _key, seed, pin = provision(tmp_path)

    def capture():
        return capture_once(
            registry_db=tmp_path / "registry.sqlite",
            journal_db=journal.path,
            root=root,
            signing_key=seed,
            public_key=pin,
            portfolios=("P1",),
        )

    capture()
    (root / "cursor.json").unlink()
    assert capture()["state"] == "NO_NEW_VERIFIED_EVENTS"  # Authenticated empty bootstrap only.
    source_event(source, 10, 20)
    capture()
    (root / "cursor.json").unlink()
    with pytest.raises(ValueError, match="STATE_MISSING"):
        capture()

    root2 = tmp_path / "private2"
    root2.mkdir(mode=0o700)
    seed2 = root2 / "seed"
    pin2 = root2 / "public"
    seed2.write_bytes(seed.read_bytes())
    pin2.write_bytes(bytes([b ^ 0x04 for b in pin.read_bytes()]))
    seed2.chmod(0o600)
    pin2.chmod(0o600)
    with pytest.raises(ValueError, match="PIN"):
        capture_once(
            registry_db=tmp_path / "registry.sqlite",
            journal_db=journal.path,
            root=root2,
            signing_key=seed2,
            public_key=pin2,
            portfolios=("P1",),
        )
