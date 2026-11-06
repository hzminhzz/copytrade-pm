"""Bounded, research-only Vike hl.fills WebSocket + REST parity canary.

No orders, broker references, source sizing, historical PIT reconstruction or
production service installation. Requires a DEDICATED Vike API key in the VPS
environment; ChatGPT MCP OAuth credentials must never be exported.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from time import monotonic
from urllib import error, parse, request

from .pm_vike_reconcile import wallet_from_registry

CHANNEL = "hl.fills"
URL = "wss://stream.vike.io/v1/stream/hl"
REST = "https://data.vike.io/v1/hyperliquid/stream-events"
SUB_ID = "copytrade_canary"
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
MAX_EVENTS = 500
MAX_REST_PAGES = 3
SCHEMA = """
CREATE TABLE IF NOT EXISTS frames(
  event_id TEXT PRIMARY KEY, frame_cursor TEXT NOT NULL,
  receipt_known_at TEXT NOT NULL, source_ts TEXT NOT NULL,
  wallet_sha256 TEXT NOT NULL, size_usd TEXT NOT NULL,
  native_trade_id TEXT NOT NULL, raw_event_sha256 TEXT NOT NULL,
  raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoint(
  id INTEGER PRIMARY KEY CHECK (id=1),
  cursor TEXT NOT NULL, had_gap INTEGER NOT NULL DEFAULT 0
);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def allowed_wallet(value: str) -> str:
    if not isinstance(value, str) or ADDRESS.fullmatch(value.lower()) is None:
        raise ValueError("VIKE_WALLET_ADDRESS_INVALID")
    return value.lower()


def subscription(wallet: str, cursor: str | None) -> dict:
    filt = {"wallet": [allowed_wallet(wallet)], "min_usd": 0}
    result = {"action": "subscribe", "id": SUB_ID, "channel": CHANNEL, "filter": filt}
    if cursor is not None:
        if not isinstance(cursor, str) or not cursor or len(cursor) > 150:
            raise ValueError("VIKE_RESUME_CURSOR_INVALID")
        result["cursor"] = cursor
    return result


def _digest(event: dict) -> tuple[str, str]:
    raw = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return raw, sha256(raw.encode()).hexdigest()


def _stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("VIKE_TIMESTAMP_INVALID")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("VIKE_TIMESTAMP_NAIVE")
    return dt.astimezone(UTC)


def validate_event(event: dict, wallet: str) -> tuple[str, str, str, str, str]:
    if not isinstance(event, dict) or event.get("schema") != "vike.event.v1":
        raise ValueError("VIKE_EVENT_SCHEMA_MISMATCH")
    if event.get("source") != CHANNEL or event.get("kind") != "fill":
        raise ValueError("VIKE_EVENT_CHANNEL_MISMATCH")
    eid = event.get("event_id")
    if not isinstance(eid, str) or not eid.startswith("hl.fills:") or len(eid) > 256:
        raise ValueError("VIKE_EVENT_ID_INVALID")
    subject = event.get("subject")
    if (
        not isinstance(subject, dict)
        or not isinstance(subject.get("wallet"), str)
        or subject["wallet"].lower() != wallet
    ):
        raise ValueError("VIKE_EVENT_WALLET_MISMATCH")
    data = event.get("data")
    if not isinstance(data, dict):
        raise ValueError("VIKE_FILL_DATA_INVALID")
    trade_id = data.get("trade_id")
    if isinstance(trade_id, bool) or not isinstance(trade_id, int) or trade_id <= 0:
        raise ValueError("VIKE_NATIVE_TRADE_ID_INVALID")
    if f":{wallet}:" not in eid or not eid.endswith(f":{trade_id}"):
        raise ValueError("VIKE_EVENT_NATIVE_IDENTITY_MISMATCH")
    try:
        usd = Decimal(str(data.get("size_usd")))
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise ValueError("VIKE_FILL_NOTIONAL_INVALID") from exc
    if not usd.is_finite() or usd < 0:
        raise ValueError("VIKE_FILL_NOTIONAL_INVALID")
    source_ts = event.get("ts")
    _stamp(source_ts)
    raw, digest = _digest(event)
    return eid, str(trade_id), str(usd), raw, digest


def _cursor(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 150:
        raise ValueError("VIKE_FRAME_CURSOR_INVALID")
    # Frame cursors are fixed-width lexical comparables, not event.cursor.
    if re.fullmatch(r"[0-9a-zA-Z_-]+", value) is None:
        raise ValueError("VIKE_FRAME_CURSOR_INVALID")
    return value


def open_journal(root: Path) -> sqlite3.Connection:
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("VIKE_CANARY_SYMLINK_PATH_REFUSED")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise PermissionError("VIKE_CANARY_PRIVATE_ROOT_REQUIRED")
    file = root / "canary.sqlite"
    if file.is_symlink():
        raise ValueError("VIKE_CANARY_DB_SYMLINK_REFUSED")
    con = sqlite3.connect(file, timeout=2)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.executescript(SCHEMA)
    if stat.S_IMODE(file.stat().st_mode) != 0o600:
        file.chmod(0o600)
    return con


def head(con: sqlite3.Connection) -> str | None:
    row = con.execute("SELECT cursor FROM checkpoint WHERE id=1").fetchone()
    return row[0] if row else None


def update_cursor(con: sqlite3.Connection, cursor: str, *, gap: bool = False) -> None:
    current = head(con)
    if current is not None and cursor < current:
        # A duplicate/out-of-order replay must not rewind the checkpoint.
        return
    con.execute(
        "INSERT INTO checkpoint(id,cursor,had_gap) VALUES(1,?,?) "
        "ON CONFLICT(id) DO UPDATE SET cursor=excluded.cursor, "
        "had_gap=MAX(checkpoint.had_gap,excluded.had_gap)",
        (cursor, int(gap)),
    )


def apply_frame(con: sqlite3.Connection, frame: dict, wallet: str, known_at: str) -> str:
    """Atomically journal event+resume cursor and record explicit source gaps."""
    seen_at = _stamp(known_at)
    if not 0 <= (datetime.now(UTC) - seen_at).total_seconds() <= 120:
        raise ValueError("VIKE_LOCAL_RECEIPT_CLOCK_NOT_CURRENT")
    if not isinstance(frame, dict):
        raise ValueError("VIKE_FRAME_INVALID")
    kind = frame.get("type")
    if kind == "ping":
        return "PONG_REQUIRED"
    if kind == "error":
        raise ValueError("VIKE_SERVER_ERROR_FRAME")
    if kind == "subscribed":
        if frame.get("id") != SUB_ID or frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_SUBSCRIPTION_ACK_MISMATCH")
        cursor = _cursor(frame.get("cursor"))
        with con:
            if head(con) is None:
                update_cursor(con, cursor)
        return "SUBSCRIBED"
    if kind == "gap":
        if frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_GAP_CHANNEL_MISMATCH")
        cursor = _cursor(frame.get("cursor"))
        with con:
            update_cursor(con, cursor, gap=True)
        return "GAP"
    if kind != "event":
        raise ValueError("VIKE_UNRECOGNIZED_FRAME")
    if frame.get("ids") != [SUB_ID]:
        raise ValueError("VIKE_EVENT_SUBSCRIPTION_ID_MISMATCH")
    cursor = _cursor(frame.get("cursor"))
    event = frame.get("event")
    eid, trade_id, usd, raw, digest = validate_event(event, wallet)
    if _stamp(event["ts"]) > seen_at:
        raise ValueError("VIKE_SOURCE_EVENT_AFTER_LOCAL_RECEIPT")
    with con:
        old = con.execute("SELECT raw_event_sha256 FROM frames WHERE event_id=?", (eid,)).fetchone()
        if old is not None and old[0] != digest:
            raise ValueError("VIKE_DUPLICATE_EVENT_ID_PAYLOAD_DRIFT")
        if old is None:
            con.execute(
                "INSERT INTO frames VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    cursor,
                    known_at,
                    event["ts"],
                    sha256(wallet.encode()).hexdigest(),
                    usd,
                    trade_id,
                    digest,
                    raw,
                ),
            )
        update_cursor(con, cursor)
    return "DUPLICATE" if old is not None else "EVENT"


def rest_request(key: str, wallet: str, cursor: str, *, limit: int = 500) -> dict:
    query = parse.urlencode(
        {
            "channel": CHANNEL,
            "wallet": wallet,
            "min_usd": 0,
            "cursor": cursor,
            "limit": limit,
        }
    )
    req = request.Request(
        REST + "?" + query,
        headers={"X-API-KEY": key, "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read(2_000_001)
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise ValueError("VIKE_REST_CATCHUP_UNAVAILABLE") from exc
    if len(body) > 2_000_000:
        raise ValueError("VIKE_REST_PAGE_TOO_LARGE")
    doc = json.loads(body)
    if not isinstance(doc, dict) or not isinstance(doc.get("events"), list):
        raise ValueError("VIKE_REST_PAGE_SCHEMA_MISMATCH")
    return doc


def compare_rest(con: sqlite3.Connection, wallet: str, start_cursor: str, key: str) -> dict:
    """Bounded REST catchup; any idle gap, truncation or mismatch blocks parity."""
    initial = _cursor(start_cursor)
    end = head(con)
    if end is None or end <= initial:
        return {"status": "INCONCLUSIVE_EMPTY_WINDOW", "catchup_complete": False}
    rest_ids: set[str] = set()
    gap = False
    cursor = initial
    has_more = True
    pages = 0
    while has_more and pages < MAX_REST_PAGES:
        page = rest_request(key, wallet, cursor)
        pages += 1
        if type(page.get("has_more")) is not bool:
            raise ValueError("VIKE_REST_HAS_MORE_INVALID")
        events = page["events"]
        for entry in events:
            if not isinstance(entry, dict):
                raise ValueError("VIKE_CATCHUP_ITEM_INVALID")
            if "gap" in entry:
                gap = True
                continue
            item = entry.get("event")
            validate_event(item, wallet)
            # A server may return events after the last observed WS cursor;
            # those don't prove an earlier loss, so exclude strictly later.
            frame_cursor = _cursor(entry.get("cursor"))
            if frame_cursor <= end:
                rest_ids.add(item["event_id"])
        next_cursor = page.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise ValueError("VIKE_REST_NEXT_CURSOR_INVALID")
        if next_cursor <= cursor and page.get("has_more"):
            raise ValueError("VIKE_REST_CURSOR_STALLED")
        cursor = next_cursor
        has_more = page.get("has_more") is True
    if (
        has_more
        or gap
        or cursor < end
        or con.execute("SELECT had_gap FROM checkpoint WHERE id=1").fetchone()[0]
    ):
        return {
            "status": "BLOCKED_REST_TRUNCATED_OR_STREAM_GAP",
            "catchup_complete": False,
            "pages": pages,
            "rest_events": len(rest_ids),
        }
    ws_ids = {
        row[0]
        for row in con.execute(
            "SELECT event_id FROM frames WHERE frame_cursor>? AND frame_cursor<=?",
            (initial, end),
        )
    }
    difference = ws_ids.symmetric_difference(rest_ids)
    small = sum(
        Decimal(size) < Decimal(1000)
        for (size,) in con.execute(
            "SELECT size_usd FROM frames WHERE frame_cursor>? AND frame_cursor<=?",
            (initial, end),
        )
    )
    return {
        "status": "PARITY_OBSERVED_SAMPLE_ONLY"
        if ws_ids and not difference and small
        else "INCONCLUSIVE_OR_PARITY_MISMATCH",
        "catchup_complete": True,
        "ws_events": len(ws_ids),
        "rest_events": len(rest_ids),
        "symmetric_difference_count": len(difference),
        "ws_sub_1000_count": small,
        "pages": pages,
        "production_admitted": False,
    }


async def run_live(wallet: str, key: str, root: Path, *, seconds: float) -> dict:
    from websockets.asyncio.client import connect

    with closing(open_journal(root)) as con:
        start = head(con)
        seen = {"EVENT": 0, "DUPLICATE": 0, "GAP": 0, "SUBSCRIBED": 0}
        ws_error = None
        async with connect(
            URL,
            additional_headers={"X-API-KEY": key},
            open_timeout=12,
            close_timeout=5,
            max_size=65536,
            ping_interval=15,
            ping_timeout=12,
        ) as socket:
            await socket.send(json.dumps(subscription(wallet, start)))
            began = monotonic()
            while monotonic() - began < seconds and seen["EVENT"] < MAX_EVENTS:
                remaining = seconds - (monotonic() - began)
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=max(0.05, remaining))
                except TimeoutError:
                    break
                frame = json.loads(raw)
                status = apply_frame(con, frame, wallet, utc_now())
                if status == "PONG_REQUIRED":
                    await socket.send('{"action":"pong"}')
                elif status in seen:
                    seen[status] += 1
        result = {
            "schema": "vike_readonly_stream_canary_v1",
            "wallet_address_reported": False,
            "order_route": "NONE",
            "production_admitted": False,
            "observed": seen,
            "start_cursor_available": start is not None,
            "last_cursor_available": head(con) is not None,
            "ws_error": ws_error,
        }
        # Do not compare post-subscription events against a made-up start cursor.
        if start is not None and seen["EVENT"]:
            result["rest_parity"] = compare_rest(con, wallet, start, key)
        else:
            result["rest_parity"] = {
                "status": "INCONCLUSIVE_NO_PRIOR_CURSOR_OR_EVENTS",
                "catchup_complete": False,
            }
        result["status"] = "BLOCKED_NOT_PRODUCTION_ADMITTED"
        return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wallet", help="Sensitive: prefer --registry-db with alias")
    p.add_argument("--registry-db", type=Path)
    p.add_argument("--alias", default="W028")
    p.add_argument("--namespace", default="frozen_pm01")
    p.add_argument("--state-root", type=Path, required=True)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--live", action="store_true", help="Bounded live read-only canary")
    p.add_argument(
        "--dedicated-key-only",
        action="store_true",
        help="Explicitly attest a key not used by another WS consumer",
    )
    args = p.parse_args()
    if (args.wallet is None) == (args.registry_db is None):
        p.error("provide exactly one of --wallet and --registry-db")
    if not 2 <= args.seconds <= 180:
        p.error("seconds must be 2..180")
    wallet = (
        allowed_wallet(args.wallet)
        if args.wallet is not None
        else wallet_from_registry(args.registry_db, namespace=args.namespace, alias=args.alias)
    )
    key = os.environ.get("VIKE_API_KEY")
    if not args.live or not args.dedicated_key_only or not key:
        print(
            json.dumps(
                {
                    "schema": "vike_readonly_stream_canary_v1",
                    "status": (
                        "BLOCKED_NOT_LIVE_OR_KEY_NOT_DEDICATED"
                        if not args.live or not args.dedicated_key_only
                        else "BLOCKED_NO_VPS_VIKE_API_KEY"
                    ),
                    "wallet_verified": bool(wallet),
                    "state_created": False,
                    "production_admitted": False,
                    "order_route": "NONE",
                    "required_env": "VIKE_API_KEY",
                }
            )
        )
        return 2
    try:
        result = asyncio.run(run_live(wallet, key, args.state_root, seconds=args.seconds))
    except Exception as exc:
        # Never log URLs, API headers, wallet identifiers or raw provider errors.
        print(
            json.dumps(
                {
                    "schema": "vike_readonly_stream_canary_v1",
                    "status": "BLOCKED_CANARY_TRANSPORT_OR_PROTOCOL",
                    "error_type": type(exc).__name__,
                    "production_admitted": False,
                    "order_route": "NONE",
                }
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["rest_parity"]["status"] == "PARITY_OBSERVED_SAMPLE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
