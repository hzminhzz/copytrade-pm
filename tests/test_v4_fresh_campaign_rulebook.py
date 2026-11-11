"""Fresh virtual-paper account policy cannot rewrite legacy risk history."""

from __future__ import annotations

from decimal import Decimal as D
import json

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_pm_forward_observed_paper import RAW_MARKET, add_quote, at, registry


def make_paper(tmp_path, *, name: str, profile: str) -> ObservedP1Paper:
    data = PaperJournal(tmp_path / "source")
    if not (tmp_path / "fixture_ready").exists():
        add_quote(data, 10)
        registry(tmp_path / "registry.sqlite")
        (tmp_path / "fixture_ready").touch()
    return ObservedP1Paper(
        source_db=data.path,
        state_root=tmp_path / "paper",
        run_id=name,
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=tmp_path / "registry.sqlite",
        started_at=at(0),
        paper_risk_profile=profile,
    )


def test_new_challenge_account_has_trailing_8pct_and_5pct_daily(tmp_path):
    p = make_paper(tmp_path, name="p1_canonical_1111", profile="CHALLENGE_TRAILING_8PCT")
    r = p.run.account.rulebook
    assert r.initial_balance == D("10000")
    assert r.daily_loss == D("500")
    assert r.static_loss is None
    assert r.trailing_loss == D("800")
    assert r.trailing_cap is None  # Do not invent a profit-lock cap.
    assert not r.account_terms_confirmed
    assert "NOT_PROP_CONTRACT" in r.source
    assert p.run.account.floor()[1]["trailing"] == D("9200")
    p.run.account.high_water = D("10300")
    assert p.run.account.floor()[1]["trailing"] == D("9500")
    saved = json.loads((tmp_path / "paper/p1_canonical_1111/manifest.json").read_text())
    assert saved["rulebook"]["trailing_loss"] == "800"
    assert saved["rulebook"]["static_loss"] is None
    assert saved["pm02_sha"] == p.policy_sha
    # Restart with the same identity and contract must not reset the account.
    same = make_paper(tmp_path, name="p1_canonical_1111", profile="CHALLENGE_TRAILING_8PCT")
    assert same.run.account.rulebook.sha == r.sha
    assert same.policy_sha == p.policy_sha
    with pytest.raises(ValueError, match="PAPER_RESTART_MANIFEST_POLICY_DRIFT"):
        make_paper(tmp_path, name="p1_canonical_1111", profile="LEGACY_STATIC_10PCT")


def test_legacy_account_remains_static_ten_percent(tmp_path):
    p = make_paper(tmp_path, name="p1_legacy_0911", profile="LEGACY_STATIC_10PCT")
    assert p.run.account.rulebook.static_loss == D("1000")
    assert p.run.account.rulebook.trailing_loss is None
    assert "paper_challenge_risk_profile" not in p.policy


def test_unknown_paper_risk_profile_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="PAPER_RISK_PROFILE_UNSUPPORTED"):
        make_paper(tmp_path, name="p1_invalid", profile="UNKNOWN")
