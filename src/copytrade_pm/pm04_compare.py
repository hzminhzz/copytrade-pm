"""Deterministic offline PM-04 policy tournament on identical synthetic inputs.

All executions and PnL are hypothetical. No real broker client, credentials,
source strategy assumptions or statistical pass probabilities are used.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
import json

from .pm03_account import Rulebook, canonical, clock, digest, number, ZERO
from .pm03_memory import Event, _atomic_private
from .pm03_run import ShadowRun


def _decline(start: D, path: list[D]) -> str:
    peak = start
    maximum = ZERO
    for equity in path:
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return str(maximum)


def compare_pm04_policies(spec: dict, output_dir: Path) -> dict:
    """Replay same ordered synthetic signal/mark events for three coordinator policies.

    Input events are PM04_SIGNAL / PM04_TICK / PM04_BROKER envelopes with
    source/knowledge/decision clocks and exactly the same input bytes.
    Policy changes ONLY batching timing, not pod risk thresholds or market data.
    """
    if spec.get("schema") != "pm04_compare_input_v1":
        raise ValueError("INVALID_PM04_COMPARE_INPUT")
    if spec.get("mode") != "RESEARCH_SYNTHETIC":
        raise ValueError("NO_NON_SYNTHETIC_PM04_POLICY_COMPARISON")
    cache = output_dir / f"pm04-comparison-{digest(spec)}.json"
    if cache.exists():
        result = json.loads(cache.read_text(encoding="utf-8"))
        if result.get("source_sha") != digest(spec) or result.get("report_sha") != digest(
            {k: v for k, v in result.items() if k != "report_sha"}
        ):
            raise ValueError("CORRUPTED_PM04_IMMUTABLE_COMPARISON")
        # A valid cached report must not hide deleted/truncated ledgers or a
        # crash that left an incomplete scenario after report publication.
        for name, scenario in result["comparison"].items():
            root = output_dir / "runs" / f"pm04-compare-{name}"
            if not (root / "events.jsonl").is_file():
                raise ValueError("MISSING_COMPARISON_LEDGER")
            replay = ShadowRun(
                output_dir / "runs",
                run_id=f"pm04-compare-{name}",
                rulebook=Rulebook.from_dict(spec["rulebook"]),
                started_at=spec["started_at"],
                mode="RESEARCH_SYNTHETIC",
                pm01_sha=spec["pm01_sha"],
                pm02_sha=spec["pm02_sha"],
                market_manifest_sha=spec["market_manifest_sha"],
            )
            rows = replay.ledger.read()
            if not rows or rows[-1]["sha"] != scenario["ledger_head"]:
                raise ValueError("COMPARISON_LEDGER_HEAD_MISMATCH")
            replay.verify_checkpoint(scenario["checkpoint_sha"])
        return result
    rulebook = Rulebook.from_dict(spec["rulebook"])
    if not rulebook.confirmed or rulebook.program != "SYNTHETIC":
        raise ValueError("PM04_COMPARE_REQUIRES_SYNTHETIC_RULEBOOK")
    started_at = spec["started_at"]
    policy = spec["policy"]
    events = spec["events"]
    if not events:
        raise ValueError("PM04_COMPARE_EMPTY_EVENTS")
    previous = clock(started_at)
    for row in events:
        if row["kind"] not in ("PM04_SIGNAL", "PM04_TICK", "PM04_BROKER"):
            raise ValueError("INVALID_PM04_COMPARE_EVENT")
        t = clock(row["decision_at"])
        if t < previous:
            raise ValueError("PM04_COMPARE_EVENTS_NOT_CHRONOLOGICAL")
        previous = t
    comparison = {}
    for mode in ("IMMEDIATE", "BATCHED", "ASYMMETRIC"):
        local_policy = deepcopy(policy)
        local_policy["execution_policy"] = mode
        local_policy["version"] = f"{policy['version']}:{mode.lower()}"
        local_policy["approval_reference"] = policy["approval_reference"] + ":comparison"
        run_id = f"pm04-compare-{mode.lower()}"
        root = output_dir / "runs"
        run = ShadowRun(
            root,
            run_id=run_id,
            rulebook=rulebook,
            started_at=started_at,
            mode="RESEARCH_SYNTHETIC",
            pm01_sha=spec["pm01_sha"],
            pm02_sha=spec["pm02_sha"],
            market_manifest_sha=spec["market_manifest_sha"],
        )
        config = Event(
            event_id=f"{run_id}:config",
            kind="PM04_CONFIG",
            source_event_at=started_at,
            first_known_at=started_at,
            decision_at=started_at,
            hypothetical_fill_at=started_at,
            source_sha=digest(local_policy),
            payload={
                "run_id": run_id,
                "rulebook_sha": rulebook.sha,
                "input": {"policy": local_policy},
            },
        )
        run.record(config)
        timeline: list[dict] = []
        for row in events:
            e = Event(
                event_id=f"{run_id}:{row['event_id']}",
                source_event_at=row["source_event_at"],
                first_known_at=row["first_known_at"],
                decision_at=row["decision_at"],
                hypothetical_fill_at=row["hypothetical_fill_at"],
                kind=row["kind"],
                source_sha=row["source_sha"],
                payload={"run_id": run_id, "rulebook_sha": rulebook.sha, "input": row["input"]},
                revision=row.get("revision", 1),
            )
            run.record(e)
            snap = run.account.snapshot()
            active_floor, floor_components = run.account.floor()
            daily_floor = floor_components.get("daily")
            timeline.append(
                {
                    "at": e.decision_at,
                    "daily_floor_headroom": (
                        str(number(snap["equity"]) - daily_floor)
                        if daily_floor is not None
                        else None
                    ),
                    "contractual_floor_headroom": (
                        str(number(snap["equity"]) - active_floor)
                        if active_floor is not None
                        else None
                    ),
                    "conservative_reserved_gross": snap.get("pm04", {})
                    .get("exposure", {})
                    .get("total_conservative_gross", "0"),
                    "equity": snap["equity"],
                    "balance": snap["balance"],
                    "daily_start_balance": snap["daily_start_balance"],
                    "daily_key": snap["daily_key"],
                    "gross": snap.get("pm04", {}).get("exposure", {}).get("actual_gross", "0"),
                    "risk": snap["risk"],
                    "pending_reductions": snap.get("pm04", {}).get("pending_reductions", {}),
                }
            )
        snap = run.account.snapshot()
        pm04 = snap["pm04"]
        equities = [number(row["equity"]) for row in timeline]
        start = rulebook.initial_balance
        worst_daily = max(
            (
                max(ZERO, number(item["daily_start_balance"]) - number(item["equity"]))
                for item in timeline
            ),
            default=ZERO,
        )
        comparison[mode.lower()] = {
            "account_pnl": str(number(snap["equity"]) - start),
            "equity_curve": timeline,
            "sampled_max_drawdown": _decline(start, equities),
            "sampled_worst_daily_equity_loss": str(worst_daily),
            "worst_daily_floor_headroom": (
                str(min(number(row["daily_floor_headroom"]) for row in timeline))
                if all(row["daily_floor_headroom"] is not None for row in timeline)
                else None
            ),
            "worst_contractual_floor_headroom": (
                str(min(number(row["contractual_floor_headroom"]) for row in timeline))
                if all(row["contractual_floor_headroom"] is not None for row in timeline)
                else None
            ),
            "gross_limit": str(number(policy["max_gross_notional"])),
            "marked_gross_peak": str(max((number(row["gross"]) for row in timeline), default=ZERO)),
            "peak_conservative_reserved_gross": str(
                max(
                    (number(row["conservative_reserved_gross"]) for row in timeline),
                    default=ZERO,
                )
            ),
            "pod_executed_pnl": {p: x["pnl"] for p, x in pm04["pod_stats"].items()},
            "pod_state": {p: x["state"] for p, x in pm04["pod_stats"].items()},
            "limit_violations": pm04["risk_breaches"],
            "pending_reductions": pm04["pending_reductions"],
            "reconciliation_residual": pm04["economics"]["reconciliation_rounding_residual"],
            "broker_discrepancies": pm04["broker"]["discrepancies"],
            "ledger_head": run.ledger.read()[-1]["sha"],
            "checkpoint_sha": run.checkpoint(),
            "shadow_only": True,
        }
    result = {
        "schema": "pm04_three_policy_comparison_v1",
        "research_only": True,
        "no_live_order_path": True,
        "not_challenge_pass_probability": True,
        "source_sha": digest(spec),
        "comparison": comparison,
    }
    result["report_sha"] = digest(result)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    _atomic_private(cache, canonical(result))
    return result
