"""PM-03: isolated, deterministic, paper-only consolidated account.

All amounts are Decimal. This module has no order, broker, network or credential API.
PM books are zero-capital virtual attribution ledgers; only the consolidated
account receives challenge starting capital. A PM's suggested risk is not a stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo

D = Decimal
ZERO = D("0")


def number(value: Any) -> Decimal:
    try:
        x = D(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_FINANCIAL_VALUE") from exc
    if not x.is_finite():
        raise ValueError("NONFINITE_FINANCIAL_VALUE")
    return x


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def clock(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(UTC)


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
        if any(not part or "/" in part for part in (self.venue, self.market, self.symbol)):
            raise ValueError("INCOMPLETE_INSTRUMENT_ID")

    @property
    def key(self) -> str:
        return "/".join((self.venue, self.market, self.symbol))

    @classmethod
    def parse(cls, key: str) -> Instrument:
        parts = key.split("/")
        if len(parts) != 3:
            raise ValueError("INVALID_INSTRUMENT_ID")
        return cls(*parts)


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
    daily_loss_rate: Decimal | None = None
    account_terms_confirmed: bool = False
    snapshot_sha: str | None = None

    def __post_init__(self) -> None:
        if not all((self.program, self.stage, self.source, self.version)):
            raise ValueError("RULEBOOK_PROVENANCE_REQUIRED")
        clock(self.observed_at)
        if self.effective_at is not None:
            clock(self.effective_at)
        ZoneInfo(self.timezone)
        if number(self.initial_balance) <= ZERO:
            raise ValueError("INVALID_INITIAL_BALANCE")
        for attr in ("profit_target", "daily_loss", "static_loss", "trailing_loss"):
            val = getattr(self, attr)
            if val is not None and number(val) <= ZERO:
                raise ValueError("INVALID_RULE")
        if self.daily_loss_rate is not None:
            if not ZERO < number(self.daily_loss_rate) < D("1") or self.daily_loss is not None:
                raise ValueError("INVALID_DAILY_LOSS_RATE")
        if self.trailing_cap is not None and self.trailing_loss is None:
            raise ValueError("CAP_WITHOUT_TRAILING")
        if self.max_gross_leverage is not None and number(self.max_gross_leverage) <= ZERO:
            raise ValueError("INVALID_LEVERAGE")
        if self.snapshot_sha and len(self.snapshot_sha) != 64:
            raise ValueError("INVALID_SOURCE_SHA")

    def daily_allowance(self, balance: Decimal) -> Decimal | None:
        if self.daily_loss_rate is not None:
            return balance * self.daily_loss_rate
        return self.daily_loss

    def to_dict(self) -> dict:
        return {
            "program": self.program,
            "stage": self.stage,
            "source": self.source,
            "observed_at": self.observed_at,
            "effective_at": self.effective_at,
            "version": self.version,
            "timezone": self.timezone,
            **{
                k: (str(getattr(self, k)) if getattr(self, k) is not None else None)
                for k in (
                    "initial_balance",
                    "profit_target",
                    "daily_loss",
                    "static_loss",
                    "trailing_loss",
                    "trailing_cap",
                    "max_gross_leverage",
                    "daily_loss_rate",
                )
            },
            "confirmed": self.confirmed,
            "account_terms_confirmed": self.account_terms_confirmed,
            "snapshot_sha": self.snapshot_sha,
            "permitted": [x.key for x in self.permitted],
        }

    @classmethod
    def from_dict(cls, row: dict) -> Rulebook:
        obj = dict(row)
        for key in (
            "initial_balance",
            "profit_target",
            "daily_loss",
            "static_loss",
            "trailing_loss",
            "trailing_cap",
            "max_gross_leverage",
            "daily_loss_rate",
        ):
            if obj.get(key) is not None:
                obj[key] = number(obj[key])
        obj["permitted"] = tuple(Instrument.parse(x) for x in obj.get("permitted", []))
        return cls(**obj)

    @property
    def sha(self) -> str:
        return digest(self.to_dict())


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
    entries: dict[Instrument, Decimal] = field(default_factory=dict)
    pm_cash: dict[str, Decimal] = field(default_factory=dict)
    pm_costs: dict[str, Decimal] = field(default_factory=dict)
    pm_funding: dict[str, Decimal] = field(default_factory=dict)
    breached: bool = False
    stage_passed: bool = False
    last_mark_at: str | None = None
    risk_reasons: tuple[str, ...] = ()
    # Optional PM-04 research metadata, replayed by the SAME PM-03 account ledger.
    # Absent for legacy PM-03 runs so their existing post-state hashes remain stable.
    pm04_state: dict[str, Any] = field(default_factory=dict)

    # Replay policy is event-local, never part of historical financial snapshots.
    _risk_semantics_version: int = field(default=2, repr=False, compare=False)

    def _prepare_risk_semantics(self, version: int) -> None:
        if type(version) is not int or version not in (1, 2):
            raise ValueError("UNSUPPORTED_RISK_SEMANTICS")
        self._risk_semantics_version = version
        # A historical diagnostic may have overwritten the enum while retaining
        # its halt reason. New events must not inherit that unsafe permission.
        if version == 2 and (self.halt_reason is not None or self.breached):
            self.risk = RiskState.HALT

    def block_readiness(self, reasons: tuple[str, ...] | list[str] | None = None) -> None:
        """Record operational failure without clearing the financial restriction.

        Version 1 is used only while verifying immutable archived event hashes.
        Newly admitted events always use version 2.
        """
        if self._risk_semantics_version == 1 or self.risk != RiskState.HALT:
            self.risk = RiskState.RED
        if reasons is not None:
            self.risk_reasons = tuple(reasons)

    @classmethod
    def start(cls, rulebook: Rulebook, as_of: str) -> Account:
        local_day = clock(as_of).astimezone(ZoneInfo(rulebook.timezone)).date().isoformat()
        cash = rulebook.initial_balance
        return cls(rulebook, cash, cash, cash, cash, local_day, last_mark_at=as_of)

    @property
    def balance(self) -> Decimal:
        """Closed PnL only; never current unrealized PnL."""
        return self.rulebook.initial_balance + self.realized_pnl - self.costs + self.funding

    @property
    def unrealized_pnl(self) -> Decimal:
        return sum(
            (q * (self.marks[k] - self.entries[k]) for k, q in self.quantities.items() if q),
            ZERO,
        )

    def floor(self) -> tuple[Decimal | None, dict[str, Decimal]]:
        r = self.rulebook
        floors: dict[str, Decimal] = {}
        allowance = r.daily_allowance(self.daily_start_balance)
        if allowance is not None:
            floors["daily"] = self.daily_start_balance - allowance
        if r.static_loss is not None:
            floors["static"] = r.initial_balance - r.static_loss
        if r.trailing_loss is not None:
            value = self.high_water - r.trailing_loss
            if r.trailing_cap is not None:
                value = min(value, r.trailing_cap)
            floors["trailing"] = value
        return (max(floors.values()) if floors else None), floors

    def _check_breach(self) -> None:
        floor, _ = self.floor()
        if floor is not None and self.equity <= floor:
            self.breached = True
            self.risk = RiskState.HALT
            self.halt_reason = "CONTRACTUAL_EQUITY_FLOOR"
        if not self.breached and self.rulebook.profit_target is not None:
            self.stage_passed = self.stage_passed or self.equity >= (
                self.rulebook.initial_balance + self.rulebook.profit_target
            )

    def _revalue(self) -> None:
        if set(self.quantities) - set(self.marks):
            raise ValueError("MISSING_MARK")
        self.equity = self.cash + sum((q * self.marks[k] for k, q in self.quantities.items()), ZERO)
        self.high_water = max(self.high_water, self.equity)
        self._check_breach()

    def mark(self, prices: dict[Instrument, Decimal], as_of: str) -> None:
        t = clock(as_of)
        if self.last_mark_at is not None and t < clock(self.last_mark_at):
            raise ValueError("BACKDATED_MARK")
        day = t.astimezone(ZoneInfo(self.rulebook.timezone)).date().isoformat()
        tracked = set(self.quantities) | {
            k for book in self.pm_quantities.values() for k, q in book.items() if q
        }
        if tracked - set(prices):
            raise ValueError("MISSING_MARK")
        for key, price in prices.items():
            if number(price) <= ZERO:
                raise ValueError("INVALID_MARK")
        # First observed mark on a new session must use realized balance for
        # its daily floor, never mark-to-market equity or a future day-end figure.
        if day != self.daily_key:
            self.daily_start_balance = self.balance
            self.daily_key = day
        self.marks.update(prices)
        self.last_mark_at = as_of
        self._revalue()

    def gross(self) -> Decimal:
        if set(self.quantities) - set(self.marks):
            raise ValueError("UNKNOWN_MARK")
        return sum((abs(q * self.marks[k]) for k, q in self.quantities.items()), ZERO)

    def external_targets(
        self, proposed: dict[str, dict[Instrument, Decimal]]
    ) -> dict[Instrument, Decimal]:
        keys = {k for book in proposed.values() for k in book}
        return {
            k: sum((number(book.get(k, ZERO)) for book in proposed.values()), ZERO)
            for k in sorted(keys)
        }

    def _update_basis(self, instrument: Instrument, delta: Decimal, price: Decimal) -> None:
        old = self.quantities.get(instrument, ZERO)
        new = old + delta
        entry = self.entries.get(instrument, price)
        if old and old * delta < ZERO:
            close_qty = min(abs(old), abs(delta))
            self.realized_pnl += close_qty * (price - entry) * (1 if old > ZERO else -1)
        if not new:
            self.entries.pop(instrument, None)
        elif not old or old * new < ZERO:
            self.entries[instrument] = price
        elif old * delta > ZERO:
            self.entries[instrument] = (abs(old) * entry + abs(delta) * price) / abs(new)
        self.quantities[instrument] = new

    def _pm_trade(
        self, pm: str, instrument: Instrument, delta: Decimal, price: Decimal, fee: Decimal = ZERO
    ) -> None:
        if not pm:
            raise ValueError("EMPTY_MANAGER_ID")
        book = self.pm_quantities.setdefault(pm, {})
        book[instrument] = book.get(instrument, ZERO) + delta
        self.pm_cash[pm] = self.pm_cash.get(pm, ZERO) - delta * price - fee
        self.pm_costs[pm] = self.pm_costs.get(pm, ZERO) + fee

    def internal_cross(
        self, instrument: Instrument, buy: str, sell: str, qty: Decimal, mark: Decimal
    ) -> None:
        if self.breached or qty <= ZERO or mark <= ZERO or buy == sell:
            raise ValueError("INVALID_INTERNAL_CROSS")
        if instrument in self.marks and self.marks[instrument] != mark:
            raise ValueError("EXPLICIT_MARK_REQUIRED_BEFORE_INTERNAL_CROSS")
        self.marks[instrument] = mark
        self._pm_trade(buy, instrument, qty, mark)
        self._pm_trade(sell, instrument, -qty, mark)
        self.revision += 1
        self.verify()

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
        if self.breached:
            raise ValueError("CONTRACTUAL_BREACH_PERMANENT")
        prior = self.quantities.get(instrument, ZERO)
        if self.stage_passed and abs(prior + delta) > abs(prior):
            raise ValueError("STAGE_PASSED_NO_INCREASE")
        if self.risk in (RiskState.RED, RiskState.HALT) and abs(prior + delta) > abs(prior):
            raise ValueError("HALT_NO_INCREASE")
        if not accepted:
            return
        if not allocated or number(price) <= ZERO or number(fee) < ZERO:
            raise ValueError("INVALID_FILL_OR_ALLOCATION")
        if sum((number(x) for x in allocated.values()), ZERO) != delta or not delta:
            raise ValueError("INVALID_FILL_OR_ALLOCATION")
        if any(number(x) * delta < ZERO for x in allocated.values()):
            raise ValueError("EXTERNAL_FILL_MIXED_SIGN_ALLOCATION")
        if instrument not in self.marks:
            self.marks[instrument] = price
        self._update_basis(instrument, delta, price)
        gross = sum((abs(x) for x in allocated.values()), ZERO)
        fees_left = fee
        keys = sorted(allocated)
        for i, pm in enumerate(keys):
            portion = (
                fees_left
                if i == len(keys) - 1
                else (fee * abs(allocated[pm]) / gross).quantize(D("0.000000000001"))
            )
            fees_left -= portion
            self._pm_trade(pm, instrument, allocated[pm], price, portion)
        # Rebuild consolidated cash from the exact PM cash legs. This avoids
        # Decimal arithmetic-order drift when the modeled impact price repeats.
        self.cash = self.rulebook.initial_balance + sum(self.pm_cash.values(), ZERO)
        self.costs = sum(self.pm_costs.values(), ZERO)
        self.revision += 1
        self._revalue()
        self.verify()

    def post_funding(self, amount: Decimal, allocated: dict[str, Decimal]) -> None:
        if self.breached:
            raise ValueError("CONTRACTUAL_BREACH_PERMANENT")
        if sum((number(v) for v in allocated.values()), ZERO) != amount:
            raise ValueError("FUNDING_ATTRIBUTION_MISMATCH")
        for pm, value in allocated.items():
            self.pm_cash[pm] = self.pm_cash.get(pm, ZERO) + value
            self.pm_funding[pm] = self.pm_funding.get(pm, ZERO) + value
        self.cash += amount
        self.funding += amount
        self.revision += 1
        self._revalue()
        self.verify()

    def pm_equity_pnl(self) -> dict[str, Decimal]:
        return {
            pm: cash
            + sum((q * self.marks[k] for k, q in self.pm_quantities.get(pm, {}).items()), ZERO)
            for pm, cash in sorted(self.pm_cash.items())
        }

    def verify(self) -> None:
        # Explicit checks remain active with python -O (unlike assert).
        for k in set(self.quantities) | {k for b in self.pm_quantities.values() for k in b}:
            if sum(
                (b.get(k, ZERO) for b in self.pm_quantities.values()), ZERO
            ) != self.quantities.get(k, ZERO):
                raise ValueError("PM_POSITION_RECONCILIATION")
        if self.equity != self.cash + sum(
            (q * self.marks[k] for k, q in self.quantities.items()), ZERO
        ):
            raise ValueError("ACCOUNT_EQUITY_RECONCILIATION")
        # Weighted-average cost basis can leave sub-picodollar Decimal rounding.
        if abs(self.equity - self.balance - self.unrealized_pnl) > D("0.000000000001"):
            raise ValueError("ACCOUNT_REALIZED_UNREALIZED_RECONCILIATION")
        if abs(sum(self.pm_cash.values(), ZERO) - (self.cash - self.rulebook.initial_balance)) > D(
            "0.000000000001"
        ):
            raise ValueError("PM_CASH_RECONCILIATION")
        if abs(
            sum(self.pm_equity_pnl().values(), ZERO) - (self.equity - self.rulebook.initial_balance)
        ) > D("0.000000000001"):
            raise ValueError("PM_PNL_RECONCILIATION")
        if sum(self.pm_costs.values(), ZERO) != self.costs:
            raise ValueError("PM_COST_RECONCILIATION")
        if sum(self.pm_funding.values(), ZERO) != self.funding:
            raise ValueError("PM_FUNDING_RECONCILIATION")

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
        if self.risk == RiskState.HALT or self.breached:
            reasons.append("HALT_LATCHED")
        if not trusted or not self.rulebook.confirmed:
            reasons.append("UNVERIFIED_INPUT_OR_RULEBOOK")
        if not market_known:
            reasons.append("UNKNOWN_MARKET_OR_ACCOUNT")
        targets = self.external_targets(proposed)
        if targets and not self.rulebook.permitted:
            reasons.append("UNKNOWN_PERMITTED_MARKETS")
        elif any(k not in self.rulebook.permitted for k in targets):
            reasons.append("UNSUPPORTED_INSTRUMENT")
        if any(k not in prices or number(prices[k]) <= ZERO for k in targets):
            reasons.append("MISSING_MARK")
        floor, _ = self.floor()
        if floor is None:
            reasons.append("UNKNOWN_CONTRACTUAL_FLOOR")
        elif self.equity - floor <= number(stressed_loss) + number(reserve):
            reasons.append("INSUFFICIENT_STRESS_HEADROOM")
        if self.equity <= ZERO:
            reasons.append("NONPOSITIVE_EQUITY")
        if not reasons and self.rulebook.max_gross_leverage is not None:
            gross = sum((abs(q * prices[k]) for k, q in targets.items()), ZERO)
            if gross > self.equity * self.rulebook.max_gross_leverage:
                reasons.append("GROSS_LEVERAGE_EXCEEDED")
        if reasons:
            if "INSUFFICIENT_STRESS_HEADROOM" in reasons or self.breached:
                self.risk = RiskState.HALT
                self.halt_reason = "RISK_HEADROOM_OR_BREACH"
            elif self.risk not in (RiskState.HALT,):
                self.risk = RiskState.RED
            self.risk_reasons = tuple(sorted(reasons))
        return {
            "state": self.risk.value,
            "allowed": not reasons,
            "reasons": sorted(reasons),
            "targets": {k.key: str(v) for k, v in targets.items()} if not reasons else {},
            "rulebook_sha": self.rulebook.sha,
        }

    def manual_reset(self, *, authorization: str, as_of: str) -> None:
        if not authorization or not self.rulebook.confirmed:
            raise ValueError("RESET_NOT_AUTHORIZED")
        floor, _ = self.floor()
        if self.breached or (floor is not None and self.equity <= floor):
            raise ValueError("CONTRACTUAL_BREACH_PERSISTS")
        if self.last_mark_at and clock(as_of) < clock(self.last_mark_at):
            raise ValueError("BACKDATED_RESET")
        self.risk = RiskState.GREEN
        self.halt_reason = None
        self.risk_reasons = ()
        self.revision += 1

    def advance_stage(self, next_rulebook: Rulebook, *, as_of: str) -> None:
        clock(as_of)
        if self.breached or not self.stage_passed:
            raise ValueError("STAGE_NOT_PASSED")
        if next_rulebook.program != self.rulebook.program or (
            next_rulebook.initial_balance != self.rulebook.initial_balance
        ):
            raise ValueError("STAGE_PROGRAM_MISMATCH")
        self.rulebook = next_rulebook
        self.stage_passed = False
        self.revision += 1
        self._check_breach()

    def snapshot(self) -> dict[str, Any]:
        def amounts(book: dict[Instrument, Decimal]) -> dict[str, str]:
            return {k.key: str(v) for k, v in sorted(book.items())}

        snap = {
            "schema": "pm03_account_v2",
            "rulebook_sha": self.rulebook.sha,
            "cash": str(self.cash),
            "equity": str(self.equity),
            "balance": str(self.balance),
            "high_water": str(self.high_water),
            "daily_start_balance": str(self.daily_start_balance),
            "daily_key": self.daily_key,
            "quantities": amounts(self.quantities),
            "marks": amounts(self.marks),
            "entries": amounts(self.entries),
            "pm_quantities": {pm: amounts(q) for pm, q in sorted(self.pm_quantities.items())},
            **{k: str(getattr(self, k)) for k in ("costs", "funding", "realized_pnl")},
            **{
                k: {pm: str(val) for pm, val in sorted(getattr(self, k).items())}
                for k in ("pm_cash", "pm_costs", "pm_funding")
            },
            "risk": self.risk.value,
            "halt_reason": self.halt_reason,
            "breached": self.breached,
            "stage_passed": self.stage_passed,
            "revision": self.revision,
            "last_mark_at": self.last_mark_at,
            "risk_reasons": list(self.risk_reasons),
        }
        if self.pm04_state:
            snap["pm04"] = self.pm04_state
        return snap

    @classmethod
    def from_snapshot(cls, rulebook: Rulebook, snap: dict) -> Account:
        if snap.get("schema") != "pm03_account_v2" or snap.get("rulebook_sha") != rulebook.sha:
            raise ValueError("SNAPSHOT_SCHEMA_OR_RULEBOOK_MISMATCH")

        def amounts(book: dict[str, str]) -> dict[Instrument, Decimal]:
            return {Instrument.parse(k): number(v) for k, v in book.items()}

        obj = cls(
            rulebook=rulebook,
            cash=number(snap["cash"]),
            equity=number(snap["equity"]),
            high_water=number(snap["high_water"]),
            daily_start_balance=number(snap["daily_start_balance"]),
            daily_key=snap["daily_key"],
            quantities=amounts(snap["quantities"]),
            marks=amounts(snap["marks"]),
            pm_quantities={pm: amounts(v) for pm, v in snap["pm_quantities"].items()},
            entries=amounts(snap["entries"]),
            **{k: number(snap[k]) for k in ("costs", "funding", "realized_pnl")},
            **{
                k: {pm: number(v) for pm, v in snap[k].items()}
                for k in ("pm_cash", "pm_costs", "pm_funding")
            },
            risk=RiskState(snap["risk"]),
            halt_reason=snap["halt_reason"],
            breached=snap["breached"],
            stage_passed=snap["stage_passed"],
            revision=snap["revision"],
            last_mark_at=snap["last_mark_at"],
            risk_reasons=tuple(snap["risk_reasons"]),
            pm04_state=snap.get("pm04", {}),
        )
        obj.verify()
        if str(obj.balance) != snap["balance"]:
            raise ValueError("SNAPSHOT_BALANCE_MISMATCH")
        return obj
