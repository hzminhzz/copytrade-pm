"""Reviewed static capability catalog and declared access contracts.

Declarative capability metadata and mode contracts live here, separate from
AST inspection and validation logic so catalog edits stay isolated.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=128)
def _parse_static_source(source: str) -> ast.Module:
    """Cache read-only ASTs by exact source contents, not file path or timestamp.

    Inspectors only traverse these trees. Mutated files always produce new
    contents and a new parse, preserving fail-closed drift detection.
    """
    return ast.parse(source)


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
    "copytrade-pm-paper-observer-health": ("paper.observer_health", "paper", "LOCAL_MUTATION"),
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
    "wallet_store": (
        "copytrade_pm.wallet_store",
        "python -c 'import copytrade_pm.wallet_store'",
        "source",
        "LOCAL_MUTATION",
        "HIVE_PARQUET_WALLET_STORE_AND_SQLITE_CATALOG",
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


class _AccessDict(TypedDict):
    read_targets: list[str]
    write_targets: list[str]
    network: bool
    credentials: bool
    privacy: str


class _BaseCommandSpec(TypedDict):
    owner: str
    family: str
    classification: str
    authority: str
    documentation: str
    required_arguments: list[str]
    runtime_required_arguments: list[str]
    access: _AccessDict
    limitations: list[str]


class _OperationsSubcommandSpec(_BaseCommandSpec):
    id: str


class _GroupOperationSpec(_BaseCommandSpec):
    script: str
    interface: str


class _GroupModeContract(TypedDict):
    store_true: frozenset[str]
    choices: dict[str, tuple[str, ...] | str]


# Registry access schema reused across reviewed subcommand and mode records.
def _access_entry(
    read_targets: list[str],
    write_targets: list[str],
    *,
    network: bool = False,
    credentials: bool = False,
    privacy: str = "OWNER_PRIVATE_REDACTED",
) -> _AccessDict:
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
) -> _AccessDict:
    return _access_entry(
        read_targets,
        write_targets,
        network=False,
        credentials=False,
        privacy=privacy,
    )


# Reviewed subcommands for copytrade-pm (pm_operations.py) not already covered
# by existing NATIVE capability IDs. Already-cataloged leaves remain in NATIVE.
OPERATIONS_SUBCOMMANDS: dict[str, _OperationsSubcommandSpec] = {
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
    "cwsa chapter2 explain": {
        "id": "operations.cwsa.chapter2.explain",
        "owner": "copytrade_pm.pm_cwsa_chapter2_projection",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "CWSA_CHAPTER2_EVIDENCE_PROJECTION",
        "documentation": "docs/CWSA-CHAPTER2-20261112.md",
        "required_arguments": ["--portfolio PORTFOLIO"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "optional_private_cwsa_source_sqlite",
                "optional_single_pm03_journal",
                "optional_private_quote_sqlite",
                "optional_signed_paper_release",
                "optional_qualification_attestation",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Metadata mode reads only scoped SQLite seals and native doctor; "
            "--inspection evidence additionally reads Chapter 2 source, single-portfolio PM03 and optional quote chains",
            "Missing evidence never implies Guardian financial or broker authorization",
        ],
    },
    "cwsa chapter2 site-view": {
        "id": "operations.cwsa.chapter2.site.view",
        "owner": "copytrade_pm.pm_cwsa_chapter2_projection",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "CWSA_CHAPTER2_EVIDENCE_PROJECTION",
        "documentation": "docs/AGENT-NATIVE-OPERATIONS.md",
        "required_arguments": ["--portfolio PORTFOLIO"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "optional_private_cwsa_source_sqlite",
                "optional_single_pm03_journal",
                "optional_private_quote_sqlite",
                "optional_signed_paper_release",
                "optional_qualification_attestation",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Returns a strict subset of the same existing Chapter 2 owner explanation as the CLI",
            "No site transport, authentication, publisher or deployed Site is established by this command",
            "No financial effects or Guardian permission",
        ],
    },
    "cwsa chapter2 recover": {
        "id": "operations.cwsa.chapter2.recover",
        "owner": "copytrade_pm.pm_cwsa_chapter2_projection",
        "family": "operations",
        "classification": "READ_ONLY",
        "authority": "OPTIONAL_PROP_PRODUCTION_GUARDIAN_OWNER",
        "documentation": "docs/CWSA-CHAPTER2-20261112.md",
        "required_arguments": [
            "--guardian-journal PATH",
            "--intent-id INTENT_ID",
            "--observed-at-ms UTC_EPOCH_MS",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["optional_original_guardian_journal_sqlite_via_read_only_owner"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Requires the optional compatible prop-production owner package and explicit private journal path",
            "Original Guardian Journal.read verifies the hash chain; no direct broker or Guardian mutations",
            "Missing owner evidence remains UNKNOWN; results never grant dispatch, retry, or trading authorization",
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
    "research preflight": {
        "id": "research.preflight",
        "owner": "copytrade_pm.pm_offline_job_catalog",
        "family": "research",
        "classification": "READ_ONLY",
        "authority": "SHA_VERIFIED_OFFLINE_JOB_REPORT_CACHE",
        "documentation": DOC,
        "required_arguments": [],
        "runtime_required_arguments": ["--cache-root PATH", "--request PATH"],
        "access": _access_entry(
            [
                "sha_verified_immutable_offline_job_cache",
                "private_research_preflight_request_json",
                "optional_local_immutable_partitions",
            ],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Read-only reuse & bounded-acquisition preflight checks SHA-verified job reports, "
            "coverage receipts, optional --partition-root immutable partitions, remote object/column/row-group "
            "cost budgets (via pm_bounded_acquisition.plan_bounded_acquisition; fails closed with "
            "REMOTE_METADATA_UNAVAILABLE when missing unit metadata is absent), and PIT/holdout bounds; "
            "performs zero remote scans or credential collection and never supplies fresh balances, "
            "quotes, HALT clearance, Copy Mandates, paper financial proof, or trading authorization",
            "--cache-root PATH and --request PATH are runtime-required for VERIFIED results",
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
GROUP_OPERATIONS: dict[str, _GroupOperationSpec] = {
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
        "limitations": [
            "RETIRED_V4_T300: historical capability only; entrypoint refuses new runs",
            "Legacy CCXT catalog path was used before retirement",
        ],
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
            "RETIRED_V4_T300: historical capability only; entrypoint refuses new runs",
            "Legacy Vike path required --propr-catalog PATH and --price-db PATH",
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
        "runtime_required_arguments": [
            "--continuous-config PATH",
            "--diagnose-preflight",
            "--preflight-only",
        ],
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
            "Read-only budget diagnostic; requires --continuous-config, --preflight-only, and --diagnose-preflight"
        ],
    },
    "paper.observer.finite": {
        "script": "copytrade-pm-paper-observe",
        "owner": "copytrade_pm.pm_forward_observer",
        "family": "paper",
        "interface": "copytrade-pm-paper-observe",
        "classification": "PROTECTED_MUTATION",
        "authority": "PUBLIC_ONLY_FINITE_OBSERVER_JOURNAL",
        "documentation": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
        "required_arguments": [
            "--primary-dir PATH",
            "--registry PATH",
            "--secondary-dir PATH",
            "--state-root PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "source_dirs",
                "pinned_release_dir",
                "public_hyperliquid_api",
            ],
            ["private_observer_journal"],
            network=True,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["Finite shared observer mode when --continuous-config is omitted"],
    },
    "paper.observer_health.heartbeat": {
        "script": "copytrade-pm-paper-observer-health",
        "owner": "copytrade_pm.pm_forward_observer_health",
        "family": "paper",
        "interface": "copytrade-pm-paper-observer-health --state-root ROOT",
        "classification": "READ_ONLY",
        "authority": "INDEPENDENT_OBSERVER_HEARTBEAT",
        "documentation": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
        "required_arguments": ["--state-root PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(["private_observer_journal"], []),
        "limitations": ["Default single-run heartbeat check without --continuous or --watch"],
    },
    "paper.identity.audit": {
        "script": "copytrade-pm-paper-registry-audit",
        "owner": "copytrade_pm.pm_forward_registry_identity",
        "family": "paper",
        "interface": "copytrade-pm-paper-registry-audit --portfolio P1|P14",
        "classification": "READ_ONLY",
        "authority": "PINNED_REGISTRY_IDENTITY_AUDIT",
        "documentation": "docs/FORWARD-PAPER-CHECKPOINT-20261104.md",
        "required_arguments": [
            "--portfolio P1|P14",
            "--primary-dir PATH",
            "--registry PATH",
            "--secondary-dir PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(["private_sqlite_registry", "source_dirs"], []),
        "limitations": ["Read-only portfolio identity audit without --prospective-reseal-preview"],
    },
    "market.ccxt.probe": {
        "script": "copytrade-pm-market-ccxt",
        "owner": "copytrade_pm.pm_forward_ccxt_market",
        "family": "market",
        "interface": "copytrade-pm-market-ccxt --instrument SYMBOL",
        "classification": "READ_ONLY",
        "authority": "PUBLIC_CCXT_L2_PROBE",
        "documentation": "docs/DATA-ACQUISITION.md",
        "required_arguments": ["--instrument SYMBOL"],
        "runtime_required_arguments": [],
        "access": _access_entry(["public_hyperliquid_api"], [], network=True),
        "limitations": [
            "Read-only public L2 quote probe when --record-root and --continuous-canary-seconds are omitted"
        ],
    },
    "market.ccxt.record": {
        "script": "copytrade-pm-market-ccxt",
        "owner": "copytrade_pm.pm_forward_ccxt_market",
        "family": "market",
        "interface": "copytrade-pm-market-ccxt --instrument SYMBOL --record-root PATH",
        "classification": "LOCAL_MUTATION",
        "authority": "PRIVATE_CCXT_QUOTE_RECORD",
        "documentation": "docs/DATA-ACQUISITION.md",
        "required_arguments": ["--instrument SYMBOL"],
        "runtime_required_arguments": ["--record-root PATH"],
        "access": _access_entry(
            ["public_hyperliquid_api"],
            ["private_market_canary_record"],
            network=True,
        ),
        "limitations": ["Appends L2 quote receipts to PaperJournal when --record-root is supplied"],
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
    "paper.observer.preflight": ["--continuous-config PATH", "--preflight-only"],
    "paper.observer.continuous": ["--continuous-config PATH"],
    "paper.observer.continuous_health": ["--continuous"],
    "paper.observer.continuous_watchdog": ["--continuous", "--watch"],
    "paper.observer.shadow_report": ["--shadow-report"],
    "market.continuous_canary": [
        "--ack-shared-ip-connection-budget",
        "--continuous-canary-seconds SECONDS",
        "--record-root PATH",
    ],
    "paper.identity_reseal_preview": ["--prospective-reseal-preview"],
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
    "wallet_store": _access_entry(
        ["private_sqlite_registry", "private_wallet_store_parquet_and_catalog"],
        ["private_wallet_store_parquet_and_catalog"],
    ),
}
EXTRA_MODULES = {
    "pm_bounded_acquisition": ("research.bounded_acquisition", "research", "LOCAL_MUTATION"),
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


ACCESS_KEYS = frozenset({"read_targets", "write_targets", "network", "credentials", "privacy"})


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
        "paper.observer.finite",
        "paper.observer.continuous",
        "paper.observer.continuous_watchdog",
        "market.ccxt.record",
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
_GROUP_SCRIPT_MODE_CONTRACTS: dict[str, _GroupModeContract] = {
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


_GROUP_MODE_POSITIONALS = {
    "copytrade-pm-receipts": frozenset({"action"}),
    "copytrade-pm-paper-standby": frozenset({"role"}),
}
