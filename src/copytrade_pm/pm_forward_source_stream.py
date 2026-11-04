"""Bounded official Hyperliquid public per-account all-DEX observation.

Uses existing E4 account parser and publicly documented WS/Info endpoints.
No broker orders, no source retro-reconstruction, no real whole-wallet
admission, no service deployment, and no parent/subaccount NAV netting.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic
from typing import Any, Callable

from .pm_e4_prospective import MAX_BODY, WS_URL, _guarded_info
from .pm_forward_journal import PaperJournal
from .pm_forward_source_observation import append_public_scope, read_public_all_dex_scope


ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


async def bounded_source_scope_capture(
    *,
    alias: str,
    address: str,
    journal: PaperJournal,
    seconds: float = 10,
    max_frames: int = 10,
    info: Callable = _guarded_info,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
) -> dict:
    if not isinstance(address, str) or ADDRESS.fullmatch(address) is None:
        raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")
    if not 2 <= seconds <= 60 or not 1 <= max_frames <= 100:
        raise ValueError("SOURCE_BOUNDED_SESSION_POLICY_INVALID")
    if connect is None:
        import websockets

        connect = websockets.connect

    # These are ONLY 2 current metadata requests, never historical fills.
    catalog, _, catalog_sha = await asyncio.to_thread(info, {"type": "perpDexs"})
    subaccounts, _, sub_sha = await asyncio.to_thread(
        info, {"type": "subAccounts", "user": address}
    )
    results = {
        "schema": "paper_public_scope_bounded_capture_v1",
        "wallet_alias": alias,
        "account_address_sha256": sha256(address.lower().encode()).hexdigest(),
        "dex_catalog_sha256": catalog_sha,
        "subaccount_discovery_sha256": sub_sha,
        "observed_subject": "PARENT_ONLY_NOT_ALL_SUBACCOUNTS",
        "complete_parent_subaccount_book": False,
        "whole_wallet_equity_attested": False,
        "paper_admitted": False,
        "paper_observed": False,
        "order_route": "NONE",
        "frames_received": 0,
        "per_account_receipts": 0,
        "snapshot_backfill_excluded": 0,
        "errors": [],
        "transport_status": "NOT_STARTED",
    }
    async with connect(
        WS_URL,
        open_timeout=12,
        close_timeout=5,
        ping_interval=15,
        ping_timeout=12,
        max_size=MAX_BODY,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "subscription": {"type": "allDexsClearinghouseState", "user": address},
                }
            )
        )
        results["transport_status"] = "CONNECTED_BOUNDED"
        started = monotonic()
        seen = set()
        while monotonic() - started < seconds and results["frames_received"] < max_frames:
            remaining = seconds - (monotonic() - started)
            try:
                wire = await asyncio.wait_for(ws.recv(), timeout=max(0.01, remaining))
            except TimeoutError:
                results["transport_status"] = "TIMEOUT_NOT_CONTINUOUS"
                break
            known = now()  # timestamp before JSON decoding or persistence
            results["frames_received"] += 1
            if not isinstance(wire, str) or len(wire.encode()) > MAX_BODY:
                results["errors"].append("SOURCE_FRAME_TOO_LARGE_OR_BINARY")
                break
            try:
                envelope = json.loads(wire)
                if not isinstance(envelope, dict):
                    raise ValueError("SOURCE_FRAME_NON_OBJECT")
                if envelope.get("channel") == "subscriptionResponse":
                    continue
                if envelope.get("channel") == "error":
                    raise ValueError("SOURCE_SUBSCRIPTION_REJECTED")
                if envelope.get("channel") != "allDexsClearinghouseState":
                    continue
                data = envelope.get("data")
                if not isinstance(data, dict):
                    raise ValueError("SOURCE_BOOK_NOT_OBJECT")
                if data.get("isSnapshot") is True:
                    # A provider-delivered historical snapshot is NOT a new
                    # first-known change; ignore for prospective signals.
                    results["snapshot_backfill_excluded"] += 1
                    continue
                receipt = read_public_all_dex_scope(
                    alias=alias,
                    address=address,
                    frame=envelope,
                    dex_catalog=catalog,
                    discovered_subaccounts=subaccounts,
                    first_known_at=known,
                )
                if receipt["source_sha"] in seen:
                    continue
                seen.add(receipt["source_sha"])
                seq = journal.source_status(alias)["cursor"] + 1
                result = append_public_scope(journal, alias=alias, seq=seq, receipt=receipt)
                if result.get("cursor") == seq:
                    results["per_account_receipts"] += 1
            except (ValueError, KeyError, TypeError) as exc:
                # Capture integrity failure blocks this source; never
                # substitute a guessed source_event_at or a zero book.
                results["errors"].append("SOURCE_CAPTURE_" + type(exc).__name__ + ":" + str(exc))
                break
    results["transport_status"] = (
        "BLOCKED_SCOPE_OR_SOURCE" if results["errors"] else "BOUNDED_SESSION_ENDED_NOT_CONTINUOUS"
    )
    results["source_cursor"] = journal.source_status(alias)["cursor"]
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded public Hyperliquid per-account read-only observation; NO paper admission"
    )
    parser.add_argument("--alias", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--max-frames", type=int, default=10)
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        component in {".devspace", ".git"} for component in args.state_root.resolve().parts
    ):
        parser.error("source capture needs an absolute non-worktree private root")
    result = asyncio.run(
        bounded_source_scope_capture(
            alias=args.alias,
            address=args.address,
            journal=PaperJournal(args.state_root),
            seconds=args.seconds,
            max_frames=args.max_frames,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
