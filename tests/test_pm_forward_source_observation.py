"""Official public all-DEX account observations cannot masquerade as whole-wallet NAV."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import SUB, WALLET, sample_state


BASE = datetime.fromtimestamp(1793294400, UTC)


def at(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def observed(*, frame=None, known_at=None, catalog=None, subaccounts=None):
    return read_public_all_dex_scope(
        alias="S035",
        address=WALLET,
        frame=frame
        if frame is not None
        else {"channel": "allDexsClearinghouseState", "data": sample_state()},
        dex_catalog=catalog if catalog is not None else [None, {"name": "xyz"}],
        discovered_subaccounts=subaccounts,
        first_known_at=known_at or at(2),
    )


def test_verified_per_dex_signed_position_preserved_but_no_wallet_admission(tmp_path):
    item = observed(subaccounts=[{"master": WALLET, "subAccountUser": SUB}])
    book = item["source_book"]
    assert book["positions"]["hyperliquid/mainnet:perp:default/BTC"] == "0.1"
    assert book["positions"]["hyperliquid/mainnet:perp:xyz/CL"] == "-5"
    assert item["status"] == "BLOCKED_INCOMPLETE_WHOLE_WALLET"
    assert "SOURCE_ACCOUNT_SCOPE_INCOMPLETE" in item["admission_reasons"]
    assert "INDEPENDENT_REAL_BOOK_ATTESTATION_UNAVAILABLE" in item["admission_reasons"]
    assert item["discovered_subaccount_count"] == 1
    assert item["whole_wallet_equity_attested"] is False
    assert book["source_equity"] is None
    assert book["whole_wallet_margin_reconciled"] is False
    assert [row["dex"] for row in book["per_dex_margin_diagnostics"]] == ["default", "xyz"]
    assert book["per_dex_margin_diagnostics"][0]["account_value_usd"] == "100"
    assert book["per_dex_margin_diagnostics"][1]["margin_used_usd"] == "5"
    assert set(book["position_margin_diagnostics"]) == set(book["positions"])
    assert book["source_marks"] == {}
    assert book["synthetic_fixture"] is False
    assert not admit_source_book(book, decision_at=at(2), fill_at=at(2)).admitted

    journal = PaperJournal(tmp_path / "paper")
    recorded = append_public_scope(journal, alias="S035", seq=1, receipt=item)
    assert recorded["cursor"] == 1
    assert recorded["status"] == "CAPTURED_ONLY"
    assert journal.source_status("S035")["paper_admitted"] is False
    assert PaperJournal(journal.root).source_status("S035")["cursor"] == 1


def test_official_native_position_values_supply_independent_timed_leader_marks():
    frame = sample_state()
    frame["clearinghouseStates"][0][1]["assetPositions"][0]["position"]["positionValue"] = "1200"
    frame["clearinghouseStates"][1][1]["assetPositions"][0]["position"]["positionValue"] = "75"
    receipt = observed(frame={"channel": "allDexsClearinghouseState", "data": frame})
    book = receipt["source_book"]
    btc = "hyperliquid/mainnet:perp:default/BTC"
    hip = "hyperliquid/mainnet:perp:xyz/CL"
    assert {key: Decimal(value) for key, value in book["source_marks"].items()} == {
        btc: Decimal("12000"),
        hip: Decimal("15"),
    }
    for market in (btc, hip):
        mark = book["source_mark_evidence"][market]
        assert mark["mark"] == book["source_marks"][market]
        assert mark["event_at"] == at(0)
        assert mark["first_known_at"] == at(2)
        assert mark["native_frame_sha"] == book["provider_raw_sha"]
    assert book["snapshot_sha"]


def test_incomplete_catalog_wrong_address_unknown_clock_and_future_rejected():
    with pytest.raises(ValueError, match="E4_ALL_DEXS_WRONG_WALLET"):
        observed(
            frame={
                "channel": "allDexsClearinghouseState",
                "data": {**sample_state(), "user": SUB},
            }
        )
    with pytest.raises(ValueError, match="E4_ALL_DEXS_NOT_EQUAL_OFFICIAL_CATALOG"):
        observed(catalog=[None, {"name": "xyz"}, {"name": "vntl"}])
    no_clock = deepcopy(sample_state())
    no_clock["clearinghouseStates"][1][1].pop("time")
    with pytest.raises(ValueError, match="SOURCE_PER_DEX_EVENT_CLOCK_UNKNOWN"):
        observed(frame={"channel": "allDexsClearinghouseState", "data": no_clock})
    with pytest.raises(ValueError, match="SOURCE_PROVIDER_EVENT_IN_FUTURE"):
        observed(known_at=at(-2))
    with pytest.raises(ValueError, match="SOURCE_PROVIDER_DEX_BOOK_STALE"):
        observed(known_at=at(300))


def test_forged_admission_claim_or_synthetic_bit_refused(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    item = observed()
    forged = {**item, "whole_wallet_equity_attested": True}
    with pytest.raises(ValueError, match="SOURCE_FALSE_ATTESTATION_REFUSED"):
        append_public_scope(j, alias="S035", seq=1, receipt=forged)
    fake = deepcopy(item)
    fake["source_book"]["synthetic_fixture"] = True
    with pytest.raises(ValueError, match="SOURCE_BOOK_RECEIPT_HASH_MISMATCH"):
        append_public_scope(j, alias="S035", seq=1, receipt=fake)
    assert j.source_status("S035")["cursor"] == 0
