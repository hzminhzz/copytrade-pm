"""Evidence-aware, read-only repo-wide operator queries.

Registry, paper, research, release and PM-03 retain their own authorities.
This module only adapts their public read interfaces. It never imports a
writer or obtains broker access. Missing authorities are explicit UNKNOWN.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import UTC, datetime
import io
import json
from pathlib import Path
import subprocess
import sqlite3

from . import pm_capabilities as capabilities
from . import wallet_registry as registry

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
            limitations=["Registry freshness is index-only; not worker health or trading authority"]
            if status != "VERIFIED"
            else [],
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


def _release() -> dict:
    """Only the existing pinned-release verification is authoritative."""
    # Existing release verifier uses owner-private lock management; do not
    # cause a lock file write from an operational query. Report unknown here
    # until a truly non-mutating installed-state reader is available.
    return result(
        "release.installed",
        "UNKNOWN",
        authority="registry_release",
        error_code="RELEASE_VERIFY_IS_SEPARATE_OPERATION",
        limitations=["Run the existing scripts/registry_release.py verify explicitly"],
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


def _research(capability: str, run_id: str | None = None) -> dict:
    # No canonical enumerated research-run read API is registered yet;
    # scanning arbitrary files would synthesize a second untrusted catalog.
    return result(
        capability,
        "UNKNOWN",
        authority="immutable_research_artifacts",
        error_code="RESEARCH_RUN_CATALOG_NOT_AVAILABLE",
        limitations=[
            "No owner-backed run enumeration; do not confuse offline job manifests with executed runs",
            "Use the existing pm_offline_job interface for an explicitly provided sealed job",
        ],
        data={"run_id": run_id, "native_interface": "python -m copytrade_pm.pm_offline_job --help"},
    )


def _health(db: Path, root: Path) -> dict:
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
    parts["selection"] = _read_registry(db, ["portfolio", "--current"], "portfolio.current")
    parts["paper"] = _paper(db)
    parts["research"] = _research("research.list")
    parts["installed_release"] = _release()
    parts["market_provider"] = result(
        "market.health",
        "UNKNOWN",
        authority="native_market_provider",
        error_code="NO_INDEPENDENT_MARKET_HEALTH_OBSERVATION",
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
        return result(
            "wallet.list",
            "UNKNOWN",
            authority="wallet_registry",
            error_code="NO_UNREDACTED_WALLET_LIST_SURFACE",
            limitations=["Use the registry's cohort and alias operations"],
        )
    if args.group == "portfolios":
        if args.verb == "list":
            return _read_registry(db, ["portfolio"], "portfolio.list", args.asof)
        if args.verb == "current":
            return _read_registry(db, ["portfolio", "--current"], "portfolio.current", args.asof)
        return _read_registry(db, ["portfolio", args.id], "portfolio.show", args.asof)
    if args.group == "research":
        return _research("research." + args.verb, getattr(args, "id", None))
    if args.group == "paper":
        return _paper(db)
    return _health(db, args.root)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="copytrade-pm",
        description="Read-only agent-native capability discovery and operations",
    )
    p.add_argument("--db", type=Path, default=registry.DB)
    p.add_argument("--root", type=Path, default=ROOT)
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
    if response.get("error_code"):
        return 2
    if response.get("status") == "UNKNOWN" and args.group not in ("status", "health", "paper"):
        return 2
    return 0


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
