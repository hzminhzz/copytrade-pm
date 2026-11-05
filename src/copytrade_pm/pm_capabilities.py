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
    "copytrade-pm-source-scope": ("source.scope", "source", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-watchdog": ("paper.watchdog", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-standby": ("paper.standby", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-unit-bundle": ("paper.unit_bundle", "paper", "LOCAL_MUTATION"),
    "copytrade-pm-paper-registry-audit": ("paper.identity", "paper", "READ_ONLY"),
    "copytrade-pm-paper-readiness": ("paper.readiness", "paper", "READ_ONLY"),
    "copytrade-pm-paper-source-campaign": ("paper.source_campaign", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-observe": ("paper.observer", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm-paper-observer-health": ("paper.observer_health", "paper", "READ_ONLY"),
    "copytrade-pm-public-observer-unit": ("paper.public_unit", "paper", "PROTECTED_MUTATION"),
    "copytrade-pm": ("operations.cli", "operations", "READ_ONLY"),
    "copytrade-pm-agent-eval": ("agent.trace.eval", "operations", "READ_ONLY"),
}
# These are reviewed, individual operations, not default safety assertions
# for the broader parent executable. No subcommand inherits READ_ONLY.
REGISTRY_OPERATIONS = {
    "status": "READ_ONLY",
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
                "dependencies": [],
                "required_arguments": _required_cli_args(module, root),
                "preflight": [],
                "documentation": DOCS[family],
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
                "dependencies": [],
                "required_arguments": NATIVE_REQUIRED_ARGUMENTS.get(cap),
                "preflight": [],
                "documentation": DOCS[family],
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
    registry = root / "src/copytrade_pm/wallet_registry.py"
    body = registry.read_text()
    for op in REGISTRY_OPERATIONS:
        cmd = op.split()[0]
        if (
            f'sub.add_parser("{cmd}"' not in body
            and f'sub.add_parser(\n        "{cmd}"' not in body
        ):
            problems.append(f"STALE_REGISTRY_OP:{op}")
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
