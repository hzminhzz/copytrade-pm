"""Reusable SQLite busy retry and per-ledger isolation for historical paper replay.

No scheduler, source signals, live paper launcher or broker authority.
"""

from __future__ import annotations

import sqlite3

from .pm_forward_observed_paper import ObservedP1Paper


def _is_retryable_sqlite_busy(exc: Exception) -> bool:
    """Retry only SQLite contention; corrupt or unavailable journals still quarantine."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(code, int) and (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return True
    return (
        str(exc)
        .lower()
        .startswith(("database is locked", "database is busy", "database table is locked"))
    )


def _tick_runs(
    runs: dict[str, ObservedP1Paper],
    prior: dict[str, tuple],
    quarantined: dict[str, str],
    retrying_busy: set[str],
) -> dict[str, dict]:
    """A transient database reader lock must not permanently retire a virtual ledger.

    Preserve its previous durable state and retry on the next tick. A different
    exception still quarantines this run without changing another portfolio.
    """
    changed: dict[str, dict] = {}
    for pid, paper in runs.items():
        if pid in quarantined:
            continue
        try:
            result = paper.step()
        except Exception as exc:
            if _is_retryable_sqlite_busy(exc):
                if pid not in retrying_busy:
                    changed[pid] = {
                        "tick": "WAIT_SQLITE_BUSY_RETRY",
                        "reason": "TRANSIENT_SQLITE_BUSY",
                        "order_route": "NONE",
                    }
                retrying_busy.add(pid)
                continue
            retrying_busy.discard(pid)
            quarantined[pid] = type(exc).__name__ + ":" + str(exc)[:160]
            changed[pid] = {
                "tick": "BLOCKED_PAPER_LEDGER",
                "reason": quarantined[pid],
                "order_route": "NONE",
            }
            continue
        recovered = pid in retrying_busy
        retrying_busy.discard(pid)
        state = (
            result["tick"],
            result["net_pnl"],
            tuple(sorted(result["source_results"].items())),
            tuple(sorted(result["execution_results"].items())),
            result["risk"],
            tuple(sorted(result["execution_outcomes"])),
        )
        if prior.get(pid) != state or recovered:
            changed[pid] = {
                "run_id": result["run_id"],
                "tick": result["tick"],
                "source_results": result["source_results"],
                "execution_results": result["execution_results"],
                "exit_results": result["exit_results"],
                "net_pnl": result["net_pnl"],
                "risk": result["risk"],
                "real_broker_fills": 0,
                "recovered_from_sqlite_busy": recovered,
            }
            prior[pid] = state
    return changed
