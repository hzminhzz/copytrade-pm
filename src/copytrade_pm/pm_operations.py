"""Evidence-aware, read-only repo-wide operator queries.

Registry, paper, research, release and PM-03 retain their own authorities.
This module only adapts their public read interfaces. It never imports a
writer or obtains broker access. Missing authorities are explicit UNKNOWN.
"""

from __future__ import annotations

import argparse
from contextlib import closing, redirect_stdout
from datetime import UTC, datetime
import io
import json
from pathlib import Path
import subprocess
import sqlite3

from . import pm_capabilities as capabilities
from . import pm_runtime_readonly as runtime
from . import wallet_registry as registry
from . import wallet_registry_catalog as catalog
from .pm_offline_job_catalog import list_reports

SCHEMA = "copytrade_read_result_v1"
ROOT = Path(__file__).resolve().parents[2]
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


def _registry_query(db: Path, command: list[str]) -> object:
    """Invoke existing registry CLI without shelling out or modifying sources."""
    sink = io.StringIO()
    with redirect_stdout(sink):
        code = registry.cli(["--db", str(db), *command])
    if code != 0:
        raise ValueError("AUTHORITATIVE_QUERY_UNAVAILABLE")
    return json.loads(sink.getvalue())


def _generation(db: Path) -> dict:
    info = _registry_query(db, ["status"])
    return {
        "status": info["freshness"],
        "sha": info["generation"]["manifest_sha256"],
        "observed_at": info["generation"]["observed_at"],
        "counts": info["counts"],
    }


def _doctor(db: Path) -> dict:
    """Verify authoritative SQLite integrity; external imports are diagnostic."""
    try:
        sink = io.StringIO()
        with redirect_stdout(sink):
            code = registry.cli(["--db", str(db), "doctor"])
        payload = json.loads(sink.getvalue())
        if (
            code == 0
            and payload.get("authority") == "SQLITE"
            and payload.get("database_integrity") == "VERIFIED"
        ):
            state = "VERIFIED"
        elif code == 2 and payload.get("error_type") == "OperationalError":
            state = "UNKNOWN"  # Missing/unavailable DB is not a stale SQLite snapshot.
        elif code == 2 or payload.get("database_integrity") == "FAILED":
            state = "STALE"
        else:
            state = "UNKNOWN"
        # The native doctor does not report a stored index generation clock;
        # that belongs to the independent status query.
        return result(
            "registry.doctor",
            state,
            {
                "database_integrity": payload.get("database_integrity"),
                "inventory_sha256": payload.get("inventory_sha256"),
                "indexed_import_clock_freshness": payload.get("indexed_import_clock_freshness"),
                "unverified_cohort_import_provenance": payload.get(
                    "unverified_cohort_import_provenance", []
                ),
            },
            authority="sqlite_wallet_registry",
            error_code="REGISTRY_SQLITE_INTEGRITY_FAILED" if state == "STALE" else None,
        )
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, sqlite3.Error) as exc:
        return result(
            "registry.doctor",
            "UNKNOWN",
            authority="sqlite_wallet_registry",
            error_code="REGISTRY_DOCTOR_UNAVAILABLE",
            limitations=[type(exc).__name__],
        )


def _read_registry(db: Path, command: list[str], capability: str, asof: str | None = None) -> dict:
    try:
        gen = _generation(db)
        args = [*command]
        if asof:
            args.extend(["--asof", asof])
        payload = _registry_query(db, args)
        status = "STALE" if gen["status"] != "CURRENT" else "VERIFIED"
        if command[:2] == ["portfolio", "--current"]:
            if payload.get("selection_state") in (
                "NOT_REGISTERED_AT_ASOF",
                "SCHEMA_UPGRADE_REQUIRED",
            ):
                status = payload["selection_state"]
        elif command and command[0] == "portfolio" and len(command) > 1:
            record = next(iter(payload.values()), {})
            if record.get("status") in ("UNKNOWN_AT_ASOF", "NOT_REGISTERED_AT_ASOF"):
                status = "NOT_REGISTERED_AT_ASOF"
        elif command and command[0] == "wallet" and not payload.get("found"):
            status = "NOT_REGISTERED_AT_ASOF"
        return result(
            capability,
            status,
            payload,
            authority="wallet_registry",
            version="sqlite_v8",
            sha256=gen["sha"],
            source_observed_at=gen["observed_at"],
            limitations=[
                "Indexed freshness is based on the stored generation clock; run doctor for live source parity",
                "Registry identity/read success does not establish worker health or trading authority",
            ],
        )
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, sqlite3.Error) as exc:
        return result(
            capability,
            "UNKNOWN",
            authority="wallet_registry",
            error_code="REGISTRY_READ_FAILED",
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
            "Only the pinned owner-private registry, not paper or broker services, was verified"
        ],
    )


def _paper(db: Path) -> dict:
    observed = _read_registry(db, ["paper"], "paper.status")
    if observed["status"] in ("VERIFIED", "STALE"):
        payload = observed["data"]
        records = payload.get("observations", [])
        if records:
            # Native registered_paper_status rechecks journals and liveness.
            statuses = [x.get("state", "UNKNOWN") for x in records]
            observed["status"] = (
                "NOT_RUNNING"
                if all(x == "NOT_RUNNING" for x in statuses)
                else "DEGRADED"
                if "DEGRADED" in statuses
                else "UNKNOWN"
            )
        else:
            observed["status"] = "UNKNOWN"
            observed["limitations"].append(
                "Zero indexed paper runs does not establish global worker absence"
            )
    return observed


def _wallets(db: Path, args: argparse.Namespace) -> dict:
    try:
        generation = _generation(db)
        cutoff = registry.asof_cutoff(args.asof)
        with closing(registry.connect(db, False)) as con:
            payload = catalog.list_wallets(
                con,
                cutoff,
                query=args.query,
                cohort=args.cohort,
                excluded=args.excluded,
                subscribed=args.subscribed,
                limit=args.limit,
                offset=args.offset,
            )
        return result(
            "wallet.list",
            "VERIFIED" if generation["status"] == "CURRENT" else "STALE",
            payload,
            authority="wallet_registry",
            version="sqlite_v8",
            sha256=generation["sha"],
            source_observed_at=generation["observed_at"],
            limitations=[
                "Indexed wallet attributes are source snapshots, not real-time equity or first-known trade receipts",
                "Run registry doctor separately for live source parity",
            ],
        )
    except (ValueError, OSError, RuntimeError, sqlite3.Error, KeyError, TypeError) as exc:
        return result(
            "wallet.list",
            "UNKNOWN",
            authority="wallet_registry",
            error_code="WALLET_INVENTORY_READ_FAILED",
            limitations=[type(exc).__name__],
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


def _health(db: Path, root: Path, observer_root: Path | None = None) -> dict:
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
    parts["registry"] = _read_registry(db, ["status"], "registry.status")
    parts["registry_source_parity"] = _doctor(db)
    if parts["registry_source_parity"]["status"] != "VERIFIED":
        # Cached indexed freshness is not an independently current source.
        parts["registry"]["status"] = parts["registry_source_parity"]["status"]
    parts["selection"] = _read_registry(db, ["portfolio", "--current"], "portfolio.current")
    parts["paper"] = _paper(db)
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
    if args.group == "wallets":
        if args.verb == "show":
            return _read_registry(db, ["wallet", "--alias", args.id], "wallet.lookup", args.asof)
        return _wallets(db, args)
    if args.group == "portfolios":
        if args.verb == "list":
            return _read_registry(db, ["portfolio"], "portfolio.list", args.asof)
        if args.verb == "current":
            return _read_registry(db, ["portfolio", "--current"], "portfolio.current", args.asof)
        return _read_registry(db, ["portfolio", args.id], "portfolio.show", args.asof)
    if args.group == "research":
        return _research(
            "research." + args.verb,
            getattr(args, "id", None),
            cache_root=args.cache_root,
            cache_key=args.cache_key,
            limit=args.limit,
            offset=args.offset,
        )
    if args.group == "contracts":
        from .pm_contract_selector import compare_portfolios, rules_catalog

        if args.verb == "rules":
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
    if args.group == "paper":
        return _paper(db)
    return _health(db, args.root, args.observer_state_root)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="copytrade-pm",
        description="Read-only agent-native capability discovery and operations",
    )
    p.add_argument("--db", type=Path, default=registry.DB)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--observer-state-root", type=Path)
    top = p.add_subparsers(dest="group", required=True)
    cap = top.add_parser("capabilities")
    sub = cap.add_subparsers(dest="verb", required=True)
    cap_list = sub.add_parser("list")
    cap_list.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    cap_validate = sub.add_parser("validate")
    cap_validate.add_argument("--json", action="store_true")
    for domain in ("wallets", "portfolios", "research", "paper"):
        node = top.add_parser(domain)
        verbs = node.add_subparsers(dest="verb", required=True)
        for op in {
            "wallets": ("list", "show"),
            "portfolios": ("list", "current", "show"),
            "research": ("list", "show"),
            "paper": ("status",),
        }[domain]:
            operation = verbs.add_parser(op)
            if op == "show":
                operation.add_argument("id")
            if domain in ("wallets", "portfolios"):
                operation.add_argument("--asof")
            if domain == "wallets" and op == "list":
                operation.add_argument("--query")
                operation.add_argument("--cohort")
                operation.add_argument("--excluded", action=argparse.BooleanOptionalAction)
                operation.add_argument("--subscribed", action=argparse.BooleanOptionalAction)
                operation.add_argument("--limit", type=int, default=100)
                operation.add_argument("--offset", type=int, default=0)
            if domain == "research":
                operation.add_argument("--cache-root", type=Path)
                operation.add_argument("--cache-key")
                operation.add_argument("--limit", type=int, default=100)
                operation.add_argument("--offset", type=int, default=0)
    contracts = top.add_parser("contracts", help="Read-only pod portfolio x contract EV screening")
    contract_verbs = contracts.add_subparsers(dest="verb", required=True)
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
    top.add_parser("status")
    top.add_parser("health")
    return p


def cli(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    response = dispatch(args)
    print(json.dumps(response, sort_keys=True, indent=2))
    if args.group == "capabilities":
        return 2 if response.get("status") in ("BLOCKED", "UNKNOWN") else 0
    if args.group == "contracts" and response.get("status") == "BLOCKED":
        return 2
    if response.get("error_code"):
        return 2
    if response.get("status") == "UNKNOWN" and args.group not in ("status", "health", "paper"):
        return 2
    return 0


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
