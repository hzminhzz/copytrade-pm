"""Non-admitting, read-only multi-gate diagnostics for the continuous observer."""

from contextlib import closing
from datetime import UTC, datetime
import json
import sqlite3

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_continuous import (
    SubscriptionBudget,
    candidate_preflight,
    diagnose_candidate_preflight,
    load_continuous_config,
)
from copytrade_pm.pm_forward_journal import PaperJournal

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
ETH = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
AT = datetime(2026, 11, 6, 12, tzinfo=UTC).isoformat()


def _registry(tmp_path):
    registry = tmp_path / "registry.sqlite"
    with closing(sqlite3.connect(registry)) as db:
        db.execute("CREATE TABLE marker (value INTEGER)")
        db.commit()
    registry.chmod(0o600)
    return registry


def test_diagnostic_reports_independent_provenance_exclusion_and_budget_without_writes(
    tmp_path, monkeypatch
):
    import copytrade_pm.pm_forward_continuous as module

    registry = _registry(tmp_path)
    old = PaperJournal(tmp_path / "old")
    old_head = old.path.read_bytes()
    new_root = tmp_path / "uncreated"
    monkeypatch.setattr(
        module,
        "db_authority_health",
        lambda _path: {
            "database_integrity": "VERIFIED",
            "inventory_sha256": "b" * 64,
        },
    )

    def excluded(*_args, **_kwargs):
        raise ValueError("PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED")

    monkeypatch.setattr(module, "registry_watched_addresses", excluded)
    monkeypatch.setattr(
        module,
        "_portfolio_seals",
        lambda *_args, **_kwargs: {"P14": {"version": 2}},
    )
    monkeypatch.setattr(module, "_diagnostic_sealed_account_count", lambda *_args: 5)
    budget = SubscriptionBudget(
        reserved_connections=8, ccxt_markets_per_socket=1, public_markets_per_socket=1
    )
    options = dict(
        registry_db=registry,
        state_root=new_root,
        instruments=(BTC, ETH),
        revision="a" * 40,
        as_of=AT,
        budget=budget,
        protected_roots=(old.root,),
        portfolio_ids=("P14",),
        expected_inventory_sha="b" * 64,
    )
    report = diagnose_candidate_preflight(**options)
    assert report["status"] == "BLOCKED"
    assert report["gates"]["registry_integrity"]["status"] == "PASS"
    assert report["gates"]["signed_selection"] == {
        "status": "PASS",
        "scope": "REQUESTED_PORTFOLIO_SEALS_ONLY",
    }
    assert (
        report["gates"]["watched_wallets"]["reason_code"] == "PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED"
    )
    assert report["gates"]["subscription_budget"]["reason_code"] == (
        "STREAM_CONNECTION_BUDGET_EXCEEDED"
    )
    assert report["account_count_basis"] == "SEALED_MEMBERSHIP_ESTIMATE"
    assert report["candidate_connections_estimate"] == 5
    assert report["candidate_users_estimate"] == 5
    assert report["candidate_subscriptions_estimate"] == 11
    assert report["safe_to_start"] is False
    assert report["order_route"] == "NONE"
    assert not new_root.exists()
    assert old.path.read_bytes() == old_head
    with pytest.raises(ValueError, match="PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED"):
        candidate_preflight(**options)


def test_diagnostic_can_pass_all_checks_but_never_admit_start(tmp_path, monkeypatch):
    import copytrade_pm.pm_forward_continuous as module

    registry = _registry(tmp_path)
    monkeypatch.setattr(
        module,
        "db_authority_health",
        lambda _path: {"database_integrity": "VERIFIED", "inventory_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        module,
        "registry_watched_addresses",
        lambda *_args, **_kwargs: {"0x" + "1" * 40: "wallet:1"},
    )
    monkeypatch.setattr(
        module,
        "_portfolio_seals",
        lambda *_args, **_kwargs: {"P1": {"version": 2}},
    )
    root = tmp_path / "uncreated"
    report = diagnose_candidate_preflight(
        registry_db=registry,
        state_root=root,
        instruments=(BTC,),
        revision="a" * 40,
        as_of=AT,
        budget=SubscriptionBudget(),
        portfolio_ids=("P1",),
        expected_inventory_sha="b" * 64,
    )
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert all(value["status"] == "PASS" for value in report["gates"].values())
    assert report["account_count_basis"] == "ELIGIBLE_WATCHLIST"
    assert report["strict_preflight_still_required"] is True
    assert report["safe_to_start"] is False
    assert not root.exists()


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
    monkeypatch.setattr(
        module,
        "db_authority_health",
        lambda _path: {"database_integrity": "VERIFIED", "inventory_sha256": "b" * 64},
    )

    monkeypatch.setattr(
        module,
        "_portfolio_seals",
        lambda *_args, **_kwargs: {"P1": {"version": 2}},
    )
    monkeypatch.setattr(module, "_diagnostic_sealed_account_count", lambda *_args: 3)
    monkeypatch.setattr(
        module,
        "registry_watched_addresses",
        lambda *_args, **_kwargs: {"0x" + "1" * 40: "wallet:1"},
    )

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
    assert report["gates"]["signed_selection"]["status"] == "PASS"
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
