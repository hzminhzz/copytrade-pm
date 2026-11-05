"""Prospective research-only preflight and bounded public source observation.

This is NOT a paper worker, source-account NAV attestation, first-known fill
outcome, or execution authorization.  It reuses the existing native public
all-DEX source collector and SHA-chained PaperJournal. Historical Phase 7
identity/selection files are never treated as actual prospective receipts.
No broker module or historical fill downloader is imported.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Awaitable, Callable

from .pm_forward_journal import PaperJournal
from .pm_forward_source_stream import (
    bounded_source_scope_capture,
    read_public_collateral_scope,
)
from .wallet_registry import DB

SCHEMA = "phase7_fivepod_prospective_research_v1"
SOURCE_SCHEMA = "phase7_universe_readonly_v1"
RESEARCH_SCHEMA = "phase7_major4_best5_exploratory_replay_v1"
DEFAULT_DECISION = (
    Path(__file__).resolve().parents[2]
    / "docs/decisions/2026-11-05-phase7-fivepod-prospective-v1.json"
)
DEFAULT_SOURCE = Path("/home/quant/.local/share/copytrade/reports/phase7_universe_20261104_v2.json")
DEFAULT_RESEARCH = Path(
    "/home/quant/.local/share/copytrade/reports/phase7_best5_major4_screen_20261105_v5.json"
)
ALLOWED_CAPTURE_ROOT = Path.home() / ".local/share/copytrade/prospective"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
PERMITTED_PORTFOLIOS = {
    "phase7.fivepod/BROAD": ("HX04", "N05", "VS025", "VS035", "W083"),
    "phase7.fivepod/M3_PLUS_TWO": ("H02", "VS002", "VS035", "VS057", "W083"),
    "phase7.fivepod/M3_BASELINE": ("H02", "VS002", "W083"),
}
REQUIRED_ALIASES = frozenset(a for members in PERMITTED_PORTFOLIOS.values() for a in members)
ALLOWED_COHORTS = ("research-108", "nansen-20", "hyperx-30")


class Phase7ResearchBlocked(ValueError):
    pass


@dataclass(frozen=True)
class ResearchSource:
    alias: str
    address: str
    address_sha256: str
    wallet_id: int


def _trusted_json(path: Path, what: str) -> tuple[dict, str]:
    if not path.is_file() or path.is_symlink():
        raise Phase7ResearchBlocked(f"{what}_FILE_UNAVAILABLE_OR_LINK")
    blob = path.read_bytes()
    if len(blob) > 2_500_000:
        raise Phase7ResearchBlocked(f"{what}_FILE_UNBOUNDED")
    item = json.loads(blob)
    if type(item) is not dict:
        raise Phase7ResearchBlocked(f"{what}_SCHEMA_INVALID")
    return item, sha256(blob).hexdigest()


def _research_provenance(manifest: dict, study: dict, evidence: dict) -> None:
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("scope") != "NEW_PROSPECTIVE_RESEARCH_ONLY"
        or manifest.get("decision_authority") != "owner_approved_in_chat_not_independently_signed"
        or manifest.get("research_contract", {}).get("trading_authorized") is not False
        or manifest["research_contract"].get("broker_order_route") != "NONE"
        or manifest["research_contract"].get("paper_worker_authorized") is not False
        or manifest["research_contract"].get("no_retroactive_source_receipts") is not True
        or manifest["research_contract"].get("reference_gemini_E6_E2_P1_unchanged") is not True
        or manifest["research_contract"].get("no_new_historical_fill_acquisition") is not True
        or manifest["research_contract"].get("initial_virtual_cash_usd") != 10_000
        or manifest["research_contract"].get("max_target_gross_at_rebalance_usd") != 5_000
        or manifest["research_contract"].get("candidate_market_policy")
        != ["BTC", "ETH", "SOL", "HYPE"]
    ):
        raise Phase7ResearchBlocked("UNAPPROVED_OR_FINANCIALLY_AUTHORIZED_RESEARCH_DECISION")
    frozen = manifest["prior_research"]
    if (
        frozen.get("frozen_source_universe_sha256") != study["sha"]
        or frozen.get("retrospective_evidence_sha256") != evidence["sha"]
        or frozen.get("touched_90d_no_pristine_holdout") is not True
        or study["data"].get("schema") != SOURCE_SCHEMA
        or evidence["data"].get("schema") != RESEARCH_SCHEMA
        or frozen.get("wallet_candidate_screens")
        != evidence["data"].get("candidate_search", {}).get("all_five_considered")
    ):
        raise Phase7ResearchBlocked("HISTORICAL_EVIDENCE_SHA_OR_TRIAL_CENSUS_MISMATCH")
    bindings = manifest.get("wallet_bindings")
    if not isinstance(bindings, dict) or set(bindings) != REQUIRED_ALIASES:
        raise Phase7ResearchBlocked("RESEARCH_WALLET_BINDING_CENSUS_MISMATCH")
    if any(type(v) is not str or not HEX64.fullmatch(v) for v in bindings.values()):
        raise Phase7ResearchBlocked("INVALID_OR_REDACTED_FULL_ADDRESS_HASH")
    if len(set(bindings.values())) != len(bindings):
        raise Phase7ResearchBlocked("DUPLICATED_SOURCE_ADDRESS_IDENTITY")
    portfolios = manifest.get("portfolios")
    if (
        not isinstance(portfolios, list)
        or len(portfolios) != 3
        or {p.get("id") for p in portfolios} != set(PERMITTED_PORTFOLIOS)
    ):
        raise Phase7ResearchBlocked("RESEARCH_PORTFOLIO_DEFINITION_MISMATCH")
    for portfolio in portfolios:
        members = portfolio.get("members")
        if (
            type(members) is not list
            or len(members) != len(set(members))
            or set(members) != set(PERMITTED_PORTFOLIOS[portfolio["id"]])
            or portfolio.get("version") != 1
        ):
            raise Phase7ResearchBlocked("RESEARCH_PORTFOLIO_MEMBERSHIP_DRIFT")
    exact = {
        tuple(sorted(x.get("members", []))): x
        for x in evidence["data"].get("finalists", [])
        if isinstance(x, dict)
    }
    for portfolio in portfolios:
        if tuple(sorted(portfolio["members"])) not in exact:
            raise Phase7ResearchBlocked("RESEARCH_PORTFOLIO_NOT_IN_FROZEN_EXPLORATORY_RESULT")


def _registry_sources(
    manifest: dict,
    universe: dict,
    registry: Path,
) -> dict[str, ResearchSource]:
    if registry.is_symlink() or not registry.is_file():
        raise Phase7ResearchBlocked("REGISTRY_FILE_UNAVAILABLE")
    source_rows = {
        x["alias"]: x
        for x in universe.get("wallets", [])
        if isinstance(x, dict) and x.get("alias") in REQUIRED_ALIASES
    }
    if len(source_rows) != len(REQUIRED_ALIASES):
        raise Phase7ResearchBlocked("MISSING_SOURCE_IDENTITY")
    for alias, row in source_rows.items():
        if row.get("recommendation") != "CANDIDATE_UNVERIFIED":
            raise Phase7ResearchBlocked("REJECTED_OR_QUALIFIED_SOURCE_STATUS_INVALID")
        address = row.get("address")
        if (
            type(address) is not str
            or not ADDRESS.fullmatch(address)
            or sha256(address.encode()).hexdigest() != manifest["wallet_bindings"][alias]
        ):
            raise Phase7ResearchBlocked("PRIVATE_SOURCE_ADDRESS_HASH_MISMATCH")
    results = {}
    uri = f"file:{registry.resolve(strict=True)}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only=ON")
        meta = dict(db.execute("SELECT key,value FROM snapshot_meta").fetchall())
        if meta.get("manifest_sha256") != manifest["registry"]["required_manifest_sha256"] or len(
            REQUIRED_ALIASES
        ) != len(set(REQUIRED_ALIASES)):
            raise Phase7ResearchBlocked("REGISTRY_SOURCE_GENERATION_DRIFT")
        for alias in sorted(REQUIRED_ALIASES):
            address = source_rows[alias]["address"]
            entries = db.execute(
                "SELECT wallet_id FROM wallets WHERE venue='hyperliquid' "
                "AND lower(address)=? ORDER BY wallet_id",
                (address,),
            ).fetchall()
            if len(entries) != 1:
                raise Phase7ResearchBlocked("SOURCE_ACCOUNT_NOT_UNIQUELY_INDEXED")
            wallet_id = entries[0][0]
            cohorts = {
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT cohort_id FROM cohort_memberships WHERE wallet_id=?",
                    (wallet_id,),
                ).fetchall()
            }
            if not set(ALLOWED_COHORTS).intersection(cohorts):
                raise Phase7ResearchBlocked("SOURCE_ACCOUNT_NOT_IN_RESEARCH_COHORT")
            if db.execute(
                "SELECT 1 FROM exclusions WHERE wallet_id=? LIMIT 1", (wallet_id,)
            ).fetchone():
                raise Phase7ResearchBlocked("OWNER_EXCLUDED_SOURCE_WALLET")
            results[alias] = ResearchSource(
                alias=alias,
                address=address,
                address_sha256=manifest["wallet_bindings"][alias],
                wallet_id=wallet_id,
            )
    return results


def preflight(
    *,
    decision_path: Path = DEFAULT_DECISION,
    universe_path: Path = DEFAULT_SOURCE,
    evidence_path: Path = DEFAULT_RESEARCH,
    registry_path: Path = DB,
) -> tuple[dict, dict[str, ResearchSource]]:
    manifest, manifest_sha = _trusted_json(decision_path, "DECISION")
    universe, universe_sha = _trusted_json(universe_path, "UNIVERSE")
    evidence, evidence_sha = _trusted_json(evidence_path, "RESEARCH")
    _research_provenance(
        manifest,
        {"data": universe, "sha": universe_sha},
        {"data": evidence, "sha": evidence_sha},
    )
    sources = _registry_sources(manifest, universe, registry_path)
    return {
        "schema": "phase7_fivepod_prospective_preflight_v1",
        "status": "RESEARCH_PRIORITY_PREPARED_OBSERVATION_NOT_YET_ATTESTED",
        "decision_manifest_sha256": manifest_sha,
        "research_fills_window_is_prospective": False,
        "historical_retrospective_evidence_sha256": evidence_sha,
        "source_universe_sha256": universe_sha,
        "research_cohort_member_count": len(sources),
        "selected_portfolios": [
            {"id": p["id"], "role": p["role"], "members": list(p["members"])}
            for p in manifest["portfolios"]
        ],
        "wallet_identity_hashes": {
            alias: source.address_sha256 for alias, source in sorted(sources.items())
        },
        "first_known_source_receipts_attested": False,
        "source_equity_and_opening_positions_attested": False,
        "matched_follower_execution_attested": False,
        "paper_worker_attested": False,
        "financial_paper_events_committed": 0,
        "portfolio_registry_updated": False,
        "portfolio_freeze_changed": False,
        "order_route": "NONE",
        "trading_authorized": False,
        "scientifically_qualified": False,
    }, sources


def _no_financial_events(journal: PaperJournal) -> None:
    db_path = journal.path
    if db_path.is_symlink():
        raise Phase7ResearchBlocked("JOURNAL_PATH_SYMLINK")
    uri = f"file:{db_path.resolve(strict=True)}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
        db.execute("PRAGMA query_only=ON")
        for table in ("runs", "events", "account_source_cursors"):
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count:
                raise Phase7ResearchBlocked("OBSERVATION_JOURNAL_HAS_FINANCIAL_STATE")


async def capture_bounded(
    *,
    sources: dict[str, ResearchSource],
    journal: PaperJournal,
    capture_one: Callable[..., Awaitable[dict]] = bounded_source_scope_capture,
    capture_collateral: Callable[..., Awaitable[dict]] = read_public_collateral_scope,
    seconds_per_account: float = 2,
    max_frames: int = 2,
) -> dict:
    """One public observation per unique parent; shared portfolios do not duplicate calls."""
    if (
        set(sources) != REQUIRED_ALIASES
        or not 2 <= seconds_per_account <= 8
        or not 1 <= max_frames <= 5
    ):
        raise Phase7ResearchBlocked("UNBOUNDED_OR_WRONG_PROSPECTIVE_CAPTURE_SCOPE")
    _no_financial_events(journal)
    observations = []
    for alias in sorted(sources):
        source = sources[alias]
        transport_status = "BLOCKED_SOURCE_ACQUISITION"
        source_receipts = 0
        first_known = False
        diagnostic_receipts = 0
        # Alias is namespaced to prevent collision with P1/P14 journals.
        tape_id = "PH7_" + alias
        try:
            before_cursor = journal.source_status(tape_id)["cursor"]
            observed = await capture_one(
                alias=tape_id,
                address=source.address,
                journal=journal,
                seconds=seconds_per_account,
                max_frames=max_frames,
            )
            after_cursor = journal.source_status(tape_id)["cursor"]
            if (
                observed.get("order_route") != "NONE"
                or observed.get("whole_wallet_equity_attested") is not False
                or observed.get("paper_admitted") is not False
                or observed.get("wallet_alias") != tape_id
                or observed.get("account_address_sha256") != source.address_sha256
            ):
                raise Phase7ResearchBlocked("PUBLIC_SOURCE_POSITIVE_ATTESTATION_REFUSED")
            transport_status = str(observed["transport_status"])
            source_receipts = int(observed["per_account_receipts"])
            if (
                source_receipts < 0
                or source_receipts > max_frames
                or source_receipts != after_cursor - before_cursor
            ):
                raise Phase7ResearchBlocked("SOURCE_RECEIPT_COUNT_INVALID")
            first_known = source_receipts > 0
        except asyncio.CancelledError:
            raise
        except Exception:
            transport_status = "BLOCKED_PUBLIC_CAPTURE_OR_INTEGRITY"
            source_receipts = 0
            first_known = False
        # Spot/vault public responses are per-account diagnostics, not a shared NAV.
        try:
            collateral = await capture_collateral(address=source.address)
            if (
                collateral.get("order_route") != "NONE"
                or collateral.get("source_equity") is not None
                or collateral.get("collateral_reconciled") is not False
                or collateral.get("account_address_sha256") != source.address_sha256
            ):
                raise Phase7ResearchBlocked("COLLATERAL_TRUE_NAV_FABRICATION")
            prior_diagnostic = journal.collateral_scope_status(source.address_sha256)["cursor"]
            diagnostic = journal.append_collateral_diagnostic(collateral)
            diagnostic_receipts = diagnostic["cursor"] - prior_diagnostic
            if diagnostic_receipts not in (0, 1):
                raise Phase7ResearchBlocked("COLLATERAL_DIAGNOSTIC_CURSOR_DRIFT")
        except asyncio.CancelledError:
            raise
        except Exception:
            diagnostic_receipts = 0
        observations.append(
            {
                "alias": alias,
                "wallet_identity_sha256": source.address_sha256,
                "transport_status": transport_status,
                "new_public_source_receipts": source_receipts,
                "new_collateral_diagnostic_groups": diagnostic_receipts,
                "any_first_known_source_receipt": first_known,
                "whole_wallet_equity_attested": False,
                "paper_admitted": False,
                "order_route": "NONE",
            }
        )
    _no_financial_events(journal)
    return {
        "schema": "phase7_fivepod_public_source_canary_v1",
        "status": "BLOCKED_PROSPECTIVE_PARTIAL_OBSERVER_ONLY",
        "capture_end_at_utc": datetime.now(UTC).isoformat(),
        "observed_unique_parent_accounts": len(observations),
        "public_source_accounts_with_new_receipts": sum(
            item["any_first_known_source_receipt"] for item in observations
        ),
        "new_public_source_receipts": sum(
            item["new_public_source_receipts"] for item in observations
        ),
        "new_collateral_diagnostic_groups": sum(
            item["new_collateral_diagnostic_groups"] for item in observations
        ),
        "observations": observations,
        "financial_paper_events_committed": 0,
        "paper_running": False,
        "whole_account_equity_attested": False,
        "market_execution_economics_attested": False,
        "trading_authorized": False,
        "order_route": "NONE",
    }


def _restricted_journal_root(root: Path) -> Path:
    if not root.is_absolute() or root.parent != ALLOWED_CAPTURE_ROOT:
        raise Phase7ResearchBlocked("PUBLIC_OBSERVER_ROOT_NOT_EXPLICITLY_ISOLATED")
    if root.is_symlink() or root.name != "phase7-fivepod-20261105":
        raise Phase7ResearchBlocked("PUBLIC_OBSERVER_ROOT_NAME_OR_SYMLINK")
    if not ALLOWED_CAPTURE_ROOT.is_dir() or ALLOWED_CAPTURE_ROOT.is_symlink():
        raise Phase7ResearchBlocked("PUBLIC_OBSERVER_PARENT_UNAVAILABLE")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=DEFAULT_DECISION)
    parser.add_argument("--source-universe", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--research-evidence", type=Path, default=DEFAULT_RESEARCH)
    parser.add_argument("--registry", type=Path, default=DB)
    parser.add_argument("--capture-bounded", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--seconds-per-account", type=float, default=2)
    parser.add_argument("--max-frames", type=int, default=2)
    args = parser.parse_args()
    info, sources = preflight(
        decision_path=args.decision,
        universe_path=args.source_universe,
        evidence_path=args.research_evidence,
        registry_path=args.registry,
    )
    if args.capture_bounded:
        if args.state_root is None:
            raise Phase7ResearchBlocked("CAPTURE_ROOT_REQUIRED")
        root = _restricted_journal_root(args.state_root)
        canary = asyncio.run(
            capture_bounded(
                sources=sources,
                journal=PaperJournal(root),
                seconds_per_account=args.seconds_per_account,
                max_frames=args.max_frames,
            )
        )
        info["bounded_canary"] = canary
        info["status"] = "BLOCKED_PROSPECTIVE_PARTIAL_OBSERVER_ONLY"
    elif args.state_root is not None:
        raise Phase7ResearchBlocked("UNEXPECTED_STATE_MUTATION_PATH")
    print(json.dumps(info, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
