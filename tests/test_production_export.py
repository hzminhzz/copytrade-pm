from contextlib import closing

from test_wallet_registry import address, fixture
from test_wallet_registry_portfolios import frozen
from copytrade_pm import wallet_registry as reg


def database(tmp_path):
    _, snap = fixture(tmp_path)
    snap["frozen_aliases"] = {"W028": address(1), "W042": address(2), "W030": address(3)}
    db = tmp_path / "private" / "registry.sqlite"
    reg.apply(db, snap, "2026-11-01T00:00:00+00:00")
    snap["portfolio_contracts"] = frozen()
    snap["sources"].update(
        {f"portfolio_doc:{k}": v["payload"]["source_doc_sha256"] for k, v in frozen().items()}
    )
    reg.apply(db, snap, "2026-11-04T05:00:00+00:00")
    return db


def test_default_fixed_k_export_is_repeatable_readonly_and_scope_gated(tmp_path):
    from copytrade_pm.production_export import export_metadata

    db = database(tmp_path)
    before = reg.db_authority_health(db)["inventory_sha256"]
    first = export_metadata(db, "A", "2026-11-04T06:00:00+00:00")
    second = export_metadata(db, "A", "2026-11-04T06:00:00+00:00")
    assert first == second
    assert first["state"] == "BLOCKED"
    assert first["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY"
    assert "SOURCE_BOOK_NAV_ATTESTATION_MISSING" not in first["blockers"]
    assert "SOURCE_POSITION_SCOPE_ATTESTATION_MISSING" in first["blockers"]
    legacy = export_metadata(
        db, "A", "2026-11-04T06:00:00+00:00", sizing_policy="ALLOCATION_OVER_LIVE_NAV"
    )
    assert "SOURCE_BOOK_NAV_ATTESTATION_MISSING" in legacy["blockers"]
    assert legacy["export_sha256"] != first["export_sha256"]
    assert first["registry_inventory_sha256"] == before
    assert len(first["members"]) == 3
    assert reg.db_authority_health(db)["inventory_sha256"] == before


def test_missing_identity_is_not_filled_from_later_alias(tmp_path):
    from copytrade_pm.production_export import export_metadata

    db = database(tmp_path)
    result = export_metadata(db, "P1", "2026-11-04T06:00:00+00:00")
    assert result["state"] == "BLOCKED"
    assert "MEMBER_IDENTITY_UNKNOWN_AT_SEAL" in result["blockers"]


def test_inventory_mutation_changes_export_approval_digest(tmp_path):
    from copytrade_pm.production_export import export_metadata

    db = database(tmp_path)
    before = export_metadata(db, "A", "2026-11-04T06:00:00+00:00")
    with closing(reg.connect(db, True)) as con:
        con.execute(
            "INSERT INTO wallets(venue,network,address) VALUES ('hyperliquid','mainnet',?)",
            (address(999),),
        )
        con.commit()
    after = export_metadata(db, "A", "2026-11-04T06:00:00+00:00")
    assert after["export_sha256"] != before["export_sha256"]
