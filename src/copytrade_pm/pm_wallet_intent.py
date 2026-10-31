"""Copy one wallet's intent onto a hypothetical follower account.

Intent source: hourly account summary (equity, margin used) plus hourly
position snapshots. Three sizing modes express what "their sizing relative to
their margin" can mean; the caller chooses one explicitly.

Everything here is a hypothetical mark-to-market replay. It never places an
order, never reads a broker credential and never claims the source wallet's
fills are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D
import json
from pathlib import Path

from .pm03_account import Account, Instrument, Rulebook

ZERO = D(0)
BPS = D(10000)


@dataclass(frozen=True)
class Position:
    symbol: str
    side: str
    notional: D
    size: D
    mark: D

    @property
    def sign(self) -> D:
        return D(1) if self.side == "long" else D(-1)


@dataclass(frozen=True)
class Hour:
    ts: str
    equity: D
    margin_used: D
    positions: tuple[Position, ...]

    @property
    def book(self) -> D:
        return sum((p.notional for p in self.positions), ZERO)


def load_intent(path: Path) -> tuple[Hour, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for row in payload["rows"]:
        positions = tuple(
            Position(
                symbol=p["symbol"],
                side=p["side"],
                notional=D(str(p["position_value"])),
                size=D(str(p["size"])),
                mark=D(str(p["mark"])),
            )
            for p in row.get("positions", ())
        )
        rows.append(
            Hour(
                ts=row["ts"],
                equity=D(str(row["equity"])),
                margin_used=D(str(row.get("margin_used", "0"))),
                positions=positions,
            )
        )
    rows.sort(key=lambda h: h.ts)
    return tuple(rows)


def scale_for(hour: Hour, capital: D, k: D, mode: str, target_leverage: D = D(1)) -> D:
    """Notional multiplier applied to every source position."""
    if mode == "equity":
        if hour.equity <= ZERO:
            return ZERO
        return capital * k / hour.equity
    if mode == "margin":
        if hour.margin_used <= ZERO:
            return ZERO
        return capital * k / hour.margin_used
    if mode == "weight":
        book = hour.book
        if book <= ZERO:
            return ZERO
        return capital * target_leverage * k / book
    raise ValueError("UNKNOWN_SIZING_MODE")


def _hours(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _floor_kinds(floors: dict[str, D], floor: D | None) -> list[str]:
    if floor is None:
        return []
    return sorted(name.upper() for name, value in floors.items() if value == floor)


def simulate(
    rows: tuple[Hour, ...],
    *,
    capital: D = D("10000"),
    k: D = D("1"),
    mode: str = "margin",
    target_leverage: D = D("1"),
    fee_bps: D = D("5"),
    profit_target: D = D("0.05"),
    daily_loss: D = D("0.05"),
    trailing_loss: D = D("0.08"),
    venue: str = "hyperliquid",
    market: str = "mainnet",
) -> dict[str, object]:
    """Follower equity path on the PM-03 account model.

    Fails closed on a non-hourly intent gap or a missing mark. Breach uses the
    PM-03 contractual floor (daily / static / trailing capped at initial
    balance, equality included) and halts the run at the first breach.
    """
    if not rows:
        raise ValueError("EMPTY_INTENT")
    rulebook = Rulebook(
        program="classic_2step",
        stage="step1",
        source="pm_wallet_intent",
        observed_at=rows[0].ts,
        version="intent-follower-v1",
        timezone="UTC",
        initial_balance=capital,
        profit_target=capital * profit_target,
        daily_loss=None,
        static_loss=None,
        daily_loss_rate=daily_loss,
        trailing_loss=capital * trailing_loss,
        trailing_cap=capital,
        confirmed=False,
    )
    account = Account.start(rulebook, rows[0].ts)
    manager = "WALLET"
    account.pm_quantities[manager] = {}
    account.pm_cash[manager] = ZERO

    def instrument(symbol: str) -> Instrument:
        return Instrument(venue, market, symbol)

    last_mark: dict[str, D] = {}
    stale_closes = 0
    peak = capital
    observed_dd = ZERO
    day = rows[0].ts[:10]
    day_start = capital
    max_day_loss = ZERO
    status = "COMPLETE"
    breach = None
    target_at = None
    steps = 0

    previous: str | None = None
    for hour in rows:
        if previous is not None:
            gap = (_hours(hour.ts) - _hours(previous)).total_seconds()
            if gap != 3600:
                return {
                    "status": "BLOCKED_INTENT_GAP",
                    "gap_seconds": gap,
                    "at": hour.ts,
                    "hypothetical": True,
                }
        previous = hour.ts
        book = {p.symbol: p for p in hour.positions}
        for symbol, position in book.items():
            if position.mark <= ZERO:
                raise ValueError("INVALID_MARK")
            last_mark[symbol] = position.mark
        # Close anything the source no longer reports, at its last observed
        # mark. The substitution is counted, never silent.
        for held in sorted(set(i.symbol for i in account.quantities) - set(book)):
            price = last_mark.get(held)
            if price is None:
                return {
                    "status": "BLOCKED_MISSING_MARK",
                    "symbol": held,
                    "at": hour.ts,
                    "hypothetical": True,
                }
            delta = -account.quantities[instrument(held)]
            fee = abs(delta) * price * fee_bps / BPS
            account.simulate_fill(
                instrument(held), delta, price, fee, accepted=True, allocated={manager: delta}
            )
            stale_closes += 1
        account.mark({instrument(s): p.mark for s, p in book.items()}, hour.ts)
        steps += 1
        peak = max(peak, account.equity)
        if peak > ZERO:
            observed_dd = max(observed_dd, (peak - account.equity) / peak)
        if hour.ts[:10] != day:
            day = hour.ts[:10]
            day_start = account.equity
        if day_start > ZERO:
            max_day_loss = max(max_day_loss, (day_start - account.equity) / day_start)
        if account.breached:
            floor, floors = account.floor()
            status = "BREACHED"
            breach = {
                "ts": hour.ts,
                "equity": str(account.equity),
                "floor": str(floor),
                "kinds": _floor_kinds(floors, floor),
            }
            break
        if account.stage_passed:
            status = "PASSED"
            target_at = {"ts": hour.ts, "equity": str(account.equity)}
            break
        scale = scale_for(hour, capital, k, mode, target_leverage)
        targets = {
            symbol: position.sign * position.notional * scale / position.mark
            for symbol, position in book.items()
        }
        held = {i.symbol: q for i, q in account.quantities.items()}
        for symbol in sorted(set(held) | set(targets)):
            delta = targets.get(symbol, ZERO) - held.get(symbol, ZERO)
            if delta == ZERO:
                continue
            price = book[symbol].mark if symbol in book else last_mark[symbol]
            fee = abs(delta) * price * fee_bps / BPS
            account.simulate_fill(
                instrument(symbol), delta, price, fee, accepted=True, allocated={manager: delta}
            )
            stale_closes += 0 if symbol in book else 1
    floor, floors = account.floor()
    return {
        "status": status,
        "mode": mode,
        "k": str(k),
        "capital": str(capital),
        "hours": steps,
        "window": [rows[0].ts, rows[-1].ts],
        "final_equity": str(account.equity),
        "balance": str(account.balance),
        "return": str((account.equity - capital) / capital),
        "observed_max_drawdown": str(observed_dd),
        "max_day_loss": str(max_day_loss),
        "fees": str(account.costs),
        "floors": {name: str(value) for name, value in floors.items()},
        "floor": str(floor),
        "breach": breach,
        "profit_target_hit": target_at,
        "stale_closes": stale_closes,
        "hypothetical": True,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Copy one wallet's intent onto a follower account."
    )
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--capital", default="10000")
    parser.add_argument("--k", default="1")
    parser.add_argument("--mode", choices=("equity", "margin", "weight"), default="equity")
    parser.add_argument("--target-leverage", default="1")
    parser.add_argument("--fee-bps", default="5")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = simulate(
        load_intent(args.intent),
        capital=D(args.capital),
        k=D(args.k),
        mode=args.mode,
        target_leverage=D(args.target_leverage),
        fee_bps=D(args.fee_bps),
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
