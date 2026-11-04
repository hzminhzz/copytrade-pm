"""Private, rebuildable, research-only wallet inventory.

This is NOT a broker ledger, trading authorization, or source of first-known fills.
All production integrations are read-only and publish UNKNOWN on missing evidence.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from contextlib import closing, contextmanager
import fcntl

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
ROOT = Path("/home/quant/.local/share/copytrade/reports/five-pod-20261029-research")
DB = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
ENV = Path("/home/quant/.config/copytrade/tracker.env")
RESEARCH = {
    "research-108": "WALLET_FILL_RESEARCH_CURRENT_108_20261103.csv",
    "nansen-20": "nansen20_research_20261103/NANSEN_STRICT_NEW_20_20261103.csv",
    "hyperx-30": "nansen30_research_20261103/HYPERX_STRICT_NEW_30_20261103.csv",
}
EXCLUSIONS = "OWNER_REJECTED_22_WALLET_RESEARCH_20261103.csv"
NEW50 = "new50_hyperx_90d_full_vendor_v2/NEW50_FULL_VENDOR_FILL_AUDIT_20261103.json"
ROSTER = "new50_hyperx_90d_full_vendor_v2/NEW50_FULL_VENDOR_FILL_ROSTER_20261103.csv"
PORTFOLIOS = {
    "P1": ("S035-ENA", "S051-BTC", "S053-HYPE"),
    "P14": ("S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"),
    "P16": ("S035-ENA", "S051-BTC", "S053-HYPE", "Whale_0x5f94"),
    "A": ("W028", "W042", "W030"),
    "B": ("W044", "CA-005", "W031"),
    "C": ("CO-001", "W015", "VS066"),
    "Combo2": ("W028", "CA-008", "W015"),
}
PORTFOLIO_DOCS = {
    "P1": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
    "P14": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
    "P16": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
    "A": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
    "B": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
    "C": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
    "Combo2": "docs/COMBO2-PAPER.md",
}
DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_runs(
    run_id TEXT PRIMARY KEY, observed_at TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL, research_wallets INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS wallets(
    wallet_id INTEGER PRIMARY KEY, venue TEXT NOT NULL, network TEXT NOT NULL,
    address TEXT NOT NULL, UNIQUE(venue, network, address)
);
CREATE TABLE IF NOT EXISTS cohorts(
    cohort_id TEXT NOT NULL, version INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL, PRIMARY KEY(cohort_id, version)
);
CREATE TABLE IF NOT EXISTS cohort_memberships(
    cohort_id TEXT NOT NULL, version INTEGER NOT NULL, wallet_id INTEGER NOT NULL,
    known_at TEXT NOT NULL,
    PRIMARY KEY(cohort_id,version,wallet_id),
    FOREIGN KEY(cohort_id,version) REFERENCES cohorts(cohort_id,version),
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS wallet_aliases(
    namespace TEXT NOT NULL, alias TEXT NOT NULL, wallet_id INTEGER NOT NULL,
    known_at TEXT NOT NULL, PRIMARY KEY(namespace,alias,known_at),
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS evidence_artifacts(
    source_key TEXT PRIMARY KEY, sha256 TEXT NOT NULL, source_path TEXT NOT NULL,
    observed_at TEXT NOT NULL, interpretation TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_versions(
    source_key TEXT NOT NULL, sha256 TEXT NOT NULL, first_known_at TEXT NOT NULL,
    PRIMARY KEY(source_key,sha256)
);
CREATE TABLE IF NOT EXISTS exclusions(
    wallet_id INTEGER NOT NULL, reason TEXT NOT NULL, known_at TEXT NOT NULL,
    source_key TEXT NOT NULL, PRIMARY KEY(wallet_id,reason,source_key),
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id),
    FOREIGN KEY(source_key) REFERENCES evidence_artifacts(source_key)
);
CREATE TABLE IF NOT EXISTS wallet_coverage(
    wallet_id INTEGER PRIMARY KEY, vendor_fills INTEGER,
    vendor_pagination TEXT NOT NULL, account_book TEXT NOT NULL,
    first_known TEXT NOT NULL, source_key TEXT NOT NULL,
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS monitoring(
    wallet_id INTEGER PRIMARY KEY, configured INTEGER NOT NULL,
    subscribed INTEGER NOT NULL, admitted TEXT NOT NULL,
    receipt_health TEXT NOT NULL, known_at TEXT NOT NULL,
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS monitoring_history(
    generation_sha TEXT NOT NULL, wallet_id INTEGER NOT NULL,
    configured INTEGER NOT NULL, subscribed INTEGER NOT NULL,
    known_at TEXT NOT NULL, PRIMARY KEY(generation_sha,wallet_id),
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS portfolio_versions(
    portfolio_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    source_doc TEXT NOT NULL, known_at TEXT NOT NULL, sizing_contract TEXT NOT NULL,
    PRIMARY KEY(portfolio_id,version)
);
CREATE TABLE IF NOT EXISTS portfolio_memberships(
    portfolio_id TEXT NOT NULL, version INTEGER NOT NULL,
    member_alias TEXT NOT NULL, wallet_id INTEGER,
    PRIMARY KEY(portfolio_id,version,member_alias),
    FOREIGN KEY(portfolio_id,version) REFERENCES portfolio_versions(portfolio_id,version),
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS portfolio_runs(
    run_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, version INTEGER NOT NULL,
    account_ref TEXT NOT NULL, journal_ref TEXT NOT NULL,
    heartbeat_at TEXT, observed_at TEXT NOT NULL,
    FOREIGN KEY(portfolio_id,version) REFERENCES portfolio_versions(portfolio_id,version)
);
CREATE TABLE IF NOT EXISTS qualification_decisions(
    decision_id TEXT PRIMARY KEY, wallet_id INTEGER NOT NULL,
    policy_version TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
    known_at TEXT NOT NULL, verdict TEXT NOT NULL,
    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);
CREATE TABLE IF NOT EXISTS snapshot_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def normalize(raw: str) -> str:
    value = raw.strip().lower()
    if not ADDRESS.fullmatch(value):
        raise ValueError("invalid wallet address (redacted)")
    return value


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "address" not in rows[0]:
        raise ValueError("missing address column")
    return rows


def trusted_env(path: Path) -> dict[str, str]:
    wanted = {"TRACKER_DESIRED_WALLETS", "TRACKER_DB_PATH", "TRACKER_LEDGER_PATH"}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in wanted:
            if key in result:
                raise ValueError("duplicate tracker configuration key")
            result[key] = value.strip().strip("'\"")
    if set(result) != wanted:
        raise ValueError("required tracker configuration keys unavailable")
    return result


def readonly_sqlite(path: Path) -> sqlite3.Connection:
    # mode=ro avoids writes, including accidental schema migrations.
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=2)
    con.execute("PRAGMA query_only=ON")
    return con


def observe_monitoring(path: Path) -> tuple[set[str], set[str], dict[str, str]]:
    cfg = trusted_env(path)
    desired = {normalize(x) for x in re.split(r"[,;\s]+", cfg["TRACKER_DESIRED_WALLETS"]) if x}
    with closing(readonly_sqlite(Path(cfg["TRACKER_DB_PATH"]))) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}
        if not {"address", "chat_id", "label"} <= cols:
            raise ValueError("unsupported subscription schema")
        subscribed = {
            normalize(row[0]) for row in con.execute("SELECT DISTINCT address FROM subscriptions")
        }
    return desired, subscribed, cfg


def observation_ledger_identity(path: Path) -> str:
    """Fingerprint only the committed ledger identity, not its moving event cursor."""
    with closing(readonly_sqlite(path)) as con:
        rows = con.execute(
            "SELECT ledger_id,current_seq,retention_floor FROM ledger_meta LIMIT 2"
        ).fetchall()
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        raise ValueError("ledger identity missing or ambiguous")
    ledger_id, seq, floor = rows[0]
    if not (isinstance(seq, int) and isinstance(floor, int) and 0 <= floor <= seq):
        raise ValueError("ledger retention/cursor inconsistency")
    return sha256(ledger_id.encode()).hexdigest()


def observe_ledger(path: Path, addresses: set[str], max_wallets: int = 500) -> dict:
    """Bounded, index-backed observational audit; NEVER claim admission."""
    if len(addresses) > max_wallets:
        raise ValueError("ledger observation budget exceeded")
    now = datetime.now(timezone.utc)
    with closing(readonly_sqlite(path)) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(outbox_events)")}
        if not {"seq", "wallet_id", "kind", "known_at"} <= columns:
            raise ValueError("unsupported observation ledger schema")
        indexes = {row[1] for row in con.execute("PRAGMA index_list(outbox_events)")}
        if "idx_outbox_wallet" not in indexes:
            raise ValueError("bounded wallet observation index unavailable")
        con.execute("BEGIN")
        meta = con.execute(
            "SELECT ledger_id,current_seq,retention_floor FROM ledger_meta LIMIT 2"
        ).fetchall()
        if len(meta) != 1:
            raise ValueError("ledger identity or cursor ambiguous")
        ledger_id, max_seq, retention_floor = meta[0]
        if not (
            isinstance(max_seq, int)
            and isinstance(retention_floor, int)
            and 0 <= retention_floor <= max_seq
        ):
            raise ValueError("observation ledger cursor/retention inconsistency")
        recent = stale = never = 0
        for addr in sorted(addresses):
            row = con.execute(
                "SELECT seq,kind,known_at FROM outbox_events "
                "WHERE wallet_id=? AND seq<=? ORDER BY seq DESC LIMIT 1",
                (addr, max_seq),
            ).fetchone()
            if row is None:
                never += 1
                continue
            try:
                known = datetime.fromisoformat(row[2].replace("Z", "+00:00"))
                age_seconds = (now - known.astimezone(timezone.utc)).total_seconds()
            except ValueError, TypeError, AttributeError:
                stale += 1
                continue
            if known.tzinfo is None or not (0 <= age_seconds <= 3600):
                stale += 1
            else:
                recent += 1
        con.rollback()
    return {
        "source": "READONLY_INDEXED_OUTBOX",
        "ledger_id_sha256": sha256(str(ledger_id).encode()).hexdigest(),
        "ledger_seq": max_seq,
        "retention_floor": retention_floor,
        "queried_wallets": len(addresses),
        "recent_outbox_observation_1h": recent,
        "stale_outbox_observation": stale,
        "no_indexed_event": never,
        "runtime_admitted": "UNKNOWN",
        "receipt_health": "UNKNOWN",
        "scientifically_qualified": "NOT_ESTABLISHED",
        "meaning": "Observed outbox activity is NOT admission, subscription, or complete receipts",
    }


def collect(root: Path, env_path: Path | None) -> dict:
    sources: dict[str, str] = {}
    source_paths: dict[str, Path] = {}
    cohorts: dict[str, set[str]] = {}
    base_rows = {}
    for cohort, rel in RESEARCH.items():
        path = root / rel
        rows = csv_rows(path)
        cohort_wallets = [normalize(row["address"]) for row in rows]
        if len(set(cohort_wallets)) != len(rows):
            raise ValueError("duplicate cohort identity")
        cohorts[cohort] = set(cohort_wallets)
        sources[cohort] = digest(path)
        source_paths[cohort] = path
        if cohort == "research-108":
            base_rows = {normalize(row["address"]): row for row in rows}
    if len(set.union(*cohorts.values())) != sum(map(len, cohorts.values())):
        raise ValueError("overlapping cohort identities")
    exclusions = {}
    for row in csv_rows(root / EXCLUSIONS):
        addr = normalize(row["address"])
        exclusions[addr] = row["exclusion_reason"]
    sources["exclusions"] = digest(root / EXCLUSIONS)
    source_paths["exclusions"] = root / EXCLUSIONS
    roster = {normalize(row["address"]): row for row in csv_rows(root / ROSTER)}
    sources["new50_roster"] = digest(root / ROSTER)
    source_paths["new50_roster"] = root / ROSTER
    audit_path = root / NEW50
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    sources["new50_audit"] = digest(audit_path)
    source_paths["new50_audit"] = audit_path
    if (
        len(roster) != 50
        or set(roster) != cohorts["nansen-20"] | cohorts["hyperx-30"]
        or audit.get("total_fills") != sum(int(row["total_fills"]) for row in roster.values())
        or audit.get("wallets") != 50
        or audit.get("source_pairs") != 1196
        or audit.get("total_fills") != 113273
    ):
        raise ValueError("full-vendor audit cannot be reconciled")
    # The immutable PM-01 adapter is authoritative for its 36 source aliases.
    from .pm_sources import load_cohort

    frozen_entries, frozen_sha = load_cohort(root)
    if len(frozen_entries) != 36:
        raise ValueError("frozen PM-01 roster drift")
    frozen_aliases = {entry.alias: entry.address for entry in frozen_entries}
    if len(frozen_aliases) != 36:
        raise ValueError("frozen PM-01 alias collision")
    for key, value in sorted(frozen_sha.items()):
        sources[f"pm01:{key}"] = value
    if env_path is None:
        desired, subscribed, cfg = set(), set(), {}
        monitoring_status = "UNAVAILABLE"
    else:
        desired, subscribed, cfg = observe_monitoring(env_path)
        monitoring_status = "OBSERVED"
        # Fingerprint only the desired set, never a credential-bearing env file.
        sources["desired_wallets"] = sha256("\n".join(sorted(desired)).encode()).hexdigest()
        sources["subscriptions"] = sha256("\n".join(sorted(subscribed)).encode()).hexdigest()
        sources["observation_ledger_id"] = observation_ledger_identity(
            Path(cfg["TRACKER_LEDGER_PATH"])
        )
    return {
        "cohorts": cohorts,
        "frozen_aliases": frozen_aliases,
        "source_paths": source_paths,
        "base_rows": base_rows,
        "exclusions": exclusions,
        "roster": roster,
        "sources": sources,
        "desired": desired,
        "subscribed": subscribed,
        "tracker_config": cfg,
        "monitoring_status": monitoring_status,
    }


def connect(db: Path, writable: bool) -> sqlite3.Connection:
    con = sqlite3.connect(str(db) if writable else f"file:{db.resolve()}?mode=ro", uri=not writable)
    con.execute("PRAGMA foreign_keys=ON")
    if not writable:
        con.execute("PRAGMA query_only=ON")
    else:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def private_lock(db: Path):
    db.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(db.parent.stat().st_mode) != 0o700:
        raise PermissionError("registry directory must have mode 0700")
    lock = db.parent / ".writer.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def apply(db: Path, snapshot: dict, when: str) -> dict:
    # Validate the staged payload even for a no-op, before trusting source digests.
    for key, path in snapshot.get("source_paths", {}).items():
        if digest(path) != snapshot["sources"][key]:
            raise ValueError("source changed since staged read (redacted)")
    for addr, row in snapshot["roster"].items():
        normalize(addr)
        if int(row["total_fills"]) < 0:
            raise ValueError("negative vendor fill count")
    all_cohort = set.union(*snapshot["cohorts"].values())
    all_addresses = (
        all_cohort
        | set(snapshot["exclusions"])
        | snapshot["desired"]
        | snapshot["subscribed"]
        | set(snapshot.get("frozen_aliases", {}).values())
    )
    manifest = sha256(json.dumps(snapshot["sources"], sort_keys=True).encode()).hexdigest()
    with private_lock(db):
        if db.exists() and stat.S_IMODE(db.stat().st_mode) != 0o600:
            raise PermissionError("registry database must have mode 0600")
        con = connect(db, True)
        try:
            con.executescript(DDL)
            with con:
                con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1,?)", (when,))
                con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?)", (when,))
            previous = con.execute(
                "SELECT value FROM snapshot_meta WHERE key='manifest_sha256'"
            ).fetchone()
            if previous and previous[0] == manifest:
                return {
                    "manifest_sha256": manifest,
                    "research_wallets": len(all_cohort),
                    "unchanged": True,
                }
            with con:
                # Migrate before the snapshot transaction. Never delete identities,
                # run observations, qualification evidence or historical cohorts.
                con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1,?)", (when,))
                con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(2,?)", (when,))
                ids = {}
                for addr in sorted(all_addresses):
                    con.execute(
                        "INSERT OR IGNORE INTO wallets(venue,network,address) "
                        "VALUES('hyperliquid','mainnet',?)",
                        (addr,),
                    )
                    ids[addr] = con.execute(
                        "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                        "AND network='mainnet' AND address=?",
                        (addr,),
                    ).fetchone()[0]
                for key, sha in sorted(snapshot["sources"].items()):
                    rel = RESEARCH.get(
                        key,
                        {
                            "exclusions": EXCLUSIONS,
                            "new50_roster": ROSTER,
                            "new50_audit": NEW50,
                        }.get(key, "redacted-aggregate"),
                    )
                    con.execute(
                        "INSERT INTO evidence_versions VALUES(?,?,?) "
                        "ON CONFLICT(source_key,sha256) DO NOTHING",
                        (key, sha, when),
                    )
                    con.execute(
                        "INSERT INTO evidence_artifacts VALUES(?,?,?,?,?) "
                        "ON CONFLICT(source_key) DO UPDATE SET "
                        "sha256=excluded.sha256,source_path=excluded.source_path,"
                        "observed_at=excluded.observed_at,"
                        "interpretation=excluded.interpretation",
                        (key, sha, str(rel), when, "SOURCE_REFERENCE_ONLY"),
                    )
                for cohort, addresses in snapshot["cohorts"].items():
                    prior = con.execute(
                        "SELECT version,source_sha256 FROM cohorts "
                        "WHERE cohort_id=? ORDER BY version DESC LIMIT 1",
                        (cohort,),
                    ).fetchone()
                    version = (
                        prior[0]
                        if prior and prior[1] == snapshot["sources"][cohort]
                        else (prior[0] + 1 if prior else 1)
                    )
                    if not prior or prior[1] != snapshot["sources"][cohort]:
                        con.execute(
                            "INSERT INTO cohorts VALUES(?,?,?)",
                            (cohort, version, snapshot["sources"][cohort]),
                        )
                        con.executemany(
                            "INSERT INTO cohort_memberships VALUES(?,?,?,?)",
                            ((cohort, version, ids[a], when) for a in sorted(addresses)),
                        )
                for alias, addr in sorted(snapshot.get("frozen_aliases", {}).items()):
                    existing = con.execute(
                        "SELECT DISTINCT wallet_id FROM wallet_aliases "
                        "WHERE namespace='frozen_pm01' AND alias=?",
                        (alias,),
                    ).fetchall()
                    if any(row[0] != ids[addr] for row in existing):
                        raise ValueError("frozen PM-01 alias identity drift")
                    if not existing:
                        con.execute(
                            "INSERT INTO wallet_aliases VALUES(?,?,?,?)",
                            ("frozen_pm01", alias, ids[addr], when),
                        )
                for a, reason in snapshot["exclusions"].items():
                    con.execute(
                        "INSERT OR IGNORE INTO exclusions VALUES(?,?,?,?)",
                        (ids[a], reason, when, "exclusions"),
                    )
                for a in sorted(all_cohort):
                    new = snapshot["roster"].get(a)
                    old = snapshot["base_rows"].get(a)
                    con.execute(
                        "INSERT INTO wallet_coverage VALUES(?,?,?,?,?,?) "
                        "ON CONFLICT(wallet_id) DO UPDATE SET "
                        "vendor_fills=excluded.vendor_fills,"
                        "vendor_pagination=excluded.vendor_pagination,"
                        "account_book=excluded.account_book,"
                        "first_known=excluded.first_known,"
                        "source_key=excluded.source_key",
                        (
                            ids[a],
                            int(new["total_fills"])
                            if new
                            else (
                                int(old["local_fill_rows"])
                                if old and old["local_fill_rows"]
                                else None
                            ),
                            "VENDOR_COIN_CENSUS_RECONCILED" if new else "UNKNOWN_PARTIAL",
                            "UNKNOWN",
                            "UNKNOWN",
                            "new50_roster" if new else "research-108",
                        ),
                    )
                con.execute(
                    "UPDATE monitoring SET configured=0,subscribed=0,admitted='UNKNOWN',"
                    "receipt_health='UNKNOWN',known_at=?",
                    (when,),
                )
                for a in sorted(snapshot["desired"] | snapshot["subscribed"]):
                    values = (
                        ids[a],
                        int(a in snapshot["desired"]),
                        int(a in snapshot["subscribed"]),
                        "UNKNOWN",
                        "UNKNOWN",
                        when,
                    )
                    con.execute(
                        "INSERT INTO monitoring VALUES(?,?,?,?,?,?) "
                        "ON CONFLICT(wallet_id) DO UPDATE SET "
                        "configured=excluded.configured,subscribed=excluded.subscribed,"
                        "admitted=excluded.admitted,receipt_health=excluded.receipt_health,"
                        "known_at=excluded.known_at",
                        values,
                    )
                    con.execute(
                        "INSERT INTO monitoring_history VALUES(?,?,?,?,?)",
                        (manifest, ids[a], values[1], values[2], when),
                    )
                for name, aliases in PORTFOLIOS.items():
                    con.execute(
                        "INSERT OR IGNORE INTO portfolio_versions VALUES(?,?,?,?,?,?)",
                        (
                            name,
                            1,
                            "RESEARCH_ONLY",
                            PORTFOLIO_DOCS[name],
                            when,
                            "SOURCE_EQUITY_WHOLE_BOOK_NOT_DEPLOYED",
                        ),
                    )
                    con.executemany(
                        "INSERT OR IGNORE INTO portfolio_memberships VALUES(?,?,?,?)",
                        (
                            (
                                name,
                                1,
                                alias,
                                ids[snapshot["frozen_aliases"][alias]]
                                if alias in snapshot.get("frozen_aliases", {})
                                else None,
                            )
                            for alias in aliases
                        ),
                    )
                for key, value in (
                    ("manifest_sha256", manifest),
                    ("observed_at", when),
                    ("monitoring_status", snapshot["monitoring_status"]),
                ):
                    con.execute(
                        "INSERT INTO snapshot_meta VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value),
                    )
                con.execute(
                    "INSERT OR IGNORE INTO import_runs VALUES(?,?,?,?)",
                    (manifest, when, manifest, len(all_cohort)),
                )
                if con.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("registry foreign-key integrity failed")
        finally:
            con.close()
        os.chmod(db, 0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db) + suffix)
            if sidecar.exists():
                os.chmod(sidecar, 0o600)
    return {"manifest_sha256": manifest, "research_wallets": len(all_cohort)}


def status(snapshot: dict) -> dict:
    research = set.union(*snapshot["cohorts"].values())
    return {
        "cohorts": {k: len(v) for k, v in snapshot["cohorts"].items()},
        "research_unique": len(research),
        "desired": len(snapshot["desired"]),
        "subscribed": len(snapshot["subscribed"]),
        "research_desired_overlap": len(research & snapshot["desired"]),
        "research_subscribed_overlap": len(research & snapshot["subscribed"]),
        "monitoring_evidence": snapshot["monitoring_status"],
        "runtime_admitted": "UNKNOWN",
        "receipt_health": "UNKNOWN",
        "paper_running": "UNKNOWN",
        "demo_running": "UNKNOWN",
        "scientifically_qualified": "NOT_ESTABLISHED",
        "trading_authorized": "NOT_ESTABLISHED",
        "source_shas": snapshot["sources"],
    }


def db_status(db: Path) -> dict:
    with closing(connect(db, False)) as con:
        counts = {
            r[0]: r[1]
            for r in con.execute(
                "SELECT m.cohort_id,COUNT(*) FROM cohort_memberships m "
                "WHERE m.version=(SELECT MAX(c.version) FROM cohorts c "
                "WHERE c.cohort_id=m.cohort_id) GROUP BY m.cohort_id"
            )
        }
        rows = con.execute("SELECT key,value FROM snapshot_meta")
        meta = dict(rows)
        counts["research_unique"] = con.execute(
            "SELECT COUNT(DISTINCT m.wallet_id) FROM cohort_memberships m "
            "WHERE m.version=(SELECT MAX(c.version) FROM cohorts c "
            "WHERE c.cohort_id=m.cohort_id)"
        ).fetchone()[0]
        counts["desired"] = con.execute(
            "SELECT COUNT(*) FROM monitoring WHERE configured=1"
        ).fetchone()[0]
        counts["subscribed"] = con.execute(
            "SELECT COUNT(*) FROM monitoring WHERE subscribed=1"
        ).fetchone()[0]
        counts["runtime_admitted"] = "UNKNOWN"
        sources = {
            key: value
            for key, value in con.execute("SELECT source_key,sha256 FROM evidence_artifacts")
        }
        counts["paper_running"] = "UNKNOWN"
        counts["scientifically_qualified"] = "NOT_ESTABLISHED"
        counts["trading_authorized"] = "NOT_ESTABLISHED"
        observed = meta.get("observed_at")
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(observed)).total_seconds()
            freshness = "CURRENT" if 0 <= age <= 86400 else "STALE"
        except TypeError, ValueError:
            freshness = "UNKNOWN"
        return {
            "counts": counts,
            "generation": meta,
            "source_shas": sources,
            "freshness": freshness,
        }


def asof_cutoff(value: str | None) -> str:
    """Use a conservative UTC knowledge cutoff, never historical event time."""
    if value is None:
        return datetime.max.replace(tzinfo=timezone.utc).isoformat()
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("as-of timestamp must include UTC offset")
    return instant.astimezone(timezone.utc).isoformat()


def backup(db: Path, target: Path) -> None:
    """Create a consistent backup of the private inventory, never an external DB."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(target.parent.stat().st_mode) != 0o700:
        raise PermissionError("backup parent directory must be private")
    if target.exists() or target.is_symlink():
        raise FileExistsError("backup already exists")
    with closing(connect(db, False)) as source:
        with closing(sqlite3.connect(target)) as dest:
            source.backup(dest)
    os.chmod(target, 0o600)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-private read-only-authority wallet registry"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--tracker-env", type=Path, default=ENV)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    flags = sync.add_mutually_exclusive_group(required=True)
    flags.add_argument("--dry-run", action="store_true")
    flags.add_argument("--apply", action="store_true")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("runtime")
    save = sub.add_parser("backup")
    save.add_argument("--to", required=True, type=Path)
    report = sub.add_parser("report")
    report.add_argument("--redacted", action="store_true", required=True)
    wallet = sub.add_parser("wallet")
    lookup = wallet.add_mutually_exclusive_group(required=True)
    lookup.add_argument("--address")
    lookup.add_argument("--alias")
    wallet.add_argument("--namespace", default="frozen_pm01", choices=("frozen_pm01",))
    wallet.add_argument("--asof", help="UTC as-known cutoff")
    cohort = sub.add_parser("cohort")
    cohort.add_argument("name", choices=tuple(RESEARCH))
    portfolio = sub.add_parser("portfolio")
    portfolio.add_argument("name", nargs="?", choices=tuple(PORTFOLIOS))
    portfolio.add_argument("--asof", help="UTC as-known cutoff")
    args = parser.parse_args(argv)
    if args.command == "sync":
        snapshot = collect(args.root, args.tracker_env)
        result = status(snapshot)
        if args.apply:
            result.update(apply(args.db, snapshot, datetime.now(timezone.utc).isoformat()))
        print(json.dumps(result, sort_keys=True))
    elif args.command == "status":
        print(json.dumps(db_status(args.db), sort_keys=True))
    elif args.command == "doctor":
        live = status(collect(args.root, args.tracker_env))
        stored = db_status(args.db)
        matched = (
            all(
                stored["counts"].get(k) == live[k]
                for k in ("research_unique", "desired", "subscribed")
            )
            and stored["source_shas"] == live["source_shas"]
            and stored["freshness"] == "CURRENT"
        )
        print(
            json.dumps(
                {
                    "counts_match": matched,
                    "freshness": stored["freshness"],
                    "runtime_admitted": "UNKNOWN",
                    "source_shas": live["source_shas"],
                },
                sort_keys=True,
            )
        )
        return 0 if matched else 2
    elif args.command == "backup":
        source = args.db.resolve()
        destination = args.to.resolve()
        if source.parent not in destination.parents:
            raise ValueError("backup must remain within the private registry root")
        backup(args.db, args.to)
        with closing(connect(args.to, False)) as con:
            if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("backup integrity check failed")
        print(json.dumps({"backup_verified": True, "bytes": args.to.stat().st_size}))
    elif args.command == "runtime":
        desired, subscribed, config = observe_monitoring(args.tracker_env)
        result = observe_ledger(Path(config["TRACKER_LEDGER_PATH"]), desired | subscribed)
        print(json.dumps(result, sort_keys=True))
    elif args.command == "report":
        stored = db_status(args.db)
        c = stored["counts"]
        print("# Private wallet registry — redacted snapshot")
        print(f"\nSource observed: {stored['generation'].get('observed_at', 'UNKNOWN')}")
        print(f"\nGeneration SHA: {stored['generation'].get('manifest_sha256', 'UNKNOWN')}")
        cohort_str = ", ".join(f"{key}: {c[key]}" for key in RESEARCH)
        print(
            f"\nResearch: {c['research_unique']} ({cohort_str}); "
            f"configured: {c['desired']}; subscribed: {c['subscribed']}."
        )
        print(f"\nFreshness: {stored['freshness']}")
        print(
            "\nRuntime admitted: UNKNOWN. Paper/demo running: UNKNOWN. "
            "Scientific qualification: NOT ESTABLISHED. Trading authorization: NOT ESTABLISHED."
        )
        print(
            "\nHistorical vendor fill pagination is not complete source-account "
            "reconstruction or prospective first-known evidence."
        )
    elif args.command == "wallet":
        cutoff = asof_cutoff(args.asof)
        with closing(connect(args.db, False)) as con:
            if args.address:
                row = con.execute(
                    "SELECT wallet_id FROM wallets WHERE address=?",
                    (normalize(args.address),),
                ).fetchone()
            else:
                matches = con.execute(
                    "SELECT DISTINCT wallet_id FROM wallet_aliases "
                    "WHERE namespace=? AND alias=? AND known_at<=?",
                    (args.namespace, args.alias, cutoff),
                ).fetchall()
                if len(matches) > 1:
                    raise ValueError("ambiguous alias, fail closed")
                row = matches[0] if matches else None
            if not row:
                print(json.dumps({"found": False}))
            else:
                cohorts = [
                    r[0]
                    for r in con.execute(
                        "SELECT m.cohort_id FROM cohort_memberships m "
                        "WHERE m.wallet_id=? AND m.known_at<=? AND m.version=("
                        "SELECT MAX(m2.version) FROM cohort_memberships m2 "
                        "WHERE m2.cohort_id=m.cohort_id AND m2.known_at<=?)",
                        (*row, cutoff, cutoff),
                    )
                ]
                excluded = con.execute(
                    "SELECT EXISTS(SELECT 1 FROM exclusions WHERE wallet_id=? AND known_at<=?)",
                    (*row, cutoff),
                ).fetchone()[0]
                print(
                    json.dumps(
                        {
                            "found": True,
                            "cohorts": cohorts,
                            "excluded": bool(excluded),
                            "authorized": False,
                        }
                    )
                )
    elif args.command == "cohort":
        with closing(connect(args.db, False)) as con:
            count = con.execute(
                "SELECT COUNT(*) FROM cohort_memberships m WHERE m.cohort_id=? "
                "AND m.version=(SELECT MAX(version) FROM cohorts WHERE cohort_id=?)",
                (args.name, args.name),
            ).fetchone()[0]
        print(json.dumps({"cohort": args.name, "count": count}))
    elif args.command == "portfolio":
        names = [args.name] if args.name else list(PORTFOLIOS)
        cutoff = asof_cutoff(args.asof)
        with closing(connect(args.db, False)) as con:
            result = {}
            for name in names:
                members = [
                    r[0]
                    for r in con.execute(
                        "SELECT pm.member_alias FROM portfolio_memberships pm "
                        "JOIN portfolio_versions pv USING(portfolio_id,version) "
                        "WHERE pm.portfolio_id=? AND pv.known_at<=?",
                        (name, cutoff),
                    )
                ]
                result[name] = {
                    "members": members,
                    "status": "RESEARCH_ONLY" if members else "UNKNOWN_AT_ASOF",
                    "actual_run": "UNKNOWN",
                    "authorized": False,
                }
        print(json.dumps(result, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
