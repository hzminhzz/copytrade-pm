"""Retirement means no V4 runtime module, while the CWSA source still works."""

import importlib

import pytest

from copytrade_pm import pm_cwsa_source_observer, pm_forward_observed_paper
from copytrade_pm.pm_checkpoint_source import selected_checkpoint_sources
from copytrade_pm.pm_source_selection import official_accounts, selected_parents


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
