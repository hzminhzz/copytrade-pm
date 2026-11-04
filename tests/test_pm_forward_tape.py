"""FP-06 partial shared source receipt tape contract, no network."""

from copytrade_pm.pm_forward_journal import PaperJournal

import pytest


def receipt(source="wallet_a", first="2026-11-04T04:00:01+00:00"):
    return {
        "schema": "paper_first_known_source_v1",
        "source_id": source,
        "source_event_at": "2026-11-04T04:00:00+00:00",
        "first_known_at": first,
        "captured_at": "2026-11-04T04:00:02+00:00",
        "payload_sha": "a" * 64,
    }


def test_durable_dedup_contiguous_and_private_source_tape(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    original = receipt()
    a = j.append_source_receipt("wallet_a", 1, "evt1", original)
    assert a["cursor"] == 1
    assert a["status"] == "CAPTURED_ONLY"
    assert not a["stream_live"] and not a["paper_admitted"]
    assert j.append_source_receipt("wallet_a", 1, "evt1", original)["status"] == "DUPLICATE_RECEIPT"
    with pytest.raises(ValueError, match="CONFLICTING_SOURCE_RECEIPT"):
        j.append_source_receipt("wallet_a", 1, "evt1", {**original, "payload_sha": "b" * 64})
    with pytest.raises(ValueError, match="SOURCE_SEQUENCE_GAP_OR_CONFLICT"):
        j.append_source_receipt("wallet_a", 3, "evt3", original)
    b = j.append_source_receipt("wallet_a", 2, "evt2", original)
    assert b["cursor"] == 2
    assert PaperJournal(j.root).source_status("wallet_a") == b


def test_clock_violation_refused_without_advancing_cursor(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    with pytest.raises(ValueError, match="SOURCE_RECEIPT_CAUSAL_CLOCK_FAILURE"):
        j.append_source_receipt("wallet_a", 1, "evt1", receipt(first="2026-11-04T04:00:03+00:00"))
    assert j.source_status("wallet_a")["cursor"] == 0
