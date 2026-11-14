"""Native REST candidates for the prospective CWSA policy; no financial authority.

The existing native read-only transport and original-wire sidecar own evidence.
A scheduled boundary identifies a collection window, never a backdated state time.
"""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Annotated, Callable, Literal
from urllib.error import HTTPError, URLError
import re

from pydantic import Field, model_validator

from .pm03_account import digest
from .pm_e4_prospective import _dex_universe, _guarded_info
from .pm_source_contracts import Contract, Position, Sha, exact_decimal
from .pm_v4_evidence import publish_wire

GRID_MS = 300_000
Milliseconds = Annotated[int, Field(ge=0)]


class CheckpointScope(Contract):
    schema_version: Literal[3] = 3
    source_id: Annotated[str, Field(min_length=1, max_length=100)]
    account_sha: Sha
    generation: Sha
    selection_sha: Sha
    dexes: tuple[str, ...]

    @model_validator(mode="after")
    def canonical_scope(self):
        if not self.dexes or len(self.dexes) > 32 or self.dexes != tuple(sorted(set(self.dexes))):
            raise ValueError("CHECKPOINT_SCOPE_INVALID")
        if "default" not in self.dexes:
            raise ValueError("CHECKPOINT_DEFAULT_SCOPE_REQUIRED")
        if any(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", dex) is None for dex in self.dexes):
            raise ValueError("CHECKPOINT_DEX_NAMESPACE_INVALID")
        return self


class SamplingLimits(Contract):
    # No numerical defaults: fixture values are not empirical policy approval.
    max_state_age_ms: Annotated[int, Field(gt=0)]
    max_acquisition_ms: Annotated[int, Field(gt=0)]
    max_dex_skew_ms: Annotated[int, Field(ge=0)]
    publication_grace_ms: Annotated[int, Field(gt=0, lt=GRID_MS)]


class NativeRequest(Contract):
    type: Literal["perpDexs", "clearinghouseState"]
    user: str | None = None
    dex: str | None = None


class NativeReceipt(Contract):
    dex: str
    raw_sha: Sha
    request_sha: Sha
    requested_ms: Milliseconds
    received_ms: Milliseconds
    state_ms: Milliseconds | None
    position_count: Annotated[int, Field(ge=0)] | None
    request: NativeRequest | None = None


class CheckpointSample(Contract):
    schema_version: Literal[3] = 3
    kind: Literal["COMPLETE", "UNAVAILABLE"]
    scope: CheckpointScope
    checkpoint_ms: Milliseconds
    started_ms: Milliseconds
    received_ms: Milliseconds
    validated_ms: Milliseconds
    catalog: NativeReceipt | None
    receipts: tuple[NativeReceipt, ...]
    positions: tuple[Position, ...]
    limits: SamplingLimits | None
    reasons: tuple[str, ...]
    financial_authority: Literal["NONE"] = "NONE"

    @property
    def economic_sha(self) -> str:
        from .pm_source_contracts import quantity_text

        return digest(
            [
                self.scope.generation,
                {p.instrument: quantity_text(p.quantity) for p in self.positions},
            ]
        )


def selected_checkpoint_sources(
    registry_db: Path, *, portfolios: tuple[str, ...], as_of: str, dexes: tuple[str, ...]
) -> dict[str, tuple[CheckpointScope, str]]:
    """Use the existing sealed SQLite reader; a follower revision is not a source epoch."""
    from .pm_source_selection import selected_parents

    parents = selected_parents(registry_db, portfolios=portfolios, as_of=as_of)
    selection_sha = digest(
        {alias: sha256(address.encode()).hexdigest() for alias, address in parents.items()}
    )
    return {
        alias: (
            CheckpointScope(
                source_id=alias,
                account_sha=sha256(address.encode()).hexdigest(),
                generation=digest(["hyperliquid/mainnet:perp", address, dexes]),
                selection_sha=selection_sha,
                dexes=dexes,
            ),
            address,
        )
        for alias, address in parents.items()
    }


def utc_milliseconds() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def collect_checkpoint(
    scope: CheckpointScope,
    address: str,
    *,
    checkpoint_ms: int,
    limits: SamplingLimits | None,
    evidence_root: Path,
    info: Callable = _guarded_info,
    now_ms: Callable[[], int] = utc_milliseconds,
) -> CheckpointSample:
    """Collect once. Callers own scheduling; failures never imply a flat book."""
    if type(checkpoint_ms) is not int or checkpoint_ms < 0 or checkpoint_ms % GRID_MS:
        raise ValueError("CHECKPOINT_UTC_BOUNDARY_REQUIRED")
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", address) is None:
        raise ValueError("CHECKPOINT_ACCOUNT_FORMAT")
    if sha256(address.lower().encode()).hexdigest() != scope.account_sha:
        raise ValueError("CHECKPOINT_ACCOUNT_MISMATCH")
    evidence_root = Path(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if evidence_root.is_symlink() or evidence_root.stat().st_mode & 0o077:
        raise ValueError("CHECKPOINT_EVIDENCE_NOT_PRIVATE")
    started = now_ms()
    catalog = None
    receipts = []
    positions: dict[str, Decimal] = {}
    errors = []
    originals = {}

    def fetch(request, dex):
        requested = now_ms()
        _normalized, raw, claimed = info(request)
        received = now_ms()
        actual = sha256(raw).hexdigest()
        publish_wire(evidence_root / "paper-events.sqlite3", raw.decode("utf-8"), actual)
        receipt = NativeReceipt(
            dex=dex,
            raw_sha=actual,
            request_sha=digest(request),
            requested_ms=requested,
            received_ms=received,
            state_ms=None,
            position_count=None,
            request=NativeRequest(**request),
        )
        originals[dex] = receipt
        if claimed != actual:
            raise ValueError("CHECKPOINT_RAW_HASH_MISMATCH")
        body = json.loads(raw)
        return body, receipt

    def failure(exc):
        if isinstance(exc, HTTPError):
            exc.close()
            return f"CHECKPOINT_HTTP_{exc.code}"
        if isinstance(exc, (TimeoutError, URLError)):
            return "CHECKPOINT_TRANSPORT_UNAVAILABLE"
        return "CHECKPOINT_NATIVE_INVALID"

    try:
        body, catalog = fetch({"type": "perpDexs"}, "catalog")
        if tuple(sorted(_dex_universe(body))) != scope.dexes:
            errors.append("CHECKPOINT_SCOPE_CENSUS_MISMATCH")
    except (ValueError, TypeError, KeyError, HTTPError, URLError, TimeoutError) as exc:
        errors.append(failure(exc))
    for dex in scope.dexes:
        request = {"type": "clearinghouseState", "user": address.lower()}
        if dex != "default":
            request["dex"] = dex
        try:
            body, receipt = fetch(request, dex)
            receipts.append(receipt)
            if not isinstance(body, dict) or not isinstance(body.get("assetPositions"), list):
                raise ValueError("CHECKPOINT_EXPLICIT_POSITIONS_REQUIRED")
            if "user" in body and body["user"] != address.lower():
                raise ValueError("CHECKPOINT_NATIVE_ACCOUNT_MISMATCH")
            if "dex" in body and (body["dex"] or "default") != dex:
                raise ValueError("CHECKPOINT_NATIVE_DEX_MISMATCH")
            if type(body.get("time")) is not int or body["time"] <= 0:
                raise ValueError("CHECKPOINT_NATIVE_TIME_REQUIRED")
            seen = set()
            dex_positions = {}
            for row in body["assetPositions"]:
                position = row["position"]
                coin = position["coin"]
                if not isinstance(coin, str) or (
                    dex != "default" and not coin.startswith(dex + ":")
                ):
                    raise ValueError("CHECKPOINT_NATIVE_NAMESPACE_MISMATCH")
                name = coin if dex == "default" else coin[len(dex) + 1 :]
                key = f"hyperliquid/mainnet:perp:{dex}/{name}"
                quantity = exact_decimal(position["szi"])
                validated_position = Position(instrument=key, quantity=quantity)
                if key in seen:
                    raise ValueError("CHECKPOINT_DUPLICATE_POSITION")
                if quantity:
                    dex_positions[key] = validated_position.quantity
                seen.add(key)
            receipts[-1] = NativeReceipt(
                **{
                    **receipt.model_dump(),
                    "state_ms": body["time"],
                    "position_count": len(dex_positions),
                }
            )
            positions.update(dex_positions)
        except (ValueError, TypeError, KeyError, HTTPError, URLError, TimeoutError) as exc:
            errors.append(dex + ":" + failure(exc))
    catalog = catalog or originals.get("catalog")
    observed = {r.dex: r for r in receipts}
    receipts = [observed.get(dex, originals[dex]) for dex in scope.dexes if dex in originals]
    validated = now_ms()
    received = max(
        (r.received_ms for r in ([catalog] if catalog else []) + receipts), default=validated
    )
    all_receipts = ([catalog] if catalog else []) + receipts
    if started < checkpoint_ms or validated >= checkpoint_ms + GRID_MS:
        errors.append("CHECKPOINT_OUTSIDE_WINDOW")
    if validated < received or any(
        r.requested_ms < started or r.received_ms < r.requested_ms for r in all_receipts
    ):
        errors.append("CHECKPOINT_LOCAL_CLOCK_REGRESSION")
    stamps = [r.state_ms for r in receipts if r.state_ms is not None]
    if any(r.state_ms is not None and r.state_ms > r.received_ms for r in receipts):
        errors.append("CHECKPOINT_FUTURE_SOURCE_TIME")
    if limits is None:
        errors.append("CHECKPOINT_UNQUALIFIED_LIMITS")
    else:
        if validated - started > limits.max_acquisition_ms:
            errors.append("CHECKPOINT_ACQUISITION_EXPIRED")
        if validated >= checkpoint_ms + limits.publication_grace_ms:
            errors.append("CHECKPOINT_PUBLICATION_EXPIRED")
        if stamps and validated - min(stamps) > limits.max_state_age_ms:
            errors.append("CHECKPOINT_SOURCE_STALE")
        if stamps and max(stamps) - min(stamps) > limits.max_dex_skew_ms:
            errors.append("CHECKPOINT_DEX_SKEW")
    if errors:
        positions.clear()
    return CheckpointSample(
        kind="UNAVAILABLE" if errors else "COMPLETE",
        scope=scope,
        checkpoint_ms=checkpoint_ms,
        started_ms=started,
        received_ms=received,
        validated_ms=validated,
        catalog=catalog,
        receipts=tuple(receipts),
        positions=tuple(
            Position(instrument=key, quantity=qty) for key, qty in sorted(positions.items())
        ),
        limits=limits,
        reasons=tuple(errors),
    )
