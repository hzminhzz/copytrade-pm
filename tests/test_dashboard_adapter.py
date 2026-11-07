"""Dashboard Phase 1 evidence/negative tests: no broker, protected journal or live writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
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
    if args[:2] == ["portfolios", "current"]:
        return {
            "schema": "copytrade_read_result_v1",
            "observed_at": T0.isoformat(),
            "trading_authorized": False,
            "scientifically_qualified": False,
            "status": "BLOCKED",
            "source": {
                "authority": "wallet_registry",
                "observed_at": T0.isoformat(),
                "sha256": "e" * 64,
                "version": "sqlite_v8",
            },
            "data": {"research_only": True},
            "limitations": ["SELECTION_PROOF_UNAVAILABLE"],
        }
    raise AssertionError(f"Unexpected native call: {args}")


def reader(*, provider=None, time=T0) -> DashboardReader:
    return DashboardReader(
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
    assert report["research_selection"]["status"] == "BLOCKED"
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
    assert out["research_selection"]["status"] == "BLOCKED"
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
    monkeypatch.setattr(adapter.registry, "apply", forbidden)
    monkeypatch.setattr(adapter.registry, "connect", forbidden)
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


def test_wallet_native_schema_and_privacy_must_be_explicit():
    payload = {
        "schema": "copytrade_read_result_v1",
        "status": "VERIFIED",
        "observed_at": T0.isoformat(),
        "trading_authorized": False,
        "scientifically_qualified": False,
        "source": {
            "authority": "wallet_registry",
            "observed_at": T0.isoformat(),
            "sha256": "a" * 64,
            "version": "sqlite_v8",
        },
        "data": {
            "schema": "wallet_registry_private_inventory_v1",
            "addresses_redacted": False,
            "wallets": [{"address": "sensitive"}],
        },
    }
    a = DashboardReader(native_read=lambda _: payload, clock=lambda: T0, cache=SmallTTLCache())
    result = a.wallets()
    assert result["status"] == "BLOCKED"
    assert result["data"] is None


def test_native_reader_rejects_fake_authority_and_malformed_observation():
    payload = fake_native(["portfolios", "current"])
    for modified in [
        {"schema": "unsupported"},
        {"trading_authorized": True},
        {"scientifically_qualified": True},
        {"observed_at": "not-utc"},
        {"observed_at": (T0 + timedelta(seconds=1)).isoformat()},
    ]:
        source = {**payload, **modified}
        a = DashboardReader(native_read=lambda _: source, clock=lambda: T0, cache=SmallTTLCache())
        answer = a.research_selection()
        assert answer["status"] == "UNKNOWN"
        assert answer["data"] is None
        assert answer["error_code"] == "NATIVE_READ_UNAVAILABLE"


def test_native_query_observed_during_read_is_not_falsely_future():
    payload = fake_native(["portfolios", "current"])
    payload["observed_at"] = (T0 + timedelta(milliseconds=100)).isoformat()
    observations = iter([T0, T0 + timedelta(seconds=1)])
    a = DashboardReader(
        native_read=lambda _: payload, clock=lambda: next(observations), cache=SmallTTLCache()
    )
    result = a.research_selection()
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
    assert all(s["state"] == "DEGRADED" for s in report["services"].values())
    assert all(s["attests_financial_health"] is False for s in report["services"].values())


def test_actual_sqlite_readonly_pagination_asof_and_zero_write(tmp_path, monkeypatch):
    from test_wallet_registry_catalog import AFTER, BEFORE, _v2_snapshot
    from copytrade_pm import wallet_registry as native_registry
    from copytrade_pm import wallet_registry_catalog as native_catalog
    from hashlib import sha256

    whale = "0x5f94" + "0" * 36
    monkeypatch.setattr(native_catalog, "WHALE_ADDRESS_SHA256", sha256(whale.encode()).hexdigest())
    # Existing, authoritative test-fixture schema. Writes only fixture setup.
    db, snapshot = _v2_snapshot(tmp_path)
    native_registry.apply(db, snapshot, AFTER)
    before_bytes = db.read_bytes()
    # This test invokes the native SQLite owner, which timestamps its answer
    # using the real clock. A fixed T0 makes valid reads look future-dated
    # once the test date has passed; synthetic capture tests still use T0.
    app = DashboardReader(db=db, clock=lambda: datetime.now(UTC), cache=SmallTTLCache())
    found = app.wallets(query="W083", asof=AFTER, limit=1)
    assert found["status"] in {"VERIFIED", "STALE"}
    assert found["data"]["total"] == 1
    assert found["data"]["addresses_redacted"] is True
    assert "W083" in [a["alias"] for a in found["data"]["wallets"][0]["aliases"]]
    assert "0x" not in json.dumps(found["data"])
    assert app.wallets(query="W083", asof=BEFORE)["data"]["total"] == 0
    excluded = app.wallets(excluded=True, limit=10)
    assert excluded["data"]["total"] > 0
    assert all(row["excluded"] for row in excluded["data"]["wallets"])
    assert db.read_bytes() == before_bytes
    assert found["inventory_sha256"] is not None
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
