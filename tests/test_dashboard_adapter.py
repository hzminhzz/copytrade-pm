"""Dashboard Phase 1 evidence/negative tests: no broker, protected journal or live writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from copytrade_pm.dashboard.adapter import (
    DashboardReader,
    SmallTTLCache,
    PROJECTION_SCHEMA,
    parse_utc,
)

T0 = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)


def capture(
    command: str,
    *,
    time: datetime = T0,
    data: dict | None = None,
    sequence: int = 12,
    release: str = "a" * 64,
) -> dict:
    source = {
        "schema": f"operator_{command}_v1",
        "journal_sequence": sequence,
        "account_binding_sha": "d" * 64,
        "release_sha": release,
        "trading_authorized": False,
    }
    if data is None:
        data = {
            "status": {
                "state": "HALTED",
                "mode": "SHADOW",
                "order_route": "NONE",
                "account_readiness": "UNCERTAIN",
                "halts": ["BROKER_STALE"],
                "health": {
                    "status": "BLOCKED",
                    "reasons": ["WATCHDOG_UNAVAILABLE"],
                    "ages_ms": {"watchdog": None},
                },
            },
            "risk": {"finance": {"equity": "0", "headroom": "100.22", "daily_headroom": None}},
            "broker": {
                "certainty": "UNKNOWN",
                "broker_epoch": 3,
                "last_snapshot_ms": None,
                "flat_confirmed": False,
            },
            "portfolio": {"decisions": []},
            "intent": {"intents": []},
        }[command]
    return {
        "schema": PROJECTION_SCHEMA,
        "command": command,
        "source_observed_at": time.isoformat(),
        "captured_at": time.isoformat(),
        "native": {**source, **data},
    }


def fake_native(args: list[str]) -> dict:
    if args[:2] == ["research", "show"]:
        return {
            "schema": "copytrade_read_result_v1",
            "observed_at": T0.isoformat(),
            "trading_authorized": False,
            "scientifically_qualified": False,
            "status": "BLOCKED",
            "source": {
                "authority": "immutable_offline_job_cache",
                "observed_at": T0.isoformat(),
                "sha256": "e" * 64,
                "version": "cache_v1",
            },
            "data": {"research_only": True},
            "limitations": ["SELECTION_PROOF_UNAVAILABLE"],
        }
    raise AssertionError(f"Unexpected native call: {args}")


def reader(*, provider=None, time=T0) -> DashboardReader:
    return DashboardReader(
        db=Path("/nonexistent/roster.sqlite"),
        clock=lambda: time,
        guardian_provider=provider or (lambda command: capture(command)),
        native_read=fake_native,
        cache=SmallTTLCache(),
    )


def test_equity_zero_is_not_unknown_and_provenance_survives():
    report = reader().overview()
    assert report["metrics"]["equity"] == {"value": "0", "status": "VERIFIED"}
    assert report["metrics"]["daily_headroom"] == {"value": None, "status": "UNKNOWN"}
    assert report["metrics"]["headroom"]["value"] == "100.22"
    assert report["sources"]["risk"]["authority"] == "prop-production.operator"
    assert report["sources"]["risk"]["journal_sequence"] == 12
    assert report["sources"]["risk"]["account_binding_sha"] == "d" * 64
    assert report["sources"]["risk"]["revision"] == "a" * 64
    assert report["sources"]["risk"]["source_observed_at"] == T0.isoformat()
    assert report["sources"]["risk"]["source_schema"] == "operator_risk_v1"
    # No committed roster database is configured, so selection stays explicitly UNKNOWN.
    assert report["research_selection"]["status"] == "UNKNOWN"
    assert report["research_selection"]["error_code"] == "ROSTER_UNAVAILABLE"
    assert report["trading_authorized"] is False
    assert report["membership_authority"].startswith("UNKNOWN")
    assert "BROKER_STALE" in report["incidents"]


@pytest.mark.parametrize(
    ("change", "wanted"),
    [
        (lambda r: r.update(source_observed_at=(T0 - timedelta(seconds=16)).isoformat()), "STALE"),
        (
            lambda r: r.update(
                source_observed_at=(T0 - timedelta(seconds=62)).isoformat(),
                captured_at=(T0 - timedelta(seconds=61)).isoformat(),
            ),
            "STALE",
        ),
        (lambda r: r.update(captured_at=(T0 - timedelta(seconds=61)).isoformat()), "BLOCKED"),
        (lambda r: r.update(captured_at=(T0 + timedelta(seconds=1)).isoformat()), "BLOCKED"),
        (lambda r: r.update(captured_at="not a UTC clock"), "BLOCKED"),
        (lambda r: r.update(command="broker"), "BLOCKED"),
        (lambda r: r["native"].update(trading_authorized=True), "BLOCKED"),
        (lambda r: r["native"].update(journal_sequence=-1), "BLOCKED"),
        (lambda r: r["native"].update(schema="other"), "BLOCKED"),
        (lambda r: r["native"].update(release_sha="bad"), "BLOCKED"),
    ],
)
def test_guardian_fail_closed(change, wanted):
    def provider(command):
        result = capture(command)
        change(result)
        return result

    assert reader(provider=provider).guardian("risk")["status"] == wanted


def test_release_and_sequence_mismatch_never_display_finance():
    def provider(command):
        return capture(command, sequence=13 if command == "broker" else 12)

    report = reader(provider=provider).overview()
    assert report["sources"]["risk"]["status"] == "BLOCKED"
    assert report["metrics"]["equity"] == {"value": None, "status": "BLOCKED"}


def test_account_binding_mismatch_never_displays_finance():
    def provider(command):
        result = capture(command)
        if command == "broker":
            result["native"]["account_binding_sha"] = "f" * 64
        return result

    report = reader(provider=provider).overview()
    assert report["sources"]["risk"]["status"] == "BLOCKED"
    assert (
        report["sources"]["risk"]["error_code"] == "GUARDIAN_ACCOUNT_SEQUENCE_OR_RELEASE_MISMATCH"
    )
    assert report["metrics"]["equity"] == {"value": None, "status": "BLOCKED"}


def test_missing_release_rejected_even_when_all_captures_agree():
    def provider(command):
        result = capture(command)
        result["native"].pop("release_sha")
        return result

    report = reader(provider=provider).overview()
    assert report["sources"]["risk"]["status"] == "BLOCKED"
    assert report["sources"]["status"]["status"] == "VERIFIED"
    assert report["metrics"]["equity"]["value"] is None


def test_partial_guardian_captures_never_authorize_financial_metric():
    def provider(command):
        if command == "broker":
            raise FileNotFoundError()
        return capture(command)

    report = reader(provider=provider).overview()
    assert report["sources"]["risk"]["status"] == "BLOCKED"
    assert report["metrics"]["equity"]["value"] is None
    assert report["metrics"]["headroom"]["status"] == "BLOCKED"


def test_missing_capture_is_unavailable_only_for_guardian():
    out = reader(provider=lambda _: (_ for _ in ()).throw(PermissionError())).overview()
    assert out["metrics"]["equity"]["status"] == "UNAVAILABLE"
    assert out["research_selection"]["status"] == "UNKNOWN"
    assert out["sources"]["broker"]["status"] == "UNAVAILABLE"


def test_no_account_id_or_addresses_in_projection():
    r = capture(
        "status",
        data={
            "state": "0x" + "a" * 40,
            "mode": "SHADOW",
            "account_id": "private-account",
            "halts": ["PRIVATE_ACCOUNT_" + "0x" + "b" * 40],
            "health": {"reasons": []},
        },
    )
    out = reader(provider=lambda _: r).guardian("status")
    serial = json.dumps(out)
    assert "private-account" not in serial
    assert "0x" + "a" * 40 not in serial
    assert "0x" + "b" * 40 not in serial
    assert "PRIVATE_WALLET" in serial


def test_no_network_mutation_or_privileged_calls(monkeypatch):
    from copytrade_pm.dashboard import adapter

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("FOREIGN_MUTATION_ATTEMPTED")

    monkeypatch.setattr(adapter.subprocess, "run", forbidden)
    monkeypatch.setattr("copytrade_pm.roster.RosterStore", forbidden)
    a = reader()
    a.guardian("risk")
    a.overview()
    assert not calls
    with pytest.raises(ValueError, match="UNAPPROVED_GUARDIAN_CAPABILITY"):
        a.guardian("halt")


def test_wallet_invalid_input_has_no_backend_calls():
    calls = []
    a = DashboardReader(native_read=lambda cmd: calls.append(cmd), clock=lambda: T0)
    for kwargs in [
        {"query": "x" * 97},
        {"cohort": "bad\nnewline"},
        {"offset": -1},
        {"limit": 999},
        {"limit": True},
        {"offset": 10001},
        {"asof": "2026-11-07T12:00:00+07:00"},
        {"subscribed": "no"},
    ]:
        assert a.wallets(**kwargs)["status"] == "BLOCKED"
    assert calls == []


def test_wallet_inventory_is_roster_derived_and_redacted(tmp_path):
    from copytrade_pm.roster import RosterStore
    from roster_fixture import WALLETS, add_account

    db = tmp_path / "roster.sqlite"
    with RosterStore(db, create=True) as store:
        add_account(
            store,
            "A",
            {"W001": WALLETS[0], "W002": WALLETS[1], "W003": WALLETS[2]},
        )
    before = db.read_bytes()
    reader = DashboardReader(
        db=db, clock=lambda: datetime(2026, 11, 5, tzinfo=UTC), cache=SmallTTLCache()
    )
    found = reader.wallets(query="W002", limit=1)
    assert found["status"] == "VERIFIED"
    assert found["authority"] == "roster_sqlite"
    assert found["data"]["schema"] == "roster_wallet_inventory_v1"
    assert found["data"]["addresses_redacted"] is True
    assert found["data"]["total"] == 1
    row = found["data"]["wallets"][0]
    assert row["alias"] == "W002"
    assert row["cohort"] == "A"
    assert row["wallet"].startswith("wallet:")
    assert row["occupancy"] == "OCCUPIED"
    assert WALLETS[1] not in json.dumps(found)
    assert "0x" not in json.dumps(found["data"])
    assert len(found["inventory_sha256"]) == 64
    # A VERIFIED capability row requires a real source clock (Grafana read model).
    assert found["source_observed_at"] is not None
    from copytrade_pm.dashboard.grafana_capabilities import build_capabilities

    capabilities = build_capabilities(reader)
    assert capabilities["wallets"]["status"] == "VERIFIED"
    assert capabilities["wallets"]["authority"] == "roster_seat_book"
    assert len(capabilities["wallets"]["rows"]) == 3
    # A later known-at clock still resolves the committed book unchanged.
    assert reader.wallets(query="W002")["data"]["total"] == 1
    assert db.read_bytes() == before


def test_wallet_inventory_rejects_unverifiable_roster(tmp_path):
    from contextlib import closing
    import sqlite3

    from copytrade_pm.roster import RosterStore
    from roster_fixture import WALLETS, add_account

    db = tmp_path / "roster.sqlite"
    with RosterStore(db, create=True) as store:
        add_account(store, "A", {"W001": WALLETS[0]})
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
    result = DashboardReader(
        db=db, clock=lambda: datetime(2026, 11, 5, tzinfo=UTC), cache=SmallTTLCache()
    ).wallets()
    assert result["status"] == "STALE"
    assert result["error_code"] == "ROSTER_INTEGRITY_UNVERIFIED"
    assert result["data"] is None


def test_wallet_inventory_absent_roster_is_unknown(tmp_path):
    result = DashboardReader(
        db=tmp_path / "missing.sqlite",
        clock=lambda: datetime(2026, 11, 5, tzinfo=UTC),
        cache=SmallTTLCache(),
    ).wallets()
    assert result["status"] == "UNKNOWN"
    assert result["error_code"] == "ROSTER_UNAVAILABLE"


def test_native_reader_rejects_fake_authority_and_malformed_observation(tmp_path):
    payload = fake_native(["research", "show", "case1"])
    for modified in [
        {"schema": "unsupported"},
        {"trading_authorized": True},
        {"scientifically_qualified": True},
        {"observed_at": "not-utc"},
        {"observed_at": (T0 + timedelta(seconds=1)).isoformat()},
    ]:
        source = {**payload, **modified}
        a = DashboardReader(
            research_root=tmp_path,
            native_read=lambda _: source,
            clock=lambda: T0,
            cache=SmallTTLCache(),
        )
        answer = a.research_reports(run_id="case1")
        assert answer["status"] == "UNKNOWN"
        assert answer["data"] is None
        assert answer["error_code"] == "NATIVE_READ_UNAVAILABLE"


def test_native_query_observed_during_read_is_not_falsely_future(tmp_path):
    payload = fake_native(["research", "show", "case1"])
    payload["observed_at"] = (T0 + timedelta(milliseconds=100)).isoformat()
    observations = iter([T0, T0 + timedelta(seconds=1), T0 + timedelta(seconds=1)])
    a = DashboardReader(
        research_root=tmp_path,
        native_read=lambda _: payload,
        clock=lambda: next(observations),
        cache=SmallTTLCache(),
    )
    result = a.research_reports(run_id="case1")
    assert result["status"] == "BLOCKED"
    assert result["error_code"] is None
    assert result["retrieved_at"] == (T0 + timedelta(seconds=1)).isoformat()


def test_monotonic_shared_refresh_cache():
    cache = SmallTTLCache()
    calls = []

    def slow():
        calls.append(1)
        return {"state": "UNKNOWN"}

    assert cache.get("x", 60, slow) == {"state": "UNKNOWN"}
    assert cache.get("x", 60, slow) == {"state": "UNKNOWN"}
    assert len(calls) == 1


def test_no_synthetic_health_and_services_from_pids(monkeypatch):
    from copytrade_pm.dashboard import adapter

    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout="LoadState=loaded\nActiveState=active\nMainPID=234\n"
        ),
    )
    a = reader(provider=lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    report = a.health()
    assert report["guardian"]["status"] == "UNAVAILABLE"
    assert report["watchdog"]["status"] == "UNKNOWN"
    assert report["market"]["status"] == "UNKNOWN"
    assert all(s["state"] == "UNKNOWN" for s in report["services"].values())
    assert all(s["os_active_state"] == "active" for s in report["services"].values())
    assert all(s["attests_financial_health"] is False for s in report["services"].values())


def test_roster_pagination_asof_and_zero_write(tmp_path):
    from copytrade_pm.roster import RosterStore
    from roster_fixture import AT, MS, WALLETS, add_account

    db = tmp_path / "roster.sqlite"
    with RosterStore(db, create=True) as store:
        add_account(
            store,
            "A",
            {"W001": WALLETS[0], "W002": WALLETS[1], "W003": WALLETS[2]},
        )
        store.record_veto(WALLETS[2], reason="reviewed exclusion", actor="operator", at_ms=MS)
    before_bytes = db.read_bytes()
    # The roster is read at a known-at clock, so the fixture instant is the floor.
    app = DashboardReader(
        db=db, clock=lambda: datetime(2026, 11, 5, tzinfo=UTC), cache=SmallTTLCache()
    )
    found = app.wallets(query="W00", asof=AT, limit=2)
    assert found["status"] == "VERIFIED"
    assert found["data"]["total"] == 3
    assert len(found["data"]["wallets"]) == 2
    assert "0x" not in json.dumps(found["data"])
    page = app.wallets(query="W00", asof=AT, limit=2, offset=2)
    assert [row["alias"] for row in page["data"]["wallets"]] == ["W003"]
    excluded = app.wallets(excluded=True, limit=10)
    assert excluded["data"]["total"] == 1
    assert all(row["excluded"] for row in excluded["data"]["wallets"])
    # A known-at clock before the first committed book cannot invent members.
    early = app.wallets(asof="2026-11-03T00:00:00+00:00")
    assert early["status"] == "VERIFIED"
    assert early["data"]["total"] == 0
    assert early["data"]["unknown_accounts"] == ["A"]
    assert db.read_bytes() == before_bytes
    assert len(found["inventory_sha256"]) == 64


def test_guardian_capture_rejects_untrusted_owner_and_symlinks(tmp_path):
    from copytrade_pm.dashboard.adapter import GuardianCaptureDirectory

    directory = tmp_path / "capture"
    directory.mkdir()
    path = directory / "risk.json"
    path.write_text(json.dumps(capture("risk")))
    assert directory.stat().st_uid == path.stat().st_uid
    with pytest.raises(PermissionError):
        GuardianCaptureDirectory(directory)("risk")
    with pytest.raises(ValueError):
        GuardianCaptureDirectory(directory)("halt")
    with pytest.raises(FileNotFoundError):
        GuardianCaptureDirectory(None)("risk")


def test_health_stale_captures_and_real_negative_incidents():
    stale_time = T0 - timedelta(seconds=35)
    report = reader(
        provider=lambda cmd: capture(cmd, time=stale_time),
    ).health()
    assert report["guardian"]["status"] == "STALE"
    assert report["watchdog"]["status"] == "UNKNOWN"
    assert report["market"]["status"] == "UNKNOWN"
    assert "BROKER_STALE" in report["incidents"]


def test_decimal_and_clock_boundaries():
    from copytrade_pm.dashboard.adapter import safe_decimal

    assert safe_decimal("0.00") == "0.00"
    assert safe_decimal("NaN") is None
    assert safe_decimal(float("inf")) is None
    assert parse_utc("2026-11-07T07:00:00+07:00") is None
    assert parse_utc("2026-11-07T00:00:00Z") is not None


def test_wallet_inventory_and_selection_never_grant_authority(tmp_path):
    """Seam 3 (dashboard wallet parity): roster identity never promotes authority."""
    from copytrade_pm.roster import RosterStore
    from roster_fixture import WALLETS, add_account

    db = tmp_path / "roster.sqlite"
    with RosterStore(db, create=True) as store:
        add_account(store, "A", {"W001": WALLETS[0]})
    app = DashboardReader(
        db=db, clock=lambda: datetime(2026, 11, 5, tzinfo=UTC), cache=SmallTTLCache()
    )
    found = app.wallets(query="W001")
    assert found["status"] == "VERIFIED"
    assert found["trading_authorized"] is False
    assert found["scientifically_qualified"] is False
    selection = app.research_selection()
    assert selection["status"] == "VERIFIED"
    assert selection["data"]["selection_state"] == "SEALED_RESEARCH_ONLY"
    assert selection["data"]["accounts"] == ["A"]
    assert selection["trading_authorized"] is False
    # An unattested selection is visible but never trading authorization.
    assert all(p["source_sealed"] is True for p in selection["data"]["portfolios"])

    missing = DashboardReader(
        db=tmp_path / "absent.sqlite",
        clock=lambda: datetime(2026, 11, 5, tzinfo=UTC),
        cache=SmallTTLCache(),
    )
    assert missing.wallets()["status"] == "UNKNOWN"
    assert missing.research_selection()["error_code"] == "ROSTER_UNAVAILABLE"
    # An account with no committed book at the requested clock is not invented.
    absent = app.research_selection(account="NO_SUCH_ACCOUNT")
    assert absent["status"] == "NOT_REGISTERED_AT_ASOF"
    assert absent["error_code"] == "SELECTION_UNKNOWN_AT_ASOF"
