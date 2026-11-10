"""Bounded official Hyperliquid public per-account all-DEX observation.

Uses existing E4 account parser and publicly documented WS/Info endpoints.
No broker orders, no source retro-reconstruction, no real whole-wallet
admission, no service deployment, and no parent/subaccount NAV netting.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from time import monotonic
from typing import Any, Callable

from .pm_e4_prospective import (
    MAX_BODY,
    PUBLIC_ACCOUNT_MODES,
    WS_URL,
    _guarded_info,
    _subaccount_roster,
)
from .pm03_account import clock, digest
from .pm_forward_stream_journal import StreamProgress
from .pm_forward_journal import PaperJournal
from .pm_forward_source_observation import append_public_scope, read_public_all_dex_scope
from .pm_source_contracts import canonical_source_book, decide_source_transition


ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
# Quote balances can collateralize perps in unified accounts. Do not treat
# non-quote spot assets as follower positions or estimate their USD value.
PERP_QUOTE_COLLATERAL = frozenset({"USDC", "USDH"})


def _perpetual_collateral_balances(balances: list) -> tuple[dict, int]:
    """Retain only native quote balances, never derive a sizing denominator."""
    quote: dict[str, dict[str, str | None]] = {}
    other = 0
    seen = set()
    for row in balances:
        if not isinstance(row, dict):
            raise ValueError("SOURCE_SPOT_BALANCE_ROW_INVALID")
        coin = row.get("coin")
        if not isinstance(coin, str) or not coin or coin in seen:
            raise ValueError("SOURCE_SPOT_BALANCE_COIN_INVALID")
        seen.add(coin)
        if coin not in PERP_QUOTE_COLLATERAL:
            other += 1
            continue
        try:
            total = Decimal(str(row.get("total")))
            hold = row.get("hold")
            held = None if hold is None else Decimal(str(hold))
        except InvalidOperation as exc:
            raise ValueError("SOURCE_SPOT_QUOTE_BALANCE_INVALID") from exc
        if not total.is_finite() or (held is not None and not held.is_finite()):
            raise ValueError("SOURCE_SPOT_QUOTE_BALANCE_NONFINITE")
        quote[coin] = {"total": str(total), "hold": str(held) if held is not None else None}
    return dict(sorted(quote.items())), other


async def discover_persistent_family(
    parents: dict[str, str], *, info=_guarded_info, now=lambda: datetime.now(UTC).isoformat()
) -> dict:
    """Acquire metadata once per unique parent; return explicit private identity.

    No NAV is derived. A missing/invalid child census fails this refresh; callers
    retain prior requirements and report UNKNOWN instead of treating it as flat.
    """
    from .pm_e4_prospective import _dex_universe

    if not parents or len(set(a.lower() for a in parents.values())) != len(parents):
        raise ValueError("SOURCE_FAMILY_PARENT_IDENTITY_DUPLICATE")
    if any(ADDRESS.fullmatch(address) is None for address in parents.values()):
        raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")

    async def fetch(request):
        payload, raw, sha = await asyncio.to_thread(info, request)
        known = now()
        if not isinstance(raw, bytes) or sha256(raw).hexdigest() != sha:
            raise ValueError("SOURCE_METADATA_RAW_SHA_MISMATCH")
        return payload, sha, known

    catalog, catalog_sha, catalog_known = await fetch({"type": "perpDexs"})
    _dex_universe(catalog)
    children = await asyncio.gather(
        *[fetch({"type": "subAccounts", "user": address}) for address in parents.values()]
    )
    accounts, proof = {}, {}
    seen = set()
    for (alias, address), (raw_subs, sha, known) in zip(parents.items(), children, strict=True):
        members = _subaccount_roster(raw_subs, address)
        for child in [address, *members]:
            canonical = child.lower()
            if canonical in seen:
                raise ValueError("SOURCE_FAMILY_SHARED_CHILD_AMBIGUOUS")
            seen.add(canonical)
            name = (
                alias
                if canonical == address.lower()
                else (alias + "_sub_" + sha256(canonical.encode()).hexdigest()[:12])
            )
            accounts[name] = {
                "address": canonical,
                "parent_alias": alias,
                "subaccounts": raw_subs if name == alias else None,
                "identity_sha": sha256(canonical.encode()).hexdigest(),
            }
        proof[alias] = {
            "subaccount_sha": sha,
            "first_known_at": known,
            "account_count": 1 + len(members),
        }
    scope = {
        "accounts": {
            alias: {"parent_alias": row["parent_alias"], "identity_sha": row["identity_sha"]}
            for alias, row in sorted(accounts.items())
        },
        "dex_catalog_sha": catalog_sha,
    }
    return {
        "accounts": accounts,
        "catalog": catalog,
        "catalog_sha": catalog_sha,
        "catalog_known_at": catalog_known,
        "parent_proofs": proof,
        "scope_sha": digest(scope),
        "scope": scope,
        "source_equity": None,
        "whole_wallet_equity_attested": False,
        "order_route": "NONE",
    }


class PersistentAccount:
    """Current per-account full-census state; snapshots never become trades.

    The existing strict parser requires every catalogued DEX and each DEX's
    assetPositions array. Delta-shaped/unknown envelopes are unsupported.
    Disappearance is an observed state difference, never a verified close.
    """

    def __init__(
        self,
        *,
        journal: PaperJournal,
        alias: str,
        address: str,
        dex_catalog: object,
        subaccounts: object,
        parent_alias: str,
        scope_sha: str,
        compact_evidence: bool = False,
    ):
        if ADDRESS.fullmatch(address) is None:
            raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")
        self.journal, self.alias, self.address = journal, alias, address.lower()
        self.dex_catalog, self.subaccounts = dex_catalog, subaccounts
        self.parent_alias, self.scope_sha = parent_alias, scope_sha
        self.compact_evidence = compact_evidence
        self.progress = StreamProgress(journal, "account:" + alias)
        self.account_scope_sha = self.progress.checkpoint.get(
            "account_scope_sha", digest(["selected_perp_scope_v2", self.address])
        )
        self.epoch = None
        # Validated but economically unchanged observations must not advance
        # immutable source receipts or stream hash heads. This projection is
        # intentionally lost on restart/reconnect, which requires a baseline.
        self._volatile_checkpoint: dict | None = None
        self._next_health_write = monotonic() + 30.0

    @property
    def checkpoint(self) -> dict:
        state = (
            dict(self._volatile_checkpoint)
            if self._volatile_checkpoint is not None
            else self.progress.checkpoint
        )
        if self.epoch is None:
            state["baseline_valid"] = False
        return state

    def begin(self, known_at: str, *, reason: str = "CONNECT_OR_PROCESS_RESTART") -> dict:
        from uuid import uuid4

        epoch = uuid4().hex
        self._volatile_checkpoint = None
        state = {
            **self.checkpoint,
            "baseline_valid": False,
            "transport": "CONNECTING",
            "subscription_acknowledged": False,
            "scope_sha": self.scope_sha,
            "parent_alias": self.parent_alias,
            "account_sha": sha256(self.address.encode()).hexdigest(),
            "source_equity": None,
            "last_transport_at": known_at,
            "gap_reason": reason,
        }
        event = self.progress.propose(
            epoch=epoch, kind="GAP", known_at=known_at, checkpoint=state, details={"reason": reason}
        )
        result = self.progress.commit(event)
        self.epoch = epoch
        return result

    def transport(self, known_at: str, *, status: str = "CONNECTED") -> dict:
        if self.progress.head["event"] and clock(known_at) <= clock(
            self.progress.head["event"]["first_known_at"]
        ):
            return {"status": "TRANSPORT_ALREADY_OBSERVED", "order_route": "NONE"}
        if self.epoch is None:
            raise ValueError("SOURCE_EPOCH_NOT_STARTED")
        state = {**self.checkpoint, "transport": status, "last_transport_at": known_at}
        return self.progress.commit(
            self.progress.propose(
                epoch=self.epoch,
                kind="TRANSPORT",
                known_at=known_at,
                checkpoint=state,
            )
        )

    def gap(self, known_at: str, reason: str, *, frame=None, raw_sha=None, raw_text=None) -> dict:
        if frame is not None or raw_text is not None:
            from .pm_source_contracts import SourceObservationRejected

            self._quarantine(
                frame,
                known_at,
                raw_sha,
                raw_text,
                SourceObservationRejected(reason),
            )
            return {"status": "SOURCE_QUARANTINED", "order_route": "NONE"}
        self._volatile_checkpoint = None
        state = {
            **self.checkpoint,
            "baseline_valid": False,
            "transport": "DEGRADED",
            "gap_reason": reason,
        }
        return self.progress.commit(
            self.progress.propose(
                epoch=self.epoch,
                kind="GAP",
                known_at=known_at,
                checkpoint=state,
                details={"reason": reason},
            )
        )

    def reconfigure(
        self,
        *,
        dex_catalog: object,
        observer_generation: str,
        known_at: str,
        contract_generation: str | None = None,
    ) -> None:
        """Metadata refresh does not itself reset an unchanged account.

        An explicitly changed native contract fences this account only. Census
        additions with positions are detected by the pure reducer on the first
        complete replacement; empty unrelated DEX additions remain unchanged.
        """
        from .pm_e4_prospective import _dex_universe

        _dex_universe(dex_catalog)
        if contract_generation is not None:
            if re.fullmatch(r"[0-9a-f]{64}", contract_generation) is None:
                raise ValueError("SOURCE_SCOPE_GENERATION_INVALID")
            if contract_generation != self.account_scope_sha:
                self._volatile_checkpoint = None
                state = {
                    **self.checkpoint,
                    "baseline_valid": False,
                    "transport": "DEGRADED",
                    "gap_reason": "SELECTED_ACCOUNT_SCOPE_CHANGED",
                    "account_scope_sha": contract_generation,
                }
                self.progress.commit(
                    self.progress.propose(
                        epoch=self.epoch,
                        kind="SCOPE",
                        known_at=known_at,
                        checkpoint=state,
                        details={"reason": "SELECTED_ACCOUNT_SCOPE_CHANGED"},
                    )
                )
                self.account_scope_sha = contract_generation
        self.dex_catalog, self.scope_sha = dex_catalog, observer_generation

    def _quarantine(self, frame, known_at, raw_sha, raw_text, rejected) -> None:
        # Any rejected frame fences previously accepted volatile continuity.
        self._volatile_checkpoint = None
        state = self.checkpoint
        count = state.get("consecutive_rejections", 0)
        if count >= 16:
            # The durable fence already exists. Bound a hostile frame flood;
            # no repeated reconnect or unbounded rejected payload writes.
            return
        from .pm_source_contracts import utc_clock

        try:
            stamp = utc_clock(known_at)
            previous = self.progress.head["event"]
            if stamp > datetime.now(UTC) or (
                previous and stamp < clock(previous["first_known_at"])
            ):
                raise ValueError("SOURCE_INVALID_LOCAL_CLOCK")
            gap_at = known_at
        except TypeError, ValueError:
            gap_at = datetime.now(UTC).isoformat(timespec="microseconds")
        diagnostic = json.dumps(frame, sort_keys=True, default=lambda _: "<non-json-value>")
        wire = raw_text if isinstance(raw_text, str) else None
        fingerprint = (
            sha256(wire.encode()).hexdigest()
            if wire is not None
            else raw_sha
            if isinstance(raw_sha, str) and re.fullmatch(r"[0-9a-f]{64}", raw_sha)
            else digest(diagnostic)
        )
        details = {
            "reason": rejected.availability.reason,
            "availability": rejected.availability.model_dump(mode="json"),
            "provided_first_known_at": known_at if isinstance(known_at, str) else None,
            "claimed_raw_sha": raw_sha if isinstance(raw_sha, str) and len(raw_sha) == 64 else None,
            "native_wire": wire if wire is not None and len(wire.encode()) <= 65536 else None,
            "diagnostic_frame_json": diagnostic[:65536] if wire is None else None,
            "raw_evidence_status": (
                "ORIGINAL_WIRE"
                if wire is not None and len(wire.encode()) <= 65536
                else "HASH_ONLY_OVERSIZED_QUARANTINE"
                if wire is not None
                else "DERIVED_DIAGNOSTIC"
            ),
        }
        state = {
            **state,
            "baseline_valid": False,
            "transport": "QUARANTINED",
            "gap_reason": rejected.availability.reason,
            "consecutive_rejections": count + 1,
            "quarantine_budget_exhausted": count + 1 >= 16,
        }
        self.progress.commit(
            self.progress.propose(
                epoch=self.epoch,
                kind="GAP",
                known_at=gap_at,
                checkpoint=state,
                raw_sha=fingerprint,
                details=details,
            )
        )

    def _validated_observation(self, frame, known_at, raw_sha):
        body = frame.get("data") if isinstance(frame, dict) else None
        if (
            not isinstance(body, dict)
            or set(frame) - {"channel", "data", "isSnapshot"}
            or ("isSnapshot" in frame and type(frame["isSnapshot"]) is not bool)
            or ("isSnapshot" in body and type(body["isSnapshot"]) is not bool)
            or set(body) - {"user", "clearinghouseStates", "isSnapshot"}
        ):
            raise ValueError("SOURCE_FRAME_REPLACEMENT_SEMANTICS_UNKNOWN")
        try:
            receipt = read_public_all_dex_scope(
                alias=self.parent_alias,
                address=self.address,
                frame=frame,
                dex_catalog=self.dex_catalog,
                discovered_subaccounts=self.subaccounts,
                first_known_at=known_at,
            )
        except (ArithmeticError, KeyError, TypeError) as exc:
            raise ValueError("SOURCE_NATIVE_CRITICAL_INVALID") from exc
        prior = self.checkpoint
        canonical = canonical_source_book(
            frame=frame,
            receipt=receipt,
            raw_sha=raw_sha or digest(frame),
            scope_generation=self.account_scope_sha,
        )
        semantic_sha = digest({key: value for key, value in body.items() if key != "isSnapshot"})
        decision = decide_source_transition(
            canonical,
            previous=prior,
            snapshot=body.get("isSnapshot", False) or frame.get("isSnapshot", False),
            frame_semantic_sha=semantic_sha,
        )
        return receipt, canonical, decision, semantic_sha

    def _persist_bounded_health(
        self, *, known_at: str, source_at: str, clocks: dict, position_sha: str
    ) -> None:
        """Non-economic liveness only; never changes stream or receipt heads."""
        now = monotonic()
        if now < self._next_health_write:
            return
        # A busy health writer is diagnostic loss, not an invented source GAP.
        # Retry no faster than the normal bounded interval.
        self._next_health_write = now + 30.0
        try:
            with closing(sqlite3.connect(self.journal.path, timeout=0.2)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute(
                    "INSERT INTO observer_source_health VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(stream_id) DO UPDATE SET "
                    "epoch=excluded.epoch,validated_at=excluded.validated_at,"
                    "source_event_at=excluded.source_event_at,dex_clocks=excluded.dex_clocks,"
                    "position_sha=excluded.position_sha,transport=excluded.transport",
                    (
                        "account:" + self.alias,
                        self.epoch,
                        known_at,
                        source_at,
                        json.dumps(clocks, sort_keys=True),
                        position_sha,
                        "CONNECTED",
                    ),
                )
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorcode", None) not in (
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            ):
                raise

    def observe(
        self, frame: dict, known_at: str, *, raw_sha: str | None = None, raw_text: str | None = None
    ) -> dict:
        if self.epoch is None:
            raise ValueError("SOURCE_EPOCH_NOT_STARTED")
        from .pm_source_contracts import source_rejection, utc_clock

        try:
            if utc_clock(known_at) > datetime.now(UTC):
                raise ValueError("SOURCE_RECEIPT_IN_FUTURE")
            if raw_text is not None:
                if not isinstance(raw_text, str):
                    raise ValueError("SOURCE_NATIVE_WIRE_INVALID")

                def unique_fields(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("SOURCE_DUPLICATE_JSON_FIELD")
                        result[key] = value
                    return result

                if digest(json.loads(raw_text, object_pairs_hook=unique_fields)) != digest(frame):
                    raise ValueError("SOURCE_NATIVE_WIRE_FRAME_MISMATCH")
                actual_sha = sha256(raw_text.encode()).hexdigest()
                if raw_sha is not None and raw_sha != actual_sha:
                    raise ValueError("SOURCE_NATIVE_WIRE_SHA_MISMATCH")
                raw_sha = actual_sha
            receipt, canonical, decision, semantic_sha = self._validated_observation(
                frame,
                known_at,
                raw_sha,
            )
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            rejected = source_rejection(exc)
            self._quarantine(frame, known_at, raw_sha, raw_text, rejected)
            raise rejected from None
        canonical = decision.next_book
        prior, book = self.checkpoint, receipt["source_book"]
        clocks = {item.dex: item.milliseconds for item in canonical.clocks}
        classification = decision.observation.kind
        if classification in ("UNCHANGED_STATE", "DUPLICATE"):
            # The validated native clocks and semantic fingerprint still move
            # forward for subsequent regression/conflict detection, but no
            # journal event, receipt, T+300 signal or committed head is made.
            self._volatile_checkpoint = {
                **prior,
                "last_transport_at": known_at,
                "last_validated_at": known_at,
                "source_event_at": receipt["source_event_at"],
                "dex_clocks": clocks,
                "semantic_sha": semantic_sha,
                "economic_sha": canonical.economic_sha,
                "account_scope_sha": canonical.scope.generation,
            }
            self._persist_bounded_health(
                known_at=known_at,
                source_at=receipt["source_event_at"],
                clocks=clocks,
                position_sha=canonical.economic_sha,
            )
            return {
                "classification": classification,
                "signal_eligible": False,
                "position_changes": {},
                "status": "VALIDATED_VOLATILE_NO_SOURCE_WRITE",
                "order_route": "NONE",
            }
        positions = book["positions"]
        before = prior.get("positions", {})
        changes = {
            key: {
                "previous": before.get(key),
                "current": positions.get(key),
                "trade_verified": False,
            }
            for key in decision.observation.changed_instruments
        }
        receipt = {
            **receipt,
            "observation_kind": classification,
            "stream_epoch": self.epoch,
            # Only a continuous, complete official position replacement may
            # drive a prospective virtual-paper target. Observer admission
            # remains NO_TRADE and is not financial/broker authorization.
            "position_transition_eligible": classification == "OBSERVED_STATE_CHANGE",
            "signal_eligible": False,
        }
        state = {
            **prior,
            "baseline_valid": True,
            "transport": "CONNECTED",
            "last_transport_at": known_at,
            "last_state_at": known_at,
            "source_event_at": receipt["source_event_at"],
            "positions": positions,
            "dex_clocks": clocks,
            "semantic_sha": semantic_sha,
            "source_semantics_version": 2,
            "economic_sha": canonical.economic_sha,
            "account_scope_sha": canonical.scope.generation,
            "observer_generation": self.scope_sha,
            "scope_changed": decision.observation.scope_changed,
            "consecutive_rejections": 0,
            "quarantine_budget_exhausted": False,
            "position_margin_diagnostics": book["position_margin_diagnostics"],
            "discovered_subaccounts": book["subaccounts"],
            "source_equity": None,
            "scope_sha": self.scope_sha,
            "parent_alias": self.parent_alias,
            "last_receipt_sha": digest(receipt),
        }
        compact_v2 = self.compact_evidence and raw_text is not None
        if compact_v2:
            from .pm_v4_evidence import publish_wire

            # fsync and atomically publish the original bytes before any
            # SQLite receipt can reference them. A crash may leave an orphan,
            # but cannot leave a committed event referencing unflushed bytes.
            publish_wire(self.journal.path, raw_text, raw_sha)
        details = {
            "classification": classification,
            "position_changes": changes,
        }
        if compact_v2:
            details.update(
                native_frame_sha=receipt["source_sha"],
                native_wire_ref=raw_sha,
            )
        else:
            details.update(native_frame=frame, native_wire=raw_text)
        event = self.progress.propose(
            epoch=self.epoch,
            kind=decision.journal_kind,
            known_at=known_at,
            source_at=receipt["source_event_at"],
            checkpoint=state,
            raw_sha=raw_sha or digest(frame),
            details=details,
            compact_v2=compact_v2,
        )
        result = self.progress.commit(
            event,
            lambda progress: append_public_scope(
                self.journal,
                alias=self.parent_alias,
                seq=None,
                receipt=receipt,
                stream_event=progress,
            ),
        )
        self.account_scope_sha = canonical.scope.generation
        self._volatile_checkpoint = None
        return {
            **result,
            "classification": classification,
            "position_changes": changes,
            "signal_eligible": False,
            "order_route": "NONE",
        }


async def bounded_source_scope_capture(
    *,
    alias: str,
    address: str,
    journal: PaperJournal,
    seconds: float = 10,
    max_frames: int = 10,
    info: Callable = _guarded_info,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
) -> dict:
    if not isinstance(address, str) or ADDRESS.fullmatch(address) is None:
        raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")
    if not 2 <= seconds <= 60 or not 1 <= max_frames <= 100:
        raise ValueError("SOURCE_BOUNDED_SESSION_POLICY_INVALID")
    if connect is None:
        import websockets

        connect = websockets.connect

    # These are ONLY 2 current metadata requests, never historical fills.
    catalog, _, catalog_sha = await asyncio.to_thread(info, {"type": "perpDexs"})
    subaccounts, _, sub_sha = await asyncio.to_thread(
        info, {"type": "subAccounts", "user": address}
    )
    results = {
        "schema": "paper_public_scope_bounded_capture_v1",
        "wallet_alias": alias,
        "account_address_sha256": sha256(address.lower().encode()).hexdigest(),
        "dex_catalog_sha256": catalog_sha,
        "subaccount_discovery_sha256": sub_sha,
        "observed_subject": "PARENT_ONLY_NOT_ALL_SUBACCOUNTS",
        "complete_parent_subaccount_book": False,
        "whole_wallet_equity_attested": False,
        "paper_admitted": False,
        "paper_observed": False,
        "order_route": "NONE",
        "frames_received": 0,
        "per_account_receipts": 0,
        "snapshot_backfill_excluded": 0,
        "errors": [],
        "transport_status": "NOT_STARTED",
    }
    async with connect(
        WS_URL,
        open_timeout=12,
        close_timeout=5,
        ping_interval=15,
        ping_timeout=12,
        max_size=MAX_BODY,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "subscription": {"type": "allDexsClearinghouseState", "user": address},
                }
            )
        )
        results["transport_status"] = "CONNECTED_BOUNDED"
        started = monotonic()
        seen = set()
        while monotonic() - started < seconds and results["frames_received"] < max_frames:
            remaining = seconds - (monotonic() - started)
            try:
                wire = await asyncio.wait_for(ws.recv(), timeout=max(0.01, remaining))
            except TimeoutError:
                results["transport_status"] = "TIMEOUT_NOT_CONTINUOUS"
                break
            known = now()  # timestamp before JSON decoding or persistence
            results["frames_received"] += 1
            if not isinstance(wire, str) or len(wire.encode()) > MAX_BODY:
                results["errors"].append("SOURCE_FRAME_TOO_LARGE_OR_BINARY")
                break
            try:
                envelope = json.loads(wire)
                if not isinstance(envelope, dict):
                    raise ValueError("SOURCE_FRAME_NON_OBJECT")
                if envelope.get("channel") == "subscriptionResponse":
                    continue
                if envelope.get("channel") == "error":
                    raise ValueError("SOURCE_SUBSCRIPTION_REJECTED")
                if envelope.get("channel") != "allDexsClearinghouseState":
                    continue
                data = envelope.get("data")
                if not isinstance(data, dict):
                    raise ValueError("SOURCE_BOOK_NOT_OBJECT")
                if data.get("isSnapshot") is True:
                    # A provider-delivered historical snapshot is NOT a new
                    # first-known change; ignore for prospective signals.
                    results["snapshot_backfill_excluded"] += 1
                    continue
                receipt = read_public_all_dex_scope(
                    alias=alias,
                    address=address,
                    frame=envelope,
                    dex_catalog=catalog,
                    discovered_subaccounts=subaccounts,
                    first_known_at=known,
                )
                if receipt["source_sha"] in seen:
                    continue
                seen.add(receipt["source_sha"])
                seq = journal.source_status(alias)["cursor"] + 1
                result = append_public_scope(journal, alias=alias, seq=seq, receipt=receipt)
                if result.get("cursor") == seq:
                    results["per_account_receipts"] += 1
            except (ValueError, KeyError, TypeError) as exc:
                # Capture integrity failure blocks this source; never
                # substitute a guessed source_event_at or a zero book.
                results["errors"].append("SOURCE_CAPTURE_" + type(exc).__name__ + ":" + str(exc))
                break
    results["transport_status"] = (
        "BLOCKED_SCOPE_OR_SOURCE" if results["errors"] else "BOUNDED_SESSION_ENDED_NOT_CONTINUOUS"
    )
    results["source_cursor"] = journal.source_status(alias)["cursor"]
    return results


async def read_public_collateral_scope(
    *,
    address: str,
    info: Callable = _guarded_info,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
    perpetuals_only: bool = False,
) -> dict:
    """Read public collateral diagnostics, never synthesize a whole-wallet NAV.

    Perpetuals-only mode does not fetch vault investments. It still reads the
    spot clearinghouse because unified/portfolio-margin accounts hold their
    *perpetual collateral* in that balance, not independent per-DEX NAVs.
    """
    if type(perpetuals_only) is not bool:
        raise ValueError("SOURCE_PERPETUALS_ONLY_POLICY_INVALID")
    if ADDRESS.fullmatch(address) is None:
        raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")
    observations = []
    for request_type in ("spotClearinghouseState", "userVaultEquities"):
        if perpetuals_only and request_type == "userVaultEquities":
            observations.append(
                {
                    "scope": request_type,
                    "status": "OUT_OF_SCOPE_PERPETUALS_ONLY",
                    "first_known_at": None,
                    "source_event_at": None,
                    "response_sha256": None,
                    "row_count": None,
                }
            )
            continue
        try:
            payload, raw, response_sha = await asyncio.to_thread(
                info, {"type": request_type, "user": address}
            )
            first_known_at = now()
            if not isinstance(raw, bytes) or sha256(raw).hexdigest() != response_sha:
                raise ValueError("SOURCE_COLLATERAL_RAW_SHA_MISMATCH")
            if request_type == "spotClearinghouseState":
                if not isinstance(payload, dict) or not isinstance(payload.get("balances"), list):
                    raise ValueError("SOURCE_SPOT_SCOPE_RESPONSE_INVALID")
                count = len(payload["balances"])
                quote_collateral = (
                    _perpetual_collateral_balances(payload["balances"]) if perpetuals_only else None
                )
            else:
                quote_collateral = None
                if not isinstance(payload, list):
                    raise ValueError("SOURCE_VAULT_SCOPE_RESPONSE_INVALID")
                count = len(payload)
            observations.append(
                {
                    "scope": request_type,
                    "status": "PARTIAL_PUBLIC_OBSERVATION",
                    "first_known_at": first_known_at,
                    "source_event_at": None,
                    "response_sha256": response_sha,
                    "row_count": count,
                    **(
                        {
                            "potential_perp_quote_collateral": quote_collateral[0],
                            "other_spot_asset_count": quote_collateral[1],
                        }
                        if quote_collateral is not None
                        else {}
                    ),
                }
            )
        except (ValueError, TypeError, KeyError, OSError) as exc:
            observations.append(
                {
                    "scope": request_type,
                    "status": "BLOCKED_SCOPE_ACQUISITION",
                    "first_known_at": None,
                    "source_event_at": None,
                    "response_sha256": None,
                    "row_count": None,
                    "reason": type(exc).__name__ + ":" + str(exc)[:100],
                }
            )
    # The official abstraction mode determines whether per-DEX accountValue
    # can represent separate collateral. Never derive whole-wallet NAV here:
    # spot/vault and parent/child requests have no atomic exchange clock.
    account_abstraction = {
        "status": "BLOCKED_ACCOUNT_MODE_ACQUISITION",
        "mode": None,
        "first_known_at": None,
        "source_event_at": None,
        "response_sha256": None,
        "source_signed": False,
    }
    try:
        value, raw, response_sha = await asyncio.to_thread(
            info, {"type": "userAbstraction", "user": address}
        )
        first_known_at = now()
        if (
            type(value) is not str
            or value not in PUBLIC_ACCOUNT_MODES
            or not isinstance(raw, bytes)
            or sha256(raw).hexdigest() != response_sha
            or json.loads(raw) != value
        ):
            raise ValueError("SOURCE_ACCOUNT_MODE_PROVIDER_RESPONSE_INVALID")
        account_abstraction = {
            "status": "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED",
            "mode": value,
            "first_known_at": first_known_at,
            "source_event_at": None,
            "response_sha256": response_sha,
            "source_signed": False,
        }
    except (ValueError, TypeError, KeyError, OSError) as exc:
        account_abstraction["reason"] = type(exc).__name__ + ":" + str(exc)[:90]
    return {
        "schema": "paper_public_collateral_scope_v1",
        **({"copy_scope": "PERPETUALS_ONLY"} if perpetuals_only else {}),
        "account_address_sha256": sha256(address.lower().encode()).hexdigest(),
        "observations": observations,
        "account_abstraction": account_abstraction,
        "provider_atomic_nav_available": False,
        "source_equity": None,
        "collateral_reconciled": False,
        "status": (
            "BLOCKED_PERPETUAL_COLLATERAL_RECONCILIATION"
            if perpetuals_only
            else "BLOCKED_COLLATERAL_AND_VAULT_RECONCILIATION"
        ),
        "paper_observed": False,
        "order_route": "NONE",
    }


async def bounded_source_family_capture(
    *,
    alias: str,
    parent_address: str,
    journal: PaperJournal,
    seconds_per_account: float = 5,
    max_frames: int = 10,
    include_collateral: bool = False,
    info: Callable = _guarded_info,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(),
) -> dict:
    """Inspect parent and discovered subaccounts sequentially, never claim atomic NAV.

    A subaccount roster is point-in-time metadata, not an immutable guarantee
    against newly created or removed accounts while this sweep is running.
    Different account WS receipts have different receive clocks; combining
    their collateral or hedge positions into a synthetic NAV is forbidden.
    """
    if ADDRESS.fullmatch(parent_address) is None:
        raise ValueError("SOURCE_PUBLIC_WALLET_ADDRESS_INVALID")
    roster_raw, _, roster_sha = await asyncio.to_thread(
        info, {"type": "subAccounts", "user": parent_address}
    )
    subs = _subaccount_roster(roster_raw, parent_address)
    addresses = [parent_address, *subs]
    observations = []
    for index, address in enumerate(addresses):
        subject = "PARENT" if index == 0 else "SUBACCOUNT"
        try:
            result = await bounded_source_scope_capture(
                alias=alias,
                address=address,
                journal=journal,
                seconds=seconds_per_account,
                max_frames=max_frames,
                info=info,
                connect=connect,
                now=now,
            )
            observations.append(
                {
                    "subject": subject,
                    "account_address_sha256": result["account_address_sha256"],
                    "transport_status": result["transport_status"],
                    "partial_receipts": result["per_account_receipts"],
                    "errors": result["errors"],
                }
            )
        except Exception as exc:
            observations.append(
                {
                    "subject": subject,
                    "account_address_sha256": sha256(address.lower().encode()).hexdigest(),
                    "transport_status": "BLOCKED_SOURCE_ACQUISITION",
                    "partial_receipts": 0,
                    "errors": [type(exc).__name__ + ":" + str(exc)[:130]],
                }
            )
    collateral = []
    if include_collateral:
        for address in addresses:
            diagnostic = await read_public_collateral_scope(
                address=address, info=info, now=now, perpetuals_only=True
            )
            try:
                diagnostic["receipt"] = journal.append_collateral_diagnostic(diagnostic)
            except ValueError as exc:
                diagnostic["persist_error"] = type(exc).__name__ + ":" + str(exc)[:110]
                diagnostic["status"] = "BLOCKED_COLLATERAL_RECEIPT_PERSISTENCE"
            collateral.append(diagnostic)
    return {
        "schema": "paper_public_family_bounded_capture_v1",
        "copy_scope": "PERPETUALS_ONLY",
        "collateral_diagnostics": collateral,
        "wallet_alias": alias,
        "parent_address_sha256": sha256(parent_address.lower().encode()).hexdigest(),
        "subaccount_discovery_sha256": roster_sha,
        "discovered_subaccount_count": len(subs),
        "expected_account_count": len(addresses),
        "observed_account_count": sum(x["partial_receipts"] > 0 for x in observations),
        "accounts": observations,
        "source_cursor": journal.source_status(alias)["cursor"],
        "parent_subaccount_census_atomic": False,
        "whole_wallet_equity_attested": False,
        "spot_vault_collateral_reconciled": False,
        "status": "BLOCKED_INCOMPLETE_WHOLE_WALLET",
        "paper_observed": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded public Hyperliquid per-account read-only observation; NO paper admission"
    )
    parser.add_argument("--alias", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--max-frames", type=int, default=10)
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        component in {".devspace", ".git"} for component in args.state_root.resolve().parts
    ):
        parser.error("source capture needs an absolute non-worktree private root")
    result = asyncio.run(
        bounded_source_scope_capture(
            alias=args.alias,
            address=args.address,
            journal=PaperJournal(args.state_root),
            seconds=args.seconds,
            max_frames=args.max_frames,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
