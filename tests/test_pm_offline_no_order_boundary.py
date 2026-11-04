"""Offline milestone dependency boundary: import graph contains no broker/network path.

This conservative source-level audit complements runtime read-only tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_ROOTS = {
    "ccxt",
    "ccxtpro",
    "requests",
    "httpx",
    "aiohttp",
    "web3",
    "eth_account",
}
FORBIDDEN_REPO_PATHS = {
    "pm_propr_broker",
    "pm_live_broker",
    "pm_order_gateway",
    "pm_forward_execution_broker",
    "pm_forward_release",
    "pm_forward_paper",
}


def test_all_offline_modules_import_no_broker_or_mutating_network_adapter():
    folder = Path(__file__).resolve().parents[1] / "src" / "copytrade_pm"
    paths = sorted(folder.glob("pm_offline_*.py"))
    assert len(paths) >= 15
    for path in paths:
        tree = ast.parse(path.read_text(), filename=path.name)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [entry.name for entry in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_ROOTS, (path.name, name)
                assert not any(
                    blocked == name or blocked in name.split(".")
                    for blocked in FORBIDDEN_REPO_PATHS
                ), (path.name, name)
