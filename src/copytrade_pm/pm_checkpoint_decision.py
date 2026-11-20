"""Kernel decision inputs for the PM03 paper checkpoint consumer.

The paper shell owns evidence: it resolves verified native markets, quotes, the
signed policy and the paper ledger.  ``copytrade_kernel`` owns the decision: the
whole-book stress sizing, the native-quantity targets, the V2 net execution
projection and the net order intents.  This module is the only place that
translates between the two, so the paper shell never re-derives financial math.

Two invariants hold here:

* every kernel input is either a signed field of the checkpoint paper policy, a
  verified native market fact, or the paper account's own ledger;
* inputs the paper shell has no evidence for are declared as *unmodeled* (zero
  funding, zero venue liquidation) instead of being invented, and the shared
  kernel's declared floors (30 bps execution shortfall, 5% hedge fidelity) are
  named constants rather than a second policy.

Q15 opening memory (``checkpoint_decision_q15_v1``) is persisted per owner and
instrument in the PM04 state so a replay reconstructs it without rebuilding the
opportunity history.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from copytrade_kernel import (
    AccountState,
    CheckpointMs,
    DecisionInputs,
    DecisionMs,
    ExecutionDecision,
    FrozenObject,
    MarketContext,
    NativeInstrument,
    OpeningMissed,
    RiskPolicy,
    VenueCapability,
)

from .pm03_account import Account, Instrument, RiskState, ZERO, clock, digest, number
from .pm03_execution import MarketObservation
from .pm03_risk import RiskPolicy as PaperRiskPolicy
from .pm_forward_ccxt_market import NativeMarket

#: Forward decision semantics persisted with every new review.
DECISION_VERSION = "checkpoint_decision_q15_v1"

#: PM04 state keys owned by the kernel decision path.
MEMORY_FIELD = "entry_memory"
SEMANTICS_FIELD = "decision_version"

#: The paper venue is a modeled-only session; it never routes an order.
SOURCE_MODE = "PAPER_VERIFIED_L2"

#: Shared-kernel floors.  ``size_book`` refuses a weaker declared shortfall or a
#: wider hedge-fidelity tolerance; PM03's own fill model keeps the signed costs.
KERNEL_SHORTFALL_BPS = Decimal("30")
KERNEL_HEDGE_TOLERANCE = Decimal("0.05")

#: 1, 0.75, 0.5, 0.25: the paper policy's declared reduction ladder.
KERNEL_SCALE_STEPS = 4

#: ``copytrade_kernel.risk.validate_quotes`` accepts at most this quote age.
KERNEL_QUOTE_MAX_AGE_MS = 5_000

#: Unmodeled venue costs: PM03 has no signed funding/liquidation evidence.
UNMODELED_RATE = Decimal("0")


class KernelNoTrade(ValueError):
    """The shared kernel refused the checkpoint; the shell must not trade."""


@dataclass(frozen=True)
class Decision:
    """The kernel's decision in paper-shell terms."""

    scale: Decimal
    state: RiskState
    targets: dict[str, dict[Instrument, Decimal]]
    net_intents: tuple[dict[str, Any], ...]
    risk: dict[str, Any]
    reasons: tuple[str, ...]


def _ms(stamp: str) -> int:
    return int(clock(stamp).timestamp() * 1000)


# --------------------------------------------------------------------------- Q15


def _read_memory(state: dict[str, Any], owner: str) -> dict[str, dict[str, Any]]:
    books = state.get(MEMORY_FIELD, {})
    if not isinstance(books, dict):
        raise ValueError("CHECKPOINT_ENTRY_MEMORY")
    book = books.get(owner, {})
    if not isinstance(book, dict):
        raise ValueError("CHECKPOINT_ENTRY_MEMORY")
    return book


def memory(state: dict[str, Any], owner: str) -> tuple[tuple[NativeInstrument, OpeningMissed], ...]:
    """Persisted owner/instrument opening memory as immutable kernel records."""
    parsed: list[tuple[NativeInstrument, OpeningMissed]] = []
    for key, row in sorted(_read_memory(state, owner).items()):
        if not isinstance(row, dict) or set(row) != {"missed_at", "qty_at_miss"}:
            raise ValueError("CHECKPOINT_ENTRY_MEMORY")
        missed_at = row["missed_at"]
        if type(missed_at) is not int or missed_at < 0:
            raise ValueError("CHECKPOINT_ENTRY_MEMORY")
        quantity = number(row["qty_at_miss"])
        if not quantity:
            raise ValueError("CHECKPOINT_ENTRY_MEMORY")
        parsed.append((NativeInstrument(key), OpeningMissed(CheckpointMs(missed_at), quantity)))
    return tuple(parsed)


def record_miss(
    state: dict[str, Any],
    owner: str,
    instrument: str,
    *,
    checkpoint_ms: int,
    quantity: Decimal,
) -> None:
    """Retain the signed quantity at the last missed eligible opening.

    A same-sign decrease or a rebound at or below the retained quantity never
    replaces it: only a genuine increase or a flip is a new miss.  This is the
    Guardian reconstruction rule, applied on the paper consume path.
    """
    if type(checkpoint_ms) is not int or checkpoint_ms < 0:
        raise ValueError("CHECKPOINT_ENTRY_MEMORY")
    value = number(quantity)
    if not value:
        raise ValueError("CHECKPOINT_ENTRY_MEMORY")
    book = _read_memory(state, owner)
    previous = book.get(instrument)
    if previous is not None:
        retained = OpeningMissed(previous["missed_at"], number(previous["qty_at_miss"]))
        if not retained.allows_retry(value):
            return
    books = state.setdefault(MEMORY_FIELD, {})
    book = books.setdefault(owner, {})
    book[instrument] = {"missed_at": checkpoint_ms, "qty_at_miss": str(value)}


def clear_miss(state: dict[str, Any], owner: str, instrument: str) -> None:
    """Clear a miss only when owner attribution proves the entry."""
    book = _read_memory(state, owner)
    if book.pop(instrument, None) is not None:
        books = state[MEMORY_FIELD]
        if not book:
            books.pop(owner, None)


# ------------------------------------------------------------------ normalisation


def _leverage(account: Account, policy: PaperRiskPolicy) -> Decimal:
    contract = account.rulebook.max_gross_leverage
    return (
        min(policy.max_gross_leverage, contract)
        if contract is not None
        else policy.max_gross_leverage
    )


def _scenarios(event: Mapping[str, Any], keys: set[str]) -> list[dict[str, str]]:
    rows = event["policy"]["shocks"]
    scenarios = []
    for row in rows:
        missing = keys - set(row)
        if missing:
            raise ValueError("CHECKPOINT_STRESS_COVERAGE")
        scenarios.append({key: str(number(row[key])) for key in sorted(keys)})
    if not scenarios:
        raise ValueError("CHECKPOINT_STRESS_COVERAGE")
    return scenarios


def _market_spec(
    key: str,
    native: NativeMarket,
    observation: MarketObservation,
    policy: PaperRiskPolicy,
    costs_rate: Decimal,
    leverage: Decimal,
    now_ms: int,
) -> dict[str, Any]:
    """Verified native lot contract plus declared paper-only risk terms."""
    step = number(native.amount_step)
    if step <= ZERO:
        raise ValueError("NATIVE_MARKET_INVALID")
    initial = ONE / leverage if leverage > ZERO else ONE
    displayed = min(number(observation.bid_size), number(observation.ask_size))
    liquidity = displayed * number(observation.mark)
    if liquidity <= ZERO:
        raise ValueError("NATIVE_MARKET_INVALID")
    return {
        "symbol": key,
        "instrument_type": "perp",
        "verified": True,
        "source_mode": SOURCE_MODE,
        # Re-verified on every checkpoint; never cached across reviews.
        "valid_until_ms": now_ms + 1,
        "qty_step": str(step),
        "price_tick": str(PRICE_TICK),
        "min_qty": str(step),
        "min_notional": str(number(native.minimum_notional)),
        "liquidity_notional": str(liquidity),
        "initial_rate": str(initial),
        "fee_rate": str(costs_rate),
        "funding_bound": str(UNMODELED_RATE),
        "liquidation_rate": str(UNMODELED_RATE),
        "tiers": [{"cap": str(liquidity), "rate": str(initial)}],
    }


PRICE_TICK = Decimal("0.00000001")


def kernel_policy(
    *,
    account: Account,
    event: Mapping[str, Any],
    policy: PaperRiskPolicy,
    costs_rate: Decimal,
    keys: set[str],
) -> dict[str, Any]:
    """Project the signed paper policy onto the shared risk policy vocabulary."""
    floor, _ = account.floor()
    if floor is None:
        raise ValueError("UNKNOWN_CONTRACT_FLOOR")
    headroom = account.equity - floor
    reserve = policy.reserve_fraction_initial * account.rulebook.initial_balance
    return {
        "schema": "risk_policy_v1",
        "scale_steps": KERNEL_SCALE_STEPS,
        "scenarios": _scenarios(event, keys),
        "minimum_headroom": str(reserve),
        # PM03 keeps no cumulative "made" ledger: the account floor is the limit.
        "made_limit": str(headroom if headroom > ZERO else reserve),
        "pod_loss_budget": str(number(event["policy"]["pod_loss_limit"])),
        "hedge_tolerance": str(KERNEL_HEDGE_TOLERANCE),
        "shortfall_bps": str(KERNEL_SHORTFALL_BPS),
        "margin_multiplier": "1",
        "checkpoint_execution": {
            "max_gross_notional": str(number(event["policy"]["max_gross_notional"])),
        },
        "source_mode": SOURCE_MODE,
    }


ONE = Decimal("1")


def decision_inputs(
    *,
    account: Account,
    owner: str,
    event: Mapping[str, Any],
    policy: PaperRiskPolicy,
    observations: Mapping[Instrument, MarketObservation],
    markets: Mapping[str, NativeMarket],
    costs_rate: Decimal,
    instruments: tuple[str, ...] = (),
) -> DecisionInputs:
    """Build the exact inputs ``step_checkpoint`` needs, from shell evidence only."""
    now_ms = event["at_ms"]
    if type(now_ms) is not int or now_ms < 0:
        raise ValueError("CHECKPOINT_CONSUMER_CLOCK")
    held = {key: quantity for key, quantity in account.quantities.items() if quantity}
    owner_books = {
        name: {key.key: str(quantity) for key, quantity in sorted(book.items()) if quantity}
        for name, book in sorted(account.pm_quantities.items())
        if any(book.values())
    }
    basis = {}
    for key, quantity in sorted(held.items()):
        entry = account.entries.get(key)
        if entry is None or number(entry) <= ZERO:
            raise ValueError("INDEPENDENT_ENTRY_BASIS_UNQUALIFIED")
        basis[key.key] = {"quantity": str(quantity), "entry_price": str(number(entry))}

    keys = (
        {key.key for key in held}
        | {key for book in owner_books.values() for key in book}
        | set(instruments)
    )
    known = {key.key: key for key in held}
    quotes = {}
    specs = {}
    capabilities = []
    leverage = _leverage(account, policy)
    for name in sorted(keys):
        key = known.get(name) or Instrument.parse(name)
        observation = observations.get(key)
        native = markets.get(name)
        if observation is None or native is None:
            raise ValueError("INDEPENDENT_FOLLOWER_QUOTE_MISSING")
        if number(observation.best_bid) <= ZERO or number(observation.best_ask) <= ZERO:
            raise ValueError("INDEPENDENT_FOLLOWER_QUOTE_INVALID")
        known_at = _ms(observation.first_known_at)
        if not 0 <= now_ms - known_at <= KERNEL_QUOTE_MAX_AGE_MS:
            raise ValueError("INDEPENDENT_FOLLOWER_QUOTE_STALE_OR_FUTURE")
        quotes[name] = {
            "bid": str(number(observation.best_bid)),
            "ask": str(number(observation.best_ask)),
            "known_at_ms": known_at,
        }
        specs[name] = _market_spec(name, native, observation, policy, costs_rate, leverage, now_ms)
        # Modeled paper venue: crossing zero and reducing are both simulated only.
        capabilities.append(VenueCapability(name, True, True))

    floor, _ = account.floor()
    if floor is None:
        raise ValueError("UNKNOWN_CONTRACT_FLOOR")
    pnl = account.pm_equity_pnl()
    return DecisionInputs(
        AccountState(
            FrozenObject.parse(
                {
                    "equity": str(account.equity),
                    "headroom": str(account.equity - floor),
                    "realized_made": "0",
                    "pod_loss_used": {
                        name: str(max(ZERO, -pnl.get(name, ZERO))) for name in owner_books
                    },
                }
            ),
            FrozenObject.parse({key.key: str(value) for key, value in held.items()}),
            FrozenObject.parse(owner_books),
            FrozenObject.parse(basis),
            # The paper ledger is its own observed basis: no second venue copy.
            FrozenObject.parse(basis),
        ),
        MarketContext(FrozenObject.parse(quotes), FrozenObject.parse(specs), tuple(capabilities)),
        RiskPolicy(
            FrozenObject.parse(
                kernel_policy(
                    account=account,
                    event=event,
                    policy=policy,
                    costs_rate=costs_rate,
                    keys=set(quotes),
                )
            )
        ),
        DecisionMs(now_ms),
    )


# ------------------------------------------------------------------- consumption


def state_for(scale: Decimal, policy: PaperRiskPolicy) -> RiskState:
    """The paper risk label for the kernel's chosen reduction scale."""
    if scale >= ONE:
        return RiskState.GREEN
    if scale >= policy.yellow_scale:
        return RiskState.YELLOW
    if scale >= policy.orange_scale:
        return RiskState.ORANGE
    return RiskState.RED


def decide(execution: ExecutionDecision | None, policy: PaperRiskPolicy) -> Decision:
    """Consume the kernel's risk decision and net intents without re-deriving them."""
    if execution is None:
        raise ValueError("KERNEL_DECISION_MISSING")
    if execution.projection_error is not None:
        raise ValueError("KERNEL_PROJECTION:" + execution.projection_error)
    risk = execution.risk.data()
    if risk.get("status") != "ACCEPTED":
        reasons = tuple(str(reason) for reason in risk.get("reasons") or ())
        raise KernelNoTrade("KERNEL_RISK:" + ",".join(reasons or ("NO_TRADE",)))
    plan = execution.execution_plan.data() if execution.execution_plan is not None else None
    if plan is None or plan.get("schema") != "checkpoint_execution_projection_v2":
        raise ValueError("KERNEL_PROJECTION_VERSION")
    targets = {
        owner: {
            Instrument.parse(market): number(quantity)
            for market, quantity in sorted(book.items())
            if number(quantity)
        }
        for owner, book in sorted(plan["pod_targets"].items())
    }
    intents = tuple(
        {
            "market": intent.market,
            "net_delta_qty": str(intent.net_delta_qty),
            "reduce_only": intent.reduce_only,
            "owner_allocations": [
                [owner, str(quantity)] for owner, quantity in intent.owner_allocations
            ],
        }
        for intent in execution.net_orders
    )
    scale = number(risk.get("scale", "0"))
    for intent in intents:
        if not number(intent["net_delta_qty"]):
            raise ValueError("KERNEL_EMPTY_NET_INTENT")
    return Decision(
        scale=scale,
        state=state_for(scale, policy),
        targets=targets,
        net_intents=intents,
        risk=risk,
        reasons=tuple(str(reason) for reason in risk.get("reasons") or ()),
    )


def intent_sha(intents: tuple[dict[str, Any], ...]) -> str:
    """Signed-evidence digest of the kernel's net intents."""
    return digest([list(intent.items()) for intent in intents])
