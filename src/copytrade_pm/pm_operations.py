"""Evidence-aware, read-only repo-wide operator queries.

Roster, paper, research and release retain their own authorities. This module
only adapts their public read interfaces. It never imports a writer or obtains
broker access. Retired authorities (the legacy wallet registry) are explicit
UNKNOWN, never re-read through a compatibility shim.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess

from . import pm_capabilities as capabilities
from . import pm_cwsa_chapter2_gate
from . import pm_forward_ccxt_market
from . import pm_forward_observer
from . import pm_forward_observer_health
from . import pm_forward_status
from . import pm_health_arguments
from . import pm_market_audit
from . import pm_runtime_readonly as runtime
from . import production_export
from .pm_bounded_acquisition import plan_bounded_acquisition
from .roster import GateFailure
from .pm_offline_job_catalog import assess_reuse, list_reports

SCHEMA = "copytrade_read_result_v1"
ROOT = Path(__file__).resolve().parents[2]
ROSTER_DB = Path("~/.local/share/copytrade/roster.sqlite").expanduser()
LIMITED = frozenset(
    {
        "VERIFIED",
        "DEGRADED",
        "STALE",
        "BLOCKED",
        "UNKNOWN",
        "NOT_RUNNING",
        "NOT_REGISTERED_AT_ASOF",
        "SCHEMA_UPGRADE_REQUIRED",
    }
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def result(
    capability: str,
    status: str,
    data: object = None,
    *,
    authority: str,
    version: str | None = None,
    sha256: str | None = None,
    observed_at: str | None = None,
    source_observed_at: str | None = None,
    limitations: list[str] | None = None,
    error_code: str | None = None,
) -> dict:
    if status not in LIMITED:
        raise ValueError("INVALID_READ_RESULT_STATUS")
    return {
        "schema": SCHEMA,
        "capability": capability,
        "status": status,
        "observed_at": observed_at or _now(),
        "source": {
            "authority": authority,
            "version": version,
            "sha256": sha256,
            "observed_at": source_observed_at,
        },
        "data": data,
        "limitations": limitations or [],
        "error_code": error_code,
        "trading_authorized": False,
        "scientifically_qualified": False,
    }


def roster_authority(db: Path) -> dict:
    """Roster SQLite integrity and content pin; the retired registry is UNKNOWN."""
    return _roster_authority(db)


def roster_selection(db: Path, account: str, as_of: str | None = None) -> dict:
    return _roster_selection(db, account, as_of)


def _roster_authority(db: Path) -> dict:
    from .roster.store import RosterStore

    try:
        verified = RosterStore.authority_health(db)
    except (OSError, ValueError, RuntimeError) as exc:
        return result(
            "roster.authority",
            "UNKNOWN",
            authority="roster_sqlite",
            error_code=getattr(exc, "args", ("ROSTER_AUTHORITY_UNAVAILABLE",))[0],
            limitations=[type(exc).__name__],
        )
    return result(
        "roster.authority",
        "VERIFIED",
        {
            "database_integrity": verified["database_integrity"],
            "inventory_sha256": verified["inventory_sha256"],
            "accounts": verified.get("accounts"),
        },
        authority="roster_sqlite",
        sha256=verified["inventory_sha256"],
        source_observed_at=verified.get("observed_at"),
    )


def _roster_selection(db: Path, account: str, as_of: str | None) -> dict:
    """Current sealed seat book for one account, or an explicit refusal."""
    from .roster.sealed import SealedSelectionError, select_sealed_book, timestamp_ms
    from .roster.store import RosterStore

    try:
        cutoff = timestamp_ms(as_of) if as_of else timestamp_ms(_now())
        with RosterStore(db) as store:
            sealed = select_sealed_book(store, account, cutoff, require_attestation=False)
        return result(
            "roster.selection",
            "VERIFIED",
            sealed.metadata(),
            authority="roster_sqlite",
            sha256=sealed.book.sha,
        )
    except SealedSelectionError as exc:
        state = "NOT_REGISTERED_AT_ASOF" if str(exc) == "SELECTION_UNKNOWN_AT_ASOF" else "UNKNOWN"
        return result(
            "roster.selection",
            state,
            authority="roster_sqlite",
            error_code=str(exc),
            limitations=[
                "Selection integrity never establishes signed admission or trading authority"
            ],
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return result(
            "roster.selection",
            "UNKNOWN",
            authority="roster_sqlite",
            error_code="ROSTER_SELECTION_UNAVAILABLE",
            limitations=[type(exc).__name__],
        )


def _git(root: Path) -> dict:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    return {"revision": proc.stdout.strip()}


def _release(root: Path) -> dict:
    checked = runtime.installed_release(root)
    return result(
        "release.installed",
        checked["state"],
        checked,
        authority="registry_release_verifier",
        version=checked.get("release_revision"),
        error_code=checked.get("error_code"),
        limitations=[
            "Only the pinned installed release checkout, not paper or broker services, was verified"
        ],
    )


def _research(
    capability: str,
    run_id: str | None = None,
    *,
    cache_root: Path | None = None,
    cache_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    if cache_root is None:
        return result(
            capability,
            "UNKNOWN",
            authority="immutable_offline_job_cache",
            error_code="EXPLICIT_RESEARCH_CACHE_ROOT_REQUIRED",
            limitations=["No canonical global research index; supply the exact private cache root"],
            data={"native_interface": "python -m copytrade_pm.pm_offline_job --help"},
        )
    try:
        payload = list_reports(
            cache_root,
            job_id=run_id,
            cache_key=cache_key,
            limit=limit,
            offset=offset,
        )
        state = "VERIFIED" if payload["status"] == "VERIFIED" else "UNKNOWN"
        return result(
            capability,
            state,
            payload,
            authority="sha_verified_immutable_offline_job_cache",
            error_code=None if state == "VERIFIED" else "NO_MATCHING_CANONICAL_JOB_REPORT",
            limitations=[
                "Scoped to one explicitly provided cache; other research sources are not inventoried"
            ],
        )
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return result(
            capability,
            "BLOCKED",
            authority="sha_verified_immutable_offline_job_cache",
            error_code="RESEARCH_CACHE_INTEGRITY_OR_SCOPE_FAILURE",
            limitations=[str(exc) if isinstance(exc, ValueError) else type(exc).__name__],
        )


def _load_preflight_request(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("UNSAFE_OR_OVERSIZED_PREFLIGHT_REQUEST")
    parsed = json.loads(path.read_bytes())
    if not isinstance(parsed, dict):
        raise ValueError("INVALID_PREFLIGHT_REQUEST_OBJECT")
    return parsed


def _research_preflight(
    *,
    cache_root: Path | None = None,
    request_path: Path | None = None,
    purpose: str | None = None,
    require_pit: bool = False,
    partition_root: Path | None = None,
    plan_acquisition: bool = False,
) -> dict:
    limitations = [
        "Research reuse preflight checks cache/coverage integrity and PIT scope only; "
        "never supplies fresh balances, quotes, HALT clearance, Copy Mandates, "
        "paper financial proof, scientific qualification, or trading authorization"
    ]
    if cache_root is None:
        return result(
            "research.preflight",
            "UNKNOWN",
            authority="immutable_offline_job_cache",
            error_code="EXPLICIT_RESEARCH_CACHE_ROOT_REQUIRED",
            limitations=["Supply --cache-root PATH and --request PATH", *limitations],
        )
    if request_path is None:
        return result(
            "research.preflight",
            "UNKNOWN",
            authority="sha_verified_immutable_offline_job_cache",
            error_code="EXPLICIT_PREFLIGHT_REQUEST_PATH_REQUIRED",
            limitations=["Supply --request PATH to evaluate research reuse", *limitations],
        )
    try:
        if partition_root is not None and partition_root.is_symlink():
            raise ValueError("SYMLINK_PARTITION_ROOT")
        req = _load_preflight_request(request_path)
        if purpose is not None:
            req = {**req, "purpose": purpose}
        if require_pit:
            req = {**req, "require_pit": True}
        base_req = {k: v for k, v in req.items() if k != "acquisition"}
        payload = assess_reuse(cache_root, base_req)
        acq_plan = None
        if plan_acquisition or partition_root is not None or "acquisition" in req:
            acq_plan = plan_bounded_acquisition(
                cache_root, req, partition_root=partition_root, reuse=payload
            )
            payload = {**payload, "acquisition_plan": acq_plan}
    except (ValueError, OSError, TypeError, KeyError, UnicodeDecodeError) as exc:
        return result(
            "research.preflight",
            "BLOCKED",
            authority="sha_verified_immutable_offline_job_cache",
            error_code="RESEARCH_PREFLIGHT_REQUEST_OR_CACHE_FAILURE",
            limitations=[
                str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                *limitations,
            ],
        )
    reuse_state = payload["state"]
    if acq_plan is not None and acq_plan["status"] == "BLOCKED":
        status, error_code = "BLOCKED", acq_plan["error_code"]
    elif reuse_state in {"VERIFIED_CACHE_HIT", "VERIFIED_EMPTY"}:
        status, error_code = "VERIFIED", None
    elif reuse_state == "CACHE_MISS":
        status, error_code = "UNKNOWN", "CACHE_MISS"
    else:
        status, error_code = "BLOCKED", reuse_state
    return result(
        "research.preflight",
        status,
        payload,
        authority="sha_verified_immutable_offline_job_cache",
        error_code=error_code,
        limitations=limitations,
    )


def _health(
    db: Path,
    root: Path,
    observer_root: Path | None = None,
    account: str | None = None,
) -> dict:
    parts: dict[str, dict] = {}
    try:
        parts["repository"] = result(
            "repository.revision", "VERIFIED", _git(root), authority="git_checkout"
        )
    except (subprocess.SubprocessError, OSError) as exc:
        parts["repository"] = result(
            "repository.revision",
            "UNKNOWN",
            authority="git_checkout",
            error_code="GIT_READ_FAILED",
            limitations=[type(exc).__name__],
        )
    parts["roster"] = _roster_authority(db)
    if account:
        parts["selection"] = _roster_selection(db, account, None)
    else:
        parts["selection"] = result(
            "roster.selection",
            "UNKNOWN",
            authority="roster_sqlite",
            error_code="ROSTER_ACCOUNT_SCOPE_REQUIRED",
            limitations=[
                "Pass --account to read one sealed seat book; no global selection default"
            ],
        )
    parts["research"] = _research("research.list")
    parts["installed_release"] = _release(root)
    paper_os = runtime.paper_unit_inventory()
    parts["paper_units"] = result(
        "paper.os_units",
        paper_os["state"],
        paper_os,
        authority="systemd_user_service_manager",
        error_code=paper_os.get("error_code"),
        limitations=["Unit activity is not protected journal/heartbeat attestation"],
    )
    observed_market = runtime.observer_market_health(observer_root)
    parts["market_provider"] = result(
        "market.observer_tapes",
        observed_market["state"],
        observed_market,
        authority="independent_public_observer",
        error_code=observed_market.get("error_code"),
        limitations=[
            "Observer quote receipts never establish live provider health or executable capacity"
        ],
    )
    parts["scientific_qualification"] = result(
        "qualification.science",
        "BLOCKED",
        authority="independent_matched_economics",
        error_code="NO_VERIFIED_POSITIVE_QUALIFICATION",
    )
    statuses = [part["status"] for part in parts.values()]
    overall = (
        "DEGRADED"
        if any(x in {"UNKNOWN", "STALE", "DEGRADED", "BLOCKED", "NOT_RUNNING"} for x in statuses)
        else "VERIFIED"
    )
    return result(
        "operations.status",
        overall,
        {"components": parts},
        authority="independent_read_adapters",
        limitations=["Aggregated statuses do not establish a running worker or authorization"],
    )


def dispatch(args: argparse.Namespace) -> dict:
    db = args.db
    if args.group == "capabilities":
        if args.verb == "list":
            return {
                "schema": "copytrade_capability_list_v1",
                "capabilities": capabilities.inventory(args.root),
            }
        if args.verb == "show":
            matches = [x for x in capabilities.inventory(args.root) if x["id"] == args.id]
            return (
                matches[0] if matches else {"status": "UNKNOWN", "error_code": "UNKNOWN_CAPABILITY"}
            )
        return capabilities.validate(args.root)
    if args.group == "research":
        if args.verb == "contracts":
            from .pm_contract_selector import compare_portfolios, rules_catalog

            if args.contract_verb == "rules":
                return rules_catalog()
            return compare_portfolios(
                args.portfolio,
                args.tape,
                db=db,
                asof=args.asof,
                paths=args.paths,
                seed=args.seed,
                block_days=args.block_days,
                evaluation_days=args.evaluation_days,
                funded_days=args.funded_days,
                evaluation_scales=tuple(args.evaluation_scales),
                funded_scales=tuple(args.funded_scales),
                extra_daily_cost=args.extra_daily_cost,
                discount_rate=args.discount_rate,
                max_no_first_payout_probability=args.max_no_first_payout_probability,
            )
        if args.verb == "preflight":
            return _research_preflight(
                cache_root=args.cache_root,
                request_path=args.request,
                purpose=args.purpose,
                require_pit=args.require_pit,
                partition_root=args.partition_root,
                plan_acquisition=args.plan_acquisition,
            )
        return _research(
            "research." + args.verb,
            getattr(args, "id", None),
            cache_root=args.cache_root,
            cache_key=args.cache_key,
            limit=args.limit,
            offset=args.offset,
        )
    if args.group == "release":
        if args.verb == "chapter2":
            return _chapter2(args)
        return _health(db, args.root, args.observer_state_root, getattr(args, "account", None))
    raise ValueError("UNKNOWN_OPERATIONS_GROUP")


def _chapter2(args: argparse.Namespace) -> dict:
    if args.policy == "projection":
        from .pm_cwsa_chapter2_projection import build_runtime_projection

        return build_runtime_projection(args)
    if args.policy in ("explain", "site-view"):
        from .pm_cwsa_chapter2_projection import explain_task, site_owner_view

        original = explain_task(args)
        return site_owner_view(original) if args.policy == "site-view" else original
    if args.policy == "recover":
        from .pm_cwsa_chapter2_projection import explain_native_guardian_intent

        return explain_native_guardian_intent(
            journal_path=args.guardian_journal,
            intent_id=args.intent_id,
            observed_at_ms=args.observed_at_ms,
        )
    from .pm_cwsa_chapter2_gate import verify

    return verify(args)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="copytrade-pm",
        description=(
            "Evidence-aware operations: capabilities, facts, research, roster, paper, release"
        ),
    )
    p.add_argument(
        "--db",
        type=Path,
        default=ROSTER_DB,
        help="Roster SQLite: the only wallet/seat identity authority",
    )
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--observer-state-root", type=Path)
    top = p.add_subparsers(dest="group", required=True)

    cap = top.add_parser("capabilities", help="Reviewed capability discovery and validation")
    sub = cap.add_subparsers(dest="verb", required=True)
    cap_list = sub.add_parser("list")
    cap_list.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    cap_validate = sub.add_parser("validate")
    cap_validate.add_argument("--json", action="store_true")

    facts = top.add_parser(
        "facts", help="Day-partitioned Decimal fact store: migrate, verify, coverage, benchmark"
    )
    facts_verbs = facts.add_subparsers(dest="verb", required=True)
    facts_migrate = facts_verbs.add_parser(
        "migrate", help="Idempotent migration from named sources"
    )
    facts_migrate.add_argument("--store", required=True)
    facts_migrate.add_argument("--wallet-store")
    facts_migrate.add_argument("--reservoir", action="append")
    facts_migrate.add_argument("--wallet-store-catalog")
    facts_migrate.add_argument("--kinds", default="fills,positions")
    facts_migrate.add_argument("--pattern", default="**/*.parquet")
    facts_migrate.add_argument("--require-all-sources", action="store_true")
    facts_migrate.add_argument("--report")
    facts_migrate.add_argument("--apply", action="store_true")
    facts_migrate.add_argument("--json", action="store_true")
    facts_verify = facts_verbs.add_parser("verify", help="Re-hash every batch against the manifest")
    facts_verify.add_argument("--store", required=True)
    facts_verify.add_argument("--kinds", default="fills,positions,equity,funding,ledger")
    facts_verify.add_argument("--json", action="store_true")
    facts_coverage = facts_verbs.add_parser("coverage", help="Day and row coverage per kind")
    facts_coverage.add_argument("--store", required=True)
    facts_coverage.add_argument("--kinds", default="fills,positions,equity,funding,ledger")
    facts_coverage.add_argument("--json", action="store_true")
    facts_benchmark = facts_verbs.add_parser(
        "benchmark", help="250-wallet x 200-day synthetic cross-sectional scan"
    )
    facts_benchmark.add_argument("--store")
    facts_benchmark.add_argument("--workdir")
    facts_benchmark.add_argument("--wallets", type=int, default=250)
    facts_benchmark.add_argument("--days", type=int, default=200)
    facts_benchmark.add_argument("--rows-per-wallet-day", type=int, default=20)
    facts_benchmark.add_argument("--repeats", type=int, default=3)
    facts_benchmark.add_argument("--end-day")
    facts_benchmark.add_argument("--keep", action="store_true")
    facts_benchmark.add_argument("--apply", action="store_true")
    facts_benchmark.add_argument("--json", action="store_true")
    facts_capture = facts_verbs.add_parser(
        "capture-health", help="Capture official wallet-health facts"
    )
    pm_health_arguments.add_arguments(facts_capture)
    facts_capture.add_argument("--apply", action="store_true", help="Run and persist the capture")

    research = top.add_parser(
        "research",
        help=("Offline job reports, bounded acquisition, native market evidence and contract EV"),
    )
    research_verbs = research.add_subparsers(dest="verb", required=True)
    research_list = research_verbs.add_parser("list", help="List cached job reports")
    research_list.add_argument("--cache-root", type=Path)
    research_list.add_argument("--cache-key")
    research_list.add_argument("--limit", type=int, default=100)
    research_list.add_argument("--offset", type=int, default=0)
    research_show = research_verbs.add_parser("show", help="Show one cached job report")
    research_show.add_argument("id")
    research_show.add_argument("--cache-root", type=Path)
    research_show.add_argument("--cache-key")
    research_show.add_argument("--limit", type=int, default=100)
    research_show.add_argument("--offset", type=int, default=0)
    research_scorecards = research_verbs.add_parser(
        "scorecards", help="Recorded wallet scorecards at a known-at clock"
    )
    research_scorecards.add_argument("--store", required=True)
    research_scorecards.add_argument("--as-of")
    research_scorecards.add_argument("--cache-root", type=Path)
    research_scorecards.add_argument("--cache-key")
    research_scorecards.add_argument("--limit", type=int, default=100)
    research_scorecards.add_argument("--offset", type=int, default=0)
    research_scorecards.add_argument("--json", action="store_true")
    research_preflight = research_verbs.add_parser(
        "preflight", help="Verify reusable research without acquiring or qualifying"
    )
    research_preflight.add_argument("--cache-root", type=Path)
    research_preflight.add_argument("--request", type=Path)
    research_preflight.add_argument("--purpose")
    research_preflight.add_argument("--require-pit", action="store_true")
    research_preflight.add_argument("--partition-root", type=Path)
    research_preflight.add_argument("--plan-acquisition", action="store_true")
    contracts = research_verbs.add_parser(
        "contracts", help="Read-only pod portfolio x contract EV screening"
    )
    contract_verbs = contracts.add_subparsers(dest="contract_verb", required=True)
    contract_verbs.add_parser("rules", help="Show the versioned, unverified rule scenarios")
    compare = contract_verbs.add_parser(
        "compare", help="Rank contracts from complete net PnL tapes"
    )
    compare.add_argument(
        "--portfolio",
        action="append",
        required=True,
        help="Namespace-qualified sealed portfolio; repeat to compare portfolios",
    )
    compare.add_argument(
        "--tape",
        action="append",
        type=Path,
        help="Full joint pod PnL tape; repeat once per portfolio",
    )
    compare.add_argument("--asof", help="Portfolio identity lookup cutoff in UTC")
    compare.add_argument("--paths", type=int, default=100_000)
    compare.add_argument("--seed", type=int, default=20261105)
    compare.add_argument("--block-days", type=int, default=7)
    compare.add_argument("--evaluation-days", type=int, default=180)
    compare.add_argument("--funded-days", type=int, default=180)
    compare.add_argument("--evaluation-scales", type=float, nargs="+", default=[0.5, 1.0])
    compare.add_argument("--funded-scales", type=float, nargs="+", default=[0.25, 0.5])
    compare.add_argument("--extra-daily-cost", type=float, default=0.0)
    compare.add_argument("--discount-rate", type=float, default=0.0)
    compare.add_argument(
        "--max-no-first-payout-probability",
        type=float,
        default=1.0,
        help="Risk constraint for any selected contract/size policy",
    )
    research_market_audit = research_verbs.add_parser(
        "market-audit", help="Read-only native minute market coverage and integrity audit"
    )
    pm_market_audit.add_arguments(research_market_audit)
    research_market_audit.add_argument(
        "--apply", action="store_true", help="Write the private evidence report"
    )
    research_ccxt_probe = research_verbs.add_parser(
        "ccxt-probe", help="Bounded read-only CCXT Pro Hyperliquid L2 probe"
    )
    pm_forward_ccxt_market.add_arguments(research_ccxt_probe)
    research_ccxt_probe.add_argument(
        "--apply", action="store_true", help="Permit a private recorded canary journal"
    )

    roster = top.add_parser(
        "roster", help="Seat leases, sticky reconciliation and daily unsigned proposals"
    )
    roster_verbs = roster.add_subparsers(dest="verb", required=True)
    roster_register = roster_verbs.add_parser("register", help="Declare one account's seats")
    roster_register.add_argument("--store", required=True)
    roster_register.add_argument("--account", required=True)
    roster_register.add_argument(
        "--seat",
        action="append",
        required=True,
        help="seat_id:RISK_UNIT_USD:MAX_CDAR_SHARE (repeatable)",
    )
    roster_register.add_argument("--policy-epoch", required=True)
    roster_register.add_argument("--apply", action="store_true")
    roster_register.add_argument("--json", action="store_true")
    roster_show = roster_verbs.add_parser("show", help="Current seat book at a known-at clock")
    roster_show.add_argument("--store", required=True)
    roster_show.add_argument("--account", required=True)
    roster_show.add_argument("--as-of")
    roster_show.add_argument("--identities", action="store_true")
    roster_show.add_argument("--json", action="store_true")
    roster_plan = roster_verbs.add_parser("plan", help="Pure reconciliation preview (no write)")
    roster_plan.add_argument("--store", required=True)
    roster_plan.add_argument("--account", required=True)
    roster_plan.add_argument("--as-of")
    roster_plan.add_argument("--identities", action="store_true")
    roster_plan.add_argument("--json", action="store_true")
    roster_commit = roster_verbs.add_parser("commit", help="Append the reconciled seat book")
    roster_commit.add_argument("--store", required=True)
    roster_commit.add_argument("--account", required=True)
    roster_commit.add_argument("--as-of")
    roster_commit.add_argument("--apply", action="store_true")
    roster_commit.add_argument("--identities", action="store_true")
    roster_commit.add_argument("--json", action="store_true")
    roster_scorecard = roster_verbs.add_parser("scorecard", help="Record one wallet scorecard")
    roster_scorecard.add_argument("--store", required=True)
    roster_scorecard.add_argument("--wallet", required=True)
    roster_scorecard.add_argument("--as-of")
    roster_scorecard.add_argument("--account-value", required=True)
    roster_scorecard.add_argument("--active-days", type=int, default=0)
    roster_scorecard.add_argument("--markout-bps", default="0")
    roster_scorecard.add_argument("--participation", default="0")
    roster_scorecard.add_argument("--cdar", default="0")
    roster_scorecard.add_argument("--k", default="1")
    roster_scorecard.add_argument("--cluster", required=True)
    roster_scorecard.add_argument("--source-sha", required=True)
    roster_scorecard.add_argument(
        "--copyable", action=argparse.BooleanOptionalAction, default=False
    )
    roster_scorecard.add_argument(
        "--failure", action="append", choices=tuple(gate.value for gate in GateFailure)
    )
    roster_scorecard.add_argument("--identities", action="store_true")
    roster_scorecard.add_argument("--apply", action="store_true")
    roster_scorecard.add_argument("--json", action="store_true")
    roster_bench = roster_verbs.add_parser("bench", help="Record a portfolio-conditioned bench")
    roster_bench.add_argument("--store", required=True)
    roster_bench.add_argument("--account", required=True)
    roster_bench.add_argument("--as-of")
    roster_bench.add_argument(
        "--candidate",
        action="append",
        help="wallet:SCORECARD_SHA:k:MARGINAL_CDAR:CLUSTER_ID:CLUSTER_DISTANCE",
    )
    roster_bench.add_argument("--apply", action="store_true")
    roster_bench.add_argument("--json", action="store_true")
    roster_veto = roster_verbs.add_parser("veto", help="Record or revoke an operator veto")
    roster_veto.add_argument("--store", required=True)
    roster_veto.add_argument("--wallet", required=True)
    roster_veto.add_argument("--reason", default="operator veto")
    roster_veto.add_argument("--actor", default="operator")
    roster_veto.add_argument("--at-ms", type=int, required=True)
    roster_veto.add_argument("--expires-ms", type=int)
    roster_veto.add_argument("--revoke", action="store_true")
    roster_veto.add_argument("--apply", action="store_true")
    roster_veto.add_argument("--identities", action="store_true")
    roster_veto.add_argument("--json", action="store_true")
    roster_cusum = roster_verbs.add_parser("cusum", help="Record one Q12 CUSUM increment")
    roster_cusum.add_argument("--store", required=True)
    roster_cusum.add_argument("--wallet", required=True)
    roster_cusum.add_argument("--increment", required=True)
    roster_cusum.add_argument("--threshold", required=True)
    roster_cusum.add_argument("--epoch", required=True)
    roster_cusum.add_argument("--at-ms", type=int, required=True)
    roster_cusum.add_argument("--apply", action="store_true")
    roster_cusum.add_argument("--json", action="store_true")
    roster_binding = roster_verbs.add_parser(
        "binding", help="Record one researched release binding (provenance pins)"
    )
    roster_binding.add_argument("--store", required=True)
    roster_binding.add_argument("--file", required=True)
    roster_binding.add_argument("--apply", action="store_true")
    roster_binding.add_argument("--json", action="store_true")
    roster_proposal = roster_verbs.add_parser(
        "proposal", help="List staged unsigned release proposals"
    )
    roster_proposal.add_argument("--store", required=True)
    roster_proposal.add_argument("--account")
    roster_proposal.add_argument("--json", action="store_true")

    paper = top.add_parser(
        "paper",
        help=(
            "Virtual paper seat view, staged mandates, per-run status and the public observer "
            "(NONE route)"
        ),
    )
    paper_verbs = paper.add_subparsers(dest="verb", required=True)
    paper_status = paper_verbs.add_parser("status", help="Virtual paper seat view")
    paper_status.add_argument("--store", required=True)
    paper_status.add_argument("--account", required=True)
    paper_status.add_argument("--as-of")
    paper_status.add_argument("--identities", action="store_true")
    paper_status.add_argument("--json", action="store_true")
    paper_mandates = paper_verbs.add_parser("mandates", help="Latest staged paper mandates")
    paper_mandates.add_argument("--store", required=True)
    paper_mandates.add_argument("--account", required=True)
    paper_mandates.add_argument("--as-of")
    paper_mandates.add_argument("--json", action="store_true")
    paper_observe = paper_verbs.add_parser(
        "observe",
        help="Shared public-only observer: preflight, bounded epochs or continuous service",
    )
    pm_forward_observer.add_arguments(paper_observe)
    paper_observe.add_argument(
        "--apply",
        action="store_true",
        help="Start observation; without it only the read-only preflight or diagnosis runs",
    )
    paper_observer_health = paper_verbs.add_parser(
        "observer-health", help="Independent observer health, watchdog and shadow report"
    )
    pm_forward_observer_health.add_arguments(paper_observer_health)
    paper_observer_health.add_argument(
        "--apply",
        action="store_true",
        help="Permit the mutating --watch witness; plain reads and shadow reports need no gate",
    )
    paper_run_status = paper_verbs.add_parser(
        "run-status", help="Per-run forward-paper journal and heartbeat status"
    )
    pm_forward_status.add_arguments(paper_run_status)

    release = top.add_parser(
        "release", help="Staged proposals, offline signing, manifest signing and release evidence"
    )
    release_verbs = release.add_subparsers(dest="verb", required=True)
    release_propose = release_verbs.add_parser(
        "propose", help="Stage one unsigned portfolio_release_v2 proposal"
    )
    release_propose.add_argument("--store", required=True)
    release_propose.add_argument("--account", required=True)
    release_propose.add_argument("--as-of")
    release_propose.add_argument("--out")
    release_propose.add_argument("--apply", action="store_true")
    release_propose.add_argument("--json", action="store_true")
    release_sign = release_verbs.add_parser("sign", help="Sign a staged proposal offline")
    release_sign.add_argument("--proposal", required=True)
    release_sign.add_argument("--release-signing-key", required=True)
    release_sign.add_argument("--reviewer-public", type=Path, required=True)
    release_sign.add_argument("--source-observer-public", type=Path, required=True)
    release_sign.add_argument("--now-ms", type=int)
    release_sign.add_argument("--out", required=True)
    release_sign.add_argument("--store", required=True)
    release_sign.add_argument("--apply", action="store_true")
    release_sign.add_argument("--json", action="store_true")
    release_verify = release_verbs.add_parser("verify", help="Verify a signed release envelope")
    release_verify.add_argument("--envelope", required=True)
    release_verify.add_argument("--signer-public", required=True)
    release_verify.add_argument("--json", action="store_true")
    release_export = release_verbs.add_parser("export", help="Redacted roster release export")
    release_export.add_argument("--store", required=True)
    release_export.add_argument("--account", required=True)
    release_export.add_argument("--as-of")
    release_export.add_argument("--identities", action="store_true")
    release_export.add_argument("--json", action="store_true")
    release_metadata = release_verbs.add_parser(
        "metadata", help="Export the read-only production metadata selection"
    )
    production_export.add_arguments(release_metadata)
    release_status = release_verbs.add_parser(
        "status", help="Aggregated read-only operations status"
    )
    release_status.add_argument("--account")
    release_health = release_verbs.add_parser("health", help="Read-only operations health")
    release_health.add_argument("--account")
    chapter2 = release_verbs.add_parser(
        "chapter2", help="CWSA Chapter 2 acceptance gates and evidence projections (read-only)"
    )
    chapter2_sub = chapter2.add_subparsers(dest="policy", required=True)
    verify_cmd = chapter2_sub.add_parser("verify")
    verify_cmd.add_argument(
        "--stage", required=True, choices=("premerge", "predeploy", "postdeploy")
    )
    pm_cwsa_chapter2_gate.add_arguments(verify_cmd)
    projection_cmd = chapter2_sub.add_parser(
        "projection", help="Read-only redacted source and PM03 proof"
    )
    pm_cwsa_chapter2_gate.add_arguments(projection_cmd)
    projection_cmd.add_argument("--release-sha", required=True)
    explain_cmd = chapter2_sub.add_parser(
        "explain", help="Explain one portfolio's independent source and paper blockers"
    )
    explain_cmd.add_argument("--portfolio", required=True)
    explain_cmd.add_argument("--inspection", choices=("metadata", "evidence"), default="metadata")
    explain_cmd.add_argument(
        "--prior-snapshot",
        type=Path,
        help="Compare with one bounded prior JSON explanation of the same portfolio and inspection",
    )
    pm_cwsa_chapter2_gate.add_arguments(explain_cmd)
    site_cmd = chapter2_sub.add_parser(
        "site-view", help="Redacted authenticated-Site view of the CLI owner explanation"
    )
    site_cmd.add_argument("--portfolio", required=True)
    site_cmd.add_argument("--inspection", choices=("metadata", "evidence"), default="metadata")
    site_cmd.add_argument("--prior-snapshot", type=Path)
    pm_cwsa_chapter2_gate.add_arguments(site_cmd)
    recover_cmd = chapter2_sub.add_parser(
        "recover", help="Interpret an original Guardian intent using its read-only owner journal"
    )
    recover_cmd.add_argument("--guardian-journal", type=Path, required=True)
    recover_cmd.add_argument("--intent-id", required=True)
    recover_cmd.add_argument("--observed-at-ms", type=int, required=True)
    return p


def _live_leaf_failure(error_code: str, exc: Exception) -> int:
    """Print one bounded refusal envelope for a ported live parser and return exit 2."""
    print(
        json.dumps(
            {
                "state": "BLOCKED",
                "error_code": error_code,
                "error_type": type(exc).__name__,
                "detail": str(exc)[:300],
                "order_route": "NONE",
                "trading_authorized": False,
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 2


def _run_live_leaf(args: argparse.Namespace) -> int:
    """Dispatch a ported live parser to its owner handler through the reviewed --apply gate."""
    if args.group == "paper":
        if args.verb == "observe":
            if not (getattr(args, "apply", False) or getattr(args, "preflight_only", False)):
                return _live_leaf_failure(
                    "OBSERVER_APPLY_REQUIRED",
                    ValueError(
                        "pass --apply to start observation; --preflight-only and "
                        "--diagnose-preflight stay read-only"
                    ),
                )
            return pm_forward_observer.run(args)
        if args.verb == "observer-health":
            if args.watch and not getattr(args, "apply", False):
                return _live_leaf_failure(
                    "OBSERVER_WATCH_APPLY_REQUIRED",
                    ValueError("--watch appends private witness samples; pass --apply"),
                )
            return pm_forward_observer_health.run(args)
        return pm_forward_status.run(args)
    if args.verb == "market-audit":
        if not getattr(args, "apply", False):
            print(
                json.dumps(
                    {
                        "schema": "pm01_market_audit_plan_v1",
                        "state": "DRY_RUN",
                        "research_root": str(args.research_root),
                        "market_root": str(args.market_root),
                        "out": str(args.out),
                        "order_route": "NONE",
                        "trading_authorized": False,
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
            return 0
        return pm_market_audit.run(args)
    if (
        getattr(args, "record_root", None) is not None
        or getattr(args, "continuous_canary_seconds", None) is not None
    ) and not getattr(args, "apply", False):
        return _live_leaf_failure(
            "CCXT_PROBE_APPLY_REQUIRED",
            ValueError("a recorded canary writes a private journal; pass --apply"),
        )
    return pm_forward_ccxt_market.run(args)


def cli(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.group in ("facts", "roster"):
        from . import pm_roster_cli

        handler = {"facts": pm_roster_cli.run_facts, "roster": pm_roster_cli.run_roster}[args.group]
        return int(handler(args))
    if (args.group == "paper" and args.verb in ("observe", "observer-health", "run-status")) or (
        args.group == "research" and args.verb in ("market-audit", "ccxt-probe")
    ):
        # Ported live parsers keep their owner registration and handler; only the
        # reviewed --apply gate is added here.
        try:
            return _run_live_leaf(args)
        except (OSError, ValueError, FileNotFoundError) as exc:
            return _live_leaf_failure("LIVE_PARSER_REFUSED", exc)
    if args.group == "paper":
        from . import pm_roster_cli

        return int(pm_roster_cli.run_paper(args))
    if args.group == "research" and args.verb == "scorecards":
        from . import pm_roster_cli

        return int(pm_roster_cli.run_research(args))
    if args.group == "release":
        from . import pm_roster_cli

        if args.verb in ("propose", "sign", "verify", "export"):
            return int(pm_roster_cli.run_release(args))
        if args.verb == "metadata":
            from . import production_export

            return int(production_export.run(args))
    response = dispatch(args)
    print(json.dumps(response, sort_keys=True, indent=2))
    if args.group == "release" and args.verb == "chapter2":
        if args.policy == "projection":
            return 0
        if args.policy in ("explain", "site-view"):
            return 2 if response.get("error_code") else 0
        if args.policy == "recover":
            return 2 if response["dispatch_state"] == "EVIDENCE_UNAVAILABLE" else 0
        return {"PASS": 0, "BLOCKED_EVIDENCE": 2, "FAIL": 1}[response["verdict"]]
    if args.group == "capabilities":
        return 2 if response.get("status") in ("BLOCKED", "UNKNOWN") else 0
    if args.group == "research" and args.verb == "contracts":
        if response.get("status") == "BLOCKED":
            return 2
    if response.get("error_code"):
        return 2
    if response.get("status") == "UNKNOWN" and args.group not in ("release",):
        return 2
    return 0


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
