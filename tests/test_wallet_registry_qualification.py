"""No unsupported positive science verdicts or live authorization via SQLite."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_qualification as qual
from test_wallet_registry import fixture


def test_no_scientific_promotion_from_manual_registry_writes(tmp_path: Path) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    with closing(registry.connect(db, True)) as con:
        with con:
            con.execute(
                "INSERT INTO qualification_decisions VALUES(?,?,?,?,?,?)",
                (
                    "negative",
                    1,
                    "research-only",
                    "a" * 64,
                    "2026-11-04T00:00:00+00:00",
                    "UNQUALIFIED",
                ),
            )
        for invented in (
            "SCIENTIFICALLY_QUALIFIED",
            "QUALIFIED",
            "TRADING_AUTHORIZED",
            "APPROVE",
            "",
            "qualified",
            "PASS",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="SIGNOFF_NOT_IMPLEMENTED"):
                with con:
                    con.execute(
                        "INSERT INTO qualification_decisions VALUES(?,?,?,?,?,?)",
                        (
                            f"synthetic-{invented}",
                            1,
                            "unknown",
                            "b" * 64,
                            "2026-11-04T00:00:00+00:00",
                            invented,
                        ),
                    )
            with pytest.raises(sqlite3.IntegrityError, match="SIGNOFF_NOT_IMPLEMENTED"):
                with con:
                    con.execute(
                        "UPDATE qualification_decisions SET verdict=? WHERE decision_id='negative'",
                        (invented,),
                    )
        assert qual.status(con)["scientifically_qualified"] == "NOT_ESTABLISHED"
        assert qual.status(con)["trading_authorized"] is False
        assert (
            con.execute(
                "SELECT verdict FROM qualification_decisions WHERE decision_id='negative'"
            ).fetchone()[0]
            == "UNQUALIFIED"
        )
    assert registry.db_status(db)["counts"]["scientifically_qualified"] == "NOT_ESTABLISHED"


def test_unsupported_qualification_is_not_inferred_from_research_provenance(
    tmp_path: Path,
) -> None:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "registry.sqlite"
    registry.apply(db, snapshot, "2026-11-04T00:00:00+00:00")
    with closing(registry.connect(db, False)) as con:
        initial = qual.status(con)
        assert initial["recorded_research_blocked_or_negative"] == 0
        assert initial["positive_verdicts_supported"] is False
        assert initial["external_independent_signoff"] == "UNAVAILABLE"
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 6
