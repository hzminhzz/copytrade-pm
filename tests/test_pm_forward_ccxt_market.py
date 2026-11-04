"""Read-only CCXT Pro Hyperliquid market/quote contract tests (no network)."""

from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm_forward_ccxt_market import (
    ReadOnlyCCXTProHyperliquid,
    parse_ccxt_book,
    parse_ccxt_market,
    verify_l2_evidence,
)
from copytrade_pm.pm_forward_market import market_contract_reasons

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
BRENT = Instrument("hyperliquid", "mainnet:perp:xyz", "BRENTOIL")
T = "2026-11-04T04:00:00+00:00"


def at(seconds: int) -> str:
    return (datetime.fromisoformat(T) + timedelta(seconds=seconds)).isoformat()


def stamp(seconds: int) -> int:
    return int(datetime.fromisoformat(at(seconds)).timestamp() * 1000)


def ccxt_market(native="BTC", *, hip3=False) -> dict:
    dex, coin = native.split(":", 1) if ":" in native else (None, native)
    return {
        "symbol": "XYZ-" + coin + "/USDC:USDC" if hip3 else coin + "/USDC:USDC",
        "id": "110044" if hip3 else "0",
        "base": "XYZ-" + coin if hip3 else coin,
        "quote": "USDC",
        "settle": "USDC",
        "swap": True,
        "spot": False,
        "linear": True,
        "contract": True,
        "type": "swap",
        "active": True,
        "precision": {"amount": 0.01 if hip3 else 0.00001, "price": 1.0},
        "limits": {"cost": {"min": 10}},
        "info": {
            "name": native,
            "dex": dex,
            "hip3": hip3,
            "baseId": 110044 if hip3 else 0,
            "szDecimals": 2 if hip3 else 5,
        },
    }


def orderbook(seconds=2, *, bid=100, ask=101) -> dict:
    return {
        "symbol": "BTC/USDC:USDC",
        "timestamp": stamp(seconds),
        "bids": [[bid, 2]],
        "asks": [[ask, 3]],
    }


def costs(*, full_spread="150") -> dict:
    return {
        "fee_bps": "2",
        "full_spread_bps": full_spread,
        "slippage_bps": "1",
        "impact_bps_at_full_participation": "4",
        "max_participation": "0.1",
        "max_age_seconds": 20,
        "latency_seconds": 1,
    }


def fixture():
    market = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    quote = parse_ccxt_book(
        market,
        orderbook(),
        first_known_at=at(3),
        max_age_seconds=20,
    )
    fee = costs()
    contract = quote.contract(costs=fee, as_of=at(4))
    obs = quote.observation()
    return quote, obs, contract, fee


def verify(obs: dict, contract: dict, fee: dict, ev: dict | None, *, quantity="0.2"):
    return market_contract_reasons(
        contract,
        instrument=BTC,
        observed_quality="VERIFIED_QUOTE",
        decision_at=at(4),
        target_quantity=D(quantity),
        costs_sha=digest(fee),
        observation=obs,
        quote_evidence=ev,
        costs=fee,
    )


def test_native_main_mapping_is_not_numeric_id_and_l2_not_trade_volume():
    quote, obs, contract, fee = fixture()
    assert quote.market.instrument == BTC
    assert quote.market.ccxt_id == "0"
    assert quote.market.market_known_at == at(1)
    assert quote.market.amount_step == D("0.00001")
    assert quote.market.minimum_notional == D("10")
    assert quote.mid == D("100.5")
    assert quote.spread_bps > 0
    assert obs["quality"] == "VERIFIED_QUOTE"
    assert obs["volume_base"] is None
    assert quote.payload()["volume_status"] == "UNKNOWN_BOOK_DEPTH_NOT_TRADED_VOLUME"
    assert quote.payload()["provider_signed"] is False
    assert contract["contract_sha"] == digest(
        {k: v for k, v in contract.items() if k != "contract_sha"}
    )
    assert not verify(obs, contract, fee, quote.payload())


def test_hip3_needs_explicit_native_identity_and_closed_session_gate():
    market = parse_ccxt_market(
        ccxt_market("xyz:BRENTOIL", hip3=True),
        first_known_at=at(1),
        expected=BRENT,
    )
    assert market.instrument == BRENT
    assert market.ccxt_id == "110044"
    assert market.session_trust == "UNKNOWN_HIP3_SESSION"
    assert not market.session_eligible
    quote = parse_ccxt_book(
        market,
        {**orderbook(), "symbol": market.ccxt_symbol},
        first_known_at=at(3),
    )
    contract = quote.contract(costs=costs(), as_of=at(4))
    assert contract["session_open"] is False


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"swap": False}, "CCXT_NON_PERP_OR_UNSUPPORTED_COLLATERAL"),
        ({"spot": True}, "CCXT_NON_PERP_OR_UNSUPPORTED_COLLATERAL"),
        ({"settle": "USDH"}, "CCXT_NON_PERP_OR_UNSUPPORTED_COLLATERAL"),
        ({"id": "999"}, "CCXT_MARKET_ASSET_INDEX_MISMATCH"),
        ({"active": None}, "CCXT_MARKET_INACTIVE_OR_UNKNOWN"),
        ({"precision": {"amount": 0.01}}, "CCXT_AMOUNT_STEP_CONFLICT"),
        ({"limits": {"cost": {"min": None}}}, "CCXT_MIN_NOTIONAL_UNKNOWN"),
    ],
)
def test_metadata_fails_closed_without_native_contract(change, reason):
    market = {**ccxt_market(), **change}
    with pytest.raises(ValueError, match=reason):
        parse_ccxt_market(market, first_known_at=at(1), expected=BTC)


def test_identity_mismatch_and_hip3_spoof_rejected():
    with pytest.raises(ValueError, match="CCXT_NATIVE_MARKET_ID_MISMATCH"):
        parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BRENT)
    spoof = ccxt_market("xyz:BRENTOIL", hip3=True)
    spoof["info"] = {**spoof["info"], "dex": "abc"}
    with pytest.raises(ValueError, match="CCXT_HIP3_IDENTITY_UNATTESTED"):
        parse_ccxt_market(spoof, first_known_at=at(1), expected=BRENT)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"timestamp": None}, "CCXT_BOOK_EVENT_CLOCK_MISSING"),
        ({"timestamp": stamp(50)}, "CCXT_BOOK_FUTURE_OR_STALE"),
        ({"timestamp": stamp(-100)}, "CCXT_BOOK_FUTURE_OR_STALE"),
        ({"bids": []}, "CCXT_BOOK_TWO_SIDED_REQUIRED"),
        ({"asks": []}, "CCXT_BOOK_TWO_SIDED_REQUIRED"),
        ({"bids": [[105, 1]]}, "CCXT_BOOK_LOCKED_OR_CROSSED"),
        ({"bids": [[0, 1]]}, "CCXT_BID_INVALID"),
        ({"symbol": "ETH/USDC:USDC"}, "CCXT_BOOK_SYMBOL_MISMATCH"),
    ],
)
def test_stale_missing_crossed_and_spoofed_books_rejected(mutation, reason):
    market = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    book = {**orderbook(), **mutation}
    with pytest.raises(ValueError, match=reason):
        parse_ccxt_book(market, book, first_known_at=at(3), max_age_seconds=20)


def test_missing_quote_evidence_and_forged_capacity_rejected():
    quote, obs, contract, fee = fixture()
    assert "MARKET_CCXT_L2_EVIDENCE_MISSING" in verify(obs, contract, fee, None)
    fake = {**obs, "volume_base": "5"}
    assert "MARKET_CCXT_L2_CAPACITY_NOT_PROVEN" in verify(fake, contract, fee, quote.payload())
    wrong = {**obs, "mark": "101"}
    assert "MARKET_CCXT_L2_MARK_BINDING_MISMATCH" in verify(wrong, contract, fee, quote.payload())
    bad_evidence = {**quote.payload(), "bid_size": "7"}
    errors = verify(obs, contract, fee, bad_evidence)
    assert "MARKET_CCXT_L2_SHA_BINDING_MISMATCH" in errors
    assert "MARKET_CCXT_L2_BOOK_HASH_MISMATCH" in errors


def test_min_notional_cost_and_stale_quote_enforced():
    quote, obs, contract, fee = fixture()
    assert "MARKET_NATIVE_MIN_NOTIONAL_VIOLATION" in verify(
        obs, contract, fee, quote.payload(), quantity="0.01"
    )
    underpriced = costs(full_spread="10")
    underpriced_contract = quote.contract(costs=underpriced, as_of=at(4))
    assert "MARKET_COST_UNDERESTIMATES_OBSERVED_SPREAD" in verify(
        obs, underpriced_contract, underpriced, quote.payload()
    )
    stale_obs = {**obs}
    assert "MARKET_CCXT_L2_STALE_AT_DECISION" in verify_l2_evidence(
        quote.payload(), contract, stale_obs, decision_at=at(50)
    )


class FakeCCXTClient:
    def __init__(self, config: dict, *, include_brent=True):
        self.config = config
        self.has = {"watchOrderBook": True}
        self.closed = False
        self.calls: list[tuple] = []
        self.books: list[dict | Exception] = [orderbook(), orderbook()]
        self.markets = {"BTC/USDC:USDC": ccxt_market()}
        if include_brent:
            self.markets["XYZ-BRENTOIL/USDC:USDC"] = ccxt_market("xyz:BRENTOIL", hip3=True)

    async def load_markets(self):
        self.calls.append(("load_markets",))
        return self.markets

    async def watch_order_book(self, symbol, limit):
        self.calls.append(("watch_order_book", symbol, limit))
        item = self.books.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True


def test_feed_reconnect_rebaseline_and_no_private_calls():
    import asyncio

    async def run():
        calls = []
        times = iter([at(1), at(3), at(4)])
        client = FakeCCXTClient({})
        feed = ReadOnlyCCXTProHyperliquid(
            (BTC,),
            factory=lambda config: (calls.append(config), client)[1],
            now=lambda: next(times),
        )
        state = await feed.open()
        assert state["metadata_loaded"] is True
        assert state["connected"] is False
        assert calls[0]["enableRateLimit"] is True
        assert "apiKey" not in calls[0]
        assert "secret" not in calls[0]
        first = await feed.quote(BTC)
        assert first.market.instrument == BTC
        assert feed.status()["connected"] is True
        with pytest.raises(ValueError, match="CCXT_BOOK_DUPLICATE_NOT_NEW_EVIDENCE"):
            await feed.quote(BTC)
        assert feed.status()["connected"] is False
        assert feed.status()["quarantined"] == [BTC.key]
        with pytest.raises(ValueError, match="CCXT_MARKET_QUARANTINED_REBASELINE_REQUIRED"):
            await feed.quote(BTC)
        await feed.close()
        assert client.closed
        assert client.calls == [
            ("load_markets",),
            ("watch_order_book", "BTC/USDC:USDC", 5),
            ("watch_order_book", "BTC/USDC:USDC", 5),
        ]
        new_client = FakeCCXTClient({})
        restarted = ReadOnlyCCXTProHyperliquid(
            (BTC,), factory=lambda config: new_client, now=lambda: at(3)
        )
        async with restarted as active:
            assert (await active.quote(BTC)).quote_sha
        assert new_client.closed

    asyncio.run(run())


def test_hip3_discovery_required_and_missing_asset_quarantined():
    import asyncio

    with pytest.raises(ValueError, match="CCXT_HIP3_DEX_EXPLICIT_DISCOVERY_REQUIRED"):
        ReadOnlyCCXTProHyperliquid((BRENT,))

    async def run():
        client = FakeCCXTClient({}, include_brent=False)
        feed = ReadOnlyCCXTProHyperliquid(
            (BTC, BRENT),
            hip3_dexes=("xyz",),
            now=lambda: at(1),
            factory=lambda config: client,
        )
        state = await feed.open()
        assert state["blocked"][BRENT.key] == "CCXT_NATIVE_MARKET_NOT_UNIQUELY_DISCOVERED"
        assert state["catalogued"] == [BTC.key]
        with pytest.raises(ValueError, match="CCXT_NATIVE_MARKET_UNAVAILABLE"):
            await feed.quote(BRENT)
        await feed.close()
        assert client.closed

    asyncio.run(run())


def test_provider_error_quarantines_without_creating_fake_quote():
    import asyncio

    async def run():
        client = FakeCCXTClient({})
        client.books = [TimeoutError("websocket feed lost")]
        times = iter([at(1), at(3)])
        feed = ReadOnlyCCXTProHyperliquid(
            (BTC,), now=lambda: next(times), factory=lambda config: client
        )
        await feed.open()
        with pytest.raises(TimeoutError, match="websocket feed lost"):
            await feed.quote(BTC)
        assert feed.status()["quarantined"] == [BTC.key]
        assert not feed.status()["connected"]
        await feed.close()

    asyncio.run(run())
