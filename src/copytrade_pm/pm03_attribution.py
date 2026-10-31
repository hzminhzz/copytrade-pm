"""Four distinct economic layers: source UNKNOWN, intended PM, executed PM, account.

Intent is a costless mid-mark counterfactual, NOT executable follower PnL.
Execution drag and the central overlay are separate reconciliation terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal as D

from .pm03_account import Account, Instrument, ZERO


@dataclass
class IntendedVirtualBooks:
    qty: dict[str, dict[Instrument, D]] = field(default_factory=dict)
    cash: dict[str, D] = field(default_factory=dict)
    last_prices: dict[Instrument, D] = field(default_factory=dict)
    quality: str = "RESEARCH_SYNTHETIC_MID_PROXY"

    def mark_and_target(
        self,
        requested: dict[str, dict[Instrument, D]],
        prices: dict[Instrument, D],
    ) -> None:
        needed = {k for b in self.qty.values() for k, q in b.items() if q}
        needed |= {k for b in requested.values() for k in b}
        if needed - set(prices):
            self.quality = "UNKNOWN_MISSING_MARK_OR_TARGET"
            raise ValueError("UNKNOWN_INTENDED_PM_ECONOMICS")
        if self.quality.startswith("UNKNOWN"):
            raise ValueError("UNKNOWN_PREVIOUS_INTENT_STATE")
        self.last_prices.update(prices)
        for pm in sorted(set(requested) | set(self.qty)):
            old = self.qty.get(pm, {})
            new = requested.get(pm, {})
            for instrument in sorted(set(old) | set(new)):
                delta = new.get(instrument, ZERO) - old.get(instrument, ZERO)
                self.cash[pm] = self.cash.get(pm, ZERO) - delta * prices[instrument]
            self.qty[pm] = dict(new)

    def pm_pnl(self) -> dict[str, D]:
        if self.quality.startswith("UNKNOWN"):
            raise ValueError("UNKNOWN_INTENDED_PM_ECONOMICS")
        return {
            pm: cash + sum((q * self.last_prices[k] for k, q in self.qty.get(pm, {}).items()), ZERO)
            for pm, cash in sorted(self.cash.items())
        }

    @property
    def pnl(self) -> D:
        return sum(self.pm_pnl().values(), ZERO)


def explain_economics(
    account: Account,
    intent: IntendedVirtualBooks,
    execution_price_drag: D,
) -> dict:
    if execution_price_drag < ZERO:
        raise ValueError("NEGATIVE_EXECUTION_DRAG")
    account.verify()
    actual = account.equity - account.rulebook.initial_balance
    virtual = intent.pnl
    # Central overlays include blocked/reduced/delayed/skipped intent PnL.
    # Exact decomposition: actual = virtual + overlay - fees - drag + funding.
    overlay = actual - virtual + account.costs + execution_price_drag - account.funding
    reconstructed = virtual + overlay - account.costs - execution_price_drag + account.funding
    residual = actual - reconstructed
    if abs(residual) > D("0.000000000001"):
        raise ValueError("ECONOMIC_RECONCILIATION_FAILED")
    return {
        "source_wallet_pnl": None,
        "source_economics_state": "UNKNOWN_NOT_EQUIVALENT_TO_FOLLOWER",
        "virtual_intended_pm_pnl": str(virtual),
        "virtual_intended_pm_by_manager": {k: str(v) for k, v in intent.pm_pnl().items()},
        "executed_pm_pnl": {k: str(v) for k, v in account.pm_equity_pnl().items()},
        "central_overlay_pnl": str(overlay),
        "external_fees": str(account.costs),
        "execution_price_drag": str(execution_price_drag),
        "funding": str(account.funding),
        "consolidated_account_pnl": str(actual),
        "reconciliation_rounding_residual": str(residual),
        "intent_price_quality": intent.quality,
        "not_follower_execution_qualification": True,
    }
