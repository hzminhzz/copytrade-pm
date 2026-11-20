"""Handlers for the five ``copytrade-pm`` domain groups.

``facts``, ``research``, ``roster``, ``paper`` and ``release`` are one entry
point over the roster/fact authorities. Handlers print one JSON object and
return a process exit code; they never print a bare address unless the operator
passes ``--identities``, and they never print a private file's contents.

Offline signing verifies the staged release and its attestations before opening
a private key and uses the existing production manifest signature format.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Sequence

from copytrade_kernel import KnownAtTs

from .roster import (
    BenchCandidate,
    GateFailure,
    ReconcilerPolicy,
    ReleaseProposal,
    ReleaseBinding,
    RosterStore,
    SeatSpec,
    WalletScorecard,
    build_release_proposal,
    canonical,
    digest,
    finalise_payload,
    reconcile_roster,
    wallet_address,
)

__all__ = [
    "run_facts",
    "run_paper",
    "run_release",
    "run_research",
    "run_roster",
]


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _fail(code: str, reason: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "schema": "copytrade_cli_result_v1",
        "state": "BLOCKED",
        "error_code": code,
        "reason": reason,
        "trading_authorized": False,
    }
    payload.update(extra)
    return payload


def _emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, sort_keys=True, indent=2, default=str))
    return code


def _ms_from_iso(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return int(parsed.astimezone(UTC).timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def _public_key(path: str | Path):
    """Read one Ed25519 public key; a private key file is never accepted here."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    raw = Path(path).expanduser().read_bytes()
    if len(raw) != 32:
        raise ValueError("ED25519_PUBLIC_KEY_LENGTH")
    return Ed25519PublicKey.from_public_bytes(raw)


def _as_of(value: str | None) -> KnownAtTs:
    if value is None:
        return KnownAtTs(int(datetime.now(tz=UTC).timestamp() * 1000))
    return KnownAtTs(_ms_from_iso(value))


def _seats(values: Sequence[str]) -> tuple[SeatSpec, ...]:
    seats: list[SeatSpec] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError("SEAT_EXPECTS_ID:RISK_UNIT:MAX_CDAR")
        seats.append(SeatSpec(parts[0], Decimal(parts[1]), Decimal(parts[2])))
    if not seats:
        raise ValueError("AT_LEAST_ONE_SEAT_REQUIRED")
    return tuple(seats)


def _candidate(raw: str) -> BenchCandidate:
    parts = raw.split(":")
    if len(parts) != 6:
        raise ValueError("CANDIDATE_EXPECTS_WALLET:SHA:K:MARGINAL:CLUSTER:DISTANCE")
    return BenchCandidate(
        wallet=parts[0],
        scorecard_sha=parts[1],
        suggested_k=Decimal(parts[2]),
        marginal_cdar_share=Decimal(parts[3]),
        cluster_id=parts[4],
        cluster_distance=Decimal(parts[5]),
    )


def _redact(value: str) -> str:
    return "wallet:" + sha256(value.encode()).hexdigest()[:16]


def _seat_view(book: Any, *, identities: bool) -> dict[str, Any]:
    seats = []
    for spec, lease in book.seats:
        seats.append(
            {
                "seat_id": spec.seat_id,
                "risk_unit_usd": str(spec.risk_unit_usd),
                "max_cdar_share": str(spec.max_cdar_share),
                "occupancy": "VACANT" if lease is None else "OCCUPIED",
                "wallet": None
                if lease is None
                else (lease.wallet if identities else _redact(lease.wallet)),
                "owner": lease.owner if lease else None,
                "generation": lease.generation if lease else None,
                "k": str(lease.k) if lease else None,
                "since_ms": lease.since_ms if lease else None,
                "baseline_required": lease.baseline_required if lease else None,
            }
        )
    return {
        "schema": "roster_seat_view_v1",
        "account_id": book.account_id,
        "as_of_ms": book.as_of.value,
        "sequence": book.sequence,
        "policy_epoch": book.policy_epoch,
        "mode": book.mode.value,
        "occupied": book.occupied,
        "seats": seats,
        "draining_owners": list(book.draining_owners),
        "draining_wallets": [
            entry.wallet if identities else _redact(entry.wallet) for entry in book.draining
        ],
        "book_sha": book.sha,
        "trading_authorized": False,
    }


def _plan_view(plan: Any, *, identities: bool) -> dict[str, Any]:
    view = plan.data
    if identities:
        return view
    changes = []
    for change in view["changes"]:
        item = dict(change)
        if item.get("wallet"):
            item["wallet"] = _redact(item["wallet"])
        changes.append(item)
    view = dict(view, changes=changes)
    return view


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------


def run_facts(args: Any) -> int:
    """Delegate to the Slice 2 fact-store CLI handlers (one implementation)."""
    from . import pm_facts_cli as facts

    if args.verb == "capture-health":
        from . import wallet_health_official

        if not args.apply or args.dry_run:
            return _emit({"state": "DRY_RUN", "trading_authorized": False}, 0)
        return wallet_health_official.run(args)

    if args.verb == "benchmark" and not args.apply:
        return _emit(
            {
                "schema": "facts_benchmark_plan_v1",
                "state": "DRY_RUN",
                "wallets": args.wallets,
                "days": args.days,
                "rows_per_wallet_day": args.rows_per_wallet_day,
                "store": str(args.store) if args.store else None,
                "trading_authorized": False,
            },
            0,
        )
    handler = {
        "migrate": facts.cmd_migrate,
        "verify": facts.cmd_verify,
        "coverage": facts.cmd_coverage,
        "benchmark": facts.cmd_benchmark,
    }[args.verb]
    return int(handler(args))


# ---------------------------------------------------------------------------
# roster
# ---------------------------------------------------------------------------


def run_roster(args: Any) -> int:
    handlers = {
        "register": _roster_register,
        "show": _roster_show,
        "plan": _roster_plan,
        "commit": _roster_commit,
        "scorecard": _roster_scorecard,
        "bench": _roster_bench,
        "binding": _roster_binding,
        "veto": _roster_veto,
        "cusum": _roster_cusum,
        "proposal": _roster_proposal,
    }
    return handlers[args.verb](args)


def _roster_register(args: Any) -> int:
    if not args.apply:
        return _emit(
            {
                "schema": "roster_register_plan_v1",
                "state": "DRY_RUN",
                "account_id": args.account,
                "seats": [spec.data for spec in _seats(args.seat)],
                "policy_epoch": args.policy_epoch,
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, create=True, writable=True)
    try:
        account_sha = store.register_account(
            args.account, _seats(args.seat), policy_epoch=args.policy_epoch
        )
        return _emit(
            {
                "schema": "roster_register_receipt_v1",
                "state": "REGISTERED",
                "account_id": args.account,
                "account_sha": account_sha,
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _roster_show(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        book = store.book_at(args.account, as_of=_as_of(args.as_of))
        return _emit(_seat_view(book, identities=bool(args.identities)), 0)
    finally:
        store.close()


def _roster_plan(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        now = _as_of(args.as_of)
        book = store.book_at(args.account, as_of=now)
        plan = reconcile_roster(
            current=book,
            scorecard=store.latest_scorecard(as_of=now, policy_epoch=book.policy_epoch),
            bench=store.latest_bench(args.account, as_of=now),
            vetoes=store.active_vetoes(as_of=now),
            latches=_latches(store, book.policy_epoch, now),
            cooldowns=store.cooldowns(),
            policy=ReconcilerPolicy.sticky_pit_bench(),
            as_of=now,
        )
        return _emit(_plan_view(plan, identities=bool(args.identities)), 0)
    finally:
        store.close()


def _latches(store: RosterStore, epoch: str, as_of: KnownAtTs) -> dict[str, Any]:
    return {
        wallet: store.cusum_state(wallet, policy_epoch=epoch, as_of=as_of)
        for wallet in store.latched_wallets(policy_epoch=epoch, as_of=as_of)
    }


def _roster_commit(args: Any) -> int:
    store = RosterStore(args.store, writable=args.apply)
    try:
        now = _as_of(args.as_of)
        book = store.book_at(args.account, as_of=now)
        plan = reconcile_roster(
            current=book,
            scorecard=store.latest_scorecard(as_of=now, policy_epoch=book.policy_epoch),
            bench=store.latest_bench(args.account, as_of=now),
            vetoes=store.active_vetoes(as_of=now),
            latches=_latches(store, book.policy_epoch, now),
            cooldowns=store.cooldowns(),
            policy=ReconcilerPolicy.sticky_pit_bench(),
            as_of=now,
        )
        if not args.apply:
            return _emit(
                dict(
                    _plan_view(plan, identities=bool(args.identities)),
                    state="DRY_RUN",
                    would_change=plan.changed,
                ),
                0,
            )
        receipt = store.commit_plan(plan, committed_ms=now.value)
        return _emit(dict(receipt.data, state="COMMITTED"), 0)
    finally:
        store.close()


def _roster_scorecard(args: Any) -> int:
    scorecard = WalletScorecard(
        wallet=wallet_address(args.wallet),
        as_of=_as_of(args.as_of),
        account_value_usd=args.account_value,
        active_days_14d=args.active_days,
        markout_5m_bps=args.markout_bps,
        p95_participation_1m=args.participation,
        euler_cdar_share=args.cdar,
        suggested_k=args.k,
        cluster_id=args.cluster,
        copyable_drift=bool(args.copyable),
        failures=tuple(GateFailure(item) for item in args.failure or ()),
        source_sha=args.source_sha,
    )
    if not args.apply:
        return _emit(
            {
                "schema": "roster_scorecard_plan_v1",
                "state": "DRY_RUN",
                "scorecard_sha": scorecard.sha,
                "wallet": scorecard.wallet if args.identities else _redact(scorecard.wallet),
                "failures": [gate.value for gate in scorecard.failures],
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, create=True, writable=True)
    try:
        recorded = store.record_scorecard(scorecard)
        return _emit(
            {
                "schema": "roster_scorecard_receipt_v1",
                "state": "RECORDED",
                "scorecard_sha": recorded,
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _roster_bench(args: Any) -> int:
    candidates = tuple(_candidate(raw) for raw in args.candidate or ())
    if not args.apply:
        return _emit(
            {
                "schema": "roster_bench_plan_v1",
                "state": "DRY_RUN",
                "candidates": len(candidates),
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, create=True, writable=True)
    try:
        bench_sha = store.record_bench(args.account, candidates, as_of=_as_of(args.as_of))
        return _emit(
            {
                "schema": "roster_bench_receipt_v1",
                "state": "RECORDED",
                "bench_sha": bench_sha,
                "candidates": len(candidates),
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _roster_binding(args: Any) -> int:
    raw = json.loads(Path(args.file).expanduser().read_text())
    binding = ReleaseBinding.parse(raw)
    if not args.apply:
        return _emit(
            {
                "schema": "roster_binding_plan_v1",
                "state": "DRY_RUN",
                "account_id": binding.account_id,
                "generation": binding.generation,
                "binding_sha": binding.sha,
                "policy_epoch": binding.policy_epoch,
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, create=True, writable=True)
    try:
        recorded = store.record_release_binding(binding)
        return _emit(
            {
                "schema": "roster_binding_receipt_v1",
                "state": "RECORDED",
                "account_id": binding.account_id,
                "generation": binding.generation,
                "binding_sha": recorded,
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _roster_veto(args: Any) -> int:
    if not args.apply:
        return _emit(
            {
                "schema": "roster_veto_plan_v1",
                "state": "DRY_RUN",
                "wallet": _redact(wallet_address(args.wallet))
                if not args.identities
                else wallet_address(args.wallet),
                "revoke": bool(args.revoke),
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, writable=True)
    try:
        if args.revoke:
            revoked = store.revoke_veto(args.wallet, at_ms=args.at_ms)
            return _emit(
                {
                    "schema": "roster_veto_receipt_v1",
                    "state": "REVOKED" if revoked else "NO_ACTIVE_VETO",
                    "revoked": revoked,
                    "trading_authorized": False,
                },
                0,
            )
        veto = store.record_veto(
            args.wallet,
            reason=args.reason,
            actor=args.actor,
            at_ms=args.at_ms,
            expires_ms=args.expires_ms,
        )
        return _emit(
            {
                "schema": "roster_veto_receipt_v1",
                "state": "VETOED",
                "wallet": veto.wallet if args.identities else _redact(veto.wallet),
                "created_ms": veto.created_ms,
                "expires_ms": veto.expires_ms,
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _roster_cusum(args: Any) -> int:
    if not args.apply:
        return _emit(
            {
                "schema": "roster_cusum_plan_v1",
                "state": "DRY_RUN",
                "wallet": _redact(wallet_address(args.wallet)),
                "increment": args.increment,
                "threshold": args.threshold,
                "trading_authorized": False,
            },
            0,
        )
    store = RosterStore(args.store, writable=True)
    try:
        state = store.observe_cusum(
            args.wallet,
            args.increment,
            threshold=args.threshold,
            policy_epoch=args.epoch,
            at_ms=args.at_ms,
        )
        return _emit(
            dict(
                state.data,
                schema="roster_cusum_receipt_v1",
                state_label="LATCHED" if state.latched else "OPEN",
                trading_authorized=False,
            ),
            0,
        )
    finally:
        store.close()


def _roster_proposal(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        proposals = store.proposals(args.account)
        return _emit(
            {
                "schema": "roster_proposal_list_v1",
                "proposals": [
                    {
                        "account_id": item.account_id,
                        "day": item.day,
                        "generation": item.generation,
                        "proposal_sha": item.sha,
                        "members": len(item.payload_json.get("members", [])),
                        "created_ms": item.created_ms,
                    }
                    for item in proposals
                ],
                "count": len(proposals),
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------


def run_release(args: Any) -> int:
    handlers = {
        "propose": _release_propose,
        "sign": _release_sign,
        "verify": _release_verify,
        "export": _release_export,
    }
    return handlers[args.verb](args)


def _write_private(path: Path, payload: dict[str, Any]) -> str | None:
    """Create a new `0600` file; never overwrite, never follow a symlink.

    Returns ``None`` on success or a stable error code the caller reports.
    """
    parent = path.parent
    if (
        path.exists()
        or path.is_symlink()
        or parent.is_symlink()
        or not parent.is_dir()
        or parent.stat().st_mode & 0o077
    ):
        return "OUTPUT_REQUIRES_NEW_FILE_IN_PRIVATE_DIRECTORY"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(payload))
        stream.flush()
        os.fsync(stream.fileno())
    return None


def _release_propose(args: Any) -> int:
    now = _as_of(args.as_of)
    store = RosterStore(args.store, writable=args.apply)
    try:
        book = store.book_at(args.account, as_of=now)
        binding = store.release_binding(args.account)
        if binding is None:
            return _emit(
                _fail(
                    "RELEASE_BINDING_MISSING",
                    "record a release binding before proposing a release",
                    account_id=args.account,
                ),
                2,
            )
        plan = reconcile_roster(
            current=book,
            scorecard=store.latest_scorecard(as_of=now, policy_epoch=book.policy_epoch),
            bench=store.latest_bench(args.account, as_of=now),
            vetoes=store.active_vetoes(as_of=now),
            latches=_latches(store, book.policy_epoch, now),
            cooldowns=store.cooldowns(),
            policy=ReconcilerPolicy.sticky_pit_bench(),
            as_of=now,
        )
        if plan.changed:
            return _emit(
                _fail(
                    "ROSTER_NOT_RECONCILED",
                    "reconcile and commit the account before proposing a release",
                    plan_sha=plan.sha,
                ),
                2,
            )
        proposal = build_release_proposal(
            plan.next_book,
            binding,
            inventory_sha=store.inventory_sha(),
            plan_sha=plan.sha,
            created_ms=now.value,
        )
        if not args.apply:
            return _emit(
                {
                    "schema": "roster_release_proposal_plan_v1",
                    "state": "DRY_RUN",
                    "proposal_sha": proposal.sha,
                    "day": proposal.day,
                    "members": len(proposal.payload_json.get("members", [])),
                    "trading_authorized": False,
                },
                0,
            )
        staged = store.stage_proposal(proposal)
        if staged != proposal.sha:
            return _emit(
                _fail(
                    "PROPOSAL_ALREADY_STAGED_FOR_DAY",
                    "today's staged proposal differs from this body; sign the staged one",
                    proposal_sha=staged,
                ),
                2,
            )
        if args.out:
            staged_record = store.proposal_day(args.account, proposal.day)
            if staged_record is None or staged_record.sha != staged:
                return _emit(_fail("RELEASE_PROPOSAL_NOT_STAGED", "staged proposal unavailable"), 2)
            problem = _write_private(Path(args.out).expanduser(), staged_record.data)
            if problem:
                return _emit(_fail(problem, "proposal output requires a new private path"), 2)
        return _emit(
            {
                "schema": "roster_release_proposal_receipt_v1",
                "state": "STAGED",
                "proposal_sha": staged,
                "day": proposal.day,
                "generation": proposal.generation,
                "members": len(proposal.payload_json.get("members", [])),
                "output": str(args.out) if args.out else None,
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def _release_sign(args: Any) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from .production_manifest import sign
    from .roster.sealed import SealedSelectionError, verify_staged_selection

    try:
        raw = json.loads(Path(args.proposal).expanduser().read_text())
        proposal = ReleaseProposal.parse(raw)
    except KeyError, OSError, TypeError, ValueError:
        return _emit(
            _fail(
                "PROPOSAL_FILE_MUST_BE_A_STAGED_PROPOSAL",
                "pass the staged roster release proposal written by 'release propose'",
            ),
            2,
        )
    with RosterStore(args.store, writable=args.apply) as store:
        staged = store.proposal(proposal.sha)
        if staged is None or canonical(staged.data) != canonical(raw):
            return _emit(
                _fail("RELEASE_PROPOSAL_NOT_STAGED", "proposal must match the staged record"), 2
            )
        body = staged.payload_json
        if body.get("schema") != "portfolio_release_v2":
            return _emit(
                _fail(
                    "RELEASE_PROPOSAL_NOT_A_RELEASE_BODY",
                    "the staged proposal does not carry a portfolio_release_v2 body",
                ),
                2,
            )
        # Independent approval is verified against the exact staged selection
        # before any signing key is opened, so a refused selection can never
        # produce a signature. SYNTHETIC and PROSPECTIVE proposals are both gated
        # by the same evidence: the reviewer-signed policy must cover this exact
        # staged body and carry independent source-observer attestations.
        try:
            reviewer = _public_key(args.reviewer_public)
            source_observer = _public_key(args.source_observer_public)
            now_ms = args.now_ms if args.now_ms is not None else _now_ms()
            verify_staged_selection(
                store,
                proposal,
                now_ms=now_ms,
                reviewer=reviewer,
                source_observer=source_observer,
            )
        except SealedSelectionError as exc:
            return _emit(
                _fail(
                    str(exc),
                    "the staged selection is not independently approved; no signature was produced",
                ),
                2,
            )
        except (OSError, ValueError, TypeError) as exc:
            return _emit(
                _fail(
                    "RELEASE_ATTESTATION_INPUT_INVALID",
                    "reviewer and source-observer public keys must be readable Ed25519 keys",
                    detail=str(exc),
                ),
                2,
            )
        if not args.apply:
            return _emit(
                {
                    "schema": "roster_release_signature_plan_v1",
                    "state": "DRY_RUN",
                    "proposal_sha": proposal.sha,
                    "trading_authorized": False,
                },
                0,
            )
        key_path = Path(args.release_signing_key).expanduser()
        try:
            fd = os.open(key_path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                mode = os.fstat(stream.fileno()).st_mode
                if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o600:
                    raise ValueError("PRIVATE_KEY_PERMISSIONS")
                key = Ed25519PrivateKey.from_private_bytes(stream.read(33))
        except OSError, ValueError:
            return _emit(
                _fail("PRIVATE_KEY_PERMISSIONS", "signing key must be a 0600 regular file"), 2
            )
        authority_sha = sha256(key.public_key().public_bytes_raw()).hexdigest()
        envelope = sign(finalise_payload(body, authority_sha), key, "approver")
        problem = _write_private(Path(args.out).expanduser(), envelope)
        if problem:
            return _emit(_fail(problem, "signed envelope requires a new private path"), 2)
        store.mark_proposal_signed(proposal.sha, envelope_sha=digest(envelope))
    return _emit(
        {
            "schema": "roster_release_signature_receipt_v1",
            "state": "SIGNED_METADATA_RELEASE",
            "release_sha": envelope["sha256"],
            "proposal_sha": proposal.sha,
            "output": str(args.out) if args.out else None,
            "trading_authorized": False,
        },
        0,
    )


def _release_verify(args: Any) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from .production_manifest import verify

    envelope = json.loads(Path(args.envelope).expanduser().read_text())
    key = Ed25519PublicKey.from_public_bytes(Path(args.signer_public).expanduser().read_bytes())
    payload = verify(envelope, key, "approver")
    return _emit(
        {
            "schema": "roster_release_verify_receipt_v1",
            "state": "VERIFIED",
            "release_sha": envelope["sha256"],
            "account_binding": payload["account_binding"],
            "generation": payload["generation"],
            "members": len(payload["members"]),
            "trading_authorized": False,
        },
        0,
    )


def _release_export(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        now = _as_of(args.as_of)
        book = store.book_at(args.account, as_of=now)
        binding = store.release_binding(args.account)
        export: dict[str, Any] = {
            "schema": "research_portfolio_export_v2",
            "account_id": args.account,
            "as_of_ms": now.value,
            "roster_inventory_sha256": store.inventory_sha(),
            "book_sha": book.sha,
            "mode": book.mode.value,
            "occupied": book.occupied,
            "draining_owners": list(book.draining_owners),
            "release_binding_sha": binding.sha if binding else None,
            "members": [
                {
                    "pod_id": lease.seat_id,
                    "source_identity": lease.wallet if args.identities else _redact(lease.wallet),
                    "identity_known_at_ms": lease.since_ms,
                    "k": str(lease.k),
                    "generation": lease.generation,
                }
                for lease in book.leases
            ],
            "order_route": "NONE",
            "trading_authorized": False,
        }
        export["export_sha256"] = digest(export)
        return _emit(export, 0)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# paper and research read-only views
# ---------------------------------------------------------------------------


def run_paper(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        now = _as_of(getattr(args, "as_of", None))
        if args.verb == "status":
            book = store.book_at(args.account, as_of=now)
            proposals = store.proposals(args.account, as_of=now)
            return _emit(
                dict(
                    _seat_view(book, identities=bool(args.identities)),
                    proposals=len(proposals),
                    latest_proposal_sha=proposals[-1].sha if proposals else None,
                    order_route="NONE",
                ),
                0,
            )
        proposals = store.proposals(args.account, as_of=now)
        if not proposals:
            return _emit(
                _fail(
                    "ROSTER_PROPOSAL_MISSING",
                    "stage a release proposal before reading paper mandates",
                    account_id=args.account,
                ),
                2,
            )
        proposal = proposals[-1]
        payload = proposal.payload_json
        return _emit(
            {
                "schema": "paper_mandate_view_v1",
                "account_id": proposal.account_id,
                "as_of_ms": now.value,
                "day": proposal.day,
                "generation": proposal.generation,
                "proposal_sha": proposal.sha,
                "mandates": [
                    {
                        "mandate_id": item["mandate_id"],
                        "seat_id": item["pod_id"],
                        "generation": item["generation"],
                        "k": item["k"],
                        "allowed_markets": item["allowed_markets"],
                        "entry_policy": item["entry_policy"],
                    }
                    for item in payload.get("mandates", [])
                ],
                "order_route": "NONE",
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()


def run_research(args: Any) -> int:
    store = RosterStore(args.store)
    try:
        now = _as_of(args.as_of)
        if args.verb == "scorecards":
            cards = store.latest_scorecard(as_of=now, include_vetoes=False)
            by_gate: dict[str, int] = {}
            for card in cards.values():
                for gate in card.failures:
                    by_gate[gate.value] = by_gate.get(gate.value, 0) + 1
            return _emit(
                {
                    "schema": "research_scorecard_summary_v1",
                    "as_of_ms": now.value,
                    "scorecards": len(cards),
                    "eligible": sum(1 for card in cards.values() if card.eligible),
                    "failures_by_gate": by_gate,
                    "latched": len(store.latched_wallets(as_of=now)),
                    "trading_authorized": False,
                },
                0,
            )
        bench = store.latest_bench(args.account, as_of=now)
        return _emit(
            {
                "schema": "research_bench_view_v1",
                "account_id": args.account,
                "as_of_ms": now.value,
                "candidates": [
                    {
                        "wallet": item.wallet if args.identities else _redact(item.wallet),
                        "suggested_k": str(item.suggested_k),
                        "marginal_cdar_share": str(item.marginal_cdar_share),
                        "cluster_id": item.cluster_id,
                        "cluster_distance": str(item.cluster_distance),
                    }
                    for item in sorted(bench, key=lambda entry: entry.rank_key)
                ],
                "trading_authorized": False,
            },
            0,
        )
    finally:
        store.close()
