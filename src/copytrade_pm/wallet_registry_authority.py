"""SQLite-primary operational registry authority and controlled, append-only writes.

Legacy CSV/Git sources remain immutable evidence; they cannot overwrite an
activated registry. No order route, monitoring subscriptions, or science promotion.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import stat

MODE = "SQLITE_PRIMARY_V1"
COHORT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")

# Database-level backstop: older installed CLI revisions must not be able to
# re-import historic source inventory after primary cutover. The primary
# registry deliberately does not own live tracker subscription mutations.
LEGACY_GUARDS = (
    """CREATE TRIGGER guard_primary_legacy_import
       BEFORE INSERT ON import_runs
       WHEN EXISTS (SELECT 1 FROM snapshot_meta
                    WHERE key='authority_mode' AND value='SQLITE_PRIMARY_V1')
       BEGIN SELECT RAISE(ABORT,'LEGACY_IMPORT_DISABLED_SQLITE_PRIMARY'); END""",
    """CREATE TRIGGER guard_primary_monitoring_update
       BEFORE UPDATE ON monitoring
       WHEN EXISTS (SELECT 1 FROM snapshot_meta
                    WHERE key='authority_mode' AND value='SQLITE_PRIMARY_V1')
       BEGIN SELECT RAISE(ABORT,'TRACKER_MONITORING_READ_ONLY_SNAPSHOT'); END""",
    """CREATE TRIGGER guard_primary_monitoring_insert
       BEFORE INSERT ON monitoring
       WHEN EXISTS (SELECT 1 FROM snapshot_meta
                    WHERE key='authority_mode' AND value='SQLITE_PRIMARY_V1')
       BEGIN SELECT RAISE(ABORT,'TRACKER_MONITORING_READ_ONLY_SNAPSHOT'); END""",
    """CREATE TRIGGER guard_primary_monitoring_delete
       BEFORE DELETE ON monitoring
       WHEN EXISTS (SELECT 1 FROM snapshot_meta
                    WHERE key='authority_mode' AND value='SQLITE_PRIMARY_V1')
       BEGIN SELECT RAISE(ABORT,'TRACKER_MONITORING_READ_ONLY_SNAPSHOT'); END""",
)


def mode(con: sqlite3.Connection) -> str:
    record = con.execute("SELECT value FROM snapshot_meta WHERE key='authority_mode'").fetchone()
    return record[0] if record else "LEGACY_IMPORTED_V1"


def _meta(con: sqlite3.Connection, key: str) -> str | None:
    record = con.execute("SELECT value FROM snapshot_meta WHERE key=?", (key,)).fetchone()
    return record[0] if record else None


def _set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO snapshot_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _integrity(con: sqlite3.Connection) -> bool:
    return (
        con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        and not con.execute("PRAGMA foreign_key_check").fetchall()
    )


def _next_generation(previous: str, operation: str, payload: str) -> str:
    return sha256(
        json.dumps(
            {"previous": previous, "operation": operation, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _preflight(con: sqlite3.Connection, expected: str | None) -> str:
    if not _integrity(con):
        raise ValueError("SQLITE_REGISTRY_INTEGRITY_FAILED")
    current = _meta(con, "manifest_sha256")
    if current is None:
        raise ValueError("SQLITE_GENERATION_UNKNOWN")
    if expected is not None and current != expected:
        raise ValueError("SQLITE_GENERATION_CHANGED")
    return current


def _require_private_db(db: Path) -> None:
    if not db.is_file() or db.is_symlink():
        raise ValueError("SQLITE_EXISTING_REGISTRY_REQUIRED")
    if stat.S_IMODE(db.stat().st_mode) != 0o600:
        raise PermissionError("SQLITE_PRIVATE_DATABASE_PERMISSIONS_REQUIRED")


def _backup(db: Path, current: str, operation: str) -> Path:
    from . import wallet_registry as registry

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = db.parent / "backups" / f"pre-{operation}-{stamp}-{current[:12]}.sqlite"
    registry.backup(db, target)
    with closing(registry.connect(target, False)) as verified:
        if not _integrity(verified):
            raise ValueError("SQLITE_AUTHORITY_BACKUP_INVALID")
    return target


def activate(db: Path, *, expected: str, apply: bool, now: str | None = None) -> dict:
    """Opt-in, backed-up activation. Never reads the legacy CSV source."""
    from . import wallet_registry as registry

    at = now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(at).tzinfo is None:
        raise ValueError("authority timestamp needs UTC offset")
    _require_private_db(db)
    with registry.private_lock(db):
        with closing(registry.connect(db, False)) as reader:
            current = _preflight(reader, expected)
            active = mode(reader) == MODE
        if active:
            return {"authority_mode": MODE, "generation": current, "unchanged": True}
        if not apply:
            return {
                "authority_mode": "LEGACY_IMPORTED_V1",
                "proposed_mode": MODE,
                "generation": current,
                "requires_backup": True,
                "applied": False,
            }
        saved = _backup(db, current, "sqlite-authority")
        with closing(registry.connect(db, True)) as con:
            with con:
                _preflight(con, expected)
                if mode(con) == MODE:
                    raise ValueError("SQLITE_AUTHORITY_CHANGED_CONCURRENTLY")
                next_generation = _next_generation(current, "activate-primary", MODE)
                _set_meta(con, "legacy_import_generation", current)
                _set_meta(con, "authority_mode", MODE)
                con.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(9,?)",
                    (at,),
                )
                _set_meta(con, "authority_activated_at", at)
                _set_meta(con, "authority_updated_at", at)
                _set_meta(con, "manifest_sha256", next_generation)
                for trigger in LEGACY_GUARDS:
                    con.execute(trigger)
                if not _integrity(con):
                    raise ValueError("SQLITE_AUTHORITY_ACTIVATION_INTEGRITY_FAILED")
        _private_sidecars(db)
        return {
            "authority_mode": MODE,
            "generation": next_generation,
            "backup_verified": True,
            "backup": str(saved),
            "applied": True,
        }


def _private_sidecars(db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(db) + suffix)
        if path.exists():
            path.chmod(0o600)


def _read_manifest(path: Path) -> tuple[str, list[tuple[str, list[str]]], str]:
    from . import wallet_registry as registry

    if (
        not path.is_file()
        or path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
        or stat.S_IMODE(path.parent.stat().st_mode) != 0o700
    ):
        raise PermissionError("PRIVATE_WALLET_MANIFEST_REQUIRED")
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or set(doc) != {"schema", "cohort", "wallets"}:
        raise ValueError("INVALID_SQLITE_WALLET_MANIFEST")
    if doc["schema"] != "sqlite_wallet_import_v1":
        raise ValueError("UNSUPPORTED_SQLITE_WALLET_MANIFEST")
    cohort = doc["cohort"]
    if not isinstance(cohort, str) or not COHORT.fullmatch(cohort):
        raise ValueError("INVALID_COHORT_ID")
    values = doc["wallets"]
    if not isinstance(values, list) or not 1 <= len(values) <= 1000:
        raise ValueError("INVALID_WALLET_MANIFEST_SIZE")
    rows: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    known_aliases: set[str] = set()
    for row in values:
        if not isinstance(row, dict) or set(row) != {"address", "aliases"}:
            raise ValueError("INVALID_WALLET_ROW")
        address = registry.normalize(row["address"])
        aliases = row["aliases"]
        if (
            not isinstance(aliases, list)
            or len(aliases) > 20
            or any(not isinstance(a, str) or not ALIAS.fullmatch(a) for a in aliases)
        ):
            raise ValueError("INVALID_WALLET_ALIASES")
        if address in seen or len(set(aliases)) != len(aliases):
            raise ValueError("DUPLICATE_WALLET_IDENTITY")
        if known_aliases.intersection(aliases):
            raise ValueError("ALIAS_COLLISION_IN_MANIFEST")
        seen.add(address)
        known_aliases.update(aliases)
        rows.append((address, aliases))
    return cohort, rows, sha256(raw).hexdigest()


def register(
    db: Path,
    manifest: Path,
    *,
    expected: str,
    apply: bool,
    now: str | None = None,
) -> dict:
    """Append wallet identities and cohort version; never touch subscriptions."""
    from . import wallet_registry as registry

    cohort, records, source_sha = _read_manifest(manifest)
    if cohort in registry.RESEARCH or cohort.startswith("pm01"):
        raise ValueError("IMMUTABLE_LEGACY_COHORT")
    _require_private_db(db)
    at = now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(at).tzinfo is None:
        raise ValueError("registration time requires UTC offset")
    with registry.private_lock(db):
        with closing(registry.connect(db, False)) as reader:
            current = _preflight(reader, expected)
            if mode(reader) != MODE:
                raise ValueError("SQLITE_AUTHORITY_NOT_ACTIVE")
            previous = reader.execute(
                "SELECT version,source_sha256 FROM cohorts "
                "WHERE cohort_id=? ORDER BY version DESC LIMIT 1",
                (cohort,),
            ).fetchone()
            if previous and previous[1] == source_sha:
                return {
                    "authority_mode": MODE,
                    "cohort": cohort,
                    "generation": current,
                    "unchanged": True,
                }
            for address, aliases in records:
                identity = reader.execute(
                    "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                    "AND network='mainnet' AND address=?",
                    (address,),
                ).fetchone()
                for alias in aliases:
                    claimed = reader.execute(
                        "SELECT DISTINCT wallet_id FROM wallet_aliases WHERE alias=?", (alias,)
                    ).fetchall()
                    if claimed and (identity is None or any(x[0] != identity[0] for x in claimed)):
                        raise ValueError("CANONICAL_ALIAS_CONFLICT")
            version = previous[0] + 1 if previous else 1
        if not apply:
            return {
                "authority_mode": MODE,
                "cohort": cohort,
                "next_version": version,
                "wallets_in_manifest": len(records),
                "generation": current,
                "source_sha256": source_sha,
                "applied": False,
            }
        saved = _backup(db, current, "sqlite-wallet-import")
        with closing(registry.connect(db, True)) as con:
            with con:
                _preflight(con, expected)
                if mode(con) != MODE:
                    raise ValueError("SQLITE_AUTHORITY_CHANGED")
                con.execute("INSERT INTO cohorts VALUES(?,?,?)", (cohort, version, source_sha))
                prior_members = (
                    {
                        row[0]
                        for row in con.execute(
                            "SELECT wallet_id FROM cohort_memberships "
                            "WHERE cohort_id=? AND version=?",
                            (cohort, version - 1),
                        )
                    }
                    if version > 1
                    else set()
                )
                new_ids = set(prior_members)
                for address, aliases in records:
                    con.execute(
                        "INSERT OR IGNORE INTO wallets(venue,network,address) "
                        "VALUES('hyperliquid','mainnet',?)",
                        (address,),
                    )
                    wallet_id = con.execute(
                        "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                        "AND network='mainnet' AND address=?",
                        (address,),
                    ).fetchone()[0]
                    new_ids.add(wallet_id)
                    for alias in aliases:
                        existing = con.execute(
                            "SELECT DISTINCT wallet_id FROM wallet_aliases WHERE alias=?", (alias,)
                        ).fetchall()
                        if existing and any(row[0] != wallet_id for row in existing):
                            raise ValueError("CANONICAL_ALIAS_CONFLICT")
                        if not existing:
                            con.execute(
                                "INSERT INTO wallet_aliases VALUES(?,?,?,?)",
                                ("sqlite_primary", alias, wallet_id, at),
                            )
                con.executemany(
                    "INSERT INTO cohort_memberships VALUES(?,?,?,?)",
                    ((cohort, version, wid, at) for wid in sorted(new_ids)),
                )
                source_key = f"sqlite_primary:{cohort}"
                con.execute(
                    "INSERT INTO evidence_versions VALUES(?,?,?) "
                    "ON CONFLICT(source_key,sha256) DO NOTHING",
                    (source_key, source_sha, at),
                )
                con.execute(
                    "INSERT INTO evidence_artifacts VALUES(?,?,?,?,?) "
                    "ON CONFLICT(source_key) DO UPDATE SET sha256=excluded.sha256,"
                    "source_path=excluded.source_path,observed_at=excluded.observed_at,"
                    "interpretation=excluded.interpretation",
                    (source_key, source_sha, "OWNER_PRIVATE_MANIFEST", at, "SQLITE_PRIMARY_IMPORT"),
                )
                next_generation = _next_generation(current, "wallet-register", source_sha)
                _set_meta(con, "manifest_sha256", next_generation)
                _set_meta(con, "authority_updated_at", at)
                if not _integrity(con):
                    raise ValueError("SQLITE_WALLET_IMPORT_INTEGRITY_FAILED")
        _private_sidecars(db)
        return {
            "authority_mode": MODE,
            "cohort": cohort,
            "version": version,
            "cohort_total": len(new_ids),
            "generation": next_generation,
            "backup_verified": True,
            "backup": str(saved),
            "applied": True,
        }
