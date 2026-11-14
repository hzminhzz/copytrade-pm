"""Original PM03/PM04 finance evidence verified without altering its journal.

Reuses original PM03 reducer and accounting invariants. Never creates a second
financial ledger; copies no original state into an executable account.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
import json
from pathlib import Path

from .pm03_account import Account, Rulebook, clock, digest, number
from .pm03_memory import Event, Ledger
from .pm03_risk import RiskPolicy
from .pm03_run import ShadowRun


def inspect_pm03_original(root: Path, *, as_of: datetime, expected_head: str | None = None) -> dict:
    """Re-execute a SHA-linked *original* ledger using PM03 reducer in memory."""
    if as_of.tzinfo is None or as_of.utcoffset() != __import__("datetime").timedelta(0):
        raise ValueError("PM03_EVIDENCE_ASOF_UTC")
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise ValueError("PM03_ORIGINAL_PRIVATE_DIRECTORY_REQUIRED")
    manifest_path = root / "manifest.json"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or (manifest_path.stat().st_mode & 0o077)
    ):
        raise ValueError("PM03_ORIGINAL_MANIFEST_UNSAFE")
    raw = manifest_path.read_bytes()
    if len(raw) > 131072:
        raise ValueError("PM03_ORIGINAL_MANIFEST_TOO_LARGE")
    manifest = json.loads(raw)
    if manifest.get("schema") != "pm03_shadow_run_v1" or manifest.get("mode") not in {
        "RESEARCH_SYNTHETIC",
        "PROSPECTIVE_OBSERVED",
        "HISTORICAL_HINDSIGHT",
    }:
        raise ValueError("PM03_ORIGINAL_MANIFEST_INVALID")
    rulebook = Rulebook.from_dict(manifest["rulebook"])
    if rulebook.sha != manifest["rulebook_sha"]:
        raise ValueError("PM03_RULEBOOK_SHA_DIVERGENCE")
    policy = RiskPolicy(
        **{field.name: number(manifest["risk_policy"][field.name]) for field in fields(RiskPolicy)}
    )
    events_path = root / "events.jsonl"
    if events_path.is_symlink():
        raise ValueError("PM03_LEDGER_SYMLINK")
    events = Ledger.read_path(events_path)
    head = events[-1]["sha"] if events else "0" * 64
    if expected_head is not None and head != expected_head:
        raise ValueError("PM03_ORIGINAL_HEAD_CHANGED")
    account = Account.start(rulebook, manifest["started_at"])
    seen = []
    last_time = clock(manifest["started_at"])
    for record in events:
        original = Event(**record["event"])
        if clock(original.decision_at) > as_of:
            raise ValueError("PM03_POST_ASOF_EVENT_PRESENT")
        if clock(original.decision_at) < last_time:
            raise ValueError("PM03_NONCAUSAL_FINANCE")
        last_time = clock(original.decision_at)
        effect = ShadowRun.replay_record(account, original, manifest, policy)
        post_sha = digest({"account": account.snapshot(), "result": effect})
        if post_sha != original.payload.get("post_state_sha"):
            raise ValueError("PM03_FINANCIAL_REPLAY_DIVERGENCE")
        if original.payload.get("tool_trace") != {
            "action": f"pm03.shadow.{original.kind.lower()}",
            "status": "OK",
            "executed_at": original.decision_at,
            "input_sha": original.source_sha,
            "output_sha": post_sha,
            "rulebook_sha": account.rulebook.sha,
        }:
            raise ValueError("PM03_ORIGINAL_TRACE_INVALID")
        seen.append(
            {
                "kind": original.kind,
                "decision_at": original.decision_at,
                "source_sha": original.source_sha,
                "source_event_at": original.source_event_at,
                "first_known_at": original.first_known_at,
                "input": original.payload["input"],
                "post_state_sha": post_sha,
            }
        )
    account.verify()
    return {
        "schema": "strategy_pm03_original_verified_v1",
        "mode": manifest["mode"],
        "run_id": manifest["run_id"],
        "manifest_sha256": digest(manifest),
        "ledger_head_sha256": head,
        "original_rulebook": manifest["rulebook"],
        "account": account.snapshot(),
        "account_as_of": last_time.isoformat(),
        "events": seen,
        "read_only": True,
        "broker_outcomes_verified": False,
        "trading_authorized": False,
    }


def reconcile_source_attempts(report, original: dict):
    """Join original PM04 attempt identity by receipt SHA + T0, never by guess."""
    from .strategy_health import StrategyAssessment, ZERO_SHA, seal

    if original["schema"] != "strategy_pm03_original_verified_v1":
        raise ValueError("UNVERIFIED_PM03_ORIGINAL")
    if report.strategy.tier != "SELECTED":
        raise ValueError("DISCOVERY_HAS_NO_PAPER_ATTEMPTS")
    source = {}
    for event in original["events"]:
        if event["kind"] != "PM04_PAPER_SOURCE":
            continue
        raw = event["input"]
        if raw.get("pod") != report.strategy.source_alias:
            continue
        key = (raw.get("source_sha"), clock(raw["first_known_at"]))
        source.setdefault(key, []).append(event)
    state = original["account"].get("pm04", {}).get("paper_execution", {})
    history = state.get("history", {})
    if not isinstance(history, dict):
        raise ValueError("PM04_ORIGINAL_ATTEMPT_SCHEMA")
    rows = []
    for opportunity in report.opportunities:
        key = (opportunity.source_receipt_sha256, opportunity.first_known_at)
        records = source.get(key, [])
        if len(records) > 1:
            raise ValueError("AMBIGUOUS_SOURCE_PAPER_JOIN")
        matching = [
            intent
            for intent in history.values()
            if intent.get("pod") == report.strategy.source_alias
            and intent.get("first_known_at") is not None
            and clock(intent["first_known_at"]) == opportunity.first_known_at
            and any(
                update.get("source_sha") == opportunity.source_receipt_sha256
                and update.get("source_seq") == opportunity.stream_cursor
                for update in intent.get("updates", [])
            )
        ]
        if not records or not matching:
            rows.append(
                opportunity.model_copy(update={"reason": "NO_ORIGINAL_MODEL_ATTEMPT_PROOF"})
            )
            continue
        if len(matching) != 1:
            raise ValueError("DUPLICATE_ORIGINAL_PAPER_INTENT")
        intent = matching[0]
        if clock(intent["due_at"]) != opportunity.due_at:
            raise ValueError("PM04_ORIGINAL_DUE_CHANGED")
        if intent.get("intent_id") is None:
            raise ValueError("PM04_ORIGINAL_ATTEMPT_ID_MISSING")
        status = intent["status"]
        if status == "PENDING_5M":
            state_name = "PENDING"
        elif status in {"CANCELED", "CANCELED_SOURCE_GAP"}:
            state_name = "CANCELED"
        elif status == "EXPIRED_NO_TRADE":
            state_name = "EXPIRED"
        elif status.startswith("REJECTED"):
            state_name = "REJECTED"
        elif status in {"FILLED", "PARTIAL"}:
            held = original["account"]["pm_quantities"].get(report.strategy.source_alias, {})
            state_name = "OPEN" if any(number(q) != 0 for q in held.values()) else "ADMITTED"
        else:
            state_name = "UNRESOLVED"
        rows.append(
            opportunity.model_copy(
                update={
                    "state": state_name,
                    "attempt_id": intent["intent_id"],
                    "attempt_receipt_sha256": original["ledger_head_sha256"],
                    "reason": status[:128],
                }
            )
        )
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "opportunities": tuple(rows),
            }
        )
    )


def summarize_pm03_economics(
    original: dict,
    *,
    as_of: datetime,
    pod_alias: str | None = None,
    max_quote_age_seconds: int = 120,
):
    """Only PM03's own reconciled balances and original open inventory."""
    from .strategy_health import FollowerEconomics

    if original["schema"] != "strategy_pm03_original_verified_v1":
        raise ValueError("PM03_UNVERIFIED_INPUT")
    snapshot = original["account"]
    if clock(original["account_as_of"]) > as_of:
        raise ValueError("PM03_ECONOMICS_AHEAD_OF_ASOF")
    if not 1 <= max_quote_age_seconds <= 86400:
        raise ValueError("PM03_QUOTE_AGE_BOUND_INVALID")
    rulebook = Rulebook.from_dict(original["original_rulebook"])
    account = Account.from_snapshot(rulebook, snapshot)
    account.verify()
    open_exposure = any(number(q) != 0 for q in snapshot["quantities"].values())
    mark_known = not open_exposure or snapshot["last_mark_at"] is not None
    reasons = ["INDEPENDENT_MARKET_AND_COST_COMPLETENESS_UNKNOWN"]
    if open_exposure and not mark_known:
        reasons.append("OPEN_UNMARKED_EXPOSURE")
    if (
        open_exposure
        and mark_known
        and (as_of - clock(snapshot["last_mark_at"])).total_seconds() > max_quote_age_seconds
    ):
        reasons.append("LAST_MARK_STALE_AT_ASOF")
    paper = snapshot.get("pm04", {}).get("paper_execution", {})
    if any(
        row.get("status") in {"PENDING_EXIT", "PARTIAL_EXIT", "UNRESOLVED_EXIT"}
        for row in paper.get("exits", {}).values()
    ):
        reasons.append("PAPER_EXIT_FINANCIAL_EFFECT_UNRESOLVED")
    per_pod = account.pm_equity_pnl() if pod_alias else {}
    pod_pnl = per_pod.get(pod_alias) if pod_alias else None
    pod_positions = account.pm_quantities.get(pod_alias, {}) if pod_alias else {}
    pod_gross = (
        sum((abs(q * account.marks[inst]) for inst, q in pod_positions.items()), number("0"))
        if pod_alias
        else None
    )
    pm04_policy = snapshot.get("pm04", {}).get("policy", {})
    pod_rule = pm04_policy.get("pods", {}).get(pod_alias, {}) if pod_alias else {}
    pod_budget = number(pod_rule["stress_loss"]) if "stress_loss" in pod_rule else None
    if pod_alias is not None and pod_pnl is None:
        reasons.append("POD_NOT_IN_PM03_FINANCIAL_LEDGER")
    if pod_alias is not None and (pod_budget is None or pod_budget <= 0):
        reasons.append("POD_FROZEN_R_BUDGET_UNAVAILABLE")
    return FollowerEconomics(
        evidence_class={
            "RESEARCH_SYNTHETIC": "RESEARCH_SYNTHETIC",
            "HISTORICAL_HINDSIGHT": "UNKNOWN",
            "PROSPECTIVE_OBSERVED": "PROSPECTIVE_SHADOW",
        }[original["mode"]],
        net_comparable=False,
        evidence_sha256=original["manifest_sha256"],
        original_pm03_head_sha256=original["ledger_head_sha256"],
        as_of=clock(original["account_as_of"]),
        marked_equity_usd=number(snapshot["equity"]),
        realized_pnl_usd=number(snapshot["realized_pnl"]),
        unrealized_pnl_usd=number(snapshot["equity"]) - number(snapshot["balance"]),
        costs_usd=number(snapshot["costs"]),
        funding_usd=number(snapshot["funding"]),
        open_risk_usd=None,
        pod_marked_net_usd=pod_pnl,
        pod_open_gross_usd=pod_gross,
        pod_budget_usd=pod_budget,
        pod_marked_net_r=(
            pod_pnl / pod_budget
            if pod_pnl is not None and pod_budget is not None and pod_budget > 0
            else None
        ),
        account_risk_state=snapshot["risk"],
        original_halt_reason=snapshot["halt_reason"],
        reasons=tuple(reasons),
    )
