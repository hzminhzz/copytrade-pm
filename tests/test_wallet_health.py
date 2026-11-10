"""Track B black-box causal, attribution, registry and publication tests."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import sqlite3

import pytest

from copytrade_pm import wallet_health as h
from copytrade_pm import wallet_health_projection as projection
from copytrade_pm import wallet_registry as registry


NOW = datetime(2026, 11, 9, 18, tzinfo=UTC)
HASH = "a" * 64


def seeded(tmp_path):
    db = tmp_path / "wallet.sqlite"
    with closing(sqlite3.connect(db)) as con, con:
        con.executescript(registry.DDL)
        con.executemany(
            "INSERT INTO wallets(wallet_id,venue,network,address) VALUES(?,?,?,?)",
            [(1, "HL", "mainnet", "0x" + "a" * 40), (2, "HL", "mainnet", "0x" + "b" * 40)],
        )
        con.execute("INSERT INTO cohorts VALUES('registered',1,?)", (HASH,))
        con.executemany(
            "INSERT INTO cohort_memberships VALUES('registered',1,?,?)",
            [(1, "2026-11-01T00:00:00+00:00"), (2, "2026-11-15T00:00:00+00:00")],
        )
    return db


def finance(**values):
    defaults = dict(
        account_scope="main-perp",
        known_at=NOW,
        observed_at=NOW,
        source_sha256=HASH,
        opening_equity=Decimal("10000"),
        closing_equity=Decimal("4000"),
        deposits=Decimal(0),
        withdrawals=Decimal("6000"),
        realized_pnl=Decimal(0),
        unrealized_pnl_change=Decimal(0),
        fees=Decimal(0),
        funding=Decimal(0),
        complete_flows=True,
        complete_pnl=True,
        capital_verified=True,
    )
    return h.FinancialEvidence(**(defaults | values))


def episode(n, *, pnl="-1", known_at=NOW, days=0, complete=True, kind="RETROSPECTIVE_ESTIMATE"):
    return h.FollowerEpisode(
        account_scope="main-perp",
        known_at=known_at,
        completed_at=NOW - timedelta(days=days),
        episode_id=f"episode-{n}",
        source_sha256=HASH,
        net_follower_pnl_usd=Decimal(pnl),
        costs_complete=complete,
        coverage_complete=complete,
        kind=kind,
    )


def test_registry_asof_dedup_later_identity_and_read_only(tmp_path):
    db = seeded(tmp_path)
    before = db.read_bytes()
    report = h.assess(db, as_of=NOW, provider_budget=0)
    assert report.assessed_wallets == 1
    assert report.findings[0].reasons[0] == "MISSING_OR_STALE_CAPITAL_EVIDENCE"
    assert report.evidence_requests == 0
    assert db.read_bytes() == before
    assert report.trading_authorized is False


def test_budget_drops_unexamined_inputs(tmp_path):
    db = seeded(tmp_path)
    report = h.assess(db, as_of=NOW, financial={1: finance()}, provider_budget=0)
    assert report.findings[0].eligibility == "UNKNOWN"
    assert "PROVIDER_BUDGET_EXHAUSTED" in report.findings[0].reasons


def test_withdrawal_is_not_trading_loss(tmp_path):
    db = seeded(tmp_path)
    result = h.assess(db, as_of=NOW, financial={1: finance()}).findings[0]
    assert result.capital_attribution == "RECONCILED"
    assert result.net_capital_flow_usd == Decimal("-6000")
    assert result.trading_pnl_usd == 0
    assert result.unexplained_equity_change_usd == 0


def test_unsupported_equity_claim_cannot_establish_floor(tmp_path):
    db = seeded(tmp_path)
    finding = h.assess(
        db,
        as_of=NOW,
        financial={1: finance(capital_verified=False, closing_equity=Decimal("20000"))},
    ).findings[0]
    assert finding.eligibility == "UNKNOWN"
    assert finding.capital_attribution == "UNKNOWN"
    assert "CAPITAL_EVIDENCE_NOT_VERIFIED" in finding.reasons


def test_funding_missing_and_residual_not_hidden(tmp_path):
    db = seeded(tmp_path)
    missing = h.assess(db, as_of=NOW, financial={1: finance(funding=None)}).findings[0]
    assert missing.capital_attribution == "UNKNOWN"
    assert missing.trading_pnl_usd is None
    unreconciled = h.assess(
        db, as_of=NOW, financial={1: finance(closing_equity=Decimal("3000"))}
    ).findings[0]
    assert unreconciled.capital_attribution == "UNRECONCILED"
    assert unreconciled.unexplained_equity_change_usd == -1000


def test_late_evidence_cannot_rewrite_earlier_asof(tmp_path):
    db = seeded(tmp_path)
    later = finance(known_at=NOW + timedelta(days=1))
    got = h.assess(db, as_of=NOW, financial={1: later}).findings[0]
    assert got.eligibility == "UNKNOWN"
    assert got.source_integrity == "UNKNOWN"
    future = episode(1, known_at=NOW + timedelta(days=1))
    got = h.assess(db, as_of=NOW, episodes={1: [future]}).findings[0]
    assert got.windows["7"]["independent_episodes"] == 0


def test_future_episode_does_not_change_historical_account_scope(tmp_path):
    db = seeded(tmp_path)
    future = h.FollowerEpisode(
        account_scope="future-scope",
        known_at=NOW + timedelta(days=2),
        completed_at=NOW + timedelta(days=1),
        episode_id="future-1",
        source_sha256=HASH,
        net_follower_pnl_usd=Decimal("200"),
        costs_complete=True,
        coverage_complete=True,
        kind="RETROSPECTIVE_ESTIMATE",
    )
    result = h.assess(db, as_of=NOW, episodes={1: [future]}).findings[0]
    assert result.account_scope == "UNKNOWN"
    assert result.activity == "UNKNOWN"
    assert result.windows["7"]["independent_episodes"] == 0


def test_mixed_retrospective_and_one_prospective_not_promoted(tmp_path):
    db = seeded(tmp_path)
    es = [episode(i, days=i) for i in range(5)]
    es.append(episode(6, days=6, kind="AUTHENTIC_PROSPECTIVE"))
    finding = h.assess(db, as_of=NOW, episodes={1: es}).findings[0]
    assert finding.copyability == "RETROSPECTIVE_ONLY"


def test_naive_evidence_timestamps_are_rejected():
    with pytest.raises(ValueError, match="UTC_AS_OF_REQUIRED"):
        finance(known_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="UTC_AS_OF_REQUIRED"):
        episode(0, known_at=NOW.replace(tzinfo=None))


def test_copyability_retrospective_and_prospective_are_distinct(tmp_path):
    db = seeded(tmp_path)
    es = [episode(i, pnl="-2", days=i) for i in range(5)]
    finding = h.assess(db, as_of=NOW, financial={1: finance()}, episodes={1: es}).findings[0]
    assert finding.edge == "PERSISTENT_WARNING"
    assert finding.copyability == "RETROSPECTIVE_ONLY"
    assert finding.recommendation == "EDGE_WARNING"
    unqualified = h.assess(
        db, as_of=NOW, episodes={1: es[:4] + [episode(5, complete=False)]}
    ).findings[0]
    assert unqualified.edge == "INSUFFICIENT_EVIDENCE"
    prospect = h.assess(
        db,
        as_of=NOW,
        episodes={1: [episode(i, days=i, kind="AUTHENTIC_PROSPECTIVE") for i in range(5)]},
    ).findings[0]
    assert prospect.copyability == "PROSPECTIVE_OBSERVED"
    assert prospect.trading_pnl_usd is None


def test_immutable_report_and_redacted_published_snapshot(tmp_path):
    db = seeded(tmp_path)
    report = h.assess(db, as_of=NOW, financial={1: finance()})
    out = tmp_path / "private"
    first = h.save_immutable(report, out)
    assert h.save_immutable(report, out) == first
    payload = projection.project(report, published_at=NOW)
    assert b"0xaaaaaaaa" not in payload
    assert b"main-perp" not in payload
    projected = tmp_path / "pub"
    projection.publish(projected, payload)
    assert projection.read(projected, now=NOW)["wallet_count"] == 1
    assert projection.read(projected, now=NOW + timedelta(days=3))["stale"]
    decoded = json.loads(payload)
    decoded["wallet_count"] = 3
    (projected / "wallet-health.json").write_text(json.dumps(decoded))
    with pytest.raises(ValueError, match="HASH"):
        projection.read(projected, now=NOW)


def test_gateway_is_read_only_and_fail_closed(tmp_path):
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient
    from copytrade_pm.dashboard.grafana_projection import create_app

    db = seeded(tmp_path)
    report = h.assess(db, as_of=NOW, financial={1: finance()})
    evidence = tmp_path / "published"
    projection.publish(evidence, projection.project(report, published_at=NOW))
    app = create_app(token="s" * 40, snapshot_dir=evidence, allowed_host="localhost")
    headers = {"Authorization": "Bearer " + "s" * 40}
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/v1/wallet-health").status_code == 403
        assert client.get("/v1/wallet-health?wallet=1", headers=headers).status_code == 400
        assert client.post("/v1/wallet-health", headers=headers).status_code == 405
        valid = client.get("/v1/wallet-health", headers=headers)
        assert valid.status_code == 200
        assert valid.json()["wallet_count"] == 1
        assert valid.json()["trading_authorized"] is False
    assert db.exists()
    assert not (tmp_path / "guardian.sqlite").exists()


def test_inactive_solvent_and_missing_nav_do_not_assert_loss(tmp_path):
    db = seeded(tmp_path)
    f = finance(
        closing_equity=Decimal("12000"),
        deposits=None,
        withdrawals=None,
        realized_pnl=None,
        unrealized_pnl_change=None,
        fees=None,
        funding=None,
    )
    finding = h.assess(db, as_of=NOW, financial={1: f}).findings[0]
    assert finding.eligibility == "ELIGIBLE"
    assert finding.activity == "UNKNOWN"
    assert finding.trading_pnl_usd is None
    assert finding.recommendation == "INSUFFICIENT_EVIDENCE"
    absent = h.assess(db, as_of=NOW).findings[0]
    assert absent.eligibility == "UNKNOWN"
    assert absent.trading_pnl_usd is None


def test_verified_inactive_solvent_wallet(tmp_path):
    db = seeded(tmp_path)
    finding = h.assess(
        db,
        as_of=NOW,
        financial={
            1: finance(
                opening_equity=Decimal("4000"),
                closing_equity=Decimal("4000"),
                withdrawals=Decimal(0),
                activity_complete=True,
                last_trade_at=NOW - timedelta(days=45),
            )
        },
    ).findings[0]
    assert finding.eligibility == "ELIGIBLE"
    assert finding.activity == "INACTIVE"
    assert finding.recommendation == "INACTIVE"


def test_duplicate_episodes_not_counted(tmp_path):
    db = seeded(tmp_path)
    items = [episode(1)] * 6
    finding = h.assess(db, as_of=NOW, episodes={1: items}).findings[0]
    assert finding.windows["7"]["independent_episodes"] == 1
    assert finding.edge == "INSUFFICIENT_EVIDENCE"


def test_invalid_provenance_and_financial_inputs_rejected():
    with pytest.raises(ValueError, match="KNOWLEDGE_PRECEDES_OBSERVATION"):
        finance(known_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="FUTURE_EPISODE"):
        episode(1, known_at=NOW - timedelta(days=1))
