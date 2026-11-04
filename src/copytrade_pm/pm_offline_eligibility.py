"""Strict, PIT-causal per-fill eligibility compiler for offline research only.

Input rows must already be independently reconciled *complete source-book*
observations by the source compiler. This module does not infer missing source
positions, receipts, equity, execution prices, or PM-03 account transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Literal

from .pm_offline_manifest import DELAYS, ManifestBlocked, ManifestInvalid


def compile_eligible(
    rows: list[dict],
    *,
    delay_minutes: int,
    clock_basis: Literal["HISTORICAL_ORACLE", "PROSPECTIVE_FIRST_KNOWN"],
    engine: Literal["streaming", "in-memory"] = "streaming",
    cutoff: datetime | None = None,
) -> dict:
    """Compile canonical last-observed whole-book instrument state at future open.

    Every source event gets its *own* eligibility clock. Identical bar/group
    candidates collapse only after eligibility. The next bar open is strictly
    after the eligibility instant, including exact minute boundaries.
    """
    if delay_minutes not in DELAYS or type(delay_minutes) is not int:
        raise ManifestInvalid("INVALID_DELAY")
    if clock_basis not in {"HISTORICAL_ORACLE", "PROSPECTIVE_FIRST_KNOWN"}:
        raise ManifestInvalid("UNKNOWN_CLOCK_BASIS")
    if engine not in ("streaming", "in-memory"):
        raise ManifestInvalid("INVALID_POLARS_ENGINE")
    if cutoff is not None and (cutoff.tzinfo is None or cutoff.utcoffset() is None):
        raise ManifestInvalid("NAIVE_CUTOFF")
    if not rows:
        raise ManifestBlocked("MISSING_FULL_BOOK_EVENTS")
    import polars as pl

    keys = {
        "account",
        "dex",
        "instrument",
        "event_id",
        "source_event_at",
        "first_known_at",
        "position_after",
    }
    seen = set()
    prepared = []
    from decimal import Decimal, InvalidOperation

    for row in rows:
        if not isinstance(row, dict) or keys - row.keys():
            raise ManifestInvalid("INCOMPLETE_EVENT_SCHEMA")
        identity = (row["account"], row["dex"], row["instrument"], row["event_id"])
        if any(not isinstance(value, str) or not value for value in identity):
            raise ManifestInvalid("INVALID_EVENT_IDENTITY")
        if identity in seen:
            raise ManifestInvalid("DUPLICATE_EVENT_IDENTITY")
        seen.add(identity)
        source = row["source_event_at"]
        known = row["first_known_at"]
        if not isinstance(source, datetime) or source.utcoffset() is None:
            raise ManifestInvalid("INVALID_SOURCE_CLOCK")
        if not isinstance(known, datetime) or known.utcoffset() is None:
            raise ManifestBlocked("MISSING_FIRST_KNOWN_CLOCK")
        source = source.astimezone(UTC)
        known = known.astimezone(UTC)
        if clock_basis == "PROSPECTIVE_FIRST_KNOWN" and known < source:
            raise ManifestInvalid("FIRST_KNOWN_BEFORE_SOURCE_EVENT")
        if clock_basis == "HISTORICAL_ORACLE" and known != source:
            raise ManifestInvalid("ORACLE_CLOCK_MUST_EQUAL_SOURCE_CLOCK")
        if clock_basis == "PROSPECTIVE_FIRST_KNOWN" and not row.get("receipt_sha256"):
            raise ManifestBlocked("MISSING_RECEIPT_PROVENANCE")
        try:
            position = Decimal(str(row["position_after"]))
        except (InvalidOperation, ValueError) as exc:
            raise ManifestInvalid("INVALID_POSITION") from exc
        if not position.is_finite():
            raise ManifestInvalid("INVALID_POSITION")
        prepared.append(
            {
                "account": identity[0],
                "dex": identity[1],
                "instrument": identity[2],
                "event_id": identity[3],
                "source_event_at": source,
                "first_known_at": known,
                "position_after": str(position),
            }
        )

    df = pl.DataFrame(prepared).lazy()
    compiled = (
        df.with_columns(eligible_at=(pl.col("first_known_at") + pl.duration(minutes=delay_minutes)))
        .with_columns(
            execute_open_at=pl.col("eligible_at").dt.truncate("1m") + pl.duration(minutes=1)
        )
        .sort(
            [
                "execute_open_at",
                "account",
                "dex",
                "instrument",
                "first_known_at",
                "source_event_at",
                "event_id",
            ]
        )
        .group_by(["execute_open_at", "account", "dex", "instrument"], maintain_order=False)
        .agg(
            pl.col("event_id").last(),
            pl.col("source_event_at").last(),
            pl.col("first_known_at").last(),
            pl.col("eligible_at").last(),
            pl.col("position_after").last(),
            pl.len().alias("collapsed_events"),
        )
        .sort(["execute_open_at", "account", "dex", "instrument"])
    )
    if cutoff is not None:
        compiled = compiled.filter(pl.col("execute_open_at") <= cutoff.astimezone(UTC))
    output = []
    for row in compiled.collect(engine=engine).to_dicts():
        output.append(
            {
                **{
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in row.items()
                },
                "clock_basis": clock_basis,
                "policy": "PER_FILL_ELIGIBILITY",
                "delay_minutes": delay_minutes,
            }
        )
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "pm_offline_eligible_tape_v1",
        "status": "HISTORICAL_ORACLE"
        if clock_basis == "HISTORICAL_ORACLE"
        else "PIT_RECEIPT_CLOCK",
        "events_in": len(rows),
        "events_out": len(output),
        "right_censored": len(rows) - sum(x["collapsed_events"] for x in output),
        "sha256": sha256(encoded).hexdigest(),
        "events": output,
    }
