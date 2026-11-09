"""Owner-private SQLite-native registry writes and legacy-import write lock.

The SQLite inventory is already the canonical read authority. This module
locks historical source re-imports and provides one backed-up, append-only
wallet/cohort registration interface. Nothing here mutates subscriptions,
paper journals, signed portfolio decisions or trading state.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os
import re
import sqlite3
import stat

COHORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
EXCLUSION_REASON = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z")
LOCK_KEY = "legacy_import_locked_at"

# Database backstops protect against older package versions bypassing the
# current Python guard. The tracker remains the owner of real subscriptions.
LOCK_TRIGGERS = (
    """CREATE TRIGGER native_registry_no_legacy_import
       BEFORE INSERT ON import_runs
       WHEN EXISTS(SELECT 1 FROM snapshot_meta WHERE key='legacy_import_locked_at')
       BEGIN SELECT RAISE(ABORT,'LEGACY_SOURCE_IMPORT_DISABLED'); END""",
    """CREATE TRIGGER native_registry_no_monitoring_update
       BEFORE UPDATE ON monitoring
       WHEN EXISTS(SELECT 1 FROM snapshot_meta WHERE key='legacy_import_locked_at')
       BEGIN SELECT RAISE(ABORT,'TRACKER_SNAPSHOT_READ_ONLY'); END""",
    """CREATE TRIGGER native_registry_no_monitoring_insert
       BEFORE INSERT ON monitoring
       WHEN EXISTS(SELECT 1 FROM snapshot_meta WHERE key='legacy_import_locked_at')
       BEGIN SELECT RAISE(ABORT,'TRACKER_SNAPSHOT_READ_ONLY'); END""",
    """CREATE TRIGGER native_registry_no_monitoring_delete
       BEFORE DELETE ON monitoring
       WHEN EXISTS(SELECT 1 FROM snapshot_meta WHERE key='legacy_import_locked_at')
       BEGIN SELECT RAISE(ABORT,'TRACKER_SNAPSHOT_READ_ONLY'); END""",
)


def locked(con: sqlite3.Connection) -> bool:
    """A lock marker alone is not protection: verify the SQLite backstops."""
    marked = (
        con.execute("SELECT 1 FROM snapshot_meta WHERE key=?", (LOCK_KEY,)).fetchone() is not None
    )
    if marked:
        for statement in LOCK_TRIGGERS:
            name = statement.split()[2]
            actual = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            ).fetchone()
            if actual is None or " ".join(actual[0].split()) != " ".join(statement.split()):
                raise ValueError("LEGACY_LOCK_TRIGGER_INTEGRITY_FAILED")
    return marked


def _set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO snapshot_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _require_private_db(db: Path) -> None:
    if not db.is_file() or db.is_symlink():
        raise ValueError("SQLITE_REGISTRY_REQUIRED")
    if stat.S_IMODE(db.stat().st_mode) != 0o600 or stat.S_IMODE(db.parent.stat().st_mode) != 0o700:
        raise PermissionError("REGISTRY_PRIVATE_PERMISSIONS_REQUIRED")


def _backup(db: Path, inventory_sha: str, action: str) -> Path:
    from . import wallet_registry as reg

    at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = db.parent / "backups" / f"pre-{action}-{at}-{inventory_sha[:12]}.sqlite"
    reg.backup(db, target)
    with closing(reg.connect(target, False)) as con:
        if (
            con.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or con.execute("PRAGMA foreign_key_check").fetchone() is not None
        ):
            raise ValueError("REGISTRY_BACKUP_INVALID")
    return target


def _check(db: Path, expected: str) -> str:
    from . import wallet_registry as reg

    actual = reg.db_authority_health(db)["inventory_sha256"]
    if actual != expected:
        raise ValueError("SQLITE_INVENTORY_SHA_CHANGED")
    return actual


def _sidecars(db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            p.chmod(0o600)


def lock_legacy_import(
    db: Path,
    *,
    expected: str,
    apply: bool = False,
    now: str | None = None,
) -> dict:
    """Freeze external source writes without changing portfolio/wallet rows."""
    from . import wallet_registry as reg

    _require_private_db(db)
    at = now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(at).tzinfo is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    with reg.private_lock(db):
        baseline = _check(db, expected)
        with closing(reg.connect(db, False)) as con:
            if locked(con):
                return {
                    "authority": "SQLITE",
                    "legacy_import": "DISABLED",
                    "inventory_sha256": baseline,
                    "unchanged": True,
                }
        if not apply:
            return {
                "authority": "SQLITE",
                "legacy_import": "ENABLED_PENDING_LOCK",
                "inventory_sha256": baseline,
                "would_disable_legacy_import": True,
                "applied": False,
            }
        backup_path = _backup(db, baseline, "legacy-lock")
        with closing(reg.connect(db, True)) as con:
            con.execute("BEGIN IMMEDIATE")
            with con:
                _check(db, expected)
                if locked(con):
                    raise ValueError("LEGACY_LOCK_CHANGED_CONCURRENTLY")
                _set(con, LOCK_KEY, at)
                for statement in LOCK_TRIGGERS:
                    con.execute(statement)
                if (
                    con.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or con.execute("PRAGMA foreign_key_check").fetchone() is not None
                ):
                    raise ValueError("LEGACY_LOCK_INTEGRITY_FAILED")
        _sidecars(db)
        return {
            "authority": "SQLITE",
            "legacy_import": "DISABLED",
            "inventory_sha256": reg.db_authority_health(db)["inventory_sha256"],
            "backup_verified": True,
            "backup": str(backup_path),
            "applied": True,
        }


def _manifest(path: Path) -> tuple[str, list[tuple[str, list[str]]], str]:
    from . import wallet_registry as reg

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
        raise ValueError("INVALID_NATIVE_MANIFEST")
    if doc["schema"] != "sqlite_wallet_import_v1":
        raise ValueError("UNSUPPORTED_NATIVE_MANIFEST")
    cohort = doc["cohort"]
    if not isinstance(cohort, str) or not COHORT_ID.fullmatch(cohort):
        raise ValueError("INVALID_COHORT_NAME")
    if cohort in reg.RESEARCH or cohort.startswith("pm01"):
        raise ValueError("LEGACY_COHORT_IMMUTABLE")
    wallets = doc["wallets"]
    if not isinstance(wallets, list) or not 1 <= len(wallets) <= 1000:
        raise ValueError("INVALID_NATIVE_MANIFEST_SIZE")
    seen_addresses: set[str] = set()
    seen_aliases: set[str] = set()
    entries: list[tuple[str, list[str]]] = []
    for wallet in wallets:
        if not isinstance(wallet, dict) or set(wallet) != {"address", "aliases"}:
            raise ValueError("INVALID_NATIVE_WALLET_RECORD")
        if not isinstance(wallet["address"], str):
            raise ValueError("INVALID_NATIVE_WALLET_ADDRESS")
        address = reg.normalize(wallet["address"])
        aliases = wallet["aliases"]
        if (
            not isinstance(aliases, list)
            or len(aliases) > 20
            or any(not isinstance(a, str) or not ALIAS.fullmatch(a) for a in aliases)
        ):
            raise ValueError("INVALID_NATIVE_ALIASES")
        if (
            address in seen_addresses
            or len(aliases) != len(set(aliases))
            or set(aliases) & seen_aliases
        ):
            raise ValueError("NATIVE_MANIFEST_DUPLICATE_IDENTITY")
        entries.append((address, aliases))
        seen_addresses.add(address)
        seen_aliases.update(aliases)
    return cohort, entries, sha256(raw).hexdigest()


def _exclusion_manifest(path: Path) -> tuple[list[tuple[str, str]], str]:
    """Validate a private, additive exclusion decision without backdated clocks."""
    from . import wallet_registry as reg

    if (
        not path.is_file()
        or path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
        or stat.S_IMODE(path.parent.stat().st_mode) != 0o700
    ):
        raise PermissionError("PRIVATE_EXCLUSION_MANIFEST_REQUIRED")
    raw = path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict) or set(document) != {"schema", "decisions"}:
        raise ValueError("INVALID_EXCLUSION_MANIFEST")
    if document["schema"] != "sqlite_wallet_exclusions_v1":
        raise ValueError("UNSUPPORTED_EXCLUSION_MANIFEST")
    decisions = document["decisions"]
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 1000:
        raise ValueError("INVALID_EXCLUSION_DECISIONS")
    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {"address", "reason_code"}:
            raise ValueError("INVALID_EXCLUSION_DECISION")
        if not isinstance(decision["address"], str):
            raise ValueError("INVALID_EXCLUSION_IDENTITY")
        address = reg.normalize(decision["address"])
        reason = decision["reason_code"]
        if not isinstance(reason, str) or not EXCLUSION_REASON.fullmatch(reason):
            raise ValueError("INVALID_EXCLUSION_REASON_CODE")
        if address in seen:
            raise ValueError("DUPLICATE_EXCLUSION_IDENTITY")
        entries.append((address, reason))
        seen.add(address)
    return entries, sha256(raw).hexdigest()


def _sync_archive_directories(db: Path, directory: Path) -> None:
    """Persist the artifact link and newly created parents before SQLite refers to it."""
    for path in (directory, directory.parent, db.parent):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _seal_manifest(
    db: Path, manifest: Path, expected_sha: str, *, category: str = "native-cohorts"
) -> str:
    """Immutable, private source reference, never a mutable input path."""
    if category not in {"native-cohorts", "native-exclusions"}:
        raise ValueError("UNSUPPORTED_EVIDENCE_CATEGORY")
    location = Path("evidence") / category / f"{expected_sha}.json"
    evidence_root = db.parent / "evidence"
    evidence_root.mkdir(mode=0o700, exist_ok=True)
    if evidence_root.is_symlink() or stat.S_IMODE(evidence_root.stat().st_mode) != 0o700:
        raise PermissionError("PRIVATE_EVIDENCE_DIRECTORY_REQUIRED")
    directory = db.parent / location.parent
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise PermissionError("PRIVATE_EVIDENCE_DIRECTORY_REQUIRED")
    final = db.parent / location
    raw = manifest.read_bytes()
    if (
        manifest.is_symlink()
        or stat.S_IMODE(manifest.stat().st_mode) != 0o600
        or sha256(raw).hexdigest() != expected_sha
    ):
        raise ValueError("NATIVE_MANIFEST_CHANGED")
    if final.exists() or final.is_symlink():
        if (
            final.is_symlink()
            or stat.S_IMODE(final.stat().st_mode) != 0o600
            or sha256(final.read_bytes()).hexdigest() != expected_sha
        ):
            raise ValueError("NATIVE_EVIDENCE_CONFLICT")
        # A previous process may have died after linking but before directory
        # fsync. Re-verify and finish durability before adopting this orphan.
        _sync_archive_directories(db, directory)
        return str(location)
    partial = directory / f".{expected_sha}.{os.getpid()}.partial"
    fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(partial, final, follow_symlinks=False)
        except FileExistsError:
            if (
                final.is_symlink()
                or stat.S_IMODE(final.stat().st_mode) != 0o600
                or sha256(final.read_bytes()).hexdigest() != expected_sha
            ):
                raise ValueError("NATIVE_EVIDENCE_CONFLICT") from None
    finally:
        partial.unlink(missing_ok=True)
    _sync_archive_directories(db, directory)
    return str(location)


def verify_native_cohort_archives(db: Path, con: sqlite3.Connection) -> None:
    """Verify exact additive membership and clocks against every archived version."""
    expected_members: dict[str, set[str]] = {}
    previous_versions: dict[str, int] = {}
    for cohort, version, digest in con.execute(
        "SELECT cohort_id,version,source_sha256 FROM cohorts ORDER BY cohort_id,version"
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        key = f"sqlite_primary:{cohort}"
        if (
            con.execute(
                "SELECT 1 FROM evidence_versions WHERE source_key=? LIMIT 1", (key,)
            ).fetchone()
            is None
        ):
            continue  # Legacy SHA-imported cohort; no native archival claim.
        archive = db.parent / "evidence" / "native-cohorts" / f"{digest}.json"
        try:
            recorded_cohort, entries, recorded_sha = _manifest(archive)
        except (ValueError, PermissionError, OSError, json.JSONDecodeError) as exc:
            raise ValueError("NATIVE_COHORT_EVIDENCE_INVALID") from exc
        if recorded_cohort != cohort or recorded_sha != digest:
            raise ValueError("NATIVE_COHORT_EVIDENCE_INVALID")
        version_proof = con.execute(
            "SELECT first_known_at FROM evidence_versions WHERE source_key=? AND sha256=?",
            (key, digest),
        ).fetchone()
        if version_proof is None:
            raise ValueError("NATIVE_COHORT_VERSION_MISSING")
        if version != previous_versions.get(cohort, 0) + 1:
            raise ValueError("NATIVE_COHORT_VERSION_MISSING")
        expected = expected_members.setdefault(cohort, set())
        expected.update(address for address, _ in entries)
        rows = con.execute(
            "SELECT w.address,m.known_at FROM cohort_memberships m "
            "JOIN wallets w USING(wallet_id) WHERE m.cohort_id=? AND m.version=?",
            (cohort, version),
        ).fetchall()
        if {row[0] for row in rows} != expected:
            raise ValueError("NATIVE_COHORT_MEMBERSHIP_MISMATCH")
        if any(row[1] != version_proof[0] for row in rows):
            raise ValueError("NATIVE_COHORT_MEMBERSHIP_CLOCK_MISMATCH")
        previous_versions[cohort] = version
        latest = con.execute(
            "SELECT MAX(version) FROM cohorts WHERE cohort_id=?", (cohort,)
        ).fetchone()[0]
        if version == latest:
            row = con.execute(
                "SELECT sha256,source_path FROM evidence_artifacts WHERE source_key=?",
                (key,),
            ).fetchone()
            expected_path = str(Path("evidence") / "native-cohorts" / f"{digest}.json")
            if row != (digest, expected_path):
                raise ValueError("NATIVE_COHORT_LATEST_EVIDENCE_MISMATCH")


def register_cohort(
    db: Path,
    manifest: Path,
    *,
    expected: str,
    apply: bool = False,
    now: str | None = None,
) -> dict:
    """Append a new research-cohort version; no roster/monitoring auto-promotion."""
    from . import wallet_registry as reg

    _require_private_db(db)
    cohort, entries, manifest_sha = _manifest(manifest)
    at = now or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(at).tzinfo is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    with reg.private_lock(db):
        baseline = _check(db, expected)
        with closing(reg.connect(db, False)) as con:
            if not locked(con):
                raise ValueError("LOCK_LEGACY_IMPORT_BEFORE_NATIVE_REGISTRATION")
            prior = con.execute(
                "SELECT version,source_sha256 FROM cohorts WHERE cohort_id=? "
                "ORDER BY version DESC LIMIT 1",
                (cohort,),
            ).fetchone()
            if prior is not None and prior[1] == manifest_sha:
                verify_native_cohort_archives(db, con)
                return {
                    "authority": "SQLITE",
                    "inventory_sha256": baseline,
                    "cohort": cohort,
                    "unchanged": True,
                }
            for address, aliases in entries:
                wallet_id = con.execute(
                    "SELECT wallet_id FROM wallets "
                    "WHERE venue='hyperliquid' AND network='mainnet' AND address=?",
                    (address,),
                ).fetchone()
                for alias in aliases:
                    holders = con.execute(
                        "SELECT DISTINCT wallet_id FROM wallet_aliases WHERE alias=?", (alias,)
                    ).fetchall()
                    if holders and (
                        wallet_id is None or any(holder[0] != wallet_id[0] for holder in holders)
                    ):
                        raise ValueError("CANONICAL_ALIAS_COLLISION")
            version = prior[0] + 1 if prior else 1
        if not apply:
            return {
                "authority": "SQLITE",
                "cohort": cohort,
                "next_version": version,
                "wallets_in_manifest": len(entries),
                "manifest_sha256": manifest_sha,
                "inventory_sha256": baseline,
                "applied": False,
            }
        backup_path = _backup(db, baseline, "native-register")
        evidence_ref = _seal_manifest(db, manifest, manifest_sha)
        with closing(reg.connect(db, True)) as con:
            con.execute("BEGIN IMMEDIATE")
            with con:
                _check(db, expected)
                if not locked(con):
                    raise ValueError("LEGACY_LOCK_CHANGED")
                con.execute(
                    "INSERT INTO cohorts(cohort_id,version,source_sha256) VALUES(?,?,?)",
                    (cohort, version, manifest_sha),
                )
                members = (
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
                for address, aliases in entries:
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
                    members.add(wallet_id)
                    for alias in aliases:
                        holders = con.execute(
                            "SELECT DISTINCT wallet_id FROM wallet_aliases WHERE alias=?", (alias,)
                        ).fetchall()
                        if holders and any(holder[0] != wallet_id for holder in holders):
                            raise ValueError("CANONICAL_ALIAS_COLLISION")
                        if not holders:
                            con.execute(
                                "INSERT INTO wallet_aliases VALUES(?,?,?,?)",
                                ("sqlite_primary", alias, wallet_id, at),
                            )
                con.executemany(
                    "INSERT INTO cohort_memberships VALUES(?,?,?,?)",
                    ((cohort, version, wallet_id, at) for wallet_id in sorted(members)),
                )
                evidence_key = f"sqlite_primary:{cohort}"
                con.execute(
                    "INSERT INTO evidence_versions VALUES(?,?,?) "
                    "ON CONFLICT(source_key,sha256) DO NOTHING",
                    (evidence_key, manifest_sha, at),
                )
                con.execute(
                    "INSERT INTO evidence_artifacts VALUES(?,?,?,?,?) "
                    "ON CONFLICT(source_key) DO UPDATE SET sha256=excluded.sha256,"
                    "source_path=excluded.source_path,observed_at=excluded.observed_at,"
                    "interpretation=excluded.interpretation",
                    (
                        evidence_key,
                        manifest_sha,
                        evidence_ref,
                        at,
                        "NATIVE_SQLITE_RESEARCH_REGISTRATION",
                    ),
                )
                _set(con, "sqlite_native_updated_at", at)
                if (
                    con.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or con.execute("PRAGMA foreign_key_check").fetchone() is not None
                ):
                    raise ValueError("NATIVE_REGISTRATION_INTEGRITY_FAILED")
        _sidecars(db)
        return {
            "authority": "SQLITE",
            "cohort": cohort,
            "version": version,
            "cohort_total": len(members),
            "inventory_sha256": reg.db_authority_health(db)["inventory_sha256"],
            "backup_verified": True,
            "backup": str(backup_path),
            "applied": True,
        }


def verify_exclusion_archives(db: Path, con: sqlite3.Connection) -> None:
    """Fail closed when any native exclusion lacks its exact immutable source."""
    for key, source_sha, path, observed_at in con.execute(
        "SELECT source_key,sha256,source_path,observed_at FROM evidence_artifacts "
        "WHERE source_key LIKE 'sqlite_primary:exclusions:%'"
    ):
        relative = Path("evidence") / "native-exclusions" / f"{source_sha}.json"
        if key != f"sqlite_primary:exclusions:{source_sha}" or path != str(relative):
            raise ValueError("EXCLUSION_EVIDENCE_INTEGRITY_FAILED")
        archive = db.parent / relative
        try:
            decisions, verified_sha = _exclusion_manifest(archive)
        except (ValueError, PermissionError, OSError, json.JSONDecodeError) as exc:
            raise ValueError("EXCLUSION_EVIDENCE_INTEGRITY_FAILED") from exc
        if verified_sha != source_sha:
            raise ValueError("EXCLUSION_EVIDENCE_INTEGRITY_FAILED")
        stored = con.execute(
            "SELECT w.address,e.reason,e.known_at FROM exclusions e "
            "JOIN wallets w USING(wallet_id) WHERE e.source_key=?",
            (key,),
        ).fetchall()
        if sorted(stored) != sorted((addr, reason, observed_at) for addr, reason in decisions):
            raise ValueError("EXCLUSION_EVIDENCE_ROWS_MISMATCH")
        version = con.execute(
            "SELECT first_known_at FROM evidence_versions WHERE source_key=? AND sha256=?",
            (key, source_sha),
        ).fetchone()
        if version is None or version[0] != observed_at:
            raise ValueError("EXCLUSION_EVIDENCE_CLOCK_MISMATCH")


def append_exclusions(
    db: Path,
    manifest: Path,
    *,
    expected: str,
    expected_manifest_sha: str,
    apply: bool = False,
    now: str | None = None,
) -> dict:
    """Append an owner-reviewed exclusion; no revocations or subscriptions.

    Exclusion knowledge begins at the actual receipt time. Retrospective
    vendor timestamps and arbitrary manifest dates cannot backdate it.
    """
    from . import wallet_registry as reg

    _require_private_db(db)
    decisions, source_sha = _exclusion_manifest(manifest)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha):
        raise ValueError("EXPECTED_MANIFEST_SHA_REQUIRED")
    if source_sha != expected_manifest_sha:
        raise ValueError("EXCLUSION_MANIFEST_SHA_CHANGED")
    timestamp = now or datetime.now(timezone.utc).isoformat()
    instant = datetime.fromisoformat(timestamp)
    if instant.tzinfo is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    known_at = instant.astimezone(timezone.utc).isoformat()
    source_key = f"sqlite_primary:exclusions:{source_sha}"

    with reg.private_lock(db):
        baseline = _check(db, expected)
        with closing(reg.connect(db, False)) as con:
            if not locked(con):
                raise ValueError("LOCK_LEGACY_IMPORT_BEFORE_NATIVE_EXCLUSION")
            previous = con.execute(
                "SELECT sha256,source_path FROM evidence_artifacts WHERE source_key=?",
                (source_key,),
            ).fetchone()
            if previous is not None:
                relative = Path("evidence") / "native-exclusions" / f"{source_sha}.json"
                snapshot = db.parent / relative
                if (
                    previous != (source_sha, str(relative))
                    or not snapshot.is_file()
                    or snapshot.is_symlink()
                    or stat.S_IMODE(snapshot.stat().st_mode) != 0o600
                    or sha256(snapshot.read_bytes()).hexdigest() != source_sha
                ):
                    raise ValueError("EXCLUSION_EVIDENCE_INTEGRITY_FAILED")
                stored = con.execute(
                    "SELECT w.address,e.reason FROM exclusions e "
                    "JOIN wallets w USING(wallet_id) WHERE e.source_key=?",
                    (source_key,),
                ).fetchall()
                if sorted(stored) != sorted(decisions):
                    raise ValueError("EXCLUSION_EVIDENCE_ROWS_MISMATCH")
                return {
                    "authority": "SQLITE",
                    "inventory_sha256": baseline,
                    "decision_sha256": source_sha,
                    "unchanged": True,
                    "applied": False,
                }
            wallet_ids: dict[str, int] = {}
            for address, _ in decisions:
                record = con.execute(
                    "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                    "AND network='mainnet' AND address=?",
                    (address,),
                ).fetchone()
                if record is None:
                    raise ValueError("EXCLUSION_WALLET_NOT_REGISTERED")
                wallet_id = record[0]
                if con.execute(
                    "SELECT 1 FROM exclusions WHERE wallet_id=? LIMIT 1", (wallet_id,)
                ).fetchone():
                    raise ValueError("EXCLUSION_ALREADY_RECORDED_REVIEW_REQUIRED")
                wallet_ids[address] = wallet_id

        if not apply:
            return {
                "authority": "SQLITE",
                "inventory_sha256": baseline,
                "decision_sha256": source_sha,
                "exclusion_count": len(decisions),
                "would_append_only": True,
                "applied": False,
            }

        backup_path = _backup(db, baseline, "native-exclusions")
        source_path = _seal_manifest(db, manifest, source_sha, category="native-exclusions")
        with closing(reg.connect(db, True)) as con:
            con.execute("BEGIN IMMEDIATE")
            with con:
                _check(db, expected)
                if not locked(con):
                    raise ValueError("LEGACY_LOCK_CHANGED")
                for address, _ in decisions:
                    wallet_id = wallet_ids[address]
                    current = con.execute(
                        "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                        "AND network='mainnet' AND address=?",
                        (address,),
                    ).fetchone()
                    if current is None or current[0] != wallet_id:
                        raise ValueError("EXCLUSION_IDENTITY_CHANGED")
                    if con.execute(
                        "SELECT 1 FROM exclusions WHERE wallet_id=? LIMIT 1", (wallet_id,)
                    ).fetchone():
                        raise ValueError("EXCLUSION_ALREADY_RECORDED_REVIEW_REQUIRED")
                con.execute(
                    "INSERT INTO evidence_artifacts "
                    "(source_key,sha256,source_path,observed_at,interpretation) "
                    "VALUES(?,?,?,?,?)",
                    (
                        source_key,
                        source_sha,
                        source_path,
                        known_at,
                        "NATIVE_EXCLUSION_METADATA_ONLY_NO_REVIEW_ATTESTATION",
                    ),
                )
                con.execute(
                    "INSERT INTO evidence_versions(source_key,sha256,first_known_at) VALUES(?,?,?)",
                    (source_key, source_sha, known_at),
                )
                con.executemany(
                    "INSERT INTO exclusions(wallet_id,reason,known_at,source_key) VALUES(?,?,?,?)",
                    (
                        (wallet_ids[address], reason, known_at, source_key)
                        for address, reason in decisions
                    ),
                )
                _set(con, "sqlite_native_updated_at", known_at)
                if (
                    con.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or con.execute("PRAGMA foreign_key_check").fetchone() is not None
                ):
                    raise ValueError("EXCLUSION_INTEGRITY_FAILED")
        _sidecars(db)
        return {
            "authority": "SQLITE",
            "decision_sha256": source_sha,
            "exclusion_count": len(decisions),
            "inventory_sha256": reg.db_authority_health(db)["inventory_sha256"],
            "backup_verified": True,
            "backup": str(backup_path),
            "applied": True,
            "owner_review_attested": False,
            "trading_authorized": False,
        }
