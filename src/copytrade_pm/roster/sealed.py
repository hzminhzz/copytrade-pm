"""Point-in-time roster identity and independent release attestation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import sqlite3
from typing import TYPE_CHECKING, Any

from copytrade_kernel import KnownAtTs

from .models import SeatBook, canonical, digest
from .proposals import ReleaseBinding, ReleaseProposal, _release_body
from .store import RosterStore, RosterStoreError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class SealedSelectionError(ValueError):
    """Public refusal for invalid selection or attestation evidence."""


def timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    delta = parsed - datetime(1970, 1, 1, tzinfo=UTC)
    return delta // timedelta(milliseconds=1)


@dataclass(frozen=True, slots=True)
class SealedRosterMember:
    account_id: str
    seat_id: str
    generation: int
    owner_id: str
    wallet: str
    identity_known_at_ms: int


@dataclass(frozen=True, slots=True)
class SealedRosterSelection:
    book: SeatBook
    members: tuple[SealedRosterMember, ...]
    definition_sha256: str
    attested: bool = False
    _approved_payload_json: str | None = None
    _binding_json: str | None = None

    @property
    def account_id(self) -> str:
        return self.book.account_id

    @property
    def version(self) -> int:
        return self.book.sequence

    @property
    def selection_known_at_ms(self) -> int:
        return self.book.as_of.value

    @property
    def trading_authorized(self) -> bool:
        return False

    @property
    def release_binding(self) -> ReleaseBinding | None:
        if self._binding_json is None:
            return None
        return ReleaseBinding.parse(json.loads(self._binding_json))

    @property
    def approved_payload(self) -> dict[str, Any]:
        if self._approved_payload_json is None:
            raise SealedSelectionError("SELECTION_ATTESTATION_MISSING")
        return json.loads(self._approved_payload_json)

    def metadata(self) -> dict[str, Any]:
        """Stable reviewer input. Appending the review cannot change its own digest."""
        binding = json.loads(self._binding_json) if self._binding_json is not None else None
        result = {
            "schema": "roster_sealed_selection_v1",
            "portfolio_id": self.account_id,
            "version": self.version,
            "asof_ms": self.selection_known_at_ms,
            "selection_known_at_ms": self.selection_known_at_ms,
            "sealed_definition_sha256": self.definition_sha256,
            "registry_inventory_sha256": self.book.sha,
            "decision_sha256": binding["decision_sha"] if binding else self.book.sha,
            "research_commit": binding["research_commit"] if binding else None,
            "release_binding_sha256": digest(binding) if binding else None,
            "members": [
                {
                    **asdict(member),
                    "pod_id": member.seat_id,
                    "source_identity": member.wallet,
                }
                for member in self.members
            ],
            "state": "BLOCKED",
            "blockers": ["SOURCE_POSITION_SCOPE_ATTESTATION_MISSING"],
            "batch_seconds": 300,
            "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
            "order_route": "NONE",
            "trading_authorized": False,
        }
        return {**result, "export_sha256": digest(result)}


def select_sealed_book(
    store: RosterStore,
    account_id: str,
    as_of_ms: int,
    *,
    reviewer: Ed25519PublicKey | None = None,
    source_observer: Ed25519PublicKey | None = None,
    require_attestation: bool = True,
) -> SealedRosterSelection:
    """Verify the committed book and its exact leases under one read snapshot."""
    return _select_at(
        store, account_id, as_of_ms, as_of_ms, reviewer, source_observer, require_attestation
    )


def _select_at(
    store: RosterStore,
    account_id: str,
    as_of_ms: int,
    now_ms: int,
    reviewer: Ed25519PublicKey | None,
    source_observer: Ed25519PublicKey | None,
    require_attestation: bool,
) -> SealedRosterSelection:
    try:
        cutoff = KnownAtTs(as_of_ms)
    except (TypeError, ValueError) as exc:
        raise SealedSelectionError("SELECTION_UNKNOWN_AT_ASOF") from exc
    with store.read_snapshot():
        try:
            book = store.verified_book_at(account_id, as_of=cutoff)
        except (
            RosterStoreError,
            sqlite3.Error,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
        ) as exc:
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT") from exc
        if book is None:
            raise SealedSelectionError("SELECTION_UNKNOWN_AT_ASOF")
        if not book.leases:
            raise SealedSelectionError("SELECTION_FLAT_NO_OCCUPIED_SEATS")
        leases = sorted(book.leases, key=lambda lease: lease.seat_id)
        members = tuple(
            SealedRosterMember(
                account_id,
                lease.seat_id,
                lease.generation,
                lease.owner,
                lease.wallet,
                lease.since_ms,
            )
            for lease in leases
        )
        definition = digest(
            {
                "schema": "roster_sealed_selection_v1",
                "book_sha": book.sha,
                "leases": [digest(lease.data) for lease in leases],
            }
        )
        try:
            binding = store.release_binding_at(account_id, now_ms=as_of_ms)
        except (RosterStoreError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT") from exc
        selection = SealedRosterSelection(
            book, members, definition, _binding_json=json.dumps(binding.data) if binding else None
        )
        if not require_attestation:
            return selection
        if reviewer is None or source_observer is None:
            raise SealedSelectionError("SELECTION_ATTESTATION_MISSING")
        return _verify_attestations(store, selection, reviewer, source_observer, now_ms)


def _verify_attestations(
    store: RosterStore,
    selection: SealedRosterSelection,
    reviewer: Ed25519PublicKey,
    source_observer: Ed25519PublicKey,
    now_ms: int,
) -> SealedRosterSelection:
    from ..production_manifest import _approved_release_payload, verify

    try:
        if reviewer.public_bytes_raw() == source_observer.public_bytes_raw():
            raise ValueError("SELECTION_ATTESTATION_KEYS_NOT_INDEPENDENT")
        row = store.policy_record_at(selection.account_id, now_ms=now_ms)
        if row is None:
            raise ValueError("SEALED_PRODUCTION_POLICY_MISSING")
        generation, known_at, envelope = row
        policy = verify(envelope, reviewer, "research-release-policy")
        if (
            type(policy["generation"]) is not int
            or policy["generation"] != generation
            or type(policy["created_at_ms"]) is not int
            or known_at < policy["created_at_ms"]
            or policy["account_binding"] != selection.account_id
        ):
            raise ValueError("POLICY_IDENTITY_OR_CLOCK_DRIFT")
        metadata = selection.metadata()
        approved = _approved_release_payload(
            metadata, policy, source_observer=source_observer, now_ms=now_ms
        )
        leases = {lease.seat_id: lease for lease in selection.book.leases}
        for member in approved["members"]:
            seat = member["pod_id"]
            if (
                member["account_scope"] != [leases[seat].wallet]
                or member["sizing_policy"] != "FIXED_K_NATIVE_QUANTITY"
                or Decimal(member["k"]) != leases[seat].k
                or Decimal(member["allocation"]) != selection.book.spec(seat).risk_unit_usd
            ):
                raise SealedSelectionError("SELECTION_MEMBER_DRIFT")
        binding = selection.release_binding
        if binding is not None and (
            binding.policy_epoch != selection.book.policy_epoch
            or approved["generation"] != binding.generation
            or approved["risk_policy_sha"] != binding.risk_policy_sha
            or approved["rulebook_sha"] != binding.rulebook_sha
            or approved["source_mode"] != binding.source_mode
            or approved["expires_at_ms"] > binding.expires_at_ms
            or any(
                tuple(member["allowed_markets"]) != binding.allowed_markets.get(member["pod_id"])
                for member in approved["members"]
            )
        ):
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT")
    except SealedSelectionError:
        raise
    except (
        RosterStoreError,
        sqlite3.Error,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as exc:
        if str(exc) in {
            "SEALED_MEMBERSHIP_DRIFT",
            "MEMBER_IDENTITY_UNKNOWN_AT_SEAL",
            "POLICY_OR_INVENTORY_DRIFT",
        }:
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT") from exc
        raise SealedSelectionError("SELECTION_ATTESTATION_MISSING") from exc
    return replace(selection, attested=True, _approved_payload_json=json.dumps(approved))


def verify_staged_selection(
    store: RosterStore,
    proposal: ReleaseProposal,
    *,
    now_ms: int,
    reviewer: Ed25519PublicKey,
    source_observer: Ed25519PublicKey,
) -> SealedRosterSelection:
    """Verify independent approval against the exact, current staged release.

    The staged body must be byte-for-byte what shared proposal construction
    derives from independently validated inputs — the verified book, the
    recorded binding and the recomputed roster inventory pin — so a staged row
    that carries a field the producer never derived (``definition_sha``,
    ``source_sha``, ``inventory_sha``, ``batch_seconds`` or any other byte the
    signer would cover) is refused before a signing key is opened.
    """
    with store.read_snapshot():
        saved = store.proposal(proposal.sha)
        selection = select_sealed_book(
            store, proposal.account_id, now_ms, reviewer=reviewer, source_observer=source_observer
        )
        approved = selection.approved_payload
        staged = proposal.payload_json
        binding = selection.release_binding
        staged_created = staged.get("created_at_ms")
        if (
            saved is None
            or saved.data != proposal.data
            or proposal.book_sha != selection.book.sha
            or binding is None
            or proposal.binding_sha != binding.sha
            or type(staged_created) is not int
            or staged_created != proposal.created_ms
            # The staged body is point-in-time: it cannot be created after the
            # verification clock even though the book and binding are current.
            or staged_created > now_ms
        ):
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT")
        try:
            expected = _release_body(
                selection.book,
                binding,
                inventory_sha=store.inventory_sha(),
                stamp=proposal.created_ms,
            )
        except (ValueError, TypeError, KeyError) as exc:
            # Includes the PIT and release-window checks re-derived from the
            # sealed book: a body built outside them was never constructed.
            raise SealedSelectionError("RELEASE_PROPOSAL_BODY_DRIFT") from exc
        if canonical(staged) != canonical(expected):
            raise SealedSelectionError("RELEASE_PROPOSAL_BODY_DRIFT")
        if any(
            staged[key] != approved[key]
            for key in (
                "generation",
                "account_binding",
                "source_mode",
                "research_commit",
                "decision_sha",
                "risk_policy_sha",
                "rulebook_sha",
                "expires_at_ms",
            )
        ) or sorted(staged["members"], key=lambda item: item["pod_id"]) != sorted(
            approved["members"], key=lambda item: item["pod_id"]
        ):
            raise SealedSelectionError("SELECTION_MEMBER_DRIFT")
        return selection
