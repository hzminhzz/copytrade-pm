"""Bounded fail-closed AST inspectors and parser parity validators for pm_capabilities."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
from importlib import metadata
from pathlib import Path
import tomllib
from typing import Any

from .pm_capabilities_catalog import (
    ACCESS_KEYS,
    GROUP_OPERATIONS,
    GROUPS,
    NATIVE,
    NATIVE_ACCESS,
    NATIVE_REQUIRED_ARGUMENTS,
    NATIVE_RUNTIME_REQUIRED_ARGUMENTS,
    OPERATIONS_SUBCOMMANDS,
    REGISTRY_ACCESS,
    REGISTRY_DISPATCH_REQUIRED_ARGUMENTS,
    REGISTRY_OPERATIONS,
    REGISTRY_REQUIRED_ARGUMENTS,
    _CLASS_RANK,
    _GROUP_MODE_POSITIONALS,
    _GROUP_NATIVE_SCRIPTS,
    _GROUP_SCRIPT_MODE_CONTRACTS,
    _NON_READ_ONLY_GROUP_MODES,
    _OPERATIONS_NATIVE_LEAVES,
    _OPERATIONS_NATIVE_MIRRORS,
    _PM03_CLI_ACTIONS,
    _parse_static_source,
)


def _declared_scripts(root: Path) -> dict[str, str]:
    scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
    return {str(k): str(v) for k, v in scripts.items()}


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
    required = _required_cli_args_from_source(path.read_text(encoding="utf-8"))
    return list(required) if required is not None else None


@lru_cache(maxsize=128)
def _required_cli_args_from_source(source: str) -> tuple[str, ...] | None:
    """Inspect a source revision once; return immutable requirements for each caller."""
    tree = _parse_static_source(source)
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
        req_node = flags.get("required")
        mandatory_flag = isinstance(req_node, ast.Constant) and req_node.value is True
        nargs_node = flags.get("nargs")
        positional = not option.startswith("-") and not (
            isinstance(nargs_node, ast.Constant) and nargs_node.value in ("?", "*")
        )
        if mandatory_flag or positional:
            required.add(option)
    return tuple(sorted(required))


def _module_available(module: str, root: Path) -> bool:
    if module.startswith("docs/") or module.startswith("scripts/"):
        return (root / module).is_file()
    pkg_dir = root / "src" / Path(*module.split("."))
    return pkg_dir.with_suffix(".py").is_file() or (pkg_dir / "__init__.py").is_file()


def _copy_access(entry: Mapping[str, object]) -> dict[str, object]:
    return {key: list(value) if isinstance(value, list) else value for key, value in entry.items()}


def _subcommand_entry(
    *,
    cap_id: str,
    description: str,
    owner: str,
    interface: str,
    classification: str,
    authority: str,
    access: Mapping[str, object],
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
    node: dict[str, Any],
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


def _new_parser_node() -> dict[str, Any]:
    return {
        "has_subparsers": False,
        "options": {},
        "positionals": {},
        "required_groups": [],
    }


def _has_parent_node_constraint(spec: dict[str, Any]) -> bool:
    return (
        any(meta["required"] for meta in spec["options"].values())
        or "--apply" in spec["options"]
        or any(meta["required"] for meta in spec["positionals"].values())
        or bool(spec["required_groups"])
    )


def _assignment_target_call(stmt: ast.stmt) -> tuple[str | None, ast.Call | None, bool]:
    """Return (target_name, call, is_valid_statement) for Assign/Expr parser statements."""
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
    ):
        if isinstance(stmt.value, ast.Call):
            return stmt.targets[0].id, stmt.value, True
        return stmt.targets[0].id, None, False
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return None, stmt.value, True
    return None, None, False


def _inspect_registry_parser(registry_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Small, registry-specific AST inspector; fails closed on unsupported constructs."""
    if not registry_path.is_file():
        return {}, ["MISSING_ENTRY_MODULE:copytrade-wallet-registry"]
    tree = _parse_static_source(registry_path.read_text(encoding="utf-8"))
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
    group_vars: dict[str, tuple[tuple[str, ...], int | None, bool]] = {}
    nodes: dict[tuple[str, ...], dict[str, Any]] = {}
    visited_calls: set[int] = set()
    errors: list[str] = []
    saw_parse_args = False

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
                nodes[()] = _new_parser_node()
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
                    nodes[child] = _new_parser_node()
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
        if _has_parent_node_constraint(spec):
            errors.append("UNSUPPORTED_REGISTRY_PARSER_CONSTRUCT:parent_node_constraint")

    leaves = {
        " ".join(path): spec for path, spec in nodes.items() if path and not spec["has_subparsers"]
    }
    return leaves, errors


def _validate_access_entry(
    access: Mapping[str, object] | None,
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


def _validate_declared_contract(
    *,
    tag: str,
    target: str,
    cap_id: str,
    safety: str,
    parser_spec: dict[str, Any] | None,
    required_arguments: Sequence[str],
    runtime_required_arguments: Sequence[str],
    access: Mapping[str, object] | None,
    mismatch_code: str,
    ignore_positionals: frozenset[str] = frozenset(),
    check_groups: bool = False,
    ignore_runtime_prefix: str | None = None,
) -> list[str]:
    """Validate required args, runtime required args, and access metadata for one capability."""
    problems: list[str] = []
    if parser_spec is not None:
        p_opts, p_pos, p_groups = _parser_required_sets(
            parser_spec, ignore_positionals=ignore_positionals
        )
        d_opts, d_pos, d_groups = _split_declared_required_args(list(required_arguments))
        for missing in sorted(p_opts - d_opts):
            problems.append(f"MISSING_{tag}_REQUIRED_ARG:{target}:{missing}")
        for extra in sorted(d_opts - p_opts):
            problems.append(f"STALE_{tag}_REQUIRED_ARG:{target}:{extra}")
        if d_pos != p_pos or (check_groups and sorted(d_groups) != sorted(p_groups)):
            problems.append(f"{mismatch_code}:{target}")
        for rtok in runtime_required_arguments:
            if ignore_runtime_prefix and rtok.startswith(ignore_runtime_prefix):
                continue
            rflag = rtok.split()[0]
            if rflag not in parser_spec["options"] or rflag in p_opts:
                problems.append(f"STALE_{tag}_RUNTIME_ARG:{target}:{rflag}")
    problems.extend(
        _validate_access_entry(
            access,
            safety=safety,
            missing_code=f"MISSING_{tag}_ACCESS:{cap_id}",
            invalid_code=f"INVALID_ACCESS_SCHEMA:{cap_id}",
            unverified_code=f"UNVERIFIED_{tag}_ACCESS:{cap_id}",
            inconsistent_code=f"INCONSISTENT_{tag}_ACCESS:{cap_id}",
        )
    )
    return problems


def _parser_required_sets(
    spec: dict[str, Any], *, ignore_positionals: frozenset[str] = frozenset()
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
        op_mode_flags = set(op.split()[len(leaf.split()) :])
        parser_required: set[str] = set()
        for opt, meta in spec["options"].items():
            in_selected_group = meta["group_idx"] is not None and opt in op_mode_flags
            if (meta["required"] or in_selected_group) and not (
                meta["flag_only"] and opt in op_mode_flags
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


def _inspect_cwsa_add_arguments(root: Path, target_node: dict[str, Any]) -> list[str]:
    cwsa_path = root / "src/copytrade_pm/pm_cwsa_chapter2_gate.py"
    if not cwsa_path.is_file():
        return ["MISSING_OWNER_MODULE:copytrade_pm.pm_cwsa_chapter2_gate"]
    tree = _parse_static_source(cwsa_path.read_text(encoding="utf-8"))
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


def _extract_op_map(dict_node: ast.Dict) -> dict[str, tuple[str, ...]] | None:
    op_map: dict[str, tuple[str, ...]] = {}
    for k_node, v_node in zip(dict_node.keys, dict_node.values, strict=True):
        k_str = _const_str(k_node) if k_node is not None else None
        v_tup = _const_str_tuple(v_node)
        if k_str is None or v_tup is None:
            return None
        op_map[k_str] = v_tup
    return op_map


def _apply_loop_add_parser(
    stmt: ast.stmt,
    *,
    var_name: str,
    val: str,
    parser_vars: dict[str, tuple[str, ...]],
    subparser_vars: Mapping[str, tuple[str, ...]],
    nodes: dict[tuple[str, ...], dict[str, Any]],
    visited_calls: set[int],
    missing_recv_code: str,
) -> tuple[bool, str | None]:
    """Match `tgt = sp.add_parser(var_name)` inside bounded domain/op loops."""
    tgt, call, valid_call = _assignment_target_call(stmt)
    if (
        not valid_call
        or tgt is None
        or call is None
        or not isinstance(call.func, ast.Attribute)
        or call.func.attr != "add_parser"
        or len(call.args) != 1
        or not isinstance(call.args[0], ast.Name)
        or call.args[0].id != var_name
    ):
        return False, None
    recv_name = call.func.value.id if isinstance(call.func.value, ast.Name) else None
    if recv_name is None or recv_name not in subparser_vars:
        return True, missing_recv_code
    visited_calls.add(id(call))
    child = (*subparser_vars[recv_name], val)
    nodes[child] = _new_parser_node()
    parser_vars[tgt] = child
    return True, None


def _inspect_operations_parser(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Bounded AST inspector for pm_operations.parser() and pm_cwsa_chapter2_gate.add_arguments."""
    ops_path = root / "src/copytrade_pm/pm_operations.py"
    if not ops_path.is_file():
        return {}, ["MISSING_ENTRY_MODULE:copytrade-pm"]
    tree = _parse_static_source(ops_path.read_text(encoding="utf-8"))
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
    nodes: dict[tuple[str, ...], dict[str, Any]] = {}
    visited_calls: set[int] = set()
    errors: list[str] = []

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
                nodes[()] = _new_parser_node()
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
                    nodes[child] = _new_parser_node()
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

    def _run_op_if(
        stmt: ast.If,
        env: dict[str, str],
        op_p: dict[str, tuple[str, ...]],
        op_s: dict[str, tuple[str, ...]],
    ) -> bool:
        if stmt.orelse:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_stmt")
            return False
        cond = _eval_static_condition(stmt.test, env)
        if cond is None:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:dynamic_condition")
            return False
        for b_stmt in stmt.body:
            if not (isinstance(b_stmt, ast.Expr) and isinstance(b_stmt.value, ast.Call)):
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:if_body_stmt")
                return False
            if cond:
                _handle_parser_call(b_stmt.value, None, op_p, op_s)
            elif _call_name(b_stmt.value) in PARSER_CALL_NAMES:
                visited_calls.add(id(b_stmt.value))
        return True

    def _run_op_loop(
        loop_stmt: ast.For,
        domain: str,
        domain_var: str,
        loc_p: dict[str, tuple[str, ...]],
        loc_s: dict[str, tuple[str, ...]],
    ) -> bool:
        is_domain_dict = (
            isinstance(loop_stmt.target, ast.Name)
            and not loop_stmt.orelse
            and isinstance(loop_stmt.iter, ast.Subscript)
            and isinstance(loop_stmt.iter.value, ast.Dict)
            and isinstance(loop_stmt.iter.slice, ast.Name)
            and loop_stmt.iter.slice.id == domain_var
        )
        if not is_domain_dict:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_body_stmt")
            return False
        assert isinstance(loop_stmt.target, ast.Name)
        assert isinstance(loop_stmt.iter, ast.Subscript)
        assert isinstance(loop_stmt.iter.value, ast.Dict)
        op_map = _extract_op_map(loop_stmt.iter.value)
        if op_map is None:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_map")
            return False
        if domain not in op_map:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:missing_domain_key")
            return False
        op_var = loop_stmt.target.id
        for op_val in op_map[domain]:
            env = {domain_var: domain, op_var: op_val}
            op_p = dict(loc_p)
            op_s = dict(loc_s)
            for op_stmt in loop_stmt.body:
                matched, err = _apply_loop_add_parser(
                    op_stmt,
                    var_name=op_var,
                    val=op_val,
                    parser_vars=op_p,
                    subparser_vars=op_s,
                    nodes=nodes,
                    visited_calls=visited_calls,
                    missing_recv_code="UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_parser",
                )
                if matched:
                    if err:
                        errors.append(err)
                        return False
                    continue
                if isinstance(op_stmt, ast.If):
                    if not _run_op_if(op_stmt, env, op_p, op_s):
                        return False
                    continue
                errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_op_stmt")
                return False
        return True

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
                matched, err = _apply_loop_add_parser(
                    inner,
                    var_name=domain_var,
                    val=domain,
                    parser_vars=loc_p,
                    subparser_vars=loc_s,
                    nodes=nodes,
                    visited_calls=visited_calls,
                    missing_recv_code="UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:loop_add_parser",
                )
                if matched:
                    if err:
                        errors.append(err)
                        return
                    continue
                tgt, call, valid_call = _assignment_target_call(inner)
                if valid_call and tgt is not None and call and isinstance(call.func, ast.Attribute):
                    _handle_parser_call(call, tgt, loc_p, loc_s)
                    continue
                if isinstance(inner, ast.For):
                    if not _run_op_loop(inner, domain, domain_var, loc_p, loc_s):
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
            continue
        tgt, call, valid_call = _assignment_target_call(stmt)
        if tgt is not None and not valid_call:
            errors.append("UNSUPPORTED_OPERATIONS_PARSER_CONSTRUCT:non_call_assign")
        elif valid_call and call is not None:
            _handle_parser_call(call, tgt, parser_vars, subparser_vars)
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
        if _has_parent_node_constraint(spec):
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

    cataloged_leaves: set[str] = native_set | subcmd_set
    for leaf in sorted(set(leaves) - cataloged_leaves):
        problems.append(f"UNLISTED_OPERATIONS_LEAF:{leaf}")
    for leaf in sorted(cataloged_leaves - set(leaves)):
        problems.append(f"STALE_OPERATIONS_LEAF:{leaf}")

    def _check_entry(
        leaf: str,
        parser_spec: dict[str, Any],
        cap_id: str,
        *,
        safety: str,
        required_arguments: Sequence[str],
        runtime_required_arguments: Sequence[str],
        access: Mapping[str, object] | None,
    ) -> None:
        if safety != "READ_ONLY" or "--apply" in parser_spec["options"]:
            problems.append(f"UNSAFE_OPERATIONS_CLASSIFICATION:{leaf}")
        problems.extend(
            _validate_declared_contract(
                tag="OPERATIONS",
                target=leaf,
                cap_id=cap_id,
                safety=safety,
                parser_spec=parser_spec,
                required_arguments=required_arguments,
                runtime_required_arguments=runtime_required_arguments,
                access=access,
                mismatch_code="OPERATIONS_POSITIONAL_MISMATCH",
            )
        )

    for leaf, cap_id in sorted(_OPERATIONS_NATIVE_LEAVES.items()):
        if cap_id not in NATIVE:
            problems.append(f"STALE_OPERATIONS_NATIVE_CAP:{cap_id}")
            continue
        if leaf in leaves:
            _, _, _, safety, _ = NATIVE[cap_id]
            _check_entry(
                leaf,
                leaves[leaf],
                cap_id,
                safety=safety,
                required_arguments=NATIVE_REQUIRED_ARGUMENTS.get(cap_id, []),
                runtime_required_arguments=NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(cap_id, []),
                access=NATIVE_ACCESS.get(cap_id),
            )
    for leaf, spec in sorted(OPERATIONS_SUBCOMMANDS.items()):
        if leaf in leaves:
            _check_entry(
                leaf,
                leaves[leaf],
                str(spec["id"]),
                safety=str(spec["classification"]),
                required_arguments=spec["required_arguments"],
                runtime_required_arguments=spec["runtime_required_arguments"],
                access=spec["access"],
            )
    for mirror_id, leaf in _OPERATIONS_NATIVE_MIRRORS:
        if leaf in leaves and mirror_id in NATIVE:
            _, _, _, safety, _ = NATIVE[mirror_id]
            _check_entry(
                leaf,
                leaves[leaf],
                mirror_id,
                safety=safety,
                required_arguments=NATIVE_REQUIRED_ARGUMENTS.get(mirror_id, []),
                runtime_required_arguments=NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(mirror_id, []),
                access=NATIVE_ACCESS.get(mirror_id),
            )
    return sorted(set(problems))


def _inspect_group_script_parser(
    path: Path, script_name: str, *, allow_policies_loop: bool
) -> tuple[dict[str, Any] | None, list[str]]:
    """Bounded AST inspector for flat GROUPS CLI scripts (no subparsers, no dynamic loops)."""
    if not path.is_file():
        return None, [f"MISSING_ENTRY_MODULE:{script_name}"]
    spec, errors = _inspect_group_script_source(
        path.read_text(encoding="utf-8"), script_name, allow_policies_loop
    )
    # Cached parser facts are mutable mappings; never share them with callers.
    return deepcopy(spec), list(errors)


@lru_cache(maxsize=128)
def _inspect_group_script_source(
    source: str, script_name: str, allow_policies_loop: bool
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    tree = _parse_static_source(source)
    constants = _extract_module_constants(tree)
    all_parser_calls = {
        id(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) in PARSER_CALL_NAMES
    }
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    entry_fn = funcs.get("main")
    if entry_fn is None:
        return None, (f"MISSING_MAIN:{script_name}",)
    has_calls_in_main = any(id(n) in all_parser_calls for n in ast.walk(entry_fn))
    if not has_calls_in_main and "run" in funcs:
        entry_fn = funcs["run"]

    node: dict[str, Any] = {
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
    return node, tuple(sorted(set(errors)))


def _inspect_pm03_cli_dispatch(path: Path) -> tuple[set[str], list[str]]:
    """Bounded AST inspector for pm03_cli.execute JSON spec['action'] dispatch."""
    if not path.is_file():
        return set(), ["MISSING_OWNER_MODULE:copytrade_pm.pm03_cli"]
    tree = _parse_static_source(path.read_text(encoding="utf-8"))
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


def _validate_group_scripts(root: Path, scripts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    parsed_scripts: dict[str, dict[str, Any]] = {}

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
        expected_store_true = contract["store_true"]
        expected_choices = contract["choices"]

        actual_store_true = {
            opt for opt, meta in spec["options"].items() if meta["action"] == "store_true"
        }
        for extra_flag in sorted(actual_store_true - expected_store_true):
            problems.append(f"UNLISTED_GROUP_MODE_FLAG:{name}:{extra_flag}")
        for missing_flag in sorted(expected_store_true - actual_store_true):
            problems.append(f"STALE_GROUP_MODE_FLAG:{name}:{missing_flag}")

        actual_choices: dict[str, dict[str, Any]] = {}
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
        interface = str(meta["interface"])
        if (
            cap_id in _NON_READ_ONLY_GROUP_MODES or "--apply" in interface.split()
        ) and safety == "READ_ONLY":
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{cap_id}")
        parent_max_rank[script_name] = max(
            parent_max_rank.get(script_name, -1), _CLASS_RANK.get(safety, 99)
        )
        problems.extend(
            _validate_declared_contract(
                tag="GROUP",
                target=cap_id,
                cap_id=cap_id,
                safety=safety,
                parser_spec=parsed_scripts.get(script_name),
                required_arguments=meta["required_arguments"],
                runtime_required_arguments=meta["runtime_required_arguments"],
                access=meta["access"],
                ignore_positionals=_GROUP_MODE_POSITIONALS.get(script_name, frozenset()),
                mismatch_code="GROUP_REQUIRED_GROUP_OR_POSITIONAL_MISMATCH",
                check_groups=True,
                ignore_runtime_prefix="spec.",
            )
        )

    for cap_id, script_name in _GROUP_NATIVE_SCRIPTS.items():
        _, _, _, safety, _ = NATIVE[cap_id]
        if cap_id in _NON_READ_ONLY_GROUP_MODES and safety == "READ_ONLY":
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{cap_id}")
        parent_max_rank[script_name] = max(
            parent_max_rank.get(script_name, -1), _CLASS_RANK.get(safety, 99)
        )
        problems.extend(
            _validate_declared_contract(
                tag="NATIVE",
                target=cap_id,
                cap_id=cap_id,
                safety=safety,
                parser_spec=parsed_scripts.get(script_name),
                required_arguments=NATIVE_REQUIRED_ARGUMENTS.get(cap_id, []),
                runtime_required_arguments=NATIVE_RUNTIME_REQUIRED_ARGUMENTS.get(cap_id, []),
                access=NATIVE_ACCESS.get(cap_id),
                mismatch_code="NATIVE_POSITIONAL_MISMATCH",
            )
        )

    for script_name, max_child_rank in parent_max_rank.items():
        parent_desc = GROUPS.get(script_name)
        if parent_desc is not None and _CLASS_RANK.get(parent_desc[2], -1) < max_child_rank:
            problems.append(f"UNSAFE_GROUP_CLASSIFICATION:{script_name}")

    return sorted(set(problems))
