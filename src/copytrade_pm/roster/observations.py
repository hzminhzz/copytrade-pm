"""Immutable observation membership adopted into RosterStore.

These are source selections, not synthetic scorecards, seat leases or trading
mandates. The retired registry is only an explicit offline migration input.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
from typing import Any

from .models import wallet_address
from .store import RosterStore

_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,150}")


def validate_selection(value: dict[str, Any]) -> None:
    if set(value) != {
        "portfolio_id",
        "version",
        "definition_sha256",
        "selection_known_at",
        "selection_known_at_ms",
        "members",
        "origin_sha256",
    }:
        raise ValueError("OBSERVATION_SELECTION_SCHEMA")
    if not isinstance(value["portfolio_id"], str) or not _ID.fullmatch(value["portfolio_id"]):
        raise ValueError("OBSERVATION_PORTFOLIO_ID")
    if type(value["version"]) is not int or value["version"] < 1:
        raise ValueError("OBSERVATION_SELECTION_VERSION")
    for field in ("definition_sha256", "origin_sha256"):
        if not isinstance(value[field], str) or not _SHA.fullmatch(value[field]):
            raise ValueError("OBSERVATION_SELECTION_PIN")
    dt = datetime.fromisoformat(value["selection_known_at"])
    if dt.tzinfo is None or type(value["selection_known_at_ms"]) is not int:
        raise ValueError("OBSERVATION_SELECTION_CLOCK")
    if int(dt.timestamp() * 1000) != value["selection_known_at_ms"]:
        raise ValueError("OBSERVATION_SELECTION_CLOCK")
    members = value["members"]
    if not isinstance(members, dict) or not members or len(members) > 512:
        raise ValueError("OBSERVATION_SELECTION_MEMBERS")
    for alias, address in members.items():
        if (
            not isinstance(alias, str)
            or not _ID.fullmatch(alias)
            or wallet_address(address) != address
        ):
            raise ValueError("OBSERVATION_SELECTION_MEMBER")
    if len(set(members.values())) != len(members):
        raise ValueError("OBSERVATION_SELECTION_DUPLICATE_WALLET")


def import_registry(
    source: Path, expected_sha256: str, destination: Path, *, at_ms: int, apply: bool
) -> dict[str, Any]:
    """One-time explicit import; normal workers never open the retired registry."""
    if source.is_symlink() or not source.is_file():
        raise ValueError("OBSERVATION_IMPORT_FILE")
    if sha256(source.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("OBSERVATION_IMPORT_PIN")
    if Path(str(source) + "-wal").exists() and Path(str(source) + "-wal").stat().st_size:
        raise ValueError("OBSERVATION_IMPORT_REQUIRES_QUIESCENT_SNAPSHOT")
    selections = []
    quarantined = []
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("OBSERVATION_IMPORT_SQLITE")
        for pid, version, definition, known in db.execute(
            "SELECT portfolio_id,version,definition_sha256,selection_known_at "
            "FROM portfolio_seals ORDER BY portfolio_id,version"
        ):
            rows = db.execute(
                "SELECT m.member_alias,w.address FROM portfolio_memberships m "
                "LEFT JOIN wallets w USING(wallet_id) WHERE m.portfolio_id=? AND m.version=? "
                "ORDER BY m.member_alias",
                (pid, version),
            ).fetchall()
            if not rows or any(address is None for _, address in rows):
                quarantined.append(
                    {
                        "portfolio_id": pid,
                        "version": version,
                        "reason": "UNRESOLVED_MEMBERSHIP",
                        "unresolved_aliases": [alias for alias, address in rows if address is None],
                    }
                )
                continue
            members = dict(rows)
            if len(members) != len(rows):
                raise ValueError("OBSERVATION_IMPORT_DUPLICATE_ALIAS")
            item = {
                "portfolio_id": pid,
                "version": version,
                "definition_sha256": definition,
                "selection_known_at": known,
                "selection_known_at_ms": int(datetime.fromisoformat(known).timestamp() * 1000),
                "members": members,
                "origin_sha256": expected_sha256,
            }
            validate_selection(item)
            if item["selection_known_at_ms"] > at_ms:
                raise ValueError("OBSERVATION_ADOPTION_CLOCK")
            selections.append(item)
    if not selections:
        raise ValueError("OBSERVATION_IMPORT_EMPTY")
    if apply:
        with RosterStore(destination, create=True) as store:
            store.record_observation_selections(selections, recorded_ms=at_ms)
    return {
        "state": "ADOPTED" if apply else "DRY_RUN",
        "selections": len(selections),
        "quarantined": quarantined,
        "portfolios": sorted({item["portfolio_id"] for item in selections}),
        "wallets": len({w for item in selections for w in item["members"].values()}),
        "origin_sha256": expected_sha256,
        "adoption_clock_ms": at_ms,
        "seat_promotions": 0,
        "trading_authorized": False,
        "order_route": "NONE",
    }
