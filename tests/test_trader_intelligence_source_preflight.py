"""Read-only source preflight keeps real identities private and science blocked."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from copytrade_pm.trader_intelligence_source_preflight import inspect_live_source, main

AT = datetime(2026, 11, 4, 7, tzinfo=UTC)
ADDRESS = "0x" + "1a" * 20


def source(tmp_path: Path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    (root / f"S035-ENA_{ADDRESS}.json").write_text("{}")
    return root


def journal(tmp_path: Path, *, known_age_minutes=1):
    path = tmp_path / "observations.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE opportunity_state(ledger_id TEXT,last_seq INTEGER)")
        db.execute("INSERT INTO opportunity_state VALUES ('a',1)")
        db.execute(
            "CREATE TABLE opportunity_decisions("
            "opportunity_id TEXT,first_source_id TEXT,first_ledger_seq INTEGER,"
            "first_event_at TEXT,first_known_at TEXT,instrument_id TEXT,"
            "wallet_id TEXT,status TEXT,blocker TEXT,payload_json TEXT)"
        )
        db.execute("CREATE TABLE source_coverage_barriers(ledger_seq INTEGER,known_at TEXT)")
        payload = {
            "first_source_id": "s1",
            "source_quantity_before": "0",
            "source_quantity_after": "2",
        }
        db.execute(
            "INSERT INTO opportunity_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "o1",
                "s1",
                1,
                (AT - timedelta(minutes=known_age_minutes + 1)).isoformat(),
                (AT - timedelta(minutes=known_age_minutes)).isoformat(),
                "hyperliquid:mainnet:perp:default:BTC",
                ADDRESS,
                "ACTIVE",
                None,
                json.dumps(payload),
            ),
        )
    return path


def inspect(
    tmp_path, *, registered_at=None, market_root=None, market_limit=25, known_age_minutes=1
):
    return inspect_live_source(
        journal_db=journal(tmp_path, known_age_minutes=known_age_minutes),
        source_root=source(tmp_path),
        aliases=("S035-ENA",),
        asof=AT.isoformat(),
        registered_at=registered_at,
        market_root=market_root,
        market_limit=market_limit,
    )


def test_unregistered_roster_never_eligible_and_contains_no_private_address(tmp_path):
    report = inspect(tmp_path)
    assert report.matched_source_events == 1
    assert report.potentially_directional_events == 1
    assert report.observed_after_registration == 0
    assert report.complete_source_book_events == 0
    assert report.verifiable_equity_events == 0
    assert report.roster_registration == "UNREGISTERED_DYNAMIC_INSPECTION"
    assert "NO_PIT_ROSTER_REGISTRATION_CLOCK" in report.reasons
    assert ADDRESS not in json.dumps(report.as_wire())
    assert report == inspect_live_source(
        journal_db=tmp_path / "observations.db",
        source_root=tmp_path / "private",
        aliases=("S035-ENA",),
        asof=AT.isoformat(),
    )


def test_operator_declared_clock_is_not_independent_proof(tmp_path):
    report = inspect(tmp_path, registered_at=(AT - timedelta(minutes=20)).isoformat())
    assert report.observed_after_registration == 1
    assert report.roster_registration == "OPERATOR_DECLARED_UNATTESTED"
    assert report.market_attempts == 1
    assert report.market_exact_mark_successes == 0
    assert report.market_blockers == {"NATIVE_MINUTE_SOURCE_NOT_CONFIGURED": 1}
    assert report.status == "NOT_SCIENTIFICALLY_QUALIFIED"
    assert "INDEPENDENT_REGISTRATION_ATTESTATION_UNAVAILABLE" in report.reasons


def test_future_clock_and_private_alias_errors_fail_closed(tmp_path):
    path = journal(tmp_path)
    src = source(tmp_path)
    with pytest.raises(ValueError, match="FUTURE_ROSTER_REGISTRATION_NOT_ELIGIBLE"):
        inspect_live_source(
            journal_db=path,
            source_root=src,
            aliases=("S035-ENA",),
            asof=AT.isoformat(),
            registered_at=(AT + timedelta(minutes=1)).isoformat(),
        )
    with pytest.raises(ValueError, match="AMBIGUOUS_OR_MISSING_PRIVATE_WALLET_ALIAS"):
        inspect_live_source(
            journal_db=path, source_root=src, aliases=("S051-BTC",), asof=AT.isoformat()
        )


def test_future_exit_horizon_is_not_peeked_at_even_in_diagnostic(monkeypatch, tmp_path):
    class NeverReadFuture:
        def __init__(self, root):
            self.source_days = {}

        def get(self, instrument, dt):
            raise AssertionError("FUTURE_MARKET_READ")

    monkeypatch.setattr(
        "copytrade_pm.trader_intelligence_source_preflight.VerifiedHyperliquidMinuteSource",
        NeverReadFuture,
    )
    report = inspect(
        tmp_path,
        registered_at=(AT - timedelta(minutes=20)).isoformat(),
        market_root=tmp_path,
    )
    assert report.market_attempts == 1
    assert report.market_blockers == {"FOLLOWER_HORIZON_NOT_YET_MATURE": 1}
    assert report.market_exact_mark_successes == 0


def test_private_immutable_report_refuses_second_write(tmp_path, monkeypatch, capsys):
    output = tmp_path / "reports" / "source-preflight.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ti-source-preflight",
            "--journal",
            str(journal(tmp_path)),
            "--private-source-files",
            str(source(tmp_path)),
            "--aliases",
            "S035-ENA",
            "--asof",
            AT.isoformat(),
            "--output",
            str(output),
        ],
    )
    main()
    written = json.loads(capsys.readouterr().out)
    assert written["economic_evidence_attested"] is False
    assert output.is_file()
    assert output.stat().st_mode & 0o077 == 0
    assert ADDRESS not in output.read_text()
    with pytest.raises(ValueError, match="GENERATION_REUSE_NOT_AUTHORIZED"):
        main()


def test_market_coverage_uses_verified_native_adapter_and_is_only_source_proof(
    tmp_path, monkeypatch
):
    class FakeNative:
        def __init__(self, root):
            assert root == tmp_path
            self.source_days = {"hyperliquid:mainnet:perp:default:BTC@2026-11-04": "a" * 64}
            self.calls = []

        def get(self, instrument, dt):
            assert instrument == "hyperliquid:mainnet:perp:default:BTC"
            assert dt.tzinfo is not None
            return type("Bar", (), {"timestamp": dt.replace(second=0, microsecond=0)})()

    monkeypatch.setattr(
        "copytrade_pm.trader_intelligence_source_preflight.VerifiedHyperliquidMinuteSource",
        FakeNative,
    )
    report = inspect(
        tmp_path,
        registered_at=(AT - timedelta(hours=3)).isoformat(),
        market_root=tmp_path,
        known_age_minutes=120,
    )
    assert report.market_attempts == 1
    assert report.market_exact_mark_successes == 1
    assert report.market_blockers == {}
    assert report.complete_source_book_events == 0
    assert "SIGNED_MATURE_WHOLE_ACCOUNT_OUTCOMES_NOT_AVAILABLE" in report.reasons
