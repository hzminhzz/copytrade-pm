"""E0: complete, point-in-time wallet book -> proportional intended follower targets.

This is a research-only intent adapter, not an exchange account verifier or broker.
An external source auditor must attest complete positions, capital, account scope
and genuine local first-known receipts. Unknown evidence never becomes a flat book.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal as D
from typing import Mapping

ZERO = D("0")


def _decimal(value: object, *, positive: bool = False) -> D:
    try:
        result = D(str(value))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("INVALID_E0_NUMBER") from exc
    if not result.is_finite() or (positive and result <= ZERO):
        raise ValueError("INVALID_E0_NUMBER")
    return result


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_E0_TIME") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("E0_TIME_NOT_AWARE")
    return stamp.astimezone(UTC)


@dataclass(frozen=True)
class WalletBook:
    wallet: str
    account_scope: str
    source_event_at: str
    first_known_at: str
    source_sha256: str
    equity_usd: D
    positions: Mapping[str, D]
    complete: bool
    capital_reconciled: bool
    continuous: bool
    receipts_prospective: bool

    def validate(self, *, decision_at: str) -> None:
        if not self.wallet or not self.account_scope or len(self.source_sha256) != 64:
            raise ValueError("E0_MISSING_SOURCE_IDENTITY")
        if not all(c in "0123456789abcdef" for c in self.source_sha256):
            raise ValueError("E0_INVALID_SOURCE_SHA")
        if not (self.complete and self.capital_reconciled and self.continuous):
            raise ValueError("E0_INCOMPLETE_SOURCE_ACCOUNT")
        if not self.receipts_prospective:
            raise ValueError("E0_RETROSPECTIVE_FIRST_KNOWN_UNPROVEN")
        if not _time(self.source_event_at) <= _time(self.first_known_at) <= _time(decision_at):
            raise ValueError("E0_NONCAUSAL_SOURCE_CLOCK")
        _decimal(self.equity_usd, positive=True)
        for key, qty in self.positions.items():
            from .pm03_account import Instrument

            try:
                inst = Instrument.parse(key)
            except (TypeError, ValueError) as exc:
                raise ValueError("E0_NON_NATIVE_INSTRUMENT") from exc
            if (inst.venue != "hyperliquid" or
                    not inst.market.startswith("mainnet:perp:") or
                    len(inst.market.split(":")) != 3 or
                    not inst.market.split(":")[-1] or "/" in inst.market.split(":")[-1]):
                raise ValueError("E0_UNMAPPED_INSTRUMENT")
            _decimal(qty)


@dataclass(frozen=True)
class Replica:
    wallet: str
    source_sha256: str
    first_known_at: str
    decision_at: str
    scale: D
    source: dict[str, D]
    intended: dict[str, D]


def replicate(
    book: WalletBook, *, decision_at: str, pod_capital_usd: D,
) -> Replica:
    """Scale ALL signed legs by one factor; never filter, normalize per trade or cap."""
    book.validate(decision_at=decision_at)
    capital = _decimal(pod_capital_usd, positive=True)
    scale = capital / book.equity_usd
    source = {key: _decimal(q) for key, q in sorted(book.positions.items())}
    return Replica(
        wallet=book.wallet, source_sha256=book.source_sha256,
        first_known_at=book.first_known_at, decision_at=decision_at,
        scale=scale, source=source,
        intended={key: qty * scale for key, qty in source.items()},
    )


def fidelity(
    replica: Replica,
    *,
    approved: Mapping[str, D],
    executed: Mapping[str, D],
    marks: Mapping[str, D],
) -> dict[str, object]:
    """Measure risk-overlay loss and execution loss separately, never conceal legs.

    Values are gross-notional-weighted L1 errors / intended gross. Overhedging
    and wrong-side trades contribute to error. Metrics remain UNKNOWN on a flat
    source book or missing marks. Caller supplies actual as-of execution book.
    """
    keys = set(replica.intended) | set(approved) | set(executed)
    if set(marks) != keys:
        raise ValueError("E0_INCOMPLETE_FIDELITY_MARKS")
    prices = {k: _decimal(marks[k], positive=True) for k in keys}
    approved_q = {k: _decimal(approved.get(k, ZERO)) for k in keys}
    executed_q = {k: _decimal(executed.get(k, ZERO)) for k in keys}
    intended_q = {k: replica.intended.get(k, ZERO) for k in keys}
    gross = sum((abs(intended_q[k]) * prices[k] for k in keys), ZERO)
    overlay_error = sum(
        (abs(intended_q[k] - approved_q[k]) * prices[k] for k in keys), ZERO
    )
    execution_error = sum(
        (abs(approved_q[k] - executed_q[k]) * prices[k] for k in keys), ZERO
    )
    total_error = sum(
        (abs(intended_q[k] - executed_q[k]) * prices[k] for k in keys), ZERO
    )
    unsupported = sorted(k for k in replica.intended if replica.intended[k] and
                         not approved_q[k])
    return {
        "classification": "E0_INTENT_FIDELITY_NOT_REALIZED_PNL",
        "source_sha256": replica.source_sha256,
        "wallet": replica.wallet,
        "first_known_at": replica.first_known_at,
        "decision_at": replica.decision_at,
        "intended_gross_usd": str(gross),
        "overlay_deviation_usd": str(overlay_error),
        "execution_deviation_usd": str(execution_error),
        "tracking_deviation_usd": str(total_error),
        "overlay_deviation_fraction": str(overlay_error / gross) if gross else None,
        "execution_deviation_fraction": str(execution_error / gross) if gross else None,
        "tracking_deviation_fraction": str(total_error / gross) if gross else None,
        "unapproved_source_legs": unsupported,
        "no_source_exposure": gross == ZERO,
        "economic_outcome_verified": False,
        "broker_authorized": False,
    }
