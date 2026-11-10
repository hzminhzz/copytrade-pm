"""Official Hyperliquid wallet health: real-response shape and adversarial boundaries."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json

import pytest

from copytrade_pm import wallet_health_official as o
from copytrade_pm.wallet_health import HealthReport
from test_wallet_health import NOW, seeded


def _state(amount="2300"):
    return {
        "time": int(NOW.timestamp() * 1000),
        "marginSummary": {"accountValue": amount},
        "assetPositions": [],
    }


def _fake_provider(*, mode="default", tamper=False, state=None, failures=None):
    queries = []

    def info(request):
        queries.append(request["type"])
        if failures and request["type"] in failures:
            raise ValueError("INVALID_PROVIDER_SCHEMA")
        kind = request["type"]
        response = {
            "clearinghouseState": _state() if state is None else state,
            "userAbstraction": mode,
            "userNonFundingLedgerUpdates": [
                {
                    "time": int((NOW - timedelta(days=1)).timestamp() * 1000),
                    "hash": "0x" + "a" * 64,
                    "delta": {"withdraw": {"usdc": "100"}},
                }
            ],
            "userFunding": [],
            "userFillsByTime": [
                {
                    "time": int((NOW - timedelta(days=1)).timestamp() * 1000),
                    "tid": 7,
                }
            ],
        }[kind]
        raw = json.dumps(response, separators=(",", ":")).encode()
        return response, raw, "f" * 64 if tamper else sha256(raw).hexdigest()

    return info, queries


def _collect(tmp_path, *, mode="default", deep=0, tamper=False, state=None, failures=None):
    db = seeded(tmp_path)
    info, calls = _fake_provider(mode=mode, tamper=tamper, state=state, failures=failures)

    # Historical cutoff selects wallet #1, never future-known #2.
    def clock():
        return NOW

    gen = tmp_path / ("g" + "r" * 13)
    result = o.capture(db, gen, info=info, clock=clock, max_wallets=1, deep_wallets=deep)
    report = HealthReport.model_validate_json(next((gen / "reports").glob("*.json")).read_text())
    return result, report, calls, gen


def test_official_main_perp_capital_only_with_separate_mode_proof(tmp_path):
    result, report, calls, gen = _collect(tmp_path)
    assert result["verified_main_perp_capital"] == 1
    assert result["raw_receipts_verified"] == 2
    assert calls == ["clearinghouseState", "userAbstraction"]
    finding = report.findings[0]
    assert finding.eligibility == "ELIGIBLE"
    assert finding.source_integrity == "UNKNOWN"
    assert finding.capital_attribution == "UNKNOWN"
    assert finding.edge == "INSUFFICIENT_EVIDENCE"
    assert finding.copyability == "INSUFFICIENT_EVIDENCE"
    assert not result["trading_authorized"]
    assert (gen / "raw" / "w000001" / "clearinghouseState.json").is_file()
    assert (gen / "receipts" / "w000001" / "clearinghouseState.json").is_file()


@pytest.mark.parametrize("mode", ["unifiedAccount", "portfolioMargin", "dexAbstraction", "UNKNOWN"])
def test_nonseparable_account_value_does_not_become_verified_equity(tmp_path, mode):
    result, report, _, _ = _collect(tmp_path, mode=mode)
    assert result["verified_main_perp_capital"] == 0
    assert report.findings[0].eligibility == "UNKNOWN"


def test_verified_under_1000_is_review_only_not_liquidation(tmp_path):
    _, report, _, _ = _collect(tmp_path, state=_state("999"))
    f = report.findings[0]
    assert f.eligibility == "CAPITAL_FLOOR_BREACH"
    assert f.liquidation == "UNKNOWN"
    assert f.recommendation == "CAPITAL_FLOOR_BREACH"


def test_recent_fill_establishes_activity_but_not_follower_edge(tmp_path):
    result, report, calls, _ = _collect(tmp_path, deep=1)
    assert len(calls) == 5
    assert result["recent_activity_windows_complete"] == 1
    assert result["financial_attribution_verified"] == 0
    f = report.findings[0]
    assert f.activity == "ACTIVE"
    assert f.trading_pnl_usd is None
    assert f.portfolio_contribution == "UNKNOWN"


def test_tampered_or_invalid_source_raw_abstains_not_zero(tmp_path):
    result, report, _, _ = _collect(tmp_path, tamper=True)
    assert result["verified_main_perp_capital"] == 0
    assert result["provider_errors"]
    assert report.findings[0].eligibility == "UNKNOWN"


def test_missing_account_mode_abstains(tmp_path):
    result, report, _, _ = _collect(tmp_path, failures={"userAbstraction"})
    assert result["verified_main_perp_capital"] == 0
    assert report.findings[0].eligibility == "UNKNOWN"


def test_incomplete_ledger_classification_and_censoring():
    now = int(NOW.timestamp() * 1000)
    rows = [{"time": now, "delta": {"deposit": {"usdc": "200"}}}]
    assert (
        o._ledger_audit(rows, since=now - 100, until=now)["external_deposit_usd_observed"] == "200"
    )
    assert (
        o._ledger_audit(
            rows + [{"time": now, "delta": {"mystery": {}}}], since=now - 100, until=now
        )["external_deposit_usd_observed"]
        is None
    )
    with pytest.raises(ValueError, match="FUTURE_OR_OUT_OF_WINDOW"):
        o._ledger_audit(rows, since=now - 1000, until=now - 1)
    assert (
        "LEDGER_PAGE_LIMIT_CENSORED" in o._ledger_audit(rows * 500, since=now, until=now)["reasons"]
    )


def test_failure_does_not_reuse_immutable_generation(tmp_path):
    _, _, _, gen = _collect(tmp_path)
    with pytest.raises(ValueError, match="IMMUTABLE_HEALTH_GENERATION_ALREADY_EXISTS"):
        o.capture(
            tmp_path / "wallet.sqlite",
            gen,
            info=_fake_provider()[0],
            clock=lambda: NOW,
            max_wallets=1,
        )


def test_reject_forged_source_incomplete_time_and_invalid_budget(tmp_path):
    assert o._book_equity(_state(), "unifiedAccount", NOW) is None
    assert (
        o._book_equity(
            {**_state(), "time": int((NOW + timedelta(days=5)).timestamp() * 1000)}, "default", NOW
        )
        is None
    )
    assert o._book_equity(_state("NaN"), "default", NOW) is None
    assert (
        o._book_equity(
            {**_state(), "time": int((NOW - timedelta(hours=1)).timestamp() * 1000)},
            "default",
            NOW,
        )
        is None
    )
    with pytest.raises(ValueError, match="UNSAFE_SHARED_IP_WEIGHT_BUDGET"):
        o.WeightBudget(1201)
    with pytest.raises(ValueError, match="INVALID_HEALTH_CAPTURE_BOUNDS"):
        o.capture(tmp_path, tmp_path / ("g" + "a" * 15), max_wallets=0)


def test_explicit_budget_cannot_sneak_more_than_selected_accounts(tmp_path):
    result, report, _, _ = _collect(tmp_path)
    assert result["requested_accounts"] == 1
    assert result["provider_calls_reserved"] == 2
    assert result["provider_weight_reserved"] == 22
    assert result["source_continuity"] == "SINGLE_SNAPSHOT_ONLY"
    assert report.scientifically_qualified is False
    assert report.trading_authorized is False
