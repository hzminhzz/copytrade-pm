"""Reproducible Q3 historical-oracle -> PM-04 -> PM-03 shadow-account study.

This deliberately uses retrospective flat-to-flat fragments, never a prospective
first-known copy signal or authentic Propr broker allowlist. Synthetic rulebook
permissions apply only to explicitly verified native Hyperliquid instruments.
No broker or trading gateway is imported.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D, ROUND_DOWN
from hashlib import sha256
import json
import os
from pathlib import Path

from .pm03_account import Instrument, Rulebook, digest
from .pm03_memory import Event
from .pm03_run import ShadowRun
from .pm36_e3 import session_multiplier
from .pm_hyperx_overlay_audit import examine
from .pm_fill_replay import _market_instrument
from .pm_propr_scope import SCOPE_STRICT, SCOPE_TENTATIVE, classify_coin
from .pm_quarter_episode_replay import closed_episodes
from .pm_quarter_fill_audit import START, END, wallet_fills
from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource
from .pm_sources import load_cohort

ZERO = D("0")
ONE = D("1")
STEP = timedelta(minutes=1)
HOUR = timedelta(hours=1)
PODS = ("CO-001", "W015", "VS066")
SCHEMA = "pm_c_historical_oracle_input_v1"
RESULT_SCHEMA = "pm_c_pm04_shadow_results_v1"
SOURCE_LABEL = "HISTORICAL_ORACLE_NOT_FIRST_KNOWN"
GROSS_CAP = D("3000")
STRESS_CAP = D("230")
POD_STRESS = D("60")
RESERVE = D("50")
EPISODE_BASE_USD = D("2000")
# Operational headroom within the frozen $60 per-pod stress allowance.
# Risk scaling remains <= the scenario budget and is the same for E1/E2/E3.
POD_PRETRADE_STRESS_USD = D("57")
# Deterministic synthetic base-unit grid; not a broker lot-size assertion.
QUANTITY_QUANTUM = D("0.000000000001")
# Fixed before seeing Portfolio C results. These are research stress approximations,
# not learned scenarios, true instrument volatility, or actual contract limits.
SHOCKS = {"xyz:CL": D("0.07"), "xyz:XYZ100": D("0.05"), "HYPE": D("0.12")}
DEFAULT_SHOCK = D("0.10")
SOURCE_FILLS_SHA = "57f4eb4e6b5abdb755a4ee599ba224d5e451e240dd2c78cf202cd764f17a93e9"
SOURCE_EPISODES_SHA = "0f10be09d577bfef9e749f258e34fe00acc2f13667c2e9180671dda8da66732b"


def native_to_pm(native: str) -> str:
    """Bijection: exact Hyperliquid DEX namespace retained in PM-03 market."""
    parts = native.split(":")
    if len(parts) != 5 or parts[:3] != ["hyperliquid", "mainnet", "perp"]:
        raise ValueError("INVALID_NATIVE_INSTRUMENT")
    dex, symbol = parts[3:]
    if not dex or not symbol or "/" in dex + symbol:
        raise ValueError("INVALID_NATIVE_INSTRUMENT")
    return Instrument("hyperliquid", f"mainnet:perp:{dex}", symbol).key


def pm_to_native(key: str) -> str:
    instrument = Instrument.parse(key)
    parts = instrument.market.split(":")
    if instrument.venue != "hyperliquid" or len(parts) != 3 or parts[:2] != ["mainnet", "perp"]:
        raise ValueError("INVALID_PM_MARKET")
    return ":".join(("hyperliquid", "mainnet", "perp", parts[2], instrument.symbol))


def shock(coin: str) -> D:
    return SHOCKS.get(coin, DEFAULT_SHOCK)


def permitted_class(coin: str, snapshot: dict) -> str | None:
    """Never relax the strict Propr gate; this is native historical research only."""
    name = classify_coin(coin, snapshot)
    return name if name in (SCOPE_STRICT, SCOPE_TENTATIVE) else None


def _private_json(out: Path, stem: str, payload: dict) -> tuple[Path, str]:
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if out.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_OUTPUT_DIR_PERMISSIONS")
    blob = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    value = sha256(blob).hexdigest()
    dest = out / f"{stem}-{value[:20]}.json"
    if dest.exists():
        if sha256(dest.read_bytes()).hexdigest() != value:
            raise ValueError("IMMUTABLE_REPORT_CONFLICT")
        return dest, value
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    return dest, value


def _checked_report(path: Path, expected: str, schema: str) -> dict:
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("SOURCE_REPORT_SHA_DRIFT")
    data = json.loads(path.read_bytes())
    if data.get("schema") != schema:
        raise ValueError("SOURCE_REPORT_SCHEMA_DRIFT")
    return data


def _hourly_history(
    market: VerifiedHyperliquidMinuteSource,
    native: str,
    at: datetime,
    memo: dict[tuple[str, datetime], D | None],
) -> list[tuple[datetime, D]]:
    anchor = at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if anchor == at:
        anchor -= HOUR
    result = []
    for i in range(841):
        current = anchor - i * HOUR
        key = (native, current)
        if key not in memo:
            try:
                memo[key] = market.get(native, current).open
            except MarketDataBlocked:
                memo[key] = None
        if memo[key] is not None:
            result.append((current, memo[key]))
    return result


def prepare(
    root: Path,
    market_root: Path,
    snapshot_path: Path,
    fill_report_path: Path,
    episode_report_path: Path,
    generations: tuple[Path, ...],
) -> dict:
    fills_report = _checked_report(
        fill_report_path, SOURCE_FILLS_SHA, "pm36_independent_2026q3_vendor_fill_audit_v1"
    )
    episode_report = _checked_report(
        episode_report_path,
        SOURCE_EPISODES_SHA,
        "pm36_2026q3_independent_completed_episode_replay_v1",
    )
    if fills_report["source_manifests_sha256"] != episode_report["source_manifests_sha256"]:
        raise ValueError("FROZEN_SOURCE_REPORTS_DISAGREE")
    if (
        fills_report["overlay_generation_shas"]
        != episode_report["overlay_source_generation_sha256"]
    ):
        raise ValueError("FROZEN_OVERLAY_REPORTS_DISAGREE")
    raw_snapshot = snapshot_path.read_bytes()
    snapshot = json.loads(raw_snapshot)
    if (
        snapshot.get("schema") != "propr_public_universe_browser_snapshot_v1"
        or snapshot.get("not_proof_of_historical_availability") is not True
        or snapshot.get("retrieved_on_utc_date") != "2026-10-30"
    ):
        raise ValueError("INVALID_POSTPERIOD_DISPLAY_SNAPSHOT")
    entries, manifests = load_cohort(root)
    if manifests != fills_report["source_manifests_sha256"] or len(entries) != 36:
        raise ValueError("FROZEN_COHORT_SOURCE_MANIFEST_DRIFT")
    cohort = {entry.alias: entry for entry in entries}
    if not set(PODS).issubset(cohort):
        raise ValueError("PORTFOLIO_C_WALLET_MISSING")
    overlay, verified = examine(root, generations)
    if (
        not overlay["original_vendor_cache_intact"]
        or overlay["private_generations"] != fills_report["overlay_generation_shas"]
    ):
        raise ValueError("UNVERIFIED_OR_CHANGED_SOURCE_OVERLAY")
    market = VerifiedHyperliquidMinuteSource(market_root)
    events = []
    ranges = []
    counts = {}
    vol_memo: dict[tuple[str, datetime], D | None] = {}
    for pod in PODS:
        rows, issues = wallet_fills(
            root,
            cohort[pod],
            generations=generations,
            verified_additions=verified.get(pod, []),
        )
        episodes, stats = closed_episodes(pod, rows)
        counters = Counter(stats)
        counters["source_chain_gaps"] = sum(x.endswith(":POSITION_DISCONTINUITY") for x in issues)
        for idx, episode in enumerate(episodes):
            counters["completed_in_q3"] += 1
            classification = permitted_class(episode.coin, snapshot)
            if classification is None:
                counters["excluded_scope_" + classify_coin(episode.coin, snapshot)] += 1
                continue
            try:
                native = _market_instrument(episode.coin)
                pm_id = native_to_pm(native)
                if pm_to_native(pm_id) != native:
                    raise ValueError("NONREVERSIBLE_MARKET")
            except MarketDataBlocked, ValueError:
                counters["excluded_native_mapping"] += 1
                continue
            first = episode.rows[0]
            last = episode.rows[-1]
            begin = VerifiedHyperliquidMinuteSource._minute(
                first.timestamp + timedelta(microseconds=1)
            )
            final = VerifiedHyperliquidMinuteSource._minute(
                last.timestamp + timedelta(microseconds=1)
            ) + timedelta(minutes=5)
            if final >= END:
                counters["excluded_after_quarter"] += 1
                continue
            # Full interval integrity, not just day SHA. This retrospective
            # selection uses future knowledge, disclosed in the input contract.
            minute = begin - STEP
            gap = None
            while minute <= final:
                try:
                    market.get(native, minute)
                except MarketDataBlocked as exc:
                    gap = str(exc).split(":", 1)[0]
                    break
                minute += STEP
            if gap:
                counters["excluded_market_" + gap] += 1
                continue
            anchor = abs(first.after) * first.price
            if anchor <= ZERO:
                raise ValueError("INVALID_EPISODE_ANCHOR")
            ranges.append(
                {
                    "start": begin.isoformat(),
                    "end": final.isoformat(),
                    "instrument": pm_id,
                    "pod": pod,
                }
            )
            for fill in episode.rows:
                when = VerifiedHyperliquidMinuteSource._minute(
                    fill.timestamp + timedelta(microseconds=1)
                )
                history = _hourly_history(market, native, when, vol_memo)
                vol = session_multiplier(history, when)
                events.append(
                    {
                        "time": when.isoformat(),
                        "source_at": fill.timestamp.isoformat(),
                        "pod": pod,
                        "coin": episode.coin,
                        "instrument": pm_id,
                        "relative_units_per_dollar": str(fill.after / anchor),
                        "episode_id": f"{pod}:{episode.coin}:{idx}",
                        "vol_factor": str(vol) if vol is not None else None,
                        "tid": fill.trade_id,
                    }
                )
            counters["included_episodes"] += 1
            counters["included_fills"] += len(episode.rows)
            counters["scope_" + classification] += 1
        counts[pod] = dict(counters)
    events.sort(key=lambda x: (x["time"], x["source_at"], x["pod"], x["instrument"], x["tid"]))
    # At minute resolution repeated source actions become the latest as-of book.
    # Preserve source TID in the private manifest, never invent a fill.
    if not events:
        raise ValueError("NO_RESEARCH_ELIGIBLE_SOURCE_EVENTS")
    return {
        "schema": SCHEMA,
        "classification": "HISTORICAL_ORACLE_PARTIAL_REPLICATION_PROXY",
        "first_known_follower_clock_available": False,
        "historical_propr_instrument_ids_verified": False,
        "start": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "pods": list(PODS),
        "source_fills_sha256": SOURCE_FILLS_SHA,
        "source_episodes_sha256": SOURCE_EPISODES_SHA,
        "source_manifests_sha256": manifests,
        "overlay_generation_sha256": overlay["private_generations"],
        "postperiod_snapshot_sha256": sha256(raw_snapshot).hexdigest(),
        "research_scope": "STRICT_CRYPTO_PLUS_TENTATIVE_NATIVE_XYZ_HIP3_ONLY",
        "excluded_other_dex": True,
        "source_sample_selection": "COMPLETED_FLAT_TO_FLAT_AND_FUTURE_MARKET_COVERAGE",
        "source_hedges_unreconciled": True,
        "market_day_shas": dict(sorted(market.source_days.items())),
        "native_liquidity_proxy_days": sorted(market.liquidity_proxy_days),
        "coverage_by_pod": counts,
        "instruments": sorted({row["instrument"] for row in events}),
        "ranges": ranges,
        "events": events,
        "frozen_assumptions": {
            "start_balance_usd": "10000",
            "profit_target_usd": "1000",
            "daily_allowance_usd": "300",
            "static_loss_usd": "600",
            "pod_daily_usd": "60",
            "pod_stress_usd": "60",
            "pod_drawdown_usd": "120",
            "reserve_usd": "50",
            "pod_pretrade_stress_target_usd": str(POD_PRETRADE_STRESS_USD),
            "aggregate_stress_limit_usd": str(STRESS_CAP),
            "gross_cap_usd": str(GROSS_CAP),
            "base_episode_anchor_usd_for_e2_e3": str(EPISODE_BASE_USD),
            "E1_per_episode_entry_notional_usd": "200",
            "cost_base_fee_spread_slippage_bps": ["5", "3", "5"],
            "funding_cost_bps_per_8h": "1",
            "funding_timing": "PRE_DECISION_BOOK_ASOF_CURRENT_VERIFIED_MARK",
            "liquidity_previous_completed_minute_quote_participation": "0.05",
            "shock": {**{k: str(v) for k, v in SHOCKS.items()}, "other": str(DEFAULT_SHOCK)},
            "E3_rule": "session_aware_7d_vol_vs_previous_28d_reduce_only",
            "risk_evaluation_marks": "SOURCE_EVENTS_AND_5M_DEADLINES_PLUS_HOURLY_WHEN_OPEN",
            "quiet_unmarked_gap_limit_hours": "6",
            "synthetic_target_and_capacity_base_unit_grid": str(QUANTITY_QUANTUM),
            "unmarked_gap_policy": "NO_ACTION_ONLY_NO_FILL_NO_MARK_CENSOR_WITH_EXPLICIT_COUNT",
        },
    }


def _policy(method: str, batching: str) -> dict:
    return {
        "schema": "pm04_research_policy_v1",
        "version": "portfolio-c-q3-v1",
        "approval_reference": "synthetic-research-only-no-trading",
        "pods": {
            p: {
                "budget_ref": f"pc-q3-{p}",
                "daily_loss": "60",
                "max_drawdown": "120",
                "stress_loss": "60",
            }
            for p in PODS
        },
        "max_gross_notional": str(GROSS_CAP),
        "max_instrument_fraction_equity": "0.30",
        "max_stress_loss": str(STRESS_CAP),
        "reserve": str(RESERVE),
        "max_signal_age_seconds": 360,
        "broker_max_age_seconds": 300,
        "reconcile_tolerance": "0.001",
        "batch_seconds": 300,
        "execution_policy": "IMMEDIATE" if batching == "IMMEDIATE" else "ASYMMETRIC",
        "broker_required": False,
    }


def _rulebook(instruments: list[str]) -> Rulebook:
    return Rulebook(
        program="SYNTHETIC_PROPR_STYLE",
        stage="evaluation",
        source="Portfolio C postperiod hypothetical rules NOT genuine Q3 Propr contract",
        observed_at=START.isoformat(),
        version="research-only-v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("300"),
        static_loss=D("600"),
        trailing_loss=None,
        confirmed=True,
        permitted=tuple(Instrument.parse(p) for p in instruments),
        max_gross_leverage=D("2"),
        account_terms_confirmed=False,
    )


def _clocks(
    at: datetime,
    source_at: str | None = None,
    first_known_at: str | None = None,
) -> tuple[str, str, str, str]:
    t = at.isoformat()
    return source_at or t, first_known_at or t, t, (at + timedelta(seconds=2)).isoformat()


def _mk_event(
    run: ShadowRun,
    index: int,
    kind: str,
    at: datetime,
    payload: dict,
    source_sha: str,
    source_at: str | None = None,
    first_known_at: str | None = None,
) -> Event:
    source, known, decision, filled = _clocks(at, source_at, first_known_at)
    return Event(
        event_id=f"pc-{index:07d}",
        source_event_at=source,
        first_known_at=known,
        decision_at=decision,
        hypothetical_fill_at=filled,
        kind=kind,
        payload={
            "run_id": run.manifest["run_id"],
            "rulebook_sha": run.account.rulebook.sha,
            "input": payload,
        },
        source_sha=source_sha,
    )


def _observations(
    market: VerifiedHyperliquidMinuteSource,
    instruments: set[str],
    at: datetime,
) -> list[dict]:
    rows = []
    for pm_id in sorted(instruments):
        native = pm_to_native(pm_id)
        # Future volume in the trade minute is forbidden. Use completed minute.
        now = market.get(native, at)
        previous = market.get(native, at - STEP)
        base_volume = (previous.quote_volume / previous.open).quantize(
            D("0.00000000001"), rounding=ROUND_DOWN
        )
        rows.append(
            {
                "instrument": pm_id,
                "event_at": at.isoformat(),
                "first_known_at": at.isoformat(),
                "mark": str(now.open),
                "volume_base": str(base_volume),
                "quality": "OHLCV_1M_PROXY",
                "supported": True,
            }
        )
    return rows


def _shocks(instruments: set[str]) -> list[dict[str, str]]:
    negative = {}
    positive = {}
    for key in sorted(instruments):
        native = pm_to_native(key)
        parts = native.split(":")
        coin = parts[-1] if parts[3] == "default" else parts[3] + ":" + parts[4]
        change = shock(coin)
        negative[key] = str(-change)
        positive[key] = str(change)
    return [negative, positive]


def _evidence(cost_multiplier: int) -> dict:
    return {
        "trusted": True,
        "account_state_known": True,
        "market_state_known": True,
        "market_coverage_valid": True,
        "pending_unknown_orders": False,
        "input_status": "RESEARCH_SYNTHETIC",
        "pm02_qualified": False,
        "hedge_break_loss": "5",
        "stressed_liquidity_loss": "5",
    }


def _costs(multiplier: int) -> dict:
    return {
        "fee_bps": str(5 * multiplier),
        "full_spread_bps": str(3 * multiplier),
        "slippage_bps": str(5 * multiplier),
        "impact_bps_at_full_participation": "0",
        "max_participation": "0.05",
        "max_age_seconds": 300,
        "latency_seconds": 1,
    }


def _quantized_targets(rows: dict[str, D]) -> dict[str, D]:
    """Round toward zero to avoid invented 28-digit fills and stress overshoot."""
    return {
        k: value
        for k, q in rows.items()
        if (value := q.quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN))
    }


def _pod_targets(
    method: str,
    pod: str,
    source: dict[tuple[str, str], D],
    factors: dict[tuple[str, str], D | None],
    marks: dict[str, D],
    cost_multiplier: int,
    *,
    wallet_equity: D | None = None,
) -> dict[str, D]:
    if method == "E4":
        from .pm36_e4 import compare_wallet_ratios, e4_size

        if wallet_equity is None:
            raise ValueError("E4_MISSING_ASOF_WALLET_EQUITY")
        book = {
            instrument: rel
            for (owner, instrument), rel in source.items()
            if owner == pod and rel != ZERO
        }
        pod_marks = {instrument: marks[instrument] for instrument in book}
        changes = {}
        for instrument in book:
            native = pm_to_native(instrument).split(":")
            coin = native[-1] if native[3] == "default" else native[3] + ":" + native[4]
            changes[instrument] = shock(coin)
        costs = (D("5") + D("1.5") + D("5")) * D(cost_multiplier) / D("10000")
        result, _, _ = e4_size(
            book,
            pod_marks,
            source_equity=wallet_equity,
            shock=changes,
            cost_rate=costs,
        )
        compare_wallet_ratios(book, result)
        return result
    quantities = {
        instrument: rel * (D("200") if method == "E1" else EPISODE_BASE_USD)
        for (owner, instrument), rel in source.items()
        if owner == pod and rel != ZERO
    }
    if not quantities:
        return {}
    # The shared quote batch includes other pods. E2 validates its own exact
    # instrument set so unrelated quotes must not enter its stress book.
    pod_marks = {instrument: marks[instrument] for instrument in quantities}
    from .pm36_e2 import risk_charge, size as stress_size

    rate = (D("5") + D("1.5") + D("5")) * D(cost_multiplier) / D("10000")
    percentages = {}
    for instrument in quantities:
        native = pm_to_native(instrument)
        p = native.split(":")
        coin = p[-1] if p[3] == "default" else p[3] + ":" + p[4]
        percentages[instrument] = shock(coin)
    # Fixed notional remains the E1 *starting* size, but all methods obey
    # the same aggregate stress-loss cap before calling PM-04. Without this
    # clipping E1 would trigger a permanent pod veto on its second trade.
    preliminary = (
        quantities
        if method == "E1"
        else stress_size(quantities, pod_marks, shock=percentages, cost_rate=rate)
    )
    charge = risk_charge(preliminary, pod_marks, shock=percentages, cost_rate=rate)
    factor = min(ONE, POD_PRETRADE_STRESS_USD / charge) if charge else ONE
    capped = {instrument: q * factor for instrument, q in preliminary.items()}
    if method in ("E1", "E2"):
        return _quantized_targets(capped)
    if method != "E3":
        raise ValueError("UNKNOWN_SIZING_METHOD")
    # A missing trailing history permits reductions of existing E2 exposure
    # only. First-time entry therefore remains zero; no synthetic zero-vol bar.
    return _quantized_targets(
        {
            k: value * factors[(pod, k)] if factors.get((pod, k)) is not None else ZERO
            for k, value in capped.items()
        }
    )


def _checkpoints(input_data: dict, *, max_events: int | None) -> tuple[list[datetime], dict]:
    raw_events = input_data["events"][:max_events] if max_events else input_data["events"]
    events_by_minute: dict[datetime, list[dict]] = defaultdict(list)
    for row in raw_events:
        events_by_minute[datetime.fromisoformat(row["time"])].append(row)
    times = set(events_by_minute)
    for moment in list(times):
        times.add(moment + timedelta(minutes=5))
    # A bounded genuine history smoke must not process the rest of the quarter.
    upper = (max(times) + timedelta(minutes=5)) if max_events else END - STEP
    for row in input_data["ranges"]:
        start = datetime.fromisoformat(row["start"])
        stop = min(datetime.fromisoformat(row["end"]), upper)
        current = start.replace(minute=0, second=0, microsecond=0) + HOUR
        while current <= stop:
            times.add(current)
            current += HOUR
    if max_events:
        times = {x for x in times if x <= upper}
    return sorted(x for x in times if START <= x < END), events_by_minute


def run_one(
    manifest: dict,
    input_sha: str,
    market_root: Path,
    out: Path,
    *,
    method: str,
    execution: str,
    cost_multiplier: int,
    smoke_events: int | None = None,
) -> dict:
    from .pm36_e4 import E4_SCHEMA

    if method not in ("E1", "E2", "E3", "E4") or execution not in ("IMMEDIATE", "ASYMMETRIC_5M"):
        raise ValueError("UNSUPPORTED_EXPERIMENT")
    if cost_multiplier not in (1, 2):
        raise ValueError("UNSUPPORTED_COST_SCENARIO")
    if (method == "E4") != (manifest.get("schema") == E4_SCHEMA):
        raise ValueError("E4_REQUIRES_ATOMIC_WHOLE_WALLET_BOOKS_NOT_EPISODES")
    if method == "E4":
        from .pm36_e4 import to_pm04_manifest

        original = manifest.get("original_payload")
        if not isinstance(original, dict) or to_pm04_manifest(original) != manifest:
            raise ValueError("E4_COMPLETE_SOURCE_CONTRACT_SHA_OR_EVENT_DRIFT")
    if method == "E4" and (
        not manifest.get("synthetic_research_only")
        or not manifest.get("source_requires_all_markets")
        or not manifest.get("source_contract_sha256")
    ):
        raise ValueError("E4_SOURCE_CENSUS_UNVERIFIED")
    start = START.isoformat()
    run_id = f"pc-{input_sha[:12]}-{method.lower()}-{execution.lower()}-{cost_multiplier}x" + (
        f"-smoke{smoke_events}" if smoke_events else ""
    )
    # ShadowRun creates the run directory but its parent must also be owner-private.
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if out.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_OUTPUT_DIR_PERMISSIONS")
    book = _rulebook(manifest["instruments"])
    source_binding = manifest["source_contract_sha256"] if method == "E4" else SOURCE_FILLS_SHA
    run = ShadowRun(
        out,
        run_id=run_id,
        rulebook=book,
        started_at=start,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=source_binding,
        pm02_sha=digest({"pm02": "not supplied", "oracle": input_sha}),
        market_manifest_sha=digest(manifest["market_day_shas"]),
    )
    if run.last_event_id is not None:
        raise ValueError("EXISTING_IMMUTABLE_SCENARIO_LEDGER_NO_OVERWRITE")
    index = 0
    run.record(
        _mk_event(
            run, index, "PM04_CONFIG", START, {"policy": _policy(method, execution)}, input_sha
        )
    )
    index += 1
    market = VerifiedHyperliquidMinuteSource(market_root)
    checkpoints, timed_events = _checkpoints(manifest, max_events=smoke_events)
    source: dict[tuple[str, str], D] = {}
    factors: dict[tuple[str, str], D | None] = {}
    source_equity: dict[str, D] = {}
    source_receipts: dict[str, dict] = {}
    e4_intents_checked = 0
    e4_scale_changes: list[dict[str, str]] = []
    e4_tracking_samples = 0
    e4_max_tracking_error = ZERO
    e4_tracking_on_source_events: list[dict] = []
    previous_targets: dict[tuple[str, str], D] = {}
    revisions = defaultdict(int)
    last_time = START
    orders = 0
    rejections = Counter()
    series = []
    peak = D("10000")
    max_dd = ZERO
    worst_daily_loss = ZERO
    min_daily_headroom = D("300")
    min_static_headroom = D("600")
    peak_gross = ZERO
    gross_sum = ZERO
    active_marks = 0
    data_blocker = None
    last_good_quote_at: datetime | None = None
    censored_mark_gaps = []
    for at in checkpoints:
        rows = timed_events.get(at, [])
        if rows:
            if method == "E4":
                if len({r["pod"] for r in rows}) != len(rows):
                    raise ValueError("E4_MULTIPLE_ATOMIC_BOOKS_SAME_DECISION_MINUTE")
                for row in rows:
                    pod = row["pod"]
                    for key in [k for k in source if k[0] == pod]:
                        del source[key]
                    for instrument, quantity in row["positions"].items():
                        amount = D(quantity)
                        if amount:
                            source[(pod, instrument)] = amount
                    source_equity[pod] = D(row["wallet_equity_usd"])
                    source_receipts[pod] = {
                        "source_event_at": row["source_at"],
                        "first_known_at": row["first_known_at"],
                        "source_evidence_sha256": row["source_evidence_sha256"],
                    }
            else:
                for row in rows:
                    key = (row["pod"], row["instrument"])
                    source[key] = D(row["relative_units_per_dollar"])
                    factors[key] = D(row["vol_factor"]) if row["vol_factor"] is not None else None
        active_pods = {
            p
            for p in PODS
            if run.account.pm04_state["pod_stats"][p]["state"] in ("ACTIVE", "RESTORED")
        }
        tracked = {inst for (p, inst), val in source.items() if val and p in active_pods}
        tracked.update(k.key for k, q in run.account.quantities.items() if q)
        tracked.update(
            k.key
            for pod_book in run.account.pm_quantities.values()
            for k, q in pod_book.items()
            if q
        )
        tracked.update(
            inst
            for pbook in run.account.pm04_state["routed_targets"].values()
            for inst, val in pbook.items()
            if D(val)
        )
        # Unrouted rejected pod intents are not positions and must not
        # demand continuous market quotes after their pod is suspended.
        tracked.update(
            inst
            for inst in run.account.pm04_state["batch_open"]
            if any(
                pod in active_pods and D(book.get(inst, "0"))
                for pod, book in run.account.pm04_state["pod_targets"].items()
            )
        )
        if not tracked:
            # No exposure. No price needs to be invented and no funding is owed.
            last_time = at
            continue
        try:
            observations = _observations(market, tracked, at)
        except MarketDataBlocked as exc:
            state_before = run.account.pm04_state
            quiet = (
                not rows
                and not state_before["batch_open"]
                and not state_before["pending_reductions"]
                and not state_before["pending_pod_reductions"]
            )
            short = last_good_quote_at is not None and at - last_good_quote_at <= timedelta(hours=6)
            if quiet and short:
                # No action/fill or fictitious mark during a HIP-3 nontrading
                # gap. Existing exposure remains unresolved and is revalued
                # at the next verifiable observation, with missing risk
                # intervals disclosed. This is NOT a verified floor path.
                censored_mark_gaps.append(
                    {
                        "at": at.isoformat(),
                        "reason": str(exc),
                        "held": sorted(k.key for k, q in run.account.quantities.items() if q),
                    }
                )
                rejections["CENSORED_QUIET_MARK_GAP"] += 1
                continue
            data_blocker = f"{at.isoformat()}:{exc}"
            rejections["MARKET_DATA_BLOCKED"] += 1
            break
        last_good_quote_at = at
        marks = {row["instrument"]: D(row["mark"]) for row in observations}
        # Accrue carry for inventory held over (last_time, at] BEFORE the
        # new pod targets execute. Charging the post-decision book would levy
        # funding retroactively on a just-opened position, or waive it for
        # a just-closed one. The current verified mark is an end-interval
        # conservative proxy, not an observed historical funding settlement.
        elapsed_hours = D(str((at - last_time).total_seconds())) / D("3600")
        last_time = at
        # PM-03 requires the first daily mark/reset before posting funding.
        # Freeze allocations using the PRE-transition book, then post the
        # precomputed cash charge immediately AFTER PM04's current mark.
        allocations = {}
        if elapsed_hours > ZERO and any(run.account.quantities.values()):
            for pod in PODS:
                notional = sum(
                    (
                        abs(q * marks[k.key])
                        for k, q in run.account.pm_quantities.get(pod, {}).items()
                        if q
                    ),
                    ZERO,
                )
                allocations[pod] = (-notional * elapsed_hours / D("8") / D("10000")).quantize(
                    D("0.00000001")
                )
        funding_amount = sum(allocations.values(), ZERO)
        desired = {}
        e4_updated = {r["pod"] for r in rows} if method == "E4" else set()
        for pod in PODS:
            if method == "E4" and pod not in e4_updated:
                desired.update({k: v for k, v in previous_targets.items() if k[0] == pod})
                continue
            if pod not in active_pods:
                # PM-04 has already latched the risk veto and forced routed
                # reductions. Do not require nonexistent quotes for stale,
                # never-routed source intentions of a suspended pod.
                desired.update({k: v for k, v in previous_targets.items() if k[0] == pod})
                continue
            desired.update(
                {
                    (pod, key): value
                    for key, value in _pod_targets(
                        method,
                        pod,
                        source,
                        factors,
                        marks,
                        cost_multiplier,
                        wallet_equity=source_equity.get(pod),
                    ).items()
                }
            )
        for old in previous_targets:
            desired.setdefault(old, ZERO)
        changed = {
            key: value for key, value in desired.items() if previous_targets.get(key, ZERO) != value
        }
        previous_targets = desired
        payload = {
            "observations": observations,
            "shocks": _shocks(tracked),
            "evidence": _evidence(cost_multiplier),
            "costs": _costs(cost_multiplier),
        }
        if method == "E4":
            from .pm36_e4 import compare_wallet_ratios

            for pod in e4_updated:
                e4_source_book = {k: q for (owner, k), q in source.items() if owner == pod and q}
                wanted = {k: q for (owner, k), q in desired.items() if owner == pod and q}
                if pod in active_pods:
                    detail = compare_wallet_ratios(e4_source_book, wanted)
                    e4_intents_checked += 1
                    e4_scale_changes.append(
                        {
                            "at": at.isoformat(),
                            "pod": pod,
                            "scale": detail["scale"],
                            "status": detail["status"],
                        }
                    )
        if changed:
            targets = []
            earliest = min((row["source_at"] for row in rows), default=at.isoformat())
            for (pod, inst), value in sorted(changed.items()):
                revisions[(pod, inst)] += 1
                targets.append(
                    {
                        "pod": pod,
                        "instrument": inst,
                        "quantity": str(value),
                        "revision": revisions[(pod, inst)],
                        "source_event_at": (
                            source_receipts[pod]["source_event_at"] if method == "E4" else earliest
                        ),
                        "first_known_at": (
                            source_receipts[pod]["first_known_at"]
                            if method == "E4"
                            else at.isoformat()
                        ),
                        "source_sha": (
                            source_receipts[pod]["source_evidence_sha256"]
                            if method == "E4"
                            else input_sha
                        ),
                        "budget_ref": f"pc-q3-{pod}",
                    }
                )
            payload["targets"] = targets
        before_rev = run.account.revision
        try:
            run.record(
                _mk_event(
                    run,
                    index,
                    "PM04_SIGNAL" if changed else "PM04_TICK",
                    at,
                    payload,
                    input_sha,
                    min((row["source_at"] for row in rows), default=None),
                )
            )
        except (ValueError, KeyError) as exc:
            data_blocker = f"{at.isoformat()}:ENGINE_ERROR:{exc}"
            rejections["ENGINE_ERROR"] += 1
            break
        index += 1
        if run.account.revision > before_rev:
            orders += run.account.revision - before_rev
        state = run.account.pm04_state
        for pod in PODS:
            if state["pod_stats"][pod]["state"] in ("REDUCED", "SUSPENDED"):
                rejections["POD_" + state["pod_stats"][pod]["state"]] += 1
        if run.account.risk == "HALT":
            rejections["ACCOUNT_HALT"] += 1
        if funding_amount:
            try:
                run.record(
                    _mk_event(
                        run,
                        index,
                        "FUNDING",
                        at,
                        {
                            "amount": str(funding_amount),
                            "allocated": {p: str(v) for p, v in allocations.items()},
                        },
                        input_sha,
                    )
                )
            except (ValueError, KeyError) as exc:
                data_blocker = f"{at.isoformat()}:FUNDING_ERROR:{exc}"
                rejections["FUNDING_ERROR"] += 1
                break
            index += 1
        if method == "E4" and (rows or at.minute == 0):
            for pod in PODS:
                if pod not in source_receipts:
                    continue
                target_book = {k: v for (owner, k), v in desired.items() if owner == pod and v}
                executed = {
                    k.key: v for k, v in run.account.pm_quantities.get(pod, {}).items() if v
                }
                keys = set(target_book) | set(executed)
                if not keys.issubset(marks):
                    raise ValueError("E4_UNMARKED_EXECUTED_WALLET_HEDGE")
                mismatch = sum(
                    (
                        abs(target_book.get(k, ZERO) - executed.get(k, ZERO)) * marks[k]
                        for k in keys
                    ),
                    ZERO,
                )
                baseline = sum((abs(v) * marks[k] for k, v in target_book.items()), ZERO)
                error = mismatch / max(ONE, baseline)
                e4_tracking_samples += 1
                e4_max_tracking_error = max(e4_max_tracking_error, error)
                if rows and pod in e4_updated:
                    e4_tracking_on_source_events.append(
                        {
                            "at": at.isoformat(),
                            "pod": pod,
                            "target_notional_usd": str(baseline),
                            "mismatch_notional_usd": str(mismatch),
                            "normalized_tracking_error": str(error),
                            "note": "PM04_SHADOW_AFTER_DECISION_NOT_BROKER_FILL",
                        }
                    )
        peak = max(peak, run.account.equity)
        max_dd = max(max_dd, peak - run.account.equity)
        day_floor = run.account.floor()[1]["daily"]
        static_floor = run.account.floor()[1]["static"]
        worst_daily_loss = max(
            worst_daily_loss, max(ZERO, run.account.daily_start_balance - run.account.equity)
        )
        min_daily_headroom = min(min_daily_headroom, run.account.equity - day_floor)
        min_static_headroom = min(min_static_headroom, run.account.equity - static_floor)
        gross = run.account.gross()
        peak_gross = max(peak_gross, gross)
        gross_sum += gross
        active_marks += 1
        if rows or at.minute == 0 or run.account.risk == "HALT":
            series.append(
                {
                    "at": at.isoformat(),
                    "equity_usd": str(run.account.equity),
                    "gross_usd": str(gross),
                    "pod_pnl_usd": {p: str(run.account.pm_equity_pnl().get(p, ZERO)) for p in PODS},
                    "risk": str(run.account.risk),
                }
            )
        if run.account.breached:
            rejections["CONTRACTUAL_FLOOR_BREACH"] += 1
            # No new risk; retain unresolved account inventory as an explicit blocker.
            break
    run.account.verify()
    attribution = run.account.pm_equity_pnl()
    residual = sum(attribution.values(), ZERO) - (run.account.equity - D("10000"))
    if abs(residual) > D("0.000000000001"):
        raise ValueError("POD_ACCOUNT_PNL_RECONCILIATION")
    snapshot = run.account.snapshot()
    pm04 = run.account.pm04_state
    result = {
        "schema": RESULT_SCHEMA,
        "state": (
            "BLOCKED_DATA_OR_ENGINE"
            if data_blocker
            else "PARTIAL_ACCOUNT_HALT"
            if run.account.breached
            else "PARTIAL_REPLICATION_WITH_UNMARKED_SESSION_GAPS"
            if censored_mark_gaps
            else "E4_SYNTHETIC_BOOK_CONTRACT_REPLAY_ONLY"
            if method == "E4"
            else "HISTORICAL_HYPOTHETICAL_PARTIAL_REPLICATION"
        ),
        "source_provenance_binding_sha256": source_binding,
        "source_classification": (
            "E4_FULL_BOOK_CONTRACT_NOT_EXTERNAL_ECONOMIC_PROOF" if method == "E4" else SOURCE_LABEL
        ),
        "e4_proportional_intent_verified_count": e4_intents_checked,
        "e4_scale_change_evidence": e4_scale_changes,
        "e4_original_account_book_independently_verified": False,
        "e4_execution_fidelity_broker_verified": False,
        "e4_tracking_samples": e4_tracking_samples,
        "e4_max_shadow_tracking_error": str(e4_max_tracking_error),
        "e4_tracking_at_source_events": e4_tracking_on_source_events,
        "method": method,
        "execution": execution,
        "cost_multiplier": cost_multiplier,
        "input_sha256": input_sha,
        "run_id": run_id,
        "ledger_event_count": index,
        "ledger_last_event_id": run.last_event_id,
        "source_event_count": len(
            manifest["events"][:smoke_events] if smoke_events else manifest["events"]
        ),
        "accepted_snapshot_count": len(series),
        "equity_curve": series,
        "net_pnl_usd": str(run.account.equity - D("10000")),
        "max_drawdown_usd_sampled": str(max_dd),
        "worst_daily_loss_usd_sampled": str(worst_daily_loss),
        "peak_gross_usd_sampled": str(peak_gross),
        "mean_gross_usd_sampled": str(gross_sum / active_marks) if active_marks else "0",
        "min_daily_headroom_usd_sampled": str(min_daily_headroom),
        "min_static_headroom_usd_sampled": str(min_static_headroom),
        "profit_target_progress_usd": str(max(ZERO, run.account.equity - D("10000"))),
        "pod_pnl_usd": {p: str(attribution.get(p, ZERO)) for p in PODS},
        "fees_usd": str(run.account.costs),
        "modeled_funding_usd": str(run.account.funding),
        "modeled_execution_drag_usd": pm04["execution_drag"],
        "orders_or_internal_crosses_proxy": orders,
        "risk_states": {p: pm04["pod_stats"][p]["state"] for p in PODS},
        "pod_rejections": pm04["pod_rejections"],
        "expired_targets": pm04["expired_targets"],
        "blocked_observations": pm04["blocked_observations"],
        "pending_reductions": pm04["pending_reductions"],
        "pending_pod_reductions": pm04["pending_pod_reductions"],
        "risk_breaches": pm04["risk_breaches"],
        "remaining_account_positions": {
            k.key: str(q) for k, q in run.account.quantities.items() if q
        },
        "counts": dict(rejections),
        "data_blocker": data_blocker,
        "censored_mark_gaps": censored_mark_gaps,
        "full_interval_equity_and_floor_verification": (
            not bool(censored_mark_gaps) and method != "E4"
        ),
        "risk_floor_checks": "HOUR_AND_DECISION_MINUTE_SAMPLED_NOT_TICK",
        "liquidity": "PREVIOUS_COMPLETED_MINUTE_VOLUME_PROXY_NOT_L2",
        "vendor_source_strategy_complete": False,
        "broker_executable": False,
        "live_authorized": False,
        "ledger_replay_verified": True,
        "account_snapshot_sha256": digest(snapshot),
        "study_start": start,
        "study_end_exclusive": END.isoformat(),
    }
    # Reopen the immutable PM-03 SHA chain and compare its authoritative account.
    recovered = ShadowRun(
        out,
        run_id=run_id,
        rulebook=book,
        started_at=start,
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=source_binding,
        pm02_sha=digest({"pm02": "not supplied", "oracle": input_sha}),
        market_manifest_sha=digest(manifest["market_day_shas"]),
    )
    if (
        digest(recovered.account.snapshot()) != digest(snapshot)
        or recovered.last_event_id != run.last_event_id
    ):
        raise ValueError("REPLAY_ACCOUNT_OR_EVENT_DIVERGENCE")
    result_path, result_sha = _private_json(out, "result", result)
    return {
        "result": str(result_path),
        "sha256": result_sha,
        "method": method,
        "execution": execution,
        "cost": cost_multiplier,
        "status": result["state"],
        "net_pnl": result["net_pnl_usd"],
        "events": index,
        "data_blocker": data_blocker,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--prepare-e4", action="store_true")
    parser.add_argument("--e4-books", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--method", choices=("E1", "E2", "E3", "E4"))
    parser.add_argument("--smoke-events", type=int)
    parser.add_argument("--execution", choices=("IMMEDIATE", "ASYMMETRIC_5M"))
    parser.add_argument("--cost-multiplier", type=int, choices=(1, 2))
    parser.add_argument("--research-root", type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--postperiod-snapshot", type=Path)
    parser.add_argument("--fill-report", type=Path)
    parser.add_argument("--episode-report", type=Path)
    parser.add_argument("--hyperx-generations", nargs="*", type=Path, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.prepare_e4:
        from .pm36_e4 import to_pm04_manifest

        if not args.e4_books:
            parser.error("--prepare-e4 requires --e4-books")
        books = json.loads(args.e4_books.read_bytes())
        prepared = to_pm04_manifest(books)
        path, sha = _private_json(args.out, "portfolio-c-input", prepared)
        print(
            json.dumps(
                {
                    "input": str(path),
                    "sha256": sha,
                    "snapshots": len(prepared["events"]),
                    "native_instruments": len(prepared["instruments"]),
                    "e4_verified_external_account": False,
                    "live_authorized": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.prepare:
        if not all(
            [
                args.research_root,
                args.postperiod_snapshot,
                args.fill_report,
                args.episode_report,
                args.hyperx_generations,
            ]
        ):
            parser.error("--prepare requires source root, snapshot, reports, generations")
        result = prepare(
            args.research_root,
            args.market_root,
            args.postperiod_snapshot,
            args.fill_report,
            args.episode_report,
            tuple(args.hyperx_generations),
        )
        p, sha = _private_json(args.out, "portfolio-c-input", result)
        print(
            json.dumps(
                {
                    "input": str(p),
                    "sha256": sha,
                    "counts": result["coverage_by_pod"],
                    "events": len(result["events"]),
                    "instruments": result["instruments"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    if not args.input or not args.method:
        parser.error("--input and --method required for comparisons")
    raw = args.input.read_bytes()
    sha = sha256(raw).hexdigest()
    if args.input.name != f"portfolio-c-input-{sha[:20]}.json":
        raise ValueError("INPUT_PATH_CONTENT_SHA_MISMATCH")
    source = json.loads(raw)
    from .pm36_e4 import E4_SCHEMA

    if source.get("schema") not in (SCHEMA, E4_SCHEMA) or source.get("pods") != list(PODS):
        raise ValueError("INVALID_FROZEN_PORTFOLIO_C_MANIFEST")
    if args.smoke_events is not None and args.smoke_events <= 0:
        parser.error("--smoke-events must be positive")
    results = []
    combinations = (
        (("IMMEDIATE", 1),)
        if args.smoke_events
        else (
            ("IMMEDIATE", 1),
            ("IMMEDIATE", 2),
            ("ASYMMETRIC_5M", 1),
            ("ASYMMETRIC_5M", 2),
        )
    )
    if args.execution or args.cost_multiplier:
        if not args.execution or not args.cost_multiplier:
            parser.error("--execution and --cost-multiplier must be supplied together")
        combinations = ((args.execution, args.cost_multiplier),)
    for execution, cost in combinations:
        results.append(
            run_one(
                source,
                sha,
                args.market_root,
                args.out,
                method=args.method,
                execution=execution,
                cost_multiplier=cost,
                smoke_events=args.smoke_events,
            )
        )
    print(json.dumps({"method": args.method, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
