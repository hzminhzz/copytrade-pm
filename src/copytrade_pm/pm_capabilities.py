"""Reviewed native capability directory; descriptive only, never an authorization engine.

CLI entry points are discovered from installed distribution metadata (with
pyproject fallback for source-only checkouts). Every entry point must have
reviewed operation metadata; unknown operations fail closed.
"""

from __future__ import annotations

from importlib import metadata
import ast
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]
DOC = "docs/AGENT-NATIVE-OPERATIONS.md"
CLASSES = frozenset({"READ_ONLY", "LOCAL_MUTATION", "PROTECTED_MUTATION", "BROKER_OR_TRADING"})
# Classifications describe the exposed DEFAULT entry point; subcommands have
# their own reviewed records. Never infer safety from a command name.
GROUPS = {
    "copytrade-pm-production-export": ("production.export.cli", "registry", "LOCAL_MUTATION"),
    "copytrade-pm-production-manifest": (
        "production.manifest.cli",
        "registry",
        "PROTECTED_MUTATION",
    ),
    "copytrade-pm-production-economics": ("production.economics.cli", "research", "READ_ONLY"),
    "copytrade-pm-track-b-prefect": ("research.track_b_prefect", "research", "LOCAL_MUTATION"),
    "copytrade-pm-replay": ("historical.replay", "historical", "LOCAL_MUTATION"),
    "copytrade-pm-rank": ("manager.rank", "qualification", "LOCAL_MUTATION"),
    "copytrade-pm-handoff": ("portfolio.handoff", "portfolio", "LOCAL_MUTATION"),
    "copytrade-pm-scope": ("market.scope", "market", "LOCAL_MUTATION"),
    "copytrade-pm-market-audit": ("market.audit", "market", "LOCAL_MUTATION"),
    "copytrade-pm-research": ("research.pm01", "research", "LOCAL_MUTATION"),
    "copytrade-pm-actuary": ("research.actuary.cli", "research", "READ_ONLY"),
    "copytrade-pm-shadow": ("account.pm03.simulate", "account", "LOCAL_MUTATION"),
    "copytrade-pm-receipts": ("source.receipts", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-source": ("source.e4", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-source-abc": ("source.rotation", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-source-audit": ("source.audit", "source", "READ_ONLY"),
    "copytrade-pm-combo2-paper": ("paper.combo2", "paper", "LOCAL_MUTATION"),
    "copytrade-wallet-registry": ("registry.cli", "registry", "PROTECTED_MUTATION"),
    "copytrade-pm-review-gate": ("qualification.review", "qualification", "READ_ONLY"),
    "copytrade-pm-paper-status": ("paper.journal_status", "paper", "READ_ONLY"),
    "copytrade-pm-paper-report": ("paper.report", "paper", "READ_ONLY"),
    "copytrade-pm-paper-preflight": ("paper.preflight", "paper", "READ_ONLY"),
    "copytrade-pm-paper-candidate-verify": ("paper.release_candidate", "paper", "READ_ONLY"),
    "copytrade-pm-market-ccxt": ("market.ccxt", "market", "PROTECTED_MUTATION"),
    "copytrade-pm-market-stream": ("market.stream", "market", "PROTECTED_MUTATION"),
    "copytrade-pm-public-trades": ("source.public_trades", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-source-scope": ("source.scope", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-watchdog": ("paper.watchdog", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-standby": ("paper.standby", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-unit-bundle": ("paper.unit_bundle", "paper", "LOCAL_MUTATION"),
    "copytrade-pm-paper-registry-audit": ("paper.identity", "paper", "READ_ONLY"),
    "copytrade-pm-paper-readiness": ("paper.readiness", "paper", "READ_ONLY"),
    "copytrade-pm-paper-source-campaign": ("paper.source_campaign", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-observe": ("paper.observer", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-observed": ("paper.observed_execution", "paper", "LOCAL_MUTATION"),
    "copytrade-pm-vike-minute": ("market.vike_minute", "market", "LOCAL_MUTATION"),
    "copytrade-pm-vike-fills": ("source.vike_selected_fills", "source", "LOCAL_MUTATION"),
    "copytrade-pm-paper-observer-health": ("paper.observer_health", "paper", "READ_ONLY"),
    "copytrade-pm-public-observer-unit": ("paper.public_unit", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm": ("operations.cli", "operations", "READ_ONLY"),
    "copytrade-pm-agent-eval": ("agent.trace.eval", "operations", "READ_ONLY"),
}
# These are reviewed, individual operations, not default safety assertions
# for the broader parent executable. No subcommand inherits READ_ONLY.
REGISTRY_OPERATIONS = {
    "status": "READ_ONLY",
    "native status": "READ_ONLY",
    "native lock": "READ_ONLY",
    "native lock --apply": "PROTECTED_MUTATION",
    "native register": "READ_ONLY",
    "native register --apply": "PROTECTED_MUTATION",
    "native exclude": "READ_ONLY",
    "native exclude --apply": "PROTECTED_MUTATION",
    "doctor": "READ_ONLY",
    "runtime": "READ_ONLY",
    "report --redacted": "READ_ONLY",
    "wallet --alias": "READ_ONLY",
    "wallet --address": "READ_ONLY",
    "cohort": "READ_ONLY",
    "portfolio": "READ_ONLY",
    "portfolio --current": "READ_ONLY",
    "paper": "READ_ONLY",
    "qualification": "READ_ONLY",
    "sync --dry-run": "READ_ONLY",
    "sync --apply": "PROTECTED_MUTATION",
    "backup --to": "LOCAL_MUTATION",
    "paper --apply": "PROTECTED_MUTATION",
    "qualification --apply": "PROTECTED_MUTATION",
    "signed-selection": "READ_ONLY",
    "signed-selection --apply": "PROTECTED_MUTATION",
}
NATIVE = {
    "production.metadata": (
        "copytrade_pm.production_export",
        "python -m copytrade_pm.production_export --help",
        "registry",
        "READ_ONLY",
        "CONSISTENT_SQLITE_SNAPSHOT_SCOPE_REQUIRED_LEGACY_NAV_ONLY",
    ),
    "production.release": (
        "copytrade_pm.production_manifest",
        "python -m copytrade_pm.production_manifest --help",
        "registry",
        "PROTECTED_MUTATION",
        "INDEPENDENT_SIGNED_SQLITE_POLICY_AND_SOURCE_SCOPE_REQUIRED",
    ),
    "production.economics": (
        "copytrade_pm.production_economics",
        "python -m copytrade_pm.production_economics --help",
        "research",
        "READ_ONLY",
        "MATCHED_PREDECLARED_NET_FOLLOWER_POLICY_TAPES_REQUIRED",
    ),
    "wallet.inventory": (
        "copytrade_pm.wallet_registry_catalog",
        "copytrade-pm wallets list --cohort research-108",
        "registry",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "research.report.catalog": (
        "copytrade_pm.pm_offline_job_catalog",
        "copytrade-pm research list --cache-root PRIVATE_CACHE",
        "research",
        "READ_ONLY",
        "SHA_VERIFIED_OFFLINE_JOB_REPORT_CACHE",
    ),
    "runtime.pinned_release": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm health",
        "operations",
        "READ_ONLY",
        "PINNED_REGISTRY_RELEASE_VERIFIER",
    ),
    "runtime.paper_units": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm health",
        "paper",
        "READ_ONLY",
        "SYSTEMD_USER_UNIT_INVENTORY",
    ),
    "runtime.market_observer": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm --observer-state-root STATE_ROOT health",
        "market",
        "READ_ONLY",
        "PUBLIC_OBSERVER_RECEIPT_EVIDENCE",
    ),
    "wallet.lookup": (
        "copytrade_pm.wallet_registry",
        "copytrade-pm wallets show W083",
        "registry",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "wallet.alias": (
        "copytrade_pm.wallet_registry_catalog",
        "copytrade-pm wallets show W083",
        "registry",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "portfolio.current": (
        "copytrade_pm.wallet_registry_catalog",
        "copytrade-pm portfolios current",
        "portfolio",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "portfolio.show": (
        "copytrade_pm.wallet_registry_portfolios",
        "copytrade-pm portfolios show E6",
        "portfolio",
        "READ_ONLY",
        "SEALED_PORTFOLIO_REGISTRY",
    ),
    "registry.doctor": (
        "copytrade_pm.wallet_registry",
        "copytrade-pm health",
        "registry",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "paper.status": (
        "copytrade_pm.wallet_registry_runs",
        "copytrade-pm paper status",
        "paper",
        "READ_ONLY",
        "INDEPENDENT_JOURNAL_AND_WORKER",
    ),
    "paper.account": (
        "copytrade_pm.pm_forward_journal",
        "copytrade-pm-paper-status --help",
        "paper",
        "READ_ONLY",
        "PM03_FINANCIAL_JOURNAL",
    ),
    "paper.identity_reseal_preview": (
        "copytrade_pm.pm_forward_registry_identity",
        "copytrade-pm-paper-registry-audit --prospective-reseal-preview --portfolio P1",
        "paper",
        "READ_ONLY",
        "UNSIGNED_ASOF_ALIAS_MATCH_ONLY_NOT_PAPER_ADMISSION",
    ),
    "research.offline": (
        "copytrade_pm.pm_offline_job",
        "python -m copytrade_pm.pm_offline_job --help",
        "research",
        "LOCAL_MUTATION",
        "IMMUTABLE_RESEARCH_REPORT",
    ),
    "research.catalog": (
        "copytrade_pm.pm_offline_repository",
        "copytrade-pm research list",
        "research",
        "READ_ONLY",
        "RESEARCH_ARTIFACTS",
    ),
    "research.polars": (
        "copytrade_pm.pm_offline_market",
        "python -m copytrade_pm.pm_offline_job --help",
        "research",
        "READ_ONLY",
        "NATIVE_MINUTE_MARKET_LAKE",
    ),
    "research.contract_selector": (
        "copytrade_pm.pm_contract_selector",
        "copytrade-pm contracts compare --portfolio gemini.phase4/E6",
        "research",
        "READ_ONLY",
        "SEALED_PORTFOLIO_AND_FULL_NET_FOLLOWER_TAPE_REQUIRED",
    ),
    "research.actuary": (
        "copytrade_pm.contract_actuary",
        "copytrade-pm-actuary --help",
        "research",
        "READ_ONLY",
        "SYNTHETIC_CONTRACT_SCENARIO_NOT_FINANCIAL_AUTHORITY",
    ),
    "research.sweep": (
        "copytrade_pm.pm_offline_sweep",
        "python -m copytrade_pm.pm_offline_job --help",
        "research",
        "LOCAL_MUTATION",
        "IMMUTABLE_RESEARCH_REPORT",
    ),
    "account.pm03": (
        "copytrade_pm.pm03_account",
        "copytrade-pm capabilities show account.pm03",
        "account",
        "LOCAL_MUTATION",
        "PM03_FINANCIAL_AUTHORITY",
    ),
    "account.execution": (
        "copytrade_pm.pm03_execution",
        "copytrade-pm capabilities show account.execution",
        "account",
        "LOCAL_MUTATION",
        "PM03_FINANCIAL_AUTHORITY",
    ),
    "source.collection": (
        "copytrade_pm.pm_forward_source_stream",
        "copytrade-pm capabilities show source.collection",
        "source",
        "PROTECTED_MUTATION",
        "PROSPECTIVE_SOURCE_RECEIPTS",
    ),
    "market.native": (
        "copytrade_pm.pm_shadow",
        "copytrade-pm-market-audit --help",
        "market",
        "READ_ONLY",
        "VERIFIED_NATIVE_MINUTE_DATA",
    ),
    "qualification.science": (
        "copytrade_pm.wallet_registry_qualification",
        "copytrade-wallet-registry qualification",
        "qualification",
        "READ_ONLY",
        "SIGNED_QUALIFICATION_EVIDENCE",
    ),
    "release.verify": (
        "scripts/registry_release.py",
        "python scripts/registry_release.py verify",
        "operations",
        "READ_ONLY",
        "PINNED_INSTALLED_RELEASE",
    ),
    "runtime.health": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm health",
        "operations",
        "READ_ONLY",
        "INDEPENDENT_RUNTIME_OBSERVATIONS",
    ),
    "source.exclusions": (
        "copytrade_pm.wallet_registry",
        "copytrade-wallet-registry status",
        "registry",
        "READ_ONLY",
        "PRIVATE_VERSIONED_WALLET_REGISTRY",
    ),
    "pm04.batching": (
        "copytrade_pm.pm04_shadow",
        "copytrade-pm capabilities show pm04.batching",
        "account",
        "LOCAL_MUTATION",
        "PM03_PM04_SHADOW_ACCOUNT",
    ),
    "paper.observer.preflight": (
        "copytrade_pm.pm_forward_continuous",
        "copytrade-pm-paper-observe --continuous-config CONFIG --preflight-only",
        "paper",
        "READ_ONLY",
        "PINNED_REGISTRY_AND_ISOLATED_OBSERVER_PREFLIGHT",
    ),
    "paper.observer.continuous": (
        "copytrade_pm.pm_forward_continuous",
        "copytrade-pm-paper-observe --continuous-config CONFIG",
        "paper",
        "PROTECTED_MUTATION",
        "PUBLIC_ONLY_CONTINUOUS_OBSERVATION_JOURNAL",
    ),
    "paper.observer.continuous_health": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm-paper-observer-health --continuous --state-root ROOT",
        "paper",
        "READ_ONLY",
        "INDEPENDENT_STREAM_AND_PROCESS_EVIDENCE",
    ),
    "paper.observer.continuous_watchdog": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm-paper-observer-health --continuous --watch --state-root ROOT",
        "paper",
        "LOCAL_MUTATION",
        "INDEPENDENT_PRIVATE_WATCHDOG_HISTORY",
    ),
    "paper.observer.shadow_report": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm-paper-observer-health --shadow-report --state-root ROOT",
        "paper",
        "READ_ONLY",
        "ACTUAL_WATCHDOG_WINDOW_AND_RECEIPT_CHAINS",
    ),
    "market.continuous_canary": (
        "copytrade_pm.pm_forward_ccxt_market",
        "copytrade-pm-market-ccxt --continuous-canary-seconds 135 --record-root ROOT",
        "market",
        "PROTECTED_MUTATION",
        "BOUNDED_PUBLIC_MARKET_TRANSPORT_ONLY",
    ),
    "recovery.guide": (
        "docs/BLOCKER-RECOVERY.md",
        "copytrade-pm capabilities show recovery.guide",
        "operations",
        "READ_ONLY",
        "REPOSITORY_RUNBOOK",
    ),
}
DOCS = {
    "registry": "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
    "portfolio": "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
    "paper": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
    "account": "docs/PM-03-shadow-account.md",
    "market": "docs/DATA-ACQUISITION.md",
    "research": "docs/RUNBOOK.md",
    "source": "docs/DATA-ACQUISITION.md",
    "qualification": "docs/QUALIFICATION.md",
    "operations": DOC,
    "historical": "docs/RUNBOOK.md",
}
REGISTRY_REQUIRED_ARGUMENTS = {
    "native lock": ["--expected-inventory-sha SHA256"],
    "native lock --apply": ["--expected-inventory-sha SHA256"],
    "native register": ["--manifest PRIVATE_PATH", "--expected-inventory-sha SHA256"],
    "native register --apply": ["--manifest PRIVATE_PATH", "--expected-inventory-sha SHA256"],
    "native exclude": [
        "--expected-inventory-sha SHA256",
        "--expected-manifest-sha SHA256",
        "--manifest PRIVATE_PATH",
    ],
    "native exclude --apply": [
        "--expected-inventory-sha SHA256",
        "--expected-manifest-sha SHA256",
        "--manifest PRIVATE_PATH",
    ],
    "wallet --alias": ["--alias ALIAS"],
    "wallet --address": ["--address ADDRESS"],
    "cohort": ["NAME"],
    "backup --to": ["--to PATH"],
    "paper --apply": ["--run-dir PATH", "--portfolio NAME"],
    "signed-selection": [
        "--manifest PATH",
        "--signature PATH",
        "--trusted-public-key PATH",
        "--trusted-key-sha256 SHA256",
    ],
    "signed-selection --apply": [
        "--manifest PATH",
        "--signature PATH",
        "--trusted-public-key PATH",
        "--trusted-key-sha256 SHA256",
    ],
    "qualification --apply": [
        "--attestation-file PATH",
        "--evidence-file PATH",
        "--auditor-public-key-file PATH",
    ],
}
# Dispatch-enforced requirements for --apply modes whose flags are optional at
# argparse parse time because the preview/list mode omits them.
REGISTRY_DISPATCH_REQUIRED_ARGUMENTS = {
    "paper --apply": ("--run-dir", "--portfolio"),
    "qualification --apply": (
        "--attestation-file",
        "--evidence-file",
        "--auditor-public-key-file",
    ),
}
UNKNOWN_ACCESS = {
    "read_targets": "UNKNOWN",
    "write_targets": "UNKNOWN",
    "network": "UNKNOWN",
    "credentials": "UNKNOWN",
    "privacy": "UNKNOWN",
}


def _registry_access_entry(
    read_targets: list[str],
    write_targets: list[str],
    *,
    privacy: str = "OWNER_PRIVATE_REDACTED",
) -> dict[str, object]:
    return {
        "read_targets": read_targets,
        "write_targets": write_targets,
        "network": False,
        "credentials": False,
        "privacy": privacy,
    }


REGISTRY_ACCESS = {
    "status": _registry_access_entry(
        ["private_sqlite_registry", "optional_private_paper_journal", "decision_repo"],
        [],
    ),
    "native status": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive"],
        [],
    ),
    "native lock": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive"],
        [],
    ),
    "native lock --apply": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive"],
        ["private_sqlite_registry", "private_sqlite_backup"],
    ),
    "native register": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive", "private_cohort_manifest"],
        [],
    ),
    "native register --apply": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive", "private_cohort_manifest"],
        ["private_sqlite_registry", "private_sqlite_backup", "private_evidence_archive"],
    ),
    "native exclude": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive", "private_exclusion_manifest"],
        [],
    ),
    "native exclude --apply": _registry_access_entry(
        ["private_sqlite_registry", "private_evidence_archive", "private_exclusion_manifest"],
        ["private_sqlite_registry", "private_sqlite_backup", "private_evidence_archive"],
    ),
    "doctor": _registry_access_entry(
        [
            "private_sqlite_registry",
            "private_evidence_archive",
            "optional_private_paper_journal",
            "decision_repo",
            "optional_legacy_import_sources",
            "optional_tracker_env_config",
            "optional_tracker_subscription_sqlite",
            "optional_observation_ledger_sqlite",
        ],
        [],
    ),
    "runtime": _registry_access_entry(
        ["tracker_env_config", "tracker_subscription_sqlite", "observation_ledger_sqlite"],
        [],
    ),
    "backup --to": _registry_access_entry(
        ["private_sqlite_registry"],
        ["private_sqlite_backup"],
        privacy="OWNER_PRIVATE",
    ),
    "report --redacted": _registry_access_entry(
        ["private_sqlite_registry", "optional_private_paper_journal", "decision_repo"],
        [],
    ),
    "wallet --alias": _registry_access_entry(["private_sqlite_registry"], []),
    "wallet --address": _registry_access_entry(["private_sqlite_registry"], []),
    "cohort": _registry_access_entry(["private_sqlite_registry"], []),
    "portfolio": _registry_access_entry(["private_sqlite_registry", "decision_repo"], []),
    "portfolio --current": _registry_access_entry(
        ["private_sqlite_registry", "decision_repo"],
        [],
    ),
    "paper": _registry_access_entry(
        ["private_sqlite_registry", "decision_repo", "optional_private_paper_journal"],
        [],
    ),
    "paper --apply": _registry_access_entry(
        ["private_sqlite_registry", "decision_repo", "private_paper_journal"],
        ["private_sqlite_registry"],
    ),
    "qualification": _registry_access_entry(
        [
            "private_sqlite_registry",
            "optional_signed_negative_evidence",
            "optional_auditor_public_key",
        ],
        [],
    ),
    "qualification --apply": _registry_access_entry(
        ["private_sqlite_registry", "signed_negative_evidence", "auditor_public_key"],
        ["private_sqlite_registry"],
    ),
    "sync --dry-run": _registry_access_entry(
        [
            "legacy_import_sources",
            "tracker_env_config",
            "tracker_subscription_sqlite",
            "observation_ledger_sqlite",
            "decision_repo",
        ],
        [],
    ),
    "sync --apply": _registry_access_entry(
        [
            "private_sqlite_registry",
            "legacy_import_sources",
            "tracker_env_config",
            "tracker_subscription_sqlite",
            "observation_ledger_sqlite",
            "decision_repo",
        ],
        ["private_sqlite_registry"],
    ),
    "signed-selection": _registry_access_entry(
        ["signed_selection_manifest", "detached_signature", "trusted_public_key"],
        [],
    ),
    "signed-selection --apply": _registry_access_entry(
        [
            "private_sqlite_registry",
            "signed_selection_manifest",
            "detached_signature",
            "trusted_public_key",
        ],
        ["private_sqlite_registry", "private_sqlite_backup"],
    ),
}
NATIVE_REQUIRED_ARGUMENTS = {
    "wallet.inventory": [],
    "research.report.catalog": ["--cache-root PATH"],
    "research.contract_selector": ["--portfolio NAMESPACE/ID", "--tape PRIVATE_TAPE"],
    "runtime.pinned_release": [],
    "runtime.paper_units": [],
    "runtime.market_observer": ["--observer-state-root PATH"],
    "wallet.lookup": ["ALIAS"],
    "wallet.alias": ["ALIAS"],
    "portfolio.show": ["PORTFOLIO"],
    "research.offline": ["JOB", "--input-root PATH", "--market-root PATH", "--cache-root PATH"],
}
EXTRA_MODULES = {
    "pm_offline_benchmark": ("research.benchmark", "research", "LOCAL_MUTATION"),
    "pm_offline_hot_market": ("market.hot_week", "market", "LOCAL_MUTATION"),
    "pm_forward_admission": ("paper.admission", "paper", "READ_ONLY"),
    "pm_forward_readiness": ("paper.source_readiness", "paper", "READ_ONLY"),
    "pm_forward_journal": ("paper.journal", "paper", "LOCAL_MUTATION"),
    "pm03_account": ("account.financial", "account", "LOCAL_MUTATION"),
    "pm03_execution": ("account.fill", "account", "LOCAL_MUTATION"),
    "wallet_registry": ("registry.owner", "registry", "PROTECTED_MUTATION"),
    "wallet_registry_catalog": ("registry.selection", "registry", "READ_ONLY"),
    "wallet_registry_portfolios": ("registry.portfolio", "registry", "READ_ONLY"),
}


def _declared_scripts(root: Path) -> dict[str, str]:
    return tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]


def _installed_scripts() -> dict[str, str]:
    try:
        dist = metadata.distribution("copytrade-pm")
    except metadata.PackageNotFoundError:
        return {}
    return {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}


def _required_cli_args(module: str, root: Path) -> list[str] | None:
    """Derive mandatory flat argparse flags/positionals from actual implementation.

    Nested subparsers have operation-dependent requirements: return None rather
    than incorrectly describe a parent CLI as requiring no arguments.
    """
    path = (root / "src" / Path(*module.split("."))).with_suffix(".py")
    if not path.is_file():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_subparsers":
                return None
    required = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument" or not node.args:
            continue
        value = node.args[0]
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        option = value.value
        flags = {keyword.arg: keyword.value for keyword in node.keywords}
        mandatory_flag = isinstance(flags.get("required"), ast.Constant) and (
            flags["required"].value is True
        )
        positional = not option.startswith("-") and not (
            isinstance(flags.get("nargs"), ast.Constant) and flags["nargs"].value in ("?", "*")
        )
        if mandatory_flag or positional:
            required.add(option)
    return sorted(required)


def _module_available(module: str, root: Path) -> bool:
    if module.startswith("docs/") or module.startswith("scripts/"):
        return (root / module).is_file()
    return (root / "src" / Path(*module.split("."))).with_suffix(".py").is_file()


def _copy_access(entry: dict[str, object]) -> dict[str, object]:
    return {key: list(value) if isinstance(value, list) else value for key, value in entry.items()}


def inventory(root: Path = ROOT) -> list[dict]:
    scripts = _declared_scripts(root)
    installed = _installed_scripts()
    results = []
    for name, invocation in sorted(scripts.items()):
        descriptor = GROUPS.get(name)
        capability, family, safety = (
            descriptor if descriptor else (f"unclassified.{name}", "operations", "UNCLASSIFIED")
        )
        module = invocation.split(":", 1)[0]
        results.append(
            {
                "id": capability,
                "schema_version": 1,
                "kind": "CLI",
                "description": f"Existing {family} command",
                "owner": module,
                "interface": name,
                "entry_point": invocation,
                "classification": safety,
                "authority": family.upper(),
                "access": _copy_access(UNKNOWN_ACCESS),
                "dependencies": [],
                "required_arguments": _required_cli_args(module, root),
                "preflight": [],
                "documentation": (
                    "docs/TRACK-B-PREFECT-ORCHESTRATION-20261110.md"
                    if capability == "research.track_b_prefect"
                    else DOCS[family]
                ),
                "available": _module_available(module, root)
                and (name not in installed or installed[name] == invocation),
                "limitations": [
                    "Review flags/subcommands before running; discovery is not authorization"
                ],
                "evidence_freshness": "VERIFY_ON_USE",
            }
        )
    for op, safety in sorted(REGISTRY_OPERATIONS.items()):
        results.append(
            {
                "id": "registry.operation." + re.sub(r"[^a-z0-9]+", ".", op).strip("."),
                "schema_version": 1,
                "kind": "SUBCOMMAND",
                "description": "Reviewed registry operation",
                "owner": "copytrade_pm.wallet_registry",
                "interface": "copytrade-wallet-registry " + op,
                "classification": safety,
                "authority": "PRIVATE_VERSIONED_WALLET_REGISTRY",
                "access": _copy_access(REGISTRY_ACCESS.get(op, UNKNOWN_ACCESS)),
                "dependencies": [],
                "required_arguments": REGISTRY_REQUIRED_ARGUMENTS.get(op, []),
                "preflight": ["registry.doctor"] if op not in ("doctor", "status") else [],
                "documentation": DOCS["registry"],
                "available": True,
                "limitations": ["Protect owner-private input and output"],
                "evidence_freshness": "VERIFY_ON_USE",
            }
        )
    for cap, (module, invocation, family, safety, authority) in NATIVE.items():
        results.append(
            {
                "id": cap,
                "schema_version": 1,
                "kind": "NATIVE",
                "description": f"Native {family} interface",
                "owner": module,
                "interface": invocation,
                "classification": safety,
                "authority": authority,
                "access": _copy_access(UNKNOWN_ACCESS),
                "dependencies": [],
                "required_arguments": NATIVE_REQUIRED_ARGUMENTS.get(cap),
                "preflight": [],
                "documentation": (
                    "docs/P1-P14-PROSPECTIVE-RESEAL-PREFLIGHT-20261106.md"
                    if cap == "paper.identity_reseal_preview"
                    else DOCS[family]
                ),
                "available": _module_available(module, root),
                "limitations": [
                    "Consult owner contract; scientific and trading gates are separate"
                ],
                "evidence_freshness": "VERIFY_ON_USE",
            }
        )
    for module, (cap, family, safety) in EXTRA_MODULES.items():
        results.append(
            {
                "id": cap,
                "schema_version": 1,
                "kind": "MODULE",
                "description": f"Native module-only {family} capability",
                "owner": "copytrade_pm." + module,
                "interface": "copytrade_pm." + module,
                "classification": safety,
                "authority": family.upper(),
                "access": _copy_access(UNKNOWN_ACCESS),
                "dependencies": [],
                "required_arguments": None,
                "preflight": [],
                "documentation": DOCS[family],
                "available": _module_available("copytrade_pm." + module, root),
                "limitations": ["Python interface; inspect signature before calling"],
                "evidence_freshness": "VERIFY_ON_USE",
            }
        )
    return sorted(results, key=lambda item: item["id"])


PARSER_CALL_NAMES = frozenset(
    {
        "ArgumentParser",
        "add_subparsers",
        "add_parser",
        "add_mutually_exclusive_group",
        "add_argument",
        "add_argument_group",
        "set_defaults",
        "parse_known_args",
    }
)
ACCESS_KEYS = frozenset({"read_targets", "write_targets", "network", "credentials", "privacy"})


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
        return node.value
    return None


def _keyword_map(call: ast.Call) -> dict[str, ast.AST] | None:
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return None
    mapping: dict[str, ast.AST] = {}
    for kw in call.keywords:
        if kw.arg is None:
            return None
        mapping[kw.arg] = kw.value
    return mapping


def _register_registry_argument(
    node: dict,
    call: ast.Call,
    *,
    group_idx: int | None,
    group_required: bool,
) -> str | None:
    kwargs = _keyword_map(call)
    if kwargs is None or not call.args:
        return "dynamic_add_argument"
    options = [_const_str(arg) for arg in call.args]
    if any(opt is None for opt in options):
        return "dynamic_add_argument"
    option_names = [opt for opt in options if opt is not None]
    option = next((opt for opt in option_names if opt.startswith("--")), option_names[0])
    req_node = kwargs.get("required")
    if req_node is not None and not (
        isinstance(req_node, ast.Constant) and isinstance(req_node.value, bool)
    ):
        return "dynamic_required"
    action_node = kwargs.get("action")
    if action_node is not None and not (
        isinstance(action_node, ast.Constant) and isinstance(action_node.value, str)
    ):
        return "dynamic_action"
    nargs_node = kwargs.get("nargs")
    if nargs_node is not None and not (
        isinstance(nargs_node, ast.Constant) and isinstance(nargs_node.value, (str, int))
    ):
        return "dynamic_nargs"
    action = action_node.value if isinstance(action_node, ast.Constant) else None
    nargs = nargs_node.value if isinstance(nargs_node, ast.Constant) else None
    if option.startswith("-"):
        required = bool(req_node.value) if isinstance(req_node, ast.Constant) else False
        flag_only = action in {"store_true", "store_false", "count"}
        node["options"][option] = {
            "required": required,
            "flag_only": flag_only,
            "group_idx": group_idx,
        }
        if group_idx is not None and group_required:
            node["required_groups"][group_idx].append(option)
    else:
        pos_required = nargs not in {"?", "*"} and nargs != 0
        node["positionals"][option] = {"required": pos_required}
    return None


def _inspect_registry_parser(registry_path: Path) -> tuple[dict[str, dict], list[str]]:
    """Small, registry-specific AST inspector; fails closed on unsupported constructs."""
    if not registry_path.is_file():
        return {}, ["MISSING_ENTRY_MODULE:copytrade-wallet-registry"]
    tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    all_parser_calls = {
        id(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) in PARSER_CALL_NAMES
    }
    cli_defs = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "cli"
    ]
    if len(cli_defs) != 1:
        return {}, ["UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:missing_cli"]

    parser_vars: dict[str, tuple[str, ...]] = {}
    subparser_vars: dict[str, tuple[str, ...]] = {}
    group_vars: dict[str, tuple[tuple[str, ...], int, bool]] = {}
    nodes: dict[tuple[str, ...], dict] = {}
    visited_calls: set[int] = set()
    errors: list[str] = []
    saw_parse_args = False

    def _new_node() -> dict:
        return {
            "has_subparsers": False,
            "options": {},
            "positionals": {},
            "required_groups": [],
        }

    for stmt in cli_defs[0].body:
        target: str | None = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            if isinstance(stmt.targets[0], ast.Name):
                target = stmt.targets[0].id
            call = stmt.value if isinstance(stmt.value, ast.Call) else None
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        else:
            continue
        if call is None or not isinstance(call.func, ast.Attribute):
            continue
        attr = call.func.attr
        if attr == "parse_args" and isinstance(call.func.value, ast.Name):
            if parser_vars.get(call.func.value.id) == ():
                saw_parse_args = True
                break
        if attr not in PARSER_CALL_NAMES:
            continue
        visited_calls.add(id(call))
        recv = call.func.value
        recv_name = recv.id if isinstance(recv, ast.Name) else None

        if attr == "ArgumentParser":
            if (
                isinstance(recv, ast.Name)
                and recv.id == "argparse"
                and target is not None
                and () not in nodes
            ):
                nodes[()] = _new_node()
                parser_vars[target] = ()
            else:
                errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:ArgumentParser")
        elif attr == "add_subparsers":
            if recv_name not in parser_vars or target is None or len(parser_vars[recv_name]) > 1:
                errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:add_subparsers")
            else:
                path = parser_vars[recv_name]
                nodes[path]["has_subparsers"] = True
                subparser_vars[target] = path
        elif attr == "add_parser":
            kwargs = _keyword_map(call)
            name = _const_str(call.args[0]) if call.args else None
            if recv_name not in subparser_vars or kwargs is None or name is None:
                errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:add_parser")
            elif not set(kwargs) <= {"help", "description"}:
                errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:add_parser_kwargs")
            else:
                child = (*subparser_vars[recv_name], name)
                if child in nodes:
                    errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:duplicate_parser")
                else:
                    nodes[child] = _new_node()
                    if target is not None:
                        parser_vars[target] = child
        elif attr == "add_mutually_exclusive_group":
            kwargs = _keyword_map(call)
            req = kwargs.get("required") if kwargs is not None else None
            req_valid = req is None or (
                isinstance(req, ast.Constant) and isinstance(req.value, bool)
            )
            if recv_name not in parser_vars or target is None or kwargs is None or not req_valid:
                errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:add_mutually_exclusive_group")
            else:
                path = parser_vars[recv_name]
                req_flag = bool(req.value) if isinstance(req, ast.Constant) else False
                idx: int | None = None
                if req_flag:
                    idx = len(nodes[path]["required_groups"])
                    nodes[path]["required_groups"].append([])
                group_vars[target] = (path, idx, req_flag)
        elif attr == "add_argument":
            if recv_name in parser_vars:
                err = _register_registry_argument(
                    nodes[parser_vars[recv_name]], call, group_idx=None, group_required=False
                )
            elif recv_name in group_vars:
                path, idx, required = group_vars[recv_name]
                err = _register_registry_argument(
                    nodes[path], call, group_idx=idx, group_required=required
                )
            else:
                err = "untracked_add_argument"
            if err:
                errors.append(f"UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:{err}")
        else:
            errors.append(f"UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:{attr}")

    if not saw_parse_args:
        errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:missing_parse_args")
    if visited_calls != all_parser_calls:
        errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:non_linear_parser_call")

    for path, spec in nodes.items():
        if path and not spec["has_subparsers"]:
            continue
        has_parent_constraint = (
            any(meta["required"] for meta in spec["options"].values())
            or "--apply" in spec["options"]
            or any(meta["required"] for meta in spec["positionals"].values())
            or bool(spec["required_groups"])
        )
        if has_parent_constraint:
            errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:parent_node_constraint")

    leaves = {
        " ".join(path): spec for path, spec in nodes.items() if path and not spec["has_subparsers"]
    }
    return leaves, errors


def _validate_registry_operations(root: Path) -> list[str]:
    """Validate copytrade-wallet-registry leaves, --apply modes, required flags and access.

    T08 expansion seam (#342): add analogous parser-leaf and mode checks for
    copytrade-pm (pm_operations.py) and GROUPS scripts in a separate validator
    without weakening these registry checks.
    """
    leaves, problems = _inspect_registry_parser(root / "src/copytrade_pm/wallet_registry.py")
    if problems:
        return problems

    op_to_leaf: dict[str, str] = {}
    covered_leaves: set[str] = set()
    for op, safety in REGISTRY_OPERATIONS.items():
        parts = op.split()
        leaf = None
        for size in range(len(parts), 0, -1):
            candidate = " ".join(parts[:size])
            if candidate in leaves:
                leaf = candidate
                break
        if leaf is None:
            problems.append(f"STALE_REGISTRY_OP:{op}")
            continue
        mode_flags = parts[len(leaf.split()) :]
        options = leaves[leaf]["options"]
        if any(flag not in options for flag in mode_flags):
            problems.append(f"STALE_REGISTRY_OP:{op}")
            continue
        op_to_leaf[op] = leaf
        covered_leaves.add(leaf)
        if "--apply" in mode_flags and safety == "READ_ONLY":
            problems.append(f"UNSAFE_REGISTRY_CLASSIFICATION:{op}")

    for leaf, spec in leaves.items():
        required_groups = [opts for opts in spec["required_groups"] if opts]
        if required_groups:
            for opts in required_groups:
                for opt in opts:
                    op_name = f"{leaf} {opt}"
                    if op_name not in op_to_leaf:
                        problems.append(f"UNLISTED_REGISTRY_OP:{op_name}")
        elif leaf not in covered_leaves:
            problems.append(f"UNLISTED_REGISTRY_OP:{leaf}")
        if "--apply" in spec["options"] and f"{leaf} --apply" not in op_to_leaf:
            problems.append(f"MISSING_REGISTRY_APPLY_OP:{leaf} --apply")

    for op, leaf in op_to_leaf.items():
        spec = leaves[leaf]
        mode_flags = set(op.split()[len(leaf.split()) :])
        parser_required: set[str] = set()
        for opt, meta in spec["options"].items():
            in_selected_group = meta["group_idx"] is not None and opt in mode_flags
            if (meta["required"] or in_selected_group) and not (
                meta["flag_only"] and opt in mode_flags
            ):
                parser_required.add(opt)
        for pos, meta in spec["positionals"].items():
            if meta["required"]:
                parser_required.add(pos.lower())

        declared = {
            tok.split()[0] if tok.startswith("-") else tok.split()[0].lower()
            for tok in REGISTRY_REQUIRED_ARGUMENTS.get(op, [])
        }
        for missing in sorted(parser_required - declared):
            problems.append(f"MISSING_REGISTRY_REQUIRED_ARG:{op}:{missing}")

        dispatch_reqs = set(REGISTRY_DISPATCH_REQUIRED_ARGUMENTS.get(op, ()))
        for flag in sorted(dispatch_reqs):
            if flag not in spec["options"] or flag in parser_required:
                problems.append(f"STALE_REGISTRY_DISPATCH_ARG:{op}:{flag}")
        for missing in sorted(dispatch_reqs - declared):
            problems.append(f"MISSING_REGISTRY_DISPATCH_ARG:{op}:{missing}")
        for extra in sorted(declared - parser_required - dispatch_reqs):
            problems.append(f"STALE_REGISTRY_REQUIRED_ARG:{op}:{extra}")

        access = REGISTRY_ACCESS.get(op)
        if access is None or set(access) != ACCESS_KEYS:
            problems.append(f"MISSING_REGISTRY_ACCESS:{op}")
        else:
            valid_types = (
                isinstance(access["read_targets"], list)
                and all(isinstance(x, str) and x for x in access["read_targets"])
                and isinstance(access["write_targets"], list)
                and all(isinstance(x, str) and x for x in access["write_targets"])
                and isinstance(access["network"], bool)
                and isinstance(access["credentials"], bool)
                and isinstance(access["privacy"], str)
                and bool(access["privacy"])
            )
            if not valid_types:
                problems.append(f"INVALID_ACCESS_SCHEMA:{op}")
            if any(access[k] == "UNKNOWN" for k in ACCESS_KEYS):
                problems.append(f"UNVERIFIED_REGISTRY_ACCESS:{op}")
            safety = REGISTRY_OPERATIONS[op]
            if safety == "READ_ONLY" and access["write_targets"] != []:
                problems.append(f"INCONSISTENT_REGISTRY_ACCESS:{op}")
            if (
                safety in {"LOCAL_MUTATION", "PROTECTED_MUTATION", "BROKER_OR_TRADING"}
                and not access["write_targets"]
            ):
                problems.append(f"INCONSISTENT_REGISTRY_ACCESS:{op}")

    for op in set(REGISTRY_ACCESS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_ACCESS:{op}")
    for op in set(REGISTRY_REQUIRED_ARGUMENTS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_REQUIRED_ARG_ENTRY:{op}")
    for op in set(REGISTRY_DISPATCH_REQUIRED_ARGUMENTS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_DISPATCH_ARG_ENTRY:{op}")

    return problems


def validate(root: Path = ROOT) -> dict:
    entries = inventory(root)
    declared = _declared_scripts(root)
    installed = _installed_scripts()
    problems = []
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        problems.append("DUPLICATE_CAPABILITY_ID")
    if set(declared) != (set(declared) & set(GROUPS)):
        problems.append("UNREVIEWED_ENTRY_POINTS")
    if installed and installed != declared:
        problems.append("INSTALLED_ENTRY_POINT_DRIFT")
    for item in entries:
        if item["classification"] not in CLASSES:
            problems.append(f"UNCLASSIFIED:{item['id']}")
        if not item["available"]:
            problems.append(f"MISSING_OWNER:{item['id']}")
        if not (root / item["documentation"]).is_file():
            problems.append(f"MISSING_DOC:{item['id']}")
        if item["schema_version"] != 1:
            problems.append(f"INVALID_SCHEMA:{item['id']}")
        if set(item.get("access", {})) != ACCESS_KEYS:
            problems.append(f"INVALID_ACCESS_SCHEMA:{item['id']}")
    for name, entry in declared.items():
        if ":" not in entry or entry.rsplit(":", 1)[1] != "main":
            problems.append(f"INVALID_ENTRY_POINT:{name}")
        else:
            module = root / "src" / Path(*entry.split(":", 1)[0].split("."))
            file = module.with_suffix(".py")
            if not file.is_file():
                problems.append(f"MISSING_ENTRY_MODULE:{name}")
            else:
                tree = ast.parse(file.read_text())
                if not any(
                    isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == "main"
                    for x in tree.body
                ):
                    problems.append(f"MISSING_MAIN:{name}")
    # T07 enforces parser leaf/flag/--apply validation solely for copytrade-wallet-registry;
    # T08 (#342) expands analogous leaf/mode checks to copytrade-pm and GROUPS entrypoints.
    problems.extend(_validate_registry_operations(root))
    return {
        "schema": "copytrade_capability_validation_v1",
        "status": "VERIFIED" if not problems else "BLOCKED",
        "cli_count": len(declared),
        "module_only_count": len(NATIVE) + len(EXTRA_MODULES),
        "capability_count": len(entries),
        "errors": sorted(set(problems)),
    }


def render(items: object) -> str:
    return json.dumps(items, sort_keys=True, indent=2)
