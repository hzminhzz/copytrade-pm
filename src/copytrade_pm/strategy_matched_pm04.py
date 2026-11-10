"""Matched same-account PM03/PM04 counterfactual with one candidate removed.

Research-synthetic first: original source, market, rulebook and timeline must
be identical; only candidate demand changes and the existing PM04 owner reruns
account netting, headroom, risk, PnL and HALT. Not source subtraction.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .pm03_account import Rulebook, clock, digest, number
from .pm03_memory import Event
from .pm03_run import ShadowRun


def _without_candidate(row: dict, candidate: str) -> dict:
    result = deepcopy(row)
    if row["kind"] == "PM04_SIGNAL":
        inputs = result["input"]
        if "targets" not in inputs or not isinstance(inputs["targets"], list):
            raise ValueError("MATCHED_TARGETS_REQUIRED")
        if any(not isinstance(t, dict) or "pod" not in t for t in inputs["targets"]):
            raise ValueError("MATCHED_TARGET_IDENTITY_INVALID")
        inputs["targets"] = [t for t in inputs["targets"] if t["pod"] != candidate]
    return result


def compare_candidate(spec: dict[str, Any], root: Path) -> dict:
    """Run both paths on ephemeral PM03 ledger directories, never official state."""
    if spec.get("schema") != "strategy_matched_comparison_input_v1":
        raise ValueError("MATCHED_INPUT_SCHEMA")
    if spec.get("mode") != "RESEARCH_SYNTHETIC":
        raise ValueError("MATCHED_ORIGINAL_FINANCE_NOT_AUTHENTICATED")
    if any(
        k not in spec
        for k in (
            "candidate",
            "portfolio_id",
            "rulebook",
            "policy",
            "started_at",
            "pm01_sha",
            "pm02_sha",
            "market_manifest_sha",
            "events",
        )
    ):
        raise ValueError("MATCHED_INPUT_INCOMPLETE")
    candidate = spec["candidate"]
    if not isinstance(candidate, str) or not candidate or "/" in candidate:
        raise ValueError("MATCHED_CANDIDATE_INVALID")
    if not isinstance(spec["events"], list) or not spec["events"]:
        raise ValueError("MATCHED_EVENTS_EMPTY")
    rulebook = Rulebook.from_dict(spec["rulebook"])
    if not rulebook.confirmed or rulebook.program != "SYNTHETIC":
        raise ValueError("MATCHED_RULEBOOK_NOT_SYNTHETIC")
    # The original source-policy identity is not an alternative accounting owner.
    from .pm03_account import canonical
    from .pm03_memory import _atomic_private

    policy = spec["policy"]
    policy_sha = digest(policy)
    results = {}
    for variant in ("with", "without"):
        run_id = f"tbv2-matched-{variant}"
        run = ShadowRun(
            root / "runs",
            run_id=run_id,
            rulebook=rulebook,
            started_at=spec["started_at"],
            mode="RESEARCH_SYNTHETIC",
            pm01_sha=spec["pm01_sha"],
            pm02_sha=spec["pm02_sha"],
            market_manifest_sha=spec["market_manifest_sha"],
        )
        config = deepcopy(policy)
        config["approval_reference"] = config["approval_reference"] + ":matched-research"
        config["version"] = config["version"] + ":matched-" + variant
        cfg = Event(
            event_id=f"{run_id}:config",
            kind="PM04_CONFIG",
            source_event_at=spec["started_at"],
            first_known_at=spec["started_at"],
            decision_at=spec["started_at"],
            hypothetical_fill_at=spec["started_at"],
            source_sha=policy_sha,
            payload={
                "run_id": run_id,
                "rulebook_sha": rulebook.sha,
                "input": {"policy": config},
            },
        )
        run.record(cfg)
        last = clock(spec["started_at"])
        curve = []
        for event in spec["events"]:
            if event["kind"] not in ("PM04_SIGNAL", "PM04_TICK", "PM04_BROKER", "HALT"):
                raise ValueError("MATCHED_EVENT_KIND_UNSUPPORTED")
            current = clock(event["decision_at"])
            if current < last:
                raise ValueError("MATCHED_EVENT_ORDER")
            last = current
            raw = event if variant == "with" else _without_candidate(event, candidate)
            e = Event(
                event_id=f"{run_id}:{raw['event_id']}",
                kind=raw["kind"],
                source_event_at=raw["source_event_at"],
                first_known_at=raw["first_known_at"],
                decision_at=raw["decision_at"],
                hypothetical_fill_at=raw["hypothetical_fill_at"],
                source_sha=raw["source_sha"],
                payload={
                    "run_id": run_id,
                    "rulebook_sha": rulebook.sha,
                    "input": raw["input"],
                },
                revision=raw.get("revision", 1),
            )
            run.record(e)
            snap = run.account.snapshot()
            curve.append(
                {
                    "at": e.decision_at,
                    "equity": snap["equity"],
                    "risk": snap["risk"],
                    "conservative_gross": snap.get("pm04", {})
                    .get("exposure", {})
                    .get("total_conservative_gross", "0"),
                }
            )
        snap = run.account.snapshot()
        results[variant] = {
            "account_pnl_usd": str(number(snap["equity"]) - rulebook.initial_balance),
            "equity": snap["equity"],
            "risk": snap["risk"],
            "halt_reason": snap.get("halt_reason"),
            "pm04": {
                "exposure": snap.get("pm04", {}).get("exposure"),
                "pod_stats": snap.get("pm04", {}).get("pod_stats"),
                "risk_breaches": snap.get("pm04", {}).get("risk_breaches"),
                "economics": snap.get("pm04", {}).get("economics"),
            },
            "curve": curve,
            "ledger_head": run.ledger.read()[-1]["sha"],
            "checkpoint_sha": run.checkpoint(),
        }
    with_pnl = number(results["with"]["account_pnl_usd"])
    without_pnl = number(results["without"]["account_pnl_usd"])
    result = {
        "schema": "strategy_matched_comparison_v1",
        "evidence_class": "RESEARCH_SYNTHETIC",
        "same_account_initial_balance_usd": str(rulebook.initial_balance),
        "portfolio_id": spec["portfolio_id"],
        "candidate": candidate,
        "rulebook_sha256": rulebook.sha,
        "input_sha256": digest(spec),
        "policy_sha256": policy_sha,
        "market_manifest_sha256": spec["market_manifest_sha"],
        "comparison": results,
        "marginal_pnl_usd": str(with_pnl - without_pnl),
        "risk_and_netting_recomputed": True,
        "authentic_prospective_marginal_value": False,
        "trading_authorized": False,
    }
    result["report_sha256"] = digest(result)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / f"matched-{result['input_sha256']}.json"
    _atomic_private(path, canonical(result))
    return result


def attach_to_strategy(report, comparison: dict):
    """Attach validated same-account synthetic context, never prospective authority."""
    from .strategy_health import MatchedContribution, StrategyAssessment, ZERO_SHA, seal

    if comparison.get("schema") != "strategy_matched_comparison_v1":
        raise ValueError("MATCHED_COMPARISON_SCHEMA")
    expected_sha = digest({k: v for k, v in comparison.items() if k != "report_sha256"})
    if expected_sha != comparison.get("report_sha256"):
        raise ValueError("MATCHED_COMPARISON_HASH")
    if (
        comparison.get("candidate") != report.strategy.source_alias
        or comparison.get("portfolio_id") != report.strategy.selected_portfolio
        or report.strategy.tier != "SELECTED"
    ):
        raise ValueError("MATCHED_CANDIDATE_SCOPE_INCOMPATIBLE")
    if comparison.get("authentic_prospective_marginal_value") is not False:
        raise ValueError("MATCHED_ORIGINAL_AUTHORITY_UNPROVEN")
    if report.follower_economics.evidence_class != comparison["evidence_class"]:
        contribution = MatchedContribution(reasons=("MATCHED_FINANCE_EVIDENCE_CLASS_INCOMPATIBLE",))
    elif comparison["evidence_class"] == "RESEARCH_SYNTHETIC":
        pair = comparison["comparison"]
        if set(pair) != {"with", "without"} or any(
            not x.get("ledger_head") or not x.get("checkpoint_sha") for x in pair.values()
        ):
            raise ValueError("MATCHED_LEDGER_RECEIPT_MISSING")
        if any(x["risk"] is None for x in pair.values()):
            raise ValueError("MATCHED_RISK_OUTCOME_MISSING")
        contribution = MatchedContribution(
            status="SYNTHETIC_COMPARISON",
            comparison_sha256=comparison["report_sha256"],
            candidate_portfolio=comparison["portfolio_id"],
            common_account_sha256=digest(
                [
                    comparison["same_account_initial_balance_usd"],
                    comparison["rulebook_sha256"],
                ]
            ),
            marginal_pnl_usd=number(comparison["marginal_pnl_usd"]),
            rulebook_sha256=comparison["rulebook_sha256"],
            risk_policy_sha256=comparison["policy_sha256"],
            market_manifest_sha256=comparison["market_manifest_sha256"],
            input_sha256=comparison["input_sha256"],
            with_pm03_head_sha256=pair["with"]["ledger_head"],
            without_pm03_head_sha256=pair["without"]["ledger_head"],
            reasons=("RESEARCH_SYNTHETIC_ONLY", "NOT_PROSPECTIVE_FOLLOWER_MARGINAL"),
        )
    else:
        contribution = MatchedContribution(
            reasons=("INDEPENDENT_PROSPECTIVE_SHARED_ACCOUNT_REPLAY_UNAVAILABLE",)
        )
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "portfolio_contribution": contribution,
            }
        )
    )
