"""One CLI over the appliance and its independent state owners.

Parser construction imports only stdlib and declarative arguments. Discovery
can inspect the actual parser without importing providers, writers or secrets.
"""

from __future__ import annotations

from typing import Any

import argparse
import json
from pathlib import Path

from . import pm_health_arguments

ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = Path("~/.local/share/copytrade").expanduser()
ROSTER_DB = STATE_ROOT / "roster.sqlite"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="copytrade-pm",
        description=(
            "Single-owner Copytrade appliance: status, configuration, observation and paper"
        ),
    )
    p.add_argument(
        "--db",
        type=Path,
        default=ROSTER_DB,
        help="Roster SQLite: the only wallet/seat identity authority",
    )
    p.add_argument("--root", type=Path, default=ROOT)
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

    research = top.add_parser("research", help="Recorded research evidence")
    research_verbs = research.add_subparsers(dest="verb", required=True)
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
    roster_scorecard.add_argument("--failure", action="append")
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
    appliance = top.add_parser("appliance", help="One checkout, environment and systemd lifecycle")
    appliance_verbs = appliance.add_subparsers(dest="verb", required=True)
    for name in ("status", "reconcile", "recover", "update", "run", "adopt"):
        cmd = appliance_verbs.add_parser(name)
        cmd.add_argument("--state-root", type=Path, default=STATE_ROOT)
        cmd.add_argument("--json", action="store_true")
        if name != "status":
            cmd.add_argument("--apply", action="store_true")
        if name == "run":
            cmd.add_argument("role", choices=("source", "paper", "quotes", "health"))
            cmd.add_argument("--once", action="store_true")
        if name == "adopt":
            cmd.add_argument("--registry-snapshot", type=Path, required=True)
            cmd.add_argument("--sha256", required=True)
        if name == "update":
            cmd.add_argument("--candidate", type=Path, required=True)
            cmd.add_argument("--receipt", type=Path, required=True)
            cmd.add_argument(
                "--checkout", type=Path, help="Explicit active checkout for bootstrap updates"
            )
    return p


def cli(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.group == "capabilities":
        from . import pm_capabilities

        payload: dict[str, Any]
        if args.verb == "list":
            payload = {"capabilities": pm_capabilities.inventory()}
        elif args.verb == "validate":
            payload = pm_capabilities.validate()
        else:
            payload = next(
                (item for item in pm_capabilities.inventory() if item["id"] == args.id),
                {"status": "UNKNOWN", "error_code": "CAPABILITY_NOT_FOUND"},
            )
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 2 if payload.get("status") in ("BLOCKED", "UNKNOWN") else 0
    if args.group == "appliance":
        from .pm_appliance import run

        return run(args)
    from . import pm_roster_cli

    handlers = {
        "facts": pm_roster_cli.run_facts,
        "roster": pm_roster_cli.run_roster,
        "paper": pm_roster_cli.run_paper,
        "research": pm_roster_cli.run_research,
        "release": pm_roster_cli.run_release,
    }
    return int(handlers[args.group](args))


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
