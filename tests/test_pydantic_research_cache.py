"""Cache schema and returned-byte integrity through the existing research owner."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm import pm_offline_cache as module
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from test_pm_offline_sweep_cache import cache, inputs


def test_cache_returns_the_exact_bytes_it_verified(tmp_path, monkeypatch):
    store = cache(tmp_path)
    deps = inputs()
    created = store.publish("market_panel", deps, version="1", content=b"good")
    target = store.root / "market_panel" / created["key"][:2] / (created["key"] + ".data")
    checksum = module._checksum
    original_read = Path.read_bytes

    def checksum_then_change(path):
        result = checksum(path)
        if path == target:
            path.write_bytes(b"evil")
        return result

    def read_then_change(path):
        result = original_read(path)
        if path == target:
            path.write_bytes(b"evil")
        return result

    monkeypatch.setattr(module, "_checksum", checksum_then_change)
    monkeypatch.setattr(Path, "read_bytes", read_then_change)
    try:
        result = store.load("market_panel", deps, version="1")
    except ManifestBlocked:
        return
    assert result == b"good"
    assert sha256(result).hexdigest() == created["sha256"]


@pytest.mark.parametrize("damage", ["list", "bool_size", "unknown_authority", "unknown_schema"])
def test_cache_manifest_ambiguity_is_explicitly_blocked(tmp_path, damage):
    store = cache(tmp_path)
    deps = inputs()
    made = store.publish("market_panel", deps, version="1", content=b"x")
    metadata = store.root / "market_panel" / made["key"][:2] / (made["key"] + ".manifest.json")
    doc = json.loads(metadata.read_text())
    if damage == "list":
        doc = []
    elif damage == "bool_size":
        doc["bytes"] = True
    elif damage == "unknown_authority":
        doc["scientifically_qualified"] = True
    else:
        doc["schema"] = "pm_offline_cache_v999"
    metadata.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked):
        store.load("market_panel", deps, version="1")
