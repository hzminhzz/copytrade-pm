"""Read-only PIT walk-forward diagnostics atop the existing five-policy comparator.

All outputs are descriptive. A declared date/plan is not evidence that a
selection plan, collector or real follower economics were pre-registered.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
from random import Random
from statistics import mean
from typing import Iterable

from .trader_intelligence import digest, norm_clock, utc
from .trader_intelligence_research import (
    CandidateCut,
    FollowerEpisode,
    MatchedMarketControl,
    matched_benchmark,
    require_matched_market_control,
)

POLICIES = (
    "incumbent_3_addresses_2_to_1",
    "independent_cluster_consensus",
    "source_pnl_ranking",
    "trader_skill_only",
    "full_trader_trade",
)


@dataclass(frozen=True)
class WalkForwardFold:
    start_at: str
    end_at: str
    embargo_minutes: int = 60

    def __post_init__(self) -> None:
        if utc(self.start_at) >= utc(self.end_at) or self.embargo_minutes < 60:
            raise ValueError("INVALID_WALK_FORWARD_FOLD")


@dataclass(frozen=True)
class FoldPolicyEvidence:
    policy: str
    evaluated: int
    selected: int
    matched: int
    missing_controls: int
    missing_outcomes: int
    paired_mean_r: str | None
    day_block_lcb_r: str | None
    day_count: int
    worst_day_r: str | None


@dataclass(frozen=True)
class FoldEvidence:
    start_at: str
    end_at: str
    candidate_cuts: int
    policies: tuple[FoldPolicyEvidence, ...]


@dataclass(frozen=True)
class WalkForwardEvidence:
    schema: str
    qualification: str
    reason: str
    plan_sha256: str
    input_sha256: str
    fold_count: int
    declared_trials: int
    folds: tuple[FoldEvidence, ...]

    def as_wire(self) -> dict:
        return asdict(self)


def _calendar_block_lcb(
    by_day: dict[str, list[Decimal]], *, seed: str, repetitions: int, alpha: float
) -> tuple[str | None, str | None, int]:
    if not by_day:
        return None, None, 0
    daily = [sum(vals) / len(vals) for _, vals in sorted(by_day.items())]
    if len(daily) < 5:
        # Never fabricate a usable confidence limit from sparse calendar days.
        return None, str(min(daily)), len(daily)
    random = Random(int(seed[:16], 16))
    estimates = sorted(
        sum(random.choice(daily) for _ in daily) / len(daily) for _ in range(repetitions)
    )
    # Resample calendar-day means (not independent overlapping episodes).
    return (
        str(estimates[max(0, int(alpha * repetitions) - 1)]),
        str(min(daily)),
        len(daily),
    )


def walkforward_diagnostic(
    cuts: Iterable[CandidateCut],
    outcomes: Iterable[FollowerEpisode],
    folds: Iterable[WalkForwardFold],
    *,
    plan_sha256: str,
    market_controls: dict[str, MatchedMarketControl] | None,
    prior_strength: int,
    tail_probability_z: str,
    trials_in_family: int = 10,
    bootstrap_repetitions: int = 2000,
) -> WalkForwardEvidence:
    """Match policies on identical candidate cuts, with predeclared folds.

    A control must bind exact candidate episode and execution policy. An
    unavailable, immature or non-matched control never becomes zero PnL.
    Calendar-block uncertainty is exploratory; no A/B or qualification gate.
    """
    from .trader_intelligence import _sha

    _sha(plan_sha256)
    if trials_in_family < len(POLICIES) or bootstrap_repetitions < 100:
        raise ValueError("INVALID_SELECTION_FAMILY_OR_BOOTSTRAP")
    declared = tuple(folds)
    if not declared:
        raise ValueError("MISSING_WALK_FORWARD_FOLDS")
    for left, right in zip(declared, declared[1:]):
        if utc(right.start_at) < utc(left.end_at) + timedelta(minutes=left.embargo_minutes):
            raise ValueError("OVERLAPPING_OR_UNEMBARGOED_FOLDS")
    candidates = tuple(sorted(cuts, key=lambda c: (utc(c.decision_at), c.instrument, c.direction)))
    ids = [c.outcome_episode_id for c in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("REUSED_CANDIDATE_EPISODE_ACROSS_FOLDS")
    labels = tuple(outcomes)
    outcome_index: dict[str, FollowerEpisode] = {}
    for item in labels:
        existing = outcome_index.get(item.episode_id)
        if existing is not None and existing != item:
            raise ValueError("CONFLICTING_BENCHMARK_EPISODE")
        outcome_index[item.episode_id] = item
    input_sha = digest(
        {
            "cuts": [
                (norm_clock(c.decision_at), c.snapshot.sha256, c.outcome_episode_id)
                for c in candidates
            ],
            "outcomes": [x.as_wire() for x in sorted(labels, key=lambda x: x.episode_id)],
            "controls": [(k, asdict(v)) for k, v in sorted((market_controls or {}).items())],
        }
    )
    result: list[FoldEvidence] = []
    assigned: set[str] = set()
    for fold in declared:
        members = tuple(
            c for c in candidates if utc(fold.start_at) <= utc(c.decision_at) < utc(fold.end_at)
        )
        assigned.update(c.outcome_episode_id for c in members)
        # Aggregate per candidate using the *same existing* selection logic.
        chosen = {policy: [] for policy in POLICIES}
        missing = {policy: 0 for policy in POLICIES}
        member_by_episode = {c.outcome_episode_id: c for c in members}
        for cut in members:
            single = matched_benchmark(
                (cut,),
                labels,
                prior_strength=prior_strength,
                tail_probability_z=tail_probability_z,
                market_controls=market_controls,
            )
            for row in single.rows:
                missing[row.policy] += row.missing_outcomes
                if row.selected:
                    chosen[row.policy].append(outcome_index[cut.outcome_episode_id])
        summaries: list[FoldPolicyEvidence] = []
        for policy in POLICIES:
            by_day: dict[str, list[Decimal]] = defaultdict(list)
            absent = 0
            matched_count = 0
            for label in chosen[policy]:
                control = (market_controls or {}).get(label.episode_id)
                if control is None:
                    absent += 1
                    continue
                require_matched_market_control(member_by_episode[label.episode_id], label, control)
                day = utc(label.observation_at).date().isoformat()
                by_day[day].append(Decimal(label.net_r) - Decimal(control.control_net_r))
                matched_count += 1
            all_deltas = [x for values in by_day.values() for x in values]
            seed = digest((input_sha, fold.start_at, policy, plan_sha256))
            lcb, worst, days = _calendar_block_lcb(
                by_day,
                seed=seed,
                repetitions=bootstrap_repetitions,
                alpha=0.05 / trials_in_family,
            )
            summaries.append(
                FoldPolicyEvidence(
                    policy=policy,
                    evaluated=len(members),
                    selected=len(chosen[policy]),
                    matched=matched_count,
                    missing_controls=absent,
                    missing_outcomes=missing[policy],
                    paired_mean_r=str(mean(all_deltas)) if all_deltas else None,
                    day_block_lcb_r=lcb if absent == 0 else None,
                    day_count=days,
                    worst_day_r=worst,
                )
            )
        result.append(
            FoldEvidence(
                start_at=norm_clock(fold.start_at),
                end_at=norm_clock(fold.end_at),
                candidate_cuts=len(members),
                policies=tuple(summaries),
            )
        )
    if len(assigned) != len(candidates):
        raise ValueError("CANDIDATE_OUTSIDE_DECLARED_FOLDS")
    return WalkForwardEvidence(
        schema="ti_matched_walkforward_diagnostic_v2",
        qualification="NOT_SCIENTIFICALLY_QUALIFIED",
        reason="HOLDOUT_REGISTRATION_AND_INDEPENDENT_ECONOMICS_NOT_ATTESTED",
        plan_sha256=plan_sha256,
        input_sha256=input_sha,
        fold_count=len(declared),
        declared_trials=trials_in_family,
        folds=tuple(result),
    )
