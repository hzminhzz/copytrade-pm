"""Versioned offline research study manifest; no broker, account, or runtime authority.

Validation is deliberately independent of vendor-only fill schemas and of the
forward-paper registration/300-second scheduler. Financial simulation comes
only after all required provenance is validated.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "pm_offline_sweep_manifest_v1"
CLOCK_BASES = frozenset({"HISTORICAL_ORACLE", "PROSPECTIVE_FIRST_KNOWN"})
POLICY = "PER_FILL_ELIGIBILITY"
DELAYS = frozenset({0, 1, 2, 5, 10})
MODES = frozenset({"SCREEN_ONLY", "CERTIFIED"})
SHA = re.compile(r"^[0-9a-f]{64}$")
SYMBOL = re.compile(r"^[A-Za-z0-9_.-]+$")
DEXES = frozenset({"default", "xyz", "io", "para"})


class ManifestBlocked(ValueError):
    """Typed, fail-closed source or clock validation result."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.status = "BLOCKED"


class ManifestInvalid(ValueError):
    """Invalid schema or unsafe study configuration."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.status = "INVALID"


def _timestamp(text: Any) -> datetime:
    if not isinstance(text, str):
        raise ManifestInvalid("INVALID_CLOCK")
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ManifestInvalid("INVALID_CLOCK") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ManifestInvalid("NAIVE_CLOCK")
    return value.astimezone(UTC)


def _digest(value: Any) -> str:
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode()
    ).hexdigest()


def _sha(value: Any, name: str) -> None:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ManifestBlocked(f"MISSING_OR_INVALID_{name}_SHA")


def _keys(data: Any, expected: set[str], optional: set[str] = frozenset()) -> dict:
    if not isinstance(data, dict):
        raise ManifestInvalid("EXPECTED_OBJECT")
    if expected - data.keys() or data.keys() - (expected | optional):
        raise ManifestInvalid("MISSING_OR_UNKNOWN_FIELDS")
    return data


def _safe_file(root: Path, item: Any) -> Path:
    if not isinstance(item, str) or not item or item.startswith("/") or "\\" in item:
        raise ManifestInvalid("UNSAFE_PATH")
    path = Path(item)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ManifestInvalid("UNSAFE_PATH")
    target = root / path
    # Reject symlinked parents, even if the target currently resolves inside root.
    if any(
        parent.is_symlink()
        for parent in (target, *target.parents)
        if parent != root.parent and (parent == root or root in parent.parents)
    ):
        raise ManifestInvalid("SYMLINK_PATH")
    if not target.is_file():
        raise ManifestBlocked("MISSING_INPUT_FILE")
    if target.stat().st_mode & 0o002:
        raise ManifestInvalid("WORLD_WRITABLE_INPUT")
    return target


@dataclass(frozen=True)
class Study:
    manifest_sha256: str
    clock_basis: str
    delay_minutes: tuple[int, ...]
    mode: str
    sources: tuple[str, ...]
    start: datetime
    end: datetime
    cutoff: datetime
    payload: dict

    @classmethod
    def validate(cls, raw: Any, *, input_root: Path) -> Study:
        doc = _keys(
            raw,
            {
                "schema",
                "study_id",
                "start",
                "end",
                "selection_cutoff",
                "clock_basis",
                "policy",
                "delays_minutes",
                "mode",
                "sources",
                "market_days",
                "rulebook",
                "cost_model",
                "follower_initial_equity",
            },
        )
        if doc["schema"] != SCHEMA or doc["policy"] != POLICY:
            raise ManifestInvalid("UNSUPPORTED_MANIFEST_OR_POLICY")
        if not isinstance(doc["study_id"], str) or not SYMBOL.fullmatch(doc["study_id"]):
            raise ManifestInvalid("INVALID_STUDY_ID")
        start = _timestamp(doc["start"])
        end = _timestamp(doc["end"])
        cutoff = _timestamp(doc["selection_cutoff"])
        if not start < end or cutoff > start:
            raise ManifestInvalid("INVALID_STUDY_WINDOW_OR_CUTOFF")
        if doc["clock_basis"] not in CLOCK_BASES:
            raise ManifestInvalid("UNKNOWN_CLOCK_BASIS")
        if doc["mode"] not in MODES:
            raise ManifestInvalid("UNKNOWN_RESULT_MODE")
        delays = doc["delays_minutes"]
        if (
            not isinstance(delays, list)
            or not delays
            or any(type(x) is not int or x not in DELAYS for x in delays)
            or len(set(delays)) != len(delays)
        ):
            raise ManifestInvalid("INVALID_DELAY_SET")
        from decimal import Decimal, InvalidOperation

        try:
            equity = Decimal(str(doc["follower_initial_equity"]))
        except (InvalidOperation, ValueError) as exc:
            raise ManifestInvalid("INVALID_FOLLOWER_EQUITY") from exc
        if not equity.is_finite() or equity <= 0:
            raise ManifestInvalid("INVALID_FOLLOWER_EQUITY")
        root = Path(input_root).resolve(strict=True)
        entries = doc["sources"]
        if not isinstance(entries, list) or not entries:
            raise ManifestBlocked("MISSING_WHOLE_SOURCE_BOOK")
        identities = set()
        for source in entries:
            _keys(
                source,
                {
                    "account",
                    "dex",
                    "instrument",
                    "book_path",
                    "book_sha256",
                    "equity_path",
                    "equity_sha256",
                    "first_known_basis",
                },
                {"receipt_path", "receipt_sha256"},
            )
            identity = (source["account"], source["dex"], source["instrument"])
            if identity in identities:
                raise ManifestInvalid("DUPLICATE_SOURCE_IDENTITY")
            identities.add(identity)
            if not all(isinstance(x, str) and SYMBOL.fullmatch(x) for x in identity):
                raise ManifestInvalid("INVALID_SOURCE_IDENTITY")
            if source["dex"] not in DEXES:
                raise ManifestInvalid("UNSUPPORTED_DEX")
            if source["first_known_basis"] != doc["clock_basis"]:
                raise ManifestInvalid("CLOCK_BASIS_MISMATCH")
            if doc["clock_basis"] == "PROSPECTIVE_FIRST_KNOWN":
                if "receipt_path" not in source or "receipt_sha256" not in source:
                    raise ManifestBlocked("MISSING_INDEPENDENT_FIRST_KNOWN_RECEIPT")
                _sha(source["receipt_sha256"], "RECEIPT")
                receipt = _safe_file(root, source["receipt_path"])
                if sha256(receipt.read_bytes()).hexdigest() != source["receipt_sha256"]:
                    raise ManifestBlocked("RECEIPT_SHA_MISMATCH")
            for label in ("book", "equity"):
                _sha(source[f"{label}_sha256"], label.upper())
                path = _safe_file(root, source[f"{label}_path"])
                if sha256(path.read_bytes()).hexdigest() != source[f"{label}_sha256"]:
                    raise ManifestBlocked(f"{label.upper()}_SHA_MISMATCH")
        days = doc["market_days"]
        if not isinstance(days, list) or not days:
            raise ManifestBlocked("MISSING_NATIVE_MARKET_DAYS")
        ids = set()
        for row in days:
            _keys(row, {"dex", "instrument", "date", "path", "sha256"})
            key = (row["dex"], row["instrument"], row["date"])
            if key in ids:
                raise ManifestInvalid("DUPLICATE_MARKET_DAY")
            ids.add(key)
            if (
                row["dex"] not in DEXES
                or not isinstance(row["instrument"], str)
                or (not SYMBOL.fullmatch(row["instrument"]))
            ):
                raise ManifestInvalid("UNSUPPORTED_MARKET_IDENTITY")
            try:
                datetime.strptime(row["date"], "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                raise ManifestInvalid("INVALID_MARKET_DAY") from exc
            _sha(row["sha256"], "MARKET_DAY")
            if sha256(_safe_file(root, row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ManifestBlocked("MARKET_DAY_SHA_MISMATCH")
        for label in ("rulebook", "cost_model"):
            row = _keys(doc[label], {"path", "sha256"})
            _sha(row["sha256"], label.upper())
            if sha256(_safe_file(root, row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ManifestBlocked(f"{label.upper()}_SHA_MISMATCH")
        return cls(
            _digest(doc),
            doc["clock_basis"],
            tuple(sorted(delays)),
            doc["mode"],
            tuple(sorted(x["account"] for x in entries)),
            start,
            end,
            cutoff,
            doc,
        )


def inspect_manifest(path: Path, *, input_root: Path) -> dict:
    """Read-only high-level entrypoint; never runs a financial scenario."""
    try:
        raw = json.loads(path.read_text())
        study = Study.validate(raw, input_root=input_root)
    except (ManifestBlocked, ManifestInvalid) as exc:
        return {"status": exc.status, "reason": exc.code, "schema": SCHEMA}
    except OSError, ValueError, TypeError:
        return {"status": "INVALID", "reason": "INVALID_MANIFEST_JSON", "schema": SCHEMA}
    return {
        "status": "VALIDATED_INPUT_ONLY",
        "schema": SCHEMA,
        "manifest_sha256": study.manifest_sha256,
        "clock_basis": study.clock_basis,
        "mode": study.mode,
        "delays_minutes": list(study.delay_minutes),
        "source_accounts": len(set(study.sources)),
        "source_instruments": len(study.payload["sources"]),
        "native_market_days": len(study.payload["market_days"]),
        "financial_certified": False,
        "scientifically_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-closed offline study manifest inspection")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_manifest(args.manifest, input_root=args.input_root), sort_keys=True))


if __name__ == "__main__":
    main()
