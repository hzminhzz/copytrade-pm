"""Costed comparisons replay original owners; missing evidence never becomes alpha."""

from contextlib import closing
from decimal import Decimal as D
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm import pm_checkpoint_economics as economics
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_checkpoint_paper import setup_paper, checkpoint, consume, quote, BOUNDARY, GRID
from test_pm_forward_observed_paper import add_quote, add_source, at, registry, RAW_MARKET, BTC


def new_run(root):
    j, sp, mandate, policy = setup_paper(root)
    consume(j, mandate, checkpoint(j, sp, 0), policy, BOUNDARY + 102)
    outcome = checkpoint(j, sp, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(j, now)
    consume(j, mandate, outcome, policy, now + 2)
    return j


def old_run(root):
    root.mkdir(mode=0o700)
    source = PaperJournal(root / "source")
    add_quote(source, 10)
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=root / "paper",
        run_id="old-first-known",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        registry_db=registry(root / "registry.sqlite"),
        started_at=at(0),
    )
    add_source(source, 1, 12, {BTC.key: "20"}, leader_marks={BTC.key: "120"})
    paper.step(at(14))
    add_quote(source, 313)
    paper.step(at(314))
    return paper


def test_checkpoint_readonly_replay_preserves_original_finance_and_files(tmp_path):
    journal = new_run(tmp_path)
    before = journal.path.read_bytes()
    trace = economics.read_checkpoint(journal.path, "p1")
    assert trace["final_account"] == journal.restore("p1")["account"]
    assert trace["timing_policy"] == "CWSA_UTC_5M_V3"
    assert D(trace["states"][-1]["account"]["costs"]) > 0
    assert trace["opportunities"]["COMMITTED_ONCE"] == 1
    assert trace["original_evidence_shas"]
    assert journal.path.read_bytes() == before


def test_legacy_readonly_replay_keeps_original_t0_plus_300(tmp_path):
    paper = old_run(tmp_path / "old")
    files = {p.name: p.read_bytes() for p in paper.run.ledger.path.iterdir() if p.is_file()}
    trace = economics.read_legacy(paper.run.ledger.path)
    assert trace["final_account"] == paper.run.account.snapshot()
    assert trace["timing_policy"] == "FIRST_KNOWN_T0_300_V1"
    assert D(trace["states"][-1]["account"]["costs"]) > 0
    executions = [r for r in trace["events"] if r["kind"] == "PM04_PAPER_EXECUTE"]
    assert executions
    assert executions[0]["decision_ms"] >= executions[0]["first_known_ms"] + 300000
    assert {p.name: p.read_bytes() for p in paper.run.ledger.path.iterdir() if p.is_file()} == files


def test_research_rejects_forged_account_post_state(tmp_path):
    journal = new_run(tmp_path)
    with closing(sqlite3.connect(journal.path)) as db, db:
        db.execute("UPDATE events SET post_sha=? WHERE seq=2", ("f" * 64,))
    with pytest.raises(ValueError, match="DIVERGENCE"):
        economics.read_checkpoint(journal.path, "p1")


def test_missing_new_prospective_evidence_is_a_reported_blocker_not_zero_pnl(tmp_path):
    specification = {
        "schema": "cwsa_matched_economics_spec_v1",
        "research_revision": "a" * 40,
        "window": {"start_ms": BOUNDARY, "end_ms": BOUNDARY + 600000, "step_ms": 300000},
        "source_roster": [
            {"source_id": "fixture-leader", "account_sha": "b" * 64, "dexes": ["default"]}
        ],
        "portfolios": [
            {
                "portfolio_id": "FIXTURE",
                "frozen_k": {"fixture-leader": "0.025"},
                "legacy": None,
                "checkpoint": None,
            }
        ],
        "reference_data": [],
        "reference_quote_max_age_ms": 2000,
        "uncertainty": {"block_intervals": 2, "replicates": 100, "seed": 313, "confidence": "0.95"},
        "extra_cost_bps": ["0", "1", "5"],
        "criterion": None,
    }
    report = economics.evaluate(specification, revision="a" * 40)
    assert report["scientifically_qualified"] is False
    assert report["trading_authorized"] is False
    assert report["portfolios"]["FIXTURE"]["matched_net_pnl"] is None
    assert "MATCHED_POLICY_LEDGER_MISSING" in report["blockers"]
    assert report["roster_sha"] == digest(specification["source_roster"])
    assert report["report_sha"] == digest({k: v for k, v in report.items() if k != "report_sha"})


def test_pairing_and_uncertainty_never_bridge_missing_intervals():
    old = {0: D("100"), 300000: D("99"), 900000: D("101"), 1200000: D("98")}
    new = {0: D("100"), 300000: D("100"), 900000: D("102"), 1200000: D("100")}
    result = economics.compare_curves(
        old,
        new,
        start_ms=0,
        end_ms=1200000,
        step_ms=300000,
        uncertainty={"block_intervals": 2, "replicates": 100, "seed": 313, "confidence": "0.95"},
    )
    assert result["matched_intervals"] == 2
    assert result["missing_intervals"] == [300000, 600000]
    assert D(result["matched_net_pnl"]["legacy"]) == D("-4")
    assert D(result["matched_net_pnl"]["checkpoint"]) == D("-2")
    assert result["full_window_net_pnl"] is None
    assert result["uncertainty"]["status"] == "INSUFFICIENT_CONTIGUOUS_BLOCKS"


def matched_pair(root, monkeypatch):
    """Both actual policy owners, one frozen synthetic parent and explicit quote tape."""
    from dataclasses import replace
    from datetime import UTC, datetime
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import test_pm_forward_observed_paper as legacy_fixture
    from copytrade_pm.pm_checkpoint_journal import CwsaPolicy
    from copytrade_pm.pm_checkpoint_source import collect_checkpoint
    from copytrade_pm.pm_forward_observed_paper import PaperPortfolioSpec
    from copytrade_pm.pm_v4_sixteen_scenarios import MANIFEST_SHA256
    from copytrade_pm.production_manifest import sign
    from test_checkpoint_source import scope, limits
    from test_checkpoint_paper import policy as paper_policy, stamp
    from test_copy_mandates import mandate as make_mandate
    from test_pm_forward_journal import manifest
    from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market

    monkeypatch.setattr(legacy_fixture, "T", datetime.fromtimestamp(BOUNDARY / 1000, UTC))
    address = legacy_fixture.ADDRESSES["S035"]
    account_sha = sha256(address.encode()).hexdigest()
    source = PaperJournal(root / "legacy-source")
    quote(source, BOUNDARY + 10000)
    old = ObservedP1Paper(
        source_db=source.path,
        state_root=root / "legacy-paper",
        run_id="matched-old",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        started_at=at(0),
        portfolio_id="FIXTURE",
        study_profile=PaperPortfolioSpec(
            "FIXTURE", ("S035",), ("S035",), ("0.025",), ("200",), "SYNTHETIC_TEST_ONLY", "200"
        ),
        study_seal={
            "source_manifest_sha256": MANIFEST_SHA256,
            "portfolio_id": "FIXTURE",
            "selection_kind": "UNSIGNED_PROSPECTIVE_PAPER_SCENARIO_NOT_SQLITE_SELECTION",
        },
        study_accounts={"S035": account_sha},
    )
    add_source(source, 1, 12, {BTC.key: "3"}, leader_marks={BTC.key: "10000"})
    old.step(at(14))
    quote(source, BOUNDARY + 313000)
    old.step(at(314))
    quote(source, BOUNDARY + 1204000)
    old.step(at(1205))

    new = PaperJournal(root / "checkpoint")
    sp = CwsaPolicy(limits=limits(), measurement_sha="c" * 64)
    sc = scope().model_copy(
        update={"source_id": "S035", "account_sha": account_sha, "dexes": ("default",)}
    )
    new.register_checkpoint_source(sc, sp, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1)
    p = paper_policy()
    mf = manifest("p1", "fixture-account")
    rules = replace(mf.rulebook, permitted=(BTC,), confirmed=True)
    new.register(replace(mf, rulebook=rules, policy_sha=digest(p), started_at=stamp(BOUNDARY)))
    m = make_mandate().model_copy(
        update={
            "source_id": "S035",
            "source_account_sha": account_sha,
            "policy_epoch": sp.epoch,
            "risk_policy_sha": digest(p),
            "rulebook_sha": rules.sha,
        }
    )
    key = Ed25519PrivateKey.generate()
    new.activate_copy_mandate(
        sign(m.model_dump(mode="json"), key, "copy-mandate-v1"),
        key.public_key(),
        account_id=m.account_id,
        at_ms=BOUNDARY - 1,
    )
    for index, quantity in enumerate(("2", "3", "3", "3", "3")):
        boundary = BOUNDARY + index * GRID

        def native(request):
            body = (
                [None]
                if request["type"] == "perpDexs"
                else {
                    "time": boundary,
                    "assetPositions": [
                        {
                            "position": {
                                "coin": "BTC",
                                "szi": quantity,
                                "positionValue": str(D(quantity) * 10000),
                            }
                        }
                    ],
                }
            )
            raw = json.dumps(body).encode()
            return body, raw, sha256(raw).hexdigest()

        sample = collect_checkpoint(
            sc,
            address,
            checkpoint_ms=boundary,
            limits=limits(),
            evidence_root=new.root,
            info=native,
            now_ms=lambda: boundary + 100,
        )
        outcome = new.append_checkpoint_sample(sp.epoch, sample, boundary + 101)
        quote(new, boundary + 102)
        consume(new, m, outcome, p, boundary + 104)

    old_trace, new_trace = (
        economics.read_legacy(old.run.ledger.path),
        economics.read_checkpoint(new.path, "p1"),
    )
    window = {"start_ms": BOUNDARY + 104, "end_ms": BOUNDARY + 4 * GRID + 104, "step_ms": GRID}
    native_market = parse_ccxt_market(
        RAW_MARKET, first_known_at=stamp(BOUNDARY - 1000), expected=BTC
    )
    references = []
    for index in range(5):
        known = window["start_ms"] + index * GRID
        references.append(
            parse_ccxt_book(
                native_market,
                {
                    "symbol": RAW_MARKET["symbol"],
                    "timestamp": known - 1,
                    "bids": [[9999 + index, 200]],
                    "asks": [[10001 + index, 200]],
                },
                first_known_at=stamp(known),
                max_age_seconds=2,
            ).payload()
        )
    quote_path = root / "quotes.json"
    quote_bytes = json.dumps({"schema": "cwsa_economics_quotes_v1", "quotes": references}).encode()
    quote_path.write_bytes(quote_bytes)
    spec = {
        "schema": "cwsa_matched_economics_spec_v1",
        "research_revision": "a" * 40,
        "window": window,
        "source_roster": [{"source_id": "S035", "account_sha": account_sha, "dexes": ["default"]}],
        "portfolios": [
            {
                "portfolio_id": "FIXTURE",
                "frozen_k": {"S035": "0.025"},
                "legacy": {
                    "path": str(old.run.ledger.path),
                    "head_sha": old_trace["head_sha"],
                    "manifest_sha": old_trace["manifest_sha"],
                    "source_journal": str(source.path),
                    "source_prefixes": {
                        "S035": {
                            "sequence": 1,
                            "head_sha": source.source_status("S035")["head_sha"],
                        }
                    },
                },
                "checkpoint": {
                    "path": str(new.path),
                    "run_id": "p1",
                    "head_sha": new_trace["head_sha"],
                    "manifest_sha": new_trace["manifest_sha"],
                },
            }
        ],
        "reference_data": [
            {
                "path": str(quote_path),
                "sha256": sha256(quote_bytes).hexdigest(),
                "role": "FOLLOWER_L2_QUOTES",
            }
        ],
        "reference_quote_max_age_ms": 2000,
        "uncertainty": {"block_intervals": 1, "replicates": 100, "seed": 313, "confidence": "0.95"},
        "extra_cost_bps": ["0", "1", "5"],
        "criterion": None,
    }
    return spec


def test_matched_original_policy_replays_include_costs_uncertainty_and_no_promotion(
    tmp_path, monkeypatch
):
    spec = matched_pair(tmp_path, monkeypatch)
    report = economics.evaluate(spec, revision="a" * 40)
    result = report["portfolios"]["FIXTURE"]
    assert result["matched_intervals"] == 4
    assert result["full_window_net_pnl"] is not None
    assert result["uncertainty"]["status"] == "CONDITIONAL_PAIRED_BLOCK_BOOTSTRAP"
    assert all(row["modeled_fill_count"] > 0 for row in result["variants"].values())
    assert (
        result["variants"]["legacy"]["source_accounts"]
        == result["variants"]["checkpoint"]["source_accounts"]
    )
    assert D(result["cost_sensitivities"][-1]["net_pnl"]["checkpoint"]) < D(
        result["full_window_net_pnl"]["checkpoint"]
    )
    assert report["verdict"] == "NOT_QUALIFIED"
    assert report["scientifically_qualified"] is False
    assert "LEGACY_NATIVE_ORIGINALS_NOT_REATTESTED" in result["blockers"]


@pytest.mark.parametrize("fault", ["account", "k", "pin", "quote_clock", "scope_missing"])
def test_matched_research_excludes_wrong_cohort_and_unavailable_evidence(
    tmp_path, monkeypatch, fault
):
    spec = matched_pair(tmp_path, monkeypatch)
    if fault == "account":
        spec["source_roster"][0]["account_sha"] = "f" * 64
    elif fault == "k":
        spec["portfolios"][0]["frozen_k"]["S035"] = "0.03"
    elif fault == "pin":
        spec["portfolios"][0]["legacy"]["head_sha"] = "f" * 64
    elif fault == "quote_clock":
        spec["reference_quote_max_age_ms"] = 0
        with pytest.raises(ValueError, match="CLOCK_POLICY"):
            economics.evaluate(spec, revision="a" * 40)
        return
    else:
        del spec["portfolios"][0]["legacy"]["source_journal"]
    result = economics.evaluate(spec, revision="a" * 40)["portfolios"]["FIXTURE"]
    assert result["matched_net_pnl"] is None
    assert result["blockers"]


def test_valuation_never_reads_a_future_quote_and_does_not_bridge_the_gap(tmp_path, monkeypatch):
    from pathlib import Path

    spec = matched_pair(tmp_path, monkeypatch)
    item = spec["reference_data"][0]
    path = Path(item["path"])
    body = json.loads(path.read_bytes())
    del body["quotes"][2]
    payload = json.dumps(body).encode()
    path.write_bytes(payload)
    item["sha256"] = sha256(payload).hexdigest()
    result = economics.evaluate(spec, revision="a" * 40)["portfolios"]["FIXTURE"]
    assert result["matched_intervals"] == 2
    assert result["full_window_net_pnl"] is None
    assert len(result["missing_intervals"]) == 2


def test_signed_numeric_criterion_is_predeclared_evidence_bound_and_cannot_promote(
    tmp_path, monkeypatch
):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from copytrade_pm.production_manifest import sign

    spec = matched_pair(tmp_path, monkeypatch)
    evidence = tmp_path / "criterion-derivation.json"
    raw = b'{"fixture":"synthetic criterion derivation; no scientific evidence"}'
    evidence.write_bytes(raw)
    evidence_sha = sha256(raw).hexdigest()
    spec["reference_data"].append(
        {"path": str(evidence), "sha256": evidence_sha, "role": "ECONOMIC_CRITERION_DERIVATION"}
    )
    key = Ed25519PrivateKey.generate()
    body = {
        "schema": "cwsa_economic_criterion_v1",
        "study_design_sha": economics.study_design_sha(spec),
        "declared_ms": spec["window"]["start_ms"] - 1,
        "derivation_evidence_sha": evidence_sha,
        "minimum_matched_intervals": 4,
        "minimum_delta_pnl": "-100000",
        "maximum_checkpoint_drawdown": "100000",
        "require_positive_lower_bound": False,
    }
    spec["criterion"] = sign(body, key, "cwsa-economics-reviewer-v1")
    report = economics.evaluate(spec, revision="a" * 40, reviewer=key.public_key())
    assert (
        report["criterion"]["portfolio_results"]["FIXTURE"] == "PASS_MODELED_NUMERIC_CRITERION_ONLY"
    )
    assert report["verdict"] == "NOT_QUALIFIED"
    spec["portfolios"][0]["legacy"]["head_sha"] = "f" * 64
    # Ledger pins are acquired after the prospective window; they are not the predeclared design.
    assert economics.study_design_sha(spec) == body["study_design_sha"]
    spec["criterion"] = sign(
        dict(body, declared_ms=spec["window"]["start_ms"]), key, "cwsa-economics-reviewer-v1"
    )
    with pytest.raises(ValueError, match="NOT_PREDECLARED"):
        economics.evaluate(spec, revision="a" * 40, reviewer=key.public_key())
