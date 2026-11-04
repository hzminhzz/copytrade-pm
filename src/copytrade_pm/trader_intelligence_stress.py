"""Deterministic five-minute follower sensitivity using the EXISTING replay engine.

Replays observed/historical source transitions under four frozen assumption
variants. All output is hypothetical research, never independently settled
follower economics, an order, or permission to grade A/B.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from typing import Iterable

from .trader_intelligence import ObservationSnapshot, digest, utc
from .trader_intelligence_research import (
    FollowerEpisode,
    FollowerPolicy,
    MinuteBar,
    follower_replay,
)

STRESS_CASES = ("BASE_300S", "DOUBLE_EXECUTION_COST", "DELAY_600S", "STOP_OR_HORIZON")


@dataclass(frozen=True)
class SensitivityOutcome:
    case: str
    episode_id: str
    policy_sha256: str
    status: str
    net_r: str | None
    gross_r: str | None
    cost_r: str | None
    entry_at: str | None
    exit_at: str | None
    outcome_known_at: str | None


@dataclass(frozen=True)
class SensitivityEvent:
    source_event_id: str
    instrument: str
    wallet: str
    horizon_minutes: int
    source_pnl_usd: str | None
    scenarios: tuple[SensitivityOutcome, ...]


@dataclass(frozen=True)
class SensitivityReport:
    schema: str
    economic_evidence_status: str
    snapshot_sha256: str
    market_input_sha256: str
    policy_scenario_sha256: str
    original_event_count: int
    rows: tuple[SensitivityEvent, ...]
    report_sha256: str

    def as_wire(self) -> dict:
        return asdict(self)


def _scenarios(base: FollowerPolicy) -> tuple[tuple[str, FollowerPolicy], ...]:
    if base.delay_seconds != 300 or base.exit_policy != "FIXED_HORIZON":
        raise ValueError("BASELINE_REQUIRES_FIXED_HORIZON_300_SECONDS")
    costs = (
        "entry_fee_bps",
        "exit_fee_bps",
        "entry_slippage_bps",
        "exit_slippage_bps",
        "spread_bps",
    )
    # Funding is a signed transfer: doubling a funding *credit* could improve
    # stressed short economics. Never call that an adverse 2x execution-cost
    # test. Keep signed funding unchanged; an independent adverse funding
    # scenario requires observed event-time rates and a separate cost policy.
    doubled = replace(
        base,
        **{key: str(Decimal(getattr(base, key)) * 2) for key in costs},
    )
    return (
        ("BASE_300S", base),
        ("DOUBLE_EXECUTION_COST", doubled),
        ("DELAY_600S", replace(base, delay_seconds=600)),
        ("STOP_OR_HORIZON", replace(base, exit_policy="STOP_OR_HORIZON")),
    )


def replay_follower_sensitivities(
    snapshot: ObservationSnapshot,
    bars: Iterable[MinuteBar],
    base_policy: FollowerPolicy,
    *,
    source_pnl_by_event: dict[str, str] | None = None,
) -> SensitivityReport:
    """One candidate census under identical market series and four policies.

    Every blocked/failed/hypothetically profitable source event remains in
    every scenario. The engine's 300-second causality and minute gap checks
    govern all variants. No independent execution claim can be inferred.
    """
    market = tuple(bars)
    if len({(x.instrument, utc(x.start_at)) for x in market}) != len(market):
        raise ValueError("DUPLICATE_SENSITIVITY_MARKET_BAR")
    market_hash = digest(
        [asdict(b) for b in sorted(market, key=lambda b: (b.instrument, utc(b.start_at)))]
    )
    versions = _scenarios(base_policy)
    by_case: dict[str, dict[str, FollowerEpisode]] = {}
    for name, policy in versions:
        outcomes = follower_replay(
            snapshot,
            market,
            policy,
            source_pnl_by_event=source_pnl_by_event,
        )
        by_case[name] = {item.episode_id: item for item in outcomes}
        if len(by_case[name]) != len(outcomes):
            raise ValueError("DUPLICATE_SENSITIVITY_EPISODE")
    rows: list[SensitivityEvent] = []
    originals = sorted(
        {e.event_id: e for e in snapshot.events}.values(),
        key=lambda e: (utc(e.known_at), e.event_id),
    )
    for event in originals:
        for horizon in sorted(base_policy.horizons_minutes):
            scenario_rows = []
            for name, policy in versions:
                eid = digest(
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
                outcome = by_case[name][eid]
                scenario_rows.append(
                    SensitivityOutcome(
                        case=name,
                        episode_id=eid,
                        policy_sha256=policy.sha256,
                        status=outcome.status,
                        net_r=outcome.net_r,
                        gross_r=outcome.gross_r,
                        cost_r=outcome.cost_r,
                        entry_at=outcome.hypothetical_entry_at,
                        exit_at=outcome.hypothetical_exit_at,
                        outcome_known_at=outcome.outcome_known_at,
                    )
                )
            rows.append(
                SensitivityEvent(
                    source_event_id=event.event_id,
                    instrument=event.instrument,
                    wallet=event.wallet,
                    horizon_minutes=horizon,
                    source_pnl_usd=(source_pnl_by_event or {}).get(event.event_id),
                    scenarios=tuple(scenario_rows),
                )
            )
    basis = {
        "schema": "ti_hypothetical_follower_sensitivity_v1",
        "economic_evidence_status": "UNATTESTED_HYPOTHETICAL_RESEARCH_ONLY",
        "snapshot_sha256": snapshot.sha256,
        "market_input_sha256": market_hash,
        "policy_scenario_sha256": digest([(name, policy.sha256) for name, policy in versions]),
        "original_event_count": len(originals),
        "rows": [asdict(row) for row in rows],
    }
    return SensitivityReport(
        schema=basis["schema"],
        economic_evidence_status=basis["economic_evidence_status"],
        snapshot_sha256=basis["snapshot_sha256"],
        market_input_sha256=market_hash,
        policy_scenario_sha256=basis["policy_scenario_sha256"],
        original_event_count=len(originals),
        rows=tuple(rows),
        report_sha256=digest(basis),
    )
