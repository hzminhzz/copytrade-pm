"""Fail-closed, read-only Grafana release acceptance over externally supplied evidence.

This verifier cannot produce evidence, authorize trading, or deploy software.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MANDATORY_GATES = (
    "five_dashboards_and_visual_review",
    "owner_ingress_and_viewer_isolation",
    "nonowner_tailscale_denial",
    "source_provenance_and_finance_nulls",
    "causal_execution_evidence",
    "alert_fault_recovery_and_browser_independence",
    "plugin_restart_and_concurrent_viewers",
    "resource_and_latency_budget",
    "protected_guardian_journal_noninterference",
    "installed_image_and_rollback",
)
EXTERNAL_GATES = frozenset(
    (
        "nonowner_tailscale_denial",
        "source_provenance_and_finance_nulls",
        "causal_execution_evidence",
        "protected_guardian_journal_noninterference",
        "installed_image_and_rollback",
    )
)
SHA = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")


def evaluate(receipt: dict, *, candidate: str, bundle_sha256: str) -> dict:
    """Only evidence bound to the selected immutable candidate can pass."""
    if not COMMIT.fullmatch(candidate) or not SHA.fullmatch(bundle_sha256):
        raise ValueError("INVALID_CANDIDATE_PIN")
    if not isinstance(receipt, dict) or receipt.get("schema") != "grafana_acceptance_evidence_v1":
        raise ValueError("INVALID_EVIDENCE_SCHEMA")
    entries = receipt.get("gates")
    if not isinstance(entries, dict):
        raise ValueError("INVALID_GATE_MAP")
    valid_envelope = (
        receipt.get("candidate") == candidate and receipt.get("bundle_sha256") == bundle_sha256
    )
    states = {}
    for name in MANDATORY_GATES:
        item = entries.get(name)
        if not valid_envelope or not isinstance(item, dict):
            states[name] = "UNKNOWN"
            continue
        valid = (
            item.get("candidate") == candidate
            and item.get("bundle_sha256") == bundle_sha256
            and isinstance(item.get("evidence"), str)
            and item["evidence"].startswith("sha256:")
            and bool(SHA.fullmatch(item["evidence"][7:]))
            and isinstance(item.get("issuer"), str)
            and bool(item["issuer"].strip())
            and item["issuer"] != "dashboard_under_test"
        )
        if not valid:
            states[name] = "UNKNOWN"
        else:
            status = item.get("status")
            states[name] = status if status in ("PASS", "FAIL", "UNKNOWN") else "UNKNOWN"
    decision = (
        "REJECT"
        if "FAIL" in states.values()
        else "ELIGIBLE_FOR_AUTHORIZED_CUTOVER"
        if all(v == "PASS" for v in states.values())
        else "HOLD"
    )
    return {
        "schema": "grafana_acceptance_decision_v1",
        "candidate": candidate,
        "bundle_sha256": bundle_sha256,
        "decision": decision,
        "gates": states,
        "deployed": False,
        "trading_authorized": False,
        "limitations": [
            "Evidence fingerprints are not independent cryptographic signatures.",
            "Source receipts do not attest installed runtime unless independently observed.",
            "Eligibility is not authorization to deploy or trade.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    result = evaluate(receipt, candidate=args.candidate, bundle_sha256=args.bundle_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["decision"] != "ELIGIBLE_FOR_AUTHORIZED_CUTOVER":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
