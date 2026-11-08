"""Shared Vike 1m collector is read-only and fails closed on missing markets."""

from datetime import UTC, datetime

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_vike_minute_collector import collect_once, parse_markets


T = datetime(2026, 11, 7, 12, 0, 30, tzinfo=UTC)


def candle(*, dex="HL", symbol="BTC"):
    return {
        "ts": int(T.replace(second=0).timestamp() * 1000),
        "dex": dex,
        "symbol": symbol,
        "kind": "perp",
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 20,
        "volume_usd": 2020,
        "n_trades": 5,
    }


def test_one_shared_price_journal_records_native_hip3_without_faking_orderbook(tmp_path):
    prices = PaperJournal(tmp_path / "shared-price")
    doc = {
        "market": "perp",
        "interval": "1m",
        "candles": [candle(), candle(dex="xyz", symbol="BRENTOIL")],
    }
    wanted = parse_markets("BTC,xyz:BRENTOIL")
    first = collect_once(prices, doc=doc, received_at=T.isoformat(), markets=wanted)
    assert first["status"] == "OBSERVED_PRICES_ONLY"
    assert first["recorded"] == 2
    second = collect_once(prices, doc=doc, received_at=T.isoformat(), markets=wanted)
    assert second["duplicates"] == 2
    with prices._writer() as db:
        assert db.execute("SELECT count(*) FROM vike_minute_receipts").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM market_quote_receipts").fetchone()[0] == 0


def test_missing_selected_market_is_explicit_and_never_backfilled(tmp_path):
    prices = PaperJournal(tmp_path / "shared-price")
    result = collect_once(
        prices,
        doc={"market": "perp", "interval": "1m", "candles": [candle()]},
        received_at=T.isoformat(),
        markets=parse_markets("BTC,ETH"),
    )
    assert result["status"] == "BLOCKED_INCOMPLETE_MARKET_SCOPE"
    assert result["missing_native_markets"] == ["ETH"]
    assert result["market_availability"]["ETH"] == {
        "price_status": "MISSING_PROVIDER_ROW",
        "propr_orderability": "UNKNOWN",
        "execution_liquidity_verified": False,
    }
    assert result["market_availability"]["BTC"]["price_status"] == "ESTIMATED_TRADE_PRICE"
    assert result["broker_executed"] is False


def test_selected_native_identity_cannot_be_duplicated_or_collapsed():
    with pytest.raises(ValueError, match="DUPLICATE"):
        parse_markets("BTC,BTC")
    assert parse_markets("BTC,xyz:BTC") == frozenset({"BTC", "xyz:BTC"})
