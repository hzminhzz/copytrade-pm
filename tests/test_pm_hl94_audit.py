"""Read-only 94-wallet ingest contract tests."""
from copytrade_pm.pm_hl94_audit import audit, normalized_fill
import json
import pytest


def sample(**updates):
    row = {"coin": "BTC", "px": "100", "sz": "2", "side": "B",
           "time": 1780000000000, "tid": 123, "startPosition": "-1",
           "closedPnl": "2.5", "hash": "0x123", "oid": 44}
    row.update(updates)
    return row


def test_two_vendor_spellings_and_signed_quantity():
    camel = normalized_fill(sample())
    snake = normalized_fill(sample(start_position="-1", closed_pnl="2.5"))
    assert camel == snake
    assert camel["signed_delta"] == "2"
    assert camel["end_position"] == "1"
    assert camel["closed_pnl"] == "2.5"
    short = normalized_fill(sample(side="A"))
    assert short["signed_delta"] == "-2"
    assert short["end_position"] == "-3"


@pytest.mark.parametrize("change", [{"tid": 0}, {"px": "0"},
                                     {"sz": "-1"}, {"side": "X"}])
def test_reject_invalid_trade_identity_or_economics(change):
    with pytest.raises(ValueError):
        normalized_fill(sample(**change))


def test_dedupe_does_not_collapse_distinct_partial_trade_ids(tmp_path):
    root = tmp_path
    cohort = root / "wallet_fills_90d"
    cohort.mkdir()
    wallet = "0x" + "a"*40
    entries = [sample(tid=123), sample(tid=123),
               sample(tid=124, startPosition="1", sz="1")]
    (cohort / "wallet.json").write_text(
        json.dumps({"address": wallet, "equity": "999", "fills": entries}))
    result = audit(root)
    assert result["counts"]["raw_fills"] == 3
    assert result["counts"]["unique_fills"] == 2
    assert result["counts"]["exact_duplicates"] == 1
    assert result["wallets"][0]["portfolio_eligible"] is False
    assert result["wallets"][0]["evidence_status"] == "RAW_FILLS_ONLY_NO_HISTORICAL_EQUITY"


def test_identical_timestamp_preserves_provider_sequence_not_tid_sort(tmp_path):
    folder = tmp_path / "wallet_fills_90d"
    folder.mkdir()
    rows = [sample(time=1780000000000, tid=999, sz="2", startPosition="0"),
            sample(time=1780000000000, tid=2, sz="2", side="A", startPosition="2")]
    (folder / "x.json").write_text(json.dumps({"address": "0x" + "b" * 40, "fills": rows}))
    record = audit(tmp_path)["wallets"][0]
    assert record["position_discontinuities"] == 0
    assert record["completed_episodes"] == 1
