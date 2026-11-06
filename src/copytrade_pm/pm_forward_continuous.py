"""Continuous public-observer coordination, using existing receipt owners.

This module owns only resource planning and lifecycle orchestration. SQLite
wallet identity, legacy receipt tapes, parsers and PM-03 finance retain their
existing owners. No broker client, credential or financial writer is used.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
import asyncio
from datetime import UTC, datetime
import fcntl
import json
import shutil
from time import monotonic
from uuid import uuid4
import os
from pathlib import Path
import re
import sqlite3

from .pm03_account import Instrument, clock, digest
from .pm_forward_observer_health import _readonly_tape_snapshot
from .pm_forward_public_trades import native_coin, registry_watched_addresses
from .wallet_registry import db_authority_health, db_status


@dataclass(frozen=True)
class SubscriptionBudget:
    """Conservative reservations against the documented shared-IP limits.

    Reservations are an operator measurement, not inferred from a successful
    connection. A missing externally measured reservation cannot qualify soak.
    """

    reserved_connections: int = 0
    reserved_users: int = 0
    reserved_subscriptions: int = 0
    max_connections: int = 10
    max_users: int = 10
    max_subscriptions: int = 1000
    ccxt_markets_per_socket: int = 80
    public_markets_per_socket: int = 128
    max_markets: int = 200

    def plan(self, instruments: tuple[Instrument, ...], *, account_count: int) -> dict:
        values = asdict(self)
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError("STREAM_BUDGET_INVALID")
        if not (
            1 <= self.max_connections <= 10
            and 1 <= self.max_users <= 10
            and 1 <= self.max_subscriptions <= 1000
            and 1 <= self.ccxt_markets_per_socket <= 128
            and 1 <= self.public_markets_per_socket <= 128
            and 1 <= self.max_markets <= 300
        ):
            raise ValueError("STREAM_BUDGET_EXCEEDS_PROVIDER_LIMIT")
        if len(set(instruments)) != len(instruments):
            raise ValueError("STREAM_MARKET_DUPLICATE")
        if (
            len(instruments) > self.max_markets
            or type(account_count) is not int
            or account_count < 0
        ):
            raise ValueError("STREAM_SCOPE_BUDGET_INVALID")
        ordered = tuple(sorted(instruments, key=lambda item: item.key))
        for item in ordered:
            native_coin(item)  # Existing exact native/DEX validation.
        ccxt = [
            [item.key for item in ordered[start : start + self.ccxt_markets_per_socket]]
            for start in range(0, len(ordered), self.ccxt_markets_per_socket)
        ]
        public = [
            [item.key for item in ordered[start : start + self.public_markets_per_socket]]
            for start in range(0, len(ordered), self.public_markets_per_socket)
        ]
        connections = bool(account_count) + len(ccxt) + len(public)
        subscriptions = account_count + 3 * len(ordered)
        if connections + self.reserved_connections > self.max_connections:
            raise ValueError("STREAM_CONNECTION_BUDGET_EXCEEDED")
        if account_count + self.reserved_users > self.max_users:
            raise ValueError("STREAM_USER_BUDGET_EXCEEDED")
        if subscriptions + self.reserved_subscriptions > self.max_subscriptions:
            raise ValueError("STREAM_SUBSCRIPTION_BUDGET_EXCEEDED")
        result = {
            "schema": "paper_subscription_plan_v1",
            "limits": values,
            "required_markets": [item.key for item in ordered],
            "account_count": account_count,
            "candidate_connections": connections,
            "subscription_count": subscriptions,
            "ccxt_shards": ccxt,
            "public_shards": public,
            "account_orderability": "UNKNOWN",
            "trade_volume_complete": False,
            "order_route": "NONE",
        }
        return {**result, "scope_sha": digest(result)}


class MarketScope:
    """Configured markets union current verified held positions and stale hedges."""

    def __init__(self, configured: tuple[Instrument, ...], budget: SubscriptionBudget):
        self.configured, self.budget = configured, budget
        self.prior_positions = {}
        self.current = None

    def update(self, accounts: dict[str, dict], *, expected_accounts: tuple[str, ...]) -> dict:
        missing = []
        for alias in expected_accounts:
            state = accounts.get(alias)
            if state is None or not state.get("baseline_valid"):
                missing.append(alias)
                # Preserve prior held requirements during unknown intervals.
                if state and "positions" in state:
                    self.prior_positions.setdefault(alias, dict(state["positions"]))
                continue
            self.prior_positions[alias] = dict(state["positions"])
        missing.extend(
            alias
            for alias, positions in self.prior_positions.items()
            if alias not in expected_accounts and positions
        )
        held = {
            Instrument.parse(key)
            for positions in self.prior_positions.values()
            for key in positions
        }
        required = tuple(sorted(set(self.configured) | held, key=lambda inst: inst.key))
        reason = None
        try:
            plan = self.budget.plan(required, account_count=len(expected_accounts))
        except ValueError as exc:
            plan, reason = None, str(exc)
        body = {
            "required_markets": [inst.key for inst in required],
            "configured_markets": [inst.key for inst in self.configured],
            "held_markets": sorted(inst.key for inst in held),
            "expected_accounts": list(expected_accounts),
            "missing_accounts": missing,
            "subscription_plan": plan,
            "budget_failure": reason,
            "status": "DEGRADED_SCOPE" if missing or reason else "SCOPE_ENUMERATED",
            "account_orderability": "UNKNOWN",
            "market_sessions": "UNKNOWN",
            "coverage_complete": False,
            "order_route": "NONE",
        }
        result = {**body, "scope_sha": digest(body)}
        self.current = result
        return result


def _private_candidate_path(root: Path, protected_roots: tuple[Path, ...]) -> None:
    root = Path(root)
    if not root.is_absolute() or any(part in {".devspace", ".git"} for part in root.parts):
        raise ValueError("STREAM_PRIVATE_ABSOLUTE_STATE_REQUIRED")
    resolved = root.resolve()
    for protected in protected_roots:
        old = Path(protected).resolve()
        if resolved == old or old in resolved.parents or resolved in old.parents:
            raise ValueError("STREAM_STATE_COLLISION")
    for component in (root, *root.parents):
        if component.is_symlink():
            raise ValueError("STREAM_STATE_SYMLINK")
    if root.exists() and (
        not root.is_dir() or root.stat().st_mode & 0o077 or root.stat().st_uid != os.geteuid()
    ):
        raise ValueError("STREAM_STATE_PERMISSION_INVALID")
    for name in ("paper-events.sqlite3", "paper-events.sqlite3-wal", "paper-events.sqlite3-shm"):
        candidate = root / name
        if candidate.is_symlink():
            raise ValueError("STREAM_JOURNAL_SYMLINK")
        if candidate.exists():
            stat = candidate.stat()
            if (
                not candidate.is_file()
                or stat.st_nlink != 1
                or stat.st_uid != os.geteuid()
                or stat.st_mode & 0o077
            ):
                raise ValueError("STREAM_JOURNAL_PERMISSION_INVALID")
    database = root / "paper-events.sqlite3"
    if database.exists():
        with closing(sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            for table in ("runs", "events"):
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type=? AND name=?", ("table", table)
                ).fetchone()
                if exists and db.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone():
                    raise ValueError("STREAM_FINANCIAL_JOURNAL_COLLISION")
    lock = root / "paper-observer.lock"
    if lock.exists() or lock.is_symlink():
        fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if os.fstat(fd).st_mode & 0o077:
                raise ValueError("STREAM_LEASE_PERMISSION_INVALID")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("STREAM_WRITER_ALREADY_ACTIVE") from exc
        finally:
            os.close(fd)


def _portfolio_seals(db_path: Path, ids: tuple[str, ...], *, as_of: str) -> dict:
    result = {}
    with closing(sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for pid in ids:
            row = db.execute(
                "SELECT version,definition_sha256,selection_known_at FROM portfolio_seals "
                "WHERE portfolio_id=? ORDER BY version DESC LIMIT 1",
                (pid,),
            ).fetchone()
            if row is None or clock(row[2]) > clock(as_of):
                raise ValueError("STREAM_PORTFOLIO_NOT_SEALED_ASOF")
            result[pid] = {
                "version": row[0],
                "definition_sha256": row[1],
                "selection_known_at": row[2],
            }
    return result


def _diagnostic_sealed_account_count(db_path: Path, seals: dict) -> int:
    """Count unique recorded identities without admitting excluded accounts.

    This is a capacity estimate only; no historical wallet identity, watchlist
    membership or source NAV is certified by these metadata rows.
    """
    ids: set[int] = set()
    with closing(sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for pid, seal in seals.items():
            rows = db.execute(
                "SELECT wallet_id FROM portfolio_memberships WHERE portfolio_id=? AND version=?",
                (pid, seal["version"]),
            ).fetchall()
            if not rows or any(row[0] is None for row in rows):
                raise ValueError("STREAM_DIAGNOSTIC_ACCOUNT_COUNT_UNKNOWN")
            ids.update(row[0] for row in rows)
    return len(ids)


def diagnose_candidate_preflight(
    *,
    registry_db: Path,
    state_root: Path,
    instruments: tuple[Instrument, ...],
    revision: str,
    as_of: str,
    budget: SubscriptionBudget,
    protected_roots: tuple[Path, ...] = (),
    portfolio_ids: tuple[str, ...] = ("P1", "P14"),
    expected_inventory_sha: str | None = None,
) -> dict:
    """Read-only multi-gate report; never an alternative admission path.

    Run independent checks even when one fails so operators see provenance,
    exclusion and shared-IP blockers in one invocation. No service, network,
    registry write or journal creation is performed.
    """
    clock(as_of)
    gates: dict[str, dict] = {}

    def check(name: str, operation):
        try:
            result = operation()
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            reason = (
                "STREAM_SELECTION_PROOF_MISSING"
                if name == "signed_selection"
                and str(exc) == "unverified research selection provenance"
                else _reason(exc)
            )
            gates[name] = {"status": "BLOCKED", "reason_code": reason}
            return None
        gates[name] = {"status": "PASS"}
        return result

    def inspect_authority():
        if registry_db.is_symlink() or not registry_db.is_file():
            raise ValueError("STREAM_REGISTRY_FILE_INVALID")
        result = db_authority_health(registry_db)
        if result.get("database_integrity") != "VERIFIED":
            raise ValueError("STREAM_REGISTRY_INTEGRITY_FAILED")
        return result

    check("private_state", lambda: _private_candidate_path(state_root, protected_roots))
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        gates["revision"] = {"status": "BLOCKED", "reason_code": "STREAM_RELEASE_REVISION_INVALID"}
    else:
        gates["revision"] = {"status": "PASS"}
    registry_db = Path(registry_db)
    authority = check("registry_integrity", inspect_authority)
    seals = None
    watched = None
    account_count = None
    count_source = "UNKNOWN"
    if authority is None:
        for name in (
            "signed_selection",
            "inventory_generation",
            "portfolio_seals",
            "watched_wallets",
            "account_census",
            "registry_stability",
        ):
            gates[name] = {"status": "UNKNOWN", "reason_code": "STREAM_REGISTRY_NOT_VERIFIED"}
    else:
        check("signed_selection", lambda: db_status(registry_db))

        def compare_inventory():
            if (
                expected_inventory_sha is not None
                and authority["inventory_sha256"] != expected_inventory_sha
            ):
                raise ValueError("STREAM_REGISTRY_GENERATION_CHANGED")
            return True

        check("inventory_generation", compare_inventory)
        seals = check(
            "portfolio_seals",
            lambda: _portfolio_seals(registry_db, portfolio_ids, as_of=as_of),
        )
        watched = check(
            "watched_wallets",
            lambda: registry_watched_addresses(registry_db, portfolio_ids, as_of=as_of),
        )
        if watched is not None:
            account_count = len(watched)
            count_source = "ELIGIBLE_WATCHLIST"
            gates["account_census"] = {"status": "PASS"}
        elif seals is not None:
            account_count = check(
                "account_census",
                lambda: _diagnostic_sealed_account_count(registry_db, seals),
            )
            count_source = "SEALED_MEMBERSHIP_ESTIMATE" if account_count is not None else "UNKNOWN"
        else:
            gates["account_census"] = {
                "status": "UNKNOWN",
                "reason_code": "STREAM_ACCOUNT_COUNT_UNKNOWN",
            }

        def recheck_inventory():
            if (
                db_authority_health(registry_db)["inventory_sha256"]
                != authority["inventory_sha256"]
            ):
                raise ValueError("STREAM_REGISTRY_GENERATION_CHANGED")
            return True

        check("registry_stability", recheck_inventory)

    if account_count is not None:
        check("subscription_budget", lambda: budget.plan(instruments, account_count=account_count))
    else:
        gates["subscription_budget"] = {
            "status": "UNKNOWN",
            "reason_code": "STREAM_ACCOUNT_COUNT_UNKNOWN",
        }

    def verify_protected_heads():
        for old in protected_roots:
            path = Path(old) / "paper-events.sqlite3"
            if path.exists():
                _readonly_tape_snapshot(path)
        return True

    check("protected_journals", verify_protected_heads)
    return {
        "schema": "paper_continuous_preflight_diagnostic_v1",
        "status": "BLOCKED"
        if any(row["status"] != "PASS" for row in gates.values())
        else "DIAGNOSTIC_ONLY",
        "revision": revision,
        "as_of": as_of,
        "inventory_sha256": authority["inventory_sha256"] if authority else None,
        "portfolio_count": len(portfolio_ids),
        "configured_market_count": len(instruments),
        "estimated_unique_accounts": account_count,
        "account_count_basis": count_source,
        "shared_ip_reservations_operator_verified": False,
        "candidate_connections_estimate": (
            int(account_count > 0)
            + (len(instruments) + budget.ccxt_markets_per_socket - 1)
            // budget.ccxt_markets_per_socket
            + (len(instruments) + budget.public_markets_per_socket - 1)
            // budget.public_markets_per_socket
            if account_count is not None
            and budget.ccxt_markets_per_socket > 0
            and budget.public_markets_per_socket > 0
            else None
        ),
        "reserved_connections_configured": budget.reserved_connections,
        "max_connections": budget.max_connections,
        "candidate_users_estimate": account_count,
        "reserved_users_configured": budget.reserved_users,
        "max_users": budget.max_users,
        "candidate_subscriptions_estimate": (
            account_count + 3 * len(instruments) if account_count is not None else None
        ),
        "reserved_subscriptions_configured": budget.reserved_subscriptions,
        "max_subscriptions": budget.max_subscriptions,
        "gates": gates,
        "safe_to_start": False,
        "strict_preflight_still_required": True,
        "financial_admission": "BLOCKED_NO_TRADE",
        "paper_observed": False,
        "order_route": "NONE",
    }


def candidate_preflight(
    *,
    registry_db: Path,
    state_root: Path,
    instruments: tuple[Instrument, ...],
    revision: str,
    as_of: str,
    budget: SubscriptionBudget,
    protected_roots: tuple[Path, ...] = (),
    portfolio_ids: tuple[str, ...] = ("P1", "P14"),
    expected_inventory_sha: str | None = None,
) -> dict:
    """Read-only preflight. No directory creation, network, or service operation."""
    clock(as_of)
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("STREAM_RELEASE_REVISION_INVALID")
    _private_candidate_path(state_root, protected_roots)
    registry_db = Path(registry_db)
    if registry_db.is_symlink() or not registry_db.is_file():
        raise ValueError("STREAM_REGISTRY_FILE_INVALID")
    authority = db_authority_health(registry_db)
    if authority.get("database_integrity") != "VERIFIED":
        raise ValueError("STREAM_REGISTRY_INTEGRITY_FAILED")
    db_status(registry_db)  # Same signed-selection proof checks as the native doctor.
    inventory_sha = authority["inventory_sha256"]
    if expected_inventory_sha is not None and inventory_sha != expected_inventory_sha:
        raise ValueError("STREAM_REGISTRY_GENERATION_CHANGED")
    watched = registry_watched_addresses(registry_db, portfolio_ids, as_of=as_of)
    seals = _portfolio_seals(registry_db, portfolio_ids, as_of=as_of)
    # Refuse an identity/selection race between independent native readers.
    if db_authority_health(registry_db)["inventory_sha256"] != inventory_sha:
        raise ValueError("STREAM_REGISTRY_GENERATION_CHANGED")
    plan = budget.plan(instruments, account_count=len(watched))
    old_heads = {}
    for old in protected_roots:
        path = Path(old) / "paper-events.sqlite3"
        if path.exists():
            old_heads[str(Path(old).resolve())] = _readonly_tape_snapshot(path)
    body = {
        "schema": "paper_continuous_preflight_v1",
        "status": "PREFLIGHT_VERIFIED_OBSERVER_ONLY",
        "revision": revision,
        "as_of": as_of,
        "inventory_sha256": inventory_sha,
        "portfolio_seals": seals,
        "watchlist_sha": digest(sorted(watched.items())),
        "unique_wallet_count": len(watched),
        "subscription_plan": plan,
        "protected_journal_heads": old_heads,
        "state_root": str(state_root),
        "source_nav_attested": False,
        "financial_admission": "BLOCKED_NO_TRADE",
        "protected_worker_attested": False,
        "paper_observed": False,
        "order_route": "NONE",
    }
    return {**body, "manifest_sha": digest(body)}


def runtime_revision() -> str:
    """Verify the checkout or a separately pinned release tree before networking."""
    import subprocess
    from hashlib import sha256

    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if dirty.strip():
            raise ValueError("STREAM_DIRTY_WORKTREE_NOT_A_PINNED_RELEASE")
        return result.stdout.strip()
    manifest_path = root / "observer-release.json"
    if manifest_path.is_symlink():
        raise ValueError("STREAM_RELEASE_MANIFEST_SYMLINK")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "paper_continuous_release_tree_v1" or manifest.get(
        "manifest_sha"
    ) != digest({k: v for k, v in manifest.items() if k != "manifest_sha"}):
        raise ValueError("STREAM_RELEASE_MANIFEST_INVALID")
    expected = manifest["files"]
    actual = {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in (root / "src").rglob("*.py")
        if p.is_file() and not p.is_symlink()
    }
    for name in ("pyproject.toml", "uv.lock"):
        actual[name] = sha256((root / name).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError("STREAM_INSTALLED_RELEASE_TREE_DRIFT")
    return manifest["revision"]


def load_continuous_config(
    path: Path, *, allow_budget_failures_for_diagnostics: bool = False
) -> tuple[dict, tuple[Instrument, ...], SubscriptionBudget]:
    from .pm_forward_public_trades import load_public_market_shards

    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128_000:
        raise ValueError("STREAM_CONFIG_FILE_INVALID")
    config = json.loads(path.read_text())
    required = {
        "schema",
        "revision",
        "inventory_sha256",
        "protected_roots",
        "budget",
        "portfolio_ids",
        "duration_seconds",
    }
    optional = {
        "instruments",
        "market_scope_file",
        "propr_snapshot",
        "refresh_seconds",
        "min_free_bytes",
        "max_journal_bytes",
        "queue_size",
    }
    if (
        not isinstance(config, dict)
        or not required.issubset(config)
        or set(config) - required - optional
        or config["schema"] != "paper_continuous_observer_config_v1"
    ):
        raise ValueError("STREAM_CONFIG_SCHEMA_INVALID")
    if (
        not isinstance(config["portfolio_ids"], list)
        or not config["portfolio_ids"]
        or len(set(config["portfolio_ids"])) != len(config["portfolio_ids"])
        or not set(config["portfolio_ids"]) <= {"P1", "P14"}
    ):
        raise ValueError("STREAM_CONFIG_PORTFOLIO_SCOPE_INVALID")
    if (
        not isinstance(config["protected_roots"], list)
        or not config["protected_roots"]
        or any(not Path(p).is_absolute() for p in config["protected_roots"])
    ):
        raise ValueError("STREAM_CONFIG_PROTECTED_ROOTS_REQUIRED")
    if re.fullmatch(r"[0-9a-f]{64}", config["inventory_sha256"]) is None:
        raise ValueError("STREAM_CONFIG_REGISTRY_SHA_REQUIRED")
    duration = config["duration_seconds"]
    if type(duration) not in (int, float) or not 0 <= duration <= 604800:
        raise ValueError("STREAM_DURATION_BOUND_INVALID")
    if ("instruments" in config) == ("market_scope_file" in config):
        raise ValueError("STREAM_CONFIG_ONE_MARKET_SCOPE_REQUIRED")
    if "instruments" in config:
        instruments = tuple(Instrument.parse(x) for x in config["instruments"])
    else:
        source = Path(config["market_scope_file"])
        if not source.is_absolute():
            source = path.parent / source
        shards = load_public_market_shards(source)
        instruments = tuple(inst for _, group in shards for inst in group)
        payload = json.loads(source.read_text())
        if payload["schema"] == "paper_public_physical_sockets_v1":
            from .pm_forward_propr_universe import verify_propr_display_layout

            snapshot = Path(config["propr_snapshot"])
            if not snapshot.is_absolute():
                snapshot = path.parent / snapshot
            verify_propr_display_layout(snapshot, payload)
        config["configured_groups"] = [
            {"name": name, "instruments": [x.key for x in group]} for name, group in shards
        ]
        config["market_scope_sha"] = digest(payload)
    if not instruments:
        raise ValueError("STREAM_CONFIG_MARKET_SCOPE_EMPTY")
    budget = SubscriptionBudget(**config["budget"])
    try:
        budget.plan(instruments, account_count=0)
    except ValueError as exc:
        if not allow_budget_failures_for_diagnostics or str(exc) not in {
            "STREAM_CONNECTION_BUDGET_EXCEEDED",
            "STREAM_USER_BUDGET_EXCEEDED",
            "STREAM_SUBSCRIPTION_BUDGET_EXCEEDED",
        }:
            raise
    for name, minimum, maximum in (
        ("min_free_bytes", 100_000_000, 1_000_000_000_000),
        ("max_journal_bytes", 1_000_000, 1_000_000_000_000),
        ("queue_size", 1, 4096),
    ):
        if name in config and (
            type(config[name]) is not int or not minimum <= config[name] <= maximum
        ):
            raise ValueError("STREAM_STORAGE_OR_QUEUE_BOUND_INVALID")
    return config, instruments, budget


def continuous_entrypoint(args) -> dict:
    """Existing public observer CLI seam; preflight precedes journal/network creation."""
    import signal
    from .pm_forward_journal import PaperJournal
    from .pm_forward_observer import exclusive_observer_lease
    from .pm_forward_registry_identity import (
        P1,
        P14,
        _private_locator,
        audit_frozen_member_resolution,
    )
    from .pm_forward_source_campaign import _ALIAS

    diagnose = getattr(args, "diagnose_preflight", False)
    config, configured, budget = load_continuous_config(
        args.continuous_config, allow_budget_failures_for_diagnostics=diagnose
    )
    actual_revision = runtime_revision()
    if actual_revision != config["revision"]:
        raise ValueError("STREAM_CONFIG_RELEASE_REVISION_MISMATCH")
    now = _now()
    if diagnose:
        if not args.preflight_only:
            raise ValueError("STREAM_DIAGNOSTIC_REQUIRES_PREFLIGHT_ONLY")
        return diagnose_candidate_preflight(
            registry_db=args.registry,
            state_root=args.state_root,
            instruments=configured,
            revision=actual_revision,
            as_of=now,
            budget=budget,
            protected_roots=tuple(Path(path) for path in config["protected_roots"]),
            portfolio_ids=tuple(config["portfolio_ids"]),
            expected_inventory_sha=config["inventory_sha256"],
        )
    manifest = candidate_preflight(
        registry_db=args.registry,
        state_root=args.state_root,
        instruments=configured,
        revision=actual_revision,
        as_of=now,
        budget=budget,
        protected_roots=tuple(Path(path) for path in config["protected_roots"]),
        portfolio_ids=tuple(config["portfolio_ids"]),
        expected_inventory_sha=config["inventory_sha256"],
    )
    manifest = {k: v for k, v in manifest.items() if k != "manifest_sha"}
    manifest["config_sha"] = digest(config)
    manifest["configured_groups"] = config.get("configured_groups", [])
    manifest["market_scope_sha"] = config.get(
        "market_scope_sha", digest([i.key for i in configured])
    )
    manifest["manifest_sha"] = digest(manifest)
    watched = registry_watched_addresses(args.registry, tuple(config["portfolio_ids"]), as_of=now)
    parents = {}
    for pid in config["portfolio_ids"]:
        audit_frozen_member_resolution(
            registry_db=args.registry,
            primary_dir=args.primary_dir,
            secondary_dir=args.secondary_dir,
            portfolio_id=pid,
        )
        for member in P1 if pid == "P1" else P14:
            _, address, _ = _private_locator(
                member, primary_dir=args.primary_dir, secondary_dir=args.secondary_dir
            )
            if address.lower() not in watched:
                raise ValueError("STREAM_CANONICAL_PARENT_WATCHLIST_MISMATCH")
            parents[_ALIAS[member]] = address.lower()
    if len(parents) != len(watched):
        raise ValueError("STREAM_CANONICAL_PARENT_SCOPE_MISMATCH")
    if args.preflight_only:
        return manifest
    journal = PaperJournal(args.state_root)

    async def run():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, stop.set)
        loop.add_signal_handler(signal.SIGTERM, stop.set)
        observer = ContinuousObserver(
            journal=journal,
            manifest=manifest,
            parents=parents,
            watched=watched,
            configured=configured,
            budget=budget,
            **{
                key: config[key]
                for key in ("refresh_seconds", "min_free_bytes", "max_journal_bytes", "queue_size")
                if key in config
            },
        )
        return await observer.run(stop, duration_seconds=config["duration_seconds"])

    with exclusive_observer_lease(journal):
        return asyncio.run(run())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _reason(exc: Exception) -> str:
    # Public stdout/health never contains raw remote errors or wallet addresses.
    value = str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", value) else type(exc).__name__


def _acknowledge_native(feed, known):
    progress = feed.progress
    return progress.commit(
        progress.propose(
            epoch=feed.epoch,
            kind="TRANSPORT",
            known_at=known,
            checkpoint={
                **progress.checkpoint,
                "subscription_acknowledged": True,
                "subscription_acknowledged_at": known,
            },
        )
    )


async def run_native_accounts(accounts, *, writer, stop, connect, now, limiter, queue_size=256):
    from .pm_forward_continuous_transport import native_session, wait_or_stop

    by_address = {account.address: account for account in accounts.values()}
    while not stop.is_set():
        for account in accounts.values():
            await writer.submit(lambda a=account: a.begin(now()))

        async def acknowledge(sub, known):
            account = by_address[sub["user"]]
            await writer.submit(lambda: _acknowledge_native(account, known))

        async def handle(frame, known, raw_sha, wire):
            data = frame.get("data")
            if frame.get("channel") != "allDexsClearinghouseState" or not isinstance(data, dict):
                raise ValueError("SOURCE_NATIVE_CHANNEL_MISMATCH")
            account = by_address.get(str(data.get("user", "")).lower())
            if account is None:
                raise ValueError("SOURCE_NATIVE_ACCOUNT_NOT_SUBSCRIBED")
            try:
                await writer.submit(
                    lambda: account.observe(frame, known, raw_sha=raw_sha, raw_text=wire)
                )
            except ValueError as exc:
                if writer.failed:
                    raise
                await writer.submit(lambda reason=_reason(exc): account.gap(now(), reason))

        async def transport(known):
            for account in accounts.values():
                if clock(known) >= clock(account.progress.head["event"]["first_known_at"]):
                    await writer.submit(lambda a=account: a.transport(known))

        reason = "ORDERLY_STOP"
        try:
            await native_session(
                subscriptions=[
                    {"type": "allDexsClearinghouseState", "user": a.address}
                    for a in accounts.values()
                ],
                on_ack=acknowledge,
                handle=handle,
                on_transport=transport,
                stop=stop,
                now=now,
                connect=connect,
                limiter=limiter,
                queue_size=queue_size,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if writer.failed:
                raise
            reason = _reason(exc)
        finally:
            for account in accounts.values():
                await writer.submit(lambda a=account: a.gap(now(), reason))
        await wait_or_stop(stop, 15)


async def run_native_public(
    feeds, *, writer, stop, connect, now, limiter, queue_size=256, info=None
):
    from .pm_forward_continuous_transport import native_session, wait_or_stop
    from .pm_forward_public_trades import validate_public_market_catalog

    by_coin = {native_coin(feed.instrument): feed for feed in feeds}
    while not stop.is_set():
        for feed in feeds:
            await writer.submit(lambda f=feed: f.begin(now()))

        async def acknowledge(sub, known):
            feed = by_coin[sub["coin"]]
            await writer.submit(lambda: _acknowledge_native(feed, known))

        async def handle(frame, known, raw_sha, wire):
            rows = frame.get("data")
            if "isSnapshot" in frame and type(frame["isSnapshot"]) is not bool:
                raise ValueError("PUBLIC_NATIVE_SNAPSHOT_SEMANTICS_UNKNOWN")
            if frame.get("channel") != "trades" or not isinstance(rows, list):
                raise ValueError("PUBLIC_NATIVE_CHANNEL_MISMATCH")
            groups = {}
            for row in rows:
                if not isinstance(row, dict) or row.get("coin") not in by_coin:
                    raise ValueError("PUBLIC_NATIVE_COIN_NOT_SUBSCRIBED")
                groups.setdefault(row["coin"], []).append(row)
            for coin, trades in groups.items():
                feed = by_coin[coin]
                try:
                    await writer.submit(
                        lambda f=feed, r=trades: f.observe(
                            r,
                            known,
                            snapshot=frame.get("isSnapshot", False),
                            raw_sha=raw_sha,
                            raw_text=wire,
                        )
                    )
                except ValueError as exc:
                    if writer.failed:
                        raise
                    await writer.submit(lambda f=feed, reason=_reason(exc): f.gap(now(), reason))

        async def transport(known):
            for feed in feeds:
                if clock(known) >= clock(feed.progress.head["event"]["first_known_at"]):
                    await writer.submit(lambda f=feed: f.transport(known))

        reason = "ORDERLY_STOP"
        try:
            catalog = await asyncio.to_thread(
                validate_public_market_catalog,
                tuple(f.instrument for f in feeds),
                info=info,
                allow_partial=True,
            )
            by_coin = {
                native_coin(f.instrument): f
                for f in feeds
                if native_coin(f.instrument) not in catalog["unavailable_markets"]
            }
            for f in feeds:
                if native_coin(f.instrument) not in by_coin:
                    await writer.submit(
                        lambda f=f: f.gap(now(), "PUBLIC_NATIVE_MARKET_UNAVAILABLE")
                    )
            if not by_coin:
                await wait_or_stop(stop, 60)
                continue
            await native_session(
                subscriptions=[{"type": "trades", "coin": coin} for coin in by_coin],
                on_ack=acknowledge,
                handle=handle,
                on_transport=transport,
                stop=stop,
                now=now,
                connect=connect,
                limiter=limiter,
                queue_size=queue_size,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if writer.failed:
                raise
            reason = _reason(exc)
        finally:
            for feed in feeds:
                await writer.submit(lambda f=feed: f.gap(now(), reason))
        await wait_or_stop(stop, 15)


async def run_ccxt_markets(
    instruments,
    *,
    journal,
    writer,
    stop,
    now,
    scope_sha,
    limiter,
    factory=None,
    receipt_clock_factory=None,
):
    """Retain one CCXT client per shard; per-channel failures do not kill siblings."""
    from .pm_forward_ccxt_market import (
        ReadOnlyCCXTProHyperliquid,
        PersistentMarket,
        CCXTLocalReceiptClock,
    )
    from .pm_forward_continuous_transport import wait_or_stop
    from .pm_forward_stream_journal import StreamProgress

    dexes = tuple(
        sorted(
            {
                item.market.split(":")[-1]
                for item in instruments
                if item.market != "mainnet:perp:default"
            }
        )
    )
    while not stop.is_set():
        feed = ReadOnlyCCXTProHyperliquid(
            instruments, hip3_dexes=dexes, factory=factory, rolling_trades=True, now=now
        )
        tasks = []
        try:
            await feed.open()
            timer = (
                receipt_clock_factory(feed._exchange)
                if receipt_clock_factory is not None
                else CCXTLocalReceiptClock(feed._exchange, now=now, limiter=limiter)
            )
            for inst in instruments:
                if inst not in feed.catalog:
                    for prefix in ("ccxt_l2:", "ccxt_trades:"):
                        progress = StreamProgress(journal, prefix + inst.key)
                        event = progress.propose(
                            epoch=uuid4().hex,
                            kind="GAP",
                            known_at=now(),
                            checkpoint={
                                "baseline_valid": False,
                                "transport": "UNSUPPORTED",
                                "scope_sha": scope_sha,
                            },
                            details={"reason": feed.blocked.get(inst.key, "CCXT_CATALOG_MISSING")},
                        )
                        await writer.submit(lambda p=progress, e=event: p.commit(e))
                    continue
                market = PersistentMarket(journal, feed.catalog[inst], scope_sha=scope_sha)
                for channel in ("quote", "trades"):
                    tasks.append(
                        asyncio.create_task(
                            _ccxt_channel(
                                market,
                                channel,
                                feed=feed,
                                timer=timer,
                                writer=writer,
                                stop=stop,
                                now=now,
                            ),
                            name="observer-" + channel + "-" + inst.key,
                        )
                    )
            if tasks:
                stopping = asyncio.create_task(stop.wait())
                try:
                    done, _ = await asyncio.wait(
                        [*tasks, stopping], return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        if task is not stopping:
                            await task
                finally:
                    stopping.cancel()
                    await asyncio.gather(stopping, return_exceptions=True)
            else:
                await wait_or_stop(stop, 60)
        except asyncio.CancelledError:
            raise
        except Exception:
            if writer.failed:
                raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await feed.close()
        await wait_or_stop(stop, 15)


async def _ccxt_channel(market, channel, *, feed, timer, writer, stop, now):
    from copy import deepcopy
    from .pm_forward_continuous_transport import wait_or_stop

    instrument, symbol = market.market.instrument, market.market.ccxt_symbol
    coin = native_coin(instrument)
    token = None
    await writer.submit(lambda: market.begin(channel, now()))
    pending = None
    last_transport = None

    async def receive_snapshot():
        # No scheduling boundary between CCXT returning its cache and capturing
        # the corresponding ingress clock. The supervisor may resume after a
        # newer raw frame; pairing that newer clock with this cache is a false gap.
        raw = deepcopy(
            await (
                feed._exchange.watch_order_book(symbol, 5)
                if channel == "quote"
                else feed._exchange.watch_trades(symbol, None, 1000)
            )
        )
        stamp = timer.stamp(
            channel, coin, native_time=raw.get("timestamp") if channel == "quote" else None
        )
        first_known = timer.trade_clocks(coin, stamp["epoch"]) if channel == "trades" else None
        return raw, stamp, first_known

    try:
        while not stop.is_set():
            try:
                pending = asyncio.create_task(receive_snapshot())
                timed_out = False
                while not stop.is_set() and not pending.done():
                    await asyncio.wait([pending], timeout=10)
                    if pending.done():
                        break
                    inbound = timer.transport_at()
                    fresh = (
                        inbound is not None
                        and 0 <= (clock(now()) - clock(inbound)).total_seconds() <= 45
                    )
                    if fresh and channel == "trades":
                        # A quiet market is not a disconnected socket.
                        if inbound != last_transport:
                            await writer.submit(lambda: market.transport(channel, inbound))
                            last_transport = inbound
                        continue
                    if not timed_out:
                        await writer.submit(
                            lambda: market.gap(
                                channel,
                                now(),
                                "CCXT_STALE_QUOTE" if fresh else "CCXT_SILENT_TRANSPORT",
                            )
                        )
                        timed_out = True
                    if not fresh:
                        raise TimeoutError("CCXT_SILENT_TRANSPORT")
                if stop.is_set():
                    break
                raw, stamp, first_known = await pending
                known = stamp["known_at"]
                if (token is not None and token != stamp["epoch"]) or timed_out:
                    await writer.submit(lambda: market.begin(channel, known))
                token = stamp["epoch"]
                if channel == "quote":
                    await writer.submit(lambda: market.quote(raw, known))
                else:
                    await writer.submit(
                        lambda: market.trades(list(raw), known, first_known_by_id=first_known)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if writer.failed:
                    raise
                await writer.submit(lambda reason=_reason(exc): market.gap(channel, now(), reason))
                await wait_or_stop(stop, 15)
                if not stop.is_set():
                    await writer.submit(lambda: market.begin(channel, now()))
                token = None
            finally:
                if pending is not None and not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
    finally:
        await writer.submit(lambda: market.gap(channel, now(), "ORDERLY_STOP"))


def _journal_storage_bytes(path: Path) -> int:
    import stat

    total = 0
    for suffix in ("", "-wal", "-shm"):
        item = Path(str(path) + suffix)
        try:
            info = item.stat(follow_symlinks=False)
        except FileNotFoundError:
            if not suffix:
                raise
            continue  # SQLite may remove a sidecar after its last connection closes.
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("STREAM_JOURNAL_STORAGE_FILE_INVALID")
        total += info.st_size
    return total


class ContinuousObserver:
    """Supervise existing owners with one journal, one writer and explicit scopes."""

    def __init__(
        self,
        *,
        journal,
        manifest: dict,
        parents: dict,
        watched: dict,
        configured: tuple[Instrument, ...],
        budget: SubscriptionBudget,
        info=None,
        connect=None,
        ccxt_factory=None,
        receipt_clock_factory=None,
        now=_now,
        refresh_seconds=300,
        heartbeat_seconds=10,
        min_free_bytes=2_000_000_000,
        max_journal_bytes=10_000_000_000,
        queue_size=256,
    ):
        from .pm_e4_prospective import _guarded_info
        from .pm_forward_stream_journal import StreamProgress, verify_streams

        if (
            manifest.get("schema") != "paper_continuous_preflight_v1"
            or manifest.get("order_route") != "NONE"
            or manifest.get("source_nav_attested") is not False
            or manifest.get("manifest_sha")
            != digest({k: v for k, v in manifest.items() if k != "manifest_sha"})
            or re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", "")) is None
            or len(set(parents.values())) != len(parents)
            or set(parents.values()) != set(watched)
            or not 0 < refresh_seconds <= 3600
            or not 0 < heartbeat_seconds <= 45
        ):
            raise ValueError("STREAM_CANDIDATE_MANIFEST_INVALID")
        if type(queue_size) is not int or not 1 <= queue_size <= 4096:
            raise ValueError("STREAM_QUEUE_BOUND_INVALID")
        verify_streams(journal.path)
        self.journal, self.manifest, self.parents, self.watched = (
            journal,
            manifest,
            parents,
            watched,
        )
        self.scope = MarketScope(configured, budget)
        self.budget, self.configured, self.now = budget, configured, now
        self.info, self.connect, self.ccxt_factory = info or _guarded_info, connect, ccxt_factory
        self.receipt_clock_factory = receipt_clock_factory
        self.refresh_seconds, self.heartbeat_seconds = refresh_seconds, heartbeat_seconds
        self.min_free_bytes, self.max_journal_bytes, self.queue_size = (
            min_free_bytes,
            max_journal_bytes,
            queue_size,
        )
        self.control = StreamProgress(journal, "observer:control")
        self.epoch = uuid4().hex
        self.accounts, self.jobs = {}, {}
        self.family = None
        self.census_status = "UNKNOWN"
        self.last_scope_sha = None
        self.started_at = now()
        self.started_monotonic = monotonic()

    async def record(self, writer, kind, state, *, reason=None):
        event = self.control.propose(
            epoch=self.epoch,
            kind=kind,
            known_at=self.now(),
            checkpoint=state,
            details={} if reason is None else {"reason": reason},
        )
        return await writer.submit(lambda: self.control.commit(event))

    async def _stop_job(self, key):
        entry = self.jobs.pop(key, None)
        if entry is not None:
            stop, task = entry
            stop.set()
            task.cancel()
            result = await asyncio.gather(task, return_exceptions=True)
            if result and isinstance(result[0], Exception):
                raise result[0]

    async def _refresh_family(self, writer, limiter):
        from .pm_forward_source_stream import (
            discover_persistent_family,
            PersistentAccount,
            read_public_collateral_scope,
        )

        family = await discover_persistent_family(self.parents, info=self.info, now=self.now)
        self.budget.plan(self.configured, account_count=len(family["accounts"]))
        if self.family is None or family["scope_sha"] != self.family["scope_sha"]:
            await self._stop_job(("accounts",))
            self.family = family
            self.accounts = {
                alias: PersistentAccount(
                    journal=self.journal,
                    alias=alias,
                    address=row["address"],
                    parent_alias=row["parent_alias"],
                    dex_catalog=family["catalog"],
                    subaccounts=row["subaccounts"],
                    scope_sha=family["scope_sha"],
                )
                for alias, row in family["accounts"].items()
            }
            local_stop = asyncio.Event()
            task = asyncio.create_task(
                run_native_accounts(
                    self.accounts,
                    writer=writer,
                    stop=local_stop,
                    connect=self.connect,
                    now=self.now,
                    limiter=limiter,
                    queue_size=self.queue_size,
                )
            )
            self.jobs[("accounts",)] = (local_stop, task)
        self.census_status = "CURRENT_PUBLIC_CENSUS"
        # Collateral/mode are asynchronous diagnostics with their own clocks.
        # They never become an atomic whole-wallet denominator.
        from .pm_forward_stream_journal import StreamProgress

        for alias, address in self.parents.items():
            report = await read_public_collateral_scope(
                address=address,
                perpetuals_only=True,
                info=self.info,
                now=self.now,
            )
            progress = StreamProgress(self.journal, "collateral:" + alias)
            event = progress.propose(
                epoch=self.epoch,
                kind="DIAGNOSTIC",
                known_at=self.now(),
                checkpoint={
                    "last_diagnostic_at": self.now(),
                    "scope_sha": family["scope_sha"],
                    "account_mode": report.get("account_abstraction", {}),
                    "source_equity": None,
                },
            )
            await writer.submit(
                lambda r=report, e=event: self.journal.append_collateral_diagnostic(
                    r, stream_event=e
                )
            )
        await self._reconcile_fills(writer)

    async def _reconcile_fills(self, writer):
        from datetime import timedelta
        from .pm_forward_public_trades import reconcile_public_wallet_fills
        from .pm_forward_stream_journal import read_stream_head

        end = clock(self.now())
        markets = tuple(
            Instrument.parse(key)
            for key in (
                self.scope.current["required_markets"]
                if self.scope.current
                else [i.key for i in self.configured]
            )
        )
        for address, wallet in self.watched.items():
            checkpoint = read_stream_head(self.journal.path, "reconcile:" + wallet)["checkpoint"]
            last = checkpoint.get("last_checked_end_at")
            start = (
                max(end - timedelta(days=1), clock(last)) if last else end - timedelta(minutes=5)
            )
            request = {
                "type": "userFillsByTime",
                "user": address,
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
                "aggregateByTime": False,
            }
            response = await asyncio.to_thread(self.info, request)
            known = self.now()

            def captured(actual, expected=request, result=response):
                if actual != expected:
                    raise ValueError("PUBLIC_RECONCILIATION_REQUEST_IDENTITY_MISMATCH")
                return result

            await writer.submit(
                lambda a=address, w=wallet, p=captured, s=start.isoformat(), k=known: (
                    reconcile_public_wallet_fills(
                        journal=self.journal,
                        watched={a: w},
                        start_at=s,
                        end_at=end.isoformat(),
                        required_markets=markets,
                        info=p,
                        now=lambda: k,
                    )
                )
            )

    async def _reconcile_markets(self, writer, limiter):
        from .pm_forward_public_trades import PersistentPublicMarket

        expected = (
            tuple(sorted(self.family["accounts"])) if self.family else tuple(sorted(self.parents))
        )
        scope = self.scope.update(
            {name: account.checkpoint for name, account in self.accounts.items()},
            expected_accounts=expected,
        )
        if (
            scope["scope_sha"] == self.last_scope_sha
            and self.control.checkpoint.get("census_status") == self.census_status
        ):
            return
        plan = scope["subscription_plan"]
        if plan is not None:
            desired = {("ccxt", *group) for group in plan["ccxt_shards"]}
            desired |= {("public", *group) for group in plan["public_shards"]}
            for key in list(self.jobs):
                if key != ("accounts",) and key not in desired:
                    await self._stop_job(key)
            for key in sorted(desired):
                if key in self.jobs:
                    continue
                instruments = tuple(Instrument.parse(item) for item in key[1:])
                local_stop = asyncio.Event()
                if key[0] == "ccxt":
                    work = run_ccxt_markets(
                        instruments,
                        journal=self.journal,
                        writer=writer,
                        stop=local_stop,
                        now=self.now,
                        scope_sha=scope["scope_sha"],
                        limiter=limiter,
                        factory=self.ccxt_factory,
                        receipt_clock_factory=self.receipt_clock_factory,
                    )
                else:
                    feeds = [
                        PersistentPublicMarket(
                            self.journal, inst, self.watched, scope_sha=scope["scope_sha"]
                        )
                        for inst in instruments
                    ]
                    work = run_native_public(
                        feeds,
                        writer=writer,
                        stop=local_stop,
                        connect=self.connect,
                        now=self.now,
                        limiter=limiter,
                        queue_size=self.queue_size,
                        info=self.info,
                    )
                self.jobs[key] = (local_stop, asyncio.create_task(work))
        state = {
            **self.control.checkpoint,
            "scope": scope,
            "census_status": self.census_status,
            "family_scope_sha": self.family["scope_sha"] if self.family else None,
        }
        await self.record(writer, "SCOPE", state)
        self.last_scope_sha = scope["scope_sha"]

    async def run(self, stop: asyncio.Event, *, duration_seconds: float = 0) -> dict:
        from .pm_forward_continuous_transport import SerialWriter, ConnectionBudget, wait_or_stop
        from .pm_forward_observer_health import publish_continuous_heartbeat

        limiter = ConnectionBudget(per_minute=6)
        async with SerialWriter(max_pending=self.queue_size) as writer:
            await self.record(
                writer,
                "START",
                {
                    "manifest": self.manifest,
                    "started_at": self.started_at,
                    "census_status": "UNKNOWN",
                    "source_nav_attested": False,
                    "financial_admission": "BLOCKED_NO_TRADE",
                    "order_route": "NONE",
                },
            )

            async def maintenance():
                last_refresh = -float("inf")
                refresh_task = None
                try:
                    while not stop.is_set():
                        if writer.failed:
                            raise writer.failed
                        for _, task in self.jobs.values():
                            if task.done():
                                await task
                                raise ValueError("STREAM_SUPERVISOR_CHILD_EXITED")
                        if (
                            refresh_task is None
                            and monotonic() - last_refresh >= self.refresh_seconds
                        ):
                            refresh_task = asyncio.create_task(
                                self._refresh_family(writer, limiter)
                            )
                            last_refresh = monotonic()
                        if refresh_task is not None and refresh_task.done():
                            try:
                                await refresh_task
                            except Exception as exc:
                                if writer.failed:
                                    raise
                                self.census_status = "UNKNOWN_CENSUS_REFRESH_FAILED"
                                await self.record(
                                    writer,
                                    "GAP",
                                    {
                                        **self.control.checkpoint,
                                        "census_status": self.census_status,
                                    },
                                    reason=_reason(exc),
                                )
                            refresh_task = None
                        await self._reconcile_markets(writer, limiter)
                        await wait_or_stop(stop, min(1, self.heartbeat_seconds))
                finally:
                    if refresh_task is not None:
                        refresh_task.cancel()
                        await asyncio.gather(refresh_task, return_exceptions=True)

            async def heartbeat():
                import resource

                while not stop.is_set():
                    free = shutil.disk_usage(self.journal.root).free
                    size = _journal_storage_bytes(self.journal.path)
                    if free < self.min_free_bytes or size > self.max_journal_bytes:
                        raise OSError("STREAM_STORAGE_BUDGET_EXHAUSTED")
                    await asyncio.to_thread(
                        publish_continuous_heartbeat,
                        self.journal.root,
                        revision=self.manifest["revision"],
                        manifest_sha=self.manifest["manifest_sha"],
                        started_at=self.started_at,
                        now=self.now(),
                        metrics={
                            "queue_depth": writer.queue.qsize(),
                            "queue_high_water": writer.high_water,
                            "queue_capacity": self.queue_size,
                            "journal_bytes": size,
                            "disk_free_bytes": free,
                            "min_free_bytes": self.min_free_bytes,
                            "max_journal_bytes": self.max_journal_bytes,
                            "elapsed_process_seconds": monotonic() - self.started_monotonic,
                            "process_peak_rss_bytes": resource.getrusage(
                                resource.RUSAGE_SELF
                            ).ru_maxrss
                            * 1024,
                            "process_cpu_seconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime
                            + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
                            "dial_attempts_last_minute": sum(
                                t >= monotonic() - 60 for t in limiter.attempts
                            ),
                            "active_supervised_jobs": len(self.jobs),
                        },
                    )
                    await wait_or_stop(stop, self.heartbeat_seconds)

            async def deadline():
                if duration_seconds:
                    await wait_or_stop(stop, duration_seconds)
                    stop.set()
                else:
                    await stop.wait()

            tasks = [
                asyncio.create_task(maintenance()),
                asyncio.create_task(heartbeat()),
                asyncio.create_task(deadline()),
            ]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            finally:
                stop.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                shutdown_errors = []
                for key in list(self.jobs):
                    try:
                        await self._stop_job(key)
                    except Exception as exc:
                        shutdown_errors.append(exc)
                if writer.failed is None:
                    await self.record(
                        writer, "STOP", {**self.control.checkpoint, "stopped_at": self.now()}
                    )
                if shutdown_errors:
                    raise shutdown_errors[0]
        return {
            "status": "OBSERVATION_STOPPED",
            "elapsed_seconds": monotonic() - self.started_monotonic,
            "source_nav_attested": False,
            "financial_events_committed": 0,
            "paper_observed": False,
            "order_route": "NONE",
        }
