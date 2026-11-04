"""Read-only forward-paper journal observations for the owner-private registry.

FP's PM-03 Account and WAL/FULL PaperJournal are the sole financial authorities.
This adapter never starts, stops, imports the writer, or modifies a paper worker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from . import wallet_registry_fp_journal as fp_journal

RUN_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_run_evidence(
    run_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, version INTEGER NOT NULL,
    portfolio_definition_sha256 TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL, status_sha256 TEXT NOT NULL,
    account_ref_sha256 TEXT NOT NULL UNIQUE, journal_ref_sha256 TEXT NOT NULL,
    run_root TEXT NOT NULL, observed_at TEXT NOT NULL,
    status TEXT NOT NULL, reason TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES portfolio_runs(run_id),
    FOREIGN KEY(portfolio_id,version) REFERENCES portfolio_versions(portfolio_id,version)
);
"""


def _unknown(reason: str) -> dict:
    return {
        "state": "UNKNOWN",
        "reason": reason,
        "order_route": "NONE",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "paper_observation_only": True,
    }


def inspect_run(
    run_dir: Path,
    selection: dict,
    *,
    now: datetime | None = None,
    run_id: str | None = None,
) -> dict:
    """Validate only the actual FP-01/02 SQLite journal contract.

    The earlier experimental JSONL v1 projection is deliberately unsupported:
    two different envelopes cannot truthfully share one v1 authority.
    """
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("now must have an offset")
    source = run_dir / "paper-events.sqlite3"
    if not source.is_file() and not source.is_symlink():
        return _unknown("UNSUPPORTED_LEGACY_PROJECTION_OR_MISSING_JOURNAL")
    return fp_journal.inspect_fp_journal(run_dir, selection, run_id=run_id, now=at)


def store_observation(con, observation: dict, *, observed_at: str) -> None:
    """Revalidate external bytes before indexing ONLY the private WR database."""
    if observation.get("state") == "UNKNOWN" or not observation.get("run_id"):
        raise ValueError("unverified paper identity must not be indexed")
    from .wallet_registry_portfolios import select_asof

    selection = select_asof(con, observation["portfolio_id"], observed_at)
    if (
        selection.get("definition_sha256") != observation["portfolio_definition_sha256"]
        or selection.get("version") != observation["portfolio_version"]
    ):
        raise ValueError("stale portfolio definition; new run required")
    verified = inspect_run(
        Path(observation["run_root"]),
        selection,
        run_id=observation["run_id"],
        now=datetime.fromisoformat(observed_at),
    )
    if verified != observation:
        raise ValueError("paper observation changed or failed re-verification")
    row = con.execute(
        "SELECT run_id,portfolio_id,version,account_ref,journal_ref "
        "FROM portfolio_runs WHERE run_id=?",
        (observation["run_id"],),
    ).fetchone()
    identity = (
        observation["run_id"],
        observation["portfolio_id"],
        observation["portfolio_version"],
        observation["account_ref_sha256"],
        observation["journal_ref_sha256"],
    )
    if row and row != identity:
        raise ValueError("paper run identity or account changed; new run required")
    existing_evidence = con.execute(
        "SELECT manifest_sha256,run_root FROM portfolio_run_evidence WHERE run_id=?",
        (observation["run_id"],),
    ).fetchone()
    if existing_evidence and existing_evidence != (
        observation["manifest_sha256"],
        observation["run_root"],
    ):
        raise ValueError("paper run manifest or directory changed; new run required")
    if not row:
        duplicate = con.execute(
            "SELECT run_id FROM portfolio_runs WHERE account_ref=?",
            (observation["account_ref_sha256"],),
        ).fetchone()
        if duplicate:
            raise ValueError("paper account already bound to a distinct run")
        con.execute(
            "INSERT INTO portfolio_runs VALUES(?,?,?,?,?,?,?)",
            (
                observation["run_id"],
                observation["portfolio_id"],
                observation["portfolio_version"],
                observation["account_ref_sha256"],
                observation["journal_ref_sha256"],
                observation.get("heartbeat_at"),
                observed_at,
            ),
        )
    else:
        con.execute(
            "UPDATE portfolio_runs SET heartbeat_at=?, observed_at=? WHERE run_id=?",
            (observation.get("heartbeat_at"), observed_at, observation["run_id"]),
        )
    con.execute(
        "INSERT INTO portfolio_run_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(run_id) DO UPDATE SET "
        "status_sha256=excluded.status_sha256,observed_at=excluded.observed_at,"
        "status=excluded.status,reason=excluded.reason",
        (
            observation["run_id"],
            observation["portfolio_id"],
            observation["portfolio_version"],
            observation["portfolio_definition_sha256"],
            observation["manifest_sha256"],
            observation["status_sha256"],
            observation["account_ref_sha256"],
            observation["journal_ref_sha256"],
            observation["run_root"],
            observed_at,
            observation["state"],
            observation["reason"],
        ),
    )


def sanitized(snapshot: dict) -> dict:
    """Suppress private directories, account IDs and run IDs in public reports."""
    result = {key: value for key, value in snapshot.items() if key not in {"run_root", "run_id"}}
    if snapshot.get("run_id"):
        result["run_ref_sha256"] = sha256(snapshot["run_id"].encode()).hexdigest()
    return result
