"""Bounded, read-only, 10-account Combo2 acquisition without WebSocket slots."""

import json

import pytest

from copytrade_pm import pm_combo2_rest_capture as probe

IDENTITIES = {
    "W028": "0x" + "1" * 40,
    "CA-008": "0x" + "2" * 40,
    "W015": "0x" + "3" * 40,
}
CHILDREN = ["0x" + format(x, "x") * 40 for x in range(4, 11)]


def fake_info(query, *, children=CHILDREN, mode="unifiedAccount"):
    typ = query["type"]
    if typ == "perpDexs":
        value = [None, {"name": "xyz"}]
    elif typ == "subAccounts":
        value = (
            [{"master": query["user"], "subAccountUser": address} for address in children]
            if query["user"].lower() == IDENTITIES["W028"]
            else None
        )
    elif typ == "userAbstraction":
        value = mode
    elif typ == "spotClearinghouseState":
        value = {"balances": [{"coin": "USDC", "total": "1.0"}]}
    elif typ == "clearinghouseState":
        value = {"marginSummary": {"accountValue": "1"}, "assetPositions": []}
    else:
        raise AssertionError("unexpected non-read-only API call")
    raw = json.dumps(value, sort_keys=True).encode()
    return value, raw


def test_ten_accounts_complete_but_unified_equity_stays_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_resolved_identity", lambda _: IDENTITIES)
    calls = []

    def fetch(query):
        assert query["type"] in probe.READ_ONLY_TYPES
        calls.append(query["type"])
        return fake_info(query)

    result = probe.collect(tmp_path, tmp_path / "evidence", fetch=fetch, sleep_between=0)
    assert result["account_count"] == 10
    assert result["dex_count"] == 2
    assert result["all_subjects_captured"] is True
    assert result["follower_source_equity_verified"] is False
    assert result["network_order_mutations"] == 0
    assert result["request_count"] == 44
    assert len(calls) == 44
    assert all(value["account_mode"] == "unifiedAccount" for value in result["subjects"].values())
    assert result["managers"]["W028"]["subaccount_count"] == 7
    report = (tmp_path / "evidence" / "report.json").read_text()
    assert IDENTITIES["W028"] not in report
    assert (tmp_path / "evidence" / "report.json").stat().st_mode & 0o077 == 0


def test_excessive_subaccount_roster_halts_scope_without_order(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_resolved_identity", lambda _: IDENTITIES)
    extras = CHILDREN + ["0x" + "b" * 40]
    result = probe.collect(
        tmp_path,
        tmp_path / "evidence",
        fetch=lambda q: fake_info(q, children=extras),
        sleep_between=0,
    )
    assert result["errors"] == ["SOURCE_SCOPE_EXCEEDS_SHARED_10_ACCOUNT_LIMIT"]
    assert result["network_order_mutations"] == 0
    assert result["follower_source_equity_verified"] is False


def test_order_endpoint_never_reachable_even_with_injected_transport(monkeypatch):
    called = []

    def forbidden(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("network reached")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(PermissionError, match="ONLY_HYPERLIQUID_INFO_READS"):
        probe.read_info({"type": "order", "orders": []})
    with pytest.raises(ValueError, match="INVALID_INFO_CATALOG_QUERY"):
        probe.read_info({"type": "perpDexs", "action": "order"})
    assert called == []


def test_duplicate_immutable_generation_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "_resolved_identity", lambda _: IDENTITIES)
    path = tmp_path / "evidence"
    probe.collect(tmp_path, path, fetch=fake_info, sleep_between=0)
    with pytest.raises(ValueError, match="IMMUTABLE_CAPTURE_GENERATION_EXISTS"):
        probe.collect(tmp_path, path, fetch=fake_info, sleep_between=0)
