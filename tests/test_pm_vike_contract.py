"""Vike fill-subscription preflight must not silently inherit a $1,000 floor."""

import pytest

from copytrade_pm.pm_vike_contract import verify_fill_subscription


WALLET = "0x" + "a" * 40
REQUESTED = {"wallet": [WALLET], "min_usd": 0}


def response(filters):
    return {
        "valid": True,
        "subscribe": {
            "action": "subscribe",
            "channel": "hl.fills",
            "filter": {"wallet": [WALLET], **filters},
        },
    }


@pytest.mark.parametrize("echo", [{}, {"min_usd": 0}])
def test_explicit_zero_normalized_echo_is_preflight_only(echo):
    verdict = verify_fill_subscription(response(echo), [WALLET], requested_filter=REQUESTED)
    assert verdict["status"] == "PREFLIGHT_ONLY"
    assert verdict["production_admitted"] is False
    assert verdict["rest_ws_parity"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "submission",
    [
        {"wallet": [WALLET]},
        {"wallet": [WALLET], "min_usd": 1000},
        {"wallet": [WALLET], "min_usd": True},
        {"wallet": [WALLET], "min_usd": "0"},
    ],
)
def test_omitted_or_ambiguous_requested_floor_refused(submission):
    with pytest.raises(ValueError, match="VIKE_EXPLICIT_SMALL_FILL_REQUEST_REQUIRED"):
        verify_fill_subscription(response({}), [WALLET], requested_filter=submission)


@pytest.mark.parametrize("echo", [{"min_usd": 1000}, {"min_usd": True}, {"min_usd": "0"}])
def test_positive_or_ambiguous_server_echo_refused(echo):
    with pytest.raises(ValueError, match="VIKE_SMALL_FILL_INCLUSION_UNVERIFIED"):
        verify_fill_subscription(response(echo), [WALLET], requested_filter=REQUESTED)


def test_submitted_wallet_must_match_approved_wallet_set():
    with pytest.raises(ValueError, match="VIKE_REQUEST_WALLETS_MISMATCH"):
        verify_fill_subscription(
            response({}),
            [WALLET],
            requested_filter={"min_usd": 0, "wallet": ["0x" + "b" * 40]},
        )


def test_valid_but_wrong_echo_wallet_fails():
    with pytest.raises(ValueError, match="VIKE_SUBSCRIPTION_WALLETS_MISMATCH"):
        verify_fill_subscription(
            {
                "valid": True,
                "subscribe": {
                    "action": "subscribe",
                    "channel": "hl.fills",
                    "filter": {"wallet": ["0x" + "b" * 40]},
                },
            },
            [WALLET],
            requested_filter=REQUESTED,
        )


def test_invalid_subscription_refused():
    with pytest.raises(ValueError, match="VIKE_SUBSCRIPTION_NOT_VALIDATED"):
        verify_fill_subscription({"valid": False}, [WALLET], requested_filter=REQUESTED)


@pytest.mark.parametrize("wallets", [[], [WALLET, WALLET]])
def test_empty_or_duplicate_wallets_refused(wallets):
    with pytest.raises(ValueError, match="VIKE_WALLET_SET_EMPTY_OR_DUPLICATED"):
        verify_fill_subscription(response({}), wallets, requested_filter=REQUESTED)
