"""Gemini-style HL94 research screens and PM03 pod budget guard regressions."""
from datetime import timedelta
from decimal import Decimal as D

from copytrade_pm.pm_historical_combos import Episode, _run_combo
from copytrade_pm.pm_hl94_research import START, source_actions
from copytrade_pm.pm_shadow import MinuteBar


def _ep(wallet, qty):
    at = START + timedelta(minutes=1)
    return Episode(wallet, "BTC", ((at, 10, "BTC", D(0), qty, qty, D(1000)),))


class DecliningNativeQuote:
    def get(self, _instrument, at):
        price = D(1000) if at < START + timedelta(minutes=8) else D(930)
        return MinuteBar(at, price, D(10_000_000), "a" * 64)


def test_fixed_k_action_batches_native_position_without_historical_equity():
    wallets = ("A", "B", "C")
    eps = {w: [_ep(w, D("2") if w == "A" else D(".001"))] for w in wallets}
    k = {"A": D(".5"), "B": D(1), "C": D(1)}
    actions = source_actions(eps, wallets, k, start=START,
                             end=START + timedelta(minutes=15),
                             delay=timedelta(minutes=5))
    assert len(actions) == 1
    due, snapshot = actions[0]
    assert due == START + timedelta(minutes=6)
    assert list(snapshot["A"].values()) == [D(1)]
    assert list(snapshot["B"].values()) == [D(".001")]


def test_zero_delay_minute_boundary_processes_source_event_once():
    at = START + timedelta(minutes=1)
    ep = Episode("A", "BTC", ((at, 1, "BTC", D(0), D(1), D(1), D(1000)),))
    actions = source_actions({"A": [ep]}, ("A",), {"A": D(".5")},
                             start=START, end=START + timedelta(minutes=3),
                             delay=timedelta(0))
    assert len(actions) == 1
    assert actions[0][0] == at
    assert list(actions[0][1]["A"].values()) == [D(".5")]


def test_pm03_per_pod_fixed_loss_latches_flat_and_preserves_source_tracking():
    wallets = ("A", "B", "C")
    eps = {w: [_ep(w, D("2") if w == "A" else D(".001"))] for w in wallets}
    scale = {w: D(1) for w in wallets}
    actions = source_actions(eps, wallets, scale, start=START,
                             end=START + timedelta(minutes=15),
                             delay=timedelta(0))
    # A 2 BTC source position at $1000 loses $140 after the price drop.
    # Trigger a $100 risk budget while account daily floor ($300) remains safe.
    run = _run_combo("TEST", wallets, eps, scale, DecliningNativeQuote(),
                     actions_override=actions, start_at=START,
                     end_at=START + timedelta(minutes=15), holdout_at=None,
                     pod_loss_limit=D(100), measure_tracking=True)
    assert run["suspended_pods"] == ["A"]
    assert run["counters"]["pod_fixed_loss_stop_latched"] == 1
    assert run["breached_floor"] is False
    assert D(run["per_wallet_pnl_usd"]["A"]) < D(-100)
    assert D(run["per_wallet_pnl_usd"]["A"]) > D(-300)
    assert D(run["action_weighted_exposure_tracking"]["A"]["tracking_error_usd_sum"]) > 0


def test_optional_stop_preserves_existing_pm03_result_schema():
    wallets = ("A", "B", "C")
    eps = {w: [_ep(w, D(".001"))] for w in wallets}
    scales = {w: D(1) for w in wallets}
    actions = source_actions(eps, wallets, scales, start=START,
                             end=START + timedelta(minutes=15),
                             delay=timedelta(minutes=5))
    run = _run_combo("LEGACY", wallets, eps, scales, DecliningNativeQuote(),
                     actions_override=actions, start_at=START,
                     end_at=START + timedelta(minutes=15), holdout_at=None,
                     measure_tracking=True)
    assert "pod_loss_limit_usd" not in run
    assert "suspended_pods" not in run
    for wallet in run["action_weighted_exposure_tracking"].values():
        assert "unpriced_target_instrument_samples" not in wallet
