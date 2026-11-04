"""Phase 7 candidate shortlist remains a non-financial cheap screen."""
from scripts.phase7_candidate_screen import pair_turnover_overlap, run


def _wallet(alias, address, coin, *, allowed=True):
    return {
        "alias": alias,
        "address": address,
        "recommendation": "CANDIDATE_UNVERIFIED" if allowed else "REJECT",
        "opening_positions": True,
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
    assert all(x["portfolio_pnl"] is None and x["max_dd"] is None for x in outcome["top10_screen_five"])
    assert outcome["scientific_qualification"] is False
    assert outcome["mandatory_controls"]["E6"]["status"] == "MISSING_SOURCE_IDENTITY"


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
