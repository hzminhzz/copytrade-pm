"""Non-admitting, read-only multi-gate diagnostics for the continuous observer."""

from datetime import UTC, datetime
import json

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_continuous import (
    SubscriptionBudget,
    candidate_preflight,
    diagnose_candidate_preflight,
    load_continuous_config,
)
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.roster import RosterStore
from roster_fixture import WALLETS, add_account

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
ETH = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
AT = datetime(2026, 11, 6, 12, tzinfo=UTC).isoformat()


def _registry(tmp_path):
    path = tmp_path / "roster.sqlite"
    with RosterStore(path, create=True) as store:
        add_account(store, "P1", {f"seat_{i}": wallet for i, wallet in enumerate(WALLETS[:5])})
    return path


def test_diagnostic_reports_seal_and_budget_without_claiming_attestation(tmp_path):
    registry = _registry(tmp_path)
    old = PaperJournal(tmp_path / "old")
    old_head = old.path.read_bytes()
    new_root = tmp_path / "uncreated"
    options = dict(
        registry_db=registry,
        state_root=new_root,
        instruments=(BTC, ETH),
        revision="a" * 40,
        as_of=AT,
        budget=SubscriptionBudget(
            reserved_connections=8, ccxt_markets_per_socket=1, public_markets_per_socket=1
        ),
        protected_roots=(old.root,),
        portfolio_ids=("P1",),
        expected_inventory_sha=RosterStore.authority_health(registry)["inventory_sha256"],
    )
    report = diagnose_candidate_preflight(**options)
    assert report["status"] == "BLOCKED"
    assert report["gates"]["registry_integrity"]["status"] == "PASS"
    assert report["gates"]["portfolio_seals"]["status"] == "PASS"
    assert report["gates"]["signed_selection"]["reason_code"] == "SELECTION_ATTESTATION_MISSING"
    assert (
        report["gates"]["subscription_budget"]["reason_code"] == "STREAM_CONNECTION_BUDGET_EXCEEDED"
    )
    assert report["account_count_basis"] == "ROSTER_WATCHLIST"
    assert report["candidate_connections_estimate"] == 5
    assert report["candidate_users_estimate"] == 5
    assert report["candidate_subscriptions_estimate"] == 11
    assert report["safe_to_start"] is False
    assert report["order_route"] == "NONE"
    assert not new_root.exists()
    assert old.path.read_bytes() == old_head
    with pytest.raises(ValueError, match="STREAM_CONNECTION_BUDGET_EXCEEDED"):
        candidate_preflight(**options)


def test_diagnostic_blocks_unknown_book_and_inventory_drift(tmp_path):
    path = _registry(tmp_path)
    report = diagnose_candidate_preflight(
        registry_db=path,
        state_root=tmp_path / "uncreated",
        instruments=(BTC,),
        revision="a" * 40,
        as_of=AT,
        budget=SubscriptionBudget(),
        portfolio_ids=("unknown",),
        expected_inventory_sha="b" * 64,
    )
    assert report["status"] == "BLOCKED"
    assert report["gates"]["portfolio_seals"]["reason_code"] == "SELECTION_UNKNOWN_AT_ASOF"
    assert (
        report["gates"]["inventory_generation"]["reason_code"]
        == "STREAM_REGISTRY_GENERATION_CHANGED"
    )
    assert report["gates"]["account_census"]["status"] == "UNKNOWN"
    assert report["safe_to_start"] is False


def test_config_budget_failure_exposed_only_for_diagnostics(tmp_path):
    config = {
        "schema": "paper_continuous_observer_config_v1",
        "revision": "a" * 40,
        "inventory_sha256": "b" * 64,
        "portfolio_ids": ["P1"],
        "protected_roots": [str(tmp_path / "old")],
        "budget": {"reserved_connections": 10},
        "instruments": [BTC.key],
        "duration_seconds": 0,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="STREAM_CONNECTION_BUDGET_EXCEEDED"):
        load_continuous_config(path)
    parsed, instruments, budget = load_continuous_config(
        path, allow_budget_failures_for_diagnostics=True
    )
    assert parsed["revision"] == config["revision"]
    assert instruments == (BTC,)
    assert budget.reserved_connections == 10
    config["budget"] = {"ccxt_markets_per_socket": 0}
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="STREAM_BUDGET_EXCEEDS_PROVIDER_LIMIT"):
        load_continuous_config(path, allow_budget_failures_for_diagnostics=True)


def test_diagnostic_entrypoint_is_read_only_and_skips_strict_preflight(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import copytrade_pm.pm_forward_continuous as module

    registry = _registry(tmp_path)
    config = {
        "schema": "paper_continuous_observer_config_v1",
        "revision": "a" * 40,
        "inventory_sha256": "b" * 64,
        "portfolio_ids": ["P1"],
        "protected_roots": [str(tmp_path / "old")],
        "budget": {"reserved_connections": 10},
        "instruments": [BTC.key],
        "duration_seconds": 0,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(module, "runtime_revision", lambda: "a" * 40)

    def cannot_run_strict(**_kwargs):
        raise AssertionError("strict preflight must never run for diagnostics")

    monkeypatch.setattr(module, "candidate_preflight", cannot_run_strict)
    root = tmp_path / "new"
    args = SimpleNamespace(
        continuous_config=config_path,
        preflight_only=True,
        diagnose_preflight=True,
        registry=registry,
        state_root=root,
    )
    report = module.continuous_entrypoint(args)
    assert report["status"] == "BLOCKED"
    assert report["gates"]["signed_selection"]["status"] == "BLOCKED"
    assert report["gates"]["subscription_budget"]["reason_code"] == (
        "STREAM_CONNECTION_BUDGET_EXCEEDED"
    )
    assert not root.exists()
    args.preflight_only = False
    with pytest.raises(ValueError, match="STREAM_DIAGNOSTIC_REQUIRES_PREFLIGHT_ONLY"):
        module.continuous_entrypoint(args)
    assert not root.exists()


def test_diagnostic_cli_reports_blocked_and_exits_two(tmp_path, monkeypatch, capsys):
    import copytrade_pm.pm_forward_observer as cli
    import copytrade_pm.pm_forward_continuous as module

    invoked = []

    def diagnostic(args):
        invoked.append(args)
        return {
            "status": "BLOCKED",
            "gates": {"signed_selection": {"reason_code": "STREAM_SELECTION_PROOF_MISSING"}},
            "safe_to_start": False,
            "order_route": "NONE",
        }

    monkeypatch.setattr(module, "continuous_entrypoint", diagnostic)
    argv = [
        "observe",
        "--registry",
        str(tmp_path / "registry"),
        "--primary-dir",
        str(tmp_path),
        "--secondary-dir",
        str(tmp_path),
        "--state-root",
        str(tmp_path / "new"),
        "--continuous-config",
        str(tmp_path / "config"),
        "--preflight-only",
        "--diagnose-preflight",
    ]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert len(invoked) == 1 and invoked[0].diagnose_preflight
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    assert not (tmp_path / "new").exists()
