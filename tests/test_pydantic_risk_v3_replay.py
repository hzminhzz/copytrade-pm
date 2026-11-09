"""Keep pre-fix v2 hashes while new reduction events use v3 semantics."""

from decimal import Decimal
import json
from pathlib import Path

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pydantic_combined_authorities import BTC, decision_at


def test_v2_risk_archive_replays_exact_then_new_v3_reduction_is_durable(tmp_path):
    home = Path(__file__).resolve().parents[1] / ".workspace/pydantic-0911"
    witness = home / "legacy-risk-v2"
    expected = home / "legacy-risk-v2-expected.json"
    if not witness.exists() or not expected.exists():
        pytest.skip("Required VPS acceptance gate: private pre-fix v2 risk journal")
    original = PaperJournal(witness)
    before = original.path.read_bytes()
    legacy = original.restore("run_1")
    proof = json.loads(expected.read_text())
    assert digest(legacy) == proof["state_sha"]
    assert legacy["journal_head_sha"] == proof["head_sha"]
    assert legacy["cursor"] == proof["cursor"]
    assert original.path.read_bytes() == before
    original.backup(tmp_path / "clone")
    clone = PaperJournal(tmp_path / "clone")
    duplicate = decision_at("2026-11-04T04:10:01+00:00", fresh_quote=True)
    assert clone.append("run_1", "valid-reduction", duplicate) == legacy
    current = decision_at("2026-11-04T04:10:02+00:00", fresh_quote=True)
    with pytest.raises(ValueError, match="LEGACY_RISK_SEMANTICS_READ_ONLY"):
        clone.append("run_1", "downgrade", {**current, "risk_semantics_version": 2})
    updated = clone.append("run_1", "v3-reduction", current)
    assert Decimal(updated["account"]["quantities"].get(BTC.key, "0")) == 0
    assert updated["account"]["risk"] == "HALT"
    assert updated["account"]["halt_reason"] == legacy["account"]["halt_reason"]
    assert clone.restore("run_1") == updated
    assert clone.append("run_1", "v3-reduction", current) == updated
