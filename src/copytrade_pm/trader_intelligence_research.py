"""Offline, deterministic TI research: causal follower labels and matched policy comparisons.

Training/selection consumes *past matured* outcomes only. The market replay
produces diagnostic hypothetical labels, not observed fills or prospective proof.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from math import sqrt
from statistics import mean
from typing import Iterable

from .trader_intelligence import (
    ObservationSnapshot,
    WalletEvent,
    decimal,
    digest,
    norm_clock,
    utc,
)


@dataclass(frozen=True)
class MinuteBar:
    instrument: str
    start_at: str
    open_px: str
    high_px: str
    low_px: str
    close_px: str
    base_volume: str
    """A minute bar is complete and knowable only at start_at + 60 seconds."""

    def __post_init__(self) -> None:
        t = utc(self.start_at)
        if t.second or t.microsecond:
            raise ValueError("UNALIGNED_MINUTE_BAR")
        op, hi, lo, cl, vol = map(
            decimal, (self.open_px, self.high_px, self.low_px, self.close_px, self.base_volume)
        )
        if min(op, hi, lo, cl) <= 0 or vol < 0 or hi < max(op, cl) or lo > min(op, cl):
            raise ValueError("INVALID_MINUTE_BAR")


@dataclass(frozen=True)
class FollowerPolicy:
    """All execution assumptions declared by caller; no hidden zero-cost defaults."""

    delay_seconds: int
    horizons_minutes: tuple[int, ...]
    stop_distance_bps: str
    entry_fee_bps: str
    exit_fee_bps: str
    entry_slippage_bps: str
    exit_slippage_bps: str
    spread_bps: str
    required_notional_usd: str
    max_prior_minute_participation: str
    funding_rate_fraction_per_8h: str
    exit_policy: str = "FIXED_HORIZON"

    def __post_init__(self) -> None:
        if self.delay_seconds < 300:
            raise ValueError("DELAY_LESS_THAN_CONTRACT")
        if not self.horizons_minutes or any(x <= 0 for x in self.horizons_minutes):
            raise ValueError("INVALID_EXIT_HORIZON")
        if len(self.horizons_minutes) != len(set(self.horizons_minutes)):
            raise ValueError("DUPLICATE_HORIZON")
        for fieldname in (
            "stop_distance_bps",
            "entry_fee_bps",
            "exit_fee_bps",
            "entry_slippage_bps",
            "exit_slippage_bps",
            "spread_bps",
            "required_notional_usd",
            "max_prior_minute_participation",
        ):
            if decimal(getattr(self, fieldname)) <= 0 and fieldname in (
                "stop_distance_bps",
                "required_notional_usd",
                "max_prior_minute_participation",
            ):
                raise ValueError(f"NONPOSITIVE_{fieldname.upper()}")
            if decimal(getattr(self, fieldname)) < 0:
                raise ValueError("NEGATIVE_EXECUTION_COST")
        if decimal(self.max_prior_minute_participation) > 1:
            raise ValueError("INVALID_PARTICIPATION_FRACTION")
        decimal(self.funding_rate_fraction_per_8h)
        if decimal(self.stop_distance_bps) >= Decimal(10_000):
            raise ValueError("UNREALISTIC_STOP_RISK_UNIT")
        if self.exit_policy not in ("FIXED_HORIZON", "STOP_OR_HORIZON"):
            raise ValueError("UNKNOWN_FOLLOWER_EXIT_POLICY")

    @property
    def sha256(self) -> str:
        return digest(
            {
                "delay_seconds": self.delay_seconds,
                "horizons_minutes": self.horizons_minutes,
                "exit_policy": self.exit_policy,
                **{
                    field: getattr(self, field)
                    for field in (
                        "stop_distance_bps",
                        "entry_fee_bps",
                        "exit_fee_bps",
                        "entry_slippage_bps",
                        "exit_slippage_bps",
                        "spread_bps",
                        "required_notional_usd",
                        "max_prior_minute_participation",
                        "funding_rate_fraction_per_8h",
                    )
                },
            }
        )


@dataclass(frozen=True)
class FollowerEpisode:
    episode_id: str
    wallet: str
    instrument: str
    direction: str
    strategy_style: str
    cluster_id: str | None
    origin: str
    observation_at: str
    first_known_at: str | None
    hypothetical_entry_at: str | None
    hypothetical_exit_at: str | None
    outcome_known_at: str | None
    horizon_minutes: int
    net_r: str | None
    gross_r: str | None
    cost_r: str | None
    source_pnl_usd: str | None
    status: str
    group_id: str
    policy_sha256: str

    def as_wire(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


def _sorted_bars(bars: Iterable[MinuteBar]) -> dict[str, list[MinuteBar]]:
    grouped: dict[str, list[MinuteBar]] = defaultdict(list)
    for b in bars:
        grouped[b.instrument].append(b)
    for instrument, series in grouped.items():
        series.sort(key=lambda b: utc(b.start_at))
        if len({x.start_at for x in series}) != len(series):
            raise ValueError(f"DUPLICATE_MINUTE_BAR:{instrument}")
    return grouped


def _simulate_exit(
    series: list[MinuteBar],
    entry_idx: int,
    exit_idx: int,
    entry_px: Decimal,
    direction: str,
    policy: FollowerPolicy,
) -> tuple[Decimal, object, str]:
    """Conservative OHLC stop proxy; intrabar timestamps remain unobservable.

    A stop hit is only known after the containing minute has closed. Gap opens
    receive the worse of open and stop; no optimistic same-bar fill priority.
    """
    if policy.exit_policy == "STOP_OR_HORIZON":
        distance = decimal(policy.stop_distance_bps) / Decimal(10_000)
        stop = entry_px * (1 - distance) if direction == "LONG" else entry_px * (1 + distance)
        for i in range(entry_idx, exit_idx):
            bar = series[i]
            if direction == "LONG" and decimal(bar.low_px) <= stop:
                fill = min(decimal(bar.open_px), stop)
            elif direction == "SHORT" and decimal(bar.high_px) >= stop:
                fill = max(decimal(bar.open_px), stop)
            else:
                continue
            return fill, utc(bar.start_at) + timedelta(minutes=1), "STOP_PROXY_FILLED"
    return decimal(series[exit_idx].open_px), utc(series[exit_idx].start_at), "OK"


def follower_replay(
    snapshot: ObservationSnapshot,
    bars: Iterable[MinuteBar],
    policy: FollowerPolicy,
    *,
    source_pnl_by_event: dict[str, str] | None = None,
    episode_group_by_event: dict[str, str] | None = None,
) -> tuple[FollowerEpisode, ...]:
    """Replay every transition, including C/X, with immutable non-zero-aware failures.

    Historical timestamps are source-event *execution proxies*, explicitly not
    observed follower latency. Capacity uses only the preceding completed minute.
    No account-risk or order gateway is instantiated.
    """
    market = _sorted_bars(bars)
    rosters = {w.alias: w for w in snapshot.wallets}
    result: list[FollowerEpisode] = []
    seen = {e.event_id: e for e in snapshot.events}
    for event in sorted(seen.values(), key=lambda e: (utc(e.event_at), e.event_id)):
        direction = event.direction
        for horizon in sorted(policy.horizons_minutes):
            observation_at = norm_clock(event.first_known_at or event.event_at)
            episode_id = digest(
                {
                    "schema": "ti_follower_episode_v1",
                    "event": event.event_id,
                    "wallet": event.wallet,
                    "instrument": event.instrument,
                    "horizon": horizon,
                    "policy": policy.sha256,
                    "source_sha256": snapshot.sha256,
                }
            )
            entry, exit_, net, gross, cost = (None,) * 5
            status = "OK"
            if direction is None:
                status = "NOT_DIRECTIONAL_ENTRY"
            elif event.strategy_style in ("FUNDING_CARRY", "MARKET_NEUTRAL", "HEDGED_BASKET"):
                status = "NON_DIRECTIONAL_STRATEGY"
            elif event.book_complete is not True:
                status = "INCOMPLETE_OR_UNKNOWN_BOOK"
            elif event.source_equity_usd is None:
                status = "SOURCE_EQUITY_UNKNOWN"
            elif event.strategy_style != "DIRECTIONAL":
                status = "UNKNOWN_STRATEGY_STYLE"
            else:
                obs = utc(observation_at)
                earliest = obs + timedelta(seconds=policy.delay_seconds)
                series = market.get(event.instrument, [])
                # At exactly the deadline, a partial bar is not hindsight-executable.
                candidate_idx = next(
                    (i for i, b in enumerate(series) if utc(b.start_at) >= earliest), None
                )
                if candidate_idx is None or candidate_idx == 0:
                    status = "MISSING_FOLLOWER_ENTRY"
                else:
                    b = series[candidate_idx]
                    prior = series[candidate_idx - 1]
                    # Prior bar must be immediately contiguous and complete.
                    if utc(prior.start_at) + timedelta(minutes=1) != utc(b.start_at):
                        status = "STALE_PRE_ENTRY_VOLUME"
                    else:
                        notional_capacity = (
                            decimal(prior.base_volume)
                            * decimal(prior.close_px)
                            * decimal(policy.max_prior_minute_participation)
                        )
                        if notional_capacity < decimal(policy.required_notional_usd):
                            status = "INSUFFICIENT_PRIOR_MINUTE_CAPACITY"
                        else:
                            entry = norm_clock(b.start_at)
                            exit_time = utc(entry) + timedelta(minutes=horizon)
                            exit_idx = next(
                                (
                                    i
                                    for i in range(candidate_idx + 1, len(series))
                                    if utc(series[i].start_at) >= exit_time
                                ),
                                None,
                            )
                            if exit_idx is None:
                                status = "UNOBSERVED_EXIT"
                            elif utc(series[exit_idx].start_at) != exit_time:
                                status = "MISSING_EXIT_MARK"
                            else:
                                # Validate every intervening minute; otherwise hidden gaps
                                # could miscount funding/stop exposure or imply markable NAV.
                                contiguous = all(
                                    utc(series[j].start_at) - utc(series[j - 1].start_at)
                                    == timedelta(minutes=1)
                                    for j in range(candidate_idx + 1, exit_idx + 1)
                                )
                                if not contiguous:
                                    status = "INTERIOR_MARKET_GAP"
                                else:
                                    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
                                    p_in = decimal(b.open_px)
                                    p_out, known_exit_at, status = _simulate_exit(
                                        series, candidate_idx, exit_idx, p_in, direction, policy
                                    )
                                    exit_ = norm_clock(known_exit_at)
                                    held_minutes = Decimal(
                                        str((known_exit_at - utc(entry)).total_seconds() / 60)
                                    )
                                    gross_bps = sign * (p_out / p_in - 1) * Decimal(10_000)
                                    cost_bps = sum(
                                        (
                                            decimal(policy.entry_fee_bps),
                                            decimal(policy.exit_fee_bps),
                                            decimal(policy.entry_slippage_bps),
                                            decimal(policy.exit_slippage_bps),
                                            decimal(policy.spread_bps),
                                        ),
                                        Decimal(0),
                                    )
                                    # Positive funding rate means longs pay, shorts receive.
                                    funding_bps = (
                                        sign
                                        * decimal(policy.funding_rate_fraction_per_8h)
                                        * held_minutes
                                        / Decimal(480)
                                        * Decimal(10_000)
                                    )
                                    gross = str(gross_bps / decimal(policy.stop_distance_bps))
                                    cost = str(
                                        (cost_bps + funding_bps) / decimal(policy.stop_distance_bps)
                                    )
                                    net = str(decimal(gross) - decimal(cost))
            result.append(
                FollowerEpisode(
                    episode_id=episode_id,
                    wallet=event.wallet,
                    instrument=event.instrument,
                    direction=direction or "NONE",
                    strategy_style=event.strategy_style,
                    cluster_id=rosters[event.wallet].cluster,
                    origin=event.origin,
                    observation_at=observation_at,
                    first_known_at=event.first_known_at,
                    hypothetical_entry_at=entry,
                    hypothetical_exit_at=exit_,
                    outcome_known_at=exit_,
                    horizon_minutes=horizon,
                    net_r=net,
                    gross_r=gross,
                    cost_r=cost,
                    source_pnl_usd=(source_pnl_by_event or {}).get(event.event_id),
                    status=status,
                    group_id=(episode_group_by_event or {}).get(
                        event.event_id, f"{event.wallet}:{event.instrument}:{event.event_id}"
                    ),
                    policy_sha256=policy.sha256,
                )
            )
    return tuple(sorted(result, key=lambda e: (e.episode_id, e.horizon_minutes)))


@dataclass(frozen=True)
class SkillEstimate:
    wallet: str
    instrument: str
    direction: str
    style: str
    sample_size: int
    effective_groups: int
    posterior_mean_r: str | None
    lower_bound_r: str | None
    history_sha256: str


def asof_skill(
    wallet: str,
    instrument: str,
    direction: str,
    style: str,
    outcomes: Iterable[FollowerEpisode],
    decision_at: str,
    *,
    prior_strength: int,
    tail_probability_z: str,
) -> SkillEstimate:
    """Normal-prior shrinkage to no-edge with overlapping group de-duplication.

    A group with multiple fills/markouts gets at most one equal-weight label.
    This is an estimate for research; it is not calibrated by itself.
    """
    if prior_strength < 1 or decimal(tail_probability_z) <= 0:
        raise ValueError("INVALID_PRIOR_OR_CONFIDENCE")
    cut = utc(decision_at)
    eligible = [
        o
        for o in outcomes
        if o.wallet == wallet
        and o.instrument == instrument
        and o.direction == direction
        and o.strategy_style == style
        and o.status in ("OK", "STOP_PROXY_FILLED")
        and o.net_r is not None
        and o.outcome_known_at is not None
        and utc(o.outcome_known_at) < cut
    ]
    by_group: dict[str, list[Decimal]] = defaultdict(list)
    for e in eligible:
        by_group[e.group_id].append(decimal(e.net_r))
    groups = [sum(v, Decimal(0)) / len(v) for _, v in sorted(by_group.items())]
    n = len(groups)
    history_hash = digest(
        {
            "wallet": wallet,
            "instrument": instrument,
            "direction": direction,
            "style": style,
            "cut": norm_clock(decision_at),
            "episode_ids": sorted(o.episode_id for o in eligible),
        }
    )
    if not n:
        return SkillEstimate(wallet, instrument, direction, style, 0, 0, None, None, history_hash)
    total = sum(groups, Decimal(0))
    posterior = total / Decimal(n + prior_strength)
    # Conservative pseudo-count shrinkage; uncertainty grows with sparse groups.
    squared = sum((x - posterior) ** 2 for x in groups)
    squared += Decimal(prior_strength) * posterior**2
    variance = squared / Decimal(max(1, n + prior_strength - 1))
    stderr = Decimal(str(sqrt(float(variance) / (n + prior_strength))))
    lcb = posterior - decimal(tail_probability_z) * stderr
    return SkillEstimate(
        wallet,
        instrument,
        direction,
        style,
        len(eligible),
        n,
        str(posterior),
        str(lcb),
        history_hash,
    )


@dataclass(frozen=True)
class CandidateCut:
    """Candidate snapshots are predeclared, not selected from hindsight winners."""

    decision_at: str
    snapshot: ObservationSnapshot
    instrument: str
    direction: str
    outcome_episode_id: str
    roster_is_point_in_time: bool

    def __post_init__(self) -> None:
        if utc(self.snapshot.roster_known_at) > utc(self.decision_at):
            raise ValueError("FUTURE_ROSTER")
        if self.direction not in ("LONG", "SHORT"):
            raise ValueError("INVALID_CANDIDATE_DIRECTION")


@dataclass(frozen=True)
class MatchedMarketControl:
    """Independent matched market-only outcome, never inferred from source PnL."""

    candidate_episode_id: str
    policy_sha256: str
    control_net_r: str
    outcome_known_at: str
    source_sha256: str

    def __post_init__(self) -> None:
        from .trader_intelligence import _sha

        _sha(self.policy_sha256)
        _sha(self.source_sha256)
        decimal(self.control_net_r)
        utc(self.outcome_known_at)
        if not self.candidate_episode_id:
            raise ValueError("MISSING_CONTROL_MATCHED_CANDIDATE")


@dataclass(frozen=True)
class BenchmarkRow:
    policy: str
    evaluated: int
    selected: int
    missing_outcomes: int
    net_r_mean: str | None
    net_r_min: str | None
    net_r_vs_market_control: str | None
    missing_controls: int
    pnl_sha256: str


@dataclass(frozen=True)
class BenchmarkReport:
    schema: str
    qualification: str
    reason: str
    cuts_sha256: str
    trial_count: int
    rows: tuple[BenchmarkRow, ...]

    def as_wire(self) -> dict:
        return {
            "schema": self.schema,
            "qualification": self.qualification,
            "reason": self.reason,
            "cuts_sha256": self.cuts_sha256,
            "trial_count": self.trial_count,
            "rows": [__import__("dataclasses").asdict(x) for x in self.rows],
        }


def matched_benchmark(
    cuts: Iterable[CandidateCut],
    outcomes: Iterable[FollowerEpisode],
    *,
    prior_strength: int,
    tail_probability_z: str,
    market_controls: dict[str, MatchedMarketControl] | None = None,
) -> BenchmarkReport:
    """Five matched policies, single candidate cuts and identical outcome labels.

    The market control must be independently supplied by the caller as a
    candidate's matched control outcome; absent controls remain unknown.
    No retrospective cohort is treated as an independent scientific holdout.
    """
    candidates = sorted(cuts, key=lambda c: (utc(c.decision_at), c.instrument, c.direction))
    history = list(outcomes)
    by_id = {e.episode_id: e for e in history}
    selected: dict[str, list[FollowerEpisode]] = {
        "incumbent_3_addresses_2_to_1": [],
        "independent_cluster_consensus": [],
        "source_pnl_ranking": [],
        "trader_skill_only": [],
        "full_trader_trade": [],
    }
    misses: dict[str, int] = {key: 0 for key in selected}
    for cut in candidates:
        if cut.outcome_episode_id not in by_id:
            for key in selected:
                misses[key] += 1
            continue
        label = by_id[cut.outcome_episode_id]
        if (
            label.instrument != cut.instrument
            or label.direction != cut.direction
            or utc(label.observation_at) > utc(cut.decision_at)
        ):
            raise ValueError("CONTROL_OR_OUTCOME_CANDIDATE_MISMATCH")
        if label.status not in ("OK", "STOP_PROXY_FILLED"):
            for key in selected:
                misses[key] += 1
            continue
        asof = [
            e
            for e in cut.snapshot.events
            if e.known_at <= utc(cut.decision_at)
            and e.instrument == cut.instrument
            and e.direction is not None
        ]
        last_by_wallet: dict[str, WalletEvent] = {}
        for e in sorted(asof, key=lambda e: (e.known_at, e.event_id)):
            last_by_wallet[e.wallet] = e
        aligned = [e for e in last_by_wallet.values() if e.direction == cut.direction]
        opposing = [e for e in last_by_wallet.values() if e.direction != cut.direction]
        roster = {w.alias: w for w in cut.snapshot.wallets}
        clusters = {roster[e.wallet].cluster for e in aligned if roster[e.wallet].cluster}
        # Never count unknown clusters as distinct.
        if len(aligned) >= 3 and len(aligned) >= 2 * max(1, len(opposing)):
            selected["incumbent_3_addresses_2_to_1"].append(label)
        if len(clusters) >= 2:
            selected["independent_cluster_consensus"].append(label)
        source_pnl = [
            decimal(e.source_pnl_usd)
            for e in history
            if e.wallet in {x.wallet for x in aligned}
            and e.source_pnl_usd is not None
            and e.outcome_known_at is not None
            and utc(e.outcome_known_at) < utc(cut.decision_at)
        ]
        if source_pnl and mean(source_pnl) > 0:
            selected["source_pnl_ranking"].append(label)
        skill_scores = [
            asof_skill(
                e.wallet,
                e.instrument,
                cut.direction,
                e.strategy_style,
                history,
                cut.decision_at,
                prior_strength=prior_strength,
                tail_probability_z=tail_probability_z,
            )
            for e in aligned
        ]
        positive = any(
            x.lower_bound_r is not None and decimal(x.lower_bound_r) > 0 for x in skill_scores
        )
        if positive:
            selected["trader_skill_only"].append(label)
        # Full model's engineering candidate gate: evidence quality + skill,
        # *not* a claim that the policy is calibrated for A/B grades.
        if (
            positive
            and len(clusters) >= 2
            and all(
                e.book_complete
                and e.source_equity_usd is not None
                and e.strategy_style == "DIRECTIONAL"
                for e in aligned
            )
        ):
            selected["full_trader_trade"].append(label)
    rows = []
    for policy, values in selected.items():
        rs = [decimal(v.net_r) for v in values if v.net_r is not None]
        matched: list[Decimal] = []
        missing_controls = 0
        for value in values:
            control = (market_controls or {}).get(value.episode_id)
            if control is None:
                missing_controls += 1
                continue
            if control.policy_sha256 != value.policy_sha256:
                raise ValueError("CONTROL_EXECUTION_POLICY_MISMATCH")
            if utc(control.outcome_known_at) <= utc(value.observation_at):
                raise ValueError("CONTROL_OUTCOME_BEFORE_CANDIDATE")
            if value.net_r is not None:
                matched.append(decimal(value.net_r) - decimal(control.control_net_r))
        rows.append(
            BenchmarkRow(
                policy=policy,
                evaluated=len(candidates),
                selected=len(values),
                missing_outcomes=misses[policy],
                net_r_mean=str(mean(rs)) if rs else None,
                net_r_min=str(min(rs)) if rs else None,
                net_r_vs_market_control=(
                    str(mean(matched)) if matched and missing_controls == 0 else None
                ),
                missing_controls=missing_controls,
                pnl_sha256=digest([v.episode_id for v in values]),
            )
        )
    return BenchmarkReport(
        schema="ti_matched_benchmark_v1",
        qualification="NOT_QUALIFIED",
        reason=(
            "NO_UNBIASED_HOLDOUT_OR_MATCHED_MARKET_CONTROL"
            if not candidates or not all(x.roster_is_point_in_time for x in candidates)
            else "FROZEN_HOLDOUT_AND_INDEPENDENT_CONTROLS_NOT_ATTESTED"
        ),
        cuts_sha256=digest(
            [
                {
                    "cut": norm_clock(x.decision_at),
                    "market": x.instrument,
                    "direction": x.direction,
                    "label": x.outcome_episode_id,
                    "snapshot": x.snapshot.sha256,
                    "pit_roster": x.roster_is_point_in_time,
                }
                for x in candidates
            ]
        ),
        trial_count=5,
        rows=tuple(rows),
    )
