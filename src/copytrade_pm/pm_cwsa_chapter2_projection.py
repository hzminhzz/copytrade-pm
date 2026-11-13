"""Privacy-safe Chapter 2 evidence projection for the authenticated operator UI.

Only journal-replayed native modeled-paper facts can populate modeled finance.
No inferred zero P&L or mixing V4 results with broker trades.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from .pm_cwsa_six_paper import ALL_14_WALLETS, PORTFOLIO_CONFIGS

SCHEMA = "cwsa_chapter2_evidence_projection_v1"
COMPLETE_KINDS = frozenset({"BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE"})


def _source_scope_gaps(
    source: dict, members: list[str] | tuple[str, ...], at_ms: int
) -> tuple[list[str], bool]:
    """Conservative per-wallet complete book test; no inferred flat or backdated receipt."""
    latest = source.get("latest_checkpoint_ms")
    grace = source.get("policy_grace_ms")
    kinds = source.get("latest_kinds") or {}
    clocks = source.get("checkpoint_ms_by_wallet") or {}
    first_known = source.get("receipt_first_known_ms_by_wallet") or {}
    publication = source.get("published_ms_by_wallet") or {}
    complete = source.get("complete_position_proof_by_wallet") or {}
    heads = source.get("source_heads_by_wallet") or {}
    epochs = source.get("policy_epochs_by_wallet") or {}
    generations = source.get("scope_generations_by_wallet") or {}
    mixed = len({epochs.get(member) for member in members if epochs.get(member)}) > 1
    if (
        not isinstance(latest, int)
        or latest <= 0
        or not isinstance(grace, int)
        or grace < 0
        or not 0 <= at_ms - latest <= 900_000
        or source.get("source_count") != len(ALL_14_WALLETS)
        or not isinstance(source.get("head_sha256"), str)
        or len(source["head_sha256"]) != 64
    ):
        return sorted(members), mixed
    gaps = []
    for member in members:
        cp = clocks.get(member)
        known = first_known.get(member)
        published = publication.get(member)
        if (
            kinds.get(member) not in COMPLETE_KINDS
            or complete.get(member) is not True
            or not isinstance(cp, int)
            or cp < latest - grace
            or cp > latest
            or not isinstance(known, int)
            or known < cp
            or known > at_ms
            or not isinstance(published, int)
            or published < known
            or published > at_ms
            or not isinstance(heads.get(member), str)
            or len(heads[member]) != 64
            or not isinstance(epochs.get(member), str)
            or len(epochs[member]) != 64
            or not isinstance(generations.get(member), str)
            or len(generations[member]) != 64
        ):
            gaps.append(member)
    if mixed:
        gaps = list(members)
    return sorted(gaps), mixed


def project(
    *,
    source: dict,
    papers: dict[str, dict],
    verified_finance: set[str],
    qualified_k: set[str],
    release_sha: str,
    epoch: str,
    blockers: dict[str, list[str]] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one redacted view from independently verified source and paper facts."""
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None or not release_sha or not epoch:
        raise ValueError("CHAPTER2_PROJECTION_NO_LINEAGE")
    allowed = set(PORTFOLIO_CONFIGS)
    if not verified_finance <= allowed or not qualified_k <= allowed:
        raise ValueError("CHAPTER2_PROJECTION_UNRECOGNIZED_FINANCE")
    if set(papers) - allowed:
        raise ValueError("CHAPTER2_PROJECTION_UNRECOGNIZED_PORTFOLIO")
    if source.get("source_count") != len(ALL_14_WALLETS):
        raise ValueError("CHAPTER2_PROJECTION_SOURCE_ROSTER")
    kinds = source.get("latest_kinds", {})
    if not isinstance(kinds, dict) or set(kinds) - set(ALL_14_WALLETS):
        raise ValueError("CHAPTER2_PROJECTION_UNKNOWN_SOURCE")
    source_sha = source.get("head_sha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ValueError("CHAPTER2_PROJECTION_SOURCE_HEAD_UNVERIFIED")
    epochs = source.get("policy_epochs_by_wallet") or {}
    mixed_native = len({epochs.get(wallet) for wallet in ALL_14_WALLETS if epochs.get(wallet)}) > 1
    at_ms = int(now.timestamp() * 1000)
    output: dict[str, dict] = {}
    for pid, cfg in PORTFOLIO_CONFIGS.items():
        members = sorted(cfg["members"])
        current = papers.get(pid)
        complete = all(kinds.get(alias) in COMPLETE_KINDS for alias in members)
        source_gaps, mixed_scope = _source_scope_gaps(source, members, at_ms)
        source_ready = not source_gaps and not mixed_scope
        reasons = list((blockers or {}).get(pid, []))
        if not source_ready:
            reasons.append("SOURCE_COMPLETE_POSITION_OR_GENERATION_UNVERIFIED")
        if current is None:
            reasons.append("PM03_FINANCIAL_JOURNAL_NOT_REPLAYED")
        if not complete:
            reasons.append("CWSA_COVERAGE_INCOMPLETE")
        if pid not in qualified_k:
            reasons.append("UNQUALIFIED_K")
        if pid not in verified_finance:
            reasons.append("NOT_FINANCIALLY_ADMITTED")
        modeled = (
            current is not None
            and pid in verified_finance
            and pid in qualified_k
            and current.get("modeled_effects", 0) > 0
        )
        if pid in verified_finance and not modeled:
            reasons.append("NO_PROVEN_MODELED_FINANCIAL_EFFECT")
        output[pid] = {
            "portfolio_id": pid,
            "members": members,
            "source_coverage_complete": complete,
            "new_risk_source_status": (
                "SOURCE_SCOPE_READY" if source_ready else "BLOCKED_EVIDENCE"
            ),
            "missing_or_stale_source_proofs": source_gaps,
            "shared_account_risk": "UNKNOWN",
            "source_heads_by_wallet": {
                member: (source.get("source_heads_by_wallet") or {}).get(member)
                for member in members
            },
            "source_policy_epochs_by_wallet": {member: epochs.get(member) for member in members},
            "receipt_first_known_ms_by_wallet": {
                member: (source.get("receipt_first_known_ms_by_wallet") or {}).get(member)
                for member in members
            },
            "original_checkpoint_by_wallet_ms": {
                member: (source.get("checkpoint_ms_by_wallet") or {}).get(member)
                for member in members
            },
            "missing_sources": [
                alias for alias in members if kinds.get(alias) not in COMPLETE_KINDS
            ],
            "source_checkpoint_ms": source.get("latest_checkpoint_ms", 0),
            "paper_wave_checkpoint_ms": current.get("wave_checkpoint_ms") if current else None,
            "paper_wave_count": current.get("wave_count") if current else None,
            "financial_journal_head_sha": current.get("journal_head_sha") if current else None,
            "financial_cursor": current.get("cursor") if current else None,
            "frozen_k_qualified": pid in qualified_k,
            "financial_admission": "PROSPECTIVE_MODELED_PAPER" if modeled else "BLOCKED_EVIDENCE",
            "model_financial_basis": "CWSA_5M_PROSPECTIVE" if modeled else None,
            "positions_count": current.get("positions_count") if modeled else None,
            "realized_pnl_usd": current.get("realized_pnl") if modeled else None,
            "total_costs_usd": current.get("costs") if modeled else None,
            "current_equity_usd": current.get("current_equity") if modeled else None,
            "drawdown_usd": current.get("drawdown") if modeled else None,
            "blockers": sorted(set(reasons)),
            "broker_orders": None,
            "trading_authorized": False,
        }
    return {
        "schema": SCHEMA,
        "generated_at": now.astimezone(UTC).isoformat(),
        "assessment_asof": now.astimezone(UTC).isoformat(),
        "snapshot_coherence": "MIXED" if mixed_native else "UNVERIFIED",
        "coherence_reasons": (["MIXED_SOURCE_POLICY_EPOCHS"] if mixed_native else [])
        + ["INDEPENDENT_RELEASE_QUOTE_MANDATE_GUARDIAN_NOT_ATOMICALLY_BOUND"],
        "owner_heads": {
            "source": {
                "head_sha256": source_sha,
                "policy_epochs_by_wallet": epochs,
                "scope_generations_by_wallet": source.get("scope_generations_by_wallet"),
            },
            "release": {"code_sha": release_sha, "financial_epoch": epoch},
            "independent_quote": None,
            "mandate": None,
            "paper_finance": {
                pid: {
                    "journal_head_sha": paper.get("journal_head_sha"),
                    "wave_head_sha": paper.get("wave_head_sha"),
                }
                for pid, paper in papers.items()
            },
        },
        "source_heads_sha256": source_sha,
        "source_latest_checkpoint_ms": source.get("latest_checkpoint_ms", 0),
        "source_wallet_count": len(ALL_14_WALLETS),
        "source_latest_observed_wallets": len(kinds),
        "release_sha": release_sha,
        "financial_epoch": epoch,
        "portfolios": output,
        "historical_v4": None,
        "native_broker": None,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


PRIOR_SNAPSHOT_MAX_BYTES = 1_000_000


def _read_prior_snapshot(path: Path, *, portfolio: str, inspection: str) -> dict:
    """Read a caller-selected small prior projection; never access a global state store."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > PRIOR_SNAPSHOT_MAX_BYTES:
        raise OSError("PRIOR_SNAPSHOT_UNAVAILABLE")
    with path.open("rb") as handle:
        raw = handle.read(PRIOR_SNAPSHOT_MAX_BYTES + 1)
    if len(raw) > PRIOR_SNAPSHOT_MAX_BYTES:
        raise OSError("PRIOR_SNAPSHOT_UNAVAILABLE")
    try:
        prior = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PRIOR_SNAPSHOT_INVALID") from exc
    if not isinstance(prior, dict) or prior.get("schema") != "cwsa_chapter2_task_explanation_v1":
        raise ValueError("PRIOR_SNAPSHOT_INVALID")
    scope = prior.get("scope")
    if (
        not isinstance(scope, dict)
        or scope.get("portfolio") != portfolio
        or scope.get("inspection") != inspection
        or scope.get("operation") != "EXPLAIN_CHAPTER2_PORTFOLIO"
    ):
        raise ValueError("PRIOR_SNAPSHOT_SCOPE_MISMATCH")
    dimensions = prior.get("dimensions")
    if (
        not isinstance(dimensions, dict)
        or len(dimensions) > 32
        or any(
            not isinstance(name, str)
            or not isinstance(dim, dict)
            or not isinstance(dim.get("state"), str)
            or (dim.get("evidence") is not None and not isinstance(dim.get("evidence"), dict))
            for name, dim in dimensions.items()
        )
    ):
        raise ValueError("PRIOR_SNAPSHOT_INVALID")
    return prior


def _stable_evidence(value: Any) -> Any:
    """Exclude derived query-age and display clocks from causal evidence identity."""
    if isinstance(value, dict):
        return {
            key: _stable_evidence(val)
            for key, val in value.items()
            if key not in ("latest_age_ms", "observed_at", "generated_at", "checked_at")
        }
    if isinstance(value, list):
        return [_stable_evidence(item) for item in value]
    return value


def _prior_delta(prior: dict, current: dict) -> dict:
    """Compare the selected owner claims, not a mutable heartbeat or global source clock."""
    old = prior["dimensions"]
    new = current["dimensions"]
    names = set(old) | set(new)
    old_source = (old.get("source_observation") or {}).get("evidence") or {}
    new_source = (new.get("source_observation") or {}).get("evidence") or {}
    members = (
        ((new.get("portfolio_seal") or {}).get("evidence") or {}).get("members")
        or ((old.get("portfolio_seal") or {}).get("evidence") or {}).get("members")
        or []
    )
    wallet_fields = (
        "original_checkpoint_by_wallet_ms",
        "published_ms_by_wallet",
        "receipt_first_known_ms_by_wallet",
        "latest_kinds",
        "complete_position_proof_by_wallet",
        "source_heads_by_wallet",
        "policy_epochs_by_wallet",
        "scope_generations_by_wallet",
    )
    changed_wallets = sorted(
        member
        for member in members
        if any(
            (old_source.get(field) or {}).get(member) != (new_source.get(field) or {}).get(member)
            for field in wallet_fields
        )
    )
    changes: set[str] = set()
    for name in names - {"source_observation"}:
        if name == "paper_finance":
            # A source/quote staleness flip cannot rewrite the original
            # independently replayed PM03 journal.
            old_paper = (old.get(name) or {}).get("evidence")
            new_paper = (new.get(name) or {}).get("evidence")
            if _stable_evidence(old_paper) != _stable_evidence(new_paper):
                changes.add(name)
        elif _stable_evidence(old.get(name)) != _stable_evidence(new.get(name)):
            changes.add(name)
    if changed_wallets or (old.get("source_observation") or {}).get("state") != (
        new.get("source_observation") or {}
    ).get("state"):
        changes.add("source_observation")
    old_scope = prior.get("scope") or {}
    new_scope = current.get("scope") or {}
    if old_scope.get("epoch") != new_scope.get("epoch"):
        changes.update(("mandate", "paper_finance"))
    if old_scope.get("version") != new_scope.get("version"):
        changes.add("portfolio_seal")
    invalidates = {
        "registry_integrity": {"portfolio_seal", "prospective_new_risk"},
        "portfolio_seal": {"portfolio_seal", "source_observation", "prospective_new_risk"},
        "source_observation": {"source_observation", "prospective_new_risk"},
        "mandate": {"mandate", "prospective_new_risk"},
        "independent_executable_quotes": {"independent_executable_quotes", "prospective_new_risk"},
        "paper_finance": {"paper_finance"},
        "risk": {"prospective_new_risk"},
        "guardian_authorization": {"prospective_new_risk"},
        "research_selection_proof": {"research_selection_proof"},
    }
    invalidated = sorted({claim for name in changes for claim in invalidates.get(name, {name})})
    return {
        "schema": "cwsa_chapter2_causal_delta_v1",
        "prior_assessment_asof": prior.get("assessment_asof", prior.get("observed_at")),
        "current_assessment_asof": current["assessment_asof"],
        "changed_scoped_dimensions": sorted(changes),
        "changed_wallets": changed_wallets,
        "global_source_head_changed": (
            old_source.get("head_sha256") != new_source.get("head_sha256")
        ),
        "invalidated_conclusions": invalidated,
        "prior_states_of_invalidated_dimensions": {
            name: (old.get(name) or {}).get("state") for name in changes if name in old
        },
        "comparison_limitation": (
            "Caller-supplied prior snapshot is not independently authenticated; "
            "original owner claims only, snapshots are not atomic, and no old permission is renewed"
        ),
    }


def explain_native_guardian_intent(
    *, journal_path, intent_id: str, observed_at_ms: int
) -> dict[str, Any]:
    """Read original Guardian's verified journal using its own read-only API.

    Optional companion integration: no new Guardian parser, transaction, retry,
    broker command or synthetic trust fallback exists here. A verified journal
    terminal is distinct from a coherent *current* broker account snapshot.
    """
    from pathlib import Path

    if (
        not isinstance(intent_id, str)
        or len(intent_id) != 64
        or any(c not in "0123456789abcdef" for c in intent_id)
        or type(observed_at_ms) is not int
        or observed_at_ms < 0
    ):
        raise ValueError("INVALID_GUARDIAN_INTENT_QUERY")
    result = {
        "schema": "cwsa_chapter2_guardian_recovery_v1",
        "owner": "PROP_PRODUCTION_GUARDIAN",
        "intent_id": intent_id,
        "observed_at_ms": observed_at_ms,
        "dispatch_state": "EVIDENCE_UNAVAILABLE",
        "original_status": None,
        "journal_sequence": None,
        "release_sha": None,
        "original_deadline_ms": None,
        "reservation_id": None,
        "reservation_active": None,
        "reservation": None,
        "halt_reasons": None,
        "risk_floors": None,
        "broker_certainty": "UNKNOWN",
        "mandate_generation": None,
        "next_operation": "prop-production intent --journal PATH --intent-id ID",
        "next_operation_effect_class": "READ_ONLY",
        "next_action": "READ_ORIGINAL_GUARDIAN_EVIDENCE",
        "unrelated_read_only_work_allowed": True,
        "original_obligation_preserved": True,
        "retry_authorized": False,
        "order_route": "NONE",
        "trading_authorized": False,
        "limitations": [
            "Only prop-production can verify its original journal and broker outcomes",
            "Original signed Copy Mandate generation is not present in Guardian intent v1",
            "Read-only projection never grants new risk, retries, or HALT clearance",
        ],
    }
    try:
        # Import the optional protected owner only when explicitly requested.
        from prop_production.journal import Journal
        from prop_production.operator import project_state

        state = Journal.read(Path(journal_path))
        intent = project_state(state, "intent", observed_at_ms, intent_id=intent_id)
        risk = project_state(state, "risk", observed_at_ms)
        broker = project_state(state, "broker", observed_at_ms)
    except ImportError, OSError, ValueError, RuntimeError, KeyError, TypeError:
        return result  # No downgrade to unverified local JSON or status files.
    if (
        state.get("schema") != "guardian_journal_v1"
        or intent.get("schema") != "operator_intent_v1"
        or risk.get("schema") != "operator_risk_v1"
        or broker.get("schema") != "operator_broker_v1"
        or any(
            view.get("journal_sequence") != state.get("sequence")
            or view.get("release_sha") != state.get("active_release_sha")
            or view.get("account_binding_sha") != intent.get("account_binding_sha")
            for view in (intent, risk, broker)
        )
        or len(intent.get("intents", [])) != 1
        or intent["intents"][0].get("intent_id") != intent_id
    ):
        return result
    original = intent["intents"][0]
    status = original.get("status")
    if status == "QUEUED" and original.get("sent_at_ms") is None:
        dispatch_state = "NOT_DISPATCHED"
        action = "PRESERVE_QUEUED_INTENT_AND_RECHECK_OWNER_DEADLINE"
    elif status in {
        "DISPATCHING",
        "UNKNOWN",
        "ACKNOWLEDGED",
        "CANCEL_PENDING",
        "REJECT_PENDING_PROOF",
    }:
        dispatch_state = "POSSIBLY_DISPATCHED"
        action = "RECONCILE_ORIGINAL_INTENT_WITH_GUARDIAN"
    elif status == "FILLED":
        dispatch_state = "VERIFIED_COMPLETED"
        action = "REVIEW_VERIFIED_ORIGINAL_POSTCONDITION"
    elif status in {"REJECTED", "NOT_ACCEPTED", "REVOKED", "EXPIRED", "CANCELLED"}:
        dispatch_state = "VERIFIED_REJECTED"
        action = "NO_NEW_EFFECT_ON_ORIGINAL_INTENT"
    else:
        return result
    reservation_id = original.get("reservation_id")
    reserved = risk.get("reservations", {}).get(reservation_id)
    floors = risk.get("finance", {})
    result.update(
        dispatch_state=dispatch_state,
        original_status=status,
        journal_sequence=state["sequence"],
        release_sha=intent.get("release_sha"),
        original_deadline_ms=original.get("expires_at_ms"),
        reservation_id=reservation_id,
        reservation_active=reserved is not None,
        reservation={k: reserved.get(k) for k in ("loss", "margin", "cost")}
        if isinstance(reserved, dict)
        else None,
        halt_reasons=risk.get("halts"),
        risk_floors={
            k: floors.get(k)
            for k in ("risk_floor", "daily_floor", "trailing_floor", "internal_floor")
        }
        if isinstance(floors, dict)
        else None,
        broker_certainty=broker.get("certainty", "UNKNOWN"),
        next_operation="prop-production broker --journal PATH",
        next_action=action,
    )
    return result


def explain_interrupted_paper(opportunity, *, observed_at: str) -> dict[str, Any]:
    """Interpret the original PM04 virtual-paper opportunity without broker claims.

    The PM04 record is authoritative only for a *modeled* attempt. An attempted
    result (including a modeled REJECTED) cannot establish native broker finality.
    Neither missing status files nor a future policy permits a fresh intent.
    """
    from .pm_paper_contracts import PaperOpportunity
    from .pm_source_contracts import utc_clock

    utc_clock(observed_at)
    original = PaperOpportunity.model_validate(opportunity) if opportunity is not None else None
    if original is None:
        state = "EVIDENCE_UNAVAILABLE"
        next_action = "READ_ORIGINAL_OWNER_EVIDENCE"
    elif original.attempted_at is not None or original.order_ids:
        state = "POSSIBLY_DISPATCHED"
        next_action = "RECONCILE_ORIGINAL_INTENT_WITH_GUARDIAN"
    else:
        state = "NOT_DISPATCHED"
        next_action = (
            "NO_NEW_EFFECT_ON_ORIGINAL_OPPORTUNITY"
            if original.status != "PENDING_5M" or original.eligibility(observed_at) == "EXPIRED"
            else "READ_ORIGINAL_PM04_OPPORTUNITY_AND_CHECK_DEADLINE"
        )
    return {
        "schema": "cwsa_chapter2_interrupted_paper_explanation_v1",
        "owner": "PM04_VIRTUAL_PAPER_ONLY",
        "observed_at": observed_at,
        "dispatch_state": state,
        "original_status": original.status if original else None,
        "intent_id": original.intent_id if original else None,
        "source_sha": original.source_sha if original else None,
        "first_known_at": original.first_known_at if original else None,
        "deadline_at": original.deadline_at if original else None,
        "frozen_k": original.frozen_k if original else None,
        "original_release_sha256": original.release_sha256 if original else None,
        "mandate_generation": None,  # PM04 opportunity is not a signed Copy Mandate.
        "reservation": None,  # Not provided by this owner's opportunity contract.
        "halt": "UNKNOWN",  # Only the financial owner can establish its latch.
        "guardian_authority": "UNKNOWN",
        "broker_completion": "UNKNOWN",
        "next_action": next_action,
        "next_operation_effect_class": "READ_ONLY",
        "original_obligation_preserved": True,
        "unrelated_read_only_work_allowed": True,
        "retry_authorized": False,
        "order_route": "NONE",
        "trading_authorized": False,
        "limitations": [
            "Native PM04 modeled status is not independently verified broker execution",
            "A missing Guardian receipt cannot mean rejection or a free retry",
            "Original signed generation, reservations, exposure and HALT belong to their owners",
        ],
    }


def explain_task(args) -> dict[str, Any]:
    """Read one portfolio's native owner proofs; never decide Guardian permission.

    Metadata mode must not open source, quote or financial journals.
    Evidence mode is explicitly requested and reads only one PM03 paper journal.
    """
    from . import pm_operations
    from . import pm_cwsa_chapter2_gate as gate
    from .pm_cwsa_six_paper import PORTFOLIO_CONFIGS, load_registry_seals

    now = datetime.now(UTC)
    pid = args.portfolio
    inspection = args.inspection
    output: dict[str, Any] = {
        "schema": "cwsa_chapter2_task_explanation_v1",
        "observed_at": now.isoformat(),
        "assessment_asof": now.isoformat(),
        "scope": {
            "operation": "EXPLAIN_CHAPTER2_PORTFOLIO",
            "portfolio": pid,
            "inspection": inspection,
            "epoch": args.epoch,
            "version": None,
            "selection_known_at": None,
            "new_risk_source_status": "NOT_INSPECTED",
        },
        "dimensions": {},
        "blockers": [],
        "economics": {
            "realized_pnl_usd": None,
            "total_costs_usd": None,
            "current_equity_usd": None,
            "drawdown_usd": None,
        },
        "limits": {
            "requested_portfolios": 1,
            "financial_journals_opened": 0,
            "source_journals_opened": 0,
            "quote_journals_opened": 0,
            "prior_snapshot_files_opened": 0,
            "prior_snapshot_max_bytes": PRIOR_SNAPSHOT_MAX_BYTES,
            "scope": "CHAPTER2_SINGLE_PORTFOLIO",
        },
        "next_operation": None,
        "owner_heads": {},
        "generation_consistency": {"state": "UNVERIFIED", "reasons": []},
        "fault_isolation": {
            "affected_portfolios": [],
            "unaffected_source_portfolios": [],
            "shared_account_risk": {"owner": "prop-production Guardian", "state": "UNKNOWN"},
        },
        "prior_to_current": None,
        "order_route": "NONE",
        "trading_authorized": False,
        "scientifically_qualified": False,
        "financially_active": False,
        "limitations": [
            "Independently timed owner reads are not an atomic global snapshot",
            "Fixture evidence proves fixture behavior, not provider execution",
            "Guardian account-bound risk and authorization remain external and unverified",
        ],
    }
    if pid not in PORTFOLIO_CONFIGS:
        output["error_code"] = "UNKNOWN_CHAPTER2_PORTFOLIO"
        return output

    prior = None
    if args.prior_snapshot is not None:
        try:
            prior = _read_prior_snapshot(args.prior_snapshot, portfolio=pid, inspection=inspection)
            output["limits"]["prior_snapshot_files_opened"] = 1
        except OSError:
            output["error_code"] = "PRIOR_SNAPSHOT_UNAVAILABLE"
            return output
        except ValueError as exc:
            output["error_code"] = str(exc)
            return output

    dimensions = output["dimensions"]
    blockers = output["blockers"]

    def dimension(name: str, state: str, owner: str, *, evidence: dict | None = None) -> None:
        dimensions[name] = {"state": state, "owner": owner, "evidence": evidence}

    def blocked(reason: str, owner: str, *, scope: str | None = None) -> None:
        blockers.append({"reason_code": reason, "owner": owner, "affected_portfolio": scope or pid})

    def finish() -> dict[str, Any]:
        owner = dimensions
        registry = (owner.get("registry_integrity") or {}).get("evidence") or {}
        seal_evidence = (owner.get("portfolio_seal") or {}).get("evidence") or {}
        source = (owner.get("source_observation") or {}).get("evidence") or {}
        quote = (owner.get("independent_executable_quotes") or {}).get("evidence") or {}
        paper = (owner.get("paper_finance") or {}).get("evidence") or {}
        mandate = (owner.get("mandate") or {}).get("evidence") or {}
        members = seal_evidence.get("members") or []
        epochs = source.get("policy_epochs_by_wallet") or {}
        selected_epochs = [epochs.get(member) for member in members]
        global_epochs = source.get("global_policy_epoch_set") or []
        mixed = (
            len({epoch for epoch in selected_epochs if epoch is not None}) > 1
            or len(global_epochs) > 1
        )
        reasons = []
        if mixed:
            reasons.append("SOURCE_POLICY_EPOCHS_MIXED")
        if (
            not members
            or len(selected_epochs) != len(members)
            or any(epoch is None for epoch in selected_epochs)
        ):
            reasons.append("SOURCE_POLICY_EPOCH_UNVERIFIED")
        if (owner.get("mandate") or {}).get("state") != "VERIFIED":
            reasons.append("SIGNED_MANDATE_UNVERIFIED")
        if (owner.get("independent_executable_quotes") or {}).get("state") != "VERIFIED":
            reasons.append("INDEPENDENT_QUOTE_UNVERIFIED")
        reasons.append("NONATOMIC_OWNER_SNAPSHOTS_AND_GUARDIAN_UNVERIFIED")
        output["generation_consistency"] = {
            "state": "MIXED" if mixed else "UNVERIFIED",
            "reasons": reasons,
        }
        output["scope"]["new_risk_source_status"] = (
            "SOURCE_SCOPE_READY"
            if (owner.get("source_observation") or {}).get("state") == "OBSERVE_READY"
            else "NOT_INSPECTED"
            if inspection == "metadata"
            else "BLOCKED_EVIDENCE"
        )
        output["owner_heads"] = {
            "registry": {"inventory_sha256": registry.get("inventory_sha256")},
            "portfolio_seal": {
                "version": seal_evidence.get("version"),
                "definition_sha256": seal_evidence.get("definition_sha256"),
                "selection_known_at": seal_evidence.get("selection_known_at"),
            },
            "source": {
                "head_sha256": source.get("head_sha256"),
                "source_heads_by_wallet": source.get("source_heads_by_wallet"),
                "policy_epochs_by_wallet": source.get("policy_epochs_by_wallet"),
                "global_policy_epoch_set": source.get("global_policy_epoch_set"),
                "scope_generations_by_wallet": source.get("scope_generations_by_wallet"),
                "original_checkpoint_by_wallet_ms": source.get("original_checkpoint_by_wallet_ms"),
                "receipt_first_known_ms_by_wallet": source.get("receipt_first_known_ms_by_wallet"),
                "published_ms_by_wallet": source.get("published_ms_by_wallet"),
            },
            "mandate": {
                "bundle_sha256": mandate.get("bundle_sha256"),
                "epoch": mandate.get("epoch"),
            },
            "quote": {"quote_heads_sha256": (quote.get("native") or {}).get("quote_heads_sha256")},
            "paper_finance": {
                "journal_head_sha": paper.get("journal_head_sha"),
                "wave_head_sha": paper.get("wave_head_sha"),
                "financial_cursor": paper.get("financial_cursor"),
            },
            "guardian": None,
        }
        if prior is not None:
            output["prior_to_current"] = _prior_delta(prior, output)
        return output

    doctor = pm_operations._doctor(args.registry_db)
    info = doctor.get("data") or {}
    integrity = info.get("database_integrity")
    dimension(
        "registry_integrity",
        "VERIFIED"
        if pm_operations._sqlite_integrity_verified(doctor)
        else "UNKNOWN"
        if integrity is None
        else "BLOCKED_EVIDENCE",
        "wallet_registry",
        evidence={
            "inventory_sha256": info.get("inventory_sha256"),
            "database_integrity": integrity,
        },
    )
    selection = info.get("research_selection_integrity")
    dimension(
        "research_selection_proof",
        "BLOCKED"
        if selection == "BLOCKED_MISSING_EXTERNAL_PROOF"
        else "VERIFIED"
        if doctor["status"] == "VERIFIED"
        else "UNKNOWN",
        "wallet_registry",
        evidence={"research_selection_integrity": selection},
    )
    if dimensions["registry_integrity"]["state"] != "VERIFIED":
        blocked("REGISTRY_SQLITE_INTEGRITY_UNVERIFIED", "wallet_registry")
    try:
        if dimensions["registry_integrity"]["state"] != "VERIFIED":
            raise ValueError("REGISTRY_INTEGRITY_NOT_VERIFIED")
        seal = load_registry_seals(args.registry_db, portfolios=(pid,))[pid]
        output["scope"]["version"] = seal.get("version")
        output["scope"]["selection_known_at"] = seal.get("selection_known_at")
        dimension(
            "portfolio_seal",
            "VERIFIED",
            "wallet_registry",
            evidence={
                "portfolio_id": pid,
                "version": seal.get("version"),
                "definition_sha256": seal.get("definition_sha256"),
                "selection_known_at": seal.get("selection_known_at"),
                "members": list(seal["members"]),
            },
        )
    except ValueError, OSError, KeyError, TypeError:
        dimension("portfolio_seal", "BLOCKED_EVIDENCE", "wallet_registry")
        blocked("PORTFOLIO_SQLITE_SEAL_UNAVAILABLE", "wallet_registry")
        seal = None

    for name, owner in (
        ("source_observation", "pm_cwsa_chapter2_gate"),
        ("mandate", "pm_cwsa_chapter2_release"),
        ("independent_executable_quotes", "pm_cwsa_chapter2_gate"),
        ("paper_finance", "pm03_account"),
    ):
        dimension(name, "NOT_INSPECTED", owner)
    for name in ("risk", "guardian_authorization"):
        dimension(name, "UNKNOWN", "prop-production Guardian")
    blocked("GUARDIAN_ACCOUNT_AUTHORIZATION_UNAVAILABLE", "prop-production Guardian")
    blocked("INDEPENDENT_ACCOUNT_RISK_UNAVAILABLE", "prop-production Guardian")

    output["next_operation"] = {
        "id": "operations.cwsa.chapter2.explain"
        if inspection == "metadata"
        else "operations.cwsa.chapter2.verify",
        "effect_class": "READ_ONLY",
        "auto_dispatched": False,
        "required_arguments": ["--portfolio " + pid, "--inspection evidence"]
        if inspection == "metadata"
        else ["--stage postdeploy"],
        "owner": "copytrade_pm.pm_cwsa_chapter2_projection"
        if inspection == "metadata"
        else "copytrade_pm.pm_cwsa_chapter2_gate",
    }
    if inspection == "metadata" or seal is None:
        return finish()

    try:
        output["limits"]["source_journals_opened"] = 1
        source = gate._source_facts(args.source_db)
        members = seal["members"]
        kinds = source.get("latest_kinds", {})
        per_wallet = source.get("checkpoint_ms_by_wallet", {})
        latest = source.get("latest_checkpoint_ms", 0)
        grace = source.get("policy_grace_ms", 0)
        # Native source owner must attest every requested wallet at this
        # checkpoint; a newer unrelated wallet cannot freshen an older member.
        first_known = source.get("receipt_first_known_ms_by_wallet") or {}
        publication = source.get("published_ms_by_wallet") or {}
        complete = source.get("complete_position_proof_by_wallet") or {}
        heads = source.get("source_heads_by_wallet") or {}
        epochs = source.get("policy_epochs_by_wallet") or {}
        generations = source.get("scope_generations_by_wallet") or {}
        at_ms = int(now.timestamp() * 1000)
        stale, mixed_epochs = _source_scope_gaps(source, members, at_ms)
        native = source.get("head_sha256")
        valid = (
            isinstance(native, str)
            and len(native) == 64
            and source.get("source_count") == len(gate.EXPECTED_WALLETS)
        )
        freshness_ms = at_ms - latest
        state = "OBSERVE_READY" if valid and not stale else "BLOCKED_EVIDENCE"
        dimension(
            "source_observation",
            state,
            "pm_cwsa_chapter2_gate",
            evidence={
                "head_sha256": native,
                "original_checkpoint_ms": latest,
                "original_checkpoint_by_wallet_ms": {
                    member: per_wallet.get(member) for member in members
                },
                "published_ms_by_wallet": {member: publication.get(member) for member in members},
                "receipt_first_known_ms_by_wallet": {
                    member: first_known.get(member) for member in members
                },
                "complete_position_proof_by_wallet": {
                    member: complete.get(member) for member in members
                },
                "source_heads_by_wallet": {member: heads.get(member) for member in members},
                "policy_epochs_by_wallet": {member: epochs.get(member) for member in members},
                "global_policy_epoch_set": sorted(set(epochs.values())),
                "scope_generations_by_wallet": {
                    member: generations.get(member) for member in members
                },
                "latest_kinds": {member: kinds.get(member) for member in members},
                "policy_grace_ms": grace,
                "latest_age_ms": freshness_ms,
            },
        )
        dimensions["source_observation"]["missing_or_stale_members"] = stale
        # One wallet gap can affect more than one portfolio, but does not
        # cross-contaminate independent source scopes or shared-account risk.
        faulted_wallets = {
            member
            for member in gate.EXPECTED_WALLETS
            if _source_scope_gaps(source, (member,), at_ms)[0]
        }
        affected = {
            portfolio_id
            for portfolio_id, cfg in PORTFOLIO_CONFIGS.items()
            if set(cfg["members"]) & faulted_wallets
            or _source_scope_gaps(source, cfg["members"], at_ms)[1]
        }
        output["fault_isolation"].update(
            affected_portfolios=sorted(affected),
            unaffected_source_portfolios=sorted(set(PORTFOLIO_CONFIGS) - affected),
        )
        if state != "OBSERVE_READY":
            blocked("SOURCE_PORTFOLIO_CHECKPOINT_INCOMPLETE_OR_STALE", "pm_checkpoint_journal")
    except ValueError, OSError, KeyError, TypeError, RuntimeError, sqlite3.Error:
        dimension("source_observation", "UNKNOWN", "pm_cwsa_chapter2_gate")
        blocked("SOURCE_OWNER_EVIDENCE_UNAVAILABLE", "pm_checkpoint_journal")

    signed_args = (
        args.approved_paper_bundle,
        args.approved_paper_sha256,
        args.trusted_paper_public_key,
        args.qualification,
        args.research_public_key,
    )
    approved = False
    if not all(signed_args):
        dimension("mandate", "BLOCKED_EVIDENCE", "pm_cwsa_chapter2_release")
        blocked("SIGNED_PAPER_BUNDLE_AND_TRUST_ROOT_REQUIRED", "pm_cwsa_chapter2_release")
    else:
        try:
            from .pm_cwsa_chapter2_release import read_activation_bundle
            from .pm_cwsa_paper_qualification import read_qualification, mandate_k_blockers

            # Signed release and research qualification are global original
            # envelopes. Validate against all sealed members, then select pid.
            all_seals = load_registry_seals(args.registry_db)
            research = read_qualification(
                args.qualification,
                args.research_public_key,
                all_seals,
                args.source_db,
            )
            paper_release = read_activation_bundle(
                path=args.approved_paper_bundle,
                expected_sha256=args.approved_paper_sha256,
                trusted_authority_hex=args.trusted_paper_public_key,
                seals=all_seals,
                configs=PORTFOLIO_CONFIGS,
                run_label=args.epoch,
                source_db=args.source_db,
            )
            if pid not in paper_release or mandate_k_blockers(paper_release, research):
                raise ValueError("SIGNED_PAPER_MANDATE_INVALID")
            approved = True
            dimension(
                "mandate",
                "VERIFIED",
                "pm_cwsa_chapter2_release",
                evidence={
                    "epoch": args.epoch,
                    "portfolio": pid,
                    "bundle_sha256": args.approved_paper_sha256,
                },
            )
        except ValueError, OSError, KeyError, TypeError:
            dimension("mandate", "BLOCKED_EVIDENCE", "pm_cwsa_chapter2_release")
            blocked("SIGNED_PAPER_MANDATE_UNVERIFIED", "pm_cwsa_chapter2_release")

    if args.quote_db is None:
        dimension("independent_executable_quotes", "BLOCKED_EVIDENCE", "pm_cwsa_chapter2_gate")
        blocked("PINNED_INDEPENDENT_L2_QUOTE_JOURNAL_REQUIRED", "pm_cwsa_chapter2_gate")
    else:
        output["limits"]["quote_journals_opened"] = 1
        quote = gate._market_evidence(args.quote_db, args.source_db)
        dimension(
            "independent_executable_quotes",
            "VERIFIED" if quote.state == "PASS" else quote.state,
            "pm_cwsa_chapter2_gate",
            evidence={"reason": quote.detail, "native": quote.evidence},
        )
        if quote.state != "PASS":
            blocked(quote.detail, "pm_cwsa_chapter2_gate")

    try:
        output["limits"]["financial_journals_opened"] = 1
        paper = gate._paper_facts(args.paper_root, portfolios=(pid,))[pid]
        effects = paper.get("modeled_effects", 0)
        verified = (
            approved
            and dimensions["source_observation"]["state"] == "OBSERVE_READY"
            and dimensions["independent_executable_quotes"]["state"] == "VERIFIED"
            and paper.get("signed_mandates") == len(seal["members"])
            and isinstance(effects, int)
            and effects > 0
            and isinstance(paper.get("cursor"), int)
            and paper["cursor"] > 0
        )
        dimension(
            "paper_finance",
            "PROSPECTIVE_MODELED_PAPER" if verified else "BLOCKED_EVIDENCE",
            "pm03_account",
            evidence={
                "journal_head_sha": paper.get("journal_head_sha"),
                "wave_head_sha": paper.get("wave_head_sha"),
                "financial_cursor": paper.get("cursor"),
                "modeled_effects": effects,
                "wave_checkpoint_ms": paper.get("wave_checkpoint_ms"),
                "signed_mandates": paper.get("signed_mandates"),
            },
        )
        if verified:
            output["economics"]["realized_pnl_usd"] = paper.get("realized_pnl")
            output["economics"]["total_costs_usd"] = paper.get("costs")
            output["economics"]["current_equity_usd"] = paper.get("current_equity")
        else:
            blocked("NO_PROVEN_MODELED_FINANCIAL_EFFECT", "pm03_account")
    except ValueError, OSError, KeyError, TypeError:
        dimension("paper_finance", "UNKNOWN", "pm03_account")
        blocked("PM03_OWNER_JOURNAL_UNAVAILABLE", "pm03_account")

    return finish()


def build_runtime_projection(args) -> dict[str, Any]:
    """Read-only native source and PM03 replay; never use projected JSON as finance."""
    from .pm_cwsa_chapter2_gate import (
        _paper_facts,
        _source_facts,
        assess_portfolio_roster,
    )
    from .pm_cwsa_chapter2_release import read_activation_bundle
    from .pm_cwsa_paper_qualification import (
        read_qualification,
        mandate_k_blockers,
    )
    from .pm_cwsa_six_paper import load_registry_seals

    seals = load_registry_seals(args.registry_db)
    roster = assess_portfolio_roster({pid: set(seal["members"]) for pid, seal in seals.items()})
    if roster.state != "PASS":
        raise ValueError("CHAPTER2_PROJECTION_REGISTRY_SEALS_DRIFT")
    source = _source_facts(args.source_db)
    papers = _paper_facts(args.paper_root)
    qualified_k: set[str] = set()
    verified_finance: set[str] = set()
    if any(
        (
            args.approved_paper_bundle,
            args.approved_paper_sha256,
            args.trusted_paper_public_key,
            args.qualification,
            args.research_public_key,
        )
    ):
        if not all(
            (
                args.approved_paper_bundle,
                args.approved_paper_sha256,
                args.trusted_paper_public_key,
                args.qualification,
                args.research_public_key,
            )
        ):
            raise ValueError("CHAPTER2_PROJECTION_INCOMPLETE_SIGNED_RELEASE")
        research = read_qualification(
            args.qualification,
            args.research_public_key,
            seals,
            args.source_db,
        )
        approved = read_activation_bundle(
            path=args.approved_paper_bundle,
            expected_sha256=args.approved_paper_sha256,
            trusted_authority_hex=args.trusted_paper_public_key,
            seals=seals,
            configs=PORTFOLIO_CONFIGS,
            run_label=args.epoch,
            source_db=args.source_db,
        )
        if mandate_k_blockers(approved, research):
            raise ValueError("CHAPTER2_PROJECTION_MANDATE_K_DRIFT")
        qualified_k = set(approved)
        verified_finance = {
            pid
            for pid in approved
            if papers[pid]["signed_mandates"] == len(PORTFOLIO_CONFIGS[pid]["members"])
        }
    return project(
        source=source,
        papers=papers,
        verified_finance=verified_finance,
        qualified_k=qualified_k,
        release_sha=args.release_sha,
        epoch=args.epoch,
    )
