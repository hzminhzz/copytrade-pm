"""Capture-ingest proofs: merge, deduplicate, fail closed, stay idempotent.

Every fixture is synthetic: invented wallets, invented coins, no private store,
no provider and no network. The suite proves the writer contract the wallet-health
capture depends on:

1. ``Decimal(38, 12)`` is the only money representation written.
2. A day is rebuilt from what is already committed plus what is offered, so a
   narrower re-observation never drops an earlier fact.
3. Deduplication is by fact identity and keeps the earliest recorded clock.
4. One identity with two different payloads fails closed.
5. Re-ingesting identical content writes nothing and reports ``created=False``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from copytrade_pm.facts import manifest as mf  # noqa: E402
from copytrade_pm.facts.ingest import FactIngestor, frame_from_rows  # noqa: E402
from copytrade_pm.facts.schemas import ProvenanceTier  # noqa: E402
from copytrade_pm.facts.store import FactStore, FactStoreError  # noqa: E402

DAY_ONE = "2026-05-01"
DAY_TWO = "2026-05-02"
W1 = "0x" + "1" * 40
W2 = "0x" + "2" * 40
FETCH_MS = int(datetime(2026, 5, 3, tzinfo=UTC).timestamp() * 1000)
SOURCE = "official_hyperliquid_info"


def epoch_ms(day: str, seconds: int = 0) -> int:
    base = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return int(base.timestamp() * 1000) + seconds * 1000


def equity_row(
    wallet: str = W1,
    *,
    day: str = DAY_ONE,
    seconds: int = 0,
    equity: str = "2300.5",
    first_known_at_ms: int | None = FETCH_MS,
) -> dict:
    ts = epoch_ms(day, seconds)
    return {
        "wallet": wallet,
        "account_scope": "HL_MAIN_PERP_ONLY",
        "abstraction_mode": "default",
        "equity_usd": Decimal(equity),
        "withdrawable_usd": Decimal("1000"),
        "margin_used_usd": Decimal("12.25"),
        "observed_at": datetime.fromtimestamp(ts / 1000, UTC),
        "event_ts_ms": ts,
        "first_known_at_ms": first_known_at_ms,
        "known_at_basis": "partition_fetch_clock" if first_known_at_ms else None,
        "arrival_seq": 0,
        "source_id": SOURCE,
        "source_rank": 1,
        "batch_sha16": "",
    }


@pytest.fixture()
def store(tmp_path: Path):
    handle = FactStore(tmp_path / "facts", create=True)
    yield handle
    handle.close()


def ingest(store: FactStore, rows: list[dict], **kwargs):
    return FactIngestor(store, dry_run=kwargs.pop("dry_run", False)).ingest_rows(
        "equity",
        rows,
        source_id=SOURCE,
        source_rank=1,
        first_known_at_ms=kwargs.pop("first_known_at_ms", FETCH_MS),
        input_label=kwargs.pop("input_label", "capture-1"),
    )


def test_equity_lands_once_as_decimal_with_a_recorded_clock(store):
    receipts = ingest(store, [equity_row()])
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.day == DAY_ONE
    assert receipt.rows_written == 1 and receipt.created is True
    frame = store.scan("equity", as_of_ms=FETCH_MS).collect()
    assert frame.height == 1
    assert frame["equity_usd"].dtype == pl.Decimal(38, 12)
    assert frame["equity_usd"][0] == Decimal("2300.500000000000")
    assert frame["known_at_basis"][0] == "partition_fetch_clock"
    assert store.verify()["ok"] is True


def test_repeating_the_same_observation_writes_nothing(store):
    first = ingest(store, [equity_row()])[0]
    second = ingest(store, [equity_row()], input_label="capture-2")[0]
    assert first.batch_sha16 == second.batch_sha16
    assert second.created is False
    assert second.rows_duplicate == 1
    assert second.rows_written == 1
    assert store.coverage("equity").rows == 1


def test_merge_keeps_earlier_facts_and_the_earliest_clock(store):
    ingest(store, [equity_row(seconds=0)])
    later = ingest(store, [equity_row(seconds=60, first_known_at_ms=FETCH_MS + 1000)])[0]
    assert later.rows_written == 2
    assert later.rows_preserved == 1
    # A re-observation of the first fact must not move its recorded clock.
    ingest(store, [equity_row(seconds=0, first_known_at_ms=FETCH_MS + 5000)])
    frame = store.scan("equity", as_of_ms=FETCH_MS + 5000).collect()
    assert frame.height == 2
    earliest = frame.filter(pl.col("event_ts_ms") == epoch_ms(DAY_ONE))
    assert earliest["first_known_at_ms"][0] == FETCH_MS
    # Point-in-time: the later fact stays invisible before its own clock.
    assert store.scan("equity", as_of_ms=FETCH_MS).collect().height == 1


def test_rows_span_days_and_each_day_is_recorded(store):
    receipts = ingest(
        store,
        [equity_row(day=DAY_ONE), equity_row(day=DAY_TWO, wallet=W2)],
    )
    assert [item.day for item in receipts] == [DAY_ONE, DAY_TWO]
    coverage = store.coverage("equity")
    assert coverage.rows == 2 and coverage.files == 2
    con = store.connect()
    inputs = mf.day_inputs(con, "equity", DAY_ONE)
    assert [(item.source_id, item.rel_path) for item in inputs] == [
        (SOURCE, "capture/capture-1/equity")
    ]


def test_one_identity_with_two_payloads_fails_closed(store):
    ingest(store, [equity_row(equity="2300.5")])
    with pytest.raises(FactStoreError, match="INGEST_CONFLICTING_VALUES"):
        ingest(store, [equity_row(equity="2400")])
    # The committed fact is untouched by the rejected write.
    assert store.scan("equity", as_of_ms=FETCH_MS).collect().height == 1


def test_duplicate_rows_inside_one_offer_are_counted(store):
    receipt = ingest(store, [equity_row(), equity_row()])[0]
    assert receipt.rows_offered == 2
    assert receipt.rows_duplicate == 1
    assert receipt.rows_written == 1


def test_missing_identity_or_schema_fails_closed(store):
    with pytest.raises(FactStoreError, match="INGEST_NULL_IDENTITY"):
        ingest(store, [equity_row(wallet=None)])  # type: ignore[arg-type]
    with pytest.raises(FactStoreError, match="INGEST_UNSUPPORTED_KIND"):
        FactIngestor(store).ingest_rows(
            "fills",
            [equity_row()],
            source_id=SOURCE,
            source_rank=1,
            first_known_at_ms=FETCH_MS,
        )
    broken = frame_from_rows("equity", [equity_row()]).drop("equity_usd")
    with pytest.raises(FactStoreError, match="INGEST_MISSING_COLUMNS"):
        FactIngestor(store).ingest_frame(
            "equity",
            broken,
            source_id=SOURCE,
            source_rank=1,
            first_known_at_ms=FETCH_MS,
        )


def test_dry_run_writes_no_batch_and_no_manifest_row(store):
    receipts = ingest(store, [equity_row()], dry_run=True)
    assert receipts[0].dry_run is True
    assert not receipts[0].path.exists()
    assert store.coverage("equity").rows == 0
    assert not list((Path(store.root) / "equity").rglob("*.parquet"))


def test_absent_clock_leaves_a_row_retrospective_and_invisible(store):
    ingest(store, [equity_row(first_known_at_ms=None)], first_known_at_ms=None)
    frame = store.scan("equity", as_of_ms=FETCH_MS).collect()
    assert frame.height == 0
    included = store.scan("equity", as_of_ms=FETCH_MS, allow_unknown_known_at=True)
    assert included.collect().height == 1
    assert "UNKNOWN_KNOWN_AT_INCLUDED" in included.notes
    tier = store.scan("equity", tiers=(ProvenanceTier.RETROSPECTIVE,))
    assert tier.collect().height == 1
