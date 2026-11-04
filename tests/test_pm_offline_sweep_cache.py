"""Crash-safe immutable cache lineage and corruption regression."""

from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_cache import ImmutableCache
from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid


def inputs():
    return {"source": sha256(b"source-v1").hexdigest(), "policy": sha256(b"v1").hexdigest()}


def cache(tmp_path):
    return ImmutableCache(tmp_path / "private", max_object_bytes=1024, min_free_bytes=0)


def test_identical_publication_is_hit_and_sha_bound(tmp_path):
    store = cache(tmp_path)
    deps = inputs()
    first = store.publish("eligible_tape", deps, version="1", content=b"abc")
    second = store.publish("eligible_tape", deps, version="1", content=b"abc")
    assert first["status"] == "CACHE_CREATED"
    assert second["status"] == "CACHE_HIT"
    assert first["key"] == second["key"]
    assert store.load("eligible_tape", deps, version="1") == b"abc"
    assert (store.root.stat().st_mode & 0o077) == 0


def test_dependency_changes_invalidate_only_descendants(tmp_path):
    store = cache(tmp_path)
    deps = inputs()
    first = store.publish("eligible_tape", deps, version="1", content=b"v1")
    changed = {**deps, "source": sha256(b"source-v2").hexdigest()}
    assert store.load("eligible_tape", changed, version="1") is None
    second = store.publish("eligible_tape", changed, version="1", content=b"v2")
    assert first["key"] != second["key"]
    assert store.load("eligible_tape", deps, version="1") == b"v1"
    assert store.load("eligible_tape", changed, version="1") == b"v2"


def test_same_key_conflicting_bytes_refused(tmp_path):
    store = cache(tmp_path)
    deps = inputs()
    store.publish("source_book", deps, version="1", content=b"good")
    with pytest.raises(ManifestBlocked, match="IMMUTABLE_CACHE_KEY_CONFLICT"):
        store.publish("source_book", deps, version="1", content=b"different")


def test_corrupt_bytes_and_manifest_refused(tmp_path):
    store = cache(tmp_path)
    deps = inputs()
    created = store.publish("market_panel", deps, version="1", content=b"good")
    data = store.root / "market_panel" / created["key"][:2] / (created["key"] + ".data")
    data.write_bytes(b"evil")
    with pytest.raises(ManifestBlocked, match="CORRUPT_CACHE_SHA"):
        store.load("market_panel", deps, version="1")
    data.write_bytes(b"good")
    metadata = data.with_name(created["key"] + ".manifest.json")
    doc = json.loads(metadata.read_text())
    doc["version"] = "forged"
    metadata.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="CACHE_DEPENDENCY_MISMATCH"):
        store.load("market_panel", deps, version="1")


def test_unsealed_object_is_not_a_cache_hit(tmp_path):
    store = cache(tmp_path)
    deps = inputs()
    key = store.identity("market_panel", deps, version="1")
    folder = store.root / "market_panel" / key[:2]
    folder.mkdir(parents=True, mode=0o700)
    folder.parent.chmod(0o700)
    (folder / (key + ".data")).write_bytes(b"orphan")
    assert store.load("market_panel", deps, version="1") is None
    with pytest.raises(ManifestBlocked, match="IMMUTABLE_CACHE_KEY_CONFLICT"):
        store.publish("market_panel", deps, version="1", content=b"new")


def test_symlink_and_bad_budget_rejected(tmp_path):
    with pytest.raises(ManifestInvalid, match="INVALID_CACHE_BUDGET"):
        ImmutableCache(tmp_path / "private", max_object_bytes=0)
    real = tmp_path / "other"
    real.mkdir()
    (tmp_path / "redirect").symlink_to(real)
    with pytest.raises(ManifestInvalid, match="SYMLINK_CACHE_ROOT"):
        ImmutableCache(tmp_path / "redirect")


def test_symlinked_cache_namespace_is_rejected(tmp_path):
    store = cache(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "market_panel").symlink_to(outside)
    with pytest.raises(ManifestInvalid, match="SYMLINK_CACHE_NAMESPACE"):
        store.load("market_panel", inputs(), version="1")


def test_object_size_is_bounded(tmp_path):
    store = cache(tmp_path)
    with pytest.raises(ManifestInvalid, match="CACHE_OBJECT_TOO_LARGE"):
        store.publish("market_panel", inputs(), version="1", content=b"x" * 1025)
