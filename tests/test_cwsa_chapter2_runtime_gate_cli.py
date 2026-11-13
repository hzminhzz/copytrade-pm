"""ANOS-06: public Chapter 2 stage CLI uses independent OS liveness and release proof."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from copytrade_pm import pm_cwsa_chapter2_gate as gate
from copytrade_pm import pm_operations, pm_runtime_readonly
from copytrade_pm.pm_cwsa_six_paper import PORTFOLIO_CONFIGS


SHA = "a" * 40
SOURCE_SHA = "b" * 40
PAPER_SHA = "c" * 40


@pytest.fixture
def chapter2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    latest = int(time.time() * 1000) - 30_000
    changed = latest - 600_000
    source = {
        "latest_checkpoint_ms": latest,
        "policy_grace_ms": 180_000,
        "source_count": 14,
        "head_sha256": "d" * 64,
        "latest_kinds": {wallet: "CHANGED" for wallet in gate.EXPECTED_WALLETS},
        "changed_sources": {wallet: changed for wallet in gate.EXPECTED_WALLETS},
    }
    paper = {
        pid: {
            "cursor": 0,
            "modeled_effects": 0,
            "signed_mandates": len(gate.EXPECTED_PORTFOLIOS[pid]),
            "finance_scan_count": 0,
            "finance_scan_checkpoint_ms": 0,
            "journal_head_sha": "e" * 64,
            "wave_count": 0,
        }
        for pid in PORTFOLIO_CONFIGS
    }
    monkeypatch.setattr(gate, "_git", lambda path, ref: SHA if ref == "HEAD" else "f" * 40)
    monkeypatch.setattr(gate, "_source_facts", lambda path: source)
    monkeypatch.setattr(gate, "_paper_facts", lambda path: paper)
    monkeypatch.setattr(gate, "_resources", lambda: gate.GateCheck("resources", "PASS", "ok"))
    monkeypatch.setattr(
        gate,
        "load_registry_seals",
        lambda path: {
            pid: {"members": cfg["members"], "definition_sha256": "d" * 64}
            for pid, cfg in PORTFOLIO_CONFIGS.items()
        },
    )
    monkeypatch.setattr(
        gate,
        "_market_evidence",
        lambda *args: gate.GateCheck("independent_executable_quotes", "PASS", "fixture"),
    )
    monkeypatch.setattr(
        gate,
        "_dashboard",
        lambda *args: gate.GateCheck("dashboard", "PASS", "fixture"),
    )
    runtime = {
        "source_state": "VERIFIED",
        "paper_state": "UNKNOWN",
        "paper_reason": "PROCESS_METADATA_UNAVAILABLE",
        "liveness_state": "RUNNING",
        "liveness_reason": "PROCESS_BOUND_TO_RUNNING_SYSTEMD_UNIT",
    }

    def binding(unit: str, *, expected_sha: str | None, manager: str = "user") -> dict:
        assert manager == "user"
        state = runtime["source_state"] if unit == gate.SOURCE_UNIT else runtime["paper_state"]
        return {
            "state": state,
            "reason": runtime["paper_reason"]
            if unit == gate.PAPER_UNIT
            else "RUNNING_RELEASE_LAUNCH_BOUND",
            "configured": {"unit": unit, "manager": manager, "active_state": "active"},
            "installed": {"expected_revision": expected_sha},
            "observed": {
                "pid": 4242 if unit == gate.PAPER_UNIT else 2121,
                "process_start_ticks": 500_000,
            },
            "clock": {"inspection_started_utc": "2026-11-13T09:00:00+00:00"},
            "limitations": ["Launch identity does not attest finance"],
            "trading_authorized": False,
            "service_mutations": 0,
        }

    def liveness(unit: str, *, manager: str = "user") -> dict:
        assert unit == gate.PAPER_UNIT and manager == "user"
        return {
            "state": runtime["liveness_state"],
            "reason": runtime["liveness_reason"],
            "unit": unit,
            "manager": manager,
            "pid": 4242,
            "process_start_ticks": 500_000,
        }

    monkeypatch.setattr(pm_runtime_readonly, "verify_unit_release", binding)
    monkeypatch.setattr(pm_runtime_readonly, "observe_unit_liveness", liveness, raising=False)

    def invoke(stage: str, *extra: str) -> tuple[int, dict]:
        code = pm_operations.cli(
            [
                "cwsa",
                "chapter2",
                "verify",
                "--stage",
                stage,
                "--root",
                str(Path.cwd()),
                "--registry-db",
                str(tmp_path / "registry"),
                "--source-db",
                str(tmp_path / "source"),
                "--paper-root",
                str(tmp_path / "paper"),
                "--expected-source-sha",
                SOURCE_SHA,
                "--expected-paper-sha",
                PAPER_SHA,
                *extra,
            ]
        )
        response = json.loads(capsys.readouterr().out)
        assert response["schema"] == "cwsa_chapter2_gate_verdict_v1"
        assert response["stage"] == stage
        assert response["order_route"] == "NONE"
        assert response["trading_authorized"] is False
        assert response["scientifically_qualified"] is False
        assert response["financially_active"] is False
        return code, response

    return runtime, paper, source, invoke


def test_public_postdeploy_active_but_unproved_process_is_evidence_blocked(chapter2):
    runtime, _, _, invoke = chapter2
    runtime["paper_state"] = "UNKNOWN"
    runtime["paper_reason"] = "PROCESS_METADATA_UNAVAILABLE"
    code, payload = invoke("postdeploy")
    assert code == 2
    assert payload["verdict"] == "BLOCKED_EVIDENCE"
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks[gate.PAPER_UNIT]["state"] == "BLOCKED_EVIDENCE"
    assert checks[gate.PAPER_UNIT]["detail"] == "PROCESS_METADATA_UNAVAILABLE"
    assert checks["paper_process_liveness"]["state"] == "PASS"
    assert checks["financial_consumer"]["state"] == "BLOCKED_EVIDENCE"
    assert not any(item["detail"] == "PAPER_SERVICE_NOT_RUNNING" for item in payload["checks"])


@pytest.mark.parametrize(
    ("release_state", "release_reason", "live_state", "live_reason", "exit_code", "verdict"),
    [
        ("NOT_RUNNING", "SYSTEMD_UNIT_STOPPED", "NOT_RUNNING", "SYSTEMD_UNIT_STOPPED", 1, "FAIL"),
        (
            "MISMATCH",
            "INSTALLED_RELEASE_SHA_DRIFT",
            "RUNNING",
            "PROCESS_BOUND_TO_RUNNING_SYSTEMD_UNIT",
            1,
            "FAIL",
        ),
        ("MISMATCH", "PROCESS_ARGV_MISMATCH", "MISMATCH", "PROCESS_LAUNCH_MISMATCH", 1, "FAIL"),
        (
            "UNKNOWN",
            "PROCESS_IDENTITY_RACED",
            "UNKNOWN",
            "PROCESS_OR_SYSTEMD_IDENTITY_RACED",
            2,
            "BLOCKED_EVIDENCE",
        ),
        (
            "UNKNOWN",
            "SYSTEMD_IDENTITY_RACED",
            "UNKNOWN",
            "PROCESS_OR_SYSTEMD_IDENTITY_RACED",
            2,
            "BLOCKED_EVIDENCE",
        ),
        (
            "UNKNOWN",
            "PROCESS_METADATA_UNAVAILABLE",
            "UNKNOWN",
            "PROCESS_LIVENESS_UNAVAILABLE",
            2,
            "BLOCKED_EVIDENCE",
        ),
    ],
)
def test_public_postdeploy_process_adversaries_fail_closed(
    chapter2, release_state, release_reason, live_state, live_reason, exit_code, verdict
):
    runtime, _, _, invoke = chapter2
    runtime.update(
        paper_state=release_state,
        paper_reason=release_reason,
        liveness_state=live_state,
        liveness_reason=live_reason,
    )
    code, payload = invoke("postdeploy")
    checks = {item["name"]: item for item in payload["checks"]}
    assert (code, payload["verdict"]) == (exit_code, verdict)
    expected_unit = "FAIL" if release_state in ("NOT_RUNNING", "MISMATCH") else "BLOCKED_EVIDENCE"
    assert checks[gate.PAPER_UNIT]["state"] == expected_unit
    expected_live = (
        "PASS"
        if live_state == "RUNNING"
        else "FAIL"
        if live_state in ("NOT_RUNNING", "MISMATCH")
        else "BLOCKED_EVIDENCE"
    )
    assert checks["paper_process_liveness"]["state"] == expected_live
    if live_state == "RUNNING":
        assert checks["financial_consumer"]["detail"] != "PAPER_SERVICE_NOT_RUNNING"
    if live_state == "NOT_RUNNING":
        assert checks["financial_consumer"]["detail"] == "PAPER_SERVICE_NOT_RUNNING"


def test_public_postdeploy_healthy_source_and_empty_paper_journals_never_pass(chapter2):
    runtime, paper, source, invoke = chapter2
    runtime.update(paper_state="VERIFIED", liveness_state="RUNNING")
    for info in paper.values():
        info["signed_mandates"] = 0
        info["modeled_effects"] = 0
        info["cursor"] = 0
    source["changed_sources"] = {}
    code, payload = invoke("postdeploy")
    checks = {item["name"]: item for item in payload["checks"]}
    assert code == 2
    assert payload["verdict"] == "BLOCKED_EVIDENCE"
    assert checks["financial_consumer"]["detail"] == "NO_SIGNED_FINANCIAL_MANDATES"


def test_public_postdeploy_signed_due_change_with_stalled_finance_wins_over_unknown(
    chapter2, monkeypatch
):
    runtime, paper, _, invoke = chapter2
    runtime.update(paper_state="UNKNOWN", liveness_state="UNKNOWN")
    for info in paper.values():
        info["finance_scan_count"] = 1
        info["finance_scan_checkpoint_ms"] = 0
    import copytrade_pm.pm_cwsa_chapter2_release as release
    import copytrade_pm.pm_cwsa_paper_qualification as qualification

    monkeypatch.setattr(
        release, "read_activation_bundle", lambda **kw: {pid: object() for pid in PORTFOLIO_CONFIGS}
    )
    monkeypatch.setattr(
        qualification,
        "inspect_qualification",
        lambda *args: gate.GateCheck("frozen_k_qualification", "PASS", "fixture"),
    )
    monkeypatch.setattr(qualification, "read_qualification", lambda *args: {"portfolios": {}})
    monkeypatch.setattr(qualification, "mandate_k_blockers", lambda *args: [])

    code, payload = invoke(
        "postdeploy",
        "--approved-paper-bundle",
        "/fixture/bundle",
        "--approved-paper-sha256",
        "f" * 64,
        "--trusted-paper-public-key",
        "d" * 64,
        "--qualification",
        "/fixture/qualification",
        "--research-public-key",
        "e" * 64,
    )
    checks = {item["name"]: item for item in payload["checks"]}
    assert (code, payload["verdict"]) == (1, "FAIL")
    assert checks["financial_consumer"]["detail"] == "FINANCIAL_CONSUMER_DID_NOT_PROCESS_DUE_CHANGE"


def test_public_postdeploy_verified_worker_without_proven_effect_not_financially_active(
    chapter2, monkeypatch
):
    runtime, paper, source, invoke = chapter2
    runtime.update(paper_state="VERIFIED", liveness_state="RUNNING")
    for info in paper.values():
        info["finance_scan_count"] = 1
        info["finance_scan_checkpoint_ms"] = source["latest_checkpoint_ms"]
        info["cursor"] = 4
        info["modeled_effects"] = 0
    import copytrade_pm.pm_cwsa_chapter2_release as release
    import copytrade_pm.pm_cwsa_paper_qualification as qualification

    monkeypatch.setattr(
        release, "read_activation_bundle", lambda **kw: {pid: object() for pid in PORTFOLIO_CONFIGS}
    )
    monkeypatch.setattr(
        qualification,
        "inspect_qualification",
        lambda *args: gate.GateCheck("frozen_k_qualification", "PASS", "fixture"),
    )
    monkeypatch.setattr(qualification, "read_qualification", lambda *args: {"portfolios": {}})
    monkeypatch.setattr(qualification, "mandate_k_blockers", lambda *args: [])
    code, payload = invoke(
        "postdeploy",
        "--approved-paper-bundle",
        "/fixture/bundle",
        "--approved-paper-sha256",
        "f" * 64,
        "--trusted-paper-public-key",
        "d" * 64,
        "--qualification",
        "/fixture/qualification",
        "--research-public-key",
        "e" * 64,
    )
    assert code == 2
    assert payload["verdict"] == "BLOCKED_EVIDENCE"
    assert next(c for c in payload["checks"] if c["name"] == "financial_consumer")["detail"] == (
        "NO_PROVEN_MODELED_FINANCIAL_EFFECT"
    )


def test_public_postdeploy_finance_progress_cannot_promote_unproved_release(chapter2, monkeypatch):
    runtime, paper, source, invoke = chapter2
    runtime.update(paper_state="UNKNOWN", liveness_state="RUNNING")
    for info in paper.values():
        info["finance_scan_count"] = 1
        info["finance_scan_checkpoint_ms"] = source["latest_checkpoint_ms"]
        info["cursor"] = 4
        info["modeled_effects"] = 1
    import copytrade_pm.pm_cwsa_chapter2_release as release
    import copytrade_pm.pm_cwsa_paper_qualification as qualification

    monkeypatch.setattr(
        release, "read_activation_bundle", lambda **kw: {pid: object() for pid in PORTFOLIO_CONFIGS}
    )
    monkeypatch.setattr(
        qualification,
        "inspect_qualification",
        lambda *args: gate.GateCheck("frozen_k_qualification", "PASS", "fixture"),
    )
    monkeypatch.setattr(qualification, "read_qualification", lambda *args: {"portfolios": {}})
    monkeypatch.setattr(qualification, "mandate_k_blockers", lambda *args: [])

    code, payload = invoke(
        "postdeploy",
        "--approved-paper-bundle",
        "/fixture/bundle",
        "--approved-paper-sha256",
        "f" * 64,
        "--trusted-paper-public-key",
        "d" * 64,
        "--qualification",
        "/fixture/qualification",
        "--research-public-key",
        "e" * 64,
    )
    checks = {item["name"]: item for item in payload["checks"]}
    assert (code, payload["verdict"]) == (2, "BLOCKED_EVIDENCE")
    assert checks["financial_consumer"]["state"] == "PASS"
    assert checks[gate.PAPER_UNIT]["state"] == "BLOCKED_EVIDENCE"
    assert not payload["financially_active"]


def test_public_postdeploy_independent_process_birth_disagreement_blocks(chapter2, monkeypatch):
    runtime, _, _, invoke = chapter2
    runtime.update(paper_state="VERIFIED", liveness_state="RUNNING")

    def newer_birth(unit: str, *, manager: str = "user") -> dict:
        return {
            "state": "RUNNING",
            "reason": "PROCESS_BOUND_TO_RUNNING_SYSTEMD_UNIT",
            "pid": 4242,
            "process_start_ticks": 500_001,
        }

    monkeypatch.setattr(pm_runtime_readonly, "observe_unit_liveness", newer_birth)
    code, payload = invoke("postdeploy")
    checks = {item["name"]: item for item in payload["checks"]}
    assert (code, payload["verdict"]) == (2, "BLOCKED_EVIDENCE")
    assert checks["paper_process_liveness"]["detail"] == (
        "PROCESS_RELEASE_AND_LIVENESS_SNAPSHOTS_DISAGREE"
    )
    assert not payload["financially_active"]


def test_public_premerge_and_predeploy_preserve_stage_contracts(chapter2, monkeypatch, tmp_path):
    _, _, _, invoke = chapter2
    from copytrade_pm import pm_ci_receipt

    monkeypatch.setattr(
        pm_ci_receipt,
        "check_receipt",
        lambda *args, **kwargs: gate.GateCheck("ci_receipt", "PASS", "fixture"),
    )
    code, premerge = invoke("premerge")
    assert (code, premerge["verdict"]) == (0, "PASS")
    assert all(c["name"] != "paper_process_liveness" for c in premerge["checks"])
    code, predeploy = invoke("predeploy")
    assert code == 2
    assert predeploy["verdict"] == "BLOCKED_EVIDENCE"
    assert next(c for c in predeploy["checks"] if c["name"] == "rollback")["detail"] == (
        "EXECUTABLE_ROLLBACK_PIN_REQUIRED"
    )
    assert all(c["name"] != "paper_process_liveness" for c in predeploy["checks"])
