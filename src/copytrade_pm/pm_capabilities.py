"""Discover real argparse routes without importing state writers or providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib
from typing import Any

from .pm_capabilities_catalog import COMMANDS, DOC, ROOT_MODULE

ROOT = Path(__file__).resolve().parents[2]


def _declared_scripts(root: Path) -> dict[str, str]:
    scripts: dict[str, str] = tomllib.loads((root / "pyproject.toml").read_text())["project"][
        "scripts"
    ]
    return scripts


def _leaves(
    parser: argparse.ArgumentParser, prefix: str = ""
) -> dict[str, argparse.ArgumentParser]:
    children = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not children:
        return {prefix: parser}
    found = {}
    for action in children:
        for name, child in action.choices.items():
            found.update(_leaves(child, (prefix + " " + name).strip()))
    return found


def inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    from .pm_operations import parser

    if root.resolve() != ROOT:
        raise ValueError("CAPABILITY_FOREIGN_CHECKOUT_USE_ITS_CLI")
    entries = []
    for route, leaf in sorted(_leaves(parser()).items()):
        meta = COMMANDS.get(route)
        owner, authority, classification, network, credentials, reads, writes = meta or (
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            ("UNKNOWN",),
            ("UNKNOWN",),
        )
        module = ROOT_MODULE + owner
        available = (root / "src" / Path(module.replace(".", "/")).with_suffix(".py")).is_file()
        entries.append(
            {
                "schema_version": 2,
                "id": "operations." + route.replace(" ", "."),
                "kind": "SUBCOMMAND",
                "interface": "copytrade-pm " + route,
                "description": leaf.description or leaf.format_usage().strip(),
                "owner": module,
                "authority": authority,
                "classification": classification,
                "available": available,
                "documentation": DOC,
                "required_arguments": [
                    (action.option_strings[0] if action.option_strings else action.dest)
                    + (" " + action.dest.upper() if action.nargs != 0 else "")
                    for action in leaf._actions
                    if action.required
                    or (not action.option_strings and action.nargs not in ("?", "*"))
                ],
                "runtime_required_arguments": [],
                "access": {
                    "network": network,
                    "credentials": credentials,
                    "read_targets": list(reads),
                    "write_targets": list(writes),
                    "privacy": "OWNER_PRIVATE_REDACTED",
                },
                "limitations": (
                    ["Dry run unless --apply is passed; never grants trading authority"]
                    if classification in ("LOCAL_MUTATION", "PROTECTED_MUTATION")
                    else ["Read-only evidence; no financial or scientific authorization"]
                ),
            }
        )
    return entries


def validate(root: Path = ROOT) -> dict[str, Any]:
    from .pm_operations import parser

    errors = []
    if root.resolve() != ROOT:
        errors.append("CAPABILITY_FOREIGN_CHECKOUT_USE_ITS_CLI")
        entries = []
    else:
        entries = inventory(root)
        routes = set(_leaves(parser()))
        for route in routes - COMMANDS.keys():
            errors.append("UNREVIEWED_COMMAND:" + route)
        for route in COMMANDS.keys() - routes:
            errors.append("RETIRED_COMMAND_ADVERTISED:" + route)
        for entry in entries:
            if not entry["available"]:
                errors.append("MISSING_OWNER:" + entry["id"])
            if entry["classification"] == "READ_ONLY" and entry["access"]["write_targets"]:
                errors.append("READ_ONLY_WRITE_TARGET:" + entry["id"])
            if entry["classification"] not in {"READ_ONLY", "LOCAL_MUTATION", "PROTECTED_MUTATION"}:
                errors.append("UNKNOWN_EFFECT:" + entry["id"])
            route = entry["interface"].removeprefix("copytrade-pm ")
            if entry["classification"] != "READ_ONLY":
                flags = {
                    flag
                    for action in _leaves(parser())[route]._actions
                    for flag in action.option_strings
                }
                if "--apply" not in flags:
                    errors.append("MUTATION_WITHOUT_APPLY:" + entry["id"])
    if _declared_scripts(root) != {"copytrade-pm": "copytrade_pm.pm_operations:main"}:
        errors.append("UNREVIEWED_ENTRY_POINT")
    if not (root / DOC).is_file():
        errors.append("OPERATIONS_DOCUMENTATION_MISSING")
    return {
        "schema": "copytrade_capability_validation_v2",
        "status": "BLOCKED" if errors else "VERIFIED",
        "errors": sorted(errors),
        "capability_count": len(entries),
        "cli_count": 1,
        "limitations": ["Describes the actual local CLI parser; metadata never authorizes effects"],
    }


def render(items: object) -> str:
    return json.dumps(items, sort_keys=True, indent=2)
