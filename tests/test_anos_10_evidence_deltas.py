"""ANOS-10: causal evidence deltas and independently scoped source failures."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import pm_cwsa_chapter2_gate as gate
from copytrade_pm import pm_cwsa_six_paper as six
from copytrade_pm import pm_operations
from copytrade_pm.pm_cwsa_chapter2_projection import project, site_owner_view


@pytest.fixture
def assessment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    checkpoint = int(datetime.now(UTC).timestamp() * 1000) - 10_000
    wallets = sorted(gate.EXPECTED_WALLETS)
    source = {
        "latest_checkpoint_ms": checkpoint,
        "policy_grace_ms": 180_000,
        "source_count": len(wallets),
        "head_sha256": "a" * 64,
        "latest_kinds": dict.fromkeys(wallets, "BASELINE"),
        "checkpoint_ms_by_wallet": dict.fromkeys(wallets, checkpoint),
        "published_ms_by_wallet": dict.fromkeys(wallets, checkpoint + 1500),
        "receipt_first_known_ms_by_wallet": dict.fromkeys(wallets, checkpoint + 1000),
        "complete_position_proof_by_wallet": dict.fromkeys(wallets, True),
        "source_heads_by_wallet": dict.fromkeys(wallets, "1" * 64),
        "policy_epochs_by_wallet": dict.fromkeys(wallets, "2" * 64),
        "scope_generations_by_wallet": dict.fromkeys(wallets, "3" * 64),
        "changed_sources": {},
    }
    paper = {
        "cursor": 0,
        "journal_head_sha": "b" * 64,
        "wave_head_sha": "c" * 64,
        "wave_count": 0,
        "wave_checkpoint_ms": 0,
        "signed_mandates": 0,
        "finance_scan_count": 0,
        "finance_scan_checkpoint_ms": 0,
        "modeled_effects": 0,
        "current_equity": "10000",
        "realized_pnl": "0",
        "costs": "0",
        "positions_count": 0,
    }
    monkeypatch.setattr(
        pm_operations,
        "_doctor",
        lambda db: pm_operations.result(
            "registry.doctor",
            "BLOCKED",
            {
                "database_integrity": "VERIFIED",
                "research_selection_integrity": "BLOCKED_MISSING_EXTERNAL_PROOF",
                "inventory_sha256": "d" * 64,
            },
            authority="sqlite_wallet_registry",
        ),
    )

    def seals(db, portfolios=None):
        return {
            pid: {
                "version": 2,
                "definition_sha256": "e" * 64,
                "selection_known_at": "2026-11-12T00:00:00+00:00",
                "members": tuple(sorted(six.PORTFOLIO_CONFIGS[pid]["members"])),
            }
            for pid in (portfolios or tuple(six.PORTFOLIO_CONFIGS))
        }

    monkeypatch.setattr(six, "load_registry_seals", seals)
    monkeypatch.setattr(gate, "_source_facts", lambda db: source)
    monkeypatch.setattr(
        gate, "_paper_facts", lambda root, *, portfolios=None: {pid: paper for pid in portfolios}
    )
    monkeypatch.setattr(
        gate,
        "_market_evidence",
        lambda db, src: gate.GateCheck(
            "independent_executable_quotes",
            "BLOCKED_EVIDENCE",
            "NATIVE_L2_CHAINS_VERIFIED_BUT_STALE",
            {"quote_heads_sha256": "f" * 64, "latest_age_ms": 999999},
        ),
    )

    def invoke(pid: str = "A", *, prior: Path | None = None, inspection: str = "evidence"):
        argv = [
            "cwsa",
            "chapter2",
            "explain",
            "--portfolio",
            pid,
            "--inspection",
            inspection,
            "--registry-db",
            str(tmp_path / "registry"),
            "--source-db",
            str(tmp_path / "source"),
            "--paper-root",
            str(tmp_path / "paper"),
            "--quote-db",
            str(tmp_path / "quotes"),
        ]
        if prior is not None:
            argv.extend(["--prior-snapshot", str(prior)])
        code = pm_operations.cli(argv)
        return code, json.loads(capsys.readouterr().out)

    def save(report):
        path = tmp_path / "prior.json"
        path.write_text(json.dumps(report))
        return path

    return source, paper, invoke, save


def test_site_owner_view_parity_redaction_and_no_side_effect(assessment, monkeypatch, capsys):
    source, _, invoke, _ = assessment
    _, cli_owner = invoke("A")
    from copytrade_pm import pm_cwsa_chapter2_projection as projection

    # The Site transport is the *same* evaluated CLI owner result, not a
    # frontend reconstruction or a second source/finance query.
    view = site_owner_view(cli_owner)
    assert view["schema"] == "cwsa_chapter2_site_owner_view_v1"
    assert view["source_schema"] == cli_owner["schema"]
    for key in ("scope", "generation_consistency", "economics", "prior_to_current"):
        assert view[key] == cli_owner[key]
    assert (
        view["owner_heads"]["source"]["receipt_first_known_ms_by_wallet"]
        == (cli_owner["owner_heads"]["source"]["receipt_first_known_ms_by_wallet"])
    )
    assert view["blockers"] == cli_owner["blockers"]
    assert view["fault_isolation"] == cli_owner["fault_isolation"]
    assert view["next_operation"]["effect_class"] == "READ_ONLY"
    assert view["next_operation"]["auto_dispatched"] is False
    assert view["economics"]["realized_pnl_usd"] is None
    assert view["trading_authorized"] is False
    assert view["order_route"] == "NONE"

    # Inject private evidence into the internal owner result. Only approved
    # scalar/head keys may leave the Site interface.
    cli_owner["private_account_key"] = "PRIVATE_CANARY"
    cli_owner["owner_heads"]["source"]["raw_journal"] = "PRIVATE_CANARY"
    cli_owner["owner_heads"]["source"]["source_heads_by_wallet"]["W028"] = "PRIVATE_CANARY"
    cli_owner["owner_heads"]["source"]["source_heads_by_wallet"][
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ] = "PRIVATE_CANARY"
    cli_owner["dimensions"]["source_observation"]["evidence"] = {
        "raw_address": "PRIVATE_CANARY",
        "secret": "PRIVATE_CANARY",
    }
    cli_owner["blockers"].append(
        {
            "reason_code": "BLOCKED",
            "owner": "source",
            "affected_portfolio": "A",
            "raw_journal": "PRIVATE_CANARY",
        }
    )
    clean = site_owner_view(cli_owner)
    assert "PRIVATE_CANARY" not in json.dumps(clean)
    assert "raw_journal" not in json.dumps(clean)
    assert "source_observation" in clean["dimensions"]

    # The actual CLI site-view verb uses the owner exactly once.
    monkeypatch.setattr(projection, "explain_task", lambda args: cli_owner)
    assert pm_operations.cli(["cwsa", "chapter2", "site-view", "--portfolio", "A"]) == 0
    routed = json.loads(capsys.readouterr().out)
    assert routed == clean
    assert source["head_sha256"] == "a" * 64


def test_site_owner_view_scoped_fault_mixed_epoch_and_unknown_finance(assessment):
    source, _, invoke, save = assessment
    _, baseline = invoke("A")
    source["latest_kinds"]["W028"] = "UNAVAILABLE"
    source["policy_epochs_by_wallet"]["W028"] = "9" * 64
    _, affected = invoke("A", prior=save(baseline))
    _, unaffected = invoke("B")
    a = site_owner_view(affected)
    b = site_owner_view(unaffected)
    assert a["generation_consistency"]["state"] == "MIXED"
    assert a["scope"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert b["scope"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
    assert a["fault_isolation"]["affected_portfolios"] == ["A", "Combo2"]
    assert "B" in a["fault_isolation"]["unaffected_source_portfolios"]
    assert a["fault_isolation"]["shared_account_risk"]["state"] == "UNKNOWN"
    assert a["prior_to_current"]["changed_wallets"] == ["W028"]
    assert a["economics"]["realized_pnl_usd"] is None
    assert b["economics"]["total_costs_usd"] is None
    assert all(not row["trading_authorized"] for row in (a, b))


def test_site_owner_view_rejects_wrong_schema_or_financial_permission():
    with pytest.raises(ValueError, match="SCHEMA_UNSUPPORTED"):
        site_owner_view({"schema": "untrusted"})
    with pytest.raises(ValueError, match="EFFECT_PERMISSION_UNSAFE"):
        site_owner_view(
            {
                "schema": "cwsa_chapter2_task_explanation_v1",
                "order_route": "PLACE_ORDER",
                "trading_authorized": True,
                "scope": {"portfolio": "A"},
            }
        )
    with pytest.raises(ValueError, match="SCOPE_UNVERIFIED"):
        site_owner_view(
            {
                "schema": "cwsa_chapter2_task_explanation_v1",
                "order_route": "NONE",
                "trading_authorized": False,
                "scope": {"portfolio": None},
            }
        )


def test_identical_original_evidence_does_not_refresh_proofs_or_prior_authorization(assessment):
    source, _, invoke, save = assessment
    _, first = invoke()
    _, current = invoke(prior=save(first))
    assert current["assessment_asof"] >= first["assessment_asof"]
    assert current["owner_heads"]["source"]["head_sha256"] == source["head_sha256"]
    assert current["dimensions"]["source_observation"]["evidence"][
        "receipt_first_known_ms_by_wallet"
    ]["W028"]
    assert current["prior_to_current"]["changed_scoped_dimensions"] == []
    assert current["prior_to_current"]["invalidated_conclusions"] == []
    assert current["dimensions"]["guardian_authorization"]["state"] == "UNKNOWN"
    assert current["financially_active"] is False
    assert current["trading_authorized"] is False


def test_one_wallet_missing_complete_position_blocks_only_dependent_scopes(assessment):
    source, _, invoke, _ = assessment
    source["latest_kinds"]["W028"] = "UNAVAILABLE"
    source["checkpoint_ms_by_wallet"].pop("W028")
    source["receipt_first_known_ms_by_wallet"].pop("W028")
    source["complete_position_proof_by_wallet"]["W028"] = False
    _, a = invoke("A")
    _, combo = invoke("Combo2")
    _, b = invoke("B")
    assert a["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert combo["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert b["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"
    assert a["fault_isolation"]["affected_portfolios"] == ["A", "Combo2"]
    assert "B" in a["fault_isolation"]["unaffected_source_portfolios"]
    assert a["fault_isolation"]["shared_account_risk"]["state"] == "UNKNOWN"
    assert (
        a["dimensions"]["source_observation"]["evidence"]["receipt_first_known_ms_by_wallet"][
            "W028"
        ]
        is None
    )
    assert a["economics"]["realized_pnl_usd"] is None
    assert a["order_route"] == "NONE"


def test_missing_first_known_receipt_is_never_flat_or_historical_entry(assessment):
    source, _, invoke, _ = assessment
    source["receipt_first_known_ms_by_wallet"].pop("W028")
    _, a = invoke()
    assert a["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert "W028" in a["dimensions"]["source_observation"]["missing_or_stale_members"]
    assert (
        a["dimensions"]["source_observation"]["evidence"]["receipt_first_known_ms_by_wallet"][
            "W028"
        ]
        is None
    )
    assert a["scope"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert a["economics"]["realized_pnl_usd"] is None


def test_mixed_native_policy_epochs_are_never_globally_verified(assessment):
    source, _, invoke, _ = assessment
    source["policy_epochs_by_wallet"]["W028"] = "9" * 64
    _, a = invoke()
    _, b = invoke("B")
    assert a["generation_consistency"]["state"] == "MIXED"
    assert b["generation_consistency"]["state"] == "MIXED"
    assert "SOURCE_POLICY_EPOCHS_MIXED" in a["generation_consistency"]["reasons"]
    assert a["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert b["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"
    assert a["scope"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert a["financially_active"] is False
    assert a["owner_heads"]["source"]["policy_epochs_by_wallet"]["W028"] == "9" * 64


def test_unrelated_global_source_head_changes_without_invalidating_selected_wallet(assessment):
    source, _, invoke, save = assessment
    _, first = invoke()
    source["head_sha256"] = "9" * 64
    source["source_heads_by_wallet"]["CA-005"] = "8" * 64  # B only
    _, current = invoke(prior=save(first))
    delta = current["prior_to_current"]
    assert delta["global_source_head_changed"] is True
    assert delta["changed_scoped_dimensions"] == []
    assert delta["invalidated_conclusions"] == []
    assert current["dimensions"]["source_observation"]["state"] == "OBSERVE_READY"


def test_wallet_change_invalidates_new_risk_not_historical_paper_or_quotes(assessment):
    source, _, invoke, save = assessment
    _, first = invoke()
    source["head_sha256"] = "9" * 64
    source["source_heads_by_wallet"]["W028"] = "7" * 64
    source["checkpoint_ms_by_wallet"]["W028"] += 1000
    source["receipt_first_known_ms_by_wallet"]["W028"] += 1000
    _, current = invoke(prior=save(first))
    delta = current["prior_to_current"]
    assert "source_observation" in delta["changed_scoped_dimensions"]
    assert "prospective_new_risk" in delta["invalidated_conclusions"]
    assert "paper_finance" not in delta["invalidated_conclusions"]
    assert "independent_executable_quotes" not in delta["invalidated_conclusions"]
    assert delta["changed_wallets"] == ["W028"]


def test_quote_head_change_invalidates_only_current_quotes_and_new_risk(assessment, monkeypatch):
    _, _, invoke, save = assessment
    _, first = invoke()
    monkeypatch.setattr(
        gate,
        "_market_evidence",
        lambda db, src: gate.GateCheck(
            "independent_executable_quotes",
            "PASS",
            "FRESH_INDEPENDENT_L2",
            {"quote_heads_sha256": "7" * 64, "latest_age_ms": 300},
        ),
    )
    _, current = invoke(prior=save(first))
    delta = current["prior_to_current"]
    assert delta["changed_scoped_dimensions"] == ["independent_executable_quotes"]
    assert "prospective_new_risk" in delta["invalidated_conclusions"]
    assert "paper_finance" not in delta["invalidated_conclusions"]
    assert "source_observation" not in delta["invalidated_conclusions"]
    assert current["financially_active"] is False


def test_fresh_display_time_does_not_renew_old_source_head_or_risk(assessment):
    source, paper, _, _ = assessment
    cp = source["latest_checkpoint_ms"]
    ready = project(
        source=source,
        papers={"B": paper},
        verified_finance={"B"},
        qualified_k={"B"},
        release_sha="d" * 40,
        epoch="paper-epoch",
        generated_at=datetime.fromtimestamp((cp + 30_000) / 1000, tz=UTC),
    )
    stale = project(
        source=source,
        papers={"B": paper},
        verified_finance={"B"},
        qualified_k={"B"},
        release_sha="d" * 40,
        epoch="paper-epoch",
        generated_at=datetime.fromtimestamp((cp + 901_000) / 1000, tz=UTC),
    )
    assert ready["portfolios"]["B"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
    assert stale["portfolios"]["B"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert ready["owner_heads"]["source"] == stale["owner_heads"]["source"]
    assert stale["portfolios"]["B"]["shared_account_risk"] == "UNKNOWN"


def test_missing_native_wallet_partition_is_not_equivalent_to_flat_position(assessment):
    source, _, invoke, _ = assessment
    source["latest_kinds"].pop("W028")
    _, result = invoke()
    assert result["dimensions"]["source_observation"]["state"] == "BLOCKED_EVIDENCE"
    assert result["scope"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert result["economics"]["realized_pnl_usd"] is None
    assert result["order_route"] == "NONE"


def test_mismatched_prior_portfolio_or_invalid_path_fails_closed(assessment, tmp_path):
    _, _, invoke, save = assessment
    _, first = invoke()
    prior = save(first)
    code, result = invoke("B", prior=prior)
    assert code == 2
    assert result["error_code"] == "PRIOR_SNAPSHOT_SCOPE_MISMATCH"
    prior.write_text("x" * 1_000_001)
    code, result = invoke(prior=prior)
    assert code == 2
    assert result["error_code"] == "PRIOR_SNAPSHOT_UNAVAILABLE"
    bad = tmp_path / "symlink.json"
    bad.symlink_to(prior)
    code, result = invoke(prior=bad)
    assert code == 2
    assert result["error_code"] == "PRIOR_SNAPSHOT_UNAVAILABLE"


def test_global_projection_blocks_new_source_risk_only_for_wallet_dependents(assessment):
    source, paper, _, _ = assessment
    source["complete_position_proof_by_wallet"]["W028"] = False
    source["latest_kinds"]["W028"] = "UNAVAILABLE"
    result = project(
        source=source,
        papers={"A": paper, "B": paper},
        verified_finance={"A", "B"},
        qualified_k={"A", "B"},
        release_sha="e" * 40,
        epoch="paper-epoch",
        generated_at=datetime.now(UTC),
    )
    assert result["snapshot_coherence"] != "VERIFIED"
    assert result["portfolios"]["A"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert result["portfolios"]["Combo2"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert result["portfolios"]["B"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
    assert result["portfolios"]["B"]["shared_account_risk"] == "UNKNOWN"
    assert result["portfolios"]["B"]["trading_authorized"] is False


@pytest.mark.parametrize("altered_field", ["published_ms", "receipt_clock", "complete_kind"])
def test_native_source_projection_rejects_outcome_payload_tampering(
    monkeypatch, tmp_path, altered_field
):
    """The outcome table alone cannot authenticate original receipt clocks or books."""
    from copytrade_pm.pm_forward_journal import PaperJournal
    from test_checkpoint_journal import register, sample
    from test_checkpoint_source import BOUNDARY

    journal = PaperJournal(tmp_path / "source")
    policy = register(journal)
    result = journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101
    )
    assert result.kind == "BASELINE"
    monkeypatch.setattr(gate, "EXPECTED_WALLETS", frozenset({"fixture-leader"}))
    native = gate._source_facts(journal.path)
    assert native["complete_position_proof_by_wallet"]["fixture-leader"] is True
    assert native["receipt_first_known_ms_by_wallet"]["fixture-leader"] == result.sample.received_ms

    # Retain outcome_id, policy_epoch and scope_generation. Prior validation
    # checked these only, so an altered outcome row looked like a complete book.
    with closing(sqlite3.connect(journal.path)) as db, db:
        row = db.execute(
            "SELECT outcome FROM cwsa_outcomes WHERE checkpoint_ms=?", (BOUNDARY,)
        ).fetchone()
        original = json.loads(row[0])
        if altered_field == "published_ms":
            original["published_ms"] += 1
        elif altered_field == "receipt_clock":
            original["sample"]["received_ms"] += 1
        else:
            original["kind"] = "UNCHANGED"
        db.execute(
            "UPDATE cwsa_outcomes SET outcome=? WHERE checkpoint_ms=?",
            (json.dumps(original), BOUNDARY),
        )
        db.commit()

    with pytest.raises(ValueError, match="CHAPTER2_SOURCE_OUTCOME_DRIFT"):
        gate._source_facts(journal.path)


def test_global_mixed_source_epochs_keep_independent_wallet_scope_eligible(assessment):
    source, paper, _, _ = assessment
    source["policy_epochs_by_wallet"]["W028"] = "9" * 64
    result = project(
        source=source,
        papers={"A": paper, "B": paper},
        verified_finance={"A", "B"},
        qualified_k={"A", "B"},
        release_sha="e" * 40,
        epoch="paper-epoch",
    )
    assert result["snapshot_coherence"] == "MIXED"
    assert result["portfolios"]["A"]["new_risk_source_status"] == "BLOCKED_EVIDENCE"
    assert result["portfolios"]["B"]["new_risk_source_status"] == "SOURCE_SCOPE_READY"
    assert result["trading_authorized"] is False
