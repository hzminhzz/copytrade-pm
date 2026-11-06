"""An unsigned newest research selection is a provenance gate, not a corrupt SQLite DB."""

from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_catalog as catalog
from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_continuous import (
    SubscriptionBudget,
    candidate_preflight,
    diagnose_candidate_preflight,
)
from test_wallet_registry_catalog import _v2_snapshot, AFTER, WHALE


@pytest.fixture(autouse=True)
def pin_fixture_whale(monkeypatch):
    monkeypatch.setattr(catalog, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())


def _registry_with_unsigned_latest(tmp_path):
    db, snapshot = _v2_snapshot(tmp_path)
    registry.apply(db, snapshot, AFTER)
    with closing(registry.connect(db, True)) as conn, conn:
        conn.execute(
            "INSERT INTO research_selections "
            "(source_sha256,scope,portfolio_id,portfolio_version,role,priority,known_at) "
            "SELECT ?,scope,portfolio_id,portfolio_version,role,priority,? "
            "FROM research_selections WHERE portfolio_id='P1' LIMIT 1",
            ("f" * 64, datetime.now(UTC).isoformat()),
        )
    return db


def test_unsigned_latest_not_misdiagnosed_as_sqlite_corruption(tmp_path, capsys):
    db = _registry_with_unsigned_latest(tmp_path)
    assert registry.db_authority_health(db)["database_integrity"] == "VERIFIED"
    indexed = registry.db_status(db)
    assert indexed["counts"]["current_research_selection"] == "UNVERIFIED_SELECTION_PROVENANCE"
    assert indexed["counts"]["current_research_portfolios"] == 0

    assert registry.cli(["--db", str(db), "doctor"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["database_integrity"] == "VERIFIED"
    assert output["research_selection_integrity"] == "BLOCKED_MISSING_EXTERNAL_PROOF"
    assert output["trading_authorized"] is False
    assert registry.cli(["--db", str(db), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["current_research_portfolios"] == 0

    with closing(registry.connect(db, False)) as conn:
        with pytest.raises(ValueError, match="unverified research selection provenance"):
            catalog.list_selection(conn, datetime.now(UTC).isoformat())
        assert conn.execute("SELECT COUNT(*) FROM research_selection_proofs").fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None


def test_unrelated_unsigned_selection_does_not_block_verified_observer(tmp_path, monkeypatch):
    import copytrade_pm.pm_forward_continuous as observer

    db = _registry_with_unsigned_latest(tmp_path)
    # The catalog fixture has no private address resolution. Isolate its
    # independent watchlist dependency while checking real SQLite seals.
    monkeypatch.setattr(observer, "registry_watched_addresses", lambda *a, **kw: {"wallet": "P1"})
    state = tmp_path / "new_observer"
    options = dict(
        registry_db=db,
        state_root=state,
        instruments=(Instrument("hyperliquid", "mainnet:perp:default", "BTC"),),
        revision="a" * 40,
        as_of=datetime.now(UTC).isoformat(),
        budget=SubscriptionBudget(),
        portfolio_ids=("P1",),
    )
    # A valid, independently sealed P1 can still be observed while an
    # unrelated research priority remains unverified and unselectable.
    result = candidate_preflight(**options)
    assert result["status"] == "PREFLIGHT_VERIFIED_OBSERVER_ONLY"
    assert result["order_route"] == "NONE"
    assert result["paper_observed"] is False
    diag = diagnose_candidate_preflight(**options)
    assert diag["status"] == "DIAGNOSTIC_ONLY"
    assert diag["gates"]["registry_integrity"]["status"] == "PASS"
    assert diag["gates"]["signed_selection"]["status"] == "PASS"
    assert diag["gates"]["portfolio_seals"]["status"] == "PASS"
    assert diag["safe_to_start"] is False
    assert not state.exists()


def test_explicit_unverified_selection_stays_quarantined(tmp_path):
    db = _registry_with_unsigned_latest(tmp_path)
    with closing(registry.connect(db, False)) as conn:
        with pytest.raises(ValueError, match="unverified research selection provenance"):
            catalog.list_selection(conn, datetime.now(UTC).isoformat())
    with pytest.raises(ValueError, match="PUBLIC_TRADE_PORTFOLIO_NOT_SEALED_ASOF"):
        candidate_preflight(
            registry_db=db,
            state_root=tmp_path / "unsealed",
            instruments=(Instrument("hyperliquid", "mainnet:perp:default", "BTC"),),
            revision="a" * 40,
            as_of=datetime.now(UTC).isoformat(),
            budget=SubscriptionBudget(),
            portfolio_ids=("regime.macro/TriadA",),
        )
