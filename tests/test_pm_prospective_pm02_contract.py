"""PM-02 sealed ledger consumer contract; preserve historical output compatibility."""

from datetime import timedelta

import pytest

from copytrade_pm.pm_manager import rank
from test_pm_prospective_audit import setup_receipt, signature
from test_pm_prospective_outcomes import make_outcome
from test_pm_prospective_ledger import IMPORTED

ASOF = IMPORTED + timedelta(minutes=6)
ALIASES = tuple(f"W{i:03d}" for i in range(1, 37))


def pm01_v2():
    return {
        "schema": "pm01_fill_only_replay_v2",
        "wallet_count": 36,
        "never_claim_prospective_alpha": True,
        "rows": [
            {
                "wallet": alias,
                "cohort": (
                    "original" if alias <= "W006" else "wave1" if alias <= "W016" else "wave2"
                ),
                "latency_minutes": lag,
                "oracle_hindsight": True,
                "known_at": "UNKNOWN_VENDOR_HISTORICAL_ORACLE",
                "status": "HISTORICAL_HINDSIGHT_SIMULATION_ONLY",
            }
            for alias in ALIASES
            for lag in (5, 15, 60)
        ],
    }


def audited_one(tmp_path):
    journal, signer, receipt_audit, now = setup_receipt(tmp_path)
    proof = journal.audit_receipt(receipt_audit, signature(signer, receipt_audit))
    now[0] = ASOF
    outcome = make_outcome(journal, proof)
    journal.record_matched_outcome(outcome, signature(signer, outcome))
    return journal


def test_signed_adapter_is_consumer_shape_and_replay_v2_unmodified(tmp_path):
    journal = audited_one(tmp_path)
    before = pm01_v2()
    result = rank(
        before,
        ALIASES,
        ASOF.isoformat(),
        prospective=journal.pm02_rows_asof(ASOF.isoformat()),
        prospective_verified_head=journal.head_sha,
    )
    assert before == pm01_v2()
    assert result["cards"][0]["prospective"]["n"] == 1
    assert result["cards"][0]["prospective"]["qualified"] is False
    assert result["qualified_count"] == 0
    assert result["five_seats"][0]["state"] == "EMPTY"
    assert result["live_trading_authorized"] is False
    assert result["untrusted_prospective_input"] is False
    assert result["audit_chain"]["prospective_ledger_head_sha256"] == journal.head_sha


def test_authenticated_asof_and_decision_parent_chain(tmp_path):
    journal = audited_one(tmp_path)
    before_maturity = IMPORTED + timedelta(seconds=10)
    r1 = rank(
        pm01_v2(),
        ALIASES,
        before_maturity.isoformat(),
        prospective=journal.pm02_rows_asof(before_maturity.isoformat()),
        prospective_verified_head=journal.head_asof(before_maturity.isoformat()),
    )
    assert r1["cards"][0]["prospective"]["n"] == 0
    # A decision before outcome recording references the audit prefix, not
    # knowledge of future evidence already present in the researcher filesystem.
    assert journal.head_asof(before_maturity.isoformat()) != journal.head_sha
    r2 = rank(
        pm01_v2(),
        ALIASES,
        (ASOF + timedelta(minutes=1)).isoformat(),
        prospective=journal.pm02_rows_asof((ASOF + timedelta(minutes=1)).isoformat()),
        prospective_verified_head=journal.head_asof((ASOF + timedelta(minutes=1)).isoformat()),
        previous_report=r1,
    )
    assert r2["audit_chain"]["parent_sha256"] == r1["sha256"]
    assert r2["cards"][0]["prospective"]["n"] == 1
    assert r2["qualified_count"] == 0


def test_unsigned_prospective_rows_still_untrusted_by_default():
    raw = {
        "W001": [
            {
                "episode_id": "x",
                "event_at": IMPORTED.isoformat(),
                "known_at": IMPORTED.isoformat(),
                "outcome_known_at": IMPORTED.isoformat(),
                "verified_first_known": False,
            }
        ]
    }
    report = rank(pm01_v2(), ALIASES, ASOF.isoformat(), prospective=raw)
    assert report["untrusted_prospective_input"] is True
    assert report["cards"][0]["prospective"]["n"] == 0
    with pytest.raises(ValueError, match="INVALID_VERIFIED_LEDGER_HEAD"):
        rank(
            pm01_v2(),
            ALIASES,
            ASOF.isoformat(),
            prospective=raw,
            prospective_verified_head="unverified",
        )
