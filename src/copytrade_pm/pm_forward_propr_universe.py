"""Reproducible Propr *displayed* universe to public Hyperliquid market observations.

Propr display symbols are NOT verified Propr account order IDs or permissions.
This generator maps the dated public snapshot to candidate Hyperliquid DEX
namespaces; official live /info metadata must independently confirm every coin
before observation. Source wallet / paper admission remains separately blocked.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .pm03_account import Instrument
from .pm_forward_public_trades import native_coin

PROPR_SOURCE_SCHEMA = "propr_public_universe_browser_snapshot_v1"
PHYSICAL_LAYOUT_SCHEMA = "paper_public_physical_sockets_v1"
TOP_MAJORS = ("HYPE", "NEAR", "ZEC", "BTC", "ETH", "XMR", "SOL", "ENA")
CATEGORY_NAMES = ("crypto", "equities", "indices", "commodities", "fx")


def _read_snapshot(path: Path) -> tuple[dict, str]:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512_000:
        raise ValueError("PROPR_SNAPSHOT_SOURCE_UNAVAILABLE")
    raw = path.read_bytes()
    try:
        snapshot = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PROPR_SNAPSHOT_JSON_INVALID") from exc
    if not isinstance(snapshot, dict) or snapshot.get("schema") != PROPR_SOURCE_SCHEMA:
        raise ValueError("PROPR_SNAPSHOT_SCHEMA_INVALID")
    if (
        snapshot.get("not_proof_of_historical_availability") is not True
        or snapshot.get("not_proof_of_execution_or_order_acceptance") is not True
        or snapshot.get("retrieved_on_utc_date") is None
    ):
        raise ValueError("PROPR_SNAPSHOT_AUTHORITY_OVERSTATED")
    symbols = snapshot.get("market_symbols")
    counts = snapshot.get("category_counts")
    if not isinstance(symbols, dict) or not isinstance(counts, dict):
        raise ValueError("PROPR_SNAPSHOT_CATEGORY_SCHEMA_INVALID")
    if (
        set(symbols) != set(CATEGORY_NAMES) - {"fx"}
        or set(counts) != set(CATEGORY_NAMES)
        or counts["fx"] != 0
    ):
        raise ValueError("PROPR_SNAPSHOT_CATEGORY_DRIFT")
    for category in CATEGORY_NAMES:
        names = symbols.get(category, [])
        if (
            not isinstance(names, list)
            or any(not isinstance(item, str) for item in names)
            or len(names) != counts[category]
            or len(names) != len(set(names))
        ):
            raise ValueError("PROPR_SNAPSHOT_CATEGORY_INVALID:" + category)
    if type(snapshot.get("snapshot_market_count")) is not int or snapshot[
        "snapshot_market_count"
    ] != sum(counts.values()):
        raise ValueError("PROPR_SNAPSHOT_COUNT_DRIFT")
    return snapshot, sha256(raw).hexdigest()


def snapshot_sha256(path: Path) -> str:
    """Independently recheck bytes against the config's pinned source identity."""
    return _read_snapshot(path)[1]


def build_propr_public_socket_layout(path: Path, *, top40_layout_path: Path | None = None) -> dict:
    """Three physical sockets: 8 core, all other crypto, all xyz display assets.

    Dedup repeated displays (e.g. COPPER equity+commodity); do not silently
    discard a source symbol or map ambiguous non-xyz DEXs without authority.
    """
    snapshot, source_sha = _read_snapshot(path)
    symbols = snapshot["market_symbols"]
    crypto = symbols["crypto"]
    if any(item not in crypto for item in TOP_MAJORS):
        raise ValueError("PROPR_SNAPSHOT_MAJOR_COVERAGE_MISSING")
    xyz = list(dict.fromkeys(symbols["equities"] + symbols["indices"] + symbols["commodities"]))
    if symbols.get("fx"):
        raise ValueError("PROPR_SNAPSHOT_FX_SCOPE_UNMAPPED")
    core = list(TOP_MAJORS)
    remaining = [name for name in crypto if name not in TOP_MAJORS]

    def key(dex: str, coin: str) -> str:
        instrument = Instrument("hyperliquid", "mainnet:perp:" + dex, coin)
        native_coin(instrument)
        return instrument.key

    sockets = [
        {"name": "core_crypto_majors", "instruments": [key("default", x) for x in core]},
        {"name": "other_crypto_perps", "instruments": [key("default", x) for x in remaining]},
        {"name": "xyz_equities_indices_commodities", "instruments": [key("xyz", x) for x in xyz]},
    ]
    universe = [x for socket in sockets for x in socket["instruments"]]
    if len(universe) != len(set(universe)):
        raise ValueError("PROPR_SNAPSHOT_NATIVE_ID_COLLISION")
    layout = {
        "schema": PHYSICAL_LAYOUT_SCHEMA,
        "source": "Dated Propr public displayed universe; not account order authorization",
        "source_snapshot_sha256": source_sha,
        "source_retrieved_on_utc_date": snapshot["retrieved_on_utc_date"],
        "display_market_count": snapshot["snapshot_market_count"],
        "native_market_count": len(universe),
        "display_category_counts": snapshot["category_counts"],
        "deduplicated_display_symbols": snapshot["snapshot_market_count"] - len(universe),
        "physical_sockets": sockets,
        "propr_order_ids_attested": False,
        "source_wallet_nav_attested": False,
        "paper_admitted": False,
    }
    if top40_layout_path is not None:
        from .pm_forward_public_trades import load_public_market_shards

        old = load_public_market_shards(top40_layout_path)
        included = set(universe)
        logical = [
            {"name": name, "instruments": [inst.key for inst in group]} for name, group in old
        ]
        if any(m not in included for group in logical for m in group["instruments"]):
            raise ValueError("PROPR_SNAPSHOT_TOP40_NOT_SUBSET")
        layout["logical_reporting_groups"] = logical
    return layout


def verify_propr_display_layout(snapshot_path: Path, layout: dict) -> dict:
    """Prove the configured entire native set equals source bytes, not just count.

    Avoid silently replacing a display market with another listed HL market.
    The source is dated PUBLIC DISPLAY metadata, still not order authorization.
    """
    expected = build_propr_public_socket_layout(snapshot_path)
    fields = (
        "source_snapshot_sha256",
        "source_retrieved_on_utc_date",
        "display_market_count",
        "native_market_count",
        "display_category_counts",
        "deduplicated_display_symbols",
        "physical_sockets",
    )
    if not isinstance(layout, dict) or layout.get("schema") != PHYSICAL_LAYOUT_SCHEMA:
        raise ValueError("PROPR_LAYOUT_SCHEMA_INVALID")
    if any(layout.get(field) != expected[field] for field in fields):
        raise ValueError("PROPR_LAYOUT_NATIVE_DISPLAY_PARITY_FAILED")
    return {
        "status": "DISPLAY_UNIVERSE_RECONCILED_NOT_ACCOUNT_AUTHORIZED",
        "source_snapshot_sha256": expected["source_snapshot_sha256"],
        "display_market_count": expected["display_market_count"],
        "native_market_count": expected["native_market_count"],
        "propr_order_ids_attested": False,
        "paper_admitted": False,
    }
