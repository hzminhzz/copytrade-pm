"""Read-only BTC/ETH/SOL/HYPE portfolio fit screen using existing Phase 7 fills.

Scores describe retrospective *fill-turnover composition*, NOT concurrent
positions, copyable source equity, follower PnL, or risk qualification.

No historical API calls, new fills, broker operations, registry writes,
portfolio freeze updates, or background data acquisition.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import UTC, datetime
import gzip
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path

from copytrade_pm.wallet_registry import DB, readonly_sqlite

MAJORS = ("BTC", "ETH", "SOL", "HYPE")
START = datetime(2026, 8, 5, tzinfo=UTC)
END = datetime(2026, 11, 3, tzinfo=UTC)
RECENT = datetime(2026, 10, 4, tzinfo=UTC)
EXPERIMENTS = {
    "M3-BALANCED": ("H02", "VS002", "W083"),
    "M4-SPECIALISTS": ("ACT33", "ACT34", "H02", "W083"),
    "M5-SOL-BOOST": ("ACT33", "ACT34", "H02", "HX01", "W083"),
}
CSV_SOURCES = {
    "phase4_hl108_csv": "HL108_ALL_90D_FILLS_CONSOLIDATED_20261103.csv.gz",
    "phase5_new50_csv": "PHASE5_NEW50_ALL_FILLS_CONSOLIDATED_20261104.csv.gz",
}
RAW_SOURCES = {
    "wallet_fills_90d",
    "broader_active_inventory_fills_90d",
    "nansen_smart_money_fills_90d",
}
MAX_POOL = 30
MAX_COMBINATIONS = 100_000


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def registry_addresses(db: Path) -> tuple[set[str], set[str], dict]:
    with closing(readonly_sqlite(db)) as conn:
        present = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT lower(w.address) FROM cohort_memberships c "
                "JOIN wallets w ON w.wallet_id=c.wallet_id "
                "WHERE c.cohort_id IN ('research-108','nansen-20','hyperx-30')"
            )
        }
        deny = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT lower(w.address) FROM exclusions e "
                "JOIN wallets w ON w.wallet_id=e.wallet_id"
            )
        }
        meta = dict(conn.execute("SELECT key,value FROM snapshot_meta"))
    if len(present) != 158 or len(meta.get("manifest_sha256", "")) != 64:
        raise ValueError("REGISTRY_GENERATION_NOT_VERIFIED")
    return (
        present,
        deny,
        {
            "research_unique": len(present),
            "registry_manifest_sha256": meta["manifest_sha256"],
            "registry_observed_at": meta.get("observed_at"),
        },
    )


def four_fraction(wallet: dict) -> float:
    weights = wallet.get("gross_turnover_by_coin_fraction") or {}
    return sum(float(weights.get(coin, 0)) for coin in MAJORS)


def eligible_wallets(universe: dict, present: set[str], deny: set[str]) -> list[dict]:
    if universe.get("schema") != "phase7_universe_readonly_v1":
        raise ValueError("INCORRECT_SOURCE_UNIVERSE_SCHEMA")
    rows = [x for x in universe["wallets"] if x["address"].lower() in present]
    if len(rows) != 158 or len({x["address"].lower() for x in rows}) != 158:
        raise ValueError("RESEARCH_UNIVERSE_NOT_COMPLETE_OR_DUPLICATED")
    pool = []
    for item in rows:
        if item["address"].lower() in deny:
            if item["recommendation"] != "REJECT":
                raise ValueError("REGISTRY_EXCLUSION_VS_STAGE1_CONFLICT")
            continue
        if (
            item["recommendation"] != "CANDIDATE_UNVERIFIED"
            or item["observation_days"] < 40
            or item.get("last_fill_age_days_at_cutoff", 999) > 14
            or item.get("main_perp_fill_fraction", 0) < 0.8
            or item.get("fills_per_observation_day", 999) > 100
        ):
            continue
        if (
            four_fraction(item) < 0.6
            and item["gross_turnover_by_coin_fraction"].get("SOL", 0) < 0.15
        ):
            continue
        pool.append(item)
    if not 3 <= len(pool) <= MAX_POOL:
        raise ValueError("MAJOR4_CANDIDATE_POOL_UNBOUNDED")
    if len({x["alias"] for x in pool}) != len(pool):
        raise ValueError("AMBIGUOUS_PORTFOLIO_ALIASES")
    return sorted(pool, key=lambda x: x["alias"])


def _components(
    members: tuple[dict, ...], key: str = "gross_turnover_by_coin_fraction"
) -> dict[str, float]:
    size = len(members)
    fractions = {
        coin: round(sum(x[key].get(coin, 0) for x in members) / size, 6) for coin in MAJORS
    }
    return fractions


def composition(members: tuple[dict, ...], recent_by_alias: dict[str, dict] | None = None) -> dict:
    if len({x["address"].lower() for x in members}) != len(members):
        raise ValueError("NON_UNIQUE_SOURCE_WALLETS")
    weights = _components(members)
    focus = sum(weights.values())
    if focus <= 0:
        raise ValueError("MISSING_MAJOR_FOCUS")
    lead = [x["gross_turnover_by_coin_fraction"] for x in members]
    overlap = sum(
        sum(min(a.get(coin, 0), b.get(coin, 0)) for coin in MAJORS)
        for a, b in combinations(lead, 2)
    ) / (len(members) * (len(members) - 1) / 2)
    concentration = sum((v / focus) ** 2 for v in weights.values())
    # Ranking has no economic meaning and rewards *observed source* focus.
    score = (
        focus * 100
        + min(weights.values()) * 140
        - concentration * 25
        - overlap * 10
        + sum(x["opening_positions"] for x in members) * 2 / len(members)
    )
    result = {
        "members": [x["alias"] for x in members],
        "size": len(members),
        "ninety_day_equal_wallet_turnover_fractions": weights,
        "ninety_day_four_major_share": round(focus, 6),
        "turnover_only_major_coin_pair_overlap": round(overlap, 4),
        "normalized_four_coin_hhi": round(concentration, 4),
        "source_startposition_available_members": sum(x["opening_positions"] for x in members),
        "observation_days_by_member": {x["alias"]: x["observation_days"] for x in members},
        "last_fill_age_days_at_study_cut_by_member": {
            x["alias"]: x["last_fill_age_days_at_cutoff"] for x in members
        },
        "screen_score_not_pnl": round(score, 4),
        "complete_source_account_books": 0,
        "source_equity_faithful": False,
        "actual_follower_pnl": None,
        "portfolio_drawdown": None,
        "trading_authorized": False,
    }
    if recent_by_alias is not None:
        if any(x["alias"] not in recent_by_alias for x in members):
            raise ValueError("MISSING_RECENT_SOURCE_DATA")
        recent = {
            coin: round(
                sum(
                    recent_by_alias[x["alias"]]["last30"]["fractions"].get(coin, 0) for x in members
                )
                / len(members),
                6,
            )
            for coin in MAJORS
        }
        result["recent30_equal_wallet_turnover_fractions"] = recent
        result["recent30_four_major_share"] = round(sum(recent.values()), 6)
        result["recent30_active_source_trade_count"] = {
            x["alias"]: recent_by_alias[x["alias"]]["last30"]["fills"] for x in members
        }
    return result


def evaluate_combinations(pool: list[dict]) -> tuple[dict[str, int], list[dict], list[dict]]:
    eligible = []
    checked = Counter()
    for size in (3, 4, 5):
        for selected in combinations(pool, size):
            checked[str(size)] += 1
            if sum(checked.values()) > MAX_COMBINATIONS:
                raise ValueError("UNBOUNDED_PORTFOLIO_SEARCH")
            res = composition(selected)
            if (
                res["ninety_day_four_major_share"] < 0.75
                or min(res["ninety_day_equal_wallet_turnover_fractions"].values()) < 0.075
            ):
                continue
            eligible.append(res)
    leaders = []
    for size in (3, 4, 5):
        ranked = sorted(
            (x for x in eligible if x["size"] == size),
            key=lambda x: (-x["screen_score_not_pnl"], x["members"]),
        )
        leaders.extend(ranked[:8])
    return dict(checked), eligible, leaders


def _record(buckets: dict, address: str, ms: int, coin: str, notional: float) -> None:
    if not math.isfinite(notional) or notional < 0:
        raise ValueError("INVALID_SOURCE_TURNOVER")
    if not int(START.timestamp() * 1000) <= ms < int(END.timestamp() * 1000):
        return
    label = "last30" if ms >= int(RECENT.timestamp() * 1000) else "first60"
    buckets[address][label]["gross"][coin] += notional
    buckets[address][label]["fills"] += 1


def load_recent(
    existing: list[dict], root: Path, *, expected_source_sha: dict[str, str] | None = None
) -> tuple[dict, dict]:
    """Re-read only local, original Stage-1 authority; no source refetch.

    CSV sources may lack unique exchange fill IDs. This calculation follows
    the source's original row-level vendor representation without inventing
    deduplication, account NAV, or source-position anchors.
    """
    owners = {x["address"].lower(): x for x in existing}
    buckets = defaultdict(lambda: defaultdict(lambda: {"gross": Counter(), "fills": 0}))
    evidence = {}
    found = set()
    for source in sorted(RAW_SOURCES):
        for path in sorted((root / "data" / source).glob("*.json")):
            blob = path.read_bytes()
            raw = json.loads(blob)
            address = str(raw.get("address") or "").lower()
            if address not in owners or owners[address]["source"] != source:
                continue
            if address in found:
                raise ValueError("CONFLICTING_DUPLICATE_RAW_ADDRESS")
            found.add(address)
            fingerprint = sha256(blob).hexdigest()
            if (
                expected_source_sha is not None
                and expected_source_sha.get(f"{source}/{path.name}") != fingerprint
            ):
                raise ValueError("FROZEN_RAW_SOURCE_SHA_MISMATCH")
            evidence[owners[address]["alias"]] = fingerprint
            for row in raw.get("fills", []):
                try:
                    _record(
                        buckets,
                        address,
                        int(row["time"]),
                        str(row["coin"]),
                        abs(float(row["px"]) * float(row["sz"])),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("INVALID_EXISTING_SOURCE_FILL") from exc
    csvhash = {}
    for source, name in CSV_SOURCES.items():
        path = root / "docs" / name
        expected = {a for a, x in owners.items() if x["source"] == source}
        if not expected:
            continue
        csvhash[name] = _sha(path)
        if (
            expected_source_sha is not None
            and expected_source_sha.get(f"docs/{name}") != csvhash[name]
        ):
            raise ValueError("FROZEN_CSV_SOURCE_SHA_MISMATCH")
        with gzip.open(path, "rt", newline="") as handle:
            for row in csv.DictReader(handle):
                addr = str(row.get("address", "")).lower()
                if addr not in expected:
                    continue
                try:
                    when = datetime.fromisoformat(row["datetime_utc"].replace("Z", "+00:00"))
                    when = when.replace(tzinfo=UTC)
                    _record(
                        buckets,
                        addr,
                        int(when.timestamp() * 1000),
                        row["coin"],
                        abs(float(row["price"]) * float(row["size"])),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("INVALID_FROZEN_CSV_SOURCE_FILL") from exc
                found.add(addr)
    if found != set(owners):
        raise ValueError("MISSING_FROZEN_EXISTING_SOURCE_ROWS")
    data = {}
    for address, wallet in owners.items():
        periods = {}
        for key in ("first60", "last30"):
            values = buckets[address][key]
            denom = sum(values["gross"].values())
            periods[key] = {
                "fills": values["fills"],
                "fractions": {
                    market: round(values["gross"].get(market, 0) / denom, 6) if denom > 0 else 0.0
                    for market in MAJORS
                },
            }
        one = buckets[address]["first60"]["gross"]
        two = buckets[address]["last30"]["gross"]
        gross = Counter(one)
        gross.update(two)
        total = sum(gross.values())
        if total <= 0:
            raise ValueError("MISSING_SOURCE_GROSS_VOLUME")
        for market in MAJORS:
            actual = gross.get(market, 0) / total
            declared = wallet["gross_turnover_by_coin_fraction"].get(market, 0)
            if abs(actual - declared) > 0.002:
                raise ValueError("SOURCE_UNIVERSE_RECONSTRUCTION_DRIFT")
        data[wallet["alias"]] = periods | {
            "input_source": wallet["source"],
            "source_identity_sha256": sha256(address.encode()).hexdigest(),
            "source_file_sha256": evidence.get(wallet["alias"])
            or csvhash[CSV_SOURCES[wallet["source"]]],
        }
    return data, {"csv_full_archives_sha256": csvhash, "direct_raw_address_count": len(evidence)}


def run(universe_path: Path, root: Path, db: Path) -> dict:
    blob = universe_path.read_bytes()
    universe = json.loads(blob)
    present, deny, registry = registry_addresses(db)
    pool = eligible_wallets(universe, present, deny)
    checked, eligible, leaders = evaluate_combinations(pool)
    address_by_alias = {x["alias"]: x for x in pool}
    if any(set(members) - set(address_by_alias) for members in EXPERIMENTS.values()):
        raise ValueError("EXPERIMENT_SOURCE_ALIAS_NOT_ELIGIBLE")
    relevant = [
        address_by_alias[a] for a in sorted(set.union(*(set(x) for x in EXPERIMENTS.values())))
    ]
    expected = universe.get("source_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("FROZEN_SOURCE_SHA_CATALOG_MISSING")
    recent, audits = load_recent(relevant, root, expected_source_sha=expected)
    selections = {}
    for name, aliases in EXPERIMENTS.items():
        item = composition(tuple(address_by_alias[alias] for alias in aliases), recent)
        if item["ninety_day_four_major_share"] < 0.75:
            raise ValueError("EXPERIMENT_BELOW_MAJOR_FOCUS")
        selections[name] = item
    return {
        "schema": "phase7_major4_registry_focus_v1",
        "interpretation": "RETROSPECTIVE_GROSS_FILL_TURNOVER_COMPOSITION_NO_PNL",
        "registry": registry,
        "universe_sha256": sha256(blob).hexdigest(),
        "source_window": ["2026-08-05T00:00:00Z", "2026-11-03T00:00:00Z"],
        "recent30_window": ["2026-10-04T00:00:00Z", "2026-11-03T00:00:00Z"],
        "pool_count": len(pool),
        "pool_aliases": [x["alias"] for x in pool],
        "pool_gate": "RESEARCH_158_NON_REJECTED_STAGE1_40D_14D_FRESH_100_FILLS_PER_DAY_MAX_AND_MAJOR4_GTE_60PCT_OR_SOL_GTE_15PCT",
        "combos_evaluated_by_size": checked,
        "combos_meeting_major4_75pct_and_each_coin_7p5pct": Counter(
            str(x["size"]) for x in eligible
        ),
        "retrospective_multiple_selection_trials": sum(checked.values()),
        "leaders_screen_only": leaders,
        "preferred_research_comparisons": selections,
        "preferred_wallet_recent_composition": recent,
        "source_audit": audits,
        "risk_model": "NONE_FILL_TURNOVER_NOT_SOURCE_POSITION_RISK",
        "follower_pnl": None,
        "source_equity_available_for_all_members": False,
        "complete_initial_positions_available_for_all_members": False,
        "true_holdout_used": False,
        "scientific_qualification": False,
        "trading_authorization": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("universe", type=Path)
    ap.add_argument("--root", type=Path, default=Path("/home/quant/dev/copytrade-pm"))
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError("IMMUTABLE_RESEARCH_REPORT_EXISTS")
    result = run(args.universe, args.root, args.db)
    report = json.dumps(result, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(
        json.dumps(
            {
                "report_sha256": sha256(report.encode()).hexdigest(),
                "registry_wallets": result["registry"]["research_unique"],
                "pool": result["pool_count"],
                "combinations_tested": result["retrospective_multiple_selection_trials"],
                "eligible": result["combos_meeting_major4_75pct_and_each_coin_7p5pct"],
                "preferred": result["preferred_research_comparisons"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
