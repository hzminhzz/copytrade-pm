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


# Registry access schema reused across reviewed subcommand and mode records.
def _access_entry(
    read_targets: list[str],
    write_targets: list[str],
    *,
    network: bool = False,
    credentials: bool = False,
    privacy: str = "OWNER_PRIVATE_REDACTED",
) -> dict[str, object]:
    return {
        "read_targets": read_targets,
        "write_targets": write_targets,
        "network": network,
        "credentials": credentials,
        "privacy": privacy,
    }


def _registry_access_entry(
    read_targets: list[str],
    write_targets: list[str],
    *,
    privacy: str = "OWNER_PRIVATE_REDACTED",
) -> dict[str, object]:
    return _access_entry(
        read_targets,
        write_targets,
        network=False,
        credentials=False,
        privacy=privacy,
    )


# Reviewed subcommands for copytrade-pm (pm_operations.py) not already covered
# by existing NATIVE capability IDs. Already-cataloged leaves remain in NATIVE.
OPERATIONS_SUBCOMMANDS: dict[str, dict[str, object]] = {
    "cwsa chapter2 verify": {
        "id": "operations.cwsa.chapter2.verify",
        "owner": "copytrade_pm.pm_cwsa_chapter2_gate",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "CWSA_CHAPTER2_ACCEPTANCE_GATES",
        "documentation": "docs/CWSA-CHAPTER2-20261112.md",
        "required_arguments": ["--stage STAGE"],
        "runtime_required_arguments": [
            "--receipt PATH",
            "--quote-db PATH",
            "--dashboard-url HTTPS_URL",
            "--dashboard-revision SHA40",
            "--dashboard-token-file PATH",
        ],
        "access": _access_entry(
            [
                "git_checkout",
                "optional_ci_receipt",
                "optional_private_sqlite_registry",
                "optional_private_cwsa_source_sqlite",
                "optional_private_pm03_journals",
                "optional_private_quote_sqlite",
                "optional_signed_paper_release",
                "optional_systemd_user_units",
                "optional_proc_pid",
                "optional_dashboard_token_file",
            ],
            [],
            network=True,
            credentials=True,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Stage-dependent evidence inputs produce BLOCKED_EVIDENCE when omitted; "
            "postdeploy optionally queries HTTPS dashboard using a bearer token file"
        ],
    },
    "cwsa chapter2 projection": {
        "id": "operations.cwsa.chapter2.projection",
        "owner": "copytrade_pm.pm_cwsa_chapter2_projection",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "CWSA_CHAPTER2_EVIDENCE_PROJECTION",
        "documentation": "docs/CWSA-CHAPTER2-20261112.md",
        "required_arguments": ["--release-sha SHA40"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "private_cwsa_source_sqlite",
                "private_pm03_journals",
                "optional_signed_paper_release",
                "optional_qualification_attestation",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Signed release flags are optional; if any signed-release or qualification flag "
            "is provided, all five must be supplied together"
        ],
    },
    "capabilities list": {
        "id": "operations.capabilities.list",
        "owner": "copytrade_pm.pm_capabilities",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "REVIEWED_CAPABILITY_DIRECTORY",
        "documentation": DOC,
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["repo_pyproject", "repo_source_ast", "installed_distribution_metadata"],
            [],
            privacy="PUBLIC_METADATA",
        ),
        "limitations": ["Descriptive inventory only; never grants authorization"],
    },
    "capabilities show": {
        "id": "operations.capabilities.show",
        "owner": "copytrade_pm.pm_capabilities",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "REVIEWED_CAPABILITY_DIRECTORY",
        "documentation": DOC,
        "required_arguments": ["ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["repo_pyproject", "repo_source_ast", "installed_distribution_metadata"],
            [],
            privacy="PUBLIC_METADATA",
        ),
        "limitations": ["Descriptive lookup only; never grants authorization"],
    },
    "capabilities validate": {
        "id": "operations.capabilities.validate",
        "owner": "copytrade_pm.pm_capabilities",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "REVIEWED_CAPABILITY_DIRECTORY",
        "documentation": DOC,
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "repo_pyproject",
                "repo_docs",
                "repo_source_ast",
                "installed_distribution_metadata",
            ],
            [],
            privacy="PUBLIC_METADATA",
        ),
        "limitations": [
            "Bounded AST inspection checks static parsers and reviewed dispatch tables; "
            "dynamic JSON/config dispatch uses explicit owner contracts"
        ],
    },
    "portfolios list": {
        "id": "portfolio.list",
        "owner": "copytrade_pm.wallet_registry_portfolios",
        "family": "portfolio",
        "classification": "READ_ONLY",
        "authority": "PRIVATE_VERSIONED_WALLET_REGISTRY",
        "documentation": "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_sqlite_registry", "decision_repo"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Registry portfolio listing never proves worker health or trading authority"
        ],
    },
    "research show": {
        "id": "research.show",
        "owner": "copytrade_pm.pm_offline_job_catalog",
        "family": "research",
        "classification": "READ_ONLY",
        "authority": "SHA_VERIFIED_OFFLINE_JOB_REPORT_CACHE",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": ["ID"],
        "runtime_required_arguments": ["--cache-root PATH"],
        "access": _access_entry(
            ["sha_verified_immutable_offline_job_cache"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Argparse requires only ID; --cache-root PATH is runtime-required for VERIFIED results "
            "and --cache-key KEY disambiguates duplicate job IDs"
        ],
    },
    "contracts rules": {
        "id": "research.contract_selector.rules",
        "owner": "copytrade_pm.pm_contract_selector",
        "family": "research",
        "classification": "READ_ONLY",
        "authority": "USER_SUPPLIED_UNVERIFIED_ARCHETYPE",
        "documentation": "docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md",
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["static_contract_archetype_catalog"],
            [],
            privacy="PUBLIC_METADATA",
        ),
        "limitations": [
            "Archetype rule parameters are scenario assumptions, not broker guarantees"
        ],
    },
    "status": {
        "id": "operations.status",
        "owner": "copytrade_pm.pm_operations",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "INDEPENDENT_READ_ADAPTERS",
        "documentation": DOC,
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "git_checkout",
                "private_sqlite_registry",
                "optional_private_paper_journal",
                "decision_repo",
                "systemd_user_and_system_units",
                "optional_observer_state_root",
                "optional_installed_registry_release",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Calls broad registry status and runtime probes; aggregate status preserves "
            "independent UNKNOWN/BLOCKED components"
        ],
    },
}


# Reviewed GROUPS mode variants that distinguish READ_ONLY vs MUTATION/network/dispatch
# modes while retaining conservative parent GROUPS classifications.
GROUP_OPERATIONS: dict[str, dict[str, object]] = {
    "source.public_trades.observe": {
        "script": "copytrade-pm-public-trades",
        "owner": "copytrade_pm.pm_forward_public_trades",
        "family": "source",
        "interface": "copytrade-pm-public-trades --mode observe",
        "classification": "PROTECTED_MUTATION",
        "authority": "PUBLIC_ONLY_PROVISIONAL_TRADE_CAPTURE",
        "documentation": "docs/FORWARD-PAPER-PUBLIC-TRADES-20261105.md",
        "required_arguments": [
            "--instrument SYMBOL | --market-file PATH",
            "--portfolio ID",
            "--registry PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": [
            "--ack-shared-ip-connection-budget",
            "--propr-snapshot PATH",
        ],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "optional_market_shards",
                "optional_propr_snapshot",
                "public_hyperliquid_api",
            ],
            ["private_observer_journal"],
            network=True,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Uses public WebSocket/REST and writes private observer journal; never produces paper admission"
        ],
    },
    "source.public_trades.plan": {
        "script": "copytrade-pm-public-trades",
        "owner": "copytrade_pm.pm_forward_public_trades",
        "family": "source",
        "interface": "copytrade-pm-public-trades --mode plan",
        "classification": "PROTECTED_MUTATION",
        "authority": "PUBLIC_ONLY_PROVISIONAL_TRADE_CAPTURE",
        "documentation": "docs/FORWARD-PAPER-PUBLIC-TRADES-20261105.md",
        "required_arguments": [
            "--instrument SYMBOL | --market-file PATH",
            "--portfolio ID",
            "--registry PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": ["--propr-snapshot PATH"],
        "access": _access_entry(
            ["private_sqlite_registry", "optional_market_shards", "optional_propr_snapshot"],
            ["private_observer_journal"],
            network=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "No live network capture in plan mode, but writes planned bucket records to PaperJournal"
        ],
    },
    "paper.public_unit.preview": {
        "script": "copytrade-pm-public-observer-unit",
        "owner": "copytrade_pm.pm_forward_public_unit",
        "family": "paper",
        "interface": "copytrade-pm-public-observer-unit",
        "classification": "READ_ONLY",
        "authority": "SYSTEMD_USER_UNIT_PLAN",
        "documentation": "docs/FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md",
        "required_arguments": [
            "--primary-dir PATH",
            "--registry PATH",
            "--revision SHA40",
            "--secondary-dir PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "pinned_release_dir",
                "private_sqlite_registry",
                "source_dirs",
                "observer_state_root",
                "optional_systemd_user_unit_file",
            ],
            [],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["Preview only when --apply is omitted; never installs or starts units"],
    },
    "paper.public_unit.apply": {
        "script": "copytrade-pm-public-observer-unit",
        "owner": "copytrade_pm.pm_forward_public_unit",
        "family": "paper",
        "interface": "copytrade-pm-public-observer-unit --apply",
        "classification": "PROTECTED_MUTATION",
        "authority": "SYSTEMD_USER_UNIT_INSTALL",
        "documentation": "docs/FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md",
        "required_arguments": [
            "--primary-dir PATH",
            "--registry PATH",
            "--revision SHA40",
            "--secondary-dir PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "pinned_release_dir",
                "private_sqlite_registry",
                "source_dirs",
                "observer_state_root",
                "optional_systemd_user_unit_file",
            ],
            ["systemd_user_unit_file"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": [
            "Writes systemd user unit file only; never runs systemctl or grants paper admission"
        ],
    },
    "account.pm03.simulate.compare": {
        "script": "copytrade-pm-shadow",
        "owner": "copytrade_pm.pm03_cli",
        "family": "account",
        "interface": "copytrade-pm-shadow --input SPEC.json --output-dir DIR",
        "classification": "LOCAL_MUTATION",
        "authority": "PM03_FINANCIAL_AUTHORITY",
        "documentation": "docs/PM-03-shadow-account.md",
        "required_arguments": ["--input PATH", "--output-dir PATH"],
        "runtime_required_arguments": ["spec.action=compare", "spec.mode=RESEARCH_SYNTHETIC"],
        "access": _access_entry(
            ["private_pm03_input_json"],
            ["private_pm03_report_dir"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": [
            "Dynamic JSON dispatch: requires spec.action='compare' inside --input JSON; "
            "verified against explicit owner contract rather than CLI flags"
        ],
    },
    "account.pm03.simulate.compare_pm04": {
        "script": "copytrade-pm-shadow",
        "owner": "copytrade_pm.pm03_cli",
        "family": "account",
        "interface": "copytrade-pm-shadow --input SPEC.json --output-dir DIR",
        "classification": "LOCAL_MUTATION",
        "authority": "PM03_FINANCIAL_AUTHORITY",
        "documentation": "docs/PM-03-shadow-account.md",
        "required_arguments": ["--input PATH", "--output-dir PATH"],
        "runtime_required_arguments": [
            "spec.action=compare_pm04",
            "spec.schema=pm04_compare_input_v1",
        ],
        "access": _access_entry(
            ["private_pm03_input_json"],
            ["private_pm03_report_dir"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": [
            "Dynamic JSON dispatch: requires spec.action='compare_pm04' and schema='pm04_compare_input_v1'"
        ],
    },
    "account.pm03.simulate.replay": {
        "script": "copytrade-pm-shadow",
        "owner": "copytrade_pm.pm03_cli",
        "family": "account",
        "interface": "copytrade-pm-shadow --input SPEC.json --output-dir DIR",
        "classification": "LOCAL_MUTATION",
        "authority": "PM03_FINANCIAL_AUTHORITY",
        "documentation": "docs/PM-03-shadow-account.md",
        "required_arguments": ["--input PATH", "--output-dir PATH"],
        "runtime_required_arguments": ["spec.action=replay"],
        "access": _access_entry(
            ["private_pm03_input_json"],
            ["private_pm03_report_dir", "private_pm03_runs_dir"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["Dynamic JSON dispatch: requires spec.action='replay' inside --input JSON"],
    },
    "source.receipts.init": {
        "script": "copytrade-pm-receipts",
        "owner": "copytrade_pm.pm_prospective_cli",
        "family": "source",
        "interface": "copytrade-pm-receipts init",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROSPECTIVE_SOURCE_RECEIPTS",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": [
            "--auditor-public-key PATH",
            "--ledger PATH",
            "--research-root PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_cohort_manifest", "auditor_public_key"],
            ["private_prospective_ledger"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["Initializes owner-private prospective ledger"],
    },
    "source.receipts.ingest": {
        "script": "copytrade-pm-receipts",
        "owner": "copytrade_pm.pm_prospective_cli",
        "family": "source",
        "interface": "copytrade-pm-receipts ingest",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROSPECTIVE_SOURCE_RECEIPTS",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": [
            "--auditor-public-key PATH",
            "--ledger PATH",
            "--research-root PATH",
        ],
        "runtime_required_arguments": ["--receipts PATH"],
        "access": _access_entry(
            [
                "private_cohort_manifest",
                "auditor_public_key",
                "private_prospective_ledger",
                "private_producer_receipts",
            ],
            ["private_prospective_ledger"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["--receipts PATH is runtime-required in ingest mode"],
    },
    "source.receipts.audit": {
        "script": "copytrade-pm-receipts",
        "owner": "copytrade_pm.pm_prospective_cli",
        "family": "source",
        "interface": "copytrade-pm-receipts audit",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROSPECTIVE_SOURCE_RECEIPTS",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": [
            "--auditor-public-key PATH",
            "--ledger PATH",
            "--research-root PATH",
        ],
        "runtime_required_arguments": ["--attestation-file PATH"],
        "access": _access_entry(
            [
                "private_cohort_manifest",
                "auditor_public_key",
                "private_prospective_ledger",
                "signed_attestation_file",
            ],
            ["private_prospective_ledger"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["--attestation-file PATH (0600) is runtime-required in audit mode"],
    },
    "source.receipts.outcome": {
        "script": "copytrade-pm-receipts",
        "owner": "copytrade_pm.pm_prospective_cli",
        "family": "source",
        "interface": "copytrade-pm-receipts outcome",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROSPECTIVE_SOURCE_RECEIPTS",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": [
            "--auditor-public-key PATH",
            "--ledger PATH",
            "--research-root PATH",
        ],
        "runtime_required_arguments": ["--attestation-file PATH"],
        "access": _access_entry(
            [
                "private_cohort_manifest",
                "auditor_public_key",
                "private_prospective_ledger",
                "signed_attestation_file",
            ],
            ["private_prospective_ledger"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["--attestation-file PATH (0600) is runtime-required in outcome mode"],
    },
    "source.receipts.inspect": {
        "script": "copytrade-pm-receipts",
        "owner": "copytrade_pm.pm_prospective_cli",
        "family": "source",
        "interface": "copytrade-pm-receipts inspect",
        "classification": "READ_ONLY",
        "authority": "PROSPECTIVE_SOURCE_RECEIPTS",
        "documentation": "docs/RUNBOOK.md",
        "required_arguments": [
            "--auditor-public-key PATH",
            "--ledger PATH",
            "--research-root PATH",
        ],
        "runtime_required_arguments": ["--asof UTC"],
        "access": _access_entry(
            ["private_cohort_manifest", "auditor_public_key", "private_prospective_ledger"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["Read-only readiness inspection; --asof UTC is runtime-required"],
    },
    "paper.unit_bundle.stage": {
        "script": "copytrade-pm-paper-unit-bundle",
        "owner": "copytrade_pm.pm_forward_protected_units",
        "family": "paper",
        "interface": "copytrade-pm-paper-unit-bundle --revision SHA40 --out DIR",
        "classification": "LOCAL_MUTATION",
        "authority": "PROTECTED_UNIT_CANDIDATE_STAGE",
        "documentation": "docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md",
        "required_arguments": ["--out PATH"],
        "runtime_required_arguments": ["--revision SHA40"],
        "access": _access_entry(
            ["git_checkout"],
            ["protected_unit_bundle"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": [
            "Stages candidate files locally; --revision is runtime-required without --verify"
        ],
    },
    "paper.unit_bundle.verify": {
        "script": "copytrade-pm-paper-unit-bundle",
        "owner": "copytrade_pm.pm_forward_protected_units",
        "family": "paper",
        "interface": "copytrade-pm-paper-unit-bundle --verify --out DIR",
        "classification": "READ_ONLY",
        "authority": "PROTECTED_UNIT_CANDIDATE_VERIFY",
        "documentation": "docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md",
        "required_arguments": ["--out PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["protected_unit_bundle"],
            [],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["Read-only bundle verification"],
    },
    "production.export.cli.stdout": {
        "script": "copytrade-pm-production-export",
        "owner": "copytrade_pm.production_export",
        "family": "registry",
        "interface": "copytrade-pm-production-export",
        "classification": "READ_ONLY",
        "authority": "PRIVATE_VERSIONED_WALLET_REGISTRY",
        "documentation": "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
        "required_arguments": ["--asof UTC", "--portfolio ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_sqlite_registry"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["Prints redacted view when --private-output is omitted"],
    },
    "production.export.cli.write": {
        "script": "copytrade-pm-production-export",
        "owner": "copytrade_pm.production_export",
        "family": "registry",
        "interface": "copytrade-pm-production-export --private-output PATH",
        "classification": "LOCAL_MUTATION",
        "authority": "PRIVATE_VERSIONED_WALLET_REGISTRY",
        "documentation": "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
        "required_arguments": ["--asof UTC", "--portfolio ID"],
        "runtime_required_arguments": ["--private-output PATH"],
        "access": _access_entry(
            ["private_sqlite_registry"],
            ["private_export_file"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["Writes 0600 private export artifact when --private-output is supplied"],
    },
    "paper.standby.worker": {
        "script": "copytrade-pm-paper-standby",
        "owner": "copytrade_pm.pm_forward_protected_ops",
        "family": "paper",
        "interface": "copytrade-pm-paper-standby worker",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROTECTED_PAPER_STANDBY",
        "documentation": "docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md",
        "required_arguments": ["--release PATH", "--revision SHA40", "--state-root PATH"],
        "runtime_required_arguments": ["--portfolio P1|P14"],
        "access": _access_entry(
            ["pinned_release_dir", "protected_paper_state_root"],
            ["protected_standby_worker_state"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": [
            "--portfolio is runtime-required in worker role; standby writes status only"
        ],
    },
    "paper.standby.watchdog": {
        "script": "copytrade-pm-paper-standby",
        "owner": "copytrade_pm.pm_forward_protected_ops",
        "family": "paper",
        "interface": "copytrade-pm-paper-standby watchdog",
        "classification": "PROTECTED_MUTATION",
        "authority": "PROTECTED_PAPER_STANDBY",
        "documentation": "docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md",
        "required_arguments": ["--release PATH", "--revision SHA40", "--state-root PATH"],
        "runtime_required_arguments": ["--p1-root PATH", "--p14-root PATH"],
        "access": _access_entry(
            ["pinned_release_dir", "protected_standby_worker_state"],
            ["protected_standby_watchdog_state"],
            privacy="OWNER_PRIVATE",
        ),
        "limitations": ["--p1-root and --p14-root are runtime-required in watchdog role"],
    },
    "agent.trace.eval.list_tasks": {
        "script": "copytrade-pm-agent-eval",
        "owner": "copytrade_pm.pm_agent_trace_eval",
        "family": "operations",
        "interface": "copytrade-pm-agent-eval --list-tasks",
        "classification": "READ_ONLY",
        "authority": "AGENT_TRACE_EVALUATION",
        "documentation": "docs/AGENT-TRACE-EVAL-20261105.md",
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["static_task_map"],
            [],
            privacy="PUBLIC_METADATA",
        ),
        "limitations": ["Read-only task catalog listing"],
    },
    "agent.trace.eval.trace": {
        "script": "copytrade-pm-agent-eval",
        "owner": "copytrade_pm.pm_agent_trace_eval",
        "family": "operations",
        "interface": "copytrade-pm-agent-eval --trace PATH",
        "classification": "READ_ONLY",
        "authority": "AGENT_TRACE_EVALUATION",
        "documentation": "docs/AGENT-TRACE-EVAL-20261105.md",
        "required_arguments": [],
        "runtime_required_arguments": ["--trace PATH"],
        "access": _access_entry(
            ["private_agent_trace_json", "optional_signature_and_public_key"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["--trace PATH is runtime-required when --list-tasks is omitted"],
    },
    "paper.observed_execution.l2": {
        "script": "copytrade-pm-paper-observed",
        "owner": "copytrade_pm.pm_forward_observed_paper",
        "family": "paper",
        "interface": "copytrade-pm-paper-observed --price-mode l2",
        "classification": "LOCAL_MUTATION",
        "authority": "PM04_VIRTUAL_PAPER",
        "documentation": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
        "required_arguments": ["--run-id ID", "--source-db PATH", "--state-root PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "private_source_db",
                "private_sqlite_registry",
                "optional_markets_json",
                "optional_public_ccxt_catalog",
            ],
            ["private_paper_journal"],
            network=True,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["Calls CCXT public catalog unless --markets-json is supplied"],
    },
    "paper.observed_execution.vike_minute": {
        "script": "copytrade-pm-paper-observed",
        "owner": "copytrade_pm.pm_forward_observed_paper",
        "family": "paper",
        "interface": "copytrade-pm-paper-observed --price-mode vike_minute",
        "classification": "LOCAL_MUTATION",
        "authority": "PM04_VIRTUAL_PAPER",
        "documentation": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
        "required_arguments": ["--run-id ID", "--source-db PATH", "--state-root PATH"],
        "runtime_required_arguments": ["--price-db PATH", "--propr-catalog PATH"],
        "access": _access_entry(
            [
                "private_source_db",
                "private_sqlite_registry",
                "private_vike_price_db",
                "propr_native_catalog",
            ],
            ["private_paper_journal"],
            network=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "No CCXT call; requires --propr-catalog PATH and --price-db PATH at runtime"
        ],
    },
    "paper.observer.diagnose_preflight": {
        "script": "copytrade-pm-paper-observe",
        "owner": "copytrade_pm.pm_forward_continuous",
        "family": "paper",
        "interface": (
            "copytrade-pm-paper-observe --continuous-config CONFIG "
            "--preflight-only --diagnose-preflight"
        ),
        "classification": "READ_ONLY",
        "authority": "PINNED_REGISTRY_AND_ISOLATED_OBSERVER_PREFLIGHT",
        "documentation": "docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md",
        "required_arguments": [
            "--primary-dir PATH",
            "--registry PATH",
            "--secondary-dir PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": ["--continuous-config PATH", "--preflight-only"],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "source_dirs",
                "continuous_observer_config",
                "pinned_release_dir",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Read-only budget diagnostic; requires --continuous-config and --preflight-only at runtime"
        ],
    },
}


# Backwards-compatible aliases: _registry_access_entry stays identical.
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
    "portfolio.current": [],
    "paper.status": [],
    "research.report.catalog": [],
    "research.catalog": [],
    "research.contract_selector": ["--portfolio NAMESPACE/ID"],
    "runtime.pinned_release": [],
    "runtime.paper_units": [],
    "runtime.market_observer": [],
    "runtime.health": [],
    "registry.doctor": [],
    "wallet.lookup": ["ALIAS"],
    "wallet.alias": ["ALIAS"],
    "portfolio.show": ["PORTFOLIO"],
    "research.offline": ["JOB", "--input-root PATH", "--market-root PATH", "--cache-root PATH"],
    "paper.observer.preflight": [
        "--primary-dir PATH",
        "--registry PATH",
        "--secondary-dir PATH",
        "--state-root PATH",
    ],
    "paper.observer.continuous": [
        "--primary-dir PATH",
        "--registry PATH",
        "--secondary-dir PATH",
        "--state-root PATH",
    ],
    "paper.observer.continuous_health": ["--state-root PATH"],
    "paper.observer.continuous_watchdog": ["--state-root PATH"],
    "paper.observer.shadow_report": ["--state-root PATH"],
    "market.continuous_canary": ["--instrument SYMBOL"],
    "paper.identity_reseal_preview": [
        "--portfolio P1|P14",
        "--primary-dir PATH",
        "--registry PATH",
        "--secondary-dir PATH",
    ],
}
NATIVE_RUNTIME_REQUIRED_ARGUMENTS = {
    "research.report.catalog": ["--cache-root PATH"],
    "research.catalog": ["--cache-root PATH"],
    "research.contract_selector": ["--tape PRIVATE_TAPE"],
    "runtime.market_observer": ["--observer-state-root PATH"],
    "paper.observer.preflight": ["--continuous-config PATH"],
    "paper.observer.continuous": ["--continuous-config PATH"],
    "market.continuous_canary": ["--continuous-canary-seconds SECONDS", "--record-root PATH"],
}
NATIVE_ACCESS = {
    "wallet.inventory": _access_entry(["private_sqlite_registry"], []),
    "wallet.lookup": _access_entry(["private_sqlite_registry"], []),
    "wallet.alias": _access_entry(["private_sqlite_registry"], []),
    "portfolio.current": _access_entry(["private_sqlite_registry", "decision_repo"], []),
    "portfolio.show": _access_entry(["private_sqlite_registry"], []),
    "paper.status": _access_entry(
        ["private_sqlite_registry", "optional_private_paper_journal"], []
    ),
    "research.report.catalog": _access_entry(["sha_verified_immutable_offline_job_cache"], []),
    "research.catalog": _access_entry(["sha_verified_immutable_offline_job_cache"], []),
    "research.contract_selector": _access_entry(
        ["private_sqlite_registry", "private_follower_pnl_tape"], []
    ),
    "runtime.health": _access_entry(
        [
            "git_checkout",
            "private_sqlite_registry",
            "optional_private_paper_journal",
            "decision_repo",
            "systemd_user_and_system_units",
            "optional_observer_state_root",
            "optional_installed_registry_release",
        ],
        [],
    ),
    "runtime.pinned_release": _access_entry(
        ["git_checkout", "optional_installed_registry_release"], []
    ),
    "runtime.paper_units": _access_entry(["systemd_user_and_system_units", "proc_pid"], []),
    "runtime.market_observer": _access_entry(["optional_observer_state_root"], []),
    "registry.doctor": _access_entry(
        ["private_sqlite_registry", "private_evidence_archive", "decision_repo"], []
    ),
    "paper.observer.preflight": _access_entry(
        [
            "private_sqlite_registry",
            "source_dirs",
            "continuous_observer_config",
            "pinned_release_dir",
        ],
        [],
    ),
    "paper.observer.continuous": _access_entry(
        [
            "private_sqlite_registry",
            "source_dirs",
            "continuous_observer_config",
            "pinned_release_dir",
            "public_hyperliquid_api",
        ],
        ["private_observer_journal"],
        network=True,
    ),
    "paper.observer.continuous_health": _access_entry(
        ["private_observer_journal", "private_continuous_heartbeat", "proc_pid"], []
    ),
    "paper.observer.continuous_watchdog": _access_entry(
        ["private_observer_journal", "private_continuous_heartbeat", "proc_pid"],
        ["private_watchdog_state"],
    ),
    "paper.observer.shadow_report": _access_entry(
        ["private_observer_journal", "private_watchdog_state"], []
    ),
    "market.continuous_canary": _access_entry(
        ["public_hyperliquid_api"],
        ["private_market_canary_record"],
        network=True,
    ),
    "paper.identity_reseal_preview": _access_entry(["private_sqlite_registry", "source_dirs"], []),
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


def _subcommand_entry(
    *,
    cap_id: str,
    description: str,
    owner: str,
    interface: str,
    classification: str,
    authority: str,
    access: dict[str, object],
    required_arguments: list[str],
    runtime_required_arguments: list[str],
    preflight: list[str],
    documentation: str,
    available: bool,
    limitations: list[str],
) -> dict[str, object]:
    return {
        "id": cap_id,
        "schema_version": 1,
        "kind": "SUBCOMMAND",
        "description": description,
        "owner": owner,
        "interface": interface,
        "classification": classification,
        "authority": authority,
        "access": _copy_access(access),
        "dependencies": [],
        "required_arguments": list(required_arguments),
        "runtime_required_arguments": list(runtime_required_arguments),
        "preflight": list(preflight),
        "documentation": documentation,
        "available": available,
        "limitations": list(limitations),
        "evidence_freshness": "VERIFY_ON_USE",
    }


def _registry_runtime_args(op: str) -> list[str]:
    dispatch = set(REGISTRY_DISPATCH_REQUIRED_ARGUMENTS.get(op, ()))
    if not dispatch:
        return []
    return [arg for arg in REGISTRY_REQUIRED_ARGUMENTS.get(op, []) if arg.split()[0] in dispatch]


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
        req_args = _required_cli_args(module, root)
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
                "required_arguments": req_args,
                "runtime_required_arguments": None if req_args is None else [],
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
            _subcommand_entry(
                cap_id="registry.operation." + re.sub(r"[^a-z0-9]+", ".", op).strip("."),
                description="Reviewed registry operation",
                owner="copytrade_pm.wallet_registry",
                interface="copytrade-wallet-registry " + op,
                classification=safety,
                authority="PRIVATE_VERSIONED_WALLET_REGISTRY",
                access=REGISTRY_ACCESS.get(op, UNKNOWN_ACCESS),
                required_arguments=REGISTRY_REQUIRED_ARGUMENTS.get(op, []),
                runtime_required_arguments=_registry_runtime_args(op),
                preflight=["registry.doctor"] if op not in ("doctor", "status") else [],
                documentation=DOCS["registry"],
                available=True,
                limitations=["Protect owner-private input and output"],
            )
        )
    for subcmd, spec in sorted(OPERATIONS_SUBCOMMANDS.items()):
        owner = str(spec["owner"])
        results.append(
            _subcommand_entry(
                cap_id=str(spec["id"]),
                description=f"Operations subcommand copytrade-pm {subcmd}",
                owner=owner,
                interface=f"copytrade-pm {subcmd}",
                classification=str(spec["classification"]),
                authority=str(spec["authority"]),
                access=spec["access"],  # type: ignore[arg-type]
                required_arguments=list(spec["required_arguments"]),  # type: ignore[arg-type]
                runtime_required_arguments=list(spec["runtime_required_arguments"]),  # type: ignore[arg-type]
                preflight=[],
                documentation=str(spec["documentation"]),
                available=_module_available("copytrade_pm.pm_operations", root)
                and _module_available(owner, root),
                limitations=list(spec["limitations"]),  # type: ignore[arg-type]
            )
        )
    for cap_id, spec in sorted(GROUP_OPERATIONS.items()):
        owner = str(spec["owner"])
        script_name = str(spec["script"])
        script_invocation = scripts.get(script_name)
        script_module = script_invocation.split(":", 1)[0] if script_invocation else owner
        results.append(
            _subcommand_entry(
                cap_id=cap_id,
                description=f"Mode variant for {script_name}",
                owner=owner,
                interface=str(spec["interface"]),
                classification=str(spec["classification"]),
                authority=str(spec["authority"]),
                access=spec["access"],  # type: ignore[arg-type]
                required_arguments=list(spec["required_arguments"]),  # type: ignore[arg-type]
                runtime_required_arguments=list(spec["runtime_required_arguments"]),  # type: ignore[arg-type]
                preflight=[],
                documentation=str(spec["documentation"]),
                available=(
                    script_name in scripts
                    and _module_available(script_module, root)
                    and _module_available(owner, root)
                    and (
                        script_name not in installed or installed[script_name] == script_invocation
                    )
                ),
                limitations=list(spec["limitations"]),  # type: ignore[arg-type]
            )
        )
    for cap, (module, invocation, family, safety, authority) in NATIVE.items():
        req_args = NATIVE_REQUIRED_ARGUMENTS.get(cap)
        runtime_args = (
            list(NATIVE_RUNTIME_REQUIRED_ARGUMENTS[cap])
            if cap in NATIVE_RUNTIME_REQUIRED_ARGUMENTS
            else (None if req_args is None else [])
        )
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
                "access": _copy_access(NATIVE_ACCESS.get(cap, UNKNOWN_ACCESS)),
                "dependencies": [],
                "required_arguments": req_args,
                "runtime_required_arguments": runtime_args,
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
                "runtime_required_arguments": None,
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


def _const_str_tuple(
    node: ast.AST, constants: dict[str, tuple[str, ...]] | None = None
) -> tuple[str, ...] | None:
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        vals = [_const_str(elt) for elt in node.elts]
        if all(val is not None for val in vals):
            return tuple(val for val in vals if val is not None)
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in {"tuple", "frozenset"} and len(node.args) == 1 and not node.keywords:
            if isinstance(node.args[0], ast.Name) and constants and node.args[0].id in constants:
                return constants[node.args[0].id]
            return _const_str_tuple(node.args[0], constants)
        if node.func.id == "sorted" and len(node.args) == 1 and not node.keywords:
            resolved = _const_str_tuple(node.args[0], constants)
            return tuple(sorted(resolved)) if resolved is not None else None
    if isinstance(node, ast.Name) and constants and node.id in constants:
        return constants[node.id]
    return None


def _extract_module_constants(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    constants: dict[str, tuple[str, ...]] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            name = stmt.targets[0].id
            if isinstance(stmt.value, ast.Dict):
                keys = [_const_str(k) for k in stmt.value.keys if k is not None]
                if len(keys) == len(stmt.value.keys) and all(k is not None for k in keys):
                    constants[name] = tuple(k for k in keys if k is not None)
                    continue
            resolved = _const_str_tuple(stmt.value, constants)
            if resolved is not None:
                constants[name] = resolved
    return constants


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
    constants: dict[str, tuple[str, ...]] | None = None,
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
        # Permit argparse.BooleanOptionalAction Attribute
        if not (
            isinstance(action_node, ast.Attribute) and action_node.attr == "BooleanOptionalAction"
        ):
            return "dynamic_action"
    nargs_node = kwargs.get("nargs")
    if nargs_node is not None and not (
        isinstance(nargs_node, ast.Constant) and isinstance(nargs_node.value, (str, int))
    ):
        return "dynamic_nargs"
    action = action_node.value if isinstance(action_node, ast.Constant) else None
    nargs = nargs_node.value if isinstance(nargs_node, ast.Constant) else None
    choices_node = kwargs.get("choices")
    choices_vals: tuple[str, ...] | None = None
    choices_expr: str | None = None
    if choices_node is not None:
        choices_vals = _const_str_tuple(choices_node, constants)
        if choices_vals is None:
            choices_expr = ast.unparse(choices_node)
    if option.startswith("-"):
        required = bool(req_node.value) if isinstance(req_node, ast.Constant) else False
        flag_only = action in {"store_true", "store_false", "count"}
        node["options"][option] = {
            "required": required,
            "flag_only": flag_only,
            "action": action,
            "choices": choices_vals,
            "choices_expr": choices_expr,
            "group_idx": group_idx,
        }
        if group_idx is not None and group_required:
            node["required_groups"][group_idx].append(option)
    else:
        pos_required = nargs not in {"?", "*"} and nargs != 0
        node["positionals"][option] = {
            "required": pos_required,
            "choices": choices_vals,
            "choices_expr": choices_expr,
        }
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


def _validate_access_entry(
    access: dict[str, object] | None,
    *,
    safety: str,
    missing_code: str,
    invalid_code: str,
    unverified_code: str,
    inconsistent_code: str,
) -> list[str]:
    if access is None or set(access) != ACCESS_KEYS:
        return [missing_code]
    problems: list[str] = []
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
        problems.append(invalid_code)
    if any(access[k] == "UNKNOWN" for k in ACCESS_KEYS):
        problems.append(unverified_code)
    if safety == "READ_ONLY" and access["write_targets"] != []:
        problems.append(inconsistent_code)
    if (
        safety in {"LOCAL_MUTATION", "PROTECTED_MUTATION", "BROKER_OR_TRADING"}
        and not access["write_targets"]
    ):
        problems.append(inconsistent_code)
    return problems


def _parser_required_sets(
    spec: dict, *, ignore_positionals: frozenset[str] = frozenset()
) -> tuple[set[str], int, list[tuple[str, ...]]]:
    """Return (required_options, required_positional_count, required_groups)."""
    req_opts = {opt for opt, meta in spec["options"].items() if meta["required"]}
    req_pos_count = sum(
        1
        for pos_name, meta in spec["positionals"].items()
        if meta["required"] and pos_name not in ignore_positionals
    )
    req_groups = [tuple(sorted(grp)) for grp in spec.get("required_groups", []) if grp]
    return req_opts, req_pos_count, req_groups


def _split_declared_required_args(tokens: list[str]) -> tuple[set[str], int, list[tuple[str, ...]]]:
    opts: set[str] = set()
    pos_count = 0
    groups: list[tuple[str, ...]] = []
    for tok in tokens:
        if " | " in tok:
            groups.append(tuple(sorted(part.split()[0] for part in tok.split(" | "))))
        else:
            head = tok.split()[0]
            if head.startswith("-"):
                opts.add(head)
            else:
                pos_count += 1
    return opts, pos_count, groups


def _validate_registry_operations(root: Path) -> list[str]:
    """Validate copytrade-wallet-registry leaves, --apply modes, required flags and access."""
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

        problems.extend(
            _validate_access_entry(
                REGISTRY_ACCESS.get(op),
                safety=REGISTRY_OPERATIONS[op],
                missing_code=f"MISSING_REGISTRY_ACCESS:{op}",
                invalid_code=f"INVALID_ACCESS_SCHEMA:{op}",
                unverified_code=f"UNVERIFIED_REGISTRY_ACCESS:{op}",
                inconsistent_code=f"INCONSISTENT_REGISTRY_ACCESS:{op}",
            )
        )

    for op in set(REGISTRY_ACCESS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_ACCESS:{op}")
    for op in set(REGISTRY_REQUIRED_ARGUMENTS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_REQUIRED_ARG_ENTRY:{op}")
    for op in set(REGISTRY_DISPATCH_REQUIRED_ARGUMENTS) - set(REGISTRY_OPERATIONS):
        problems.append(f"STALE_REGISTRY_DISPATCH_ARG_ENTRY:{op}")

    return problems


_OPERATIONS_NATIVE_LEAVES = {
    "wallets list": "wallet.inventory",
    "wallets show": "wallet.lookup",
    "portfolios current": "portfolio.current",
    "portfolios show": "portfolio.show",
    "research list": "research.report.catalog",
    "paper status": "paper.status",
    "contracts compare": "research.contract_selector",
    "health": "runtime.health",
}
_OPERATIONS_NATIVE_MIRRORS = (
    ("wallet.alias", "wallets show"),
    ("research.catalog", "research list"),
)
_PM03_CLI_ACTIONS = frozenset({"compare", "compare_pm04", "replay"})
_PM03_CAPABILITIES = {
    "compare": "account.pm03.simulate.compare",
    "compare_pm04": "account.pm03.simulate.compare_pm04",
    "replay": "account.pm03.simulate.replay",
}
_CLASS_RANK = {
    "READ_ONLY": 0,
    "LOCAL_MUTATION": 1,
    "PROTECTED_MUTATION": 2,
    "BROKER_OR_TRADING": 3,
}
_NON_READ_ONLY_GROUP_MODES = frozenset(
    {
        "source.public_trades.observe",
        "source.public_trades.plan",
        "paper.public_unit.apply",
        "account.pm03.simulate.compare",
        "account.pm03.simulate.compare_pm04",
        "account.pm03.simulate.replay",
        "source.receipts.init",
        "source.receipts.ingest",
        "source.receipts.audit",
        "source.receipts.outcome",
        "paper.unit_bundle.stage",
        "production.export.cli.write",
        "paper.standby.worker",
        "paper.standby.watchdog",
        "paper.observed_execution.l2",
        "paper.observed_execution.vike_minute",
        "paper.observer.continuous",
        "paper.observer.continuous_watchdog",
        "market.continuous_canary",
    }
)
_GROUP_NATIVE_SCRIPTS = {
    "paper.observer.preflight": "copytrade-pm-paper-observe",
    "paper.observer.continuous": "copytrade-pm-paper-observe",
    "paper.observer.continuous_health": "copytrade-pm-paper-observer-health",
    "paper.observer.continuous_watchdog": "copytrade-pm-paper-observer-health",
    "paper.observer.shadow_report": "copytrade-pm-paper-observer-health",
    "market.continuous_canary": "copytrade-pm-market-ccxt",
    "paper.identity_reseal_preview": "copytrade-pm-paper-registry-audit",
}
_GROUP_SCRIPT_MODE_CONTRACTS: dict[str, dict[str, object]] = {
    "copytrade-pm-actuary": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-agent-eval": {"store_true": frozenset({"--list-tasks"}), "choices": {}},
    "copytrade-pm-combo2-paper": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-handoff": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-market-audit": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-market-ccxt": {
        "store_true": frozenset({"--ack-shared-ip-connection-budget"}),
        "choices": {},
    },
    "copytrade-pm-market-stream": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-paper-candidate-verify": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-paper-observe": {
        "store_true": frozenset({"--preflight-only", "--diagnose-preflight"}),
        "choices": {},
    },
    "copytrade-pm-paper-observed": {
        "store_true": frozenset({"--watch"}),
        "choices": {
            "--portfolio": ("P1", "P14", "P16"),
            "--price-mode": ("l2", "vike_minute"),
        },
    },
    "copytrade-pm-paper-observer-health": {
        "store_true": frozenset(
            {"--continuous", "--watch", "--require-watchdog", "--shadow-report"}
        ),
        "choices": {},
    },
    "copytrade-pm-paper-preflight": {
        "store_true": frozenset({"--inspect-services"}),
        "choices": {},
    },
    "copytrade-pm-paper-readiness": {
        "store_true": frozenset(),
        "choices": {
            "--portfolio": ("P1", "P14"),
            "--sizing-policy": ("FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV"),
        },
    },
    "copytrade-pm-paper-registry-audit": {
        "store_true": frozenset({"--prospective-reseal-preview"}),
        "choices": {"--portfolio": ("P1", "P14")},
    },
    "copytrade-pm-paper-report": {"store_true": frozenset({"--cost-stress"}), "choices": {}},
    "copytrade-pm-paper-source-campaign": {
        "store_true": frozenset({"--include-subaccounts", "--include-collateral"}),
        "choices": {"--portfolio": ("P1", "P14")},
    },
    "copytrade-pm-paper-standby": {
        "store_true": frozenset({"--once", "--unprotected-canary"}),
        "choices": {"role": ("worker", "watchdog"), "--portfolio": ("P1", "P14")},
    },
    "copytrade-pm-paper-status": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-paper-unit-bundle": {"store_true": frozenset({"--verify"}), "choices": {}},
    "copytrade-pm-paper-watchdog": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-production-economics": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-production-export": {
        "store_true": frozenset(),
        "choices": {"--sizing-policy": ("FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV")},
    },
    "copytrade-pm-production-manifest": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-public-observer-unit": {"store_true": frozenset({"--apply"}), "choices": {}},
    "copytrade-pm-public-trades": {
        "store_true": frozenset({"--ack-shared-ip-connection-budget"}),
        "choices": {
            "--mode": ("observe", "plan"),
            "--timing-policy": ("UTC_BUCKET_CLOSE", "UTC_BUCKET_PLUS_5M"),
        },
    },
    "copytrade-pm-rank": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-receipts": {
        "store_true": frozenset(),
        "choices": {"action": ("init", "ingest", "audit", "outcome", "inspect")},
    },
    "copytrade-pm-replay": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-research": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-review-gate": {
        "store_true": frozenset(),
        "choices": {
            "--operation": (
                "FROZEN_ROSTER_PROMOTION",
                "MATERIAL_POLICY_CHANGE",
                "PERMANENT_ROSTER_DELETION",
                "SCIENTIFIC_QUALIFICATION",
            )
        },
    },
    "copytrade-pm-scope": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-shadow": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-source": {
        "store_true": frozenset({"--forever"}),
        "choices": {"--portfolio": "tuple(PORTFOLIO_PODS)"},
    },
    "copytrade-pm-source-abc": {"store_true": frozenset({"--forever"}), "choices": {}},
    "copytrade-pm-source-audit": {
        "store_true": frozenset(),
        "choices": {"--portfolio": "tuple(PORTFOLIOS)"},
    },
    "copytrade-pm-source-scope": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-track-b-prefect": {"store_true": frozenset(), "choices": {}},
    "copytrade-pm-vike-fills": {
        "store_true": frozenset({"--positions", "--dedicated-key-only"}),
        "choices": {},
    },
    "copytrade-pm-vike-minute": {"store_true": frozenset({"--watch"}), "choices": {}},
}
_VALIDATE_LIMITATIONS = [
    "Owner-specific bounded AST inspectors cover wallet_registry.py, pm_operations.py (+ pm_cwsa_chapter2_gate.add_arguments), 39 GROUPS script parsers, and pm03_cli.execute rather than arbitrary dynamic Python.",
    "pm03_cli.execute (--input JSON spec.action) and production_economics.py POLICIES flag generation rely on reviewed owner contracts rather than arbitrary dynamic dispatch inference.",
    "Conditional runtime_required_arguments capture mode-specific runtime requirements verified from owner dispatch contracts and are kept separate from argparse required_arguments.",
    "CLI/NATIVE/MODULE entries outside reviewed subcommands/modes retain UNKNOWN access rather than inferred safety.",
]


def _eval_static_condition(test: ast.AST, env: dict[str, str]) -> bool | None:
    if isinstance(test, ast.BoolOp):
        vals = [_eval_static_condition(v, env) for v in test.values]
        if any(v is None for v in vals):
            return None
        return all(vals) if isinstance(test.op, ast.And) else any(vals)
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        left = test.left
        right = test.comparators[0]
        if not isinstance(left, ast.Name) or left.id not in env:
            return None
        lval = env[left.id]
        op = test.ops[0]
        if isinstance(op, (ast.Eq, ast.NotEq)):
            rval = _const_str(right)
            if rval is None:
                return None
            return lval == rval if isinstance(op, ast.Eq) else lval != rval
        if isinstance(op, (ast.In, ast.NotIn)):
            rvals = _const_str_tuple(right)
            if rvals is None:
                return None
            return lval in rvals if isinstance(op, ast.In) else lval not in rvals
    return None


def _inspect_cwsa_add_arguments(root: Path, target_node: dict) -> list[str]:
    cwsa_path = root / "src/copytrade_pm/pm_cwsa_chapter2_gate.py"
    if not cwsa_path.is_file():
        return ["MISSING_OWNER_MODULE:copytrade_pm.pm_cwsa_chapter2_gate"]
    tree = ast.parse(cwsa_path.read_text(encoding="utf-8"))
    constants = _extract_module_constants(tree)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "add_arguments"]
    if len(funcs) != 1 or len(funcs[0].args.args) != 1:
        return ["UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_add_arguments"]
    param_name = funcs[0].args.args[0].arg
    all_calls = {
        id(n)
        for n in ast.walk(funcs[0])
        if isinstance(n, ast.Call) and _call_name(n) in PARSER_CALL_NAMES
    }
    visited: set[int] = set()
    for stmt in funcs[0].body:
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            return ["UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_add_arguments_stmt"]
        call = stmt.value
        if (
            not isinstance(call.func, ast.Attribute)
            or not isinstance(call.func.value, ast.Name)
            or call.func.value.id != param_name
            or call.func.attr != "add_argument"
        ):
            return ["UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_add_arguments_call"]
        visited.add(id(call))
        err = _register_registry_argument(
            target_node, call, group_idx=None, group_required=False, constants=constants
        )
        if err:
            return [f"UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_{err}"]
    if visited != all_calls:
        return ["UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_non_linear_call"]
    return []


def _inspect_operations_parser(root: Path) -> tuple[dict[str, dict], list[str]]:
    """Bounded AST inspector for pm_operations.parser() and pm_cwsa_chapter2_gate.add_arguments."""
    ops_path = root / "src/copytrade_pm/pm_operations.py"
    if not ops_path.is_file():
        return {}, ["MISSING_ENTRY_MODULE:copytrade-pm"]
    tree = ast.parse(ops_path.read_text(encoding="utf-8"))
    constants = _extract_module_constants(tree)
    all_parser_calls = {
        id(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) in PARSER_CALL_NAMES
    }
    parser_defs = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "parser"
    ]
    if len(parser_defs) != 1:
        return {}, ["UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:missing_parser"]

    parser_vars: dict[str, tuple[str, ...]] = {}
    subparser_vars: dict[str, tuple[str, ...]] = {}
    nodes: dict[tuple[str, ...], dict] = {}
    visited_calls: set[int] = set()
    errors: list[str] = []

    def _new_node() -> dict:
        return {
            "has_subparsers": False,
            "options": {},
            "positionals": {},
            "required_groups": [],
        }

    def _handle_parser_call(
        call: ast.Call,
        target: str | None,
        local_parsers: dict[str, tuple[str, ...]],
        local_subparsers: dict[str, tuple[str, ...]],
    ) -> None:
        if isinstance(call.func, ast.Name) and call.func.id == "add_arguments":
            if len(call.args) != 1 or call.keywords or not isinstance(call.args[0], ast.Name):
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_add_arguments_call")
                return
            arg_path = local_parsers.get(call.args[0].id)
            if arg_path is None:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:cwsa_unknown_parser")
                return
            errors.extend(_inspect_cwsa_add_arguments(root, nodes[arg_path]))
            return

        if not isinstance(call.func, ast.Attribute):
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:unknown_call")
            return
        attr = call.func.attr
        if attr not in PARSER_CALL_NAMES:
            return
        visited_calls.add(id(call))
        recv = call.func.value
        recv_name = recv.id if isinstance(recv, ast.Name) else None

        if attr == "ArgumentParser":
            if isinstance(recv, ast.Name) and recv.id == "argparse" and target and () not in nodes:
                nodes[()] = _new_node()
                local_parsers[target] = ()
            else:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:ArgumentParser")
        elif attr == "add_subparsers":
            if recv_name not in local_parsers or target is None:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:add_subparsers")
            else:
                path = local_parsers[recv_name]
                if len(path) >= 3:
                    errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:deep_subparsers")
                else:
                    nodes[path]["has_subparsers"] = True
                    local_subparsers[target] = path
        elif attr == "add_parser":
            kwargs = _keyword_map(call)
            name = _const_str(call.args[0]) if call.args else None
            if recv_name not in local_subparsers or kwargs is None or name is None:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:add_parser")
            elif not set(kwargs) <= {"help", "description"}:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:add_parser_kwargs")
            else:
                child = (*local_subparsers[recv_name], name)
                if child in nodes:
                    errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:duplicate_parser")
                else:
                    nodes[child] = _new_node()
                    if target is not None:
                        local_parsers[target] = child
        elif attr == "add_argument":
            if recv_name not in local_parsers:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:untracked_add_argument")
            else:
                err = _register_registry_argument(
                    nodes[local_parsers[recv_name]],
                    call,
                    group_idx=None,
                    group_required=False,
                    constants=constants,
                )
                if err:
                    errors.append(f"UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:{err}")
        else:
            errors.append(f"UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:{attr}")

    def _run_domain_loop(loop_stmt: ast.For) -> None:
        domains = _const_str_tuple(loop_stmt.iter)
        if not isinstance(loop_stmt.target, ast.Name) or domains is None or loop_stmt.orelse:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:dynamic_for_loop")
            return
        domain_var = loop_stmt.target.id
        for domain in domains:
            loc_p = dict(parser_vars)
            loc_s = dict(subparser_vars)
            for inner in loop_stmt.body:
                if (
                    isinstance(inner, ast.Assign)
                    and len(inner.targets) == 1
                    and isinstance(inner.targets[0], ast.Name)
                ):
                    tgt = inner.targets[0].id
                    call = inner.value if isinstance(inner.value, ast.Call) else None
                    if call and isinstance(call.func, ast.Attribute):
                        if (
                            call.func.attr == "add_parser"
                            and len(call.args) == 1
                            and isinstance(call.args[0], ast.Name)
                            and call.args[0].id == domain_var
                        ):
                            recv_n = (
                                call.func.value.id
                                if isinstance(call.func.value, ast.Name)
                                else None
                            )
                            if recv_n not in loc_s:
                                errors.append(
                                    "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_add_parser"
                                )
                                return
                            visited_calls.add(id(call))
                            child = (*loc_s[recv_n], domain)
                            nodes[child] = _new_node()
                            loc_p[tgt] = child
                            continue
                        _handle_parser_call(call, tgt, loc_p, loc_s)
                        continue
                elif (
                    isinstance(inner, ast.For)
                    and isinstance(inner.target, ast.Name)
                    and not inner.orelse
                ):
                    op_var = inner.target.id
                    if (
                        isinstance(inner.iter, ast.Subscript)
                        and isinstance(inner.iter.value, ast.Dict)
                        and isinstance(inner.iter.slice, ast.Name)
                        and inner.iter.slice.id == domain_var
                    ):
                        op_map: dict[str, tuple[str, ...]] = {}
                        for k_node, v_node in zip(
                            inner.iter.value.keys, inner.iter.value.values, strict=True
                        ):
                            k_str = _const_str(k_node) if k_node is not None else None
                            v_tup = _const_str_tuple(v_node)
                            if k_str is None or v_tup is None:
                                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_map")
                                return
                            op_map[k_str] = v_tup
                        if domain not in op_map:
                            errors.append(
                                "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:missing_domain_key"
                            )
                            return
                        for op_val in op_map[domain]:
                            env = {domain_var: domain, op_var: op_val}
                            op_p = dict(loc_p)
                            op_s = dict(loc_s)
                            for op_stmt in inner.body:
                                if (
                                    isinstance(op_stmt, ast.Assign)
                                    and len(op_stmt.targets) == 1
                                    and isinstance(op_stmt.targets[0], ast.Name)
                                    and isinstance(op_stmt.value, ast.Call)
                                ):
                                    c = op_stmt.value
                                    if (
                                        isinstance(c.func, ast.Attribute)
                                        and c.func.attr == "add_parser"
                                        and len(c.args) == 1
                                        and isinstance(c.args[0], ast.Name)
                                        and c.args[0].id == op_var
                                    ):
                                        rn = (
                                            c.func.value.id
                                            if isinstance(c.func.value, ast.Name)
                                            else None
                                        )
                                        if rn not in op_s:
                                            errors.append(
                                                "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_parser"
                                            )
                                            return
                                        visited_calls.add(id(c))
                                        child = (*op_s[rn], op_val)
                                        nodes[child] = _new_node()
                                        op_p[op_stmt.targets[0].id] = child
                                        continue
                                if isinstance(op_stmt, ast.If) and not op_stmt.orelse:
                                    cond = _eval_static_condition(op_stmt.test, env)
                                    if cond is None:
                                        errors.append(
                                            "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:dynamic_condition"
                                        )
                                        return
                                    for b_stmt in op_stmt.body:
                                        if not (
                                            isinstance(b_stmt, ast.Expr)
                                            and isinstance(b_stmt.value, ast.Call)
                                        ):
                                            errors.append(
                                                "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:if_body_stmt"
                                            )
                                            return
                                        if cond:
                                            _handle_parser_call(b_stmt.value, None, op_p, op_s)
                                        else:
                                            if _call_name(b_stmt.value) in PARSER_CALL_NAMES:
                                                visited_calls.add(id(b_stmt.value))
                                    continue
                                errors.append(
                                    "UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_stmt"
                                )
                                return
                        continue
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_body_stmt")
                return

    for stmt in parser_defs[0].body:
        if isinstance(stmt, ast.ImportFrom):
            if stmt.module != "pm_cwsa_chapter2_gate" or [a.name for a in stmt.names] != [
                "add_arguments"
            ]:
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:unexpected_import")
        elif (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            if not isinstance(stmt.value, ast.Call):
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:non_call_assign")
            else:
                _handle_parser_call(stmt.value, stmt.targets[0].id, parser_vars, subparser_vars)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            _handle_parser_call(stmt.value, None, parser_vars, subparser_vars)
        elif isinstance(stmt, ast.For):
            _run_domain_loop(stmt)
        elif (
            isinstance(stmt, ast.Return)
            and isinstance(stmt.value, ast.Name)
            and parser_vars.get(stmt.value.id) == ()
        ):
            continue
        else:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:" + type(stmt).__name__)

    if visited_calls != all_parser_calls:
        errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:non_linear_parser_call")

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
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:parent_node_constraint")

    leaves = {
        " ".join(path): spec for path, spec in nodes.items() if path and not spec["has_subparsers"]
    }
    return leaves, sorted(set(errors))


def _validate_operations_cli(root: Path) -> list[str]:
    leaves, problems = _inspect_operations_parser(root)
    if problems:
        return problems

    native_set = set(_OPERATIONS_NATIVE_LEAVES)
    subcmd_set = set(OPERATIONS_SUBCOMMANDS)
    for dup in sorted(native_set & subcmd_set):
        problems.append(f"DUPLICATE_OPERATIONS_CATALOG:{dup}")

    cataloged_leaves: dict[str, tuple[str, dict[str, object]]] = {}
    for leaf, cap_id in _OPERATIONS_NATIVE_LEAVES.items():
        if cap_id not in NATIVE:
            problems.append(f"STALE_OPERATIONS_NATIVE_CAP:{cap_id}")
            continue
        _, _, _, safety, _ = NATIVE[cap_id]
        cataloged_leaves[leaf] = (
            cap_id,
            {
                "classification": safety,
                "required_arguments": NATIVE_REQUIRED_ARGUMENTS.get(cap_id, []),
                "runtime_required_arguments": NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(cap_id, []),
                "access": NATIVE_ACCESS.get(cap_id),
            },
        )
    for leaf, spec in OPERATIONS_SUBCOMMANDS.items():
        cataloged_leaves[leaf] = (str(spec["id"]), spec)

    for leaf in sorted(set(leaves) - set(cataloged_leaves)):
        problems.append(f"UNLISTED_OPERATIONS_LEAF:{leaf}")
    for leaf in sorted(set(cataloged_leaves) - set(leaves)):
        problems.append(f"STALE_OPERATIONS_LEAF:{leaf}")

    def _check_entry(leaf: str, spec: dict, cap_id: str, meta: dict[str, object]) -> None:
        safety = str(meta["classification"])
        if safety != "READ_ONLY" or "--apply" in spec["options"]:
            problems.append(f"UNSAFE_OPERATIONS_CLASSIFICATION:{leaf}")

        parser_req_opts, parser_req_pos, _ = _parser_required_sets(spec)
        decl_req_opts, decl_req_pos, _ = _split_declared_required_args(
            list(meta.get("required_arguments") or [])  # type: ignore[arg-type]
        )
        for missing in sorted(parser_req_opts - decl_req_opts):
            problems.append(f"MISSING_OPERATIONS_REQUIRED_ARG:{leaf}:{missing}")
        for extra in sorted(decl_req_opts - parser_req_opts):
            problems.append(f"STALE_OPERATIONS_REQUIRED_ARG:{leaf}:{extra}")
        if decl_req_pos != parser_req_pos:
            problems.append(f"OPERATIONS_POSITIONAL_MISMATCH:{leaf}")

        for rtok in list(meta.get("runtime_required_arguments") or []):  # type: ignore[arg-type]
            flag = rtok.split()[0]
            if flag not in spec["options"] or flag in parser_req_opts:
                problems.append(f"STALE_OPERATIONS_RUNTIME_ARG:{leaf}:{flag}")

        problems.extend(
            _validate_access_entry(
                meta.get("access"),  # type: ignore[arg-type]
                safety=safety,
                missing_code=f"MISSING_OPERATIONS_ACCESS:{cap_id}",
                invalid_code=f"INVALID_ACCESS_SCHEMA:{cap_id}",
                unverified_code=f"UNVERIFIED_OPERATIONS_ACCESS:{cap_id}",
                inconsistent_code=f"INCONSISTENT_OPERATIONS_ACCESS:{cap_id}",
            )
        )

    for leaf, (cap_id, meta) in sorted(cataloged_leaves.items()):
        if leaf in leaves:
            _check_entry(leaf, leaves[leaf], cap_id, meta)
    for mirror_id, leaf in _OPERATIONS_NATIVE_MIRRORS:
        if leaf in leaves and mirror_id in NATIVE:
            _, _, _, safety, _ = NATIVE[mirror_id]
            _check_entry(
                leaf,
                leaves[leaf],
                mirror_id,
                {
                    "classification": safety,
                    "required_arguments": NATIVE_REQUIRED_ARGUMENTS.get(mirror_id, []),
                    "runtime_required_arguments": NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(
                        mirror_id, []
                    ),
                    "access": NATIVE_ACCESS.get(mirror_id),
                },
            )
    return sorted(set(problems))


def _inspect_group_script_parser(
    path: Path, script_name: str, *, allow_policies_loop: bool
) -> tuple[dict | None, list[str]]:
    """Bounded AST inspector for flat GROUPS CLI scripts (no subparsers, no dynamic loops)."""
    if not path.is_file():
        return None, [f"MISSING_ENTRY_MODULE:{script_name}"]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _extract_module_constants(tree)
    all_parser_calls = {
        id(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) in PARSER_CALL_NAMES
    }
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    entry_fn = funcs.get("main")
    if entry_fn is None:
        return None, [f"MISSING_MAIN:{script_name}"]
    has_calls_in_main = any(id(n) in all_parser_calls for n in ast.walk(entry_fn))
    if not has_calls_in_main and "run" in funcs:
        entry_fn = funcs["run"]

    node: dict = {
        "options": {},
        "positionals": {},
        "required_groups": [],
    }
    parser_vars: set[str] = set()
    group_vars: dict[str, tuple[int | None, bool]] = {}
    visited: set[int] = set()
    errors: list[str] = []
    saw_parse_args = False

    def _visit_call(call: ast.Call, target: str | None) -> None:
        nonlocal saw_parse_args
        if not isinstance(call.func, ast.Attribute):
            return
        attr = call.func.attr
        recv = call.func.value
        recv_name = recv.id if isinstance(recv, ast.Name) else None
        if attr in {"parse_args", "parse_known_args"} and recv_name in parser_vars:
            saw_parse_args = True
            if attr == "parse_known_args":
                visited.add(id(call))
            return
        if attr not in PARSER_CALL_NAMES:
            return
        visited.add(id(call))
        if attr == "ArgumentParser":
            if isinstance(recv, ast.Name) and recv.id == "argparse" and target and not parser_vars:
                parser_vars.add(target)
            else:
                errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:ArgumentParser")
        elif attr == "add_subparsers":
            errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:unexpected_subparsers")
        elif attr == "add_mutually_exclusive_group":
            kwargs = _keyword_map(call)
            req = kwargs.get("required") if kwargs is not None else None
            req_valid = req is None or (
                isinstance(req, ast.Constant) and isinstance(req.value, bool)
            )
            if recv_name not in parser_vars or target is None or kwargs is None or not req_valid:
                errors.append(
                    f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:add_mutually_exclusive_group"
                )
            else:
                req_flag = bool(req.value) if isinstance(req, ast.Constant) else False
                idx: int | None = None
                if req_flag:
                    idx = len(node["required_groups"])
                    node["required_groups"].append([])
                group_vars[target] = (idx, req_flag)
        elif attr == "add_argument":
            if recv_name in parser_vars:
                err = _register_registry_argument(
                    node, call, group_idx=None, group_required=False, constants=constants
                )
            elif recv_name in group_vars:
                idx, req_flag = group_vars[recv_name]
                err = _register_registry_argument(
                    node, call, group_idx=idx, group_required=req_flag, constants=constants
                )
            else:
                err = "untracked_add_argument"
            if err:
                errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:{err}")
        else:
            errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:{attr}")

    for stmt in entry_fn.body:
        if isinstance(stmt, ast.For):
            has_parser_call = any(id(n) in all_parser_calls for n in ast.walk(stmt))
            if not has_parser_call:
                continue
            if (
                allow_policies_loop
                and isinstance(stmt.iter, ast.Name)
                and stmt.iter.id == "POLICIES"
                and "POLICIES" in constants
                and isinstance(stmt.target, ast.Name)
                and len(stmt.body) == 1
                and isinstance(stmt.body[0], ast.Expr)
                and isinstance(stmt.body[0].value, ast.Call)
            ):
                loop_call = stmt.body[0].value
                visited.add(id(loop_call))
                for policy in constants["POLICIES"]:
                    node["options"][f"--{policy.lower().replace('_', '-')}"] = {
                        "required": False,
                        "flag_only": False,
                        "action": None,
                        "choices": None,
                        "choices_expr": None,
                        "group_idx": None,
                    }
                continue
            errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:dynamic_for_loop")
            continue
        target: str | None = None
        call: ast.Call | None = None
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            target = stmt.targets[0].id
            call = stmt.value if isinstance(stmt.value, ast.Call) else None
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        if call is not None:
            _visit_call(call, target)

    if not saw_parse_args:
        errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:missing_parse_args")
    if visited != all_parser_calls:
        errors.append(f"UNSUPPORTED_GROUP_PARSER_CONSTRUCT:{script_name}:non_linear_parser_call")
    return node, sorted(set(errors))


def _inspect_pm03_cli_dispatch(path: Path) -> tuple[set[str], list[str]]:
    """Bounded AST inspector for pm03_cli.execute JSON spec['action'] dispatch."""
    if not path.is_file():
        return set(), ["MISSING_OWNER_MODULE:copytrade_pm.pm03_cli"]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    exec_defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute"]
    if len(exec_defs) != 1:
        return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:missing_execute"]

    def _is_spec_action_get(expr: ast.AST) -> bool:
        return (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and isinstance(expr.func.value, ast.Name)
            and expr.func.value.id == "spec"
            and expr.func.attr == "get"
            and len(expr.args) == 1
            and _const_str(expr.args[0]) == "action"
            and not expr.keywords
        )

    def _is_unknown_action_raise(stmts: list[ast.stmt]) -> bool:
        if len(stmts) != 1 or not isinstance(stmts[0], ast.Raise):
            return False
        exc = stmts[0].exc
        return (
            isinstance(exc, ast.Call)
            and isinstance(exc.func, ast.Name)
            and exc.func.id == "ValueError"
            and len(exc.args) == 1
            and _const_str(exc.args[0]) == "UNKNOWN_PM03_ACTION"
        )

    dispatch_if: ast.If | None = None
    for stmt in exec_defs[0].body:
        if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
            if _is_spec_action_get(stmt.test.left):
                dispatch_if = stmt
                break
    if dispatch_if is None:
        return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:dynamic_dispatch"]

    actions: set[str] = set()
    curr: ast.If | None = dispatch_if
    while curr is not None:
        if (
            not isinstance(curr.test, ast.Compare)
            or len(curr.test.ops) != 1
            or not isinstance(curr.test.ops[0], ast.Eq)
            or len(curr.test.comparators) != 1
            or not _is_spec_action_get(curr.test.left)
        ):
            return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:non_literal_branch"]
        action_val = _const_str(curr.test.comparators[0])
        if action_val is None:
            return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:dynamic_action_value"]
        actions.add(action_val)
        if not curr.orelse:
            return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:missing_fail_closed_else"]
        if len(curr.orelse) == 1 and isinstance(curr.orelse[0], ast.If):
            curr = curr.orelse[0]
        elif _is_unknown_action_raise(curr.orelse):
            curr = None
        else:
            return set(), ["UNSUPPORTED_PM03_DISPATCH_CONSTRUCT:invalid_else_branch"]
    return actions, []


_GROUP_MODE_POSITIONALS = {
    "copytrade-pm-receipts": frozenset({"action"}),
    "copytrade-pm-paper-standby": frozenset({"role"}),
}


def _validate_group_scripts(root: Path, scripts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    parsed_scripts: dict[str, dict] = {}

    for name in sorted(scripts):
        if name in {"copytrade-wallet-registry", "copytrade-pm"}:
            continue
        invocation = scripts[name]
        module = invocation.split(":", 1)[0]
        file_path = root / "src" / Path(*module.split(".")).with_suffix(".py")
        spec, errs = _inspect_group_script_parser(
            file_path, name, allow_policies_loop=(name == "copytrade-pm-production-economics")
        )
        if errs:
            problems.extend(errs)
            continue
        assert spec is not None
        parsed_scripts[name] = spec

        contract = _GROUP_SCRIPT_MODE_CONTRACTS.get(name)
        if contract is None:
            problems.append(f"UNREVIEWED_GROUP_MODE_CONTRACT:{name}")
            continue
        expected_store_true: frozenset[str] = contract["store_true"]  # type: ignore[assignment]
        expected_choices: dict[str, object] = contract["choices"]  # type: ignore[assignment]

        actual_store_true = {
            opt for opt, meta in spec["options"].items() if meta["action"] == "store_true"
        }
        for extra_flag in sorted(actual_store_true - expected_store_true):
            problems.append(f"UNLISTED_GROUP_MODE_FLAG:{name}:{extra_flag}")
        for missing_flag in sorted(expected_store_true - actual_store_true):
            problems.append(f"STALE_GROUP_MODE_FLAG:{name}:{missing_flag}")

        actual_choices: dict[str, dict] = {}
        for opt, meta in spec["options"].items():
            if meta["choices"] is not None or meta["choices_expr"] is not None:
                actual_choices[opt] = meta
        for pos, meta in spec["positionals"].items():
            if meta["choices"] is not None or meta["choices_expr"] is not None:
                actual_choices[pos] = meta

        for opt in sorted(set(actual_choices) - set(expected_choices)):
            problems.append(f"UNLISTED_GROUP_MODE_CHOICE:{name}:{opt}")
        for opt in sorted(set(expected_choices) - set(actual_choices)):
            problems.append(f"STALE_GROUP_MODE_CHOICE:{name}:{opt}")
        for opt in sorted(set(actual_choices) & set(expected_choices)):
            meta = actual_choices[opt]
            exp = expected_choices[opt]
            if isinstance(exp, tuple):
                actual_vals = tuple(meta["choices"] or ())
                for extra_c in sorted(set(actual_vals) - set(exp)):
                    problems.append(f"UNLISTED_GROUP_MODE_CHOICE:{name}:{opt}:{extra_c}")
                for missing_c in sorted(set(exp) - set(actual_vals)):
                    problems.append(f"STALE_GROUP_MODE_CHOICE:{name}:{opt}:{missing_c}")
            elif meta["choices_expr"] != exp:
                problems.append(f"GROUP_CHOICE_EXPR_DRIFT:{name}:{opt}")

    # Validate pm03_cli dynamic JSON spec.get("action") contract.
    pm03_actions, pm03_errs = _inspect_pm03_cli_dispatch(root / "src/copytrade_pm/pm03_cli.py")
    if pm03_errs:
        problems.extend(pm03_errs)
    else:
        for extra_action in sorted(pm03_actions - _PM03_CLI_ACTIONS):
            problems.append(f"UNLISTED_PM03_ACTION:{extra_action}")
        for missing_action in sorted(_PM03_CLI_ACTIONS - pm03_actions):
            problems.append(f"STALE_PM03_ACTION:{missing_action}")

    # Validate GROUP_OPERATIONS entries + NATIVE script-bound entries.
    parent_max_rank: dict[str, int] = {}
    for cap_id, meta in GROUP_OPERATIONS.items():
        script_name = str(meta["script"])
        safety = str(meta["classification"])
        if cap_id in _NON_READ_ONLY_GROUP_MODES and safety == "READ_ONLY":
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{cap_id}")
        parent_max_rank[script_name] = max(
            parent_max_rank.get(script_name, -1), _CLASS_RANK.get(safety, 99)
        )
        script_spec = parsed_scripts.get(script_name)
        if script_spec is not None:
            p_opts, p_pos, p_groups = _parser_required_sets(
                script_spec,
                ignore_positionals=_GROUP_MODE_POSITIONALS.get(script_name, frozenset()),
            )
            d_opts, d_pos, d_groups = _split_declared_required_args(
                list(meta["required_arguments"])  # type: ignore[arg-type]
            )
            for missing in sorted(p_opts - d_opts):
                problems.append(f"MISSING_GROUP_REQUIRED_ARG:{cap_id}:{missing}")
            for extra in sorted(d_opts - p_opts):
                problems.append(f"STALE_GROUP_REQUIRED_ARG:{cap_id}:{extra}")
            if d_pos != p_pos or sorted(d_groups) != sorted(p_groups):
                problems.append(f"GROUP_REQUIRED_GROUP_OR_POSITIONAL_MISMATCH:{cap_id}")
            for rtok in list(meta["runtime_required_arguments"]):  # type: ignore[arg-type]
                if rtok.startswith("spec."):
                    continue
                rflag = rtok.split()[0]
                if rflag not in script_spec["options"] or rflag in p_opts:
                    problems.append(f"STALE_GROUP_RUNTIME_ARG:{cap_id}:{rflag}")
        problems.extend(
            _validate_access_entry(
                meta.get("access"),  # type: ignore[arg-type]
                safety=safety,
                missing_code=f"MISSING_GROUP_ACCESS:{cap_id}",
                invalid_code=f"INVALID_ACCESS_SCHEMA:{cap_id}",
                unverified_code=f"UNVERIFIED_GROUP_ACCESS:{cap_id}",
                inconsistent_code=f"INCONSISTENT_GROUP_ACCESS:{cap_id}",
            )
        )

    for script_name, max_child_rank in parent_max_rank.items():
        parent_desc = GROUPS.get(script_name)
        if parent_desc is not None and _CLASS_RANK.get(parent_desc[2], -1) < max_child_rank:
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{script_name}")

    for cap_id, script_name in _GROUP_NATIVE_SCRIPTS.items():
        _, _, _, safety, _ = NATIVE[cap_id]
        if cap_id in _NON_READ_ONLY_GROUP_MODES and safety == "READ_ONLY":
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{cap_id}")
        script_spec = parsed_scripts.get(script_name)
        if script_spec is not None:
            p_opts, p_pos, _ = _parser_required_sets(script_spec)
            d_opts, d_pos, _ = _split_declared_required_args(
                list(NATIVE_REQUIRED_ARGUMENTS.get(cap_id, []))
            )
            for missing in sorted(p_opts - d_opts):
                problems.append(f"MISSING_NATIVE_REQUIRED_ARG:{cap_id}:{missing}")
            for extra in sorted(d_opts - p_opts):
                problems.append(f"STALE_NATIVE_REQUIRED_ARG:{cap_id}:{extra}")
            if d_pos != p_pos:
                problems.append(f"NATIVE_POSITIONAL_MISMATCH:{cap_id}")
            for rtok in NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(cap_id, []):
                rflag = rtok.split()[0]
                if rflag not in script_spec["options"] or rflag in p_opts:
                    problems.append(f"STALE_NATIVE_RUNTIME_ARG:{cap_id}:{rflag}")
        problems.extend(
            _validate_access_entry(
                NATIVE_ACCESS.get(cap_id),
                safety=safety,
                missing_code=f"MISSING_NATIVE_ACCESS:{cap_id}",
                invalid_code=f"INVALID_ACCESS_SCHEMA:{cap_id}",
                unverified_code=f"UNVERIFIED_NATIVE_ACCESS:{cap_id}",
                inconsistent_code=f"INCONSISTENT_NATIVE_ACCESS:{cap_id}",
            )
        )

    return sorted(set(problems))


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
    problems.extend(_validate_registry_operations(root))
    problems.extend(_validate_operations_cli(root))
    problems.extend(_validate_group_scripts(root, declared))
    return {
        "schema": "copytrade_capability_validation_v1",
        "status": "VERIFIED" if not problems else "BLOCKED",
        "cli_count": len(declared),
        "module_only_count": len(NATIVE) + len(EXTRA_MODULES),
        "capability_count": len(entries),
        "errors": sorted(set(problems)),
        "limitations": list(_VALIDATE_LIMITATIONS),
    }


def render(items: object) -> str:
    return json.dumps(items, sort_keys=True, indent=2)
