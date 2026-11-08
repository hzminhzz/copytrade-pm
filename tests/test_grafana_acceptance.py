"""Release eligibility is a fail-closed decision over independently produced receipts."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = "copytrade_pm.dashboard.grafana_acceptance"


def evaluate(tmp_path, gates, *, candidate="a" * 40, expected="b" * 64):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "grafana_acceptance_evidence_v1",
                "candidate": candidate,
                "bundle_sha256": expected,
                "gates": gates,
            }
        )
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--receipt",
            str(receipt),
            "--candidate",
            candidate,
            "--bundle-sha256",
            expected,
        ],
        capture_output=True,
        text=True,
    )
    return process, json.loads(process.stdout)


def test_all_mandatory_independent_receipts_qualify(tmp_path):
    from copytrade_pm.dashboard.grafana_acceptance import MANDATORY_GATES

    gates = {
        name: {
            "status": "PASS",
            "candidate": "a" * 40,
            "bundle_sha256": "b" * 64,
            "evidence": "sha256:" + "c" * 64,
            "issuer": "independent_test_authority",
        }
        for name in MANDATORY_GATES
    }
    process, result = evaluate(tmp_path, gates)
    assert process.returncode == 0
    assert result["decision"] == "ELIGIBLE_FOR_AUTHORIZED_CUTOVER"
    assert result["trading_authorized"] is False
    assert result["deployed"] is False


def test_missing_evidence_is_unknown_and_blocks(tmp_path):
    process, result = evaluate(tmp_path, {})
    assert process.returncode == 2
    assert result["decision"] == "HOLD"
    assert all(value == "UNKNOWN" for value in result["gates"].values())


def test_false_pass_from_different_candidate_is_rejected(tmp_path):
    from copytrade_pm.dashboard.grafana_acceptance import MANDATORY_GATES

    gates = {
        name: {
            "status": "PASS",
            "candidate": "d" * 40,
            "bundle_sha256": "b" * 64,
            "evidence": "sha256:" + "c" * 64,
            "issuer": "independent_test_authority",
        }
        for name in MANDATORY_GATES
    }
    process, result = evaluate(tmp_path, gates)
    assert process.returncode == 2
    assert result["decision"] == "HOLD"
    assert all(value == "UNKNOWN" for value in result["gates"].values())


def test_explicit_failure_rejects_even_when_others_pass(tmp_path):
    from copytrade_pm.dashboard.grafana_acceptance import MANDATORY_GATES

    gates = {
        name: {
            "status": "PASS",
            "candidate": "a" * 40,
            "bundle_sha256": "b" * 64,
            "evidence": "sha256:" + "c" * 64,
            "issuer": "independent_test_authority",
        }
        for name in MANDATORY_GATES
    }
    gates["nonowner_tailscale_denial"]["status"] = "FAIL"
    process, result = evaluate(tmp_path, gates)
    assert process.returncode == 2
    assert result["decision"] == "REJECT"


def test_missing_issuer_cannot_qualify_external_gates(tmp_path):
    from copytrade_pm.dashboard.grafana_acceptance import MANDATORY_GATES

    gates = {
        name: {
            "status": "PASS",
            "candidate": "a" * 40,
            "bundle_sha256": "b" * 64,
            "evidence": "sha256:" + "c" * 64,
        }
        for name in MANDATORY_GATES
    }
    process, result = evaluate(tmp_path, gates)
    assert process.returncode == 2
    assert result["gates"]["protected_guardian_journal_noninterference"] == "UNKNOWN"


def test_self_attestation_cannot_qualify_external_gates(tmp_path):
    from copytrade_pm.dashboard.grafana_acceptance import MANDATORY_GATES

    gates = {
        name: {
            "status": "PASS",
            "candidate": "a" * 40,
            "bundle_sha256": "b" * 64,
            "evidence": "sha256:" + "c" * 64,
            "issuer": "dashboard_under_test",
        }
        for name in MANDATORY_GATES
    }
    process, result = evaluate(tmp_path, gates)
    assert process.returncode == 2
    assert result["decision"] == "HOLD"
