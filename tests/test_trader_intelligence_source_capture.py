"""P1 read-only native snapshot inherits official parser and fail-closed source limits."""

from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest

from copytrade_pm.trader_intelligence_source_capture import collect


def identity_files(tmp_path, aliases=("S035-ENA",)):
    root = tmp_path / "historical-private-locators"
    root.mkdir(mode=0o700)
    addresses = {}
    for index, alias in enumerate(aliases):
        address = "0x" + f"{index + 1:040x}"
        (root / f"{alias}_{address}.json").write_text("{}")
        addresses[alias] = address
    return root, addresses


def stub_info(request):
    typ = request["type"]
    if typ == "perpDexs":
        answer = [None]
    elif typ == "subAccounts":
        answer = None
    elif typ == "clearinghouseState":
        assert request["dex"] == ""
        answer = {
            "marginSummary": {
                "accountValue": "1000",
                "totalNtlPos": "0",
                "totalMarginUsed": "0",
            },
            "assetPositions": [],
        }
    elif typ == "spotClearinghouseState":
        answer = {"balances": []}
    else:
        raise AssertionError("source capture requested an unapproved endpoint")
    raw = json.dumps(answer).encode()
    return answer, raw, sha256(raw).hexdigest()


def test_bounded_snapshot_uses_existing_parsers_without_claiming_equity(tmp_path):
    source, ids = identity_files(tmp_path)
    generation = tmp_path / "gTI_20261103_000000"
    summary = collect(
        source,
        generation,
        ("S035-ENA",),
        info=stub_info,
        clock=lambda: datetime(2026, 11, 3, 1, tzinfo=UTC),
    )
    assert summary["accounts_observed"] == 1
    assert summary["provider_calls"] == 4
    assert summary["trading_authorized"] is False
    assert summary["scientific_qualification"] == "NOT_QUALIFIED"
    record = json.loads((generation / "snapshot.json").read_text())
    assert record["roster_provenance"].startswith("PRIVATE_HISTORICAL_FILENAME")
    assert record["whole_wallet_equity_reconciled"] is False
    assert record["accounts"]["S035-ENA"]["independent_equity_attested"] is False
    assert record["accounts"]["S035-ENA"]["all_dexs"]["position_count"] == 0
    assert (
        record["accounts"]["S035-ENA"]["subject_identity_sha256"]
        == sha256(ids["S035-ENA"].encode()).hexdigest()
    )
    assert (generation / "raw" / "S035-ENA" / "perp-default.json").exists()
    assert record["accounts"]["S035-ENA"]["atomic_cross_dex_snapshot"] is False
    assert generation.stat().st_mode & 0o077 == 0
    assert (generation / "snapshot.json").stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match="EXISTS|ALREADY_EXISTS"):
        collect(source, generation, ("S035-ENA",), info=stub_info)


def test_unknown_alias_and_duplicate_subject_fail_closed_before_network(tmp_path):
    source, _ids = identity_files(tmp_path, ("AA", "BB"))

    def never_call(_request):
        raise AssertionError("no provider call expected")

    with pytest.raises(ValueError, match="MISSING_PRIVATE_WALLET_ALIAS"):
        collect(source, tmp_path / "gTI_20261103_000001", ("CC",), info=never_call)
    with pytest.raises(ValueError, match="BOUNDED_SOURCE_ROSTER"):
        collect(source, tmp_path / "gTI_20261103_000001", ("AA", "AA"), info=never_call)


def test_per_dex_http_response_is_separately_bound_to_each_native_dex(tmp_path):
    source, _ = identity_files(tmp_path, ("P1",))
    requests = []

    def multivenue(request):
        requests.append(request)
        if request["type"] == "perpDexs":
            raw = json.dumps([None, {"name": "xyz"}]).encode()
            return [None, {"name": "xyz"}], raw, sha256(raw).hexdigest()
        if request["type"] == "clearinghouseState":
            answer = {
                "marginSummary": {
                    "accountValue": "1000",
                    "totalNtlPos": "50" if request["dex"] == "xyz" else "0",
                    "totalMarginUsed": "1",
                },
                "assetPositions": (
                    [{"position": {"coin": "xyz:TEST", "szi": "2"}}]
                    if request["dex"] == "xyz"
                    else []
                ),
            }
        else:
            return stub_info(request)
        raw = json.dumps(answer).encode()
        return answer, raw, sha256(raw).hexdigest()

    generation = tmp_path / "gTI_20261103_000003"
    result = collect(source, generation, ("P1",), info=multivenue)
    book = json.loads((generation / "snapshot.json").read_text())["accounts"]["P1"]
    assert result["provider_calls"] == 5
    assert book["all_dexs"]["observed_dex_count"] == 2
    assert book["all_dexs"]["positions"]["hyperliquid/mainnet:perp:xyz/TEST"] == "2"
    assert book["atomic_cross_dex_snapshot"] is False
    assert [r["dex"] for r in requests if r["type"] == "clearinghouseState"] == ["", "xyz"]


def test_discovered_subaccounts_must_not_be_silently_truncated(tmp_path):
    source, ids = identity_files(tmp_path, ("AA", "BB", "CC"))
    network = []

    def oversized(request):
        network.append(request["type"])
        if request["type"] == "subAccounts":
            answer = [
                {
                    "master": request["user"],
                    "subAccountUser": "0x" + f"{1000 + index + len(network) * 100:040x}",
                }
                for index in range(16)
            ]
            raw = json.dumps(answer).encode()
            return answer, raw, sha256(raw).hexdigest()
        return stub_info(request)

    with pytest.raises(ValueError, match="TOO_MANY_DISCOVERED_SUBACCOUNTS"):
        collect(
            source,
            tmp_path / "gTI_20261103_000002",
            tuple(ids),
            info=oversized,
        )
    assert network.count("subAccounts") == 3
    assert "clearinghouseState" not in network
