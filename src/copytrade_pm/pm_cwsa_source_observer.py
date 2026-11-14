"""Canonical five-minute CWSA source observer; no V4 streaming policy.

Only complete official REST checkpoints with original-wire evidence are
admissible. This module owns no broker permissions or modeled paper finance.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import signal
from typing import Annotated, Literal

from pydantic import Field

from .pm03_account import digest
from .pm_checkpoint_journal import CwsaPolicy
from .pm_checkpoint_source import GRID_MS, CheckpointScope, collect_checkpoint, utc_milliseconds
from .pm_forward_continuous_transport import SerialWriter
from .pm_forward_journal import PaperJournal
from .pm_source_contracts import Contract
from .pm_source_selection import selected_parents


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
    from .pm_private_io import private_input

    raw = private_input(path)
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
    parser.add_argument("--portfolios", required=True)
    # Accept the existing pinned CWSA unit's explicit REST mode; no WS mode exists.
    parser.add_argument(
        "--source-mode", choices=("CHECKPOINT_REST_V3",), default="CHECKPOINT_REST_V3"
    )
    parser.add_argument("--checkpoint-config", type=Path, required=True)
    parser.add_argument("--checkpoint-config-sha256", required=True)
    parser.add_argument("--checkpoint-once", action="store_true")
    parser.add_argument("--duration-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    if not 0 <= args.duration_seconds <= 86400:
        parser.error("--duration-seconds must be 0..86400")
    ids = tuple(args.portfolios.split(","))
    if not ids or len(ids) != len(set(ids)):
        parser.error("CWSA_PORTFOLIO_SCOPE_INVALID")
    os.umask(0o077)
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    parents = selected_parents(args.registry_db, portfolios=ids, as_of=now)
    config = load_checkpoint_configuration(
        args.checkpoint_config, args.checkpoint_config_sha256, parents
    )
    with source_lease(args.state_root):
        journal = PaperJournal(args.state_root)

        async def session():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
            return await observe_checkpoints(
                journal,
                parents,
                config,
                stop=stop,
                duration_seconds=args.duration_seconds,
                once=args.checkpoint_once,
            )

        result = asyncio.run(session())
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
