"""CF07: late bucket data, process crash and cache corruption stay nonfinancial."""

from datetime import UTC, datetime
from hashlib import sha256
import json
import multiprocessing
import os

import pytest

from copytrade_pm import pm_forward_journal as journal_module
from copytrade_pm import pm_offline_cache as cache_module
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_offline_cache import ImmutableCache
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from test_pm_forward_public_trades import BTC, FixedDateTime, known, normalized


@pytest.mark.parametrize("after_manifest", [False, True])
def test_cf07_late_seal_crash_and_corrupt_cache(tmp_path, monkeypatch, after_manifest):
    monkeypatch.setattr(journal_module, "datetime", FixedDateTime)
    journal = PaperJournal(tmp_path / "journal")
    journal.append_public_wallet_trades(normalized(1, 40))
    original = journal.observed_utc_net_delta(
        "wallet:17", BTC.key, bucket_start_at=known(0), as_of=known(301)
    )
    sealed = journal.persist_observed_utc_bucket(original)
    content = json.dumps(original, sort_keys=True).encode()
    deps = {"bucket": sha256(content).hexdigest()}
    cache = ImmutableCache(tmp_path / "cache", min_free_bytes=0)
    publish = cache_module._publish_exclusive

    def child():
        def cut(path, data):
            if path.name.endswith(".manifest.json"):
                if after_manifest:
                    publish(path, data)
                os._exit(74)
            return publish(path, data)

        cache_module._publish_exclusive = cut
        cache.publish("utc_bucket", deps, version="1", content=content)

    worker = multiprocessing.get_context("fork").Process(target=child)
    worker.start()
    worker.join(10)
    assert worker.exitcode == 74
    cache = ImmutableCache(tmp_path / "cache", min_free_bytes=0)
    assert cache.load("utc_bucket", deps, version="1") == (content if after_manifest else None)

    class LateDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 12, 6, tzinfo=UTC)

    monkeypatch.setattr(journal_module, "datetime", LateDateTime)
    restored = PaperJournal(tmp_path / "journal")
    assert restored.append_public_wallet_trades(normalized(1, 40))["duplicates"] == 2
    restored.append_public_wallet_trades(normalized(2, 60))
    changed = restored.observed_utc_net_delta(
        "wallet:17", BTC.key, bucket_start_at=known(0), as_of=known(361)
    )
    assert changed["late_event_count"] == 1
    assert changed["net_position_delta"] == original["net_position_delta"]
    assert changed["paper_admitted"] is False
    with pytest.raises(ValueError, match="CORRECTION"):
        restored.persist_observed_utc_bucket(changed)
    assert restored.persist_observed_utc_bucket(original) == sealed

    created = cache.publish("utc_bucket", deps, version="1", content=content)
    assert cache.load("utc_bucket", deps, version="1") == content
    target = cache.root / "utc_bucket" / created["key"][:2] / (created["key"] + ".data")
    target.write_bytes(b"x" * len(content))
    with pytest.raises(ManifestBlocked, match="CORRUPT_CACHE_SHA"):
        cache.load("utc_bucket", deps, version="1")
    # A rebuild uses a distinct semantic generation, retaining corrupt evidence.
    cache.publish("utc_bucket", deps, version="2", content=content)
    assert cache.load("utc_bucket", deps, version="2") == content
    assert target.read_bytes() == b"x" * len(content)
