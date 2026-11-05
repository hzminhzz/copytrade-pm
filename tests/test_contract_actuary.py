"""Deterministic contracts for lifecycle pricing, no network or execution."""
import pytest

from copytrade_pm.contract_actuary import CONTRACTS, Contract, simulate

np = pytest.importorskip('numpy')


def test_no_risk_no_edge_never_passes() -> None:
    for contract in CONTRACTS:
        result = simulate(contract, paths=25, daily_sigma=0, daily_mu=0, daily_cost=0, evaluation_days=5, funded_days=5)
        assert result["funded_probability"] == 0
        assert result["net_ev"] == -contract.fee


def test_promotion_and_payout_with_deterministic_positive_drift() -> None:
    contract = Contract("test", 10, (10, 10), 100, 100, 100, None, False, green_days=1, payout_every_days=2)
    result = simulate(contract, paths=50, daily_sigma=0, daily_mu=5, evaluation_days=10, funded_days=10)
    assert result["funded_probability"] == 1
    assert result["first_payout_probability"] == 1
    assert result["mean_payout"] > 0
    assert result["mean_payouts_per_purchase"] >= 1


def test_daily_reset_differs_from_permanent_loss_limit() -> None:
    contract = Contract("daily", 1, (100,), 1000, 10, 1000, 10, False)
    # A +8 followed by -8 can survive; two losses within same day breach.
    z = np.array([[[8.0], [-8.0]], [[8.0], [-8.0]]])
    r = simulate(contract, paths=1, evaluation_days=2, funded_days=2,
                 steps_per_day=2, daily_sigma=np.sqrt(2), innovations=z)
    assert r["ruin_probability"] == 0


def test_maximum_drawdown_is_absorbing() -> None:
    contract = Contract("trailing", 1, (100,), 10, 100, 10, None, False)
    z = np.array([[[20.0], [-20.0]], [[0.0], [0.0]]])
    r = simulate(contract, paths=1, evaluation_days=2, funded_days=2,
                 steps_per_day=2, daily_sigma=np.sqrt(2), innovations=z)
    assert r["ruin_probability"] == 1
    assert r["funded_probability"] == 0


def test_eod_peak_sampling_is_not_intraday_peak_sampling() -> None:
    live = Contract('live', 1, (100,), 10, 100, 10, None, False)
    eod = Contract('eod', 1, (100,), 10, 100, 10, None, False,
                   challenge_eod=True)
    # Day 1 interim equity +15 then close +5: no violation of a $10
    # EOD-trailing floor (still -10), but the intraday HWM floor becomes +5.
    z = np.array([[[15.0], [-10.0]], [[0.0], [0.0]]])
    kwargs = dict(paths=1, evaluation_days=2, funded_days=2,
                  steps_per_day=2, daily_sigma=np.sqrt(2), innovations=z)
    a = simulate(live, **kwargs)
    b = simulate(eod, **kwargs)
    assert a['ruin_probability'] == 1
    assert b['ruin_probability'] == 0


def test_validation() -> None:
    with pytest.raises(ValueError):
        simulate(CONTRACTS[0], paths=0)
    with pytest.raises(ValueError):
        simulate(CONTRACTS[0], daily_cost=-1)


def test_phase_specific_sizing_is_applied() -> None:
    contract = Contract('size', 1, (10,), 100, 100, 100, None, False,
                        payout_every_days=1)
    none = simulate(contract, paths=20, daily_mu=10, daily_sigma=0,
                    phase_bet_sizes=(0, 1), evaluation_days=4, funded_days=4)
    assert none['funded_probability'] == 0
    racing = simulate(contract, paths=20, daily_mu=10, daily_sigma=0,
                      phase_bet_sizes=(1, 0), evaluation_days=4, funded_days=4)
    assert racing['funded_probability'] == 1
    assert racing['mean_payout'] == 0
    with pytest.raises(ValueError):
        simulate(contract, phase_bet_sizes=(1,))


def test_same_seed_reproduces_all_statistics() -> None:
    a = simulate(CONTRACTS[1], paths=400, evaluation_days=20, funded_days=20, seed=3)
    b = simulate(CONTRACTS[1], paths=400, evaluation_days=20, funded_days=20, seed=3)
    assert a == b
