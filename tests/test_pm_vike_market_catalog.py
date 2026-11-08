"""Pinned catalog cannot silently omit or remap Propr native instruments."""

import json
from pathlib import Path
from decimal import Decimal
from hashlib import sha256

import pytest

from copytrade_pm.pm_vike_market_catalog import (
    load_propr_catalog,
    official_paper_contracts,
)
from copytrade_pm.pm03_account import Instrument

CATALOG = (
    Path(__file__).resolve().parents[1] / "docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json"
)


def test_official_native_contracts_are_independent_of_price_rows():
    calls = []

    def official_info(request):
        calls.append(request)
        dex = request.get("dex", "default")
        universe = (
            [{"name": "BTC", "szDecimals": 5}, {"name": "ETH", "szDecimals": 4}]
            if dex == "default"
            else [{"name": "xyz:SP500", "szDecimals": 2}]
        )
        doc = {"universe": universe}
        raw = json.dumps(doc, sort_keys=True).encode()
        return doc, raw, sha256(raw).hexdigest()

    contracts = official_paper_contracts(
        frozenset({"BTC", "ETH", "xyz:SP500", "xyz:QUIET"}),
        observed_at="2026-11-08T10:00:00+00:00",
        minimum_notional_usd=Decimal("10"),
        info=official_info,
    )
    assert calls == [{"type": "meta"}, {"type": "meta", "dex": "xyz"}]
    btc = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
    xyz = Instrument("hyperliquid", "mainnet:perp:xyz", "SP500")
    assert set(contracts) == {
        btc.key,
        Instrument("hyperliquid", "mainnet:perp:default", "ETH").key,
        xyz.key,
    }
    assert contracts[btc.key].amount_step == Decimal("0.00001")
    assert contracts[xyz.key].amount_step == Decimal("0.01")
    assert contracts[xyz.key].hip3
    assert contracts[btc.key].minimum_notional == Decimal("10")
    assert contracts[btc.key].min_notional_source == "ESTIMATED_PAPER_POLICY_NOT_VENUE_ATTESTED"
    assert contracts[btc.key].metadata_source == "OFFICIAL_HYPERLIQUID_META"


def test_official_native_contracts_reject_unauthenticated_meta():
    def bad_info(_):
        return {"universe": [{"name": "BTC", "szDecimals": 5}]}, b"invalid", "0" * 64

    with pytest.raises(ValueError, match="OFFICIAL_META_INVALID"):
        official_paper_contracts(
            frozenset({"BTC"}),
            observed_at="2026-11-08T10:00:00+00:00",
            minimum_notional_usd=Decimal("10"),
            info=bad_info,
        )


def test_propr_catalog_has_all_157_native_markets():
    catalog = load_propr_catalog(CATALOG)
    assert catalog.count == 157
    assert "BTC" in catalog.native_symbols
    assert "xyz:BRENTOIL" in catalog.native_symbols
    assert len(catalog.catalog_sha256) == 64
    assert catalog.scope == "PROPR_DISPLAY_ONLY_NOT_ORDER_AUTHORIZED"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["physical_sockets"][0]["instruments"].append(
            d["physical_sockets"][0]["instruments"][0]
        ),
        lambda d: d.update(propr_order_ids_attested=True),
        lambda d: d["physical_sockets"][0]["instruments"].append(
            "hyperliquid/mainnet:perp:xyz/BTC"
        ),
        lambda d: d.update(native_market_count=999),
    ],
)
def test_catalog_fails_closed_on_corruption(tmp_path, mutation):
    doc = json.loads(CATALOG.read_text())
    mutation(doc)
    target = tmp_path / "catalog.json"
    target.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="PROPR_CATALOG"):
        load_propr_catalog(target)
