"""Explicit versioned margin-health projection, never an invented liquidation."""

from __future__ import annotations

from decimal import Decimal

from .pm03_account import Account, clock, digest, number


def margin_projection(account: Account, contract: dict | None, *, as_of: str) -> dict:
    """Observe margin headroom or refuse to model venue liquidation."""
    if not isinstance(contract, dict):
        return {"status": "UNKNOWN_LIQUIDATION", "reasons": ["MISSING_MARGIN_CONTRACT"]}
    body = {k: v for k, v in contract.items() if k != "contract_sha"}
    if (
        contract.get("contract_sha") != digest(body)
        or contract.get("schema") != "paper_margin_contract_v1"
        or contract.get("synthetic_fixture") is not True
    ):
        return {"status": "UNKNOWN_LIQUIDATION", "reasons": ["UNVERIFIED_MARGIN_CONTRACT"]}
    try:
        if clock(contract["first_known_at"]) > clock(as_of):
            raise ValueError
        initial = number(contract["initial_margin_fraction"])
        maintenance = number(contract["maintenance_margin_fraction"])
        if not (Decimal("0") < maintenance <= initial <= Decimal("1")):
            raise ValueError
        if contract.get("margin_mode") not in ("CROSS", "ISOLATED"):
            raise ValueError
        gross = account.gross()
    except ValueError, KeyError, TypeError:
        return {"status": "UNKNOWN_LIQUIDATION", "reasons": ["INVALID_MARGIN_EVIDENCE"]}
    needed = gross * maintenance
    if account.equity <= needed:
        return {
            "status": "MARGIN_BREACH_HALT",
            "maintenance_requirement": str(needed),
            "account_equity": str(account.equity),
            "forced_exit_assumed": False,
        }
    return {
        "status": "MODELED_MARGIN_OK",
        "maintenance_requirement": str(needed),
        "initial_requirement": str(gross * initial),
        "account_equity": str(account.equity),
        "forced_exit_assumed": False,
        "synthetic_only": True,
    }
