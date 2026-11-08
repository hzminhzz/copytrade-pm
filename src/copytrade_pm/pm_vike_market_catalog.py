"""Versioned, read-only Propr display universe for Vike market observations.

The display snapshot is not a broker tradability claim. Native IDs are
preserved and missing prices are explicitly reported by the collector.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .pm_vike_minute import native_instrument


@dataclass(frozen=True)
class MarketCatalog:
    native_symbols: frozenset[str]
    snapshot_sha256: str
    catalog_sha256: str
    scope: str = "PROPR_DISPLAY_ONLY_NOT_ORDER_AUTHORIZED"

    @property
    def count(self) -> int:
        return len(self.native_symbols)


def load_propr_catalog(path: Path) -> MarketCatalog:
    if path.is_symlink() or not path.is_file():
        raise ValueError("PROPR_CATALOG_FILE_UNAVAILABLE")
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("PROPR_CATALOG_TOO_LARGE")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("PROPR_CATALOG_INVALID_JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema") != "paper_public_physical_sockets_v1":
        raise ValueError("PROPR_CATALOG_SCHEMA_MISMATCH")
    if doc.get("propr_order_ids_attested") is not False:
        raise ValueError("PROPR_CATALOG_ORDER_AUTHORITY_MISREPRESENTED")
    sha = doc.get("source_snapshot_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("PROPR_CATALOG_SNAPSHOT_SHA_INVALID")
    sockets = doc.get("physical_sockets")
    if not isinstance(sockets, list) or not sockets:
        raise ValueError("PROPR_CATALOG_SOCKETS_INVALID")
    native = []
    for socket in sockets:
        if not isinstance(socket, dict) or not isinstance(socket.get("instruments"), list):
            raise ValueError("PROPR_CATALOG_SOCKET_INVALID")
        for instrument in socket["instruments"]:
            if not isinstance(instrument, str) or not instrument.startswith("hyperliquid/mainnet:perp:"):
                raise ValueError("PROPR_CATALOG_INSTRUMENT_INVALID")
            prefix, sep, symbol = instrument.rpartition("/")
            if not sep or not symbol:
                raise ValueError("PROPR_CATALOG_INSTRUMENT_INVALID")
            dex = prefix.removeprefix("hyperliquid/mainnet:perp:")
            if dex == "default":
                value = symbol
            elif dex and dex.islower():
                value = f"{dex}:{symbol}"
            else:
                raise ValueError("PROPR_CATALOG_DEX_INVALID")
            if native_instrument(value) != instrument:
                raise ValueError("PROPR_CATALOG_NATIVE_ID_MISMATCH")
            native.append(value)
    if len(native) != len(set(native)):
        raise ValueError("PROPR_CATALOG_DUPLICATE_NATIVE_MARKET")
    if len(native) != doc.get("native_market_count"):
        raise ValueError("PROPR_CATALOG_MARKET_COUNT_MISMATCH")
    return MarketCatalog(
        frozenset(native), sha, sha256(raw).hexdigest()
    )
