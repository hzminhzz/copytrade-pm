"""Paired OOS follower sensitivity and complete trial-denominator checks."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_k_recalibration import PairedControlBlock, Trial, evaluate_k
from test_pm_k_recalibration import BEFORE, AFTER, S, _input


def _paired_input(*, negative=False, missing_funding=False, duplicate=False, future=False):
    trial = Trial(
        trial_id="candidate",
        candidate_id="wallet-A",
        selection_as_of=BEFORE,
        status="ACCEPTED",
        evidence_sha256=S,
        variant_k=D("0.02"),
    )
    rejected = Trial(
        trial_id="screen-rejected",
        candidate_id="wallet-B",
        selection_as_of=BEFORE,
        status="REJECTED",
        evidence_sha256=S,
        variant_k=D("0.5"),
    )
    blocks = []
    for i in range(7):
        start = datetime(2026, 11, 2 + i, tzinfo=UTC)
        for scenario in ("BASE", "DELAYED", "ADVERSE"):
            end = start + timedelta(hours=1)
            known = end + timedelta(hours=1)
            blocks.append(
                PairedControlBlock(
                    trial_id="candidate",
                    block_id=f"day-{i}",
                    scenario=scenario,
                    split="FORWARD" if i == 6 else "OOS",
                    started_at=start.isoformat(),
                    ended_at=end.isoformat(),
                    known_at=AFTER if future and i == 0 else known.isoformat(),
                    follower_report_sha256=S,
                    candidate_follower_net_usd=D("1") if negative else D("12"),
                    current_k_follower_net_usd=D("4"),
                    cash_net_usd=D("0"),
                    matched_wallet_net_usd=D("1"),
                    market_net_usd=D("2"),
                    fees_usd=D("1"),
                    slippage_usd=D("1"),
                    funding_usd=None if missing_funding else D("0"),
                    capacity_verified=True,
                )
            )
    if duplicate:
        blocks.append(blocks[0].model_copy())
    roster = (trial, rejected)
    return _input(
        trials=roster,
        trial_roster_sha256=digest([t.model_dump(mode="json") for t in roster]),
        paired_control_blocks=tuple(blocks),
    )


def test_paired_controls_are_counted_with_rejected_variant_and_not_self_certified():
    proposal = evaluate_k(_paired_input())
    assert proposal.decision == "INSUFFICIENT_EVIDENCE"
    assert proposal.paired_economics["trials_in_denominator"] == 2
    assert proposal.paired_economics["independent_blocks"] == 7
    assert proposal.paired_economics["calendar_days"] == 7
    assert D(proposal.paired_economics["lower_incremental_usd"]) > 0
    assert proposal.paired_economics["original_reports_verified"] is False
    assert "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED" in proposal.reasons


@pytest.mark.parametrize(
    "opts,reason",
    [
        ({"negative": True}, "PAIRED_MULTIPLICITY_ADJUSTED_BOUND_NONPOSITIVE"),
        ({"missing_funding": True}, "PAIRED_FINANCING_CAPACITY_OR_CONTROL_MISSING"),
        ({"duplicate": True}, "DUPLICATE_PAIRED_BASE_BLOCK"),
    ],
)
def test_missing_negative_or_duplicated_economic_blocks(opts, reason):
    proposal = evaluate_k(_paired_input(**opts))
    assert reason in proposal.reasons
    assert proposal.authorized_for_trading is False


def test_future_block_is_refused_before_any_risk_processing():
    with pytest.raises(ValidationError, match="PAIRED_BLOCK_FROM_FUTURE"):
        _paired_input(future=True)
