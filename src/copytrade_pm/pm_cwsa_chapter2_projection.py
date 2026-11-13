"""Privacy-safe Chapter 2 evidence projection for the authenticated operator UI.

Only journal-replayed native modeled-paper facts can populate modeled finance.
No inferred zero P&L or mixing V4 results with broker trades.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .pm_cwsa_six_paper import ALL_14_WALLETS, PORTFOLIO_CONFIGS

SCHEMA = "cwsa_chapter2_evidence_projection_v1"
COMPLETE_KINDS = frozenset({"BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE"})


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
    output: dict[str, dict] = {}
    for pid, cfg in PORTFOLIO_CONFIGS.items():
        members = sorted(cfg["members"])
        current = papers.get(pid)
        complete = all(kinds.get(alias) in COMPLETE_KINDS for alias in members)
        reasons = list((blockers or {}).get(pid, []))
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
        "scope": {
            "operation": "EXPLAIN_CHAPTER2_PORTFOLIO",
            "portfolio": pid,
            "inspection": inspection,
            "epoch": args.epoch,
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
            "scope": "CHAPTER2_SINGLE_PORTFOLIO",
        },
        "next_operation": None,
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

    dimensions = output["dimensions"]
    blockers = output["blockers"]

    def dimension(name: str, state: str, owner: str, *, evidence: dict | None = None) -> None:
        dimensions[name] = {"state": state, "owner": owner, "evidence": evidence}

    def blocked(reason: str, owner: str, *, scope: str | None = None) -> None:
        blockers.append({"reason_code": reason, "owner": owner, "affected_portfolio": scope or pid})

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
        return output

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
        stale = [
            member
            for member in members
            if kinds.get(member) not in COMPLETE_KINDS
            or member not in per_wallet
            or not isinstance(per_wallet[member], int)
            or per_wallet[member] < latest - grace
            or per_wallet[member] > latest
        ]
        native = source.get("head_sha256")
        valid = (
            isinstance(native, str)
            and len(native) == 64
            and source.get("source_count") == len(gate.EXPECTED_WALLETS)
        )
        freshness_ms = int(now.timestamp() * 1000) - latest
        state = (
            "OBSERVE_READY"
            if valid and not stale and latest > 0 and 0 <= freshness_ms <= 900_000
            else "BLOCKED_EVIDENCE"
        )
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
                "latest_kinds": {member: kinds.get(member) for member in members},
                "policy_grace_ms": grace,
                "latest_age_ms": freshness_ms,
            },
        )
        dimensions["source_observation"]["missing_or_stale_members"] = stale
        if state != "OBSERVE_READY":
            blocked("SOURCE_PORTFOLIO_CHECKPOINT_INCOMPLETE_OR_STALE", "pm_checkpoint_journal")
    except ValueError, OSError, KeyError, TypeError, RuntimeError:
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
                evidence={"epoch": args.epoch, "portfolio": pid},
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

    return output


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
