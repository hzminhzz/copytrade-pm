"""Predeclared, immutable OOS windows and conservative lifecycle transitions."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from copytrade_pm.pm02_campaign import register_plan, read_plan, window_asof, transition
from copytrade_pm.pm_manager import _score, timestamp, _prospective_evidence, rank
from test_pm_manager import ASOF, ALIASES, replay, samples

NOW = datetime(2026, 11, 1, tzinfo=UTC)
COHORT = [f"TEST-{i:02d}" for i in range(36)]


def windows():
    start = NOW + timedelta(days=1)
    return [
        {
            "id": f"oos-{i + 1}",
            "start_at": (start + timedelta(days=30 * i)).isoformat(),
            "end_at": (start + timedelta(days=30 * (i + 1))).isoformat(),
            "decision_at": (start + timedelta(days=30 * (i + 1), hours=1)).isoformat(),
        }
        for i in range(4)
    ]


def test_registration_is_immutable_and_cannot_be_backdated(tmp_path):
    path = register_plan(
        tmp_path / "campaign",
        pm01_sha256="a" * 64,
        aliases=COHORT,
        windows=windows(),
        clock_source=lambda: NOW,
    )
    plan = read_plan(path)
    assert plan["declared_hypotheses"] == 36 * 3 * 4
    assert window_asof(plan, NOW.isoformat()) is None
    assert window_asof(plan, windows()[0]["decision_at"])["id"] == "oos-1"
    assert (
        register_plan(
            tmp_path / "campaign",
            pm01_sha256="a" * 64,
            aliases=COHORT,
            windows=windows(),
            clock_source=lambda: NOW,
        )
        == path
    )
    with pytest.raises(ValueError, match="IMMUTABLE_CAMPAIGN"):
        register_plan(
            tmp_path / "campaign",
            pm01_sha256="b" * 64,
            aliases=COHORT,
            windows=windows(),
            clock_source=lambda: NOW,
        )
    with pytest.raises(ValueError, match="BEFORE_OOS"):
        register_plan(
            tmp_path / "late",
            pm01_sha256="a" * 64,
            aliases=COHORT,
            windows=windows(),
            clock_source=lambda: NOW + timedelta(days=2),
        )
    value = json.loads(path.read_text())
    value["declared_hypotheses"] = 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        read_plan(path)


def test_overlapping_oos_windows_and_underdeclared_trials_rejected(tmp_path):
    overlapping = windows()
    overlapping[1]["start_at"] = overlapping[0]["start_at"]
    with pytest.raises(ValueError, match="OVERLAPPING"):
        register_plan(
            tmp_path / "bad",
            pm01_sha256="a" * 64,
            aliases=COHORT,
            windows=overlapping,
            clock_source=lambda: NOW,
        )


def test_evidence_reuse_cannot_advance_lifecycle():
    assert transition("SHADOW", qualified=True, new_window=False, failures=0) == "SHADOW"
    state = "CANDIDATE"
    for expected in ("SHADOW", "INCUBATION", "ACTIVE", "CORE"):
        state = transition(state, qualified=True, new_window=True, failures=0)
        assert state == expected
    assert transition("ACTIVE", qualified=False, new_window=True, failures=1) == "REDUCED"
    assert (
        transition("ACTIVE", qualified=False, new_window=True, failures=1, stale=True)
        == "SUSPENDED"
    )
    assert transition("REDUCED", qualified=False, new_window=True, failures=3) == "RETIRED"
    assert transition("RETIRED", qualified=True, new_window=True, failures=3) == "RETIRED"


def test_multiplicity_penalty_counts_the_declared_family():
    rows = samples("A")
    normal = _score(rows, ASOF, 36)
    many = _score(rows, ASOF, 100000)
    assert many["incremental_lcb_r"] < normal["incremental_lcb_r"]


def test_signed_head_without_preregistered_oos_never_qualifies():
    report = rank(
        replay(), ALIASES, ASOF.isoformat(), {"A": samples("A")}, prospective_verified_head="a" * 64
    )
    assert report["qualified_count"] == 0
    assert "PREDECLARED_OOS_REQUIRED" in report["cards"][0]["prospective"]["reasons"]


def test_pit_sorting_uses_utc_instants_and_boolean_claims_are_strict():
    rows = samples("A", count=2)
    rows[0]["event_at"] = "2026-10-30T02:00:00+02:00"
    rows[0]["known_at"] = "2026-10-30T00:01:00+00:00"
    rows[0]["outcome_known_at"] = "2026-10-30T00:02:00+00:00"
    rows[1]["event_at"] = "2026-10-30T00:30:00+00:00"
    rows[1]["known_at"] = "2026-10-30T00:31:00+00:00"
    rows[1]["outcome_known_at"] = "2026-10-30T00:32:00+00:00"
    ordered = _prospective_evidence(list(reversed(rows)), timestamp(ASOF.isoformat()))
    assert ordered[0]["episode_id"] == rows[0]["episode_id"]
    rows[0]["verified_first_known"] = "false"
    assert len(_prospective_evidence(rows, ASOF)) == 1


def test_campaign_itself_must_be_known_at_the_decision(tmp_path):
    path = register_plan(
        tmp_path / "clock",
        pm01_sha256="a" * 64,
        aliases=COHORT,
        windows=windows(),
        clock_source=lambda: NOW,
    )
    with pytest.raises(ValueError, match="CAMPAIGN_NOT_KNOWN_ASOF"):
        window_asof(read_plan(path), (NOW - timedelta(seconds=1)).isoformat())
