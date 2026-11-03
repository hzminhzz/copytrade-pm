"""Read-only scientific evidence readiness from an existing sealed prospective ledger.

Never initializes a ledger, signs outcomes, submits orders or claims alpha.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from .pm_prospective_ledger import ProspectiveLedger
from .trader_intelligence_qualification import audit_prospective_evidence


def run(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--auditor-public-key", required=True, type=Path)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--holdout-start", required=True)
    parser.add_argument("--holdout-end", required=True)
    parser.add_argument("--selection-plan-sha256", required=True)
    parser.add_argument("--horizons", default="5,15,60")
    args = parser.parse_args(argv)
    manifest_file = args.ledger / "manifest.json"
    key_file = args.auditor_public_key
    for file in (manifest_file, key_file):
        if file.is_symlink() or not file.is_file() or file.stat().st_mode & 0o077:
            raise ValueError("INSECURE_OR_MISSING_PROSPECTIVE_READ_ONLY_SOURCE")
    if manifest_file.stat().st_size > 1_000_000 or key_file.stat().st_size != 32:
        raise ValueError("INVALID_PROSPECTIVE_MANIFEST_OR_KEY_SIZE")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema") != "pm01_prospective_receipt_ledger_v1":
        raise ValueError("UNKNOWN_PROSPECTIVE_LEDGER_SCHEMA")
    public = key_file.read_bytes()
    if manifest.get("auditor_public_key_sha256") != sha256(public).hexdigest():
        raise ValueError("INDEPENDENT_AUDITOR_TRUST_ROOT_MISMATCH")
    ledger = ProspectiveLedger.open_existing(
        args.ledger,
        cohort=manifest["cohort"],
        cohort_manifest_sha=manifest["cohort_manifest_sha"],
        audit_public_key=public,
    )
    horizons = tuple(int(h.strip()) for h in args.horizons.split(","))
    return audit_prospective_evidence(
        ledger,
        asof=args.asof,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        selection_plan_sha256=args.selection_plan_sha256,
        required_horizons=horizons,
    ).as_wire()


def main() -> None:
    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
