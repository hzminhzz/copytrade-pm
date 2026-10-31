"""Continuous read-only E4 prospective event capture with fail-closed gaps.

This observer consumes public Hyperliquid WebSocket account data for the
three E4 wallet identities and independently discovered subaccounts.
It persists each fill/funding/ledger frame and every changed signed account
book; unchanged books receive bounded 5-minute checkpoints. No exchange
trading API or credentials are imported. All reconnects are explicit gaps.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import signal
import shutil
from time import monotonic
import uuid
from typing import Any

from .pm_e4_prospective import (
    MAX_BODY,
    PODS,
    SUBSCRIPTIONS,
    WS_URL,
    _account_state,
    _canonical,
    _dex_universe,
    _guarded_info,
    _safe_dir,
    _subaccount_roster,
)
from .pm_hyperx_account_triage import _write_immutable_private
from .pm_hyperx_gap_recovery import _private_dir
from .pm_sources import load_cohort

MIN_SESSION_SECONDS = 10
MAX_SESSION_SECONDS = 3600
MIN_SAMPLE_SECONDS = 15
MAX_SAMPLE_SECONDS = 600
MAX_SESSION_RAW_BYTES = 100_000_000
MIN_FREE_DISK_BYTES = 10 * 1024 * 1024 * 1024


def capture_book_change(
    *,
    subject: str,
    positions: dict[str, str],
    observed_at: datetime,
    last: dict[str, tuple[str, datetime]],
    sample_seconds: int,
) -> tuple[bool, bool]:
    """Persist any quantity change immediately; checkpoint unchanged books."""
    signature = sha256(_canonical(positions)).hexdigest()
    previous = last.get(subject)
    changed = previous is not None and previous[0] != signature
    checkpoint = previous is None or (observed_at - previous[1]).total_seconds() >= sample_seconds
    if changed or checkpoint:
        last[subject] = (signature, observed_at)
    return changed, checkpoint


def _discovery(root: Path, session_root: Path) -> tuple[dict, dict[str, str], set[str], dict]:
    entries, manifests = load_cohort(root)
    roster = {x.alias: x for x in entries if x.alias in PODS}
    if set(roster) != set(PODS):
        raise ValueError("E4_STREAM_FROZEN_ROSTER_MISMATCH")
    dex, raw, catalog_sha = _guarded_info({"type": "perpDexs"})
    _write_immutable_private(session_root / "discovery" / "dex_catalog.json", raw)
    dexs = _dex_universe(dex)
    subjects = {p: roster[p].address for p in PODS}
    sub_counts: dict[str, int] = {}
    for pod in PODS:
        content, raw, response_sha = _guarded_info(
            {"type": "subAccounts", "user": roster[pod].address}
        )
        sub_accounts = _subaccount_roster(content, roster[pod].address)
        _write_immutable_private(session_root / "discovery" / f"{pod}-subaccounts.json", raw)
        for n, address in enumerate(sub_accounts):
            code = f"{pod}-sub{n:02d}"
            subjects[code] = address
        sub_counts[pod] = len(sub_accounts)
    if len(subjects) != len({v.lower() for v in subjects.values()}):
        raise ValueError("E4_DUPLICATED_SOURCE_ACCOUNT_ADDRESS")
    return (
        subjects,
        sub_counts,
        dexs,
        {
            "cohort_sha256": manifests,
            "dex_catalog_sha256": catalog_sha,
            "dex_count": len(dexs),
        },
    )


async def session(
    root: Path,
    store: Path,
    *,
    session_seconds: int = 900,
    sample_seconds: int = 300,
    stop_event: asyncio.Event | None = None,
) -> dict:
    if not MIN_SESSION_SECONDS <= session_seconds <= MAX_SESSION_SECONDS:
        raise ValueError("E4_INVALID_SESSION_DURATION")
    if not MIN_SAMPLE_SECONDS <= sample_seconds <= MAX_SAMPLE_SECONDS:
        raise ValueError("E4_INVALID_ACCOUNT_CHECKPOINT_INTERVAL")
    _private_dir(store)
    if store.stat().st_mode & 0o077:
        raise ValueError("E4_STREAM_ROOT_NOT_PRIVATE")
    if shutil.disk_usage(store).free < MIN_FREE_DISK_BYTES:
        raise ValueError("E4_STREAM_DISK_HEADROOM_INSUFFICIENT")
    date = datetime.now(UTC)
    generation = store / ("gE4" + date.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8])
    _safe_dir(generation)
    report: dict[str, Any] = {
        "schema": "e4_live_readonly_stream_session_v1",
        "started_at": date.isoformat(),
        "source": "OFFICIAL_HYPERLIQUID_WS_PUBLIC_INFO_ONLY",
        "raw_generation": generation.name,
        "trading_authorized": False,
        "complete_historical_source_book": False,
        "first_known_source_receipts_observed_locally": True,
        "coverage_gaps_assumed_absent": False,
        "session_max_seconds": session_seconds,
        "sample_seconds": sample_seconds,
        "frames_received": 0,
        "frames_stored": 0,
        "raw_bytes_stored": 0,
        "subscription_acks": 0,
        "account_checkpoints": 0,
        "actual_position_change_frames": 0,
        "event_channel_frames": 0,
        "snapshots": {},
        "errors": [],
        "disconnect_reason": "UNKNOWN",
        "connection": "NOT_STARTED",
    }
    latest: dict[str, tuple[str, datetime]] = {}
    try:
        subjects, subcounts, dexs, discovery = await asyncio.to_thread(_discovery, root, generation)
        report.update(discovery)
        report["subaccount_counts"] = subcounts
        report["subjects"] = {
            key: sha256(value.lower().encode()).hexdigest() for key, value in subjects.items()
        }
        by_addr = {address.lower(): code for code, address in subjects.items()}
        import websockets

        async with websockets.connect(
            WS_URL,
            open_timeout=16,
            close_timeout=6,
            ping_interval=15,
            ping_timeout=12,
            max_size=MAX_BODY,
        ) as ws:
            report["connection"] = "CONNECTED"
            report["connection_at"] = datetime.now(UTC).isoformat()
            for subject, address in subjects.items():
                types = SUBSCRIPTIONS if subject in PODS else ("allDexsClearinghouseState",)
                for message_type in types:
                    await ws.send(
                        json.dumps(
                            {
                                "method": "subscribe",
                                "subscription": {
                                    "type": message_type,
                                    "user": address,
                                },
                            }
                        )
                    )
            until = monotonic() + session_seconds
            serial = 0
            while monotonic() < until:
                if stop_event is not None and stop_event.is_set():
                    report["disconnect_reason"] = "OPERATOR_REQUESTED_STOP"
                    break
                try:
                    received = await asyncio.wait_for(
                        ws.recv(), timeout=min(5.0, max(0.01, until - monotonic()))
                    )
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    report["errors"].append("WS_RECV_" + type(exc).__name__)
                    report["disconnect_reason"] = "STREAM_DISCONNECTED"
                    break
                at = datetime.now(UTC)
                report["frames_received"] += 1
                if not isinstance(received, str) or len(received.encode()) > MAX_BODY:
                    report["errors"].append("WS_FRAME_TOO_LARGE_OR_BINARY")
                    report["disconnect_reason"] = "INVALID_FRAME"
                    break
                try:
                    body = json.loads(received)
                except ValueError, TypeError:
                    report["errors"].append("BAD_JSON_FRAME")
                    report["disconnect_reason"] = "INVALID_FRAME"
                    break
                if not isinstance(body, dict):
                    report["errors"].append("BAD_FRAME_SHAPE")
                    report["disconnect_reason"] = "INVALID_FRAME"
                    break
                channel = body.get("channel")
                data = body.get("data")
                subject = (
                    by_addr.get(str(data.get("user", "")).lower())
                    if isinstance(data, dict)
                    else None
                )
                store_frame = True
                change = False
                checkpoint = False
                snapshot_parsed = None
                if channel == "allDexsClearinghouseState":
                    if subject is None:
                        report["errors"].append("UNATTRIBUTED_ACCOUNT_FRAME")
                        continue
                    try:
                        snapshot_parsed = _account_state(data, subjects[subject], dexs)
                    except (ValueError, KeyError, TypeError) as exc:
                        report["errors"].append("ACCOUNT_CENSUS_" + type(exc).__name__)
                        continue
                    change, checkpoint = capture_book_change(
                        subject=subject,
                        positions=snapshot_parsed["positions"],
                        observed_at=at,
                        last=latest,
                        sample_seconds=sample_seconds,
                    )
                    store_frame = change or checkpoint
                    if store_frame:
                        report["account_checkpoints"] += 1
                        report["actual_position_change_frames"] += int(change)
                elif channel in (
                    "userEvents",
                    "userFills",
                    "userFundings",
                    "userNonFundingLedgerUpdates",
                ):
                    store_frame = True
                    report["event_channel_frames"] += 1
                elif channel == "subscriptionResponse":
                    store_frame = True
                    report["subscription_acks"] += 1
                elif channel == "error":
                    report["errors"].append("SUBSCRIPTION_OR_SOURCE_ERROR")
                    report["disconnect_reason"] = "SOURCE_REJECTED_SUBSCRIPTION"
                    break
                if not store_frame:
                    continue
                wire = received.encode()
                if report["raw_bytes_stored"] + len(wire) > MAX_SESSION_RAW_BYTES:
                    report["errors"].append("SESSION_STORAGE_BUDGET_EXHAUSTED")
                    report["disconnect_reason"] = "STORAGE_BUDGET_REACHED"
                    break
                filename = f"{serial:08d}-{sha256(wire).hexdigest()[:20]}.json"
                raw_sha = _write_immutable_private(generation / "frames" / filename, wire)
                _write_immutable_private(
                    generation / "metadata" / f"{serial:08d}.json",
                    _canonical(
                        {
                            "schema": "e4_live_received_frame_v1",
                            "locally_received_at": at.isoformat(),
                            "subject": subject,
                            "channel": channel,
                            "source_raw_sha256": raw_sha,
                            "filename": filename,
                            "source_is_snapshot": (
                                data.get("isSnapshot") if isinstance(data, dict) else None
                            ),
                            "position_change": change,
                            "periodic_account_checkpoint": checkpoint,
                            "not_first_known_for_snapshot_backfill": (
                                data.get("isSnapshot") is True if isinstance(data, dict) else False
                            ),
                        }
                    ),
                )
                report["frames_stored"] += 1
                report["raw_bytes_stored"] += len(wire)
                serial += 1
                if snapshot_parsed is not None:
                    report["snapshots"][subject] = {
                        "locally_received_at": at.isoformat(),
                        "nonzero_positions": snapshot_parsed["position_count"],
                        "perp_dexs_seen": snapshot_parsed["observed_dex_count"],
                        "official_dex_catalog_parity": True,
                        "last_frame_sha256": raw_sha,
                    }
            if report["disconnect_reason"] == "UNKNOWN":
                report["disconnect_reason"] = "BOUNDED_SESSION_ROTATION"
    except Exception as exc:
        report["errors"].append("SESSION_" + type(exc).__name__)
        report["disconnect_reason"] = "SOURCE_UNAVAILABLE"
    report["finished_at"] = datetime.now(UTC).isoformat()
    _write_immutable_private(generation / "session-report.json", _canonical(report))
    return {
        "generation": generation.name,
        "raw_report_sha256": sha256((generation / "session-report.json").read_bytes()).hexdigest(),
        "frames_received": report["frames_received"],
        "frames_stored": report["frames_stored"],
        "account_checkpoints": report["account_checkpoints"],
        "position_changes": report["actual_position_change_frames"],
        "events": report["event_channel_frames"],
        "subaccounts": report.get("subaccount_counts"),
        "snapshots": len(report["snapshots"]),
        "errors": report["errors"],
        "disconnect_reason": report["disconnect_reason"],
    }


async def run(
    root: Path,
    store: Path,
    *,
    forever: bool,
    session_seconds: int,
    sample_seconds: int,
) -> None:
    stop = asyncio.Event()
    if forever:
        loop = asyncio.get_running_loop()
        for name in ("SIGTERM", "SIGINT"):
            loop.add_signal_handler(getattr(signal, name), stop.set)
    delay = 5
    while True:
        outcome = await session(
            root,
            store,
            session_seconds=session_seconds,
            sample_seconds=sample_seconds,
            stop_event=stop,
        )
        print(json.dumps(outcome, sort_keys=True), flush=True)
        if not forever or stop.is_set():
            return
        if outcome["errors"]:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        else:
            delay = 5
            await asyncio.sleep(0.25)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--forever", action="store_true")
    p.add_argument("--session-seconds", type=int, default=900)
    p.add_argument("--sample-seconds", type=int, default=300)
    a = p.parse_args()
    asyncio.run(
        run(
            a.research_root,
            a.store,
            forever=a.forever,
            session_seconds=a.session_seconds,
            sample_seconds=a.sample_seconds,
        )
    )


if __name__ == "__main__":
    main()
