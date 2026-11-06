"""Native full-state projection, without treating baseline or gap as trades."""

from copy import deepcopy
from datetime import timedelta

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_forward_source_stream import T, frame
from test_pm_e4_prospective import WALLET, SUB


def account(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    source = PersistentAccount(
        journal=journal,
        alias="test",
        address=WALLET,
        dex_catalog=[None, {"name": "xyz"}],
        subaccounts=None,
        parent_alias="test",
        scope_sha="a" * 64,
    )
    source.begin(T.isoformat())
    return source, journal


def shifted(seconds, qty=None):
    f = frame()
    for _, state in f["data"]["clearinghouseStates"]:
        state["time"] += seconds * 1000
    if qty is not None:
        f["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["szi"] = qty
    return f


def test_baseline_then_change_and_duplicate_do_not_create_economic_effect(tmp_path):
    source, journal = account(tmp_path)
    first = source.observe(frame(), T.isoformat())
    assert first["classification"] == "BASELINE"
    assert first["signal_eligible"] is False
    duplicate = source.observe(frame(), T.isoformat())
    assert duplicate["classification"] == "DUPLICATE"
    assert journal.source_status("test")["cursor"] == 1
    changed = source.observe(shifted(140, "-0.2"), (T + timedelta(seconds=140)).isoformat())
    assert changed["classification"] == "OBSERVED_STATE_CHANGE"
    assert source.checkpoint["positions"]["hyperliquid/mainnet:perp:default/BTC"] == "-0.2"
    assert source.checkpoint["parent_alias"] == "test"
    assert source.checkpoint["source_equity"] is None
    assert journal.source_status("test")["cursor"] == 2
    audit = verify_streams(journal.path)["streams"]["account:test"]
    assert audit["baseline_count"] == 1
    assert audit["observation_count"] == 1
    assert audit["epoch_count"] == 1


@pytest.mark.parametrize(
    "fault", ["wrong", "partial", "delta", "regress", "snapshot_type", "snapshot_top_type"]
)
def test_invalid_frame_never_advances_source_or_projection(tmp_path, fault):
    source, journal = account(tmp_path)
    source.observe(frame(), T.isoformat())
    before = deepcopy(source.checkpoint)
    bad = shifted(1, "0.2")
    if fault == "wrong":
        bad["data"]["user"] = SUB
    if fault == "partial":
        bad["data"]["clearinghouseStates"].pop()
    if fault == "delta":
        bad["data"]["isDelta"] = True
    if fault == "regress":
        bad["data"]["clearinghouseStates"][0][1]["time"] -= 2000
    if fault == "snapshot_type":
        bad["data"]["isSnapshot"] = "true"
    if fault == "snapshot_top_type":
        bad["isSnapshot"] = "true"
    with pytest.raises(ValueError):
        source.observe(bad, (T + timedelta(seconds=1)).isoformat())
    assert source.checkpoint == before
    assert journal.source_status("test")["cursor"] == 1


def test_reconnect_baseline_retains_gap_and_does_not_invent_close(tmp_path):
    source, journal = account(tmp_path)
    source.observe(frame(), T.isoformat())
    original_epoch = source.epoch
    source.begin((T + timedelta(seconds=3)).isoformat(), reason="RECONNECT")
    fresh = shifted(4)
    for _, state in fresh["data"]["clearinghouseStates"]:
        state["assetPositions"] = []
    observed = source.observe(fresh, (T + timedelta(seconds=4)).isoformat())
    assert source.epoch != original_epoch
    assert observed["classification"] == "BASELINE"
    assert observed["position_changes"] == {}
    assert source.checkpoint["positions"] == {}
    assert not observed["signal_eligible"]
    audit = verify_streams(journal.path)["streams"]["account:test"]
    assert audit["gap_count"] == 2
    assert audit["baseline_count"] == 2


def test_explicit_top_level_snapshot_is_excluded_from_position_changes(tmp_path):
    source, _ = account(tmp_path)
    source.observe(frame(), T.isoformat())
    fresh = {**shifted(3, "-9"), "isSnapshot": True}
    result = source.observe(fresh, (T + timedelta(seconds=3)).isoformat())
    assert result["classification"] == "BASELINE"
    assert result["position_changes"] == {}
    assert not result["signal_eligible"]


def test_commit_failure_does_not_publish_in_memory_state(tmp_path, monkeypatch):
    source, journal = account(tmp_path)
    before = deepcopy(source.checkpoint)

    def unavailable(*args, **kwargs):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(journal, "append_source_receipt", unavailable)
    with pytest.raises(OSError):
        source.observe(frame(), T.isoformat())
    assert source.checkpoint == before
    assert journal.source_status("test")["cursor"] == 0
