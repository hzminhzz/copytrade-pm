"""Synthetic committed roster books for consumer tests."""

from decimal import Decimal
from pathlib import Path

from copytrade_kernel import KnownAtTs
from copytrade_pm.roster import (
    BenchCandidate,
    RosterStore,
    SeatSpec,
    WalletScorecard,
    digest,
    reconcile_roster,
)
from copytrade_pm.roster.sealed import timestamp_ms

AT = "2026-11-04T06:00:00+00:00"
MS = timestamp_ms(AT)
WALLETS = tuple("0x" + f"{i:02x}" * 20 for i in range(1, 9))


def add_account(
    store: RosterStore,
    account_id: str,
    members: dict[str, str],
    *,
    at_ms: int = MS,
    k: dict[str, str] | None = None,
    risk: dict[str, str] | None = None,
    epoch: str = digest("roster fixture epoch"),
):
    at = KnownAtTs(at_ms)
    specs = tuple(
        SeatSpec(seat, Decimal((risk or {}).get(seat, "200")), Decimal("0.45")) for seat in members
    )
    store.register_account(account_id, specs, policy_epoch=epoch, at_ms=at_ms)
    cards = []
    bench = []
    for index, (seat, wallet) in enumerate(members.items()):
        coefficient = Decimal((k or {}).get(seat, "0.04"))
        card = WalletScorecard(
            wallet,
            at,
            Decimal("10000"),
            5,
            Decimal("4"),
            Decimal("0.002"),
            Decimal("0.31"),
            coefficient,
            f"cluster-{index}",
            True,
            (),
            digest(["synthetic", index]),
        )
        cards.append(card)
        bench.append(
            BenchCandidate(
                wallet,
                card.sha,
                coefficient,
                Decimal("0.20") + Decimal(index) / 100,
                card.cluster_id,
                Decimal("1"),
            )
        )
        store.record_scorecard(card, recorded_ms=at_ms)
    store.record_bench(account_id, bench, as_of=at, recorded_ms=at_ms)
    plan = reconcile_roster(
        current=store.book_at(account_id, as_of=at),
        scorecard={card.wallet: card for card in cards},
        bench=bench,
        as_of=at,
    )
    store.commit_plan(plan, committed_ms=at_ms, with_proposal=False)
    assert {lease.seat_id: lease.wallet for lease in plan.next_book.leases} == members
    return store.book_at(account_id, as_of=at)


def database(tmp_path: Path) -> Path:
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True) as store:
        add_account(store, "A", dict(zip(("seat_1", "seat_2", "seat_3"), WALLETS[:3], strict=True)))
    return path
