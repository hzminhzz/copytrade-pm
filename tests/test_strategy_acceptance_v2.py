"""Q32 Track B v2 acceptance: 16 independent and 8 coinjected failure cases.

Each parameter has a distinct fault setup and asserted expected invariant. These
are engineering fixtures, NOT authenticated live follower-PnL, calibrated alerts,
a deployment receipt or trading authorization.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.dashboard.grafana_projection import create_app
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.strategy_advisory import gate
from copytrade_pm.strategy_finance import inspect_pm03_original, summarize_pm03_economics
from copytrade_pm.strategy_health import (
    Opportunity,
    StrategyAssessment,
    ZERO_SHA,
    seal,
)
from copytrade_pm.strategy_health_projection import project, publish, read
from copytrade_pm.strategy_incidents import classify
from copytrade_pm.strategy_matched_pm04 import compare_candidate
from copytrade_pm.strategy_proof import seal_reference, verify_originals_for_track_c
from copytrade_pm.strategy_source_verify import verify_packet
from copytrade_pm.strategy_windows import compute_windows
from copytrade_pm.v4_source_export import export_signed_events
from test_pm04_compare import _external_event
from test_pm04_shadow import engine
from test_pm_forward_observed_paper import BTC, at, add_quote, add_source
from test_pm_forward_single_shot import new_paper
from test_pm_vike_paper_integration import official_frame, official_observer, price
from test_pydantic_continuity import paper_for
from test_strategy_finance import AS_OF
from test_strategy_health_v2 import (
    ADDRESSES,
    H,
    NOW,
    assessment,
    observer,
    source_event,
)
from test_strategy_incidents import _gap_report
from test_strategy_matched_pm04 import _input
from test_strategy_proof import _original_bundle
from test_strategy_windows import suite


CASES_I = tuple(f"I{i:02d}" for i in range(1, 17))
CASES_C = tuple(f"C{i:02d}" for i in range(1, 9))


def _first_opportunity(report):
    t = NOW - timedelta(minutes=7)
    op = Opportunity(
        opportunity_id="8" * 64,
        source_event_sha256=H,
        source_receipt_sha256=H,
        source_event_at=t,
        first_known_at=t,
        due_at=t + timedelta(seconds=300),
        stream_cursor=3,
        source_epoch="original",
        frozen_k_version="k1",
        frozen_k=D("0.125"),
    )
    return seal(
        StrategyAssessment.model_validate(
            {
                **report.model_dump(),
                "report_sha256": ZERO_SHA,
                "opportunities": (op,),
            }
        )
    )


def _original_open(tmp_path, *, mark="80", max_gross=None):
    spec = _input()
    if max_gross is not None:
        spec["policy"]["max_gross_notional"] = str(max_gross)
    spec["events"][-1] = _external_event("adverse_open", "PM04_TICK", engine(420, mark=mark), 420)
    compare_candidate(spec, tmp_path)
    original = inspect_pm03_original(tmp_path / "runs" / "tbv2-matched-with", as_of=AS_OF)
    return original


def _signed_original(tmp_path, *, with_gap=False):
    journal, src = observer(tmp_path)
    source_event(src, 10, 20)
    if with_gap:
        src.gap(at(22), "SIMULATED_DISCONNECT")
        src.begin(at(24), reason="RECOVER")
        src.observe(official_frame(25, 20), at(26))
    key = Ed25519PrivateKey.generate()
    selected = {"S035": ADDRESSES["S035"]}
    packet = export_signed_events(
        journal.path,
        selected=selected,
        signer=key,
        after={"S035": 2},
    )
    return journal, packet, key, selected


def _assert_no_original_writes(paths, before):
    assert {str(p): p.read_bytes() for p in paths} == before


def _snapshot(paths):
    return {str(p): p.read_bytes() for p in paths}


@pytest.mark.parametrize("case", CASES_I, ids=CASES_I)
def test_independent_q32(case, tmp_path):
    if case == "I01":
        discovery = seal(assessment(selected=False))
        assert discovery.source_observability == "UNKNOWN"
        assert classify(discovery, cycle=None, original_finance=None, quote_stale=True) is None
    elif case == "I02":
        # Actual V4 unchanged source observation 45 days after the first transition.
        from copytrade_pm.pm_forward_source_stream import PersistentAccount

        source = PaperJournal(tmp_path / "unchanged-original")
        start = NOW - timedelta(days=46)
        observer_owner = PersistentAccount(
            journal=source,
            alias="S035",
            address=ADDRESSES["S035"],
            dex_catalog=[None],
            subaccounts=None,
            parent_alias="S035",
            scope_sha="b" * 64,
        )
        observer_owner.begin(start.isoformat())

        def frame(known_at, amount):
            raw = official_frame(1, amount)
            raw["data"]["clearinghouseStates"][0][1]["time"] = int(
                (known_at - timedelta(seconds=1)).timestamp() * 1000
            )
            if amount:
                raw["data"]["clearinghouseStates"][0][1]["assetPositions"][0]["position"][
                    "positionValue"
                ] = str(D(amount) * D("100"))
            return raw

        baseline = observer_owner.observe(
            frame(start + timedelta(seconds=2), 0),
            (start + timedelta(seconds=2)).isoformat(),
        )
        assert baseline["classification"] == "BASELINE"
        changed_at = start + timedelta(seconds=4)
        changed = observer_owner.observe(frame(changed_at, 20), changed_at.isoformat())
        assert changed["classification"] == "OBSERVED_STATE_CHANGE"
        unchanged = observer_owner.observe(
            frame(NOW - timedelta(seconds=1), 20),
            (NOW - timedelta(seconds=1)).isoformat(),
        )
        assert unchanged["classification"] == "UNCHANGED_STATE"
        key = Ed25519PrivateKey.generate()
        packet = export_signed_events(
            source.path,
            selected={"S035": ADDRESSES["S035"]},
            signer=key,
            after={"S035": 0},
        )
        verified = verify_packet(
            packet,
            key.public_key(),
            selected={"S035": ADDRESSES["S035"]},
            original_journal=source.path,
            after={"S035": 0},
            as_of=NOW,
            policy_version="k1",
            frozen_k="0.125",
        )
        assert len(verified["opportunities"]) == 1
        assert datetime.fromisoformat(verified["opportunities"][0]["first_known_at"]) == changed_at
        # The follower's open MTM is independent of transition frequency.
        original = _original_open(tmp_path / "finance")
        finance = summarize_pm03_economics(original, as_of=AS_OF, pod_alias="W028")
        assert finance.pod_marked_net_usd < 0
        assert finance.pod_open_gross_usd > 0
    elif case == "I03":
        journal, packet, signer, selected = _signed_original(tmp_path)
        original = journal.path.read_bytes()
        kwargs = dict(
            selected=selected,
            original_journal=journal.path,
            after={"S035": 2},
            as_of=NOW,
            policy_version="k1",
            frozen_k="0.125",
        )
        one = verify_packet(packet, signer.public_key(), **kwargs)
        two = verify_packet(packet, signer.public_key(), **kwargs)
        assert one["opportunities"] == two["opportunities"]
        assert len(one["opportunities"]) == 1
        assert journal.path.read_bytes() == original
    elif case == "I04":
        report, points = suite(10, complete=8)
        same_source = points[1].model_copy(
            update={"causal_cluster_sha256": points[0].causal_cluster_sha256}
        )
        window = compute_windows(report, evidence=(points[0], same_source, *points[2:]))[0]
        assert window.independent_clusters == 6
        assert window.effective_opportunities <= 6
    elif case == "I05":
        original = _original_open(tmp_path)
        finance = summarize_pm03_economics(original, as_of=AS_OF, pod_alias="W028")
        assert finance.pod_open_gross_usd > 0
        assert finance.pod_marked_net_usd < 0
        assert finance.unrealized_pnl_usd < 0
        assert original["account"]["pm_quantities"]["W028"]
    elif case == "I06":
        tape = PaperJournal(tmp_path / "tape")
        add_quote(tape, 10)
        paper = new_paper(tmp_path, tape)
        add_source(tape, 1, 12, {BTC.key: "20"})
        assert paper.step(at(14))["execution_intents"]["S035"]["status"] == "PENDING_5M"
        expired = paper.step(at(344))
        assert expired["execution_intents"]["S035"]["status"] == "EXPIRED_NO_TRADE"
        assert expired["positions"] == {}
        assert all(row["event"]["kind"] != "PM04_PAPER_EXECUTE" for row in paper.run.ledger.read())
    elif case == "I07":
        source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
        official = official_observer(source)
        paper = paper_for(tmp_path, source, prices)
        official.observe(official_frame(12, 20), at(13))
        before = paper.step(at(14))["execution_intents"]["S035"]
        official.gap(at(312), "T0_PLUS_299_SOURCE_GAP")
        price(prices, 312)
        after = paper.step(at(313))["execution_intents"]["S035"]
        assert before["due_at"] == after["due_at"] == at(313)
        assert after["status"] == "CANCELED_SOURCE_GAP"
        assert not paper.run.account.quantities
    elif case == "I08":
        source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
        official = official_observer(source)
        paper = paper_for(tmp_path, source, prices)
        official.observe(official_frame(12, 20), at(13))
        old = paper.step(at(14))["execution_intents"]["S035"]
        official.gap(at(100), "SOCKET_LOSS")
        assert paper.step(at(101))["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
        official.begin(at(120), reason="RECONNECT")
        assert official.observe(official_frame(121, 20), at(122))["classification"] == "BASELINE"
        outcome = paper.step(at(123))
        assert outcome["execution_intents"]["S035"]["intent_id"] == old["intent_id"]
        assert outcome["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
        assert not any(r["event"]["kind"] == "PM04_PAPER_EXECUTE" for r in paper.run.ledger.read())
    elif case == "I09":
        original = _original_open(tmp_path)
        finance = summarize_pm03_economics(original, as_of=AS_OF, pod_alias="W028")
        assert "LAST_MARK_STALE_AT_ASOF" in finance.reasons
        assert not finance.net_comparable
    elif case == "I10":
        report, points = suite(10, complete=8)
        invalid = points[0].model_copy(update={"funding_complete": False})
        window = compute_windows(report, evidence=(invalid, *points[1:]))[0]
        assert window.missing_critical_finance >= 1
        assert gate(window, persistent=False)[0] == "INSUFFICIENT_EVIDENCE"
    elif case == "I11":
        # Unresolved held exit after an original PM03 HALT remains inventoried.
        from copytrade_pm.pm03_memory import Event
        from copytrade_pm.pm03_account import RiskState, digest
        from copytrade_pm.pm_source_contracts import SourceObservationRejected

        source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
        official = official_observer(source)
        paper = paper_for(tmp_path, source, prices)
        official.observe(official_frame(12, 20), at(13))
        paper.step(at(14))
        price(prices, 312)
        opened = paper.step(at(313))
        assert opened["positions"]
        original_inventory = dict(paper.run.account.quantities)
        paper.run.record(
            Event(
                "owner_halt",
                at(314),
                at(314),
                at(314),
                at(314),
                "HALT",
                {
                    "run_id": "continuity",
                    "rulebook_sha": paper.run.account.rulebook.sha,
                    "input": {"reason": "INDEPENDENT_FINANCIAL_HALT"},
                },
                digest("halt"),
            )
        )
        malformed = official_frame(315, 0)
        malformed["data"]["clearinghouseStates"][0][1]["time"] = False
        with pytest.raises(SourceObservationRejected):
            official.observe(malformed, at(316))
        paper.step(at(601))
        assert paper.run.account.quantities == original_inventory
        assert paper.run.account.risk == RiskState.HALT
        verified = inspect_pm03_original(paper.run.ledger.path, as_of=AS_OF)
        assert verified["account"]["risk"] == "HALT"
        assert verified["account"]["halt_reason"] == "INDEPENDENT_FINANCIAL_HALT"
        assert verified["account"]["quantities"]
        assert not summarize_pm03_economics(verified, as_of=AS_OF).net_comparable
    elif case == "I12":
        comparison = compare_candidate(_input(), tmp_path)
        a = comparison["comparison"]["with"]
        b = comparison["comparison"]["without"]
        assert a["ledger_head"] != b["ledger_head"]
        assert a["pm04"]["pod_stats"] != b["pm04"]["pod_stats"]
        assert D(comparison["marginal_pnl_usd"]) == (
            D(a["account_pnl_usd"]) - D(b["account_pnl_usd"])
        )
        assert comparison["risk_and_netting_recomputed"]
    elif case == "I13":
        journal, packet, signer, selected = _signed_original(tmp_path)
        packet["events"]["S035"][0]["proof"]["payload"]["classification"] = "HISTORICAL_FILL"
        with pytest.raises(ValueError):
            verify_packet(
                packet,
                signer.public_key(),
                selected=selected,
                original_journal=journal.path,
                after={"S035": 2},
                as_of=NOW,
                policy_version="k1",
                frozen_k="0.125",
            )
    elif case == "I14":
        original = _first_opportunity(assessment())
        op = original.opportunities[0]
        assert op.due_at == op.first_known_at + timedelta(seconds=300)
        changed = op.model_copy(update={"frozen_k_version": "new-k"})
        with pytest.raises(ValueError, match="VERSION"):
            StrategyAssessment.model_validate(
                {
                    **original.model_dump(),
                    "report_sha256": ZERO_SHA,
                    "opportunities": (changed,),
                }
            )
    elif case == "I15":
        report, points = suite(10, complete=8)
        early = compute_windows(report, evidence=points)[0]
        assert early.effective_opportunities == D(8)
        assert early.comparable_coverage == D("0.8")
        assert gate(early, persistent=False)[0] == "EARLY_WARNING"
        assert report.advisory.status == "INSUFFICIENT_EVIDENCE"
        assert not report.scientifically_qualified
    elif case == "I16":
        TestClient = pytest.importorskip("starlette.testclient").TestClient
        now = datetime.now(UTC)
        base = assessment().model_copy(update={"as_of": now, "created_at": now})
        projection = project(seal(base), published_at=now)
        publish(tmp_path, projection)
        assert read(tmp_path, now=now)["schema"] == "strategy_health_grafana_v1"
        app = create_app(token="z" * 40, snapshot_dir=tmp_path, allowed_host="localhost")
        with TestClient(app, base_url="http://localhost") as client:
            path = "/v1/strategy-health"
            assert client.get(path).status_code == 403
            hdr = {"authorization": "Bearer " + "z" * 40}
            assert client.get(path, headers=hdr).status_code == 200
            assert client.post(path, headers=hdr).status_code == 405
            assert client.get("/v1/wallet-health", headers=hdr).status_code == 503
    else:
        raise AssertionError(f"UNREGISTERED_INDEPENDENT_Q32_CASE:{case}")


@pytest.mark.parametrize("case", CASES_C, ids=CASES_C)
def test_combined_q32(case, tmp_path):
    if case == "C01":
        # Selected source GAP + stale quote + genuine open PM03 follower inventory.
        original = _original_open(tmp_path / "finance")
        report = _gap_report()
        report = seal(
            StrategyAssessment.model_validate(
                {
                    **report.model_dump(),
                    "report_sha256": ZERO_SHA,
                    "strategy": report.strategy.model_copy(update={"source_alias": "W028"}),
                }
            )
        )
        incident = classify(report, cycle=None, original_finance=original, quote_stale=True)
        assert incident.cause == "SOURCE_GAP"
        assert incident.priority == "CRITICAL_RISK_EXPOSED"
        assert incident.risk_at_finding == "OPEN"
        before = original["account"]["quantities"].copy()
        assert original["account"]["quantities"] == before
        assert not incident.trading_authorized
        assert incident.alert_delivery == "PENDING_UNVERIFIED_CADENCE"
    elif case == "C02":
        # Duplicate transition + reconnect baseline + original pending T300.
        source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
        official = official_observer(source)
        paper = paper_for(tmp_path, source, prices)
        official.observe(official_frame(12, 20), at(13))
        pending = paper.step(at(14))["execution_intents"]["S035"]
        official.observe(official_frame(12, 20), at(20))
        official.gap(at(100), "REPLAY_AND_DISCONNECT")
        paper.step(at(101))
        official.begin(at(120))
        official.observe(official_frame(121, 20), at(122))
        paper.step(at(123))
        after = paper.step(at(313))["execution_intents"]["S035"]
        assert after["intent_id"] == pending["intent_id"]
        assert after["due_at"] == pending["due_at"]
        assert after["status"] == "CANCELED_SOURCE_GAP"
        assert paper.run.account.quantities == {}
    elif case == "C03":
        # Forged source T0 + internally valid private reference SHA + Track C import.
        report, ref, params, _market = _original_bundle(tmp_path)
        packet = json.loads(json.dumps(params["signed_packet"]))
        packet["events"]["S035"][0]["proof"]["payload"]["first_known_ms"] += 1000
        forged = seal_reference(
            ref.model_copy(
                update={
                    "ref_sha256": ZERO_SHA,
                    "original_source_head_sha256": "a" * 64,
                }
            )
        )
        assert forged.ref_sha256 != ref.ref_sha256
        with pytest.raises(ValueError):
            verify_originals_for_track_c(forged, report, **{**params, "signed_packet": packet})
    elif case == "C04":
        # Negative open MTM + >=8 independent first-known + one missing funding proof.
        report, points = suite(10, complete=8, amount=D("-0.10"))
        bad = points[0].model_copy(update={"funding_complete": False})
        w = compute_windows(report, evidence=(bad, *points[1:]))[0]
        assert w.independent_clusters == 7
        assert w.missing_critical_finance == 1
        assert gate(w, persistent=False)[0] == "INSUFFICIENT_EVIDENCE"
        original = _original_open(tmp_path / "finance")
        assert (
            summarize_pm03_economics(original, as_of=AS_OF, pod_alias="W028").pod_marked_net_usd < 0
        )
    elif case == "C05":
        # Supported 7d adverse diagnostic + 30d low-N + favorable 90d context.
        report, points = suite(10, complete=8, amount=D("0.05"))
        windows = compute_windows(report, evidence=points)
        seven = windows[0].model_copy(update={"matched_adverse_r": D("0.30")})
        thirty = windows[1]
        ninety = windows[2].model_copy(update={"matched_adverse_r": D("-2")})
        assert gate(seven, persistent=False)[0] == "EARLY_WARNING"
        assert gate(thirty, persistent=True)[0] == "INSUFFICIENT_EVIDENCE"
        assert ninety.matched_adverse_r < 0
        assert report.advisory.last_warning_at is None
    elif case == "C06":
        # k rollover + overlapping pod clusters + reused historical outcome.
        report, points = suite(10, complete=8)
        rollover = report.opportunities[0].model_copy(update={"frozen_k_version": "future-k"})
        with pytest.raises(ValueError):
            StrategyAssessment.model_validate(
                {
                    **report.model_dump(),
                    "report_sha256": ZERO_SHA,
                    "opportunities": (rollover, *report.opportunities[1:]),
                }
            )
        overlapping = points[1].model_copy(
            update={"causal_cluster_sha256": points[0].causal_cluster_sha256}
        )
        window = compute_windows(report, evidence=(points[0], overlapping, *points[2:]))[0]
        assert window.independent_clusters == 6
        with pytest.raises(ValueError, match="WINDOW_OPPORTUNITY_ID"):
            compute_windows(report, evidence=(points[0], points[0], *points[2:]))
    elif case == "C07":
        # Shared-account candidate exclusion + concurrent risk-latched pod + netting.
        spec = _input()
        spec["events"][-1] = _external_event(
            "loss-with-risk-latch", "PM04_TICK", engine(420, mark="60"), 420
        )
        # Same independent PM03 HALT in both counterfactuals, after pod stress.
        spec["events"].append(
            {
                "event_id": "independent-account-halt",
                "kind": "HALT",
                "source_event_at": at(430),
                "first_known_at": at(430),
                "decision_at": at(430),
                "hypothetical_fill_at": at(430),
                "source_sha": H,
                "input": {"reason": "ORIGINAL_ACCOUNT_GLOBAL_HALT"},
            }
        )
        matched = compare_candidate(spec, tmp_path)
        with_account = matched["comparison"]["with"]
        without = matched["comparison"]["without"]
        assert with_account["pm04"]["pod_stats"]["W028"]["state"] == "SUSPENDED"
        assert without["pm04"]["pod_stats"]["W028"]["state"] != "SUSPENDED"
        assert with_account["ledger_head"] != without["ledger_head"]
        assert with_account["risk"] == without["risk"] == "HALT"
        assert (
            with_account["halt_reason"] == without["halt_reason"] == "ORIGINAL_ACCOUNT_GLOBAL_HALT"
        )
        assert D(with_account["account_pnl_usd"]) < D(without["account_pnl_usd"])
        assert not matched["authentic_prospective_marginal_value"]
    elif case == "C08":
        TestClient = pytest.importorskip("starlette.testclient").TestClient
        # Original v1 wallet dashboard + stale v2 + open-risk incident.
        original = _original_open(tmp_path / "finance")
        report = _gap_report()
        report = seal(
            StrategyAssessment.model_validate(
                {
                    **report.model_dump(),
                    "report_sha256": ZERO_SHA,
                    "strategy": report.strategy.model_copy(update={"source_alias": "W028"}),
                }
            )
        )
        incident = classify(report, cycle=None, original_finance=original, quote_stale=True)
        enriched = seal(
            StrategyAssessment.model_validate(
                {
                    **report.model_dump(),
                    "report_sha256": ZERO_SHA,
                    "operational_incidents": (incident,),
                }
            )
        )
        assert incident.priority == "CRITICAL_RISK_EXPOSED"
        publish(tmp_path, project(enriched, published_at=NOW))
        with pytest.raises(ValueError, match="STALE"):
            read(tmp_path, now=NOW + timedelta(days=1))
        app = create_app(token="z" * 40, snapshot_dir=tmp_path, allowed_host="localhost")
        with TestClient(app, base_url="http://localhost") as client:
            hdr = {"authorization": "Bearer " + "z" * 40}
            assert client.get("/v1/strategy-health", headers=hdr).status_code == 503
            assert client.get("/v1/wallet-health", headers=hdr).status_code == 503
            assert client.post("/v1/strategy-health", headers=hdr).status_code == 405
        assert original["account"]["pm_quantities"]["W028"]
        assert not incident.trading_authorized
    else:
        raise AssertionError(f"UNREGISTERED_COMBINED_Q32_CASE:{case}")
