"""Immutable, read-only Vike position-event observations.

This is *not* a complete account book and cannot emit source transitions.
A Vike event is only evidence for later independent official reconciliation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import sqlite3

from .pm_vike_stream_canary import _cursor, _stamp, allowed_wallet

CHANNEL = "hl.positions"
SUB_ID = "copytrade_position"
SCHEMA = """
CREATE TABLE IF NOT EXISTS selected_position_events (
 event_id TEXT PRIMARY KEY,
 cursor TEXT NOT NULL,
 account_sha256 TEXT NOT NULL,
 event_at TEXT NOT NULL,
 first_known_at TEXT NOT NULL,
 native_trade_id TEXT NOT NULL,
 market TEXT NOT NULL,
 native_position_after TEXT NOT NULL,
 raw_wire_sha256 TEXT NOT NULL,
 raw_event_sha256 TEXT NOT NULL,
 raw_wire TEXT NOT NULL,
 prospective INTEGER NOT NULL CHECK(prospective IN (0,1))
);
CREATE TABLE IF NOT EXISTS selected_position_checkpoint (
 id INTEGER PRIMARY KEY CHECK(id=1),
 cursor TEXT NOT NULL, had_gap INTEGER NOT NULL DEFAULT 0,
 last_received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_position_gaps (
 cursor TEXT PRIMARY KEY, known_at TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_position_subscription (
 id INTEGER PRIMARY KEY CHECK(id=1),
 acknowledged_at TEXT NOT NULL, acknowledgment_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_position_wallet_health (
 account_sha256 TEXT PRIMARY KEY,
 observed_count INTEGER NOT NULL,
 last_observed_at TEXT NOT NULL
);
"""


def initialize(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    # One-time upgrade for preexisting observational DBs; normal coverage
    # reads only the bounded per-wallet table, never a full event GROUP BY.
    if db.execute("SELECT 1 FROM selected_position_wallet_health LIMIT 1").fetchone() is None:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO selected_position_wallet_health "
                "SELECT account_sha256,COUNT(*),MAX(first_known_at) "
                "FROM selected_position_events GROUP BY account_sha256"
            )


def position_subscription(wallets: tuple[str, ...], cursor: str | None = None) -> dict:
    unique = tuple(sorted({allowed_wallet(a) for a in wallets}))
    if len(unique) != len(wallets) or not 1 <= len(unique) <= 1000:
        raise ValueError("VIKE_POSITION_SELECTION_INVALID")
    request = {
        "action": "subscribe",
        "id": SUB_ID,
        "channel": CHANNEL,
        "filter": {"wallet": list(unique), "min_usd": 0},
    }
    if cursor is not None:
        request["cursor"] = _cursor(cursor)
    return request


def checkpoint(db: sqlite3.Connection) -> tuple[str | None, bool]:
    row = db.execute(
        "SELECT cursor,had_gap FROM selected_position_checkpoint WHERE id=1"
    ).fetchone()
    return (row[0], bool(row[1])) if row else (None, False)


def _advance(db: sqlite3.Connection, cursor: str, known_at: str, gap: bool) -> None:
    current, _ = checkpoint(db)
    if current is not None and cursor < current:
        if gap:
            db.execute("UPDATE selected_position_checkpoint SET had_gap=1 WHERE id=1")
        return
    db.execute(
        "INSERT INTO selected_position_checkpoint VALUES(1,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET cursor=excluded.cursor,"
        "had_gap=MAX(selected_position_checkpoint.had_gap,excluded.had_gap),"
        "last_received_at=excluded.last_received_at",
        (cursor, int(gap), known_at),
    )


def _number(value: object) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("VIKE_POSITION_NATIVE_QUANTITY_INVALID") from exc
    if isinstance(value, bool) or not number.is_finite():
        raise ValueError("VIKE_POSITION_NATIVE_QUANTITY_INVALID")
    return str(number)


def validate(event: dict, wallets: tuple[str, ...]) -> tuple[str, str, str, str, str]:
    if not isinstance(event, dict) or event.get("schema") != "vike.event.v1":
        raise ValueError("VIKE_POSITION_SCHEMA_INVALID")
    if event.get("source") != CHANNEL or event.get("kind") != "position":
        raise ValueError("VIKE_POSITION_CHANNEL_INVALID")
    subject, data = event.get("subject"), event.get("data")
    if not isinstance(subject, dict) or not isinstance(data, dict):
        raise ValueError("VIKE_POSITION_FIELDS_INVALID")
    wallet = allowed_wallet(subject.get("wallet"))
    if wallet not in wallets:
        raise ValueError("VIKE_POSITION_UNSELECTED_WALLET")
    trade_id = data.get("trade_id")
    if isinstance(trade_id, bool) or not isinstance(trade_id, int) or trade_id <= 0:
        raise ValueError("VIKE_POSITION_NATIVE_ID_INVALID")
    eid = event.get("event_id")
    if (
        not isinstance(eid, str)
        or len(eid) > 256
        or not eid.startswith("hl.positions:" + wallet + ":")
        or not eid.endswith(":" + str(trade_id))
    ):
        raise ValueError("VIKE_POSITION_EVENT_ID_INVALID")
    symbol, dex = subject.get("symbol"), data.get("dex")
    if not isinstance(symbol, str) or not symbol or not isinstance(dex, str) or not dex:
        raise ValueError("VIKE_POSITION_MARKET_INVALID")
    if dex == "HL":
        if ":" in symbol:
            raise ValueError("VIKE_POSITION_DEX_SYMBOL_CONFLICT")
    elif not symbol.startswith(dex.lower() + ":") and not symbol.startswith(dex + ":"):
        raise ValueError("VIKE_POSITION_DEX_SYMBOL_CONFLICT")
    if data.get("action") not in {"open", "increase", "reduce", "close", "flip"}:
        raise ValueError("VIKE_POSITION_ACTION_INVALID")
    if data.get("side") not in {"buy", "sell"}:
        raise ValueError("VIKE_POSITION_SIDE_INVALID")
    after = _number(data.get("position_after"))
    _number(data.get("start_position"))
    size = Decimal(_number(data.get("size_token")))
    if size <= 0:
        raise ValueError("VIKE_POSITION_NATIVE_SIZE_NOT_POSITIVE")
    _stamp(event.get("ts"))
    return eid, wallet, str(trade_id), symbol, after


def apply_frame(
    db: sqlite3.Connection,
    frame: dict,
    wallets: tuple[str, ...],
    known_at: str,
    *,
    raw_wire: str,
    prospective: bool = False,
) -> str:
    """Commit raw wire, local receipt and cursor atomically.

    A recovered or pre-subscription-head frame is explicitly retrospective.
    Even a prospective frame is NOT a complete-book or financial signal.
    """
    _stamp(known_at)
    if not isinstance(raw_wire, str):
        raise ValueError("VIKE_POSITION_WIRE_INVALID")

    def unique_keys(pairs):
        parsed = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError("VIKE_POSITION_DUPLICATE_WIRE_KEY")
            parsed[key] = value
        return parsed

    if json.loads(raw_wire, object_pairs_hook=unique_keys) != frame:
        raise ValueError("VIKE_POSITION_WIRE_INVALID")
    kind = frame.get("type")
    if kind == "subscribed":
        if frame.get("id") != SUB_ID or frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_POSITION_ACK_INVALID")
        with db:
            if checkpoint(db)[0] is None:
                _advance(db, _cursor(frame.get("cursor")), known_at, False)
            db.execute(
                "INSERT INTO selected_position_subscription VALUES(1,?,1) "
                "ON CONFLICT(id) DO UPDATE SET acknowledged_at=excluded.acknowledged_at,"
                "acknowledgment_count=selected_position_subscription.acknowledgment_count+1",
                (known_at,),
            )
        return "SUBSCRIBED"
    if kind == "gap":
        if frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_POSITION_GAP_CHANNEL_INVALID")
        cursor = _cursor(frame.get("cursor"))
        with db:
            db.execute(
                "INSERT OR IGNORE INTO selected_position_gaps VALUES(?,?,?)",
                (cursor, known_at, "PROVIDER_STREAM_GAP"),
            )
            _advance(db, cursor, known_at, True)
        return "GAP"
    if kind != "event" or frame.get("ids") != [SUB_ID]:
        raise ValueError("VIKE_POSITION_FRAME_INVALID")
    cursor = _cursor(frame.get("cursor"))
    event = frame.get("event")
    eid, wallet, tid, market, after = validate(event, wallets)
    if _stamp(event["ts"]) > _stamp(known_at):
        raise ValueError("VIKE_POSITION_FUTURE_EVENT")
    wire_sha = sha256(raw_wire.encode()).hexdigest()
    event_sha = sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with db:
        old = db.execute(
            "SELECT raw_event_sha256 FROM selected_position_events WHERE event_id=?",
            (eid,),
        ).fetchone()
        if old and old[0] != event_sha:
            raise ValueError("VIKE_POSITION_EVENT_PAYLOAD_DRIFT")
        if old is None:
            db.execute(
                "INSERT INTO selected_position_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    cursor,
                    sha256(wallet.encode()).hexdigest(),
                    event["ts"],
                    known_at,
                    tid,
                    market,
                    after,
                    wire_sha,
                    event_sha,
                    raw_wire,
                    int(prospective),
                ),
            )
            db.execute(
                "INSERT INTO selected_position_wallet_health VALUES(?,?,?) "
                "ON CONFLICT(account_sha256) DO UPDATE SET "
                "observed_count=selected_position_wallet_health.observed_count+1,"
                "last_observed_at=excluded.last_observed_at",
                (sha256(wallet.encode()).hexdigest(), 1, known_at),
            )
        _advance(db, cursor, known_at, False)
    return (
        "DUPLICATE"
        if old
        else ("PROSPECTIVE_POSITION_EVENT" if prospective else "RECOVERED_POSITION_EVENT")
    )


def coverage(db: sqlite3.Connection, wallets: tuple[str, ...]) -> dict:
    current, gap = checkpoint(db)
    acknowledged = db.execute(
        "SELECT acknowledged_at,acknowledgment_count FROM selected_position_subscription WHERE id=1"
    ).fetchone()
    rows = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            "SELECT account_sha256, observed_count, last_observed_at "
            "FROM selected_position_wallet_health"
        )
    }
    return {
        "schema": "vike_selected_position_transport_coverage_v1",
        "subscription_cursor_present": current is not None,
        "subscription_acknowledged": acknowledged is not None,
        "last_acknowledged_at": acknowledged[0] if acknowledged else None,
        "subscription_acknowledgments": acknowledged[1] if acknowledged else 0,
        "stream_gap": gap,
        "selected_account_count": len(wallets),
        "accounts": {
            sha256(wallet.encode()).hexdigest(): {
                "observed_position_events": rows.get(
                    sha256(wallet.encode()).hexdigest(), (0, None)
                )[0],
                "last_observed_at": rows.get(sha256(wallet.encode()).hexdigest(), (0, None))[1],
                "complete_book_verified": False,
                "paper_new_risk_eligible": False,
            }
            for wallet in wallets
        },
        "position_authority": "NONE_TRANSPORT_ONLY",
        "paper_new_risk_eligible": False,
        "order_route": "NONE",
    }
