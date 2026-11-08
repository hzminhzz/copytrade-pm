"""Pinned catalog cannot silently omit or remap Propr native instruments."""
import json
from pathlib import Path

import pytest

from copytrade_pm.pm_vike_market_catalog import load_propr_catalog

CATALOG = Path(__file__).resolve().parents[1] / "docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json"


def test_propr_catalog_has_all_157_native_markets():
    catalog = load_propr_catalog(CATALOG)
    assert catalog.count == 157
    assert "BTC" in catalog.native_symbols
    assert "xyz:BRENTOIL" in catalog.native_symbols
    assert len(catalog.catalog_sha256) == 64
    assert catalog.scope == "PROPR_DISPLAY_ONLY_NOT_ORDER_AUTHORIZED"


@pytest.mark.parametrize("mutation", [
    lambda d: d["physical_sockets"][0]["instruments"].append(d["physical_sockets"][0]["instruments"][0]),
    lambda d: d.update(propr_order_ids_attested=True),
    lambda d: d["physical_sockets"][0]["instruments"].append("hyperliquid/mainnet:perp:xyz/BTC"),
    lambda d: d.update(native_market_count=999),
])
def test_catalog_fails_closed_on_corruption(tmp_path, mutation):
    doc = json.loads(CATALOG.read_text())
    mutation(doc)
    target = tmp_path / "catalog.json"
    target.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="PROPR_CATALOG"):
        load_propr_catalog(target)
