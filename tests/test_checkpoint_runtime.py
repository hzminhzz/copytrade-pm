"""Canonical source journals preserve CWSA identity through restart."""

import asyncio
from contextlib import closing
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm import pm_cwsa_source_observer as entry
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_checkpoint_journal import CwsaPolicy
from copytrade_pm.pm_checkpoint_source import CheckpointScope
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import canonical
from test_checkpoint_source import ADDRESS, BOUNDARY, limits


def configuration():
    parents = {"fixture-leader": ADDRESS}
    dexes = ("default", "xyz")
    scope = CheckpointScope(
        source_id="fixture-leader",
        account_sha=sha256(ADDRESS.encode()).hexdigest(),
        generation=digest(["hyperliquid/mainnet:perp", ADDRESS, dexes]),
        selection_sha=digest({a: sha256(v.encode()).hexdigest() for a, v in parents.items()}),
        dexes=dexes,
    )
    policy = CwsaPolicy(limits=limits(), measurement_sha="c" * 64)
    body = {
        "schema": "cwsa_observer_config_v1",
        "policy": policy.model_dump(mode="json"),
        "scopes": {scope.source_id: scope.model_dump(mode="json")},
        "first_checkpoint_ms": BOUNDARY,
        "workers": 2,
        "weight_per_second": 8,
    }
    return parents, scope, policy, body


class Clock:
    def __init__(self):
        self.at = BOUNDARY - 1
        self.quantity = "2"
        self.calls = []

    async def wait(self, milliseconds):
        self.at += milliseconds

    def info(self, request):
        self.calls.append(dict(request))
        if request["type"] == "perpDexs":
            body = [None, {"name": "xyz"}]
        else:
            body = {
                "time": self.at,
                "assetPositions": []
                if request.get("dex")
                else [
                    {"position": {"coin": "BTC", "szi": self.quantity, "positionValue": "20000"}}
                ],
            }
        raw = json.dumps(body).encode()
        return body, raw, sha256(raw).hexdigest()


def collect(journal, config, parents, clock):
    return asyncio.run(
        entry.observe_checkpoints(
            journal,
            parents,
            config,
            once=True,
            info=clock.info,
            now_ms=lambda: clock.at,
            wait=clock.wait,
        )
    )


def test_rest_mode_uses_one_source_journal_and_resumes_without_backfill(tmp_path):
    parents, scope, policy, raw = configuration()
    config = entry.CheckpointObserverConfig.model_validate_json(canonical(raw))
    clock = Clock()
    journal = PaperJournal(tmp_path / "source")
    first = collect(journal, config, parents, clock)
    assert first["outcomes"] == {"BASELINE": 1}
    clock.at += 300000
    clock.quantity = "3"
    second = collect(journal, config, parents, clock)
    assert second["outcomes"] == {"CHANGED": 1}
    changed = journal.checkpoint_history(scope, policy.epoch)[-1].effect
    assert changed.checkpoint_ms == BOUNDARY + 300000
    assert changed.published_ms == BOUNDARY + 300000
    # Miss a grid boundary during downtime: no historical collection or opening.
    clock.at += 600000
    restarted = collect(PaperJournal(journal.root), config, parents, clock)
    assert restarted["outcomes"] == {"RECOVERY_BASELINE": 1}
    history = journal.checkpoint_history(scope, policy.epoch)
    assert [t.effect.kind for t in history if t.effect] == [
        "BASELINE",
        "CHANGED",
        "UNAVAILABLE",
        "RECOVERY_BASELINE",
    ]
    assert sum(t.event == "REGISTER" for t in history) == 1
    assert len(clock.calls) == 9
    assert {c.get("dex", "default") for c in clock.calls if c["type"] == "clearinghouseState"} == {
        "default",
        "xyz",
    }
    with closing(sqlite3.connect(journal.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_pinned_configuration_requires_complete_limits_and_exact_selected_roster(tmp_path):
    parents, _, _, body = configuration()
    path = tmp_path / "config.json"
    raw = canonical(body)
    path.write_bytes(raw)
    path.chmod(0o600)
    config = entry.load_checkpoint_configuration(path, sha256(raw).hexdigest(), parents)
    assert config.policy.limits.max_state_age_ms == 4000
    with pytest.raises(ValueError, match="PIN"):
        entry.load_checkpoint_configuration(path, "f" * 64, parents)
    with pytest.raises(ValueError, match="ROSTER"):
        entry.load_checkpoint_configuration(path, sha256(raw).hexdigest(), {"other": ADDRESS})
    del body["policy"]["limits"]["max_state_age_ms"]
    with pytest.raises(ValueError):
        entry.CheckpointObserverConfig.model_validate(body)


def test_single_existing_source_entrypoint_lease_rejects_second_owner(tmp_path):
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    with entry.source_lease(root):
        with pytest.raises(ValueError, match="SOURCE_AUTHORITY_LEASE"):
            with entry.source_lease(root):
                pytest.fail("second authority")
