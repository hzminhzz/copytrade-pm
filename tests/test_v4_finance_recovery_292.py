"""Independent PM03 financial replay identity and no-overwrite backup tests."""

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_v4_finance_recovery import (
    backup_financial_roots,
    replay_financial_roots,
)
from test_pm_vike_paper_integration import new_paper, price
from test_pm_forward_observed_paper import at


def test_finance_backup_replays_same_head_and_blocks_unapproved_or_overwrite(tmp_path):
    source = PaperJournal(tmp_path / "source")
    prices = PaperJournal(tmp_path / "prices")
    price(prices, 1)
    paper = new_paper(tmp_path, source, prices)
    paper.step(at(2))
    original = tmp_path / "vike_virtual"
    baseline = replay_financial_roots((original,))
    assert baseline["run_count"] == 1
    destination = tmp_path / "restored-finance"
    with pytest.raises(ValueError, match="REQUIRES_QUIESCENCE"):
        backup_financial_roots((original,), destination, quiescence_verified=False)
    receipt = backup_financial_roots((original,), destination, quiescence_verified=True)
    assert receipt["status"] == "FINANCIAL_BACKUP_INDEPENDENT_REPLAY_VERIFIED"
    assert receipt["runs"] == baseline["runs"]
    assert receipt["run_count"] == 1
    with pytest.raises(FileExistsError, match="BACKUP_EXISTS"):
        backup_financial_roots((original,), destination, quiescence_verified=True)
