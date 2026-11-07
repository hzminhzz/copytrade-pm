"""One shared, public CCXT Pro L2 WebSocket journal for observed paper portfolios.

Reuses the existing continuous CCXT ingress clock, stream checkpoints, native
market parser and append-only PaperJournal. No keys, trades, finance or broker.
All consumers keep reading the same journal; price age still fails closed.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
from types import SimpleNamespace
from typing import Callable, Iterator

from .pm03_account import Instrument, clock, digest
from .pm_forward_ccxt_market import _now
from .pm_forward_continuous import run_ccxt_markets
from .pm_forward_continuous_transport import ConnectionBudget, SerialWriter
from .pm_forward_journal import PaperJournal
from .pm_forward_observer import source_native_inventory
from .pm_forward_registry_identity import audit_frozen_member_resolution
from .pm_forward_source_campaign import _ALIAS

MAX_MARKETS = 64
DEFAULT_INTERVAL = 5.0


def native_scope(
    source_db: Path,
    *,
    registry_db: Path,
    primary_dir: Path,
    secondary_dir: Path,
    max_markets: int = MAX_MARKETS,
) -> tuple[Instrument, ...]:
    """Derive exact P14-observed native scope from owner-private identity proof."""
    if not 1 <= max_markets <= MAX_MARKETS:
        raise ValueError("QUOTE_SCOPE_BUDGET_INVALID")
    db = Path(source_db)
    if db.is_symlink() or not db.is_file():
        raise ValueError("QUOTE_SOURCE_JOURNAL_MISSING")
    identity = audit_frozen_member_resolution(
        registry_db=registry_db,
        primary_dir=primary_dir,
        secondary_dir=secondary_dir,
        portfolio_id="P14",
    )
    if len(identity["members"]) != 5:
        raise ValueError("QUOTE_SOURCE_MEMBER_CENSUS_INCOMPLETE")
    expected = {_ALIAS[row["alias"]]: row["address_sha256"] for row in identity["members"]}
    inventory = source_native_inventory(
        SimpleNamespace(path=db), expected_parent_hashes=expected,
    )
    if inventory["missing_parent_aliases"]:
        raise ValueError("QUOTE_SOURCE_PARENT_OBSERVATION_MISSING")
    markets = inventory["instruments"]
    if not markets or len(markets) > max_markets:
        raise ValueError("QUOTE_NATIVE_SCOPE_BUDGET_EXCEEDED")
    return markets


def live_quote_health(
    source_db: Path, instruments: tuple[Instrument, ...], at: str | None = None,
    *, max_age_seconds: int = 20,
) -> dict:
    """Read-only age/coverage; it does not invent a heartbeat quote."""
    current = clock(at or _now())
    if not 1 <= max_age_seconds <= 120:
        raise ValueError("QUOTE_HEALTH_MAX_AGE_INVALID")
    uri = "file:" + str(Path(source_db).resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=3.0)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            "SELECT instrument,known_at,chain_sha FROM market_quote_heads"
        ).fetchall()
    observed = {key: (clock(known), sha) for key, known, sha in rows}
    fresh = []
    stale = []
    absent = []
    for inst in instruments:
        row = observed.get(inst.key)
        if row is None:
            absent.append(inst.key)
            continue
        age = (current - row[0]).total_seconds()
        if 0 <= age <= max_age_seconds:
            fresh.append(inst.key)
        else:
            stale.append(inst.key)
    return {
        "schema": "paper_shared_ccxt_quote_health_v1",
        "as_of": current.isoformat(),
        "source": "CCXT_PRO_HYPERLIQUID_PUBLIC_L2",
        "status": "FRESH_MARKET_COVERAGE" if len(fresh) == len(instruments)
                  else "DEGRADED_MARKET_COVERAGE",
        "requested": len(instruments),
        "fresh": len(fresh), "stale": len(stale), "missing": len(absent),
        "stale_instruments": stale, "missing_instruments": absent,
        "max_age_seconds": max_age_seconds,
        "modeled_only": True, "order_route": "NONE",
    }


@contextmanager
def _single_writer(root: Path) -> Iterator[None]:
    """Independent lease for one CCXT writer, not source observer ownership."""
    base = Path(root)
    if base.is_symlink() or not base.is_dir() or base.stat().st_mode & 0o077:
        raise ValueError("CCXT_QUOTE_ROOT_NOT_PRIVATE")
    path = base / "paper-ccxt-quote-writer.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        mode = os.fstat(fd)
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077:
            raise ValueError("CCXT_QUOTE_LOCK_NOT_PRIVATE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("CCXT_QUOTE_WRITER_ALREADY_RUNNING") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


async def serve(
    journal: PaperJournal,
    *,
    scope: Callable[[], tuple[Instrument, ...]],
    stop: asyncio.Event,
    min_interval_seconds: float = DEFAULT_INTERVAL,
    refresh_seconds: int = 300,
    report_seconds: float = 15,
    max_db_bytes: int = 12_000_000_000,
    factory=None,
) -> None:
    """Serial CCXT quote writer, bounded rates, restart-safe dynamic scope."""
    if not 1 <= min_interval_seconds <= 20:
        raise ValueError("CCXT_QUOTE_INTERVAL_INVALID")
    if not 30 <= refresh_seconds <= 1800 or not 1 <= report_seconds <= 60:
        raise ValueError("CCXT_QUOTE_LIFECYCLE_BUDGET_INVALID")
    if not 100_000_000 <= max_db_bytes <= 100_000_000_000:
        raise ValueError("CCXT_QUOTE_DISK_BUDGET_INVALID")
    from time import monotonic

    # The source and market producers share a per-transaction SQLite lease.
    # A short collision rejects before BEGIN; bounded retries are safe here.
    async with SerialWriter(max_pending=512, busy_retries=20) as writer:
        prior_scope: tuple[Instrument, ...] | None = None
        while not stop.is_set():
            markets = scope()
            if not markets or len(markets) > MAX_MARKETS:
                raise ValueError("CCXT_QUOTE_UNAPPROVED_NATIVE_SCOPE")
            prior_scope = markets
            stream_stop = asyncio.Event()
            worker = asyncio.create_task(
                run_ccxt_markets(
                    markets, journal=journal, writer=writer, stop=stream_stop, now=_now,
                    scope_sha=digest([x.key for x in markets]),
                    limiter=ConnectionBudget(per_minute=6), factory=factory,
                    channels=("quote",), min_quote_interval_seconds=min_interval_seconds,
                ),
                name="ccxt-quote-market-stream",
            )
            begin = monotonic()
            try:
                while not stop.is_set() and not worker.done():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=report_seconds)
                    except TimeoutError:
                        pass
                    if writer.failed is not None:
                        raise RuntimeError("CCXT_QUOTE_SQLITE_WRITER_FAILED") from writer.failed
                    if journal.path.stat().st_size > max_db_bytes:
                        raise ValueError("CCXT_QUOTE_JOURNAL_DISK_LIMIT")
                    health = live_quote_health(journal.path, markets)
                    # Logs are aggregated; never include source-wallet addresses.
                    health.pop("stale_instruments")
                    health.pop("missing_instruments")
                    health["journal_only"] = True
                    print(json.dumps(health, sort_keys=True), flush=True)
                    if monotonic() - begin >= refresh_seconds:
                        updated = scope()
                        begin = monotonic()
                        if updated != prior_scope:
                            break
                if worker.done():
                    await worker
                    if not stop.is_set():
                        raise RuntimeError("CCXT_QUOTE_WORKER_EXITED_UNEXPECTEDLY")
            finally:
                stream_stop.set()
                try:
                    await asyncio.wait_for(worker, timeout=30)
                except TimeoutError:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument(
        "--quote-root", type=Path,
        help="Private output journal; defaults to source journal for active portfolios",
    )
    parser.add_argument(
        "--canary-seconds", type=int, default=0,
        help="Finite read-only public WebSocket observation, without a standing service",
    )
    parser.add_argument("--registry-db", type=Path, required=True)
    parser.add_argument("--primary-dir", type=Path, required=True)
    parser.add_argument("--secondary-dir", type=Path, required=True)
    parser.add_argument("--quote-every-seconds", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--refresh-seconds", type=int, default=300)
    parser.add_argument("--max-markets", type=int, default=MAX_MARKETS)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if not args.source_db.is_absolute():
        parser.error("source database path must be absolute")
    if args.quote_root is not None and not args.quote_root.is_absolute():
        parser.error("quote output root must be absolute")
    if args.canary_seconds != 0 and not 5 <= args.canary_seconds <= 300:
        parser.error("canary duration must be 5..300 seconds")
    if args.source_db.name != "paper-events.sqlite3":
        parser.error("requires the existing observed PaperJournal filename")
    markets = native_scope(
        args.source_db, registry_db=args.registry_db, primary_dir=args.primary_dir,
        secondary_dir=args.secondary_dir, max_markets=args.max_markets,
    )
    if args.preflight:
        print(json.dumps({
            "status": "QUOTE_SCOPE_PREFLIGHT_ONLY",
            "native_market_count": len(markets),
            "scope_sha": digest([m.key for m in markets]),
            "order_route": "NONE",
            "no_network": True, "no_writes": True,
        }, sort_keys=True))
        return
    quote_root = args.quote_root or args.source_db.parent
    if args.health:
        quote_db = quote_root / "paper-events.sqlite3"
        print(json.dumps(live_quote_health(quote_db, markets), sort_keys=True))
        return
    journal = PaperJournal(quote_root)
    if args.quote_root is None and journal.path != args.source_db:
        raise ValueError("CCXT_QUOTE_JOURNAL_PATH_MISMATCH")
    stop = asyncio.Event()

    async def loop() -> None:
        running = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            running.add_signal_handler(sig, stop.set)
        def scope() -> tuple[Instrument, ...]:
            return native_scope(
                args.source_db, registry_db=args.registry_db,
                primary_dir=args.primary_dir, secondary_dir=args.secondary_dir,
                max_markets=args.max_markets,
            )
        async def stop_canary() -> None:
            await asyncio.sleep(args.canary_seconds)
            stop.set()

        canary = (
            asyncio.create_task(stop_canary()) if args.canary_seconds else None
        )
        try:
            with _single_writer(journal.root):
                await serve(
                    journal, scope=scope, stop=stop,
                    min_interval_seconds=args.quote_every_seconds,
                    refresh_seconds=args.refresh_seconds,
                )
        finally:
            if canary is not None:
                canary.cancel()
                await asyncio.gather(canary, return_exceptions=True)

    asyncio.run(loop())


if __name__ == "__main__":
    main()
