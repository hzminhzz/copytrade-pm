"""Immutable, SHA-pinned, research-only wallet portfolio decision contracts.

The public documents and first-known Git revisions are decision provenance, not
source-wallet identity proof or execution authorization. No broker functionality.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

# The dates are the conservatively pinned timestamps of the last committed
# version of each document. Do not backdate using trader fills or vendor clocks.
# A changed document MUST be reviewed and repinned in a new source generation.
DECISIONS: dict[str, dict[str, str]] = {
    "P1": {
        "sha256": "2711e543513c8f49273f2d28d4ab0238978b0b38b84aa12b07f0856186b4ae38",
        "commit": "f7f68291aaf3f442d834850feb012fe0052107a9",
        "known_at": "2026-11-02T17:52:22+00:00",
        "path": "docs/decisions/2026-11-02-gemini-selected-three-pod.md",
        "status": "PAPER_RESEARCH_PRIMARY",
        "sizing": "P1_VIRTUAL_10000_USD_TOTAL_NOMINAL_LOSS_600_USD",
    },
    "P14": {
        "sha256": "8a92b5f3fc581e21779e791cdcd9a682193cce158a5359ced667466d17415ad5",
        "commit": "f7f68291aaf3f442d834850feb012fe0052107a9",
        "known_at": "2026-11-02T17:52:22+00:00",
        "path": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
        "status": "PAPER_RESEARCH_CHALLENGER",
        "sizing": "P14_VIRTUAL_10000_USD_TOTAL_NOMINAL_LOSS_600_USD",
    },
    "P16": {
        "sha256": "8a92b5f3fc581e21779e791cdcd9a682193cce158a5359ced667466d17415ad5",
        "commit": "f7f68291aaf3f442d834850feb012fe0052107a9",
        "known_at": "2026-11-02T17:52:22+00:00",
        "path": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
        "status": "RESEARCH_OPTIONAL_CONTROL",
        "sizing": "P16_VIRTUAL_10000_USD_ILLUSTRATIVE_RISK_600_USD",
    },
    "A": {
        "sha256": "a031b29a529674eb32208fc9b4ef983bccbefb1c1eb7842cfb0de28758dd20c4",
        "commit": "67d4cb776cd0b2a836c0fe878102bfc97e034ea7",
        "known_at": "2026-11-02T07:01:53+00:00",
        "path": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
        "status": "HISTORICAL_RESEARCH_ONLY",
        "sizing": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "B": {
        "sha256": "a031b29a529674eb32208fc9b4ef983bccbefb1c1eb7842cfb0de28758dd20c4",
        "commit": "67d4cb776cd0b2a836c0fe878102bfc97e034ea7",
        "known_at": "2026-11-02T07:01:53+00:00",
        "path": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
        "status": "HISTORICAL_RESEARCH_ONLY",
        "sizing": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "C": {
        "sha256": "a031b29a529674eb32208fc9b4ef983bccbefb1c1eb7842cfb0de28758dd20c4",
        "commit": "67d4cb776cd0b2a836c0fe878102bfc97e034ea7",
        "known_at": "2026-11-02T07:01:53+00:00",
        "path": "docs/Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md",
        "status": "HISTORICAL_RESEARCH_ONLY",
        "sizing": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "Combo2": {
        "sha256": "6684bae5c0aa78b5c48757862014231006037ec63988837e1828ec3d6cc2dbaf",
        "commit": "fb50105d130b7d99f0414560d1d62ce487066d40",
        "known_at": "2026-11-02T10:28:11+00:00",
        "path": "docs/COMBO2-PAPER.md",
        "status": "PAPER_RESEARCH_EXPERIMENT",
        "sizing": "COMBO2_VIRTUAL_5000_USD_ACCOUNT_NOT_BROKER",
    },
}

SCHEMA = "wallet_portfolio_definition_v1"
SEALED_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_seals (
    portfolio_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    definition_sha256 TEXT NOT NULL,
    doc_sha256 TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    selection_known_at TEXT NOT NULL,
    PRIMARY KEY(portfolio_id,version),
    FOREIGN KEY(portfolio_id,version)
        REFERENCES portfolio_versions(portfolio_id,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_seal_sha
    ON portfolio_seals(portfolio_id,definition_sha256);
"""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def read_decisions(
    repository: Path, source_members: dict[str, tuple[str, ...]], *, observed_at: str
) -> dict[str, dict]:
    """Fail closed on even whitespace changes to a pinned decision document."""
    now = datetime.fromisoformat(observed_at)
    if now.tzinfo is None:
        raise ValueError("observed_at must contain UTC offset")
    if set(source_members) != set(DECISIONS):
        raise ValueError("unreviewed portfolio roster must not be sealed")
    result = {}
    for pid, record in sorted(DECISIONS.items()):
        known = datetime.fromisoformat(record["known_at"])
        if known > now.astimezone(timezone.utc):
            raise ValueError("portfolio source was not yet known")
        document = repository / record["path"]
        if not document.is_file() or document.is_symlink():
            raise ValueError("missing or symlinked portfolio decision source")
        actual_sha = sha256(document.read_bytes()).hexdigest()
        if actual_sha != record["sha256"]:
            raise ValueError("portfolio decision document drift (redacted)")
        members = source_members[pid]
        if not members or len(set(members)) != len(members):
            raise ValueError("missing or repeated portfolio member")
        payload = {
            "schema": SCHEMA,
            "portfolio_id": pid,
            "aliases": list(members),
            "source_commit": record["commit"],
            "source_doc_sha256": actual_sha,
            "selection_known_at": record["known_at"],
            "status": record["status"],
            "sizing_contract": record["sizing"],
            "source_identity_proven": False,
            "order_route": "NONE",
        }
        result[pid] = {
            "payload": payload,
            "definition_sha256": sha256(_canonical_json(payload)).hexdigest(),
        }
    return result


def _decision_source_path(rel_path: str) -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / rel_path
    for parent in here.parents:
        candidate = parent / rel_path
        if candidate.is_file() or candidate.is_symlink():
            return candidate
    if (
        (Path.cwd() / "pyproject.toml").is_file()
        or (Path.cwd() / rel_path).is_file()
        or (Path.cwd() / rel_path).is_symlink()
    ):
        return Path.cwd() / rel_path
    return here.parents[2] / rel_path


def select_asof(con, portfolio_id: str, cutoff: str, *, version: int | None = None) -> dict:
    """Only independently validated sealed decisions are visible."""
    if version is not None and (type(version) is not int or version < 1):
        raise ValueError("invalid requested portfolio version")
    conditions = " AND pv.version=?" if version is not None else ""
    params = (portfolio_id, cutoff, version) if version is not None else (portfolio_id, cutoff)
    rows = con.execute(
        "SELECT pv.version,pv.status,pv.sizing_contract,ps.definition_sha256,"
        "ps.doc_sha256,ps.source_revision,ps.selection_known_at "
        "FROM portfolio_versions pv JOIN portfolio_seals ps USING(portfolio_id,version) "
        "WHERE pv.portfolio_id=? AND ps.selection_known_at<=?" + conditions + " "
        "ORDER BY pv.version DESC LIMIT 1",
        params,
    ).fetchall()
    if not rows:
        return {
            "portfolio_id": portfolio_id,
            "state": "UNKNOWN_AT_ASOF",
            "definition_sha256": None,
            "members": [],
            "order_route": "NONE",
            "paper_running": "UNKNOWN",
            "trading_authorized": False,
        }
    version, status, sizing, seal, doc_sha, commit, known_at = rows[0]
    members = con.execute(
        "SELECT member_alias,wallet_id FROM portfolio_memberships "
        "WHERE portfolio_id=? AND version=? ORDER BY member_alias",
        (portfolio_id, version),
    ).fetchall()
    from . import wallet_registry_catalog as catalog
    from .wallet_registry import PORTFOLIOS

    # The stored SHA is not proof that its underlying membership survived
    # unchanged. Reconstruct it from the reviewed, independent Git source.
    if portfolio_id in DECISIONS and doc_sha == DECISIONS[portfolio_id]["sha256"]:
        record = DECISIONS[portfolio_id]
        expected_members = sorted(PORTFOLIOS[portfolio_id])
        source = _decision_source_path(record["path"])
        if (
            not source.is_file()
            or source.is_symlink()
            or sha256(source.read_bytes()).hexdigest() != record["sha256"]
        ):
            raise ValueError("sealed portfolio source document drift")
        expected_payload = {
            "schema": SCHEMA,
            "portfolio_id": portfolio_id,
            "aliases": list(PORTFOLIOS[portfolio_id]),
            "source_commit": record["commit"],
            "source_doc_sha256": record["sha256"],
            "selection_known_at": record["known_at"],
            "status": record["status"],
            "sizing_contract": record["sizing"],
            "source_identity_proven": False,
            "order_route": "NONE",
        }
        expected_sha = sha256(_canonical_json(expected_payload)).hexdigest()
        required = (
            record["sha256"],
            record["commit"],
            record["known_at"],
            record["status"],
            record["sizing"],
        )
    elif doc_sha == catalog.V2_SHA256 and portfolio_id in catalog.NAMES.values():
        pinned = catalog.read_v2(Path(__file__).resolve().parents[2], observed_at=cutoff)
        definition = pinned["definitions"][portfolio_id]
        expected_members = sorted(definition["members"])
        expected_sha = definition["definition_sha256"]
        required = (
            catalog.V2_SHA256,
            catalog.V2_COMMIT,
            catalog.V2_KNOWN_AT,
            definition["payload"]["status"],
            definition["payload"]["sizing_contract"],
        )
    else:
        from . import wallet_registry_signed_catalog as signed

        signed_record = signed.load(con, doc_sha)
        payload, expected_sha = signed.definition(signed_record, portfolio_id)
        expected_members = sorted(payload["aliases"])
        required = (
            doc_sha,
            payload["source_commit"],
            payload["selection_known_at"],
            payload["status"],
            payload["sizing_contract"],
        )
    if (
        [alias for alias, _ in members] != expected_members
        or len(members) != len(expected_members)
        or seal != expected_sha
        or (doc_sha, commit, known_at, status, sizing) != required
    ):
        raise ValueError("sealed portfolio membership or definition disagrees with approved source")

    resolved = []
    for alias, frozen_wallet_id in members:
        # Match later first-known alias evidence as-of without rewriting
        # any frozen membership or backdating its source-known timestamp.
        known_id = catalog.resolve_alias(con, alias, cutoff)
        if frozen_wallet_id is not None and known_id is not None and frozen_wallet_id != known_id:
            raise ValueError("frozen portfolio member identity conflicts with observed alias")
        # Even an already-populated frozen ID is not sufficient if the
        # registry cannot establish its alias mapping at this as-of cutoff.
        resolved.append(known_id is not None)
    return {
        "portfolio_id": portfolio_id,
        "version": version,
        "state": status,
        "definition_sha256": seal,
        "source_doc_sha256": doc_sha,
        "source_commit": commit,
        "selection_known_at": known_at,
        "sizing_contract": sizing,
        "members": [row[0] for row in members],
        "alias_resolution_complete": bool(members) and all(resolved),
        "source_identity_proven": False,
        "paper_running": "UNKNOWN",
        "trading_authorized": False,
        "order_route": "NONE",
    }
