"""E4: preserve an entire source wallet's signed position allocation.

A proportional common scalar can faithfully mirror *relative* positions only
when independent complete-book and equity evidence is available. This module
validates the input contract and mathematics; it does NOT authenticate the
truth of external account evidence, authorize trading, or create a second
account simulator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D, ROUND_DOWN
from hashlib import sha256
import json
import re
from typing import Any, Mapping

E4_SCHEMA = "pm_c_e4_full_wallet_books_v1"
E4_SOURCE_SCOPE = "ALL_HYPERLIQUID_MAINNET_PERP_DEX_AND_COLLATERAL"
E4_EVIDENCE_CLASS = "SOURCE_CONTRACT_ATTESTED_NOT_INDEPENDENTLY_AUTHENTICATED"
PODS = ("CO-001", "W015", "VS066")
ZERO = D(0)
ONE = D(1)
QUANTUM = D("0.000000000001")
POD_CAPITAL = D("2000")
STRESS_LIMIT = D("57")
START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)
SHA = re.compile(r"[0-9a-f]{64}\Z")
_NEEDED_ATTESTATIONS = (
    "all_dex_instrument_census_confirmed",
    "account_equity_reconciled",
    "collateral_and_funding_reconciled",
    "continuous_position_event_feed_confirmed",
)


def _stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("E4_INVALID_CLOCK")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("E4_INVALID_CLOCK") from exc
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("E4_CLOCK_MUST_BE_AWARE")
    return t.astimezone(UTC)


def _money(value: str, *, positive: bool = False) -> D:
    if not isinstance(value, str):
        raise ValueError("E4_DECIMAL_STRING_REQUIRED")
    try:
        num = D(value)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("E4_INVALID_NUMBER") from exc
    if not num.is_finite() or (positive and num <= ZERO):
        raise ValueError("E4_NONFINITE_OR_NONPOSITIVE")
    return num


def canonical_hash(payload: Any) -> str:
    return sha256(
        (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode()
    ).hexdigest()


def _parse_book(positions: object) -> dict[str, D]:
    if not isinstance(positions, dict):
        raise ValueError("E4_FULL_POSITION_MAP_REQUIRED")
    book: dict[str, D] = {}
    for name, raw in positions.items():
        # No heuristic native symbol mapping or silent exclusion of hedges.
        if not isinstance(name, str) or not name.startswith("hyperliquid/mainnet:perp:"):
            raise ValueError("E4_UNKNOWN_NATIVE_INSTRUMENT")
        try:
            from .pm03_account import Instrument

            inst = Instrument.parse(name)
        except (ValueError, TypeError) as exc:
            raise ValueError("E4_UNKNOWN_NATIVE_INSTRUMENT") from exc
        if inst.venue != "hyperliquid" or not inst.market.startswith("mainnet:perp:"):
            raise ValueError("E4_UNKNOWN_NATIVE_INSTRUMENT")
        parts = inst.market.split(":")
        if len(parts) != 3 or not parts[-1] or "/" in parts[-1]:
            raise ValueError("E4_UNKNOWN_NATIVE_INSTRUMENT")
        book[name] = _money(raw)
    return book


def validate_full_book_manifest(manifest: dict) -> dict:
    """Fail closed on incomplete wallet/equity source and chronology.

    An attestation flag is a *claimed source contract*, not an independent
    verification of exchange book or an authenticated historic receipt.
    """
    if not isinstance(manifest, dict) or manifest.get("schema") != E4_SCHEMA:
        raise ValueError("E4_REJECTS_EPISODE_OR_UNSUPPORTED_MANIFEST")
    if manifest.get("source_scope") != E4_SOURCE_SCOPE:
        raise ValueError("E4_UNVERIFIED_ALL_DEX_WALLET_SCOPE")
    if manifest.get("research_only") is not True or manifest.get("broker_authorized") is not False:
        raise ValueError("E4_NOT_AUTHORIZED_FOR_BROKER")
    if manifest.get("pods") != list(PODS):
        raise ValueError("E4_FROZEN_POD_ROSTER_MISMATCH")
    if _stamp(manifest.get("start")) != START or _stamp(manifest.get("end_exclusive")) != END:
        raise ValueError("E4_FROZEN_QUARTER_MISMATCH")
    wallets = manifest.get("wallets")
    if not isinstance(wallets, list) or len(wallets) != 3:
        raise ValueError("E4_THREE_COMPLETE_WALLETS_REQUIRED")
    grouped: dict[str, list[dict]] = {}
    universe: set[str] = set()
    positions_count = 0
    for item in wallets:
        if not isinstance(item, dict):
            raise ValueError("E4_INVALID_WALLET")
        pod = item.get("pod")
        if pod not in PODS or pod in grouped:
            raise ValueError("E4_UNKNOWN_OR_DUPLICATE_POD")
        identity = item.get("wallet_identity_sha256")
        if not isinstance(identity, str) or SHA.fullmatch(identity) is None:
            raise ValueError("E4_UNVERIFIED_WALLET_IDENTITY")
        snapshots = item.get("snapshots")
        if not isinstance(snapshots, list) or not snapshots:
            raise ValueError("E4_MISSING_COMPLETE_BOOK_SNAPSHOTS")
        previous_source = None
        previous_known = None
        previous_sequence = None
        rows = []
        for snap in snapshots:
            if not isinstance(snap, dict):
                raise ValueError("E4_INVALID_SNAPSHOT")
            for name in _NEEDED_ATTESTATIONS:
                if snap.get(name) is not True:
                    raise ValueError("E4_UNVERIFIED_SOURCE_" + name.upper())
            token = snap.get("source_evidence_sha256")
            if not isinstance(token, str) or SHA.fullmatch(token) is None:
                raise ValueError("E4_MISSING_SOURCE_EVIDENCE_SHA")
            source_at = _stamp(snap.get("source_event_at"))
            known_at = _stamp(snap.get("first_known_at"))
            if (
                source_at > known_at
                or known_at >= END
                or (previous_source is not None and source_at <= previous_source)
                or (previous_known is not None and known_at <= previous_known)
            ):
                raise ValueError("E4_NONCAUSAL_OR_NONMONOTONIC_SOURCE_CLOCK")
            sequence = snap.get("account_event_sequence")
            if type(sequence) is not int or sequence < 0:
                raise ValueError("E4_MISSING_ACCOUNT_EVENT_SEQUENCE")
            if previous_sequence is not None and sequence != previous_sequence + 1:
                raise ValueError("E4_MISSING_INTERMEDIATE_ACCOUNT_EVENTS")
            _money(snap.get("wallet_equity_usd"), positive=True)
            book = _parse_book(snap.get("positions"))
            previous_source, previous_known, previous_sequence = (source_at, known_at, sequence)
            rows.append(snap)
            universe.update(book)
            positions_count += sum(bool(q) for q in book.values())
        # Need a known full account book at or before the start of Q3; a
        # snapshot seen after start cannot assert what existed on July 1.
        if _stamp(rows[0]["first_known_at"]) > START:
            raise ValueError("E4_NO_PIT_BOOK_AT_QUARTER_START")
        grouped[pod] = rows
    if set(grouped) != set(PODS):
        raise ValueError("E4_MISSING_POD")
    return {
        "wallet_count": 3,
        "snapshot_count": sum(len(x) for x in grouped.values()),
        "nonzero_position_observations": positions_count,
        "native_instruments": sorted(universe),
        "wallets": grouped,
        "evidence_quality": E4_EVIDENCE_CLASS,
        "source_is_independently_verified": False,
        "true_historical_first_known_qualified": False,
        "live_authorized": False,
    }


def e4_size(
    book: Mapping[str, D],
    marks: Mapping[str, D],
    *,
    source_equity: D,
    capital_usd: D = POD_CAPITAL,
    shock: Mapping[str, D],
    cost_rate: D,
    stress_cap: D = STRESS_LIMIT,
) -> tuple[dict[str, D], D, str]:
    """One scalar for the entire signed book, preserving source ratios.

    Returns target, scalar and binding cap. Does NOT drop riskier hedges or
    individually normalize positions. Rounding is toward zero per market.
    """
    if source_equity <= ZERO or capital_usd <= ZERO or stress_cap <= ZERO:
        raise ValueError("E4_INVALID_CAPITAL_OR_EQUITY")
    if not all(x.is_finite() for x in (source_equity, capital_usd, stress_cap, cost_rate)):
        raise ValueError("E4_NONFINITE_CAPITAL")
    if cost_rate < ZERO:
        raise ValueError("E4_NEGATIVE_COST")
    if set(book) != set(marks) or set(book) != set(shock):
        raise ValueError("E4_INCOMPLETE_OR_EXTRA_HEDGE_MARKS")
    if not book:
        return {}, capital_usd / source_equity, "UNCONSTRAINED"
    source = {key: _money(str(q)) for key, q in book.items()}
    mark = {key: _money(str(p), positive=True) for key, p in marks.items()}
    moves = {key: _money(str(s)) for key, s in shock.items()}
    if any(v < ZERO for v in moves.values()):
        raise ValueError("E4_NEGATIVE_STRESS_MOVE")
    scale = capital_usd / source_equity
    target_risk = (
        sum((abs(q * mark[k]) * (moves[k] + cost_rate) for k, q in source.items()), ZERO) * scale
    )
    reason = "SOURCE_EQUITY_CAPITAL_SHARE"
    if target_risk > stress_cap:
        scale *= stress_cap / target_risk
        reason = "POD_STRESS_COMMON_SCALAR"
    result = {
        k: rounded
        for k, q in source.items()
        if (rounded := (q * scale).quantize(QUANTUM, rounding=ROUND_DOWN)) != ZERO
    }
    # A micro-hedge that rounds to zero changes the source allocation;
    # no silently suppressed exposure, even if its notional is small.
    if any(q != ZERO and k not in result for k, q in source.items()):
        raise ValueError("E4_UNREPRESENTABLE_SOURCE_MICROHEDGE")
    return result, scale, reason


def compare_wallet_ratios(
    source: Mapping[str, D], target: Mapping[str, D], *, tolerance: D = D("0.000000001")
) -> dict:
    """Exact signed proportionality with explicit rounding tolerance.

    This verifies the adapter's *intended* book, not PM-04 executed fills.
    """
    if tolerance < ZERO:
        raise ValueError("E4_INVALID_TOLERANCE")
    keys = {k for k, q in source.items() if q}
    if keys != {k for k, q in target.items() if q}:
        raise ValueError("E4_DROPPED_OR_INVENTED_POSITION")
    ratios = [target[k] / source[k] for k in sorted(keys)]
    if not ratios:
        return {"scale": None, "maximum_relative_scale_deviation": "0", "status": "FLAT"}
    scale = max(ratios)
    if scale <= ZERO:
        raise ValueError("E4_INVALID_REPLICATION_SCALE")
    maximum = max((abs(x - scale) / scale for x in ratios), default=ZERO)
    if maximum > tolerance:
        raise ValueError("E4_RELATIVE_WALLET_SIZING_NOT_PRESERVED")
    return {
        "scale": str(scale),
        "maximum_relative_scale_deviation": str(maximum),
        "status": "PROPORTIONAL_INTENDED_BOOK_ONLY",
    }


def to_pm04_manifest(payload: dict, *, allowed_market_ids: set[str] | None = None) -> dict:
    """Convert each complete snapshot *atomically* into one PM-04 input event.

    This conversion never filters an instrument. The market allowlist is a
    synthetic research-permitted list, NOT genuine broker instrument IDs.
    """
    audit = validate_full_book_manifest(payload)
    if allowed_market_ids is not None and set(audit["native_instruments"]) - allowed_market_ids:
        raise ValueError("E4_UNMAPPED_OR_UNAUTHORIZED_HEDGE")
    events = []
    for pod, books in audit["wallets"].items():
        for snap in books:
            observed = _stamp(snap["first_known_at"])
            first_decision = max(START, observed)
            # Always use a strictly later minute open than knowledge time.
            minute = first_decision.replace(second=0, microsecond=0) + timedelta(minutes=1)
            if minute >= END:
                raise ValueError("E4_ACTION_AFTER_QUARTER_END")
            events.append(
                {
                    "time": minute.isoformat(),
                    "source_at": _stamp(snap["source_event_at"]).isoformat(),
                    "first_known_at": observed.isoformat(),
                    "pod": pod,
                    "positions": snap["positions"],
                    "wallet_equity_usd": snap["wallet_equity_usd"],
                    "account_event_sequence": snap["account_event_sequence"],
                    "source_evidence_sha256": snap["source_evidence_sha256"],
                }
            )
    events.sort(key=lambda x: (x["time"], x["pod"], x["account_event_sequence"]))
    for prev, current in zip(events, events[1:]):
        if prev["time"] == current["time"] and prev["pod"] == current["pod"]:
            raise ValueError("E4_SAME_MINUTE_MULTIPLE_SOURCE_BOOKS")
    return {
        "schema": E4_SCHEMA,
        "classification": "E4_WALLET_COMPLETE_BOOK_CONTRACT_RESEARCH_ONLY",
        "source_independently_authenticated": False,
        "first_known_historical_economic_fact_verified": False,
        "historical_propr_instrument_ids_verified": False,
        "source_sample_selection": "ALL_CONTRACT_ATTESTED_SOURCE_ACCOUNT_EVENTS",
        "start": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "pods": list(PODS),
        "events": events,
        "instruments": audit["native_instruments"],
        "ranges": [
            {
                "pod": pod,
                "instrument": inst,
                "start": START.isoformat(),
                "end": END.isoformat(),
            }
            for pod in PODS
            for inst in audit["native_instruments"]
        ],
        "market_day_shas": {},
        "contract_audit": {k: v for k, v in audit.items() if k != "wallets"},
        "source_contract_sha256": canonical_hash(payload),
        "synthetic_research_only": True,
        "wallet_capital_usd": str(POD_CAPITAL),
        "source_requires_all_markets": True,
        # Private only: allows every replay to verify the complete source
        # contract and its SHA, rather than trusting a derived event list.
        "original_payload": payload,
    }
