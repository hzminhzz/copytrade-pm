"""E4 prospective source captures: all-DEX and subaccount scope fail closed."""

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_e4_prospective import (
    MAX_SUBACCOUNTS,
    _account_state,
    _dex_universe,
    _guarded_info,
    _subaccount_roster,
    _safe_dir,
)

WALLET = "0x" + "a" * 40
SUB = "0x" + "b" * 40


def sample_state():
    return {
        "user": WALLET,
        "clearinghouseStates": [
            [
                "",
                {
                    "marginSummary": {
                        "accountValue": "100",
                        "totalNtlPos": "100",
                        "totalMarginUsed": "20",
                    },
                    "assetPositions": [{"position": {"coin": "BTC", "szi": "0.1"}}],
                    "time": 1793294400000,
                },
            ],
            [
                "xyz",
                {
                    "marginSummary": {
                        "accountValue": "30",
                        "totalNtlPos": "10",
                        "totalMarginUsed": "5",
                    },
                    "assetPositions": [{"position": {"coin": "xyz:CL", "szi": "-5"}}],
                    "time": 1793294400000,
                },
            ],
        ],
    }


def test_e4_all_dex_parser_preserves_signed_source_hedges():
    result = _account_state(sample_state(), WALLET, {"default", "xyz"})
    assert result["dex_catalog_parity_verified"]
    assert result["position_count"] == 2
    assert result["positions"] == {
        "hyperliquid/mainnet:perp:default/BTC": "0.1",
        "hyperliquid/mainnet:perp:xyz/CL": "-5",
    }


def test_e4_missing_dex_or_duplicate_rejected():
    s = sample_state()
    with pytest.raises(ValueError, match="E4_ALL_DEXS_NOT_EQUAL_OFFICIAL_CATALOG"):
        _account_state(s, WALLET, {"default", "xyz", "other"})
    s["clearinghouseStates"].append(deepcopy(s["clearinghouseStates"][0]))
    with pytest.raises(ValueError, match="E4_INVALID_OR_DUPLICATE_DEX_NAME"):
        _account_state(s, WALLET, {"default", "xyz"})


def test_e4_requires_authoritative_dex_catalog():
    assert _dex_universe([None, {"name": "xyz"}]) == {"default", "xyz"}
    with pytest.raises(ValueError, match="E4_INVALID_DEX_CATALOG"):
        _dex_universe([{"name": "xyz"}])
    with pytest.raises(ValueError, match="E4_DUPLICATE_DEX"):
        _dex_universe([None, {"name": "xyz"}, {"name": "xyz"}])


def test_e4_subaccounts_validate_parent_and_empty_null():
    assert _subaccount_roster(None, WALLET) == []
    assert _subaccount_roster([{"subAccountUser": SUB, "master": WALLET}], WALLET) == [SUB]
    with pytest.raises(ValueError, match="E4_SUBACCOUNT_PARENT_MISMATCH"):
        _subaccount_roster([{"subAccountUser": SUB, "master": "0x" + "c" * 40}], WALLET)
    with pytest.raises(ValueError, match="E4_INVALID_SUBACCOUNT_CENSUS"):
        _subaccount_roster([{}] * (MAX_SUBACCOUNTS + 1), WALLET)
    with pytest.raises(ValueError, match="E4_DUPLICATE_OR_SELF_SUBACCOUNT"):
        _subaccount_roster([{"subAccountUser": SUB, "master": WALLET}] * 2, WALLET)


def test_official_account_abstraction_allows_only_documented_scalar(monkeypatch):
    import copytrade_pm.pm_e4_prospective as module

    class Response:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, _size):
            return self.data

    def wire_for(raw):
        def fake_open(request, timeout):
            assert timeout == 18
            assert json.loads(request.data)["type"] == "userAbstraction"
            return Response(raw)

        return fake_open

    monkeypatch.setattr(module, "urlopen", wire_for(b'"unifiedAccount"'))
    mode, raw, fingerprint = _guarded_info({"type": "userAbstraction", "user": WALLET})
    assert mode == "unifiedAccount"
    assert fingerprint == sha256(raw).hexdigest()
    monkeypatch.setattr(module, "urlopen", wire_for(b'"unrecognized"'))
    with pytest.raises(ValueError, match="E4_UNKNOWN_PUBLIC_ACCOUNT_ABSTRACTION"):
        _guarded_info({"type": "userAbstraction", "user": WALLET})


def test_e4_cannot_overwrite_live_generation(tmp_path):
    path = tmp_path / "ge4existinggeneration20261031"
    _safe_dir(path)
    assert (path.stat().st_mode & 0o077) == 0
    with pytest.raises(ValueError, match="E4_IMMUTABLE_GENERATION_ALREADY_EXISTS"):
        _safe_dir(path)
