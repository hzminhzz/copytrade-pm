"""Read-only operator projection of private forward-paper state (FP-11 partial).

Checks journal state via SQLite mode=ro, never opens worker, network,
broker or service manager. Runtime status does not imply scientific validity.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import shutil

from .pm03_account import clock
from .pm_forward_journal import PaperJournal
from .pm_sqlite_readonly import connect_readonly


def paper_operator_status(
    db_path: Path,
    *,
    run_id: str,
    as_of: str,
    worker_pid: int | None = None,
    worker_heartbeat_at: str | None = None,
    transport_heartbeat_at: str | None = None,
    source_snapshot_at: str | None = None,
    market_quote_at: str | None = None,
    last_wallet_trade_at: str | None = None,
    heartbeat_root: Path | None = None,
) -> dict:
    now = clock(as_of)

    def age(when: str | None) -> float | None:
        if not when:
            return None
        seconds = (now - clock(when)).total_seconds()
        if seconds < 0:
            raise ValueError("FUTURE_RUNTIME_HEARTBEAT")
        return seconds

    with closing(connect_readonly(db_path, timeout=0, query_only=False)) as db:
        state = PaperJournal.verify(db, run_id)
        source_count = db.execute("SELECT COUNT(*) FROM source_receipts").fetchone()[0]
    heartbeat_age = age(worker_heartbeat_at)
    transport_age = age(transport_heartbeat_at)
    snapshot_age = age(source_snapshot_at)
    market_age = age(market_quote_at)
    trade_age = age(last_wallet_trade_at)
    if worker_pid is None or heartbeat_age is None:
        health = "NOT_RUNNING"
        reasons = ["WORKER_NOT_ATTESTED"]
    elif heartbeat_age > 90:
        health = "STALE"
        reasons = ["WORKER_HEARTBEAT_STALE"]
    else:
        # Caller-supplied PID/timestamps are not independent OS or signed
        # heartbeat attestation. Never elevate an unverifiable worker to healthy.
        reasons = ["WORKER_IDENTITY_UNATTESTED"]
        if transport_age is None or transport_age > 90:
            reasons.append("TRANSPORT_NOT_HEALTHY")
        if snapshot_age is None or snapshot_age > 180:
            reasons.append("SOURCE_SNAPSHOT_STALE_OR_MISSING")
        if market_age is None or market_age > 90:
            reasons.append("MARKET_QUOTE_STALE_OR_MISSING")
        health = "DEGRADED"
    if state["account"]["risk"] == "HALT":
        health = "HALT"
        reasons.append("PM03_HALT_LATCHED")
    observer = None
    if heartbeat_root is not None:
        from .pm_forward_heartbeat import inspect_observer_heartbeat

        class ReadOnlyJournalView:
            path = Path(db_path)

            def restore(self, selected_run: str) -> dict:
                with closing(connect_readonly(self.path, timeout=0)) as conn:
                    return PaperJournal.verify(conn, selected_run)

        observer = inspect_observer_heartbeat(
            heartbeat_root,
            journal=ReadOnlyJournalView(),
            run_id=run_id,
            as_of=as_of,
        )
        if observer["health"] == "UNKNOWN" and health != "HALT":
            health = "UNKNOWN"
            reasons = list(dict.fromkeys(reasons + observer["reasons"]))
        elif observer["health"] == "HALT":
            health = "HALT"
            reasons = list(dict.fromkeys(reasons + observer["reasons"]))
        else:
            health = "DEGRADED" if health != "HALT" else "HALT"
            reasons = list(dict.fromkeys(reasons + observer["reasons"]))
    free = shutil.disk_usage(Path(db_path).parent).free
    return {
        "schema": "paper_operator_status_v1",
        "run_id": run_id,
        "as_of": as_of,
        "health": health,
        "reasons": reasons,
        "order_route": "NONE",
        "paper_admitted": False,
        "worker_pid": worker_pid,
        "heartbeat_age_seconds": heartbeat_age,
        "transport_age_seconds": transport_age,
        "source_snapshot_age_seconds": snapshot_age,
        "market_quote_age_seconds": market_age,
        "last_wallet_trade_age_seconds": trade_age,
        "quiet_wallet_not_automatic_disconnect": True,
        "local_source_receipt_count": source_count,
        "journal_head_sha": state["journal_head_sha"],
        "manifest_sha": state["manifest_sha"],
        "cursor": state["cursor"],
        "account_risk": state["account"]["risk"],
        "disk_free_bytes": free,
        "scientifically_qualified": False,
        "real_worker_evidence": False,
        "independent_observer_evidence": observer,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only local paper status")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--heartbeat-root", type=Path)
    parser.add_argument("--as-of", default=datetime.now().astimezone().isoformat())
    args = parser.parse_args()
    print(
        json.dumps(
            paper_operator_status(
                args.db,
                run_id=args.run_id,
                as_of=args.as_of,
                heartbeat_root=args.heartbeat_root,
            ),
            sort_keys=True,
            indent=2,
        )
    )
