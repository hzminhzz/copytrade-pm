from __future__ import annotations

from decimal import Decimal as D
import json

import pytest

from copytrade_pm.pm_wallet_intent import load_intent, simulate


def _rows(specs, equity="10000", margin="5000", symbol="BTC", side="long", times=None):
    """specs: list of (mark, size) or None for a flat book."""
    out = []
    for i, spec in enumerate(specs):
        ts = times[i] if times else f"2026-10-01T0{i}:00:00Z"
        positions = []
        if spec is not None:
            mark, size = spec
            m, s = D(mark), D(size)
            positions = [
                {
                    "symbol": symbol,
                    "side": side,
                    "position_value": str(m * s),
                    "size": size,
                    "mark": mark,
                }
            ]
        out.append({"ts": ts, "equity": equity, "margin_used": margin, "positions": positions})
    return out


def _load(tmp_path, rows):
    path = tmp_path / "intent.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return load_intent(path)


def test_equity_mode_reproduces_source_notional(tmp_path):
    rows = _load(tmp_path, _rows([("100", "1"), ("110", "1"), ("105", "1")]))
    out = simulate(rows, capital=D("10000"), k=D("1"), mode="equity")
    assert out["status"] == "COMPLETE"
    assert out["final_equity"] == "10004.95"
    assert D(str(out["observed_max_drawdown"])) > 0
    assert out["breach"] is None


def test_margin_mode_doubles_size(tmp_path):
    rows = _load(tmp_path, _rows([("100", "1"), ("110", "1")]))
    out = simulate(rows, capital=D("10000"), k=D("1"), mode="margin")
    assert out["final_equity"] == "10019.9"


def test_daily_breach_is_detected_and_stops(tmp_path):
    rows = _load(tmp_path, _rows([("100", "100"), ("80", "100"), ("80", "100"), ("80", "100")]))
    out = simulate(rows, capital=D("10000"), k=D("1"), mode="equity")
    assert out["status"] == "BREACHED"
    assert "DAILY" in out["breach"]["kinds"]
    assert out["hours"] < len(rows)


def test_non_hourly_gap_fails_closed(tmp_path):
    rows = _load(
        tmp_path,
        _rows(
            [("100", "1"), ("101", "1"), ("102", "1")],
            times=["2026-10-01T00:00:00Z", "2026-10-01T01:00:00Z", "2026-10-01T03:00:00Z"],
        ),
    )
    out = simulate(rows, mode="equity")
    assert out["status"] == "BLOCKED_INTENT_GAP"
    assert out["gap_seconds"] == 7200


def test_exit_turnover_is_charged(tmp_path):
    rows = _load(tmp_path, _rows([("100", "1"), None, None]))
    out = simulate(rows, mode="equity")
    # 5bp on the 100 entry and 5bp on the 100 exit
    assert out["fees"] == "0.10"
    assert out["stale_closes"] == 1
    assert out["final_equity"] == "9999.90"


def test_trailing_floor_is_capped_at_initial_balance(tmp_path):
    rows = _load(tmp_path, _rows([("100", "10"), ("200", "10"), ("110", "10"), ("100", "10")]))
    out = simulate(rows, mode="equity", trailing_loss=D("0.08"), profit_target=D("0.5"))
    # HWM ~10999.95; uncapped trailing floor would be ~10199.95 and breach at
    # 110. The cap puts the floor at 10000, so 110 survives and 100 breaches.
    assert out["status"] == "BREACHED"
    assert out["breach"]["ts"] == "2026-10-01T03:00:00Z"
    assert "TRAILING" in out["breach"]["kinds"]
    assert out["breach"]["floor"] == "10000"


def test_unknown_mode_rejected(tmp_path):
    rows = _load(tmp_path, _rows([("100", "1"), ("110", "1")]))
    with pytest.raises(ValueError, match="UNKNOWN_SIZING_MODE"):
        simulate(rows, mode="notional")
