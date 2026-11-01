"""Offline specification oracle for native broker identity and reconciliation.

No broker import, credentials, persistence, financial ledger, or order route.
The production adapter remains separately scoped and unauthorized.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .pm03_account import Instrument, clock, number


@dataclass(frozen=True)
class NativeMarket:
    native_id: str
    instrument: str
    aliases: tuple[str, ...] = ()


def native_decimal(value: str | Decimal) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValueError("LOSSLESS_NATIVE_DECIMAL_REQUIRED")
    return number(value)


class NativeRegistry:
    """One account/environment registry; display aliases are never inventory keys."""

    def __init__(self, account_id: str, markets: Iterable[NativeMarket]):
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("ACCOUNT_ID_REQUIRED")
        self.account_id = account_id
        self._markets: dict[str, str] = {}
        self._aliases: dict[str, set[str]] = {}
        instruments = set()
        for market in markets:
            instrument = Instrument.parse(market.instrument)
            if (
                instrument.venue != "propr"
                or not isinstance(market.native_id, str)
                or not market.native_id
            ):
                raise ValueError("EXPLICIT_PROPR_NATIVE_MARKET_REQUIRED")
            if market.native_id in self._markets or instrument.key in instruments:
                raise ValueError("NON_BIJECTIVE_NATIVE_MARKET_REGISTRY")
            self._markets[market.native_id] = instrument.key
            instruments.add(instrument.key)
            for alias in market.aliases:
                if not isinstance(alias, str) or not alias:
                    raise ValueError("INVALID_DISPLAY_ALIAS")
                self._aliases.setdefault(alias, set()).add(instrument.key)
        if not self._markets:
            raise ValueError("EMPTY_NATIVE_MARKET_REGISTRY")

    def native(self, native_id: str) -> str:
        if native_id not in self._markets:
            raise ValueError("UNKNOWN_NATIVE_MARKET")
        return self._markets[native_id]

    def display_lookup(self, alias: str) -> str:
        matches = self._aliases.get(alias, set())
        if len(matches) != 1:
            raise ValueError("UNKNOWN_OR_AMBIGUOUS_DISPLAY_ALIAS")
        return next(iter(matches))

    def positions(self, rows: list[dict]) -> dict[str, Decimal]:
        result = {}
        position_ids = set()
        for row in rows:
            if row.get("account_id") != self.account_id:
                raise ValueError("WRONG_BROKER_ACCOUNT")
            identity = row.get("position_id")
            if not isinstance(identity, str) or not identity or identity in position_ids:
                raise ValueError("DUPLICATE_OR_MISSING_NATIVE_POSITION_ID")
            position_ids.add(identity)
            instrument = self.native(row["native_market_id"])
            if instrument in result:
                # No ticker netting or invented hedge-side equivalence.
                raise ValueError("MULTIPLE_NATIVE_POSITIONS_REQUIRE_HEDGE_POLICY")
            result[instrument] = native_decimal(row["signed_quantity"])
        return dict(sorted(result.items()))

    def orders(self, rows: list[dict]) -> dict[str, tuple]:
        result = {}
        for row in rows:
            if row.get("account_id") != self.account_id:
                raise ValueError("WRONG_BROKER_ACCOUNT")
            identity = row.get("order_id")
            intent = row.get("client_intent_id")
            if not isinstance(identity, str) or not identity or identity in result:
                raise ValueError("DUPLICATE_OR_MISSING_NATIVE_ORDER_ID")
            if not isinstance(intent, str) or not intent:
                raise ValueError("UNRESOLVED_ORDER_INTENT")
            instrument = self.native(row["native_market_id"])
            quantity, filled = (
                native_decimal(row["signed_quantity"]),
                native_decimal(row["cumulative_filled"]),
            )
            if not quantity or filled < 0 or filled > abs(quantity):
                raise ValueError("INVALID_NATIVE_ORDER_QUANTITY")
            if row.get("status") not in {"PENDING", "PARTIAL", "CANCEL_REQUESTED", "UNKNOWN"}:
                raise ValueError("UNKNOWN_PENDING_ORDER_STATUS")
            if type(row.get("reduce_only")) is not bool:
                raise ValueError("EXPLICIT_REDUCE_ONLY_REQUIRED")
            result[identity] = (
                instrument,
                quantity,
                filled,
                row["status"],
                intent,
                row["reduce_only"],
            )
        return dict(sorted(result.items()))


def validate_clocks(
    event_at: str, received_at: str, decision_at: str, max_age_seconds: int
) -> None:
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ValueError("INVALID_OBSERVATION_FRESHNESS_POLICY")
    event, receipt, decision = map(clock, (event_at, received_at, decision_at))
    if not event <= receipt <= decision:
        raise ValueError("BROKER_CAUSAL_CLOCK_VIOLATION")
    if any((decision - t).total_seconds() > max_age_seconds for t in (event, receipt)):
        raise ValueError("STALE_BROKER_SOURCE_OR_RECEIPT")


def reconciliation_gate(
    *,
    expected_positions: dict,
    observed_positions: dict,
    expected_orders: dict,
    observed_orders: dict,
    complete: bool,
    fail_on_reconciliation_mismatch: bool,
    mode: str,
    prior_halt: bool,
) -> dict:
    """Pure veto oracle, even for shadow; clean reconciliation never clears HALT."""
    if mode not in {"offline", "shadow", "read_only"}:
        raise ValueError("EXECUTION_MODE_NOT_AUTHORIZED")
    reasons = []
    if fail_on_reconciliation_mismatch is not True:
        reasons.append("MANDATORY_RECONCILIATION_GUARD_DISABLED")
    if complete is not True:
        reasons.append("INCOMPLETE_BROKER_OBSERVATION")
    if type(prior_halt) is not bool:
        raise ValueError("EXPLICIT_PRIOR_HALT_REQUIRED")
    if prior_halt:
        reasons.append("PERSISTENT_HALT")
    if expected_positions != observed_positions:
        reasons.append("NATIVE_POSITION_MISMATCH")
    if expected_orders != observed_orders:
        reasons.append("NATIVE_ORDER_OR_CUMULATIVE_FILL_MISMATCH")
    if any(order[3] == "UNKNOWN" for order in observed_orders.values()):
        reasons.append("UNKNOWN_ORDER_OUTCOME")
    return {
        "status": "NO_TRADE" if reasons else "OFFLINE_CONTRACT_PASS",
        "reasons": reasons,
        "live_authority": False,
        "order_submission": False,
    }
