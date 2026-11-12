"""Postdeployment gate must reject a live PID whose signed consumer is stalled."""

from argparse import Namespace
from pathlib import Path

from copytrade_pm.pm_cwsa_chapter2_gate import GateCheck, verify
from copytrade_pm.pm_cwsa_six_paper import PORTFOLIO_CONFIGS
from copytrade_pm.pm_cwsa_chapter2_gate import EXPECTED_WALLETS


def test_postdeploy_active_service_stalled_finance_rejected(monkeypatch, tmp_path):
    import copytrade_pm.pm_cwsa_chapter2_gate as gate

    changed = 1794470500000
    source = {
        "latest_checkpoint_ms": changed + 600000,
        "policy_grace_ms": 180000,
        "source_count": 14,
        "head_sha256": "a" * 64,
        "latest_kinds": {m: "CHANGED" for m in EXPECTED_WALLETS},
        "changed_sources": {m: changed for m in EXPECTED_WALLETS},
    }
    monkeypatch.setattr(gate, "_source_facts", lambda path: source)
    monkeypatch.setattr(gate, "_resources", lambda: GateCheck("resources", "PASS", "ok"))
    monkeypatch.setattr(
        gate, "_unit", lambda name, expected_sha: GateCheck(name, "PASS", "pid verified")
    )
    monkeypatch.setattr(
        gate,
        "_dashboard",
        lambda *a: GateCheck("dashboard", "BLOCKED_EVIDENCE", "site not published"),
    )
    paper = {
        pid: {
            "cursor": 0,
            "modeled_effects": 0,
            "signed_mandates": 3,
            "finance_scan_count": 1,
            "finance_scan_checkpoint_ms": changed - 300000,
            "journal_head_sha": "b" * 64,
            "wave_count": 4,
        }
        for pid in PORTFOLIO_CONFIGS
    }
    monkeypatch.setattr(gate, "_paper_facts", lambda path: paper)
    monkeypatch.setattr(
        gate,
        "load_registry_seals",
        lambda path: {
            pid: {"definition_sha256": "d" * 64, "members": cfg["members"]}
            for pid, cfg in PORTFOLIO_CONFIGS.items()
        },
    )
    # Stub a separately validated signed release to isolate the stalled-consumer
    # invariant. The production verifier checks actual external signatures.
    import copytrade_pm.pm_cwsa_chapter2_release as releases
    import copytrade_pm.pm_cwsa_paper_qualification as qualifications

    monkeypatch.setattr(
        releases,
        "read_activation_bundle",
        lambda **kwargs: {pid: object() for pid in PORTFOLIO_CONFIGS},
    )
    monkeypatch.setattr(
        qualifications,
        "inspect_qualification",
        lambda *args: GateCheck("frozen_k_qualification", "PASS", "verified"),
    )
    monkeypatch.setattr(qualifications, "read_qualification", lambda *args: {"portfolios": {}})
    monkeypatch.setattr(qualifications, "mandate_k_blockers", lambda *args: [])
    args = Namespace(
        stage="postdeploy",
        root=Path.cwd(),
        expected_sha=None,
        registry_db=tmp_path,
        source_db=tmp_path,
        paper_root=tmp_path,
        expected_source_sha="a" * 40,
        expected_paper_sha="b" * 40,
        dashboard_url=None,
        dashboard_revision=None,
        dashboard_token_file=None,
        approved_paper_bundle=tmp_path / "approval.json",
        approved_paper_sha256="a" * 64,
        trusted_paper_public_key="b" * 64,
        qualification=tmp_path / "research.json",
        research_public_key="c" * 64,
        epoch="test",
    )
    result = verify(args)
    assert result["verdict"] == "FAIL"
    assert not result["financially_active"]
    assert any(
        check["name"] == "financial_consumer" and check["state"] == "FAIL"
        for check in result["checks"]
    )
