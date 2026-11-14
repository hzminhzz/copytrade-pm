"""Retirement means no V4 runtime module, while the CWSA source still works."""

import ast
import importlib
from pathlib import Path

import pytest

from copytrade_pm import pm_cwsa_source_observer, pm_forward_observed_paper
from copytrade_pm.pm_checkpoint_source import selected_checkpoint_sources
from copytrade_pm.pm_source_selection import official_accounts, selected_parents

PKG_DIR = Path(__file__).resolve().parents[1] / "src" / "copytrade_pm"


@pytest.mark.parametrize(
    "module",
    ["copytrade_pm.pm_v4_selected_positions", "copytrade_pm.pm_v4_sixteen_paper"],
)
def test_retired_v4_launcher_is_unimportable(module):
    with pytest.raises(ImportError):
        importlib.import_module(module)


def test_cwsa_source_rejects_old_ws_mode_before_io(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        pm_cwsa_source_observer.main(
            [
                "--registry-db",
                str(tmp_path / "registry.sqlite"),
                "--state-root",
                str(tmp_path / "state"),
                "--portfolios",
                "A",
                "--checkpoint-config",
                str(tmp_path / "config.json"),
                "--checkpoint-config-sha256",
                "a" * 64,
                "--source-mode",
                "LEGACY_WS",
            ]
        )
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not (tmp_path / "state").exists()


def test_retired_v4_single_paper_rejected_before_io(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "pm_forward_observed_paper",
            "--source-db",
            "/missing/source.db",
            "--state-root",
            "/missing/state",
            "--run-id",
            "retired_p1",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        pm_forward_observed_paper.main()
    assert exc.value.code == 2
    assert "RETIRED_V4_T300" in capsys.readouterr().err


def test_cwsa_and_historical_proof_adapters_remain_importable():
    assert callable(selected_checkpoint_sources)
    assert callable(pm_cwsa_source_observer.observe_checkpoints)
    assert callable(selected_parents)
    assert callable(official_accounts)


def test_active_modules_never_import_legacy_v4_or_grafana_modules():
    prefixes = ("pm_cwsa_", "pm_checkpoint_", "pm_forward_", "wallet_health_", "strategy_")
    exempt = {"strategy_source_verify.py"}
    forbidden_prefixes = ("pm_v4_", "v4_source_", "dashboard")
    violations: list[str] = []

    for path in sorted(PKG_DIR.glob("*.py")):
        if not path.name.startswith(prefixes) or path.name in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
                if node.module in ("", "copytrade_pm"):
                    modules.extend(alias.name for alias in node.names)
                lineno = node.lineno
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
                lineno = node.lineno
            else:
                lineno = 0
            for mod in modules:
                top = mod.split(".")[-1] if mod.startswith("copytrade_pm.") else mod.split(".")[0]
                if any(mod.startswith(fp) or top.startswith(fp) for fp in forbidden_prefixes):
                    violations.append(f"{path.name}:{lineno} imports {mod}")

    assert violations == []
