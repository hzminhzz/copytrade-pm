"""Read-only, fail-closed paper-run status adapter for wallet registry.

This is an observational contract for the separate FP paper runtime. A worker
must independently publish both v1 files. This code never creates the worker,
journal, paper account or orders, and never reads a broker credential.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

SCHEMA_MANIFEST = "paper_run_manifest_v1"
SCHEMA_STATUS = "paper_run_status_v1"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_JSON_BYTES = 65536
HEARTBEAT_MAX = timedelta(seconds=90)
FEED_MAX = timedelta(seconds=120)
QUOTE_MAX = timedelta(seconds=120)
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


def _hash(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict:
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate JSON key")
        data[key] = value
    return data


def _read_private_json(path: Path) -> tuple[dict, str]:
    # Open-once, O_NOFOLLOW and descriptor-bound permission/size checks prevent
    # time-of-check/time-of-use symlink replacement from reading arbitrary files.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("status file must be private")
        if info.st_size <= 0 or info.st_size > MAX_JSON_BYTES:
            raise ValueError("status file exceeds safe bound")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(MAX_JSON_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(raw) == 0 or len(raw) > MAX_JSON_BYTES:
        raise ValueError("status size changed during read")
    data = json.loads(raw, object_pairs_hook=_unique_keys)
    if not isinstance(data, dict):
        raise ValueError("status document must be an object")
    return data, sha256(raw).hexdigest()


def _clock(value: Any, now: datetime) -> timedelta:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("timezone missing")
    age = now - instant.astimezone(timezone.utc)
    if age < timedelta(0):
        raise ValueError("future timestamp")
    return age


def process_start_ticks(pid: int) -> str | None:
    """Linux proc start_ticks, preventing PID reuse from implying a live worker."""
    if not isinstance(pid, int) or isinstance(pid, bool) or not 1 < pid < 2**31:
        return None
    try:
        # The comm may contain spaces/parentheses; split only after the last ')'.
        stats = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = stats.rsplit(") ", 1)[1].split()
        return str(int(fields[19]))
    except OSError, ValueError, IndexError:
        return None


def inspect_run(run_dir: Path, selection: dict, *, now: datetime | None = None) -> dict:
    """No filesystem writes and no raw path, wallet or account identity in output.

    RUNNING is an operational *observation* only. A validated Linux worker,
    feed heartbeat, quote heartbeat and journal presence are required; it does
    NOT certify journal economics, source-account books or trading permission.
    """
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("now must be aware")
    at = at.astimezone(timezone.utc)
    base = {
        "state": "UNKNOWN",
        "reason": "NOT_FOUND",
        "order_route": "NONE",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "paper_observation_only": True,
    }
    if not run_dir.is_dir() or run_dir.is_symlink():
        return base
    if stat.S_IMODE(run_dir.stat().st_mode) != 0o700:
        return {**base, "reason": "INSECURE_SOURCE"}
    try:
        manifest, manifest_sha = _read_private_json(run_dir / "manifest.json")
        status, status_sha = _read_private_json(run_dir / "status.json")
    except OSError, ValueError, UnicodeError, json.JSONDecodeError:
        return {**base, "reason": "INSECURE_SOURCE"}
    if (
        manifest.get("schema") != SCHEMA_MANIFEST
        or status.get("schema") != SCHEMA_STATUS
        or not isinstance(manifest.get("run_id"), str)
        or not RUN_ID.fullmatch(manifest["run_id"])
        or not isinstance(manifest.get("portfolio_definition_sha256"), str)
        or not HEX256.fullmatch(manifest["portfolio_definition_sha256"])
        or not isinstance(manifest.get("portfolio_version"), int)
        or not isinstance(manifest.get("account_id"), str)
        or not manifest["account_id"].strip()
        or len(manifest["account_id"]) > 128
        or manifest.get("environment") != "PAPER"
        or manifest.get("order_route") != "NONE"
        or not isinstance(manifest.get("journal_name"), str)
        or manifest["journal_name"] != "events.jsonl"
        or status.get("run_id") != manifest["run_id"]
        or status.get("portfolio_definition_sha256") != manifest["portfolio_definition_sha256"]
        or status.get("account_id") != manifest["account_id"]
    ):
        return {**base, "reason": "INVALID_SCHEMA"}
    if (
        not selection.get("definition_sha256")
        or not selection.get("source_commit")
        or selection["definition_sha256"] != manifest["portfolio_definition_sha256"]
        or selection.get("portfolio_id") != manifest.get("portfolio_id")
        or selection.get("version") != manifest["portfolio_version"]
    ):
        return {**base, "reason": "PORTFOLIO_MISMATCH"}
    journal = run_dir / "events.jsonl"
    if (
        journal.is_symlink()
        or not journal.is_file()
        or stat.S_IMODE(journal.stat().st_mode) != 0o600
    ):
        return {**base, "reason": "JOURNAL_UNAVAILABLE"}
    if (
        not isinstance(status.get("journal_seq"), int)
        or isinstance(status.get("journal_seq"), bool)
        or status["journal_seq"] < 0
        or not isinstance(status.get("journal_head_sha256"), str)
        or not HEX256.fullmatch(status["journal_head_sha256"])
    ):
        return {**base, "reason": "INVALID_SCHEMA"}
    observed = {
        **base,
        "run_id": manifest["run_id"],
        "portfolio_id": manifest["portfolio_id"],
        "portfolio_version": manifest["portfolio_version"],
        "portfolio_definition_sha256": manifest["portfolio_definition_sha256"],
        "manifest_sha256": manifest_sha,
        "status_sha256": status_sha,
        "account_ref_sha256": _hash(manifest["account_id"]),
        "journal_ref_sha256": sha256(str(journal.resolve()).encode()).hexdigest(),
        "journal_seq_reported": status["journal_seq"],
        "journal_head_reported_sha256": status["journal_head_sha256"],
        "heartbeat_at": status.get("heartbeat_at"),
        "run_root": str(run_dir.resolve()),
    }
    try:
        elapsed = {
            "heartbeat": _clock(status.get("heartbeat_at"), at),
            "feed": _clock(status.get("transport_heartbeat_at"), at),
            "quote": _clock(status.get("quote_heartbeat_at"), at),
        }
    except ValueError, TypeError, OverflowError:
        return {**observed, "reason": "INVALID_CLOCK"}
    if elapsed["heartbeat"] > HEARTBEAT_MAX:
        return {**observed, "state": "STALE", "reason": "HEARTBEAT_STALE"}
    if elapsed["feed"] > FEED_MAX:
        return {**observed, "state": "DEGRADED", "reason": "FEED_STALE"}
    if elapsed["quote"] > QUOTE_MAX:
        return {**observed, "state": "DEGRADED", "reason": "QUOTE_STALE"}
    if status.get("worker_state") not in {"RUNNING", "HALTED", "DEGRADED", "STOPPED"}:
        return {**observed, "reason": "SOURCE_STATUS_UNKNOWN"}
    if status["worker_state"] in {"HALTED", "DEGRADED", "STOPPED"}:
        return {
            **observed,
            "state": status["worker_state"],
            "reason": "WORKER_REPORTED_" + status["worker_state"],
        }
    pid = status.get("worker_pid")
    if (
        not isinstance(status.get("worker_start_ticks"), str)
        or process_start_ticks(pid) != status["worker_start_ticks"]
    ):
        return {**observed, "reason": "WORKER_UNVERIFIED"}
    return {
        **observed,
        "state": "PAPER_RUNNING_OBSERVED",
        "reason": "FRESH_WORKER_AND_TRANSPORT_OBSERVED",
    }


def store_observation(con, observation: dict, *, observed_at: str) -> None:
    """Write to the new registry only. Never mutate source manifests or journals."""
    if observation.get("state") == "UNKNOWN" or not observation.get("run_id"):
        raise ValueError("unverified paper identity must not be indexed")
    from .wallet_registry_portfolios import select_asof

    selection = select_asof(con, observation["portfolio_id"], observed_at)
    if (
        selection.get("definition_sha256") != observation["portfolio_definition_sha256"]
        or selection.get("version") != observation["portfolio_version"]
    ):
        raise ValueError("stale portfolio definition; new run required")
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
    """Never print private root paths or account/journal refs."""
    return {key: value for key, value in snapshot.items() if key != "run_root"}
