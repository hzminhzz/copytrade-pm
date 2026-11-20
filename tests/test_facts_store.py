"""Slice 2 proofs for the unified bi-temporal :class:`FactStore`.

Every fixture here is synthetic: wallets are ``0x`` + a repeated nibble, coins
are invented, and no private store, catalog, registry or journal is opened.

The suite proves the four claims the migration depends on:

1. ``Decimal(38, 12)`` is the only money representation written.
2. A day batch is immutable and content-addressed, so re-running is a no-op.
3. Point-in-time reads cannot see a row before its recorded clock, and a row
   without a recorded clock is invisible rather than guessed.
4. All five named sources reconcile row-for-row, including overlaps, with a
   stable receipt SHA across runs.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from copytrade_pm import pm_facts_cli  # noqa: E402
from copytrade_pm.facts import manifest as mf  # noqa: E402
from copytrade_pm.facts.bench import SyntheticPlan, build_synthetic_store, run_benchmark  # noqa: E402
from copytrade_pm.facts.migrate import Migration, new_receipt  # noqa: E402
from copytrade_pm.facts.repair import FillLink, repair_same_ms_order  # noqa: E402
from copytrade_pm.facts.schemas import (  # noqa: E402
    SCHEMA_VERSION,
    ProvenanceTier,
    schema_for,
)
from copytrade_pm.facts.sources import (  # noqa: E402
    RESERVOIR_FULL_HISTORY,
    RESERVOIR_LIQUID12_DISCOVERY,
    RESERVOIR_MONITORED_PLUS_SIX,
    RESERVOIR_ROSTER_DAILY,
    SOURCE_CATALOGUE,
    WALLET_STORE_SOURCE,
    build_catalogue,
)
from copytrade_pm.facts.store import FactStore, FactStoreError, PreparedDay  # noqa: E402

DAY_ONE = "2026-05-01"
DAY_TWO = "2026-05-02"
DAY_THREE = "2026-05-03"
W1 = "0x" + "1" * 40
W2 = "0x" + "2" * 40
W3 = "0x" + "3" * 40
FETCH_CLOCK = "2026-11-01T00:00:00+00:00"


def utc(day: str, seconds: int = 0) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(seconds=seconds)


def epoch_ms(day: str, seconds: int = 0) -> int:
    return int(utc(day, seconds).timestamp() * 1000)


def write_reservoir_day(root: Path, day: str, rows: list[dict]) -> Path:
    path = root / "hyperliquid" / "fills" / f"day={day}" / "data.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
    return path


def reservoir_row(
    wallet: str,
    day: str,
    trade_id: str,
    seconds: int,
    size: float,
    start_position: float,
    *,
    side: str = "buy",
    coin: str = "BTC",
) -> dict:
    return {
        "wallet": wallet,
        "exchange_ts": utc(day, seconds),
        "coin": coin,
        "dex": "hyperliquid",
        "side": side,
        "size": size,
        "start_position": start_position,
        "trade_id": trade_id,
    }


def write_wallet_store_fills(root: Path, wallet: str, day: str, rows: list[dict]) -> Path:
    year, month, dom = day.split("-")
    path = root / "fills" / f"wallet={wallet}" / f"year={year}" / f"month={month}" / f"day={dom}"
    path.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "ts": [row["ts"] for row in rows],
            "wallet": [wallet] * len(rows),
            "symbol": [row.get("symbol", "BTC") for row in rows],
            "dex": [row.get("dex", "HL") for row in rows],
            "side": [row.get("side", "sell") for row in rows],
            "size_token": [row["size_token"] for row in rows],
            "price": [row.get("price", 100.5) for row in rows],
            "size_usd": [row.get("size_usd", 25.125) for row in rows],
            "fee": [row.get("fee", 0.01) for row in rows],
            "fee_token": ["USDC"] * len(rows),
            "is_maker": [False] * len(rows),
            "order_id": [row.get("order_id", "o1") for row in rows],
            "trade_id": [row["trade_id"] for row in rows],
            "crossed": [False] * len(rows),
            "closed_pnl": [row.get("closed_pnl", 0.0) for row in rows],
            "start_position": [row.get("start_position") for row in rows],
            "source": ["vike"] * len(rows),
            "source_ts": [row.get("source_ts", "2026-05-01T00:00:00Z") for row in rows],
        }
    ).write_parquet(path / "data.parquet")
    return path / "data.parquet"


def write_wallet_store_positions(root: Path, wallet: str, day: str) -> Path:
    year, month, dom = day.split("-")
    path = (
        root / "positions" / f"wallet={wallet}" / f"year={year}" / f"month={month}" / f"day={dom}"
    )
    path.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "snapshot_ts": [utc(day, 30)],
            "wallet": [wallet],
            "symbol": ["BTC"],
            "dex": ["HL"],
            "direction": ["long"],
            "size_token": [0.75],
            "size_usd": [75.0],
            "entry_price": [99.0],
            "mark_price": [100.0],
            "liquidation_price": [None],
            "unrealized_pnl": [0.75],
            "leverage": [3.0],
            "leverage_type": ["cross"],
            "margin_used": [25.0],
            "opened_at": [None],
            "pnl_cohort": [None],
            "size_cohort": [None],
            "liq_progress": [None],
            "source": ["vike"],
        }
    ).write_parquet(path / "data.parquet")
    return path / "data.parquet"


def write_legacy_catalog(root: Path, entries: list[tuple[str, str, str, Path]]) -> Path:
    path = root / "catalog.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE partitions(kind TEXT, wallet TEXT, day TEXT, path TEXT, rows INTEGER, "
        "bytes INTEGER, sha256 TEXT, fetched_at TEXT, source TEXT, source_cmd TEXT)"
    )
    for kind, wallet, day, partition in entries:
        con.execute(
            "INSERT INTO partitions VALUES(?,?,?,?,1,1,'x',?,'vike','')",
            (kind, wallet, day, str(partition), FETCH_CLOCK),
        )
    con.commit()
    con.close()
    return path


@pytest.fixture()
def sources(tmp_path: Path) -> dict[str, Path]:
    """Five named sources with deliberate overlap between them."""
    research = tmp_path / "research"
    paths = {
        "wallet_store": tmp_path / "wallet_store",
        RESERVOIR_FULL_HISTORY: research / "reservoir-full-history-20261115",
        RESERVOIR_MONITORED_PLUS_SIX: research / "reservoir-monitored-plus-six",
        RESERVOIR_ROSTER_DAILY: research / "reservoir-roster-daily",
        RESERVOIR_LIQUID12_DISCOVERY: research / "liquid12-discovery-20261117",
    }
    write_reservoir_day(
        paths[RESERVOIR_FULL_HISTORY],
        DAY_ONE,
        [
            reservoir_row(W1, DAY_ONE, "t1", 1, 1.0, 0.0),
            # Inverted same-ms pair. Raw arrival order is t2 (opens at 0) then t3
            # (opens at 1); the only chain-consistent order is t3 then t2.
            reservoir_row(W1, DAY_ONE, "t2", 2, 1.0, 0.0),
            reservoir_row(W1, DAY_ONE, "t3", 2, 1.0, 1.0, side="sell"),
            reservoir_row(W2, DAY_ONE, "u1", 3, 2.0, 0.0),
        ],
    )
    write_reservoir_day(
        paths[RESERVOIR_FULL_HISTORY], DAY_TWO, [reservoir_row(W2, DAY_TWO, "u2", 4, 1.0, 2.0)]
    )
    # monitored overlaps day one: one duplicate trade + one new trade
    write_reservoir_day(
        paths[RESERVOIR_MONITORED_PLUS_SIX],
        DAY_ONE,
        [
            reservoir_row(W1, DAY_ONE, "t1", 1, 1.0, 0.0),
            reservoir_row(W1, DAY_ONE, "t9", 7, 1.0, 1.0),
        ],
    )
    write_reservoir_day(
        paths[RESERVOIR_ROSTER_DAILY], DAY_TWO, [reservoir_row(W1, DAY_TWO, "r1", 5, 0.5, 0.0)]
    )
    # liquid12 publishes a batch directory without day= partitions
    batch = paths[RESERVOIR_LIQUID12_DISCOVERY] / "fills_batch2"
    batch.mkdir(parents=True, exist_ok=True)
    pl.DataFrame([reservoir_row(W2, DAY_ONE, "u1", 3, 2.0, 0.0)]).write_parquet(
        batch / "part-000.parquet"
    )
    # legacy wallet-first partitions, with a recorded fetch clock
    fills = write_wallet_store_fills(
        paths["wallet_store"],
        W1,
        DAY_ONE,
        [{"ts": utc(DAY_ONE, 9), "size_token": 0.25, "trade_id": "w1", "start_position": 1.0}],
    )
    positions = write_wallet_store_positions(paths["wallet_store"], W1, DAY_ONE)
    write_legacy_catalog(
        paths["wallet_store"],
        [("fills", W1, DAY_ONE, fills), ("positions", W1, DAY_ONE, positions)],
    )
    return paths


def catalogue(paths: dict[str, Path]):
    return build_catalogue(
        wallet_store=paths["wallet_store"],
        reservoir={
            "full-history": paths[RESERVOIR_FULL_HISTORY],
            "monitored-plus-six": paths[RESERVOIR_MONITORED_PLUS_SIX],
            "roster-daily": paths[RESERVOIR_ROSTER_DAILY],
            "liquid12-discovery": paths[RESERVOIR_LIQUID12_DISCOVERY],
        },
    )


_OPEN_STORES: list[FactStore] = []


@pytest.fixture(autouse=True)
def _close_stores():
    """Close every store a test opened, so no sqlite handle outlives the test."""
    yield
    while _OPEN_STORES:
        _OPEN_STORES.pop().close()


def open_store(root: Path, *, create: bool = True) -> FactStore:
    store = FactStore(root, create=create)
    _OPEN_STORES.append(store)
    return store


def migrate(paths: dict[str, Path], store_root: Path, *, kinds=("fills", "positions")):
    sources, absent = catalogue(paths)
    assert absent == ()
    store = open_store(store_root)
    receipt = new_receipt(store_root=store_root, sources=sources, not_supplied=absent, kinds=kinds)
    return Migration(store=store, sources=sources, kinds=kinds).run(receipt), store


def canonical_fills(rows: list[dict]):
    """Build a canonical fills frame directly, for store-level unit tests."""
    from copytrade_pm.facts.schemas import column_names

    count = len(rows)
    frame = pl.DataFrame(
        {
            "wallet": [row.get("wallet", W1) for row in rows],
            "coin": [row.get("coin", "BTC") for row in rows],
            "dex": ["hyperliquid"] * count,
            "dex_raw": ["hyperliquid"] * count,
            "provider": [None] * count,
            "side": [row.get("side", "buy") for row in rows],
            "size": [str(row.get("size", "1")) for row in rows],
            "price": [str(row.get("price", "100")) for row in rows],
            "fee": ["0"] * count,
            "fee_token": [None] * count,
            "size_usd": ["100"] * count,
            "start_position": [str(row.get("start_position", "0")) for row in rows],
            "closed_pnl": ["0"] * count,
            "trade_id": [row.get("trade_id") for row in rows],
            "order_id": [None] * count,
            "direction": [None] * count,
            "is_liquidation": [None] * count,
            "is_maker": [None] * count,
            "crossed": [None] * count,
            "exchange_ts": [row["ts"] for row in rows],
            "event_ts_ms": [int(row["ts"].timestamp() * 1000) for row in rows],
            "source_ts": [None] * count,
            "first_known_at_ms": [row.get("first_known_at_ms") for row in rows],
            "known_at_basis": [
                "partition_fetch_clock"
                if row.get("first_known_at_ms") is not None
                else "unrecorded"
                for row in rows
            ],
            "arrival_seq": list(range(count)),
            "source_id": [row.get("source_id", "synthetic") for row in rows],
            "source_rank": [0] * count,
            "batch_sha16": [""] * count,
        }
    )
    money = ("size", "price", "fee", "size_usd", "start_position", "closed_pnl")
    return frame.with_columns(
        [
            pl.col("exchange_ts").cast(pl.Datetime("ms", "UTC")),
            *[pl.col(name).cast(pl.Decimal(38, 12), strict=False) for name in money],
        ]
    ).select(column_names("fills"))


# ---------------------------------------------------------------------------
# Schema and precision
# ---------------------------------------------------------------------------


def test_money_columns_are_decimal_38_12_in_the_written_parquet(tmp_path: Path) -> None:
    store = open_store(tmp_path / "facts")
    store.connect()
    frame = canonical_fills(
        [{"ts": utc(DAY_ONE, 1), "trade_id": "a", "size": "1.5", "price": "0.000000000001"}]
    )
    write = store.write_day(PreparedDay("fills", DAY_ONE, frame, repair_stats=_repair_stats()))
    on_disk = pl.read_parquet(write.path)
    for column in ("size", "price", "start_position"):
        assert on_disk.schema[column] == pl.Decimal(38, 12)
    assert on_disk.schema["exchange_ts"] == pl.Datetime("ms", "UTC")
    assert dict(on_disk.schema) == dict(schema_for("fills"))
    assert mf.get_meta(store.connect(), "schema_version") == SCHEMA_VERSION
    store.close()


def test_sub_scale_values_are_counted_not_silently_zeroed(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    """1e-13 cannot be represented at scale 12; the receipt must say so."""
    batch = sources[RESERVOIR_LIQUID12_DISCOVERY] / "fills_batch2"
    row = reservoir_row(W3, DAY_ONE, "tiny", 11, 1e-13, 0.0, coin="MEME")
    pl.DataFrame([row]).write_parquet(batch / "part-001.parquet")
    receipt, store = migrate(sources, tmp_path / "facts")
    payload = receipt.as_dict()
    assert payload["reconciliation"]["fills"]["rows_quantized_to_zero"] >= 1
    frame = store.scan("fills", wallets=[W3]).collect()
    assert frame.height == 1
    assert frame["size"].to_list() == [Decimal("0E-12")]
    store.close()


def test_decimal_widening_preserves_the_stored_float_value() -> None:
    from copytrade_pm.facts.sources import adapt_reservoir_fills

    frame = pl.DataFrame(
        [
            reservoir_row(W1, DAY_ONE, "f1", 1, 0.1 + 0.2, 0.0),
            reservoir_row(W1, DAY_ONE, "f2", 2, 1e-9, 1.0),
        ]
    )
    result = adapt_reservoir_fills(frame, source_id="synthetic", source_rank=0)
    sizes = result.frame["size"].to_list()
    # 0.1 + 0.2 is stored as the float's shortest repr; no recovery is claimed
    assert sizes[0] == Decimal("0.300000000000")
    # 1e-9 is representable at scale 12 (9 decimal places) and must survive
    assert sizes[1] == Decimal("1e-9")
    assert result.rows_quantized_to_zero == 0


def _repair_stats():
    from copytrade_pm.facts.repair import RepairStats

    return RepairStats()


# ---------------------------------------------------------------------------
# Immutability and idempotence
# ---------------------------------------------------------------------------


def test_write_day_is_content_addressed_and_never_rewritten(tmp_path: Path) -> None:
    store = open_store(tmp_path / "facts")
    store.connect()
    frame = canonical_fills([{"ts": utc(DAY_ONE, 1), "trade_id": "a"}])
    prepared = PreparedDay("fills", DAY_ONE, frame, repair_stats=_repair_stats())
    first = store.write_day(prepared)
    assert first.created
    assert first.path.name == f"{first.batch_sha16}.parquet"
    second = store.write_day(prepared)
    assert not second.created
    assert second.batch_sha16 == first.batch_sha16
    assert second.file_sha256 == first.file_sha256
    assert len(list(first.path.parent.glob("*.parquet"))) == 1

    changed = canonical_fills(
        [{"ts": utc(DAY_ONE, 1), "trade_id": "a"}, {"ts": utc(DAY_ONE, 2), "trade_id": "b"}]
    )
    third = store.write_day(PreparedDay("fills", DAY_ONE, changed, repair_stats=_repair_stats()))
    assert third.batch_sha16 != first.batch_sha16
    assert len(list(third.path.parent.glob("*.parquet"))) == 1, "a day must never hold two batches"
    store.close()


def test_migration_is_idempotent_and_receipt_sha_is_stable(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    store_root = tmp_path / "facts"
    first, store = migrate(sources, store_root)
    first_payload = first.as_dict()
    assert first_payload["days_created"] == 3  # two fills days + one positions day
    assert first_payload["reconciliation"]["fills"]["identity_holds"]

    second = Migration(
        store=open_store(store_root, create=False),
        sources=catalogue(sources)[0],
        kinds=("fills", "positions"),
    ).run(
        new_receipt(
            store_root=store_root,
            sources=catalogue(sources)[0],
            not_supplied=(),
            kinds=("fills", "positions"),
        )
    )
    second_payload = second.as_dict()
    assert second_payload["days_created"] == 0
    assert second_payload["days_rebuilt"] == 0
    assert second_payload["days_unchanged"] == 3
    assert second_payload["totals"] == first_payload["totals"]
    assert second_payload["receipt_sha256"] == first_payload["receipt_sha256"]
    store.close()


# ---------------------------------------------------------------------------
# Point-in-time discipline
# ---------------------------------------------------------------------------


def test_scan_cannot_see_rows_before_their_recorded_clock(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    _, store = migrate(sources, tmp_path / "facts")
    before = store.scan("fills", as_of_ms=epoch_ms("2026-10-01")).collect()
    assert before.height == 0, "archive rows have no clock and must stay invisible"
    assert "UNKNOWN_KNOWN_AT_EXCLUDED" in store.scan("fills", as_of_ms=epoch_ms("2026-10-01")).notes

    after = store.scan("fills", as_of_ms=epoch_ms("2026-11-02")).collect()
    assert after.height == 1
    assert set(after["source_id"].to_list()) == {WALLET_STORE_SOURCE}

    explicit = store.scan(
        "fills", as_of_ms=epoch_ms("2026-10-01"), allow_unknown_known_at=True
    ).collect()
    # Opting in admits the seven unclocked archive rows only. The wallet-store
    # row still has a recorded clock in November and stays out: opting in to
    # "unknown" never overrides a clock that was actually observed.
    assert explicit.height == 7
    assert explicit["first_known_at_ms"].null_count() == 7
    store.close()


def test_provenance_tier_filter_selects_clock_evidence(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    _, store = migrate(sources, tmp_path / "facts")
    observed = store.scan("fills", tiers=(ProvenanceTier.OBSERVED_FETCH,)).collect()
    retrospective = store.scan("fills", tiers=(ProvenanceTier.RETROSPECTIVE,)).collect()
    assert observed.height == 1
    assert retrospective.height == 7
    assert observed["first_known_at_ms"].null_count() == 0
    assert retrospective["first_known_at_ms"].null_count() == 7
    with pytest.raises(FactStoreError, match="INVALID_PROVENANCE_TIER"):
        store.scan("fills", tiers=("OBSERVED_FETCH",))  # type: ignore[arg-type]
    assert store.scan("fills", tiers=()).collect().is_empty()
    store.close()


def test_wallet_store_clock_never_invented_without_a_catalog_row(tmp_path: Path) -> None:
    store_root = tmp_path / "facts"
    wallet_store = tmp_path / "wallet_store"
    write_wallet_store_fills(
        wallet_store,
        W1,
        DAY_ONE,
        [{"ts": utc(DAY_ONE, 9), "size_token": 0.25, "trade_id": "w1", "start_position": 1.0}],
    )
    sources, absent = build_catalogue(wallet_store=wallet_store)
    assert absent == tuple(
        source_id for source_id in SOURCE_CATALOGUE if source_id != WALLET_STORE_SOURCE
    )
    store = open_store(store_root)
    Migration(store=store, sources=sources, kinds=("fills",)).run(
        new_receipt(store_root=store_root, sources=sources, not_supplied=absent, kinds=("fills",))
    )
    frame = store.scan("fills").collect()
    assert frame["first_known_at_ms"].to_list() == [None]
    assert frame["known_at_basis"].to_list() == ["unrecorded"]
    assert store.scan("fills", as_of_ms=epoch_ms("2026-12-01")).collect().height == 0
    store.close()


# ---------------------------------------------------------------------------
# Ordering repair at intake
# ---------------------------------------------------------------------------


def test_same_ms_repair_reorders_only_broken_bursts() -> None:
    # t1 buys 1 from 0 and closes at 1. Of the same-ms pair, only the row that
    # opens at 1 can follow, and only the row that opens at 0 can follow that.
    # Raw arrival order is inverted, so exactly one consistent order exists.
    inverted = [
        FillLink(ts_ms=1000, start_position=Decimal("0"), sign=1, size=Decimal("1")),
        FillLink(ts_ms=2000, start_position=Decimal("0"), sign=1, size=Decimal("1")),
        FillLink(ts_ms=2000, start_position=Decimal("1"), sign=-1, size=Decimal("1")),
    ]
    result = repair_same_ms_order(inverted)
    assert result.order == (0, 2, 1)
    assert result.stats.bursts == 1
    assert result.stats.bursts_repaired == 1
    assert result.stats.rows_moved == 2
    assert result.stats.bursts_left_broken == 0

    already_correct = [inverted[0], inverted[2], inverted[1]]
    untouched = repair_same_ms_order(already_correct)
    assert untouched.order == (0, 1, 2)
    assert untouched.stats.bursts_repaired == 0


def test_missing_start_position_leaves_burst_in_arrival_order() -> None:
    links = [
        FillLink(ts_ms=1000, start_position=None, sign=1, size=Decimal("1")),
        FillLink(ts_ms=1000, start_position=Decimal("2"), sign=-1, size=Decimal("1")),
    ]
    result = repair_same_ms_order(links)
    assert result.order == (0, 1)
    assert result.stats.bursts_skipped_missing_start_position == 1


def test_ingest_repairs_same_ms_order_once_and_keeps_it_stable(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    store_root = tmp_path / "facts"
    receipt, store = migrate(sources, store_root)
    order = (
        store.scan("fills", wallets=[W1], start_day=DAY_ONE, end_day=DAY_ONE)
        .collect()
        .sort(["event_ts_ms", "arrival_seq"])["trade_id"]
        .to_list()
    )
    assert order == ["t1", "t3", "t2", "t9", "w1"]
    assert receipt.reconciliation["fills"]["repair_bursts_repaired"] == 1

    # A second migration of the same inputs must not renumber arrival_seq.
    before = store.scan("fills").collect().sort(["wallet", "coin", "event_ts_ms", "arrival_seq"])
    Migration(store=open_store(store_root, create=False), sources=catalogue(sources)[0]).run(
        new_receipt(
            store_root=store_root,
            sources=catalogue(sources)[0],
            not_supplied=(),
            kinds=("fills", "positions"),
        )
    )
    after = store.scan("fills").collect().sort(["wallet", "coin", "event_ts_ms", "arrival_seq"])
    assert before.equals(after)
    store.close()


# ---------------------------------------------------------------------------
# Reconciliation across all five sources
# ---------------------------------------------------------------------------


def test_every_row_is_accounted_for_across_all_sources(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    receipt, store = migrate(sources, tmp_path / "facts")
    payload = receipt.as_dict()
    totals = payload["totals"]
    fills = {key: value for key, value in totals.items() if key.startswith("fills:")}

    expected_read = {
        f"fills:{WALLET_STORE_SOURCE}": 1,
        f"fills:{RESERVOIR_FULL_HISTORY}": 5,
        f"fills:{RESERVOIR_MONITORED_PLUS_SIX}": 2,
        f"fills:{RESERVOIR_ROSTER_DAILY}": 1,
        f"fills:{RESERVOIR_LIQUID12_DISCOVERY}": 1,
    }
    assert {key: value["rows_read"] for key, value in fills.items()} == expected_read

    read = sum(value["rows_read"] for value in fills.values())
    accounted = sum(
        value["rows_kept"]
        + value["rows_duplicate_within"]
        + value["rows_duplicate_cross"]
        + value["rows_null_key"]
        + value["rows_rejected"]
        for value in fills.values()
    )
    assert read == accounted == 10
    assert sum(value["rows_kept"] for value in fills.values()) == 8
    # the overlaps: t1 repeated by monitored, u1 repeated by liquid12
    assert fills[f"fills:{RESERVOIR_MONITORED_PLUS_SIX}"]["rows_duplicate_cross"] == 1
    assert fills[f"fills:{RESERVOIR_LIQUID12_DISCOVERY}"]["rows_duplicate_cross"] == 1
    assert payload["reconciliation"]["fills"]["rows_written"] == 8
    assert store.coverage("fills").rows == 8
    store.close()


def test_priority_wins_over_argument_order(tmp_path: Path) -> None:
    """Supplying sources in a different order must not change who wins."""
    research = tmp_path / "research"
    full = research / "reservoir-full-history-20261115"
    monitored = research / "reservoir-monitored-plus-six"
    write_reservoir_day(full, DAY_ONE, [reservoir_row(W1, DAY_ONE, "t1", 1, 1.0, 0.0)])
    # same identity, different value: the higher-priority source must win
    write_reservoir_day(monitored, DAY_ONE, [reservoir_row(W1, DAY_ONE, "t1", 1, 9.0, 0.0)])

    reversed_sources, _ = build_catalogue(
        reservoir={"monitored-plus-six": monitored, "full-history": full}
    )
    assert [spec.source_id for spec in reversed_sources] == [
        RESERVOIR_FULL_HISTORY,
        RESERVOIR_MONITORED_PLUS_SIX,
    ]
    store_root = tmp_path / "facts"
    store = open_store(store_root)
    receipt = Migration(store=store, sources=reversed_sources, kinds=("fills",)).run(
        new_receipt(
            store_root=store_root, sources=reversed_sources, not_supplied=(), kinds=("fills",)
        )
    )
    totals = receipt.as_dict()["totals"]
    assert totals[f"fills:{RESERVOIR_FULL_HISTORY}"]["rows_kept"] == 1
    assert totals[f"fills:{RESERVOIR_MONITORED_PLUS_SIX}"]["rows_kept"] == 0
    assert totals[f"fills:{RESERVOIR_MONITORED_PLUS_SIX}"]["rows_conflicting_values"] == 1
    kept = store.scan("fills").collect()
    assert kept["size"].to_list() == [Decimal("1.000000000000")]
    store.close()


def test_rebuild_replaces_a_day_when_a_new_source_appears(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    store_root = tmp_path / "facts"
    only_full, _ = build_catalogue(reservoir={"full-history": sources[RESERVOIR_FULL_HISTORY]})
    store = open_store(store_root)
    Migration(store=store, sources=only_full, kinds=("fills",)).run(
        new_receipt(store_root=store_root, sources=only_full, not_supplied=(), kinds=("fills",))
    )
    assert store.coverage("fills").rows == 5

    # add a source that contributes to an already-closed day
    everything, _ = catalogue(sources)
    receipt = Migration(store=store, sources=everything, kinds=("fills",)).run(
        new_receipt(store_root=store_root, sources=everything, not_supplied=(), kinds=("fills",))
    )
    payload = receipt.as_dict()
    assert payload["days_rebuilt"] == 2
    assert store.coverage("fills").rows == 8
    assert store.verify()["ok"]
    store.close()


def test_verify_detects_a_tampered_batch(sources: dict[str, Path], tmp_path: Path) -> None:
    _, store = migrate(sources, tmp_path / "facts")
    batch = mf.day_batches(store.connect(), "fills")[0]
    path = Path(batch.path)
    path.write_bytes(path.read_bytes() + b"\x00")
    report = store.verify()
    assert not report["ok"]
    assert any(problem.startswith("FILE_SHA_MISMATCH") for problem in report["problems"])
    store.close()


def test_day_batch_conflict_is_refused(tmp_path: Path) -> None:
    store = open_store(tmp_path / "facts")
    store.connect()
    frame = canonical_fills([{"ts": utc(DAY_ONE, 1), "trade_id": "a"}])
    write = store.write_day(PreparedDay("fills", DAY_ONE, frame, repair_stats=_repair_stats()))
    # simulate a corrupted file that still claims the same batch identity
    write.path.write_bytes(b"not a parquet file")
    with pytest.raises(FactStoreError, match="BATCH_CONTENT_CONFLICT"):
        store.write_day(PreparedDay("fills", DAY_ONE, frame, repair_stats=_repair_stats()))
    store.close()


def test_coverage_flags_missing_days(sources: dict[str, Path], tmp_path: Path) -> None:
    _, store = migrate(sources, tmp_path / "facts")
    report = store.coverage("fills", start_day=DAY_ONE, end_day=DAY_THREE)
    assert report.missing_days == (DAY_THREE,)
    assert report.days_present == (DAY_ONE, DAY_TWO)
    assert report.observed_fetch_rows == 1
    assert report.retrospective_rows == 7
    store.close()


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_migrate_prints_aggregates_only(
    sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "facts"
    report = tmp_path / "receipt.json"
    argv = [
        "migrate",
        "--store",
        str(store_root),
        "--wallet-store",
        str(sources["wallet_store"]),
        "--reservoir",
        f"full-history={sources[RESERVOIR_FULL_HISTORY]}",
        "--reservoir",
        f"monitored-plus-six={sources[RESERVOIR_MONITORED_PLUS_SIX]}",
        "--reservoir",
        f"roster-daily={sources[RESERVOIR_ROSTER_DAILY]}",
        "--reservoir",
        f"liquid12-discovery={sources[RESERVOIR_LIQUID12_DISCOVERY]}",
        "--require-all-sources",
        "--report",
        str(report),
        "--apply",
    ]
    dry = [item for item in argv if item != "--apply"]
    dry_report = tmp_path / "dry.json"
    dry[dry.index("--report") + 1] = str(dry_report)
    assert pm_facts_cli.main(dry) == 0
    assert "dry_run=3" in capsys.readouterr().out
    assert json.loads(dry_report.read_text())["applied"] is False
    assert not store_root.exists()

    assert pm_facts_cli.main(argv) == 0
    captured = capsys.readouterr()
    assert "0x" not in captured.out
    assert "0x" not in captured.err
    assert "identity_holds=True" in captured.out
    assert store_root.joinpath("fills").is_dir(), "the store was created"
    payload = json.loads(report.read_text())
    assert payload["sources_not_supplied"] == []
    assert payload["reconciliation"]["fills"]["rows_written"] == 8
    assert payload["applied"] is True

    assert pm_facts_cli.main(argv) == 0
    assert "identity_holds=True" in capsys.readouterr().out
    rerun = json.loads(report.read_text())
    assert rerun["days_unchanged"] == 3
    assert rerun["receipt_sha256"] == payload["receipt_sha256"]


def test_cli_output_is_redacted_and_guarded(capsys: pytest.CaptureFixture[str]) -> None:
    """Two layers: the guard refuses raw text, the emitter redacts before print."""
    with pytest.raises(RuntimeError, match="FACTS_OUTPUT_WOULD_LEAK_WALLET_ADDRESS"):
        pm_facts_cli.assert_aggregate_only(f"row owner {W1}")
    pm_facts_cli.emit([f"legacy partition wallet={W1}/day=2026-05-01"])
    out = capsys.readouterr().out
    assert "0x" not in out
    assert "<wallet>" in out


def test_cli_requires_all_sources_when_asked(sources: dict[str, Path], tmp_path: Path) -> None:
    argv = [
        "migrate",
        "--store",
        str(tmp_path / "facts"),
        "--wallet-store",
        str(sources["wallet_store"]),
        "--require-all-sources",
    ]
    with pytest.raises(SystemExit) as excinfo:
        pm_facts_cli.main(argv)
    assert "MISSING_REQUIRED_SOURCES" in str(excinfo.value)


def test_cli_coverage_and_verify(
    sources: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "facts"
    migrate(sources, store_root)
    assert pm_facts_cli.main(["coverage", "--store", str(store_root), "--kinds", "fills"]) == 0
    out = capsys.readouterr().out
    assert "fills: days=2 rows=8" in out
    assert pm_facts_cli.main(["verify", "--store", str(store_root)]) == 0
    assert "ok=True" in capsys.readouterr().out


def test_benchmark_selects_wallets_across_sparse_days(
    sources: dict[str, Path], tmp_path: Path
) -> None:
    write_reservoir_day(
        sources[RESERVOIR_FULL_HISTORY],
        DAY_ONE,
        [reservoir_row(W3, DAY_ONE, "w3-only-first-day", 1, 1.0, 0.0)],
    )
    _, store = migrate(sources, tmp_path / "facts")
    stats = run_benchmark(store, wallets=3, days=2, repeats=1, day_end=DAY_TWO)
    assert stats["wallets"] == 3
    assert stats["files_scanned"] == 2


def test_benchmark_runs_the_250_by_200_scan_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = SyntheticPlan(wallets=12, days=5, rows_per_wallet_day=4)
    store = build_synthetic_store(tmp_path / "bench", plan)
    stats = run_benchmark(store, wallets=12, days=5, repeats=2)
    assert stats["wallets"] == 12
    assert stats["rows_returned"] == plan.rows
    assert stats["files_scanned"] == 5
    assert stats["seconds_p50"] > 0
    assert stats["pit_rows_returned"] == plan.rows, "synthetic rows carry a fetch clock"
    store.close()

    assert (
        pm_facts_cli.main(
            [
                "benchmark",
                "--workdir",
                str(tmp_path / "cli-bench"),
                "--wallets",
                "6",
                "--days",
                "3",
                "--rows-per-wallet-day",
                "2",
                "--repeats",
                "1",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "facts benchmark: wallets=6 days=3" in out
    assert "0x" not in out


# ---------------------------------------------------------------------------
# Boundary proofs
# ---------------------------------------------------------------------------


def test_manifest_imports_without_polars() -> None:
    source = Path(mf.__file__).read_text()
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "polars" not in imported
    assert "numpy" not in imported


def test_wallet_first_writer_is_retired_for_the_live_store(tmp_path: Path) -> None:
    """A new wallet-first partition may not appear in the canonical store."""
    from copytrade_pm.wallet_store import store as legacy_store
    from copytrade_pm.wallet_store.schema import FILLS_POLARS_SCHEMA

    frame = pl.DataFrame(
        [
            {
                "ts": utc(DAY_ONE, 1),
                "wallet": W1,
                "symbol": "BTC",
                "dex": "HL",
                "side": "buy",
                "size_token": 1.0,
                "price": 100.0,
                "size_usd": 100.0,
                "fee": 0.01,
                "fee_token": "USDC",
                "is_maker": False,
                "order_id": "o1",
                "trade_id": "t1",
                "crossed": False,
                "closed_pnl": 0.0,
                "start_position": 0.0,
                "source": "vike",
                "source_ts": "2026-05-01T00:00:01Z",
            }
        ],
        schema=FILLS_POLARS_SCHEMA,
    )
    with pytest.raises(RuntimeError, match="WALLET_STORE_WRITER_RETIRED"):
        legacy_store.ingest("fills", W1, DAY_ONE, frame, source="vike")
    # an explicit, local opt-in still works for reproducing a historical archive
    receipt = legacy_store.ingest(
        "fills",
        W1,
        DAY_ONE,
        frame,
        source="vike",
        store_dir=tmp_path / "legacy",
        allow_retired_writer=True,
    )
    assert receipt["rows"] == 1


def test_no_float64_in_canonical_write_schemas() -> None:
    from copytrade_pm.facts import schemas as facts_schemas

    for kind in ("fills", "positions"):
        schema = schema_for(kind)
        assert all(dtype != pl.Float64 for dtype in schema.values()), kind
    money = set(facts_schemas.MONEY_COLUMNS["fills"]) | set(
        facts_schemas.MONEY_COLUMNS["positions"]
    )
    for kind in ("fills", "positions"):
        for column in money.intersection(schema_for(kind).names()):
            assert schema_for(kind)[column] == pl.Decimal(38, 12), (kind, column)
