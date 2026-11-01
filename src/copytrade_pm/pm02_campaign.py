"""Immutable prospective selection plans and OOS lifecycle gates.

Registration is a local, time-stamped research record, not independent scientific
approval. The external outcome auditor must verify the plan and its provenance.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from .pm03_account import canonical, digest
from .pm03_memory import clock

SCHEMA = "pm02_forward_campaign_v1"
STATES = {"CANDIDATE", "SHADOW", "INCUBATION", "ACTIVE", "CORE", "REDUCED", "SUSPENDED", "RETIRED"}


def policy_contract() -> dict:
    from . import pm_manager as manager

    return {
        "min_episodes": manager.MIN_EPISODES,
        "min_effective": manager.MIN_EFFECTIVE_EPISODES,
        "min_days": manager.MIN_DAYS,
        "familywise_alpha": manager.ALPHA_FAMILY,
        "min_z": 3.5,
        "max_drawdown_r": manager.MAX_DRAWDOWN_R,
        "max_staleness_hours": manager.MAX_STALENESS_HOURS,
        "whole_account_outcome_schema": "pm02_independent_matched_outcome_v2",
        "selection_contract": "fixed_oos_all_horizons_v1",
        "concentration_contract": "worst_daily_absolute_envelope_v1",
        "code_sha256": {
            name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in (
                "pm02_campaign.py",
                "pm02_outcomes.py",
                "pm02_risk.py",
                "pm_manager.py",
                "pm_prospective_ledger.py",
                "pm02_audit.py",
            )
        },
    }


def validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("INVALID_CAMPAIGN_SCHEMA")
    if plan.get("sha256") != digest({k: v for k, v in plan.items() if k != "sha256"}):
        raise ValueError("CAMPAIGN_HASH_MISMATCH")
    if not isinstance(plan.get("pm01_source_sha256"), str) or not re.fullmatch(
        "[0-9a-f]{64}", plan["pm01_source_sha256"]
    ):
        raise ValueError("CAMPAIGN_SOURCE_HASH_REQUIRED")
    cohort = plan.get("cohort")
    if (
        not isinstance(cohort, list)
        or len(cohort) != 36
        or any(not isinstance(a, str) or not a for a in cohort)
        or cohort != sorted(set(cohort))
    ):
        raise ValueError("CAMPAIGN_REQUIRES_FROZEN_36_COHORT")
    if plan.get("horizons_minutes") != [5, 15, 60] or plan.get("primary_horizon_minutes") != 15:
        raise ValueError("CAMPAIGN_HORIZON_CONTRACT_CHANGED")
    windows = plan.get("windows")
    if not isinstance(windows, list) or not 1 <= len(windows) <= 12:
        raise ValueError("INVALID_OOS_WINDOWS")
    if plan.get("declared_hypotheses") != len(cohort) * 3 * len(windows):
        raise ValueError("UNDERDECLARED_MULTIPLICITY_FAMILY")
    if plan.get("policy") != policy_contract() or plan.get("research_only") is not True:
        raise ValueError("CAMPAIGN_POLICY_CHANGED")
    registered = clock(plan["registered_at"])
    previous_end = None
    seen = set()
    for window in windows:
        name = window.get("id")
        if (
            not isinstance(name, str)
            or not re.fullmatch("[A-Za-z0-9_-]{1,64}", name)
            or name in seen
        ):
            raise ValueError("INVALID_OOS_WINDOW_ID")
        seen.add(name)
        start, end, decision = (clock(window[k]) for k in ("start_at", "end_at", "decision_at"))
        if registered >= start:
            raise ValueError("CAMPAIGN_MUST_BE_REGISTERED_BEFORE_OOS")
        if previous_end is not None and start < previous_end:
            raise ValueError("OVERLAPPING_OOS_WINDOWS")
        if end - start < timedelta(days=30) or not end + timedelta(
            minutes=60
        ) <= decision <= end + timedelta(hours=24):
            raise ValueError("INVALID_OOS_DURATION_OR_MATURITY")
        previous_end = end


def read_plan(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o077
        or path.stat().st_size > 64000
    ):
        raise ValueError("UNSAFE_CAMPAIGN_FILE")
    raw = path.read_bytes()
    plan = json.loads(raw)
    validate_plan(plan)
    if path.name != f"pm02-campaign-{plan['sha256']}.json" or raw != canonical(plan) + b"\n":
        raise ValueError("NONCANONICAL_CAMPAIGN_FILE")
    return plan


def register_plan(
    root: Path,
    *,
    pm01_sha256: str,
    aliases: list[str],
    windows: list[dict],
    clock_source=lambda: datetime.now(UTC),
) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("UNSAFE_CAMPAIGN_DIRECTORY")
    proposed = {
        "schema": SCHEMA,
        "pm01_source_sha256": pm01_sha256,
        "cohort": sorted(aliases),
        "windows": windows,
        "horizons_minutes": [5, 15, 60],
        "primary_horizon_minutes": 15,
        "declared_hypotheses": len(aliases) * 3 * len(windows),
        "policy": policy_contract(),
        "research_only": True,
    }
    fd = os.open(root / ".registration.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        existing = list(root.glob("pm02-campaign-*.json"))
        if existing:
            if len(existing) != 1:
                raise ValueError("AMBIGUOUS_CAMPAIGN_REGISTRY")
            previous = read_plan(existing[0])
            if {
                k: v for k, v in previous.items() if k not in ("sha256", "registered_at")
            } != proposed:
                raise ValueError("IMMUTABLE_CAMPAIGN_ALREADY_REGISTERED")
            return existing[0]
        plan = {**proposed, "registered_at": clock_source().isoformat()}
        plan["sha256"] = digest(plan)
        validate_plan(plan)
        path = root / f"pm02-campaign-{plan['sha256']}.json"
        out = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, "wb") as stream:
            stream.write(canonical(plan) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def window_asof(plan: dict, asof: str) -> dict | None:
    validate_plan(plan)
    at = clock(asof)
    if at < clock(plan["registered_at"]):
        raise ValueError("CAMPAIGN_NOT_KNOWN_ASOF")
    eligible = [w for w in plan["windows"] if clock(w["decision_at"]) <= at]
    return eligible[-1] if eligible else None


def evaluate_window(
    rows: list[dict], plan: dict, window: dict | None, asof: str
) -> tuple[list[dict], dict, list[dict]]:
    """Evaluate declared horizons separately; never pool correlated horizon trials.

    The primary rows describe the current OOS result. Risk history includes only
    independently audited primary outcomes available at each prior fixed look.
    """
    from .pm_manager import _prospective_evidence, _score
    from .pm02_outcomes import SCHEMA as OUTCOME_SCHEMA, validate_whole_account

    at = clock(asof)
    if window is None:
        score = _score([], at, plan["declared_hypotheses"])
        score["reasons"].append("OOS_WINDOW_NOT_MATURE")
        return [], score, []
    cutoff = clock(window["decision_at"])
    available = _prospective_evidence(rows, min(at, cutoff))
    start, end = clock(window["start_at"]), clock(window["end_at"])
    current = [r for r in available if start <= clock(r["event_at"]) < end]
    reasons = []
    valid = []
    identities = set()
    for row in available:
        if (
            row.get("whole_account_verified") is not True
            or row.get("outcome_schema") != OUTCOME_SCHEMA
        ):
            if row in current:
                reasons.append("INDEPENDENT_WHOLE_ACCOUNT_OUTCOME_REQUIRED")
            continue
        validate_whole_account({**row, "schema": row["outcome_schema"]})
        if row.get("selection_plan_sha256") != plan["sha256"]:
            if row in current:
                reasons.append("CAMPAIGN_LINEAGE_MISMATCH")
            continue
        horizon = row.get("horizon_minutes")
        if type(horizon) is not int or horizon not in plan["horizons_minutes"]:
            raise ValueError("UNDECLARED_OUTCOME_HORIZON")
        identity = (row.get("source_event_id"), horizon)
        if not isinstance(identity[0], str) or not identity[0] or identity in identities:
            raise ValueError("DUPLICATE_OR_MISSING_SOURCE_HORIZON")
        identities.add(identity)
        if clock(row["decision_at"]) < clock(row["known_at"]):
            raise ValueError("DECISION_PRECEDES_FIRST_KNOWN")
        if clock(row["outcome_known_at"]) < clock(row["decision_at"]) + timedelta(minutes=horizon):
            raise ValueError("IMMATURE_WHOLE_ACCOUNT_OUTCOME")
        valid.append(row)
    horizons = {}
    primary = []
    for horizon in plan["horizons_minutes"]:
        selected = [
            r
            for r in valid
            if start <= clock(r["event_at"]) < end and r["horizon_minutes"] == horizon
        ]
        score = _score(selected, cutoff, plan["declared_hypotheses"])
        # Repeated overlapping marks of one position are not independent episodes.
        decision_order = sorted(selected, key=lambda r: clock(r["decision_at"]))
        if any(
            clock(b["decision_at"]) < clock(a["decision_at"]) + timedelta(minutes=horizon)
            for a, b in zip(decision_order, decision_order[1:])
        ):
            score["reasons"].append("OVERLAPPING_OUTCOME_WINDOWS")
            score["qualified"] = False
        horizons[str(horizon)] = score
        if horizon == plan["primary_horizon_minutes"]:
            primary = selected
    result = dict(horizons[str(plan["primary_horizon_minutes"])])
    result["reasons"] = sorted(set(result["reasons"] + reasons))
    if not all(score["qualified"] for score in horizons.values()):
        result["reasons"].append("ALL_PREDECLARED_HORIZONS_REQUIRED")
    if at > cutoff + timedelta(hours=24):
        result["reasons"].append("STALE_OOS_DECISION")
        result["stale"] = True
    result["qualified"] = not result["reasons"]
    result["horizon_scores"] = horizons
    result["window_id"] = window["id"]
    result["fixed_decision_at"] = window["decision_at"]
    risk_rows = [
        row
        for row in valid
        if row["horizon_minutes"] == plan["primary_horizon_minutes"]
        and any(
            clock(w["start_at"]) <= clock(row["event_at"]) < clock(w["end_at"])
            and clock(row["outcome_known_at"]) <= clock(w["decision_at"]) <= cutoff
            for w in plan["windows"]
        )
    ]
    risk_order = sorted(risk_rows, key=lambda r: clock(r["decision_at"]))
    if any(
        clock(b["decision_at"])
        < clock(a["decision_at"]) + timedelta(minutes=plan["primary_horizon_minutes"])
        for a, b in zip(risk_order, risk_order[1:])
    ):
        result["reasons"].append("OVERLAPPING_RISK_HISTORY")
        result["qualified"] = False
    return primary, result, risk_rows


def transition(
    previous: str,
    *,
    qualified: bool,
    new_window: bool,
    failures: int,
    stale: bool = False,
) -> str:
    if previous not in STATES:
        raise ValueError("INVALID_MANAGER_LIFECYCLE_STATE")
    if previous == "RETIRED" or (new_window and failures >= 3):
        return "RETIRED"
    if stale:
        return "SUSPENDED" if previous != "CANDIDATE" else "CANDIDATE"
    if not qualified:
        return "REDUCED" if previous in ("ACTIVE", "CORE", "INCUBATION", "REDUCED") else previous
    if not new_window:
        return previous
    return {
        "CANDIDATE": "SHADOW",
        "SHADOW": "INCUBATION",
        "INCUBATION": "ACTIVE",
        "ACTIVE": "CORE",
        "CORE": "CORE",
        "REDUCED": "INCUBATION",
        "SUSPENDED": "SHADOW",
    }[previous]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm01", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--oos-start", required=True)
    parser.add_argument("--windows", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.windows <= 12:
        raise ValueError("INVALID_OOS_WINDOWS")
    from .pm02_audit import source_file_read
    from .pm_manager import source_rows
    from .pm_portfolio import Coverage, WalletSource, validate_36_wallet_cohort

    replay, _ = source_file_read(args.pm01)
    cohorts = {r["wallet"]: r["cohort"] for r in replay["rows"]}
    aliases = sorted(cohorts)
    validate_36_wallet_cohort(
        WalletSource(a, cohorts[a], Coverage.HISTORICAL_ONLY) for a in aliases
    )
    source_rows(replay, aliases)
    start = clock(args.oos_start)
    windows = [
        {
            "id": f"oos-{i + 1}",
            "start_at": (start + timedelta(days=30 * i)).isoformat(),
            "end_at": (start + timedelta(days=30 * (i + 1))).isoformat(),
            "decision_at": (start + timedelta(days=30 * (i + 1), hours=1)).isoformat(),
        }
        for i in range(args.windows)
    ]
    path = register_plan(args.out, pm01_sha256=digest(replay), aliases=aliases, windows=windows)
    print(
        json.dumps(
            {
                "file": str(path),
                "sha256": read_plan(path)["sha256"],
                "status": "REGISTERED_RESEARCH_ONLY_REQUIRES_INDEPENDENT_AUDIT",
            }
        )
    )


if __name__ == "__main__":
    main()
