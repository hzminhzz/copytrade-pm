"""Equity-normalized source portfolio exposure targets, independent of trade tickets.

One source book snapshot -> one vector of signed notional/equity weights.
Follower pod capital determines all target notionals together. Missed follower
executions remain actual inventory differences; the next verified source book
reconciles against actual positions, not against a past trade signal.

Pure research/intent calculation: no broker, no authority to trade, no synthetic
equity reconstruction. A caller must separately attest account scope and clocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D
from typing import Mapping

from .pm03_account import Instrument
from .pm_wallet_replica import WalletBook, _decimal

ZERO = D("0")


def _native_identity(key: str) -> None:
    try:
        inst = Instrument.parse(key)
    except (ValueError, TypeError) as exc:
        raise ValueError("EXPOSURE_INVALID_NATIVE_INSTRUMENT") from exc
    if (
        inst.venue != "hyperliquid"
        or not inst.market.startswith("mainnet:perp:")
        or len(inst.market.split(":")) != 3
        or not inst.market.split(":")[-1]
        or ":" in inst.symbol
        or ":" in inst.market.split(":")[-1]
    ):
        raise ValueError("EXPOSURE_INVALID_NATIVE_INSTRUMENT")


def _book(positions: Mapping[str, D]) -> dict[str, D]:
    if not isinstance(positions, Mapping):
        raise ValueError("EXPOSURE_INVALID_BOOK")
    out = {}
    for market, amount in positions.items():
        _native_identity(market)
        qty = _decimal(amount)
        if qty and market in out:
            raise ValueError("EXPOSURE_DUPLICATE_MARKET")
        if qty:
            out[market] = qty
    return dict(sorted(out.items()))


def _marks(
    expected: set[str], values: Mapping[str, D], *, accept_extra: bool = False
) -> dict[str, D]:
    if not isinstance(values, Mapping) or not expected.issubset(values):
        raise ValueError("EXPOSURE_MISSING_MARK")
    if not accept_extra and set(values) != expected:
        raise ValueError("EXPOSURE_MARK_SCOPE_MISMATCH")
    prices = {}
    for key in sorted(expected):
        _native_identity(key)
        prices[key] = _decimal(values[key], positive=True)
    return prices


@dataclass(frozen=True)
class ExposureIntent:
    wallet: str
    account_scope: str
    source_sha256: str
    source_equity_usd: D
    pod_capital_usd: D
    source_weights: dict[str, D]
    target_notionals_usd: dict[str, D]
    target_quantities: dict[str, D]
    source_gross_exposure_multiple: D
    source_net_exposure_multiple: D
    evidence_class: str = "EQUITY_NORMALIZED_SOURCE_INTENT_NOT_EXECUTED"


def calculate_weights(
    *,
    source_quantities: Mapping[str, D],
    source_equity_usd: D,
    source_marks: Mapping[str, D],
) -> dict[str, D]:
    """w_i = signed source quantity * native source mark / source account equity.

    A 300k long on 100k equity yields +3, regardless of trade count, margin
    setting, or whether the follower missed an earlier trade. The source
    equity must be authentic for the weights to represent the real wallet.
    """
    positions = _book(source_quantities)
    equity = _decimal(source_equity_usd, positive=True)
    # Source snapshots may retain explicitly flat (zero-quantity) markets.
    # Their optional marks cannot turn a genuinely flat leg into exposure.
    marks = _marks(set(positions), source_marks, accept_extra=True)
    return {market: qty * marks[market] / equity for market, qty in positions.items()}


def target_from_weights(
    *,
    weights: Mapping[str, D],
    pod_capital_usd: D,
    follower_marks: Mapping[str, D],
) -> tuple[dict[str, D], dict[str, D]]:
    """Target dollar exposure = signed wallet weight * allocated pod capital.

    Use follower marks for quantity conversion; source and follower prices need
    not match. Does not clip leverage, change sign, or normalize each trade.
    """
    capital = _decimal(pod_capital_usd, positive=True)
    signed = _book(weights)
    marks = _marks(set(signed), follower_marks, accept_extra=True)
    notionals = {market: weight * capital for market, weight in signed.items()}
    quantities = {market: notional / marks[market] for market, notional in notionals.items()}
    return notionals, quantities


def target_from_fixed_k(
    *,
    source_quantities: Mapping[str, D],
    k: D,
    source_marks: Mapping[str, D],
    follower_marks: Mapping[str, D],
    follower_equity_usd: D,
    max_gross_notional_usd: D,
    max_market_notional_usd: D,
    pod_loss_budget_usd: D,
) -> dict[str, object]:
    """NAV-free signed-position mirroring intent, never a live risk permit.

    Leader signed position NOTIONAL is multiplied by the preselected k.
    Follower quantity is the resulting notional divided by follower mark;
    source and follower prices may differ. No leader NAV is used. Caller must
    independently verify selected source position scope, local receipt clocks,
    follower quote freshness and account-bound policy provenance. The Guardian
    owns actual loss-stop, margin, drawdown and order authorization.
    """
    positions = _book(source_quantities)
    ratio = _decimal(k, positive=True)
    if ratio > D("10"):
        raise ValueError("FIXED_K_POLICY_OUT_OF_BOUNDS")
    equity = _decimal(follower_equity_usd, positive=True)
    gross_limit = _decimal(max_gross_notional_usd, positive=True)
    market_limit = _decimal(max_market_notional_usd, positive=True)
    loss_budget = _decimal(pod_loss_budget_usd, positive=True)
    if loss_budget > equity:
        raise ValueError("POD_LOSS_BUDGET_EXCEEDS_FOLLOWER_EQUITY")
    leader_marks = _marks(set(positions), source_marks, accept_extra=True)
    follower_prices = _marks(set(positions), follower_marks, accept_extra=True)
    notionals = {key: qty * leader_marks[key] * ratio for key, qty in positions.items()}
    quantities = {key: notional / follower_prices[key] for key, notional in notionals.items()}
    if sum((abs(v) for v in notionals.values()), ZERO) > gross_limit:
        raise ValueError("FIXED_K_GROSS_NOTIONAL_CAP")
    if any(abs(v) > market_limit for v in notionals.values()):
        raise ValueError("FIXED_K_MARKET_NOTIONAL_CAP")
    return {
        "schema": "copytrade_risk_budgeted_fixed_k_intent_v1",
        "status": "RESEARCH_INTENT_REQUIRES_GUARDIAN",
        "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
        "k": str(ratio),
        "target_quantities": {key: str(value) for key, value in quantities.items()},
        "target_notionals_usd": {key: str(value) for key, value in notionals.items()},
        "follower_equity_usd": str(equity),
        "max_gross_notional_usd": str(gross_limit),
        "max_market_notional_usd": str(market_limit),
        "pod_loss_budget_usd": str(loss_budget),
        "source_nav_required": False,
        "leader_equity_relative_fidelity_claimed": False,
        "risk_supervisor_required": True,
        "order_route": "NONE",
        "trading_authorized": False,
    }


def build_intent(
    book: WalletBook,
    *,
    decision_at: str,
    pod_capital_usd: D,
    source_marks: Mapping[str, D],
    follower_marks: Mapping[str, D],
) -> ExposureIntent:
    """Prospective E0 seam. Keep its original complete book/equity/clock gates."""
    book.validate(decision_at=decision_at)
    weights = calculate_weights(
        source_quantities=book.positions,
        source_equity_usd=book.equity_usd,
        source_marks=source_marks,
    )
    notionals, target = target_from_weights(
        weights=weights, pod_capital_usd=pod_capital_usd, follower_marks=follower_marks
    )
    return ExposureIntent(
        wallet=book.wallet,
        account_scope=book.account_scope,
        source_sha256=book.source_sha256,
        source_equity_usd=_decimal(book.equity_usd, positive=True),
        pod_capital_usd=_decimal(pod_capital_usd, positive=True),
        source_weights=weights,
        target_notionals_usd=notionals,
        target_quantities=target,
        source_gross_exposure_multiple=sum((abs(w) for w in weights.values()), ZERO),
        source_net_exposure_multiple=sum(weights.values(), ZERO),
    )


def reconcile_actual(
    plan: ExposureIntent,
    *,
    actual_quantities: Mapping[str, D],
    follower_marks: Mapping[str, D],
) -> dict[str, object]:
    """Calculate catch-up orders from *current actual positions*, not prior signals.

    A skipped follower order does not zero the source position. Only a newer
    validated complete source snapshot can legitimately remove a source leg.
    This is a diagnostic, not permission to execute the returned differences.
    """
    actual = _book(actual_quantities)
    instruments = set(plan.target_quantities) | set(actual)
    marks = _marks(instruments, follower_marks)
    target = plan.target_quantities
    differences = {
        key: target.get(key, ZERO) - actual.get(key, ZERO) for key in sorted(instruments)
    }
    missing_usd = sum((abs(differences[key]) * marks[key] for key in instruments), ZERO)
    intended_gross = sum((abs(target.get(key, ZERO) * marks[key]) for key in instruments), ZERO)
    return {
        "wallet": plan.wallet,
        "source_sha256": plan.source_sha256,
        "source_equity_usd": str(plan.source_equity_usd),
        "pod_capital_usd": str(plan.pod_capital_usd),
        "source_signed_exposure_weights": {
            key: str(value) for key, value in plan.source_weights.items()
        },
        "target_notionals_usd": {
            key: str(value) for key, value in plan.target_notionals_usd.items()
        },
        "target_quantities": {key: str(value) for key, value in sorted(target.items())},
        "actual_quantities": {key: str(value) for key, value in sorted(actual.items())},
        "catch_up_deltas": {key: str(delta) for key, delta in differences.items() if delta},
        "tracking_deviation_usd": str(missing_usd),
        "tracking_deviation_fraction": (
            str(missing_usd / intended_gross) if intended_gross else None
        ),
        "source_gross_exposure_multiple": str(plan.source_gross_exposure_multiple),
        "source_net_exposure_multiple": str(plan.source_net_exposure_multiple),
        "status": "RESEARCH_CATCH_UP_INTENT_NOT_ORDER_AUTHORITY",
        "exposure_preserved_even_when_execution_skipped": True,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
