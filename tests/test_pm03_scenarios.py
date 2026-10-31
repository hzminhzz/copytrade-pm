"""PM-03 comparator, contract bridge and standalone CLI regression tests."""

from decimal import Decimal as D
import json
from pathlib import Path

import pytest

from copytrade_pm.pm03_account import Account, RiskState, digest
from copytrade_pm.pm03_bridge import inspect_pm02, require_external_targets
from copytrade_pm.pm03_cli import execute as cli_execute
from copytrade_pm.pm03_execution import MarketObservation
from copytrade_pm.pm03_stress import ScenarioStep, compare_policies
from test_pm03_extended import T, BTC, HIP, book, cost


def steps():
    p1 = "2026-10-31T04:01:00+00:00"
    p2 = "2026-10-31T04:02:00+00:00"
    return [
        ScenarioStep(
            p1,
            "2026-10-31T04:01:02+00:00",
            {"A": {BTC: D("10")}, "B": {HIP: D("-4")}},
            {
                BTC: MarketObservation(BTC, p1, p1, D("100"), D("1000"), supported=True),
                HIP: MarketObservation(HIP, p1, p1, D("50"), D("1000"), supported=True),
            },
            ({BTC: D("-0.1"), HIP: D("0.1")},),
        ),
        ScenarioStep(
            p2,
            "2026-10-31T04:02:02+00:00",
            {"A": {BTC: D("7")}, "B": {HIP: D("-2")}},
            {
                BTC: MarketObservation(BTC, p2, p2, D("80"), D("1000"), supported=True),
                HIP: MarketObservation(HIP, p2, p2, D("60"), D("1000"), supported=True),
            },
            ({BTC: D("-0.12"), HIP: D("0.13")},),
        ),
    ]


def _input():
    frames = []
    for s in steps():
        frames.append(
            {
                "as_of": s.as_of,
                "hypothetical_fill_at": s.hypothetical_fill_at,
                "proposed": {
                    pm: {k.key: str(v) for k, v in pos.items()} for pm, pos in s.proposed.items()
                },
                "observations": [
                    {
                        "instrument": k.key,
                        "event_at": q.event_at,
                        "first_known_at": q.first_known_at,
                        "mark": str(q.mark),
                        "volume_base": str(q.volume_base),
                        "quality": q.quality,
                        "supported": q.supported,
                    }
                    for k, q in s.observations.items()
                ],
                "shocks": [{k.key: str(v) for k, v in shock.items()} for shock in s.shocks],
            }
        )
    return {
        "schema": "pm03_cli_input_v1",
        "mode": "RESEARCH_SYNTHETIC",
        "action": "compare",
        "rulebook": book().to_dict(),
        "started_at": T,
        "historical_scores": {"A": "2", "B": "1"},
        "costs": {
            "fee_bps": "2",
            "full_spread_bps": "4",
            "slippage_bps": "1",
            "impact_bps_at_full_participation": "4",
            "max_participation": "0.1",
            "max_age_seconds": 300,
            "latency_seconds": 1,
        },
        "steps": frames,
    }


def test_same_path_three_policy_replay_and_cli_immutable(tmp_path):
    result = compare_policies(
        rulebook=book(),
        started_at=T,
        steps=steps(),
        cost_model=cost(),
        historical_scores={"A": D("2"), "B": D("1")},
    )
    assert result == compare_policies(
        rulebook=book(),
        started_at=T,
        steps=steps(),
        cost_model=cost(),
        historical_scores={"A": D("2"), "B": D("1")},
    )
    assert len(result["comparison"]) == 3
    assert result["report_sha"] == digest({k: v for k, v in result.items() if k != "report_sha"})
    assert all(len(row["equity"]) == 3 for row in result["comparison"].values())
    assert result["hindsight_top_pnl_is_not_a_prospective_policy"]
    assert result["economically_qualified_wallet_count"] == 0
    report = cli_execute(_input(), tmp_path)
    assert report["mode"] == "RESEARCH_SYNTHETIC"
    assert cli_execute(_input(), tmp_path) == report
    file = Path(report["path"])
    assert file.exists() and file.stat().st_mode & 0o077 == 0


def test_hindsight_not_qualified_and_missing_path_rejected():
    with pytest.raises(ValueError, match="EMPTY_SCENARIO"):
        compare_policies(
            rulebook=book(), started_at=T, steps=[], cost_model=cost(), historical_scores={}
        )
    with pytest.raises(ValueError, match="SYNTHETIC_RULEBOOK"):
        compare_policies(
            rulebook=book(confirmed=False),
            started_at=T,
            steps=steps(),
            cost_model=cost(),
            historical_scores={},
        )


def test_stage_step1_to_step2_simulation_preserves_equity_hwm():
    b = book(
        program="classic_2step",
        stage="step1",
        profit_target=D("500"),
        static_loss=None,
        trailing_loss=D("800"),
        trailing_cap=D("10000"),
    )
    a = Account.start(b, T)
    a.simulate_fill(BTC, D("10"), D("100"), D("0"), accepted=True, allocated={"A": D("10")})
    a.mark({BTC: D("160")}, "2026-10-31T05:00:00+00:00")
    assert a.stage_passed and a.high_water == D("10600")
    nxt = book(
        program="classic_2step",
        stage="step2",
        profit_target=D("1000"),
        static_loss=None,
        trailing_loss=D("800"),
        trailing_cap=D("10000"),
    )
    a.advance_stage(nxt, as_of="2026-10-31T05:00:01+00:00")
    assert not a.stage_passed and a.equity == D("10600")
    assert a.floor()[1]["trailing"] == D("9800")
    assert not a.breached


def test_pm02_empty_seats_not_synthesized_as_new_risk(tmp_path):
    original = {
        "schema": "pm02_manager_governance_v1",
        "asof": T,
        "live_trading_authorized": False,
        "policy": {"risk_authority": "PM03_ACCOUNT_SUPERVISOR_ONLY"},
        "qualified_count": 0,
        "scientifically_qualified_from_pm01": 0,
        "cards": [{}] * 36,
        "five_seats": [
            {
                "state": "EMPTY",
                "authority": "RESEARCH_PROPOSAL_ONLY",
                "risk_budget_r": 0.0,
                "wallet": None,
            }
        ]
        * 5,
        "research_risk_allocated_r": 0,
        "reserve_r": 1.0,
    }
    sha = digest(original)
    path = tmp_path / "pm02.json"
    path.write_text(json.dumps({**original, "sha256": sha}))
    gate = inspect_pm02(path, decision_at=T, expected_sha=sha)
    assert gate.scientifically_qualified == 0
    assert gate.actionable_budgets == {}
    assert require_external_targets(
        gate, position_artifact_sha=None, position_first_known_at=None, decision_at=T
    ) == {"status": "NO_QUALIFIED_SEATS", "actionable": False, "targets": {}}
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        inspect_pm02(path, decision_at=T, expected_sha="0" * 64)


def test_real_36_wallet_pm02_parity_if_owner_private_fixture_available():
    path = Path(
        "/home/quant/.local/share/copytrade/reports/pm02-extraction-target-parity/"
        "pm02-7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f.json"
    )
    if not path.is_file():
        pytest.skip("Owner-private PM02 artifact not installed; synthetic test already validates")
    gate = inspect_pm02(
        path,
        decision_at=T,
        expected_sha="7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f",
    )
    assert gate.wallet_count == 36 and gate.scientifically_qualified == 0
    assert gate.status == "ZERO_ACTIONABLE_RISK" and gate.actionable_budgets == {}
    assert gate.raw_sha == "a4f5261df167d0958cf58f3e3fe003050d3ce2f34fe1761764721d4bad40dbc1"


def test_manual_halt_is_persistent_but_contract_breach_not_reversible():
    a = Account.start(book(), T)
    a.risk = RiskState.HALT
    a.manual_reset(authorization="signed-synthetic", as_of=T)
    assert a.risk == RiskState.GREEN
    a.breached = True
    a.risk = RiskState.HALT
    with pytest.raises(ValueError, match="BREACH_PERSISTS"):
        a.manual_reset(authorization="signed-synthetic", as_of=T)
