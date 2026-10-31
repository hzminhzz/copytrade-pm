"""Contracts protecting the isolated PM package after repository extraction."""

import ast
from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules

import copytrade_pm
import pytest
from copytrade_pm.pm_manager import source_rows


def test_every_extracted_module_imports_without_legacy_ensemble_runtime():
    modules = sorted(module.name for module in iter_modules(copytrade_pm.__path__))
    assert len(modules) == 22
    for name in modules:
        module = import_module(f"copytrade_pm.{name}")
        assert module.__name__ == f"copytrade_pm.{name}"


def test_no_pm_module_imports_legacy_ensemble_or_broker_runtime():
    root = Path(copytrade_pm.__file__).parent
    for path in root.glob("pm*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("ensemble", "ccxt", "propr"))
            if isinstance(node, ast.Import):
                for item in node.names:
                    assert not item.name.startswith(("ensemble", "ccxt", "propr"))


def test_pm01_v2_acceptance_and_schema_downgrade_guard():
    aliases = [f"TEST-{i:02d}" for i in range(36)]
    replay = {
        "schema": "pm01_fill_only_replay_v2",
        "wallet_count": 36,
        "never_claim_prospective_alpha": True,
        "rows": [
            {
                "wallet": alias,
                "latency_minutes": latency,
                "oracle_hindsight": True,
                "known_at": "UNKNOWN_VENDOR_HISTORICAL_ORACLE",
            }
            for alias in aliases
            for latency in (5, 15, 60)
        ],
    }
    grouped = source_rows(replay, aliases)
    assert len(grouped) == 36
    assert all(len(grouped[alias]) == 3 for alias in aliases)

    with pytest.raises(ValueError, match="UNSUPPORTED_PM01_REPLAY"):
        source_rows({**replay, "schema": "pm01_fill_only_replay_v3"}, aliases)
    with pytest.raises(ValueError, match="PM01_PROVENANCE_MISSING"):
        source_rows({**replay, "never_claim_prospective_alpha": False}, aliases)
