"""Position-only official Hyperliquid observer for selected virtual-paper pods.

One native WS for a sealed, deduplicated parent account set. The existing
PersistentAccount / PaperJournal stream owner handles baseline, transitions,
raw provenance, gaps and restart. No Vike fills, CCXT, broker or finance writes.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
from typing import Callable

from .pm03_account import digest
from .pm_e4_prospective import _dex_universe, _guarded_info
from .pm_forward_continuous import run_native_accounts
from .pm_forward_continuous_transport import ConnectionBudget, SerialWriter
from .pm_forward_journal import PaperJournal
from .pm_forward_observed_paper import (
    PAPER_PROFILES,
    _readonly,
    _verify_portfolio_selection,
)
from .pm_forward_source_stream import PersistentAccount
from .pm_forward_stream_journal import verify_streams


def selected_parents(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str
) -> dict[str, str]:
    """Read exact current portfolio selections once; do not widen to child NAV."""
    if not portfolios or len(portfolios) != len(set(portfolios)):
        raise ValueError("V4_SELECTED_PORTFOLIOS_INVALID")
    if any(pid not in PAPER_PROFILES for pid in portfolios):
        raise ValueError("V4_SELECTED_PORTFOLIO_UNAPPROVED")
    for pid in portfolios:
        selection = _verify_portfolio_selection(
            registry_db,
            PAPER_PROFILES[pid],
            as_of=as_of,
        )
        if not selection.get("definition_sha256"):
            raise ValueError("V4_SELECTED_PORTFOLIO_SEAL_MISSING")

    parents: dict[str, str] = {}
    with closing(_readonly(registry_db)) as db:
        db.execute("BEGIN")
        try:
            for pid in portfolios:
                for alias, full in PAPER_PROFILES[pid].registry_aliases.items():
                    addresses = db.execute(
                        "SELECT DISTINCT w.address FROM wallets w "
                        "JOIN wallet_aliases a ON a.wallet_id=w.wallet_id "
                        "WHERE a.alias=? AND a.known_at<=?",
                        (full, as_of),
                    ).fetchall()
                    if len(addresses) != 1:
                        raise ValueError("V4_SELECTED_ACCOUNT_IDENTITY_AMBIGUOUS")
                    address = addresses[0][0].lower()
                    if (
                        not address.startswith("0x")
                        or len(address) != 42
                        or any(c not in "0123456789abcdef" for c in address[2:])
                    ):
                        raise ValueError("V4_SELECTED_ADDRESS_INVALID")
                    previous = parents.setdefault(alias, address)
                    if previous != address:
                        raise ValueError("V4_SHARED_SELECTED_ACCOUNT_CONFLICT")
        finally:
            db.execute("ROLLBACK")
    if len(set(parents.values())) != len(parents):
        raise ValueError("V4_SELECTED_DUPLICATE_ACCOUNTS")
    return dict(sorted(parents.items()))


def official_accounts(
    journal: PaperJournal,
    parents: dict[str, str],
    *,
    info: Callable = _guarded_info,
) -> dict[str, PersistentAccount]:
    """Verify a real official DEX census; only explicitly selected parents."""
    if not parents:
        raise ValueError("V4_SELECTED_ACCOUNTS_EMPTY")
    catalog, raw, provided_sha = info({"type": "perpDexs"})
    if not isinstance(raw, bytes) or sha256(raw).hexdigest() != provided_sha:
        raise ValueError("V4_OFFICIAL_DEX_CATALOG_PROVENANCE_INVALID")
    _dex_universe(catalog)
    scope_sha = digest(
        [
            "SELECTED_PARENT_PERP_ONLY",
            sorted((alias, sha256(addr.encode()).hexdigest()) for alias, addr in parents.items()),
            provided_sha,
        ]
    )
    return {
        alias: PersistentAccount(
            journal=journal,
            alias=alias,
            address=address,
            dex_catalog=catalog,
            subaccounts=None,
            parent_alias=alias,
            scope_sha=scope_sha,
        )
        for alias, address in parents.items()
    }


async def observe(
    accounts: dict[str, PersistentAccount],
    *,
    duration_seconds: float = 0,
    stop: asyncio.Event | None = None,
) -> dict:
    stop = stop or asyncio.Event()
    async with SerialWriter(max_pending=256) as writer:
        worker = asyncio.create_task(
            run_native_accounts(
                accounts,
                writer=writer,
                stop=stop,
                connect=None,
                now=lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
                limiter=ConnectionBudget(per_minute=6),
            )
        )
        timer = None
        try:
            if duration_seconds:

                async def end_after_duration():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=duration_seconds)
                    except TimeoutError:
                        stop.set()

                timer = asyncio.create_task(end_after_duration())
            await worker
        finally:
            stop.set()
            if timer is not None:
                timer.cancel()
                await asyncio.gather(timer, return_exceptions=True)
            if not worker.done():
                await worker
    return {
        "status": "STOPPED_READ_ONLY",
        "accounts": len(accounts),
        "order_route": "NONE",
        "source_nav_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-db", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--portfolios", default="P1,P14,P16")
    parser.add_argument(
        "--campaign-manifest",
        type=Path,
        help="Owner-private SHA-pinned sixteen-portfolio prospective paper study",
    )
    parser.add_argument("--campaign-sha256")
    parser.add_argument("--duration-seconds", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.duration_seconds <= 86400:
        parser.error("--duration-seconds must be 0..86400")
    os.umask(0o077)
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    ids = tuple(args.portfolios.split(","))
    if args.campaign_manifest is not None:
        from .pm_v4_sixteen_scenarios import IDENTITIES, load_campaign

        if (
            args.campaign_sha256 is None
            or len(ids) != len(IDENTITIES)
            or set(ids) != set(IDENTITIES)
        ):
            raise ValueError("V4_CAMPAIGN_PORTFOLIO_SCOPE_MISMATCH")
        campaign = load_campaign(
            manifest=args.campaign_manifest,
            registry_db=args.registry_db,
            at=now,
            expected_sha256=args.campaign_sha256,
        )
        parents = campaign.parents
    else:
        if args.campaign_sha256 is not None:
            raise ValueError("V4_CAMPAIGN_REQUIRES_PRIVATE_MANIFEST")
        parents = selected_parents(args.registry_db, portfolios=ids, as_of=now)
    journal = PaperJournal(args.state_root)
    verify_streams(journal.path)
    accounts = official_accounts(journal, parents)

    async def session():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        return await observe(accounts, stop=stop, duration_seconds=args.duration_seconds)

    result = asyncio.run(session())
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
