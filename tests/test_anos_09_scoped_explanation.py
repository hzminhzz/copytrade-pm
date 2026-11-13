"""ANOS-09: task-scoped native Chapter 2 explanations preserve independent authority."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from copytrade_pm import pm_cwsa_chapter2_gate as gate
from copytrade_pm import pm_cwsa_six_paper as six
from copytrade_pm import pm_operations, pm_runtime_readonly


@pytest.fixture
def explained(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    checkpoint = int(datetime.now(UTC).timestamp() * 1000) - 5_000
    source = {
        "latest_checkpoint_ms": checkpoint,
        "policy_grace_ms": 180_000,
        "source_count": len(gate.EXPECTED_WALLETS),
        "head_sha256": "a" * 64,
        "latest_kinds": {member: "BASELINE" for member in gate.EXPECTED_WALLETS},
        "checkpoint_ms_by_wallet": {member: checkpoint for member in gate.EXPECTED_WALLETS},
        "published_ms_by_wallet": {member: checkpoint + 1500 for member in gate.EXPECTED_WALLETS},
        "receipt_first_known_ms_by_wallet": {
            member: checkpoint + 1000 for member in gate.EXPECTED_WALLETS
        },
        "complete_position_proof_by_wallet": {member: True for member in gate.EXPECTED_WALLETS},
        "source_heads_by_wallet": {member: "1" * 64 for member in gate.EXPECTED_WALLETS},
        "policy_epochs_by_wallet": {member: "2" * 64 for member in gate.EXPECTED_WALLETS},
        "scope_generations_by_wallet": {member: "3" * 64 for member in gate.EXPECTED_WALLETS},
        "changed_sources": {},
    }
    paper = {
        "cursor": 0,
        "journal_head_sha": "b" * 64,
        "wave_count": 0,
        "wave_checkpoint_ms": 0,
        "signed_mandates": 0,
        "finance_scan_count": 0,
        "finance_scan_checkpoint_ms": 0,
        "modeled_effects": 0,
        "current_equity": "10000",
        "realized_pnl": "0",
        "costs": "0",
        "positions_count": 0,
    }
    monkeypatch.setattr(
        pm_operations,
        "_doctor",
        lambda db: pm_operations.result(
            "registry.doctor",
            "BLOCKED",
            {
                "database_integrity": "VERIFIED",
                "research_selection_integrity": "BLOCKED_MISSING_EXTERNAL_PROOF",
                "inventory_sha256": "c" * 64,
            },
            authority="sqlite_wallet_registry",
            error_code="RESEARCH_SELECTION_PROOF_BLOCKED",
        ),
    )

    def seals(db, portfolios=None):
        selected = portfolios if portfolios is not None else tuple(six.PORTFOLIO_CONFIGS)
        return {
            pid: {
                "portfolio_id": pid,
                "version": 2,
                "selection_known_at": "2026-11-12T00:00:00+00:00",
                "definition_sha256": "d" * 64,
                "members": tuple(sorted(six.PORTFOLIO_CONFIGS[pid]["members"])),
            }
            for pid in selected
        }

    monkeypatch.setattr(six, "load_registry_seals", seals)
    monkeypatch.setattr(gate, "_source_facts", lambda db: source)

    def financial(root, *, portfolios=None):
        assert portfolios == ("A",)
        return {"A": paper}

    monkeypatch.setattr(gate, "_paper_facts", financial)
    monkeypatch.setattr(
        gate,
        "_market_evidence",
        lambda db, src: gate.GateCheck(
            "independent_executable_quotes",
            "BLOCKED_EVIDENCE",
            "PINNED_INDEPENDENT_L2_QUOTE_JOURNAL_REQUIRED",
        ),
    )

    def invoke(*extra: str):
        code = pm_operations.cli(
            [
                "cwsa",
                "chapter2",
                "explain",
                "--portfolio",
                "A",
                "--registry-db",
                str(tmp_path / "registry"),
                "--source-db",
                str(tmp_path / "source"),
                "--paper-root",
                str(tmp_path / "paper"),
                *extra,
            ]
        )
        return code, json.loads(capsys.readouterr().out)

    return source, paper, invoke


def test_scoped_metadata_never_reads_source_market_or_financial_journals(explained, monkeypatch):
    _, _, invoke = explained

    def forbidden(*args, **kwargs):
        raise AssertionError("METADATA_INSPECTION_ESCAPED_READ_SCOPE")

    monkeypatch.setattr(gate, "_source_facts", forbidden)
    monkeypatch.setattr(gate, "_paper_facts", forbidden)
    monkeypatch.setattr(gate, "_market_evidence", forbidden)
    monkeypatch.setattr(pm_runtime_readonly, "verify_unit_release", forbidden)
    code, report = invoke()
    assert code == 0
    assert report["schema"] == "cwsa_chapter2_task_explanation_v1"
    assert report["scope"]["inspection"] == "metadata"
    assert report["dimensions"]["registry_integrity"]["state"] == "VERIFIED"
    assert report["dimensions"]["research_selection_proof"]["state"] == "BLOCKED"
    assert report["dimensions"]["portfolio_seal"]["state"] == "VERIFIED"
    assert report["dimensions"]["source_observation"]["state"] == "NOT_INSPECTED"
    assert report["limits"]["financial_journals_opened"] == 0
    assert report["next_operation"]["id"] == "operations.cwsa.chapter2.explain"
    assert report["next_operation"]["effect_class"] == "READ_ONLY"
    assert report["next_operation"]["auto_dispatched"] is False
    assert report["economics"]["realized_pnl_usd"] is None
    assert report["trading_authorized"] is False


def test_source_observe_ready_but_paper_blocked_and_unknown_economics(explained):
    source, _, invoke = explained
    code, report = invoke("--inspection", "evidence")
    assert code == 0
    assert report["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"
    assert (
        report["dimensions"]["source_observation"]["evidence"]["head_sha256"]
        == source["head_sha256"]
    )
    assert (
        report["dimensions"]["source_observation"]["evidence"]["original_checkpoint_ms"]
        == source["latest_checkpoint_ms"]
    )
    assert report["dimensions"]["portfolio_seal"]["evidence"]["definition_sha256"] == "d" * 64
    assert report["dimensions"]["paper_finance"]["state"] == "BLOCKED_EVIDENCE"
    assert report["dimensions"]["guardian_authorization"]["state"] == "UNKNOWN"
    assert report["dimensions"]["risk"]["state"] == "UNKNOWN"
    codes = {block["reason_code"] for block in report["blockers"]}
    assert "SIGNED_PAPER_BUNDLE_AND_TRUST_ROOT_REQUIRED" in codes
    assert "PINNED_INDEPENDENT_L2_QUOTE_JOURNAL_REQUIRED" in codes
    assert "NO_PROVEN_MODELED_FINANCIAL_EFFECT" in codes
    assert report["limits"]["financial_journals_opened"] == 1
    assert report["economics"]["realized_pnl_usd"] is None
    assert report["economics"]["total_costs_usd"] is None
    assert report["next_operation"]["id"] == "operations.cwsa.chapter2.verify"
    assert report["next_operation"]["auto_dispatched"] is False


def test_missing_native_evidence_is_not_observed_flat_or_zero(explained, monkeypatch):
    _, _, invoke = explained

    def missing(*args, **kwargs):
        raise ValueError("MISSING_NATIVE_EVIDENCE")

    monkeypatch.setattr(gate, "_source_facts", missing)
    monkeypatch.setattr(gate, "_paper_facts", missing)
    code, report = invoke("--inspection", "evidence")
    assert code == 0
    assert report["dimensions"]["source_observation"]["state"] == "UNKNOWN"
    assert report["dimensions"]["paper_finance"]["state"] == "UNKNOWN"
    assert report["economics"]["realized_pnl_usd"] is None
    assert report["dimensions"]["guardian_authorization"]["state"] == "UNKNOWN"
    assert "SOURCE_OWNER_EVIDENCE_UNAVAILABLE" in {
        item["reason_code"] for item in report["blockers"]
    }


def test_old_wallet_checkpoint_does_not_inherit_latest_other_wallet_clock(explained):
    source, _, invoke = explained
    member = six.PORTFOLIO_CONFIGS["A"]["members"][0]
    source["checkpoint_ms_by_wallet"][member] -= 900_000
    _, report = invoke("--inspection", "evidence")
    assert report["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert member in report["dimensions"]["source_observation"]["missing_or_stale_members"]
    assert "SOURCE_PORTFOLIO_CHECKPOINT_INCOMPLETE_OR_STALE" in {
        item["reason_code"] for item in report["blockers"]
    }


def test_zero_economics_cannot_be_promoted_with_signed_fixture(explained, monkeypatch):
    _, paper, invoke = explained
    paper["signed_mandates"] = len(six.PORTFOLIO_CONFIGS["A"]["members"])
    paper["cursor"] = 3
    paper["modeled_effects"] = 0
    paper["realized_pnl"] = "0"

    from copytrade_pm import pm_cwsa_chapter2_release as release
    from copytrade_pm import pm_cwsa_paper_qualification as qualification

    monkeypatch.setattr(release, "read_activation_bundle", lambda **kw: {"A": object()})
    monkeypatch.setattr(qualification, "read_qualification", lambda *args: {"A": object()})
    monkeypatch.setattr(qualification, "mandate_k_blockers", lambda *args: [])
    monkeypatch.setattr(
        gate,
        "_market_evidence",
        lambda *args: gate.GateCheck("independent_executable_quotes", "PASS", "FIXTURE_L2_CHAIN"),
    )
    code, report = invoke(
        "--inspection",
        "evidence",
        "--quote-db",
        "/fixture/quotes.sqlite",
        "--approved-paper-bundle",
        "/fixture/approved.json",
        "--approved-paper-sha256",
        "f" * 64,
        "--trusted-paper-public-key",
        "e" * 64,
        "--qualification",
        "/fixture/k.json",
        "--research-public-key",
        "b" * 64,
    )
    assert code == 0
    assert report["dimensions"]["mandate"]["state"] == "VERIFIED"
    assert report["dimensions"]["paper_finance"]["state"] == "BLOCKED_EVIDENCE"
    assert report["economics"]["realized_pnl_usd"] is None
    assert "NO_PROVEN_MODELED_FINANCIAL_EFFECT" in {
        item["reason_code"] for item in report["blockers"]
    }


def test_even_modeled_fixture_cannot_attest_guardian_or_live_permission(explained, monkeypatch):
    _, paper, invoke = explained
    paper.update(
        signed_mandates=len(six.PORTFOLIO_CONFIGS["A"]["members"]),
        modeled_effects=1,
        cursor=4,
        realized_pnl="-2",
        costs="3",
    )
    from copytrade_pm import pm_cwsa_chapter2_release as release
    from copytrade_pm import pm_cwsa_paper_qualification as qualification

    monkeypatch.setattr(release, "read_activation_bundle", lambda **kw: {"A": object()})
    monkeypatch.setattr(qualification, "read_qualification", lambda *args: {"A": object()})
    monkeypatch.setattr(qualification, "mandate_k_blockers", lambda *args: [])
    monkeypatch.setattr(
        gate, "_market_evidence", lambda *args: gate.GateCheck("quotes", "PASS", "fixture")
    )
    _, report = invoke(
        "--inspection",
        "evidence",
        "--quote-db",
        "/fixture/quotes.sqlite",
        "--approved-paper-bundle",
        "/fixture/approved.json",
        "--approved-paper-sha256",
        "f" * 64,
        "--trusted-paper-public-key",
        "e" * 64,
        "--qualification",
        "/fixture/k.json",
        "--research-public-key",
        "b" * 64,
    )
    assert report["dimensions"]["paper_finance"]["state"] == "PROSPECTIVE_MODELED_PAPER"
    assert report["economics"]["realized_pnl_usd"] == "-2"
    assert report["dimensions"]["risk"]["state"] == "UNKNOWN"
    assert report["dimensions"]["guardian_authorization"]["state"] == "UNKNOWN"
    assert report["trading_authorized"] is False
    assert report["scientifically_qualified"] is False
    assert report["order_route"] == "NONE"


def test_unknown_portfolio_fails_closed_before_owner_reads(explained, monkeypatch, capsys):
    _, _, _ = explained
    monkeypatch.setattr(pm_operations, "_doctor", lambda *a: pytest.fail("unexpected read"))
    code = pm_operations.cli(["cwsa", "chapter2", "explain", "--portfolio", "../X"])
    response = json.loads(capsys.readouterr().out)
    assert code == 2
    assert response["error_code"] == "UNKNOWN_CHAPTER2_PORTFOLIO"
    assert response["trading_authorized"] is False
