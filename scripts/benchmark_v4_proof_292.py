"""40,000-event/account indexed official proof benchmark for issue #292.

Synthetic, immutable local SQLite only. No network, broker, or live source DB.
Run: PYTHONPATH=.:tests uv run --frozen --group dev python scripts/benchmark_v4_proof_292.py
"""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import statistics
import tempfile
from time import perf_counter

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_stream_journal import (
    INTERRUPTION_INDEX_SCHEMA,
    append_checkpoint,
    verify_official_position_transition,
    stream_event,
)
from copytrade_pm.pm_forward_observed_paper import _read_source, _readonly
from copytrade_pm.pm_v4_selected_positions import official_accounts
from test_pm_vike_paper_integration import official_frame
from test_pm_forward_observed_paper import at


def build(path: Path, *, event_count: int = 40_000) -> dict:
    journal = PaperJournal(path)
    address = official_frame(1, 0)["data"]["user"]

    def info(_):
        raw = b"[null]"
        return [None], raw, sha256(raw).hexdigest()

    source = official_accounts(journal, {"S035": address}, info=info, compact_evidence=True)["S035"]
    source.begin(at(0))
    for seconds, qty in ((1, 0), (12, 20)):
        frame = official_frame(seconds, qty)
        wire = json.dumps(frame, separators=(",", ":"))
        source.observe(frame, at(seconds + 1), raw_text=wire)
    with closing(_readonly(journal.path)) as db:
        receipt = _read_source(db, "S035", 2)
    assert receipt is not None
    sid, epoch = "account:S035", source.epoch
    state = source.checkpoint
    cursor = source.progress.head["cursor"]
    start = perf_counter()
    with closing(sqlite3.connect(journal.path, isolation_level=None)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            for index in range(event_count):
                known_at = at(14 + index)
                event = stream_event(
                    stream_id=sid,
                    epoch=epoch,
                    kind="TRANSPORT",
                    known_at=known_at,
                    expected_cursor=cursor,
                    checkpoint={**state, "last_transport_at": known_at},
                    details={},
                    compact_v2=True,
                )
                result = append_checkpoint(db, event, [])
                cursor = result["cursor"]
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        # Heavy historical index builds are quiescent migration steps, not
        # normal service startup. Build the SQLite partial index here.
        db.executescript(INTERRUPTION_INDEX_SCHEMA)
    build_seconds = perf_counter() - start
    with closing(_readonly(journal.path)) as db:
        plan = [
            str(row[-1])
            for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT e.seq FROM observer_source_locators l "
                "JOIN observer_stream_events e ON e.stream_id=l.stream_id "
                "AND e.seq=l.event_seq WHERE l.stream_id=? "
                "AND l.source_id=? AND l.receipt_id=? AND l.receipt_sha=?",
                (sid, "S035", receipt["receipt_id"], receipt["sha"]),
            )
        ]
        interruptions_plan = [
            str(row[-1])
            for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT 1 FROM observer_stream_events "
                "WHERE stream_id=? AND seq>? "
                "AND json_extract(payload,'$.kind') IN ('GAP','BASELINE','SCOPE') LIMIT 1",
                (sid, 3),
            )
        ]
        assert any("INDEX" in item.upper() for item in plan)
        assert any("observer_stream_interruptions_idx" in item for item in interruptions_plan)
        samples = []
        for _ in range(100):
            start = perf_counter()
            assert verify_official_position_transition(
                db,
                alias="S035",
                receipt_id=receipt["receipt_id"],
                receipt_sha=receipt["sha"],
                receipt=receipt["receipt"],
                require_current_positions=True,
            )
            samples.append((perf_counter() - start) * 1000)
    return {
        "schema": "v4_proof_40k_indexed_292_v1",
        "verified": True,
        "synthetic": True,
        "stream_events": cursor,
        "added_transport_events": event_count,
        "build_seconds": round(build_seconds, 3),
        "proof_p50_ms": round(statistics.median(samples), 3),
        "proof_p95_ms": round(sorted(samples)[94], 3),
        "proof_max_ms": round(max(samples), 3),
        "indexed_locator_plan": plan,
        "indexed_interruptions_plan": interruptions_plan,
        "db_bytes": journal.path.stat().st_size,
        "wal_bytes": Path(str(journal.path) + "-wal").stat().st_size
        if Path(str(journal.path) + "-wal").exists()
        else 0,
        "source_finance": "SYNTHETIC_NO_BROKER",
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="v4-proof-scale-292-") as root:
        print(json.dumps(build(Path(root) / "paper"), sort_keys=True))


if __name__ == "__main__":
    main()
