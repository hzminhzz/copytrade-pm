"""Shared read-only SQLite connection helper."""

from __future__ import annotations

from pathlib import Path
import sqlite3


def connect_readonly(
    path: Path,
    *,
    timeout: float = 5.0,
    query_only: bool = True,
) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, timeout=timeout)
    if query_only:
        conn.execute("PRAGMA query_only=ON")
    return conn
