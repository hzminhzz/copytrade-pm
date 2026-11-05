"""Phase 7 candidate shortlist remains a non-financial cheap screen."""

import pytest

pytest.importorskip("polars")

from scripts.phase7_candidate_screen import main_perp_turnover, pair_turnover_overlap, run


def _wallet(alias, address, coin, *, allowed=True):
    return {
        "alias": alias,
        "address": address,
        "recommendation": "CANDIDATE_UNVERIFIED" if allowed else "REJECT",
        "opening_positions": True,
        "main_perp_fill_fraction": 1.0,
        "observation_days": 60,
        "fills_per_observation_day": 10,
        "top_coin": coin,
        "gross_turnover_by_coin_fraction": {coin: 1.0},
    }


def test_pair_turnover_overlap_penalizes_same_coin() -> None:
    a = _wallet("A", "0x" + "1" * 40, "BTC")
    b = _wallet("B", "0x" + "2" * 40, "BTC")
    c = _wallet("C", "0x" + "3" * 40, "ETH")
    assert pair_turnover_overlap(a, b) == 1.0
    assert pair_turnover_overlap(a, c) == 0.0


def test_no_financial_rankings_or_unsupported_wallet_promotion() -> None:
    wallets = [
        _wallet(f"W{i}", "0x" + f"{i:040x}", symbol)
        for i, symbol in enumerate(("BTC", "ETH", "NEAR", "HYPE", "SOL", "TAO"), 1)
    ]
    wallets.append(_wallet("R", "0x" + "a" * 40, "ARB", allowed=False))
    # Frozen controls remain separately visible even when absent from the pool.
    outcome = run({"wallets": wallets})
    assert outcome["pool_count"] == 6
    assert len(outcome["top10_screen_three"]) == 10
    assert all("R" not in x["members"] for x in outcome["top10_screen_three"])
    assert all(
        x["portfolio_pnl"] is None and x["max_dd"] is None for x in outcome["top10_screen_five"]
    )
    assert outcome["scientific_qualification"] is False
    assert outcome["mandatory_controls"]["E6"]["status"] == "MISSING_SOURCE_IDENTITY"


def test_missing_source_positions_or_main_perp_fills_cannot_be_promoted() -> None:
    wallets = [
        _wallet("A", "0x" + "1" * 40, "BTC"),
        _wallet("B", "0x" + "2" * 40, "ETH"),
        _wallet("C", "0x" + "3" * 40, "NEAR"),
        _wallet("D", "0x" + "4" * 40, "SOL"),
    ]
    wallets[2]["opening_positions"] = False
    wallets[3]["main_perp_fill_fraction"] = 0.79
    result = run({"wallets": wallets})
    assert result["pool_count"] == 2
    assert result["top10_screen_three"] == []
    assert "C" not in result["pool_aliases"]
    assert "D" not in result["pool_aliases"]


def test_small_hip3_side_activities_are_excluded_from_turnover_not_manager() -> None:
    base = _wallet("A", "0x" + "1" * 40, "BTC")
    base["gross_turnover_by_coin_fraction"] = {"BTC": 0.85, "xyz:PLTR": 0.15}
    eth = _wallet("B", "0x" + "2" * 40, "ETH")
    pure = _wallet("C", "0x" + "3" * 40, "BTC")
    normalized, fraction = main_perp_turnover(base)
    assert normalized == {"BTC": 1.0}
    assert fraction == 0.85
    assert pair_turnover_overlap(base, eth) == 0
    assert pair_turnover_overlap(base, pure) == 1
    output = run({"wallets": [base, eth, pure]})
    assert "A" in output["pool_aliases"]
    assert output["pool_count"] == 3
    assert output["top10_screen_three"][0]["verified_atomic_initial_books"] == 0


def test_unknown_market_scope_cannot_improve_diversity() -> None:
    no_book = _wallet("A", "0x" + "1" * 40, "BTC")
    no_book["gross_turnover_by_coin_fraction"] = {"xyz:BRENTOIL": 1.0}
    other = _wallet("B", "0x" + "2" * 40, "ETH")
    assert pair_turnover_overlap(no_book, other) == 1
    assert run({"wallets": [no_book, other]})["pool_count"] == 1


def test_hip3_is_not_eligible_for_main_perp_screen() -> None:
    wallets = [
        _wallet("A", "0x" + "1" * 40, "BTC"),
        _wallet("B", "0x" + "2" * 40, "ETH"),
        _wallet("C", "0x" + "3" * 40, "HYPE"),
        _wallet("OIL", "0x" + "4" * 40, "xyz:BRENTOIL"),
    ]
    outcome = run({"wallets": wallets})
    assert outcome["pool_count"] == 3
    assert "OIL" not in outcome["pool_aliases"]
