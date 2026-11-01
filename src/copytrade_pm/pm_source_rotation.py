"""One bounded A/B/C observer within Hyperliquid's per-IP user subscription cap.

A rotation is sampled prospective evidence. It does not assert an uninterrupted
source book or historical first knowledge. Every process uses one shared lock.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal

from .pm_e4_stream import session
from .pm_portfolio_e0 import PORTFOLIOS

DEFAULT_LOCK = Path.home() / ".local/share/copytrade/source-observer.lock"


@contextmanager
def observer_lock(path: Path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise ValueError("E4_OBSERVER_LOCK_NOT_PRIVATE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("E4_SOURCE_OBSERVER_ALREADY_RUNNING") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


async def rotate(
    root: Path,
    store: Path,
    *,
    forever: bool,
    session_seconds: int = 60,
    sample_seconds: int = 15,
    receiver=session,
    cooldown_seconds: float = 2,
) -> None:
    """Close each account window before subscribing to the next; no overlapping users."""
    stop = asyncio.Event()
    if forever:
        loop = asyncio.get_running_loop()
        for name in ("SIGTERM", "SIGINT"):
            loop.add_signal_handler(getattr(signal, name), stop.set)
    failures = 0
    while True:
        for portfolio, pods in PORTFOLIOS.items():
            index, count = 0, 1
            while index < count:
                outcome = await receiver(
                    root,
                    store / portfolio,
                    session_seconds=session_seconds,
                    sample_seconds=sample_seconds,
                    stop_event=stop,
                    pods=pods,
                    account_window_index=index,
                )
                print(json.dumps({"portfolio": portfolio, **outcome}, sort_keys=True), flush=True)
                if stop.is_set():
                    return
                count = outcome.get("account_window_count", 1)
                if type(count) is not int or not 1 <= count <= 6:
                    raise ValueError("E4_INVALID_ROTATION_WINDOW_COUNT")
                failures = min(failures + 1, 5) if outcome.get("errors") else 0
                delay = max(cooldown_seconds, min(60, 2**failures) if failures else 0)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                    return
                except TimeoutError:
                    pass
                index += 1
        if not forever:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--session-seconds", type=int, default=60)
    parser.add_argument("--sample-seconds", type=int, default=15)
    args = parser.parse_args()
    with observer_lock(DEFAULT_LOCK):
        asyncio.run(
            rotate(
                args.research_root,
                args.store,
                forever=args.forever,
                session_seconds=args.session_seconds,
                sample_seconds=args.sample_seconds,
            )
        )


if __name__ == "__main__":
    main()
