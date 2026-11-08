"""Shared, read-only selected-wallet Vike fill intake.

One hl.fills subscription for the whole selected universe, with min_usd=0.
WS observations retain their actual local first-known time. REST recovery
is explicitly retrospective and must never emit forward-paper source signals.
The existing official complete-position observer remains necessary: a fill
is not an independently verified full selected-account position vector.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
from time import monotonic
from urllib import error, parse, request

from .pm_vike_stream_canary import (
    CHANNEL, URL, _cursor, _stamp, allowed_wallet, validate_event,
)

REST = "https://data.vike.io/v1/hyperliquid/stream-events"
SUB_ID = "copytrade_selected"
SCHEMA = """
CREATE TABLE IF NOT EXISTS selected_fills (
 event_id TEXT PRIMARY KEY, cursor TEXT NOT NULL, wallet_sha256 TEXT NOT NULL,
 native_trade_id TEXT NOT NULL, source_at TEXT NOT NULL,
 first_known_at TEXT NOT NULL, raw_sha TEXT NOT NULL, raw_json TEXT NOT NULL,
 prospective INTEGER NOT NULL CHECK(prospective IN (0,1))
);
CREATE TABLE IF NOT EXISTS selected_checkpoint (
 id INTEGER PRIMARY KEY CHECK(id=1), cursor TEXT NOT NULL,
 had_gap INTEGER NOT NULL DEFAULT 0, last_received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_gaps (
 cursor TEXT PRIMARY KEY, known_at TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selected_transport (
 id INTEGER PRIMARY KEY CHECK(id=1),
 last_server_frame_at TEXT NOT NULL,
 ping_count INTEGER NOT NULL,
 subscription_count INTEGER NOT NULL
);
"""


def selected_wallets_from_registry(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str,
) -> tuple[str, ...]:
    """Read only the exact sealed, currently resolvable selected accounts.

    This is a transport allowlist, never proof of an admitted signal, source
    position census, or a fresh research selection. No addresses are logged.
    """
    from .pm_forward_observed_paper import (
        PAPER_PROFILES, _readonly, _verify_portfolio_selection,
    )

    if not portfolios or len(portfolios) != len(set(portfolios)):
        raise ValueError("VIKE_SELECTED_PORTFOLIO_IDS_INVALID")
    if any(portfolio not in PAPER_PROFILES for portfolio in portfolios):
        raise ValueError("VIKE_SELECTED_PORTFOLIO_NOT_FROZEN")
    _stamp(as_of)
    accounts = set()
    for portfolio in portfolios:
        profile = PAPER_PROFILES[portfolio]
        seal = _verify_portfolio_selection(registry_db, profile, as_of=as_of)
        digest_value = seal.get("definition_sha256")
        if (
            not isinstance(digest_value, str)
            or len(digest_value) != 64
            or any(char not in "0123456789abcdef" for char in digest_value)
        ):
            raise ValueError("VIKE_SELECTED_PORTFOLIO_SEAL_NOT_VERIFIED")
        with closing(_readonly(registry_db)) as conn:
            conn.execute("BEGIN")
            try:
                for alias in profile.full_aliases:
                    rows = conn.execute(
                        "SELECT DISTINCT w.address FROM wallets w "
                        "JOIN wallet_aliases a ON a.wallet_id=w.wallet_id "
                        "WHERE a.alias=? AND a.known_at<=?",
                        (alias, as_of),
                    ).fetchall()
                    if len(rows) != 1:
                        raise ValueError("VIKE_SELECTED_ALIAS_IDENTITY_AMBIGUOUS")
                    accounts.add(allowed_wallet(rows[0][0]))
            finally:
                conn.execute("ROLLBACK")
    return tuple(sorted(accounts))


def selected_subscription(wallets: tuple[str, ...], cursor: str | None) -> dict:
    selected = tuple(sorted({allowed_wallet(item) for item in wallets}))
    if not selected or len(selected) > 1000 or len(selected) != len(wallets):
        raise ValueError("VIKE_SELECTED_WALLET_UNIVERSE_INVALID")
    request_body = {
        "action": "subscribe", "id": SUB_ID, "channel": CHANNEL,
        "filter": {"wallet": list(selected), "min_usd": 0},
    }
    if cursor is not None:
        request_body["cursor"] = _cursor(cursor)
    return request_body


def open_selected_journal(root: Path) -> sqlite3.Connection:
    if root.is_symlink() or any(item.is_symlink() for item in root.parents):
        raise ValueError("VIKE_SELECTED_SYMLINK_PATH")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError("VIKE_SELECTED_JOURNAL_NOT_PRIVATE")
    path = root / "selected-fills.sqlite3"
    if path.is_symlink():
        raise ValueError("VIKE_SELECTED_DB_SYMLINK")
    conn = sqlite3.connect(path, timeout=2)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(SCHEMA)
    path.chmod(0o600)
    return conn


def current_cursor(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT cursor FROM selected_checkpoint WHERE id=1").fetchone()
    return row[0] if row else None


def had_gap(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT had_gap FROM selected_checkpoint WHERE id=1").fetchone()
    return bool(row and row[0])


def _checkpoint(conn: sqlite3.Connection, cursor: str, known_at: str, gap: bool) -> None:
    previous = current_cursor(conn)
    if previous is not None and cursor < previous:
        return
    conn.execute(
        "INSERT INTO selected_checkpoint VALUES(1,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET cursor=excluded.cursor,"
        "had_gap=MAX(selected_checkpoint.had_gap,excluded.had_gap),"
        "last_received_at=excluded.last_received_at",
        (cursor, int(gap), known_at),
    )


def _record_transport(conn: sqlite3.Connection, known_at: str, kind: str) -> None:
    _stamp(known_at)
    if kind not in ("PING", "SUBSCRIBED"):
        raise ValueError("VIKE_SELECTED_TRANSPORT_KIND_INVALID")
    with conn:
        conn.execute(
            "INSERT INTO selected_transport VALUES(1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "last_server_frame_at=excluded.last_server_frame_at, "
            "ping_count=selected_transport.ping_count+excluded.ping_count, "
            "subscription_count=selected_transport.subscription_count+"
            "excluded.subscription_count",
            (known_at, int(kind == "PING"), int(kind == "SUBSCRIBED")),
        )


def record_event(
    conn: sqlite3.Connection, event: dict, *,
    cursor: str, known_at: str, wallets: tuple[str, ...], prospective: bool,
) -> str:
    """Atomic event and checkpoint commit; catch-up never fabricates local receipt."""
    from hashlib import sha256

    stamp, frame_cursor = _stamp(known_at), _cursor(cursor)
    wallet = (event.get("subject") or {}).get("wallet")
    if not isinstance(wallet, str) or wallet.lower() not in wallets:
        raise ValueError("VIKE_SELECTED_EVENT_WALLET_UNKNOWN")
    eid, trade_id, _, raw, digest = validate_event(event, wallet.lower())
    if _stamp(event["ts"]) > stamp:
        raise ValueError("VIKE_SELECTED_EVENT_AFTER_RECEIPT")
    with conn:
        prior = conn.execute(
            "SELECT raw_sha FROM selected_fills WHERE event_id=?", (eid,),
        ).fetchone()
        if prior is not None and prior[0] != digest:
            raise ValueError("VIKE_SELECTED_EVENT_PAYLOAD_DRIFT")
        if prior is None:
            conn.execute(
                "INSERT INTO selected_fills VALUES (?,?,?,?,?,?,?,?,?)",
                (eid, frame_cursor, sha256(wallet.lower().encode()).hexdigest(),
                 trade_id, event["ts"], known_at, digest, raw, int(prospective)),
            )
        _checkpoint(conn, frame_cursor, known_at, False)
    return "DUPLICATE" if prior else ("PROSPECTIVE_FILL" if prospective else "RECOVERED_FILL")


def apply_frame(
    conn: sqlite3.Connection, frame: dict, wallets: tuple[str, ...],
    known_at: str, *, prospective: bool = True,
) -> str:
    kind = frame.get("type")
    if kind == "ping":
        _record_transport(conn, known_at, "PING")
        return "PONG_REQUIRED"
    if kind == "error":
        raise ValueError("VIKE_SELECTED_SERVER_ERROR")
    if kind == "subscribed":
        if frame.get("id") != SUB_ID or frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_SELECTED_ACK_MISMATCH")
        cursor = _cursor(frame.get("cursor"))
        with conn:
            if current_cursor(conn) is None:
                _checkpoint(conn, cursor, known_at, False)
        _record_transport(conn, known_at, "SUBSCRIBED")
        return "SUBSCRIBED"
    if kind == "gap":
        if frame.get("channel") != CHANNEL:
            raise ValueError("VIKE_SELECTED_GAP_CHANNEL")
        cursor = _cursor(frame.get("cursor"))
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO selected_gaps VALUES(?,?,?)",
                (cursor, known_at, "PROVIDER_STREAM_GAP"),
            )
            _checkpoint(conn, cursor, known_at, True)
        return "GAP"
    if kind != "event" or frame.get("ids") != [SUB_ID]:
        raise ValueError("VIKE_SELECTED_FRAME_INVALID")
    return record_event(
        conn, frame["event"], cursor=frame["cursor"], known_at=known_at,
        wallets=wallets, prospective=prospective,
    )


def recover_rest(
    conn: sqlite3.Connection, *,
    key: str, wallets: tuple[str, ...], max_pages: int = 5,
) -> dict:
    """Bounded REST catch-up from previously committed cursor, never PAPER_READY."""
    if not 1 <= max_pages <= 30:
        raise ValueError("VIKE_SELECTED_REST_BUDGET")
    cursor = current_cursor(conn)
    if not cursor:
        return {"status": "BLOCKED_NO_CURSOR_TO_RECOVER", "recovered": 0}
    recovered = 0
    for page_number in range(max_pages):
        query = parse.urlencode({
            "channel": CHANNEL, "wallet": ",".join(wallets),
            "min_usd": 0, "cursor": cursor, "limit": 500,
        })
        req = request.Request(
            REST + "?" + query,
            headers={"X-API-KEY": key,
                     "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0"},
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                body = response.read(2_000_001)
                known_at = datetime.now(UTC).isoformat()
        except (OSError, TimeoutError, error.URLError) as exc:
            raise ValueError("VIKE_SELECTED_REST_UNAVAILABLE") from exc
        if len(body) > 2_000_000:
            raise ValueError("VIKE_SELECTED_REST_RESPONSE_TOO_LARGE")
        doc = json.loads(body)
        if not isinstance(doc, dict) or not isinstance(doc.get("events"), list):
            raise ValueError("VIKE_SELECTED_REST_SCHEMA_INVALID")
        for item in doc["events"]:
            if not isinstance(item, dict):
                raise ValueError("VIKE_SELECTED_REST_ITEM_INVALID")
            if "gap" in item:
                apply_frame(conn, {
                    "type": "gap", "channel": CHANNEL, "cursor": item["cursor"],
                }, wallets, known_at)
                continue
            if item.get("event") is None:
                raise ValueError("VIKE_SELECTED_REST_EVENT_MISSING")
            status = record_event(
                conn, item["event"], cursor=item["cursor"],
                known_at=known_at, wallets=wallets, prospective=False,
            )
            recovered += status == "RECOVERED_FILL"
        next_cursor = _cursor(doc.get("next_cursor"))
        if next_cursor < cursor or (next_cursor == cursor and doc.get("has_more")):
            raise ValueError("VIKE_SELECTED_REST_CURSOR_REGRESSED")
        if type(doc.get("has_more")) is not bool:
            raise ValueError("VIKE_SELECTED_REST_HAS_MORE_INVALID")
        cursor = next_cursor
        if not doc["has_more"]:
            return {
                "status": "BLOCKED_GAP" if had_gap(conn) else "RECOVERED_RETROSPECTIVE_ONLY",
                "recovered": recovered, "pages": page_number + 1,
                "paper_eligible": False,
            }
    return {"status": "BLOCKED_REST_BUDGET_EXHAUSTED", "recovered": recovered,
            "paper_eligible": False}


async def run_selected(
    *, root: Path, key: str, wallets: tuple[str, ...],
    seconds: float,
) -> dict:
    from websockets.asyncio.client import connect

    from websockets.exceptions import ConnectionClosed

    with closing(open_selected_journal(root)) as conn:
        # The cursor checkpoint survives restart, but recovered events are
        # observational evidence, NEVER backdated actionable signals.
        stats = {"PROSPECTIVE_FILL": 0, "RECOVERED_FILL": 0,
                 "DUPLICATE": 0, "GAP": 0}
        deadline = monotonic() + seconds
        attempts = 0
        stop_reason = "BOUNDED_DURATION_COMPLETE"
        while monotonic() < deadline and attempts < 3:
            attempts += 1
            subscribed_head = None
            if attempts > 1 and current_cursor(conn):
                try:
                    recovery = recover_rest(conn, key=key, wallets=wallets)
                except (ValueError, TypeError):
                    stop_reason = "REST_RECOVERY_FAILED"
                    break
                if recovery["status"] != "RECOVERED_RETROSPECTIVE_ONLY":
                    stop_reason = recovery["status"]
                    break
                stats["RECOVERED_FILL"] += recovery["recovered"]
            try:
                async with connect(
                    URL, additional_headers={"X-API-KEY": key},
                    open_timeout=12, close_timeout=5, max_size=262144,
                    ping_interval=15, ping_timeout=12,
                ) as socket:
                    await socket.send(json.dumps(
                        selected_subscription(wallets, current_cursor(conn)),
                    ))
                    while monotonic() < deadline:
                        try:
                            raw = await asyncio.wait_for(
                                socket.recv(), timeout=max(.05, deadline - monotonic()),
                            )
                        except TimeoutError:
                            break
                        frame = json.loads(raw)
                        if frame.get("type") == "subscribed":
                            subscribed_head = _cursor(frame.get("cursor"))
                        # The server's subscribed head separates old replay
                        # from later live frames. Unknown epochs fail closed.
                        is_live = (
                            subscribed_head is not None
                            and frame.get("type") == "event"
                            and _cursor(frame["cursor"]) > subscribed_head
                            and not had_gap(conn)
                        )
                        status = apply_frame(
                            conn, frame, wallets, datetime.now(UTC).isoformat(),
                            prospective=is_live,
                        )
                        if status == "PONG_REQUIRED":
                            await socket.send('{"action":"pong"}')
                        if status in stats:
                            stats[status] += 1
                if monotonic() < deadline:
                    stop_reason = "UNEXPECTED_WEBSOCKET_CLOSE"
                else:
                    stop_reason = "BOUNDED_DURATION_COMPLETE"
                    break
            except ConnectionClosed as exc:
                code = getattr(getattr(exc, "rcvd", None), "code", None)
                if code == 4410:
                    stop_reason = "REPLACED_BY_OTHER_CONNECTION_4410"
                    break
                if code in (4401, 4403):
                    stop_reason = "CREDENTIAL_REFUSED"
                    break
                stop_reason = "WEBSOCKET_DISCONNECT"
            except (OSError, TimeoutError):
                stop_reason = "WEBSOCKET_TRANSPORT_UNAVAILABLE"
            if monotonic() < deadline and attempts < 3:
                await asyncio.sleep(min(2**attempts, max(0, deadline - monotonic())))
        else:
            if monotonic() < deadline and attempts >= 3:
                stop_reason = "BOUNDED_RECONNECT_BUDGET_EXHAUSTED"
        heartbeat = conn.execute(
            "SELECT ping_count,subscription_count,last_server_frame_at "
            "FROM selected_transport WHERE id=1"
        ).fetchone()
        return {
            "schema": "vike_selected_fill_observer_v1",
            "transport_pings": heartbeat[0] if heartbeat else 0,
            "subscription_acknowledgments": heartbeat[1] if heartbeat else 0,
            "last_server_frame_at": heartbeat[2] if heartbeat else None,
            "status": (
                "BLOCKED_STREAM_GAP" if had_gap(conn)
                else "OBSERVED_FILL_INTAKE_ONLY"
                if stop_reason == "BOUNDED_DURATION_COMPLETE"
                else "BLOCKED_" + stop_reason
            ),
            "stop_reason": stop_reason,
            "reconnect_attempts": max(0, attempts - 1),
            "observed": stats,
            "cursor_persisted": current_cursor(conn) is not None,
            "source_positions_verified": False,
            "financial_events_committed": 0, "order_route": "NONE",
        }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-root", required=True, type=Path)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--wallets-file", type=Path,
                        help="Private JSON list of selected native addresses")
    source.add_argument("--registry-db", type=Path,
                        help="Sealed SQLite registry; no private addresses printed")
    p.add_argument("--portfolios", default="P1,P14,P16",
                   help="Comma-separated frozen portfolio IDs, for --registry-db")
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--dedicated-key-only", action="store_true")
    args = p.parse_args()
    if not 2 <= args.seconds <= 86400:
        p.error("--seconds must be 2..86400")
    key = os.environ.get("VIKE_API_KEY")
    if not key or not args.dedicated_key_only:
        print(json.dumps({"status": "BLOCKED_NO_DEDICATED_VIKE_KEY",
                          "state_created": False, "order_route": "NONE"}))
        return 2
    if args.registry_db is not None:
        selection = selected_wallets_from_registry(
            args.registry_db, portfolios=tuple(args.portfolios.split(",")),
            as_of=datetime.now(UTC).isoformat(),
        )
    else:
        private = args.wallets_file
        if private.is_symlink() or stat.S_IMODE(private.stat().st_mode) & 0o077:
            raise ValueError("VIKE_SELECTED_WALLETS_FILE_NOT_PRIVATE")
        wallets = json.loads(private.read_text())
        if not isinstance(wallets, list):
            raise ValueError("VIKE_SELECTED_WALLET_FILE_INVALID")
        selection = tuple(sorted(allowed_wallet(value) for value in wallets))
    selected_subscription(selection, None)
    try:
        result = asyncio.run(run_selected(
            root=args.state_root, key=key, wallets=selection, seconds=args.seconds,
        ))
    except Exception as exc:
        # Never emit sensitive wallet addresses, credentials, URLs or bodies.
        print(json.dumps({
            "status": "BLOCKED_SELECTED_STREAM",
            "error_class": type(exc).__name__,
            "order_route": "NONE",
        }))
        return 2
    print(json.dumps(result, sort_keys=True))
    # systemd RestartPreventExitStatus=42: never fight another process sharing
    # this key or retry revoked credentials in a replacement storm.
    if result.get("stop_reason") in (
        "REPLACED_BY_OTHER_CONNECTION_4410", "CREDENTIAL_REFUSED",
    ):
        return 42
    return 0 if result["status"] == "OBSERVED_FILL_INTAKE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
