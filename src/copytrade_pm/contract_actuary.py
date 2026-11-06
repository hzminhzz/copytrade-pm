"""Research-only, vectorized, path-dependent prop challenge lifecycle simulation.

All rulebook fields are scenario assumptions, not verified provider terms.
One Monte Carlo sample is a whole lifecycle; no trades or remote side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class Contract:
    name: str
    fee: float
    targets: tuple[float, ...]
    challenge_dd: float
    challenge_daily: float
    funded_dd: float
    funded_daily: float | None
    funded_eod: bool
    challenge_eod: bool = False
    green_days: int = 0
    payout_every_days: int = 14
    split: float = 0.8


CONTRACTS = (
    Contract("A Flex", 40, (900,), 400, 250, 300, 200, True, green_days=5),
    Contract("B Sprint", 75, (800,), 500, 300, 400, 250, True, green_days=5),
    Contract("C 2-Step", 100, (1000, 500), 800, 500, 800, None, False),
)


def simulate(
    contract: Contract,
    *,
    paths: int = 100_000,
    seed: int = 20261105,
    evaluation_days: int = 180,
    funded_days: int = 180,
    steps_per_day: int = 4,
    daily_sigma: float = 95.0,
    daily_mu: float = 0.0,
    daily_cost: float = 0.0,
    phase_bet_sizes: tuple[float, ...] | None = None,
    max_payouts: int | None = None,
    payout_safety_buffer: float = 25.0,
    discount_rate_annual: float = 0.0,
    innovations: np.ndarray | Callable[[int, int], np.ndarray] | None = None,
) -> dict[str, float | int | str]:
    """Fixed-dollar PnL walk with intra-day monitoring and UTC daily resets.

    Underlying PnL increments are NORMAL with mean daily_mu - daily_cost
    and std daily_sigma, not a calibrated wallet-return law. daily_cost is
    applied evenly at each monitoring interval (turnover assumption).
    Eligible gross profits are withdrawn only to the extent that the
    account stays strictly above the larger trailing/daily floor plus
    payout_safety_buffer; trader receives split thereof.
    Trailing floors only ratchet; withdrawals do not reset high-water marks.
    Green day means positive net daily PnL, not a vendor threshold.
    Stage transitions reset PnL and HWM (contract assumption).
    """
    # NumPy is an optional extra: module import/discovery must work in core-only installs.
    import numpy as np

    if paths < 1 or steps_per_day < 1 or evaluation_days < 1 or funded_days < 1:
        raise ValueError("positive paths, days, and monitoring frequency required")
    if daily_sigma < 0 or daily_cost < 0 or not (0 <= contract.split <= 1):
        raise ValueError("invalid volatility/cost/split")
    if discount_rate_annual < 0 or payout_safety_buffer < 0:
        raise ValueError("discount rate and payout buffer must be nonnegative")
    if phase_bet_sizes is None:
        phase_bet_sizes = (1.0,) * (len(contract.targets) + 1)
    if len(phase_bet_sizes) != len(contract.targets) + 1 or not all(
        np.isfinite(x) and x >= 0 for x in phase_bet_sizes
    ):
        raise ValueError("phase_bet_sizes must be finite, nonnegative and stage-aligned")
    size_lookup = np.asarray(phase_bet_sizes, dtype=np.float64)
    rng = np.random.default_rng(seed)
    phase = np.zeros(paths, dtype=np.int8)
    active = np.ones(paths, dtype=bool)
    equity = np.zeros(paths, dtype=np.float64)
    hwm = np.zeros(paths, dtype=np.float64)
    daily_base = np.zeros(paths, dtype=np.float64)
    funded = np.zeros(paths, dtype=bool)
    ruined_before_payout = np.zeros(paths, dtype=bool)
    expired_before_payout = np.zeros(paths, dtype=bool)
    ruined = np.zeros(paths, dtype=bool)
    paid_count = np.zeros(paths, dtype=np.int16)
    payouts = np.zeros(paths, dtype=np.float64)
    gross_paid = np.zeros(paths, dtype=np.float64)
    green = np.zeros(paths, dtype=np.int16)
    last_distribution_equity = np.zeros(paths, dtype=np.float64)
    funded_age = np.zeros(paths, dtype=np.int16)
    eval_age = np.zeros(paths, dtype=np.int16)
    funded_day_open = np.zeros(paths, dtype=np.float64)
    evaluation_breached = np.zeros(paths, dtype=bool)
    evaluation_timed_out = np.zeros(paths, dtype=bool)
    evaluation_pass_time = np.full(paths, np.nan)
    daily_peak = np.zeros(paths, dtype=np.float64)
    evaluation_made = np.zeros(paths, dtype=np.float64)
    max_days = evaluation_days * len(contract.targets) + funded_days
    sigma_step = daily_sigma / np.sqrt(steps_per_day)
    mu_step = (daily_mu - daily_cost) / steps_per_day

    for day in range(max_days):
        promoted_today = np.zeros(paths, dtype=bool)
        # At midnight, new daily equity baseline; no stale daily PnL.
        daily_base[active] = equity[active]
        daily_peak[active] = equity[active]
        funded_day_open[active & funded] = equity[active & funded]
        for step in range(steps_per_day):
            if not active.any():
                break
            if innovations is None:
                z = rng.standard_normal(paths)
            else:
                z = innovations(day, step) if callable(innovations) else innovations[day, step]
                if z.shape != (paths,) or not np.isfinite(z).all():
                    raise ValueError("invalid innovation: expected finite (paths,) vector")
            size = size_lookup[phase[active]]
            equity[active] += size * (mu_step + sigma_step * z[active])
            challenge = active & ~funded
            funded_now = active & funded
            daily_peak[challenge] = np.maximum(daily_peak[challenge], equity[challenge])
            evaluation_made[challenge] = np.maximum(
                evaluation_made[challenge], daily_peak[challenge] - equity[challenge]
            )
            # Continuous HWM is updated each monitoring step; EOD HWM only
            # ratchets after the final step. No intrabar Brownian bridge.
            update_hwm = step == steps_per_day - 1
            if not contract.challenge_eod:
                hwm[challenge] = np.maximum(hwm[challenge], equity[challenge])
            elif update_hwm:
                hwm[challenge] = np.maximum(hwm[challenge], equity[challenge])
            if not contract.funded_eod:
                hwm[funded_now] = np.maximum(hwm[funded_now], equity[funded_now])
            elif update_hwm:
                hwm[funded_now] = np.maximum(hwm[funded_now], equity[funded_now])

            trailing = np.where(funded, contract.funded_dd, contract.challenge_dd)
            daily_limit = np.where(
                funded,
                np.inf if contract.funded_daily is None else contract.funded_daily,
                contract.challenge_daily,
            )
            floor = np.maximum(hwm - trailing, daily_base - daily_limit)
            hit = active & (equity <= floor)
            evaluation_breached |= hit & ~funded
            ruined_before_payout |= hit & (paid_count == 0)
            ruined |= hit
            active[hit] = False
            # Evaluation target checked AFTER KO. Boundary tie favors KO.
            candidate = active & ~funded
            hit_target = candidate & (
                equity >= np.take(contract.targets, np.minimum(phase, len(contract.targets) - 1))
            )
            if hit_target.any():
                phase[hit_target] += 1
                eval_age[hit_target] = 0
                # Reset stage equity/HWM/daily anchor at promotion.
                equity[hit_target] = 0
                hwm[hit_target] = 0
                daily_base[hit_target] = 0
                daily_peak[hit_target] = 0
                promotes = hit_target & (phase >= len(contract.targets))
                evaluation_pass_time[promotes] = day + (step + 1) / steps_per_day
                funded[promotes] = True
                promoted_today[promotes] = True
                funded_age[promotes] = 0
                funded_day_open[promotes] = 0
                last_distribution_equity[promotes] = 0
                green[promotes] = 0
        # Stage boundary counters; no payouts on the promotion day.
        in_eval = active & ~funded
        eval_age[in_eval] += 1
        expired_eval = in_eval & (eval_age >= evaluation_days)
        evaluation_timed_out |= expired_eval
        expired_before_payout |= expired_eval & (paid_count == 0)
        active[expired_eval] = False
        # The UTC day of promotion is partial; never grant a qualifying
        # green day or a full funded payout day for it.
        in_fund = active & funded & ~promoted_today
        funded_age[in_fund] += 1
        green[in_fund & (equity > funded_day_open)] += 1
        pays = in_fund & (funded_age % contract.payout_every_days == 0)
        pays &= green >= contract.green_days
        pays &= equity > last_distribution_equity
        payout_floor = np.maximum(
            hwm - contract.funded_dd,
            daily_base - (np.inf if contract.funded_daily is None else contract.funded_daily),
        )
        available = np.maximum(
            0.0,
            np.minimum(
                equity - last_distribution_equity,
                equity - payout_floor - payout_safety_buffer,
            ),
        )
        pays &= available > 0
        if max_payouts is not None:
            pays &= paid_count < max_payouts
        if pays.any():
            gross = available[pays]
            cash = gross * contract.split
            discount = (1 + discount_rate_annual) ** (-(day + 1) / 365)
            payouts[pays] += cash * discount
            gross_paid[pays] += gross
            paid_count[pays] += 1
            # Gross profits are removed from funded equity on payout.
            equity[pays] -= gross
            # A prior peak remains part of the trailing constraint.
            last_distribution_equity[pays] = equity[pays]
            green[pays] = 0
            # Withdrawal cannot rewrite a floor; if it crosses, close.
            floor_post = np.maximum(
                hwm[pays] - contract.funded_dd,
                daily_base[pays]
                - (np.inf if contract.funded_daily is None else contract.funded_daily),
            )
            post_ruin = equity[pays] <= floor_post
            idx = np.flatnonzero(pays)[post_ruin]
            ruined[idx] = True
            active[idx] = False
        active[in_fund & (funded_age >= funded_days)] = False

    funded_probability = funded.mean()
    first_payout_probability = (paid_count > 0).mean()
    mean_payout = payouts.mean()
    return {
        "contract": contract.name,
        "paths": paths,
        "seed": seed,
        "funded_probability": float(funded_probability),
        "evaluation_pass_probability": float(np.isfinite(evaluation_pass_time).mean()),
        "evaluation_breach_before_pass_probability": float(evaluation_breached.mean()),
        "evaluation_timeout_probability": float(evaluation_timed_out.mean()),
        "conditional_pass_time_days": float(np.nanmean(evaluation_pass_time))
        if np.isfinite(evaluation_pass_time).any()
        else None,
        "conditional_pass_time_standard_error": float(
            np.nanstd(evaluation_pass_time, ddof=1)
            / np.sqrt(np.isfinite(evaluation_pass_time).sum())
        )
        if np.isfinite(evaluation_pass_time).sum() > 1
        else None,
        "maximum_daily_adverse_excursion": float(evaluation_made.max()),
        "made_95th_percentile": float(np.quantile(evaluation_made, 0.95)),
        "first_payout_probability": float(first_payout_probability),
        "ruin_before_first_payout": float(ruined_before_payout.mean()),
        "evaluation_expired_before_first_payout": float(expired_before_payout.mean()),
        "no_first_payout": float(1 - first_payout_probability),
        "conditional_cost_to_fund": float(contract.fee / funded_probability)
        if funded_probability
        else None,
        "mean_payout": float(mean_payout),
        "net_ev": float(mean_payout - contract.fee),
        "roi_pct": float(100 * (mean_payout - contract.fee) / contract.fee),
        "mean_payouts_per_purchase": float(paid_count.mean()),
        "mean_payout_conditional_funded": float(mean_payout / funded_probability)
        if funded_probability
        else 0.0,
        "ruin_probability": float(ruined.mean()),
        "payout_standard_error": float(payouts.std(ddof=1) / np.sqrt(paths)) if paths > 1 else None,
    }


def main() -> None:
    """Print reproducible JSON scorecards; not an account-specific valuation."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Research-only three-contract actuarial scenarios")
    parser.add_argument("--paths", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--evaluation-days", type=int, default=180)
    parser.add_argument("--funded-days", type=int, default=180)
    parser.add_argument("--steps-per-day", type=int, default=4)
    parser.add_argument("--daily-sigma", type=float, default=75.0)
    parser.add_argument("--daily-mu", type=float, default=0.0)
    parser.add_argument("--daily-cost", type=float, default=1.0)
    parser.add_argument(
        "--bet-sizes",
        type=float,
        nargs="+",
        default=None,
        help="one per evaluation phase, then funded stage",
    )
    parser.add_argument("--discount-rate-annual", type=float, default=0.0)
    args = parser.parse_args()
    print(
        json.dumps(
            [
                simulate(
                    contract,
                    paths=args.paths,
                    seed=args.seed,
                    evaluation_days=args.evaluation_days,
                    funded_days=args.funded_days,
                    steps_per_day=args.steps_per_day,
                    daily_sigma=args.daily_sigma,
                    daily_mu=args.daily_mu,
                    daily_cost=args.daily_cost,
                    phase_bet_sizes=tuple(args.bet_sizes) if args.bet_sizes else None,
                    discount_rate_annual=args.discount_rate_annual,
                )
                for contract in CONTRACTS
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
