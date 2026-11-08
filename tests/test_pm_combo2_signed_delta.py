"""Genuine two-snapshot REST deltas: signed, subaccount-aggregated and causal."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json

import pytest

from copytrade_pm import pm_combo2_rest_capture as capture
from copytrade_pm.pm_combo2_signed_delta import compare_generations

ADDRESSES = {
    "W028": "0x" + "1" * 40,
    "CA-008": "0x" + "2" * 40,
    "W015": "0x" + "3" * 40,
}
CHILDREN = ["0x" + format(x, "x") * 40 for x in range(4, 11)]
HYPE = "hyperliquid/mainnet:perp:default/HYPE"
ETH = "hyperliquid/mainnet:perp:default/ETH"


def scenario_fetch(books, *, children=CHILDREN, dexs=None):
    def fetch(query):
        kind = query["type"]
        address = query.get("user", "").lower()
        if kind == "perpDexs":
            payload = [None] if dexs is None else [None, {"name": "xyz"}]
        elif kind == "subAccounts":
            payload = (
                [{"master": address, "subAccountUser": child} for child in children]
                if address == ADDRESSES["W028"]
                else None
            )
        elif kind == "userAbstraction":
            payload = "unifiedAccount"
        elif kind == "spotClearinghouseState":
            payload = {"balances": [{"coin": "USDC", "total": "200"}]}
        elif kind == "clearinghouseState":
            dex = query.get("dex", "default")
            payload = {
                "marginSummary": {"accountValue": "0"},
                "assetPositions": [
                    {"position": {"coin": coin, "szi": qty}}
                    for coin, qty in books.get((address, dex), {}).items()
                ],
            }
        else:
            raise AssertionError("unexpected non-information API request")
        data = json.dumps(payload, sort_keys=True).encode()
        return payload, data

    return fetch


def collector(tmp_path, monkeypatch, label, books, **kwargs):
    monkeypatch.setattr(capture, "_resolved_identity", lambda _: ADDRESSES)
    root = tmp_path / label
    capture.collect(tmp_path, root, fetch=scenario_fetch(books, **kwargs), sleep_between=0)
    return root


def test_opposing_subaccount_transfers_are_not_new_wallet_exposure(tmp_path, monkeypatch):
    before = {(ADDRESSES["W028"], "default"): {"HYPE": "2"}}
    after = {
        (ADDRESSES["W028"], "default"): {"HYPE": "3"},
        (CHILDREN[0], "default"): {"HYPE": "-1"},
    }
    a = collector(tmp_path, monkeypatch, "gC2-1", before)
    b = collector(tmp_path, monkeypatch, "gC2-2", after)
    result = compare_generations(a, b)
    assert result["signals"] == []
    assert result["source_equity_verified"] is False
    assert result["execution_authorized"] is False


def test_first_known_later_complete_book_and_exact_300s(tmp_path, monkeypatch):
    old = {
        (ADDRESSES["W028"], "default"): {"HYPE": "2"},
        (ADDRESSES["CA-008"], "default"): {"ETH": "-2"},
    }
    new = {
        (ADDRESSES["W028"], "default"): {"HYPE": "3"},
        (CHILDREN[0], "default"): {"HYPE": "-0.75"},
        (ADDRESSES["CA-008"], "default"): {"ETH": "-2.2"},
    }
    a = collector(tmp_path, monkeypatch, "gC2-1", old)
    b = collector(tmp_path, monkeypatch, "gC2-2", new)
    res = compare_generations(a, b)
    signals = {x["instrument"]: x for x in res["signals"]}
    assert set(signals) == {HYPE, ETH}
    assert signals[HYPE]["manager"] == "W028"
    assert signals[HYPE]["signed_quantity_before"] == "2"
    assert Decimal(signals[HYPE]["signed_delta"]) == Decimal("0.25")
    assert signals[HYPE]["change_kind"] == "INCREASE_LONG"
    assert signals[ETH]["change_kind"] == "INCREASE_SHORT"
    assert signals[ETH]["signed_delta"] == "-0.2"
    assert res["execution_authorized"] is False
    for event in signals.values():
        assert datetime.fromisoformat(event["due_at"]) - datetime.fromisoformat(
            event["first_known_at"]
        ) == timedelta(seconds=300)
        assert event["source_event_at"] is None
        assert not event["source_equity_verified"]
        assert event["subaccounts_included"]
        assert len(event["signal_id"]) == 64
    assert compare_generations(a, b) == res


def test_reversals_reductions_close_preserve_sign(tmp_path, monkeypatch):
    old = {
        (ADDRESSES["W028"], "default"): {"HYPE": "2"},
        (ADDRESSES["CA-008"], "default"): {"ETH": "-2"},
    }
    new = {
        (ADDRESSES["W028"], "default"): {"HYPE": "-1"},
        (ADDRESSES["CA-008"], "default"): {},
    }
    a = collector(tmp_path, monkeypatch, "gC2-1", old)
    b = collector(tmp_path, monkeypatch, "gC2-2", new)
    actual = {s["manager"]: s["change_kind"] for s in compare_generations(a, b)["signals"]}
    assert actual == {"W028": "REVERSE_SHORT", "CA-008": "CLOSE"}


@pytest.mark.parametrize("target", ["report", "frame", "metadata"])
def test_tampered_source_evidence_fails_closed(tmp_path, monkeypatch, target):
    a = collector(tmp_path, monkeypatch, "gC2-1", {})
    b = collector(tmp_path, monkeypatch, "gC2-2", {})
    paths = {
        "report": b / "report.json",
        "frame": b / "raw" / "W028-dex-default.json",
        "metadata": b / "metadata" / "W028-dex-default.json",
    }
    if target == "report":
        obj = json.loads(paths[target].read_text())
        obj["account_count"] = 9
        paths[target].write_text(json.dumps(obj))
    elif target == "frame":
        paths[target].write_text("{}")
    else:
        obj = json.loads(paths[target].read_text())
        obj["sha256"] = "e" * 64
        paths[target].write_text(json.dumps(obj))
    with pytest.raises(ValueError):
        compare_generations(a, b)


def test_scope_drift_and_gap_rejected(tmp_path, monkeypatch):
    a = collector(tmp_path, monkeypatch, "gC2-1", {})
    b = collector(tmp_path, monkeypatch, "gC2-2", {}, dexs=True)
    with pytest.raises(ValueError, match="REST_SUBACCOUNT_OR_DEX_SCOPE_DRIFT"):
        compare_generations(a, b)
    monkeypatch.setattr(
        capture, "_now", lambda: (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    )
    c = collector(tmp_path, monkeypatch, "gC2-3", {})
    with pytest.raises(ValueError, match="REST_OBSERVATION_GAP"):
        compare_generations(a, c)


def test_no_synthetic_equity_promotion_or_network_orders(tmp_path, monkeypatch):
    a = collector(tmp_path, monkeypatch, "gC2-1", {})
    b = collector(
        tmp_path,
        monkeypatch,
        "gC2-2",
        {
            (ADDRESSES["W028"], "default"): {"HYPE": "10"},
        },
    )
    report = compare_generations(a, b)
    assert report["signals"][0]["signed_quantity_before"] == "0"
    assert report["signals"][0]["change_kind"] == "OPEN_LONG"
    assert report["source_equity_verified"] is False
    assert report["signals"][0]["execution_authorized"] is False
