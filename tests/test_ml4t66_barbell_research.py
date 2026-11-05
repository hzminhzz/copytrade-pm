"""Deterministic invariants for the research-only barbell scenario tool."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ml4t66_barbell_research import (  # noqa: E402
    first_unmanaged_pod_stop,
    passage,
    risk_stats,
    scale_batch,
)


def test_intrabar_adverse_loss_precedes_same_minute_target() -> None:
    close = np.array([10000., 11001.])
    adverse = np.array([10000., 9990.])
    result = passage(close, adverse, None)
    assert result["status"] == "MODELED_BREACH_BEFORE_GAP"
    assert result["minute"] == 1


def test_first_passage_blocks_on_first_unknown_mark() -> None:
    close = np.array([10000., 10050., 11100.])
    adverse = close.copy()
    result = passage(close, adverse, 2)
    assert result["status"] == "BLOCKED_GAP"
    assert result["minute"] == 2


def test_first_passage_touch_at_boundary() -> None:
    close = np.array([10000., 10500., 11000.])
    adverse = close.copy()
    result = passage(close, adverse, None)
    assert result["status"] == "MODELED_TARGET_BEFORE_GAP"
    assert result["minute"] == 2


def test_adverse_risk_includes_high_watermark() -> None:
    daily, trailing = risk_stats(
        np.array([10010., 9990.]),
        np.array([10005., 9980.]),
    )
    assert daily == 30.
    assert trailing == 30.


def test_scale_batch_preserves_requested_true_k() -> None:
    batch = pl.DataFrame({
        "alias": ["A", "B"],
        "net_qty": [10., -4.],
    })
    # Source E=20k gives base=.35, n=2 => built-in effective .175.
    scaled = scale_batch(batch, ("A", "B"), {"A": 0.10, "B": 0.05},
                         {"A": "20000", "B": "20000"})
    got = scaled["net_qty"].to_list()
    assert np.isclose(got[0] * .175, 1.0)
    assert np.isclose(got[1] * .175, -.2)


def test_runner_hard_stop_is_latched_diagnostic() -> None:
    result = first_unmanaged_pod_stop(
        np.array([10000., 9980.]),
        np.array([10000., 9890.]),
        "runner",
    )
    assert result == {"minute": 1, "reason": "DAILY_HARD"}
