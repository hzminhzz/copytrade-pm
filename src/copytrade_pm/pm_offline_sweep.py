"""Bounded deterministic *synthetic fixture* study using offline tapes and PM-03.

This is intentionally NOT a historical wallet-economics engine: a source
manifest with real vendor fills, or a missing complete PIT receipt and NAV
attestation, is blocked. Uses exact native 1m SHA-qualified market context,
per-fill eligibility, and existing PM03 Decimal simulator for fixture trials.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .pm03_account import Rulebook
from .pm03_execution import CostModel
from .pm03_risk import RiskPolicy
from .pm_offline_account import replay_fixture
from .pm_offline_cache import ImmutableCache
from .pm_offline_eligibility import compile_eligible
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid, Study
from .pm_offline_market import _verified_day
from .pm_offline_source import reconstruct_whole_books
from .pm_shadow import VerifiedHyperliquidMinuteSource

SCHEMA = "pm_offline_synthetic_sweep_v1"
MAX_SCENARIO_MINUTES = 12000
MAX_MARKETS = 32
MAX_EVENTS = 2000


def _json(root: Path, path: str) -> dict:
    value = json.loads((root / path).read_text())
    if not isinstance(value, dict):
        raise ManifestInvalid("EXPECTED_SOURCE_OBJECT")
    return value


def _clock(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ManifestInvalid("INVALID_FIXTURE_CLOCK")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ManifestInvalid("INVALID_FIXTURE_CLOCK") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ManifestInvalid("NAIVE_FIXTURE_CLOCK")
    return dt.astimezone(UTC)


def _software_sha() -> str:
    folder = Path(__file__).resolve().parent
    modules = (
        "pm_offline_sweep.py",
        "pm_offline_manifest.py",
        "pm_offline_source.py",
        "pm_offline_eligibility.py",
        "pm_offline_market.py",
        "pm_offline_account.py",
        "pm_offline_cache.py",
        "pm03_account.py",
        "pm03_execution.py",
    )
    digest = sha256()
    for name in modules:
        digest.update(name.encode())
        digest.update(sha256((folder / name).read_bytes()).digest())
    return digest.hexdigest()


def _source_tape(
    doc: dict, root: Path, clock_basis: str, *, max_age_minutes: int
) -> tuple[dict, dict, dict]:
    expected: dict[tuple[str, str], set[str]] = {}
    account_paths: dict[tuple[str, str], tuple[str, str]] = {}
    for item in doc["sources"]:
        key = (item["account"], item["dex"])
        expected.setdefault(key, set()).add(item["instrument"])
        paths = (item["book_path"], item["equity_path"])
        if key in account_paths and account_paths[key] != paths:
            raise ManifestBlocked("CONFLICTING_WHOLE_BOOK_PROVENANCE")
        account_paths[key] = paths
    by_account: dict[str, set[str]] = {}
    for account, dex in expected:
        by_account.setdefault(account, set()).add(dex)
    if any(len(dexes) > 1 for dexes in by_account.values()):
        raise ManifestBlocked("CROSS_DEX_ACCOUNT_NEEDS_CONSOLIDATED_SOURCE_BOOK")
    initial = []
    fills = []
    equity = []
    for key, (book_path, equity_path) in sorted(account_paths.items()):
        source = _json(root, book_path)
        navs = _json(root, equity_path)
        if set(source) != {"initial_books", "fills"} or set(navs) != {"snapshots"}:
            raise ManifestInvalid("INVALID_FIXTURE_SOURCE_SCHEMA")
        if len(source["initial_books"]) != 1:
            raise ManifestBlocked("MISSING_ATOMIC_WHOLE_BOOK_SNAPSHOT")
        initial.extend(source["initial_books"])
        fills.extend(source["fills"])
        equity.extend(navs["snapshots"])
        if any(
            (row.get("account"), row.get("dex")) != key
            for row in (*source["initial_books"], *source["fills"], *navs["snapshots"])
        ):
            raise ManifestBlocked("CROSS_ACCOUNT_SOURCE_FILE")
    if not fills or len(fills) > MAX_EVENTS:
        raise ManifestBlocked("UNBOUNDED_OR_EMPTY_SOURCE_EVENTS")
    for record in (*initial, *fills, *equity):
        for field in ("first_known_at", "source_event_at"):
            if field in record:
                record[field] = _clock(record[field])
    source = reconstruct_whole_books(
        fills=fills,
        initial_books=initial,
        equity_snapshots=equity,
        required_instruments=expected,
        clock_basis=clock_basis,
        asof_max_age=timedelta(minutes=max_age_minutes),
    )
    original = {
        (row["account"], row["dex"], row["instrument"], row["event_id"]): row for row in fills
    }
    return source, {(row["account"], row["dex"]): row["positions"] for row in initial}, original


def _minute_market(
    doc: dict, market_root: Path, *, start: datetime, end: datetime
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    import polars as pl

    declared = {(x["dex"], x["instrument"], x["date"]): x for x in doc["market_days"]}
    instruments = {(x["dex"], x["instrument"]) for x in doc["sources"]}
    if len(instruments) > MAX_MARKETS:
        raise ManifestBlocked("TOO_MANY_MARKETS_FOR_FIXTURE_HARNESS")
    total = int((end - start).total_seconds() // 60)
    if total <= 0 or total > 1440:
        raise ManifestBlocked("UNBOUNDED_FIXTURE_MINUTE_WINDOW")
    if (end - start).total_seconds() != 60 * total:
        raise ManifestInvalid("NON_MINUTE_FIXTURE_WINDOW")
    panel: dict[datetime, dict] = {
        start + timedelta(minutes=i): {
            "at": start + timedelta(minutes=i),
            "prices": {},
            "prior_volume": {},
            "updates": [],
        }
        for i in range(total)
    }
    source_days: dict[str, dict[str, str]] = {}
    all_dates = sorted(
        {moment.date() for when in panel for moment in (when, when - timedelta(minutes=1))}
    )
    for dex, symbol in sorted(instruments):
        native = f"hyperliquid:mainnet:perp:{dex}:{symbol}"
        frames = []
        for date in all_dates:
            when = datetime.combine(date, datetime.min.time(), tzinfo=UTC)
            frame, day_sha, metadata_sha = _verified_day(market_root, native, when)
            pinned = declared.get((dex, symbol, date.isoformat()))
            if pinned is None or (
                pinned["sha256"] != day_sha or pinned["metadata_sha256"] != metadata_sha
            ):
                raise ManifestBlocked("NATIVE_DAY_NOT_PINNED_TO_STUDY_MANIFEST")
            relative = VerifiedHyperliquidMinuteSource._family(native)
            folder = relative / (f"year={date.year:04d}/month={date.month:02d}/day={date.day:02d}")
            if (
                Path(pinned["path"]) != folder / "data.parquet"
                or Path(pinned["metadata_path"]) != folder / "source.json"
            ):
                raise ManifestBlocked("NATIVE_DAY_PATH_NAMESPACE_MISMATCH")
            source_days[f"{native}@{date.isoformat()}"] = {
                "data_sha256": day_sha,
                "metadata_sha256": metadata_sha,
            }
            frames.append(frame)
        combined = pl.concat(frames)
        bars = {row["timestamp"]: row for row in combined.iter_rows(named=True)}
        for when in sorted(panel):
            if when not in bars or when - timedelta(minutes=1) not in bars:
                raise ManifestBlocked("MISSING_REQUIRED_MARK_OR_PRIOR_CAPACITY")
            bar = bars[when]
            prior = bars[when - timedelta(minutes=1)]
            panel[when]["prices"][native] = str(bar["open"])
            panel[when]["prior_volume"][native] = str(prior["volume"])
    return list(panel.values()), source_days


def _cost(path: dict) -> CostModel:
    return CostModel(
        **{
            key: (
                int(value) if key in ("max_age_seconds", "latency_seconds") else Decimal(str(value))
            )
            for key, value in path.items()
        }
    )


def _risk_policy(raw: dict) -> RiskPolicy:
    allowed = {field.name for field in fields(RiskPolicy)}
    if set(raw) != allowed:
        raise ManifestInvalid("MISSING_OR_UNKNOWN_RISK_POLICY_FIELDS")
    return RiskPolicy(**{key: Decimal(str(value)) for key, value in raw.items()})


def run_synthetic_fixture_study(
    manifest_path: Path,
    *,
    input_root: Path,
    market_root: Path,
    cache_root: Path,
    workers: int = 1,
) -> dict:
    """No network/orders. Only an explicitly declared synthetic test study."""
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ManifestInvalid("INVALID_BOUNDED_WORKER_COUNT")
    doc = json.loads(Path(manifest_path).read_text())
    study = Study.validate(doc, input_root=input_root)
    if doc.get("synthetic_fixture") is not True:
        raise ManifestBlocked("REAL_SOURCE_SWEEP_NOT_YET_CERTIFIED")
    scenarios = doc.get("scenarios", [])
    if not scenarios:
        raise ManifestBlocked("NO_FROZEN_SCENARIOS")
    root = Path(input_root).resolve(strict=True)
    start, end = study.start, study.end
    if start.second or start.microsecond or end.second or end.microsecond:
        raise ManifestInvalid("NON_MINUTE_FIXTURE_STUDY")
    rulebook = Rulebook.from_dict(_json(root, doc["rulebook"]["path"]))
    if rulebook.initial_balance != Decimal(str(doc["follower_initial_equity"])):
        raise ManifestInvalid("FOLLOWER_EQUITY_RULEBOOK_CONFLICT")
    costs = _cost(_json(root, doc["cost_model"]["path"]))
    risk_policy = _risk_policy(_json(root, doc["risk_policy"]["path"]))
    source, initial, originals = _source_tape(
        doc,
        root,
        study.clock_basis,
        max_age_minutes=doc["source_equity_max_age_minutes"],
    )
    if any(Decimal(str(q)) != 0 for book in initial.values() for q in book.values()):
        raise ManifestBlocked("NONFLAT_INITIAL_BOOK_REQUIRES_VERIFIED_ADMISSION_TARGET")
    market, market_shas = _minute_market(doc, market_root, start=start, end=end)
    for account, dex in initial:
        expected_symbols = {
            item["instrument"]
            for item in doc["sources"]
            if item["account"] == account and item["dex"] == dex
        }
        if set(initial[(account, dex)]) != expected_symbols:
            raise ManifestBlocked("INCOMPLETE_INITIAL_BOOK_IN_RUNNER")
    if len(scenarios) * len(study.delay_minutes) * len(market) > MAX_SCENARIO_MINUTES:
        raise ManifestBlocked("TOO_MANY_FIXTURE_SCENARIO_MINUTES")
    store = ImmutableCache(
        cache_root,
        max_object_bytes=8 * 1024 * 1024,
        min_free_bytes=1024 * 1024 * 1024,
    )
    software = _software_sha()
    results = []
    cache_hits = 0
    tape_cache_hits = 0
    for delay in study.delay_minutes:
        source_events = []
        for event in source["events"]:
            identity = (event["account"], event["dex"], event["instrument"], event["event_id"])
            original = originals[identity]
            leader = original.get("leader_prices")
            source_scope = initial[(event["account"], event["dex"])]
            if not isinstance(leader, dict) or leader.keys() != source_scope.keys():
                raise ManifestBlocked("MISSING_WHOLE_BOOK_LEADER_MARKS")
            source_events.append(
                {
                    "account": event["account"],
                    "dex": event["dex"],
                    "instrument": event["instrument"],
                    "event_id": event["event_id"],
                    "source_event_at": _clock(event["source_event_at"]),
                    "first_known_at": _clock(event["first_known_at"]),
                    "position_after": event["position_after"],
                    "leader_prices": leader,
                    "source_equity": event["source_equity"],
                    "whole_book_after": event["whole_book_after"],
                }
            )
        tape_deps = {
            "manifest": study.manifest_sha256,
            "software": software,
            "source": source["sha256"],
            "delay": sha256(str(delay).encode()).hexdigest(),
        }
        cached_tape = store.load("eligible_tape", tape_deps, version=SCHEMA)
        if cached_tape is not None:
            tape = json.loads(cached_tape)
            tape_cache_hits += 1
        else:
            tape = compile_eligible(
                source_events,
                delay_minutes=delay,
                clock_basis=study.clock_basis,
                cutoff=end - timedelta(minutes=1),
            )
            store.publish(
                "eligible_tape",
                tape_deps,
                version=SCHEMA,
                content=json.dumps(tape, sort_keys=True, separators=(",", ":")).encode(),
            )
        position: dict[tuple[str, str], dict] = {k: dict(v) for k, v in initial.items()}
        last_leader: dict[tuple[str, str], dict] = {}
        updates: dict[str, list] = {}
        by_identity = {
            (event["account"], event["dex"], event["instrument"], event["event_id"]): event
            for event in source_events
        }
        for event in tape["events"]:
            key = (event["account"], event["dex"])
            identity = (*key, event["instrument"], event["event_id"])
            original = by_identity[identity]
            position[key][event["instrument"]] = event["position_after"]
            last_leader[key] = original["leader_prices"]
            updates.setdefault(event["execute_open_at"], []).append(
                {
                    "manager": event["account"],
                    "book": {
                        f"hyperliquid:mainnet:perp:{key[1]}:{sym}": qty
                        for sym, qty in position[key].items()
                    },
                    "leader_prices": {
                        f"hyperliquid:mainnet:perp:{key[1]}:{sym}": px
                        for sym, px in last_leader[key].items()
                    },
                    "source_equity": original["source_equity"],
                    "verified_whole_book": True,
                }
            )

        def _run_scenario(scenario: dict) -> tuple[dict, bool]:
            # Scenario-local copies: no financial/event state shared across runs.
            rows = []
            complete_accounts = set(scenario["k_by_account"])
            last_known_by_manager = {}
            admitted = False
            for day in market:
                observed_now = {
                    item["manager"]: item
                    for item in updates.get(day["at"].isoformat(), [])
                    if item["manager"] in complete_accounts
                }
                last_known_by_manager.update(observed_now)
                if not admitted and complete_accounts <= last_known_by_manager.keys():
                    # First actionable moment must have ALL managers independently
                    # known, including those with no new fill in this minute.
                    action_updates = [last_known_by_manager[pm] for pm in sorted(complete_accounts)]
                    admitted = True
                elif admitted:
                    action_updates = [observed_now[pm] for pm in sorted(observed_now)]
                else:
                    action_updates = []
                rows.append(
                    {
                        **day,
                        "prices": dict(day["prices"]),
                        "prior_volume": dict(day["prior_volume"]),
                        "updates": [dict(item) for item in action_updates],
                    }
                )
            if not admitted:
                raise ManifestBlocked("MISSING_COMPLETE_MANAGER_BOOK_WITHIN_WINDOW")
            dependencies = {
                "manifest": study.manifest_sha256,
                "software": software,
                "source": source["sha256"],
                "market": sha256(json.dumps(market_shas, sort_keys=True).encode()).hexdigest(),
                "scenario": sha256(f"{delay}:{scenario['id']}".encode()).hexdigest(),
            }
            cached = store.load("scenario", dependencies, version=SCHEMA)
            hit = cached is not None
            if cached is not None:
                report = json.loads(cached)
            else:
                multiple = Decimal(str(scenario.get("cost_multiplier", "1")))
                stressed_costs = replace(
                    costs,
                    fee_bps=costs.fee_bps * multiple,
                    full_spread_bps=costs.full_spread_bps * multiple,
                    slippage_bps=costs.slippage_bps * multiple,
                    impact_bps_at_full_participation=(
                        costs.impact_bps_at_full_participation * multiple
                    ),
                )
                report = replay_fixture(
                    rulebook=rulebook,
                    minutes=rows,
                    costs=stressed_costs,
                    k_by_manager={
                        pm: Decimal(str(k)) for pm, k in scenario["k_by_account"].items()
                    },
                    mode=study.mode,
                    risk_policy=risk_policy,
                    scenario_shocks=tuple(scenario["stress_shocks"]),
                    hedge_break_loss=Decimal(str(scenario["hedge_break_loss"])),
                    stressed_liquidity_loss=Decimal(str(scenario["stressed_liquidity_loss"])),
                )
                store.publish(
                    "scenario",
                    dependencies,
                    version=SCHEMA,
                    content=json.dumps(report, sort_keys=True, separators=(",", ":")).encode(),
                )
            return (
                {
                    "delay_minutes": delay,
                    "scenario": scenario["id"],
                    "account_sha256": report["sha256"],
                    "status": report["status"],
                    "equity": report["ledger"]["equity"],
                    "fees": report["ledger"]["fees"],
                    "breached": report["ledger"]["breached"],
                },
                hit,
            )

        ordered_scenarios = sorted(scenarios, key=lambda x: x["id"])
        if workers == 1:
            evaluations = [_run_scenario(scenario) for scenario in ordered_scenarios]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                evaluations = list(executor.map(_run_scenario, ordered_scenarios))
        for item, hit in evaluations:
            results.append(item)
            cache_hits += int(hit)
    output = {
        "schema": SCHEMA,
        "status": "COMPLETE_SYNTHETIC_FIXTURE_ONLY",
        "manifest_sha256": study.manifest_sha256,
        "source_tape_sha256": source["sha256"],
        "market_day_shas": market_shas,
        "software_sha256": software,
        "scenarios": sorted(results, key=lambda x: (x["scenario"], x["delay_minutes"])),
        "cache_hits": cache_hits,
        "tape_cache_hits": tape_cache_hits,
        "workers_used": workers,
        "requested_scenarios": len(scenarios) * len(study.delay_minutes),
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "broker_authorized": False,
    }
    logical = {
        key: value
        for key, value in output.items()
        if key not in {"cache_hits", "tape_cache_hits", "workers_used"}
    }
    output["logical_sha256"] = sha256(
        json.dumps(logical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    try:
        result = run_synthetic_fixture_study(
            args.manifest,
            input_root=args.input_root,
            market_root=args.market_root,
            cache_root=args.cache_root,
            workers=args.workers,
        )
    except (ManifestBlocked, ManifestInvalid) as exc:
        result = {"schema": SCHEMA, "status": exc.status, "reason": exc.code}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
