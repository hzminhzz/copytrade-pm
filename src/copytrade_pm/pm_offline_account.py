"""Isolated offline fixture driver for the existing PM-03 financial authority.

This is a conservative integration seam, not a second account simulator.
The source whole-book, known-at quotes and native market context MUST be
independently verified before any non-fixture study can use this adapter.
Financial outputs are synthetic and cannot authorize a broker or science claim.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json

from .pm03_account import Account, Instrument, RiskState, Rulebook, number
from .pm03_execution import CostModel, MarketObservation, execute_targets
from .pm03_risk import RiskEvidence, RiskPolicy, classify
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

ZERO = Decimal("0")


def _minute(when: datetime) -> datetime:
    if not isinstance(when, datetime) or when.utcoffset() is None:
        raise ManifestInvalid("NAIVE_OR_UNKNOWN_ACCOUNT_CLOCK")
    when = when.astimezone(UTC)
    if when.second or when.microsecond:
        raise ManifestInvalid("NON_MINUTE_ACCOUNT_CLOCK")
    return when


def _instrument(native: str) -> Instrument:
    if not isinstance(native, str):
        raise ManifestInvalid("INVALID_NATIVE_INSTRUMENT")
    pieces = native.split(":")
    if len(pieces) != 5 or pieces[:3] != ["hyperliquid", "mainnet", "perp"]:
        raise ManifestInvalid("UNSUPPORTED_NATIVE_MARKET")
    dex, symbol = pieces[3:]
    if not symbol or "/" in symbol:
        raise ManifestInvalid("INVALID_NATIVE_SYMBOL")
    if dex == "default":
        return Instrument("hyperliquid", "perp", symbol)
    if dex not in {"xyz", "io", "para"}:
        raise ManifestInvalid("UNSUPPORTED_NATIVE_DEX")
    return Instrument("hyperliquid", f"hip3:{dex}", symbol)


def _report(account: Account, clock: datetime, events: list[dict], mode: str) -> dict:
    account.verify()
    ledger = {
        "as_of": clock.isoformat(),
        "risk": account.risk.value,
        "breached": account.breached,
        "stage_passed": account.stage_passed,
        "cash": str(account.cash),
        "balance": str(account.balance),
        "equity": str(account.equity),
        "daily_key": account.daily_key,
        "daily_start_balance": str(account.daily_start_balance),
        "high_water": str(account.high_water),
        "realized_pnl": str(account.realized_pnl),
        "unrealized_pnl": str(account.unrealized_pnl),
        "fees": str(account.costs),
        "funding": str(account.funding),
        "positions": {k.key: str(q) for k, q in sorted(account.quantities.items()) if q},
        "pm_quantities": {
            pm: {k.key: str(q) for k, q in sorted(book.items()) if q}
            for pm, book in sorted(account.pm_quantities.items())
        },
        "events": events,
        "first_breach_at": next((e["at"] for e in events if e.get("breached_after")), None),
        "first_target_at": next((e["at"] for e in events if e.get("stage_passed_after")), None),
        "account_snapshot_sha256": sha256(
            json.dumps(account.snapshot(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    encoded = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": "pm_offline_pm03_fixture_v1",
        "status": "SYNTHETIC_PM03_"
        + ("BREACH" if account.breached else ("TARGET" if account.stage_passed else "OPEN")),
        "mode": mode,
        "sha256": sha256(encoded).hexdigest(),
        "ledger": ledger,
        "financial_authority": "PM03_ACCOUNT_DECIMAL",
        "prospective_verified": False,
        "scientifically_qualified": False,
    }


def replay_fixture(
    *,
    rulebook: Rulebook,
    minutes: list[dict],
    costs: CostModel,
    k_by_manager: dict[str, Decimal],
    mode: str = "CERTIFIED",
    risk_policy: RiskPolicy | None = None,
    scenario_shocks: tuple[dict[str, Decimal], ...] = (),
    hedge_break_loss: Decimal = ZERO,
    stressed_liquidity_loss: Decimal = ZERO,
) -> dict:
    """Replay synthetic fixture minutes and optional source-book intent updates.

    Each minute row: at: datetime, prices: dict[native, Decimal],
    prior_volume: dict[native, Decimal], updates: list[dict],
    optional funding: list[{amount, allocated, first_known_at}].
    Each update: manager, source_equity, book: dict[native, signed qty],
    leader_prices: dict[native, source mark], verified_whole_book=True.
    A single minute marks all open positions even without orders.
    """
    if mode not in {"CERTIFIED", "SCREEN_ONLY"}:
        raise ManifestInvalid("INVALID_REPLAY_MODE")
    if not minutes:
        raise ManifestBlocked("MISSING_MARK_TO_MARK_PATH")
    if risk_policy is not None and not scenario_shocks:
        raise ManifestBlocked("MISSING_FROZEN_PORTFOLIO_STRESS")
    if hedge_break_loss < ZERO or stressed_liquidity_loss < ZERO:
        raise ManifestInvalid("INVALID_NEGATIVE_PORTFOLIO_STRESS")
    if not rulebook.confirmed:
        raise ManifestBlocked("UNCONFIRMED_FIXTURE_RULEBOOK")
    k_values = {pm: number(k) for pm, k in k_by_manager.items()}
    if not k_values or any(not pm or k <= ZERO for pm, k in k_values.items()):
        raise ManifestInvalid("INVALID_MANAGER_K")
    times = [_minute(row["at"]) for row in minutes]
    if len(set(times)) != len(times) or times != sorted(times):
        raise ManifestInvalid("NONMONOTONIC_MINUTE_SERIES")
    if any(b - a != timedelta(minutes=1) for a, b in zip(times, times[1:])):
        raise ManifestBlocked("GAP_IN_REQUIRED_MINUTE_MARKS")
    account = Account.start(rulebook, times[0].isoformat())
    last_target_by_manager: dict[str, dict[Instrument, Decimal]] = {}
    journal: list[dict] = []
    for when, row in zip(times, minutes):
        prices = {_instrument(key): number(price) for key, price in row["prices"].items()}
        previous = {_instrument(key): number(vol) for key, vol in row["prior_volume"].items()}
        if not prices or any(x <= ZERO for x in prices.values()):
            raise ManifestBlocked("MISSING_OR_INVALID_PRICE_MARK")
        if any(x <= ZERO for x in previous.values()):
            raise ManifestBlocked("UNKNOWN_PRIOR_BAR_CAPACITY")
        if set(prices) - set(previous):
            raise ManifestBlocked("MISSING_PRIOR_BAR_CAPACITY")
        active = {inst for inst, qty in account.quantities.items() if qty}
        if active - set(prices):
            raise ManifestBlocked("MISSING_ACTIVE_MINUTE_MARK")
        account.mark(prices, when.isoformat())
        item: dict = {
            "at": when.isoformat(),
            "risk_after_mark": account.risk.value,
            "breached_after": account.breached,
            "stage_passed_after": account.stage_passed,
        }
        if account.breached:
            item["status"] = "HALT_PERSISTENT"
            item["breached_after"] = account.breached
            journal.append(item)
            continue
        funding_rows = row.get("funding", [])
        if not isinstance(funding_rows, list):
            raise ManifestInvalid("INVALID_FUNDING_EVENT_LIST")
        for funding in funding_rows:
            if not isinstance(funding, dict) or set(funding) != {
                "amount",
                "allocated",
                "first_known_at",
            }:
                raise ManifestInvalid("INVALID_FUNDING_EVENT")
            known = funding["first_known_at"]
            if not isinstance(known, datetime) or known.utcoffset() is None:
                raise ManifestBlocked("MISSING_FUNDING_RECEIPT_CLOCK")
            if known.astimezone(UTC) > when:
                raise ManifestBlocked("FUTURE_KNOWN_FUNDING")
            allocations = funding["allocated"]
            if (
                not isinstance(allocations, dict)
                or not allocations
                or set(allocations) - k_values.keys()
            ):
                raise ManifestInvalid("INVALID_FUNDING_ALLOCATION")
            amount = number(funding["amount"])
            weights = {pm: number(v) for pm, v in allocations.items()}
            if sum(weights.values(), ZERO) != amount:
                raise ManifestInvalid("FUNDING_ATTRIBUTION_MISMATCH")
            account.post_funding(amount, weights)
            item.setdefault("funding", []).append(
                {
                    "amount": str(amount),
                    "allocated": {pm: str(value) for pm, value in sorted(weights.items())},
                    "first_known_at": known.astimezone(UTC).isoformat(),
                    "pm03_funding_total": str(account.funding),
                }
            )
        if account.breached:
            item["status"] = "HALT_AFTER_FUNDING"
            item["breached_after"] = account.breached
            journal.append(item)
            continue
        updates = row.get("updates", [])
        if updates:
            for update in updates:
                pm = update.get("manager")
                if pm not in k_values:
                    raise ManifestInvalid("UNKNOWN_SOURCE_MANAGER")
                if update.get("verified_whole_book") is not True:
                    raise ManifestBlocked("INCOMPLETE_SOURCE_BOOK")
                equity = number(update.get("source_equity"))
                if equity <= ZERO:
                    raise ManifestBlocked("INVALID_SOURCE_EQUITY")
                book = update.get("book")
                leader = update.get("leader_prices")
                if not isinstance(book, dict) or not isinstance(leader, dict):
                    raise ManifestBlocked("INCOMPLETE_SOURCE_BOOK")
                if not book or book.keys() != leader.keys():
                    raise ManifestBlocked("INCOMPLETE_SOURCE_HEDGE_MARKS")
                if any(_instrument(inst) not in prices for inst in book):
                    raise ManifestBlocked("UNKNOWN_FOLLOWER_MARK_FOR_HEDGE")
                # Create a new follower intent ONLY for the manager whose
                # new source book was observed. Never reprice another manager
                # from stale leader marks when a different manager signals.
                current_book = {_instrument(inst): number(q) for inst, q in book.items()}
                current_leader = {_instrument(inst): number(px) for inst, px in leader.items()}
                manager_target: dict[Instrument, Decimal] = {}
                for inst, qty in sorted(current_book.items()):
                    source_mark = current_leader[inst]
                    if source_mark <= ZERO:
                        raise ManifestBlocked("INVALID_LEADER_PRICE")
                    manager_target[inst] = (
                        (qty * source_mark / equity) * account.equity * k_values[pm] / prices[inst]
                    )
                last_target_by_manager[pm] = manager_target
            # A partial manager universe cannot invent missing flat managers.
            if set(last_target_by_manager) != set(k_values):
                raise ManifestBlocked("MISSING_MANAGER_WHOLE_BOOK")
            desired = {pm: dict(target) for pm, target in sorted(last_target_by_manager.items())}
            if risk_policy is None:
                decision = account.evaluate(desired, prices, trusted=True, market_known=True)
                approved = desired if decision["allowed"] else {}
                permitted = decision["allowed"]
                reasons = decision["reasons"]
            else:
                evidence = RiskEvidence(
                    trusted=True,
                    account_state_known=True,
                    market_state_known=True,
                    market_coverage_valid=True,
                    pending_unknown_orders=False,
                    input_status="RESEARCH_SYNTHETIC",
                    pm02_qualified=False,
                    stressed_liquidity_loss=stressed_liquidity_loss,
                    hedge_break_loss=hedge_break_loss,
                )
                shocks = tuple(
                    {_instrument(inst): number(move) for inst, move in scenario.items()}
                    for scenario in scenario_shocks
                )
                decision = classify(account, desired, prices, shocks, evidence, risk_policy)
                approved = decision["approved"]
                permitted = decision["approved_new_risk"]
                reasons = list(decision["reason_codes"])
                # PM-03 classifier guards net exposure. Explicitly veto a
                # new gross-before-net or single-pod concentration expansion.
                gross = sum(
                    (
                        abs(q * prices[inst])
                        for book in approved.values()
                        for inst, q in book.items()
                    ),
                    ZERO,
                )
                prior_gross = sum(
                    (
                        abs(q * prices[inst])
                        for book in account.pm_quantities.values()
                        for inst, q in book.items()
                    ),
                    ZERO,
                )
                max_leverage = risk_policy.max_gross_leverage
                if account.rulebook.max_gross_leverage is not None:
                    max_leverage = min(max_leverage, account.rulebook.max_gross_leverage)
                single_pod_max = max(
                    (
                        abs(q * prices[inst])
                        for book in approved.values()
                        for inst, q in book.items()
                    ),
                    default=ZERO,
                )
                excessive = gross > account.equity * max_leverage or (
                    single_pod_max > account.equity * risk_policy.max_instrument_fraction_equity
                )
                if excessive and gross > prior_gross:
                    permitted = False
                    reasons.append("GROSS_BEFORE_NET_OR_POD_CONCENTRATION")
                    account.risk = RiskState.RED
                    account.risk_reasons = tuple(sorted(set(reasons)))
            item["pretrade"] = {
                "allowed": permitted,
                "reasons": sorted(set(reasons)),
            }
            observations = {
                inst: MarketObservation(
                    inst,
                    event_at=when.isoformat(),
                    first_known_at=when.isoformat(),
                    mark=price,
                    volume_base=previous[inst],
                    quality="OHLCV_1M_PROXY",
                    supported=True,
                )
                for inst, price in prices.items()
            }
            result = execute_targets(
                account,
                approved if permitted else {},
                observations,
                costs,
                decision_at=when.isoformat(),
                hypothetical_fill_at=when.isoformat(),
                permitted=permitted,
            )
            item["execution"] = result
        account.verify()
        item["equity_after"] = str(account.equity)
        item["breached_after"] = account.breached
        item["stage_passed_after"] = account.stage_passed
        item["risk_after"] = account.risk.value
        journal.append(item)
    return _report(account, times[-1], journal, mode)
