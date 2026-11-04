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
from typing import Any

from .pm03_account import Account, Instrument, Rulebook, number
from .pm03_execution import CostModel, MarketObservation, execute_targets
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
        "equity": str(account.equity),
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
) -> dict:
    """Replay synthetic fixture minutes and optional source-book intent updates.

    Each minute row: at: datetime, prices: dict[native, Decimal],
    prior_volume: dict[native, Decimal], updates: list[dict].
    Each update: manager, source_equity, book: dict[native, signed qty],
    leader_prices: dict[native, source mark], verified_whole_book=True.
    A single minute marks all open positions even without orders.
    """
    if mode not in {"CERTIFIED", "SCREEN_ONLY"}:
        raise ManifestInvalid("INVALID_REPLAY_MODE")
    if not minutes:
        raise ManifestBlocked("MISSING_MARK_TO_MARK_PATH")
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
    sources: dict[str, dict[str, Any]] = {}
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
        item: dict = {"at": when.isoformat(), "risk_after_mark": account.risk.value}
        if account.breached:
            item["status"] = "HALT_PERSISTENT"
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
                sources[pm] = {
                    "equity": equity,
                    "book": {_instrument(inst): number(q) for inst, q in book.items()},
                    "leader": {_instrument(inst): number(px) for inst, px in leader.items()},
                }
            # Refuse partial portfolio updates when a manager has not yet been
            # observed. Existing sources remain unchanged until explicitly updated.
            if set(sources) != set(k_values):
                raise ManifestBlocked("MISSING_MANAGER_WHOLE_BOOK")
            desired: dict[str, dict[Instrument, Decimal]] = {}
            for pm, source in sorted(sources.items()):
                desired[pm] = {}
                for inst, qty in sorted(source["book"].items()):
                    price = source["leader"][inst]
                    if price <= ZERO:
                        raise ManifestBlocked("INVALID_LEADER_PRICE")
                    # Source signed notional / source equity * follower equity * k.
                    # Separate native follower open price -> target quantity.
                    target = (
                        (qty * price / source["equity"])
                        * account.equity
                        * k_values[pm]
                        / prices[inst]
                    )
                    desired[pm][inst] = target
            decision = account.evaluate(desired, prices, trusted=True, market_known=True)
            item["pretrade"] = {
                "allowed": decision["allowed"],
                "reasons": decision["reasons"],
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
                desired if decision["allowed"] else {},
                observations,
                costs,
                decision_at=when.isoformat(),
                hypothetical_fill_at=when.isoformat(),
                permitted=decision["allowed"],
            )
            item["execution"] = result
        account.verify()
        item["equity_after"] = str(account.equity)
        item["risk_after"] = account.risk.value
        journal.append(item)
    return _report(account, times[-1], journal, mode)
