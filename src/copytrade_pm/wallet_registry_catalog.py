"""Versioned read interface for *research-only* wallet/portfolio selections.

The source of truth for a research *decision* is the committed SHA-pinned
manifest, not an unreviewed Markdown edit or the portfolio run journal.
The private SQLite database materializes an immutable as-of index. It never
owns trading risk, research fills, market data or paper-account finance.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

V2_FILE = "docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json"
V2_SHA256 = "21f4e9406370fefcb0e38719c2a07bb57b68b073d70b3530034f7f5944c240fc"
V2_COMMIT = "a87e587700282517d68524997486d5f2fa3efd57"
V2_KNOWN_AT = "2026-11-04T09:06:33+00:00"
# Pin the complete private wallet address by its SHA, never a display prefix.
WHALE_ADDRESS_SHA256 = "d505878b68a81d92889946d1fc5a04d06e7d0d5f877fa7fc8f947797f950be03"
PRIVATE_PHASE4_SOURCE_SHA256 = "0391836ead6b264a1d9e89d6bc7bf8cb989e330b9104d40d6b7065378049897e"
PRIVATE_PHASE4_SOURCE = Path(
    "/home/quant/dev/copytrade-pm/docs/PHASE4_PROPR_SIMULATION_RESULTS_108_WALLETS_20261103.csv"
)
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
NAMES = {
    "E6": "gemini.phase4/E6",
    "E2": "gemini.phase4/E2",
    "E3": "gemini.phase4/E3",
    "B_phase5": "gemini.phase5/B",
}
ROLE = {
    "E6": "PRIMARY_FORWARD_PAPER_RESEARCH",
    "E2": "THREE_POD_FORWARD_PAPER_CHALLENGER",
    "P1": "INCUMBENT_HISTORICAL_BASELINE_NO_NEW_PROMOTION",
    "P14": "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER",
    "E3": "OPTIONAL_DEFENSIVE_RESEARCH_RESERVE",
    "B_phase5": "SEPARATE_PHASE5_COMPARISON_NOT_SELECTED",
}
DDL = """
CREATE TABLE IF NOT EXISTS research_selections(
    source_sha256 TEXT NOT NULL,
    scope TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    portfolio_version INTEGER NOT NULL,
    role TEXT NOT NULL,
    priority INTEGER,
    known_at TEXT NOT NULL,
    PRIMARY KEY(source_sha256,scope,portfolio_id),
    FOREIGN KEY(portfolio_id,portfolio_version)
        REFERENCES portfolio_versions(portfolio_id,version)
);
CREATE INDEX IF NOT EXISTS idx_research_selection_cut
    ON research_selections(scope,known_at,portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_membership_wallet
    ON portfolio_memberships(wallet_id,portfolio_id,version);
CREATE INDEX IF NOT EXISTS idx_wallet_alias_lookup
    ON wallet_aliases(alias,known_at,wallet_id);
CREATE TRIGGER IF NOT EXISTS guard_sealed_membership_update
BEFORE UPDATE ON portfolio_memberships
WHEN EXISTS (SELECT 1 FROM portfolio_seals s WHERE s.portfolio_id=OLD.portfolio_id
             AND s.version=OLD.version)
BEGIN SELECT RAISE(ABORT, 'sealed portfolio membership is immutable'); END;
CREATE TRIGGER IF NOT EXISTS guard_sealed_membership_delete
BEFORE DELETE ON portfolio_memberships
WHEN EXISTS (SELECT 1 FROM portfolio_seals s WHERE s.portfolio_id=OLD.portfolio_id
             AND s.version=OLD.version)
BEGIN SELECT RAISE(ABORT, 'sealed portfolio membership is immutable'); END;
CREATE TRIGGER IF NOT EXISTS guard_sealed_membership_insert
BEFORE INSERT ON portfolio_memberships
WHEN EXISTS (SELECT 1 FROM portfolio_seals s WHERE s.portfolio_id=NEW.portfolio_id
             AND s.version=NEW.version)
BEGIN SELECT RAISE(ABORT, 'sealed portfolio membership is immutable'); END;
"""


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _json_sha(obj: dict) -> str:
    return sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_v2(repository: Path, *, observed_at: str) -> dict:
    """Validate the reviewed V2 selection, no silent portfolio redefinition."""
    cutoff = datetime.fromisoformat(observed_at)
    if cutoff.tzinfo is None:
        raise ValueError("observed_at requires UTC offset")
    p = repository / V2_FILE
    if not p.is_file() or p.is_symlink() or _sha(p) != V2_SHA256:
        raise ValueError("unreviewed portfolio V2 source drift")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if (
        doc.get("schema") != "gemini_research_portfolio_priority_v2"
        or doc.get("scope") != "NEW_FORWARD_PAPER_RESEARCH_ONLY"
        or doc.get("status") != "SELECTION_SAVED_NOT_REGISTERED_OR_DEPLOYED"
        or doc.get("decision_authority") != "user_approved"
        or doc.get("research_contract", {}).get("trading_authorized") is not False
        or doc.get("research_contract", {}).get("manual_activation_allowed") is not False
        or doc.get("research_contract", {}).get("source_equity_relative_whole_book_required")
        is not True
        or doc.get("new_forward_paper_priority") != ["E6", "E2", "P1", "E3", "B_phase5"]
        or set(doc.get("portfolios", {}))
        != {"E6", "E2", "E3", "B_phase5", "P1", "P14", "P16", "P15"}
    ):
        raise ValueError("unreviewed or authorized V2 declaration")
    if datetime.fromisoformat(V2_KNOWN_AT) > cutoff.astimezone(timezone.utc):
        raise ValueError("portfolio V2 not yet known at requested cut")
    definitions = {}
    for ref, canonical in NAMES.items():
        item = doc["portfolios"][ref]
        aliases = [x["canonical_alias"] for x in item["members"]]
        if len(aliases) != item["pod_count"] or len(aliases) != len(set(aliases)):
            raise ValueError("V2 repeated/mismatched manager identities")
        if item["state"] != ROLE[ref]:
            raise ValueError("unreviewed V2 role")
        payload = {
            "schema": "wallet_portfolio_definition_v2",
            "portfolio_id": canonical,
            "aliases": aliases,
            "original_source_aliases": [x["wallet"] for x in item["members"]],
            "source_commit": V2_COMMIT,
            "source_doc_sha256": V2_SHA256,
            "selection_known_at": V2_KNOWN_AT,
            "status": "RESEARCH_SELECTION_ONLY",
            "sizing_contract": "GEMINI_REFERENCE_K_NOT_EXECUTABLE",
            "source_identity_proven": False,
            "order_route": "NONE",
        }
        definitions[canonical] = {
            "payload": payload,
            "definition_sha256": _json_sha(payload),
            "members": aliases,
        }
    selections = []
    for ref in ("E6", "E2", "P1", "P14", "E3", "B_phase5"):
        item = doc["portfolios"][ref]
        if item["state"] != ROLE[ref]:
            raise ValueError("unreviewed V2 selection role")
        selections.append(
            {
                "portfolio_id": NAMES.get(ref, ref),
                "priority": item["priority"],
                "role": item["state"],
            }
        )
    if [x["priority"] for x in selections] != [1, 2, 3, None, 4, 5]:
        raise ValueError("unreviewed portfolio priority order")
    return {
        "source_sha256": V2_SHA256,
        "known_at": V2_KNOWN_AT,
        "source_commit": V2_COMMIT,
        "definitions": definitions,
        "selections": selections,
        "document": doc,
    }


def read_private_identities(path: Path | None, v2: dict) -> dict[str, str]:
    """Bind user-approved alias equivalences to owner-private source addresses.

    A generic 'HL Perps Whale' display name is never used as an identity.
    Missing source means no claims of resolved identities. Conflicts fail.
    """
    if path is None or not path.is_file():
        return {}
    if path.is_symlink():
        raise ValueError("private Phase 4 identity source is a symlink")
    if path.resolve() == PRIVATE_PHASE4_SOURCE and _sha(path) != PRIVATE_PHASE4_SOURCE_SHA256:
        raise ValueError("unreviewed private Phase 4 source SHA drift")
    mapped: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            alias, addr = row.get("alias", ""), row.get("address", "").lower()
            if not alias or not ADDRESS.fullmatch(addr):
                raise ValueError("invalid Phase 4 private address evidence")
            if alias in mapped and mapped[alias] != addr:
                raise ValueError("conflicting Phase 4 alias identities")
            mapped[alias] = addr
    resolved: dict[str, str] = {}
    required = {"E6", "E2"}
    for name in ("E6", "E2", "P1", "P14", "E3"):
        item = v2["document"]["portfolios"][name]
        for member in item["members"]:
            raw = member["wallet"]
            canonical = member["canonical_alias"]
            addr = mapped.get(raw)
            if name in required and not addr:
                raise ValueError("missing required Phase 4 wallet identity")
            if addr is None:
                continue
            if (
                canonical == "Whale_0x5f94"
                and sha256(addr.encode()).hexdigest() != WHALE_ADDRESS_SHA256
            ):
                raise ValueError("full-address whale digest mismatch")
            if raw == "HL Perps Whale" and not canonical.startswith("Whale_0x"):
                raise ValueError("ambiguous whale display name")
            for alias in (raw, canonical):
                if alias in resolved and resolved[alias] != addr:
                    raise ValueError("cross-portfolio canonical alias collision")
                # Do not add the ambiguous generic whale label as a lookup alias.
                if alias != "HL Perps Whale":
                    resolved[alias] = addr
    return resolved


def store_selection(con: sqlite3.Connection, v2: dict, ids: dict[str, int], when: str) -> None:
    """Write only immutable research decisions and identity pointers.

    Must be called inside the existing wallet_registry.apply() transaction.
    """
    if datetime.fromisoformat(when) < datetime.fromisoformat(v2["known_at"]):
        raise ValueError("research selection cannot be backdated")
    for pid, definition in v2["definitions"].items():
        payload = definition["payload"]
        previous = con.execute(
            "SELECT pv.version,ps.definition_sha256 FROM portfolio_versions pv "
            "LEFT JOIN portfolio_seals ps USING(portfolio_id,version) "
            "WHERE pv.portfolio_id=? ORDER BY pv.version DESC LIMIT 1",
            (pid,),
        ).fetchone()
        if previous and previous[1] == definition["definition_sha256"]:
            version = previous[0]
        else:
            previous_date = con.execute(
                "SELECT MAX(selection_known_at) FROM portfolio_seals WHERE portfolio_id=?", (pid,)
            ).fetchone()[0]
            if previous_date and previous_date > v2["known_at"]:
                raise ValueError("rejected out-of-order portfolio identity source")
            version = previous[0] + 1 if previous else 1
            con.execute(
                "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
                (
                    pid,
                    version,
                    payload["status"],
                    V2_FILE,
                    v2["known_at"],
                    payload["sizing_contract"],
                ),
            )
            con.executemany(
                "INSERT INTO portfolio_memberships VALUES(?,?,?,?)",
                ((pid, version, alias, ids.get(alias)) for alias in definition["members"]),
            )
            con.execute(
                "INSERT INTO portfolio_seals VALUES(?,?,?,?,?,?)",
                (pid, version, definition["definition_sha256"], V2_SHA256, V2_COMMIT, V2_KNOWN_AT),
            )
    for event in v2["selections"]:
        pid = event["portfolio_id"]
        version = con.execute(
            "SELECT MAX(version) FROM portfolio_versions WHERE portfolio_id=?", (pid,)
        ).fetchone()[0]
        if version is None:
            raise ValueError("V2 selection references a missing historical definition")
        expected = (
            V2_SHA256,
            "NEW_FORWARD_PAPER_RESEARCH",
            pid,
            version,
            event["role"],
            event["priority"],
            V2_KNOWN_AT,
        )
        existing = con.execute(
            "SELECT source_sha256,scope,portfolio_id,portfolio_version,role,priority,known_at "
            "FROM research_selections WHERE source_sha256=? AND scope=? AND portfolio_id=?",
            expected[:3],
        ).fetchone()
        if existing is not None and existing != expected:
            raise ValueError("immutable selection history changed")
        if existing is None:
            con.execute("INSERT INTO research_selections VALUES(?,?,?,?,?,?,?)", expected)


def resolve_alias(con: sqlite3.Connection, alias: str, cutoff: str) -> int | None:
    """As-of alias identity, across namespaces; reject collisions instead of guessing."""
    rows = con.execute(
        "SELECT DISTINCT wallet_id FROM wallet_aliases "
        "WHERE alias=? AND known_at<=? ORDER BY wallet_id LIMIT 2",
        (alias, cutoff),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError("ambiguous canonical wallet alias")
    return rows[0][0] if rows else None


def resolve_portfolio(con: sqlite3.Connection, ref: str, cutoff: str) -> str | None:
    """Resolve unique short ref or explicit namespace, without ambiguous B collisions."""
    explicit = {
        "q3/A": "A",
        "q3/B": "B",
        "q3/C": "C",
        "gemini.phase3/P1": "P1",
        "gemini.phase3/P14": "P14",
        "gemini.phase3/P16": "P16",
    }
    names = [
        x[0]
        for x in con.execute(
            "SELECT DISTINCT portfolio_id FROM portfolio_versions "
            "WHERE known_at<=? ORDER BY portfolio_id",
            (cutoff,),
        )
    ]
    target = explicit.get(ref, ref)
    matches = [name for name in names if name == target or name.rsplit("/", 1)[-1] == target]
    if ref in explicit:
        return target if target in names else None
    if len(matches) > 1:
        raise ValueError("ambiguous portfolio alias; specify qualified name")
    return matches[0] if matches else None


def list_selection(con: sqlite3.Connection, cutoff: str) -> dict:
    """Return current new-study selection, explicitly NOT paper-running state."""
    installed = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_selections'"
    ).fetchone()
    if installed is None:
        return {
            "selection_state": "SCHEMA_UPGRADE_REQUIRED",
            "selection_sha256": None,
            "portfolios": [],
            "paper_running": "UNKNOWN",
            "trading_authorized": False,
        }
    sources = con.execute(
        "SELECT DISTINCT source_sha256,known_at FROM research_selections "
        "WHERE scope='NEW_FORWARD_PAPER_RESEARCH' AND known_at<=? "
        "ORDER BY known_at DESC,source_sha256 DESC LIMIT 1",
        (cutoff,),
    ).fetchone()
    if sources is None:
        return {
            "selection_state": "NOT_REGISTERED_AT_ASOF",
            "selection_sha256": None,
            "portfolios": [],
            "paper_running": "UNKNOWN",
            "trading_authorized": False,
        }
    sha, at = sources
    from . import wallet_registry_signed_catalog as signed

    if sha == V2_SHA256:
        if at != V2_KNOWN_AT:
            raise ValueError("reviewed V2 research selection known-at drift")
        expected = {
            "gemini.phase4/E6": (ROLE["E6"], 1),
            "gemini.phase4/E2": (ROLE["E2"], 2),
            "P1": (ROLE["P1"], 3),
            "P14": (ROLE["P14"], None),
            "gemini.phase4/E3": (ROLE["E3"], 4),
            "gemini.phase5/B": (ROLE["B_phase5"], 5),
        }
        source_status = "OWNER_APPROVED_RESEARCH_ONLY"
    else:
        verified = signed.load(con, sha)
        if at != verified["first_known_at"]:
            raise ValueError("signed research selection known-at drift")
        expected = {
            item["portfolio_id"]: (item["role"], item["priority"])
            for item in verified["document"]["selections"]
        }
        source_status = "SIGNATURE_CHECKED_RESEARCH_ONLY"
    rows = con.execute(
        "SELECT portfolio_id,portfolio_version,role,priority FROM research_selections "
        "WHERE source_sha256=? AND scope='NEW_FORWARD_PAPER_RESEARCH' "
        "ORDER BY priority IS NULL,priority,portfolio_id",
        (sha,),
    ).fetchall()
    from .wallet_registry_portfolios import select_asof

    if len(rows) != len(expected) or any(
        pid not in expected or expected[pid] != (role, priority) for pid, _, role, priority in rows
    ):
        raise ValueError("immutable research selection history drift")
    result = []
    for pid, version, role, priority in rows:
        source = select_asof(con, pid, cutoff, version=version)
        if source.get("version") != version or not source.get("definition_sha256"):
            raise ValueError("selection refers to stale/unsealed portfolio")
        if (
            source.get("source_doc_sha256") != (V2_SHA256 if sha == V2_SHA256 else sha)
            and pid in NAMES.values()
        ):
            raise ValueError("research portfolio source seal drift")
        if sha != V2_SHA256 and source.get("source_doc_sha256") != sha:
            raise ValueError("signed research portfolio source seal drift")
        result.append(
            {
                "portfolio_id": pid,
                "version": version,
                "priority": priority,
                "role": role,
                "members": source["members"],
                "alias_resolution_complete": source["alias_resolution_complete"],
                "definition_sha256": source["definition_sha256"],
                "paper_running": "UNKNOWN",
                "trading_authorized": False,
            }
        )
    return {
        "selection_state": source_status,
        "selection_sha256": sha,
        "selection_known_at": at,
        "portfolios": result,
        "paper_running": "UNKNOWN",
        "trading_authorized": False,
    }
