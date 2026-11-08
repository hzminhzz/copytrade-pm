"""Actual restricted-file openat integration for dashboard synthetic capture fixtures.

An alternate os.geteuid is simulated to exercise the producer/reader identity
boundary in a normal unprivileged local test process; this is not an OS ACL
attestation for a deployed dashboard service.
"""

from __future__ import annotations

import json
import os
from datetime import timedelta


from copytrade_pm.dashboard import adapter
from test_dashboard_adapter import T0, capture, fake_native


def _directory(tmp_path, monkeypatch, *, include_history=True):
    target = tmp_path / "owner-output"
    target.mkdir(mode=0o750)
    target.chmod(0o750)
    for command in ("status", "risk", "broker", "portfolio", "intent", "history"):
        if command == "history" and not include_history:
            continue
        if command == "history":
            data = {
                "scientifically_qualified": False,
                "evidence_class": "PAPER_SHADOW",
                "source_coverage": "RECENT_BOUNDED_TAIL_NOT_COMPLETE_HISTORY",
                "rows": [
                    {
                        "journal_sequence": 12,
                        "release_sha": "a" * 64,
                        "observed_at_ms": int((T0 - timedelta(seconds=1)).timestamp() * 1000),
                        "day": 20103,
                        "equity": "10000",
                        "risk_floor": "9600",
                        "headroom": "400",
                    }
                ],
            }
            body = capture(command, data=data)
        else:
            body = capture(command)
        path = target / (command + ".json")
        path.write_text(json.dumps(body))
        path.chmod(0o640)
    # Simulate the trusted source producer having a distinct UID.
    original = os.geteuid()
    monkeypatch.setattr(adapter.os, "geteuid", lambda: original + 5000)
    return target


def test_owner_restricted_files_open_in_real_reader_and_preserve_provenance(tmp_path, monkeypatch):
    target = _directory(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    reader = adapter.DashboardReader(
        capture_root=target,
        clock=lambda: T0,
        native_read=fake_native,
        cache=adapter.SmallTTLCache(),
    )
    report = reader.risk_status()
    assert report["metrics"]["equity"]["value"] == "0"
    assert report["sources"]["risk"]["journal_sequence"] == 12
    assert report["sources"]["risk"]["account_binding_sha"] == "d" * 64
    assert reader.execution_monitor()["link_status"] == "VERIFIED_CAPTURE_BINDING"
    history = reader.performance_history(risk_report=report)
    assert history["status"] == "VERIFIED_OWNER_SHADOW_TAIL"
    assert history["points"][0]["evidence_class"] == "PAPER_SHADOW"
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before


def test_missing_or_symlinked_capture_is_not_financially_admitted(tmp_path, monkeypatch):
    target = _directory(tmp_path, monkeypatch, include_history=False)
    reader = adapter.DashboardReader(
        capture_root=target,
        clock=lambda: T0,
        native_read=fake_native,
        cache=adapter.SmallTTLCache(),
    )
    assert reader.performance_history()["status"] == "UNAVAILABLE"
    (target / "risk.json").unlink()
    (target / "risk.json").symlink_to(target / "status.json")
    blocked = reader.risk_status()
    assert blocked["sources"]["risk"]["status"] == "BLOCKED"
    assert blocked["metrics"]["equity"]["value"] is None


def test_capture_root_is_only_owner_configured_not_browser_supplied(tmp_path, monkeypatch):
    root = tmp_path / "static-admin-root"
    monkeypatch.setenv("DASHBOARD_GUARDIAN_CAPTURE_ROOT", str(root))
    reader = adapter.DashboardReader(clock=lambda: T0, native_read=fake_native)
    assert reader.guardian_provider.directory == root
    assert reader.guardian("risk")["status"] == "UNAVAILABLE"
