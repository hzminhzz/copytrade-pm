"""Read-only conversion of official Hyperliquid all-DEX account receipts.

No network imports. Standard-mode perp accounts only: unified and portfolio
margin accounts do not expose economically meaningful independent DEX NAVs.
A live acquisition caller must capture the official abstraction mode, complete
DEX census, subaccount scope, raw response bytes and first-local-receipt clock.
"""

from __future__ import annotations

from decimal import Decimal as D
from hashlib import sha256
from typing import Any

from .pm03_account import clock, number
from .pm_e4_prospective import account_state


def standard_mode_book(
    *,
    manager: str,
    address: str,
    received_at: str,
    raw_all_dexs: dict[str, Any],
    expected_dexs: set[str],
    account_mode: str,
    subaccount_scope_complete: bool,
    spot_collateral_verified_absent: bool,
) -> dict[str, Any]:
    """Produce a coherent manager book or reject; never infer missing equity."""
    if manager not in ("W028", "CA-008", "W015"):
        raise ValueError("UNKNOWN_COMBO2_MANAGER")
    if account_mode != "STANDARD_SEPARATE_DEX_BALANCES":
        raise ValueError("SOURCE_ACCOUNT_MODE_EQUITY_NOT_RECONCILED")
    if not subaccount_scope_complete or not expected_dexs:
        raise ValueError("SOURCE_SUBACCOUNT_OR_DEX_CENSUS_UNKNOWN")
    if spot_collateral_verified_absent is not True:
        raise ValueError("SOURCE_SPOT_COLLATERAL_NOT_RECONCILED")
    clock(received_at)
    parsed = account_state(raw_all_dexs, address, expected_dexs)
    records = raw_all_dexs["clearinghouseStates"]
    equity = D("0")
    positions: dict[str, dict[str, str]] = {}
    for pair in records:
        dex, state = pair
        dex = dex or "default"
        nav = number(state["marginSummary"]["accountValue"])
        equity += nav
        for wrapper in state["assetPositions"]:
            row = wrapper["position"]
            qty = number(row["szi"])
            if not qty:
                continue
            coin = row["coin"]
            if dex == "default" and ":" in coin:
                raise ValueError("SOURCE_DEFAULT_DEX_SYMBOL_NAMESPACE_MISMATCH")
            if dex != "default" and not coin.startswith(dex + ":"):
                raise ValueError("SOURCE_HIP3_MARKET_NAMESPACE_MISMATCH")
            native = coin.split(":")[-1]
            identifier = f"hyperliquid/mainnet:perp:{dex}/{native}"
            valuation = number(row["positionValue"])
            if valuation <= 0:
                raise ValueError("UNKNOWN_SOURCE_MARK")
            derived_mark = abs(valuation / qty)
            if identifier in positions:
                raise ValueError("DUPLICATE_SOURCE_POSITION")
            positions[identifier] = {
                "quantity": str(qty),
                "mark": str(derived_mark),
            }
    if equity <= 0 or parsed["position_count"] != len(positions):
        raise ValueError("SOURCE_EQUITY_OR_POSITION_CENSUS_MISMATCH")
    return {
        "manager": manager,
        "subject_sha": sha256(address.lower().encode()).hexdigest(),
        "quality": "OFFICIAL_ALL_DEXS_READ_ONLY",
        "full_book": True,
        "all_dexes_complete": True,
        "source_equity_basis": "STANDARD_PERP_DEX_NAV_SUM",
        "spot_or_other_collateral_included": False,
        "spot_collateral_verified_absent": True,
        "equity": str(equity),
        "positions": dict(sorted(positions.items())),
        # Account snapshots do not establish an earlier *trade* observation.
        # Treat receipt as the first-known source state, never backfill trades.
        "event_at": received_at,
        "first_known_at": received_at,
        "not_first_known_fill": True,
    }
