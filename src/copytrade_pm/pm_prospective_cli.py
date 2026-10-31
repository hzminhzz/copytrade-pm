"""Offline PM-01 receipt→audit→outcome journal. No source polling or order API.

The independent auditor signs attestations outside this process. No private
signing key or raw wallet mapping is accepted as a CLI argument or written.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from .pm_prospective_ledger import ProspectiveLedger, digest
from .pm_sources import load_cohort


def load_auditor_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != 32:
        raise ValueError("INVALID_AUDITOR_PUBLIC_KEY")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("INVALID_AUDITOR_PUBLIC_KEY")
    return key


def cohort_contract(root: Path) -> tuple[dict[str, str], str]:
    entries, fingerprints = load_cohort(root)
    cohorts = {}
    for row in entries:
        cohorts[row.cohort] = cohorts.get(row.cohort, 0) + 1
    if len(entries) != 36 or cohorts != {"original": 6, "wave1": 10, "wave2": 20}:
        raise ValueError("INVALID_PRIVATE_36_WALLET_COHORT")
    aliases = {entry.alias: entry.address_sha256 for entry in entries}
    if len(aliases) != 36 or len(set(aliases.values())) != 36:
        raise ValueError("INVALID_COHORT_ALIAS_IDENTITY")
    return aliases, digest(fingerprints)


def open_ledger(
    *,
    root: Path,
    research_root: Path,
    auditor_key_file: Path,
) -> ProspectiveLedger:
    cohort, manifest_sha = cohort_contract(research_root)
    return ProspectiveLedger.open_existing(
        root,
        cohort=cohort,
        cohort_manifest_sha=manifest_sha,
        audit_public_key=load_auditor_key(auditor_key_file),
    )


def run(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("init", "ingest", "audit", "outcome", "inspect"))
    p.add_argument("--research-root", required=True, type=Path)
    p.add_argument("--ledger", required=True, type=Path)
    p.add_argument("--auditor-public-key", required=True, type=Path)
    p.add_argument("--receipts", type=Path)
    p.add_argument("--attestation-file", type=Path)
    p.add_argument("--asof")
    args = p.parse_args(argv)
    if args.action == "init":
        cohort, manifest_sha = cohort_contract(args.research_root)
        journal = ProspectiveLedger(
            args.ledger,
            cohort=cohort,
            cohort_manifest_sha=manifest_sha,
            audit_public_key=load_auditor_key(args.auditor_public_key),
        )
        journal.read()
        return {
            "status": "INITIALIZED",
            "schema": journal.manifest["schema"],
            "wallet_count": len(cohort),
            "ledger_head_sha256": journal.head_sha,
            "research_only": True,
        }
    journal = open_ledger(
        root=args.ledger,
        research_root=args.research_root,
        auditor_key_file=args.auditor_public_key,
    )
    if args.action == "ingest":
        if args.receipts is None:
            raise ValueError("MISSING_PRODUCER_RECEIPTS_DIRECTORY")
        return journal.ingest_folder(args.receipts)
    if args.action in {"audit", "outcome"}:
        if args.attestation_file is None:
            raise ValueError("MISSING_SIGNED_ATTESTATION_FILE")
        file = args.attestation_file
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 64_000:
            raise ValueError("INVALID_SIGNED_ATTESTATION_FILE")
        if file.stat().st_mode & 0o077:
            raise ValueError("ATTESTATION_FILE_NOT_OWNER_PRIVATE")
        signed = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(signed, dict) or not isinstance(signed.get("attestation"), dict):
            raise ValueError("INVALID_SIGNED_ATTESTATION_PAYLOAD")
        signature_hex = signed.get("signature_hex")
        if not isinstance(signature_hex, str):
            raise ValueError("INVALID_SIGNED_ATTESTATION_PAYLOAD")
        sha = (
            journal.audit_receipt(signed["attestation"], signature_hex)
            if args.action == "audit"
            else journal.record_matched_outcome(signed["attestation"], signature_hex)
        )
        return {"status": "SEALED", "event_sha256": sha, "research_only": True}
    if args.asof is None:
        raise ValueError("ASOF_REQUIRED")
    asof = datetime.fromisoformat(args.asof)
    if asof.tzinfo is None:
        raise ValueError("NAIVE_PROSPECTIVE_CLOCK")
    consumer = journal.pm02_rows_asof(asof.isoformat())
    return {
        "schema": "pm01_prospective_readiness_v1",
        "asof": asof.astimezone(UTC).isoformat(),
        "ledger_head_sha256": journal.head_sha,
        "receipt_count": len(journal.receipts_asof(asof.isoformat())),
        "pm02_episode_count": sum(len(v) for v in consumer.values()),
        "prospective_research_only": True,
        "no_broker_or_live_authority": True,
    }


def main() -> None:
    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
