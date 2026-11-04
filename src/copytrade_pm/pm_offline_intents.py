"""Per-fill, whole-wallet intent admission for offline PM-03 fixture studies.

Inputs are independently validated source-books, equity as-of observations
and named market clocks. This layer never derives source equity or a missing
hedge from individual fills. The separate Forward-Paper T+300s first-event
scheduler is deliberately not imported.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

from .pm_offline_eligibility import compile_eligible
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

SCHEMA = "pm_offline_whole_book_intents_v1"


def _utc(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ManifestInvalid("INVALID_INTENT_CLOCK") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ManifestInvalid("INVALID_INTENT_CLOCK")
    return value.astimezone(UTC)


def _finite(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ManifestInvalid("INVALID_INTENT_NUMBER") from exc
    if not result.is_finite():
        raise ManifestInvalid("NONFINITE_INTENT_NUMBER")
    return result


def _next_open(known: datetime, delay: int) -> datetime:
    eligible = known + timedelta(minutes=delay)
    return eligible.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _full_book(
    book: Any,
    leader_prices: Any,
    equity: Any,
    equity_at: Any,
    *,
    observation_at: datetime,
    execution_at: datetime,
    age: timedelta,
) -> tuple[dict[str, str], dict[str, str], str]:
    if not isinstance(book, dict) or not book:
        raise ManifestBlocked("MISSING_COMPLETE_SOURCE_BOOK")
    if not isinstance(leader_prices, dict):
        raise ManifestBlocked("MISSING_COMPLETE_SOURCE_LEADER_MARKS")
    if not set(leader_prices) <= set(book):
        raise ManifestInvalid("UNKNOWN_LEADER_MARK_IN_BOOK")
    book_qty = {k: _finite(q) for k, q in book.items()}
    marks = {k: _finite(px) for k, px in leader_prices.items()}
    if any(not isinstance(k, str) or not k for k in book):
        raise ManifestInvalid("INVALID_SOURCE_MARKET_ID")
    if any(q != 0 and k not in marks for k, q in book_qty.items()):
        raise ManifestBlocked("MISSING_NONZERO_HEDGE_LEADER_PRICE")
    if any(px <= 0 for px in marks.values()):
        raise ManifestBlocked("INVALID_SOURCE_LEADER_PRICE")
    nav = _finite(equity)
    known = _utc(equity_at)
    if nav <= 0:
        raise ManifestBlocked("INVALID_ASOF_SOURCE_EQUITY")
    if known > observation_at or known > execution_at:
        raise ManifestBlocked("FUTURE_KNOWN_SOURCE_EQUITY")
    if execution_at - known > age:
        raise ManifestBlocked("STALE_SOURCE_EQUITY_AT_EXECUTION")
    return (
        {str(k): str(q) for k, q in sorted(book_qty.items())},
        {str(k): str(q) for k, q in sorted(marks.items())},
        str(nav),
    )


def compile_whole_book_intents(
    source_events: list[dict],
    opening_books: dict[tuple[str, str], dict],
    *,
    delay_minutes: int,
    start: datetime,
    end: datetime,
    max_equity_age_minutes: int,
    clock_basis: str,
    engine: str = "streaming",
) -> dict:
    """Last eligible source event's FULL book wins, across all its instruments.

    A complete atomic initial snapshot is an independent admission event. Its
    eligible open is clamped to the study start, never treated as a zero book.
    Full books may only be used after each source event is individually due.
    """
    begin, finish = _utc(start), _utc(end)
    if begin >= finish or begin.second or begin.microsecond or finish.second or finish.microsecond:
        raise ManifestInvalid("INVALID_INTENT_STUDY_WINDOW")
    if type(max_equity_age_minutes) is not int or not 1 <= max_equity_age_minutes <= 1440:
        raise ManifestInvalid("INVALID_INTENT_EQUITY_AGE")
    age = timedelta(minutes=max_equity_age_minutes)
    if not opening_books:
        raise ManifestBlocked("MISSING_VERIFIED_OPENING_BOOK")
    events = compile_eligible(
        source_events,
        delay_minutes=delay_minutes,
        clock_basis=clock_basis,
        engine=engine,
        cutoff=finish - timedelta(minutes=1),
    )
    censored: dict[str, int] = {}
    for source in source_events:
        known_at = _utc(source["first_known_at"])
        if max(begin, _next_open(known_at, delay_minutes)) >= finish:
            manager = source["account"]
            censored[manager] = censored.get(manager, 0) + 1
    by_identity = {
        (row["account"], row["dex"], row["instrument"], row["event_id"]): row
        for row in source_events
    }
    prepared: list[tuple[datetime, str, str, datetime, datetime, str, dict]] = []
    for (account, dex), anchor in sorted(opening_books.items()):
        if anchor.get("atomic_source_verified") is not True:
            raise ManifestBlocked("UNVERIFIED_ATOMIC_OPENING_BOOK")
        known = _utc(anchor.get("first_known_at"))
        if clock_basis == "HISTORICAL_ORACLE":
            if anchor.get("first_known_basis") != "HISTORICAL_ORACLE":
                raise ManifestInvalid("INVALID_OPENING_CLOCK_BASIS")
        elif clock_basis != "PROSPECTIVE_FIRST_KNOWN":
            raise ManifestInvalid("UNSUPPORTED_OPENING_CLOCK_BASIS")
        if clock_basis == "PROSPECTIVE_FIRST_KNOWN" and not anchor.get("receipt_sha256"):
            raise ManifestBlocked("MISSING_OPENING_RECEIPT_PROVENANCE")
        when = max(begin, _next_open(known, delay_minutes))
        if when >= finish:
            continue
        prepared.append(
            (
                when,
                account,
                dex,
                known,
                known,
                "__initial__",
                {
                    "account": account,
                    "dex": dex,
                    "book": anchor.get("positions"),
                    "leader_prices": anchor.get("leader_prices", {}),
                    "source_equity": anchor.get("source_equity"),
                    "source_equity_known_at": anchor.get("source_equity_known_at"),
                    "verified_whole_book": True,
                    "source_clock_basis": clock_basis,
                    "event_id": "__initial__",
                },
            )
        )
    for row in events["events"]:
        identity = (row["account"], row["dex"], row["instrument"], row["event_id"])
        original = by_identity[identity]
        when = _utc(row["execute_open_at"])
        if when < begin:
            when = begin
        if when >= finish:
            continue
        first_known = _utc(row["first_known_at"])
        anchor = opening_books.get((row["account"], row["dex"]))
        if anchor is None:
            raise ManifestBlocked("SOURCE_FILL_WITHOUT_OPENING_BOOK")
        if first_known < _utc(anchor["first_known_at"]):
            raise ManifestBlocked("EVENT_KNOWN_BEFORE_OPENING_BOOK")
        source_at = _utc(row["source_event_at"])
        if when <= first_known + timedelta(minutes=delay_minutes):
            raise ManifestBlocked("EARLY_EXECUTION_BEFORE_OWN_ELIGIBILITY")
        prepared.append(
            (
                when,
                row["account"],
                row["dex"],
                first_known,
                source_at,
                row["event_id"],
                {
                    "account": row["account"],
                    "dex": row["dex"],
                    "book": original.get("whole_book_after"),
                    "leader_prices": original.get("leader_prices"),
                    "source_equity": original.get("source_equity"),
                    "source_equity_known_at": original.get("source_equity_known_at"),
                    "verified_whole_book": True,
                    "source_clock_basis": clock_basis,
                    "event_id": row["event_id"],
                },
            )
        )
    # The source compiler guarantees complete-book monotonic knowledge order.
    # Sorting by instrument would select the wrong "last" across two legs.
    prepared.sort(key=lambda x: x[:6])
    grouped: dict[tuple[datetime, str, str], dict] = {}
    for when, account, dex, known, source_at, event_id, update in prepared:
        if (account, dex) not in opening_books:
            raise ManifestBlocked("SOURCE_FILL_WITHOUT_OPENING_BOOK")
        full, marks, nav = _full_book(
            update["book"],
            update["leader_prices"],
            update["source_equity"],
            update["source_equity_known_at"],
            observation_at=known,
            execution_at=when,
            age=age,
        )
        expected = set(opening_books[(account, dex)]["positions"])
        if set(full) != expected:
            raise ManifestBlocked("SOURCE_BOOK_INSTRUMENT_DRIFT")
        native = {f"hyperliquid:mainnet:perp:{dex}:{market}": qty for market, qty in full.items()}
        known_prices = {
            f"hyperliquid:mainnet:perp:{dex}:{market}": px for market, px in marks.items()
        }
        grouped[(when, account, dex)] = {
            "manager": account,
            "book": native,
            "leader_prices": known_prices,
            "source_equity": nav,
            "verified_whole_book": True,
            "source_event_id": event_id,
            "source_known_at": known.isoformat(),
            "source_event_at": source_at.isoformat(),
            "source_equity_known_at": _utc(update["source_equity_known_at"]).isoformat(),
            "clock_basis": clock_basis,
        }
    updates: dict[str, list[dict]] = {}
    for (when, account, dex), value in sorted(grouped.items()):
        updates.setdefault(when.isoformat(), []).append(value)
    logical = {
        "schema": SCHEMA,
        "clock_basis": clock_basis,
        "policy": "PER_FILL_ELIGIBILITY",
        "delay_minutes": delay_minutes,
        "updates": updates,
        "source_events_in": len(source_events),
        "source_right_censored_by_manager": dict(sorted(censored.items())),
    }
    logical["sha256"] = sha256(
        json.dumps(logical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return logical
