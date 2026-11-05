"""Provisional market-wide Hyperliquid public wallet fills, no execution route.

Official WsTrade.users is [buyer, seller]. Unlike the CCXT trade cache, the
native public feed includes counterparties, but it has no globally complete
sequence proof, leader NAV, or subaccount/hedge attestation. Every receipt is
therefore D4 *candidate evidence*, never an admitted financial paper order.
The first streaming batch after a (re)subscription is a discarded baseline.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from time import monotonic
from typing import Any, Callable, Mapping
from uuid import uuid4

from .pm03_account import Instrument, clock, digest, number
from .pm_e4_prospective import WS_URL
from .pm_forward_journal import PaperJournal
from .pm_forward_portfolios import _verify_sealed_definition_sha

ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
MAX_NATIVE_MARKETS = 8
MAX_FRAME_BYTES = 2_000_000


def native_coin(instrument: Instrument) -> str:
    if instrument.venue != "hyperliquid" or not instrument.market.startswith("mainnet:perp:"):
        raise ValueError("PUBLIC_TRADE_NOT_HYPERLIQUID_PERP")
    dex = instrument.market.removeprefix("mainnet:perp:")
    if not dex or not instrument.symbol or ":" in instrument.symbol:
        raise ValueError("PUBLIC_TRADE_INVALID_NATIVE_COIN")
    if dex == "default":
        return instrument.symbol
    return dex + ":" + instrument.symbol


def registry_watched_addresses(
    db_path: Path, portfolio_ids: tuple[str, ...], *, as_of: str
) -> dict[str, str]:
    """Resolve sealed portfolios from SQLite, never a Markdown alias map.

    Addresses are used in process memory only. The journal writes numeric
    wallet references, not the underlying private roster.
    """
    if not portfolio_ids or len(portfolio_ids) != len(set(portfolio_ids)):
        raise ValueError("PUBLIC_TRADE_PORTFOLIO_CENSUS_INVALID")
    clock(as_of)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("PUBLIC_TRADE_REGISTRY_MISSING")
    conn = sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    watched: dict[str, str] = {}
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")  # one consistent SQLite registry generation across portfolios
        for pid in portfolio_ids:
            seal = conn.execute(
                "SELECT version, definition_sha256, selection_known_at "
                "FROM portfolio_seals WHERE portfolio_id=? "
                "ORDER BY version DESC LIMIT 1",
                (pid,),
            ).fetchone()
            if seal is None or clock(seal["selection_known_at"]) > clock(as_of):
                raise ValueError("PUBLIC_TRADE_PORTFOLIO_NOT_SEALED_ASOF")
            definition_sha = seal["definition_sha256"]
            if (
                not isinstance(definition_sha, str)
                or len(definition_sha) != 64
                or any(c not in "0123456789abcdef" for c in definition_sha)
            ):
                raise ValueError("PUBLIC_TRADE_UNVERIFIED_PORTFOLIO_SEAL")
            version = seal["version"]
            members = conn.execute(
                "SELECT p.member_alias,p.wallet_id,w.address,w.venue,w.network "
                "FROM portfolio_memberships p LEFT JOIN wallets w "
                "ON p.wallet_id=w.wallet_id "
                "WHERE p.portfolio_id=? AND p.version=? ORDER BY p.member_alias",
                (pid, version),
            ).fetchall()
            if not members or any(row["wallet_id"] is None for row in members):
                raise ValueError("PUBLIC_TRADE_PORTFOLIO_IDENTITY_UNRESOLVED")
            _verify_sealed_definition_sha(
                conn,
                pid,
                version,
                tuple(row["member_alias"] for row in members),
                seal["definition_sha256"],
            )
            for row in members:
                if row["venue"] != "hyperliquid" or row["network"] != "mainnet":
                    raise ValueError("PUBLIC_TRADE_NON_HL_WALLET")
                address = row["address"].lower()
                if ADDRESS.fullmatch(address) is None:
                    raise ValueError("PUBLIC_TRADE_WALLET_ADDRESS_INVALID")
                excluded = conn.execute(
                    "SELECT 1 FROM exclusions WHERE wallet_id=? LIMIT 1",
                    (row["wallet_id"],),
                ).fetchone()
                denylist_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='propfirm_exclusions'"
                ).fetchone()
                if denylist_exists is not None:
                    additional = conn.execute(
                        "SELECT 1 FROM propfirm_exclusions WHERE wallet_id=? LIMIT 1",
                        (row["wallet_id"],),
                    ).fetchone()
                    if additional is not None:
                        raise ValueError("PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED")
                if excluded is not None:
                    raise ValueError("PUBLIC_TRADE_WALLET_EXCLUDED")
                ref = "wallet:" + str(row["wallet_id"])
                if address in watched and watched[address] != ref:
                    raise ValueError("PUBLIC_TRADE_ADDRESS_IDENTITY_CONFLICT")
                watched[address] = ref
    finally:
        conn.close()
    return watched


def normalize_native_trade(
    raw: Mapping[str, Any],
    *,
    instrument: Instrument,
    watched: Mapping[str, str],
    first_known_at: str,
    stream_epoch: str,
) -> list[dict]:
    """Two signed wallet fills per public trade if both parties are watched."""
    if raw.get("coin") != native_coin(instrument):
        raise ValueError("PUBLIC_TRADE_COIN_IDENTITY_MISMATCH")
    users = raw.get("users")
    if (
        not isinstance(users, (tuple, list))
        or len(users) != 2
        or any(not isinstance(addr, str) for addr in users)
    ):
        raise ValueError("PUBLIC_TRADE_BUYER_SELLER_UNKNOWN")
    buyer, seller = (addr.lower() for addr in users)
    if ADDRESS.fullmatch(buyer) is None or ADDRESS.fullmatch(seller) is None:
        raise ValueError("PUBLIC_TRADE_COUNTERPARTY_INVALID")
    if raw.get("side") not in ("B", "A"):
        raise ValueError("PUBLIC_TRADE_AGGRESSOR_UNKNOWN")
    stamp, tid = raw.get("time"), raw.get("tid")
    if type(stamp) is not int or stamp <= 0 or type(tid) is not int or tid < 0:
        raise ValueError("PUBLIC_TRADE_NATIVE_ID_INVALID")
    source_at = datetime.fromtimestamp(stamp / 1000, tz=UTC).isoformat()
    if clock(source_at) > clock(first_known_at):
        raise ValueError("PUBLIC_TRADE_FUTURE_SOURCE_CLOCK")
    price, size = number(raw.get("px")), number(raw.get("sz"))
    if price <= 0 or size <= 0:
        raise ValueError("PUBLIC_TRADE_PRICE_SIZE_INVALID")
    tx_hash = raw.get("hash")
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise ValueError("PUBLIC_TRADE_TRANSACTION_HASH_INVALID")
    if (
        not isinstance(stream_epoch, str)
        or len(stream_epoch) != 32
        or any(c not in "0123456789abcdef" for c in stream_epoch)
    ):
        raise ValueError("PUBLIC_TRADE_STREAM_EPOCH_INVALID")

    first_known_at = clock(first_known_at).astimezone(UTC).isoformat(timespec="microseconds")
    trade_sha = digest(dict(raw))
    # Bind each receipt to the complete in-memory SQLite-resolved watchlist.
    # Numeric registry wallet IDs are generation-local, not global identities.
    watchlist_sha = digest(sorted(watched.items()))
    results = []
    for address, side, qty in ((buyer, "BUY", size), (seller, "SELL", -size)):
        wallet_key = watched.get(address)
        if wallet_key is None:
            continue
        if not wallet_key.startswith("wallet:") or not wallet_key[7:].isdecimal():
            raise ValueError("PUBLIC_TRADE_NOT_CANONICAL_REGISTRY_WALLET")
        results.append(
            {
                "schema": "paper_public_wallet_trade_v1",
                "wallet_key": wallet_key,
                "instrument": instrument.key,
                "source_timestamp_ms": stamp,
                "native_tid": tid,
                "event_key": digest([instrument.key, stamp, tid, wallet_key, side]),
                "source_event_at": source_at,
                "first_known_at": first_known_at,
                "stream_epoch": stream_epoch,
                "wallet_side": side,
                "signed_qty": str(qty),
                "price": str(price),
                "source_trade_sha": trade_sha,
                "watchlist_sha": watchlist_sha,
                "evidence_class": "PUBLIC_TRADE_PROVISIONAL_NO_NAV",
                "provider_signed": False,
                "source_account_complete": False,
                "paper_admitted": False,
                "order_route": "NONE",
            }
        )
    return results


async def capture_bounded_native_trades(
    *,
    instruments: tuple[Instrument, ...],
    watched: Mapping[str, str],
    journal: PaperJournal,
    duration_seconds: float = 10,
    max_frames: int = 500,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
) -> dict:
    """Shared public WS (no per-user subscriptions), strictly bounded and gap-aware."""
    if not instruments or len(instruments) > MAX_NATIVE_MARKETS:
        raise ValueError("PUBLIC_TRADE_MAX_MARKET_SHARD_EXCEEDED")
    if not (0.5 <= duration_seconds <= 120 and 1 <= max_frames <= 50000):
        raise ValueError("PUBLIC_TRADE_CAPTURE_BOUNDS_INVALID")
    if not watched or any(ADDRESS.fullmatch(addr) is None for addr in watched):
        raise ValueError("PUBLIC_TRADE_WATCHLIST_INVALID")
    markets = {native_coin(inst): inst for inst in instruments}
    if len(markets) != len(instruments):
        raise ValueError("PUBLIC_TRADE_DUPLICATE_MARKET")
    if connect is None:
        import websockets

        connect = websockets.connect

    epoch = uuid4().hex
    baselined: set[str] = set()
    received = accepted = matches = 0
    started = monotonic()
    failure = None
    try:
        async with connect(
            WS_URL,
            open_timeout=12,
            close_timeout=5,
            ping_interval=15,
            ping_timeout=12,
            max_size=MAX_FRAME_BYTES,
        ) as ws:
            for coin in markets:
                await ws.send(
                    json.dumps(
                        {
                            "method": "subscribe",
                            "subscription": {"type": "trades", "coin": coin},
                        }
                    )
                )
            while received < max_frames:
                remain = duration_seconds - (monotonic() - started)
                if remain <= 0:
                    break
                try:
                    wire = await asyncio.wait_for(ws.recv(), timeout=remain)
                except TimeoutError:
                    break
                known = now()  # stamp on reception, before decoding and SQLite I/O
                received += 1
                if not isinstance(wire, str) or len(wire.encode()) > MAX_FRAME_BYTES:
                    raise ValueError("PUBLIC_TRADE_FRAME_INVALID")
                envelope = json.loads(wire)
                if not isinstance(envelope, dict):
                    raise ValueError("PUBLIC_TRADE_ENVELOPE_INVALID")
                if envelope.get("channel") == "subscriptionResponse":
                    continue
                if envelope.get("channel") == "error":
                    raise ValueError("PUBLIC_TRADE_SUBSCRIPTION_REJECTED")
                if envelope.get("channel") != "trades":
                    raise ValueError("PUBLIC_TRADE_UNEXPECTED_CHANNEL")
                rows = envelope.get("data")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("PUBLIC_TRADE_WS_BATCH_INVALID")
                baseline_coins = set()
                for trade in rows:
                    if not isinstance(trade, dict) or trade.get("coin") not in markets:
                        raise ValueError("PUBLIC_TRADE_UNSUBSCRIBED_COIN")
                    if trade["coin"] not in baselined:
                        baseline_coins.add(trade["coin"])
                for coin in sorted(baseline_coins):
                    await asyncio.to_thread(
                        journal.append_public_trade_gap,
                        instrument=markets[coin].key,
                        stream_epoch=epoch,
                        observed_at=known,
                        reason="INITIAL_BASELINE",
                    )
                baselined.update(baseline_coins)
                events = []
                for trade in rows:
                    if not isinstance(trade, dict) or trade.get("coin") not in markets:
                        raise ValueError("PUBLIC_TRADE_UNSUBSCRIBED_COIN")
                    coin = trade["coin"]
                    # Discard the entire first batch for each market, not just
                    # its first trade. Reconnect snapshots are not first-known.
                    if coin in baseline_coins or envelope.get("isSnapshot") is True:
                        continue
                    events.extend(
                        normalize_native_trade(
                            trade,
                            instrument=markets[coin],
                            watched=watched,
                            first_known_at=known,
                            stream_epoch=epoch,
                        )
                    )
                if events:
                    result = await asyncio.to_thread(journal.append_public_wallet_trades, events)
                    accepted += result["new_receipts"]
                    matches += len(events)
    except asyncio.CancelledError:
        failure = "DISCONNECT"
        raise
    except Exception:
        failure = "INTEGRITY_FAILURE"
        raise
    finally:
        closed_at = now()
        for inst in instruments:
            await asyncio.to_thread(
                journal.append_public_trade_gap,
                instrument=inst.key,
                stream_epoch=epoch,
                observed_at=closed_at,
                reason=failure or "BOUNDED_CAPTURE_ENDED",
            )

    return {
        "schema": "paper_public_market_wallet_trade_capture_v1",
        "status": "PROVISIONAL_OBSERVATION_ONLY",
        "stream_epoch": epoch,
        "frames_received": received,
        "matched_wallet_sides": matches,
        "new_wallet_receipts": accepted,
        "baseline_markets": len(baselined),
        "coverage_complete": False,
        "whole_wallet_nav_attested": False,
        "paper_admitted": False,
        "order_route": "NONE",
    }


def plan_latest_public_utc_bucket(
    *,
    journal: PaperJournal,
    instruments: tuple[Instrument, ...],
    wallet_keys: tuple[str, ...],
    as_of: str,
    timing_policy: str = "UTC_BUCKET_CLOSE",
) -> dict:
    """Run one deterministic, durable, NONFINANCIAL UTC scheduling cycle.

    This reads only candidate trade receipts. It does not infer an opening
    position, account NAV, executable follower quantity or virtual fill.
    """
    if timing_policy not in {"UTC_BUCKET_CLOSE", "UTC_BUCKET_PLUS_5M"}:
        raise ValueError("PUBLIC_BUCKET_POLICY_UNSUPPORTED")
    if not instruments or len(instruments) > MAX_NATIVE_MARKETS:
        raise ValueError("PUBLIC_BUCKET_MARKET_LIMIT")
    if not wallet_keys or len(wallet_keys) > 50 or len(set(wallet_keys)) != len(wallet_keys):
        raise ValueError("PUBLIC_BUCKET_WALLET_LIMIT")
    if any(not x.startswith("wallet:") or not x[7:].isdecimal() for x in wallet_keys):
        raise ValueError("PUBLIC_BUCKET_CANONICAL_ID_REQUIRED")
    checked = clock(as_of).astimezone(UTC)
    boundary = checked.replace(minute=(checked.minute // 5) * 5, second=0, microsecond=0)
    offset = timedelta(minutes=5 if timing_policy == "UTC_BUCKET_CLOSE" else 10)
    bucket_start = boundary - offset
    due_at = bucket_start + offset
    outcome = []
    for instrument in sorted(instruments, key=lambda x: x.key):
        native_coin(instrument)
        for wallet_key in sorted(wallet_keys):
            report = journal.observed_utc_net_delta(
                wallet_key,
                instrument.key,
                bucket_start_at=bucket_start.isoformat(),
                as_of=as_of,
            )
            if report["status"] == "WAIT":
                raise ValueError("PUBLIC_BUCKET_DUE_BEFORE_END")
            if report["event_count"] == 0 and report["late_event_count"] == 0:
                continue
            journal.audit_public_wallet_trade_tape(wallet_key, instrument.key)
            try:
                seal = journal.persist_observed_utc_bucket(report)
                status = seal["status"]
            except ValueError as exc:
                if "CORRECTION" not in str(exc):
                    raise
                # An already-sealed bucket cannot be changed by a late fill.
                # Keep the original record and report the discrepancy.
                status = "BLOCKED_IMMUTABLE_BUCKET_CORRECTION_REQUIRED"
            quote = journal.first_eligible_quote_after(
                instrument.key,
                due_at=due_at.isoformat(),
                checked_at=as_of,
            )
            outcome.append(
                {
                    "wallet_key": wallet_key,
                    "instrument": instrument.key,
                    "batch_start_at": bucket_start.isoformat(),
                    "batch_end_at": (bucket_start + timedelta(minutes=5)).isoformat(),
                    "due_at": due_at.isoformat(),
                    "event_count": report["event_count"],
                    "late_event_count": report["late_event_count"],
                    "observed_net_delta": report["net_position_delta"],
                    "observed_gross_turnover": report["gross_observed_turnover"],
                    "source_gap_count": report["gap_count"],
                    "bucket_status": status,
                    "quote_status": quote["status"],
                    "quote_sha": quote.get("quote_sha"),
                    "paper_admitted": False,
                    "paper_executed": False,
                }
            )
    return {
        "schema": "paper_public_utc_bucket_scheduler_v1",
        "as_of": as_of,
        "timing_policy": timing_policy,
        "window_start_at": bucket_start.isoformat(),
        "due_at": due_at.isoformat(),
        "buckets": outcome,
        "result_count": len(outcome),
        "whole_wallet_nav_attested": False,
        "market_capacity_attested": False,
        "financial_events_committed": 0,
        "paper_running": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only provisional public wallet trades; NO paper fills"
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--portfolio", action="append", required=True)
    parser.add_argument("--instrument", action="append", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("observe", "plan"), default="observe")
    parser.add_argument(
        "--timing-policy",
        choices=("UTC_BUCKET_CLOSE", "UTC_BUCKET_PLUS_5M"),
        default="UTC_BUCKET_CLOSE",
    )
    parser.add_argument("--duration-seconds", type=float, default=10)
    parser.add_argument("--max-frames", type=int, default=500)
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        part in {".devspace", ".git"} for part in args.state_root.resolve().parts
    ):
        parser.error("state root must be an absolute private non-worktree path")
    watched = registry_watched_addresses(
        args.registry,
        tuple(args.portfolio),
        as_of=datetime.now(UTC).isoformat(),
    )
    instruments = tuple(Instrument.parse(x) for x in args.instrument)
    journal = PaperJournal(args.state_root)
    if args.mode == "plan":
        report = plan_latest_public_utc_bucket(
            journal=journal,
            instruments=instruments,
            wallet_keys=tuple(sorted(set(watched.values()))),
            as_of=datetime.now(UTC).isoformat(timespec="microseconds"),
            timing_policy=args.timing_policy,
        )
    else:
        report = asyncio.run(
            capture_bounded_native_trades(
                instruments=instruments,
                watched=watched,
                journal=journal,
                duration_seconds=args.duration_seconds,
                max_frames=args.max_frames,
            )
        )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
