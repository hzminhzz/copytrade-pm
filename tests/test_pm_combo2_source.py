"""Read-only source snapshot rules for Combo 2."""

from hashlib import sha256

import pytest

from copytrade_pm.pm_combo2_source import standard_mode_book

ADDRESS = "0x" + "1" * 40
RECEIVED = "2026-11-02T10:05:00+00:00"


def state(equity="100000", positions=()):
    return {
        "marginSummary": {
            "accountValue": equity,
            "totalNtlPos": "300000",
            "totalMarginUsed": "30000",
        },
        "assetPositions": list(positions),
    }


def source(*, account_mode="STANDARD_SEPARATE_DEX_BALANCES", spot_absent=True):
    return standard_mode_book(
        manager="W028",
        address=ADDRESS,
        received_at=RECEIVED,
        expected_dexs={"default", "xyz"},
        account_mode=account_mode,
        subaccount_scope_complete=True,
        spot_collateral_verified_absent=spot_absent,
        raw_all_dexs={
            "user": ADDRESS,
            "clearinghouseStates": [
                [
                    "",
                    state(
                        positions=[
                            {
                                "type": "oneWay",
                                "position": {"coin": "BTC", "szi": "3", "positionValue": "300000"},
                            }
                        ]
                    ),
                ],
                ["xyz", state(equity="0", positions=[])],
            ],
        },
    )


def test_source_live_equity_and_position_value_reconcile():
    book = source()
    assert book["equity"] == "100000"
    assert book["positions"]["hyperliquid/mainnet:perp:default/BTC"] == {
        "quantity": "3",
        "mark": "100000",
    }
    assert book["subject_sha"] == sha256(ADDRESS.lower().encode()).hexdigest()
    assert book["event_at"] == RECEIVED
    assert book["not_first_known_fill"] is True


@pytest.mark.parametrize("mode", ["UNIFIED", "PORTFOLIO_MARGIN", "UNKNOWN"])
def test_cannot_sum_dex_nav_when_account_mode_is_ambiguous(mode):
    with pytest.raises(ValueError, match="SOURCE_ACCOUNT_MODE"):
        source(account_mode=mode)


def test_spot_collateral_cannot_be_omitted_from_equity_denominator():
    with pytest.raises(ValueError, match="SOURCE_SPOT_COLLATERAL"):
        source(spot_absent=False)


def test_missing_dex_census_never_assumes_zero_positions():
    with pytest.raises(ValueError, match="E4_ALL_DEXS_NOT_EQUAL_OFFICIAL_CATALOG"):
        standard_mode_book(
            manager="W028",
            address=ADDRESS,
            received_at=RECEIVED,
            expected_dexs={"default", "xyz", "another"},
            account_mode="STANDARD_SEPARATE_DEX_BALANCES",
            subaccount_scope_complete=True,
            spot_collateral_verified_absent=True,
            raw_all_dexs={"user": ADDRESS, "clearinghouseStates": [["", state()]]},
        )
