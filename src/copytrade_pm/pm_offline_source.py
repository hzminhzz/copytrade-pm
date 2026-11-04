"""Conservative all-leg source-book and equity tape reconstruction.

Consumes only independently validated source records. Requires explicit initial
book snapshots and equity observations for each account/DEX; missing evidence
blocks the entire source account, never creates zero exposure by inference.
No execution, simulated balance, or PM-03 state is created here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import groupby
import json
from typing import Any

from .pm_offline_manifest import ManifestBlocked, ManifestInvalid


def _dt(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ManifestInvalid("INVALID_SOURCE_CLOCK")
    return value.astimezone(UTC)


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ManifestInvalid("INVALID_SOURCE_QUANTITY") from exc
    if not number.is_finite():
        raise ManifestInvalid("NONFINITE_SOURCE_QUANTITY")
    return number


def _nonempty(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestInvalid("INVALID_SOURCE_IDENTITY")
    return value


def _key(row: dict) -> tuple[str, str]:
    return (_nonempty(row.get("account")), _nonempty(row.get("dex")))


def _canonical(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode()).hexdigest()


def reconstruct_whole_books(
    *,
    fills: list[dict],
    initial_books: list[dict],
    equity_snapshots: list[dict],
    required_instruments: dict[tuple[str, str], set[str]],
    clock_basis: str,
    asof_max_age: timedelta,
) -> dict:
    """Reconcile each fill to an existing full-source-book/known-equity state.

    Input initial_books must be an independently verified atomic observation,
    not the union of separately observed fills or arbitrary REST fragments.
    For oracle research, source event time is the explicitly labelled
    retrospective clock. Prospective receipt SHA verification is upstream.
    """
    if clock_basis not in {"HISTORICAL_ORACLE", "PROSPECTIVE_FIRST_KNOWN"}:
        raise ManifestInvalid("UNSUPPORTED_CLOCK_BASIS")
    if not timedelta(0) < asof_max_age <= timedelta(days=7):
        raise ManifestInvalid("INVALID_EQUITY_FRESHNESS")
    if not required_instruments:
        raise ManifestBlocked("NO_EXPECTED_SOURCE_BOOK")
    state: dict[tuple[str, str], dict[str, Decimal]] = {}
    book_times: dict[tuple[str, str], datetime] = {}
    for row in initial_books:
        key = _key(row)
        if key in state:
            raise ManifestInvalid("DUPLICATE_INITIAL_BOOK")
        expected = required_instruments.get(key)
        if not expected:
            raise ManifestInvalid("UNKNOWN_INITIAL_ACCOUNT")
        if row.get("atomic_source_verified") is not True:
            raise ManifestBlocked("UNVERIFIED_ATOMIC_SOURCE_BOOK")
        positions = row.get("positions")
        if not isinstance(positions, dict) or positions.keys() != expected:
            raise ManifestBlocked("INCOMPLETE_INITIAL_HEDGE_BOOK")
        state[key] = {instrument: _decimal(qty) for instrument, qty in positions.items()}
        book_times[key] = _dt(row.get("first_known_at"))
    if state.keys() != required_instruments.keys():
        raise ManifestBlocked("MISSING_INITIAL_ACCOUNT_BOOK")

    equity: dict[tuple[str, str], list[tuple[datetime, Decimal]]] = {
        key: [] for key in required_instruments
    }
    for row in equity_snapshots:
        key = _key(row)
        if key not in equity:
            raise ManifestInvalid("UNKNOWN_EQUITY_ACCOUNT")
        if row.get("source_verified") is not True:
            raise ManifestBlocked("UNVERIFIED_EQUITY_SOURCE")
        nav = _decimal(row.get("equity"))
        if nav <= 0:
            raise ManifestBlocked("NONPOSITIVE_SOURCE_EQUITY")
        equity[key].append((_dt(row.get("first_known_at")), nav))
    for key, snapshots in equity.items():
        if not snapshots:
            raise ManifestBlocked("MISSING_SOURCE_EQUITY")
        snapshots.sort()
        if len({when for when, _ in snapshots}) != len(snapshots):
            raise ManifestInvalid("CONFLICTING_EQUITY_SNAPSHOT_CLOCK")

    seen: set[tuple[str, str, str, str]] = set()
    prepared: list[tuple] = []
    for row in fills:
        key = _key(row)
        instrument = _nonempty(row.get("instrument"))
        event_id = _nonempty(row.get("event_id"))
        if key not in state or instrument not in state[key]:
            raise ManifestBlocked("SOURCE_INSTRUMENT_OUTSIDE_COMPLETE_BOOK")
        identity = (*key, instrument, event_id)
        if identity in seen:
            raise ManifestInvalid("DUPLICATE_SOURCE_FILL")
        seen.add(identity)
        source_at = _dt(row.get("source_event_at"))
        known_at = _dt(row.get("first_known_at"))
        if known_at < source_at and clock_basis == "PROSPECTIVE_FIRST_KNOWN":
            raise ManifestInvalid("FIRST_KNOWN_BEFORE_SOURCE_FILL")
        if clock_basis == "HISTORICAL_ORACLE" and known_at != source_at:
            raise ManifestInvalid("HISTORICAL_ORACLE_CLOCK_MISMATCH")
        before, after = _decimal(row.get("position_before")), _decimal(row.get("position_after"))
        prepared.append((source_at, event_id, key, instrument, known_at, before, after))
    prepared.sort(key=lambda x: (x[0], x[2], x[3], x[1]))
    # Exchange TIDs (and lexical IDs) need not follow fill order within a
    # millisecond. Link from actual position_before/after, and block rather
    # than guess when the source leaves multiple possible paths.
    shadow = {key: dict(book) for key, book in state.items()}
    ordered = []
    for _, batch in groupby(prepared, key=lambda x: (x[0], x[2], x[3])):
        remaining = list(batch)
        while remaining:
            item = remaining[0]
            account_key, market = item[2], item[3]
            candidates = [row for row in remaining if row[5] == shadow[account_key][market]]
            if not candidates:
                raise ManifestBlocked("SOURCE_POSITION_DISCONTINUITY")
            if len(candidates) != 1:
                raise ManifestBlocked("AMBIGUOUS_SAME_TIMESTAMP_SOURCE_CHAIN")
            chosen = candidates[0]
            remaining.remove(chosen)
            ordered.append(chosen)
            shadow[account_key][market] = chosen[6]
    output = []
    last_source: dict[tuple[str, str], datetime] = {}
    last_known: dict[tuple[str, str], datetime] = {}
    for source_at, event_id, key, instrument, known_at, before, after in ordered:
        if source_at < last_source.get(key, source_at):
            raise ManifestInvalid("BACKWARD_SOURCE_CLOCK")
        last_source[key] = source_at
        if known_at < book_times[key]:
            raise ManifestBlocked("FILL_KNOWN_BEFORE_INITIAL_BOOK")
        if known_at < last_known.get(key, known_at):
            raise ManifestBlocked("OUT_OF_ORDER_SOURCE_RECEIPTS")
        last_known[key] = known_at
        if state[key][instrument] != before:
            raise ManifestBlocked("SOURCE_POSITION_DISCONTINUITY")
        matching = [(when, nav) for when, nav in equity[key] if when <= known_at]
        if not matching:
            raise ManifestBlocked("FUTURE_ONLY_SOURCE_EQUITY")
        observed_at, nav = matching[-1]
        if known_at - observed_at > asof_max_age:
            raise ManifestBlocked("STALE_SOURCE_EQUITY")
        state[key][instrument] = after
        output.append(
            {
                "account": key[0],
                "dex": key[1],
                "instrument": instrument,
                "event_id": event_id,
                "source_event_at": source_at.isoformat(),
                "first_known_at": known_at.isoformat(),
                "position_after": str(after),
                "whole_book_after": {part: str(qty) for part, qty in sorted(state[key].items())},
                "source_equity": str(nav),
                "source_equity_known_at": observed_at.isoformat(),
                "clock_basis": clock_basis,
            }
        )
    return {
        "schema": "pm_offline_source_book_v1",
        "clock_basis": clock_basis,
        "accounts": len(required_instruments),
        "events": output,
        "sha256": _canonical(output),
        "status": "HISTORICAL_ORACLE"
        if clock_basis == "HISTORICAL_ORACLE"
        else "RECEIPT_PROVENANCE_UPSTREAM",
    }
