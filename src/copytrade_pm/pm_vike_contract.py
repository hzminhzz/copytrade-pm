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
) -> dict[str, object]:
    """Require an explicit zero-minimum subscription and exact wallet coverage.

    Reject omitted defaults, unexpected extra wallets and ambiguous acceptance.
    A passing preflight still requires actual WebSocket/REST parity tests.
    """
    expected = [address.lower() for address in wallets]
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("VIKE_WALLET_SET_EMPTY_OR_DUPLICATED")
    if any(_ADDRESS.fullmatch(address) is None for address in expected):
        raise ValueError("VIKE_WALLET_ADDRESS_INVALID")
    if len(expected) > 1000:
        raise ValueError("VIKE_WALLET_SUBSCRIPTION_LIMIT")

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
    # bool is a subclass of int; do not accept True as a numeric zero.
    floor = filters.get("min_usd")
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or floor != 0:
        raise ValueError("VIKE_SMALL_FILL_INCLUSION_UNVERIFIED")
    return {
        "status": "PREFLIGHT_ONLY",
        "channel": "hl.fills",
        "wallet_count": len(expected),
        "min_usd": 0,
        "rest_ws_parity": "UNVERIFIED",
        "production_admitted": False,
    }
