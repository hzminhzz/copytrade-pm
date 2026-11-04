"""Phase 6B: independent, bounded snapshot shocks on historical observed source legs.

This is a *conditional oracle diagnostic*, NOT a full 90d backtest or a real
challenge-pass calculation. Fixed Gemini trade-copy k is not equity-faithful
without source-equity snapshots; lost/unknown legs NEVER become flat targets.
No broker or service adapter, no external requests, no orders.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal as D
import json
from pathlib import Path

from .pm03_account import Account, Instrument, Rulebook
from .pm03_risk import RiskEvidence, RiskPolicy, classify, loss_under_shock
from .pm_fill_replay import _market_instrument
from .pm_phase6b import START, END, WALLETS, fingerprint, safe_write_json
from .pm_phase6b_activity import SourceStep, load_events
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource

ZERO = D(0)
CAPITAL = D("10000")
REFERENCE_CAPITAL = D("100000")
POD_BUDGET_AGGREGATE = D("300")
SOFT_DAILY = D("350")
HARD_DAILY = D("450")
CONTRACT_TRAILING = D("1000")
P2_GROSS_LIMIT = D("20000")
P2_SYMBOL_CONCENTRATION = D("5000")
STUDY_STEP = timedelta(days=1)
WAIT = timedelta(minutes=5)


def _native(coin: str) -> Instrument:
    parts = _market_instrument(coin).split(":")
    if len(parts) != 5:
        raise MarketDataBlocked("NON_NATIVE_POSITION_IDENTITY")
    return Instrument("hyperliquid", "mainnet:perp:" + parts[3], parts[4])


def frozen_scalar_policy(phase5: dict) -> dict[str, dict[str, D]]:
    """Scale Gemini's frozen 100k k values to a 10k follower.

    The equal-capital controls derive k per nominal-percent from the frozen
    A/B base records: NOT originally Gemini portfolios, risk equalization or
    real historical source equity.
    """
    profiles = {p["portfolio_id"]: p for p in phase5["portfolios"]}
    pairs = {
        "A_base": "Ensemble_A_Pure_New50_1x",
        "A_active": "Ensemble_A_Pure_New50_Active_1.5x",
        "B_base": "Ensemble_B_CrossCohort_Hybrid_1x",
        "B_active": "Ensemble_B_CrossCohort_Hybrid_Active_1.6x",
    }
    result = {}
    for short, original in pairs.items():
        p = profiles[original]
        got = {m["member_alias"]: D(str(m["original_weight_percent"])) for m in p["members"]}
        expected = {x: D(str(weight)) for x, weight in WALLETS[short].items()}
        if got != expected:
            raise ValueError("PHASE6B_FROZEN_WEIGHTS_MISMATCH")
        result[short] = {
            m["member_alias"]: D(str(m["original_effective_k"])) * CAPITAL / REFERENCE_CAPITAL
            for m in p["members"]
        }
    per_unit = {}
    for origin in ("A_base", "B_base"):
        p = profiles[pairs[origin]]
        for member in p["members"]:
            alias = member["member_alias"]
            if alias in per_unit:
                continue
            per_unit[alias] = D(str(member["original_effective_k"])) / D(
                str(member["original_weight_percent"])
            )
    for control in ("C_equal", "D_equal"):
        result[control] = {
            alias: per_unit[alias] * (D(100) / D(3)) * CAPITAL / REFERENCE_CAPITAL
            for alias in WALLETS[control]
        }
    return result


def sources_asof(events: list[SourceStep], at: datetime) -> tuple[dict[str, D], int]:
    """The latest AFTER from a historical event known at least 5m earlier.

    Does not assert there were no unseen additional positions. Do not extrapolate
    the before of a first fill backwards. All records are retrospective oracle.
    """
    if at.utcoffset() is None:
        raise ValueError("NAIVE_SNAPSHOT_TIME")
    by_coin = defaultdict(list)
    for event in events:
        by_coin[event.coin].append(event)
    known = {}
    unseen = 0
    cutoff = at - WAIT
    for coin, rows in by_coin.items():
        # load_events returns stable linked chains; never sort same-ms by TID.
        rows = sorted(rows, key=lambda x: x.t)
        index = bisect_right([r.t for r in rows], cutoff) - 1
        if index < 0:
            unseen += 1
            continue
        qty = rows[index].after
        if qty:
            known[coin] = qty
    return known, unseen


def _all_books(events: dict, at: datetime) -> tuple[dict[str, dict[str, D]], dict[str, int]]:
    books = {}
    unseen = {}
    for wallet, rows in events.items():
        books[wallet], unseen[wallet] = sources_asof(rows, at)
    return books, unseen


def _mark(
    quote: VerifiedHyperliquidMinuteSource,
    coin: str,
    at: datetime,
    cache: dict,
) -> tuple[D | None, str]:
    key = (coin, at)
    if key not in cache:
        try:
            bar = quote.get(_market_instrument(coin), at)
            cache[key] = (bar.open, bar.source_sha256)
        except (MarketDataBlocked, ValueError) as exc:
            cache[key] = (None, str(exc).split(":", 1)[0])
    return cache[key]


def _pm03_unknown_source_gate(
    per_pod: dict[str, dict[Instrument, D]],
    marks: dict[Instrument, D],
    at: datetime,
) -> dict:
    """Invoke the real PM03 supervisor with truthful UNKNOWN source evidence.

    Account/rulebook fixtures are synthetic, unconfirmed. NEVER turn the
    conditional market sensitivity into permission to fill or trade.
    """
    rulebook = Rulebook(
        program="PHASE6B_SYNTHETIC_UNCONFIRMED",
        stage="EVALUATION",
        source="RESEARCH_HISTORICAL_UNVERIFIED",
        observed_at="2026-08-01T00:00:00+00:00",
        version="phase6b-risk-gate-v1",
        timezone="UTC",
        initial_balance=CAPITAL,
        profit_target=D("1000"),
        daily_loss=None,
        daily_loss_rate=D("0.045"),
        static_loss=None,
        trailing_loss=D("1000"),
        trailing_cap=CAPITAL,
        permitted=(),
        confirmed=False,
        account_terms_confirmed=False,
    )
    account = Account.start(rulebook, at.isoformat())
    evidence = RiskEvidence(
        trusted=False,
        account_state_known=False,
        market_state_known=False,
        market_coverage_valid=False,
        pending_unknown_orders=True,
        input_status="RESEARCH_SYNTHETIC",
        pm02_qualified=False,
    )
    result = classify(account, per_pod, marks, (), evidence, RiskPolicy())
    if result["approved_new_risk"] or result["approved"]:
        raise ValueError("PM03_UNTRUSTED_ACCOUNT_ILLEGALLY_ADMITTED")
    return {
        "PM03_state": result["state"],
        "approved_new_risk": result["approved_new_risk"],
        "reason_codes": result["reason_codes"],
        "source_completeness_asserted": False,
        "broker_orders_sent": False,
        "synthetic_fixture_not_actual_source_equity": True,
    }


def _portfolio_observation(
    policy: str,
    multipliers: dict[str, D],
    books: dict[str, dict[str, D]],
    unseen: dict[str, int],
    market: VerifiedHyperliquidMinuteSource,
    at: datetime,
    cache: dict,
    previous_books: dict[str, dict[str, D]] | None = None,
) -> dict:
    per_pod: dict[str, dict[Instrument, D]] = {}
    marks: dict[Instrument, D] = {}
    missing = []
    quantities: dict[Instrument, D] = defaultdict(lambda: ZERO)
    gross_per_pod: dict[str, D] = defaultdict(lambda: ZERO)
    for alias, k in multipliers.items():
        per_pod[alias] = {}
        for coin, source_qty in books[alias].items():
            native = _native_or_none(coin)
            if native is None:
                missing.append(
                    {"wallet": alias, "instrument": coin, "reason": "UNSUPPORTED_NATIVE_MARKET"}
                )
                continue
            px, reason = _mark(market, coin, at, cache)
            if px is None:
                missing.append({"wallet": alias, "instrument": coin, "reason": reason})
                continue
            if native in marks and marks[native] != px:
                raise ValueError("NONMATCHING_SAME_MINUTE_NATIVE_MARK")
            marks[native] = px
            qty = source_qty * k
            quantities[native] += qty
            per_pod[alias][native] = qty
            gross_per_pod[alias] += abs(qty * px)
    gross = sum((abs(qty * marks[k]) for k, qty in quantities.items()), ZERO)
    net = sum((qty * marks[k] for k, qty in quantities.items()), ZERO)
    total_source_legs_gross = sum(gross_per_pod.values(), ZERO)
    shock = {}
    for percent in (D("0.10"), D("0.20"), D("0.30")):
        adverse = {k: -percent for k in quantities}
        shock[f"S3_crash_{int(percent * 100)}pct"] = loss_under_shock(quantities, marks, adverse)
    short_gross = sum((-q * marks[k] for k, q in quantities.items() if q < 0), ZERO)
    shock["S4_short_squeeze_plus50pct"] = short_gross * D("0.50")
    shock["S2_all_pod_sign_adverse_10pct"] = total_source_legs_gross * D("0.10")
    shock["S5_exit_30bps_extra_execution_drag"] = gross * D("0.0030")
    max_known_leg_model_loss = max(shock.values(), default=ZERO)
    simultaneous_shock_10 = shock["S2_all_pod_sign_adverse_10pct"]
    pod_count = len(multipliers)
    pod_loss_proxy = {alias: gross_per_pod[alias] * D("0.10") for alias in multipliers}
    concentration = max((abs(q * marks[k]) for k, q in quantities.items()), default=ZERO)
    # A dollar budget on each pod is a HYPOTHETICAL P1 rule. Gemini Phase5
    # included nominal weights but no independently ratified pod-loss limits.
    p0 = []
    if simultaneous_shock_10 >= HARD_DAILY:
        p0.append("MODEL_DAILY_HARD_LOSS_SENSITIVITY")
    if max_known_leg_model_loss >= CONTRACT_TRAILING:
        p0.append("MODEL_TRAILING_FLOOR_SENSITIVITY")
    p1 = p0 + (
        ["P1_MODEL_POD_LOSS_BUDGET"]
        if any(x >= POD_BUDGET_AGGREGATE / pod_count for x in pod_loss_proxy.values())
        else []
    )
    p2 = p1 + (["P2_SOFT_DAILY_SENSITIVITY"] if simultaneous_shock_10 >= SOFT_DAILY else [])
    if gross > P2_GROSS_LIMIT:
        p2.append("P2_GROSS_LEVERAGE_PROXY_CAP")
    if concentration > P2_SYMBOL_CONCENTRATION:
        p2.append("P2_INSTRUMENT_CONCENTRATION_PROXY_CAP")
    absent_source = sum(unseen[alias] for alias in multipliers)
    admissible = not missing and absent_source == 0
    # S7 removes each observed pod with no renormalization. The true account
    # could include omitted legs; this is NOT portfolio alpha attribution.
    leave_one_out = {}
    for alias, pod in per_pod.items():
        without = {inst: q - pod.get(inst, ZERO) for inst, q in quantities.items()}
        leave_one_out[alias] = {
            "priced_gross_without_pod_usd": str(
                sum((abs(q * marks[inst]) for inst, q in without.items()), ZERO)
            ),
            "net_30pct_crash_model_loss_usd": str(
                loss_under_shock(without, marks, {inst: D("-0.30") for inst in without})
            ),
            "risk_normalized": False,
        }
    # S6 denies new risk on unknown market and source states. Flatten is never
    # called executed without independent fill and fresh quote evidence.
    missing_source = absent_source or missing
    s6 = {
        "missing_or_unverified_legs": bool(missing_source),
        "would_block_new_risk": bool(missing_source),
        "flatten_requested": bool(missing_source),
        "flatten_executed": None,
        "remaining_exposure_known": False,
        "account_halt_latched": None,
    }
    s1 = (
        _hour_hold_diagnostic(multipliers, previous_books, market, at, cache)
        if previous_books is not None
        else None
    )
    # Unverified all-DEX account scope and historical equity ALWAYS block
    # complete account risk and execution even if all observed legs are priced.
    status = "PARTIAL_OBSERVED_LEGS_ONLY" if quantities else "NO_PRICED_OBSERVED_LEGS"
    return {
        "portfolio": policy,
        "snapshot_at": at.isoformat(),
        "status": status,
        "frozen_reference_scalars": {k: str(v) for k, v in multipliers.items()},
        "source_unobserved_coin_count": absent_source,
        "source_missing_market_leg_count": len(missing),
        "missing_legs": missing,
        "priced_observed_leg_count": sum(len(x) for x in per_pod.values()),
        "priced_distinct_instruments": len(quantities),
        "priced_gross_notional_usd": str(gross),
        "priced_source_pod_gross_usd": {k: str(v) for k, v in gross_per_pod.items()},
        "priced_net_notional_usd": str(net),
        "priced_short_gross_usd": str(short_gross),
        "known_leg_instantaneous_model_losses_usd": {k: str(v) for k, v in shock.items()},
        "S1_frozen_one_hour_held_leg_diagnostic": s1,
        "S6_missing_feed_response_model": s6,
        "S7_leave_one_out_model": leave_one_out,
        "PM03_actual_supervisor_unknown_source_gate": _pm03_unknown_source_gate(per_pod, marks, at),
        "hypothetical_initial_equity_usd": "10000",
        "model_supervisor": {
            "P0": {"model_veto_reasons": p0},
            "P1": {"model_veto_reasons": p1},
            "P2": {"model_veto_reasons": p2},
        },
        "all_observed_legs_priced": admissible,
        "whole_wallet_equity_reconstructed": False,
        "actual_follower_pnl_usd": None,
        "actual_challenge_first_passage": None,
        "price_provenance": "EXACT_SHA_NATIVE_1M_OPEN_PROXY_NOT_MARK_OR_BID_ASK",
        "actionable": False,
    }


def _native_or_none(coin: str) -> Instrument | None:
    try:
        return _native(coin)
    except MarketDataBlocked, ValueError:
        return None


def _hour_hold_diagnostic(
    multipliers: dict[str, D],
    previous_books: dict[str, dict[str, D]],
    market: VerifiedHyperliquidMinuteSource,
    at: datetime,
    cache: dict,
) -> dict:
    """S1: mark frozen T-1h observed holdings across exactly one hour.

    This is a historical past-hour *snapshot sensitivity*, not an account
    execution replay: source trades inside the hour are not replayed here.
    """
    begin = at - timedelta(hours=1)
    pnl = ZERO
    missing = 0
    observed = 0
    for alias, k in multipliers.items():
        for coin, source_qty in previous_books[alias].items():
            prior_price, _ = _mark(market, coin, begin, cache)
            current_price, _ = _mark(market, coin, at, cache)
            if prior_price is None or current_price is None:
                missing += 1
                continue
            pnl += source_qty * k * (current_price - prior_price)
            observed += 1
    return {
        "model_pnl_usd_on_priced_prior_holdings": str(pnl),
        "source_holdings_anchored_asof": (begin - WAIT).isoformat(),
        "price_start_at": begin.isoformat(),
        "price_end_at": at.isoformat(),
        "verified_prior_held_legs": observed,
        "missing_prior_held_leg_quotes": missing,
        "assumption": "ONE_HOUR_STATIC_SOURCE_HOLDINGS_WITHOUT_INTERVENING_REBALANCE",
        "complete_follower_account_economics": False,
    }


def _temporal_stability(snapshots: list[dict], portfolios: list[str]) -> dict:
    """S8: predeclared three 30-day slices, no return imputation."""
    out = {}
    for portfolio in portfolios:
        samples = [r for r in snapshots if r["portfolio"] == portfolio]
        bins = []
        for start_day in (0, 30, 60):
            left = START + timedelta(days=start_day)
            end = left + timedelta(days=30)
            rows = [r for r in samples if left <= datetime.fromisoformat(r["snapshot_at"]) < end]
            losses = [
                D(r["known_leg_instantaneous_model_losses_usd"]["S3_crash_30pct"]) for r in rows
            ]
            bins.append(
                {
                    "start": left.isoformat(),
                    "end_exclusive": end.isoformat(),
                    "n_fixed_snapshots": len(rows),
                    "n_any_observed_leg_priced": sum(
                        r["priced_observed_leg_count"] > 0 for r in rows
                    ),
                    "n_missing_pricing": sum(
                        r["source_missing_market_leg_count"] > 0 for r in rows
                    ),
                    "max_observed_leg_crash30pct_model_loss_usd": str(max(losses, default=ZERO)),
                    "sharpe": None,
                    "realized_pnl": None,
                    "out_of_sample_qualified": False,
                }
            )
        out[portfolio] = bins
    return out


def _verify_consumed_native_shas(
    consumed: dict[str, str],
    audit: dict,
    day_rows: dict,
) -> None:
    """Price source SHA must match the *previously frozen* independent audit."""
    for tagged, digest in consumed.items():
        native, day = tagged.rsplit("@", 1)
        parts = native.split(":")
        if len(parts) != 5 or parts[:3] != ["hyperliquid", "mainnet", "perp"]:
            raise ValueError("NATIVE_MARKET_CONSUMPTION_SCOPE_MISMATCH")
        coin = parts[4] if parts[3] == "default" else parts[3] + ":" + parts[4]
        if coin not in audit["instruments"]:
            raise ValueError("NATIVE_MARKET_OUTSIDE_FROZEN_AUDIT")
        key = (coin, day)
        if key not in day_rows:
            day_rows[key] = {
                r["day"]: r.get("sha256") for r in audit["instruments"][coin]["days"]
            }.get(day)
        if day_rows[key] != digest:
            raise ValueError("NATIVE_MARKET_SHA_DRIFT_VS_FROZEN_AUDIT")


def _reduce(daily: list[dict], policies: list[str]) -> dict:
    out = {}
    for p in policies:
        rows = [r for r in daily if r["portfolio"] == p]
        priced = sum(r["priced_observed_leg_count"] for r in rows)
        gross = [
            D(r["priced_gross_notional_usd"]) for r in rows if r["priced_observed_leg_count"] > 0
        ]
        maximum = {
            key: max(
                (D(r["known_leg_instantaneous_model_losses_usd"][key]) for r in rows), default=ZERO
            )
            for key in (
                "S2_all_pod_sign_adverse_10pct",
                "S3_crash_10pct",
                "S3_crash_20pct",
                "S3_crash_30pct",
                "S4_short_squeeze_plus50pct",
                "S5_exit_30bps_extra_execution_drag",
            )
        }
        out[p] = {
            "snapshot_days": len(rows),
            "days_with_any_priced_leg": sum(r["priced_observed_leg_count"] > 0 for r in rows),
            "days_all_observed_legs_priced": sum(r["all_observed_legs_priced"] for r in rows),
            "aggregate_priced_leg_observations": priced,
            "days_missing_one_or_more_mark": sum(
                r["source_missing_market_leg_count"] > 0 for r in rows
            ),
            "days_with_unobserved_future_coin_roster": sum(
                r["source_unobserved_coin_count"] > 0 for r in rows
            ),
            "maximum_known_leg_gross_usd": str(max(gross, default=ZERO)),
            "maximum_conditional_model_losses_usd": {k: str(v) for k, v in maximum.items()},
            "model_veto_days": {
                rule: sum(bool(r["model_supervisor"][rule]["model_veto_reasons"]) for r in rows)
                for rule in ("P0", "P1", "P2")
            },
            "complete_source_account_stress_runs": 0,
            "validated_challenge_probabilities": None,
        }
    return out


def run(
    *,
    phase5: Path,
    new50: Path,
    phase4_source: Path,
    coverage: Path,
    native_minute: Path,
    market_root: Path,
    output: Path,
) -> dict:
    audit = json.loads(native_minute.read_text())
    if audit.get("original_coverage_sha256") != fingerprint(coverage):
        raise ValueError("FROZEN_MARKET_AUDIT_SOURCE_SHA_MISMATCH")
    frozen = json.loads(phase5.read_text())
    scalar = frozen_scalar_policy(frozen)
    events = load_events(phase5, new50, phase4_source, coverage)
    snapshots = []
    consumed_days: dict[str, str] = {}
    audit_lookup: dict = {}
    at = START + timedelta(hours=12)
    while at < END:
        # Bound Parquet + Decimal memory to one day, reused across all pods.
        quote = VerifiedHyperliquidMinuteSource(market_root)
        cache = {}
        books, unseen = _all_books(events, at)
        previous_books, _ = _all_books(events, at - timedelta(hours=1))
        for p, mults in scalar.items():
            snapshots.append(
                _portfolio_observation(p, mults, books, unseen, quote, at, cache, previous_books)
            )
        _verify_consumed_native_shas(quote.source_days, audit, audit_lookup)
        consumed_days.update(quote.source_days)
        at += STUDY_STEP
    report = {
        "schema": "phase6b_daily_known_leg_snapshot_stress_v2",
        "research_only": True,
        "account_challenge_curve": None,
        "portfolio_source_equity_faithful": False,
        "source_receipt_first_known_verified": False,
        "never_fill_missing_positions": True,
        "study_start": START.isoformat(),
        "study_end": END.isoformat(),
        "snapshot_schedule": "fixed daily 16:30 UTC after retrospective five-minute source lag",
        "source_file_audit_sha256": fingerprint(coverage),
        "native_market_audit_sha256": fingerprint(native_minute),
        "consumed_native_day_count": len(consumed_days),
        "S8_30_day_temporal_sensitivity": _temporal_stability(snapshots, list(scalar)),
        "snapshot_basis": "SOURCE_AFTER_AT_MOST_T_MINUS_5M_KNOWN_IN_RETROSPECT",
        "capital_scalars": "ORIGINAL_GEMINI_100K_K_SCALED_0.1_NOT_ACCOUNT_EQUITY",
        "P0_P1_P2": "one-step initial-capital sensitivity; not historical kill-switch execution",
        "modeling_assumptions": {
            "hypothetical_initial_balance_usd": "10000",
            "daily_hard_usd": "450",
            "trailing_usd": "1000",
            "P1_aggregate_pod_budget_usd": "300",
            "P2_daily_soft_usd": "350",
            "P2_gross_cap_usd": "20000",
            "P2_instrument_cap_usd": "5000",
            "S2_max_model_loss_fraction_of_gross": "0.10",
            "S4_short_squeeze_fraction": "0.50",
            "S5_exit_incremental_cost_bps": 30,
        },
        "portfolio_summary": _reduce(snapshots, list(scalar)),
        "daily_snapshots": snapshots,
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    checksum = safe_write_json(output / "known_leg_snapshot_stress.json", report)
    return {
        "status": "CONDITIONAL_SENSITIVITY_COMPLETED_NOT_FULL_ACCOUNT",
        "snapshot_rows": len(snapshots),
        "portfolios": len(scalar),
        "sha256": checksum,
        "output": str(output / "known_leg_snapshot_stress.json"),
        "summary": report["portfolio_summary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase5", type=Path, required=True)
    parser.add_argument("--new50", type=Path, required=True)
    parser.add_argument("--phase4-source", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--native-minute", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                phase5=args.phase5,
                new50=args.new50,
                phase4_source=args.phase4_source,
                coverage=args.coverage,
                native_minute=args.native_minute,
                market_root=args.market_root,
                output=args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
