"""Read-only V4 0811/0911 source journal sizing and process evidence (#292)."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from copytrade_pm.pm_v4_sqlite_recovery import active_source_handles


def inspect(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("V4_INSPECT_SOURCE_INVALID")
    db_path = path.resolve()
    stat = os.statvfs(db_path.parent)
    result = {
        "schema": "v4_sqlite_runtime_inspection_292_v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_db": str(db_path),
        "db_bytes": db_path.stat().st_size,
        "wal_bytes": Path(str(db_path) + "-wal").stat().st_size
        if Path(str(db_path) + "-wal").exists()
        else 0,
        "shm_bytes": Path(str(db_path) + "-shm").stat().st_size
        if Path(str(db_path) + "-shm").exists()
        else 0,
        "filesystem_free_bytes": stat.f_bavail * stat.f_frsize,
        "same_user_active_db_handles": active_source_handles(db_path),
        "source_and_paper_only": True,
        "broker_route": "NONE",
        "checkpoint_passive_attempted": False,
    }
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only=ON")
        for metric in ("page_size", "page_count", "freelist_count"):
            result[metric] = db.execute(f"PRAGMA {metric}").fetchone()[0]
        result["streams"] = [
            {"stream_id": row[0], "cursor": row[1], "chain_sha": row[2], "last_known_at": row[3]}
            for row in db.execute(
                "SELECT h.stream_id,h.cursor,h.chain_sha,"
                "json_extract(e.payload, '$.first_known_at') "
                "FROM observer_stream_heads h "
                "JOIN observer_stream_events e "
                "ON e.stream_id=h.stream_id AND e.seq=h.cursor "
                "ORDER BY h.stream_id"
            )
        ]
        result["total_stream_events"] = sum(row["cursor"] for row in result["streams"])
        result["source_receipt_cursors"] = [
            {"alias": row[0], "max_seq": row[1]}
            for row in db.execute(
                "SELECT source_id,MAX(seq) FROM source_receipts GROUP BY source_id"
            )
        ]
        result["locator_table_present"] = (
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observer_source_locators'"
            ).fetchone()
            is not None
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db", nargs="+", type=Path)
    args = parser.parse_args()
    for db in args.db:
        print(json.dumps(inspect(db), sort_keys=True))
