"""Configured native workers; systemd owns their supervision."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from datetime import UTC, datetime
import json
import os
import signal
import socket
import time
from typing import Any

from .pm_appliance_config import ApplianceConfig


def _ready(config: ApplianceConfig, role: str) -> None:
    """Notify systemd only after this role has verified its durable inputs."""
    from .pm_appliance import _private_json

    path = config.root / "runtime" / f"{role}.json"
    receipt = json.loads(path.read_text())
    if receipt["pid"] != os.getpid() or receipt["config_sha256"] != config.sha256:
        raise ValueError("APPLIANCE_READINESS_IDENTITY")
    _private_json(path, {**receipt, "phase": "READY", "ready_at": datetime.now(UTC).isoformat()})
    address = os.environ.get("NOTIFY_SOCKET")
    if address:
        if address.startswith("@"):
            address = "\u0000" + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(b"READY=1")


def paper_consumers(config: ApplianceConfig) -> list[Any]:
    from .pm_cwsa_paper import PaperConsumer

    consumers = []
    for item in config.papers.values():
        approval = item["approval"]
        consumers.append(
            PaperConsumer(
                configs=item["portfolios"],
                state_root=config.path(item["state"]),
                roster_db=config.roster,
                run_label=item["run_label"],
                source_db=config.path(config.sources[item["source"]]["state"])
                / "paper-events.sqlite3",
                approval_path=config.path(approval["path"]) if approval else None,
                approval_sha256=approval["sha256"] if approval else None,
                trusted_authority_hex=approval["public_key"] if approval else None,
                quote_db=config.path(config.quotes["state"]) / "paper-events.sqlite3",
            )
        )
    return consumers


async def source(config: ApplianceConfig, stop: asyncio.Event, *, once: bool) -> None:
    from .pm_checkpoint_capacity import CaptureTransport
    from .pm_cwsa_source_observer import (
        load_checkpoint_configuration,
        observe_checkpoints,
        source_lease,
    )
    from .pm_forward_journal import PaperJournal
    from .pm_source_selection import selected_parents

    selected = []
    for item in config.sources.values():
        parents = selected_parents(
            config.roster, portfolios=tuple(item["portfolios"]), as_of=datetime.now(UTC).isoformat()
        )
        policy = load_checkpoint_configuration(
            config.path(item["checkpoint_config"]), item["checkpoint_sha256"], parents
        )
        selected.append((config.path(item["state"]), parents, policy))
    selected.sort(key=lambda item: item[2].policy.limits.publication_grace_ms)
    remaining = len(selected)

    def owner_ready() -> None:
        nonlocal remaining
        remaining -= 1
        if remaining == 0:
            _ready(config, "source")

    # One shared budget, bounded by the largest already approved owner budget.
    # Do not sum historical per-process budgets when consolidating acquisition.
    transport = CaptureTransport(max(policy.weight_per_second for _, _, policy in selected))
    with ExitStack() as locks:
        for root, _, _ in selected:
            locks.enter_context(source_lease(root))
        async with asyncio.TaskGroup() as group:
            for root, parents, policy in selected:
                journal = PaperJournal(root)
                group.create_task(
                    observe_checkpoints(
                        journal,
                        parents,
                        policy,
                        stop=stop,
                        once=once,
                        info=transport,
                        on_ready=owner_ready,
                    )
                )


async def _pause(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def paper(config: ApplianceConfig, stop: asyncio.Event, *, once: bool) -> None:
    from .pm_cwsa_source_observer import source_lease
    from .pm_forward_continuous_transport import _complete_admitted

    async def poll(consumer: Any) -> None:
        while not stop.is_set():
            # Cancellation must drain the admitted thread before releasing its
            # owner lease. One slow account must not delay another owner.
            await _complete_admitted(asyncio.create_task(asyncio.to_thread(consumer.poll_once)))
            if once:
                return
            await _pause(stop, 5.0)

    with ExitStack() as locks:
        for item in config.papers.values():
            locks.enter_context(source_lease(config.path(item["state"])))
        consumers = await _complete_admitted(
            asyncio.create_task(asyncio.to_thread(paper_consumers, config))
        )
        _ready(config, "paper")
        # A failing owner stops the role; siblings drain before leases release.
        # systemd records the failure and retries from durable owner cursors.
        async with asyncio.TaskGroup() as group:
            for consumer in consumers:
                group.create_task(poll(consumer))


async def quotes(config: ApplianceConfig, stop: asyncio.Event, *, once: bool) -> None:
    from .pm03_account import Instrument
    from .pm_cwsa_source_observer import source_lease
    from .pm_forward_ccxt_market import ReadOnlyCCXTProHyperliquid
    from .pm_forward_journal import PaperJournal

    root = config.path(config.quotes["state"])
    instruments = tuple(Instrument.parse(raw) for raw in config.quotes["instruments"])
    last_seen: dict[str, tuple[str, str]] = {}
    ready = False
    with source_lease(root):
        journal = PaperJournal(root)
        async with ReadOnlyCCXTProHyperliquid(instruments, timeout_seconds=15) as feed:
            while not stop.is_set():
                for instrument in instruments:
                    quote = await feed.quote(instrument)
                    key = (quote.source_event_at, quote.book_sha)
                    if last_seen.get(instrument.key) == key:
                        continue
                    try:
                        journal.append_market_quote(quote.payload())
                    except ValueError as exc:
                        if str(exc) != "PAPER_MARKET_QUOTE_REPLAYED_BOOK":
                            raise
                    last_seen[instrument.key] = key
                if not ready:
                    _ready(config, "quotes")
                    ready = True
                if once:
                    return
                await _pause(stop, float(config.quotes["poll_seconds"]))


def health(config: ApplianceConfig) -> int:
    from .pm_operations import cli

    generation = (
        config.root
        / "health-research"
        / ("g" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + str(time.time_ns()))
    )
    return cli(
        [
            "facts",
            "capture-health",
            "--apply",
            "--roster-db",
            str(config.roster),
            "--store",
            str(config.root / "facts"),
            "--facts-root",
            str(config.root / "facts"),
            "--generation",
            str(generation),
            "--max-wallets",
            str(config.health["max_wallets"]),
            "--deep-wallets",
            str(config.health["deep_wallets"]),
            "--weight-per-minute",
            str(config.health["weight_per_minute"]),
        ]
    )


def run_worker(config: ApplianceConfig, role: str, *, once: bool = False) -> int:
    if role == "health":
        return health(config)

    async def session() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await {"source": source, "paper": paper, "quotes": quotes}[role](config, stop, once=once)

    print(json.dumps({"role": role, "state": "STARTING", "order_route": "NONE"}), flush=True)
    asyncio.run(session())
    return 0
