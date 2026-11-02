"""Credential-free Combo 2 paper replay and local status.

Reads a frozen first-known fixture. Writes only an owner-private local paper
event ledger. There is intentionally no broker/network/order client.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pm_combo2 import Combo2PaperTracker, PaperPolicy


def replay(path: Path, root: Path) -> dict:
    contents = json.loads(path.read_text(encoding="utf-8"))
    if contents.get("schema") != "combo2_first_known_fixture_v1":
        raise ValueError("UNSUPPORTED_COMBO2_INPUT_SCHEMA")
    tracker = Combo2PaperTracker(
        root,
        run_id=contents["run_id"],
        started_at=contents["started_at"],
        source_subject_hashes=contents["source_subject_hashes"],
        policy=PaperPolicy(),
    )
    for record in contents["events"]:
        if record.get("kind") not in {
            "SOURCE_RECEIPT",
            "PAPER_REBALANCE",
            "PAPER_MARK",
            "PAPER_FUNDING",
            "OPERATOR_RESET",
        }:
            raise ValueError("UNKNOWN_OR_NETWORK_MUTATING_EVENT")
        tracker.record(
            kind=record["kind"],
            event_id=record["event_id"],
            source_event_at=record["source_event_at"],
            first_known_at=record["first_known_at"],
            decision_at=record["decision_at"],
            hypothetical_fill_at=record["hypothetical_fill_at"],
            data=record["data"],
        )
    return tracker.state()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combo 2 five-minute paper replay; no network or broker orders"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.input, args.paper_root)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
