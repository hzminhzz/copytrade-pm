"""Current Gemini V2 priorities are read-only overlays, never WR/FP source promotion."""

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_portfolios as sealed
from copytrade_pm import wallet_registry_priority as priority
from test_wallet_registry_runs import _db

REPO = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc).isoformat()


def test_pinned_v2_current_selection_distinct_from_original_wr_fp(tmp_path: Path) -> None:
    selection = priority.priority_v2(REPO, as_of=NOW)
    assert selection["schema"] == "wallet_registry_priority_overlay_v1"
    assert selection["state"] == "NEW_RESEARCH_ONLY_NOT_REGISTERED"
    assert selection["source_sha256"] == priority.SOURCE_SHA256
    assert selection["priority"] == ["E6", "E2", "P1", "E3", "B_phase5"]
    assert selection["paper_registry_changed"] is False
    assert selection["forward_paper_portfolios_changed"] is False
    assert selection["trading_authorized"] is False
    members = selection["portfolios"]
    assert members["E6"]["research_disposition"] == "PRIMARY_FORWARD_PAPER_RESEARCH"
    assert members["E2"]["research_disposition"] == "THREE_POD_FORWARD_PAPER_CHALLENGER"
    assert set(members["E2"]["member_aliases"]) == {
        "ACT04",
        "S053-HYPE",
        "S051-BTC",
    }
    assert set(members["E2"]["member_aliases"]).issubset(set(members["E6"]["member_aliases"]))
    assert members["P1"]["research_disposition"] == "INCUMBENT_HISTORICAL_BASELINE_NO_NEW_PROMOTION"
    assert members["P14"]["research_disposition"] == "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER"
    assert members["P14"]["new_research_rank"] is None
    assert tuple(members["P1"]["member_aliases"]) == reg.PORTFOLIOS["P1"]
    assert tuple(members["P14"]["member_aliases"]) == reg.PORTFOLIOS["P14"]
    assert all(member["nominal_total_risk_budget_usd"] == 600 for member in members.values())
    assert all(member["registered_forward_paper_worker"] is False for member in members.values())
    assert all(
        member["wallet_identity_independently_proven"] is False for member in members.values()
    )

    private = _db(tmp_path)
    with closing(reg.connect(private, False)) as db:
        before = sealed.select_asof(db, "P1", NOW)
        assert before["state"] == "PAPER_RESEARCH_PRIMARY"
        assert before["definition_sha256"] != priority.SOURCE_SHA256
        assert before["definition_sha256"] != selection["source_sha256"]
        p14 = sealed.select_asof(db, "P14", NOW)
        assert p14["state"] == "PAPER_RESEARCH_CHALLENGER"
        assert before["source_identity_proven"] is False
        assert p14["source_identity_proven"] is False


def test_priority_asof_is_not_backdated_to_report_date() -> None:
    early = priority.priority_v2(REPO, as_of="2026-11-04T09:06:32+00:00")
    assert early["state"] == "UNKNOWN_AT_ASOF"
    assert early["new_research_priorities"] == []
    assert early["trading_authorized"] is False
    now = priority.priority_v2(REPO, as_of="2026-11-04T09:06:33+00:00")
    assert now["state"] == "NEW_RESEARCH_ONLY_NOT_REGISTERED"
    with pytest.raises(ValueError, match="OFFSET"):
        priority.priority_v2(REPO, as_of="2026-11-04T16:20:00")


def test_priority_frozen_bytes_refuse_tamper_and_symlink(tmp_path: Path) -> None:
    target = tmp_path / priority.SOURCE
    target.parent.mkdir(parents=True)
    shutil.copy2(REPO / priority.SOURCE, target)
    assert priority.priority_v2(tmp_path, as_of=NOW)["source_sha256"] == priority.SOURCE_SHA256
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="PRIORITY_V2_SOURCE_DOCUMENT_DRIFT"):
        priority.priority_v2(tmp_path, as_of=NOW)
    target.unlink()
    target.symlink_to(REPO / priority.SOURCE)
    with pytest.raises(ValueError, match="PRIORITY_V2_SOURCE_FILE_UNAVAILABLE"):
        priority.priority_v2(tmp_path, as_of=NOW)


def test_priority_cli_presents_v2_without_changing_source_seals_or_paper(tmp_path, capsys):
    private = _db(tmp_path)
    before = sha256(private.read_bytes()).hexdigest()
    assert reg.cli(["--db", str(private), "--decision-repo", str(REPO), "portfolio", "P1"]) == 0
    p1 = json.loads(capsys.readouterr().out)["P1"]
    assert p1["state"] == "PAPER_RESEARCH_PRIMARY"
    assert p1["new_research_priority_v2"] == "INCUMBENT_HISTORICAL_BASELINE_NO_NEW_PROMOTION"
    assert p1["new_research_rank_v2"] == 3
    assert p1["source_sealed"] is True
    assert p1["research_priority_is_not_paper_admission"] is True
    assert p1["actual_run"] == "UNKNOWN"
    assert p1["authorized"] is False
    assert reg.cli(["--db", str(private), "--decision-repo", str(REPO), "portfolio", "P14"]) == 0
    p14 = json.loads(capsys.readouterr().out)["P14"]
    assert p14["state"] == "PAPER_RESEARCH_CHALLENGER"
    assert p14["new_research_priority_v2"] == "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER"
    assert p14["new_research_rank_v2"] is None
    assert p14["authorized"] is False
    assert reg.cli(["--db", str(private), "--decision-repo", str(REPO), "priority"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["portfolios"]["E6"]["new_research_rank"] == 1
    assert result["portfolios"]["E2"]["new_research_rank"] == 2
    assert result["paper_admitted"] is False
    assert sha256(private.read_bytes()).hexdigest() == before


def test_standalone_registry_without_later_v2_source_fails_closed_not_broken(tmp_path, capsys):
    private = _db(tmp_path)
    root = tmp_path / "old_release"
    root.mkdir()
    args = [
        "--db",
        str(private),
        "--decision-repo",
        str(root),
        "portfolio",
        "P1",
    ]
    assert reg.cli(args) == 0
    p1 = json.loads(capsys.readouterr().out)["P1"]
    assert p1["state"] == "PAPER_RESEARCH_PRIMARY"
    assert p1["new_research_priority_view_status"] == "PRIORITY_V2_SOURCE_NOT_INSTALLED"
    assert p1["new_research_priority_v2"] == "NOT_SELECTED_OR_UNKNOWN"
    assert p1["actual_run"] == "UNKNOWN" and p1["authorized"] is False
    with pytest.raises(ValueError, match="PRIORITY_V2_SOURCE_FILE_UNAVAILABLE"):
        reg.cli(["--decision-repo", str(root), "priority"])


def test_old_asof_keeps_original_state_and_no_new_priority(tmp_path, capsys):
    private = _db(tmp_path)
    args = [
        "--db",
        str(private),
        "--decision-repo",
        str(REPO),
        "portfolio",
        "P1",
        "--asof",
        "2026-11-03T10:00:00+00:00",
    ]
    assert reg.cli(args) == 0
    row = json.loads(capsys.readouterr().out)["P1"]
    assert row["state"] == "PAPER_RESEARCH_PRIMARY"
    assert row["new_research_priority_v2"] == "NOT_SELECTED_OR_UNKNOWN"
    assert row["new_research_priority_source_sha256"] is None
    assert row["authorized"] is False
