"""Phase 7: deterministic, PIT-boundary and falsification tests for oracle sensitivity."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("polars")

from scripts import phase7_combo_328_native_sensitivity as combo  # noqa: E402


def _evidence() -> dict:
    return {
        "source_sha256": "a" * 64,
        "source_missing_any_coin": np.zeros(combo.MINUTES, dtype=np.bool_),
        "supported_nonflat_intervals": 1,
        "all_reconstructed_source_chain_leg_minutes": 10,
        "sha_verified_native_chain_leg_minutes": 10,
        "eligible_fills": 2,
        "source_market_missing_minute_leg_count": 0,
        "observed_source_active_minute_count": 10,
    }


def test_interval_slices_count_only_complete_source_minutes() -> None:
    start = combo.START_MS
    assert combo._full_minute_slice({"start_ms": start + 1, "end_ms": start + 3 * 60_000 + 10}) == (
        1,
        3,
    )
    assert combo._full_minute_slice({"start_ms": start, "end_ms": start + 60_000}) == (0, 1)
    assert combo._full_minute_slice({"start_ms": start + 20_000, "end_ms": start + 50_000}) == (
        1,
        0,
    )


def test_source_gross_normalization_and_market_gap_block() -> None:
    market = np.full(combo.MINUTES, np.nan, dtype=np.float32)
    market[:25] = 100.0
    market[7] = np.nan
    intervals = {
        "BTC": {
            "A": [
                {
                    "coin": "BTC",
                    "start_ms": combo.START_MS,
                    "end_ms": combo.START_MS + 12 * 60_000,
                    "qty": 2.0,
                }
            ]
        }
    }
    source_weights, evidence = combo._source_weights("A", _evidence(), intervals, {"BTC": market})
    assert evidence["all_reconstructed_source_chain_leg_minutes"] == 12
    assert evidence["sha_verified_native_chain_leg_minutes"] == 11
    assert evidence["source_missing_any_coin"][7]
    assert source_weights["BTC"][6] == pytest.approx(1.0)
    assert source_weights["BTC"][7] == 0.0


def test_six_minute_asof_observation_delay_no_same_bar_target() -> None:
    w = np.zeros(combo.MINUTES, dtype=np.float32)
    w[3:20] = 1
    market = np.full(combo.MINUTES, 100.0, dtype=np.float32)
    market[11] = 101.0
    model = combo.model_wallet("A", {"BTC": w}, {"BTC": market}, _evidence())
    assert not model.active[0:10].any()
    assert model.active[10]
    assert model.unit_mark[9] == 0
    assert model.unit_mark[10] == pytest.approx(0.01)
    assert model.unit_turnover[10] == pytest.approx(1.0)
    assert model.unit_turnover[11:15].sum() == 0


def test_final_in_window_position_is_unpriced_without_next_market_close() -> None:
    weights = np.zeros(combo.MINUTES, dtype=np.float32)
    weights[-20:] = 1
    prices = np.full(combo.MINUTES, 100.0, dtype=np.float32)
    model = combo.model_wallet("A", {"BTC": weights}, {"BTC": prices}, _evidence(), delay=0)
    assert model.active[-1]
    assert model.invalid[-1]
    peers = {_alias: _wallet(_alias, return_unit=0) for _alias in ("B", "C")}
    result = combo.simulate({"members": ["A", "B", "C"], "size": 3}, {"A": model, **peers})
    assert result["complete_priced_days"] == 89


def test_native_forward_price_gap_invalid_not_zero() -> None:
    w = np.zeros(combo.MINUTES, dtype=np.float32)
    w[:20] = 1
    market = np.full(combo.MINUTES, 100.0, dtype=np.float32)
    market[12] = np.nan
    model = combo.model_wallet("A", {"BTC": w}, {"BTC": market}, _evidence())
    assert model.invalid[11]
    assert model.invalid[12]


def _wallet(alias: str, *, return_unit: float = 1e-6, turnover: float = 0) -> combo.WalletModel:
    return combo.WalletModel(
        alias=alias,
        unit_mark=np.full(combo.MINUTES, return_unit, dtype=np.float64),
        unit_turnover=np.full(combo.MINUTES, turnover, dtype=np.float64),
        invalid=np.zeros(combo.MINUTES, dtype=np.bool_),
        active=np.ones(combo.MINUTES, dtype=np.bool_),
        selected_coin_weights={"BTC": np.ones(combo.MINUTES, dtype=np.float32)},
        source_coin_weights={"BTC": np.ones(combo.MINUTES, dtype=np.float32)},
        source_sha256="a" * 64,
        interval_count=1,
        full_interval_leg_minutes=100,
        priced_interval_leg_minutes=100,
        eligible_fill_events=2,
        missing_price_source_leg_minutes=0,
        estimated_active_source_minutes=100,
    )


def test_portfolio_score_fee_stress_increases_cost_and_flags_no_financial_pnl() -> None:
    members = ["A", "B", "C"]
    combo_row = {"members": members, "size": 3, "turnover_overlap": 1.0}
    result = combo.simulate(
        combo_row, {alias: _wallet(alias, turnover=0.0001) for alias in members}
    )
    assert result["complete_priced_days"] == 90
    assert (
        result["scenario"]["10"]["conditional_net_mark_pnl_usd"]
        > result["scenario"]["30"]["conditional_net_mark_pnl_usd"]
    )
    assert result["financial_follower_pnl"] is None
    assert result["prospective_first_known"] is False
    assert result["scientific_qualification"] is False
    assert result["worst_instant_btc_eth_down10_hype_down20_usd"] == pytest.approx(600)


def test_any_member_unpriceable_minute_blocks_its_entire_calendar_day() -> None:
    wallets = {alias: _wallet(alias) for alias in ("A", "B", "C")}
    wallets["A"].invalid[500] = True
    report = combo.simulate({"members": ["A", "B", "C"], "size": 3}, wallets)
    assert report["complete_priced_days"] == 89
    assert report["incomplete_priced_minutes"] == 1


def test_same_coin_opposite_positions_do_not_claim_agreement() -> None:
    wallets = [_wallet("A"), _wallet("B", return_unit=-1e-6)]
    wallets[1].source_coin_weights["BTC"] = -np.ones(combo.MINUTES, dtype=np.float32)
    fraction, weighted = combo._pairwise_same_coin_overlap(wallets)
    assert fraction == 0
    assert weighted == pytest.approx(1.0)


def test_intraday_breach_can_hide_behind_profitable_day_close() -> None:
    wallets = {alias: _wallet(alias, return_unit=0.0) for alias in ("A", "B", "C")}
    wallets["A"].unit_mark[100] = -0.25
    wallets["A"].unit_mark[200] = 0.28
    result = combo.simulate({"members": ["A", "B", "C"], "size": 3}, wallets)
    assert result["scenario"]["20"]["worst_completed_day_usd"] >= 0
    assert result["scenario"]["20"]["worst_intraday_loss_from_day_start_usd"] == pytest.approx(-500)
    assert result["sample_only_loss_reference_pass_20bps"] is True
    assert result["intraday_model_loss_reference_pass_20bps"] is False


def test_registry_rejects_alias_outside_158_addresses(monkeypatch, tmp_path) -> None:
    import sqlite3
    from contextlib import closing

    database = tmp_path / "registry.sqlite"
    with closing(sqlite3.connect(database)) as con:
        con.executescript(
            """
            CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,address TEXT);
            CREATE TABLE cohort_memberships(cohort_id TEXT,wallet_id INTEGER);
            CREATE TABLE exclusions(wallet_id INTEGER);
            CREATE TABLE snapshot_meta(key TEXT,value TEXT);
            """
        )
        con.execute("INSERT INTO snapshot_meta VALUES (?,?)", ("manifest_sha256", "a" * 64))
        con.execute(
            "INSERT INTO snapshot_meta VALUES (?,?)", ("observed_at", "2026-11-04T09:36:57Z")
        )
        for i in range(158):
            addr = f"0x{i:040x}"
            con.execute("INSERT INTO wallets VALUES (?,?)", (i + 1, addr))
            con.execute(
                "INSERT INTO cohort_memberships VALUES (?,?)",
                ("research-108" if i < 108 else "nansen-20" if i < 128 else "hyperx-30", i + 1),
            )
        con.commit()
    monkeypatch.setattr(combo, "DB", database)
    valid = combo.registry_source_identity([{"alias": "TEST", "address": "0x" + "0" * 40}])
    assert valid["registry_research_unique_count"] == 158
    with pytest.raises(ValueError, match="SCREEN_POOL_NOT_IN_CURRENT_RESEARCH_REGISTRY"):
        combo.registry_source_identity([{"alias": "TEST", "address": "0x" + "f" * 40}])


def test_max_drawdown_starts_at_10k_and_detects_peak_to_trough() -> None:
    assert combo._max_drawdown(np.array([500.0, -100.0, -900.0, 200.0])) == pytest.approx(1000.0)
