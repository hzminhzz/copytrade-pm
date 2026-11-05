"""Bounded Phase 7 first-stage candidates; not financial portfolio rankings.

All scores are source fill-turnover overlap heuristics. The output never claims
mark-to-market DD, independent bets, follower PnL or cost qualification.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

if __package__:
    from scripts.phase7_native_exposure import ALIASES, PORTFOLIOS
else:
    from phase7_native_exposure import ALIASES, PORTFOLIOS


def main_perp_turnover(wallet: dict) -> tuple[dict[str, float], float]:
    """Normalize only supported default-perp turnover; missing DEX is not diversification."""
    all_weights = wallet.get("gross_turnover_by_coin_fraction", {})
    supported = {
        coin: weight
        for coin, weight in all_weights.items()
        if isinstance(coin, str)
        and coin
        and ":" not in coin
        and not coin.startswith("@")
        and isinstance(weight, (int, float))
        and 0 < weight < float("inf")
    }
    fraction = sum(supported.values())
    if fraction <= 0:
        return {}, 0.0
    return {coin: weight / fraction for coin, weight in supported.items()}, fraction


def select_pool(wallets: list[dict], *, max_total: int = 20) -> list[dict]:
    """New research proposals require partial source-position evidence.

    startPosition on fills is NOT an independently verified initial account book.
    Frozen Gemini benchmarks remain separate even if they fail this screen.
    """
    unsupported_hip3 = ALIASES.get("S064-xyz:BRENTOIL", "").lower()
    candidates = [
        x
        for x in wallets
        if x["recommendation"] == "CANDIDATE_UNVERIFIED"
        and x["address"].lower() != unsupported_hip3
        and x.get("opening_positions") is True
        and x.get("main_perp_fill_fraction", 0.0) >= 0.8
        and main_perp_turnover(x)[1] >= 0.6
        and x.get("top_coin") in main_perp_turnover(x)[0]
    ]
    candidates.sort(
        key=lambda x: (
            -x["observation_days"],
            x["fills_per_observation_day"],
            -main_perp_turnover(x)[1],
            x["address"],
        )
    )
    pool = []
    coin_counter = Counter()
    for item in candidates:
        if len(pool) == max_total:
            break
        coin = item["top_coin"]
        if coin_counter[coin] >= 3:
            continue
        pool.append(item)
        coin_counter[coin] += 1
    return pool


def pair_turnover_overlap(a: dict, b: dict) -> float:
    aa, _ = main_perp_turnover(a)
    bb, _ = main_perp_turnover(b)
    if not aa or not bb:
        return 1.0  # unknown cannot reward purported diversification
    return sum(min(weight, bb.get(coin, 0)) for coin, weight in aa.items())


def score_combo(wallets: list[dict]) -> dict:
    coin = Counter()
    for item in wallets:
        supported, _ = main_perp_turnover(item)
        for symbol, weight in supported.items():
            coin[symbol] += weight / len(wallets)
    overlap = [pair_turnover_overlap(a, b) for a, b in itertools.combinations(wallets, 2)]
    mean_overlap = sum(overlap) / len(overlap) if overlap else 1.0
    concentration = max(coin.values(), default=1.0)
    missing_source_positions = sum(not x["opening_positions"] for x in wallets)
    additional_cautions = sum(x["recommendation"] != "CANDIDATE_UNVERIFIED" for x in wallets)
    high_churn = sum(x["fills_per_observation_day"] > 60 for x in wallets)
    # Explicit screen-only heuristic: never claim risk-normalized optimality.
    score = (
        100 * (1 - mean_overlap)
        - 25 * concentration
        - 8 * missing_source_positions / len(wallets)
        - 5 * additional_cautions / len(wallets)
        - 2 * high_churn / len(wallets)
    )
    return {
        "members": [x["alias"] for x in wallets],
        "canonical_addresses": [x["address"] for x in wallets],
        "score_screen_only": round(score, 4),
        "mean_pair_gross_fill_turnover_overlap": round(mean_overlap, 4),
        "largest_aggregate_gross_fill_turnover_coin_fraction": round(concentration, 4),
        "missing_fill_startposition_sources": missing_source_positions,
        "verified_atomic_initial_books": 0,
        "min_supported_main_perp_turnover_fraction": round(
            min(main_perp_turnover(x)[1] for x in wallets), 4
        ),
        "members_with_stage1_cautions": additional_cautions,
        "high_churn_members": high_churn,
        "portfolio_pnl": None,
        "max_dd": None,
        "cost_effect": None,
    }


def run(universe: dict) -> dict:
    # The approved frozen alias is address-bound, never generic display-name-bound.
    alias_by_addr = {address.lower(): alias for alias, address in ALIASES.items()}
    normalized = [
        {**x, "alias": alias_by_addr.get(x["address"].lower(), x["alias"])}
        for x in universe["wallets"]
    ]
    pool = select_pool(normalized)
    by_addr = {x["address"]: x for x in normalized}
    ranks = {}
    # Explicit bounded combinatorics; 20 choose 5 = 15,504, not all universe wallets.
    attempted = {}
    for n in (3, 5):
        combos = []
        for pick in itertools.combinations(pool, n):
            top_coins = Counter(x["top_coin"] for x in pick)
            if top_coins.most_common(1)[0][1] >= 3:
                continue
            combos.append(score_combo(list(pick)))
        combos.sort(key=lambda x: (-x["score_screen_only"], x["canonical_addresses"]))
        ranks[str(n)] = combos[:10]
        attempted[str(n)] = len(combos)
    controls = {}
    for name, aliases in PORTFOLIOS.items():
        if not all(a in ALIASES and ALIASES[a].lower() in by_addr for a in aliases):
            controls[name] = {"status": "MISSING_SOURCE_IDENTITY"}
            continue
        result = score_combo([by_addr[ALIASES[a].lower()] for a in aliases])
        result["status"] = "FROZEN_CONTROL_ONLY"
        controls[name] = result
    return {
        "schema": "phase7_first_stage_candidate_screen_v2",
        "interpretation": "HINDSIGHT_SOURCE_FILL_TURNOVER_DIVERSITY_ONLY_NO_FINANCIAL_RANKING",
        "pool_count": len(pool),
        "pool_aliases": [x["alias"] for x in pool],
        "pool_gate": "PARTIAL_FILL_STARTPOSITION_AND_GTE80PCT_MAIN_PERP_FILLS_GTE60PCT_MAIN_PERP_TURNOVER",
        "selection_freeze": "RETROSPECTIVE_IN_SAMPLE_NO_NEW_ALPHA_TRIAL_AUTHORIZATION",
        "invalidates_previous_v4_ranking": True,
        "n_combinations_evaluated": attempted,
        "total_exploratory_combinations": sum(attempted.values()),
        "top10_screen_three": ranks["3"],
        "top10_screen_five": ranks["5"],
        "mandatory_controls": controls,
        "risk_budget_usd": 600,
        "sizing": "THREE_200_PER_POD_FIVE_120_PER_POD_RISK_BUDGET_NOT_REALIZED_LOSS_CAP",
        "source_equity_follower_sizing_available": False,
        "scientific_qualification": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("universe_json", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = run(json.loads(args.universe_json.read_text()))
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("immutable report exists")
        args.output.write_text(output)
    for name in ("top10_screen_three", "top10_screen_five"):
        print(name, len(result[name]))
        for index, portfolio in enumerate(result[name], 1):
            print(index, ",".join(portfolio["members"]), portfolio["score_screen_only"])
    print(
        "pool", result["pool_count"], "candidate_combinations", result["n_combinations_evaluated"]
    )


if __name__ == "__main__":
    main()
