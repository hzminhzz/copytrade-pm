"""Strict causal source contracts shared by canonical observation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from copytrade_pm.pm_source_contracts import (
    Position,
    SourceEvidenceRef,
    UnavailableObservation,
    exact_decimal,
    utc_clock,
)

T = datetime(2026, 11, 4, 4, tzinfo=UTC)


def test_typed_contracts_reject_coercion_unknown_fields_and_naive_clocks():
    key = "hyperliquid/mainnet:perp:default/BTC"
    with pytest.raises(ValueError):
        Position(instrument=key, quantity="20")
    with pytest.raises(ValueError):
        Position(instrument=key, quantity=Decimal("NaN"))
    with pytest.raises(ValueError):
        Position(instrument=key, quantity=Decimal(20), permit=True)
    with pytest.raises(ValueError):
        utc_clock("2026-11-01T00:00:00")
    with pytest.raises(ValueError):
        SourceEvidenceRef(
            source_id="test",
            raw_sha="a" * 64,
            native_frame_sha="b" * 64,
            first_known_at=T,
            source_event_at=T + timedelta(seconds=1),
        )
    with pytest.raises(ValueError):
        UnavailableObservation(status="VALID", reason="schema alone is not admission")
    assert exact_decimal("1.23456789012345678901234567890123456789") == Decimal(
        "1.23456789012345678901234567890123456789"
    )
