"""Private, durable forward-paper account-event journal (FP-02).

Financial transitions are made exclusively with PM-03 Account methods. There is
no exchange transport or shared registry database.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from time import monotonic, sleep
from typing import Iterator

from .pm03_account import Account, RiskState, Rulebook, clock, digest, number
from .pm_e4_prospective import PUBLIC_ACCOUNT_MODES
from .pm_forward_paper import PaperManifest
from .pm_forward_stream_journal import SCHEMA as STREAM_SCHEMA, append_checkpoint


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass
class PaperJournal:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError("PAPER_STATE_DIRECTORY_NOT_PRIVATE")
        self.path = self.root / "paper-events.sqlite3"
        if self.path.is_symlink():
            raise ValueError("PAPER_JOURNAL_SYMLINK")
        self._lock_path = self.root / "paper-events.lock"
        # WAL is persistent database configuration. Negotiate it once during
        # initialization, never on each receipt while independent readers hold
        # snapshots. Repeated journal_mode=WAL requests need exclusive locks.
        self._configure_wal = True
        with self._writer() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL UNIQUE,
                    manifest TEXT NOT NULL,
                    manifest_sha TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    snapshot_sha TEXT NOT NULL,
                    last_event_at TEXT NOT NULL,
                    cursor INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS funding_claims (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    instrument TEXT NOT NULL,
                    interval_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    PRIMARY KEY (run_id, instrument, interval_id)
                );
                CREATE TABLE IF NOT EXISTS market_quote_heads (
                    instrument TEXT PRIMARY KEY,
                    cursor INTEGER NOT NULL,
                    event_at TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    chain_sha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_quote_receipts (
                    instrument TEXT NOT NULL REFERENCES market_quote_heads(instrument),
                    seq INTEGER NOT NULL,
                    quote_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    PRIMARY KEY (instrument, seq),
                    UNIQUE (instrument, quote_id)
                );
                CREATE TABLE IF NOT EXISTS vike_minute_heads (
                    instrument TEXT PRIMARY KEY,
                    cursor INTEGER NOT NULL,
                    event_at TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    chain_sha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vike_minute_receipts (
                    instrument TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    observation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    PRIMARY KEY(instrument, seq),
                    UNIQUE(instrument, observation_id),
                    FOREIGN KEY(instrument) REFERENCES vike_minute_heads(instrument)
                );
                CREATE TABLE IF NOT EXISTS market_trade_heads (
                    instrument TEXT PRIMARY KEY,
                    cursor INTEGER NOT NULL,
                    known_at TEXT NOT NULL,
                    chain_sha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_trade_batches (
                    instrument TEXT NOT NULL REFERENCES market_trade_heads(instrument),
                    seq INTEGER NOT NULL,
                    batch_sha TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    PRIMARY KEY (instrument, seq),
                    UNIQUE (instrument, batch_sha)
                );
                CREATE TABLE IF NOT EXISTS source_receipts (
                    source_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    receipt_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    receipt_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    PRIMARY KEY (source_id, seq),
                    UNIQUE (source_id, receipt_id)
                );
                CREATE TABLE IF NOT EXISTS source_scope_receipts (
                    account_sha TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    receipt_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    PRIMARY KEY (account_sha, seq),
                    UNIQUE (account_sha, receipt_id)
                );
                CREATE TABLE IF NOT EXISTS account_source_cursors (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    source_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    receipt_sha TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    PRIMARY KEY (run_id, source_id, seq),
                    UNIQUE (run_id, event_id)
                );
                -- Public market trade evidence is provisional. A trade is not
                -- a whole-wallet NAV attestation or an executable paper order.
                CREATE TABLE IF NOT EXISTS public_wallet_trade_heads (
                    wallet_key TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    cursor INTEGER NOT NULL,
                    known_at TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    PRIMARY KEY(wallet_key, instrument)
                );
                CREATE TABLE IF NOT EXISTS public_wallet_trade_receipts (
                    wallet_key TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    known_at TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY(wallet_key, instrument, seq),
                    UNIQUE(wallet_key, instrument, event_key),
                    FOREIGN KEY(wallet_key, instrument)
                        REFERENCES public_wallet_trade_heads(wallet_key, instrument)
                );
                CREATE INDEX IF NOT EXISTS idx_public_trade_bucket
                ON public_wallet_trade_receipts(wallet_key, instrument, known_at, committed_at);
                CREATE TABLE IF NOT EXISTS public_trade_stream_gaps (
                    gap_sha TEXT PRIMARY KEY,
                    instrument TEXT NOT NULL,
                    stream_epoch TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provisional_utc_buckets (
                    bucket_key TEXT PRIMARY KEY,
                    wallet_key TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    plan_sha TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    input TEXT NOT NULL,
                    input_sha TEXT NOT NULL,
                    prior_sha TEXT NOT NULL,
                    post_sha TEXT NOT NULL,
                    chain_sha TEXT NOT NULL,
                    PRIMARY KEY (run_id, seq),
                    UNIQUE (run_id, event_id)
                );
                """
            )
            db.executescript(STREAM_SCHEMA)
            from .pm_checkpoint_journal import SCHEMA as CWSA_SCHEMA

            db.executescript(CWSA_SCHEMA)
            from .pm_copy_mandate_journal import SCHEMA as MANDATE_SCHEMA

            db.executescript(MANDATE_SCHEMA)
        self._configure_wal = False
        os.chmod(self.path, 0o600)

    @contextmanager
    def writer(self) -> Iterator[sqlite3.Connection]:
        with self._writer() as db:
            yield db

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        db = None
        try:
            # A second process is never allowed to become a journal writer.
            # Do not retry the filesystem lease: this is an ownership conflict.
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("PAPER_JOURNAL_BUSY_OR_UNAVAILABLE:LEASE_HELD") from exc

            # Retry only connection setup and busy/locked PRAGMA acquisition.
            # No application transaction or source receipt exists yet, so
            # retrying cannot duplicate a committed financial/source effect.
            deadline = monotonic() + 2.0
            while True:
                try:
                    db = sqlite3.connect(self.path, timeout=0.25, isolation_level=None)
                    mode = db.execute("PRAGMA journal_mode").fetchone()
                    if mode != ("wal",):
                        if self._configure_wal:
                            if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                                raise ValueError("PAPER_JOURNAL_WAL_NOT_CONFIGURED")
                        else:
                            raise ValueError("PAPER_JOURNAL_WAL_NOT_CONFIGURED")
                    db.execute("PRAGMA synchronous=FULL")
                    db.execute("PRAGMA foreign_keys=ON")
                    break
                except sqlite3.OperationalError as exc:
                    if db is not None:
                        db.close()
                        db = None
                    code = getattr(exc, "sqlite_errorcode", None)
                    transient = code is not None and (code & 0xFF) in (
                        sqlite3.SQLITE_BUSY,
                        sqlite3.SQLITE_LOCKED,
                    )
                    if not transient:
                        raise ValueError("PAPER_JOURNAL_SQLITE_PERMANENT") from exc
                    if monotonic() >= deadline:
                        raise ValueError("PAPER_JOURNAL_SQLITE_CONTENTION_EXHAUSTED") from exc
                    sleep(min(0.05, max(0.0, deadline - monotonic())))
            # Errors after entering the caller's transaction must propagate
            # unchanged. A failed COMMIT is ambiguous until durable replay;
            # blindly repeating the callback could create a duplicate T0.
            yield db
        finally:
            if db is not None:
                db.close()
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _copy_mandate_update(self, operation, *args, **kwargs):
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = operation(db, *args, **kwargs)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return result

    def activate_copy_mandate(self, envelope, key, *, account_id: str, at_ms: int):
        from .pm_copy_mandate import verify_mandate
        from .pm_copy_mandate_journal import activate

        mandate = verify_mandate(envelope, key, account_id=account_id)
        return self._copy_mandate_update(
            activate,
            mandate,
            at_ms=at_ms,
            evidence_sha=envelope["sha256"],
            approval=envelope,
            authority_public=key.public_bytes_raw().hex(),
        )

    def control_copy_mandate(self, envelope, key, *, at_ms: int):
        from .production_manifest import verify
        from .pm_copy_mandate_journal import control

        command = verify(envelope, key, "copy-mandate-control-v1")
        return self._copy_mandate_update(
            control,
            command,
            at_ms=at_ms,
            approval=envelope,
            authority_public=key.public_bytes_raw().hex(),
        )

    def baseline_copy_mandate(self, owner: str, outcome_id: str, *, at_ms: int):
        from .pm_copy_mandate_journal import baseline

        return self._copy_mandate_update(baseline, owner, outcome_id, at_ms=at_ms)

    def copy_mandate_state(self, owner: str):
        from .pm_copy_mandate_journal import history, state

        with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as db:
            history(db, owner)
            return state(db, owner)

    def consume_checkpoint(self, run_id, owner, outcome_id, *, at_ms, policy, catalog):
        """Canonical v3 paper consumption; PM03 remains the financial owner."""
        from .pm_checkpoint_paper import consume

        return consume(self, run_id, owner, outcome_id, at_ms=at_ms, policy=policy, catalog=catalog)

    def register_checkpoint_source(self, scope, policy, *, first_checkpoint_ms: int, at_ms: int):
        from .pm_checkpoint_journal import register

        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = register(db, scope, policy, first_checkpoint_ms, at_ms)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return result

    def append_checkpoint_sample(self, policy_epoch: str, sample, published_ms: int):
        from .pm_checkpoint_journal import record, verify_candidate

        proof_valid = verify_candidate(sample, self.root)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = record(db, policy_epoch, sample, published_ms, proof_valid=proof_valid)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return result

    def checkpoint_history(self, scope, policy_epoch: str):
        from .pm_checkpoint_journal import history

        with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)) as db:
            return history(db, scope, policy_epoch)

    def append_stream_event(self, event: dict) -> dict:
        """Persist a transport/gap/checkpoint event without a financial effect."""
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = append_checkpoint(db, event, [])
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return result

    @staticmethod
    def apply(account: Account, event: dict) -> dict:
        account.prepare_risk_semantics(event.get("risk_semantics_version", 1))
        kind = event.get("kind")
        if kind == "CWSA_PAPER_REVIEW":
            from .pm_checkpoint_paper import apply

            return apply(account, event)
        if kind == "HALT":
            account.latch_halt(event.get("reason") or "PAPER_OPERATOR_HALT")
            return {"status": "HALT_LATCHED"}
        if kind == "MARK":
            if not event.get("state_known", False):
                account.latch_halt("UNKNOWN_PAPER_MARK")
                return {"status": "HALT_UNKNOWN_MARK"}
            from .pm03_account import Instrument

            account.mark(
                {Instrument.parse(k): number(v) for k, v in event["prices"].items()},
                event["event_at"],
            )
            account.verify()
            return {"status": "MARKED"}
        if kind == "FUNDING_UNKNOWN":
            account.block_readiness(("UNOBSERVED_FUNDING_INTERVAL",))
            return {"status": "UNKNOWN_FUNDING", "cash_effect_assumed": False}
        if kind == "FUNDING":
            from .pm03_account import Instrument
            from .pm_forward_margin import margin_projection

            if event.get("fixture_attested") is not True:
                raise ValueError("FUNDING_RECEIPT_NOT_ATTESTED")
            instrument = Instrument.parse(event["instrument"])
            if not account.quantities.get(instrument):
                raise ValueError("FUNDING_WITHOUT_OPEN_POSITION")
            if not event.get("interval_id") or not isinstance(event["interval_id"], str):
                raise ValueError("FUNDING_INTERVAL_UNKNOWN")
            if not (
                clock(event["source_event_at"])
                <= clock(event["first_known_at"])
                <= clock(event["event_at"])
            ):
                raise ValueError("FUNDING_CLOCK_ORDER_INVALID")
            quote_rows = event.get("marks")
            if not isinstance(quote_rows, dict):
                raise ValueError("FUNDING_MARKS_UNKNOWN")
            account.mark(
                {Instrument.parse(k): number(v) for k, v in quote_rows.items()},
                event["event_at"],
            )
            account.post_funding(
                number(event["amount"]),
                {k: number(v) for k, v in event["allocated"].items()},
            )
            margin = margin_projection(
                account, event.get("margin_contract"), as_of=event["event_at"]
            )
            if margin["status"] == "UNKNOWN_LIQUIDATION":
                account.block_readiness(margin["reasons"])
            elif margin["status"] == "MARGIN_BREACH_HALT":
                account.latch_halt("MODELED_MAINTENANCE_MARGIN_BREACH")
            account.verify()
            return {
                "status": "FUNDING_POSTED",
                "signed_amount": event["amount"],
                "margin": margin,
                "forced_exit_assumed": False,
            }
        if kind in ("PM04_CONFIG", "PM04_SIGNAL", "PM04_TICK"):
            from .pm_forward_pm04 import apply_forward_pm04

            return apply_forward_pm04(account, event)
        if kind == "SIMULATED_DECISION":
            from .pm03_account import Instrument
            from .pm03_execution import CostModel, MarketObservation, execute_targets
            from .pm03_risk import RiskEvidence, RiskPolicy, classify

            if event.get("evidence_class") != "FORWARD_PAPER_SIMULATED_v1":
                raise ValueError("PAPER_WRONG_EVIDENCE_CLASS")
            if event.get("order_route") != "NONE":
                raise ValueError("PAPER_ORDER_ROUTE_FORBIDDEN")
            from .pm_forward_admission import admit_source_book

            admission = admit_source_book(
                event.get("source_book"),
                decision_at=event["event_at"],
                fill_at=event["hypothetical_fill_at"],
                allow_synthetic_fixture=event.get("fixture_attested") is True,
            )
            if not admission.admitted:
                account.block_readiness(admission.reason_codes)
                return {
                    "status": "BLOCKED_SOURCE",
                    "reason_codes": list(admission.reason_codes),
                }
            if event.get("fixture_attested") is not True:
                raise ValueError("PAPER_SOURCE_ADMISSION_MISSING")
            if not account.rulebook.confirmed:
                raise ValueError("PAPER_RULEBOOK_UNCONFIRMED")
            decision_at = event["event_at"]
            obs = {}
            for entry in event["observations"]:
                instrument = Instrument.parse(entry["instrument"])
                if instrument in obs:
                    raise ValueError("PAPER_DUPLICATE_MARKET")
                quote = MarketObservation(
                    instrument=instrument,
                    event_at=entry["source_at"],
                    first_known_at=entry["first_known_at"],
                    mark=number(entry["mark"]),
                    volume_base=number(entry["volume_base"])
                    if entry.get("volume_base") is not None
                    else None,
                    quality=entry.get("quality", "SYNTHETIC"),
                    supported=entry["supported"],
                )
                quote.validate(decision_at)
                obs[instrument] = quote
            proposed = {
                pm: {Instrument.parse(k): number(q) for k, q in book.items()}
                for pm, book in event["proposed"].items()
            }
            shocks = tuple(
                {Instrument.parse(k): number(v) for k, v in scenario.items()}
                for scenario in event["shocks"]
            )
            expected_keys = set(account.quantities)
            expected_keys |= {
                instrument
                for book in account.pm_quantities.values()
                for instrument, q in book.items()
                if q
            }
            if expected_keys - set(obs):
                account.latch_halt("MISSING_EXISTING_POSITION_MARK")
                return {"status": "BLOCKED", "reason": "MISSING_EXISTING_POSITION_MARK"}
            if any(not q.supported or q.volume_base is None for q in obs.values()):
                account.block_readiness()
                return {"status": "BLOCKED", "reason": "INCOMPLETE_MARKET"}
            from .pm_forward_market import market_contract_reasons

            market_reasons: list[str] = []
            market_contracts = event.get("market_contracts")
            if not isinstance(market_contracts, dict):
                market_contracts = {}
            targets = account.external_targets(proposed)
            for instrument in sorted(set(targets) | expected_keys):
                quote = obs.get(instrument)
                if quote is None:
                    market_reasons.append("MARKET_MISSING_QUOTE")
                    continue
                market_reasons.extend(
                    market_contract_reasons(
                        market_contracts.get(instrument.key),
                        instrument=instrument,
                        observed_quality=quote.quality,
                        decision_at=decision_at,
                        target_quantity=targets.get(instrument, number("0")),
                        costs_sha=digest(event["costs"]),
                        observation={
                            "instrument": instrument.key,
                            "event_at": quote.event_at,
                            "first_known_at": quote.first_known_at,
                            "mark": str(quote.mark),
                            "volume_base": (
                                str(quote.volume_base) if quote.volume_base is not None else None
                            ),
                            "quality": quote.quality,
                            "supported": quote.supported,
                        },
                        quote_evidence=event.get("market_evidence", {}).get(instrument.key),
                        costs=event["costs"],
                    )
                )
            if market_reasons:
                account.block_readiness(sorted(set(market_reasons)))
                return {"status": "BLOCKED_MARKET", "reason_codes": list(account.risk_reasons)}
            account.mark({k: q.mark for k, q in obs.items()}, decision_at)
            evidence = RiskEvidence(
                trusted=True,
                account_state_known=True,
                market_state_known=True,
                market_coverage_valid=True,
                pending_unknown_orders=False,
                input_status="FORWARD_PAPER_SIMULATED_v1",
                pm02_qualified=False,
            )
            decision = classify(
                account,
                proposed,
                {k: q.mark for k, q in obs.items()},
                shocks,
                evidence,
                RiskPolicy(),
            )
            args = event["costs"]
            costs = CostModel(
                fee_bps=number(args["fee_bps"]),
                full_spread_bps=number(args["full_spread_bps"]),
                slippage_bps=number(args["slippage_bps"]),
                impact_bps_at_full_participation=number(args["impact_bps_at_full_participation"]),
                max_participation=number(args["max_participation"]),
                max_age_seconds=args["max_age_seconds"],
                latency_seconds=args["latency_seconds"],
            )
            fill = execute_targets(
                account,
                decision["approved"],
                obs,
                costs,
                decision_at=decision_at,
                hypothetical_fill_at=event["hypothetical_fill_at"],
                permitted=decision["approved_new_risk"]
                or (
                    account.risk_semantics_version >= 3
                    and account.risk == RiskState.HALT
                    and not account.breached
                    and set(decision["reason_codes"]) == {"PERSISTENT_HALT"}
                ),
            )
            return {
                "risk": decision["state"],
                "reasons": decision["reason_codes"],
                "execution": fill,
            }
        raise ValueError("PAPER_EVENT_NOT_SUPPORTED")

    def register(self, manifest: PaperManifest) -> dict:
        initial = Account.start(manifest.rulebook, manifest.started_at).snapshot()
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT manifest_sha FROM runs WHERE run_id=?", (manifest.run_id,)
                ).fetchone()
                if row:
                    if row[0] != manifest.sha:
                        raise ValueError("CONFLICTING_PAPER_RUN_MANIFEST")
                else:
                    db.execute(
                        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,0)",
                        (
                            manifest.run_id,
                            manifest.account_id,
                            _json(manifest.payload()),
                            manifest.sha,
                            _json(initial),
                            digest(initial),
                            manifest.started_at,
                        ),
                    )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.restore(manifest.run_id)

    @staticmethod
    def _validate_event(event_id: str, event: dict) -> None:
        if not isinstance(event_id, str) or not event_id or len(event_id) > 128:
            raise ValueError("INVALID_PAPER_EVENT_ID")
        if not isinstance(event, dict) or not isinstance(event.get("event_at"), str):
            raise ValueError("INVALID_PAPER_EVENT")
        clock(event["event_at"])

    def append_locked(
        self, db: sqlite3.Connection, run_id: str, event_id: str, event: dict
    ) -> bool:
        """Append a PM-03 effect inside the CALLER'S transaction, never commit here."""
        self.verify(db, run_id)
        old = db.execute(
            "SELECT input FROM events WHERE run_id=? AND event_id=?",
            (run_id, event_id),
        ).fetchone()
        if old:
            prior = json.loads(old[0])
            claimed = dict(event)
            if "risk_semantics_version" in claimed and (
                type(claimed["risk_semantics_version"]) is not int
                or claimed["risk_semantics_version"] != prior.get("risk_semantics_version", 1)
            ):
                raise ValueError("CONFLICTING_PAPER_EVENT")
            prior.pop("risk_semantics_version", None)
            claimed.pop("risk_semantics_version", None)
            if prior != claimed:
                raise ValueError("CONFLICTING_PAPER_EVENT")
            return False
        if (
            type(event.get("risk_semantics_version", 3)) is not int
            or event.get("risk_semantics_version", 3) != 3
        ):
            raise ValueError("LEGACY_RISK_SEMANTICS_READ_ONLY")
        event = {**event, "risk_semantics_version": 3}
        input_sha = digest(event)
        row = db.execute(
            "SELECT manifest,snapshot,last_event_at,cursor,snapshot_sha FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError("UNKNOWN_PAPER_RUN")
        manifest, snapshot, last_at, cursor, prior_sha = row
        if event.get("kind") == "CWSA_PAPER_REVIEW":
            from .pm_checkpoint_paper import validate_binding

            validate_binding(db, run_id, event)
        if event.get("kind", "").startswith("PM04_"):
            saved_manifest = json.loads(manifest)
            if (
                event.get("run_id") != run_id
                or event.get("sealed_policy_sha") != saved_manifest["policy_sha"]
            ):
                raise ValueError("PM04_MANIFEST_POLICY_MISMATCH")
        if clock(event["event_at"]) < clock(last_at):
            raise ValueError("PAPER_EVENT_OUT_OF_ORDER")
        if event.get("kind") == "FUNDING":
            prior_funding = db.execute(
                "SELECT event_id FROM funding_claims "
                "WHERE run_id=? AND instrument=? AND interval_id=?",
                (run_id, event.get("instrument"), event.get("interval_id")),
            ).fetchone()
            if prior_funding is not None:
                raise ValueError("DUPLICATE_FUNDING_INTERVAL")
        rulebook = Rulebook.from_dict(json.loads(manifest)["rulebook"])
        account = Account.from_snapshot(rulebook, json.loads(snapshot))
        self.apply(account, event)
        post = account.snapshot()
        post_sha = digest(post)
        chain_sha = digest([run_id, cursor + 1, event_id, input_sha, prior_sha, post_sha])
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                cursor + 1,
                event_id,
                event["event_at"],
                _json(event),
                input_sha,
                prior_sha,
                post_sha,
                chain_sha,
            ),
        )
        db.execute(
            "UPDATE runs SET snapshot=?,snapshot_sha=?,last_event_at=?,cursor=? WHERE run_id=?",
            (_json(post), post_sha, event["event_at"], cursor + 1, run_id),
        )
        if event.get("kind") == "FUNDING":
            db.execute(
                "INSERT INTO funding_claims VALUES (?,?,?,?)",
                (run_id, event["instrument"], event["interval_id"], event_id),
            )
        return True

    def append(self, run_id: str, event_id: str, event: dict) -> dict:
        self._validate_event(event_id, event)
        if "source_ref" in event or event.get("kind") == "CWSA_PAPER_REVIEW":
            raise ValueError("SOURCE_REF_REQUIRES_ATOMIC_CONSUME")
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self.append_locked(db, run_id, event_id, event)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.restore(run_id)

    def consume_source_effect(self, run_id: str, event_id: str, event: dict) -> dict:
        """Commit a source's next cursor and its simulated account effect atomically.

        The shared source receipt must already exist and be SHA/clock matched.
        Repeated source receipts may be independently consumed by separate
        virtual accounts, never twice in the same account.
        """
        self._validate_event(event_id, event)
        ref = event.get("source_ref")
        # append_locked accepts exact historical retries before rejecting
        # legacy semantics for any new event; do not block old ACK retries here.
        if event.get("kind") not in ("SIMULATED_DECISION", "PM04_SIGNAL") or not isinstance(
            ref, dict
        ):
            raise ValueError("SOURCE_EFFECT_EVENT_REQUIRED")
        source_id = ref.get("source_id")
        seq = ref.get("sequence")
        sha = ref.get("receipt_sha")
        if not isinstance(source_id, str) or not source_id or type(seq) is not int or seq < 1:
            raise ValueError("INVALID_SOURCE_REFERENCE")
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("INVALID_SOURCE_REFERENCE")
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self.verify(db, run_id)
                source_row = db.execute(
                    "SELECT payload,receipt_sha FROM source_receipts WHERE source_id=? AND seq=?",
                    (source_id, seq),
                ).fetchone()
                if source_row is None:
                    raise ValueError("SOURCE_RECEIPT_NOT_PRESENT")
                raw, actual_sha = source_row
                if digest(json.loads(raw)) != actual_sha or sha != actual_sha:
                    raise ValueError("SOURCE_RECEIPT_SHA_MISMATCH")
                receipt = json.loads(raw)
                book = event.get("source_book")
                if not isinstance(book, dict) or (
                    receipt.get("payload_sha") != book.get("snapshot_sha")
                    or source_id != book.get("wallet_id")
                    or receipt.get("source_event_at") != book.get("source_event_at")
                    or receipt.get("first_known_at") != book.get("first_known_at")
                ):
                    raise ValueError("SOURCE_BOOK_RECEIPT_BINDING_MISMATCH")
                if not (
                    clock(receipt["source_event_at"])
                    <= clock(receipt["first_known_at"])
                    <= clock(receipt["captured_at"])
                    <= clock(event["event_at"])
                    <= clock(event["hypothetical_fill_at"])
                ):
                    raise ValueError("SOURCE_EFFECT_CLOCK_VIOLATION")
                prior = db.execute(
                    "SELECT seq,receipt_sha,event_id FROM account_source_cursors "
                    "WHERE run_id=? AND source_id=? ORDER BY seq DESC LIMIT 1",
                    (run_id, source_id),
                ).fetchone()
                expected = prior[0] + 1 if prior else 1
                if prior and seq == prior[0]:
                    if prior[1:] != (sha, event_id):
                        raise ValueError("SOURCE_ALREADY_CONSUMED")
                    if self.append_locked(db, run_id, event_id, event):
                        raise ValueError("SOURCE_ALREADY_CONSUMED")
                elif seq != expected:
                    raise ValueError("SOURCE_RUN_SEQUENCE_GAP")
                else:
                    if not self.append_locked(db, run_id, event_id, event):
                        raise ValueError("SOURCE_EVENT_ID_REUSED")
                    db.execute(
                        "INSERT INTO account_source_cursors VALUES (?,?,?,?,?)",
                        (run_id, source_id, seq, sha, event_id),
                    )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.restore(run_id)

    @staticmethod
    def verify(db: sqlite3.Connection, run_id: str, *, on_event=None) -> dict:
        row = db.execute(
            "SELECT manifest,manifest_sha,snapshot,snapshot_sha,last_event_at,cursor FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError("UNKNOWN_PAPER_RUN")
        manifest_raw, manifest_sha, snapshot_raw, snapshot_sha, last_at, cursor = row
        manifest = json.loads(manifest_raw)
        if digest(manifest) != manifest_sha or manifest.get("order_route") != "NONE":
            raise ValueError("PAPER_MANIFEST_TAMPERED")
        rulebook = Rulebook.from_dict(manifest["rulebook"])
        account = Account.start(rulebook, manifest["started_at"])
        prior_sha = digest(account.snapshot())
        prior_at = manifest["started_at"]
        last_result: dict | None = None
        funding_events: list[tuple[str, str, str]] = []
        source_links: list[tuple[str, int, str, str]] = []
        source_cursors: dict[str, int] = {}
        rows = db.execute(
            "SELECT seq,event_id,event_at,input,input_sha,prior_sha,post_sha,chain_sha "
            "FROM events WHERE run_id=? ORDER BY seq",
            (run_id,),
        ).fetchall()
        for expected_seq, entry in enumerate(rows, 1):
            seq, event_id, at, payload, input_sha, before, after, chain_sha = entry
            event = json.loads(payload)
            if event.get("kind") == "FUNDING":
                funding_events.append((event["instrument"], event["interval_id"], event_id))
            ref = event.get("source_ref")
            if ref is not None:
                if not isinstance(ref, dict) or event.get("kind") not in (
                    "SIMULATED_DECISION",
                    "PM04_SIGNAL",
                ):
                    raise ValueError("SOURCE_CURSOR_REPLAY_DIVERGENCE")
                sid = ref.get("source_id")
                source_seq = ref.get("sequence")
                source_sha = ref.get("receipt_sha")
                if (
                    not isinstance(sid, str)
                    or type(source_seq) is not int
                    or (source_seq != source_cursors.get(sid, 0) + 1)
                ):
                    raise ValueError("SOURCE_CURSOR_REPLAY_DIVERGENCE")
                source_row = db.execute(
                    "SELECT payload,receipt_sha FROM source_receipts WHERE source_id=? AND seq=?",
                    (sid, source_seq),
                ).fetchone()
                if source_row is None or source_row[1] != source_sha:
                    raise ValueError("SOURCE_CURSOR_REPLAY_DIVERGENCE")
                receipt = json.loads(source_row[0])
                book = event.get("source_book")
                if (
                    digest(receipt) != source_sha
                    or not isinstance(book, dict)
                    or receipt.get("payload_sha") != book.get("snapshot_sha")
                    or receipt.get("source_event_at") != book.get("source_event_at")
                    or receipt.get("first_known_at") != book.get("first_known_at")
                    or receipt.get("source_id") != book.get("wallet_id")
                ):
                    raise ValueError("SOURCE_CURSOR_REPLAY_DIVERGENCE")
                source_cursors[sid] = source_seq
                source_links.append((sid, source_seq, source_sha, event_id))
            if (
                seq != expected_seq
                or event.get("event_at") != at
                or digest(event) != input_sha
                or before != prior_sha
                or clock(at) < clock(prior_at)
            ):
                raise ValueError("PAPER_JOURNAL_DIVERGENCE")
            if event.get("kind", "").startswith("PM04_") and (
                event.get("run_id") != run_id
                or event.get("sealed_policy_sha") != manifest["policy_sha"]
            ):
                raise ValueError("PM04_MANIFEST_POLICY_MISMATCH")
            if event.get("kind") == "CWSA_PAPER_REVIEW":
                from .pm_checkpoint_paper import validate_binding

                validate_binding(db, run_id, event)
            last_result = PaperJournal.apply(account, event)
            expected_post = digest(account.snapshot())
            if after != expected_post or chain_sha != digest(
                [run_id, seq, event_id, input_sha, before, after]
            ):
                raise ValueError("PAPER_JOURNAL_DIVERGENCE")
            if on_event is not None:
                on_event(event, account.snapshot(), last_result, chain_sha)
            prior_sha = after
            prior_at = at
        funding_claims = db.execute(
            "SELECT instrument,interval_id,event_id FROM funding_claims "
            "WHERE run_id=? ORDER BY instrument,interval_id,event_id",
            (run_id,),
        ).fetchall()
        if len(funding_events) != len(set(funding_events)) or (
            sorted(funding_events) != funding_claims
        ):
            raise ValueError("FUNDING_RECEIPT_REPLAY_DIVERGENCE")
        saved_links = db.execute(
            "SELECT source_id,seq,receipt_sha,event_id FROM account_source_cursors "
            "WHERE run_id=? ORDER BY source_id,seq",
            (run_id,),
        ).fetchall()
        if sorted(source_links) != saved_links:
            raise ValueError("SOURCE_CURSOR_REPLAY_DIVERGENCE")
        if (
            cursor != len(rows)
            or prior_sha != snapshot_sha
            or digest(json.loads(snapshot_raw)) != snapshot_sha
            or last_at != prior_at
            or account.snapshot() != json.loads(snapshot_raw)
        ):
            raise ValueError("PAPER_CHECKPOINT_DIVERGENCE")
        return {
            "run_id": run_id,
            "manifest_sha": manifest_sha,
            "cursor": cursor,
            "last_event_at": last_at,
            "account": account.snapshot(),
            "journal_head_sha": rows[-1][-1] if rows else "0" * 64,
            "last_event_result": last_result,
            "source_cursors": source_cursors,
        }

    def append_source_receipt(
        self,
        source_id: str,
        sequence: int | None,
        receipt_id: str,
        receipt: dict,
        *,
        stream_event: dict | None = None,
    ) -> dict:
        """Import one already-captured receipt, never create a subscription."""
        if (
            not source_id
            or not receipt_id
            or (sequence is None and stream_event is None)
            or (sequence is not None and (type(sequence) is not int or sequence <= 0))
            or len(source_id) > 128
            or len(receipt_id) > 128
        ):
            raise ValueError("INVALID_SOURCE_RECEIPT_IDENTITY")
        if receipt.get("schema") not in (
            "paper_first_known_source_v1",
            "paper_first_known_source_v2",
        ):
            raise ValueError("UNKNOWN_SOURCE_RECEIPT_SCHEMA")
        if receipt["schema"] == "paper_first_known_source_v2" and (
            stream_event is None
            or stream_event.get("schema") != "paper_observer_stream_event_v2"
            or receipt.get("wire_raw_sha") != stream_event.get("raw_sha")
            or receipt.get("source_book", {}).get("schema") != "paper_source_book_v2"
        ):
            raise ValueError("V4_COMPACT_SOURCE_WIRE_PROOF_REQUIRED")
        if receipt.get("source_id") != source_id:
            raise ValueError("SOURCE_RECEIPT_ID_MISMATCH")
        try:
            if not (
                clock(receipt["source_event_at"])
                <= clock(receipt["first_known_at"])
                <= clock(receipt["captured_at"])
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("SOURCE_RECEIPT_CAUSAL_CLOCK_FAILURE") from exc
        receipt_sha = digest(receipt)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute(
                    "SELECT receipt_sha FROM source_receipts WHERE source_id=? AND receipt_id=?",
                    (source_id, receipt_id),
                ).fetchone()
                if old is not None:
                    if old[0] != receipt_sha:
                        raise ValueError("CONFLICTING_SOURCE_RECEIPT")
                    append_checkpoint(
                        db,
                        stream_event,
                        [{"kind": "source", "key": [source_id, receipt_id], "sha": receipt_sha}],
                    )
                    db.execute("COMMIT")
                    return {
                        "source_id": source_id,
                        "status": "DUPLICATE_RECEIPT",
                        "stream_live": False,
                        "paper_admitted": False,
                    }
                last = db.execute(
                    "SELECT seq,chain_sha FROM source_receipts "
                    "WHERE source_id=? ORDER BY seq DESC LIMIT 1",
                    (source_id,),
                ).fetchone()
                expected = last[0] + 1 if last else 1
                if sequence is None:
                    sequence = expected
                if sequence != expected:
                    raise ValueError("SOURCE_SEQUENCE_GAP_OR_CONFLICT")
                previous = last[1] if last else "0" * 64
                chained = digest([source_id, sequence, receipt_id, previous, receipt_sha])
                db.execute(
                    "INSERT INTO source_receipts VALUES (?,?,?,?,?,?,?)",
                    (
                        source_id,
                        sequence,
                        receipt_id,
                        _json(receipt),
                        receipt_sha,
                        previous,
                        chained,
                    ),
                )
                append_checkpoint(
                    db,
                    stream_event,
                    [{"kind": "source", "key": [source_id, receipt_id], "sha": receipt_sha}],
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        if stream_event is not None:
            return {
                "source_id": source_id,
                "cursor": sequence,
                "head_sha": chained,
                "status": "RECORDED_UNADMITTED_SOURCE",
                "paper_admitted": False,
            }
        return self.source_status(source_id)

    @staticmethod
    def check_collateral_diagnostic(report: dict) -> None:
        if not isinstance(report, dict):
            raise ValueError("SOURCE_COLLATERAL_UNTRUSTED_POSITIVE_CLAIM")
        scope = report.get("copy_scope")
        if scope not in (None, "PERPETUALS_ONLY"):
            raise ValueError("SOURCE_COLLATERAL_UNKNOWN_COPY_SCOPE")
        perpetuals_only = scope == "PERPETUALS_ONLY"
        required_status = (
            "BLOCKED_PERPETUAL_COLLATERAL_RECONCILIATION"
            if perpetuals_only
            else "BLOCKED_COLLATERAL_AND_VAULT_RECONCILIATION"
        )
        if (
            report.get("schema") != "paper_public_collateral_scope_v1"
            or report.get("source_equity") is not None
            or report.get("provider_atomic_nav_available") is not False
            or report.get("collateral_reconciled") is not False
            or report.get("paper_observed") is not False
            or report.get("order_route") != "NONE"
            or report.get("status") != required_status
        ):
            raise ValueError("SOURCE_COLLATERAL_UNTRUSTED_POSITIVE_CLAIM")
        account = report.get("account_address_sha256")
        if (
            not isinstance(account, str)
            or len(account) != 64
            or any(x not in "0123456789abcdef" for x in account)
        ):
            raise ValueError("SOURCE_COLLATERAL_ACCOUNT_HASH_INVALID")
        scopes = report.get("observations")
        if (
            not isinstance(scopes, list)
            or [x.get("scope") for x in scopes if isinstance(x, dict)]
            != ["spotClearinghouseState", "userVaultEquities"]
            or len(scopes) != 2
        ):
            raise ValueError("SOURCE_COLLATERAL_SCOPE_CENSUS_INVALID")
        last_known = None
        for row in scopes:
            if row.get("source_event_at") is not None:
                raise ValueError("SOURCE_COLLATERAL_EVENT_TIME_FABRICATED")
            state = row.get("status")
            if state == "PARTIAL_PUBLIC_OBSERVATION":
                stamp = row.get("first_known_at")
                if not isinstance(stamp, str):
                    raise ValueError("SOURCE_COLLATERAL_KNOWN_TIME_MISSING")
                known = clock(stamp)
                if last_known is not None and known < last_known:
                    raise ValueError("SOURCE_COLLATERAL_CLOCK_REGRESSION")
                last_known = known
                sha = row.get("response_sha256")
                if (
                    not isinstance(sha, str)
                    or len(sha) != 64
                    or any(x not in "0123456789abcdef" for x in sha)
                ):
                    raise ValueError("SOURCE_COLLATERAL_RESPONSE_SHA_INVALID")
                if type(row.get("row_count")) is not int or row["row_count"] < 0:
                    raise ValueError("SOURCE_COLLATERAL_ROW_COUNT_INVALID")
            elif state == "BLOCKED_SCOPE_ACQUISITION":
                if any(
                    row.get(field) is not None
                    for field in ("first_known_at", "response_sha256", "row_count")
                ):
                    raise ValueError("SOURCE_COLLATERAL_FAILED_SCOPE_FABRICATED")
            elif state == "OUT_OF_SCOPE_PERPETUALS_ONLY":
                if (
                    not perpetuals_only
                    or row["scope"] != "userVaultEquities"
                    or any(
                        row.get(field) is not None
                        for field in ("first_known_at", "response_sha256", "row_count")
                    )
                ):
                    raise ValueError("SOURCE_COLLATERAL_INVALID_PERPETUAL_SCOPE_EXCLUSION")
            else:
                raise ValueError("SOURCE_COLLATERAL_UNKNOWN_SCOPE_STATUS")
        if perpetuals_only and scopes[1]["status"] != "OUT_OF_SCOPE_PERPETUALS_ONLY":
            raise ValueError("SOURCE_COLLATERAL_UNNECESSARY_VAULT_SCOPE")
        if perpetuals_only:
            spot = scopes[0]
            if spot["status"] == "PARTIAL_PUBLIC_OBSERVATION":
                balances = spot.get("potential_perp_quote_collateral")
                other = spot.get("other_spot_asset_count")
                if (
                    not isinstance(balances, dict)
                    or type(other) is not int
                    or other < 0
                    or len(balances) + other != spot["row_count"]
                ):
                    raise ValueError("SOURCE_COLLATERAL_QUOTE_CENSUS_INVALID")
                for token, amount in balances.items():
                    if (
                        token not in ("USDC", "USDH")
                        or not isinstance(amount, dict)
                        or set(amount) != {"total", "hold"}
                        or type(amount["total"]) is not str
                        or (amount["hold"] is not None and type(amount["hold"]) is not str)
                    ):
                        raise ValueError("SOURCE_COLLATERAL_QUOTE_FIELDS_INVALID")
                    number(amount["total"])
                    if amount["hold"] is not None:
                        number(amount["hold"])
            elif any(
                key in spot for key in ("potential_perp_quote_collateral", "other_spot_asset_count")
            ):
                raise ValueError("SOURCE_COLLATERAL_FAILED_SPOT_FABRICATED")
        # New prospective receipts include the official userAbstraction
        # /info response. Legacy SHA-sealed two-scope evidence has no mode and
        # remains replayable, but never gains a default/assumed account mode.
        if "account_abstraction" in report:
            mode = report["account_abstraction"]
            if not isinstance(mode, dict) or mode.get("source_signed") is not False:
                raise ValueError("SOURCE_ACCOUNT_MODE_UNTRUSTED_ATTESTATION")
            if mode.get("source_event_at") is not None:
                raise ValueError("SOURCE_ACCOUNT_MODE_EVENT_TIME_FABRICATED")
            if mode.get("status") == "OFFICIAL_PUBLIC_ACCOUNT_MODE_OBSERVED":
                value = mode.get("mode")
                sha = mode.get("response_sha256")
                stamp = mode.get("first_known_at")
                if (
                    type(value) is not str
                    or value not in PUBLIC_ACCOUNT_MODES
                    or type(sha) is not str
                    or len(sha) != 64
                    or any(x not in "0123456789abcdef" for x in sha)
                    or type(stamp) is not str
                    or "reason" in mode
                ):
                    raise ValueError("SOURCE_ACCOUNT_MODE_PROVENANCE_INVALID")
                known = clock(stamp)
                if last_known is not None and known < last_known:
                    raise ValueError("SOURCE_ACCOUNT_MODE_CLOCK_REGRESSION")
            elif mode.get("status") == "BLOCKED_ACCOUNT_MODE_ACQUISITION":
                if any(
                    mode.get(key) is not None
                    for key in ("mode", "response_sha256", "first_known_at")
                ):
                    raise ValueError("SOURCE_ACCOUNT_MODE_BLOCKED_CLAIM_INVALID")
            else:
                raise ValueError("SOURCE_ACCOUNT_MODE_STATUS_INVALID")

    def append_collateral_diagnostic(
        self, report: dict, *, stream_event: dict | None = None
    ) -> dict:
        """Durably SHA-chain incomplete spot/vault scopes, never authorize finance."""
        self.check_collateral_diagnostic(report)
        account = report["account_address_sha256"]
        receipt_sha = digest(report)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute(
                    "SELECT payload_sha FROM source_scope_receipts "
                    "WHERE account_sha=? AND receipt_id=?",
                    (account, receipt_sha),
                ).fetchone()
                if old is None:
                    last = db.execute(
                        "SELECT seq,chain_sha FROM source_scope_receipts WHERE account_sha=? "
                        "ORDER BY seq DESC LIMIT 1",
                        (account,),
                    ).fetchone()
                    previous = last[1] if last else "0" * 64
                    seq = last[0] + 1 if last else 1
                    chained = digest([account, seq, receipt_sha, previous])
                    db.execute(
                        "INSERT INTO source_scope_receipts VALUES (?,?,?,?,?,?,?)",
                        (account, seq, receipt_sha, _json(report), receipt_sha, previous, chained),
                    )
                elif old[0] != receipt_sha:
                    raise ValueError("SOURCE_COLLATERAL_RECEIPT_CONFLICT")
                append_checkpoint(
                    db,
                    stream_event,
                    [{"kind": "collateral", "key": [account, receipt_sha], "sha": receipt_sha}],
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.collateral_scope_status(account)

    def collateral_scope_status(self, account_sha: str) -> dict:
        with self._writer() as db:
            rows = db.execute(
                "SELECT seq,receipt_id,payload,payload_sha,prior_sha,chain_sha "
                "FROM source_scope_receipts WHERE account_sha=? ORDER BY seq",
                (account_sha,),
            ).fetchall()
        head = "0" * 64
        for expected, (seq, receipt_id, payload, sha, prior, chain_sha) in enumerate(rows, 1):
            content = json.loads(payload)
            if (
                seq != expected
                or receipt_id != sha
                or digest(content) != sha
                or content.get("account_address_sha256") != account_sha
                or prior != head
                or chain_sha != digest([account_sha, seq, sha, prior])
            ):
                raise ValueError("SOURCE_COLLATERAL_CHAIN_DIVERGENCE")
            self.check_collateral_diagnostic(content)
            head = chain_sha
        return {
            "account_address_sha256": account_sha,
            "cursor": len(rows),
            "head_sha": head,
            "status": "CAPTURED_DIAGNOSTICS_ONLY" if rows else "NO_COLLATERAL_DIAGNOSTICS",
            "source_equity": None,
            "paper_admitted": False,
        }

    def source_status(self, source_id: str) -> dict:
        with self._writer() as db:
            rows = db.execute(
                "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
                "FROM source_receipts WHERE source_id=? ORDER BY seq",
                (source_id,),
            ).fetchall()
        previous = "0" * 64
        for expected, (seq, receipt_id, payload, sha, prior, head) in enumerate(rows, 1):
            if (
                seq != expected
                or prior != previous
                or digest(json.loads(payload)) != sha
                or head != digest([source_id, seq, receipt_id, previous, sha])
            ):
                raise ValueError("SOURCE_TAPE_DIVERGENCE")
            previous = head
        return {
            "source_id": source_id,
            "cursor": len(rows),
            "head_sha": previous,
            "status": "CAPTURED_ONLY" if rows else "NO_SOURCE_RECEIPTS",
            "stream_live": False,
            "paper_admitted": False,
        }

    @staticmethod
    def _validate_market_trade_batch(batch: dict) -> None:
        if not isinstance(batch, dict):
            raise ValueError("PAPER_CCXT_TRADE_BATCH_INVALID")
        if (
            batch.get("schema") != "paper_ccxt_trade_cache_observation_v1"
            or not isinstance(batch.get("instrument"), str)
            or not batch["instrument"]
            or not isinstance(batch.get("stream_epoch"), str)
            or not batch["stream_epoch"]
            or batch.get("broker_order_route") != "NONE"
            or batch.get("trade_volume_complete") is not False
            or batch.get("executable_volume_base") is not None
            or batch.get("paper_observed") is not False
        ):
            raise ValueError("PAPER_CCXT_TRADE_EVIDENCE_UNTRUSTED")
        try:
            known = clock(batch["first_known_at"])
            rows = batch["trades"]
            baseline = batch["status"] == "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
            if not isinstance(rows, list) or (baseline and rows):
                raise ValueError
            if batch["status"] not in (
                "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE",
                "PARTIAL_LOCAL_TRADES",
            ):
                raise ValueError
            if batch["new_local_trade_count"] != len(rows):
                raise ValueError
            if number(batch["observed_volume_base"]) != sum(
                (number(row["amount_base"]) for row in rows), Decimal("0")
            ):
                raise ValueError
            seen = set()
            for row in rows:
                if (
                    row.get("instrument") != batch["instrument"]
                    or row.get("broker_order_route") != "NONE"
                    or row.get("provider_signed") is not False
                    or row.get("source") != "CCXT_PRO_HYPERLIQUID_PUBLIC_TRADES"
                    or not isinstance(row.get("native_trade_id"), str)
                    or not row["native_trade_id"]
                    or row["native_trade_id"] in seen
                    or number(row["price"]) <= 0
                    or number(row["amount_base"]) <= 0
                    or clock(row["source_event_at"]) > clock(row["first_known_at"])
                    or (
                        clock(row["first_known_at"]) > known
                        if batch.get("local_clock_semantics") == "PER_NATIVE_TRADE_FIRST_RECEIPT"
                        else clock(row["first_known_at"]) != known
                    )
                ):
                    raise ValueError
                seen.add(row["native_trade_id"])
        except ValueError, TypeError, KeyError:
            raise ValueError("PAPER_CCXT_TRADE_BATCH_INVALID") from None

    def append_market_trade_batch(self, batch: dict, *, stream_event: dict | None = None) -> dict:
        """Immutable partial observed trades, never executable volume evidence."""
        self._validate_market_trade_batch(batch)
        instrument = batch["instrument"]
        batch_sha = digest(batch)
        received = batch["first_known_at"]
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                duplicate = db.execute(
                    "SELECT batch_sha FROM market_trade_batches WHERE instrument=? AND batch_sha=?",
                    (instrument, batch_sha),
                ).fetchone()
                if duplicate is not None:
                    append_checkpoint(
                        db,
                        stream_event,
                        [{"kind": "trades", "key": [instrument, batch_sha], "sha": batch_sha}],
                    )
                    db.execute("COMMIT")
                    return {
                        "status": "DUPLICATE_PARTIAL_TRADE_OBSERVATION",
                        "batch_sha": batch_sha,
                    }
                head = db.execute(
                    "SELECT cursor,known_at,chain_sha FROM market_trade_heads WHERE instrument=?",
                    (instrument,),
                ).fetchone()
                if head:
                    cursor, prior_time, prior_sha = head
                    if clock(received) < clock(prior_time):
                        raise ValueError("PAPER_CCXT_TRADE_KNOWN_TIME_REGRESSION")
                    prior = db.execute(
                        "SELECT batch_sha,prior_sha,chain_sha,payload "
                        "FROM market_trade_batches WHERE instrument=? AND seq=?",
                        (instrument, cursor),
                    ).fetchone()
                    if (
                        prior is None
                        or prior[2] != prior_sha
                        or prior[2] != digest([instrument, cursor, prior[0], prior[1]])
                        or digest(json.loads(prior[3])) != prior[0]
                    ):
                        raise ValueError("PAPER_CCXT_TRADE_TAPE_DIVERGENCE")
                    previous_epoch = json.loads(prior[3])["stream_epoch"]
                    if previous_epoch != batch["stream_epoch"] and batch["status"] != (
                        "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE"
                    ):
                        raise ValueError("PAPER_CCXT_TRADE_EPOCH_NOT_BASELINED")
                else:
                    cursor, prior_sha = 0, "0" * 64
                    if batch["status"] != "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE":
                        raise ValueError("PAPER_CCXT_TRADE_EPOCH_NOT_BASELINED")
                seq = cursor + 1
                chain_sha = digest([instrument, seq, batch_sha, prior_sha])
                if head:
                    db.execute(
                        "UPDATE market_trade_heads SET cursor=?,known_at=?,chain_sha=? "
                        "WHERE instrument=?",
                        (seq, received, chain_sha, instrument),
                    )
                else:
                    db.execute(
                        "INSERT INTO market_trade_heads VALUES (?,?,?,?)",
                        (instrument, seq, received, chain_sha),
                    )
                db.execute(
                    "INSERT INTO market_trade_batches VALUES (?,?,?,?,?,?,?)",
                    (
                        instrument,
                        seq,
                        batch_sha,
                        _json(batch),
                        prior_sha,
                        chain_sha,
                        received,
                    ),
                )
                append_checkpoint(
                    db,
                    stream_event,
                    [{"kind": "trades", "key": [instrument, batch_sha], "sha": batch_sha}],
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {
            "status": "RECORDED_PARTIAL_TRADES_ONLY",
            "instrument": instrument,
            "cursor": seq,
            "batch_sha": batch_sha,
            "head_sha": chain_sha,
            "executable_volume_base": None,
        }

    def market_trade_status(self, instrument: str) -> dict:
        from contextlib import closing

        uri = "file:" + str(self.path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT seq,batch_sha,payload,prior_sha,chain_sha,known_at "
                "FROM market_trade_batches WHERE instrument=? ORDER BY seq",
                (instrument,),
            ).fetchall()
            head = db.execute(
                "SELECT cursor,known_at,chain_sha FROM market_trade_heads WHERE instrument=?",
                (instrument,),
            ).fetchone()
        previous = "0" * 64
        known_at = None
        epochs: list[str] = []
        observed_count = 0
        for seq, (ordinal, sha, raw, prior, chain, known) in enumerate(rows, 1):
            batch = json.loads(raw)
            self._validate_market_trade_batch(batch)
            if (
                ordinal != seq
                or digest(batch) != sha
                or batch["instrument"] != instrument
                or batch["first_known_at"] != known
                or (known_at is not None and clock(known) < clock(known_at))
                or prior != previous
                or chain != digest([instrument, seq, sha, prior])
            ):
                raise ValueError("PAPER_CCXT_TRADE_TAPE_DIVERGENCE")
            if batch["stream_epoch"] not in epochs:
                if batch["status"] != "BASELINE_RETROSPECTIVE_NOT_ELIGIBLE":
                    raise ValueError("PAPER_CCXT_TRADE_EPOCH_NOT_BASELINED")
                epochs.append(batch["stream_epoch"])
            previous, known_at = chain, known
            observed_count += batch["new_local_trade_count"]
        if (head is None and rows) or (
            head is not None
            and (head[0] != len(rows) or head[1] != known_at or head[2] != previous)
        ):
            raise ValueError("PAPER_CCXT_TRADE_HEAD_DIVERGENCE")
        return {
            "schema": "paper_ccxt_trade_tape_status_v1",
            "instrument": instrument,
            "cursor": len(rows),
            "head_sha": previous,
            "stream_epochs": len(epochs),
            "locally_observed_trade_count": observed_count,
            "last_received_at": known_at,
            "trade_volume_complete": False,
            "executable_volume_base": None,
            "paper_observed": False,
            "order_route": "NONE",
        }

    @staticmethod
    def validate_market_quote(quote: dict) -> None:
        from .pm_forward_ccxt_market import SCHEMA, verify_l2_evidence

        if not isinstance(quote, dict) or quote.get("schema") != SCHEMA:
            raise ValueError("PAPER_CCXT_QUOTE_SCHEMA_UNKNOWN")
        try:
            contract = {
                "quote_sha": digest(quote),
                "provider_catalog_sha": quote["catalog_sha"],
                "instrument": quote["instrument"],
                "quote_mid": quote["mid_quote"],
            }
            observation = {
                "instrument": quote["instrument"],
                "event_at": quote["source_event_at"],
                "first_known_at": quote["first_known_at"],
                "mark": quote["mid_quote"],
                "quality": "VERIFIED_QUOTE",
                "volume_base": None,
            }
            failed = verify_l2_evidence(
                quote,
                contract,
                observation,
                decision_at=quote["first_known_at"],
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("PAPER_CCXT_QUOTE_INVALID") from exc
        if failed:
            raise ValueError("PAPER_CCXT_QUOTE_INVALID:" + ",".join(failed))

    def append_market_quote(self, quote: dict, *, stream_event: dict | None = None) -> dict:
        """One public CCXT L2 capture, never a trade-capacity or wallet signal.

        The private SQLite market receipt is locally SHA-chained and
        idempotent. This does not provide a vendor signature, authenticated
        exchange session, or a filled paper order.
        """
        self.validate_market_quote(quote)
        instrument = quote["instrument"]
        known_at = quote["first_known_at"]
        event_at = quote["source_event_at"]
        raw_sha = digest(quote)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT payload_sha FROM market_quote_receipts "
                    "WHERE instrument=? AND quote_id=?",
                    (instrument, raw_sha),
                ).fetchone()
                if existing is not None:
                    if existing[0] != raw_sha:
                        raise ValueError("PAPER_MARKET_QUOTE_CONFLICT")
                    append_checkpoint(
                        db,
                        stream_event,
                        [{"kind": "quote", "key": [instrument, raw_sha], "sha": raw_sha}],
                    )
                    db.execute("COMMIT")
                    return {"status": "DUPLICATE_MARKET_QUOTE", "quote_sha": raw_sha}
                head = db.execute(
                    "SELECT cursor,event_at,known_at,chain_sha FROM market_quote_heads "
                    "WHERE instrument=?",
                    (instrument,),
                ).fetchone()
                if head is not None:
                    cursor, prev_event, prev_known, previous = head
                    if clock(event_at) < clock(prev_event) or clock(known_at) < clock(prev_known):
                        raise ValueError("PAPER_MARKET_QUOTE_CLOCK_REGRESSION")
                    previous_book = db.execute(
                        "SELECT payload,payload_sha,prior_sha,chain_sha "
                        "FROM market_quote_receipts WHERE instrument=? AND seq=?",
                        (instrument, cursor),
                    ).fetchone()
                    if previous_book is None:
                        raise ValueError("PAPER_MARKET_QUOTE_HEAD_DIVERGENCE")
                    old_quote = json.loads(previous_book[0])
                    if (
                        digest(old_quote) != previous_book[1]
                        or previous_book[3] != previous
                        or previous_book[3]
                        != digest([instrument, cursor, previous_book[1], previous_book[2]])
                    ):
                        raise ValueError("PAPER_MARKET_QUOTE_HEAD_DIVERGENCE")
                    if old_quote.get("source_event_at") == event_at and old_quote.get(
                        "book_sha"
                    ) == quote.get("book_sha"):
                        raise ValueError("PAPER_MARKET_QUOTE_REPLAYED_BOOK")
                else:
                    cursor, previous = 0, "0" * 64
                seq = cursor + 1
                head_sha = digest([instrument, seq, raw_sha, previous])
                if head is None:
                    db.execute(
                        "INSERT INTO market_quote_heads VALUES (?,?,?,?,?)",
                        (instrument, seq, event_at, known_at, head_sha),
                    )
                else:
                    db.execute(
                        "UPDATE market_quote_heads SET cursor=?,event_at=?,known_at=?,"
                        "chain_sha=? WHERE instrument=?",
                        (seq, event_at, known_at, head_sha, instrument),
                    )
                db.execute(
                    "INSERT INTO market_quote_receipts VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        instrument,
                        seq,
                        raw_sha,
                        _json(quote),
                        raw_sha,
                        previous,
                        head_sha,
                        event_at,
                        known_at,
                    ),
                )
                append_checkpoint(
                    db,
                    stream_event,
                    [{"kind": "quote", "key": [instrument, raw_sha], "sha": raw_sha}],
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {
            "status": "RECORDED_L2_ONLY_CAPACITY_UNKNOWN",
            "instrument": instrument,
            "cursor": seq,
            "quote_sha": raw_sha,
            "journal_head_sha": head_sha,
            "paper_observed": False,
            "order_route": "NONE",
        }

    def append_vike_minute(self, observation: dict) -> dict:
        """Store a causally observed minute trade price separately from L2.

        A finalized historical bar cannot acquire a fictional earlier receipt.
        Both forming and finalized observations carry their actual REST clock.
        """
        from .pm_vike_minute import native_instrument, validate_observation

        validate_observation(observation)
        instrument = native_instrument(observation["native_symbol"])
        known_at = observation["first_known_at"]
        event_at = observation["bar_start_at"]
        if clock(event_at) > clock(known_at):
            raise ValueError("PAPER_VIKE_FUTURE_PRICE")
        raw_sha = digest(observation)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute(
                    "SELECT payload_sha FROM vike_minute_receipts "
                    "WHERE instrument=? AND observation_id=?",
                    (instrument, raw_sha),
                ).fetchone()
                if old is not None:
                    db.execute("COMMIT")
                    return {"status": "DUPLICATE_VIKE_MINUTE", "instrument": instrument}
                head = db.execute(
                    "SELECT cursor,event_at,known_at,chain_sha FROM vike_minute_heads "
                    "WHERE instrument=?",
                    (instrument,),
                ).fetchone()
                if head is not None:
                    seq, prior_event, prior_known, previous = head
                    if clock(event_at) < clock(prior_event) or clock(known_at) < clock(prior_known):
                        raise ValueError("PAPER_VIKE_MINUTE_CLOCK_REGRESSION")
                else:
                    seq, previous = 0, "0" * 64
                seq += 1
                chain = digest([instrument, seq, raw_sha, previous])
                if head is None:
                    db.execute(
                        "INSERT INTO vike_minute_heads VALUES (?,?,?,?,?)",
                        (instrument, seq, event_at, known_at, chain),
                    )
                else:
                    db.execute(
                        "UPDATE vike_minute_heads SET cursor=?,event_at=?,known_at=?,"
                        "chain_sha=? WHERE instrument=?",
                        (seq, event_at, known_at, chain, instrument),
                    )
                db.execute(
                    "INSERT INTO vike_minute_receipts VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        instrument,
                        seq,
                        raw_sha,
                        _json(observation),
                        raw_sha,
                        previous,
                        chain,
                        event_at,
                        known_at,
                    ),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {
            "status": "RECORDED_ESTIMATED_PRICE_ONLY",
            "instrument": instrument,
            "cursor": seq,
            "journal_head_sha": chain,
            "paper_observed": False,
            "order_route": "NONE",
        }

    def market_quote_status(self, instrument: str) -> dict:
        """Read-only full chain audit; no market/financial mutations."""
        return self.market_quote_file_status(self.path, instrument)

    @staticmethod
    def market_quote_file_status(path: Path, instrument: str) -> dict:
        """Native chain/quote verification without instantiating a writable journal."""
        from contextlib import closing

        if path.is_symlink() or not path.is_file():
            raise ValueError("PAPER_MARKET_QUOTE_PATH_INVALID")
        uri = "file:" + str(path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha,"
                "event_at,known_at FROM market_quote_receipts "
                "WHERE instrument=? ORDER BY seq",
                (instrument,),
            ).fetchall()
            head = db.execute(
                "SELECT cursor,event_at,known_at,chain_sha FROM market_quote_heads "
                "WHERE instrument=?",
                (instrument,),
            ).fetchone()
        previous = "0" * 64
        last_event = last_known = ""
        for expected_seq, (seq, quote_id, payload, sha, prior, chain, at, known) in enumerate(
            rows, 1
        ):
            quote = json.loads(payload)
            PaperJournal.validate_market_quote(quote)
            if (
                seq < 1
                or seq != expected_seq
                or quote.get("instrument") != instrument
                or digest(quote) != sha
                or quote_id != sha
                or previous != prior
                or chain != digest([instrument, seq, sha, prior])
                or quote["source_event_at"] != at
                or quote["first_known_at"] != known
                or (last_event and clock(at) < clock(last_event))
                or (last_known and clock(known) < clock(last_known))
            ):
                raise ValueError("PAPER_MARKET_QUOTE_CHAIN_DIVERGENCE")
            previous, last_event, last_known = chain, at, known
        if head is None:
            if rows:
                raise ValueError("PAPER_MARKET_QUOTE_HEAD_DIVERGENCE")
        elif (
            head[0] != len(rows)
            or head[1] != last_event
            or head[2] != last_known
            or head[3] != previous
        ):
            raise ValueError("PAPER_MARKET_QUOTE_HEAD_DIVERGENCE")
        return {
            "schema": "paper_ccxt_market_tape_status_v1",
            "instrument": instrument,
            "cursor": len(rows),
            "journal_head_sha": previous,
            "last_quote_known_at": last_known or None,
            "trade_volume_complete": False,
            "paper_observed": False,
            "order_route": "NONE",
        }

    @staticmethod
    def _validate_public_wallet_trade(event: dict) -> None:
        """Market-wide public trades are wallet-position *observations*, never NAV."""
        from .pm03_account import Instrument

        if not isinstance(event, dict) or event.get("schema") != "paper_public_wallet_trade_v1":
            raise ValueError("PUBLIC_WALLET_TRADE_SCHEMA_INVALID")
        wallet = event.get("wallet_key")
        if (
            not isinstance(wallet, str)
            or not wallet.startswith("wallet:")
            or not wallet[7:].isdecimal()
            or int(wallet[7:]) <= 0
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_CANONICAL_ID_REQUIRED")
        instrument = Instrument.parse(event.get("instrument", ""))
        if instrument.venue != "hyperliquid" or not instrument.market.startswith("mainnet:perp:"):
            raise ValueError("PUBLIC_WALLET_TRADE_NOT_NATIVE_PERP")
        if (
            event.get("evidence_class") != "PUBLIC_TRADE_PROVISIONAL_NO_NAV"
            or event.get("order_route") != "NONE"
            or event.get("provider_signed") is not False
            or event.get("source_account_complete") is not False
            or event.get("paper_admitted") is not False
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_FALSE_ADMISSION")
        epoch = event.get("stream_epoch")
        sha = event.get("source_trade_sha")
        watchlist_sha = event.get("watchlist_sha")
        if (
            not isinstance(watchlist_sha, str)
            or len(watchlist_sha) != 64
            or any(c not in "0123456789abcdef" for c in watchlist_sha)
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_WATCHLIST_PROVENANCE_REQUIRED")
        if (
            not isinstance(epoch, str)
            or len(epoch) != 32
            or any(c not in "0123456789abcdef" for c in epoch)
            or not isinstance(sha, str)
            or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_PROVENANCE_INVALID")
        t = event.get("source_timestamp_ms")
        tid = event.get("native_tid")
        if type(t) is not int or t <= 0 or type(tid) is not int or tid < 0:
            raise ValueError("PUBLIC_WALLET_TRADE_NATIVE_ID_INVALID")
        side = event.get("wallet_side")
        if side not in {"BUY", "SELL"} or event.get("event_key") != digest(
            [event["instrument"], t, tid, wallet, side]
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_IDENTITY_MISMATCH")
        if number(event.get("price")) <= 0:
            raise ValueError("PUBLIC_WALLET_TRADE_PRICE_INVALID")
        qty = number(event.get("signed_qty"))
        if qty == 0 or (qty > 0) != (side == "BUY"):
            raise ValueError("PUBLIC_WALLET_TRADE_SIGN_MISMATCH")
        try:
            source = datetime.fromtimestamp(t / 1000, tz=UTC)
            if clock(event["source_event_at"]) != source or source > clock(event["first_known_at"]):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("PUBLIC_WALLET_TRADE_CLOCK_INVALID") from exc

    def append_public_wallet_trades(
        self, events: list[dict], *, stream_event: dict | None = None
    ) -> dict:
        """Atomically append one or more first-known public wallet trade observations.

        On reconnect, a duplicate may have a later first-known clock; the
        original receipt remains immutable. A conflicting native trade fails.
        """
        if not isinstance(events, list) or not events:
            raise ValueError("PUBLIC_WALLET_TRADE_BATCH_EMPTY")
        for event in events:
            self._validate_public_wallet_trade(event)
        unique = {}
        for event in events:
            key = (event["wallet_key"], event["instrument"], event["event_key"])
            prior = unique.setdefault(key, event)
            if prior != event:
                raise ValueError("PUBLIC_WALLET_TRADE_BATCH_CONFLICT")
        appended, duplicates = 0, 0
        receipt_refs = []
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                committed_at = datetime.now(UTC).isoformat(timespec="microseconds")
                for event in sorted(
                    unique.values(),
                    key=lambda item: (
                        item["wallet_key"],
                        item["instrument"],
                        item["first_known_at"],
                        item["event_key"],
                    ),
                ):
                    wallet, inst = event["wallet_key"], event["instrument"]
                    event_key = event["event_key"]
                    existing = db.execute(
                        "SELECT payload FROM public_wallet_trade_receipts "
                        "WHERE wallet_key=? AND instrument=? AND event_key=?",
                        (wallet, inst, event_key),
                    ).fetchone()
                    if existing is not None:
                        previous = json.loads(existing[0])
                        # Transport epoch and first-known can change after reconnect.
                        stable = (
                            "source_event_at",
                            "source_timestamp_ms",
                            "native_tid",
                            "source_trade_sha",
                            "wallet_side",
                            "price",
                            "signed_qty",
                        )
                        if any(previous[field] != event[field] for field in stable):
                            raise ValueError("PUBLIC_WALLET_TRADE_CONFLICTING_REPLAY")
                        duplicates += 1
                        receipt_refs.append(
                            {
                                "kind": "public",
                                "key": [wallet, inst, event_key],
                                "sha": digest(previous),
                            }
                        )
                        continue
                    if clock(event["first_known_at"]) > clock(committed_at):
                        raise ValueError("PUBLIC_WALLET_TRADE_RECEIPT_IN_FUTURE")
                    head = db.execute(
                        "SELECT cursor,known_at,chain_sha FROM public_wallet_trade_heads "
                        "WHERE wallet_key=? AND instrument=?",
                        (wallet, inst),
                    ).fetchone()
                    if head is None:
                        cursor, previous_sha = 0, "0" * 64
                    else:
                        cursor, last_known, previous_sha = head
                        if clock(event["first_known_at"]) < clock(last_known):
                            raise ValueError("PUBLIC_WALLET_TRADE_LOCAL_CLOCK_REGRESSION")
                        prior = db.execute(
                            "SELECT payload,payload_sha,prior_sha,chain_sha,committed_at "
                            "FROM public_wallet_trade_receipts "
                            "WHERE wallet_key=? AND instrument=? AND seq=?",
                            (wallet, inst, cursor),
                        ).fetchone()
                        if (
                            prior is None
                            or digest(json.loads(prior[0])) != prior[1]
                            or prior[3] != previous_sha
                            or prior[3]
                            != digest([wallet, inst, cursor, prior[1], prior[2], prior[4]])
                        ):
                            raise ValueError("PUBLIC_WALLET_TRADE_HEAD_DIVERGENCE")
                    seq = cursor + 1
                    payload_sha = digest(event)
                    # Bind the durable commit clock; it is PIT-critical and
                    # must not be retroactively backdated in SQLite.
                    next_sha = digest([wallet, inst, seq, payload_sha, previous_sha, committed_at])
                    if head is None:
                        db.execute(
                            "INSERT INTO public_wallet_trade_heads VALUES (?,?,?,?,?)",
                            (wallet, inst, seq, event["first_known_at"], next_sha),
                        )
                    else:
                        db.execute(
                            "UPDATE public_wallet_trade_heads SET cursor=?,known_at=?,chain_sha=? "
                            "WHERE wallet_key=? AND instrument=?",
                            (seq, event["first_known_at"], next_sha, wallet, inst),
                        )
                    db.execute(
                        "INSERT INTO public_wallet_trade_receipts VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            wallet,
                            inst,
                            seq,
                            event_key,
                            _json(event),
                            payload_sha,
                            previous_sha,
                            next_sha,
                            event["first_known_at"],
                            committed_at,
                        ),
                    )
                    appended += 1
                    receipt_refs.append(
                        {"kind": "public", "key": [wallet, inst, event_key], "sha": payload_sha}
                    )
                append_checkpoint(db, stream_event, receipt_refs)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {
            "status": "RECORDED_PROVISIONAL_WALLET_TRADES",
            "new_receipts": appended,
            "duplicates": duplicates,
            "paper_admitted": False,
            "order_route": "NONE",
        }

    def append_public_trade_gap(
        self, *, instrument: str, stream_epoch: str, observed_at: str, reason: str
    ) -> dict:
        from .pm03_account import Instrument

        inst = Instrument.parse(instrument)
        if inst.venue != "hyperliquid" or not inst.market.startswith("mainnet:perp:"):
            raise ValueError("PUBLIC_TRADE_GAP_MARKET_INVALID")
        if (
            len(stream_epoch) != 32
            or any(c not in "0123456789abcdef" for c in stream_epoch)
            or reason
            not in {
                "INITIAL_BASELINE",
                "RECONNECT",
                "DISCONNECT",
                "TIMEOUT",
                "INTEGRITY_FAILURE",
                "BOUNDED_CAPTURE_ENDED",
            }
        ):
            raise ValueError("PUBLIC_TRADE_GAP_REASON_INVALID")
        clock(observed_at)
        identity = digest([instrument, stream_epoch, observed_at, reason])
        with self._writer() as db:
            db.execute(
                "INSERT OR IGNORE INTO public_trade_stream_gaps VALUES (?,?,?,?,?)",
                (identity, instrument, stream_epoch, observed_at, reason),
            )
        return {"status": "COVERAGE_GAP_RECORDED", "gap_sha": identity, "order_route": "NONE"}

    def audit_public_wallet_trade_tape(self, wallet_key: str, instrument: str) -> dict:
        """Verify the entire prospective chain once, outside hot bucket reads."""
        uri = "file:" + str(self.path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")  # consistent receipt rows and chain head
            rows = db.execute(
                "SELECT seq,event_key,payload,payload_sha,prior_sha,chain_sha,known_at,committed_at "
                "FROM public_wallet_trade_receipts "
                "WHERE wallet_key=? AND instrument=? ORDER BY seq",
                (wallet_key, instrument),
            ).fetchall()
            head = db.execute(
                "SELECT cursor,known_at,chain_sha FROM public_wallet_trade_heads "
                "WHERE wallet_key=? AND instrument=?",
                (wallet_key, instrument),
            ).fetchone()
        previous, last_known = "0" * 64, None
        for index, (seq, event_key, raw, sha, prior, chain, known, committed) in enumerate(rows, 1):
            event = json.loads(raw)
            self._validate_public_wallet_trade(event)
            if (
                seq != index
                or event["event_key"] != event_key
                or event["wallet_key"] != wallet_key
                or event["instrument"] != instrument
                or digest(event) != sha
                or prior != previous
                or chain != digest([wallet_key, instrument, seq, sha, prior, committed])
                or clock(committed) < clock(known)
                or known != event["first_known_at"]
                or (last_known and clock(known) < clock(last_known))
            ):
                raise ValueError("PUBLIC_WALLET_TRADE_TAPE_DIVERGENCE")
            previous, last_known = chain, known
        if (head is None and rows) or (
            head is not None and head != (len(rows), last_known, previous)
        ):
            raise ValueError("PUBLIC_WALLET_TRADE_HEAD_DIVERGENCE")
        return {
            "status": "VERIFIED_PROVISIONAL_TAPE",
            "receipts": len(rows),
            "head_sha": previous,
            "source_complete": False,
            "paper_admitted": False,
        }

    def observed_utc_net_delta(
        self, wallet_key: str, instrument: str, *, bucket_start_at: str, as_of: str
    ) -> dict:
        """Read only events durably available by the UTC bucket close.

        A retrospective backfill cannot be executed at its original event time.
        Even an intact provisional tape is NEVER a complete leader book/NAV.
        """
        start = clock(bucket_start_at).astimezone(UTC)
        if start.second or start.microsecond or start.minute % 5:
            raise ValueError("PUBLIC_WALLET_BUCKET_NOT_UTC_ALIGNED")
        end = start + timedelta(minutes=5)
        as_of_dt = clock(as_of)
        if as_of_dt < end:
            return {
                "status": "WAIT",
                "bucket_end_at": end.isoformat(),
                "paper_admitted": False,
                "order_route": "NONE",
            }
        uri = "file:" + str(self.path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")  # atomic receipt/gap snapshot at the requested as-of
            rows = db.execute(
                "SELECT seq,payload,payload_sha,prior_sha,chain_sha,known_at,committed_at "
                "FROM public_wallet_trade_receipts "
                "WHERE wallet_key=? AND instrument=? AND known_at>=? AND known_at<? "
                "AND committed_at<=? ORDER BY seq",
                (
                    wallet_key,
                    instrument,
                    start.isoformat(),
                    end.isoformat(),
                    as_of_dt.astimezone(UTC).isoformat(),
                ),
            ).fetchall()
            gaps = db.execute(
                "SELECT COUNT(*) FROM public_trade_stream_gaps "
                "WHERE instrument=? AND observed_at>=? AND observed_at<?",
                (instrument, start.isoformat(), end.isoformat()),
            ).fetchone()[0]
        net = gross = Decimal("0")
        count = late = 0
        provenance = []
        for seq, raw, sha, prior, chain, known, committed in rows:
            event = json.loads(raw)
            self._validate_public_wallet_trade(event)
            if (
                digest(event) != sha
                or event["wallet_key"] != wallet_key
                or event["instrument"] != instrument
                or event["first_known_at"] != known
                or chain != digest([wallet_key, instrument, seq, sha, prior, committed])
                or clock(committed) < clock(known)
            ):
                raise ValueError("PUBLIC_WALLET_BUCKET_RECEIPT_DIVERGENCE")
            if clock(committed) > end:
                late += 1
                continue
            count += 1
            qty = number(event["signed_qty"])
            net += qty
            gross += abs(qty)
            provenance.append(sha)
        return {
            "schema": "paper_public_utc_net_delta_v1",
            "status": "BLOCKED_NO_WHOLE_WALLET_NAV_OR_CONTINUITY",
            "wallet_key": wallet_key,
            "instrument": instrument,
            "bucket_start_at": start.isoformat(),
            "bucket_end_at": end.isoformat(),
            "read_at": as_of,
            "event_count": count,
            "late_event_count": late,
            "gap_count": gaps,
            "net_position_delta": str(net),
            "gross_observed_turnover": str(gross),
            "receipt_set_sha": digest(provenance),
            "source_complete": False,
            "whole_wallet_nav_attested": False,
            "paper_admitted": False,
            "order_route": "NONE",
        }

    def persist_observed_utc_bucket(self, report: dict) -> dict:
        """Persist one immutable, nonfinancial bucket. Never submit a fill."""
        if (
            report.get("schema") != "paper_public_utc_net_delta_v1"
            or report.get("status") != "BLOCKED_NO_WHOLE_WALLET_NAV_OR_CONTINUITY"
            or report.get("paper_admitted") is not False
            or report.get("order_route") != "NONE"
            or clock(report["read_at"]) < clock(report["bucket_end_at"])
        ):
            raise ValueError("PUBLIC_BUCKET_POSITIVE_ADMISSION_FORBIDDEN")
        expected = self.observed_utc_net_delta(
            report["wallet_key"],
            report["instrument"],
            bucket_start_at=report["bucket_start_at"],
            as_of=report["read_at"],
        )
        if expected != report:
            raise ValueError("PUBLIC_BUCKET_RECOMPUTATION_DIVERGENCE")
        key = digest([report["wallet_key"], report["instrument"], report["bucket_start_at"]])
        # The read clock is audit metadata, not part of the immutable policy/result.
        # A second read with identical evidence must remain idempotent.
        sha = digest({key: value for key, value in report.items() if key != "read_at"})
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                prior = db.execute(
                    "SELECT plan_sha FROM provisional_utc_buckets WHERE bucket_key=?", (key,)
                ).fetchone()
                if prior is not None and prior[0] != sha:
                    raise ValueError("PUBLIC_BUCKET_MUTATION_REQUIRES_CORRECTION")
                if prior is None:
                    db.execute(
                        "INSERT INTO provisional_utc_buckets VALUES (?,?,?,?,?,?,?,?)",
                        (
                            key,
                            report["wallet_key"],
                            report["instrument"],
                            report["bucket_start_at"],
                            report["bucket_end_at"],
                            sha,
                            _json(report),
                            report["status"],
                        ),
                    )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {
            "status": "BLOCKED_PROVISIONAL_BUCKET_PERSISTED",
            "bucket_key": key,
            "plan_sha": sha,
            "paper_admitted": False,
        }

    def first_eligible_quote_after(
        self,
        instrument: str,
        *,
        due_at: str,
        checked_at: str,
        max_wait_seconds: int = 10,
        max_book_age_seconds: int = 20,
    ) -> dict:
        """PIT-safe earliest received quote after deadline; never a future bar."""
        if not (0 < max_wait_seconds <= 60 and 0 < max_book_age_seconds <= 30):
            raise ValueError("PUBLIC_QUOTE_AGE_POLICY_INVALID")
        due, checked = clock(due_at), clock(checked_at)
        if checked < due:
            return {"status": "WAIT", "order_route": "NONE"}
        uri = "file:" + str(self.path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT payload,payload_sha FROM market_quote_receipts "
                "WHERE instrument=? AND known_at>=? AND known_at<=? "
                "ORDER BY known_at,seq LIMIT 1",
                (instrument, due.astimezone(UTC).isoformat(), checked.astimezone(UTC).isoformat()),
            ).fetchone()
        if row is None:
            return {"status": "BLOCKED_NO_POST_DEADLINE_QUOTE", "order_route": "NONE"}
        quote = json.loads(row[0])
        self.validate_market_quote(quote)
        if digest(quote) != row[1]:
            raise ValueError("PUBLIC_QUOTE_SHA_DIVERGENCE")
        quote_time = clock(quote["first_known_at"])
        if (quote_time - due).total_seconds() > max_wait_seconds or (
            quote_time - clock(quote["source_event_at"])
        ).total_seconds() > max_book_age_seconds:
            return {"status": "BLOCKED_STALE_OR_LATE_QUOTE", "order_route": "NONE"}
        return {
            "status": "QUOTE_OBSERVED_SCENARIO_ONLY",
            "quote": quote,
            "quote_sha": row[1],
            "actual_observed_at": quote["first_known_at"],
            "executed": False,
            "order_route": "NONE",
        }

    def restore(self, run_id: str) -> dict:
        with self._writer() as db:
            return self.verify(db, run_id)

    def backup(self, destination: Path) -> dict[str, str]:
        """Create one exclusive private SQLite online backup; never overwrite."""
        destination = Path(destination)
        if destination.resolve() == self.root.resolve():
            raise ValueError("PAPER_BACKUP_SELF_OVERWRITE")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        if destination.is_symlink() or destination.stat().st_mode & 0o077:
            raise ValueError("PAPER_BACKUP_DIRECTORY_NOT_PRIVATE")
        target = destination / "paper-events.sqlite3"
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
        os.close(fd)
        with self._writer() as source:
            with closing(sqlite3.connect(target)) as copied:
                source.backup(copied)
                if copied.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("PAPER_BACKUP_INTEGRITY_FAILED")
        recovered = PaperJournal(destination)
        with self._writer() as source:
            run_ids = [row[0] for row in source.execute("SELECT run_id FROM runs")]
            markets = [
                row[0] for row in source.execute("SELECT instrument FROM market_quote_heads")
            ]
            trade_markets = [
                row[0] for row in source.execute("SELECT instrument FROM market_trade_heads")
            ]
            source_ids = [
                row[0] for row in source.execute("SELECT DISTINCT source_id FROM source_receipts")
            ]
            observed_wallet_markets = [
                (row[0], row[1])
                for row in source.execute(
                    "SELECT wallet_key,instrument FROM public_wallet_trade_heads"
                )
            ]
            collateral_accounts = [
                row[0]
                for row in source.execute("SELECT DISTINCT account_sha FROM source_scope_receipts")
            ]
        for account_sha in collateral_accounts:
            original = self.collateral_scope_status(account_sha)
            copied = recovered.collateral_scope_status(account_sha)
            if original["head_sha"] != copied["head_sha"]:
                raise ValueError("PAPER_BACKUP_COLLATERAL_SCOPE_MISMATCH")
        for source_id in source_ids:
            original = self.source_status(source_id)
            copied = recovered.source_status(source_id)
            if original["head_sha"] != copied["head_sha"]:
                raise ValueError("PAPER_BACKUP_SOURCE_RECEIPT_MISMATCH")
        for wallet_key, instrument in observed_wallet_markets:
            original = self.audit_public_wallet_trade_tape(wallet_key, instrument)
            copied = recovered.audit_public_wallet_trade_tape(wallet_key, instrument)
            if original["head_sha"] != copied["head_sha"]:
                raise ValueError("PAPER_BACKUP_PUBLIC_WALLET_TRADE_MISMATCH")
        for market in trade_markets:
            original = self.market_trade_status(market)
            copied = recovered.market_trade_status(market)
            if original["head_sha"] != copied["head_sha"]:
                raise ValueError("PAPER_BACKUP_MARKET_TRADES_MISMATCH")
        for market in markets:
            original = self.market_quote_status(market)
            copied = recovered.market_quote_status(market)
            if original["journal_head_sha"] != copied["journal_head_sha"]:
                raise ValueError("PAPER_BACKUP_MARKET_QUOTE_MISMATCH")
        from .pm_forward_stream_journal import verify_streams

        if verify_streams(self.path)["head_sha"] != verify_streams(recovered.path)["head_sha"]:
            raise ValueError("PAPER_BACKUP_STREAM_CHECKPOINT_MISMATCH")
        return {run_id: recovered.restore(run_id)["journal_head_sha"] for run_id in run_ids}
