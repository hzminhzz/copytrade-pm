"""Verify identified original native rows read-only; print no account addresses."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_stream_journal import validate_event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--sample",
        type=Path,
        required=True,
    )
    args = parser.parse_args()
    samples = json.loads(args.sample.read_text())
    with closing(
        sqlite3.connect("file:" + str(args.database.resolve()) + "?mode=ro", uri=True)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for sample in samples:
            row = db.execute(
                "SELECT payload,event_sha,receipt_refs,prior_sha,chain_sha,committed_at "
                "FROM observer_stream_events WHERE stream_id=? AND seq=?",
                (sample["stream"], sample["seq"]),
            ).fetchone()
            if row is None:
                raise ValueError("BASELINE_NATIVE_ROW_MISSING")
            raw, event_sha, refs, prior, chain, committed = row
            event = json.loads(raw)
            validate_event(event)
            wire = event["details"]["native_wire"]
            frame = event["details"]["native_frame"]
            expected_chain = digest(
                [sample["stream"], sample["seq"], event_sha, prior, committed, json.loads(refs)]
            )
            if not (
                sha256(wire.encode()).hexdigest() == event["raw_sha"] == sample["raw_sha"]
                and digest(event) == event_sha
                and chain == expected_chain
                and digest(frame) == sample["native_frame_sha"]
                and event["first_known_at"] == sample["known_at"]
                and event["source_event_at"] == sample["source_at"]
            ):
                raise ValueError("BASELINE_NATIVE_EVIDENCE_DIVERGENCE")
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "native_rows": len(samples),
                "sample_sha256": sha256(args.sample.read_bytes()).hexdigest(),
                "database_mutated": False,
                "full_journal_audit": False,
            }
        )
    )


if __name__ == "__main__":
    main()
