"""Offline baseline through existing owners; never a live-feed or alpha claim."""

from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import resource
import statistics
import time

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_pm_forward_persistent_source import account, shifted, T
from test_pm_forward_observed_paper import BTC, RAW_MARKET, add_quote, add_source, at, registry


def test_independent_semantic_oracle():
    corpus = json.loads(
        (Path(__file__).parent / "fixtures/pydantic_source_oracles.json").read_text()
    )
    for case in corpus["cases"]:
        values = [Decimal(v) for v in case["quantities"]]
        expected = ["BASELINE"] + [
            "OBSERVED_STATE_CHANGE" if a != b else "UNCHANGED_STATE"
            for a, b in zip(values, values[1:])
        ]
        assert expected == case["corrected"]


def test_source_matches_versioned_independent_oracle(tmp_path):
    corpus = json.loads(
        (Path(__file__).parent / "fixtures/pydantic_source_oracles.json").read_text()
    )
    for case in corpus["cases"]:
        source, _ = account(tmp_path / case["name"])
        actual = [
            source.observe(shifted(i, qty), (T + timedelta(seconds=i)).isoformat())[
                "classification"
            ]
            for i, qty in enumerate(case["quantities"])
        ]
        oracle = (
            "corrected" if source.checkpoint.get("source_semantics_version") == 2 else "baseline"
        )
        assert actual == case[oracle]


def test_source_to_paper_baseline_measurement(tmp_path):
    source, _ = account(tmp_path / "capture")
    elapsed = []
    cpu_start, wall_start = time.process_time(), time.perf_counter()
    for i in range(100):
        start = time.perf_counter()
        source.observe(shifted(i, str(20 + i % 2)), (T + timedelta(seconds=i)).isoformat())
        elapsed.append((time.perf_counter() - start) * 1000)
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start

    observed = PaperJournal(tmp_path / "public")
    add_quote(observed, 10)
    paper = ObservedP1Paper(
        source_db=observed.path,
        state_root=tmp_path / "private",
        run_id="baseline",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(tmp_path / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(observed, 1, 12, {BTC.key: "20"})
    pending = paper.step(at(14))["execution_intents"]["S035"]
    assert pending["first_known_at"] == at(13)
    assert pending["due_at"] == at(313)
    add_quote(observed, 313)
    result = paper.step(at(314))
    assert result["quantity_count"] == 1
    event = next(
        row["event"]
        for row in paper.run.ledger.read()
        if row["event"]["kind"] == "PM04_PAPER_EXECUTE"
    )
    print(
        "\nPYDANTIC_BASELINE="
        + json.dumps(
            {
                "schema": "pydantic_offline_baseline_v1",
                "synthetic_fixture": True,
                "source_samples": len(elapsed),
                "source_journal_ms_p50": statistics.median(elapsed),
                "source_journal_ms_p95": sorted(elapsed)[94],
                "source_journal_frames_per_second": len(elapsed) / wall,
                "source_cpu_seconds": cpu,
                "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "source_connections_opened": 0,
                "first_known_t0": pending["first_known_at"],
                "due_at": pending["due_at"],
                "actual_attempt_at": event["decision_at"],
                "intent_id": pending["intent_id"],
                "attempt_event_id": event["event_id"],
                "simulated_scheduler_jitter_seconds": 1,
                "real_scheduler_jitter": "UNMEASURED_NO_DEPLOYMENT",
                "order_route": result["order_route"],
            },
            sort_keys=True,
        )
    )
