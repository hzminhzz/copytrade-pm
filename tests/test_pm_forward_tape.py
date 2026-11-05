"""FP-06 partial shared source receipt tape contract, no network."""

from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal


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


def test_backup_verifies_source_chain_and_restores_exact_heads(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    j.append_source_receipt("wallet_a", 1, "evt1", receipt())
    j.append_source_receipt("wallet_b", 1, "evt1", receipt(source="wallet_b"))
    j.backup(tmp_path / "backup")
    restored = PaperJournal(tmp_path / "backup")
    for source_id in ("wallet_a", "wallet_b"):
        assert restored.source_status(source_id) == j.source_status(source_id)
    assert not restored.source_status("wallet_a")["paper_admitted"]


def diagnostic():
    return {
        "schema": "paper_public_collateral_scope_v1",
        "account_address_sha256": "a" * 64,
        "observations": [
            {
                "scope": "spotClearinghouseState",
                "status": "PARTIAL_PUBLIC_OBSERVATION",
                "first_known_at": "2026-11-04T04:00:01+00:00",
                "source_event_at": None,
                "response_sha256": "b" * 64,
                "row_count": 2,
            },
            {
                "scope": "userVaultEquities",
                "status": "BLOCKED_SCOPE_ACQUISITION",
                "first_known_at": None,
                "source_event_at": None,
                "response_sha256": None,
                "row_count": None,
            },
        ],
        "provider_atomic_nav_available": False,
        "source_equity": None,
        "collateral_reconciled": False,
        "status": "BLOCKED_COLLATERAL_AND_VAULT_RECONCILIATION",
        "paper_observed": False,
        "order_route": "NONE",
    }


def test_durable_collateral_chain_backup_and_anti_promotion(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    report = diagnostic()
    result = journal.append_collateral_diagnostic(report)
    assert result["cursor"] == 1
    assert journal.append_collateral_diagnostic(report)["cursor"] == 1
    assert result["source_equity"] is None
    assert result["paper_admitted"] is False
    updated = {**report, "observations": [dict(r) for r in report["observations"]]}
    updated["observations"][0]["first_known_at"] = "2026-11-04T04:01:01+00:00"
    assert journal.append_collateral_diagnostic(updated)["cursor"] == 2
    assert PaperJournal(journal.root).collateral_scope_status("a" * 64)["cursor"] == 2
    journal.backup(tmp_path / "backup")
    backup = PaperJournal(tmp_path / "backup")
    assert backup.collateral_scope_status("a" * 64) == journal.collateral_scope_status("a" * 64)
    with pytest.raises(ValueError, match="SOURCE_COLLATERAL_UNTRUSTED_POSITIVE_CLAIM"):
        journal.append_collateral_diagnostic({**report, "source_equity": "1"})
    with pytest.raises(ValueError, match="SOURCE_COLLATERAL_EVENT_TIME_FABRICATED"):
        forged = {**report, "observations": [dict(r) for r in report["observations"]]}
        forged["observations"][0]["source_event_at"] = "2026-11-04T04:00:01+00:00"
        journal.append_collateral_diagnostic(forged)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute("UPDATE source_scope_receipts SET payload_sha=? WHERE seq=1", ("f" * 64,))
        db.commit()
    with pytest.raises(ValueError, match="SOURCE_COLLATERAL_CHAIN_DIVERGENCE"):
        journal.collateral_scope_status("a" * 64)
    with pytest.raises(ValueError, match="SOURCE_COLLATERAL_CHAIN_DIVERGENCE"):
        journal.backup(tmp_path / "corrupt_backup")


def test_account_mode_evidence_requires_exact_public_enum_hash_and_causal_clock(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    mode = {
        "status": "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED",
        "mode": "unifiedAccount",
        "first_known_at": "2026-11-04T04:00:03+00:00",
        "source_event_at": None,
        "response_sha256": "c" * 64,
        "source_signed": False,
    }
    case = {**diagnostic(), "account_abstraction": mode}
    assert journal.append_collateral_diagnostic(case)["cursor"] == 1
    for corrupt in (
        {**mode, "mode": "unknown"},
        {**mode, "source_event_at": "2026-11-04T04:00:02+00:00"},
        {**mode, "response_sha256": None},
        {**mode, "source_signed": True},
        {**mode, "first_known_at": "2026-11-04T03:59:00+00:00"},
    ):
        with pytest.raises(ValueError, match="SOURCE_ACCOUNT_MODE"):
            journal.append_collateral_diagnostic({**case, "account_abstraction": corrupt})
    assert journal.collateral_scope_status("a" * 64)["cursor"] == 1


def test_clock_violation_refused_without_advancing_cursor(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    with pytest.raises(ValueError, match="SOURCE_RECEIPT_CAUSAL_CLOCK_FAILURE"):
        j.append_source_receipt("wallet_a", 1, "evt1", receipt(first="2026-11-04T04:00:03+00:00"))
    assert j.source_status("wallet_a")["cursor"] == 0
