"""Retired T0+300 entrypoints must fail closed without blocking CWSA imports."""

import pytest

from copytrade_pm import (
    pm_forward_observed_paper,
    pm_v4_selected_positions,
    pm_v4_sixteen_paper,
)
from copytrade_pm.pm_checkpoint_source import selected_checkpoint_sources


def test_retired_v4_ws_entrypoint_rejected_before_io(capsys):
    with pytest.raises(SystemExit) as exc:
        pm_v4_selected_positions.main(
            ["--registry-db", "/missing/registry.db", "--state-root", "/missing/state"]
        )
    assert exc.value.code == 2
    assert "RETIRED_V4_T300" in capsys.readouterr().err


def test_retired_v4_sixteen_paper_rejected_before_io(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "pm_v4_sixteen_paper",
            "--registry-db",
            "/missing/registry.db",
            "--source-db",
            "/missing/source.db",
            "--price-db",
            "/missing/price.db",
            "--propr-catalog",
            "/missing/catalog.json",
            "--campaign-manifest",
            "/missing/campaign.json",
            "--campaign-sha256",
            "0" * 64,
            "--state-root",
            "/missing/state",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        pm_v4_sixteen_paper.main()
    assert exc.value.code == 2
    assert "RETIRED_V4_T300" in capsys.readouterr().err


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


def test_cwsa_source_reader_remains_importable():
    assert callable(selected_checkpoint_sources)
    assert callable(pm_v4_selected_positions.observe_checkpoints)
