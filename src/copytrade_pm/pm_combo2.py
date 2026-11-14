"""Combo 2: causal, strictly local, read-only-source paper follower.

Only SOURCE_RECEIPT, PAPER_REBALANCE, PAPER_FUNDING and OPERATOR_RESET events
are accepted. There is no network, broker, exchange order or credential import.
The existing PM-03 Account is the *only* PnL and position authority. Ledger is
the existing PM-03 append-only, hash-chained store, not a second account engine.

All marks, snapshots, costs and stress inputs are explicit first-known inputs.
Nothing in this module is authorization to place a Propr order.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal as D, ROUND_DOWN
import json
from pathlib import Path

from .pm03_account import (
    Account,
    Instrument,
    Rulebook,
    ZERO,
    clock,
    digest,
    number,
)
from .pm03_memory import Event, Ledger, atomic_private

MANAGERS = ("W028", "CA-008", "W015")
SCHEMA = "combo2_paper_v1"
BATCH_SECONDS = 300


@dataclass(frozen=True)
class PaperPolicy:
    account_alias: str = "#JhW9"
    capital: D = D("5000")
    sleeve: D = D("1000")
    coin_gross_cap: D = D("1250")
    account_gross_cap: D = D("5000")
    min_opening_usd: D = D("10")
    max_snapshot_age_seconds: int = 90
    max_quote_age_seconds: int = 90
    max_carry_seconds: int = 1800
    max_participation: D = D("0.01")
    daily_loss_rate: D = D("0.03")
    total_loss_usd: D = D("300")
    soft_fraction: D = D("0.8")

    def __post_init__(self) -> None:
        if self.account_alias != "#JhW9" or self.capital != D("5000") or self.sleeve != D("1000"):
            raise ValueError("COMBO2_FROZEN_ACCOUNT_AND_SLEEVES")
        if self.coin_gross_cap != D("1250") or self.account_gross_cap != D("5000"):
            raise ValueError("COMBO2_FROZEN_GROSS_CAPS")
        if self.min_opening_usd != D("10") or self.daily_loss_rate != D(".03"):
            raise ValueError("COMBO2_FROZEN_RISK_RULE")
        if self.total_loss_usd != D("300") or self.soft_fraction != D(".8"):
            raise ValueError("COMBO2_FROZEN_SOFT_LIMITS")
        if min(self.max_snapshot_age_seconds, self.max_quote_age_seconds) < 1:
            raise ValueError("INVALID_SOURCE_AGE_POLICY")
        if self.max_carry_seconds < 1 or not ZERO < self.max_participation <= D("1"):
            raise ValueError("INVALID_MARKET_POLICY")

    def manifest(self) -> dict:
        return {
            "schema": SCHEMA,
            "managers": list(MANAGERS),
            "account_alias": self.account_alias,
            "provisional_rulebook": "CLASSIC_1STEP_EVALUATION_UNATTESTED",
            "paper_only": True,
            "live_authorization": False,
            **{
                name: str(value) if isinstance(value, D) else value
                for name, value in vars(self).items()
            },
        }


def _utc(text: str) -> datetime:
    return clock(text)


def _age(observed: str, now: str, maximum: int) -> None:
    delta = (_utc(now) - _utc(observed)).total_seconds()
    if delta < 0 or delta > maximum:
        raise ValueError("STALE_OR_FUTURE_FIRST_KNOWN_SOURCE")


def _int_id(value: str) -> Instrument:
    obj = Instrument.parse(value)
    if obj.venue != "hyperliquid" or not obj.market.startswith("mainnet:perp:"):
        raise ValueError("UNKNOWN_VENUE_OR_DEX")
    dex = obj.market.rsplit(":", 1)[-1]
    if not dex or obj.symbol.startswith(":") or ":" in obj.symbol:
        raise ValueError("INVALID_NATIVE_INSTRUMENT")
    return obj


def _round_zero(quantity: D, lot: D) -> D:
    if lot <= ZERO:
        raise ValueError("INVALID_LOT")
    return (
        (abs(quantity) / lot).to_integral_value(rounding=ROUND_DOWN)
        * lot
        * (D("1") if quantity >= ZERO else D("-1"))
    )


def _positions(book: dict[str, dict[str, str]]) -> dict[Instrument, tuple[D, D]]:
    if not isinstance(book, dict):
        raise ValueError("UNKNOWN_SOURCE_BOOK")
    result = {}
    for identifier, row in book.items():
        inst = _int_id(identifier)
        if not isinstance(row, dict) or set(row) != {"quantity", "mark"}:
            raise ValueError("UNKNOWN_SOURCE_POSITION")
        qty, mark = number(row["quantity"]), number(row["mark"])
        if mark <= ZERO or inst in result:
            raise ValueError("INVALID_SOURCE_MARK_OR_DUPLICATE")
        result[inst] = (qty, mark)
    return result


def _snapshot(
    snapshot: dict, manager: str, decision_at: str, hashes: dict[str, str], max_age: int
) -> dict[Instrument, tuple[D, D]]:
    if not isinstance(snapshot, dict) or snapshot.get("manager") != manager:
        raise ValueError("SOURCE_MANAGER_IDENTITY_MISMATCH")
    if snapshot.get("subject_sha") != hashes[manager]:
        raise ValueError("SOURCE_ACCOUNT_IDENTITY_MISMATCH")
    if snapshot.get("quality") != "OFFICIAL_ALL_DEXS_READ_ONLY":
        raise ValueError("UNVERIFIED_SOURCE_SNAPSHOT")
    if snapshot.get("full_book") is not True or snapshot.get("all_dexes_complete") is not True:
        raise ValueError("INCOMPLETE_SOURCE_BOOK")
    _age(snapshot["first_known_at"], decision_at, max_age)
    if _utc(snapshot["event_at"]) > _utc(snapshot["first_known_at"]):
        raise ValueError("BACKDATED_SOURCE_SNAPSHOT")
    if number(snapshot.get("equity", "0")) <= ZERO:
        raise ValueError("SOURCE_EQUITY_NONPOSITIVE")
    return _positions(snapshot["positions"])


def _quote(row: dict, now: str, policy: PaperPolicy, *, require_open: bool) -> dict:
    required = {
        "first_known_at",
        "mark",
        "lot",
        "minimum",
        "volume_base",
        "fee_bps",
        "spread_bps",
        "slippage_bps",
        "session_open",
        "supported",
        "native_market_id",
    }
    if not isinstance(row, dict) or not required.issubset(row):
        raise ValueError("INCOMPLETE_MARKET_CONTRACT")
    if type(row["supported"]) is not bool or type(row["session_open"]) is not bool:
        raise ValueError("INVALID_MARKET_STATE")
    if require_open and (not row["session_open"] or not row["supported"]):
        raise ValueError("MARKET_NOT_EXECUTABLE")
    _age(
        row["first_known_at"],
        now,
        policy.max_quote_age_seconds if row["session_open"] else policy.max_carry_seconds,
    )
    if not row["native_market_id"] or "/" in str(row["native_market_id"]):
        raise ValueError("UNVERIFIED_NATIVE_MARKET_ID")
    numbers = {
        k: number(row[k])
        for k in ("mark", "lot", "minimum", "volume_base", "fee_bps", "spread_bps", "slippage_bps")
    }
    if min(numbers["mark"], numbers["lot"], numbers["minimum"]) <= ZERO:
        raise ValueError("INVALID_MARKET_PRECISION_OR_MARK")
    if any(numbers[k] < ZERO for k in ("volume_base", "fee_bps", "spread_bps", "slippage_bps")):
        raise ValueError("NEGATIVE_MARKET_COST_OR_VOLUME")
    # Optional OHLC adverse extremes are evidence, not an executable quote.
    low = number(row.get("adverse_low", row["mark"]))
    high = number(row.get("adverse_high", row["mark"]))
    if not ZERO < low <= numbers["mark"] <= high:
        raise ValueError("INVALID_INTRABAR_EXTREMES")
    return {
        **numbers,
        "adverse_low": low,
        "adverse_high": high,
        "session_open": row["session_open"],
        "supported": row["supported"],
        "native_market_id": row["native_market_id"],
        "carried": not row["session_open"],
    }


def _net(books: dict[str, dict[Instrument, D]]) -> dict[Instrument, D]:
    out: dict[Instrument, D] = {}
    for book in books.values():
        for inst, q in book.items():
            out[inst] = out.get(inst, ZERO) + q
    return out


def _book_json(book: dict[str, dict[Instrument, D]]) -> dict:
    return {
        m: {i.key: str(q) for i, q in sorted(values.items()) if q}
        for m, values in sorted(book.items())
    }


def _paper_rulebook(policy: PaperPolicy, as_of: str) -> Rulebook:
    # "confirmed" allows the *synthetic Account* to simulate trades. It does
    # not attest a real account, and may never flow into a broker contract.
    return Rulebook(
        program="classic_1step",
        stage="evaluation",
        source="COMBO2_PROVISIONAL_SIMULATED_ONLY",
        observed_at=as_of,
        version=SCHEMA,
        timezone="UTC",
        initial_balance=policy.capital,
        profit_target=None,
        daily_loss=None,
        static_loss=policy.total_loss_usd,
        trailing_loss=None,
        daily_loss_rate=policy.daily_loss_rate,
        confirmed=True,
        account_terms_confirmed=False,
        permitted=(),
        max_gross_leverage=D("1"),
    )


def _fresh_state() -> dict:
    return {
        "pending": {},
        "receipts": {},
        "desired": {manager: {} for manager in MANAGERS},
        "frozen_daily_key": None,
        "total_frozen": False,
        "halt_reason": None,
        "last_rebalance": None,
        "last_report": None,
        "status": "ACTIVE_PAPER",
    }


def _account_soft_limits(account: Account, policy: PaperPolicy) -> tuple[D, D, bool]:
    daily_start = account.daily_start_balance
    daily_soft = daily_start * policy.daily_loss_rate * policy.soft_fraction
    total_soft = policy.total_loss_usd * policy.soft_fraction
    return (
        daily_soft,
        total_soft,
        (
            account.equity <= daily_start - daily_soft
            or account.equity <= policy.capital - total_soft
        ),
    )


def _latch(account: Account, meta: dict, policy: PaperPolicy) -> None:
    daily, total, touched = _account_soft_limits(account, policy)
    if account.equity <= account.daily_start_balance - daily:
        meta["frozen_daily_key"] = account.daily_key
        meta["halt_reason"] = "PAPER_DAILY_SOFT_80_PERCENT"
    if account.equity <= policy.capital - total:
        meta["total_frozen"] = True
        meta["halt_reason"] = "PAPER_TOTAL_SOFT_80_PERCENT"
    if account.breached:
        meta["total_frozen"] = True
        meta["halt_reason"] = "PAPER_CONTRACTUAL_BREACH"
        meta["status"] = "PAPER_BREACHED"
    elif touched or meta["total_frozen"] or meta["frozen_daily_key"] is not None:
        meta["status"] = "FROZEN"


def _mark_with_extremes(
    account: Account,
    meta: dict,
    quotes: dict[Instrument, dict],
    now: str,
    policy: PaperPolicy,
) -> None:
    # Opposing virtual manager books require marks even when net inventory
    # is zero. They are attribution positions, not external order inventory.
    tracked = set(account.quantities) | {
        inst for book in account.pm_quantities.values() for inst, qty in book.items() if qty
    }
    if tracked - set(quotes):
        raise ValueError("MISSING_HELD_PAPER_MARK")
    if tracked:
        adverse = {
            inst: (
                quotes[inst]["adverse_low"]
                if account.quantities.get(inst, ZERO) > ZERO
                else quotes[inst]["adverse_high"]
                if account.quantities.get(inst, ZERO) < ZERO
                else quotes[inst]["mark"]
            )
            for inst in tracked
        }
        account.mark(adverse, now)
        _latch(account, meta, policy)
    account.mark({inst: quotes[inst]["mark"] for inst in tracked}, now)
    _latch(account, meta, policy)


def _increase(old: D, new: D) -> bool:
    return old * new < ZERO or abs(new) > abs(old)


def _reduce_book(account: Account, books: dict[str, dict[Instrument, D]]) -> dict:
    for manager, targets in books.items():
        prior_book = account.pm_quantities.get(manager, {})
        for inst, desired in list(targets.items()):
            prior = prior_book.get(inst, ZERO)
            if prior * desired < ZERO or (not prior and desired):
                targets[inst] = ZERO
            elif abs(desired) > abs(prior):
                targets[inst] = prior
    if any(abs(q) > abs(account.quantities.get(inst, ZERO)) for inst, q in _net(books).items()):
        raise ValueError("HEDGE_BREAK_REDUCTION_INCREASES_NET_RISK")
    return books


def _model_fill(
    account: Account,
    inst: Instrument,
    qty: D,
    quotes: dict,
    policy: PaperPolicy,
    owner: dict[str, D],
    *,
    remaining_capacity: D | None = None,
) -> dict:
    info = quotes[inst]
    if not info["session_open"] or not info["supported"]:
        return {"status": "CLOSED_MARKET", "requested": str(qty)}
    lot, minimum, mark = info["lot"], info["minimum"], info["mark"]
    qty = _round_zero(qty, lot)
    if not qty or abs(qty) < minimum:
        return {"status": "LOT_DUST", "requested": str(qty)}
    prior = account.quantities.get(inst, ZERO)
    is_reduce = prior * qty < ZERO and abs(qty) <= abs(prior)
    if not is_reduce and abs(qty * mark) < policy.min_opening_usd:
        return {"status": "MIN_NOTIONAL", "requested": str(qty)}
    capacity = _round_zero(info["volume_base"] * policy.max_participation, lot)
    if remaining_capacity is not None:
        if remaining_capacity < ZERO:
            raise ValueError("NEGATIVE_REMAINING_CAPACITY")
        capacity = min(capacity, _round_zero(remaining_capacity, lot))
    if capacity <= ZERO:
        return {"status": "NO_CAPACITY", "requested": str(qty)}
    fill = min(abs(qty), capacity) * (D("1") if qty > ZERO else D("-1"))
    # Preserve manager allocation and prevent rounding a PM past its request.
    allowed = {}
    remaining = fill
    for name, requested in sorted(owner.items()):
        if requested * fill <= ZERO or not remaining:
            continue
        piece = min(abs(requested), abs(remaining)) * (D("1") if fill > ZERO else D("-1"))
        if piece:
            allowed[name] = piece
            remaining -= piece
    if remaining or not allowed:
        raise ValueError("PARTIAL_FILL_ALLOCATION_MISMATCH")
    drag = (info["spread_bps"] / D("2") + info["slippage_bps"]) / D("10000")
    px = mark * (D("1") + (D("1") if fill > ZERO else D("-1")) * drag)
    if px <= ZERO:
        raise ValueError("INVALID_MODEL_FILL_PRICE")
    fee = abs(fill * px) * info["fee_bps"] / D("10000")
    account.simulate_fill(inst, fill, px, fee, accepted=True, allocated=allowed)
    return {
        "status": "FILLED" if fill == qty else "PARTIAL",
        "quantity": str(fill),
        "price": str(px),
        "fee": str(fee),
        "allocation": {m: str(v) for m, v in allowed.items()},
        "unfilled": str(qty - fill),
        "hypothetical": True,
    }


def _risk_frozen(account: Account, meta: dict, semantics_version: int) -> bool:
    legacy = meta["total_frozen"] or meta["frozen_daily_key"] is not None or account.breached
    return legacy or (
        semantics_version >= 2 and (meta["status"] == "FROZEN" or account.risk.value == "HALT")
    )


def _run_rebalance(
    account: Account,
    meta: dict,
    payload: dict,
    now: str,
    policy: PaperPolicy,
    hashes: dict[str, str],
    *,
    semantics_version: int = 2,
) -> dict:
    due = {key: at for key, at in meta["pending"].items() if _utc(now) >= _utc(at)}
    if not due:
        raise ValueError("NO_DUE_FIRST_KNOWN_BATCH")
    # Validate every required state and mark before changing anything. Work on
    # a detached account/meta in the caller, so any error is fully atomic.
    touched = {key.split("|", 1)[0] for key in due}
    raw_books = payload.get("leaders")
    market_rows = payload.get("markets")
    if not isinstance(raw_books, dict) or not isinstance(market_rows, dict):
        raise ValueError("MISSING_LEADERS_OR_MARKETS")
    sources = {}
    for manager in touched:
        source = raw_books.get(manager)
        if source is None:
            raise ValueError("MISSING_DUE_MANAGER_SOURCE")
        positions = _snapshot(source, manager, now, hashes, policy.max_snapshot_age_seconds)
        sources[manager] = (number(source["equity"]), positions)

    existing_books = {
        m: {_int_id(k): number(v) for k, v in meta["desired"].get(m, {}).items()} for m in MANAGERS
    }
    all_instruments = set(account.quantities)
    for book in account.pm_quantities.values():
        all_instruments.update(book)
    for book in existing_books.values():
        all_instruments.update(book)
    for _, positions in sources.values():
        all_instruments.update(positions)
    quotes = {}
    skipped = []
    for inst in sorted(all_instruments):
        raw = market_rows.get(inst.key)
        if raw is None:
            if inst in account.quantities and account.quantities[inst]:
                raise ValueError("MISSING_OPEN_POSITION_MARK")
            skipped.append(inst.key)
            continue
        quotes[inst] = _quote(raw, now, policy, require_open=False)
        if not quotes[inst]["supported"]:
            skipped.append(inst.key)
    # Model marks can be carried for valuation while the market is closed.
    _mark_with_extremes(account, meta, quotes, now, policy)
    for manager, (equity, positions) in sources.items():
        desired = {}
        for inst, (qty, leader_mark) in positions.items():
            if inst not in quotes or not quotes[inst]["supported"]:
                continue
            # Never normalize by sleeve margin, nor collapse source fills.
            notional = qty * leader_mark / equity * policy.sleeve
            desired[inst] = notional / quotes[inst]["mark"]
        existing_books[manager] = desired

    for m in MANAGERS:
        # Missing a new *market* mark cannot silently flatten a previously held
        # PM position; it blocks the rebalance if the old position is material.
        for inst, qty in existing_books[m].items():
            if qty and inst not in quotes:
                raise ValueError("MISSING_EXISTING_DESIRED_MARK")
    desired_original = deepcopy(existing_books)
    coins = sorted({i for b in existing_books.values() for i in b})
    coin_clamps = {}
    for inst in coins:
        gross = sum(
            abs(book.get(inst, ZERO) * quotes[inst]["mark"]) for book in existing_books.values()
        )
        factor = min(D("1"), policy.coin_gross_cap / gross) if gross else D("1")
        coin_clamps[inst.key] = str(factor)
        if factor < D("1"):
            for book in existing_books.values():
                if inst in book:
                    book[inst] *= factor
    portfolio_gross = sum(
        abs(q * quotes[inst]["mark"])
        for book in existing_books.values()
        for inst, q in book.items()
    )
    portfolio_factor = (
        min(D("1"), policy.account_gross_cap / portfolio_gross) if portfolio_gross else D("1")
    )
    if portfolio_factor < D("1"):
        for book in existing_books.values():
            for inst in book:
                book[inst] *= portfolio_factor
    for book in existing_books.values():
        for inst, qty in list(book.items()):
            book[inst] = _round_zero(qty, quotes[inst]["lot"])

    frozen = _risk_frozen(account, meta, semantics_version)
    if frozen:
        existing_books = _reduce_book(account, existing_books)
    else:
        # A fully source-backed stress scenario must be available before any
        # new risk. Hedge-break loss is explicit when virtual PMs oppose.
        new_net = _net(existing_books)
        old_net = account.quantities
        new_risk = any(
            _increase(old_net.get(inst, ZERO), new_net.get(inst, ZERO))
            for inst in set(new_net) | set(old_net)
        )
        opposing_legs = any(
            any(book.get(inst, ZERO) > ZERO for book in existing_books.values())
            and any(book.get(inst, ZERO) < ZERO for book in existing_books.values())
            for inst in coins
        )
        if opposing_legs and number(payload.get("hedge_break_loss", "0")) <= ZERO:
            raise ValueError("MISSING_HEDGE_BREAK_STRESS")
        if new_risk or opposing_legs:
            shock_rows = payload.get("shocks")
            if not isinstance(shock_rows, list) or not shock_rows:
                raise ValueError("MISSING_STRESS_SCENARIOS")
            stress = ZERO
            for scenario in shock_rows:
                if not isinstance(scenario, dict) or set(scenario) != {
                    i.key for i in new_net if new_net[i]
                }:
                    raise ValueError("INCOMPLETE_STRESS_SCENARIO")
                move = sum(
                    (
                        q * quotes[i]["mark"] * number(scenario[i.key])
                        for i, q in new_net.items()
                        if q
                    ),
                    ZERO,
                )
                stress = max(stress, -move)
            stress += number(payload.get("hedge_break_loss", "0"))
            daily_soft, total_soft, _ = _account_soft_limits(account, policy)
            headroom = min(
                account.equity - (account.daily_start_balance - daily_soft),
                account.equity - (policy.capital - total_soft),
            )
            if headroom <= ZERO or stress > headroom:
                existing_books = _reduce_book(account, existing_books)
                meta["status"] = "FROZEN"
                meta["halt_reason"] = "MODELED_STRESS_EXCEEDS_SOFT_HEADROOM"

    results = []
    for inst in sorted(
        set(account.quantities)
        | {i for b in existing_books.values() for i in b}
        | {i for b in account.pm_quantities.values() for i in b}
    ):
        info = quotes.get(inst)
        if info is None:
            raise ValueError("MISSING_EXECUTION_INSTRUMENT")
        desired_delta = {
            m: existing_books[m].get(inst, ZERO) - account.pm_quantities.get(m, {}).get(inst, ZERO)
            for m in MANAGERS
        }
        buyers = {m: q for m, q in desired_delta.items() if q > ZERO}
        sellers = {m: -q for m, q in desired_delta.items() if q < ZERO}
        # Internal manager exchanges are hypothetical attribution moves, not
        # broker fills, and incur no external spread or fee.
        if info["session_open"] and info["supported"] and not account.breached:
            for buy in sorted(buyers):
                for sell in sorted(sellers):
                    cross = min(buyers[buy], sellers[sell])
                    if cross > ZERO:
                        account.internal_cross(inst, buy, sell, cross, info["mark"])
                        buyers[buy] -= cross
                        sellers[sell] -= cross
                        results.append(
                            {
                                "kind": "INTERNAL_CROSS",
                                "instrument": inst.key,
                                "buy": buy,
                                "sell": sell,
                                "quantity": str(cross),
                            }
                        )
        pending = {m: q for m, q in buyers.items() if q > ZERO}
        if not pending:
            pending = {m: -q for m, q in sellers.items() if q > ZERO}
        delta = sum(pending.values(), ZERO)
        if not delta:
            continue
        prior = account.quantities.get(inst, ZERO)
        # One reversal has two distinct legs; opening is suppressed when frozen.
        legs = []
        if prior and delta * prior < ZERO and abs(delta) > abs(prior):
            closing = -prior
            legs.append((closing, pending))
            opening = delta - closing
            if not _risk_frozen(account, meta, semantics_version):
                legs.append((opening, pending))
        else:
            legs.append((delta, pending))
        # Close and opening legs share one decision's capacity allowance.
        remaining_capacity = _round_zero(
            info["volume_base"] * policy.max_participation, info["lot"]
        )
        for leg_index, (leg, request) in enumerate(legs):
            if leg_index and account.quantities.get(inst, ZERO):
                # Never open the opposite side while the close is partial.
                break
            if account.breached:
                results.append(
                    {"kind": "REJECTED", "instrument": inst.key, "reason": "CONTRACTUAL_BREACH"}
                )
                break
            if _risk_frozen(account, meta, semantics_version) and (abs(prior + leg) > abs(prior)):
                results.append(
                    {
                        "kind": "REJECTED",
                        "instrument": inst.key,
                        "reason": "PAPER_SOFT_FREEZE_OPENING",
                    }
                )
                continue
            shares = {}
            remaining = abs(leg)
            for manager in sorted(request):
                portion = min(abs(request[manager]), remaining)
                if portion > ZERO:
                    shares[manager] = portion * (D("1") if leg > ZERO else D("-1"))
                    remaining -= portion
            if remaining:
                raise ValueError("REVERSAL_ALLOCATION_UNDERFUNDED")
            item = _model_fill(
                account,
                inst,
                leg,
                quotes,
                policy,
                shares,
                remaining_capacity=remaining_capacity,
            )
            results.append({"kind": "EXTERNAL_PAPER", "instrument": inst.key, **item})
            if "quantity" in item:
                remaining_capacity -= abs(number(item["quantity"]))
            prior = account.quantities.get(inst, ZERO)
            _latch(account, meta, policy)

    account.verify()
    for key in due:
        meta["pending"].pop(key, None)
    # Explicitly requeue partial closes/opens and closed/illiquid markets.
    # The next decision must acquire another fresh causal source state.
    retry_instruments = {
        Instrument.parse(action["instrument"])
        for action in results
        if action.get("kind") == "EXTERNAL_PAPER"
        and action.get("status") in ("PARTIAL", "NO_CAPACITY", "CLOSED_MARKET")
    }
    for manager in MANAGERS:
        for inst in retry_instruments:
            wanted = existing_books[manager].get(inst, ZERO)
            actual = account.pm_quantities.get(manager, {}).get(inst, ZERO)
            if wanted != actual:
                key = manager + "|" + inst.key
                meta["pending"].setdefault(
                    key, (_utc(now) + timedelta(seconds=BATCH_SECONDS)).isoformat()
                )
    meta["desired"] = _book_json(desired_original)
    meta["last_rebalance"] = now
    info = {
        "status": meta["status"],
        "due_events": sorted(due),
        "desired": _book_json(desired_original),
        "allowed": _book_json(existing_books),
        "coin_clamp_factors": coin_clamps,
        "portfolio_clamp_factor": str(portfolio_factor),
        "skipped_unlisted": skipped,
        "partial_book": bool(skipped),
        "actions": results,
        "paper_equity": str(account.equity),
        "paper_daily_start_balance": str(account.daily_start_balance),
        "risk_reason": meta["halt_reason"],
        "hypothetical": True,
        "authorized_for_live": False,
    }
    meta["last_report"] = info
    return info


class Combo2PaperTracker:
    """Durable, deterministic paper experiment; no remote transport at all."""

    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        started_at: str,
        source_subject_hashes: dict[str, str],
        policy: PaperPolicy | None = None,
    ):
        self.policy = policy or PaperPolicy()
        if not run_id or "/" in run_id or run_id in (".", ".."):
            raise ValueError("UNSAFE_RUN_ID")
        if set(source_subject_hashes) != set(MANAGERS) or any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
            for v in source_subject_hashes.values()
        ):
            raise ValueError("THREE_SHA256_SOURCE_IDENTITIES_REQUIRED")
        _utc(started_at)
        self.rulebook = _paper_rulebook(self.policy, started_at)
        self.manifest = {
            "run_id": run_id,
            "started_at": started_at,
            "policy": self.policy.manifest(),
            "policy_sha": digest(self.policy.manifest()),
            "source_subject_hashes": dict(sorted(source_subject_hashes.items())),
            "rulebook_sha": self.rulebook.sha,
        }
        self.ledger = Ledger(Path(root) / run_id)
        atomic_private(
            self.ledger.path / "manifest.json",
            json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode(),
        )
        self.account = Account.start(self.rulebook, started_at)
        self.meta = _fresh_state()
        self.head = "0" * 64
        self.restore()

    def _apply(self, account: Account, meta: dict, event: Event) -> dict:
        data = event.payload["input"]
        version = event.payload.get("combo2_semantics_version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("UNKNOWN_COMBO2_SEMANTICS")
        kind = event.kind
        if kind == "SOURCE_RECEIPT":
            manager, inst_key = data["manager"], data["instrument"]
            if manager not in MANAGERS:
                raise ValueError("UNKNOWN_COMBO2_MANAGER")
            _int_id(inst_key)
            prior = meta["receipts"].get(event.event_id)
            if prior is not None:
                raise ValueError("DUPLICATE_SOURCE_RECEIPT_ID")
            meta["receipts"][event.event_id] = event.first_known_at
            key = manager + "|" + inst_key
            if key not in meta["pending"]:
                meta["pending"][key] = (
                    _utc(event.first_known_at) + timedelta(seconds=BATCH_SECONDS)
                ).isoformat()
            return {"status": "SCHEDULED", "due": meta["pending"][key], "key": key}
        if kind == "PAPER_REBALANCE":
            return _run_rebalance(
                account,
                meta,
                data,
                event.decision_at,
                self.policy,
                self.manifest["source_subject_hashes"],
                semantics_version=version,
            )
        if kind == "PAPER_MARK":
            rows = data.get("markets")
            if not isinstance(rows, dict):
                raise ValueError("MISSING_MARKS")
            quotes = {}
            tracked = set(account.quantities) | {
                inst for book in account.pm_quantities.values() for inst, qty in book.items() if qty
            }
            for inst in tracked:
                quotes[inst] = _quote(
                    rows[inst.key], event.decision_at, self.policy, require_open=False
                )
            _mark_with_extremes(account, meta, quotes, event.decision_at, self.policy)
            return {"status": meta["status"], "equity": str(account.equity)}
        if kind == "PAPER_FUNDING":
            allocated = {m: number(v) for m, v in data["allocated"].items()}
            if set(allocated) - set(MANAGERS):
                raise ValueError("UNKNOWN_MANAGER_FUNDING")
            account.post_funding(number(data["amount"]), allocated)
            _latch(account, meta, self.policy)
            return {"status": "PAPER_FUNDING_RECORDED"}
        if kind == "OPERATOR_RESET":
            if not data.get("operator_ref") or not data.get("reconciled"):
                raise ValueError("OPERATOR_RECONCILIATION_REQUIRED")
            if meta["total_frozen"] or account.breached:
                raise ValueError("TOTAL_BREACH_NEVER_RESET")
            frozen_day = meta["frozen_daily_key"]
            if frozen_day is None or account.daily_key <= frozen_day:
                raise ValueError("DAILY_FREEZE_CANNOT_RESET_SAME_DAY")
            meta["frozen_daily_key"] = None
            meta["halt_reason"] = None
            meta["status"] = "ACTIVE_PAPER"
            return {"status": "PAPER_DAILY_LATCH_RESET"}
        raise ValueError("UNKNOWN_COMBO2_EVENT_KIND")

    def _state(self, account: Account, meta: dict) -> dict:
        return {"account": account.snapshot(), "meta": meta}

    def restore(self) -> dict:
        account = Account.start(self.rulebook, self.manifest["started_at"])
        meta = _fresh_state()
        rows = self.ledger.read()
        for row in rows:
            event = Event(**row["event"])
            if event.payload.get("manifest_sha") != digest(self.manifest):
                raise ValueError("RETROACTIVE_RUN_POLICY_CHANGE")
            result = self._apply(account, meta, event)
            if event.payload.get("post_state_sha") != digest(
                {
                    "state": self._state(account, meta),
                    "result": result,
                }
            ):
                raise ValueError("PAPER_REPLAY_POST_STATE_DIVERGENCE")
        self.account, self.meta = account, meta
        self.head = rows[-1]["sha"] if rows else "0" * 64
        return self.state()

    def record(
        self,
        *,
        kind: str,
        event_id: str,
        source_event_at: str,
        first_known_at: str,
        decision_at: str,
        hypothetical_fill_at: str,
        data: dict,
    ) -> dict:
        # The only public mutation is a local hash-chained event append.
        # No broker or HTTP transport exists on this object.
        old_rows = self.ledger.read()
        live_head = old_rows[-1]["sha"] if old_rows else "0" * 64
        if live_head != self.head:
            raise ValueError("STALE_PAPER_WRITER_RESTORE_FIRST")
        payload = {
            "input": data,
            "manifest_sha": digest(self.manifest),
            "combo2_semantics_version": 2,
        }
        proposal = Event(
            event_id=event_id,
            kind=kind,
            source_event_at=source_event_at,
            first_known_at=first_known_at,
            decision_at=decision_at,
            hypothetical_fill_at=hypothetical_fill_at,
            source_sha=digest(data),
            payload=payload,
        )
        proposal.validate()
        if _utc(decision_at) < _utc(self.manifest["started_at"]):
            raise ValueError("PAPER_EVENT_BEFORE_START")
        for row in old_rows:
            previous = dict(row["event"])
            if previous["event_id"] == event_id:
                for k in ("post_state_sha", "combo2_semantics_version"):
                    previous["payload"].pop(k, None)
                candidate = proposal.to_dict()
                candidate["payload"].pop("combo2_semantics_version", None)
                if previous != candidate:
                    raise ValueError("PAPER_DUPLICATE_EVENT_CONFLICT")
                return self.state()
        staged_account, staged_meta = deepcopy(self.account), deepcopy(self.meta)
        result = self._apply(staged_account, staged_meta, proposal)
        staged_account.verify()
        payload["post_state_sha"] = digest(
            {
                "state": self._state(staged_account, staged_meta),
                "result": result,
            }
        )
        sealed = Event(**{**proposal.to_dict(), "payload": payload})
        self.head = self.ledger.append(sealed, expected_head=live_head)
        self.account, self.meta = staged_account, staged_meta
        return self.state()

    def verified_paper_decisions(self) -> list[dict]:
        """Re-verify every post-state before exposing simulated decisions.

        This read-only projection has no broker, transport or SQLite writes.
        A caller may copy each verified paper result to a separate journal;
        the original hash-chained account stays the sole P&L authority.
        """
        account = Account.start(self.rulebook, self.manifest["started_at"])
        meta = _fresh_state()
        decisions = []
        for row in self.ledger.read():
            event = Event(**row["event"])
            if event.payload.get("manifest_sha") != digest(self.manifest):
                raise ValueError("PROJECTION_MANIFEST_MISMATCH")
            outcome = self._apply(account, meta, event)
            account.verify()
            if event.payload.get("post_state_sha") != digest(
                {"state": self._state(account, meta), "result": outcome}
            ):
                raise ValueError("PROJECTION_POST_STATE_DIVERGENCE")
            if event.kind == "PAPER_REBALANCE":
                decisions.append(
                    {
                        "run_id": self.manifest["run_id"],
                        "event_id": event.event_id,
                        "paper_event_sha": row["sha"],
                        "account_alias": self.policy.account_alias,
                        "report": deepcopy(outcome),
                    }
                )
        return decisions

    def state(self) -> dict:
        return {
            "schema": SCHEMA,
            "run_id": self.manifest["run_id"],
            "paper_only": True,
            "real_account_monitor": "SEPARATE_UNKNOWN",
            "propr_contract_verified": False,
            "scientifically_qualified": False,
            "live_trading_authorized": False,
            "journal_head": self.head,
            **self._state(self.account, self.meta),
        }
