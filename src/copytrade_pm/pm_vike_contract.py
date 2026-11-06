"""Fail-closed contract validation for a proposed Vike Hyperliquid fill feed.

This is a research-only preflight, not a deployed feed or admission authority.
The provider's validation endpoint may omit an explicitly requested zero floor.
A missing echo cannot establish that small fills are delivered.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")


def verify_fill_subscription(
    response: Mapping[str, object],
    wallets: Sequence[str],
    *,
    requested_filter: Mapping[str, object],
) -> dict[str, object]:
    """Check zero request plus server validation; never certify WS delivery.

    Vike's normalization drops an explicitly requested zero from the echo,
    whereas an omitted minimum is echoed as the $1,000 default. Distinguish
    these by binding the original submitted filter to the validated response.
    """
    expected = [address.lower() for address in wallets]
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("VIKE_WALLET_SET_EMPTY_OR_DUPLICATED")
    if any(_ADDRESS.fullmatch(address) is None for address in expected):
        raise ValueError("VIKE_WALLET_ADDRESS_INVALID")
    if len(expected) > 1000:
        raise ValueError("VIKE_WALLET_SUBSCRIPTION_LIMIT")

    # Must inspect the *actual outbound request*, not infer it from the echo.
    requested_floor = requested_filter.get("min_usd")
    if (
        isinstance(requested_floor, bool)
        or not isinstance(requested_floor, (int, float))
        or requested_floor != 0
    ):
        raise ValueError("VIKE_EXPLICIT_SMALL_FILL_REQUEST_REQUIRED")
    submitted_wallets = requested_filter.get("wallet")
    if not isinstance(submitted_wallets, list) or len(submitted_wallets) != len(expected):
        raise ValueError("VIKE_REQUEST_WALLETS_MISMATCH")
    if any(not isinstance(addr, str) for addr in submitted_wallets) or set(
        addr.lower() for addr in submitted_wallets
    ) != set(expected):
        raise ValueError("VIKE_REQUEST_WALLETS_MISMATCH")

    if response.get("valid") is not True:
        raise ValueError("VIKE_SUBSCRIPTION_NOT_VALIDATED")
    subscribe = response.get("subscribe")
    if not isinstance(subscribe, Mapping):
        raise ValueError("VIKE_SUBSCRIPTION_ECHO_MISSING")
    if subscribe.get("action") != "subscribe" or subscribe.get("channel") != "hl.fills":
        raise ValueError("VIKE_SUBSCRIPTION_CHANNEL_MISMATCH")
    filters = subscribe.get("filter")
    if not isinstance(filters, Mapping):
        raise ValueError("VIKE_SUBSCRIPTION_FILTER_MISSING")
    actual = filters.get("wallet")
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError("VIKE_SUBSCRIPTION_WALLETS_MISMATCH")
    if any(not isinstance(addr, str) for addr in actual) or set(
        addr.lower() for addr in actual
    ) != set(expected):
        raise ValueError("VIKE_SUBSCRIPTION_WALLETS_MISMATCH")
    # Vike currently elides explicit zero from the normalized filter. The
    # validated default request, by contrast, echoes min_usd: 1000. Reject
    # every nonzero echo and retain an UNVERIFIED WS delivery classification.
    floor = filters.get("min_usd")
    if floor is not None and (
        isinstance(floor, bool) or not isinstance(floor, (int, float)) or floor != 0
    ):
        raise ValueError("VIKE_SMALL_FILL_INCLUSION_UNVERIFIED")
    return {
        "status": "PREFLIGHT_ONLY",
        "channel": "hl.fills",
        "wallet_count": len(expected),
        "min_usd": 0,
        "rest_ws_parity": "UNVERIFIED",
        "production_admitted": False,
    }
