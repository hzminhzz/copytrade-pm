"""Phase 6B offline source-evidence gates (no network or trade authority)."""

from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
import pytest

from copytrade_pm.pm_phase6b import (
    WALLETS,
    _market_directory,
    inspect_fill_chain,
    market_days,
    require_same_frozen,
    safe_write_json,
)


ADDRESS = "0x" + "1" * 40


def _fill(tid: int, before: str, side: str, size: str, ms: int = 1786000000000):
    return {
        "user": ADDRESS,
        "coin": "BTC",
        "tid": tid,
        "time": ms,
        "sz": size,
        "start_position": before,
        "px": "100",
        "side": side,
    }


def test_portfolio_sizes_and_original_composition():
    assert sum(map(D, map(str, WALLETS["A_base"].values()))) == D("100")
    assert sum(map(D, map(str, WALLETS["A_active"].values()))) == D("150")
    assert sum(map(D, map(str, WALLETS["B_active"].values()))) == D("160")
    assert set(WALLETS["C_equal"]) == {"H21", "N01", "N07"}
    assert set(WALLETS["D_equal"]) == {"N01", "N07", "ACT08"}


def test_reject_frozen_weight_change():
    bad = [
        {
            "portfolio_id": "Ensemble_A_Pure_New50_1x",
            "members": [
                {"member_alias": alias, "original_weight_percent": 2} for alias in WALLETS["A_base"]
            ],
        },
    ]
    with pytest.raises((ValueError, KeyError), match="PHASE5_FROZEN_WEIGHTS_CHANGED|Ensemble"):
        require_same_frozen(bad)


def test_zero_before_and_zero_after_anchor():
    e = [_fill(1, "0", "B", "2"), _fill(2, "2", "A", "2", 1786000060000)]
    row = inspect_fill_chain(e, ADDRESS)
    assert row["fill_events_in_window"] == 2
    assert row["instruments"][0]["first_observed_flat_after_at"] is not None
    assert row["instruments"][0]["chain_breaks"] == 0
    assert row["counts"].get("UNKNOWN_PRE_ANCHOR_POSITION", 0) == 0


def test_open_position_and_gap_are_not_imputed_flat():
    e = [
        _fill(1, "3", "B", "2"),
        _fill(2, "100", "A", "2", 1786000060000),
    ]
    row = inspect_fill_chain(e, ADDRESS)
    assert row["counts"]["UNKNOWN_PRE_ANCHOR_POSITION"] == 1
    assert row["counts"]["POSITION_CHAIN_BREAK"] == 1
    assert row["instruments"][0]["first_observed_flat_after_at"] is None


def test_same_millisecond_link_can_override_tid_order():
    e = [
        _fill(30, "2", "A", "2"),
        _fill(20, "0", "B", "2"),
    ]
    row = inspect_fill_chain(e, ADDRESS)
    assert row["instruments"][0]["chain_breaks"] == 0


def test_duplicates_are_not_silent():
    e = [_fill(1, "0", "B", "2"), _fill(1, "0", "B", "2")]
    row = inspect_fill_chain(e, ADDRESS)
    assert row["counts"]["DUPLICATE_COIN_TID"] == 1


def test_wrong_wallet_fails():
    with pytest.raises(ValueError, match="FILL_WALLET_IDENTITY_MISMATCH"):
        inspect_fill_chain([dict(_fill(1, "0", "B", "1"), user="bad")], ADDRESS)


def test_market_namespace_is_exact(tmp_path: Path):
    family, name = _market_directory(tmp_path, "xyz:CL")
    assert family == tmp_path / "crypto_futures_ohlcv_1m_HYPERLIQUID_XYZ_PERP" / "symbol=CL"
    assert name == "xyz:CL"
    assert _market_directory(tmp_path, "#123")[0] is None
    assert _market_directory(tmp_path, "../BTC")[0] is None


def test_missing_days_not_zero_coverage(tmp_path: Path):
    result = market_days(
        tmp_path,
        "BTC",
        start=datetime(2026, 8, 5, tzinfo=UTC),
        end=datetime(2026, 8, 6, tzinfo=UTC),
    )
    assert result["native_days"] == 0
    assert result["missing_days"] == ["2026-08-05"]
    assert result["all_parquet_hashes_verified"] is False


def test_immutable_evidence_writes(tmp_path: Path):
    p = tmp_path / "report.json"
    original = safe_write_json(p, {"a": 1})
    assert safe_write_json(p, {"a": 1}) == original
    with pytest.raises(FileExistsError, match="IMMUTABLE_RESEARCH_GENERATION_CONFLICT"):
        safe_write_json(p, {"a": 2})
