"""Real-format official public source receipts must not reach PM04 financial effects.

This is a source-to-ledger integration regression, not retrospective trading
research. Reuse exactly the production public all-DEX parser and the existing
PM04/PM03 fixture worker, with independent P1/P14 $10k journals. The input
lacks atomic parent/subaccount/spot/vault NAV and must fail closed.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_fixture_worker import FixturePaperWorker
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_portfolios import P1, P14
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import sample_state
from test_pm_forward_journal import manifest
from test_pm_forward_pm04 import BTC, policy

SOURCE_KNOWN_AT = (datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)).isoformat()
DECISION_AT = "2026-11-04T04:02:00+00:00"
FILL_AT = "2026-11-04T04:02:02+00:00"


def run_manifest(portfolio, frozen_policy):
    original = manifest(portfolio.name, portfolio.name + "_account")
    return replace(
        original,
        rulebook=replace(original.rulebook, confirmed=True, permitted=(BTC,)),
        portfolio_sha=portfolio.sha,
        policy_sha=digest(frozen_policy),
    )


def test_real_format_five_source_receipts_do_not_execute_or_consume_paper_cursors(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    for index, alias in enumerate(P14.members, 1):
        address = f"0x{index:040x}"
        state = deepcopy(sample_state())
        state["user"] = address
        receipt = read_public_all_dex_scope(
            alias=alias,
            address=address,
            frame={"channel": "allDexsClearinghouseState", "data": state},
            dex_catalog=[None, {"name": "xyz"}],
            discovered_subaccounts=None,
            first_known_at=SOURCE_KNOWN_AT,
        )
        assert receipt["source_book"]["synthetic_fixture"] is False
        assert receipt["source_book"]["source_equity"] is None
        assert receipt["source_book"]["position_margin_diagnostics"]
        append_public_scope(journal, alias=alias, seq=1, receipt=receipt)

    policies = {
        "P1": policy(P1.members, "3000"),
        "P14": policy(P14.members, "1600"),
    }
    prepared = {
        name: run_manifest(portfolio, policies[name])
        for name, portfolio in (("P1", P1), ("P14", P14))
    }
    workers = {
        name: FixturePaperWorker(journal, portfolio, prepared[name], policies[name])
        for name, portfolio in (("P1", P1), ("P14", P14))
    }

    before = {name: journal.restore(name) for name in workers}
    assert all(row["cursor"] == 1 for row in before.values())
    assert all(row["account"]["cash"] == "10000" for row in before.values())
    assert all(row["account"]["quantities"] == {} for row in before.values())
    assert all(row["source_cursors"] == {} for row in before.values())
    for name, worker in workers.items():
        readiness = worker.readiness(decision_at=DECISION_AT)
        assert readiness["status"] == "BLOCKED"
        assert readiness["missing_wallets"] == []
        assert set(readiness["stale_or_incomplete_wallets"]) == set(worker.portfolio.members)
        result = worker.drive(
            decision_at=DECISION_AT,
            hypothetical_fill_at=FILL_AT,
            observations=[],
            shocks=[],
            evidence={},
            costs={},
            market_contracts={},
        )
        assert result["status"] == "BLOCKED"
        assert result["paper_observed"] is False
        assert result["order_route"] == "NONE"
        assert journal.restore(name) == before[name]

    # Restart re-registers the same frozen PM04 policy and leaves financial
    # heads/cursors exactly identical, even with five live-format source tapes.
    reopened = PaperJournal(journal.root)
    for name, portfolio in (("P1", P1), ("P14", P14)):
        worker = FixturePaperWorker(reopened, portfolio, prepared[name], policies[name])
        assert worker.readiness(decision_at=DECISION_AT)["status"] == "BLOCKED"
        assert reopened.restore(name) == before[name]
    assert all(reopened.source_status(alias)["cursor"] == 1 for alias in P14.members)
    assert not any(reopened.restore(name)["account"]["quantities"] for name in ("P1", "P14"))
