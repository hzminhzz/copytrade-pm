"""Independently verify immutable prospective E4 stream evidence; never authorize trading."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from .pm_e4_stream import PORTFOLIO_PODS


def audit(store: Path, portfolio: str) -> dict:
    """Audit raw bytes and metadata, not the untrusted session counters alone."""
    if portfolio not in PORTFOLIO_PODS:
        raise ValueError("UNKNOWN_PORTFOLIO")
    generations = sorted(p for p in store.glob("gE4*") if p.is_dir())
    results = []
    previous_finished: datetime | None = None
    for directory in generations:
        errors: list[str] = []
        report_path = directory / "session-report.json"
        try:
            report = json.loads(report_path.read_bytes())
        except (OSError, ValueError):
            results.append({"generation": directory.name, "status": "INVALID_REPORT"})
            continue
        checked = 0
        metadata_files = sorted((directory / "metadata").glob("*.json"))
        for meta_file in metadata_files:
            try:
                meta = json.loads(meta_file.read_bytes())
                filename = meta["filename"]
                if Path(filename).name != filename or "/" in filename:
                    raise ValueError("UNSAFE_FILENAME")
                raw = (directory / "frames" / filename).read_bytes()
                if sha256(raw).hexdigest() != meta["source_raw_sha256"]:
                    raise ValueError("RAW_HASH_MISMATCH")
                received_at = datetime.fromisoformat(meta["locally_received_at"])
                if received_at.tzinfo is None:
                    raise ValueError("NAIVE_RECEIPT_TIME")
                frame = json.loads(raw)
                if frame.get("channel") != meta["channel"]:
                    raise ValueError("CHANNEL_MISMATCH")
                checked += 1
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{meta_file.name}:{type(exc).__name__}")
        if checked != report.get("frames_stored"):
            errors.append("FRAME_COUNT_MISMATCH")
        if len(list((directory / "frames").glob("*.json"))) != checked:
            errors.append("RAW_FRAME_COUNT_MISMATCH")
        if report.get("errors"):
            errors.append("SOURCE_SESSION_ERRORS")
        if report.get("disconnect_reason") != "BOUNDED_SESSION_ROTATION":
            errors.append("INCOMPLETE_SESSION")
        observed = report.get("snapshots", {})
        expected = set(PORTFOLIO_PODS[portfolio])
        if not expected.issubset(observed):
            errors.append("MISSING_MASTER_ACCOUNT_SNAPSHOTS")
        counts = report.get("subaccount_counts", {})
        for alias in expected:
            if not isinstance(counts.get(alias), int):
                errors.append("MISSING_SUBACCOUNT_CENSUS")
            elif sum(k.startswith(alias + "-sub") for k in observed) != counts[alias]:
                errors.append("MISSING_SUBACCOUNT_SNAPSHOTS")
        try:
            started = datetime.fromisoformat(report["started_at"])
            finished = datetime.fromisoformat(report["finished_at"])
            if started.tzinfo is None or finished.tzinfo is None or finished < started:
                errors.append("INVALID_SESSION_TIMESTAMPS")
            if previous_finished is not None:
                if started < previous_finished:
                    errors.append("OVERLAPPING_SESSIONS_NOT_DEDUPLICATED")
                elif started > previous_finished:
                    errors.append("INTER_SESSION_GAP_UNPROVEN_CONTINUITY")
            previous_finished = finished
        except (KeyError, TypeError, ValueError):
            errors.append("INVALID_SESSION_TIMESTAMPS")
        results.append({
            "generation": directory.name,
            "session_report_sha256": sha256(report_path.read_bytes()).hexdigest(),
            "verified_frame_count": checked,
            "observed_accounts": len(observed),
            "errors": errors,
            "status": "OBSERVED_BOUNDED_ONLY" if not errors else "BLOCKED",
        })
    return {
        "schema": "e4_independent_source_integrity_v1",
        "portfolio": portfolio,
        "prospective_generations": results,
        "all_generations_integrity_pass": bool(results) and all(
            not row.get("errors") for row in results
        ),
        "continuous_account_book_qualified": False,
        "equity_collateral_funding_transfers_reconciled": False,
        "historical_q3_first_known_reconstructed": False,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--portfolio", choices=tuple(PORTFOLIO_PODS), required=True)
    args = p.parse_args()
    print(json.dumps(audit(args.store, args.portfolio), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
