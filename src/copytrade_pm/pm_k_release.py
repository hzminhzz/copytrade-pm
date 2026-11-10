"""Track C read-only release candidate verification against actual PM03/PM04 wires.

Never writes an active policy pointer, paper journal, SQLite selection or broker.
The existing V4 consumer is not release-version-aware: activation always blocked.
"""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .pm03_account import clock, digest, number
from .pm_k_recalibration import KReleaseCandidate
from .pm_offline_cache import ImmutableCache


def verify_cutover(
    candidate: KReleaseCandidate,
    *,
    paper_snapshot: dict[str, Any],
    paper_snapshot_sha256: str,
    current_policy: dict[str, Any],
    checked_at: str,
    observed_release_sha256: str,
) -> dict:
    """Audit the real historical paper snapshot structure; no financial mutation."""
    KReleaseCandidate.model_validate_json(candidate.model_dump_json(by_alias=True))
    blockers: set[str] = set()
    if digest(paper_snapshot) != paper_snapshot_sha256:
        blockers.add("PAPER_SNAPSHOT_HASH_MISMATCH")
    if not isinstance(current_policy, dict):
        raise ValueError("PM04_POLICY_REQUIRED")
    if candidate.rollback_release_sha256 != observed_release_sha256:
        blockers.add("ROLLBACK_RELEASE_IDENTITY_MISMATCH")
    if candidate.current_policy_sha256 is None or digest(current_policy) != (
        candidate.current_policy_sha256
    ):
        blockers.add("FROZEN_PM04_POLICY_HASH_MISMATCH")
    if current_policy.get("sizing_policy") == "ALLOCATION_OVER_LIVE_NAV":
        blockers.add("INCOMPATIBLE_NAV_RELATIVE_POLICY")
    if candidate.sizing_policy_version == "ALLOCATION_OVER_LIVE_NAV":
        blockers.add("RELEASE_NONFIXED_SIZING_POLICY")
    frozen_k = current_policy.get("fixed_k_by_pod", {})
    if not isinstance(frozen_k, dict) or set(candidate.pod_membership) - set(frozen_k):
        blockers.add("ORIGINAL_POD_K_MISSING")
    else:
        for proposal in candidate.proposals:
            if number(frozen_k[proposal.pod_id]) != proposal.current_frozen_k:
                blockers.add("ORIGINAL_K_POLICY_DRIFT")
    if paper_snapshot.get("schema") != "pm03_account_v2":
        blockers.add("UNSUPPORTED_PAPER_ACCOUNT_SCHEMA")
    pm04 = paper_snapshot.get("pm04", {})
    if not isinstance(pm04, dict) or pm04.get("policy") != current_policy:
        blockers.add("PM04_SNAPSHOT_POLICY_MISMATCH")
    execution = pm04.get("paper_execution", {}) if isinstance(pm04, dict) else {}
    if not isinstance(execution, dict):
        blockers.add("UNKNOWN_PM04_PAPER_EXECUTION_FORMAT")
        execution = {}
    if execution and execution.get("schema") != "pm04_single_shot_intents_v2":
        blockers.add("UNSUPPORTED_PENDING_OPPORTUNITY_FORMAT")
    history = execution.get("history", {})
    if not isinstance(history, dict):
        blockers.add("INVALID_PAPER_OPPORTUNITY_HISTORY")
        history = {}
    if any(
        isinstance(item, dict) and item.get("status") == "PENDING_5M" for item in history.values()
    ):
        blockers.add("PENDING_T300_ORIGINAL_K_NOT_PINNED")
    exits = execution.get("exits", {})
    if not isinstance(exits, dict):
        blockers.add("INVALID_PROTECTIVE_EXIT_HISTORY")
        exits = {}
    if any(
        isinstance(item, dict) and item.get("status") == "PENDING_EXIT" for item in exits.values()
    ):
        blockers.add("PROTECTIVE_EXIT_UNRESOLVED")
    if execution.get("unresolved_exposures"):
        blockers.add("FINANCIAL_EFFECT_UNRESOLVED")
    quantities = paper_snapshot.get("pm_quantities", {})
    if not isinstance(quantities, dict):
        blockers.add("INVALID_PAPER_INVENTORY")
    elif any(quantities.get(pod) for pod in candidate.pod_membership):
        blockers.add("OPEN_INVENTORY_NEEDS_EXPLICIT_LEGACY_K")
    if paper_snapshot.get("risk") != "GREEN" or paper_snapshot.get("breached"):
        blockers.add("PERSISTENT_PM03_RISK_RESTRICTION")
    at = clock(checked_at)
    if not at < clock(candidate.effective_at):
        blockers.add("EFFECTIVE_TIME_NOT_FUTURE")
    if clock(candidate.effective_at) - at < timedelta(minutes=5):
        blockers.add("T300_RELEASE_PREFLIGHT_LEAD_INSUFFICIENT")
    if at < clock(candidate.proposed_at):
        blockers.add("RELEASE_NOT_YET_PROPOSED")
    # Required provenance remains unavailable. Typed JSON and valid hashes are
    # not independent original event signatures or approved financial effects.
    blockers.add("INDEPENDENT_ORIGINAL_FINANCE_REPORT_PROOF_REQUIRED")
    blockers.add("RUNTIME_RELEASE_CONSUMER_NOT_VERSION_AWARE")
    return {
        "schema": "track_c_k_cutover_audit_v1",
        "candidate_sha256": candidate.identity_sha256,
        "paper_snapshot_sha256": paper_snapshot_sha256,
        "observed_release_sha256": observed_release_sha256,
        "status": "BLOCKED_NONACTIVATING",
        "blockers": sorted(blockers),
        "future_only": True,
        "legacy_k_t0_preservation_required": True,
        "active_policy_changed": False,
        "inventory_flattened": False,
        "catch_up_attempt_created": False,
        "paper_journal_mutated": False,
        "order_route": "NONE",
        "shadow_deployed": False,
        "trading_authorized": False,
    }


def publish_k_candidate(candidate: KReleaseCandidate, cache_root: Path) -> dict:
    """Separate immutable, unsigned SHADOW canary package. No installation."""
    KReleaseCandidate.model_validate_json(candidate.model_dump_json(by_alias=True))
    data = candidate.model_dump_json(by_alias=True).encode()
    artifact = ImmutableCache(
        cache_root, max_object_bytes=4 * 1024 * 1024, min_free_bytes=1024 * 1024
    ).publish(
        "track_c_k_candidate",
        {
            "candidate": candidate.identity_sha256,
            "previous_release": candidate.rollback_release_sha256,
            "portfolio": candidate.portfolio_definition_sha256,
        },
        version="track_c_k_release_candidate_v1",
        content=data,
    )
    return {
        "schema": "track_c_k_candidate_package_v1",
        "candidate_sha256": candidate.identity_sha256,
        "package_sha256": sha256(data).hexdigest(),
        "cache_key": artifact["key"],
        "cache_status": artifact["status"],
        "signature_verified": False,
        "shadow_deployed": False,
        "active_policy_changed": False,
        "order_route": "NONE",
        "trading_authorized": False,
    }


def read_only_cutover_cli(
    candidate_json: bytes,
    snapshot_json: bytes,
    policy_json: bytes,
    *,
    checked_at: str,
    observed_release_sha256: str,
) -> dict:
    """Pure bounded adapter for a separately authored preflight command."""
    if max(map(len, (candidate_json, snapshot_json, policy_json))) > 4 * 1024 * 1024:
        raise ValueError("OVERSIZED_K_PREFLIGHT_INPUT")
    candidate = KReleaseCandidate.model_validate_json(candidate_json)
    snap = json.loads(snapshot_json)
    policy = json.loads(policy_json)
    return verify_cutover(
        candidate,
        paper_snapshot=snap,
        paper_snapshot_sha256=digest(snap),
        current_policy=policy,
        checked_at=checked_at,
        observed_release_sha256=observed_release_sha256,
    )
