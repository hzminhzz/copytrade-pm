"""FP-04 source whole-book completeness and causal admission contracts."""

from dataclasses import replace

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_fill import BTC, _decision, _source_book
from test_pm_forward_journal import T, manifest


def _alter(source: dict, **changes) -> dict:
    changed = {key: val for key, val in source.items() if key != "snapshot_sha"}
    changed.update(changes)
    return {**changed, "snapshot_sha": digest(changed)}


def test_full_fixture_admits_but_retro_rest_sequential_does_not() -> None:
    source = _source_book()
    ok = admit_source_book(source, decision_at=T, fill_at="2026-11-04T04:00:02+00:00")
    assert ok.admitted and ok.source_equity is not None
    assert ok.positions[BTC] == 2
    sequential = admit_source_book(
        _alter(source, snapshot_kind="SEQUENTIAL_REST"),
        decision_at=T,
        fill_at="2026-11-04T04:00:02+00:00",
    )
    assert not sequential.admitted
    assert "SOURCE_NOT_ATOMIC_WHOLE_ACCOUNT" in sequential.reason_codes
    unsigned = admit_source_book(
        _alter(source, synthetic_fixture=False),
        decision_at=T,
        fill_at="2026-11-04T04:00:02+00:00",
    )
    assert not unsigned.admitted
    assert "INDEPENDENT_REAL_BOOK_ATTESTATION_UNAVAILABLE" in unsigned.reason_codes


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"source_equity": None}, "SOURCE_EQUITY_OR_COLLATERAL_UNKNOWN"),
        ({"source_marks": None}, "SOURCE_POSITION_MARKS_UNKNOWN"),
        ({"source_marks": {}}, "SOURCE_POSITION_MARKS_INVALID"),
        (
            {"dex_census": ["mainnet:perp:default", "mainnet:perp:xyz"]},
            "SOURCE_DEX_CENSUS_INCOMPLETE",
        ),
        ({"dex_census": [{"bad": "unhashable"}]}, "SOURCE_DEX_CENSUS_INCOMPLETE"),
        ({"subaccounts": [{"bad": "unhashable"}]}, "SOURCE_SUBACCOUNT_CENSUS_INCOMPLETE"),
        ({"hedges_complete": False}, "SOURCE_HEDGES_INCOMPLETE"),
        ({"spot_scope_known": False}, "SOURCE_SPOT_UNKNOWN"),
        ({"vault_scope_known": False}, "SOURCE_VAULT_UNKNOWN"),
        ({"margin_mode": "UNKNOWN"}, "SOURCE_MARGIN_MODE_UNKNOWN"),
        ({"subaccounts": ["child"]}, "SOURCE_SUBACCOUNT_CENSUS_INCOMPLETE"),
        ({"first_known_at": "2026-11-04T04:01:00+00:00"}, "SOURCE_CLOCK_ORDER_INVALID"),
        (
            {"positions": {"hyperliquid/mainnet:perp:xyz/BTC": "1"}},
            "SOURCE_NATIVE_POSITIONS_INVALID",
        ),
    ],
)
def test_incomplete_source_denied_with_explicit_reason(change, reason) -> None:
    outcome = admit_source_book(
        _alter(_source_book(), **change),
        decision_at=T,
        fill_at="2026-11-04T04:00:02+00:00",
    )
    assert not outcome.admitted
    assert reason in outcome.reason_codes
    assert outcome.positions == {}


def test_incomplete_source_commits_blocked_without_fill(tmp_path) -> None:
    source = manifest("run_1", "acct_1")
    rules = replace(source.rulebook, confirmed=True, permitted=(BTC,))
    campaign = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    campaign.register(replace(source, rulebook=rules))
    decision = _decision()
    decision["source_book"] = _alter(_source_book(), source_equity=None)
    state = campaign.record_event("run_1", "blocked", decision)
    assert state["cursor"] == 1
    assert state["account"]["quantities"] == {}
    assert state["account"]["equity"] == "10000"
    journal = PaperJournal(tmp_path / "paper")
    result = journal.restore("run_1")["last_event_result"]
    assert result["status"] == "BLOCKED_SOURCE"
    assert "SOURCE_EQUITY_OR_COLLATERAL_UNKNOWN" in result["reason_codes"]
    assert journal.append("run_1", "blocked", decision)["cursor"] == 1
