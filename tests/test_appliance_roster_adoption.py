"""Observation adoption must preserve identity without manufacturing financial authority."""

from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
import json
import sqlite3

import pytest
from copytrade_kernel import KnownAtTs
from copytrade_pm.roster import RosterStore
from copytrade_pm.roster.observations import import_registry
from copytrade_pm.pm_source_selection import selected_parents

ORIGIN = 1_700_000_000_000
ADOPTED = ORIGIN + 1_000
ADDRESS = "0x" + "a" * 40


def selection(pid="A", *, address=ADDRESS, version=1):
    return {
        "portfolio_id": pid,
        "version": version,
        "definition_sha256": "d" * 64,
        "selection_known_at": datetime.fromtimestamp(ORIGIN / 1000, UTC).isoformat(),
        "selection_known_at_ms": ORIGIN,
        "members": {"leader": address},
        "origin_sha256": "f" * 64,
    }


def legacy_snapshot(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE portfolio_seals(portfolio_id TEXT, version INTEGER,
            definition_sha256 TEXT, selection_known_at TEXT);
        CREATE TABLE portfolio_memberships(portfolio_id TEXT, version INTEGER,
            member_alias TEXT, wallet_id TEXT);
        CREATE TABLE wallets(wallet_id TEXT, address TEXT);
        """)
        value = selection()
        db.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?)",
            ("A", 1, value["definition_sha256"], value["selection_known_at"]),
        )
        db.execute("INSERT INTO portfolio_memberships VALUES('A',1,'leader','w')")
        db.execute("INSERT INTO wallets VALUES('w',?)", (ADDRESS,))
    return sha256(path.read_bytes()).hexdigest()


def test_adoption_keeps_origin_and_store_clocks_and_never_promotes_seats(tmp_path):
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True) as store:
        original = selection()
        pin = store.record_observation_selection(original, recorded_ms=ADOPTED)
        assert store.observation_selection("A", as_of=KnownAtTs(ADOPTED - 1)) is None
        observed = store.observation_selection("A", as_of=KnownAtTs(ADOPTED))
        assert observed is not None
        assert observed["selection_known_at_ms"] == ORIGIN
        assert observed["adopted_at_ms"] == ADOPTED
        assert observed["payload_sha256"] == pin
        assert store.accounts() == ()
        assert store.health()["counts"]["leases"] == 0
        assert store.health()["counts"]["scorecards"] == 0
        assert store.record_observation_selection(original, recorded_ms=ADOPTED + 1) == pin
        assert store.observation_selection("A", as_of=KnownAtTs(ADOPTED)) == observed
    assert selected_parents(
        path, portfolios=("A",), as_of=datetime.fromtimestamp(ADOPTED / 1000, UTC).isoformat()
    ) == {"leader": ADDRESS}
    with pytest.raises(ValueError):
        selected_parents(
            path, portfolios=("A",), as_of=datetime.fromtimestamp(ORIGIN / 1000, UTC).isoformat()
        )


def test_batch_drift_rolls_back_even_when_the_conflict_was_adopted_later(tmp_path):
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True) as store:
        store.record_observation_selection(selection(), recorded_ms=ADOPTED + 10)
        with pytest.raises(ValueError, match="DRIFT"):
            store.record_observation_selections(
                [selection("B"), selection(address="0x" + "b" * 40)], recorded_ms=ADOPTED
            )
        assert store.observation_portfolios() == ("A",)
        with pytest.raises(ValueError, match="CLOCK"):
            store.record_observation_selection(selection("B"), recorded_ms=ORIGIN - 1)


def test_import_is_explicit_pinned_idempotent_and_read_only_by_default(tmp_path):
    source, target = tmp_path / "legacy.sqlite", tmp_path / "roster.sqlite"
    pin = legacy_snapshot(source)
    before = source.read_bytes()
    report = import_registry(source, pin, target, at_ms=ADOPTED, apply=False)
    assert report["state"] == "DRY_RUN" and report["seat_promotions"] == 0
    assert not target.exists()
    with pytest.raises(ValueError, match="PIN"):
        import_registry(source, "0" * 64, target, at_ms=ADOPTED, apply=True)
    assert not target.exists()
    import_registry(source, pin, target, at_ms=ADOPTED, apply=True)
    import_registry(source, pin, target, at_ms=ADOPTED + 1, apply=True)
    assert source.read_bytes() == before
    with RosterStore(target) as store:
        assert store.health()["counts"]["observation_selections"] == 1
        adopted = store.observation_selection("A", as_of=KnownAtTs(ADOPTED))
        assert adopted is not None and adopted["origin_sha256"] == pin


def test_schema_one_migrates_without_rewriting_existing_books_and_unknown_is_rejected(tmp_path):
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True):
        pass
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DROP TABLE observation_selections")
        db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    with RosterStore(path, create=True) as store:
        assert store.health()["database_integrity"] == "VERIFIED"
        store.record_observation_selection(selection(), recorded_ms=ADOPTED)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="SCHEMA"):
        RosterStore(path, create=True)
    assert path.read_bytes() == before


def test_adopted_membership_is_immutable_and_tamper_detected(tmp_path):
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True) as store:
        store.record_observation_selection(selection(), recorded_ms=ADOPTED)
    with closing(sqlite3.connect(path)) as db, db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM observation_selections")
        trigger = db.execute(
            "SELECT name FROM sqlite_schema WHERE type='trigger' AND tbl_name='observation_selections' AND sql LIKE '%UPDATE%'"
        ).fetchone()[0]
        db.execute('DROP TRIGGER "' + trigger + '"')
        changed = selection(address="0x" + "b" * 40)
        db.execute("UPDATE observation_selections SET payload=?", (json.dumps(changed),))
    with pytest.raises(ValueError, match="INTEGRITY_FAILED"):
        RosterStore.authority_health(path)
    with RosterStore(path) as store, pytest.raises(ValueError, match="DRIFT"):
        store.observation_selection("A", as_of=KnownAtTs(ADOPTED))


def test_incomplete_legacy_selection_is_reported_and_never_partially_adopted(tmp_path):
    source, target = tmp_path / "legacy.sqlite", tmp_path / "roster.sqlite"
    legacy_snapshot(source)
    with closing(sqlite3.connect(source)) as db, db:
        row = selection("B")
        db.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?)",
            ("B", 1, row["definition_sha256"], row["selection_known_at"]),
        )
        db.execute("INSERT INTO portfolio_memberships VALUES('B',1,'known','w')")
        db.execute("INSERT INTO portfolio_memberships VALUES('B',1,'unresolved',NULL)")
    pin = sha256(source.read_bytes()).hexdigest()
    report = import_registry(source, pin, target, at_ms=ADOPTED, apply=True)
    assert report["selections"] == 1
    assert report["quarantined"] == [
        {
            "portfolio_id": "B",
            "version": 1,
            "reason": "UNRESOLVED_MEMBERSHIP",
            "unresolved_aliases": ["unresolved"],
        }
    ]
    with RosterStore(target) as store:
        assert store.observation_portfolios() == ("A",)
        assert store.observation_selection("B", as_of=KnownAtTs(ADOPTED)) is None
    with pytest.raises(ValueError):
        selected_parents(
            target, portfolios=("B",), as_of=datetime.fromtimestamp(ADOPTED / 1000, UTC).isoformat()
        )
