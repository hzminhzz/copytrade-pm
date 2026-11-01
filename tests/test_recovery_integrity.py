"""Regression tests for fail-closed E0/E4 integration, using synthetic inputs."""

from dataclasses import replace
from decimal import Decimal as D
import json

import pytest

from copytrade_pm.pm_e4_prospective import _account_state
from copytrade_pm.pm_e4_source_readiness import audit
from copytrade_pm.pm_wallet_replica import WalletBook, replicate

AT = "2026-11-01T12:00:00+00:00"
BTC = "hyperliquid/mainnet:perp:default/BTC"
ADDRESS = "0x" + "1" * 40


def wallet_book():
    return WalletBook(
        wallet="W028",
        account_scope="verified-master-and-subs",
        source_event_at="2026-11-01T11:59:30+00:00",
        first_known_at="2026-11-01T11:59:31+00:00",
        source_sha256="a" * 64,
        equity_usd=D("10000"),
        positions={BTC: D("2")},
        complete=True,
        capital_reconciled=True,
        continuous=True,
        receipts_prospective=True,
    )


@pytest.mark.parametrize(
    "field",
    [
        "complete",
        "capital_reconciled",
        "continuous",
        "receipts_prospective",
    ],
)
@pytest.mark.parametrize("claim", ["false", 1])
def test_completeness_claims_must_be_real_booleans(field, claim):
    with pytest.raises(ValueError):
        replicate(
            replace(wallet_book(), **{field: claim}), decision_at=AT, pod_capital_usd=D("2000")
        )


def test_decimal_equity_input_is_normalized_before_scaling():
    result = replicate(
        replace(wallet_book(), equity_usd="10000"), decision_at=AT, pod_capital_usd=D("2000")
    )
    assert result.intended[BTC] == D(".4")


def test_fresh_receipt_cannot_refresh_old_source_state():
    old = replace(wallet_book(), source_event_at="2026-11-01T10:00:00+00:00")
    with pytest.raises(ValueError, match="STALE_SOURCE"):
        replicate(old, decision_at=AT, pod_capital_usd=D("2000"))


def state(positions):
    return {
        "user": ADDRESS,
        "clearinghouseStates": [
            [
                "",
                {
                    "marginSummary": {
                        "accountValue": "1",
                        "totalNtlPos": "1",
                        "totalMarginUsed": "1",
                    },
                    "assetPositions": [{"position": p} for p in positions],
                },
            ]
        ],
    }


def test_default_dex_never_accepts_hip3_alias():
    with pytest.raises(ValueError, match="DEX_COIN_MISMATCH"):
        _account_state(state([{"coin": "xyz:BTC", "szi": "1"}]), ADDRESS)


def test_zero_position_does_not_hide_duplicate_native_instrument():
    with pytest.raises(ValueError, match="DUPLICATE_POSITION"):
        _account_state(
            state(
                [
                    {"coin": "BTC", "szi": "0"},
                    {"coin": "BTC", "szi": "1"},
                ]
            ),
            ADDRESS,
        )


@pytest.mark.parametrize("payload", [None, "[]", "{broken"])
def test_missing_or_malformed_report_never_counts_as_integrity_pass(tmp_path, payload):
    generation = tmp_path / "gE420261101T120000000000Z-abcd1234"
    generation.mkdir(mode=0o700)
    if payload is not None:
        (generation / "session-report.json").write_text(payload)
    result = audit(tmp_path, "A")
    assert result["all_generations_integrity_pass"] is False
    assert result["prospective_generations"][0]["errors"]


def test_report_snapshot_claims_require_matching_raw_evidence(tmp_path):
    generation = tmp_path / "gE420261101T120000000000Z-abcd1234"
    generation.mkdir(mode=0o700)
    report = {
        "frames_stored": 0,
        "errors": [],
        "disconnect_reason": "BOUNDED_SESSION_ROTATION",
        "snapshots": {p: {} for p in ("W028", "W042", "W030")},
        "subaccount_counts": {p: 0 for p in ("W028", "W042", "W030")},
        "started_at": AT,
        "finished_at": AT,
    }
    (generation / "session-report.json").write_text(json.dumps(report))
    result = audit(tmp_path, "A")
    assert result["all_generations_integrity_pass"] is False
    assert result["prospective_generations"][0]["errors"]
