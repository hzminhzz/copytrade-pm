"""V4 source export: official chain, causal clocks, and signer provenance."""

from hashlib import sha256
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.production_manifest import verify
from copytrade_pm.v4_source_export import export_signed_events
from test_pm_forward_observed_paper import ADDRESSES, at
from test_pm_vike_paper_integration import official_frame


def observer(tmp_path):
    journal = PaperJournal(tmp_path / "observer")
    source = PersistentAccount(
        journal=journal,
        alias="S035",
        address=ADDRESSES["S035"],
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="S035",
        scope_sha=digest(["S035", "default"]),
    )
    source.begin(at(0))
    frame = official_frame(1, 0)
    source.observe(frame, at(2))
    return journal, source


def source_event(source, seconds, qty, *, with_mark=True):
    frame = official_frame(seconds, qty)
    if qty and with_mark:
        frame["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"][
            "positionValue"
        ] = str(abs(qty) * 100)
    wire = json.dumps(frame, separators=(",", ":"))
    return source.observe(
        frame, at(seconds + 1), raw_sha=sha256(wire.encode()).hexdigest(), raw_text=wire
    )


def test_export_preserves_t0_signed_source_mark_and_native_identity(tmp_path):
    journal, source = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(source, 10, 20)
    result = export_signed_events(
        journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key, after={"S035": 2}
    )
    assert result["schema"] == "v4_signed_source_export_v1"
    assert len(result["events"]["S035"]) == 1
    event = result["events"]["S035"][0]
    proof = verify(event["proof"], key.public_key(), "source-observer-v4")
    book = verify(event["book"], key.public_key(), "source-observer")
    assert proof["kind"] == "OBSERVATION"
    assert proof["classification"] == "OBSERVED_STATE_CHANGE"
    assert proof["first_known_ms"] == int(
        __import__("datetime").datetime.fromisoformat(at(11)).timestamp() * 1000
    )
    assert book["known_at_ms"] == proof["first_known_ms"]
    assert book["positions"] == [
        {
            "market": "hyperliquid/mainnet:perp:default/BTC",
            "quantity": "20",
            "mark": "100",
            "mark_known_at_ms": book["known_at_ms"],
        }
    ]
    assert book["nav"] is None
    assert book["scope"] == [ADDRESSES["S035"]]
    assert proof["source_book_sha"] == event["book"]["sha256"]


def test_gap_and_reconnect_baseline_never_replay_previous_risk(tmp_path):
    journal, source = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(source, 10, 20)
    source.gap(at(20), "FAULT")
    source.observe(official_frame(21, 0), at(22))
    result = export_signed_events(
        journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key, after={"S035": 2}
    )
    kinds = [
        verify(event["proof"], key.public_key(), "source-observer-v4")["kind"]
        for event in result["events"]["S035"]
    ]
    assert kinds == ["OBSERVATION", "GAP", "BASELINE"]
    assert result["events"]["S035"][1]["book"] is None
    assert (
        verify(result["events"]["S035"][2]["proof"], key.public_key(), "source-observer-v4")[
            "classification"
        ]
        == "BASELINE"
    )


def test_missing_official_mark_fails_closed_without_fake_price(tmp_path):
    journal, source = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(source, 10, 20, with_mark=False)
    result = export_signed_events(
        journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key, after={"S035": 2}
    )
    event = result["events"]["S035"][0]
    assert event["book"] is None
    assert (
        verify(event["proof"], key.public_key(), "source-observer-v4")["full_selected_scope"]
        is False
    )


def test_no_historical_source_risk_by_default_and_invalid_identity_refused(tmp_path):
    journal, source = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(source, 10, 20)
    exported = export_signed_events(journal.path, selected={"S035": ADDRESSES["S035"]}, signer=key)
    assert exported["events"]["S035"] == []
    with pytest.raises(ValueError, match="IDENTITY|CHAIN"):
        export_signed_events(
            journal.path,
            selected={"S035": "0x" + "d" * 40},
            signer=key,
            after={"S035": 2},
        )
