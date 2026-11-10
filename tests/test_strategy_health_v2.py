"""Track B v2 first-frontier contract/field-failure tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.strategy_health import (
    Campaign,
    FollowerEconomics,
    Opportunity,
    StrategyAssessment,
    StrategyScope,
    canonical_report,
    publish,
    read,
    seal,
)
from copytrade_pm.strategy_source_verify import verify_packet
from copytrade_pm.strategy_census import assess_verified_packet
from copytrade_pm.v4_source_export import export_signed_events
from test_v4_source_export import ADDRESSES, at, observer, source_event


H = "a" * 64
NOW = datetime(2026, 11, 10, 8, tzinfo=UTC)


def campaign():
    return Campaign(
        campaign_id="campaign-1",
        trial_family_sha256=H,
        frozen_at=NOW - timedelta(days=2),
        trial_count=3,
        rejected_trials=2,
        weekly_look_ids=("week-1",),
    )


def scope(version="k1", selected=True):
    return StrategyScope(
        tier="SELECTED" if selected else "DISCOVERY",
        source_alias="S035",
        source_account_sha256=H,
        registry_asof_sha256=H,
        **(
            {
                "selected_portfolio": "P1",
                "selection_seal_sha256": H,
                "dex_census_sha256": H,
                "selection_known_at": NOW - timedelta(days=1),
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "k_version": version,
                "k_policy_sha256": H,
                "frozen_k": Decimal("0.125"),
            }
            if selected
            else {}
        ),
    )


def assessment(version="k1", selected=True, **values):
    return StrategyAssessment(
        created_at=NOW,
        as_of=NOW,
        strategy=scope(version, selected),
        campaign=campaign(),
        **values,
    )


def test_private_report_deterministic_separate_versions(tmp_path):
    root = tmp_path / "reports"
    root.mkdir(mode=0o700)
    one, two = seal(assessment()), seal(assessment("k2"))
    assert one.report_sha256 != two.report_sha256
    assert canonical_report(one) == canonical_report(seal(assessment()))
    a, b = root / "one.json", root / "two.json"
    publish(one, a)
    publish(two, b)
    assert read(a) == one
    assert read(b) == two
    assert (a.stat().st_mode & 0o777) == 0o600
    assert one.scientifically_qualified is False
    assert one.trading_authorized is False
    assert one.source_finance_authenticated is False
    assert one.follower_economics.net_comparable is False
    with pytest.raises(ValueError, match="EXISTS"):
        publish(one, a)


def test_discovery_only_unknown_and_no_future_economics():
    report = seal(assessment(selected=False))
    assert not report.opportunities
    assert report.source_observability == "UNKNOWN"
    assert report.portfolio_contribution.status == "UNKNOWN"
    with pytest.raises(ValueError, match="DISCOVERY"):
        assessment(selected=False, source_observability="VERIFIED_CONTINUOUS")
    with pytest.raises(ValueError, match="DISCOVERY"):
        assessment(
            selected=False,
            follower_economics=FollowerEconomics(evidence_class="RESEARCH_SYNTHETIC"),
        )


def test_invalid_input_mutation_hash_and_nan_fail_closed(tmp_path):
    report = seal(assessment())
    raw = json.loads(canonical_report(report))
    for key, value in (
        ("unexpected", "hi"),
        ("policy_version", "unapproved"),
        ("created_at", "2035-01-01T00:00:00Z"),
    ):
        tamper = dict(raw)
        tamper[key] = value
        with pytest.raises((ValueError, TypeError)):
            StrategyAssessment.model_validate(tamper)
    with pytest.raises(ValueError, match="finite"):
        scope_invalid = scope().model_copy(update={"frozen_k": Decimal("NaN")})
        StrategyScope.model_validate(scope_invalid.model_dump())
    out = tmp_path / "reports"
    out.mkdir(mode=0o700)
    p = out / "one.json"
    publish(report, p)
    corrupt = dict(raw)
    corrupt["campaign"]["campaign_id"] = "forged"
    p.write_text(json.dumps(corrupt))
    with pytest.raises(ValueError, match="REPORT|NONCANONICAL"):
        read(p)
    os.chmod(p, 0o644)
    with pytest.raises(ValueError, match="PRIVATE"):
        read(p)


def test_opportunity_prohibits_rebased_t0_and_version():
    first = NOW - timedelta(minutes=7)
    kwargs = dict(
        opportunity_id=H,
        source_event_sha256=H,
        source_receipt_sha256=H,
        source_event_at=first,
        first_known_at=first + timedelta(seconds=1),
        due_at=first + timedelta(seconds=301),
        stream_cursor=3,
        source_epoch="test",
        frozen_k_version="k1",
        frozen_k=Decimal("0.125"),
    )
    event = Opportunity(**kwargs)
    assert event.due_at - event.first_known_at == timedelta(seconds=300)
    with pytest.raises(ValueError, match="T300"):
        Opportunity(**{**kwargs, "due_at": first + timedelta(seconds=302)})
    with pytest.raises(ValueError, match="VERSION"):
        assessment(opportunities=(event.model_copy(update={"frozen_k_version": "k2"}),))


def test_original_v4_verified_source_transition_and_gap(tmp_path):
    journal, src = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(src, 10, 20)
    packet = export_signed_events(
        journal.path,
        selected={"S035": ADDRESSES["S035"]},
        signer=key,
        after={"S035": 2},
    )
    args = dict(
        selected={"S035": ADDRESSES["S035"]},
        original_journal=journal.path,
        after={"S035": 2},
        as_of=NOW,
        policy_version="k1",
        frozen_k="0.125",
    )
    result = verify_packet(packet, key.public_key(), **args)
    assert len(result["opportunities"]) == 1
    assert result["opportunities"][0]["due_at"]
    assert result["read_only"]
    altered = json.loads(json.dumps(packet))
    altered["events"]["S035"][0]["proof"]["payload"]["first_known_ms"] += 1000
    with pytest.raises(ValueError):
        verify_packet(altered, key.public_key(), **args)
    wrong = json.loads(json.dumps(packet))
    wrong["events"]["S035"][0]["book"] = None
    with pytest.raises(ValueError):
        verify_packet(wrong, key.public_key(), **args)


def test_census_gap_baseline_and_original_first_known(tmp_path):
    journal, source = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    source_event(source, 10, 20)
    source.gap(at(20), "FAULT")
    source.observe(
        __import__("test_pm_vike_paper_integration").official_frame(21, 0),
        at(22),
    )
    packet = export_signed_events(
        journal.path,
        selected={"S035": ADDRESSES["S035"]},
        signer=key,
        after={"S035": 2},
    )
    report = assess_verified_packet(
        packet,
        key.public_key(),
        source_journal=journal.path,
        selected={"S035": ADDRESSES["S035"]},
        source_after={"S035": 2},
        scope=scope(),
        campaign=campaign(),
        as_of=NOW,
        created_at=NOW,
    )
    assert len(report.opportunities) == 1
    assert report.opportunities[0].due_at - report.opportunities[0].first_known_at == timedelta(
        minutes=5
    )
    assert len(report.missing_intervals) == 1
    assert report.missing_intervals[0].missed_opportunities == "UNKNOWN"
    assert report.missing_intervals[0].recovered_at is not None
    assert report.follower_economics.evidence_class == "UNKNOWN"
    assert report.portfolio_contribution.status == "UNKNOWN"
    assert report.trading_authorized is False
