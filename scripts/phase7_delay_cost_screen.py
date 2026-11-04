"""Bounded source-event first-event delay/cost screen; never an executable fill model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

if __package__:
    from scripts.phase7_conditional_stress import SCALES
    from scripts.phase7_native_exposure import BASE, END_MS, START_MS, source_files
else:
    from phase7_conditional_stress import SCALES
    from phase7_native_exposure import BASE, END_MS, START_MS, source_files

DELAYS = (0, 1, 2, 5, 10)
BASELINE_TOTAL_COST_BPS = 10.0


def batch_orders(events: list[tuple[int, float, float]], delay_seconds: int) -> list[tuple[int, float, float, int]]:
    """Non-resetting first-event window per wallet/instrument.

    Returns (decision_ms, net_qty, reference_price, n_fills). Market price is
    LAST LEADER FILL px, a pricing proxy, NOT the future executable price.
    Events may be censored at the retrospective window boundary.
    """
    if delay_seconds < 0:
        raise ValueError("negative delay")
    out = []
    if not events:
        return out
    events = sorted(events, key=lambda x: x[0])
    if delay_seconds == 0:
        return [(ms, qty, price, 1) for ms, qty, price in events if START_MS <= ms < END_MS]
    i = 0
    while i < len(events):
        first = events[i][0]
        deadline = first + delay_seconds * 1000
        qty = 0.0
        price = events[i][2]
        n = 0
        while i < len(events) and events[i][0] < deadline:
            qty += events[i][1]
            price = events[i][2]
            n += 1
            i += 1
        if not (START_MS <= deadline < END_MS):
            continue
        if abs(qty) > 1e-10:
            out.append((deadline, qty, price, n))
    return out


def study_one_source(fills: list[dict]) -> dict:
    groups = defaultdict(list)
    invalid = 0
    duplicated = 0
    seen = set()
    for f in fills:
        try:
            ms = int(f["time"])
            if not (START_MS <= ms < END_MS):
                continue
            coin = f["coin"]
            if ":" in coin or coin.startswith("@"):
                continue
            price = float(f["px"])
            size = float(f["sz"])
            side = f["side"]
            tid = f.get("tid")
            if side not in ("A", "B") or not all(map(math.isfinite, (price, size))) or price <= 0 or size <= 0:
                invalid += 1
                continue
            key = (coin, tid) if tid is not None else (coin, ms, price, size, side)
            if key in seen:
                duplicated += 1
                continue
            seen.add(key)
            groups[coin].append((ms, size * (1 if side == "B" else -1), price))
        except (ValueError, TypeError, KeyError, AttributeError):
            invalid += 1
    result = {"valid_events": sum(map(len, groups.values())), "invalid": invalid,
              "duplicates": duplicated, "scope": "VERIFIED_MAIN_PERP_SOURCE_EVENT_PROXY"}
    for delay in DELAYS:
        n_batches = 0
        sum_notional = 0.0
        cancelled = 0
        for events in groups.values():
            orders = batch_orders(events, delay * 60)
            n_batches += len(orders)
            sum_notional += sum(abs(qty) * px for _, qty, px, _ in orders)
            cancelled += sum(1 for x in orders if x[3] > 1)
        result[str(delay)] = {
            "orders": n_batches,
            "source_notional_proxy_usd": round(sum_notional, 2),
            "multi_source_event_orders": cancelled,
        }
    return result


def run(root: Path) -> dict:
    files = source_files(root)
    all_members = sorted({w for scales in SCALES.values() for w in scales})
    wallet_metrics = {}
    for alias in all_members:
        if alias not in files:
            wallet_metrics[alias] = {"status": "NO_RAW_MAIN_PERP_FILLS"}
            continue
        source = files[alias]
        data = json.loads(source.read_text())
        wallet_metrics[alias] = {**study_one_source(data.get("fills", [])),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    portfolios = {}
    for name, scales in SCALES.items():
        results = {}
        for delay in DELAYS:
            n_orders, notional = 0, 0.0
            missing = []
            for alias, k in scales.items():
                stats = wallet_metrics[alias]
                if "valid_events" not in stats:
                    missing.append(alias)
                    continue
                n_orders += stats[str(delay)]["orders"]
                notional += k * stats[str(delay)]["source_notional_proxy_usd"]
            results[str(delay)] = {
                "estimated_market_orders": n_orders,
                "conditional_follower_traded_notional_usd": round(notional, 2),
                "illustrative_1x_cost_10bps_usd": round(notional * 0.001, 2),
                "illustrative_2x_cost_20bps_usd": round(notional * 0.002, 2),
                "illustrative_3x_cost_30bps_usd": round(notional * 0.003, 2),
                "missing_source_wallets": missing,
                "realized_follower_pnl": None,
                "native_market_executable_price": None,
                "first_known_source_receipt": None,
            }
        portfolios[name] = results
    return {
        "schema": "phase7_frozen_k_retrospective_first_event_batch_cost_v1",
        "frozen_model_k_source": "GEMINI_PHASE6A_RESEARCH_REFERENCE_ONLY",
        "decision_clock": "HISTORICAL_EVENT_PLUS_DELAY_NOT_LOCAL_RECEIPT",
        "policy": "NON_RESETTING_FIRST_EVENT_BATCH_PER_WALLET_PER_COIN",
        "prices": "LAST_LEADER_FILL_PROXY_NOT_FUTURE_NATIVE_EXECUTION",
        "total_cost_bps_hypothetical": [10, 20, 30],
        "source_wallets": wallet_metrics,
        "portfolios": portfolios,
        "scientifically_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=BASE / "data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(run(args.source_root), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("immutable output already exists")
        args.output.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
