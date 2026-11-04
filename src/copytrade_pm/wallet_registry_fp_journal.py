"""Read-only adapter for the existing FP-01/02 paper-events.sqlite3 contract.

The forward-paper PM-03 Account and PaperJournal own financial state. This
observer neither imports its writer classes nor opens any writable connection.
A stored journal record is not proof that a worker is running or a book is safe.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote
import re
import sqlite3
import stat

EXPECTED_MANIFEST = "paper_run_manifest_v1"
EVIDENCE_CLASS = "FORWARD_PAPER_SIMULATED_v1"
MAX_RUNS = 500
MAX_JSON = 262144
HASH = re.compile(r"[0-9a-f]{64}\Z")
SAFE_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")

# Explicit alias-only agreement between FP PR73's frozen paper membership
# and WR #49's manager labels. No verified address/equity identity is implied.
FP_BINDINGS = {
    "P1": {
        "fp_members": ("S035", "S051", "S053"),
        "wr_members": ("S035-ENA", "S051-BTC", "S053-HYPE"),
        "sizing": "P1_VIRTUAL_10000_USD_TOTAL_NOMINAL_LOSS_600_USD",
    },
    "P14": {
        "fp_members": ("S035", "S051", "S053", "S064", "Whale_0x5f94"),
        "wr_members": (
            "S035-ENA",
            "S051-BTC",
            "S053-HYPE",
            "S064-xyz:BRENTOIL",
            "Whale_0x5f94",
        ),
        "sizing": "P14_VIRTUAL_10000_USD_TOTAL_NOMINAL_LOSS_600_USD",
    },
}


def canonical(value: object) -> bytes:
    """Match PM-03 digest canonical JSON exactly; reject nonfinite floats."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source JSON key")
        result[key] = value
    return result


def parse_json(raw: str) -> dict:
    if not isinstance(raw, str) or len(raw.encode()) > MAX_JSON:
        raise ValueError("oversized source JSON")
    data = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(data, dict):
        raise ValueError("source JSON must be a dictionary")
    return data


def known_time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("timestamp missing")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return value.astimezone(timezone.utc)


def fp_portfolio_sha(selection: dict) -> str | None:
    """Recompute actual FP frozen_paper_portfolio_v1 SHA, not WR's doc SHA."""
    pid = selection.get("portfolio_id")
    contract = FP_BINDINGS.get(pid)
    if contract is None:
        return None
    members = selection.get("members")
    if (
        not isinstance(members, list)
        or len(members) != len(contract["wr_members"])
        or sorted(members) != sorted(contract["wr_members"])
        or selection.get("sizing_contract") != contract["sizing"]
        or not isinstance(selection.get("definition_sha256"), str)
        or not HASH.fullmatch(selection["definition_sha256"])
    ):
        return None
    return digest(
        {
            "schema": "frozen_paper_portfolio_v1",
            "name": pid,
            "members": list(contract["fp_members"]),
            "starting_capital": 10000,
            "total_nominal_risk": 600,
        }
    )


def _base(reason: str = "JOURNAL_UNAVAILABLE") -> dict:
    return {
        "state": "UNKNOWN",
        "reason": reason,
        "order_route": "NONE",
        "scientifically_qualified": False,
        "trading_authorized": False,
        "paper_observation_only": True,
        "source_contract": "FP01_PAPER_JOURNAL_V1",
    }


def _safe_path(run_dir: Path) -> Path:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError("missing or linked private paper root")
    if stat.S_IMODE(run_dir.stat().st_mode) != 0o700:
        raise ValueError("paper directory permissions")
    journal = run_dir / "paper-events.sqlite3"
    if journal.is_symlink() or not journal.is_file():
        raise ValueError("missing or linked journal")
    if stat.S_IMODE(journal.stat().st_mode) != 0o600:
        raise ValueError("journal permissions")
    return journal


def _validate_tail(
    con: sqlite3.Connection, run_id: str, cursor: int, snapshot_sha: str, last_at: str
) -> tuple[str, int]:
    """Verify bounded recent chain, not an independent full PM-03 replay."""
    rows = con.execute(
        "SELECT seq,event_id,event_at,input,input_sha,prior_sha,post_sha,chain_sha "
        "FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 64",
        (run_id,),
    ).fetchall()
    if not rows:
        if cursor != 0:
            raise ValueError("nonzero cursor without event")
        return "0" * 64, 0
    rows.reverse()
    if cursor != rows[-1][0]:
        raise ValueError("last event seq not equal cursor")
    if rows[-1][6] != snapshot_sha:
        raise ValueError("last event snapshot hash mismatch")
    if known_time(rows[-1][2]) != known_time(last_at):
        raise ValueError("last event clock mismatch")
    previous_post = None
    previous_at = None
    for index, (seq, event_id, at, event_json, event_sha, prior, post, chain) in enumerate(rows):
        if type(seq) is not int or seq < 1:
            raise ValueError("invalid event sequence")
        if index and (seq != rows[index - 1][0] + 1 or prior != previous_post):
            raise ValueError("event tail discontinuity")
        if (
            not all(
                isinstance(x, str) and HASH.fullmatch(x) for x in (event_sha, prior, post, chain)
            )
            or digest(parse_json(event_json)) != event_sha
            or chain != digest([run_id, seq, event_id, event_sha, prior, post])
        ):
            raise ValueError("journal tail checksum mismatch")
        at_instant = known_time(at)
        if previous_at and at_instant < previous_at:
            raise ValueError("journal event clock reversed")
        previous_post = post
        previous_at = at_instant
    return rows[-1][7], len(rows)


def inspect_fp_journal(
    run_dir: Path,
    selection: dict,
    *,
    run_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Observe a single FP journal run. Does not invent any worker liveness."""
    result = _base()
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("now must be offset-aware")
    at = at.astimezone(timezone.utc)
    try:
        journal = _safe_path(run_dir)
    except ValueError, OSError:
        return {**result, "reason": "INSECURE_OR_MISSING_JOURNAL"}
    try:
        with closing(
            sqlite3.connect(
                f"file:{quote(journal.resolve().as_posix(), safe='/')}?mode=ro",
                uri=True,
                timeout=0.25,
            )
        ) as con:
            con.execute("PRAGMA query_only=ON")
            con.execute("PRAGMA busy_timeout=250")
            con.execute("BEGIN")
            if run_id is None:
                names = con.execute("SELECT run_id FROM runs ORDER BY run_id LIMIT 2").fetchall()
                if len(names) != 1:
                    return {**result, "reason": "RUN_ID_REQUIRED_OR_MISSING"}
                run_id = names[0][0]
            if not isinstance(run_id, str) or not SAFE_RUN.fullmatch(run_id):
                return {**result, "reason": "INVALID_RUN_ID"}
            row = con.execute(
                "SELECT account_id,manifest,manifest_sha,snapshot,snapshot_sha,"
                "last_event_at,cursor FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return {**result, "reason": "RUN_NOT_FOUND"}
            account, manifest_json, manifest_sha, snapshot_json, snapshot_sha, last_at, cursor = row
            manifest = parse_json(manifest_json)
            snapshot = parse_json(snapshot_json)
            if (
                manifest.get("schema") != EXPECTED_MANIFEST
                or manifest.get("run_id") != run_id
                or manifest.get("account_id") != account
                or manifest.get("order_route") != "NONE"
                or manifest.get("evidence_class") != EVIDENCE_CLASS
                or not isinstance(account, str)
                or not 0 < len(account) <= 128
                or not isinstance(manifest_sha, str)
                or not HASH.fullmatch(manifest_sha)
                or digest(manifest) != manifest_sha
                or not isinstance(snapshot_sha, str)
                or not HASH.fullmatch(snapshot_sha)
                or digest(snapshot) != snapshot_sha
                or type(cursor) is not int
                or cursor < 0
                or not isinstance(manifest.get("rulebook"), dict)
                or str(manifest["rulebook"].get("initial_balance")) != "10000"
                or not all(
                    isinstance(manifest.get(k), str) and HASH.fullmatch(manifest[k])
                    for k in ("portfolio_sha", "market_manifest_sha", "policy_sha", "release_sha")
                )
            ):
                return {**result, "reason": "INVALID_FP_MANIFEST_OR_CHECKPOINT"}
            selected = known_time(manifest.get("selected_at"))
            started = known_time(manifest.get("started_at"))
            known = known_time(selection.get("selection_known_at"))
            if not known <= selected <= started <= at:
                return {**result, "reason": "PIT_SELECTION_CLOCK_INVALID"}
            if not started <= known_time(last_at) <= at:
                return {**result, "reason": "FP_JOURNAL_EVENT_CLOCK_INVALID"}
            expected_fp_sha = fp_portfolio_sha(selection)
            if (
                expected_fp_sha is None
                or not selection.get("source_commit")
                or not isinstance(selection.get("version"), int)
            ):
                return {**result, "reason": "FP_PORTFOLIO_BINDING_UNAVAILABLE"}
            if manifest["portfolio_sha"] != expected_fp_sha:
                return {**result, "reason": "PORTFOLIO_MISMATCH"}
            tail_sha, tail_rows = _validate_tail(con, run_id, cursor, snapshot_sha, last_at)
            con.execute("ROLLBACK")
            projection = {
                "run_id": run_id,
                "fp_portfolio_sha": manifest["portfolio_sha"],
                "registry_definition_sha": selection["definition_sha256"],
                "manifest_sha": manifest_sha,
                "snapshot_sha": snapshot_sha,
                "last_event_at": last_at,
                "cursor": cursor,
                "tail_sha": tail_sha,
            }
            return {
                **result,
                "state": "NOT_RUNNING",
                "reason": "FP_JOURNAL_ONLY_WORKER_UNVERIFIED",
                "run_id": run_id,
                "portfolio_id": selection["portfolio_id"],
                "portfolio_version": selection["version"],
                "portfolio_definition_sha256": selection["definition_sha256"],
                "fp_portfolio_sha256": manifest["portfolio_sha"],
                "portfolio_identity_bridge": "REVIEWED_ALIASES_ONLY_NOT_SOURCE_IDENTITY_PROOF",
                "manifest_sha256": manifest_sha,
                "status_sha256": digest(projection),
                "account_ref_sha256": sha256(account.encode()).hexdigest(),
                "journal_ref_sha256": sha256(str(journal.resolve()).encode()).hexdigest(),
                "journal_seq_reported": cursor,
                "journal_head_reported_sha256": tail_sha,
                "journal_tail_rows_verified": tail_rows,
                "journal_validation": "BOUNDED_TAIL_HASH_ONLY_NOT_PM03_ECONOMIC_REPLAY",
                "heartbeat_at": None,
                "run_root": str(run_dir.resolve()),
                "paper_admission": "UNKNOWN",
                "source_identity_proven": False,
            }
    except sqlite3.Error, ValueError, TypeError, KeyError, OverflowError, OSError:
        return {**result, "reason": "FP_JOURNAL_UNAVAILABLE_OR_INTEGRITY_FAILURE"}
