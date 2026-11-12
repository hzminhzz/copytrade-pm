"""Dependency-light Reservoir pilot checks for core and market CI legs."""

from __future__ import annotations

import ast
from pathlib import Path
import re


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "pilot_reservoir_wallet_scoped.py"


def test_bounded_pilot_source_parses_and_owns_no_live_finance():
    tree = ast.parse(SOURCE.read_text())
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {
        "registry_scope",
        "source_keys",
        "column_budget",
        "fetch_fills",
        "fetch_snapshot",
        "validate_fills",
        "report",
    } <= functions
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(
        name.startswith(
            (
                "trading_connector",
                "prop_production",
                "copytrade_pm.pm03",
                "copytrade_pm.pm04",
                "copytrade_pm.wallet_store",
            )
        )
        for name in imported
    )


def test_no_hardcoded_live_wallet_or_secret_in_pilot_source():
    source = SOURCE.read_text()
    assert not re.search(r"0x[0-9a-fA-F]{40}", source)
    assert "AWS_SECRET_ACCESS_KEY=" not in source
    assert "PRIVATE_KEY=" not in source
    assert "RETROSPECTIVE_FIXED_COHORT_NOT_PIT_SELECTION" in source
    assert "historical_first_known" in source
