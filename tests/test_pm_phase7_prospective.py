"""Offline falsification tests for Phase 7 prospective source observation."""

from __future__ import annotations

import asyncio
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import pm_phase7_prospective as phase7
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import read_public_collateral_scope


def _encoded(path: Path, payload: dict) -> str:
    blob = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(blob)
    return sha256(blob).hexdigest()


@pytest.fixture
def study(tmp_path):
    decision = json.loads(phase7.DEFAULT_DECISION.read_text())
    canonical = {
        alias: "0x" + f"{index:040x}"
        for index, alias in enumerate(sorted(phase7.REQUIRED_ALIASES), 1)
    }
    for alias, address in canonical.items():
        decision["wallet_bindings"][alias] = sha256(address.encode()).hexdigest()
    original = {
        "schema": phase7.SOURCE_SCHEMA,
        "wallets": [
            {"alias": alias, "address": addr, "recommendation": "CANDIDATE_UNVERIFIED"}
            for alias, addr in canonical.items()
        ],
    }
    frozen = {
        "schema": phase7.RESEARCH_SCHEMA,
        "candidate_search": {"all_five_considered": 42_504},
        "finalists": [
            {"members": list(members)} for members in phase7.PERMITTED_PORTFOLIOS.values()
        ],
    }
    source = tmp_path / "universe.json"
    historical = tmp_path / "historical.json"
    decision_path = tmp_path / "decision.json"
    db_path = tmp_path / "registry.sqlite"
    decision["prior_research"]["frozen_source_universe_sha256"] = _encoded(source, original)
    decision["prior_research"]["retrospective_evidence_sha256"] = _encoded(historical, frozen)
    decision["registry"]["required_manifest_sha256"] = "a" * 64
    _encoded(decision_path, decision)
    with closing(sqlite3.connect(db_path)) as db:
        db.executescript(
            """
            CREATE TABLE snapshot_meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,venue TEXT,address TEXT);
            CREATE TABLE cohort_memberships(wallet_id INTEGER,cohort_id TEXT);
            CREATE TABLE exclusions(wallet_id INTEGER);
            """
        )
        db.execute("INSERT INTO snapshot_meta VALUES(?,?)", ("manifest_sha256", "a" * 64))
        for idx, (_alias, addr) in enumerate(sorted(canonical.items()), 1):
            db.execute("INSERT INTO wallets VALUES(?,?,?)", (idx, "hyperliquid", addr))
            db.execute(
                "INSERT INTO cohort_memberships VALUES(?,?)",
                (idx, "research-108" if idx % 2 else "hyperx-30"),
            )
        db.commit()
    return {
        "decision": decision_path,
        "universe": source,
        "evidence": historical,
        "db": db_path,
        "canonical": canonical,
    }


def preflight(sources):
    return phase7.preflight(
        decision_path=sources["decision"],
        universe_path=sources["universe"],
        evidence_path=sources["evidence"],
        registry_path=sources["db"],
    )


def test_preflight_eight_unique_whole_hash_registered_sources_no_finance(study):
    output, sources = preflight(study)
    assert len(sources) == 8
    assert len(output["selected_portfolios"]) == 3
    assert output["order_route"] == "NONE"
    assert output["scientifically_qualified"] is False
    assert output["financial_paper_events_committed"] == 0
    assert not output["first_known_source_receipts_attested"]
    assert "0x000" not in json.dumps(output)
    assert output["status"] == "RESEARCH_PRIORITY_PREPARED_OBSERVATION_NOT_YET_ATTESTED"


def test_source_universe_mutation_blocks_without_rebinding_research_history(study):
    blob = json.loads(study["universe"].read_text())
    blob["wallets"][0]["recommendation"] = "REJECT"
    _encoded(study["universe"], blob)
    with pytest.raises(phase7.Phase7ResearchBlocked, match="HISTORICAL_EVIDENCE_SHA"):
        preflight(study)


def test_owner_exclusion_blocks_entire_captured_scope(study):
    with closing(sqlite3.connect(study["db"])) as db:
        db.execute("INSERT INTO exclusions VALUES(1)")
        db.commit()
    with pytest.raises(phase7.Phase7ResearchBlocked, match="OWNER_EXCLUDED"):
        preflight(study)


def test_trading_permission_mutation_is_refused(study):
    manifest = json.loads(study["decision"].read_text())
    manifest["research_contract"]["trading_authorized"] = True
    _encoded(study["decision"], manifest)
    with pytest.raises(phase7.Phase7ResearchBlocked, match="FINANCIALLY_AUTHORIZED"):
        preflight(study)


def test_wallet_hash_conflict_refused(study):
    manifest = json.loads(study["decision"].read_text())
    manifest["wallet_bindings"]["H02"] = manifest["wallet_bindings"]["N05"]
    _encoded(study["decision"], manifest)
    with pytest.raises(phase7.Phase7ResearchBlocked, match="DUPLICATED_SOURCE"):
        preflight(study)


def test_altered_portfolio_membership_does_not_promote(study):
    manifest = json.loads(study["decision"].read_text())
    manifest["portfolios"][0]["members"] = ["HX04", "N05", "VS025", "VS035", "H02"]
    _encoded(study["decision"], manifest)
    with pytest.raises(phase7.Phase7ResearchBlocked, match="MEMBERSHIP_DRIFT"):
        preflight(study)


def test_fabricated_source_receipt_count_is_not_accepted(study, tmp_path):
    _, sources = preflight(study)
    journal = PaperJournal(tmp_path / "canary")
    calls = []

    async def fake_source(*, alias, address, journal, seconds, max_frames):
        calls.append(alias)
        return {
            "wallet_alias": alias,
            "account_address_sha256": sha256(address.encode()).hexdigest(),
            "per_account_receipts": 1,
            "transport_status": "BOUNDED_SESSION_ENDED_NOT_CONTINUOUS",
            "whole_wallet_equity_attested": False,
            "paper_admitted": False,
            "order_route": "NONE",
        }

    async def failed_collateral(*, address):
        return {
            "account_address_sha256": sha256(address.encode()).hexdigest(),
            "source_equity": None,
            "collateral_reconciled": False,
            "order_route": "NONE",
            "observations": [],
        }

    observed = asyncio.run(
        phase7.capture_bounded(
            sources=sources,
            journal=journal,
            capture_one=fake_source,
            capture_collateral=failed_collateral,
        )
    )
    assert len(calls) == 8 and len(set(calls)) == 8
    assert observed["new_public_source_receipts"] == 0
    assert observed["public_source_accounts_with_new_receipts"] == 0
    assert all(
        x["transport_status"] == "BLOCKED_PUBLIC_CAPTURE_OR_INTEGRITY"
        for x in observed["observations"]
    )
    assert observed["paper_running"] is False
    assert observed["financial_paper_events_committed"] == 0


def test_bounded_collateral_diagnostic_stays_source_equity_unknown(study, tmp_path):
    _, sources = preflight(study)
    journal = PaperJournal(tmp_path / "canary")

    async def no_source(*, alias, address, journal, seconds, max_frames):
        return {
            "wallet_alias": alias,
            "account_address_sha256": sha256(address.encode()).hexdigest(),
            "per_account_receipts": 0,
            "transport_status": "BOUNDED_SESSION_ENDED_NOT_CONTINUOUS",
            "whole_wallet_equity_attested": False,
            "paper_admitted": False,
            "order_route": "NONE",
        }

    def info(request):
        if request["type"] == "spotClearinghouseState":
            raw = b'{"balances":[]}'
            return {"balances": []}, raw, sha256(raw).hexdigest()
        raw = b"[]"
        return [], raw, sha256(raw).hexdigest()

    async def collateral(*, address):
        return await read_public_collateral_scope(
            address=address, info=info, now=lambda: "2026-11-05T03:42:00+00:00"
        )

    report = asyncio.run(
        phase7.capture_bounded(
            sources=sources,
            journal=journal,
            capture_one=no_source,
            capture_collateral=collateral,
        )
    )
    assert report["new_collateral_diagnostic_groups"] == 8
    assert report["whole_account_equity_attested"] is False
    assert report["financial_paper_events_committed"] == 0
    for alias, source in sources.items():
        assert journal.collateral_scope_status(source.address_sha256)["source_equity"] is None
        assert journal.source_status("PH7_" + alias)["cursor"] == 0


def test_preexisting_financial_state_fails_before_public_capture(study, tmp_path):
    _, sources = preflight(study)
    journal = PaperJournal(tmp_path / "canary")
    with closing(sqlite3.connect(journal.path)) as db:
        db.execute(
            "INSERT INTO runs(run_id,account_id,manifest,manifest_sha,snapshot,"
            "snapshot_sha,last_event_at,cursor) VALUES(?,?,?,?,?,?,?,?)",
            ("R", "A", "{}", "0" * 64, "{}", "0" * 64, "2026-11-05T00:00:00Z", 0),
        )
        db.commit()
    with pytest.raises(phase7.Phase7ResearchBlocked, match="HAS_FINANCIAL_STATE"):
        asyncio.run(phase7.capture_bounded(sources=sources, journal=journal))


def test_capture_root_must_not_be_existing_observer_or_repo(tmp_path):
    with pytest.raises(phase7.Phase7ResearchBlocked, match="NOT_EXPLICITLY_ISOLATED"):
        phase7._restricted_journal_root(tmp_path / "phase7-fivepod-20261105")
    with pytest.raises(phase7.Phase7ResearchBlocked):
        phase7._restricted_journal_root(phase7.ALLOWED_CAPTURE_ROOT / "p1p14-observer-20261105")
