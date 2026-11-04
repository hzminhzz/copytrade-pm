"""Private, durable forward-paper account-event journal (FP-02).

Financial transitions are made exclusively with PM-03 Account methods. There is
no exchange transport or shared registry database.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from .pm03_account import Account, RiskState, Rulebook, clock, digest, number
from .pm_forward_paper import PaperManifest


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
        os.chmod(self.path, 0o600)

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            db = sqlite3.connect(self.path, timeout=0, isolation_level=None)
            try:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA foreign_keys=ON")
                yield db
            finally:
                db.close()
        except (BlockingIOError, sqlite3.OperationalError) as exc:
            raise ValueError("PAPER_JOURNAL_BUSY_OR_UNAVAILABLE") from exc
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _apply(account: Account, event: dict) -> dict:
        kind = event.get("kind")
        if kind == "HALT":
            account.risk = RiskState.HALT
            account.halt_reason = event.get("reason") or "PAPER_OPERATOR_HALT"
            return {"status": "HALT_LATCHED"}
        if kind == "MARK":
            if not event.get("state_known", False):
                account.risk = RiskState.HALT
                account.halt_reason = "UNKNOWN_PAPER_MARK"
                return {"status": "HALT_UNKNOWN_MARK"}
            from .pm03_account import Instrument

            account.mark(
                {Instrument.parse(k): number(v) for k, v in event["prices"].items()},
                event["event_at"],
            )
            account.verify()
            return {"status": "MARKED"}
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
            )
            if not admission.admitted:
                account.risk = RiskState.RED
                account.risk_reasons = admission.reason_codes
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
                account.risk = RiskState.HALT
                account.halt_reason = "MISSING_EXISTING_POSITION_MARK"
                return {"status": "BLOCKED", "reason": account.halt_reason}
            if any(not q.supported or q.volume_base is None for q in obs.values()):
                account.risk = RiskState.RED
                return {"status": "BLOCKED", "reason": "INCOMPLETE_MARKET"}
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
                permitted=decision["approved_new_risk"],
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

    def append(self, run_id: str, event_id: str, event: dict) -> dict:
        if not event_id or len(event_id) > 128:
            raise ValueError("INVALID_PAPER_EVENT_ID")
        if not isinstance(event, dict) or not isinstance(event.get("event_at"), str):
            raise ValueError("INVALID_PAPER_EVENT")
        clock(event["event_at"])
        input_sha = digest(event)
        with self._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._verify(db, run_id)
                old = db.execute(
                    "SELECT input_sha FROM events WHERE run_id=? AND event_id=?",
                    (run_id, event_id),
                ).fetchone()
                if old:
                    if old[0] != input_sha:
                        raise ValueError("CONFLICTING_PAPER_EVENT")
                    db.execute("COMMIT")
                    return self._verify(db, run_id)
                row = db.execute(
                    "SELECT manifest,snapshot,last_event_at,cursor,snapshot_sha FROM runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("UNKNOWN_PAPER_RUN")
                manifest, snapshot, last_at, cursor, prior_sha = row
                if clock(event["event_at"]) < clock(last_at):
                    raise ValueError("PAPER_EVENT_OUT_OF_ORDER")
                rulebook = Rulebook.from_dict(json.loads(manifest)["rulebook"])
                account = Account.from_snapshot(rulebook, json.loads(snapshot))
                self._apply(account, event)
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
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.restore(run_id)

    def _verify(self, db: sqlite3.Connection, run_id: str) -> dict:
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
        rows = db.execute(
            "SELECT seq,event_id,event_at,input,input_sha,prior_sha,post_sha,chain_sha "
            "FROM events WHERE run_id=? ORDER BY seq",
            (run_id,),
        ).fetchall()
        for expected_seq, entry in enumerate(rows, 1):
            seq, event_id, at, payload, input_sha, before, after, chain_sha = entry
            event = json.loads(payload)
            if (
                seq != expected_seq
                or event.get("event_at") != at
                or digest(event) != input_sha
                or before != prior_sha
                or clock(at) < clock(prior_at)
            ):
                raise ValueError("PAPER_JOURNAL_DIVERGENCE")
            last_result = self._apply(account, event)
            expected_post = digest(account.snapshot())
            if after != expected_post or chain_sha != digest(
                [run_id, seq, event_id, input_sha, before, after]
            ):
                raise ValueError("PAPER_JOURNAL_DIVERGENCE")
            prior_sha = after
            prior_at = at
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
        }

    def append_source_receipt(
        self, source_id: str, sequence: int, receipt_id: str, receipt: dict
    ) -> dict:
        """Import one already-captured receipt, never create a subscription."""
        if (
            not source_id
            or not receipt_id
            or not isinstance(sequence, int)
            or sequence <= 0
            or len(source_id) > 128
            or len(receipt_id) > 128
        ):
            raise ValueError("INVALID_SOURCE_RECEIPT_IDENTITY")
        if receipt.get("schema") != "paper_first_known_source_v1":
            raise ValueError("UNKNOWN_SOURCE_RECEIPT_SCHEMA")
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
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return self.source_status(source_id)

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

    def restore(self, run_id: str) -> dict:
        with self._writer() as db:
            return self._verify(db, run_id)

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
        return {run_id: recovered.restore(run_id)["journal_head_sha"] for run_id in run_ids}
