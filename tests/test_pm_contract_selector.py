"""Native portfolio-contract component: evidence and rule boundary tests."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')

from copytrade_pm import pm_contract_selector as selector  # noqa: E402
from copytrade_pm import pm_operations as operations  # noqa: E402


def _fixture(
    path: Path,
    *,
    days: int = 49,
    pnl_a: float = 7.0,
    pnl_b: float = -2.0,
    peak_leverage: float | None = 3.0,
) -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    records = []
    for t in range(days * 4):
        records.append({
            "timestamp": (start + timedelta(hours=t * 6)).isoformat(),
            "pnl_by_member": {"podA": str(pnl_a), "podB": str(pnl_b)},
        })
    data = {
        "schema": selector.SCHEMA,
        "portfolio_id": "demo/AB",
        "portfolio_definition_sha256": "a" * 64,
        "members": ["podA", "podB"],
        "source_status": "SYNTHETIC_FIXTURE",
        "observed_at": (start + timedelta(days=days)).isoformat(),
        "pnl_basis": "FOLLOWER_NET_MARK_TO_MARKET_USD",
        "initial_capital_usd": 10000,
        "step_minutes": 360,
        "costs_included": {key: True for key in selector.COSTS},
        "peak_gross_leverage": peak_leverage,
        "rows": records,
    }
    path.write_text(json.dumps(data))
    return data


def _identity() -> dict:
    return {"portfolio_id": "demo/AB", "definition_sha256": "a" * 64,
            "members": ["podA", "podB"], "version": 1,
            "selection_known_at": "2026-01-01T00:00:00+00:00",
            "registry_generation_sha256": "b" * 64, "registry_observed_at": "2026-02-20",
            "registry_state": "RESEARCH_SELECTION_ONLY", "trading_authorized": False}


def test_rulebook_versions_are_stable_and_never_account_authority() -> None:
    a = selector.rules_catalog()
    b = selector.rules_catalog()
    assert a == b
    assert len(a["contracts"]) == 3
    assert all(not x["account_trading_authorized"] for x in a["contracts"])
    assert any("daily-stop" in x.lower() for x in selector.RULE_UNKNOWNS["C 2-Step"])


def test_complete_joint_pnl_and_causal_utc_grid(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path)
    tape = selector.load_tape(path)
    assert tape.days == 49
    assert tape.increments.shape == (49, 4, 2)
    assert np.array_equal(tape.increments[0, 0], [7, -2])
    bootstrap = selector.JointBlockBootstrap(tape, paths=15, max_days=15, block_days=7,
                                               seed=43)
    assert np.all(bootstrap(0, 0) == 5)
    assert np.all(bootstrap(13, 3) == 5)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda d: d["rows"].pop(5), "INSUFFICIENT_OR_EXCESSIVE"),
        (lambda d: d["rows"][8].update({"timestamp": d["rows"][7]["timestamp"]}),
         "GAPPED_DUPLICATED"),
        (lambda d: d["rows"][0]["pnl_by_member"].pop("podB"), "MISSING_OR_UNEXPECTED"),
        (lambda d: d["costs_included"].update({"funding": False}), "INCOMPLETE_EXECUTION"),
        (lambda d: d.update({"pnl_basis": "LEADER_REALIZED_PNL"}), "LEADER_OR_REALIZED"),
        (lambda d: d["rows"][0]["pnl_by_member"].update({"podA": "NaN"}), "NONFINITE"),
        (lambda d: d.update({"observed_at": "2026-01-01T00:00:00+00:00"}),
         "OBSERVED_BEFORE"),
        (lambda d: d.update({"peak_gross_leverage": -1}), "NEGATIVE_GROSS"),
        (lambda d: d.update({"members": ["podA", "podA"]}), "INVALID_PORTFOLIO_MEMBERS"),
    ],
)
def test_invalid_tapes_fail_closed(tmp_path: Path, mutate, error: str) -> None:
    file = tmp_path / "pnl.json"
    data = _fixture(file)
    mutate(data)
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=error):
        selector.load_tape(file)


def test_reject_identity_drift(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path)
    tape = selector.load_tape(path)
    wrong = {**_identity(), "definition_sha256": "0" * 64}
    with pytest.raises(ValueError, match="MISMATCH"):
        selector.compare_contracts(tape, wrong, paths=20, evaluation_days=5, funded_days=15)


def test_scorecard_and_no_purchase_authorization(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, pnl_a=90, pnl_b=-10)
    tape = selector.load_tape(path)
    result = selector.compare_contracts(
        tape, _identity(), paths=128, seed=4, evaluation_days=20, funded_days=42,
        evaluation_scales=(0.5, 1), funded_scales=(0.5,),
    )
    assert result["status"] == "SCENARIO_ONLY"
    assert len(result["scorecard"]) == 6
    assert result["best_modeled_choice"]["net_ev"] > 0
    assert not result["scientifically_qualified"]
    assert not result["trading_authorized"]
    assert result["purchase_decision"] == "NO_AUTHORIZED_PURCHASE_RECOMMENDATION"
    repeat = selector.compare_contracts(
        tape, _identity(), paths=128, seed=4, evaluation_days=20, funded_days=42,
        evaluation_scales=(0.5, 1), funded_scales=(0.5,),
    )
    assert result == repeat


def test_unknown_leverage_blocks_all_contract_comparison(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, peak_leverage=None)
    result = selector.compare_contracts(
        selector.load_tape(path), _identity(), paths=20,
        evaluation_days=5, funded_days=10,
        evaluation_scales=(1,), funded_scales=(1,),
    )
    assert result["status"] == "BLOCKED"
    assert result["best_modeled_choice"] is None
    assert any(row["status"] == "BLOCKED_LEVERAGE_UNKNOWN" for row in result["scorecard"])


def test_coarse_historical_mark_grid_refused(tmp_path: Path) -> None:
    path = tmp_path / 'pnl.json'
    data = _fixture(path)
    data['source_status'] = 'HISTORICAL_HYPOTHETICAL'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='SAMPLING_TOO_COARSE'):
        selector.compare_contracts(selector.load_tape(path), _identity(), paths=10)


def test_ruin_constraint_can_reject_every_modeled_purchase(tmp_path: Path) -> None:
    path = tmp_path / 'pnl.json'
    _fixture(path, pnl_a=-100, pnl_b=0)
    result = selector.compare_contracts(
        selector.load_tape(path), _identity(), paths=50,
        evaluation_days=10, funded_days=21,
        evaluation_scales=(1,), funded_scales=(1,),
        max_no_first_payout_probability=0.01,
    )
    assert result['status'] == 'SCENARIO_ONLY'
    assert not result['risk_constraint_feasible']
    assert result['best_modeled_choice'] is None
    assert result['scenario_decision'] == 'NO_BUY_OR_INCOMPLETE_EVIDENCE'


def test_over_leverage_scenario_blocks_optimum(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, peak_leverage=40)
    result = selector.compare_contracts(
        selector.load_tape(path), _identity(), paths=20,
        evaluation_days=5, funded_days=10,
        evaluation_scales=(1,), funded_scales=(1,),
    )
    assert result["status"] == "BLOCKED"
    assert any(row["status"] == "BLOCKED_LEVERAGE_LIMIT" for row in result["scorecard"])


def test_missing_tapes_return_blocked_for_each_saved_portfolio(monkeypatch) -> None:
    monkeypatch.setattr(selector, "_registry_identity", lambda pid, **k: {
        **_identity(), "portfolio_id": pid,
    })
    result = selector.compare_portfolios(["demo/AB", "demo/CD"])
    assert result["status"] == "BLOCKED"
    assert result["best_modeled_portfolio_contract"] is None
    assert len(result["comparisons"]) == 2
    assert all(r["error_code"] == "MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE"
               for r in result["comparisons"])


def test_global_portfolio_winner_requires_identical_pnl_windows(
    tmp_path: Path, monkeypatch,
) -> None:
    p1 = tmp_path / "ab.json"
    p2 = tmp_path / "cd.json"
    first = _fixture(p1, days=49, pnl_a=40)
    second = _fixture(p2, days=49, pnl_a=20)
    second["portfolio_id"] = "demo/CD"
    second["portfolio_definition_sha256"] = "b" * 64
    # A different (valid, complete) 49-day UTC window is not a paired comparison.
    for row in second["rows"]:
        row["timestamp"] = (
            datetime.fromisoformat(row["timestamp"]) + timedelta(days=1)
        ).isoformat()
    second["observed_at"] = (
        datetime.fromisoformat(second["observed_at"]) + timedelta(days=1)
    ).isoformat()
    p2.write_text(json.dumps(second))
    monkeypatch.setattr(selector, "_registry_identity", lambda pid, **kw: {
        **_identity(), "portfolio_id": pid,
        "definition_sha256": first["portfolio_definition_sha256"]
        if pid == "demo/AB" else second["portfolio_definition_sha256"],
    })
    options = dict(paths=50, evaluation_days=10, funded_days=21,
                   evaluation_scales=(1,), funded_scales=(0.5,))
    mismatch = selector.compare_portfolios(["demo/AB", "demo/CD"], [p1, p2], **options)
    assert mismatch["status"] == "BLOCKED"
    assert mismatch["best_modeled_portfolio_contract"] is None
    assert not mismatch["portfolio_window_alignment_verified"]
    assert mismatch["comparison_blockers"]
    for row, template in zip(second["rows"], first["rows"]):
        row["timestamp"] = template["timestamp"]
    second["observed_at"] = first["observed_at"]
    p2.write_text(json.dumps(second))
    matched = selector.compare_portfolios(["demo/AB", "demo/CD"], [p1, p2], **options)
    assert matched["status"] == "SCENARIO_ONLY"
    assert matched["best_modeled_portfolio_contract"] is not None
    assert matched["portfolio_window_alignment_verified"]


def test_real_registry_integrity_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(operations, "_doctor", lambda _: {"status": "STALE"})
    with pytest.raises(ValueError, match="REGISTRY_SOURCE_PARITY"):
        selector._registry_identity("gemini.phase4/E6", db=Path("missing"), asof=None)
    with pytest.raises(ValueError, match="NAMESPACE"):
        selector._registry_identity("E6", db=Path("missing"), asof=None)


def test_operations_contracts_rule_and_parser(tmp_path: Path) -> None:
    assert operations.cli(["contracts", "rules"]) == 0
    args = operations.parser().parse_args([
        "contracts", "compare", "--portfolio", "gemini.phase4/E6",
        "--portfolio", "gemini.phase4/E2", "--paths", "64"
    ])
    assert args.portfolio == ["gemini.phase4/E6", "gemini.phase4/E2"]
    assert args.paths == 64
