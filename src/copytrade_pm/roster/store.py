"""SQLite persistence for roster evidence, books, latches, vetoes and proposals.

The store is the roster's only IO boundary. It is stdlib-only (no Polars, no
pydantic, no network) so a read-only consumer can inspect roster state without
the research stack, and it keeps every authority table append-only:

* ``books`` rows are immutable snapshots (UPDATE/DELETE are abort triggers).
* ``leases`` and ``draining`` are insert-only; a settled draining owner is marked
  by their omission from a successor book.
* ``policies`` rows are immutable, mirroring the signed release policy contract.
* Scorecards and bench snapshots are idempotent by content SHA: recording the
  same evidence twice writes one row and returns the same digest.

Reads merge independent verdicts at read time: a latched ``CUSUM_KILL`` (Q12)
and an active :class:`OperatorVeto` are appended to the stored scorecard
``failures`` so no caller can forget them.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping, Sequence

from copytrade_kernel import KnownAtTs

from .models import (
    BenchCandidate,
    CooldownRecord,
    GateFailure,
    OperatorVeto,
    RosterCUSUMState,
    SeatBook,
    SeatLease,
    SeatSpec,
    WalletScorecard,
    as_decimal,
    canonical,
    decimal_text,
    digest,
    wallet_address,
)
from .proposals import ReleaseBinding, ReleaseProposal, build_release_proposal
from .reconciler import ReconcilePlan

__all__ = ["CommitReceipt", "RosterStore", "RosterStoreError"]

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts(
    account_id TEXT PRIMARY KEY,
    policy_epoch TEXT NOT NULL,
    seats TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    UNIQUE(account_id)
);
CREATE TABLE IF NOT EXISTS scorecards(
    wallet TEXT NOT NULL,
    scorecard_sha TEXT NOT NULL,
    as_of_ms INTEGER NOT NULL,
    payload TEXT NOT NULL,
    recorded_ms INTEGER NOT NULL,
    PRIMARY KEY(wallet, scorecard_sha)
);
CREATE TABLE IF NOT EXISTS bench(
    account_id TEXT NOT NULL,
    as_of_ms INTEGER NOT NULL,
    payload TEXT NOT NULL,
    bench_sha TEXT NOT NULL,
    recorded_ms INTEGER NOT NULL,
    PRIMARY KEY(account_id, as_of_ms),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS books(
    account_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    as_of_ms INTEGER NOT NULL,
    book_sha TEXT NOT NULL,
    plan_sha TEXT NOT NULL,
    payload TEXT NOT NULL,
    committed_ms INTEGER NOT NULL,
    PRIMARY KEY(account_id, sequence),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS leases(
    account_id TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    owner TEXT NOT NULL,
    wallet TEXT NOT NULL,
    opened_ms INTEGER NOT NULL,
    scorecard_sha TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(account_id, seat_id, generation),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS draining(
    account_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    wallet TEXT NOT NULL,
    retired_ms INTEGER NOT NULL,
    reason TEXT NOT NULL,
    settled_ms INTEGER,
    PRIMARY KEY(account_id, owner),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS vetoes(
    wallet TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    expires_ms INTEGER,
    revoked_ms INTEGER,
    PRIMARY KEY(wallet, created_ms)
);
CREATE TABLE IF NOT EXISTS cusum(
    wallet TEXT NOT NULL,
    policy_epoch TEXT NOT NULL,
    s_neg TEXT NOT NULL,
    episodes_seen INTEGER NOT NULL,
    retired_latch INTEGER NOT NULL,
    retired_reason TEXT,
    observed_ms INTEGER NOT NULL,
    PRIMARY KEY(wallet, policy_epoch)
);
CREATE TABLE IF NOT EXISTS cusum_events(
    wallet TEXT NOT NULL,
    policy_epoch TEXT NOT NULL,
    at_ms INTEGER NOT NULL,
    increment TEXT NOT NULL,
    s_neg TEXT NOT NULL,
    retired_latch INTEGER NOT NULL,
    PRIMARY KEY(wallet, policy_epoch, at_ms, increment)
);
CREATE TABLE IF NOT EXISTS cooldowns(
    wallet TEXT PRIMARY KEY,
    evicted_ms INTEGER NOT NULL,
    last_failure_ms INTEGER NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS release_bindings(
    account_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    payload TEXT NOT NULL,
    binding_sha TEXT NOT NULL,
    recorded_ms INTEGER NOT NULL,
    PRIMARY KEY(account_id, generation),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS proposals(
    account_id TEXT NOT NULL,
    day TEXT NOT NULL,
    generation INTEGER NOT NULL,
    proposal_sha TEXT NOT NULL,
    plan_sha TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    signed_sha TEXT,
    PRIMARY KEY(account_id, day),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TABLE IF NOT EXISTS policies(
    account_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    known_at_ms INTEGER NOT NULL,
    policy_sha TEXT NOT NULL,
    envelope TEXT NOT NULL,
    PRIMARY KEY(account_id, generation),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);
CREATE TRIGGER IF NOT EXISTS books_no_update BEFORE UPDATE ON books
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_BOOK'); END;
CREATE TRIGGER IF NOT EXISTS books_no_delete BEFORE DELETE ON books
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_BOOK'); END;
CREATE TRIGGER IF NOT EXISTS leases_no_update BEFORE UPDATE ON leases
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_LEASE'); END;
CREATE TRIGGER IF NOT EXISTS leases_no_delete BEFORE DELETE ON leases
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_LEASE'); END;
CREATE TRIGGER IF NOT EXISTS policies_no_update BEFORE UPDATE ON policies
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_POLICY'); END;
CREATE TRIGGER IF NOT EXISTS policies_no_delete BEFORE DELETE ON policies
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_POLICY'); END;
CREATE TRIGGER IF NOT EXISTS draining_no_update BEFORE UPDATE ON draining
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_DRAINING'); END;
CREATE TRIGGER IF NOT EXISTS draining_no_delete BEFORE DELETE ON draining
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ROSTER_DRAINING'); END;
CREATE TRIGGER IF NOT EXISTS cusum_events_no_update BEFORE UPDATE ON cusum_events
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CUSUM_EVENT'); END;
CREATE TRIGGER IF NOT EXISTS cusum_events_no_delete BEFORE DELETE ON cusum_events
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CUSUM_EVENT'); END;
"""

_AUTHORITY_TABLES = (
    "accounts",
    "books",
    "leases",
    "draining",
    "scorecards",
    "bench",
    "vetoes",
    "cusum",
    "cusum_events",
    "cooldowns",
    "release_bindings",
    "proposals",
    "policies",
)

# The release inventory must not include the release artifacts themselves, or a
# proposal's digest would depend on whether it had already been staged.
_INVENTORY_TABLES = tuple(
    table for table in _AUTHORITY_TABLES if table not in ("proposals", "policies")
)


_OBSERVER_KEYS = {
    "accounts": ("account_id",),
    "books": ("account_id", "sequence"),
    "leases": ("account_id", "seat_id", "generation"),
    "draining": ("account_id", "owner"),
    "vetoes": ("wallet", "created_ms"),
    "cusum": ("wallet", "policy_epoch"),
    "cusum_events": ("wallet", "policy_epoch", "at_ms", "increment"),
    "policies": ("account_id", "generation"),
}
_SEALED_TABLES = ("books", "policies", "leases", "draining")
DEFAULT_ROSTER_PATH = Path.home() / ".local/share/copytrade/roster.sqlite"


def _check_sealed_triggers(con: sqlite3.Connection) -> None:
    expected = {}
    for statement in DDL.strip().split(";\n"):
        if statement.startswith("CREATE TRIGGER IF NOT EXISTS "):
            sql = statement.replace(" IF NOT EXISTS", "", 1)
            name = sql.split()[2]
            if name.rsplit("_no_", 1)[0] in _SEALED_TABLES:
                expected[name] = sql
    actual = dict(
        con.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type='trigger'"
            " AND tbl_name IN ('books','policies','leases','draining')"
        )
    )
    if actual != expected:
        raise ValueError("ROSTER_APPEND_ONLY_TRIGGERS")


def _verified_book(con: sqlite3.Connection, row: sqlite3.Row) -> SeatBook:
    body = json.loads(row["payload"])
    book = SeatBook.parse(body)
    if (
        canonical(body) != canonical(book.data)
        or book.sha != row["book_sha"]
        or (book.account_id, book.sequence, book.as_of.value)
        != (row["account_id"], row["sequence"], row["as_of_ms"])
    ):
        raise ValueError("BOOK_SHA_OR_IDENTITY_DRIFT")
    for lease in book.leases:
        stored = con.execute(
            "SELECT owner,wallet,opened_ms,scorecard_sha,payload FROM leases"
            " WHERE account_id=? AND seat_id=? AND generation=?",
            (book.account_id, lease.seat_id, lease.generation),
        ).fetchone()
        if (
            stored is None
            or tuple(stored)[:4] != (lease.owner, lease.wallet, lease.since_ms, lease.scorecard_sha)
            or digest(json.loads(stored["payload"])) != digest(lease.data)
        ):
            raise ValueError("LEASE_SHA_OR_IDENTITY_DRIFT")
    for entry in book.draining:
        stored = con.execute(
            "SELECT seat_id,generation,wallet,retired_ms,reason FROM draining"
            " WHERE account_id=? AND owner=?",
            (book.account_id, entry.owner),
        ).fetchone()
        if stored is None or tuple(stored) != (
            entry.seat_id,
            entry.generation,
            entry.wallet,
            entry.retired_ms,
            entry.reason.value,
        ):
            raise ValueError("DRAINING_IDENTITY_DRIFT")
    return book


class RosterStoreError(RuntimeError):
    """Fail-closed roster store error."""


def _now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def _signature_epoch(policy_epoch: object) -> str:
    if not isinstance(policy_epoch, str) or not policy_epoch:
        raise ValueError("INVALID_POLICY_EPOCH")
    return policy_epoch


class CommitReceipt:
    """Result of :meth:`RosterStore.commit_plan`; never a trading authorization."""

    __slots__ = (
        "account_id",
        "book_sha",
        "changed",
        "plan_sha",
        "proposal_sha",
        "proposal_state",
        "sequence",
    )

    def __init__(
        self,
        *,
        account_id: str,
        sequence: int,
        book_sha: str,
        plan_sha: str,
        changed: bool,
        proposal_sha: str | None,
        proposal_state: str,
    ) -> None:
        self.account_id = account_id
        self.sequence = sequence
        self.book_sha = book_sha
        self.plan_sha = plan_sha
        self.changed = changed
        self.proposal_sha = proposal_sha
        self.proposal_state = proposal_state

    @property
    def data(self) -> dict[str, Any]:
        return {
            "schema": "roster_commit_receipt_v1",
            "account_id": self.account_id,
            "sequence": self.sequence,
            "book_sha": self.book_sha,
            "plan_sha": self.plan_sha,
            "changed": self.changed,
            "proposal_sha": self.proposal_sha,
            "proposal_state": self.proposal_state,
            "trading_authorized": False,
        }

    @property
    def sha(self) -> str:
        return digest(self.data)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"CommitReceipt({self.data!r})"


class RosterStore:
    """Typed roster persistence. Writes require an explicit ``writable`` store."""

    def __init__(
        self,
        path: Path | str,
        *,
        create: bool = False,
        writable: bool = False,
        clock: Any = None,
    ) -> None:
        self.path = Path(path).expanduser().absolute()
        self.writable = bool(writable or create)
        self._clock = clock or _now_ms
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("STREAM_REGISTRY_FILE_INVALID")
        if not self.path.exists():
            if not create:
                raise FileNotFoundError(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "rwc" if create else ("rw" if self.writable else "ro")
        self._con = sqlite3.connect(
            f"{self.path.as_uri()}?mode={mode}", uri=True, timeout=30, isolation_level=None
        )
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.execute("PRAGMA recursive_triggers=ON")
        self._con.execute("PRAGMA busy_timeout=30000")
        if create:
            self._con.executescript(DDL)
            self._con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> RosterStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        with closing(self._con):
            pass

    def _tx(self):
        return _Transaction(self)

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        """Keep related reads on one SQLite snapshot, including within writes."""
        owns_snapshot = not self._con.in_transaction
        if owns_snapshot:
            self._con.execute("BEGIN")
        try:
            yield
        finally:
            if owns_snapshot:
                self._con.rollback()

    def _require_writable(self) -> None:
        if not self.writable:
            raise RosterStoreError("ROSTER_READ_ONLY")

    def _require_schema(self) -> int:
        row = self._con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None or row["value"] != str(SCHEMA_VERSION):
            raise RosterStoreError("ROSTER_SCHEMA_VERSION")
        return SCHEMA_VERSION

    # -- accounts ----------------------------------------------------------
    def register_account(
        self,
        account_id: str,
        seats: Sequence[SeatSpec],
        *,
        policy_epoch: str,
        at_ms: int | None = None,
    ) -> str:
        self._require_writable()
        self._require_schema()
        specs = tuple(seats)
        if not specs:
            raise ValueError("EMPTY_SEAT_SET")
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("INVALID_ACCOUNT_ID")
        epoch = _signature_epoch(policy_epoch)
        payload = canonical([spec.data for spec in specs])
        stamp = _now_ms() if at_ms is None else int(at_ms)
        with self._tx() as con:
            row = con.execute(
                "SELECT policy_epoch, seats FROM accounts WHERE account_id=?", (account_id,)
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO accounts(account_id, policy_epoch, seats, created_ms)"
                    " VALUES(?,?,?,?)",
                    (account_id, epoch, payload.decode(), stamp),
                )
            elif row["policy_epoch"] != epoch or row["seats"] != payload.decode():
                if row["policy_epoch"] != epoch:
                    raise ValueError("ACCOUNT_POLICY_EPOCH_DRIFT")
                raise ValueError("ACCOUNT_SEATS_DRIFT")
        return digest(
            {
                "account_id": account_id,
                "policy_epoch": epoch,
                "seats": [spec.data for spec in specs],
            }
        )

    def accounts(self) -> tuple[str, ...]:
        self._require_schema()
        return tuple(
            row["account_id"]
            for row in self._con.execute("SELECT account_id FROM accounts ORDER BY account_id")
        )

    def seats(self, account_id: str) -> tuple[SeatSpec, ...]:
        self._require_schema()
        row = self._con.execute(
            "SELECT seats FROM accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return tuple(
            SeatSpec(
                seat_id=item["seat_id"],
                risk_unit_usd=item["risk_unit_usd"],
                max_cdar_share=item["max_cdar_share"],
            )
            for item in json.loads(row["seats"])
        )

    def policy_epoch(self, account_id: str) -> str:
        self._require_schema()
        row = self._con.execute(
            "SELECT policy_epoch FROM accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return str(row["policy_epoch"])

    # -- evidence ----------------------------------------------------------
    def record_scorecard(
        self, scorecard: WalletScorecard, *, recorded_ms: int | None = None
    ) -> str:
        """Idempotent by content SHA; returns the scorecard digest."""
        self._require_writable()
        self._require_schema()
        if not isinstance(scorecard, WalletScorecard):
            raise ValueError("INVALID_SCORECARD")
        stamp = _now_ms() if recorded_ms is None else int(recorded_ms)
        with self._tx() as con:
            con.execute(
                "INSERT OR IGNORE INTO scorecards"
                "(wallet, scorecard_sha, as_of_ms, payload, recorded_ms) VALUES(?,?,?,?,?)",
                (
                    scorecard.wallet,
                    scorecard.sha,
                    scorecard.as_of.value,
                    canonical(scorecard.data).decode(),
                    stamp,
                ),
            )
        return scorecard.sha

    def latest_scorecard(
        self,
        *,
        as_of: KnownAtTs,
        include_vetoes: bool = True,
        policy_epoch: str | None = None,
    ) -> dict[str, WalletScorecard]:
        """Latest stored card per wallet with ``as_of_ms <= as_of``, plus latches."""
        self._require_schema()
        if not isinstance(as_of, KnownAtTs):
            raise ValueError("INVALID_CLOCK")
        rows = self._con.execute(
            "SELECT wallet, payload FROM scorecards WHERE as_of_ms<=?"
            " ORDER BY wallet, as_of_ms DESC, recorded_ms DESC",
            (as_of.value,),
        ).fetchall()
        cards: dict[str, WalletScorecard] = {}
        for row in rows:
            if row["wallet"] in cards:
                continue
            cards[row["wallet"]] = WalletScorecard.parse(json.loads(row["payload"]))
        # Only latches under an epoch that is still registered for an account are
        # live; a latch recorded under a retired epoch is history, not evidence.
        epochs = (
            (policy_epoch,)
            if policy_epoch is not None
            else tuple(
                row["policy_epoch"]
                for row in self._con.execute("SELECT DISTINCT policy_epoch FROM accounts")
            )
        )
        latched = {
            wallet
            for epoch in epochs
            for wallet in self.latched_wallets(policy_epoch=epoch, as_of=as_of)
        }
        vetoed = self.vetoed_wallets(as_of=as_of) if include_vetoes else frozenset()
        for wallet, card in tuple(cards.items()):
            if wallet in latched:
                cards[wallet] = card.with_failure(GateFailure.CUSUM_KILL)
            if wallet in vetoed:
                cards[wallet] = card.with_failure(GateFailure.OPERATOR_VETO)
        return cards

    def scorecard_at(self, wallet: str, *, as_of: KnownAtTs) -> WalletScorecard | None:
        return self.latest_scorecard(as_of=as_of, include_vetoes=False).get(wallet_address(wallet))

    def record_bench(
        self,
        account_id: str,
        candidates: Sequence[BenchCandidate],
        *,
        as_of: KnownAtTs,
        recorded_ms: int | None = None,
    ) -> str:
        self._require_writable()
        self._require_schema()
        if not isinstance(as_of, KnownAtTs):
            raise ValueError("INVALID_CLOCK")
        items = tuple(candidates)
        for candidate in items:
            if not isinstance(candidate, BenchCandidate):
                raise ValueError("INVALID_BENCH_CANDIDATE")
        payload = [candidate.data for candidate in items]
        bench_sha = digest(sorted(payload, key=lambda item: item["wallet"]))
        stamp = _now_ms() if recorded_ms is None else int(recorded_ms)
        with self._tx() as con:
            con.execute(
                "INSERT OR REPLACE INTO bench(account_id, as_of_ms, payload, bench_sha,"
                " recorded_ms) VALUES(?,?,?,?,?)",
                (account_id, as_of.value, canonical(payload).decode(), bench_sha, stamp),
            )
        return bench_sha

    def latest_bench(self, account_id: str, *, as_of: KnownAtTs) -> tuple[BenchCandidate, ...]:
        self._require_schema()
        row = self._con.execute(
            "SELECT payload FROM bench WHERE account_id=? AND as_of_ms<=?"
            " ORDER BY as_of_ms DESC LIMIT 1",
            (account_id, as_of.value),
        ).fetchone()
        if row is None:
            return ()
        return tuple(BenchCandidate.parse(item) for item in json.loads(row["payload"]))

    # -- books -------------------------------------------------------------
    def book_at(self, account_id: str, *, as_of: KnownAtTs) -> SeatBook:
        """Latest committed book at or before ``as_of``; empty book before any commit."""
        self._require_schema()
        if not isinstance(as_of, KnownAtTs):
            raise ValueError("INVALID_CLOCK")
        row = self._con.execute(
            "SELECT payload FROM books WHERE account_id=? AND as_of_ms<=?"
            " ORDER BY sequence DESC LIMIT 1",
            (account_id, as_of.value),
        ).fetchone()
        if row is not None:
            return SeatBook.parse(json.loads(row["payload"]))
        return SeatBook.empty(
            account_id,
            self.seats(account_id),
            as_of=as_of,
            policy_epoch=self.policy_epoch(account_id),
        )

    def verified_book_at(self, account_id: str, *, as_of: KnownAtTs) -> SeatBook | None:
        """Verify the exact persisted PIT book and every matching lease row."""
        with self.read_snapshot():
            self._require_schema()
            row = self._con.execute(
                "SELECT books.* FROM books JOIN accounts USING(account_id)"
                " WHERE account_id=? AND as_of_ms<=? AND committed_ms<=? AND accounts.created_ms<=?"
                " ORDER BY sequence DESC LIMIT 1",
                (account_id, as_of.value, as_of.value, as_of.value),
            ).fetchone()
            return _verified_book(self._con, row) if row is not None else None

    def observer_books_at(
        self, account_ids: Sequence[str], *, as_of: KnownAtTs
    ) -> tuple[SeatBook, ...]:
        """Resolve one coherent watch scope, including FLAT and unsettled residuals."""
        with self.read_snapshot():
            books = []
            for account_id in account_ids:
                if (
                    self._con.execute(
                        "SELECT 1 FROM accounts WHERE account_id=? AND created_ms<=?",
                        (account_id, as_of.value),
                    ).fetchone()
                    is None
                ):
                    raise ValueError("SELECTION_UNKNOWN_AT_ASOF")
                book = self.verified_book_at(account_id, as_of=as_of)
                if book is None:
                    book = SeatBook.empty(
                        account_id,
                        self.seats(account_id),
                        as_of=as_of,
                        policy_epoch=self.policy_epoch(account_id),
                    )
                books.append(book)
            return tuple(books)

    def latest_book(self, account_id: str) -> SeatBook | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT payload FROM books WHERE account_id=? ORDER BY sequence DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        return SeatBook.parse(json.loads(row["payload"])) if row else None

    def commit_plan(
        self,
        plan: ReconcilePlan,
        *,
        committed_ms: int | None = None,
        with_proposal: bool = True,
    ) -> CommitReceipt:
        """Append the plan's book, leases and draining rows (idempotent)."""
        self._require_writable()
        self._require_schema()
        if not isinstance(plan, ReconcilePlan):
            raise ValueError("INVALID_PLAN")
        account_id = plan.account_id
        stamp = _now_ms() if committed_ms is None else int(committed_ms)
        current = self.latest_book(account_id)
        if not plan.changed:
            # A daily cycle still stages today's proposal (decision: one batched
            # unsigned proposal per day) even when no seat changed.
            if current is None:
                proposal_sha, proposal_state = (None, "UNCHANGED")
                if with_proposal and plan.next_book.leases:
                    proposal_sha, proposal_state = self._stage_proposal(plan.next_book, plan, stamp)
                return CommitReceipt(
                    account_id=account_id,
                    sequence=0,
                    book_sha=plan.next_book.sha,
                    plan_sha=plan.sha,
                    changed=False,
                    proposal_sha=proposal_sha,
                    proposal_state=proposal_state,
                )
            if current.sha != plan.before.sha:
                raise ValueError("PLAN_PRECEDES_COMMITTED_BOOK")
            proposal_sha, proposal_state = (self._proposal_for_day(account_id, stamp), "UNCHANGED")
            if with_proposal:
                proposal_sha, proposal_state = self._stage_proposal(current, plan, stamp)
            return CommitReceipt(
                account_id=account_id,
                sequence=current.sequence,
                book_sha=current.sha,
                plan_sha=plan.sha,
                changed=False,
                proposal_sha=proposal_sha,
                proposal_state=proposal_state,
            )
        if current is not None and plan.before.sha != current.sha:
            raise ValueError("PLAN_PRECEDES_COMMITTED_BOOK")
        sequence = 1 if current is None else current.sequence + 1
        book = SeatBook(
            account_id=plan.next_book.account_id,
            as_of=plan.next_book.as_of,
            policy_epoch=plan.next_book.policy_epoch,
            seats=plan.next_book.seats,
            draining=plan.next_book.draining,
            sequence=sequence,
        )
        with self._tx() as con:
            con.execute(
                "INSERT INTO books(account_id, sequence, as_of_ms, book_sha, plan_sha,"
                " payload, committed_ms) VALUES(?,?,?,?,?,?,?)",
                (
                    account_id,
                    sequence,
                    book.as_of.value,
                    book.sha,
                    plan.sha,
                    canonical(book.data).decode(),
                    stamp,
                ),
            )
            for change in plan.promoted:
                lease = book.lease(change.seat_id)
                if lease is None:
                    raise ValueError("PROMOTION_WITHOUT_LEASE")
                con.execute(
                    "INSERT OR IGNORE INTO leases(account_id, seat_id, generation, owner,"
                    " wallet, opened_ms, scorecard_sha, payload) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        account_id,
                        lease.seat_id,
                        lease.generation,
                        lease.owner,
                        lease.wallet,
                        lease.since_ms,
                        lease.scorecard_sha,
                        canonical(lease.data).decode(),
                    ),
                )
            for entry in book.draining:
                con.execute(
                    "INSERT OR IGNORE INTO draining(account_id, owner, seat_id, generation,"
                    " wallet, retired_ms, reason, settled_ms) VALUES(?,?,?,?,?,?,?,NULL)",
                    (
                        account_id,
                        entry.owner,
                        entry.seat_id,
                        entry.generation,
                        entry.wallet,
                        entry.retired_ms,
                        entry.reason.value,
                    ),
                )
            # Omission from a successor book marks settlement. The original drain stays immutable.
            for change in plan.evicted:
                if change.reason in {
                    GateFailure.ACCOUNT_VALUE_BELOW_FLOOR.value,
                    GateFailure.NO_ACTIVE_FILLS.value,
                }:
                    con.execute(
                        "INSERT INTO cooldowns(wallet, evicted_ms, last_failure_ms, reason)"
                        " VALUES(?,?,?,?) ON CONFLICT(wallet) DO UPDATE SET"
                        " evicted_ms=excluded.evicted_ms,"
                        " last_failure_ms=excluded.last_failure_ms, reason=excluded.reason",
                        (change.wallet, stamp, stamp, change.reason),
                    )
        proposal_sha: str | None = None
        proposal_state = "DISABLED"
        if with_proposal:
            proposal_sha, proposal_state = self._stage_proposal(book, plan, stamp)
        return CommitReceipt(
            account_id=account_id,
            sequence=sequence,
            book_sha=book.sha,
            plan_sha=plan.sha,
            changed=True,
            proposal_sha=proposal_sha,
            proposal_state=proposal_state,
        )

    # -- vetoes ------------------------------------------------------------
    def record_veto(
        self,
        wallet: str,
        *,
        reason: str,
        actor: str,
        at_ms: int,
        expires_ms: int | None = None,
    ) -> OperatorVeto:
        self._require_writable()
        self._require_schema()
        veto = OperatorVeto(
            wallet=wallet,
            reason=reason,
            actor=actor,
            created_ms=int(at_ms),
            expires_ms=expires_ms,
        )
        with self._tx() as con:
            con.execute(
                "INSERT OR IGNORE INTO vetoes(wallet, created_ms, reason, actor, expires_ms,"
                " revoked_ms) VALUES(?,?,?,?,?,NULL)",
                (veto.wallet, veto.created_ms, veto.reason, veto.actor, veto.expires_ms),
            )
        return veto

    def revoke_veto(self, wallet: str, *, at_ms: int) -> int:
        self._require_writable()
        self._require_schema()
        with self._tx() as con:
            rows = con.execute(
                "SELECT created_ms FROM vetoes WHERE wallet=? AND revoked_ms IS NULL",
                (wallet_address(wallet),),
            ).fetchall()
            for row in rows:
                con.execute(
                    "UPDATE vetoes SET revoked_ms=? WHERE wallet=? AND created_ms=?",
                    (int(at_ms), wallet_address(wallet), row["created_ms"]),
                )
        return len(rows)

    def active_vetoes(self, *, as_of: KnownAtTs) -> tuple[OperatorVeto, ...]:
        self._require_schema()
        out: list[OperatorVeto] = []
        for row in self._con.execute(
            "SELECT wallet, created_ms, reason, actor, expires_ms, revoked_ms FROM vetoes"
            " ORDER BY created_ms, wallet"
        ):
            veto = OperatorVeto.parse(dict(row))
            if veto.active(as_of):
                out.append(veto)
        return tuple(out)

    def vetoed_wallets(self, *, as_of: KnownAtTs) -> frozenset[str]:
        return frozenset(veto.wallet for veto in self.active_vetoes(as_of=as_of))

    # -- CUSUM latch -------------------------------------------------------
    def cusum_state(
        self, wallet: str, *, policy_epoch: str, as_of: KnownAtTs | None = None
    ) -> RosterCUSUMState:
        self._require_schema()
        wallet = wallet_address(wallet)
        if as_of is not None:
            row = self._con.execute(
                "SELECT s_neg, retired_latch, at_ms, COUNT(*) OVER () AS episodes_seen"
                " FROM cusum_events WHERE wallet=? AND policy_epoch=? AND at_ms<=?"
                " ORDER BY at_ms DESC, rowid DESC LIMIT 1",
                (wallet, policy_epoch, as_of.value),
            ).fetchone()
            if row is None:
                return RosterCUSUMState.initial(wallet, policy_epoch, at_ms=0)
            return RosterCUSUMState.parse(
                {
                    "wallet": wallet,
                    "policy_epoch": policy_epoch,
                    "s_neg": row["s_neg"],
                    "episodes_seen": row["episodes_seen"],
                    "retired_latch": row["retired_latch"],
                    "retired_reason": GateFailure.CUSUM_KILL.value
                    if row["retired_latch"]
                    else None,
                    "observed_ms": row["at_ms"],
                }
            )
        row = self._con.execute(
            "SELECT * FROM cusum WHERE wallet=? AND policy_epoch=?",
            (wallet, policy_epoch),
        ).fetchone()
        if row is None:
            return RosterCUSUMState.initial(wallet_address(wallet), policy_epoch, at_ms=0)
        return RosterCUSUMState.parse(dict(row))

    def observe_cusum(
        self,
        wallet: str,
        increment: Any,
        *,
        threshold: Any,
        policy_epoch: str,
        at_ms: int,
    ) -> RosterCUSUMState:
        """Record one CUSUM increment; the latch is terminal within its epoch."""
        self._require_writable()
        self._require_schema()
        before = self.cusum_state(wallet, policy_epoch=policy_epoch)
        after = before.observe(as_decimal(increment), threshold=threshold, at_ms=int(at_ms))
        with self._tx() as con:
            con.execute(
                "INSERT OR REPLACE INTO cusum(wallet, policy_epoch, s_neg, episodes_seen,"
                " retired_latch, retired_reason, observed_ms) VALUES(?,?,?,?,?,?,?)",
                (
                    after.wallet,
                    after.policy_epoch,
                    decimal_text(after.s_neg),
                    after.episodes_seen,
                    int(after.retired_latch),
                    after.retired_reason.value if after.retired_reason else None,
                    after.observed_ms,
                ),
            )
            con.execute(
                "INSERT OR IGNORE INTO cusum_events(wallet, policy_epoch, at_ms, increment,"
                " s_neg, retired_latch) VALUES(?,?,?,?,?,?)",
                (
                    after.wallet,
                    after.policy_epoch,
                    int(at_ms),
                    decimal_text(as_decimal(increment)),
                    decimal_text(after.s_neg),
                    int(after.retired_latch),
                ),
            )
        return after

    def latched_wallets(
        self, *, policy_epoch: str | None = None, as_of: KnownAtTs | None = None
    ) -> tuple[str, ...]:
        self._require_schema()
        if as_of is not None:
            rows = self._con.execute(
                "SELECT DISTINCT wallet FROM cusum_events WHERE retired_latch=1 AND at_ms<=?"
                " AND (? IS NULL OR policy_epoch=?) ORDER BY wallet",
                (as_of.value, policy_epoch, policy_epoch),
            )
            return tuple(row["wallet"] for row in rows)
        if policy_epoch is None:
            rows = self._con.execute(
                "SELECT wallet FROM cusum WHERE retired_latch=1 ORDER BY wallet"
            )
        else:
            rows = self._con.execute(
                "SELECT wallet FROM cusum WHERE retired_latch=1 AND policy_epoch=? ORDER BY wallet",
                (policy_epoch,),
            )
        return tuple(row["wallet"] for row in rows)

    def clear_epoch(self, policy_epoch: str, *, at_ms: int | None = None) -> int:
        """Explicit new policy epoch: drop latched states recorded under other epochs."""
        self._require_writable()
        self._require_schema()
        _signature_epoch(policy_epoch)
        stamp = _now_ms() if at_ms is None else int(at_ms)
        with self._tx() as con:
            same_epoch = con.execute(
                "SELECT COUNT(*) FROM cusum WHERE retired_latch=1 AND policy_epoch=?",
                (policy_epoch,),
            ).fetchone()[0]
            if same_epoch:
                # A latch is terminal inside its own epoch: only a *new* epoch clears.
                raise ValueError("CUSUM_LATCH_EPOCH_UNCHANGED")
            rows = con.execute(
                "SELECT wallet, policy_epoch FROM cusum WHERE retired_latch=1 AND policy_epoch<>?",
                (policy_epoch,),
            ).fetchall()
            for row in rows:
                con.execute(
                    "INSERT OR REPLACE INTO cusum(wallet, policy_epoch, s_neg, episodes_seen,"
                    " retired_latch, retired_reason, observed_ms) VALUES(?,?,?,?,?,?,?)",
                    (row["wallet"], policy_epoch, "0", 0, 0, None, stamp),
                )
            for row in con.execute(
                "SELECT account_id FROM accounts WHERE policy_epoch<>?", (policy_epoch,)
            ).fetchall():
                con.execute(
                    "UPDATE accounts SET policy_epoch=? WHERE account_id=?",
                    (policy_epoch, row["account_id"]),
                )
        return len(rows)

    def cooldowns(self) -> tuple[CooldownRecord, ...]:
        self._require_schema()
        return tuple(
            CooldownRecord.parse(dict(row))
            for row in self._con.execute("SELECT * FROM cooldowns ORDER BY wallet")
        )

    def cooldown(self, wallet: str) -> CooldownRecord | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT * FROM cooldowns WHERE wallet=?", (wallet_address(wallet),)
        ).fetchone()
        return CooldownRecord.parse(dict(row)) if row else None

    def note_cooldown_failure(self, wallet: str, *, at_ms: int, reason: GateFailure) -> None:
        """A failing observation resets the continuous cooldown window."""
        self._require_writable()
        self._require_schema()
        with self._tx() as con:
            con.execute(
                "UPDATE cooldowns SET last_failure_ms=?, reason=? WHERE wallet=?",
                (int(at_ms), reason.value, wallet_address(wallet)),
            )

    # -- release bindings and proposals ------------------------------------
    def record_release_binding(
        self, binding: ReleaseBinding, *, recorded_ms: int | None = None
    ) -> str:
        self._require_writable()
        self._require_schema()
        if not isinstance(binding, ReleaseBinding):
            raise ValueError("INVALID_RELEASE_BINDING")
        stamp = _now_ms() if recorded_ms is None else int(recorded_ms)
        with self._tx() as con:
            row = con.execute(
                "SELECT MAX(generation) AS generation FROM release_bindings WHERE account_id=?",
                (binding.account_id,),
            ).fetchone()
            latest = row["generation"] if row and row["generation"] is not None else 0
            if binding.generation <= latest:
                raise ValueError("RELEASE_BINDING_ROLLBACK")
            con.execute(
                "INSERT INTO release_bindings(account_id, generation, payload, binding_sha,"
                " recorded_ms) VALUES(?,?,?,?,?)",
                (
                    binding.account_id,
                    binding.generation,
                    canonical(binding.data).decode(),
                    binding.sha,
                    stamp,
                ),
            )
        return binding.sha

    def release_binding(self, account_id: str) -> ReleaseBinding | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT payload FROM release_bindings WHERE account_id=?"
            " ORDER BY generation DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        return ReleaseBinding.parse(json.loads(row["payload"])) if row else None

    def release_binding_at(self, account_id: str, *, now_ms: int) -> ReleaseBinding | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT generation,payload,binding_sha FROM release_bindings"
            " WHERE account_id=? AND recorded_ms<=? ORDER BY generation DESC LIMIT 1",
            (account_id, now_ms),
        ).fetchone()
        if row is None:
            return None
        body = json.loads(row["payload"])
        binding = ReleaseBinding.parse(body)
        if (
            digest(body) != row["binding_sha"]
            or binding.sha != row["binding_sha"]
            or (binding.account_id, binding.generation) != (account_id, row["generation"])
        ):
            raise ValueError("RELEASE_BINDING_DRIFT")
        return binding

    def _stage_proposal(
        self, book: SeatBook, plan: ReconcilePlan, stamp: int
    ) -> tuple[str | None, str]:
        binding = self.release_binding(book.account_id)
        if binding is None:
            return None, "BLOCKED_RELEASE_BINDING_MISSING"
        try:
            proposal = build_release_proposal(
                book,
                binding,
                inventory_sha=self.inventory_sha(),
                plan_sha=plan.sha,
                created_ms=stamp,
            )
        except ValueError as exc:
            return None, f"BLOCKED_{exc}"
        return self.stage_proposal(proposal), "STAGED"

    def stage_proposal(self, proposal: ReleaseProposal) -> str:
        """One proposal per account per UTC day; re-staging the same day is a no-op."""
        self._require_writable()
        self._require_schema()
        if not isinstance(proposal, ReleaseProposal):
            raise ValueError("INVALID_PROPOSAL")
        with self._tx() as con:
            row = con.execute(
                "SELECT proposal_sha FROM proposals WHERE account_id=? AND day=?",
                (proposal.account_id, proposal.day),
            ).fetchone()
            if row is not None:
                # One proposal per UTC day: the first staged body stands even if a
                # later plan in the same day differs (no silent re-signing target).
                return str(row["proposal_sha"])
            con.execute(
                "INSERT INTO proposals(account_id, day, generation, proposal_sha, plan_sha,"
                " payload, created_ms, signed_sha) VALUES(?,?,?,?,?,?,?,NULL)",
                (
                    proposal.account_id,
                    proposal.day,
                    proposal.generation,
                    proposal.sha,
                    proposal.plan_sha,
                    canonical(proposal.data).decode(),
                    proposal.created_ms,
                ),
            )
        return proposal.sha

    def proposals(
        self, account_id: str | None = None, *, as_of: KnownAtTs | None = None
    ) -> tuple[ReleaseProposal, ...]:
        self._require_schema()
        cutoff = as_of.value if as_of is not None else None
        rows = self._con.execute(
            "SELECT payload FROM proposals WHERE (? IS NULL OR account_id=?)"
            " AND (? IS NULL OR created_ms<=?) ORDER BY created_ms, account_id",
            (account_id, account_id, cutoff, cutoff),
        )
        return tuple(ReleaseProposal.parse(json.loads(row["payload"])) for row in rows)

    def proposal(self, proposal_sha: str) -> ReleaseProposal | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT payload FROM proposals WHERE proposal_sha=?", (proposal_sha,)
        ).fetchone()
        return ReleaseProposal.parse(json.loads(row["payload"])) if row else None

    def proposal_day(self, account_id: str, day: str) -> ReleaseProposal | None:
        self._require_schema()
        row = self._con.execute(
            "SELECT payload FROM proposals WHERE account_id=? AND day=?", (account_id, day)
        ).fetchone()
        return ReleaseProposal.parse(json.loads(row["payload"])) if row else None

    def mark_proposal_signed(self, proposal_sha: str, *, envelope_sha: str) -> None:
        """Record the signed envelope digest against a staged proposal."""
        self._require_writable()
        self._require_schema()
        if self.proposal(proposal_sha) is None:
            raise KeyError(proposal_sha)
        with self._tx() as con:
            con.execute(
                "UPDATE proposals SET signed_sha=? WHERE proposal_sha=?",
                (envelope_sha, proposal_sha),
            )

    # -- price/policy seals ------------------------------------------------
    def seal_policy(
        self,
        account_id: str,
        *,
        generation: int,
        envelope: Mapping[str, Any],
        known_at_ms: int,
        policy_sha: str | None = None,
    ) -> str:
        """Append-only signed release policy; rollback or equivocation is refused."""
        self._require_writable()
        self._require_schema()
        if type(generation) is not int or generation < 1:
            raise ValueError("POLICY_GENERATION")
        body = json.loads(canonical(dict(envelope)))
        computed = digest(body)
        if policy_sha is not None and policy_sha != computed:
            raise ValueError("POLICY_SHA_DRIFT")
        KnownAtTs(known_at_ms)
        with self._tx() as con:
            _check_sealed_triggers(con)
            row = con.execute(
                "SELECT generation, policy_sha, known_at_ms FROM policies WHERE account_id=?"
                " ORDER BY generation DESC LIMIT 1",
                (account_id,),
            ).fetchone()
            if row is not None:
                if generation <= row["generation"]:
                    if (generation, computed, known_at_ms) == tuple(row):
                        return str(row["policy_sha"])
                    raise ValueError("POLICY_ROLLBACK_OR_EQUIVOCATION")
                if known_at_ms < row["known_at_ms"]:
                    raise ValueError("POLICY_ROLLBACK_OR_EQUIVOCATION")
            con.execute(
                "INSERT INTO policies(account_id, generation, known_at_ms, policy_sha, envelope)"
                " VALUES(?,?,?,?,?)",
                (account_id, generation, int(known_at_ms), computed, canonical(body).decode()),
            )
        return computed

    def policy_at(self, account_id: str, *, now_ms: int) -> dict[str, Any] | None:
        row = self.policy_record_at(account_id, now_ms=now_ms)
        return row[2] if row is not None else None

    def policy_record_at(
        self, account_id: str, *, now_ms: int
    ) -> tuple[int, int, dict[str, Any]] | None:
        self._require_schema()
        _check_sealed_triggers(self._con)
        row = self._con.execute(
            "SELECT * FROM policies WHERE account_id=? AND known_at_ms<=?"
            " ORDER BY generation DESC LIMIT 1",
            (account_id, now_ms),
        ).fetchone()
        if row is None:
            return None
        envelope = json.loads(row["envelope"])
        if not isinstance(envelope, dict) or digest(envelope) != row["policy_sha"]:
            raise ValueError("POLICY_SHA_DRIFT")
        return row["generation"], row["known_at_ms"], envelope

    # -- reporting ---------------------------------------------------------
    @staticmethod
    def authority_health(db_path: Path) -> dict[str, Any]:
        """Check observer authority and pin its content from one read-only snapshot."""
        path = Path(db_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError("STREAM_REGISTRY_FILE_INVALID")
        try:
            with RosterStore(path) as store, store.read_snapshot():
                con = store._con
                store._require_schema()
                if [r[0] for r in con.execute("PRAGMA quick_check")] != ["ok"] or con.execute(
                    "PRAGMA foreign_key_check"
                ).fetchone() is not None:
                    raise ValueError("ROSTER_SQLITE_INTEGRITY")
                _check_sealed_triggers(con)
                for row in con.execute("SELECT * FROM books"):
                    _verified_book(con, row)
                for row in con.execute("SELECT * FROM scorecards"):
                    body = json.loads(row["payload"])
                    if digest(body) != row["scorecard_sha"] or (
                        body["wallet"],
                        body["as_of_ms"],
                    ) != (row["wallet"], row["as_of_ms"]):
                        raise ValueError("SCORECARD_SHA_DRIFT")
                for row in con.execute("SELECT payload,bench_sha FROM bench"):
                    if (
                        digest(sorted(json.loads(row[0]), key=lambda item: item["wallet"]))
                        != row[1]
                    ):
                        raise ValueError("BENCH_SHA_DRIFT")
                for row in con.execute("SELECT envelope,policy_sha FROM policies"):
                    if digest(json.loads(row[0])) != row[1]:
                        raise ValueError("POLICY_SHA_DRIFT")
                inventory_tables = {}
                for table, keys in _OBSERVER_KEYS.items():
                    inventory_tables[table] = [
                        ([row[key] for key in keys], digest(dict(row)))
                        for row in con.execute(f"SELECT * FROM {table} ORDER BY " + ", ".join(keys))
                    ]
                inventory = digest(
                    {"schema": "roster_observer_inventory_v1", "tables": inventory_tables}
                )
        except FileNotFoundError as exc:
            raise ValueError("STREAM_REGISTRY_FILE_INVALID") from exc
        except (
            OSError,
            RosterStoreError,
            sqlite3.Error,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ) as exc:
            raise ValueError("STREAM_REGISTRY_INTEGRITY_FAILED") from exc
        return {
            "schema": "roster_authority_health_v1",
            "schema_version": SCHEMA_VERSION,
            "database_integrity": "VERIFIED",
            "inventory_sha256": inventory,
            "trading_authorized": False,
        }

    def inventory_sha(self) -> str:
        """Digest of every authority row in a fixed order (release inventory)."""
        self._require_schema()
        return self._inventory(_INVENTORY_TABLES)

    def _inventory(self, tables: tuple[str, ...]) -> str:
        fingerprint = canonical(
            {
                "schema_version": SCHEMA_VERSION,
                "tables": list(tables),
            }
        )
        hasher = sha256(fingerprint)
        for table in tables:
            rows = [
                json.dumps(dict(row), sort_keys=True, separators=(",", ":"))
                for row in self._con.execute(f"SELECT * FROM {table}")
            ]
            hasher.update(table.encode("ascii") + b"\0")
            for row in sorted(rows):
                hasher.update(row.encode() + b"\n")
        return hasher.hexdigest()

    def health(self) -> dict[str, Any]:
        """Read-only integrity report; never a trading or qualification claim."""
        problems: list[str] = []
        try:
            sqlite_row = self._con.execute("PRAGMA integrity_check").fetchone()
            integrity = sqlite_row[0] if sqlite_row else "unknown"
        except sqlite3.DatabaseError as exc:  # pragma: no cover - corrupted file
            integrity = f"ERROR:{exc}"
        if integrity != "ok":
            problems.append("ROSTER_SQLITE_INTEGRITY")
        try:
            version_row = self._con.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
        except sqlite3.DatabaseError:
            version_row = None
        if version_row is None or int(version_row[0]) != SCHEMA_VERSION:
            problems.append("ROSTER_SCHEMA_VERSION")
        try:
            dangling = self._con.execute(
                "SELECT COUNT(*) FROM books b LEFT JOIN accounts a USING(account_id)"
                " WHERE a.account_id IS NULL"
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            dangling = 0
        if dangling:
            problems.append("ROSTER_ORPHAN_BOOKS")
        counts = {}
        for table in _AUTHORITY_TABLES:
            try:
                counts[table] = self._con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.DatabaseError:
                counts[table] = None
        return {
            "schema": "roster_store_health_v1",
            "path": str(self.path),
            "schema_version": SCHEMA_VERSION,
            "database_integrity": "VERIFIED" if not problems else "BLOCKED",
            "problems": problems,
            "counts": counts,
            "trading_authorized": False,
        }

    def verify(self) -> dict[str, Any]:
        """Re-derive every book/lease/draining identity from stored payloads."""
        self._require_schema()
        problems: list[str] = []
        for row in self._con.execute("SELECT account_id, sequence, book_sha, payload FROM books"):
            book = SeatBook.parse(json.loads(row["payload"]))
            if book.sha != row["book_sha"]:
                problems.append(f"BOOK_SHA_DRIFT:{row['account_id']}:{row['sequence']}")
            if book.sequence != row["sequence"]:
                problems.append(f"BOOK_SEQUENCE_DRIFT:{row['account_id']}:{row['sequence']}")
        for row in self._con.execute("SELECT account_id, seat_id, generation, payload FROM leases"):
            lease = SeatLease.parse(json.loads(row["payload"]))
            if (lease.account_id, lease.seat_id, lease.generation) != (
                row["account_id"],
                row["seat_id"],
                row["generation"],
            ):
                problems.append(f"LEASE_IDENTITY_DRIFT:{row['seat_id']}")
        for row in self._con.execute("SELECT proposal_sha, payload FROM proposals"):
            proposal = ReleaseProposal.parse(json.loads(row["payload"]))
            if proposal.sha != row["proposal_sha"]:
                problems.append(f"PROPOSAL_SHA_DRIFT:{row['proposal_sha']}")
        return {
            "schema": "roster_store_verify_v1",
            "books": self._con.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "leases": self._con.execute("SELECT COUNT(*) FROM leases").fetchone()[0],
            "problems": problems,
            "ok": not problems,
        }

    def campaigns(self) -> tuple[str, ...]:  # pragma: no cover - compatibility alias
        return self.accounts()

    def _proposal_for_day(self, account_id: str, stamp: int) -> str | None:
        day = datetime.fromtimestamp(stamp / 1000, UTC).date().isoformat()
        row = self._con.execute(
            "SELECT proposal_sha FROM proposals WHERE account_id=? AND day=?",
            (account_id, day),
        ).fetchone()
        return str(row["proposal_sha"]) if row else None


class _Transaction:
    """``BEGIN IMMEDIATE`` context manager; one writer at a time, no silent commit."""

    __slots__ = ("_store", "_con")

    def __init__(self, store: RosterStore) -> None:
        self._store = store
        self._con = store._con  # noqa: SLF001 - same-module transaction helper

    def __enter__(self) -> sqlite3.Connection:
        self._con.execute("BEGIN IMMEDIATE")
        return self._con

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self._con.execute("COMMIT")
        else:
            self._con.execute("ROLLBACK")
