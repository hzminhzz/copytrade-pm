"""CWSA outcomes through the existing paper journal, not a parallel store."""

from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from copytrade_pm.pm_checkpoint_source import GRID_MS, collect_checkpoint
from copytrade_pm.pm_forward_journal import PaperJournal
from test_checkpoint_source import ADDRESS, BOUNDARY, limits, scope


def sample(
    journal,
    boundary,
    quantity="2",
    fail=False,
    provider_ms=None,
    source_scope=None,
    address=ADDRESS,
):
    def native(request):
        if request["type"] == "perpDexs":
            body = [None, {"name": "xyz"}]
        elif fail and request.get("dex") == "xyz":
            raise TimeoutError("fixture")
        else:
            body = {
                "time": boundary if provider_ms is None else provider_ms,
                "assetPositions": []
                if request.get("dex") == "xyz" or quantity == "0"
                else [
                    {
                        "position": {
                            "coin": "BTC",
                            "szi": quantity,
                            "positionValue": str(abs(Decimal(quantity)) * 10000),
                        }
                    }
                ],
            }
        raw = json.dumps(body).encode()
        return body, raw, sha256(raw).hexdigest()

    return collect_checkpoint(
        source_scope or scope(),
        address,
        checkpoint_ms=boundary,
        limits=limits(),
        evidence_root=journal.root,
        info=native,
        now_ms=lambda: boundary + 100,
    )


def register(journal):
    from copytrade_pm.pm_checkpoint_journal import CwsaPolicy

    policy = CwsaPolicy(limits=limits(), measurement_sha="c" * 64)
    journal.register_checkpoint_source(
        scope(), policy, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1
    )
    return policy


def test_baseline_unchanged_and_one_genuine_change_survive_restart(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    first = journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101
    )
    assert first.kind == "BASELINE"
    assert first.signal_id is None
    same = journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY + GRID_MS, "2.000"), BOUNDARY + GRID_MS + 101
    )
    assert same.kind == "UNCHANGED"
    assert same.economic_sha == first.economic_sha
    assert same.outcome_id != first.outcome_id
    assert same.signal_id is None
    candidate = sample(journal, BOUNDARY + 2 * GRID_MS, "3")
    changed = journal.append_checkpoint_sample(policy.epoch, candidate, candidate.validated_ms + 1)
    assert changed.kind == "CHANGED"
    assert changed.signal_id not in (None, changed.outcome_id, changed.economic_sha)
    restarted = PaperJournal(journal.root)
    assert (
        restarted.append_checkpoint_sample(policy.epoch, candidate, candidate.validated_ms + 2)
        == changed
    )
    history = restarted.checkpoint_history(scope(), policy.epoch)
    assert [t.event for t in history] == ["REGISTER", "SAMPLE", "SAMPLE", "SAMPLE"]
    assert history[-1].predecessor.phase == "CONTINUOUS"
    assert history[-1].successor.phase == "CONTINUOUS"
    assert history[-1].effect == changed
    assert history[-1].guard == "COMPLETE_CONTINUOUS"


def test_gap_recovery_and_wallet_local_failure_never_open(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    journal.append_checkpoint_sample(policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101)
    recovery = journal.append_checkpoint_sample(
        policy.epoch,
        sample(journal, BOUNDARY + 2 * GRID_MS, "9"),
        BOUNDARY + 2 * GRID_MS + 101,
    )
    assert recovery.kind == "RECOVERY_BASELINE"
    assert recovery.signal_id is None
    assert [
        t.effect.kind for t in journal.checkpoint_history(scope(), policy.epoch) if t.effect
    ] == [
        "BASELINE",
        "UNAVAILABLE",
        "RECOVERY_BASELINE",
    ]
    failed = journal.append_checkpoint_sample(
        policy.epoch,
        sample(journal, BOUNDARY + 3 * GRID_MS, fail=True),
        BOUNDARY + 3 * GRID_MS + 101,
    )
    assert failed.kind == "UNAVAILABLE"
    assert failed.positions == ()
    assert failed.signal_id is None
    recovered = journal.append_checkpoint_sample(
        policy.epoch,
        sample(journal, BOUNDARY + 4 * GRID_MS, "0"),
        BOUNDARY + 4 * GRID_MS + 101,
    )
    assert recovered.kind == "RECOVERY_BASELINE"
    assert recovered.positions == ()
    assert recovered.signal_id is None


def test_equivocation_is_durable_and_cannot_replace_existing_outcome(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    original = sample(journal, BOUNDARY)
    baseline = journal.append_checkpoint_sample(policy.epoch, original, BOUNDARY + 101)
    conflicting = sample(journal, BOUNDARY, "50")
    rejected = journal.append_checkpoint_sample(policy.epoch, conflicting, BOUNDARY + 102)
    assert rejected.guard == "EQUIVOCATION"
    assert rejected.effect is None
    assert rejected.successor.phase == "FENCED"
    assert journal.append_checkpoint_sample(policy.epoch, original, BOUNDARY + 103) == baseline
    restarted = PaperJournal(journal.root)
    assert restarted.checkpoint_history(scope(), policy.epoch)[-1] == rejected
    next_sample = sample(restarted, BOUNDARY + GRID_MS, "51")
    result = restarted.append_checkpoint_sample(
        policy.epoch, next_sample, next_sample.validated_ms + 1
    )
    assert result.kind == "RECOVERY_BASELINE"
    assert result.signal_id is None


@pytest.mark.parametrize("fault", ["vector", "clock", "stale", "publication", "missing_raw"])
def test_independently_replayed_proof_and_publication_guards(tmp_path, fault):
    from copytrade_pm.pm_checkpoint_source import CheckpointSample

    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    candidate = sample(journal, BOUNDARY)
    body = candidate.model_dump()
    published = BOUNDARY + 101
    if fault == "vector":
        body["positions"] = ()
    elif fault == "clock":
        body["receipts"] = tuple(
            r.model_dump() | {"requested_ms": BOUNDARY - 1} for r in candidate.receipts
        )
    elif fault == "stale":
        body["started_ms"] = BOUNDARY + 10_000
        body["received_ms"] = BOUNDARY + 10_000
        body["validated_ms"] = BOUNDARY + 10_000
        published = BOUNDARY + 10_001
    elif fault == "publication":
        published = BOUNDARY + limits().publication_grace_ms
    else:
        for item in journal.root.rglob("*.zlib"):
            item.unlink()
    altered = CheckpointSample(**body)
    outcome = journal.append_checkpoint_sample(policy.epoch, altered, published)
    assert outcome.kind == "QUARANTINE"
    assert outcome.signal_id is None
    assert journal.checkpoint_history(scope(), policy.epoch)[-1].successor.phase == "FENCED"


def crash_worker(root, boundary):
    from contextlib import contextmanager

    journal = PaperJournal(Path(root))
    policy = register(journal)
    candidate = sample(journal, BOUNDARY + GRID_MS, "3")
    original_writer = journal._writer

    @contextmanager
    def instrumented():
        with original_writer() as db:

            def trace(sql):
                if boundary == "before_commit" and sql == "COMMIT":
                    os.kill(os.getpid(), signal.SIGKILL)

            db.set_trace_callback(trace)
            yield db

    journal._writer = instrumented
    journal.append_checkpoint_sample(policy.epoch, candidate, candidate.validated_ms + 1)
    os.kill(os.getpid(), signal.SIGKILL)


@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_sigkill_has_one_atomic_outcome_or_none(tmp_path, boundary):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    journal.append_checkpoint_sample(policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101)
    code = (
        "from test_checkpoint_journal import crash_worker;"
        "import sys;crash_worker(sys.argv[1],sys.argv[2])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(journal.root), boundary],
        env=os.environ | {"PYTHONPATH": os.pathsep.join(sys.path)},
        timeout=15,
    )
    assert result.returncode == -signal.SIGKILL
    restarted = PaperJournal(journal.root)
    history = restarted.checkpoint_history(scope(), policy.epoch)
    assert len(history) == (2 if boundary == "before_commit" else 3)
    candidate = sample(restarted, BOUNDARY + GRID_MS, "3")
    outcome = restarted.append_checkpoint_sample(
        policy.epoch, candidate, candidate.validated_ms + 1
    )
    assert outcome.kind == "CHANGED"
    assert len(restarted.checkpoint_history(scope(), policy.epoch)) == 3


def test_reordered_observation_fences_without_rewinding_the_source(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    journal.append_checkpoint_sample(policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101)
    old = sample(journal, BOUNDARY - GRID_MS, "100")
    rejection = journal.append_checkpoint_sample(policy.epoch, old, BOUNDARY + 102)
    assert rejection.event == "LATE"
    assert rejection.guard == "REORDERED"
    assert rejection.successor.next_checkpoint_ms == BOUNDARY + GRID_MS
    assert rejection.effect is None
    assert len(journal.checkpoint_history(scope(), policy.epoch)) == 3


def test_wallet_fault_does_not_change_another_registered_scope(tmp_path):
    from copytrade_pm.pm_checkpoint_source import CheckpointScope

    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    other = CheckpointScope(
        **(
            scope().model_dump()
            | {
                "source_id": "fixture-other",
                "account_sha": "d" * 64,
                "generation": "e" * 64,
            }
        )
    )
    journal.register_checkpoint_source(
        other, policy, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1
    )
    original = journal.checkpoint_history(other, policy.epoch)
    journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY, fail=True), BOUNDARY + 101
    )
    assert journal.checkpoint_history(other, policy.epoch) == original
    assert original[-1].successor.phase == "UNANCHORED"
