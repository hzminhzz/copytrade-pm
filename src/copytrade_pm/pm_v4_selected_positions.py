"""Position-only official Hyperliquid observer for selected virtual-paper pods.

One selected WS or complete five-minute REST mode for a sealed parent set. The existing
PersistentAccount / PaperJournal stream owner handles baseline, transitions,
raw provenance, gaps and restart. No Vike fills, CCXT, broker or finance writes.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
import fcntl
import os
from pathlib import Path
import signal
from typing import Annotated, Callable, Literal

from pydantic import Field

from .pm_source_contracts import Contract
from .pm_checkpoint_journal import CwsaPolicy
from .pm_checkpoint_source import GRID_MS, CheckpointScope, collect_checkpoint, utc_milliseconds

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
from .pm_forward_stream_journal import verify_stream_heads_fast


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
    compact_evidence: bool = False,
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
            compact_evidence=compact_evidence,
        )
        for alias, address in parents.items()
    }


async def observe(
    accounts: dict[str, PersistentAccount],
    *,
    duration_seconds: float = 0,
    stop: asyncio.Event | None = None,
    native_user_budget: int = 7,
    native_rotation_seconds: float = 420,
    native_stable_aliases: tuple[str, ...] | None = None,
) -> dict:
    stop = stop or asyncio.Event()
    async with SerialWriter(max_pending=256) as writer:
        result = None
        worker = asyncio.create_task(
            run_native_accounts(
                accounts,
                writer=writer,
                stop=stop,
                connect=None,
                now=lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
                limiter=ConnectionBudget(per_minute=6),
                user_budget=native_user_budget,
                rotation_seconds=native_rotation_seconds,
                stable_aliases=native_stable_aliases,
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
            result = await worker
        finally:
            stop.set()
            if timer is not None:
                timer.cancel()
                await asyncio.gather(timer, return_exceptions=True)
            if not worker.done():
                await worker
    return {
        "status": "STOPPED_READ_ONLY" if result is None else result["status"],
        "native_transport": result,
        "accounts": len(accounts),
        "writer_health": {
            "write_count": writer.write_count,
            "write_failures": writer.write_failures,
            "max_write_ms": round(writer.write_max_ms, 3),
            "total_write_ms": round(writer.write_total_ms, 3),
            "queue_high_water": writer.high_water,
            "recovery_policy": "PRE_TRANSACTION_ONLY",
        },
        "order_route": "NONE",
        "source_nav_required": False,
    }


class CheckpointObserverConfig(Contract):
    schema_name: Literal["cwsa_observer_config_v1"] = Field(alias="schema")
    policy: CwsaPolicy
    scopes: dict[str, CheckpointScope]
    first_checkpoint_ms: Annotated[int, Field(ge=0, multiple_of=GRID_MS)]
    workers: Annotated[int, Field(ge=1, le=16)]
    weight_per_second: Annotated[int, Field(ge=1, le=8)]

    def bind(self, parents: dict[str, str]) -> None:
        roster_sha = digest(
            {alias: sha256(address.encode()).hexdigest() for alias, address in parents.items()}
        )
        if not parents or set(self.scopes) != set(parents):
            raise ValueError("CWSA_CONFIG_ROSTER")
        for alias, address in parents.items():
            scope = self.scopes[alias]
            if (
                scope.source_id != alias
                or scope.account_sha != sha256(address.encode()).hexdigest()
                or scope.selection_sha != roster_sha
                or scope.generation != digest(["hyperliquid/mainnet:perp", address, scope.dexes])
            ):
                raise ValueError("CWSA_CONFIG_ROSTER_OR_SCOPE")


def load_checkpoint_configuration(path: Path, expected_sha: str, parents: dict[str, str]):
    from .v4_source_export import _private_input

    raw = _private_input(path)
    if sha256(raw).hexdigest() != expected_sha:
        raise ValueError("CWSA_CONFIG_PIN")
    config = CheckpointObserverConfig.model_validate_json(raw)
    config.bind(parents)
    return config


@contextmanager
def source_lease(root: Path):
    """Exclusive mode selection within the existing source process boundary."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("CWSA_SOURCE_PRIVATE_DIRECTORY")
    fd = os.open(root / "source-authority.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("CWSA_SOURCE_AUTHORITY_LEASE") from exc
        yield
    finally:
        os.close(fd)


def selected_source_parents(
    registry_db: Path,
    *,
    portfolios: tuple[str, ...],
    as_of: str,
    campaign_manifest: Path | None = None,
    campaign_sha256: str | None = None,
) -> dict[str, str]:
    if campaign_manifest is None:
        if campaign_sha256 is not None:
            raise ValueError("V4_CAMPAIGN_REQUIRES_PRIVATE_MANIFEST")
        return selected_parents(registry_db, portfolios=portfolios, as_of=as_of)
    from .pm_v4_sixteen_scenarios import IDENTITIES, load_campaign

    if (
        campaign_sha256 is None
        or len(portfolios) != len(IDENTITIES)
        or set(portfolios) != set(IDENTITIES)
    ):
        raise ValueError("V4_CAMPAIGN_PORTFOLIO_SCOPE_MISMATCH")
    return load_campaign(
        manifest=campaign_manifest,
        registry_db=registry_db,
        at=as_of,
        expected_sha256=campaign_sha256,
    ).parents


async def observe_checkpoints(
    journal: PaperJournal,
    parents: dict[str, str],
    config: CheckpointObserverConfig,
    *,
    stop: asyncio.Event | None = None,
    duration_seconds: float = 0,
    once: bool = False,
    info=None,
    now_ms=utc_milliseconds,
    wait=None,
) -> dict:
    """REST transport mode of this observer; the existing journal owns every transition."""
    config.bind(parents)
    stop = stop or asyncio.Event()
    started = now_ms()
    heads = {}
    for alias, scope in config.scopes.items():
        history = journal.checkpoint_history(scope, config.policy.epoch)
        if history:
            heads[alias] = history[-1].successor.next_checkpoint_ms
        else:
            state = journal.register_checkpoint_source(
                scope,
                config.policy,
                first_checkpoint_ms=config.first_checkpoint_ms,
                at_ms=started,
            )
            heads[alias] = state.next_checkpoint_ms
    if info is None:
        from .pm_checkpoint_capacity import CaptureTransport

        info = CaptureTransport(config.weight_per_second)
    semaphore = asyncio.Semaphore(config.workers)
    outcomes = {}
    waves = 0
    async with SerialWriter(max_pending=max(16, len(parents))) as writer:
        while not stop.is_set():
            current = now_ms()
            if duration_seconds and current - started >= duration_seconds * 1000:
                break
            due = min(heads.values())
            if current < due:
                delay = due - current
                if duration_seconds:
                    delay = min(delay, max(0, int(duration_seconds * 1000) - (current - started)))
                if wait is not None:
                    await wait(delay)
                else:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay / 1000)
                    except TimeoutError:
                        pass
                continue
            boundary = max(due, current // GRID_MS * GRID_MS)

            async def collect(alias):
                async with semaphore:
                    candidate = await asyncio.to_thread(
                        collect_checkpoint,
                        config.scopes[alias],
                        parents[alias],
                        checkpoint_ms=boundary,
                        limits=config.policy.limits,
                        evidence_root=journal.root,
                        info=info,
                        now_ms=now_ms,
                    )
                    outcome = await writer.submit(
                        lambda: journal.append_checkpoint_sample(
                            config.policy.epoch, candidate, now_ms()
                        )
                    )
                    if not hasattr(outcome, "kind"):
                        raise ValueError("CWSA_CONCURRENT_SOURCE_DRIFT")
                    heads[alias] = boundary + GRID_MS
                    outcomes[outcome.kind] = outcomes.get(outcome.kind, 0) + 1

            # Drain every admitted collection/write before releasing this authority on failure.
            results = await asyncio.gather(
                *(collect(alias) for alias in sorted(heads) if heads[alias] <= boundary),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            waves += 1
            if hasattr(info, "requests"):
                # Pacing continues across waves; diagnostic request memory remains bounded.
                info.requests.clear()
            if once:
                break
    return {
        "schema": "cwsa_observer_status_v3",
        "status": "STOPPED_READ_ONLY",
        "policy_epoch": config.policy.epoch,
        "accounts": len(parents),
        "waves": waves,
        "outcomes": outcomes,
        "writer_count": writer.write_count,
        "order_route": "NONE",
        "trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--source-mode", choices=("LEGACY_WS", "CHECKPOINT_REST_V3"), default="LEGACY_WS"
    )
    parser.add_argument("--checkpoint-config", type=Path)
    parser.add_argument("--checkpoint-config-sha256")
    parser.add_argument("--checkpoint-once", action="store_true")
    parser.add_argument("--native-user-budget", type=int, default=7)
    parser.add_argument("--native-rotation-seconds", type=float, default=420)
    parser.add_argument("--native-stable-aliases", default="")
    parser.add_argument(
        "--compact-evidence",
        action="store_true",
        help="V2 raw sidecars and source receipts: requires all readers to be V2-compatible",
    )
    args = parser.parse_args(argv)
    if args.source_mode == "CHECKPOINT_REST_V3":
        if args.checkpoint_config is None or args.checkpoint_config_sha256 is None:
            parser.error(
                "checkpoint REST requires an explicit externally approved config and SHA pin"
            )
    elif (
        args.checkpoint_config is not None
        or args.checkpoint_config_sha256 is not None
        or args.checkpoint_once
    ):
        parser.error("checkpoint options require CHECKPOINT_REST_V3 mode")
    if not 0 <= args.duration_seconds <= 86400:
        parser.error("--duration-seconds must be 0..86400")
    # Reserve three user-specific slots for the co-running 0811 source on this
    # shared-IP host. This is a local budget, not an IP-wide lease manager.
    if not 1 <= args.native_user_budget <= 7:
        parser.error("--native-user-budget must be 1..7 (reserve 3 shared-IP users)")
    if not 330 <= args.native_rotation_seconds <= 3600:
        parser.error("--native-rotation-seconds must be 330..3600")
    stable = tuple(part.strip() for part in args.native_stable_aliases.split(",") if part.strip())
    if stable and (len(stable) > args.native_user_budget or len(stable) != len(set(stable))):
        parser.error("--native-stable-aliases must be a unique subset within the WS budget")
    os.umask(0o077)
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    ids = tuple(args.portfolios.split(","))
    parents = selected_source_parents(
        args.registry_db,
        portfolios=ids,
        as_of=now,
        campaign_manifest=args.campaign_manifest,
        campaign_sha256=args.campaign_sha256,
    )
    config = (
        load_checkpoint_configuration(
            args.checkpoint_config,
            args.checkpoint_config_sha256,
            parents,
        )
        if args.source_mode == "CHECKPOINT_REST_V3"
        else None
    )
    with source_lease(args.state_root):
        journal = PaperJournal(args.state_root)
        if config is None:
            verify_stream_heads_fast(journal.path)
            accounts = official_accounts(journal, parents, compact_evidence=args.compact_evidence)

        async def session():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
            if config is not None:
                return await observe_checkpoints(
                    journal,
                    parents,
                    config,
                    stop=stop,
                    duration_seconds=args.duration_seconds,
                    once=args.checkpoint_once,
                )
            return await observe(
                accounts,
                stop=stop,
                duration_seconds=args.duration_seconds,
                native_user_budget=args.native_user_budget,
                native_rotation_seconds=args.native_rotation_seconds,
                native_stable_aliases=stable or None,
            )

        result = asyncio.run(session())
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
