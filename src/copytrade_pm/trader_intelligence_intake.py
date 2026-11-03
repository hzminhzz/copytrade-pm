"""Read-only as-known Trader Intelligence intake from the existing journal.

No second ledger, no network client, and no inferred account equity or books.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import timedelta

from .trader_intelligence import (
    ObservationSnapshot,
    WalletEvent,
    WalletIdentity,
    digest,
    utc,
)


def native_instrument(journal_id: str) -> str:
    """Map an exact supported source identifier; never strip the ticker."""
    parts = journal_id.split(":")
    if len(parts) != 5 or parts[:3] != ["hyperliquid", "mainnet", "perp"]:
        raise ValueError("UNKNOWN_JOURNAL_INSTRUMENT_NAMESPACE")
    if not parts[3] or not parts[4] or "/" in parts[3] or "/" in parts[4]:
        raise ValueError("UNKNOWN_JOURNAL_MARKET_ID")
    from .trader_intelligence import _instrument

    native = f"hyperliquid/mainnet:perp:{parts[3]}/{parts[4]}"
    _instrument(native)
    return native


def from_opportunity_journal(
    *,
    journal_db: Path,
    decision_at: str,
    roster_id: str,
    roster_known_at: str,
    wallets: tuple[WalletIdentity, ...],
    maximum_source_rows: int = 50_000,
    lookback_hours: int = 4,
) -> ObservationSnapshot:
    """Load a bounded, read-only PIT decision stream and retain unknown evidence.

    The roster's registration clock must be real; hindsight-selected rosters
    cannot be treated as independent historical OOS.
    """
    cut = utc(decision_at)
    if utc(roster_known_at) > cut:
        raise ValueError("FUTURE_MONITORED_ROSTER")
    if not 1 <= maximum_source_rows <= 500_000:
        raise ValueError("INVALID_SOURCE_ROW_BUDGET")
    if not 1 <= lookback_hours <= 24:
        raise ValueError("INVALID_JOURNAL_LOOKBACK")
    since = (cut - timedelta(hours=lookback_hours)).isoformat()
    cut_text = cut.isoformat()
    if journal_db.is_symlink() or not journal_db.is_file():
        raise ValueError("JOURNAL_MISSING_OR_SYMLINK")
    try:
        with closing(sqlite3.connect(f"file:{journal_db}?mode=ro", uri=True, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            # One consistent SQLite WAL snapshot across decisions, updates and
            # coverage barriers while the original producer continues writing.
            db.execute("BEGIN")
            tables = {
                str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"opportunity_decisions", "opportunity_state"}.issubset(tables):
                raise ValueError("UNKNOWN_OPPORTUNITY_JOURNAL_SCHEMA")
            rows = db.execute(
                "SELECT opportunity_id,first_source_id,first_ledger_seq,"
                "first_event_at,first_known_at,instrument_id,wallet_id,"
                "status,blocker,payload_json FROM opportunity_decisions "
                "WHERE first_known_at > ? AND first_known_at <= ? "
                "ORDER BY first_ledger_seq LIMIT ?",
                (since, cut_text, maximum_source_rows + 1),
            ).fetchall()
            if len(rows) > maximum_source_rows:
                raise ValueError("INCOMPLETE_JOURNAL_SOURCE_WINDOW")
            barriers = (
                db.execute(
                    "SELECT ledger_seq,known_at FROM source_coverage_barriers "
                    "WHERE known_at<=? ORDER BY ledger_seq",
                    (cut_text,),
                ).fetchall()
                if "source_coverage_barriers" in tables
                else []
            )
            update_cols = (
                {str(c[1]) for c in db.execute("PRAGMA table_info(opportunity_updates)")}
                if "opportunity_updates" in tables
                else set()
            )
            full_fields = {
                "source_id",
                "opportunity_id",
                "ledger_seq",
                "event_at",
                "known_at",
                "status",
                "payload_json",
            }
            has_full_updates = full_fields.issubset(update_cols)
            updates = (
                db.execute(
                    (
                        "SELECT source_id,opportunity_id,ledger_seq,event_at,known_at,"
                        "status,payload_json FROM opportunity_updates "
                        if has_full_updates
                        else "SELECT opportunity_id,ledger_seq,known_at,status "
                        "FROM opportunity_updates "
                    )
                    + "WHERE known_at > ? AND known_at <= ? "
                    "ORDER BY ledger_seq LIMIT ?",
                    (since, cut_text, maximum_source_rows * 20 + 1),
                ).fetchall()
                if "opportunity_updates" in tables
                else []
            )
            if len(updates) > maximum_source_rows * 20:
                raise ValueError("INCOMPLETE_JOURNAL_UPDATE_WINDOW")
    except sqlite3.Error as exc:
        raise ValueError("UNREADABLE_OPPORTUNITY_JOURNAL") from exc

    barrier_seq = max(
        (int(r["ledger_seq"]) for r in barriers if utc(str(r["known_at"])) <= cut),
        default=0,
    )
    latest_updates: dict[str, sqlite3.Row] = {}
    for update in updates:
        if utc(str(update["known_at"])) > cut:
            continue
        key = str(update["opportunity_id"])
        if key and (
            key not in latest_updates
            or int(update["ledger_seq"]) > int(latest_updates[key]["ledger_seq"])
        ):
            latest_updates[key] = update

    allowed = {w.alias for w in wallets}
    by_opportunity = {str(row["opportunity_id"]): row for row in rows}
    seen: set[str] = set()
    events: list[WalletEvent] = []
    for row in rows:
        first_event, known_at = str(row["first_event_at"]), str(row["first_known_at"])
        if utc(first_event) > cut or utc(known_at) > cut:
            continue
        if utc(known_at) < utc(first_event):
            raise ValueError("SOURCE_RECEIPT_PRECEDES_EVENT")
        alias = str(row["wallet_id"])
        if alias not in allowed:
            continue
        event_id = str(row["first_source_id"])
        if not event_id or event_id in seen:
            raise ValueError("DUPLICATE_SOURCE_TRANSITION_ID")
        seen.add(event_id)
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("INVALID_OPPORTUNITY_PAYLOAD") from exc
        if not isinstance(payload, dict) or payload.get("first_source_id") != event_id:
            raise ValueError("SOURCE_PAYLOAD_IDENTITY_CONFLICT")
        before, after = payload.get("source_quantity_before"), payload.get("source_quantity_after")
        if before is None or after is None:
            raise ValueError("SOURCE_POSITION_TRANSITION_MISSING")
        update = latest_updates.get(str(row["opportunity_id"]))
        blocked = (
            str(row["status"]) in ("INVALIDATED", "EXPIRED", "NO_COPY")
            or row["blocker"] is not None
            or int(row["first_ledger_seq"]) <= barrier_seq
            or (
                update is not None
                and str(update["status"]) in ("INVALIDATED", "EXPIRED", "NO_COPY")
            )
        )
        events.append(
            WalletEvent(
                event_id=event_id,
                wallet=alias,
                instrument=native_instrument(str(row["instrument_id"])),
                event_at=first_event,
                first_known_at=known_at,
                origin="PROSPECTIVE_OBSERVED",
                position_before=str(before),
                position_after=str(after),
                book_complete=None,
                source_equity_usd=None,
                strategy_style="UNKNOWN",
                source_sha256=digest(payload),
                verified_position_transition=not blocked,
            )
        )
    # Coalesced ADDs have their own first-known clocks; do not rewrite the
    # original first-entry payload with future state.
    if has_full_updates:
        for upd in updates:
            if str(upd["status"]) != "UPDATED" or utc(str(upd["known_at"])) > cut:
                continue
            original = by_opportunity.get(str(upd["opportunity_id"]))
            if original is None or str(original["wallet_id"]) not in allowed:
                continue
            if utc(str(original["first_known_at"])) > cut:
                continue
            source_id = str(upd["source_id"])
            if source_id == str(original["first_source_id"]):
                continue
            if not source_id or source_id in seen:
                raise ValueError("DUPLICATE_SOURCE_TRANSITION_ID")
            seen.add(source_id)
            known_at, event_at = str(upd["known_at"]), str(upd["event_at"])
            if utc(event_at) > utc(known_at) or utc(event_at) > cut:
                raise ValueError("SOURCE_UPDATE_EVENT_CLOCK_INVALID")
            try:
                payload = json.loads(str(upd["payload_json"]))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("INVALID_SOURCE_UPDATE_PAYLOAD") from exc
            if not isinstance(payload, dict) or not {"before", "after"}.issubset(payload):
                raise ValueError("INCOMPLETE_SOURCE_UPDATE_POSITION")
            latest = latest_updates.get(str(upd["opportunity_id"]))
            terminal = latest is not None and str(latest["status"]) in (
                "INVALIDATED",
                "EXPIRED",
                "NO_COPY",
            )
            events.append(
                WalletEvent(
                    event_id=source_id,
                    wallet=str(original["wallet_id"]),
                    instrument=native_instrument(str(original["instrument_id"])),
                    event_at=event_at,
                    first_known_at=known_at,
                    origin="PROSPECTIVE_OBSERVED",
                    position_before=str(payload["before"]),
                    position_after=str(payload["after"]),
                    book_complete=None,
                    source_equity_usd=None,
                    strategy_style="UNKNOWN",
                    source_sha256=digest(payload),
                    verified_position_transition=not (terminal or barrier_seq > 0),
                )
            )
    return ObservationSnapshot(
        roster_id=roster_id,
        roster_known_at=roster_known_at,
        wallets=wallets,
        events=tuple(events),
        roster_origin="PROSPECTIVE_OBSERVED",
    )


def historical_fill_events(
    *,
    wallet: str,
    raw_fill_rows: tuple[dict, ...],
    instrument_map: dict[str, str],
    source_page_sha256: str,
    source_schema: str = "HYPERX_PAGE",
) -> tuple[WalletEvent, ...]:
    """Historical vendor fills: explicit provider schema, no fictitious receipt."""
    from datetime import UTC, datetime
    from .trader_intelligence import _instrument, _sha, decimal

    _sha(source_page_sha256)
    position_field = {
        "HYPERX_PAGE": "start_position",
        "HYPERLIQUID_PUBLIC": "startPosition",
    }.get(source_schema)
    if position_field is None:
        raise ValueError("UNKNOWN_SOURCE_FILL_SCHEMA")
    events: list[WalletEvent] = []
    for row in raw_fill_rows:
        native = instrument_map.get(str(row["coin"]))
        if native is None:
            raise ValueError("UNKNOWN_SOURCE_INSTRUMENT_MAP")
        _instrument(native)
        if row.get("side") not in ("A", "B"):
            raise ValueError("UNKNOWN_HYPERX_FILL_SIDE")
        before, size = decimal(row[position_field]), decimal(row["sz"])
        if size <= 0:
            raise ValueError("INVALID_SOURCE_FILL_SIZE")
        after = before + (size if row["side"] == "B" else -size)
        event_time = datetime.fromtimestamp(int(row["time"]) / 1000, UTC).isoformat()
        events.append(
            WalletEvent(
                event_id=f"{wallet}:{row['tid']}:{native}",
                wallet=wallet,
                instrument=native,
                event_at=event_time,
                origin="HISTORICAL_PROXY",
                position_before=str(before),
                position_after=str(after),
                first_known_at=None,
                book_complete=None,
                source_equity_usd=None,
                strategy_style="UNKNOWN",
                observed_price=str(decimal(row["px"])),
                source_sha256=source_page_sha256,
            )
        )
    return tuple(events)
