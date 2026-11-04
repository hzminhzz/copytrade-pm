"""Private, versioned encoding of independently validated offline source and market tapes.

Deterministic structured envelopes serialize timezone-aware clocks as ISO-8601
and tuple source identities as named fields. These are *derived* cache inputs,
not a new source registry or a source provenance producer.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from .pm_offline_manifest import ManifestBlocked, ManifestInvalid

SOURCE_SCHEMA = "pm_offline_source_bundle_cache_v1"
MARKET_SCHEMA = "pm_offline_market_panel_cache_v1"


def _encode(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda x: x.isoformat() if isinstance(x, datetime) else _reject(x),
    ).encode()


def _reject(value: Any) -> None:
    raise ManifestInvalid("NON_SERIALIZABLE_CACHE_INPUT")


def source_bundle(
    source: dict,
    opening: dict[tuple[str, str], dict],
    original: dict[tuple[str, str, str, str], dict],
) -> bytes:
    return _encode(
        {
            "schema": SOURCE_SCHEMA,
            "source": source,
            "opening": [
                {"account": account, "dex": dex, "row": value}
                for (account, dex), value in sorted(opening.items())
            ],
            "original": [
                {
                    "account": account,
                    "dex": dex,
                    "instrument": market,
                    "event_id": event_id,
                    "row": row,
                }
                for (account, dex, market, event_id), row in sorted(original.items())
            ],
        }
    )


def read_source_bundle(raw: bytes) -> tuple[dict, dict, dict]:
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise ManifestBlocked("INVALID_SEALED_SOURCE_BUNDLE") from exc
    if (
        not isinstance(obj, dict)
        or set(obj) != {"schema", "source", "opening", "original"}
        or obj["schema"] != SOURCE_SCHEMA
        or not isinstance(obj["source"], dict)
        or not isinstance(obj["opening"], list)
        or not isinstance(obj["original"], list)
    ):
        raise ManifestBlocked("INVALID_SEALED_SOURCE_BUNDLE")
    opening = {}
    for item in obj["opening"]:
        if not isinstance(item, dict) or set(item) != {"account", "dex", "row"}:
            raise ManifestBlocked("INVALID_SEALED_OPENING_BOOK")
        key = item["account"], item["dex"]
        if key in opening or not isinstance(item["row"], dict):
            raise ManifestBlocked("CONFLICTING_SEALED_OPENING_BOOK")
        opening[key] = item["row"]
    original = {}
    for item in obj["original"]:
        if not isinstance(item, dict) or set(item) != {
            "account",
            "dex",
            "instrument",
            "event_id",
            "row",
        }:
            raise ManifestBlocked("INVALID_SEALED_SOURCE_EVENT")
        key = item["account"], item["dex"], item["instrument"], item["event_id"]
        if key in original or not isinstance(item["row"], dict):
            raise ManifestBlocked("CONFLICTING_SEALED_SOURCE_EVENT")
        original[key] = item["row"]
    return obj["source"], opening, original


def market_bundle(
    rows: list[dict],
    day_shas: dict[str, dict[str, str]],
) -> bytes:
    return _encode(
        {
            "schema": MARKET_SCHEMA,
            "rows": rows,
            "day_shas": day_shas,
        }
    )


def read_market_bundle(raw: bytes) -> tuple[list[dict], dict]:
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise ManifestBlocked("INVALID_SEALED_MARKET_PANEL") from exc
    if (
        not isinstance(obj, dict)
        or set(obj) != {"schema", "rows", "day_shas"}
        or obj["schema"] != MARKET_SCHEMA
        or not isinstance(obj["rows"], list)
        or not isinstance(obj["day_shas"], dict)
    ):
        raise ManifestBlocked("INVALID_SEALED_MARKET_PANEL")
    rows = obj["rows"]
    for item in rows:
        if (
            not isinstance(item, dict)
            or set(item) != {"at", "prices", "prior_volume", "updates"}
            or not isinstance(item["prices"], dict)
            or not isinstance(item["prior_volume"], dict)
            or item["updates"] != []
        ):
            raise ManifestBlocked("INVALID_SEALED_MARKET_PANEL_ROW")
        try:
            item["at"] = datetime.fromisoformat(item["at"])
        except (TypeError, ValueError) as exc:
            raise ManifestBlocked("INVALID_SEALED_MARKET_PANEL_CLOCK") from exc
        if item["at"].utcoffset() is None:
            raise ManifestBlocked("NAIVE_SEALED_MARKET_PANEL_CLOCK")
    return rows, obj["day_shas"]


def pinned_source_dependencies(doc: dict, *, policy_sha: str, software_sha: str) -> dict:
    entries = doc["sources"]
    digests = sorted(
        [
            {
                "account": x["account"],
                "dex": x["dex"],
                "instrument": x["instrument"],
                "book": x["book_sha256"],
                "equity": x["equity_sha256"],
                "receipt": x.get("receipt_sha256"),
            }
            for x in entries
        ],
        key=lambda x: (
            x["account"],
            x["dex"],
            x["instrument"],
            x["book"],
            x["equity"],
            x["receipt"] or "",
        ),
    )
    return {
        "source": sha256(_encode({"entries": digests})).hexdigest(),
        "software": software_sha,
        "clock": sha256(doc["clock_basis"].encode()).hexdigest(),
        "policy": policy_sha,
        "equity_age": sha256(str(doc["source_equity_max_age_minutes"]).encode()).hexdigest(),
    }


def pinned_market_dependencies(doc: dict, *, software_sha: str) -> dict:
    rows = sorted(
        (
            {
                "dex": x["dex"],
                "instrument": x["instrument"],
                "date": x["date"],
                "data_sha": x["sha256"],
                "sidecar_sha": x["metadata_sha256"],
            }
            for x in doc["market_days"]
        ),
        key=lambda x: (x["dex"], x["instrument"], x["date"]),
    )
    return {
        "source": sha256(_encode({"days": rows})).hexdigest(),
        "software": software_sha,
        "window": sha256(f"{doc['start']}/{doc['end']}".encode()).hexdigest(),
        "namespace": sha256(
            _encode({"markets": sorted((x["dex"], x["instrument"]) for x in doc["sources"])})
        ).hexdigest(),
    }
