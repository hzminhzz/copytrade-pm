"""Read-only operator diagnostics for missing signed research selection lineage.

Never invent or self-sign an owner selection. Never mutate a live registry or
turn a valid SQLite physical check into scientific/trading authorization.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from . import wallet_registry_catalog, wallet_registry_signed_catalog


def inspect_provenance(db: Path) -> dict:
    """Separate SQLite byte integrity from unverified selection authority."""
    report: dict = {
        "schema": "wallet_registry_selection_provenance_diagnostics_v1",
        "sqlite_physical_integrity": "FAILED_OR_UNAVAILABLE",
        "selection_provenance": "UNKNOWN",
        "safe_to_write": False,
        "doctor_ready": False,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
    if db.is_symlink() or not db.is_file():
        report["failure_code"] = "REGISTRY_DB_MISSING_OR_SYMLINK"
        return report
    uri = f"file:{db.resolve()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as con:
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")
            if con.execute("PRAGMA query_only").fetchone()[0] != 1:
                report["failure_code"] = "REGISTRY_NOT_QUERY_ONLY"
                return report
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                report["failure_code"] = "REGISTRY_PHYSICAL_INTEGRITY_FAILED"
                return report
            if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
                report["failure_code"] = "REGISTRY_FOREIGN_KEYS_FAILED"
                return report
            report["sqlite_physical_integrity"] = "VERIFIED"
            sources = con.execute(
                "SELECT source_sha256, COUNT(*), GROUP_CONCAT(portfolio_id, ',') "
                "FROM research_selections GROUP BY source_sha256 "
                "ORDER BY source_sha256"
            ).fetchall()
            proof_count = con.execute("SELECT COUNT(*) FROM research_selection_proofs").fetchone()[
                0
            ]
            issues = []
            valid = []
            for source, count, pids in sources:
                # Reviewed SHA-pinned V2 is grandfathered and not signed.
                if source == wallet_registry_catalog.V2_SHA256:
                    valid.append(
                        {
                            "source_sha256": source,
                            "state": "PINNED_V2_LEGACY",
                            "selection_count": count,
                        }
                    )
                    continue
                if not isinstance(source, str) or len(source) != 64:
                    state = "INVALID_SOURCE_ID"
                else:
                    try:
                        wallet_registry_signed_catalog.load(con, source)
                        state = "SIGNATURE_VERIFIED"
                    except ValueError as exc:
                        state = (
                            "MISSING_SIGNED_PROOF"
                            if str(exc) == "unverified research selection provenance"
                            else "INVALID_SIGNED_PROOF"
                        )
                entry = {
                    "source_sha256": source,
                    "selection_count": count,
                    "portfolio_ids": sorted((pids or "").split(",")),
                    "state": state,
                }
                (valid if state == "SIGNATURE_VERIFIED" else issues).append(entry)
            report.update(
                {
                    "selection_provenance": "BLOCKED" if issues else "VERIFIED_OR_LEGACY_PINNED",
                    "selection_source_count": len(sources),
                    "signed_proof_count": proof_count,
                    "source_status": valid,
                    "blockers": issues,
                    "selection_provenance_ready": not issues,
                    "doctor_ready": False,  # Full registry state is not audited here.
                    "safe_to_write": False,
                }
            )
            return report
    except (sqlite3.Error, OSError, ValueError) as exc:
        report["failure_code"] = type(exc).__name__
        return report
