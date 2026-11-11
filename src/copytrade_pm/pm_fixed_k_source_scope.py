"""Read-only, NAV-independent selected-source scope diagnostic.

Research observation is not independent live execution attestation. Source
positions and first-local clocks are required; unrelated source parent/child
collateral is neither required nor inferred for a *parent-only* copy policy.
"""

from __future__ import annotations

import re
from typing import Any

from .pm03_account import Instrument, clock, digest, number


def verified_source_native_marks(
    book: dict[str, Any],
    *,
    instruments: set[str],
    decision_at: str,
    max_age_seconds: int,
) -> dict[str, str]:
    """Require independently captured native valuation, never follower quote substitution.

    The age limit is an explicit future release input. The caller must obtain
    an evidence-derived venue/contract limit before activating a new release;
    this function does not invent one from historical bars or follower marks.
    """
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ValueError("SOURCE_MARK_AGE_POLICY_UNVERIFIED")
    if not isinstance(book, dict) or book.get("snapshot_sha") != digest(
        {key: value for key, value in book.items() if key != "snapshot_sha"}
    ):
        raise ValueError("SOURCE_MARK_BOOK_INTEGRITY_FAILURE")
    marks = book.get("source_marks")
    evidence = book.get("source_mark_evidence")
    if not isinstance(marks, dict) or not isinstance(evidence, dict):
        raise ValueError("SOURCE_MARK_EVIDENCE_MISSING")
    if not instruments.issubset(book.get("positions", {})):
        raise ValueError("SOURCE_MARK_POSITION_SCOPE_MISMATCH")
    try:
        cutoff = clock(decision_at)
    except (ValueError, TypeError) as exc:
        raise ValueError("SOURCE_MARK_DECISION_CLOCK_INVALID") from exc
    verified: dict[str, str] = {}
    for instrument in sorted(instruments):
        record = evidence.get(instrument)
        if not isinstance(record, dict) or not isinstance(marks.get(instrument), str):
            raise ValueError("SOURCE_MARK_EVIDENCE_MISSING:" + instrument)
        if (
            record.get("basis") != "OFFICIAL_POSITION_VALUE_DIV_ABS_NATIVE_QUANTITY"
            or record.get("mark") != marks[instrument]
            or record.get("native_frame_sha") != book.get("provider_raw_sha")
        ):
            raise ValueError("SOURCE_MARK_NATIVE_PROVENANCE_MISMATCH:" + instrument)
        value = number(record["mark"])
        if value <= 0:
            raise ValueError("SOURCE_MARK_NONPOSITIVE:" + instrument)
        try:
            observed = clock(record["event_at"])
            known = clock(record["first_known_at"])
        except (TypeError, KeyError, ValueError) as exc:
            raise ValueError("SOURCE_MARK_CLOCK_INVALID:" + instrument) from exc
        if (
            known != clock(book["first_known_at"])
            or not observed <= known <= cutoff
            or (cutoff - observed).total_seconds() > max_age_seconds
        ):
            raise ValueError("SOURCE_MARK_STALE_OR_FUTURE:" + instrument)
        verified[instrument] = str(value)
    return verified


def compare_native_fixed_k_economics(
    book: dict[str, Any],
    *,
    decision_at: str,
    source_mark_max_age_seconds: int,
    follower_quotes: dict[str, str],
    native_steps: dict[str, str],
    k: str,
    equity_usd: str,
    gross_cap_usd: str,
    market_cap_usd: str,
    pod_loss_budget_usd: str,
    taker_fee_bps: str,
    extra_slippage_bps: str,
) -> dict[str, object]:
    """Matched historical-vs-corrected intent, never follower profit evidence.

    Uses the existing sizing owner and independently verified native source
    mark. The old same-midpoint model is reported as a *legacy comparator*,
    not silently installed as a valid prospective leader price.
    """
    from decimal import ROUND_DOWN, Decimal

    from .pm_exposure_sizing import target_from_fixed_k

    scope = set(book["positions"])
    corrected_marks = verified_source_native_marks(
        book,
        instruments=scope,
        decision_at=decision_at,
        max_age_seconds=source_mark_max_age_seconds,
    )
    kwargs = {
        "source_quantities": {key: Decimal(qty) for key, qty in book["positions"].items()},
        "k": Decimal(k),
        "follower_marks": {key: Decimal(v) for key, v in follower_quotes.items()},
        "follower_equity_usd": Decimal(equity_usd),
        "max_gross_notional_usd": Decimal(gross_cap_usd),
        "max_market_notional_usd": Decimal(market_cap_usd),
        "pod_loss_budget_usd": Decimal(pod_loss_budget_usd),
    }
    legacy = target_from_fixed_k(
        **kwargs,
        source_marks=kwargs["follower_marks"],
    )
    corrected = target_from_fixed_k(
        **kwargs,
        source_marks={key: Decimal(v) for key, v in corrected_marks.items()},
    )
    fee = Decimal(taker_fee_bps)
    slippage = Decimal(extra_slippage_bps)
    if fee < 0 or slippage < 0:
        raise ValueError("PRICE_COMPARISON_NEGATIVE_EXECUTION_COST")
    comparisons = {}
    for key in sorted(scope):
        mark = Decimal(follower_quotes[key])
        step = Decimal(native_steps[key])
        if step <= 0:
            raise ValueError("PRICE_COMPARISON_NATIVE_STEP_INVALID")
        raw_old = Decimal(legacy["target_quantities"][key])
        raw_new = Decimal(corrected["target_quantities"][key])

        def quantize(qty: Decimal) -> Decimal:
            return (
                (abs(qty) / step).to_integral_value(rounding=ROUND_DOWN)
                * step
                * (1 if qty >= 0 else -1)
            )

        old_qty, new_qty = quantize(raw_old), quantize(raw_new)
        old_usd, new_usd = old_qty * mark, new_qty * mark
        comparisons[key] = {
            "legacy_follower_qty": str(old_qty),
            "corrected_follower_qty": str(new_qty),
            "follower_qty_delta": str(new_qty - old_qty),
            "legacy_follower_notional_usd": str(old_usd),
            "corrected_follower_notional_usd": str(new_usd),
            "follower_notional_delta_usd": str(new_usd - old_usd),
            "legacy_modeled_cost_usd": str(abs(old_usd) * (fee + slippage) / 10000),
            "corrected_modeled_cost_usd": str(abs(new_usd) * (fee + slippage) / 10000),
            "source_native_mark": corrected_marks[key],
            "follower_quote": str(mark),
            "native_step": str(step),
        }
    return {
        "schema": "v4_matched_price_semantics_diagnostic_v1",
        "decision_at": decision_at,
        "source_book_sha": book["snapshot_sha"],
        "legacy_policy": "legacy_same_follower_midpoint",
        "corrected_policy": "future_fixed_k_independent_native_mark_v1",
        "per_market": comparisons,
        "execution_cost_class": "STATIC_COST_SCENARIO_ONLY",
        "follower_net_pnl_evidence": "UNKNOWN_NOT_FROM_REAL_EXECUTIONS",
        "scientific_qualification": False,
        "trading_authorized": False,
    }


def assess_selected_parent_perp_scope(
    book: dict[str, Any] | None,
    *,
    decision_at: str,
    max_age_seconds: float = 180,
) -> dict[str, object]:
    reasons: list[str] = []
    if not isinstance(book, dict):
        return {
            "status": "BLOCKED",
            "reasons": ["SELECTED_SOURCE_BOOK_MISSING"],
            "source_nav_required": False,
            "position_scope_observed": False,
        }
    if book.get("schema") not in ("paper_source_book_v1", "paper_source_book_v2") or book.get(
        "snapshot_sha"
    ) != digest({key: value for key, value in book.items() if key != "snapshot_sha"}):
        reasons.append("SELECTED_SOURCE_SHA_OR_SCHEMA_INVALID")
    if (
        not isinstance(book.get("wallet_id"), str)
        or not book["wallet_id"]
        or not isinstance(book.get("account_id"), str)
        or re.fullmatch(r"[0-9a-f]{64}", book["account_id"]) is None
    ):
        reasons.append("SELECTED_SOURCE_IDENTITY_MISSING")
    if book.get("snapshot_kind") != "OFFICIAL_WS_PER_ACCOUNT_ALL_DEX_ONLY":
        reasons.append("SELECTED_SOURCE_NOT_PER_ACCOUNT_ALL_DEX")
    if book.get("synthetic_fixture") is not False:
        reasons.append("SELECTED_SOURCE_NOT_REAL_PUBLIC_OBSERVATION")
    census, observed = book.get("dex_census"), book.get("observed_dexes")
    if (
        not isinstance(census, list)
        or not census
        or not all(isinstance(x, str) and x for x in census)
        or len(set(census)) != len(census)
        or not isinstance(observed, list)
        or not all(isinstance(x, str) and x for x in observed)
        or len(set(observed)) != len(observed)
        or set(census) != set(observed)
    ):
        reasons.append("SELECTED_SOURCE_DEX_CENSUS_INCOMPLETE")
    raw_positions = book.get("positions")
    if not isinstance(raw_positions, dict):
        reasons.append("SELECTED_SOURCE_POSITIONS_UNKNOWN")
    else:
        try:
            for key, qty in raw_positions.items():
                inst = Instrument.parse(key)
                if inst.venue != "hyperliquid" or inst.market not in (census or ()):
                    raise ValueError
                number(qty)
        except ValueError, TypeError:
            reasons.append("SELECTED_SOURCE_POSITION_INVALID")
    try:
        source_at = clock(book["source_event_at"])
        known_at = clock(book["first_known_at"])
        now = clock(decision_at)
        if (
            not 0 <= (now - known_at).total_seconds() <= max_age_seconds
            or not source_at <= known_at
        ):
            raise ValueError
    except ValueError, TypeError, KeyError:
        reasons.append("SELECTED_SOURCE_CLOCK_STALE_OR_INVALID")
    # Provider raw SHA must come from the original official frame, even though
    # it is NOT a provider cryptographic signature / execution authorization.
    raw_sha = book.get("provider_raw_sha")
    if not isinstance(raw_sha, str) or re.fullmatch(r"[0-9a-f]{64}", raw_sha) is None:
        reasons.append("SELECTED_SOURCE_PROVIDER_FRAME_SHA_MISSING")
    return {
        "status": "SELECTED_SCOPE_OBSERVED_RESEARCH_ONLY" if not reasons else "BLOCKED",
        "reasons": sorted(set(reasons)),
        "source_nav_required": False,
        "position_scope_observed": not reasons,
        "source_equity_relative_fidelity": False,
        "source_account_scope": "PARENT_PERPS_ONLY",
        "trading_authorized": False,
        "order_route": "NONE",
    }
