"""Fail-closed science and authorization boundary for the inventory database.

The original PM-02 scientific signoff remains unimplemented. Owner approval and
an independently signed forward matched-outcome producer are both missing.
Therefore registry v5 may store only explicitly non-positive research verdicts.
It cannot transition to scientific qualification or broker authorization.
"""

from __future__ import annotations

import sqlite3

NEGATIVE_VERDICTS = ("UNQUALIFIED", "BLOCKED", "NOT_ESTABLISHED")
DDL = """
CREATE TRIGGER IF NOT EXISTS qualification_reject_unsupported_positive_insert
BEFORE INSERT ON qualification_decisions
WHEN NEW.verdict NOT IN ('UNQUALIFIED','BLOCKED','NOT_ESTABLISHED')
BEGIN
    SELECT RAISE(ABORT, 'INDEPENDENT_SCIENTIFIC_SIGNOFF_NOT_IMPLEMENTED');
END;
CREATE TRIGGER IF NOT EXISTS qualification_reject_unsupported_positive_update
BEFORE UPDATE OF verdict ON qualification_decisions
WHEN NEW.verdict NOT IN ('UNQUALIFIED','BLOCKED','NOT_ESTABLISHED')
BEGIN
    SELECT RAISE(ABORT, 'INDEPENDENT_SCIENTIFIC_SIGNOFF_NOT_IMPLEMENTED');
END;
"""


def status(con: sqlite3.Connection) -> dict:
    """Reporting is read-only and never treats counts as trade permissions."""
    by_type = {
        row[0]: row[1]
        for row in con.execute(
            "SELECT verdict,COUNT(*) FROM qualification_decisions GROUP BY verdict"
        )
    }
    if any(label not in NEGATIVE_VERDICTS for label in by_type):
        return {
            "registry_science_integrity": "FAILED_UNTRUSTED_VERDICT",
            "scientifically_qualified": "NOT_ESTABLISHED",
            "trading_authorized": False,
            "positive_verdicts_supported": False,
        }
    return {
        "registry_science_integrity": "FAIL_CLOSED",
        "recorded_research_blocked_or_negative": sum(by_type.values()),
        "scientifically_qualified": "NOT_ESTABLISHED",
        "trading_authorized": False,
        "positive_verdicts_supported": False,
        "external_independent_signoff": "UNAVAILABLE",
    }
