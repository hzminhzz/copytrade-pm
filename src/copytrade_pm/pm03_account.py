"""PM-03 deterministic, research-only portfolio accounting and risk supervision.

All quantities are synthetic shadow targets. No broker imports or order methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo

D = Decimal
ZERO = D("0")


def number(value: Any) -> Decimal:
    x = D(str(value))
    if not x.is_finite():
        raise ValueError("NONFINITE_FINANCIAL_VALUE")
    return x


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def clock(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt


class RiskState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    HALT = "HALT"


@dataclass(frozen=True, order=True)
class Instrument:
    venue: str
    market: str
    symbol: str

    def __post_init__(self) -> None:
        if not all((self.venue, self.market, self.symbol)):
            raise ValueError("INCOMPLETE_INSTRUMENT_ID")


@dataclass(frozen=True)
class Rulebook:
    program: str
    stage: str
    source: str
    observed_at: str
    version: str
    timezone: str
    initial_balance: Decimal
    profit_target: Decimal | None
    daily_loss: Decimal | None
    static_loss: Decimal | None
    trailing_loss: Decimal | None
    trailing_cap: Decimal | None = None
    confirmed: bool = False
    effective_at: str | None = None
    permitted: tuple[Instrument, ...] = ()
    max_gross_leverage: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.version or not self.program or not self.stage:
            raise ValueError("RULEBOOK_PROVENANCE_REQUIRED")
        clock(self.observed_at)
        if self.effective_at:
            clock(self.effective_at)
        ZoneInfo(self.timezone)
        if self.initial_balance <= ZERO:
            raise ValueError("INVALID_INITIAL_BALANCE")
        for key in ("profit_target", "daily_loss", "static_loss", "trailing_loss"):
            val = getattr(self, key)
            if val is not None and val <= ZERO:
                raise ValueError("INVALID_RULE")
        if self.trailing_cap is not None and self.trailing_loss is None:
            raise ValueError("CAP_WITHOUT_TRAILING")
        if self.max_gross_leverage is not None and self.max_gross_leverage <= ZERO:
            raise ValueError("INVALID_LEVERAGE")

    @property
    def sha(self) -> str:
        return digest(
            {
                "program": self.program,
                "stage": self.stage,
                "source": self.source,
                "observed_at": self.observed_at,
                "effective_at": self.effective_at,
                "version": self.version,
                "timezone": self.timezone,
                "initial_balance": str(self.initial_balance),
                **{
                    k: str(getattr(self, k)) if getattr(self, k) is not None else None
                    for k in (
                        "profit_target",
                        "daily_loss",
                        "static_loss",
                        "trailing_loss",
                        "trailing_cap",
                        "max_gross_leverage",
                    )
                },
                "confirmed": self.confirmed,
                "permitted": [list((i.venue, i.market, i.symbol)) for i in self.permitted],
            }
        )


@dataclass
class Account:
    rulebook: Rulebook
    cash: Decimal
    equity: Decimal
    high_water: Decimal
    daily_start_balance: Decimal
    daily_key: str
    quantities: dict[Instrument, Decimal] = field(default_factory=dict)
    marks: dict[Instrument, Decimal] = field(default_factory=dict)
    pm_quantities: dict[str, dict[Instrument, Decimal]] = field(default_factory=dict)
    costs: Decimal = ZERO
    funding: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    risk: RiskState = RiskState.GREEN
    halt_reason: str | None = None
    revision: int = 0

    @classmethod
    def start(cls, rulebook: Rulebook, as_of: str) -> Account:
        t = clock(as_of)
        local_day = t.astimezone(ZoneInfo(rulebook.timezone)).date().isoformat()
        cash = rulebook.initial_balance
        return cls(rulebook, cash, cash, cash, cash, local_day)

    def floor(self) -> tuple[Decimal | None, dict[str, Decimal]]:
        r = self.rulebook
        floors: dict[str, Decimal] = {}
        if r.daily_loss is not None:
            floors["daily"] = self.daily_start_balance - r.daily_loss
        if r.static_loss is not None:
            floors["static"] = r.initial_balance - r.static_loss
        if r.trailing_loss is not None:
            value = self.high_water - r.trailing_loss
            if r.trailing_cap is not None:
                value = min(value, r.trailing_cap)
            floors["trailing"] = value
        return (max(floors.values()) if floors else None), floors

    def mark(self, prices: dict[Instrument, Decimal], as_of: str) -> None:
        day = clock(as_of).astimezone(ZoneInfo(self.rulebook.timezone)).date().isoformat()
        if day < self.daily_key:
            raise ValueError("BACKDATED_MARK")
        if set(self.quantities) - set(prices):
            raise ValueError("MISSING_MARK")
        for instrument, price in prices.items():
            if price <= ZERO:
                raise ValueError("INVALID_MARK")
            self.marks[instrument] = price
        previous_equity = self.equity
        self.equity = self.cash + sum((q * self.marks[k] for k, q in self.quantities.items()), ZERO)
        # Reset from prior observed equity; the first new-session mark cannot
        # retrospectively set its own drawdown baseline.
        if day != self.daily_key:
            self.daily_start_balance = previous_equity
            self.daily_key = day
        self.high_water = max(self.high_water, self.equity)
        floor, _ = self.floor()
        if floor is not None and self.equity <= floor:
            self.risk = RiskState.HALT
            self.halt_reason = "CONTRACTUAL_EQUITY_FLOOR"

    def gross(self) -> Decimal:
        return sum((abs(q * self.marks[k]) for k, q in self.quantities.items()), ZERO)

    def external_targets(
        self, proposed: dict[str, dict[Instrument, Decimal]]
    ) -> dict[Instrument, Decimal]:
        keys = {k for book in proposed.values() for k in book}
        return {
            k: sum((book.get(k, ZERO) for book in proposed.values()), ZERO) for k in sorted(keys)
        }

    def evaluate(
        self,
        proposed: dict[str, dict[Instrument, Decimal]],
        prices: dict[Instrument, Decimal],
        *,
        trusted: bool,
        market_known: bool,
        stressed_loss: Decimal = ZERO,
        reserve: Decimal = ZERO,
    ) -> dict[str, Any]:
        reasons = []
        if self.risk == RiskState.HALT:
            reasons.append("HALT_LATCHED")
        if not trusted or not self.rulebook.confirmed:
            reasons.append("UNVERIFIED_INPUT_OR_RULEBOOK")
        if not market_known:
            reasons.append("UNKNOWN_MARKET_OR_ACCOUNT")
        targets = self.external_targets(proposed)
        if self.rulebook.permitted and any(k not in self.rulebook.permitted for k in targets):
            reasons.append("UNSUPPORTED_INSTRUMENT")
        if any(k not in prices or prices[k] <= ZERO for k in targets):
            reasons.append("MISSING_MARK")
        floor, _ = self.floor()
        if floor is None:
            reasons.append("UNKNOWN_CONTRACTUAL_FLOOR")
        elif self.equity - floor <= stressed_loss + reserve:
            reasons.append("INSUFFICIENT_STRESS_HEADROOM")
        if self.equity <= ZERO:
            reasons.append("NONPOSITIVE_EQUITY")
        if not reasons and self.rulebook.max_gross_leverage is not None:
            gross = sum((abs(q * prices[k]) for k, q in targets.items()), ZERO)
            if gross > self.equity * self.rulebook.max_gross_leverage:
                reasons.append("GROSS_LEVERAGE_EXCEEDED")
        if reasons:
            self.risk = (
                RiskState.HALT
                if "INSUFFICIENT_STRESS_HEADROOM" in reasons
                else max(self.risk, RiskState.RED, key=lambda s: list(RiskState).index(s))
            )
        return {
            "state": self.risk.value,
            "allowed": not reasons,
            "reasons": sorted(reasons),
            "targets": {"/".join((k.venue, k.market, k.symbol)): str(v) for k, v in targets.items()}
            if not reasons
            else {},
            "rulebook_sha": self.rulebook.sha,
        }

    def simulate_fill(
        self,
        instrument: Instrument,
        delta: Decimal,
        price: Decimal,
        fee: Decimal,
        *,
        accepted: bool,
        allocated: dict[str, Decimal],
    ) -> None:
        if self.risk == RiskState.HALT and self.quantities.get(instrument, ZERO) * delta >= ZERO:
            raise ValueError("HALT_NO_INCREASE")
        if not accepted:
            return
        if price <= ZERO or fee < ZERO or sum(allocated.values(), ZERO) != delta:
            raise ValueError("INVALID_FILL_OR_ALLOCATION")
        for pm, share in allocated.items():
            book = self.pm_quantities.setdefault(pm, {})
            book[instrument] = book.get(instrument, ZERO) + share
        self.quantities[instrument] = self.quantities.get(instrument, ZERO) + delta
        self.cash -= delta * price + fee
        self.costs += fee
        self.marks[instrument] = price
        self.equity = self.cash + sum((q * self.marks[k] for k, q in self.quantities.items()), ZERO)
        self.revision += 1

    def verify(self) -> None:
        for k in self.quantities:
            assert (
                sum((b.get(k, ZERO) for b in self.pm_quantities.values()), ZERO)
                == self.quantities[k]
            )
        assert self.equity == self.cash + sum(
            (q * self.marks[k] for k, q in self.quantities.items()), ZERO
        )

    def manual_reset(self, *, authorization: str, as_of: str) -> None:
        clock(as_of)
        floor, _ = self.floor()
        if not authorization or self.rulebook.confirmed is False:
            raise ValueError("RESET_NOT_AUTHORIZED")
        if floor is not None and self.equity <= floor:
            raise ValueError("CONTRACTUAL_BREACH_PERSISTS")
        self.risk = RiskState.GREEN
        self.halt_reason = None
