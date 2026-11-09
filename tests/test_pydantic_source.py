"""Public prospective boundary: economic equality never replaces evidence identity."""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_stream_journal import verify_streams
from copytrade_pm.pm_source_contracts import (
    Position,
    SourceEvidenceRef,
    UnavailableObservation,
    exact_decimal,
    utc_clock,
)
from test_pm_forward_persistent_source import account, shifted, T


def observe(source, seconds, qty):
    frame = shifted(seconds, qty)
    raw = json.dumps(frame, separators=(", ", ": "))
    return source.observe(
        frame,
        (T + timedelta(seconds=seconds)).isoformat(),
        raw_sha=sha256(raw.encode()).hexdigest(),
        raw_text=raw,
    )


def test_formatting_change_has_distinct_raw_evidence_but_no_transition(tmp_path):
    source, journal = account(tmp_path)
    observe(source, 0, "20")
    before = deepcopy(source.checkpoint)
    assert observe(source, 1, "20.0")["classification"] == "UNCHANGED_STATE"
    assert source.checkpoint["economic_sha"] == before["economic_sha"]
    assert source.checkpoint["semantic_sha"] != before["semantic_sha"]
    assert journal.source_status("test")["cursor"] == 2
    assert verify_streams(journal.path)["streams"]["account:test"]["observation_count"] == 0
    assert observe(source, 2, "21")["classification"] == "OBSERVED_STATE_CHANGE"


def test_same_clock_format_change_is_not_a_conflicting_position(tmp_path):
    source, journal = account(tmp_path)
    observe(source, 0, "20")
    assert observe(source, 0, "20.000")["classification"] == "UNCHANGED_STATE"
    assert journal.source_status("test")["cursor"] == 2


def test_equal_reopened_state_has_distinct_committed_identity(tmp_path):
    source, journal = account(tmp_path)
    identities = []
    for i, qty in enumerate(("0", "20", "0", "20")):
        result = observe(source, i, qty)
        if qty == "20":
            assert result["classification"] == "OBSERVED_STATE_CHANGE"
            identities.append((source.progress.head["cursor"], source.progress.head["chain_sha"]))
    assert identities[0][0] != identities[1][0]
    assert identities[0][1] != identities[1][1]
    assert verify_streams(journal.path)["streams"]["account:test"]["observation_count"] == 3


@pytest.mark.parametrize(
    "qty", [20.0, True, "NaN", "Infinity", "-Infinity", None, " 20", "2_0", "0x14"]
)
def test_critical_quantity_rejected_without_source_receipt(tmp_path, qty):
    source, journal = account(tmp_path)
    observe(source, 0, "20")
    bad = shifted(1, qty)
    if qty is None:
        bad["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["szi"] = None
    with pytest.raises(ValueError):
        source.observe(bad, (T + timedelta(seconds=1)).isoformat())
    assert journal.source_status("test")["cursor"] == 1
    assert source.checkpoint["positions"]["hyperliquid/mainnet:perp:default/BTC"] == "20"


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_state",
        "unknown_position",
        "unknown_margin",
        "clock_bool",
        "clock_float",
        "duplicate",
        "missing_margin",
    ],
)
def test_unknown_or_ambiguous_critical_semantics_fail_closed(tmp_path, fault):
    source, journal = account(tmp_path)
    observe(source, 0, "20")
    bad = shifted(1, "21")
    state = bad["data"]["clearinghouseStates"][0][1]
    if fault == "unknown_state":
        state["isDelta"] = True
    if fault == "unknown_position":
        state["assetPositions"][0]["position"]["deltaQuantity"] = "1"
    if fault == "unknown_margin":
        state["marginSummary"]["replacement"] = False
    if fault == "clock_bool":
        state["time"] = True
    if fault == "clock_float":
        state["time"] = float(state["time"])
    if fault == "duplicate":
        state["assetPositions"] *= 2
    if fault == "missing_margin":
        del state["marginSummary"]
    with pytest.raises(ValueError):
        source.observe(bad, (T + timedelta(seconds=1)).isoformat())
    assert journal.source_status("test")["cursor"] == 1


def test_known_optional_diagnostics_never_create_economic_change(tmp_path):
    source, _ = account(tmp_path)
    observe(source, 0, "20")
    f = shifted(1, "20")
    f["data"]["clearinghouseStates"][0][1]["withdrawable"] = {"unavailable": True}
    assert (
        source.observe(f, (T + timedelta(seconds=1)).isoformat())["classification"]
        == "UNCHANGED_STATE"
    )
    assert source.checkpoint["source_equity"] is None


def test_typed_contracts_reject_coercion_unknown_fields_and_naive_clocks():
    key = "hyperliquid/mainnet:perp:default/BTC"
    with pytest.raises(ValueError):
        Position(instrument=key, quantity="20")
    with pytest.raises(ValueError):
        Position(instrument=key, quantity=Decimal("NaN"))
    with pytest.raises(ValueError):
        Position(instrument=key, quantity=Decimal(20), permit=True)
    with pytest.raises(ValueError):
        utc_clock("2026-11-01T00:00:00")
    with pytest.raises(ValueError):
        SourceEvidenceRef(
            source_id="test",
            raw_sha="a" * 64,
            native_frame_sha="b" * 64,
            first_known_at=T,
            source_event_at=T + timedelta(seconds=1),
        )
    with pytest.raises(ValueError):
        UnavailableObservation(status="VALID", reason="schema alone is not admission")
    assert exact_decimal("1.23456789012345678901234567890123456789") == Decimal(
        "1.23456789012345678901234567890123456789"
    )


def test_original_wire_and_canonical_frame_hashes_are_unchanged(tmp_path):
    source, journal = account(tmp_path)
    f = shifted(0, "20.0")
    wire = json.dumps(f, indent=2)
    fingerprint = sha256(wire.encode()).hexdigest()
    source.observe(f, T.isoformat(), raw_text=wire, raw_sha=fingerprint)
    head = source.progress.head
    assert head["event"]["raw_sha"] == fingerprint
    assert head["event"]["details"]["native_wire"] == wire
    assert head["event"]["details"]["native_frame"] == f
    assert fingerprint != digest(f)
    assert verify_streams(journal.path)["integrity"] == "VERIFIED"
