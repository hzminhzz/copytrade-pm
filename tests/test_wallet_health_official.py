"""Official Hyperliquid wallet-health capture: roster enumeration -> FactStore.

Every fixture is synthetic: a throwaway ``roster.sqlite``, a throwaway fact
store, an injected ``info`` callable and no network. The suite proves the Slice 3
cutover contract:

1. wallets come from the roster (active + draining + scored) and, optionally,
   from the fact store — never from ``wallet_registry.sqlite``;
2. only the main-perp equity a reply can actually support becomes a fact, and
   every normalised row carries the reply's own receive clock as ``first_known``;
3. equity / funding / ledger rows land in the ``FactStore`` as ``Decimal(38,12)``
   with deduplication, and a repeated capture writes nothing;
4. the raw private archive and the aggregate publication are both optional;
5. the roster is opened read-only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest

pl = pytest.importorskip("polars")

from copytrade_kernel import KnownAtTs  # noqa: E402
from copytrade_pm import wallet_health_official as o  # noqa: E402
from copytrade_pm.facts.ingest import FactIngestor  # noqa: E402
from copytrade_pm.facts.schemas import ProvenanceTier  # noqa: E402
from copytrade_pm.facts.store import FactStore  # noqa: E402
from copytrade_pm.roster import (  # noqa: E402
    BenchCandidate,
    RosterStore,
    SeatSpec,
    WalletScorecard,
    digest,
    reconcile_roster,
)

_OPENED: list = []


@pytest.fixture(autouse=True)
def _close_handles():
    _OPENED.clear()
    yield
    while _OPENED:
        _OPENED.pop().close()


def store_at(directory: Path, name: str = "facts", *, create: bool = True) -> FactStore:
    store = FactStore(directory / name, create=create)
    _OPENED.append(store)
    return store


NOW = datetime(2026, 11, 20, 6, 0, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)
DAY_MS = 86_400_000
EPOCH = digest("wallet-health-capture-test-epoch")
SEATS = (
    SeatSpec("seat_1", Decimal("200"), Decimal("0.45")),
    SeatSpec("seat_2", Decimal("200"), Decimal("0.45")),
)
WALLETS = tuple("0x" + f"{index:02x}" * 20 for index in range(1, 5))
OUTSIDER = "0x" + "9" * 40


def _card(index: int) -> WalletScorecard:
    return WalletScorecard(
        wallet=WALLETS[index],
        as_of=KnownAtTs(NOW_MS),
        account_value_usd=Decimal("10000"),
        active_days_14d=5,
        markout_5m_bps=Decimal("4"),
        p95_participation_1m=Decimal("0.002"),
        euler_cdar_share=Decimal("0.31"),
        suggested_k=Decimal("1"),
        cluster_id=f"c{index}",
        copyable_drift=True,
        failures=(),
        source_sha=digest(["synthetic-source", index]),
    )


def _candidate(card: WalletScorecard) -> BenchCandidate:
    return BenchCandidate(
        wallet=card.wallet,
        scorecard_sha=card.sha,
        suggested_k=card.suggested_k,
        marginal_cdar_share=Decimal("0.15"),
        cluster_id=card.cluster_id,
        cluster_distance=Decimal("1.0"),
    )


def seeded_roster(tmp_path: Path) -> tuple[Path, dict[str, tuple[str, ...]]]:
    """Two leased seats, one drained owner, four scored candidates."""
    path = tmp_path / "roster.sqlite"
    cards = [_card(index) for index in range(3)]
    with RosterStore(path, create=True) as roster:
        roster.register_account("cft-10k-paper", SEATS, policy_epoch=EPOCH, at_ms=NOW_MS)
        for card in cards:
            roster.record_scorecard(card)
        # A fourth card with no bench entry is a scored-only candidate.
        roster.record_scorecard(_card(3))
        roster.record_bench(
            "cft-10k-paper", [_candidate(card) for card in cards], as_of=KnownAtTs(NOW_MS)
        )
        book = roster.book_at("cft-10k-paper", as_of=KnownAtTs(NOW_MS))
        roster.commit_plan(
            reconcile_roster(
                current=book,
                scorecard=roster.latest_scorecard(as_of=KnownAtTs(NOW_MS)),
                bench=roster.latest_bench("cft-10k-paper", as_of=KnownAtTs(NOW_MS)),
                as_of=KnownAtTs(NOW_MS),
            )
        )
    with RosterStore(path, writable=True) as roster:
        book = roster.book_at("cft-10k-paper", as_of=KnownAtTs(NOW_MS))
        victim = book.wallets[0]
        roster.record_veto(victim, reason="synthetic", actor="operator", at_ms=NOW_MS)
        roster.commit_plan(
            reconcile_roster(
                current=book,
                scorecard=roster.latest_scorecard(as_of=KnownAtTs(NOW_MS)),
                bench=roster.latest_bench("cft-10k-paper", as_of=KnownAtTs(NOW_MS)),
                vetoes=roster.active_vetoes(as_of=KnownAtTs(NOW_MS)),
                as_of=KnownAtTs(NOW_MS),
            )
        )
    with RosterStore(path) as reader:
        stored = reader.book_at("cft-10k-paper", as_of=KnownAtTs(NOW_MS))
    identity = {
        "active": stored.wallets,
        "draining": stored.draining_wallets,
    }
    return path, identity


def _state(amount: str = "2300.5", *, at: int = NOW_MS) -> dict:
    return {
        "time": at,
        "marginSummary": {"accountValue": amount, "totalMarginUsed": "12.25"},
        "assetPositions": [],
        "withdrawable": "1000",
    }


def provider(
    *,
    mode: str = "default",
    tamper: bool = False,
    state: dict | None = None,
    failures: frozenset[str] = frozenset(),
    funding: list | None = None,
):
    """Deterministic stand-in for ``guarded_info``; records every request type."""
    calls: list[str] = []

    def info(request):
        kind = request["type"]
        calls.append(kind)
        if kind in failures:
            raise ValueError("INVALID_PROVIDER_SCHEMA")
        response = {
            "clearinghouseState": _state() if state is None else state,
            "userAbstraction": mode,
            "userNonFundingLedgerUpdates": [
                {
                    "time": NOW_MS - DAY_MS,
                    "hash": "0x" + "a" * 64,
                    "delta": {"withdraw": {"usdc": "100"}},
                }
            ],
            "userFunding": [
                {
                    "time": NOW_MS - 3_600_000,
                    "hash": "0x" + "b" * 64,
                    "delta": {
                        "type": "funding",
                        "coin": "BTC",
                        "usdc": "-1.25",
                        "szi": "0.5",
                        "fundingRate": "0.0001",
                    },
                }
            ]
            if funding is None
            else funding,
            "userFillsByTime": [{"time": NOW_MS - DAY_MS, "tid": 7}],
        }[kind]
        raw = json.dumps(response, separators=(",", ":")).encode()
        return response, raw, "f" * 64 if tamper else sha256(raw).hexdigest()

    return info, calls


class NoWaitBudget(o.WeightBudget):
    """Count reservations without sleeping out the shared-IP window."""

    def acquire(self, kind: str) -> None:
        self.calls += 1
        self.total_reserved += o.WEIGHTS[kind]


def capture(tmp_path: Path, *, store: FactStore | None = None, **kwargs):
    roster_db = kwargs.pop("roster_db", None) or (tmp_path / "roster.sqlite")
    facts = store if store is not None else store_at(tmp_path)
    info = kwargs.pop("info", None) or provider()[0]
    generation = kwargs.pop("generation", tmp_path / ("g" + "x" * 13))
    clock = kwargs.pop("clock", lambda: NOW)
    result = o.capture_health(
        roster_db=roster_db,
        store=facts,
        generation=generation,
        budget=NoWaitBudget(),
        info=info,
        clock=clock,
        **kwargs,
    )
    return result, facts, generation


# ---------------------------------------------------------------------------
# Candidates come from the roster, read-only
# ---------------------------------------------------------------------------


def test_candidates_are_active_draining_and_scored_roster_wallets(tmp_path):
    roster_db, identity = seeded_roster(tmp_path)
    selection = o.roster_candidates(roster_db, as_of_ms=NOW_MS)
    wallets = {item.wallet for item in selection.candidates}
    assert set(identity["active"]) <= wallets
    assert set(identity["draining"]) <= wallets
    assert WALLETS[3] in wallets  # scored only, never leased
    assert selection.active == len(identity["active"])
    assert selection.draining == len(identity["draining"])
    assert selection.scored == 4
    assert selection.inventory_sha256 == sha256_of_roster(roster_db)


def sha256_of_roster(path: Path) -> str:
    with RosterStore(path) as roster:
        return roster.inventory_sha()


def test_roster_is_opened_read_only_and_never_written(tmp_path):
    roster_db, _ = seeded_roster(tmp_path)
    before = sha256_of_roster(roster_db)
    capture(tmp_path)
    assert sha256_of_roster(roster_db) == before


def test_facts_union_adds_wallets_the_store_already_tracks(tmp_path):
    roster_db, _ = seeded_roster(tmp_path)
    facts = store_at(tmp_path, "prior")
    FactIngestor(facts).ingest_rows(
        "equity",
        [
            {
                "wallet": OUTSIDER,
                "account_scope": "HL_MAIN_PERP_ONLY",
                "abstraction_mode": "default",
                "equity_usd": Decimal("500"),
                "withdrawable_usd": None,
                "margin_used_usd": None,
                "observed_at": datetime.fromtimestamp((NOW_MS - DAY_MS) / 1000, UTC),
                "event_ts_ms": NOW_MS - DAY_MS,
                "first_known_at_ms": NOW_MS - DAY_MS,
                "known_at_basis": "partition_fetch_clock",
                "arrival_seq": 0,
                "source_id": "official_hyperliquid_info",
                "source_rank": 1,
                "batch_sha16": "",
            }
        ],
        source_id="official_hyperliquid_info",
        source_rank=1,
        first_known_at_ms=NOW_MS - DAY_MS,
        input_label="prior",
    )
    result, _, _ = capture(tmp_path, roster_db=roster_db, facts_root=tmp_path / "prior")
    assert result["candidates"]["facts_only"] == 1
    assert result["candidates"]["total"] == 5
    assert result["requested_accounts"] == 5


def test_facts_union_includes_fills_only_wallets(tmp_path):
    from copytrade_pm.facts.migrate import Migration, new_receipt
    from copytrade_pm.facts.sources import build_catalogue

    roster_db, _ = seeded_roster(tmp_path)
    day = (NOW - timedelta(days=1)).date().isoformat()
    archive = tmp_path / "reservoir"
    path = archive / "hyperliquid" / "fills" / f"day={day}" / "data.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "wallet": [OUTSIDER],
            "exchange_ts": [datetime.fromtimestamp((NOW_MS - DAY_MS) / 1000, UTC)],
            "coin": ["BTC"],
            "dex": ["hyperliquid"],
            "side": ["buy"],
            "size": [0.5],
            "price": [10000.0],
            "start_position": [0.0],
            "trade_id": [1],
        }
    ).with_columns(
        pl.col("exchange_ts").cast(pl.Datetime("us", "UTC")),
        pl.col("trade_id").cast(pl.UInt64),
    ).write_parquet(path)

    facts = store_at(tmp_path, "prior_fills")
    sources, absent = build_catalogue(reservoir={"full-history": archive})
    Migration(store=facts, sources=sources, kinds=("fills",)).run(
        new_receipt(store_root=facts.root, sources=sources, not_supplied=absent, kinds=("fills",))
    )
    result, _, _ = capture(tmp_path, roster_db=roster_db, facts_root=tmp_path / "prior_fills")
    assert result["candidates"]["facts_only"] == 1
    assert result["candidates"]["total"] == 5
    assert result["requested_accounts"] == 5


# ---------------------------------------------------------------------------
# Normalisation into the FactStore
# ---------------------------------------------------------------------------


def test_capture_writes_decimal_equity_funding_and_ledger_rows(tmp_path):
    seeded_roster(tmp_path)
    result, facts, generation = capture(tmp_path, deep_wallets=8)

    assert result["schema"] == o.CAPTURE_SCHEMA
    assert result["requested_accounts"] == 4
    assert result["verified_main_perp_equity"] == 4
    assert result["provider_errors"] == {}
    assert result["trading_authorized"] is False
    assert result["read_only_source_and_roster"] is True

    equity = facts.scan("equity", as_of_ms=NOW_MS).collect()
    assert equity.height == 4
    assert equity["equity_usd"].dtype == pl.Decimal(38, 12)
    assert set(equity["equity_usd"].to_list()) == {Decimal("2300.500000000000")}
    assert set(equity["first_known_at_ms"].to_list()) == {NOW_MS}
    assert set(equity["known_at_basis"].to_list()) == {"partition_fetch_clock"}
    assert set(equity["account_scope"].to_list()) == {"HL_MAIN_PERP_ONLY"}

    funding = facts.scan("funding", as_of_ms=NOW_MS).collect()
    assert funding.height == 4
    assert funding["payment_usd"].dtype == pl.Decimal(38, 12)
    assert set(funding["payment_usd"].to_list()) == {Decimal("-1.250000000000")}
    assert set(funding["coin"].to_list()) == {"BTC"}

    ledger = facts.scan("ledger", as_of_ms=NOW_MS).collect()
    assert ledger.height == 4
    assert set(ledger["kind"].to_list()) == {"withdraw"}
    assert set(ledger["amount_usd"].to_list()) == {Decimal("100.000000000000")}

    assert facts.verify()["ok"] is True
    assert (generation / o.SUMMARY_NAME).is_file()
    # Raw archive and receipts stay private.
    assert (generation / "raw" / "w000001" / "clearinghouseState.json").is_file()
    assert (generation / "receipts" / "w000001" / "clearinghouseState.json").is_file()
    assert generation.stat().st_mode & 0o077 == 0


def test_known_at_is_the_capture_clock_not_the_event_clock(tmp_path):
    seeded_roster(tmp_path)
    _, facts, _ = capture(tmp_path)
    # The provider stamped its reply before this instant; the fact was only
    # learned at the capture clock, so it must be invisible one ms earlier.
    assert facts.scan("equity", as_of_ms=NOW_MS - 1).collect().height == 0
    assert facts.scan("equity", as_of_ms=NOW_MS).collect().height == 4
    slice_ = facts.scan("equity", as_of_ms=NOW_MS, tiers=(ProvenanceTier.OBSERVED_FETCH,))
    assert slice_.collect().height == 4


def test_repeating_the_capture_writes_nothing_new(tmp_path):
    seeded_roster(tmp_path)
    first, facts, _ = capture(tmp_path, deep_wallets=8)
    assert first["fact_batches"]["created"] == 3
    before = {kind: facts.coverage(kind).rows for kind in o.FACT_KINDS}
    second, _, _ = capture(
        tmp_path, store=facts, generation=tmp_path / ("g" + "y" * 13), deep_wallets=8
    )
    assert second["fact_batches"]["unchanged"] == 3
    assert second["fact_rows_written"] == {"equity": 0, "funding": 0, "ledger": 0}
    after = {kind: facts.coverage(kind).rows for kind in o.FACT_KINDS}
    assert after == before


def test_a_later_capture_merges_and_keeps_earlier_facts(tmp_path):
    seeded_roster(tmp_path)
    _, facts, _ = capture(tmp_path)
    later_state = _state(at=NOW_MS + 3_600_000)
    later_info, _ = provider(state=later_state)
    result, _, _ = capture(
        tmp_path,
        store=facts,
        info=later_info,
        generation=tmp_path / ("g" + "z" * 13),
        history_days=1,
        clock=lambda: NOW + timedelta(hours=1),
    )
    assert result["fact_rows_written"]["equity"] == 4
    equity = facts.scan("equity", as_of_ms=NOW_MS + 3_600_000).collect()
    assert equity.height == 8  # four earlier snapshots preserved, four new
    assert equity["event_ts_ms"].n_unique() == 2
    # The first snapshot keeps its original first-known clock.
    early = equity.filter(pl.col("event_ts_ms") == NOW_MS)
    assert set(early["first_known_at_ms"].to_list()) == {NOW_MS}


def test_nonyearable_account_value_abstains_instead_of_zero(tmp_path):
    seeded_roster(tmp_path)
    info, _ = provider(mode="unifiedAccount")
    result, facts, _ = capture(tmp_path, info=info)
    assert result["verified_main_perp_equity"] == 0
    assert result["equity_abstained"] == 4
    assert facts.scan("equity", as_of_ms=NOW_MS).collect().height == 0


def test_tampered_reply_abstains_and_records_a_provider_error(tmp_path):
    seeded_roster(tmp_path)
    info, _ = provider(tamper=True)
    result, facts, _ = capture(tmp_path, info=info)
    assert result["verified_main_perp_equity"] == 0
    assert result["provider_errors"]
    assert facts.scan("equity", as_of_ms=NOW_MS).collect().height == 0


def test_missing_account_mode_abstains(tmp_path):
    seeded_roster(tmp_path)
    info, _ = provider(failures=frozenset({"userAbstraction"}))
    result, facts, _ = capture(tmp_path, info=info)
    assert result["verified_main_perp_equity"] == 0
    assert facts.scan("equity", as_of_ms=NOW_MS).collect().height == 0


# ---------------------------------------------------------------------------
# Optional sinks
# ---------------------------------------------------------------------------


def test_raw_archive_is_optional_and_facts_still_land(tmp_path):
    seeded_roster(tmp_path)
    result = o.capture_health(
        roster_db=tmp_path / "roster.sqlite",
        store=store_at(tmp_path),
        generation=None,
        raw_archive=False,
        deep_wallets=8,
        budget=NoWaitBudget(),
        info=provider()[0],
        clock=lambda: NOW,
    )
    assert result["raw_receipts_verified"] == 20
    assert not (tmp_path / ("g" + "x" * 13)).exists()
    assert store_at(tmp_path, create=False).coverage("equity").rows == 4


def test_publish_dir_is_optional_and_carries_no_address(tmp_path):
    seeded_roster(tmp_path)
    result, _, _ = capture(tmp_path)
    assert not (tmp_path / "publish").exists()

    published, _, _ = capture(
        tmp_path,
        generation=tmp_path / ("g" + "w" * 13),
        publish_dir=tmp_path / "publish",
        deep_wallets=8,
    )
    assert published["candidates"] == result["candidates"]
    payload = (tmp_path / "publish" / o.PUBLISHED_NAME).read_text()
    assert "0x" not in payload
    data = json.loads(payload)
    assert data["schema"] == o.CAPTURE_SCHEMA
    assert data["trading_authorized"] is False
    # Aggregate counts only: no USD amount ever reaches the published summary.
    assert "2300.5" not in payload
    assert "100" not in json.dumps(data["fact_rows_normalized"])
    assert "external_deposit_usd_observed" not in payload
    assert data["ledger_summary"]["wallets_audited"] == 4


def test_capture_requires_a_sink_and_bounded_windows(tmp_path):
    seeded_roster(tmp_path)
    with pytest.raises(ValueError, match="NO_CAPTURE_SINK"):
        o.capture_health(roster_db=tmp_path / "roster.sqlite", raw_archive=False)
    with pytest.raises(ValueError, match="RAW_ARCHIVE_GENERATION_REQUIRED"):
        o.capture_health(roster_db=tmp_path / "roster.sqlite", store=None, raw_archive=True)
    with pytest.raises(ValueError, match="INVALID_HEALTH_CAPTURE_BOUNDS"):
        o.capture_health(
            roster_db=tmp_path / "roster.sqlite",
            store=store_at(tmp_path, "facts2"),
            generation=tmp_path / ("g" + "v" * 13),
            max_wallets=0,
            info=provider()[0],
            clock=lambda: NOW,
        )
    with pytest.raises(ValueError, match="INVALID_HEALTH_HISTORY_WINDOW"):
        o.capture_health(
            roster_db=tmp_path / "roster.sqlite",
            store=store_at(tmp_path, "facts3"),
            generation=tmp_path / ("g" + "u" * 13),
            history_days=0,
            info=provider()[0],
            clock=lambda: NOW,
        )


def test_immutable_generation_is_never_reused(tmp_path):
    seeded_roster(tmp_path)
    _, _, generation = capture(tmp_path)
    with pytest.raises(ValueError, match="IMMUTABLE_HEALTH_GENERATION_ALREADY_EXISTS"):
        capture(tmp_path, generation=generation)


def test_duplicate_roster_identity_fails_closed():
    with pytest.raises(ValueError, match="CANDIDATE_INVALID_HL_ACCOUNT_IDENTITY"):
        o.merge_candidates([o.CandidateWallet("not-an-address", ("active",))])


# ---------------------------------------------------------------------------
# Row normalisation and the command surface
# ---------------------------------------------------------------------------


def test_funding_and_ledger_rows_keep_exact_decimals():
    since, until = NOW_MS - DAY_MS, NOW_MS
    funding = o.funding_rows(
        WALLETS[0],
        [
            {
                "time": NOW_MS - 1000,
                "hash": "0x" + "c" * 64,
                "delta": {
                    "type": "funding",
                    "coin": "ETH",
                    "usdc": "-0.000000000001",
                    "szi": "3",
                    "fundingRate": "0.0000125",
                },
            }
        ],
        since=since,
        until=until,
        first_known_at_ms=NOW_MS,
    )
    assert funding[0]["payment_usd"] == Decimal("-0.000000000001")
    assert funding[0]["funding_rate"] == Decimal("0.0000125")

    ledger = o.ledger_rows(
        WALLETS[0],
        [
            {
                "time": NOW_MS - 1000,
                "hash": "0x" + "d" * 64,
                "delta": {"deposit": {"usdc": "250.75"}},
            }
        ],
        since=since,
        until=until,
        first_known_at_ms=NOW_MS,
    )
    assert ledger[0]["amount_usd"] == Decimal("250.75")
    assert ledger[0]["token"] == "USDC"

    tagged_ledger = o.ledger_rows(
        WALLETS[0],
        [
            {
                "time": NOW_MS - 1000,
                "hash": "0x" + "e" * 64,
                "delta": {"type": "deposit", "usdc": "125.50"},
            },
            {
                "time": NOW_MS - 500,
                "hash": "0x" + "f" * 64,
                "delta": {
                    "type": "send",
                    "token": "USDC",
                    "amount": "50",
                    "usdcValue": "50.0",
                },
            },
        ],
        since=since,
        until=until,
        first_known_at_ms=NOW_MS,
    )
    assert [row["kind"] for row in tagged_ledger] == ["deposit", "send"]
    assert [row["amount_usd"] for row in tagged_ledger] == [Decimal("125.50"), Decimal("50.0")]
    assert (
        o._ledger_audit(
            [{"time": NOW_MS, "delta": {"type": "deposit", "usdc": "125.50"}}],
            since=NOW_MS - 100,
            until=NOW_MS,
        )["external_deposit_usd_observed"]
        == "125.50"
    )

    with pytest.raises(ValueError, match="FUTURE_OR_OUT_OF_WINDOW_LEDGER"):
        o.ledger_rows(
            WALLETS[0],
            [{"time": NOW_MS + 1, "hash": "0x" + "d" * 64, "delta": {"deposit": {"usdc": "1"}}}],
            since=since,
            until=until,
            first_known_at_ms=NOW_MS,
        )
    with pytest.raises(ValueError, match="INVALID_HL_FUNDING_PAGE"):
        o.funding_rows(WALLETS[0], {}, since=since, until=until, first_known_at_ms=NOW_MS)


def test_incomplete_ledger_classification_and_censoring():
    rows = [{"time": NOW_MS, "delta": {"deposit": {"usdc": "200"}}}]
    assert (
        o._ledger_audit(rows, since=NOW_MS - 100, until=NOW_MS)["external_deposit_usd_observed"]
        == "200"
    )
    assert (
        o._ledger_audit(
            rows + [{"time": NOW_MS, "delta": {"mystery": {}}}],
            since=NOW_MS - 100,
            until=NOW_MS,
        )["external_deposit_usd_observed"]
        is None
    )
    with pytest.raises(ValueError, match="FUTURE_OR_OUT_OF_WINDOW"):
        o._ledger_audit(rows, since=NOW_MS - 1000, until=NOW_MS - 1)
    assert (
        "LEDGER_PAGE_LIMIT_CENSORED"
        in o._ledger_audit(rows * 500, since=NOW_MS, until=NOW_MS)["reasons"]
    )


def test_reject_forged_source_incomplete_time_and_invalid_budget():
    assert o._book_equity(_state(), "unifiedAccount", NOW) is None
    assert o._book_equity(_state(at=NOW_MS + 5 * DAY_MS), "default", NOW) is None
    assert o._book_equity(_state("NaN"), "default", NOW) is None
    assert o._book_equity(_state(at=NOW_MS - 3_600_000), "default", NOW) is None
    with pytest.raises(ValueError, match="UNSAFE_SHARED_IP_WEIGHT_BUDGET"):
        o.WeightBudget(1201)


def test_command_surface_mounts_on_a_facts_subparser(tmp_path):
    import argparse

    parser = argparse.ArgumentParser(prog="copytrade-pm")
    groups = parser.add_subparsers(dest="group", required=True)
    facts = groups.add_parser("facts")
    commands = facts.add_subparsers(dest="command", required=True)
    o.add_arguments(commands.add_parser("capture-health"))
    args = parser.parse_args(
        [
            "facts",
            "capture-health",
            "--roster-db",
            str(tmp_path / "roster.sqlite"),
            "--store",
            str(tmp_path / "facts"),
            "--no-raw-archive",
            "--publish-dir",
            str(tmp_path / "publish"),
        ]
    )
    assert args.group == "facts" and args.command == "capture-health"
    assert args.no_raw_archive is True
    assert args.publish_dir == tmp_path / "publish"
    # The handler refuses to run with no roster before it touches the network.
    args.roster_db = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        o.run(args)


def test_default_provider_is_never_reached_in_tests(tmp_path, monkeypatch):
    seeded_roster(tmp_path)

    def explode(request):  # pragma: no cover - must never run
        raise AssertionError("NETWORK_CALLED")

    monkeypatch.setattr(o, "guarded_info", explode)
    result, _, _ = capture(tmp_path)
    assert result["verified_main_perp_equity"] == 4


def test_zero_hash_hourly_funding_rows_ingest_without_conflict(tmp_path):
    from copytrade_pm.facts import FactIngestor, FactStore, FactStoreError

    with FactStore(tmp_path / "facts", create=True) as facts:
        ingestor = FactIngestor(facts)
        zero_hash = "0x" + "0" * 64
        rows = o.funding_rows(
            WALLETS[0],
            [
                {
                    "time": NOW_MS - 7_200_000,
                    "hash": zero_hash,
                    "delta": {
                        "type": "funding",
                        "coin": "BTC",
                        "usdc": "-1.25",
                        "fundingRate": "0.0001",
                        "szi": "1.0",
                    },
                },
                {
                    "time": NOW_MS - 3_600_000,
                    "hash": zero_hash,
                    "delta": {
                        "type": "funding",
                        "coin": "BTC",
                        "usdc": "0.75",
                        "fundingRate": "-0.0001",
                        "szi": "1.0",
                    },
                },
            ],
            since=NOW_MS - 10_000_000,
            until=NOW_MS,
            first_known_at_ms=NOW_MS,
        )
        ingestor.ingest_rows(
            "funding", rows, source_id="hl-official", source_rank=1, first_known_at_ms=None
        )
        stored = facts.scan("funding", as_of_ms=NOW_MS).collect()
        assert stored.height == 2
        assert facts.verify()["ok"] is True

        conflict = o.funding_rows(
            WALLETS[0],
            [
                {
                    "time": NOW_MS - 3_600_000,
                    "hash": zero_hash,
                    "delta": {
                        "type": "funding",
                        "coin": "BTC",
                        "usdc": "0.99",
                        "fundingRate": "-0.0001",
                        "szi": "1.0",
                    },
                }
            ],
            since=NOW_MS - 10_000_000,
            until=NOW_MS,
            first_known_at_ms=NOW_MS + 1000,
        )
        with pytest.raises(FactStoreError, match="INGEST_CONFLICTING_VALUES"):
            ingestor.ingest_rows(
                "funding",
                conflict,
                source_id="hl-official",
                source_rank=1,
                first_known_at_ms=None,
            )
