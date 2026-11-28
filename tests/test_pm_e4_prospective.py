"""Official REST census and account-mode validation remain fail closed."""

from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_e4_prospective import dex_universe, guarded_info

WALLET = "0x" + "a" * 40


def test_e4_requires_authoritative_dex_catalog():
    assert dex_universe([None, {"name": "xyz"}]) == {"default", "xyz"}
    with pytest.raises(ValueError, match="E4_INVALID_DEX_CATALOG"):
        dex_universe([{"name": "xyz"}])
    with pytest.raises(ValueError, match="E4_DUPLICATE_DEX"):
        dex_universe([None, {"name": "xyz"}, {"name": "xyz"}])


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
    mode, raw, fingerprint = guarded_info({"type": "userAbstraction", "user": WALLET})
    assert mode == "unifiedAccount"
    assert fingerprint == sha256(raw).hexdigest()
    monkeypatch.setattr(module, "urlopen", wire_for(b'"unrecognized"'))
    with pytest.raises(ValueError, match="E4_UNKNOWN_PUBLIC_ACCOUNT_ABSTRACTION"):
        guarded_info({"type": "userAbstraction", "user": WALLET})
