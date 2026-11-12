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
