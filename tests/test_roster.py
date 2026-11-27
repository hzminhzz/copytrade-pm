"""Property proofs for the typed roster: leases, latch, cooldown, FLAT, isolation.

The suite is deterministic and hypothesis-free: :class:`random.Random` scenarios
are generated from fixed seeds and every generated case asserts the same
invariants, so a failure names the seed that produced it. No private registry,
journal or network is read; every fixture is synthetic.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import random
import sqlite3
from typing import Any

import pytest

from copytrade_kernel import KnownAtTs
from copytrade_pm.roster import (
    AllocationMode,
    BenchCandidate,
    CooldownRecord,
    GateFailure,
    OperatorVeto,
    ReleaseBinding,
    RosterCUSUMState,
    RosterStore,
    RosterStoreError,
    SeatBook,
    SeatLease,
    SeatSpec,
    WalletScorecard,
    build_release_proposal,
    digest,
    owner_id,
    reconcile_roster,
)

DAY_MS = 86_400_000
NOW = KnownAtTs(1_800_000_000_000)
CHECKPOINT_POLICY = {
    "name": "cwsa_utc_5m_v3",
    "limits": {
        "max_state_age_ms": 90_000,
        "max_acquisition_ms": 30_000,
        "max_dex_skew_ms": 5_000,
        "publication_grace_ms": 30_000,
    },
    "measurement_sha": digest(["measurement"]),
}
EPOCH = digest(CHECKPOINT_POLICY)
SEATS = (
    SeatSpec("seat_1", Decimal("200"), Decimal("0.45")),
    SeatSpec("seat_2", Decimal("200"), Decimal("0.45")),
    SeatSpec("seat_3", Decimal("200"), Decimal("0.45")),
)
WALLETS = tuple("0x" + f"{index:02x}" * 20 for index in range(1, 9))


def wallet(index: int) -> str:
    return WALLETS[index % len(WALLETS)]


def card(
    index: int,
    *,
    as_of: KnownAtTs = NOW,
    account_value: str = "10000",
    active_days: int = 5,
    markout_bps: str = "4",
    participation: str = "0.002",
    cdar: str = "0.31",
    k: str = "1",
    cluster: str | None = None,
    copyable: bool = True,
    failures: tuple[GateFailure, ...] = (),
) -> WalletScorecard:
    return WalletScorecard(
        wallet=wallet(index),
        as_of=as_of,
        account_value_usd=Decimal(account_value),
        active_days_14d=active_days,
        markout_5m_bps=Decimal(markout_bps),
        p95_participation_1m=Decimal(participation),
        euler_cdar_share=Decimal(cdar),
        suggested_k=Decimal(k),
        cluster_id=cluster or f"c{index}",
        copyable_drift=copyable,
        failures=failures,
        source_sha=digest(["synthetic-source", index]),
    )


def candidate(
    scorecard: WalletScorecard,
    *,
    marginal: str = "0.15",
    distance: str = "1.0",
) -> BenchCandidate:
    return BenchCandidate(
        wallet=scorecard.wallet,
        scorecard_sha=scorecard.sha,
        suggested_k=scorecard.suggested_k,
        marginal_cdar_share=Decimal(marginal),
        cluster_id=scorecard.cluster_id,
        cluster_distance=Decimal(distance),
    )


_OPENED: list[RosterStore] = []


@pytest.fixture(autouse=True)
def _close_stores():
    _OPENED.clear()
    yield
    while _OPENED:
        _OPENED.pop().close()


def open_store(tmp_path: Path, seats: tuple[SeatSpec, ...] = SEATS) -> RosterStore:
    store = RosterStore(tmp_path / "roster.sqlite", create=True)
    store.register_account("cft-10k-paper", seats, policy_epoch=EPOCH, at_ms=NOW.value)
    _OPENED.append(store)
    return store


def occupied_book(store: RosterStore, cards: list[WalletScorecard]) -> SeatBook:
    for item in cards:
        store.record_scorecard(item)
    store.record_bench("cft-10k-paper", [candidate(item) for item in cards], as_of=NOW)
    book = store.book_at("cft-10k-paper", as_of=NOW)
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        as_of=NOW,
    )
    store.commit_plan(plan)
    return store.book_at("cft-10k-paper", as_of=NOW)


def test_observer_health_refuses_changed_trigger_body(tmp_path):
    store = open_store(tmp_path)
    occupied_book(store, [card(0)])
    assert RosterStore.authority_health(store.path)["database_integrity"] == "VERIFIED"
    with closing(sqlite3.connect(store.path)) as con, con:
        con.execute("DROP TRIGGER leases_no_update")
        con.execute("CREATE TRIGGER leases_no_update BEFORE UPDATE ON leases BEGIN SELECT 1; END")
    with pytest.raises(ValueError, match="STREAM_REGISTRY_INTEGRITY_FAILED"):
        RosterStore.authority_health(store.path)


# --------------------------------------------------------------------------
# models: illegal states are unrepresentable
# --------------------------------------------------------------------------


def test_seat_book_refuses_owner_both_leased_and_draining():
    lease = SeatLease("acct", "seat_1", wallet(1), 1, Decimal("1"), NOW.value, digest("card"))
    draining = __import__("copytrade_pm.roster", fromlist=["DrainingOwner"]).DrainingOwner(
        owner=lease.owner,
        wallet=lease.wallet,
        seat_id="seat_1",
        generation=1,
        retired_ms=NOW.value,
        reason=GateFailure.CUSUM_KILL,
    )
    with pytest.raises(ValueError, match="OWNER_BOTH_LEASED_AND_DRAINING"):
        SeatBook(
            "acct",
            NOW,
            EPOCH,
            ((SEATS[0], lease),),
            (draining,),
        )


def test_seat_book_refuses_duplicate_wallet_across_seats():
    first = SeatLease("acct", "seat_1", wallet(1), 1, Decimal("1"), NOW.value, digest("card"))
    second = SeatLease("acct", "seat_2", wallet(1), 1, Decimal("1"), NOW.value, digest("card"))
    with pytest.raises(ValueError, match="DUPLICATE_LEASED_WALLET"):
        SeatBook("acct", NOW, EPOCH, ((SEATS[0], first), (SEATS[1], second)))


def test_lease_owner_matches_signed_mandate_owner_digest():
    lease = SeatLease("acct", "seat_1", wallet(1), 3, Decimal("1"), NOW.value, digest("card"))
    assert lease.owner == digest(["acct", lease.mandate_id, 3])
    assert lease.owner == owner_id("acct", lease.mandate_id, 3)
    assert lease.baseline_required is True


def test_mode_is_flat_when_every_seat_is_vacant():
    book = SeatBook.empty("acct", SEATS, as_of=NOW, policy_epoch=EPOCH)
    assert book.mode is AllocationMode.FLAT
    lease = SeatLease("acct", "seat_1", wallet(1), 1, Decimal("1"), NOW.value, digest("card"))
    partial = SeatBook("acct", NOW, EPOCH, ((SEATS[0], lease), (SEATS[1], None), (SEATS[2], None)))
    assert partial.mode is AllocationMode.PARTIAL
    full = SeatBook(
        "acct",
        NOW,
        EPOCH,
        tuple(
            (
                spec,
                SeatLease(
                    "acct", spec.seat_id, wallet(index), 1, Decimal("1"), NOW.value, digest("c")
                ),
            )
            for index, spec in enumerate(SEATS)
        ),
    )
    assert full.mode is AllocationMode.ACTIVE


def test_cusum_latch_is_terminal_within_an_epoch_and_clears_only_on_a_new_epoch():
    state = RosterCUSUMState.initial(wallet(1), EPOCH)
    latched = state.observe(Decimal("3"), threshold=Decimal("3"), at_ms=NOW.value)
    assert latched.retired_latch is True
    assert latched.retired_reason is GateFailure.CUSUM_KILL
    later = latched.observe(Decimal("0.5"), threshold=Decimal("3"), at_ms=NOW.value + 1)
    assert later.retired_latch is True  # a later episode never self-clears
    assert later.s_neg == latched.s_neg
    with pytest.raises(ValueError, match="CUSUM_LATCH_EPOCH_UNCHANGED"):
        latched.clear_for_epoch(EPOCH, at_ms=NOW.value + 2)
    cleared = latched.clear_for_epoch(digest("epoch-2"), at_ms=NOW.value + 2)
    assert cleared.retired_latch is False and cleared.policy_epoch == digest("epoch-2")


# --------------------------------------------------------------------------
# reconciliation properties (seeded scenarios)
# --------------------------------------------------------------------------


def test_property_empty_bench_is_explicit_flat_and_stays_flat(tmp_path):
    store = open_store(tmp_path)
    book = store.book_at("cft-10k-paper", as_of=NOW)
    plan = reconcile_roster(current=book, as_of=NOW)
    receipt = store.commit_plan(plan)
    assert receipt.changed is False
    assert plan.mode is AllocationMode.FLAT
    assert plan.next_book.mode is AllocationMode.FLAT
    assert plan.trading_authorized is False


def test_property_reconciliation_is_idempotent(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(index) for index in range(3)])
    assert book.mode is AllocationMode.ACTIVE
    again = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        as_of=NOW,
    )
    assert again.changed is False
    assert again.next_book.sha == book.sha
    receipt = store.commit_plan(again)
    assert receipt.changed is False
    assert receipt.sequence == book.sequence


def test_property_sticky_incumbent_beats_better_bench(tmp_path):
    store = open_store(tmp_path, seats=(SEATS[0],))
    incumbent = card(0, k="1", cluster="c0")
    book = occupied_book(store, [incumbent])
    challenger = card(1, k="9", cluster="c9")
    for offset in (1, DAY_MS // 2, DAY_MS):
        plan = reconcile_roster(
            current=book,
            scorecard={incumbent.wallet: incumbent, challenger.wallet: challenger},
            bench=[candidate(challenger, marginal="0.01", distance="9")],
            as_of=KnownAtTs(NOW.value + offset),
        )
        assert plan.evicted == ()
        assert plan.promoted == ()
        assert plan.next_book.wallets == (incumbent.wallet,)
        assert plan.changes == (plan.changes[0],)
        assert plan.changes[0].action == "RETAIN"


def test_property_shuffling_bench_does_not_change_the_choice():
    base = [card(index, k=f"{index + 1}") for index in range(5)]
    bench = [candidate(item, marginal=f"0.{20 - index}") for index, item in enumerate(base)]
    cards = {item.wallet: item for item in base}
    book = SeatBook.empty("acct", SEATS, as_of=NOW, policy_epoch=EPOCH)
    first = reconcile_roster(current=book, scorecard=cards, bench=bench, as_of=NOW)
    rng = random.Random(7)
    for _ in range(20):
        shuffled = bench[:]
        rng.shuffle(shuffled)
        again = reconcile_roster(current=book, scorecard=cards, bench=shuffled, as_of=NOW)
        assert again.next_book.sha == first.next_book.sha


def test_property_veto_evicts_incumbent_and_blocks_admission(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    victim = book.wallets[0]
    veto = store.record_veto(victim, reason="compromised key", actor="operator", at_ms=NOW.value)
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        vetoes=store.active_vetoes(as_of=NOW),
        as_of=NOW,
    )
    assert [change.reason for change in plan.evicted] == [GateFailure.OPERATOR_VETO.value]
    assert victim not in plan.next_book.wallets
    assert victim in plan.next_book.draining_wallets  # the owner drains, the seat is freed
    assert plan.next_book.draining[0].wallet == victim
    # The veto is merged into the stored scorecard at read time.
    assert GateFailure.OPERATOR_VETO in store.latest_scorecard(as_of=NOW)[victim].failures
    # Expired veto no longer evicts, and is no longer merged.
    later = KnownAtTs(NOW.value + DAY_MS)
    assert store.revoke_veto(victim, at_ms=NOW.value + 1) == 1
    expired = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=later),
        vetoes=(OperatorVeto(victim, "x", "operator", NOW.value, expires_ms=NOW.value + 1),),
        as_of=later,
    )
    assert expired.evicted == ()
    assert veto.reason == "compromised key"


def test_property_eviction_promotes_immediately_with_a_new_generation_owner(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    evicted_owner = book.leases[0].owner
    evicted_wallet = book.leases[0].wallet
    replacement = card(4, k="2", cluster="c4")
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW) | {replacement.wallet: replacement},
        bench=[candidate(replacement, marginal="0.1")],
        latches={
            evicted_wallet: RosterCUSUMState.initial(evicted_wallet, EPOCH).observe(
                Decimal("3"), threshold=Decimal("3"), at_ms=NOW.value
            )
        },
        as_of=NOW,
    )
    assert [change.action for change in plan.changes].count("PROMOTE") == 1
    assert plan.next_book.wallets[0] == replacement.wallet
    assert plan.next_book.leases[0].generation == 2
    assert plan.next_book.leases[0].owner != evicted_owner
    assert plan.next_book.draining_owners == (evicted_owner,)
    receipt = store.commit_plan(plan)
    assert receipt.changed is True
    stored = store.book_at("cft-10k-paper", as_of=NOW)
    assert stored.sequence == receipt.sequence
    assert evicted_owner in stored.draining_owners
    assert evicted_owner not in {lease.owner for lease in stored.leases}


def test_property_latched_wallet_is_never_promoted(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0)])
    latched_wallet = card(2, k="9", cluster="c2")
    state = RosterCUSUMState.initial(latched_wallet.wallet, EPOCH).observe(
        Decimal("4"), threshold=Decimal("3"), at_ms=NOW.value
    )
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW) | {latched_wallet.wallet: latched_wallet},
        bench=[candidate(latched_wallet, marginal="0.01")],
        latches={latched_wallet.wallet: state},
        as_of=NOW,
    )
    assert latched_wallet.wallet not in plan.next_book.wallets
    assert plan.next_book.mode is AllocationMode.PARTIAL


def test_property_cooldown_requires_fourteen_continuous_days_and_readmission_floor(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0)])
    evicted = book.leases[0]
    reason = GateFailure.ACCOUNT_VALUE_BELOW_FLOOR
    plan = reconcile_roster(
        current=book,
        scorecard={evicted.wallet: card(0, account_value="900", failures=(reason,))},
        as_of=NOW,
    )
    assert plan.evicted
    assert plan.mode is AllocationMode.FLAT
    store.commit_plan(plan)
    assert store.cooldown(evicted.wallet) is not None

    readmit = card(0, account_value="6000", cluster="c0")
    cooldown = CooldownRecord(evicted.wallet, NOW.value, NOW.value, reason)
    thirteen_days = KnownAtTs(NOW.value + 13 * DAY_MS)
    early = reconcile_roster(
        current=store.book_at("cft-10k-paper", as_of=thirteen_days),
        scorecard={readmit.wallet: readmit},
        bench=[candidate(readmit)],
        cooldowns=(cooldown,),
        as_of=thirteen_days,
    )
    assert early.next_book.mode is AllocationMode.FLAT

    fourteen_days = KnownAtTs(NOW.value + 14 * DAY_MS)
    ready_card = card(0, as_of=fourteen_days, account_value="6000", cluster="c0")
    late = reconcile_roster(
        current=store.book_at("cft-10k-paper", as_of=fourteen_days),
        scorecard={ready_card.wallet: ready_card},
        bench=[candidate(ready_card)],
        cooldowns=(cooldown,),
        as_of=fourteen_days,
    )
    assert late.next_book.mode is AllocationMode.PARTIAL
    assert late.next_book.wallets == (ready_card.wallet,)
    assert late.next_book.leases[0].generation == 2  # old generation is never reused

    # Below the 5,000 re-admission floor the cooldown is not enough.
    cheap = card(0, as_of=fourteen_days, account_value="4999", cluster="c0")
    below_floor = reconcile_roster(
        current=store.book_at("cft-10k-paper", as_of=fourteen_days),
        scorecard={cheap.wallet: cheap},
        bench=[candidate(cheap)],
        cooldowns=(cooldown,),
        as_of=fourteen_days,
    )
    assert below_floor.next_book.mode is AllocationMode.FLAT


def test_property_orthogonality_and_cdar_limits_block_promotion():
    book = SeatBook.empty("acct", SEATS, as_of=NOW, policy_epoch=EPOCH)
    seated = card(0, cluster="shared")
    same_cluster = card(1, cluster="shared")
    heavy = card(2, cluster="other", k="3")
    plan = reconcile_roster(
        current=book,
        scorecard={seated.wallet: seated, same_cluster.wallet: same_cluster, heavy.wallet: heavy},
        bench=[
            candidate(seated, marginal="0.05"),
            candidate(same_cluster, marginal="0.10"),
            candidate(heavy, marginal="0.9"),
        ],
        as_of=NOW,
    )
    assert plan.next_book.wallets == (seated.wallet,)
    assert plan.next_book.mode is AllocationMode.PARTIAL


def test_bench_candidate_rank_key_prefers_lowest_cdar_then_highest_k():
    low_cdar_low_k = BenchCandidate(
        wallet(0), digest("a"), Decimal("0.5"), Decimal("0.05"), "c0", Decimal("1")
    )
    low_cdar_high_k = BenchCandidate(
        wallet(1), digest("b"), Decimal("2.0"), Decimal("0.05"), "c1", Decimal("1")
    )
    high_cdar = BenchCandidate(
        wallet(2), digest("c"), Decimal("9.0"), Decimal("0.40"), "c2", Decimal("1")
    )
    ordered = sorted([high_cdar, low_cdar_low_k, low_cdar_high_k], key=lambda item: item.rank_key)
    assert [item.wallet for item in ordered] == [wallet(1), wallet(0), wallet(2)]


def test_reconcile_roster_k_overrides_decouples_seat_k_from_scorecard():
    book = SeatBook.empty("acct", SEATS[:1], as_of=NOW, policy_epoch=EPOCH)
    candidate_card = card(0, k="1.5")
    plan = reconcile_roster(
        current=book,
        scorecard={candidate_card.wallet: candidate_card},
        bench=[candidate(candidate_card, marginal="0.1")],
        as_of=NOW,
        k_overrides={f"  {candidate_card.wallet.upper()}  ": Decimal("0.25")},
    )
    assert plan.next_book.leases[0].k == Decimal("0.25")
    for bad_k in (Decimal("0"), Decimal("-0.1"), Decimal("11")):
        with pytest.raises(ValueError, match="INVALID_FIXED_K"):
            reconcile_roster(
                current=book,
                scorecard={candidate_card.wallet: candidate_card},
                bench=[candidate(candidate_card, marginal="0.1")],
                as_of=NOW,
                k_overrides={candidate_card.wallet: bad_k},
            )


def test_property_negative_markout_and_dormancy_evict(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    first, second = book.leases
    plan = reconcile_roster(
        current=book,
        scorecard={
            first.wallet: card(0, markout_bps="-3", failures=(GateFailure.NEGATIVE_5M_MARKOUT,)),
            second.wallet: card(1, active_days=0, failures=(GateFailure.NO_ACTIVE_FILLS,)),
        },
        as_of=NOW,
    )
    assert {change.reason for change in plan.evicted} == {
        GateFailure.NEGATIVE_5M_MARKOUT.value,
        GateFailure.NO_ACTIVE_FILLS.value,
    }
    assert plan.mode is AllocationMode.FLAT


def test_property_missing_scorecard_never_evicts_or_flatlines(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0)])
    plan = reconcile_roster(current=book, as_of=NOW)
    assert plan.evicted == ()
    assert plan.next_book.wallets == book.wallets
    assert any(warning.startswith("SCORECARD_MISSING") for warning in plan.warnings)


def test_property_settled_draining_owner_is_released(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    evicted_owner = book.leases[0].owner
    evicted_wallet = book.leases[0].wallet
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW)
        | {evicted_wallet: card(0, failures=(GateFailure.CUSUM_KILL,))},
        as_of=NOW,
    )
    store.commit_plan(plan)
    after = store.book_at("cft-10k-paper", as_of=NOW)
    assert evicted_owner in after.draining_owners
    settled = reconcile_roster(
        current=after,
        scorecard=store.latest_scorecard(as_of=NOW),
        settled_owners=(evicted_owner,),
        as_of=KnownAtTs(NOW.value + 1),
    )
    assert settled.next_book.draining_owners == ()
    # Positions settled: the owner leaves the draining set but never returns to a seat.
    assert evicted_owner not in {lease.owner for lease in settled.next_book.leases}


def test_property_random_scenarios_preserve_book_invariants():
    rng = random.Random(424242)
    for _ in range(200):
        cards = [card(index) for index in range(6)]
        failures = rng.choice(
            [(), (GateFailure.NEGATIVE_5M_MARKOUT,), (GateFailure.NO_ACTIVE_FILLS,)]
        )
        cards[0] = card(0, failures=failures, account_value=rng.choice(["900", "6000"]))
        bench = [candidate(item, marginal=str(round(rng.uniform(0.01, 0.44), 3))) for item in cards]
        rng.shuffle(bench)
        vetoes = (
            (OperatorVeto(cards[1].wallet, "r", "op", NOW.value),) if rng.random() < 0.3 else ()
        )
        book = SeatBook.empty("acct", SEATS, as_of=NOW, policy_epoch=EPOCH)
        plan = reconcile_roster(
            current=book,
            scorecard={item.wallet: item for item in cards},
            bench=bench,
            vetoes=vetoes,
            as_of=NOW,
        )
        next_book = plan.next_book
        next_book.validate()
        assert set(next_book.wallets).isdisjoint(next_book.draining_wallets)
        assert set(next_book.draining_owners).isdisjoint(
            {lease.owner for lease in next_book.leases}
        )
        assert next_book.mode is not None
        assert plan.trading_authorized is False
        # Re-applying the same evidence and clock is a fixed point.
        again = reconcile_roster(
            current=next_book,
            scorecard={item.wallet: item for item in cards},
            bench=bench,
            vetoes=vetoes,
            as_of=NOW,
        )
        assert again.next_book.sha == next_book.sha


# --------------------------------------------------------------------------
# store behaviour
# --------------------------------------------------------------------------


def test_store_is_read_only_unless_opened_writable(tmp_path):
    store = open_store(tmp_path)
    store.close()
    reader = RosterStore(tmp_path / "roster.sqlite")
    with pytest.raises(RosterStoreError, match="ROSTER_READ_ONLY"):
        reader.record_scorecard(card(0))
    reader.close()


def test_store_missing_file_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        RosterStore(tmp_path / "absent.sqlite")


def test_store_scorecard_and_bench_recording_is_idempotent(tmp_path):
    store = open_store(tmp_path)
    first = card(0)
    assert store.record_scorecard(first) == store.record_scorecard(first) == first.sha
    assert store.health()["counts"]["scorecards"] == 1
    bench = [candidate(first)]
    assert store.record_bench("cft-10k-paper", bench, as_of=NOW) == store.record_bench(
        "cft-10k-paper", bench, as_of=NOW
    )
    assert store.health()["counts"]["bench"] == 1


def test_store_books_are_append_only(tmp_path):
    import sqlite3

    store = open_store(tmp_path)
    occupied_book(store, [card(0)])
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ROSTER_BOOK"):
        store._con.execute("UPDATE books SET as_of_ms=0")  # noqa: SLF001
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ROSTER_LEASE"):
        store._con.execute("DELETE FROM leases")  # noqa: SLF001


def test_store_rejects_a_plan_that_precedes_the_committed_book(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0)])
    stale = reconcile_roster(
        current=SeatBook.empty("cft-10k-paper", SEATS, as_of=NOW, policy_epoch=EPOCH),
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        as_of=NOW,
    )
    with pytest.raises(ValueError, match="PLAN_PRECEDES_COMMITTED_BOOK"):
        store.commit_plan(stale)
    assert store.book_at("cft-10k-paper", as_of=NOW).sha == book.sha


def test_store_account_registration_refuses_seat_or_epoch_drift(tmp_path):
    store = open_store(tmp_path)
    with pytest.raises(ValueError, match="ACCOUNT_POLICY_EPOCH_DRIFT"):
        store.register_account("cft-10k-paper", SEATS, policy_epoch=digest("other"))
    with pytest.raises(ValueError, match="ACCOUNT_SEATS_DRIFT"):
        store.register_account(
            "cft-10k-paper",
            (SeatSpec("seat_9", Decimal("100"), Decimal("0.4")),),
            policy_epoch=EPOCH,
        )


def test_store_inventory_sha_tracks_evidence(tmp_path):
    store = open_store(tmp_path)
    before = store.inventory_sha()
    store.record_scorecard(card(0))
    after = store.inventory_sha()
    assert before != after
    assert len(after) == 64
    assert store.verify()["ok"] is True
    assert store.health()["database_integrity"] == "VERIFIED"


def test_store_clear_epoch_drops_only_other_epoch_latches(tmp_path):
    store = open_store(tmp_path)
    store.observe_cusum(wallet(0), "3", threshold="3", policy_epoch=EPOCH, at_ms=NOW.value)
    assert store.latched_wallets() == (wallet(0),)
    with pytest.raises(ValueError, match="CUSUM_LATCH_EPOCH_UNCHANGED"):
        store.clear_epoch(EPOCH)
    new_epoch = digest("epoch-2")
    assert store.clear_epoch(new_epoch, at_ms=NOW.value) == 1
    assert store.latched_wallets(policy_epoch=new_epoch) == ()
    assert store.latched_wallets() == (wallet(0),)  # historical latch is retained
    assert store.policy_epoch("cft-10k-paper") == new_epoch


def test_historical_scorecard_does_not_see_future_cusum_latch(tmp_path):
    store = open_store(tmp_path)
    first = card(0)
    store.record_scorecard(first)
    store.observe_cusum(first.wallet, "3", threshold="3", policy_epoch=EPOCH, at_ms=NOW.value + 1)
    assert store.latest_scorecard(as_of=NOW)[first.wallet] == first
    later = store.latest_scorecard(as_of=KnownAtTs(NOW.value + 1))
    assert GateFailure.CUSUM_KILL in later[first.wallet].failures


def test_store_veto_expiry_and_revocation(tmp_path):
    store = open_store(tmp_path)
    veto = store.record_veto(wallet(0), reason="r", actor="op", at_ms=NOW.value)
    assert store.vetoed_wallets(as_of=NOW) == frozenset({veto.wallet})
    assert store.vetoed_wallets(as_of=KnownAtTs(NOW.value - 1)) == frozenset()
    assert store.revoke_veto(wallet(0), at_ms=NOW.value + 5) == 1
    assert store.vetoed_wallets(as_of=KnownAtTs(NOW.value + 5)) == frozenset()


# --------------------------------------------------------------------------
# release proposals (unsigned) end to end
# --------------------------------------------------------------------------


def binding_for(book: SeatBook, *, generation: int = 1) -> ReleaseBinding:
    scopes = {
        lease.wallet: {
            "schema_version": 3,
            "source_id": lease.wallet,
            "account_sha": digest(["account", lease.wallet]),
            "generation": digest(["source-generation", lease.wallet]),
            "selection_sha": digest(["selection", lease.wallet]),
            "dexes": ["default"],
        }
        for lease in book.leases
    }
    return ReleaseBinding(
        account_id=book.account_id,
        generation=generation,
        research_commit="a" * 40,
        decision_sha=digest(["decision"]),
        selection_known_at_ms=NOW.value - DAY_MS,
        source_mode="SYNTHETIC",
        risk_policy_sha=digest(["risk-policy"]),
        rulebook_sha=digest(["rulebook"]),
        checkpoint_policy=CHECKPOINT_POLICY,
        checkpoint_scopes=scopes,
        allowed_markets={
            lease.seat_id: ("hyperliquid/mainnet:perp:BTC/USD",) for lease in book.leases
        },
        created_ms=NOW.value - 1_000,
        expires_at_ms=NOW.value + DAY_MS,
    )


def test_release_proposal_is_unsigned_and_matches_the_guardian_contract(tmp_path):
    from copytrade_kernel import CopyMandateSpec

    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    binding = binding_for(book)
    store.record_release_binding(binding)
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        as_of=KnownAtTs(NOW.value + 1_000),
    )
    receipt = store.commit_plan(plan, committed_ms=NOW.value + 1_000)
    assert receipt.proposal_state == "STAGED"
    proposal = store.proposals("cft-10k-paper")[-1]
    payload = proposal.payload_json
    assert "signature" not in payload and "authority" not in payload
    assert payload["schema"] == "portfolio_release_v2"
    assert payload["account_binding"] == "cft-10k-paper"
    assert payload["definition_sha"] == digest(payload["members"])
    assert payload["source_sha"] == digest(
        {
            key: payload[key]
            for key in (
                "research_commit",
                "decision_sha",
                "inventory_sha",
                "definition_sha",
                "selection_known_at_ms",
            )
        }
    )
    assert payload["batch_seconds"] == 300
    assert payload["source_mode"] == "SYNTHETIC"
    for mandate in payload["mandates"]:
        spec = CopyMandateSpec.parse(mandate)
        assert spec.account_id == "cft-10k-paper"
        assert spec.generation >= 1
        assert spec.policy_epoch == binding.policy_epoch
    # One proposal per UTC day: re-proposing the same day keeps the first body.
    assert store.stage_proposal(proposal) == proposal.sha
    assert store.health()["counts"]["proposals"] == 1


def test_release_proposal_requires_a_binding_and_a_non_flat_book(tmp_path):
    store = open_store(tmp_path)
    book = store.book_at("cft-10k-paper", as_of=NOW)
    plan = reconcile_roster(current=book, as_of=NOW)
    receipt = store.commit_plan(plan, committed_ms=NOW.value)
    assert receipt.proposal_sha is None
    assert receipt.proposal_state == "UNCHANGED"  # zero occupied seats: nothing to sign
    flat_binding = ReleaseBinding(
        account_id="cft-10k-paper",
        generation=1,
        research_commit="a" * 40,
        decision_sha=digest(["decision"]),
        selection_known_at_ms=NOW.value - DAY_MS,
        source_mode="SYNTHETIC",
        risk_policy_sha=digest(["risk-policy"]),
        rulebook_sha=digest(["rulebook"]),
        checkpoint_policy=CHECKPOINT_POLICY,
        checkpoint_scopes={"0x" + "00" * 20: {"generation": digest(["g"])}},
        allowed_markets={"seat_1": ("hyperliquid/mainnet:perp:BTC/USD",)},
        created_ms=NOW.value - 1_000,
        expires_at_ms=NOW.value + DAY_MS,
    )
    with pytest.raises(ValueError, match="ROSTER_FLAT_NO_RELEASE"):
        build_release_proposal(
            book,
            flat_binding,
            inventory_sha=digest(["inventory"]),
            plan_sha=plan.sha,
        )


def test_proposal_refuses_a_selection_unknown_at_release_time(tmp_path):
    store = open_store(tmp_path)
    book = occupied_book(store, [card(0)])
    binding = replace(binding_for(book), selection_known_at_ms=NOW.value + 1)
    with pytest.raises(ValueError, match="RELEASE_SELECTION_NOT_KNOWN"):
        build_release_proposal(
            book,
            binding,
            inventory_sha=store.inventory_sha(),
            plan_sha=digest("plan"),
            created_ms=NOW.value,
        )


def test_roster_promotion_requires_signed_predecessor_retirement(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from copytrade_pm.pm_forward_journal import PaperJournal
    from copytrade_pm.pm_mandate import SignedMandate, state_sha
    from copytrade_pm.production_manifest import sign

    store = open_store(tmp_path, seats=SEATS[:1])
    first = card(0)
    current = occupied_book(store, [first])
    binding = binding_for(current)
    prior = build_release_proposal(
        current,
        binding,
        inventory_sha=store.inventory_sha(),
        plan_sha=digest("prior"),
        created_ms=NOW.value,
    )
    current_mandate = SignedMandate.parse(prior.payload_json["mandates"][0])
    key = Ed25519PrivateKey.generate()
    journal = PaperJournal(tmp_path / "paper")
    active = journal.activate_copy_mandate(
        sign(current_mandate.data, key, "copy-mandate-v1"),
        key.public_key(),
        account_id=current.account_id,
        at_ms=binding.created_ms - 1,
    )
    assert active.phase == "AWAITING_BASELINE"

    later = KnownAtTs(NOW.value + 300_000)
    replacement = card(1, as_of=later)
    veto = OperatorVeto(
        first.wallet, reason="synthetic eviction", actor="test", created_ms=later.value
    )
    plan = reconcile_roster(
        current=current,
        as_of=later,
        scorecard={first.wallet: first, replacement.wallet: replacement},
        bench=(candidate(replacement),),
        vetoes=(veto,),
    )
    assert plan.next_book.draining[0].owner == current_mandate.owner
    successor = build_release_proposal(
        plan.next_book,
        replace(binding_for(plan.next_book, generation=2), created_ms=later.value),
        inventory_sha=store.inventory_sha(),
        plan_sha=plan.sha,
        created_ms=later.value,
    )
    successor_mandate = SignedMandate.parse(successor.payload_json["mandates"][0])
    assert successor_mandate.owner != current_mandate.owner
    with pytest.raises(ValueError, match="MANDATE_OPENING_INTERVAL_OVERLAP"):
        journal.activate_copy_mandate(
            sign(successor_mandate.data, key, "copy-mandate-v1"),
            key.public_key(),
            account_id=current.account_id,
            at_ms=later.value - 1,
        )
    assert journal.copy_mandate_state(current_mandate.owner) == active

    retirement = sign(
        {
            "schema": "copy_mandate_control_v1",
            "owner": current_mandate.owner,
            "mandate_sha": current_mandate.sha,
            "predecessor_sha": state_sha(active),
            "event": "RETIRE",
            "issued_ms": later.value - 1,
            "expires_ms": later.value + 1,
            "nonce": digest("roster-predecessor-retirement"),
        },
        key,
        "copy-mandate-control-v1",
    )
    retired = journal.control_copy_mandate(retirement, key.public_key(), at_ms=later.value - 1)
    assert retired.phase == "RETIRED"
    promoted = journal.activate_copy_mandate(
        sign(successor_mandate.data, key, "copy-mandate-v1"),
        key.public_key(),
        account_id=current.account_id,
        at_ms=later.value - 1,
    )
    assert promoted.phase == "AWAITING_BASELINE"
    reopened = PaperJournal(journal.root)
    assert reopened.copy_mandate_state(current_mandate.owner) == retired
    assert reopened.copy_mandate_state(successor_mandate.owner) == promoted


def test_release_proposal_reports_a_missing_binding_on_an_occupied_book(tmp_path):
    store = open_store(tmp_path)
    for item in (card(0), card(1)):
        store.record_scorecard(item)
    store.record_bench("cft-10k-paper", [candidate(card(0)), candidate(card(1))], as_of=NOW)
    book = store.book_at("cft-10k-paper", as_of=NOW)
    plan = reconcile_roster(
        current=book,
        scorecard=store.latest_scorecard(as_of=NOW),
        bench=store.latest_bench("cft-10k-paper", as_of=NOW),
        as_of=NOW,
    )
    receipt = store.commit_plan(plan, committed_ms=NOW.value)
    assert receipt.proposal_sha is None
    assert receipt.proposal_state == "BLOCKED_RELEASE_BINDING_MISSING"


def test_release_proposal_signs_and_verifies_with_production_manifest(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    from copytrade_pm.production_manifest import sign, verify
    from copytrade_pm.roster import finalise_payload

    store = open_store(tmp_path)
    book = occupied_book(store, [card(0), card(1)])
    binding = binding_for(book)
    proposal = build_release_proposal(
        book,
        binding,
        inventory_sha=store.inventory_sha(),
        plan_sha=digest(["plan"]),
        created_ms=NOW.value + 500,
    )
    store.stage_proposal(proposal)
    key = Ed25519PrivateKey.generate()
    authority_sha = __import__("hashlib").sha256(key.public_key().public_bytes_raw()).hexdigest()
    envelope = sign(finalise_payload(proposal.payload_json, authority_sha), key, "approver")
    store.mark_proposal_signed(proposal.sha, envelope_sha=digest(envelope))
    recovered = verify(
        envelope,
        Ed25519PublicKey.from_public_bytes(key.public_key().public_bytes_raw()),
        "approver",
    )
    assert recovered == finalise_payload(proposal.payload_json, authority_sha)
    assert recovered["definition_sha"] == digest(recovered["members"])


def test_roster_layer_imports_without_research_stack():
    import subprocess
    import sys

    code = (
        "import sys; import copytrade_pm.roster as r; "
        "blocked=[m for m in ('polars','pandas','pydantic','numpy') if m in sys.modules]; "
        "print(blocked)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "[]"


def _json_round_trip(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


@pytest.mark.parametrize(
    "table,column",
    [
        ("books", "book_sha"),
        ("scorecards", "scorecard_sha"),
        ("bench", "bench_sha"),
        ("policies", "policy_sha"),
    ],
)
def test_authority_health_rehashes_all_evidence(tmp_path, table, column):
    store = open_store(tmp_path)
    occupied_book(store, [card(0)])
    store.seal_policy(
        "cft-10k-paper", generation=1, envelope={"synthetic": True}, known_at_ms=NOW.value
    )
    with closing(sqlite3.connect(store.path)) as con, con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name=?", (f"{table}_no_update",)
        ).fetchone()
        if ddl:
            con.execute(f"DROP TRIGGER {table}_no_update")
        con.execute(f"UPDATE {table} SET {column}=?", ("a" * 64,))
        if ddl:
            con.execute(ddl[0])
    with pytest.raises(ValueError, match="STREAM_REGISTRY_INTEGRITY_FAILED"):
        RosterStore.authority_health(store.path)


def test_authority_health_refuses_missing_symlink_and_wrong_version(tmp_path):
    store = open_store(tmp_path)
    link = tmp_path / "link.sqlite"
    link.symlink_to(store.path)
    for path in (link, tmp_path / "missing.sqlite"):
        with pytest.raises(ValueError, match="STREAM_REGISTRY_FILE_INVALID"):
            RosterStore.authority_health(path)
    with closing(sqlite3.connect(store.path)) as con, con:
        con.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    with pytest.raises(ValueError, match="STREAM_REGISTRY_INTEGRITY_FAILED"):
        RosterStore.authority_health(store.path)
