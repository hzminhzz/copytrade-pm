"""Versioned, read-only Propr display universe for Vike market observations.

The display snapshot is not a broker tradability claim. Native IDs are
preserved and missing prices are explicitly reported by the collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

from .pm03_account import Instrument, clock, digest, number
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
            if not isinstance(instrument, str) or not instrument.startswith(
                "hyperliquid/mainnet:perp:"
            ):
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
    return MarketCatalog(frozenset(native), sha, sha256(raw).hexdigest())


# Official native contract resolution is independent of the Propr display and
# of current Vike prices. It confers no account-specific trading permission.
@dataclass(frozen=True)
class NativePaperContract:
    instrument: Instrument
    amount_step: Decimal
    minimum_notional: Decimal
    active: bool
    market_known_at: str
    catalog_sha: str
    hip3: bool
    provider_meta_sha: str = ""
    metadata_source: str = "OFFICIAL_HYPERLIQUID_META"
    min_notional_source: str = "ESTIMATED_PAPER_POLICY_NOT_VENUE_ATTESTED"

    @property
    def session_eligible(self) -> bool:
        # The latest traded Vike minute is checked separately at attempt time.
        # Official metadata existence is NOT independent HIP-3 session evidence.
        return self.active


def official_paper_contracts(
    selected_symbols: frozenset[str],
    *,
    observed_at: str,
    minimum_notional_usd: Decimal,
    info: Callable | None = None,
) -> dict[str, NativePaperContract]:
    """Resolve active native contracts from official /info meta, not quote heads.

    The minimum notional is an explicitly configured paper assumption. Do not
    treat this result as an exchange order-acceptance or session attestation.
    Missing/unlisted native symbols remain catalog identities, not permissions.
    """
    from .pm_e4_prospective import guarded_info

    clock(observed_at)
    minimum_notional = number(minimum_notional_usd)
    if not minimum_notional.is_finite() or minimum_notional <= 0:
        raise ValueError("VIKE_NATIVE_PAPER_MINIMUM_ASSUMPTION_INVALID")
    if not selected_symbols:
        raise ValueError("VIKE_NATIVE_PAPER_CATALOG_EMPTY")
    provider = info or guarded_info
    grouped: dict[str, set[str]] = {}
    for native in selected_symbols:
        if ":" in native:
            dex, _coin = native.split(":", 1)
        else:
            dex = "default"
        grouped.setdefault(dex, set()).add(native)

    contracts: dict[str, NativePaperContract] = {}
    for dex, names in sorted(grouped.items()):
        request = {"type": "meta"} if dex == "default" else {"type": "meta", "dex": dex}
        payload, raw, raw_sha = provider(request)
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("universe"), list)
            or not isinstance(raw, bytes)
            or sha256(raw).hexdigest() != raw_sha
        ):
            raise ValueError("VIKE_NATIVE_PAPER_OFFICIAL_META_INVALID")
        rows = {}
        for row in payload["universe"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise ValueError("VIKE_NATIVE_PAPER_OFFICIAL_META_ROW_INVALID")
            if row["name"] in rows:
                raise ValueError("VIKE_NATIVE_PAPER_OFFICIAL_META_DUPLICATE")
            rows[row["name"]] = row
        for native in sorted(names):
            row = rows.get(native)
            if row is None or row.get("isDelisted") is True:
                continue
            decimals = row.get("szDecimals")
            if type(decimals) is not int or not 0 <= decimals <= 15:
                raise ValueError("VIKE_NATIVE_PAPER_SIZE_PRECISION_UNKNOWN:" + native)
            inst = Instrument.parse(native_instrument(native))
            step = Decimal("1").scaleb(-decimals)
            contracts[inst.key] = NativePaperContract(
                instrument=inst,
                amount_step=step,
                minimum_notional=minimum_notional,
                active=True,
                market_known_at=observed_at,
                hip3=dex != "default",
                # Contract identity is local to the selected market: a new
                # unrelated venue listing must not invalidate this run.
                catalog_sha=digest(
                    [
                        inst.key,
                        str(step),
                        str(minimum_notional),
                        row.get("onlyIsolated"),
                        row.get("isDelisted", False),
                    ]
                ),
                provider_meta_sha=raw_sha,
            )
    return contracts
