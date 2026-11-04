"""One shared, read-only P1/P14 source+market observation cycle.

Uses the existing frozen-registry view, E4 source collector, CCXT Pro public
market collector and private SQLite source/market receipt chains. No financial
event writer is called. Complete wallet equity, traded volume, worker
protection and paper execution remain explicitly unavailable.

This library can be supervised by an external operator after protected
release approval; executing a cycle here does not install a daemon.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, contextmanager
import fcntl
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Awaitable, Callable, Iterator, Mapping

from .pm03_account import Instrument
from .pm_forward_journal import PaperJournal
from .pm_forward_market_stream import BoundedMarketCapture
from .pm_forward_readiness import _source, audit_live_paper_readiness
from .pm_forward_registry_identity import P14, audit_frozen_member_resolution
from .pm_forward_source_campaign import (
    _ALIAS,
    observe_shared_frozen_sources_readonly,
)


@contextmanager
def exclusive_observer_lease(journal: PaperJournal) -> Iterator[None]:
    """One process per private public-observation journal, no file rewrites.

    The financial journal holds its own short per-write lock. This separate
    process lease is deliberately not held by any SQLite transaction and
    cannot be confused with protected OS authorization.
    """
    root = journal.root
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("PAPER_OBSERVER_PRIVATE_ROOT_INVALID")
    descriptor = None
    acquired = False
    try:
        descriptor = os.open(
            root / "paper-observer.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
        ):
            raise ValueError("PAPER_OBSERVER_LEASE_PERMISSION_INVALID")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("PAPER_OBSERVER_ALREADY_RUNNING_FOR_JOURNAL") from exc
        acquired = True
        yield
    except OSError as exc:
        raise ValueError("PAPER_OBSERVER_LEASE_UNAVAILABLE") from exc
    finally:
        if descriptor is not None:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def source_native_inventory(
    journal: PaperJournal, *, expected_parent_hashes: Mapping[str, str]
) -> dict:
    """Extract every witnessed parent/child native position after SHA verification.

    This is an *observed* lower bound, not full account market coverage.
    A missing source or unknown hedge may expand the true target universe.
    """
    uri = "file:" + str(journal.path.resolve()) + "?mode=ro"
    if set(expected_parent_hashes) != {_ALIAS[member] for member in P14}:
        raise ValueError("PAPER_OBSERVER_PARENT_IDENTITY_CENSUS_INVALID")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
        for value in expected_parent_hashes.values()
    ):
        raise ValueError("PAPER_OBSERVER_PARENT_IDENTITY_HASH_INVALID")
    instruments: set[Instrument] = set()
    missing: list[str] = []
    accounts = 0
    with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        for member in P14:
            alias = _ALIAS[member]
            tape = _source(db, alias)
            if expected_parent_hashes[alias] not in tape["account_receipts"]:
                missing.append(member)
            for receipt in tape["account_receipts"].values():
                book = receipt.get("source_book")
                if not isinstance(book, dict) or not isinstance(book.get("positions"), dict):
                    raise ValueError("OBSERVED_SOURCE_NATIVE_POSITION_SCOPE_INVALID")
                accounts += 1
                for native in book["positions"]:
                    inst = Instrument.parse(native)
                    if inst.venue != "hyperliquid" or not inst.market.startswith("mainnet:perp:"):
                        raise ValueError("OBSERVED_SOURCE_NON_NATIVE_PERP")
                    instruments.add(inst)
    ordered = tuple(sorted(instruments, key=lambda inst: inst.key))
    return {
        "schema": "paper_observed_native_inventory_v1",
        "observed_account_count": accounts,
        "missing_parent_aliases": missing,
        "observed_native_instruments": [item.key for item in ordered],
        "observed_native_market_count": len(ordered),
        "source_scope_complete": False,
        "all_hedges_attested": False,
        "whole_wallet_nav_attested": False,
        "instruments": ordered,
    }


async def capture_shared_observer_cycle(
    *,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    journal: PaperJournal,
    seconds_per_account: float = 5,
    max_source_frames: int = 10,
    market_duration_seconds: float = 10,
    max_market_updates: int = 15,
    market_shard_size: int = 8,
    max_native_markets: int = 100,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
    source_capture: Callable[..., Awaitable[dict]] = observe_shared_frozen_sources_readonly,
    market_factory: Callable[..., Any] = BoundedMarketCapture,
) -> dict:
    """One self-contained public-data cycle, no modeled fill and no broker."""
    if not 1 <= market_shard_size <= 10 or not 1 <= max_native_markets <= 100:
        raise ValueError("PAPER_OBSERVER_SHARD_OR_NATIVE_SCOPE_LIMIT_INVALID")
    if not 2 <= seconds_per_account <= 60 or not 1 <= max_source_frames <= 100:
        raise ValueError("PAPER_OBSERVER_SOURCE_BUDGET_INVALID")
    if not 0.5 <= market_duration_seconds <= 120 or not 1 <= max_market_updates <= 1000:
        raise ValueError("PAPER_OBSERVER_MARKET_BUDGET_INVALID")

    observed = await source_capture(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        journal=journal,
        seconds_per_wallet=seconds_per_account,
        max_frames=max_source_frames,
        include_collateral=True,
        now=now,
    )
    if (
        observed.get("status") != "BLOCKED_OBSERVATION_ONLY_NO_TRADE"
        or observed.get("order_route") != "NONE"
    ):
        raise ValueError("PAPER_OBSERVER_SOURCE_POSITIVE_ATTESTATION_UNTRUSTED")
    identity = audit_frozen_member_resolution(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        portfolio_id="P14",
    )
    native = source_native_inventory(
        journal,
        expected_parent_hashes={
            _ALIAS[member["alias"]]: member["address_sha256"] for member in identity["members"]
        },
    )
    selected: tuple[Instrument, ...] = native.pop("instruments")
    shard_reports: list[dict] = []
    failures: list[dict] = []
    if len(selected) > max_native_markets:
        failures.append(
            {
                "reason": "PAPER_OBSERVER_NATIVE_UNIVERSE_EXCEEDS_BOUNDED_BUDGET",
                "required": len(selected),
                "max_allowed": max_native_markets,
            }
        )
    else:
        for shard_number, start in enumerate(range(0, len(selected), market_shard_size), 1):
            shard = selected[start : start + market_shard_size]
            dexes = tuple(
                sorted(
                    {
                        item.market.removeprefix("mainnet:perp:").split("/", 1)[0]
                        for item in shard
                        if item.market != "mainnet:perp:default"
                    }
                )
            )
            try:
                capture = market_factory(shard, journal=journal, hip3_dexes=dexes, now=now)
                result = await capture.run(
                    duration_seconds=market_duration_seconds,
                    max_updates_per_channel=max_market_updates,
                )
                shard_reports.append(
                    {
                        "shard": shard_number,
                        "market_count": len(shard),
                        "requested_markets": [item.key for item in shard],
                        "missing_native_markets": result["missing_native_markets"],
                        "stream_failures": result["stream_failures"],
                        "receipt_counts": result["receipt_counts"],
                        "status": (
                            "DEGRADED"
                            if result["missing_native_markets"] or result["stream_failures"]
                            else "BOUNDED_CAPTURE_ENDED"
                        ),
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures.append(
                    {
                        "shard": shard_number,
                        "requested_markets": [item.key for item in shard],
                        "reason": type(exc).__name__ + ":" + str(exc)[:120],
                    }
                )
    # Use the independent, existing readonly readiness join; never construct
    # market coverage from a count of recently observed quotes alone.
    readiness = {
        portfolio: audit_live_paper_readiness(
            registry_db=registry_db,
            primary_dir=primary_dir,
            secondary_dir=secondary_dir,
            source_db=journal.path,
            market_db=journal.path,
            portfolio_id=portfolio,
            as_of=now(),
        )
        for portfolio in ("P1", "P14")
    }
    if any(item["status"] != "BLOCKED_NO_TRADE" for item in readiness.values()):
        raise ValueError("PAPER_OBSERVER_READINESS_UNEXPECTEDLY_ADMITTED")
    source_capture_gaps = []
    for item in observed["portfolios"]["P14"]["partial_account_observations"]:
        if item.get("partial_receipts", 0) == 0:
            source_capture_gaps.append(
                {"member": item["member"], "reason": "NO_ACCOUNT_BOOK_RECEIPT_THIS_EPOCH"}
            )
        if item.get("errors"):
            source_capture_gaps.append(
                {"member": item["member"], "reason": "SOURCE_CAPTURE_ERRORS_THIS_EPOCH"}
            )
    return {
        "schema": "paper_p1_p14_readonly_observer_cycle_v1",
        "observed_at": now(),
        "status": "BLOCKED_NO_TRADE",
        "shared_source": {
            "unique_source_wallet_count": observed["unique_source_wallet_count"],
            "source_subscription_deduplication": observed["source_subscription_deduplication"],
            "per_portfolio": {
                key: {
                    "unresolved_members": value["unresolved_members"],
                    "observed_member_count": len(value["partial_account_observations"]),
                    "whole_wallet_equity_attested": False,
                }
                for key, value in observed["portfolios"].items()
            },
        },
        "native_inventory": native,
        "market_shards": shard_reports,
        "market_failures": failures,
        "source_capture_gaps": source_capture_gaps,
        "readiness": {
            key: {
                "status": value["status"],
                "reason_codes": value["reason_codes"],
                "required_native_market_count": value["needed_native_market_count"],
                "source_wallet_equity_attested": False,
            }
            for key, value in readiness.items()
        },
        "source_scope_complete": False,
        "trade_volume_complete": False,
        "executable_volume_base": None,
        "real_worker_attested": False,
        "independent_watchdog_attested": False,
        "paper_admitted": False,
        "paper_observed": False,
        "financial_events_committed": 0,
        "broker_orders": 0,
        "order_route": "NONE",
    }


async def run_readonly_observer_epochs(
    *,
    run_cycle: Callable[[], Awaitable[dict]],
    epochs: int,
    pause_seconds: float = 3,
    pause: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict:
    """Bounded retries; a restarted process never implies prior coverage."""
    if not 1 <= epochs <= 20 or not 0 <= pause_seconds <= 120:
        raise ValueError("PAPER_OBSERVER_EPOCH_POLICY_INVALID")
    attempts = []
    for index in range(epochs):
        try:
            result = await run_cycle()
            if result.get("status") != "BLOCKED_NO_TRADE" or result.get("order_route") != "NONE":
                raise ValueError("PAPER_OBSERVER_POSITIVE_FINANCIAL_STATUS_FORBIDDEN")
            gap_count = (
                len(result.get("source_capture_gaps", []))
                + len(result.get("market_failures", []))
                + sum(
                    bool(row.get("stream_failures") or row.get("missing_native_markets"))
                    for row in result["market_shards"]
                )
            )
            attempts.append(
                {
                    "epoch": index + 1,
                    "status": "DEGRADED_OBSERVER_EVIDENCE" if gap_count else "BLOCKED_NO_TRADE",
                    "reason": (
                        "READONLY_SOURCE_OR_MARKET_CAPTURE_GAPS"
                        if gap_count
                        else "SOURCE_NAV_OR_MARKET_CAPACITY_NOT_ATTESTED"
                    ),
                    "current_epoch_capture_gap_count": gap_count,
                    "native_market_count": result["native_inventory"][
                        "observed_native_market_count"
                    ],
                    "market_shards": len(result["market_shards"]),
                    "gap_before_epoch": index > 0,
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            attempts.append(
                {
                    "epoch": index + 1,
                    "status": "DEGRADED_OBSERVER_FAILURE",
                    "reason": type(exc).__name__ + ":" + str(exc)[:160],
                    "gap_before_epoch": index > 0,
                }
            )
        if index + 1 < epochs:
            await pause(pause_seconds)
    return {
        "schema": "paper_p1_p14_readonly_observer_supervision_v1",
        "epochs": attempts,
        "reconnect_gap_count": max(0, len(attempts) - 1),
        "completed_epochs": len(attempts),
        "status": "BLOCKED_NO_TRADE",
        "uninterrupted_prospective_observation_verified": False,
        "protected_worker_attested": False,
        "financial_events_committed": 0,
        "paper_observed": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finite shared P1/P14 public-only observation; NO TRADE or financial events"
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--seconds-per-account", type=float, default=5)
    parser.add_argument("--max-source-frames", type=int, default=10)
    parser.add_argument("--market-duration-seconds", type=float, default=10)
    parser.add_argument("--max-market-updates", type=int, default=15)
    parser.add_argument("--market-shard-size", type=int, default=8)
    parser.add_argument("--pause-seconds", type=float, default=3)
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        part in {".git", ".devspace"} for part in args.state_root.resolve().parts
    ):
        parser.error("observer journal must be outside the worktree at an absolute private path")
    journal = PaperJournal(args.state_root)

    async def run() -> dict:
        return await run_readonly_observer_epochs(
            run_cycle=lambda: capture_shared_observer_cycle(
                registry_db=args.registry,
                primary_dir=args.primary_dir,
                secondary_dir=args.secondary_dir,
                journal=journal,
                seconds_per_account=args.seconds_per_account,
                max_source_frames=args.max_source_frames,
                market_duration_seconds=args.market_duration_seconds,
                max_market_updates=args.max_market_updates,
                market_shard_size=args.market_shard_size,
            ),
            epochs=args.epochs,
            pause_seconds=args.pause_seconds,
        )

    with exclusive_observer_lease(journal):
        print(json.dumps(asyncio.run(run()), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
