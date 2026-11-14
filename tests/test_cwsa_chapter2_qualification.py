"""Qualification and receipt gates must fail closed on research-only claims."""

import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from decimal import Decimal
from types import SimpleNamespace

from copytrade_pm.pm_cwsa_paper_qualification import (
    inspect_qualification,
    qualification_blockers,
    paper_candidate,
    mandate_k_blockers,
)
from copytrade_pm.pm_cwsa_chapter2_gate import EXPECTED_PORTFOLIOS
from copytrade_pm.pm_ci_receipt import _verify_steps, _pytest_counts
from copytrade_pm.production_manifest import sign


def seals():
    return {pid: {"definition_sha256": "a" * 64} for pid in EXPECTED_PORTFOLIOS}


def qualify(candidate):
    candidate["effective_from_ms"] = 1_900_000_000_000
    for rec in candidate["portfolios"].values():
        rec["qualification"] = "QUALIFIED"
        rec["negative_findings"] = []
        for member in rec["members"].values():
            member.update(
                {
                    "frozen_k": "0.01",
                    "risk_approved_max_k": "0.02",
                    "research_basis": "POINT_IN_TIME",
                    "oos_status": "PASS",
                    "original_cost_evidence": True,
                    "independent_market_evidence": True,
                    **{
                        key: "b" * 64
                        for key in (
                            "track_c_report_sha256",
                            "source_sha256",
                            "market_sha256",
                            "cost_sha256",
                            "oos_report_sha256",
                        )
                    },
                }
            )
    return candidate


def test_unqualified_candidate_keeps_research_failures():
    payload = paper_candidate(seals(), now_ms=1_800_000_000_000)
    assert "UNQUALIFIED_K:A" in qualification_blockers(payload, seals(), now_ms=1_800_000_000_000)
    assert set(payload["portfolios"]) == set(EXPECTED_PORTFOLIOS)
    assert all(row["qualification"] == "UNQUALIFIED_K" for row in payload["portfolios"].values())


def test_paper_qualification_validates_risk_oos_and_portfolio_identity():
    payload = qualify(paper_candidate(seals(), now_ms=1_800_000_000_000))
    assert not qualification_blockers(payload, seals(), now_ms=1_800_000_000_000)
    payload["portfolios"]["A"]["members"]["W028"]["risk_approved_max_k"] = "0.001"
    assert "K_RISK_LIMIT:A/W028" in qualification_blockers(
        payload, seals(), now_ms=1_800_000_000_000
    )
    payload["portfolios"]["A"]["members"]["W028"]["risk_approved_max_k"] = "0.02"
    payload["portfolios"]["A"]["members"]["W028"]["oos_status"] = "UNQUALIFIED_K"
    assert "K_NOT_PIT_OOS:A/W028" in qualification_blockers(
        payload, seals(), now_ms=1_800_000_000_000
    )


def test_qualification_requires_independent_pinned_research_key(tmp_path):
    payload = qualify(paper_candidate(seals(), now_ms=1_800_000_000_000))
    payload["effective_from_ms"] = 5_000_000_000_000
    payload["known_at_ms"] = 1_700_000_000_000
    key = Ed25519PrivateKey.generate()
    bundle = sign(payload, key, "cwsa-paper-k-research-only")
    path = tmp_path / "attested.json"
    path.write_text(json.dumps(bundle))
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"evidence placeholder")
    assert (
        inspect_qualification(
            path, key.public_key().public_bytes_raw().hex(), seals(), source
        ).state
        == "PASS"
    )
    assert inspect_qualification(path, "c" * 64, seals(), source).state == "FAIL"
    bundle["payload"]["portfolios"]["A"]["members"]["W028"]["frozen_k"] = "9"
    path.write_text(json.dumps(bundle))
    assert (
        inspect_qualification(
            path, key.public_key().public_bytes_raw().hex(), seals(), source
        ).state
        == "FAIL"
    )


def test_signed_mandate_k_and_activation_cannot_drift_from_research():
    payload = qualify(paper_candidate(seals(), now_ms=1_800_000_000_000))

    def mk(**kw):
        return SimpleNamespace(**kw)

    binding = {
        "A": mk(
            mandates=[
                (
                    mk(
                        source_id="W028",
                        k=Decimal("0.01"),
                        effective_from_ms=payload["effective_from_ms"],
                    ),
                    {},
                ),
            ]
        )
    }
    assert not mandate_k_blockers(binding, payload)
    binding["A"].mandates[0][0].k = Decimal("0.2")
    assert any("VALUE_MISMATCH" in x for x in mandate_k_blockers(binding, payload))
    binding["A"].mandates[0][0].k = Decimal("0.01")
    binding["A"].mandates[0][0].effective_from_ms -= 1
    assert any("BEFORE_RESEARCH" in x for x in mandate_k_blockers(binding, payload))


def test_receipt_rejects_skip_and_partial_results():
    assert _pytest_counts("1900 passed, 40 skipped in 12.0s") == {"passed": 1900, "skipped": 40}
    assert _pytest_counts("FAILED 3 tests") == {"passed": 0, "skipped": 0}
    incomplete = {
        "schema": "copytrade_local_ci_receipt_v1",
        "stage": "premerge",
        "leg": "all",
        "status": "PASS",
    }
    failures = _verify_steps(incomplete)
    assert "MISSING_REQUIRED_LOGS" in failures
    assert "MISSING_OR_SKIPPED_REQUIRED_ADVERSARIAL_TESTS" in failures


def test_receipt_requires_local_worktree_project_binding():
    from copytrade_pm.pm_ci_receipt import ALL_HASHES, REQUIRED_LOGS

    receipt = {
        "schema": "copytrade_local_ci_receipt_v1",
        "stage": "premerge",
        "leg": "all",
        "status": "PASS",
        "logs": {name: {} for name in REQUIRED_LOGS},
        "commands": {name: "checked" for name in REQUIRED_LOGS},
        "sources": {name: "hash" for name in ALL_HASHES},
        "tests": {
            "core": {"passed": 1500, "skipped": 0},
            "market": {"passed": 1700, "skipped": 0},
            "adversarial": {"passed": 40, "skipped": 0},
        },
        "checks": {
            name: "PASS"
            for name in (
                "core",
                "market",
                "adversarial",
                "frontend",
                "build",
                "ruff",
                "format",
                "types",
                "project_binding",
            )
        },
    }
    assert _verify_steps(receipt) == []
    del receipt["checks"]["project_binding"]
    assert "REQUIRED_BUILD_OR_LINT_GATE_NOT_PASS" in _verify_steps(receipt)
