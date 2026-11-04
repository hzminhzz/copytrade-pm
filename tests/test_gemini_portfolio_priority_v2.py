"""Portfolio Freeze V2: static, research-only selection invariants.

Do not change any historical cohorts or admit positions based on this file.
No source-data reads, network, secrets, orders or in-place registry writes.
"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
PATH = DECISIONS / "2026-11-04-gemini-phase6-portfolio-freeze-v2.json"


def _freeze() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def _canonical(portfolio: dict) -> list[str]:
    return [m["canonical_alias"] for m in portfolio["members"]]


def test_selection_identity_is_versioned_research_only() -> None:
    freeze = _freeze()
    assert freeze["schema"] == "gemini_research_portfolio_priority_v2"
    assert freeze["decision_date_utc"] == "2026-11-04"
    assert freeze["scope"] == "NEW_FORWARD_PAPER_RESEARCH_ONLY"
    assert freeze["status"] == "SELECTION_SAVED_NOT_REGISTERED_OR_DEPLOYED"
    assert freeze["new_forward_paper_priority"] == ["E6", "E2", "P1", "E3", "B_phase5"]
    assert freeze["portfolios"]["E6"]["state"] == "PRIMARY_FORWARD_PAPER_RESEARCH"
    assert freeze["portfolios"]["E2"]["state"] == "THREE_POD_FORWARD_PAPER_CHALLENGER"


def test_frozen_wallet_mapping_and_no_duplicate_managers() -> None:
    portfolios = _freeze()["portfolios"]
    assert _canonical(portfolios["E6"]) == [
        "ACT04",
        "S053-HYPE",
        "S051-BTC",
        "CM-002",
        "Whale_0x5f94",
    ]
    assert _canonical(portfolios["E2"]) == ["ACT04", "S053-HYPE", "S051-BTC"]
    assert _canonical(portfolios["P1"]) == ["S035-ENA", "S051-BTC", "S053-HYPE"]
    assert _canonical(portfolios["P14"]) == [
        "S035-ENA",
        "S051-BTC",
        "S053-HYPE",
        "S064-xyz:BRENTOIL",
        "Whale_0x5f94",
    ]
    assert _canonical(portfolios["E3"]) == ["ACT04", "S053-HYPE", "CM-002"]
    assert _canonical(portfolios["B_phase5"]) == [
        "N01",
        "N07",
        "N02",
        "N05",
        "ACT08",
    ]
    for name, portfolio in portfolios.items():
        if "members" in portfolio:
            names = _canonical(portfolio)
            assert len(names) == len(set(names)), name
            assert len(names) == portfolio["pod_count"], name
    assert set(_canonical(portfolios["E6"])) & set(_canonical(portfolios["E2"])) == set(
        _canonical(portfolios["E2"])
    )
    assert not set(_canonical(portfolios["P1"])) <= set(_canonical(portfolios["E6"]))


def test_equal_nominal_budget_but_not_equal_source_sizing() -> None:
    freeze = _freeze()
    assert freeze["research_contract"]["virtual_initial_equity_usd"] == 10000
    assert freeze["research_contract"]["equal_nominal_risk_budget_usd"] == 600
    for name, count, budget, pod_stop in [
        ("E6", 5, 120, 60),
        ("E2", 3, 200, 100),
    ]:
        portfolio = freeze["portfolios"][name]
        assert portfolio["pod_count"] == count
        assert portfolio["nominal_total_risk_budget_usd"] == 600
        assert portfolio["nominal_pod_budget_usd"] == budget
        assert portfolio["gemini_modeled_pod_daily_flatten_usd"] == pod_stop
        assert count * budget == 600
        assert count * pod_stop == 300

    assert [m["gemini_k_10k_reference"] for m in freeze["portfolios"]["E6"]["members"]] == [
        "0.00257",
        "0.02825",
        "0.02908",
        "0.00231",
        "0.00029",
    ]
    assert [m["gemini_k_10k_reference"] for m in freeze["portfolios"]["E2"]["members"]] == [
        "0.00428",
        "0.04708",
        "0.04847",
    ]
    for name in ("E6", "E2"):
        assert all(
            Decimal(m["gemini_k_10k_reference"]).is_finite()
            and Decimal(m["gemini_k_10k_reference"]) > 0
            for m in freeze["portfolios"][name]["members"]
        )
    assert freeze["portfolios"]["E3"]["source_k_complete"] is False


def test_no_implicit_activation_or_contract_authority() -> None:
    freeze = _freeze()
    contract = freeze["research_contract"]
    assert contract["policy_candidate"] == "P2_flatten"
    assert contract["account_supervisor_terms_verified"] is False
    assert contract["manual_activation_allowed"] is False
    assert contract["trading_authorized"] is False
    assert contract["phase6a_static_k_is_order_sizing_authority"] is False
    assert contract["source_equity_relative_whole_book_required"] is True
    assert contract["first_local_receipt_required"] is True
    assert contract["future_study_registered"] is False
    assert contract["future_start_utc"] is None
    assert contract["execution_first_signal_delay_seconds"] == 300
    assert freeze["source"]["source_metrics_are"].startswith("GEMINI_CONDITIONAL")
    preserved = freeze["preservation"]
    assert all(value is True for value in preserved.values())
    assert freeze["portfolios"]["P14"]["priority"] is None
    assert freeze["portfolios"]["P15"]["state"].startswith("DEFERRED")
    assert freeze["portfolios"]["P16"]["priority"] is None


def test_old_selected_portfolio_frozen_documents_unchanged() -> None:
    # Exact original decisions were inspected before V2; never rewrite their
    # members or risk fields merely to show a new research preference.
    expected = {
        "2026-11-02-gemini-selected-three-pod.md": "2711e543513c8f49273f2d28d4ab0238978b0b38b84aa12b07f0856186b4ae38",
        "2026-11-03-gemini-phase3-adoption-180d.md": "8a92b5f3fc581e21779e791cdcd9a682193cce158a5359ced667466d17415ad5",
    }
    for name, digest in expected.items():
        assert sha256((DECISIONS / name).read_bytes()).hexdigest() == digest


def test_current_index_points_to_new_selection_without_rewriting_old_study() -> None:
    handbook = (ROOT / "docs" / "INDEX.md").read_text()
    runbook = (ROOT / "docs" / "RUNBOOK.md").read_text()
    assert "2026-11-04-gemini-phase6-portfolio-freeze-v2.md" in handbook
    assert "2026-11-04-gemini-phase6-portfolio-freeze-v2.json" in handbook
    assert "2026-11-04-gemini-phase6-portfolio-freeze-v2.md" in runbook
    assert "P1/P14" in runbook
    assert "no running roster/service changes" in handbook
