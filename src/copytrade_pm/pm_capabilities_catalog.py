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
ROSTER_DOC = "docs/ROSTER.md"
CLASSES = frozenset({"READ_ONLY", "LOCAL_MUTATION", "PROTECTED_MUTATION", "BROKER_OR_TRADING"})
# Classifications describe the exposed DEFAULT entry point; subcommands have
# their own reviewed records. Never infer safety from a command name.
GROUPS = {
    "copytrade-pm": ("operations.cli", "operations", "READ_ONLY"),
}
# These are reviewed, individual operations, not default safety assertions
# for the broader parent executable. No subcommand inherits READ_ONLY.
REGISTRY_OPERATIONS = {}
# The legacy wallet registry CLI and its reviewed operations are retired; the
# roster owns identity and no shim keeps the old surface alive.
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
    "research.report.catalog": (
        "copytrade_pm.pm_offline_job_catalog",
        "copytrade-pm research list --cache-root PRIVATE_CACHE",
        "research",
        "READ_ONLY",
        "SHA_VERIFIED_OFFLINE_JOB_REPORT_CACHE",
    ),
    "runtime.pinned_release": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm release health",
        "operations",
        "READ_ONLY",
        "PINNED_REGISTRY_RELEASE_VERIFIER",
    ),
    "runtime.paper_units": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm release health",
        "paper",
        "READ_ONLY",
        "SYSTEMD_USER_UNIT_INVENTORY",
    ),
    "runtime.market_observer": (
        "copytrade_pm.pm_runtime_readonly",
        "copytrade-pm --observer-state-root STATE_ROOT release health",
        "market",
        "READ_ONLY",
        "PUBLIC_OBSERVER_RECEIPT_EVIDENCE",
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
        "copytrade-pm research contracts compare --portfolio gemini.phase4/E6",
        "research",
        "READ_ONLY",
        "SEALED_PORTFOLIO_AND_FULL_NET_FOLLOWER_TAPE_REQUIRED",
    ),
    "agent.trace.eval": (
        "copytrade_pm.pm_agent_trace_eval",
        "python -m copytrade_pm.pm_agent_trace_eval --list-tasks",
        "operations",
        "READ_ONLY",
        "AGENT_TRACE_EVALUATION",
    ),
    "research.actuary": (
        "copytrade_pm.contract_actuary",
        "python -m copytrade_pm.contract_actuary --help",
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
    "runtime.health": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm release status",
        "operations",
        "READ_ONLY",
        "INDEPENDENT_RUNTIME_OBSERVATIONS",
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
        "copytrade-pm paper observe --continuous-config CONFIG --preflight-only",
        "paper",
        "READ_ONLY",
        "PINNED_REGISTRY_AND_ISOLATED_OBSERVER_PREFLIGHT",
    ),
    "paper.observer.continuous_health": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm paper observer-health --continuous --state-root ROOT",
        "paper",
        "READ_ONLY",
        "INDEPENDENT_STREAM_AND_PROCESS_EVIDENCE",
    ),
    "paper.observer.shadow_report": (
        "copytrade_pm.pm_forward_observer_health",
        "copytrade-pm paper observer-health --shadow-report --state-root ROOT",
        "paper",
        "READ_ONLY",
        "ACTUAL_WATCHDOG_WINDOW_AND_RECEIPT_CHAINS",
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
    "roster": ROSTER_DOC,
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
REGISTRY_REQUIRED_ARGUMENTS = {}
REGISTRY_DISPATCH_REQUIRED_ARGUMENTS = {}
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
    "release chapter2 verify": {
        "id": "operations.release.chapter2.verify",
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
    "release chapter2 explain": {
        "id": "operations.release.chapter2.explain",
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
    "release chapter2 site-view": {
        "id": "operations.release.chapter2.site.view",
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
    "release chapter2 recover": {
        "id": "operations.release.chapter2.recover",
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
    "release chapter2 projection": {
        "id": "operations.release.chapter2.projection",
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
    "research contracts rules": {
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
    "release status": {
        "id": "operations.release.status",
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
    # --- Slice 3: facts / roster / release domain groups -------------------
    # These five groups are one entry point over the fact and roster owners.
    # Every mutation is gated by an explicit --apply flag; every read declares
    # no write target, so the reviewed classification cannot silently drift.
    "facts capture-health": {
        "id": "operations.facts.capture-health",
        "owner": "copytrade_pm.wallet_health_official",
        "family": "roster",
        "classification": "LOCAL_MUTATION",
        "authority": "BI_TEMPORAL_FACT_STORE",
        "documentation": ROSTER_DOC,
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite", "optional_fact_store", "hyperliquid_public_info"],
            ["facts_store_parquet_and_manifest", "optional_private_capture_archive"],
            network=True,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": ["Capture requires --apply and grants no trading authorization"],
    },
    "facts migrate": {
        "id": "operations.facts.migrate",
        "owner": "copytrade_pm.facts",
        "family": "roster",
        "classification": "LOCAL_MUTATION",
        "authority": "BI_TEMPORAL_FACT_STORE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "optional_legacy_wallet_store_parquet",
                "optional_reservoir_parquet",
                "optional_legacy_wallet_store_catalog",
            ],
            ["facts_store_parquet_and_manifest"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Never invents a known-at clock; unclocked archive rows stay PIT-invisible",
        ],
    },
    "facts verify": {
        "id": "operations.facts.verify",
        "owner": "copytrade_pm.facts",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "BI_TEMPORAL_FACT_STORE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["facts_store_parquet_and_manifest"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Re-hashes batches; a hash mismatch is a hard failure",
        ],
    },
    "facts coverage": {
        "id": "operations.facts.coverage",
        "owner": "copytrade_pm.facts",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "BI_TEMPORAL_FACT_STORE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["facts_store_parquet_and_manifest"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Coverage is not qualification and not a trading permission",
        ],
    },
    "facts benchmark": {
        "id": "operations.facts.benchmark",
        "owner": "copytrade_pm.facts",
        "family": "roster",
        "classification": "LOCAL_MUTATION",
        "authority": "BI_TEMPORAL_FACT_STORE",
        "documentation": ROSTER_DOC,
        "required_arguments": [],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["optional_facts_store_parquet"],
            ["optional_synthetic_facts_store"],
            network=False,
            credentials=False,
            privacy="SYNTHETIC",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Synthetic benchmark numbers never describe a real wallet universe",
        ],
    },
    "roster register": {
        "id": "operations.roster.register",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": [
            "--store STORE_PATH",
            "--account ACCOUNT_ID",
            "--seat SEAT_SPEC",
            "--policy-epoch POLICY_EPOCH_SHA256",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Seat drift or a policy-epoch change on an existing account is refused",
        ],
    },
    "roster show": {
        "id": "operations.roster.show",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Wallet addresses are redacted unless --identities is passed",
            "A vacant book reports FLAT; it is not a missing-evidence state",
        ],
    },
    "roster plan": {
        "id": "operations.roster.plan",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Pure preview: no book, lease or proposal is written",
            "A plan is never a trading authorization",
        ],
    },
    "roster commit": {
        "id": "operations.roster.commit",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Books and leases are append-only; a stale plan is refused",
        ],
    },
    "roster scorecard": {
        "id": "operations.roster.scorecard",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": [
            "--store STORE_PATH",
            "--wallet WALLET_ADDRESS",
            "--account-value ACCOUNT_VALUE_USD",
            "--cluster CLUSTER_ID",
            "--source-sha SOURCE_SHA256",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Idempotent by content SHA; gates are supplied evidence, never inferred",
        ],
    },
    "roster bench": {
        "id": "operations.roster.bench",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "A candidate must cite the exact scorecard SHA it was scored from",
        ],
    },
    "roster binding": {
        "id": "operations.roster.binding",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_RELEASE_PROPOSAL",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--file BINDING_JSON_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_binding_json"],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Provenance fields are validated, never invented; a rollback generation is refused",
        ],
    },
    "roster veto": {
        "id": "operations.roster.veto",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_OPERATOR_CONTAINMENT",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--wallet WALLET_ADDRESS", "--at-ms UTC_MS"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "A veto contains without proving; it never grants admission",
        ],
    },
    "roster cusum": {
        "id": "operations.roster.cusum",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_EPOCH_LATCH",
        "documentation": ROSTER_DOC,
        "required_arguments": [
            "--store STORE_PATH",
            "--wallet WALLET_ADDRESS",
            "--increment CUSUM_DECIMAL",
            "--threshold CUSUM_THRESHOLD",
            "--epoch POLICY_EPOCH_SHA256",
            "--at-ms UTC_MS",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [],
            ["roster_sqlite"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "A latched kill is terminal for its policy epoch and never self-clears",
        ],
    },
    "roster proposal": {
        "id": "operations.roster.proposal",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_RELEASE_PROPOSAL",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "A staged proposal is unsigned and is not a release or an authorization",
        ],
    },
    "release propose": {
        "id": "operations.release.propose",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "ROSTER_RELEASE_PROPOSAL",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            ["roster_sqlite", "optional_private_proposal_json"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry run unless --apply is passed",
            "Refuses to propose from a changed or unrecorded release binding",
        ],
    },
    "release sign": {
        "id": "operations.release.sign",
        "owner": "copytrade_pm.production_manifest",
        "family": "roster",
        "classification": "PROTECTED_MUTATION",
        "authority": "PRODUCTION_MANIFEST_SIGNING",
        "documentation": ROSTER_DOC,
        "required_arguments": [
            "--proposal PROPOSAL_JSON_PATH",
            "--release-signing-key PRIVATE_ED25519_KEY_PATH",
            "--reviewer-public ED25519_PUBLIC_KEY_PATH",
            "--source-observer-public ED25519_PUBLIC_KEY_PATH",
            "--out SIGNED_ENVELOPE_PATH",
            "--store ROSTER_SQLITE_PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            [
                "roster_sqlite",
                "private_proposal_json",
                "private_ed25519_key",
                "trusted_public_key",
            ],
            ["private_signed_release_envelope", "roster_sqlite"],
            network=False,
            credentials=True,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Requires an exact match to a staged SYNTHETIC proposal",
            "Independent reviewer and source-observer approval is verified against the staged selection before any key is opened",
            "Dry run does not load the key; --apply requires a regular 0600 key",
            "Requires a new output in a private directory",
        ],
    },
    "release verify": {
        "id": "operations.release.verify",
        "owner": "copytrade_pm.production_manifest",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "PRODUCTION_MANIFEST_SIGNING",
        "documentation": ROSTER_DOC,
        "required_arguments": [
            "--envelope SIGNED_ENVELOPE_PATH",
            "--signer-public ED25519_PUBLIC_KEY_PATH",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_signed_release_envelope", "ed25519_public_key"],
            [],
            network=False,
            credentials=False,
            privacy="PUBLIC_METADATA",
        ),
        "limitations": [
            "A verified envelope is evidence of an offline signature, not a trading authorization",
        ],
    },
    "release export": {
        "id": "operations.release.export",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_RELEASE_PROPOSAL",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Wallet addresses are redacted unless --identities is passed",
            "Export order_route is always NONE",
        ],
    },
    "research scorecards": {
        "id": "operations.research.scorecards",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_SCORECARD_READ_MODEL",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Aggregate gate counts only; never a qualification claim",
            "A missing scorecard is missing evidence, not a pass or a fail",
        ],
    },
    "research contracts compare": {
        "id": "research.contract_selector.compare",
        "owner": "copytrade_pm.pm_contract_selector",
        "family": "research",
        "classification": "READ_ONLY",
        "authority": "USER_SUPPLIED_UNVERIFIED_ARCHETYPE",
        "documentation": "docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md",
        "required_arguments": ["--portfolio NAMESPACE/ID"],
        "runtime_required_arguments": ["--tape PRIVATE_TAPE"],
        "access": _access_entry(
            ["roster_sqlite", "private_follower_pnl_tape"],
            [],
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Synthetic EV is SCENARIO_ONLY and never a trading permission",
            "A missing tape is BLOCKED, never inferred",
        ],
    },
    "paper status": {
        "id": "operations.paper.status",
        "owner": "copytrade_pm.pm_roster_cli",
        "family": "paper",
        "classification": "READ_ONLY",
        "authority": "ROSTER_SEAT_LEASE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store ROSTER_SQLITE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(["roster_sqlite"], [], privacy="OWNER_PRIVATE_REDACTED"),
        "limitations": [
            "The seat view is virtual paper only; order_route is always NONE",
        ],
    },
    "release metadata": {
        "id": "operations.release.metadata",
        "owner": "copytrade_pm.production_export",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_SEALED_SELECTION",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--portfolio ACCOUNT_ID", "--asof UTC_TIMESTAMP"],
        "runtime_required_arguments": [],
        "access": _access_entry(["roster_sqlite"], [], privacy="OWNER_PRIVATE_REDACTED"),
        "limitations": [
            "Read-only metadata handoff; no broker or signing authority",
        ],
    },
    "paper mandates": {
        "id": "operations.paper.mandates",
        "owner": "copytrade_pm.roster",
        "family": "roster",
        "classification": "READ_ONLY",
        "authority": "ROSTER_PAPER_BRIDGE",
        "documentation": ROSTER_DOC,
        "required_arguments": ["--store STORE_PATH", "--account ACCOUNT_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["roster_sqlite"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Reads the staged unsigned proposal at or before --as-of; no journal or broker",
        ],
    },
    # --- Ported live parsers: one owner registration, mounted once under a group --
    # Each owner module still exposes its own `python -m` route; the consolidated
    # leaf adds only the reviewed --apply gate for a mutating mode.
    "paper observe": {
        "id": "paper.observer.continuous",
        "owner": "copytrade_pm.pm_forward_observer",
        "family": "paper",
        "classification": "PROTECTED_MUTATION",
        "authority": "PUBLIC_ONLY_CONTINUOUS_OBSERVATION_JOURNAL",
        "documentation": "docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md",
        "required_arguments": [
            "--registry REGISTRY_SQLITE_PATH",
            "--primary-dir PRIMARY_SOURCE_DIR",
            "--secondary-dir SECONDARY_SOURCE_DIR",
            "--state-root OBSERVER_STATE_ROOT",
        ],
        "runtime_required_arguments": ["--continuous-config CONFIG", "--preflight-only"],
        "access": _access_entry(
            [
                "private_sqlite_registry",
                "source_dirs",
                "continuous_observer_config",
                "pinned_release_dir",
                "public_hyperliquid_api",
            ],
            ["private_observer_journal"],
            network=True,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Without --apply only the read-only preflight/diagnosis runs; starting observation "
            "requires an explicit --apply",
            "Continuous capture creates no PM-03 run and commits no financial event",
        ],
    },
    "paper observer-health": {
        "id": "paper.observer.continuous_watchdog",
        "owner": "copytrade_pm.pm_forward_observer_health",
        "family": "paper",
        "classification": "LOCAL_MUTATION",
        "authority": "INDEPENDENT_PRIVATE_WATCHDOG_HISTORY",
        "documentation": "docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md",
        "required_arguments": ["--state-root OBSERVER_STATE_ROOT"],
        "runtime_required_arguments": ["--continuous", "--watch"],
        "access": _access_entry(
            ["private_observer_journal", "private_continuous_heartbeat", "proc_pid"],
            ["private_watchdog_state"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Plain health and --shadow-report reads are read-only; only --watch appends private "
            "witness samples and requires --apply",
            "A healthy heartbeat is flawed observer evidence, never PAPER_RUNNING",
        ],
    },
    "paper run-status": {
        "id": "paper.account",
        "owner": "copytrade_pm.pm_forward_status",
        "family": "paper",
        "classification": "READ_ONLY",
        "authority": "PM03_FINANCIAL_JOURNAL",
        "documentation": "docs/FORWARD-PAPER-OBSERVER-HEALTH-20261104.md",
        "required_arguments": ["--db PAPER_EVENT_DB", "--run-id RUN_ID"],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["private_paper_journal", "private_heartbeat_root"],
            [],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Reads one sealed run's journal and heartbeat; unverifiable worker identity stays "
            "NOT_RUNNING, never PROMOTED",
            "Runtime status is not scientific validity or trading authorization",
        ],
    },
    "research market-audit": {
        "id": "market.native",
        "owner": "copytrade_pm.pm_market_audit",
        "family": "market",
        "classification": "LOCAL_MUTATION",
        "authority": "VERIFIED_NATIVE_MINUTE_DATA",
        "documentation": "docs/DATA-ACQUISITION.md",
        "required_arguments": [
            "--research-root RESEARCH_ROOT",
            "--market-root NATIVE_MARKET_ROOT",
            "--out EVIDENCE_OUT",
        ],
        "runtime_required_arguments": [],
        "access": _access_entry(
            ["research_root", "native_minute_market_lake"],
            ["private_evidence_store"],
            network=False,
            credentials=False,
            privacy="OWNER_PRIVATE_REDACTED",
        ),
        "limitations": [
            "Dry runs print the plan; writing the private evidence report requires --apply",
            "Per-instrument-day coverage never proves every requested minute is executable",
        ],
    },
    "research ccxt-probe": {
        "id": "market.continuous_canary",
        "owner": "copytrade_pm.pm_forward_ccxt_market",
        "family": "market",
        "classification": "PROTECTED_MUTATION",
        "authority": "BOUNDED_PUBLIC_MARKET_TRANSPORT_ONLY",
        "documentation": "docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md",
        "required_arguments": ["--instrument INSTRUMENT"],
        "runtime_required_arguments": [
            "--record-root RECORD_ROOT",
            "--continuous-canary-seconds SECONDS",
            "--ack-shared-ip-connection-budget",
        ],
        "access": _access_entry(
            ["public_hyperliquid_api"],
            ["private_market_canary_record"],
            network=True,
            credentials=False,
            privacy="PUBLIC_METADATA",
        ),
        "limitations": [
            "A one-shot probe without --record-root is read-only; recording a canary journal "
            "requires --apply",
            "Best-level public depth is not traded volume or independent quote authority",
        ],
    },
}


# Reviewed GROUPS mode variants that distinguish READ_ONLY vs MUTATION/network/dispatch
# modes while retaining conservative parent GROUPS classifications.
GROUP_OPERATIONS: dict[str, _GroupOperationSpec] = {}
REGISTRY_ACCESS = {}
NATIVE_REQUIRED_ARGUMENTS = {
    "research.report.catalog": [],
    "research.catalog": [],
    "research.contract_selector": ["--portfolio NAMESPACE/ID"],
    "runtime.pinned_release": [],
    "runtime.paper_units": [],
    "runtime.market_observer": [],
    "runtime.health": [],
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
}
NATIVE_ACCESS = {
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
}


ACCESS_KEYS = frozenset({"read_targets", "write_targets", "network", "credentials", "privacy"})


_OPERATIONS_NATIVE_LEAVES = {
    "research list": "research.report.catalog",
    "release health": "runtime.health",
}
_OPERATIONS_NATIVE_MIRRORS = (("research.catalog", "research list"),)
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
_NON_READ_ONLY_GROUP_MODES = frozenset()
_GROUP_SCRIPT_MODE_CONTRACTS: dict[str, _GroupModeContract] = {}
_GROUP_NATIVE_SCRIPTS = {}
_VALIDATE_LIMITATIONS = [
    "Owner-specific bounded AST inspectors cover pm_operations.py (+ pm_cwsa_chapter2_gate, pm_health_arguments, production_export, pm_forward_observer, pm_forward_observer_health, pm_forward_status, pm_market_audit and pm_forward_ccxt_market leaf parsers), production_manifest, and pm03_cli.execute rather than arbitrary dynamic Python.",
    "pm03_cli.execute (--input JSON spec.action) and production_economics.py POLICIES flag generation rely on reviewed owner contracts rather than arbitrary dynamic dispatch inference.",
    "Conditional runtime_required_arguments capture mode-specific runtime requirements verified from owner dispatch contracts and are kept separate from argparse required_arguments.",
    "CLI/NATIVE/MODULE entries outside reviewed subcommands/modes retain UNKNOWN access rather than inferred safety.",
]


_GROUP_MODE_POSITIONALS = {}
