"""Isolation and release-contract tests for the new paper-only campaign."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import v4_canonical_paper_release as release


def test_rendered_unit_is_pinned_and_paper_only():
    sha = "d" * 40
    root = release.root_for(sha)
    unit = release.unit_text(root, sha)
    args = release.args_for(root)
    assert f"--run-label {release.LABEL}" in unit
    assert "--paper-risk-profile CHALLENGE_TRAILING_8PCT" in unit
    assert str(root) in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=" + str(release.STATE) in unit
    assert "MemoryMax=2G" in unit
    assert "trading-connector" not in unit
    assert "prop-production" not in unit
    assert "guardian" not in unit.lower()
    assert "--broker" not in unit
    assert len([a for a in args if a == "--run-label"]) == 1
    with pytest.raises(ValueError, match="INVALID_RELEASE_SHA"):
        release.root_for("../../bad")


def test_new_campaign_verifier_requires_sixteen_isolated_trailing_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "STATE", tmp_path / "canonical")
    root = release.STATE
    for pid in ("p1", "p14", "p15", "p16", *(f"e{i}" for i in range(1, 13))):
        folder = root / pid / f"{pid}_v4_sixteen_{release.LABEL}"
        folder.mkdir(parents=True)
        manifest = {
            "started_at": "2026-11-11T09:00:00+00:00",
            "rulebook": {
                "initial_balance": "10000",
                "daily_loss": "500",
                "static_loss": None,
                "trailing_loss": "800",
                "trailing_cap": None,
                "account_terms_confirmed": False,
                "source": f"{pid}_TRAILING_8PCT_RESEARCH_NOT_PROP_CONTRACT",
            },
        }
        (folder / "manifest.json").write_text(json.dumps(manifest))
        (folder / "events.jsonl").write_text(
            json.dumps({"event": {"kind": "PM04_CONFIG", "first_known_at": manifest["started_at"]}})
            + "\n"
        )
    assert release.verify_fresh_root() == {
        "new_ledgers": 16,
        "risk_profile": "CHALLENGE_TRAILING_8PCT",
    }
    broken = root / "e7" / f"e7_v4_sixteen_{release.LABEL}" / "manifest.json"
    data = json.loads(broken.read_text())
    data["rulebook"]["static_loss"] = "1000"
    broken.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="UNEXPECTED_RISK_PROFILE"):
        release.verify_fresh_root()
    data["rulebook"]["static_loss"] = None
    broken.write_text(json.dumps(data))
    journal = broken.with_name("events.jsonl")
    journal.write_text(
        json.dumps(
            {"event": {"kind": "PM04_PAPER_EXECUTE", "first_known_at": "2026-11-11T08:58:00+00:00"}}
        )
        + "\n"
    )
    with pytest.raises(RuntimeError, match="PRESTART_SOURCE_REPLAY_ADMITTED"):
        release.verify_fresh_root()


def test_archive_records_35_immutable_historical_heads(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(
        release,
        "unit_status",
        lambda _name: {"ActiveState": "inactive", "MainPID": "0"},
    )
    for service, folder in release.OLD:
        amount = 16 if "sixteen" in folder else 1
        for i in range(amount):
            target = tmp_path / "prospective" / folder / f"p{i}" / "run"
            target.mkdir(parents=True)
            (target / "events.jsonl").write_text('{"kind":"CONFIG"}\n')
            (target / "manifest.json").write_text('{"trading_authorized":false}')
    result = release.archive_old_heads()
    receipt = Path(result["receipt"])
    assert result["historical_ledgers"] == 35
    payload = json.loads(receipt.read_text())
    assert len(payload["journals"]) == 35
    for row in payload["journals"]:
        journal = tmp_path / row["journal_relative"]
        assert sha256(journal.read_bytes()).hexdigest() == row["events_sha256"]
        assert journal.exists()


def test_old_writers_block_historical_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(
        release,
        "unit_status",
        lambda _name: {"ActiveState": "active", "MainPID": "321"},
    )
    with pytest.raises(RuntimeError, match="STILL_WRITING"):
        release.archive_old_heads()
