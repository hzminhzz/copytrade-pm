"""Reviewed native capability directory; descriptive only, never an authorization engine.

CLI entry points are discovered from installed distribution metadata (with
pyproject fallback for source-only checkouts). Every entry point must have
reviewed operation metadata; unknown operations fail closed.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re

from .pm_capabilities_catalog import (
    ACCESS_KEYS as ACCESS_KEYS,
    CLASSES as CLASSES,
    DOC as DOC,
    DOCS as DOCS,
    EXTRA_MODULES as EXTRA_MODULES,
    GROUP_OPERATIONS as GROUP_OPERATIONS,
    GROUPS as GROUPS,
    NATIVE as NATIVE,
    NATIVE_ACCESS as NATIVE_ACCESS,
    NATIVE_REQUIRED_ARGUMENTS as NATIVE_REQUIRED_ARGUMENTS,
    NATIVE_RUNTIME_REQUIRED_ARGUMENTS as NATIVE_RUNTIME_REQUIRED_ARGUMENTS,
    OPERATIONS_SUBCOMMANDS as OPERATIONS_SUBCOMMANDS,
    REGISTRY_ACCESS as REGISTRY_ACCESS,
    REGISTRY_DISPATCH_REQUIRED_ARGUMENTS as REGISTRY_DISPATCH_REQUIRED_ARGUMENTS,
    REGISTRY_OPERATIONS as REGISTRY_OPERATIONS,
    REGISTRY_REQUIRED_ARGUMENTS as REGISTRY_REQUIRED_ARGUMENTS,
    ROOT as ROOT,
    UNKNOWN_ACCESS as UNKNOWN_ACCESS,
    _VALIDATE_LIMITATIONS as _VALIDATE_LIMITATIONS,
    _access_entry as _access_entry,
    _parse_static_source as _parse_static_source,
    _registry_access_entry as _registry_access_entry,
)
from .pm_capabilities_inspector import (
    PARSER_CALL_NAMES as PARSER_CALL_NAMES,
    _copy_access as _copy_access,
    _declared_scripts as _declared_scripts,
    _inspect_group_script_parser as _inspect_group_script_parser,
    _installed_scripts as _installed_scripts,
    _module_available as _module_available,
    _registry_runtime_args as _registry_runtime_args,
    _required_cli_args as _required_cli_args,
    _subcommand_entry as _subcommand_entry,
    _validate_group_scripts as _validate_group_scripts,
    _validate_operations_cli as _validate_operations_cli,
    _validate_registry_operations as _validate_registry_operations,
)


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
                access=spec["access"],
                required_arguments=list(spec["required_arguments"]),
                runtime_required_arguments=list(spec["runtime_required_arguments"]),
                preflight=[],
                documentation=str(spec["documentation"]),
                available=_module_available("copytrade_pm.pm_operations", root)
                and _module_available(owner, root),
                limitations=list(spec["limitations"]),
            )
        )
    for cap_id, group_spec in sorted(GROUP_OPERATIONS.items()):
        owner = str(group_spec["owner"])
        script_name = str(group_spec["script"])
        script_invocation = scripts.get(script_name)
        script_module = script_invocation.split(":", 1)[0] if script_invocation else owner
        results.append(
            _subcommand_entry(
                cap_id=cap_id,
                description=f"Mode variant for {script_name}",
                owner=owner,
                interface=str(group_spec["interface"]),
                classification=str(group_spec["classification"]),
                authority=str(group_spec["authority"]),
                access=group_spec["access"],
                required_arguments=list(group_spec["required_arguments"]),
                runtime_required_arguments=list(group_spec["runtime_required_arguments"]),
                preflight=[],
                documentation=str(group_spec["documentation"]),
                available=(
                    script_name in scripts
                    and _module_available(script_module, root)
                    and _module_available(owner, root)
                    and (
                        script_name not in installed or installed[script_name] == script_invocation
                    )
                ),
                limitations=list(group_spec["limitations"]),
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
                    else "docs/WALLET-STORE.md"
                    if cap == "wallet_store"
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
                tree = _parse_static_source(file.read_text())
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
