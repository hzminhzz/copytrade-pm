from contextlib import closing
import sqlite3

import pytest

from copytrade_pm.production_export import export_metadata
from copytrade_pm.roster import RosterStore
from copytrade_pm.roster.sealed import select_sealed_book
from roster_fixture import AT, MS, WALLETS, database as database


def test_fixed_k_export_is_repeatable_readonly_and_scope_gated(tmp_path):
    db = database(tmp_path)
    before = db.read_bytes()
    one = export_metadata(db, "A", AT)
    assert one == export_metadata(db, "A", "2026-11-04T06:00:01+00:00")
    assert one["state"] == "BLOCKED"
    assert one["blockers"] == ["SOURCE_POSITION_SCOPE_ATTESTATION_MISSING"]
    assert one["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY"
    assert not one["trading_authorized"]
    assert db.read_bytes() == before
    assert [m["pod_id"] for m in one["members"]] == ["seat_1", "seat_2", "seat_3"]
    assert [m["source_identity"] for m in one["members"]] == list(WALLETS[:3])
    with RosterStore(db) as store:
        sealed = select_sealed_book(store, "A", MS, require_attestation=False)
        assert sealed.definition_sha256 == one["sealed_definition_sha256"]
        assert not sealed.attested and not sealed.trading_authorized
        assert all(m.account_id == "A" and m.generation == 1 for m in sealed.members)
        assert {m.owner_id for m in sealed.members} == {lease.owner for lease in sealed.book.leases}


def test_future_book_and_unknown_account_fail_closed(tmp_path):
    db = database(tmp_path)
    with pytest.raises(ValueError, match="SELECTION_UNKNOWN_AT_ASOF"):
        export_metadata(db, "A", "2026-11-04T05:59:59.999+00:00")
    with pytest.raises(ValueError, match="SELECTION_UNKNOWN_AT_ASOF"):
        export_metadata(db, "unknown", AT)
    with pytest.raises(ValueError, match="SELECTION_MEMBER_DRIFT"):
        export_metadata(db, "A", AT, version=2)


@pytest.mark.parametrize(
    "table,column", [("books", "book_sha"), ("leases", "payload"), ("leases", "owner")]
)
def test_export_refuses_exact_book_or_lease_drift(tmp_path, table, column):
    db = database(tmp_path)
    with closing(sqlite3.connect(db)) as con, con:
        con.execute(f"DROP TRIGGER {table}_no_update")
        con.execute(f"UPDATE {table} SET {column}=?", ("{}",))
    with pytest.raises(ValueError, match="SELECTION_MEMBER_DRIFT"):
        export_metadata(db, "A", AT)


def test_effective_but_uncommitted_book_is_not_pit_evidence(tmp_path):
    db = database(tmp_path)
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("DROP TRIGGER books_no_update")
        con.execute("UPDATE books SET committed_ms=?", (MS + 1000,))
    with pytest.raises(ValueError, match="SELECTION_UNKNOWN_AT_ASOF"):
        export_metadata(db, "A", AT)
    assert export_metadata(db, "A", "2026-11-04T06:00:01+00:00")["version"] == 1
