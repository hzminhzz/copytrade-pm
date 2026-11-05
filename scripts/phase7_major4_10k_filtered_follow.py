"""Exploratory $10k four-market follower replay for Phase 7 M3/M4/M5.

Hypothetical event-time + 5m delayed signal, next full minute OPEN; no
historical first-known receipts. Equal per-wallet fraction of $6k gross cap.
Uses SHA-pinned historical fills and exact-day native Hyperliquid OHLCV. Raw
startPosition is used only when directly available on the fill; CSV leaders
are directional open/close reconstructed from a *zero-assumed* window start.

This is NOT source-equity-faithful copying nor full-wallet PnL. Exactly four
default-perp symbols BTC/ETH/SOL/HYPE; all other trades are excluded under
an explicitly hypothetical instrument-filtering policy.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import csv
import gzip
import json
import math
from pathlib import Path

import numpy as np

from copytrade_pm.pm_offline_market import _verified_day
from scripts.phase7_major4_portfolio_screen import (
    CSV_SOURCES,
    EXPERIMENTS,
    MAJORS,
    RAW_SOURCES,
    _sha,
    registry_addresses,
)

START_MS = 1785888000000  # Aug 5 2026 UTC
END_MS = 1793664000000  # Nov 3 2026 00:00 UTC exclusive
MINUTE_MS = 60_000
N = (END_MS - START_MS) // MINUTE_MS
N_DAYS = N // 1440
EQUITY_USD = 10_000.0
GROSS_BUDGET_USD = 6_000.0
DEFAULT_COSTS = (10, 20, 30)
SOURCE_ROOT = Path("/home/quant/dev/copytrade-pm")
MARKET_ROOT = Path("/home/quant/dev/quant/ml4t-data/.data/store")
MAX_EVENTS = 80_000
MAX_ABS_SOURCE_POSITION = 1e14


def source_members(universe: dict, db: Path) -> tuple[dict, dict]:
    present, excluded, generation = registry_addresses(db)
    addresses = {x["address"].lower(): x for x in universe.get("wallets", [])}
    selected = set.union(*(set(a) for a in EXPERIMENTS.values()))
    by_alias = {}
    for alias in selected:
        matches = [x for x in addresses.values() if x["alias"] == alias]
        if len(matches) != 1:
            raise ValueError("AMBIGUOUS_UNIVERSE_WALLET_ALIAS")
        w = matches[0]
        if w["address"].lower() not in present or w["address"].lower() in excluded:
            raise ValueError("NOT_CURRENT_REGISTERED_RESEARCH_WALLET")
        if w["recommendation"] != "CANDIDATE_UNVERIFIED":
            raise ValueError("UNSUPPORTED_SOURCE_WALLET_STATUS")
        by_alias[alias] = w
    if len({x["address"].lower() for x in by_alias.values()}) != len(by_alias):
        raise ValueError("DUPLICATED_PHYSICAL_WALLET")
    return by_alias, generation


def _parse_ms(value: str | int) -> int:
    if isinstance(value, int):
        return value
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.astimezone(UTC).timestamp() * 1000)


def _number(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_{name}") from exc
    if not math.isfinite(number):
        raise ValueError(f"NONFINITE_{name}")
    return number


def parse_fill(row: dict, *, alias: str, raw: bool, row_index: int) -> dict | None:
    coin = row.get("coin")
    if coin not in MAJORS:
        return None
    timestamp = _parse_ms(row["time"] if raw else row["datetime_utc"])
    if not START_MS <= timestamp < END_MS:
        return None
    size = _number(row["sz"] if raw else row["size"], "FILL_SIZE")
    price = _number(row["px"] if raw else row["price"], "FILL_PRICE")
    if not size > 0 or not price > 0:
        raise ValueError("INVALID_SOURCE_FILL_PRICE_OR_SIZE")
    side = row["side"]
    direction = row["dir"]
    if side not in ("B", "A") or direction not in (
        "Open Long",
        "Close Long",
        "Open Short",
        "Close Short",
        "Long > Short",
        "Short > Long",
    ):
        raise ValueError("UNSUPPORTED_SOURCE_FILL_SIDE_OR_DIR")
    if direction in ("Open Long", "Close Short", "Short > Long") and side != "B":
        raise ValueError("SOURCE_DIR_AND_SIDE_CONFLICT")
    if direction in ("Open Short", "Close Long", "Long > Short") and side != "A":
        raise ValueError("SOURCE_DIR_AND_SIDE_CONFLICT")
    start = row.get("startPosition", row.get("start_position")) if raw else None
    if start is not None and start != "":
        start = _number(start, "START_POSITION")
    else:
        start = None
    return {
        "alias": alias,
        "coin": coin,
        "ms": timestamp,
        "size": size,
        "price": price,
        "side": side,
        "dir": direction,
        "start": start,
        "row_order": row_index,
        "source_tid": row.get("tid") if raw else None,
    }


def _recover_anchored_timestamp_order(
    events: list[dict],
) -> tuple[list[dict], dict]:
    """Recover a unique complete position chain within each same-ms group.

    Raw source TID and file row order are not guaranteed execution order.
    Each raw fill with startPosition is a directed edge (before -> after).
    A unique Eulerian trail, anchored by a unique start/end, is required;
    ambiguous or disconnected groups fail closed. Never order by TID.
    """
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for event in events:
        groups[(event["ms"], event["coin"])].append(event)
    ordered: list[dict] = []
    previous_end: dict[str, float] = {}
    audit = Counter()
    for (ms, coin), batch in sorted(groups.items()):
        if len(batch) == 1:
            path = batch
        else:
            audit["multi_fill_same_ms_groups"] += 1
            audit["source_rows_in_same_ms_groups"] += len(batch)
            from_counts: Counter[float] = Counter()
            to_counts: Counter[float] = Counter()
            edges = defaultdict(list)
            for event in batch:
                if event["start"] is None:
                    raise ValueError("UNRESOLVED_SOURCE_SAME_MS_MISSING_START_POSITION")
                before = round(event["start"], 8)
                after = round(
                    event["start"] + event["size"] * (1 if event["side"] == "B" else -1), 8
                )
                if before == after:
                    raise ValueError("UNRESOLVED_SOURCE_QUANTITY_PRECISION")
                edges[before].append((event["row_order"], after, event))
                from_counts[before] += 1
                to_counts[after] += 1
            nodes = set(from_counts) | set(to_counts)
            starts = [p for p in nodes if from_counts[p] - to_counts[p] == 1]
            ends = [p for p in nodes if to_counts[p] - from_counts[p] == 1]
            if (
                len(starts) != 1
                or len(ends) != 1
                or any(abs(from_counts[x] - to_counts[x]) > 1 for x in nodes)
            ):
                raise ValueError("AMBIGUOUS_SAME_MS_SOURCE_POSITION_GRAPH")
            for outgoing in edges.values():
                outgoing.sort(key=lambda x: x[0], reverse=True)
            stack: list[tuple[float, dict | None]] = [(starts[0], None)]
            backwards = []
            while stack:
                node, incoming = stack[-1]
                if edges[node]:
                    _, after, fill = edges[node].pop()
                    stack.append((after, fill))
                else:
                    stack.pop()
                    if incoming is not None:
                        backwards.append(incoming)
            path = list(reversed(backwards))
            if len(path) != len(batch):
                raise ValueError("DISCONNECTED_SAME_MS_SOURCE_POSITION_GRAPH")
            for before, after in zip(path, path[1:]):
                ending = round(
                    before["start"] + before["size"] * (1 if before["side"] == "B" else -1),
                    8,
                )
                if ending != round(after["start"], 8):
                    raise ValueError("NONCONTIGUOUS_SAME_MS_SOURCE_POSITION_GRAPH")
            if round(path[0]["start"], 8) != starts[0]:
                raise ValueError("SOURCE_SAME_MS_GRAPH_START_MISMATCH")
            terminal = round(
                path[-1]["start"] + path[-1]["size"] * (1 if path[-1]["side"] == "B" else -1),
                8,
            )
            if terminal != ends[0]:
                raise ValueError("SOURCE_SAME_MS_GRAPH_END_MISMATCH")
            audit["restored_same_ms_groups"] += 1

        start = path[0]["start"]
        if start is not None and coin in previous_end:
            if abs(start - previous_end[coin]) > 1e-6 * max(1, abs(start)):
                audit["between_timestamp_source_position_gaps"] += 1
        tail = path[-1]
        if tail["start"] is not None:
            previous_end[coin] = tail["start"] + tail["size"] * (1 if tail["side"] == "B" else -1)
        ordered.extend(path)
    if audit["between_timestamp_source_position_gaps"]:
        raise ValueError("RAW_FILL_POSITION_CHAIN_NOT_CONTINUOUS")
    return ordered, dict(audit)


def load_fills(
    source_dir: Path,
    universe: dict,
    by_alias: dict,
) -> tuple[dict[str, list[dict]], dict]:
    """All original sources remain read-only and byte-hash pinned."""
    source_expected = universe.get("source_sha256")
    if not isinstance(source_expected, dict):
        raise ValueError("NO_FROZEN_SOURCE_SHA_CATALOG")
    by_address = {x["address"].lower(): x for x in by_alias.values()}
    rows = {alias: [] for alias in by_alias}
    origins = {}
    raw_tid = defaultdict(set)
    csv_row_duplicates = Counter()
    counts = Counter()
    raw_continuity_audit = {}
    for directory in sorted(RAW_SOURCES):
        for file in sorted((source_dir / "data" / directory).glob("*.json")):
            # Strict address from file contents; never infer from path alias.
            payload = json.loads(file.read_bytes())
            wallet = by_address.get(str(payload.get("address") or "").lower())
            if wallet is None or wallet["source"] != directory:
                continue
            key = f"{directory}/{file.name}"
            if _sha(file) != source_expected.get(key):
                raise ValueError("FROZEN_RAW_SOURCE_SHA_DRIFT")
            alias = wallet["alias"]
            if alias in origins:
                raise ValueError("MULTIPLE_RAW_VERSIONS_FOR_WALLET")
            origins[alias] = {"source": key, "sha256": source_expected[key]}
            for idx, item in enumerate(payload["fills"]):
                event = parse_fill(item, alias=alias, raw=True, row_index=idx)
                if event is None:
                    continue
                identity = (event["coin"], str(event["source_tid"]))
                if event["source_tid"] is None or identity in raw_tid[alias]:
                    raise ValueError("DUPLICATE_OR_MISSING_EXCHANGE_TID")
                raw_tid[alias].add(identity)
                rows[alias].append(event)
            counts["raw_files"] += 1

    for source, name in CSV_SOURCES.items():
        needed = {addr: wallet for addr, wallet in by_address.items() if wallet["source"] == source}
        if not needed:
            continue
        file = source_dir / "docs" / name
        expected = source_expected.get(f"docs/{name}")
        if expected is None or _sha(file) != expected:
            raise ValueError("FROZEN_CSV_SOURCE_SHA_DRIFT")
        seen_row_by_alias = defaultdict(set)
        with gzip.open(file, "rt", newline="") as stream:
            for idx, row in enumerate(csv.DictReader(stream)):
                wallet = needed.get(str(row.get("address") or "").lower())
                if wallet is None:
                    continue
                alias = wallet["alias"]
                if alias not in origins:
                    origins[alias] = {"source": f"docs/{name}", "sha256": expected}
                event = parse_fill(row, alias=alias, raw=False, row_index=idx)
                if event is None:
                    continue
                # CSV has no exchange TID. Keep all rows; record ambiguity
                # instead of deleting identical records without evidence.
                key = (
                    event["coin"],
                    event["ms"],
                    event["dir"],
                    event["side"],
                    event["size"],
                    event["price"],
                )
                if key in seen_row_by_alias[alias]:
                    csv_row_duplicates[alias] += 1
                seen_row_by_alias[alias].add(key)
                rows[alias].append(event)
        counts["csv_files"] += 1
    if set(origins) != set(by_alias):
        raise ValueError("MISSING_SOURCE_FILL_FILE")
    for alias, events in rows.items():
        if not events:
            raise ValueError("WALLET_NO_EXACT_FOUR_COIN_FILLS")
        if len(events) > MAX_EVENTS:
            raise ValueError("UNBOUNDED_WALLET_FILL_EVENTS")
        if by_alias[alias]["source"] in RAW_SOURCES:
            ordered, fidelity = _recover_anchored_timestamp_order(events)
            rows[alias] = ordered
            raw_continuity_audit[alias] = fidelity
        else:
            # CSV-only ties retain original vendor row order; no invented TID.
            events.sort(key=lambda x: (x["ms"], x["row_order"]))
    audit = {
        "sources_by_alias": origins,
        "total_four_market_fills": sum(map(len, rows.values())),
        "counts_by_alias": {a: len(v) for a, v in sorted(rows.items())},
        "exact_identical_csv_rows_ambiguous_by_alias": dict(csv_row_duplicates),
        "sources_loaded": dict(counts),
        "raw_timestamp_position_chain_reconciliation": raw_continuity_audit,
    }
    return rows, audit


def verified_bars(store: Path) -> tuple[dict, dict]:
    """Read 90 full UTC days, native SHA verified, no fill-forward."""
    ret = {}
    provenance = {}
    first = datetime.fromtimestamp(START_MS / 1000, UTC)
    for coin in MAJORS:
        data = {
            key: np.full(N, np.nan, dtype=np.float64) for key in ("open", "high", "low", "close")
        }
        hashes = sha256()
        for daynum in range(N_DAYS):
            date = first + timedelta(days=daynum)
            frame, digest, meta_digest = _verified_day(
                store, f"hyperliquid:mainnet:perp:default:{coin}", date
            )
            if frame.height != 1440 or frame["timestamp"].n_unique() != 1440:
                raise ValueError("INCOMPLETE_NATIVE_ONE_MINUTE_DAY")
            ms = frame["timestamp"].dt.epoch("ms").to_numpy()
            expected = START_MS + (daynum * 1440 + np.arange(1440)) * MINUTE_MS
            if not np.array_equal(ms, expected):
                raise ValueError("MISSING_OR_SHIFTED_NATIVE_ONE_MINUTE_GRID")
            start = daynum * 1440
            for key in data:
                data[key][start : start + 1440] = frame[key].to_numpy()
            hashes.update(f"{coin}:{date.date()}:{digest}:{meta_digest}\n".encode())
        if any(~np.isfinite(x).all() for x in data.values()):
            raise ValueError("UNVERIFIED_OR_NONFINITE_NATIVE_PRICE")
        ret[coin] = data
        provenance[coin] = {
            "sha_verification_days": N_DAYS,
            "day_sha_fingerprint": hashes.hexdigest(),
        }
    return ret, provenance


def _source_update(q: float, event: dict, audit: Counter, *, source_mode: str) -> float:
    """Raw observed startPosition is authoritative; otherwise infer episodes.

    A CSV close without earlier observed open is not interpreted as a new short.
    """
    size, side, direction, anchor = (event["size"], event["side"], event["dir"], event["start"])
    if source_mode == "anchored_or_episode" and anchor is not None:
        post = anchor + size * (1 if side == "B" else -1)
        if not math.isfinite(post) or abs(post) > MAX_ABS_SOURCE_POSITION:
            raise ValueError("CORRUPT_EXPLICIT_START_POSITION")
        coin_anchor_key = "anchored_events_" + event["coin"]
        if abs(q - anchor) > 1e-5 * max(1, abs(anchor)) and audit[coin_anchor_key] > 0:
            audit["explicit_position_chain_discontinuities"] += 1
        audit[coin_anchor_key] += 1
        audit["anchored_events"] += 1
        return 0.0 if abs(post) < 1e-10 else post

    if source_mode == "signed_delta":
        post = q + size * (1 if side == "B" else -1)
        return 0.0 if abs(post) < 1e-10 else post

    audit["episode_inferred_events"] += 1
    if direction == "Open Long" and q >= -1e-9:
        return max(0, q) + size
    if direction == "Open Short" and q <= 1e-9:
        return min(0, q) - size
    if direction == "Close Long" and q > 0:
        if size > q + 1e-8:
            audit["overclosing_unanchored_episode"] += 1
        return max(0, q - size)
    if direction == "Close Short" and q < 0:
        if size > -q + 1e-8:
            audit["overclosing_unanchored_episode"] += 1
        return min(0, q + size)
    if direction == "Long > Short" and q > 0:
        return q - size
    if direction == "Short > Long" and q < 0:
        return q + size
    audit["unknown_preexisting_close_or_unmatched_side"] += 1
    return q


def _remove_csv_exact_duplicates(events: list[dict]) -> list[dict]:
    """Sensitivity ONLY: CSV lacks TID; identical rows might be real trades."""
    seen: set[tuple] = set()
    filtered = []
    for event in events:
        if event["source_tid"] is not None:
            filtered.append(event)
            continue
        identity = (
            event["coin"],
            event["ms"],
            event["dir"],
            event["side"],
            event["size"],
            event["price"],
        )
        if identity in seen:
            continue
        seen.add(identity)
        filtered.append(event)
    return filtered


def model_wallet(
    fills: list[dict],
    bars: dict,
    *,
    delay_minutes: int = 5,
    source_mode: str = "anchored_or_episode",
    batch_minutes: int = 1,
) -> dict:
    """Per-$1 gross-budget profit/turnover arrays; no execution certification."""
    if (
        delay_minutes not in (0, 5, 10)
        or batch_minutes not in (1, 5)
        or source_mode not in ("anchored_or_episode", "signed_delta")
    ):
        raise ValueError("UNREGISTERED_SENSITIVITY_MODEL")
    scheduled = defaultdict(list)
    for item in fills:
        # Strictly after event + hypothetical delay. The five-minute grid
        # collapses all source fills received within its execution window.
        index = (
            (item["ms"] + delay_minutes * MINUTE_MS - START_MS) // (batch_minutes * MINUTE_MS) + 1
        ) * batch_minutes
        if 0 <= index < N:
            scheduled[int(index)].append(item)
    states = {coin: 0.0 for coin in MAJORS}
    audit = Counter()
    pos = {coin: np.zeros(N, dtype=np.float64) for coin in MAJORS}
    prior_idx = 0
    prior_qty = {coin: 0.0 for coin in MAJORS}
    for idx, items in sorted(scheduled.items()):
        if idx < prior_idx:
            raise ValueError("SOURCE_EVENT_CLOCK_NOT_MONOTONIC")
        for coin in MAJORS:
            pos[coin][prior_idx:idx] = prior_qty[coin]
        for item in items:
            coin = item["coin"]
            states[coin] = _source_update(states[coin], item, audit, source_mode=source_mode)
        # The follower follows *relative inferred source book weights*,
        # never isolated fixed-size per-fill buy/sell directions.
        dollar = {coin: states[coin] * bars[coin]["open"][idx] for coin in MAJORS}
        gross = sum(abs(v) for v in dollar.values())
        targets = {
            coin: (dollar[coin] / gross) / bars[coin]["open"][idx] if gross > 0 else 0.0
            for coin in MAJORS
        }
        for coin in MAJORS:
            if abs(targets[coin]) > MAX_ABS_SOURCE_POSITION:
                raise ValueError("INVALID_FOLLOWER_TARGET")
        prior_idx = idx
        prior_qty = targets
        audit["execution_batches"] += 1
        audit["source_events_processed"] += len(items)
    for coin in MAJORS:
        pos[coin][prior_idx:] = prior_qty[coin]

    pnl_minute = np.zeros(N, dtype=np.float64)
    worst_minute = np.zeros(N, dtype=np.float64)
    turnover_minute = np.zeros(N, dtype=np.float64)
    max_abs_gross = np.zeros(N, dtype=np.float64)
    for coin in MAJORS:
        q = pos[coin]
        old = np.concatenate(([0.0], q[:-1]))
        open_price = bars[coin]["open"]
        close_price = bars[coin]["close"]
        gap = np.zeros(N, dtype=np.float64)
        gap[1:] = old[1:] * (open_price[1:] - close_price[:-1])
        pnl_minute += gap + q * (close_price - open_price)
        low, high = bars[coin]["low"], bars[coin]["high"]
        adverse = np.where(q >= 0, low, high)
        worst_minute += gap + q * (adverse - open_price)
        turnover_minute += np.abs(q - old) * open_price
        max_abs_gross += np.abs(q * close_price)
    # Terminal market-close flatten, not an actual leader closing fill.
    terminal_turnover = sum(abs(pos[coin][-1] * bars[coin]["close"][-1]) for coin in MAJORS)
    turnover_minute[-1] += terminal_turnover
    audit["terminal_unclosed_source_legs"] = sum(abs(x) > 1e-10 for x in states.values())
    audit["unexecuted_tail_source_events"] = len(fills) - audit["source_events_processed"]
    audit["max_unit_gross_from_price_drift"] = round(float(max_abs_gross.max()), 5)
    audit["terminal_liquidation_unit_notional"] = round(terminal_turnover, 7)
    return {
        "pnl_delta_per_budget_usd": pnl_minute,
        "worst_bar_delta_per_budget_usd": worst_minute,
        "turnover_per_budget_usd": turnover_minute,
        "audit": dict(audit),
    }


def _metrics(pnl: np.ndarray, worst: np.ndarray, turnover: np.ndarray, *, cost_bps: int) -> dict:
    """Portfolio cash equity starts 10k, no stop/kill on reference breach."""
    net_delta = pnl - turnover * cost_bps / 10_000
    equity = EQUITY_USD + np.cumsum(net_delta)
    start_equity = np.concatenate(([EQUITY_USD], equity[1439:-1:1440]))
    daily_ref = np.repeat(start_equity, 1440)
    cum_peak = np.maximum.accumulate(np.concatenate(([EQUITY_USD], equity)))[1:]
    dd = cum_peak - equity
    # Pessimistic synchronous per-coin bar extremes, not actual aligned ticks.
    worst_equity = equity - net_delta + worst - turnover * cost_bps / 10_000
    worst_drawdown = cum_peak - worst_equity
    worst_day = float(np.min(worst_equity - daily_ref))
    daily_low = (worst_equity - daily_ref).reshape(N_DAYS, 1440).min(axis=1)
    breach_idx = np.flatnonzero((worst_drawdown >= 850) | ((worst_equity - daily_ref) <= -450))
    final = float(equity[-1])
    daily_net = net_delta.reshape(N_DAYS, 1440).sum(axis=1)
    blocks = [
        round(float(daily_net[first : first + 30].sum()), 2) for first in range(0, N_DAYS, 30)
    ]
    return {
        "starting_equity_usd": EQUITY_USD,
        "ending_equity_usd": round(final, 2),
        "net_pnl_usd": round(final - EQUITY_USD, 2),
        "return_pct": round((final / EQUITY_USD - 1) * 100, 3),
        "gross_mark_pnl_usd": round(float(pnl.sum()), 2),
        "gross_notional_turnover_usd": round(float(turnover.sum()), 2),
        "modeled_composite_cost_usd": round(float(turnover.sum()) * cost_bps / 10_000, 2),
        "max_drawdown_close_only_usd": round(float(dd.max()), 2),
        "max_drawdown_worst_bar_bound_usd": round(float(worst_drawdown.max()), 2),
        "worst_worst_bar_day_from_utc_start_usd": round(worst_day, 2),
        "days_worst_bar_daily_loss_at_least_450": int(np.sum(daily_low <= -450)),
        "earliest_model_reference_breach_minute": int(breach_idx[0]) if breach_idx.size else None,
        "earliest_model_reference_breach_at_utc": (
            datetime.fromtimestamp(
                (START_MS + int(breach_idx[0]) * MINUTE_MS) / 1000, UTC
            ).isoformat()
            if breach_idx.size
            else None
        ),
        "equity_worst_bar_at_first_reference_breach_usd": (
            round(float(worst_equity[breach_idx[0]]), 2) if breach_idx.size else None
        ),
        "illustrative_prop_loss_reference_breached": bool(breach_idx.size),
        "positive_calendar_days_count": int(np.sum(daily_net > 0)),
        "in_sample_30d_net_pnl_blocks_usd": blocks,
        "in_sample_30d_blocks_positive_count": sum(x > 0 for x in blocks),
        "break_even_composite_cost_bps_in_sample": (
            round(float(pnl.sum() / turnover.sum() * 10_000), 3) if turnover.sum() > 0 else None
        ),
        "priced_market_days": N_DAYS,
    }


def evaluate(
    universe_path: Path,
    root: Path,
    db: Path,
    market: Path,
    *,
    delay_values: tuple[int, ...] = (0, 5, 10),
) -> dict:
    raw = universe_path.read_bytes()
    universe = json.loads(raw)
    members, generation = source_members(universe, db)
    input_events, source_audit = load_fills(root, universe, members)
    prices, market_audit = verified_bars(market)
    models = {
        f"{source_mode}:{delay}": {
            alias: model_wallet(fills, prices, delay_minutes=delay, source_mode=source_mode)
            for alias, fills in input_events.items()
        }
        for source_mode in ("anchored_or_episode", "signed_delta")
        for delay in delay_values
    }
    for source_mode in ("anchored_or_episode", "signed_delta"):
        models[f"{source_mode}:5:batch5"] = {
            alias: model_wallet(
                fills,
                prices,
                delay_minutes=5,
                source_mode=source_mode,
                batch_minutes=5,
            )
            for alias, fills in input_events.items()
        }
    models["csv_duplicate_collapsed_sensitivity:5:batch5"] = {
        alias: model_wallet(
            _remove_csv_exact_duplicates(fills),
            prices,
            delay_minutes=5,
            source_mode="anchored_or_episode",
            batch_minutes=5,
        )
        for alias, fills in input_events.items()
    }
    experiments = {}
    for name, memberset in EXPERIMENTS.items():
        size = len(memberset)
        per_pod_gross = GROSS_BUDGET_USD / size
        scenarios = {}
        lower_gross_stress = {}
        for model_id, wallets in models.items():
            gross = np.zeros(N, dtype=np.float64)
            worst = np.zeros(N, dtype=np.float64)
            turnover = np.zeros(N, dtype=np.float64)
            for alias in memberset:
                wallet = wallets[alias]
                gross += per_pod_gross * wallet["pnl_delta_per_budget_usd"]
                worst += per_pod_gross * wallet["worst_bar_delta_per_budget_usd"]
                turnover += per_pod_gross * wallet["turnover_per_budget_usd"]
            scenarios[model_id] = {
                str(bps): _metrics(gross, worst, turnover, cost_bps=bps) for bps in DEFAULT_COSTS
            }
            if model_id in ("anchored_or_episode:5", "anchored_or_episode:5:batch5"):
                lower_gross_stress[model_id] = {
                    str(bps): _metrics(
                        gross * (5000 / GROSS_BUDGET_USD),
                        worst * (5000 / GROSS_BUDGET_USD),
                        turnover * (5000 / GROSS_BUDGET_USD),
                        cost_bps=bps,
                    )
                    for bps in DEFAULT_COSTS
                }
        component_model = models["anchored_or_episode:5:batch5"]
        contribution = {}
        for alias in memberset:
            wallet = component_model[alias]
            gross_profit = per_pod_gross * float(wallet["pnl_delta_per_budget_usd"].sum())
            dollar_turnover = per_pod_gross * float(wallet["turnover_per_budget_usd"].sum())
            contribution[alias] = {
                "source_coin_pnl_proxy_before_cost_usd": round(gross_profit, 2),
                "modeled_twenty_bps_cost_usd": round(dollar_turnover * 0.002, 2),
                "model_twenty_bps_net_usd": round(gross_profit - dollar_turnover * 0.002, 2),
            }
        experiments[name] = {
            "members": list(memberset),
            "per_wallet_gross_budget_usd": per_pod_gross,
            "scenarios": scenarios,
            "gross_budget_5000_sensitivity": lower_gross_stress,
            "wallet_proxy_contributions_20bps_batch5": contribution,
        }
    return {
        "schema": "phase7_major4_10k_filtered_follow_retro_sensitivity_v2",
        "modeled_account": {
            "capital_usd": EQUITY_USD,
            "total_gross_target_budget_usd": GROSS_BUDGET_USD,
            "max_gross_notional_at_source_change_only": True,
            "instrument_policy": "BTC_ETH_SOL_HYPE_ONLY_NOT_FULL_SOURCE_ACCOUNT",
            "leader_signal_time": "RETROSPECTIVE_EVENT_TIME_NOT_FIRST_KNOWN",
            "hypothetical_execution": "EVENT_TIME_PLUS_DELAY_THEN_NEXT_MINUTE_VERIFIED_NATIVE_OPEN",
            "sizing": "EQUAL_WALLET_CAP_GROSS_NORMALIZE_KNOWN_SOURCE_POSITION_MIX",
            "source_equity_faithful": False,
            "source_opening_inventory_complete": False,
            "csv_missing_first_position": "INFERRED_FROM_ZERO_WITH_UNMATCHED_CLOSE_IGNORED",
            "raw_fill_startPosition": "USED_WHEN_PRESENT",
            "model_modes": [
                "anchored_or_episode",
                "signed_delta",
                "csv_duplicate_collapsed_sensitivity",
            ],
            "batching_scenarios_minutes": [1, 5],
            "alternative_total_gross_budget_usd": 5000.0,
            "slippage": "FIXED_COMPOSITE_BPS_PER_EXECUTED_NOTIONAL_EXPLORATORY",
            "funding_and_liquidation": "OMITTED",
            "exit_policy": "HYPOTHETICAL_FLATTEN_AT_FINAL_VERIFIED_MINUTE_CLOSE",
            "daily_reference": "UTC_DAY_INITIAL_EQUITY",
            "loss_references_usd": {"daily": 450, "trailing": 850},
            "loss_references_do_not_halt": True,
            "costs_bps": list(DEFAULT_COSTS),
            "delays_minutes": list(delay_values),
            "fully_independent_heldout_sample": False,
            "portfolio_members_selected_on_same_90d_data": True,
            "financial_follower_pnl_verified": False,
            "trading_authorized": False,
        },
        "registry": generation,
        "universe_sha256": sha256(raw).hexdigest(),
        "input_source_audit": source_audit,
        "market_audit": market_audit,
        "wallet_scenario_diagnostics": {
            key: {alias: m["audit"] for alias, m in wallets.items()}
            for key, wallets in models.items()
        },
        "portfolios": experiments,
        "scientific_qualification": False,
        "live_trading_authorization": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("universe", type=Path)
    p.add_argument("--root", type=Path, default=SOURCE_ROOT)
    p.add_argument("--market-root", type=Path, default=MARKET_ROOT)
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError("IMMUTABLE_REPORT_ALREADY_EXISTS")
    from copytrade_pm.wallet_registry import DB

    result = evaluate(args.universe, args.root, args.db or DB, args.market_root)
    encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": sha256(encoded).hexdigest(),
                "market_days_by_coin": {
                    c: a["sha_verification_days"] for c, a in result["market_audit"].items()
                },
                "summary": {
                    p: {
                        "five_minute_batch5_20bps": x["scenarios"]["anchored_or_episode:5:batch5"][
                            "20"
                        ],
                        "five_minute_batch5_30bps": x["scenarios"]["anchored_or_episode:5:batch5"][
                            "30"
                        ],
                        "five_minute_batch1_20bps": x["scenarios"]["anchored_or_episode:5"]["20"],
                        "five_minute_batch5_lower_gross_20bps": x["gross_budget_5000_sensitivity"][
                            "anchored_or_episode:5:batch5"
                        ]["20"],
                    }
                    for p, x in result["portfolios"].items()
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
