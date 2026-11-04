"""Read-only source+market+registry readiness must never silently trade partial NAV."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_readiness import audit_live_paper_readiness
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import WALLET, sample_state
from test_pm_forward_ccxt_market import BTC, at, ccxt_market, orderbook
from test_pm_forward_registry_identity import prepare
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market


def _setup(tmp_path):
    registry, primary, secondary = prepare(tmp_path)
    source = PaperJournal(tmp_path / "source")
    market = PaperJournal(tmp_path / "market")
    book = read_public_all_dex_scope(
        alias="S035",
        address=WALLET,
        frame={"channel": "allDexsClearinghouseState", "data": sample_state()},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)).isoformat(),
    )
    append_public_scope(source, alias="S035", seq=1, receipt=book)
    # Market may be available even while wallet has no combined collateral.
    native = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    observed = parse_ccxt_book(native, orderbook(seconds=2), first_known_at=at(3)).payload()
    market.append_market_quote(observed)
    return registry, primary, secondary, source, market


def audit(roots, portfolio):
    registry, primary, secondary, source, market = roots
    return audit_live_paper_readiness(
        registry_db=registry,
        primary_dir=primary,
        secondary_dir=secondary,
        source_db=source.path,
        market_db=market.path,
        portfolio_id=portfolio,
        as_of="2026-11-04T04:00:10+00:00",
    )


def test_all_approved_portfolios_stay_blocked_on_partial_source_and_registry(tmp_path):
    roots = _setup(tmp_path)
    registry, _, _, source, market = roots
    registry_before = registry.read_bytes()
    source_before = source.path.read_bytes()
    market_before = market.path.read_bytes()
    p1 = audit(roots, "P1")
    p14 = audit(roots, "P14")
    assert p1["status"] == p14["status"] == "BLOCKED_NO_TRADE"
    assert len(p1["registry"]["unresolved_aliases"]) == 3
    assert len(p14["registry"]["unresolved_aliases"]) == 5
    assert p1["source"][0]["admitted"] is False
    assert p1["source_wallet_equity_attested"] is False
    assert p1["trade_volume_complete"] is False
    assert p1["order_route"] == "NONE"
    assert "INDEPENDENT_PARENT_SUBACCOUNT_NAV_NOT_RECONCILED" in p1["reason_codes"]
    assert "UNSEALED_FROZEN_MEMBER_WALLET_IDS" in p14["reason_codes"]
    assert "MISSING_FOLLOWER_MARKET_QUOTE" in p1["reason_codes"]
    assert len(p1["market"]) > 0
    assert registry.read_bytes() == registry_before
    assert source.path.read_bytes() == source_before
    assert market.path.read_bytes() == market_before
    assert "0x" not in json.dumps(p1["source"])


def test_readiness_raises_on_tampered_source_chain(tmp_path):
    roots = _setup(tmp_path)
    source = roots[3]
    with closing(sqlite3.connect(source.path)) as db:
        with db:
            db.execute(
                "UPDATE source_receipts SET chain_sha=? WHERE source_id='S035' AND seq=1",
                ("a" * 64,),
            )
    with pytest.raises(ValueError, match="PAPER_SOURCE_READONLY_TAPE_DIVERGENCE"):
        audit(roots, "P1")
