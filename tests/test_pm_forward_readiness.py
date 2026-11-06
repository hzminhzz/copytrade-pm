"""Read-only source+market+registry readiness must never silently trade partial NAV."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_readiness import audit_live_paper_readiness
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import sample_state
from test_pm_forward_ccxt_market import BTC, at, ccxt_market, orderbook
from test_pm_forward_registry_identity import prepare
from test_pm_forward_tape import diagnostic
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market


def _setup(tmp_path):
    registry, primary, secondary = prepare(tmp_path)
    source = PaperJournal(tmp_path / "source")
    market = PaperJournal(tmp_path / "market")
    parent_address = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    native_state = sample_state()
    native_state["user"] = parent_address
    book = read_public_all_dex_scope(
        alias="S035",
        address=parent_address,
        frame={"channel": "allDexsClearinghouseState", "data": native_state},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)).isoformat(),
    )
    append_public_scope(source, alias="S035", seq=1, receipt=book)
    # Market may be available even while wallet has no combined collateral.
    native = parse_ccxt_market(ccxt_market(), first_known_at=at(1), expected=BTC)
    observed = parse_ccxt_book(native, orderbook(seconds=2), first_known_at=at(3)).payload()
    market.append_market_quote(observed)
    return registry, primary, secondary, source, market


def audit(roots, portfolio, *, sizing_policy="FIXED_K_NATIVE_QUANTITY"):
    registry, primary, secondary, source, market = roots
    return audit_live_paper_readiness(
        registry_db=registry,
        primary_dir=primary,
        secondary_dir=secondary,
        source_db=source.path,
        market_db=market.path,
        portfolio_id=portfolio,
        as_of="2026-11-04T04:00:10+00:00",
        sizing_policy=sizing_policy,
    )


def test_all_approved_portfolios_stay_blocked_on_partial_source_and_registry(tmp_path):
    roots = _setup(tmp_path)
    registry, _, _, source, market = roots
    registry_before = registry.read_bytes()
    source_before = source.path.read_bytes()
    market_before = market.path.read_bytes()
    p1 = audit(roots, "P1")
    p14 = audit(roots, "P14")
    assert p1["status"] == p14["status"] == "BLOCKED_NO_TRADE"
    assert len(p1["registry"]["unresolved_aliases"]) == 3
    assert len(p14["registry"]["unresolved_aliases"]) == 5
    assert p1["source"][0]["admitted"] is False
    assert p1["source"][0]["collateral_diagnostics"]["cursor"] == 0
    assert "COLLATERAL_DIAGNOSTICS_MISSING" not in p1["source"][0]["reason_codes"]
    assert "SELECTED_SCOPE_REAL_EXECUTION_ATTESTATION_PENDING" in p1["source"][0]["reason_codes"]
    assert p1["source_wallet_equity_attested"] is False
    assert p1["trade_volume_complete"] is False
    assert p1["order_route"] == "NONE"
    assert p1["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY"
    assert p1["source_nav_required"] is False
    assert "INDEPENDENT_PARENT_SUBACCOUNT_NAV_NOT_RECONCILED" not in p1["reason_codes"]
    assert "SOURCE_EQUITY_OR_COLLATERAL_UNKNOWN" not in p1["reason_codes"]
    assert "UNSEALED_FROZEN_MEMBER_WALLET_IDS" in p14["reason_codes"]
    assert "MISSING_FOLLOWER_MARKET_QUOTE" in p1["reason_codes"]
    assert len(p1["market"]) > 0
    assert registry.read_bytes() == registry_before
    assert source.path.read_bytes() == source_before
    assert market.path.read_bytes() == market_before
    assert "0x" not in json.dumps(p1["source"])


def test_readiness_audits_diagnostic_collateral_chain_without_promoting_nav(tmp_path):
    roots = _setup(tmp_path)
    _, primary, _, source, _ = roots
    address = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    report = diagnostic()
    report["account_address_sha256"] = sha256(address.lower().encode()).hexdigest()
    source.append_collateral_diagnostic(report)
    before = source.collateral_scope_status(report["account_address_sha256"])
    observed = audit(roots, "P1", sizing_policy="ALLOCATION_OVER_LIVE_NAV")
    first = observed["source"][0]
    assert first["collateral_diagnostics"]["cursor"] == 1
    assert first["collateral_diagnostics"]["head_sha"] == before["head_sha"]
    assert first["collateral_diagnostics"]["status"] == "DIAGNOSTIC_ONLY_NOT_NAV"
    assert "COLLATERAL_SCOPE_NOT_ATOMIC_NAV" in first["reason_codes"]
    assert first["admitted"] is False
    assert source.collateral_scope_status(report["account_address_sha256"]) == before
    with closing(sqlite3.connect(source.path)) as db:
        with db:
            db.execute(
                "UPDATE source_scope_receipts SET chain_sha=? WHERE account_sha=?",
                ("f" * 64, report["account_address_sha256"]),
            )
    with pytest.raises(ValueError, match="PAPER_COLLATERAL_READONLY_CHAIN_DIVERGENCE"):
        audit(roots, "P1")


def test_official_unified_mode_blocks_independent_dex_nav_even_with_source_receipts(tmp_path):
    roots = _setup(tmp_path)
    _, primary, _, source, _ = roots
    addr = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    report = diagnostic()
    report["account_address_sha256"] = sha256(addr.lower().encode()).hexdigest()
    report["account_abstraction"] = {
        "status": "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED",
        "mode": "unifiedAccount",
        "first_known_at": "2026-11-04T04:00:03+00:00",
        "source_event_at": None,
        "response_sha256": "c" * 64,
        "source_signed": False,
    }
    source.append_collateral_diagnostic(report)
    first = audit(roots, "P1", sizing_policy="ALLOCATION_OVER_LIVE_NAV")["source"][0]
    assert first["collateral_diagnostics"]["last_account_mode"] == "unifiedAccount"
    assert "SHARED_COLLATERAL_MODE_BLOCKS_PER_DEX_NAV_SUM" in first["reason_codes"]
    assert "COLLATERAL_SCOPE_NOT_ATOMIC_NAV" in first["reason_codes"]
    assert first["admitted"] is False
    assert "0x" not in json.dumps(first)


def test_parent_discovered_subaccount_missing_from_observations_blocks(tmp_path):
    roots = _setup(tmp_path)
    _, primary, _, source, _ = roots
    parent = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    child = "0x" + "f" * 40
    state = sample_state()
    state["user"] = parent
    receipt = read_public_all_dex_scope(
        alias="S035",
        address=parent,
        frame={"channel": "allDexsClearinghouseState", "data": state},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=[{"master": parent, "subAccountUser": child}],
        first_known_at=(datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=4)).isoformat(),
    )
    append_public_scope(source, alias="S035", seq=2, receipt=receipt)
    first = audit(roots, "P1", sizing_policy="ALLOCATION_OVER_LIVE_NAV")["source"][0]
    assert first["declared_subaccount_count"] == 1
    assert first["observed_subaccount_receipt_count"] == 0
    assert first["missing_subaccount_receipt_count"] == 1
    assert "DISCOVERED_SUBACCOUNT_POSITION_SCOPE_MISSING" in first["reason_codes"]
    assert first["admitted"] is False


def test_perps_only_scope_skips_vault_but_never_promotes_quote_balance_to_nav(tmp_path):
    roots = _setup(tmp_path)
    _, primary, _, source, _ = roots
    parent = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    report = diagnostic()
    report["account_address_sha256"] = sha256(parent.lower().encode()).hexdigest()
    report["copy_scope"] = "PERPETUALS_ONLY"
    report["status"] = "BLOCKED_PERPETUAL_COLLATERAL_RECONCILIATION"
    report["observations"][0] = {
        **report["observations"][0],
        "potential_perp_quote_collateral": {"USDC": {"total": "5000", "hold": "0"}},
        "other_spot_asset_count": 1,
    }
    report["observations"][1] = {
        "scope": "userVaultEquities",
        "status": "OUT_OF_SCOPE_PERPETUALS_ONLY",
        "first_known_at": None,
        "source_event_at": None,
        "response_sha256": None,
        "row_count": None,
    }
    report["account_abstraction"] = {
        "status": "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED",
        "mode": "unifiedAccount",
        "first_known_at": "2026-11-04T04:00:03+00:00",
        "source_event_at": None,
        "response_sha256": "c" * 64,
        "source_signed": False,
    }
    source.append_collateral_diagnostic(report)
    first = audit(roots, "P1", sizing_policy="ALLOCATION_OVER_LIVE_NAV")["source"][0]
    assert first["collateral_diagnostics"]["copy_scope"] == "PERPETUALS_ONLY"
    assert first["collateral_diagnostics"]["last_vault_known_at"] is None
    assert "COLLATERAL_SCOPE_STALE_OR_MISSING" not in first["reason_codes"]
    assert "SHARED_COLLATERAL_MODE_BLOCKS_PER_DEX_NAV_SUM" in first["reason_codes"]
    assert "COLLATERAL_SCOPE_NOT_ATOMIC_NAV" in first["reason_codes"]
    assert first["admitted"] is False


def test_subaccount_latest_receipt_cannot_replace_parent_and_hedges_stay_visible(tmp_path):
    roots = _setup(tmp_path)
    _, primary, _, source, _ = roots
    parent = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    child_address = "0x" + "f" * 40
    child_state = sample_state()
    child_state["user"] = child_address
    child_state["clearinghouseStates"][1][1]["assetPositions"][0]["position"]["coin"] = "xyz:MU"
    child = read_public_all_dex_scope(
        alias="S035",
        address=child_address,
        frame={"channel": "allDexsClearinghouseState", "data": child_state},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=3)).isoformat(),
    )
    append_public_scope(source, alias="S035", seq=2, receipt=child)
    observed = audit(roots, "P1", sizing_policy="ALLOCATION_OVER_LIVE_NAV")
    first = observed["source"][0]
    assert first["first_local_receipts"] == 2
    assert first["observed_distinct_account_count"] == 2
    assert first["observed_subaccount_receipt_count"] == 1
    assert first["unmatched_subaccount_receipt_count"] == 1
    assert "UNMATCHED_SUBACCOUNT_SOURCE_RECEIPT" in first["reason_codes"]
    assert first["parent_receipt_present"] is True
    assert first["last_first_known_at"] != child["first_known_at"]
    assert "NON_ATOMIC_SUBACCOUNT_OBSERVATIONS" in first["reason_codes"]
    assert "SOURCE_REGISTRY_ADDRESS_IDENTITY_MISMATCH" not in first["reason_codes"]
    assert "hyperliquid/mainnet:perp:xyz/MU" in {
        entry["instrument"] for entry in observed["market"]
    }
    assert observed["status"] == "BLOCKED_NO_TRADE"
    assert not first["admitted"]
    assert first["collateral_diagnostics"]["status"] == "NOT_CAPTURED"
    assert parent.lower() != child_address


def test_readiness_raises_on_tampered_source_chain(tmp_path):
    roots = _setup(tmp_path)
    source = roots[3]
    with closing(sqlite3.connect(source.path)) as db:
        with db:
            db.execute(
                "UPDATE source_receipts SET chain_sha=? WHERE source_id='S035' AND seq=1",
                ("a" * 64,),
            )
    with pytest.raises(ValueError, match="PAPER_SOURCE_READONLY_TAPE_DIVERGENCE"):
        audit(roots, "P1")
