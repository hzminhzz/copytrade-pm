"""Pure Vike position reducer never admits a financial source transition."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from copytrade_pm.pm_vike_reconciled_positions import (
    candidate_from_vike_event,
    mark_gap,
    reconcile_candidate_with_official,
    start_nonactionable_baseline,
)

WALLET = "0x" + "a" * 40
MANIFEST = "e" * 64
EPOCH = "epoch_20261111_a"
CURSOR = "1794410000000-0000"
NOW = datetime.now(UTC)
ACK = NOW - timedelta(seconds=3)
BASE = NOW - timedelta(seconds=1)
MARKET = "hyperliquid/mainnet:perp:default/BTC"


def census(*, quantity="4", known=None, provider=None, verified=True, manifest=MANIFEST):
    known = known or BASE
    provider = provider or known - timedelta(milliseconds=500)
    return {
        "schema": "copytrade_independent_official_rest_perp_census_v1",
        "account_sha256": sha256(WALLET.encode()).hexdigest(),
        "manifest_sha256": manifest,
        "original_bytes_independently_verified": verified,
        "scope_parity": True,
        "dex_provider_times_ms": {"default": int(provider.timestamp() * 1000)},
        "dex_state_shas": {"default": "a" * 64},
        "positions": {MARKET: str(quantity)},
        "completed_at": known.isoformat(),
    }


def baseline(*, gap=False):
    return start_nonactionable_baseline(
        WALLET,
        official_census=census(),
        manifest_sha256=MANIFEST,
        live_subscription_ack_at=ACK.isoformat(),
        stream_cursor=CURSOR,
        stream_epoch=EPOCH,
        had_gap=gap,
    )


def event(*, start="4", size="1", after="5", side="buy", action="increase", ts=None):
    return {
        "schema": "vike.event.v1",
        "source": "hl.positions",
        "kind": "position",
        "event_id": f"hl.positions:{WALLET}:1794410001000:123",
        "ts": (ts or NOW).isoformat(),
        "subject": {"wallet": WALLET, "symbol": "BTC"},
        "data": {
            "trade_id": 123,
            "dex": "HL",
            "action": action,
            "side": side,
            "start_position": start,
            "size_token": size,
            "position_after": after,
        },
    }


def update(state=None, *, observation=None, **kwargs):
    return candidate_from_vike_event(
        state or baseline(),
        event=observation or event(),
        raw_event_sha256="b" * 64,
        cursor="1794410001000-0000",
        local_first_known_at=(NOW + timedelta(milliseconds=100)).isoformat(),
        is_prospective=True,
        has_stream_gap=False,
        epoch_id=EPOCH,
        **kwargs,
    )


def test_baseline_never_creates_entry_even_if_all_dexes_match():
    state = baseline()
    assert state.status == "BASELINE_NON_ACTIONABLE"
    assert state.positions == ((MARKET, "4"),)
    assert state.first_known_transition is None
    assert state.paper_new_risk_eligible is False
    assert state.order_route == "NONE"
    bad = baseline(gap=True)
    assert bad.status == "GAP_INELIGIBLE"
    assert update(bad) is bad
    with pytest.raises(ValueError, match="ORIGINAL_PROOF_MISSING"):
        start_nonactionable_baseline(
            WALLET,
            official_census=census(verified=False),
            manifest_sha256=MANIFEST,
            live_subscription_ack_at=ACK.isoformat(),
            stream_cursor=CURSOR,
            stream_epoch=EPOCH,
            had_gap=False,
        )


def test_one_genuine_position_delta_is_candidate_only_after_independent_parity():
    candidate = update()
    assert candidate.positions == ((MARKET, "5"),)
    assert candidate.event_count == 1
    assert candidate.status == "PENDING_INDEPENDENT_RECONCILIATION"
    assert candidate.first_known_transition is None
    assert candidate.paper_new_risk_eligible is False
    verified = reconcile_candidate_with_official(
        candidate,
        verified_census=census(
            quantity="5",
            known=NOW + timedelta(seconds=1),
            provider=NOW + timedelta(milliseconds=250),
        ),
        manifest_sha256=MANIFEST,
    )
    assert verified.status == "RECONCILED_CANDIDATE_NOT_PAPER_PROOF"
    assert verified.official_parity_verified is True
    assert verified.first_known_transition == candidate.last_first_known_at
    assert verified.paper_new_risk_eligible is False
    assert verified.order_route == "NONE"


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (event(start="2"), "SOURCE_POSITION_PRESTATE_MISMATCH"),
        (event(size="2"), "SOURCE_NATIVE_DELTA_MISMATCH"),
        (event(action="reduce"), "SOURCE_POSITION_ACTION_MISMATCH"),
        (event(ts=NOW - timedelta(minutes=5)), "SOURCE_EVENT_CLOCK_OR_LAG"),
    ],
)
def test_inconsistent_source_event_latches_gap(observation, expected):
    result = update(observation=observation)
    assert result.status == "GAP_INELIGIBLE"
    assert result.gap_reason == expected
    assert result.paper_new_risk_eligible is False
    assert update(result) is result


def test_reconnect_gap_cursor_and_independent_mismatch_never_infer_exit():
    state = baseline()
    assert mark_gap(state, reason="STREAM_GAP").status == "GAP_INELIGIBLE"
    assert (
        candidate_from_vike_event(
            state,
            event=event(),
            raw_event_sha256="b" * 64,
            cursor="1794410001000-0000",
            local_first_known_at=(NOW + timedelta(milliseconds=100)).isoformat(),
            is_prospective=False,
            has_stream_gap=False,
            epoch_id=EPOCH,
        ).gap_reason
        == "NONPROSPECTIVE_OR_GAP_EVENT"
    )
    candidate = update()
    mismatch = reconcile_candidate_with_official(
        candidate,
        verified_census=census(
            quantity="-4",
            known=NOW + timedelta(seconds=1),
            provider=NOW + timedelta(milliseconds=250),
        ),
        manifest_sha256=MANIFEST,
    )
    assert mismatch.status == "GAP_INELIGIBLE"
    assert mismatch.gap_reason == "SOURCE_RECON_WHOLE_BOOK_MISMATCH"
    assert mismatch.paper_new_risk_eligible is False
    assert mismatch.first_known_transition is None


def test_expired_baseline_and_epoch_switch_fail_closed():
    with pytest.raises(ValueError, match="SOURCE_STALE"):
        start_nonactionable_baseline(
            WALLET,
            official_census=census(provider=BASE - timedelta(seconds=60)),
            manifest_sha256=MANIFEST,
            live_subscription_ack_at=ACK.isoformat(),
            stream_cursor=CURSOR,
            stream_epoch=EPOCH,
            had_gap=False,
        )
    result = candidate_from_vike_event(
        baseline(),
        event=event(),
        raw_event_sha256="b" * 64,
        cursor="1794410001000-0000",
        local_first_known_at=(NOW + timedelta(milliseconds=100)).isoformat(),
        is_prospective=True,
        has_stream_gap=False,
        epoch_id="epoch_20261111_b",
    )
    assert result.status == "GAP_INELIGIBLE"
    assert result.gap_reason == "SOURCE_EPOCH_CHANGED"
