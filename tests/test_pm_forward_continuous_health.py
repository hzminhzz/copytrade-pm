from datetime import UTC, datetime, timedelta
import json
import os
import sqlite3
from contextlib import closing

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observer_health import (
    publish_continuous_heartbeat,
    inspect_continuous_observer,
)
from copytrade_pm.pm_forward_stream_journal import StreamProgress

T = datetime(2026, 11, 5, 1, tzinfo=UTC)


def test_shadow_witness_log_detects_tampering_and_never_compresses_time(tmp_path):
    import pytest
    from copytrade_pm.pm_forward_observer_health import (
        _append_watchdog_sample,
        audit_continuous_shadow,
        verify_watchdog_samples,
    )

    journal = build(tmp_path)
    report = inspect_continuous_observer(journal.root, as_of=T.isoformat())
    first = _append_watchdog_sample(
        journal.root, report, observed_at=T.isoformat(), sequence=1, prior_sha="0" * 64
    )
    _append_watchdog_sample(
        journal.root,
        report,
        observed_at=(T + timedelta(seconds=15)).isoformat(),
        sequence=2,
        prior_sha=first,
    )
    audit = audit_continuous_shadow(journal.root, as_of=(T + timedelta(seconds=20)).isoformat())
    assert audit["actual_witness_window_seconds"] == 15
    assert audit["status"] == "BLOCKED_BY_GATE"
    assert "ACTUAL_72_HOUR_WATCHDOG_WINDOW_NOT_COMPLETE" in audit["gate_reasons"]
    assert audit["financial_rows"] == {"runs": 0, "events": 0}
    path = journal.root / "continuous-watchdog.samples.jsonl"
    path.write_text(path.read_text().replace('"sequence":2', '"sequence":3'))
    with pytest.raises(ValueError, match="DIVERGENCE"):
        verify_watchdog_samples(journal.root)


def test_missing_ack_and_resource_exhaustion_are_explicit(tmp_path):
    journal = build(tmp_path)
    source = StreamProgress(journal, "account:quiet")
    source.commit(
        source.propose(
            epoch="b" * 32,
            kind="TRANSPORT",
            known_at=T.isoformat(),
            checkpoint={**source.checkpoint, "subscription_acknowledged": False},
        )
    )
    path = journal.root / "continuous-observer.heartbeat.json"
    old = json.loads(path.read_text())
    publish_continuous_heartbeat(
        journal.root,
        revision="a" * 40,
        manifest_sha=old["manifest_sha"],
        started_at=T.isoformat(),
        now=T.isoformat(),
        metrics={**old["metrics"], "disk_free_bytes": 0, "queue_depth": 10},
    )
    report = inspect_continuous_observer(journal.root, as_of=T.isoformat())
    assert "LOW_DISK" in report["reason_codes"]
    assert "WRITER_QUEUE_SATURATED" in report["reason_codes"]
    assert "NATIVE_SUBSCRIPTION_ACK_NOT_OBSERVED" in report["feeds"]["account:quiet"]["reasons"]


def test_continuous_unit_templates_are_distinct_and_cannot_authorize(tmp_path):
    from copytrade_pm.pm_forward_public_unit import continuous_unit_templates, UNIT

    report = continuous_unit_templates(
        release=tmp_path / ("a" * 40),
        revision="a" * 40,
        registry=tmp_path / "registry.sqlite",
        primary=tmp_path / "primary",
        secondary=tmp_path / "secondary",
        state=tmp_path / "candidate",
        config=tmp_path / "config.json",
    )
    assert UNIT not in report["units"]
    assert report["systemd_activated"] is False
    collector = report["units"]["copytrade-continuous-shadow.service"]
    watchdog = report["units"]["copytrade-continuous-shadow-watchdog.service"]
    assert "--preflight-only" in collector and "--continuous-config" in collector
    assert "--continuous --watch" in watchdog and "ExecStartPre=" not in watchdog
    assert "ProtectSystem=strict" in collector
    assert "--epochs" not in collector


def build(tmp_path):
    journal = PaperJournal(tmp_path / "new")
    manifest = {
        "schema": "paper_continuous_preflight_v1",
        "revision": "a" * 40,
        "order_route": "NONE",
        "source_nav_attested": False,
    }
    manifest["manifest_sha"] = digest(manifest)
    control = StreamProgress(journal, "observer:control")
    scope = {
        "expected_accounts": ["quiet"],
        "required_markets": ["hyperliquid/mainnet:perp:default/BTC"],
        "missing_accounts": [],
        "budget_failure": None,
    }
    control.commit(
        control.propose(
            epoch="a" * 32,
            kind="START",
            known_at=T.isoformat(),
            checkpoint={
                "manifest": manifest,
                "scope": scope,
                "census_status": "CURRENT_PUBLIC_CENSUS",
            },
        )
    )
    for prefix, tail in [
        ("account:", "quiet"),
        ("ccxt_l2:", scope["required_markets"][0]),
        ("ccxt_trades:", scope["required_markets"][0]),
        ("public:", scope["required_markets"][0]),
    ]:
        progress = StreamProgress(journal, prefix + tail)
        progress.commit(
            progress.propose(
                epoch="b" * 32,
                kind="BASELINE",
                known_at=T.isoformat(),
                checkpoint={
                    "baseline_valid": True,
                    "transport": "CONNECTED",
                    "subscription_acknowledged": True,
                    "last_transport_at": T.isoformat(),
                    "last_quote_at": T.isoformat(),
                },
            )
        )
    publish_continuous_heartbeat(
        journal.root,
        revision="a" * 40,
        manifest_sha=manifest["manifest_sha"],
        started_at=T.isoformat(),
        now=T.isoformat(),
        metrics={
            "queue_depth": 0,
            "queue_capacity": 10,
            "disk_free_bytes": 1e9,
            "min_free_bytes": 1e8,
            "journal_bytes": 1000,
            "max_journal_bytes": 1e8,
        },
    )
    return journal


def test_independent_feed_health_keeps_financial_gate_and_quiet_account(tmp_path):
    journal = build(tmp_path)
    report = inspect_continuous_observer(journal.root, as_of=(T + timedelta(seconds=5)).isoformat())
    assert report["feed_health"] == "CURRENT_FEEDS_OBSERVED"
    assert report["financial_admission"] == "BLOCKED_NO_TRADE"
    assert report["feeds"]["account:quiet"]["trade_inactivity_is_failure"] is False
    assert not report["paper_observed"]


def test_stale_quote_detected_despite_fresh_transport_and_process(tmp_path):
    journal = build(tmp_path)
    later = T + timedelta(seconds=70)
    for sid in [
        "account:quiet",
        "ccxt_l2:hyperliquid/mainnet:perp:default/BTC",
        "ccxt_trades:hyperliquid/mainnet:perp:default/BTC",
        "public:hyperliquid/mainnet:perp:default/BTC",
    ]:
        progress = StreamProgress(journal, sid)
        progress.commit(
            progress.propose(
                epoch="b" * 32,
                kind="TRANSPORT",
                known_at=later.isoformat(),
                checkpoint={**progress.checkpoint, "last_transport_at": later.isoformat()},
            )
        )
    path = journal.root / "continuous-observer.heartbeat.json"
    current = json.loads(path.read_text())
    publish_continuous_heartbeat(
        journal.root,
        revision="a" * 40,
        manifest_sha=current["manifest_sha"],
        started_at=T.isoformat(),
        now=later.isoformat(),
        metrics=current["metrics"],
    )
    report = inspect_continuous_observer(journal.root, as_of=later.isoformat())
    assert report["feed_health"] == "DEGRADED"
    assert report["feeds"]["account:quiet"]["status"] == "CONNECTED_QUIET_OR_ACTIVE"
    assert (
        "QUOTE_STALE_OR_MISSING"
        in report["feeds"]["ccxt_l2:hyperliquid/mainnet:perp:default/BTC"]["reasons"]
    )


def test_tampered_or_future_heartbeat_and_receipt_fail_closed(tmp_path):
    journal = build(tmp_path)
    path = journal.root / "continuous-observer.heartbeat.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    payload["revision"] = "f" * 40
    path.write_text(json.dumps(payload))
    assert (
        inspect_continuous_observer(journal.root, as_of=T.isoformat())["feed_health"] == "UNKNOWN"
    )
    path.write_bytes(raw)
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute("UPDATE observer_stream_heads SET chain_sha=?", ("0" * 64,))
        db.commit()
    assert (
        inspect_continuous_observer(journal.root, as_of=T.isoformat())["feed_health"] == "UNKNOWN"
    )
    assert os.stat(journal.path).st_mode & 0o077 == 0
