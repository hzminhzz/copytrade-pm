"""Bi-temporal ``bars_1m`` venue market-volume proofs for :class:`FactStore`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from copytrade_pm.facts import BARS_1M_COLUMNS, manifest as mf  # noqa: E402
from copytrade_pm.facts.ingest import FactIngestor  # noqa: E402
from copytrade_pm.facts.schemas import MONEY_COLUMNS, ProvenanceTier, schema_sha  # noqa: E402
from copytrade_pm.facts.store import FactStore, FactStoreError  # noqa: E402

DAY_ONE = "2026-05-01"
SOURCE = "hyperliquid_candles_1m"
FETCH_MS = int(datetime(2026, 5, 1, 0, 5, tzinfo=UTC).timestamp() * 1000)
W1 = "0x" + "a" * 40


def minute_ms(day: str = DAY_ONE, minutes: int = 0, extra_ms: int = 0) -> int:
    base = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return int(base.timestamp() * 1000) + minutes * 60_000 + extra_ms


def bar_row(
    *,
    venue: str = "hyperliquid",
    coin: str = "BTC",
    day: str = DAY_ONE,
    minutes: int = 0,
    extra_ms: int = 0,
    open_: str = "100000.25",
    high: str = "100120.50",
    low: str = "99980.00",
    close: str = "100050.75",
    volume: str = "12.345678901234",
    quote_volume_usd: str = "1235200.5",
    first_known_at_ms: int | None = FETCH_MS,
) -> dict:
    ts = minute_ms(day, minutes, extra_ms)
    return {
        "venue": venue,
        "coin": coin,
        "open": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": Decimal(volume),
        "quote_volume_usd": Decimal(quote_volume_usd),
        "bar_ts": datetime.fromtimestamp(ts / 1000, UTC),
        "event_ts_ms": ts,
        "first_known_at_ms": first_known_at_ms,
        "known_at_basis": "partition_fetch_clock" if first_known_at_ms is not None else None,
        "arrival_seq": 0,
        "source_id": SOURCE,
        "source_rank": 1,
        "batch_sha16": "",
    }


def equity_row(*, day: str = DAY_ONE, first_known_at_ms: int | None = FETCH_MS) -> dict:
    ts = minute_ms(day, 0)
    return {
        "wallet": W1,
        "account_scope": "HL_MAIN_PERP_ONLY",
        "abstraction_mode": "default",
        "equity_usd": Decimal("1000"),
        "withdrawable_usd": Decimal("500"),
        "margin_used_usd": Decimal("100"),
        "observed_at": datetime.fromtimestamp(ts / 1000, UTC),
        "event_ts_ms": ts,
        "first_known_at_ms": first_known_at_ms,
        "known_at_basis": "partition_fetch_clock" if first_known_at_ms is not None else None,
        "arrival_seq": 0,
        "source_id": "official_hyperliquid_info",
        "source_rank": 1,
        "batch_sha16": "",
    }


@pytest.fixture()
def store(tmp_path: Path):
    handle = FactStore(tmp_path / "facts", create=True)
    yield handle
    handle.close()


def ingest_bars(store: FactStore, rows: list[dict], **kwargs):
    return FactIngestor(store).ingest_rows(
        "bars_1m",
        rows,
        source_id=kwargs.pop("source_id", SOURCE),
        source_rank=kwargs.pop("source_rank", 1),
        first_known_at_ms=kwargs.pop("first_known_at_ms", FETCH_MS),
        input_label=kwargs.pop("input_label", "bars-1"),
    )


def test_bars_1m_writes_exact_decimal_38_12_and_normalises_identity(store):
    assert len(BARS_1M_COLUMNS) == 16
    receipt = ingest_bars(store, [bar_row(venue="  HyperLiquid ", coin=" btc ")])[0]
    assert receipt.created is True
    assert receipt.rows_written == 1

    parquet_schema = pl.scan_parquet(receipt.path).collect_schema()
    for col in MONEY_COLUMNS["bars_1m"]:
        assert parquet_schema[col] == pl.Decimal(38, 12)

    frame = store.scan("bars_1m", as_of_ms=FETCH_MS).collect()
    assert frame.height == 1
    assert frame["venue"][0] == "hyperliquid"
    assert frame["coin"][0] == "BTC"
    assert frame["volume"][0] == Decimal("12.345678901234")
    assert frame["quote_volume_usd"][0] == Decimal("1235200.500000000000")
    assert store.verify()["ok"] is True


def test_bars_1m_dedupes_by_venue_coin_ts_and_keeps_earliest_clock(store):
    first = ingest_bars(store, [bar_row(minutes=0, first_known_at_ms=FETCH_MS)])[0]
    later = ingest_bars(
        store,
        [
            bar_row(minutes=0, first_known_at_ms=FETCH_MS + 60_000),
            bar_row(minutes=1, first_known_at_ms=FETCH_MS + 60_000),
        ],
        first_known_at_ms=FETCH_MS + 60_000,
        input_label="bars-2",
    )[0]
    assert later.rows_written == 2
    assert later.rows_preserved == 1
    assert later.rows_duplicate == 1

    repeat = ingest_bars(
        store,
        [bar_row(minutes=0, first_known_at_ms=FETCH_MS + 120_000)],
        first_known_at_ms=FETCH_MS + 120_000,
        input_label="bars-3",
    )[0]
    assert repeat.created is False
    assert repeat.batch_sha16 == later.batch_sha16
    assert first.batch_sha16 != later.batch_sha16

    frame = store.scan("bars_1m", as_of_ms=FETCH_MS + 60_000).collect()
    bar0 = frame.filter(pl.col("event_ts_ms") == minute_ms(DAY_ONE, 0))
    assert bar0["first_known_at_ms"][0] == FETCH_MS
    assert store.verify()["ok"] is True


def test_bars_1m_conflicting_payload_fails_closed(store):
    ingest_bars(store, [bar_row(close="100050.75")])
    with pytest.raises(FactStoreError, match="INGEST_CONFLICTING_VALUES"):
        ingest_bars(store, [bar_row(close="100099.00")], input_label="bars-conflict")
    assert store.scan("bars_1m", as_of_ms=FETCH_MS).collect().height == 1


def test_bars_1m_validation_rejects_off_grid_negative_volume_and_empty_identity(store):
    with pytest.raises(FactStoreError, match="BARS_1M_NOT_ON_MINUTE_GRID"):
        ingest_bars(store, [bar_row(extra_ms=1000)])

    with pytest.raises(FactStoreError, match="BARS_1M_NEGATIVE_VOLUME"):
        ingest_bars(store, [bar_row(volume="-0.01")])

    with pytest.raises(FactStoreError, match="BARS_1M_NEGATIVE_VOLUME"):
        ingest_bars(store, [bar_row(quote_volume_usd="-1")])

    with pytest.raises(FactStoreError, match="INGEST_EMPTY_IDENTITY:bars_1m"):
        ingest_bars(store, [bar_row(venue="   ")])

    with pytest.raises(FactStoreError, match="INGEST_EMPTY_IDENTITY:bars_1m"):
        ingest_bars(store, [bar_row(coin="")])


def test_bitemporal_causality_violation_fails_closed(store):
    bar_ts = minute_ms(DAY_ONE, 10)
    with pytest.raises(FactStoreError, match="BITEMPORAL_CAUSALITY_VIOLATION:bars_1m"):
        ingest_bars(
            store,
            [bar_row(minutes=10, first_known_at_ms=bar_ts - 1)],
            first_known_at_ms=bar_ts - 1,
        )

    eq_ts = minute_ms(DAY_ONE, 0)
    with pytest.raises(FactStoreError, match="BITEMPORAL_CAUSALITY_VIOLATION:equity"):
        FactIngestor(store).ingest_rows(
            "equity",
            [equity_row(first_known_at_ms=eq_ts - 1)],
            source_id="official_hyperliquid_info",
            source_rank=1,
            first_known_at_ms=eq_ts - 1,
        )

    ok_receipt = ingest_bars(
        store,
        [bar_row(minutes=10, first_known_at_ms=bar_ts)],
        first_known_at_ms=bar_ts,
    )[0]
    assert ok_receipt.rows_written == 1


def test_bars_1m_pit_as_of_and_allow_unknown_known_at(store):
    t1 = minute_ms(DAY_ONE, 1)
    t2 = minute_ms(DAY_ONE, 2)
    ingest_bars(
        store,
        [
            bar_row(minutes=0, first_known_at_ms=t1),
            bar_row(minutes=1, first_known_at_ms=t2),
        ],
        first_known_at_ms=t1,
    )
    ingest_bars(
        store,
        [bar_row(minutes=2, first_known_at_ms=None)],
        first_known_at_ms=None,
        input_label="bars-retro",
    )

    assert store.scan("bars_1m", as_of_ms=t1).collect().height == 1
    assert store.scan("bars_1m", as_of_ms=t2).collect().height == 2
    assert store.scan("bars_1m", as_of_ms=t2, allow_unknown_known_at=True).collect().height == 3
    assert store.scan("bars_1m", tiers=(ProvenanceTier.RETROSPECTIVE,)).collect().height == 1


def test_scan_coins_and_wallets_column_guards_fail_closed_even_when_empty(store):
    with pytest.raises(FactStoreError, match="KIND_HAS_NO_WALLET_COLUMN:bars_1m"):
        store.scan("bars_1m", wallets=W1)
    with pytest.raises(FactStoreError, match="KIND_HAS_NO_COIN_COLUMN:equity"):
        store.scan("equity", coins="BTC")

    ingest_bars(
        store,
        [
            bar_row(coin="BTC", minutes=0),
            bar_row(coin="ETH", minutes=0),
            bar_row(coin="SOL", minutes=0),
        ],
    )
    with pytest.raises(FactStoreError, match="KIND_HAS_NO_WALLET_COLUMN:bars_1m"):
        store.scan("bars_1m", wallets=[W1])

    btc = store.scan("bars_1m", coins=" btc ").collect()
    assert btc["coin"].to_list() == ["BTC"]
    pair = store.scan("bars_1m", coins=["eth", "SOL"]).collect()
    assert sorted(pair["coin"].to_list()) == ["ETH", "SOL"]


def test_distinct_wallets_skips_bars_1m_cleanly(store):
    ingest_bars(store, [bar_row(coin="BTC")])
    FactIngestor(store).ingest_rows(
        "equity",
        [equity_row()],
        source_id="official_hyperliquid_info",
        source_rank=1,
        first_known_at_ms=FETCH_MS,
    )
    assert store.distinct_wallets(("bars_1m",)) == ()
    assert store.distinct_wallets(("bars_1m", "equity")) == (W1,)


def test_preexisting_store_without_bars_1m_dataset_can_ingest(tmp_path: Path):
    root = tmp_path / "legacy_facts"
    with FactStore(root, create=True) as created:
        con = created.connect()
        with con:
            con.execute("DELETE FROM datasets WHERE kind = 'bars_1m'")
        assert mf.dataset_schema_sha(con, "bars_1m") is None

    with FactStore(root, create=False) as reopened:
        receipt = ingest_bars(reopened, [bar_row()])[0]
        assert receipt.created is True
        assert mf.dataset_schema_sha(reopened.connect(), "bars_1m") == schema_sha("bars_1m")
        assert reopened.verify()["ok"] is True
