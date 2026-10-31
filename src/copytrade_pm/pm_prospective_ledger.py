"""Independent PM-01 receipt ledger; nothing here authorizes follower economics.

The ledger's first-known bound is the later of the producer's local receive
clock and the recorder's local ingest clock. Vendor event time is never a
signal clock. A recorded observation is *not* an audited outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "pm01_prospective_receipt_ledger_v1"
RECEIPT_SCHEMA = "pm01_hyperx_first_local_receipt_v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(obj: dict) -> str:
    return sha256(canonical(obj)).hexdigest()


def utc(value: str | datetime) -> datetime:
    obj = datetime.fromisoformat(value) if isinstance(value, str) else value
    if obj.tzinfo is None or obj.utcoffset() is None:
        raise ValueError("NAIVE_PROSPECTIVE_CLOCK")
    return obj.astimezone(UTC)


def _file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("INSECURE_PROSPECTIVE_FILE")


class ProspectiveLedger:
    """Sealed identity-bound receipt journal, independent of PM-03."""

    def __init__(
        self,
        root: Path,
        *,
        cohort: dict[str, str],
        cohort_manifest_sha: str,
        clock_source: Callable[[], datetime] | None = None,
        audit_public_key: bytes | None = None,
    ):
        if not cohort or not HEX64.fullmatch(cohort_manifest_sha):
            raise ValueError("INVALID_COHORT_PROVENANCE")
        if any(not alias or not HEX64.fullmatch(fp) for alias, fp in cohort.items()):
            raise ValueError("INVALID_COHORT_IDENTITY")
        if len(set(cohort.values())) != len(cohort):
            raise ValueError("DUPLICATED_SOURCE_WALLET_IDENTITY")
        if root.is_symlink():
            raise ValueError("SYMLINK_PROSPECTIVE_ROOT")
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if root.stat().st_mode & 0o077:
            raise ValueError("NONPRIVATE_PROSPECTIVE_ROOT")
        self.root = root
        self.clock_source = clock_source or (lambda: datetime.now(UTC))
        if audit_public_key is not None and len(audit_public_key) != 32:
            raise ValueError("INVALID_INDEPENDENT_AUDITOR_KEY")
        self.audit_public_key = audit_public_key
        self.manifest = {
            "schema": SCHEMA,
            "cohort": dict(sorted(cohort.items())),
            "cohort_manifest_sha": cohort_manifest_sha,
            "research_only": True,
            "auditor_public_key_sha256": (
                sha256(audit_public_key).hexdigest() if audit_public_key is not None else None
            ),
            "never_infer_prospective_from_vendor_time": True,
        }
        self.journal = root / "events.jsonl"
        self.lock = root / ".write.lock"
        self.manifest_file = root / "manifest.json"
        body = canonical(self.manifest) + b"\n"
        if self.manifest_file.exists():
            _file(self.manifest_file)
            if self.manifest_file.read_bytes() != body:
                raise ValueError("IMMUTABLE_COHORT_MANIFEST_CONFLICT")
        else:
            fd = os.open(
                self.manifest_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())

    @classmethod
    def open_existing(
        cls,
        root: Path,
        *,
        cohort: dict[str, str],
        cohort_manifest_sha: str,
        audit_public_key: bytes | None,
        clock_source: Callable[[], datetime] | None = None,
    ) -> ProspectiveLedger:
        """Read a frozen ledger without creating missing historical evidence."""
        if root.is_symlink() or not root.is_dir() or not (root / "manifest.json").is_file():
            raise ValueError("LEDGER_NOT_INITIALIZED")
        journal = cls(
            root,
            cohort=cohort,
            cohort_manifest_sha=cohort_manifest_sha,
            audit_public_key=audit_public_key,
            clock_source=clock_source,
        )
        journal.read()
        return journal

    def read(self) -> list[dict]:
        if not self.journal.exists():
            return []
        _file(self.journal)
        data = self.journal.read_bytes()
        if data and not data.endswith(b"\n"):
            raise ValueError("TRUNCATED_PROSPECTIVE_LEDGER")
        try:
            entries = [json.loads(x) for x in data.splitlines()]
        except (UnicodeError, ValueError) as exc:
            raise ValueError("CORRUPT_PROSPECTIVE_LEDGER") from exc
        previous = "0" * 64
        seen = set()
        last_recorded = None
        for seq, row in enumerate(entries, 1):
            payload = row["payload"]
            if (
                row["sequence"] != seq
                or row["previous_sha"] != previous
                or (
                    row["sha"]
                    != digest(
                        {
                            "sequence": seq,
                            "previous_sha": previous,
                            "kind": row["kind"],
                            "payload": payload,
                        }
                    )
                )
            ):
                raise ValueError("PROSPECTIVE_SHA_CHAIN_BROKEN")
            eid = (row["kind"], payload["event_id"])
            if eid in seen:
                raise ValueError("DUPLICATE_PROSPECTIVE_EVENT")
            seen.add(eid)
            recorded = utc(payload["recorded_at"])
            if last_recorded is not None and recorded < last_recorded:
                raise ValueError("REORDERED_PROSPECTIVE_CLOCK")
            last_recorded = recorded
            previous = row["sha"]
        known_receipts = {}
        known_audits = {}
        for row in entries:
            if row["kind"] == "RECEIPT":
                known_receipts[row["payload"]["event_id"]] = row
            elif row["kind"] == "AUDIT":
                audit = row["payload"]
                receipt = known_receipts.get(audit["event_id"])
                if receipt is None:
                    raise ValueError("AUDIT_WITHOUT_CAUSAL_RECEIPT")
                self._validate_audit(
                    audit["attestation"],
                    audit["signature_hex"],
                    receipt,
                    recorded_at=audit["recorded_at"],
                )
                known_audits[audit["event_id"]] = row
            elif row["kind"] == "OUTCOME":
                candidate = row["payload"]
                att = candidate["attestation"]
                receipt = known_receipts.get(att.get("source_event_id"))
                audit = known_audits.get(att.get("source_event_id"))
                if receipt is None or audit is None:
                    raise ValueError("UNMATCHED_OUTCOME_WITHOUT_AUDIT")
                self._validate_outcome(
                    att,
                    candidate["signature_hex"],
                    receipt,
                    audit,
                    recorded_at=candidate["recorded_at"],
                )
            else:
                raise ValueError("UNKNOWN_PROSPECTIVE_EVENT_KIND")
        return entries

    def _validate_audit(
        self, attestation: dict, signature_hex: str, receipt: dict, *, recorded_at: str
    ) -> None:
        if self.audit_public_key is None:
            raise ValueError("MISSING_INDEPENDENT_AUDIT_TRUST_ROOT")
        try:
            Ed25519PublicKey.from_public_bytes(self.audit_public_key).verify(
                bytes.fromhex(signature_hex), canonical(attestation)
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("INVALID_AUDIT_SIGNATURE") from exc
        first = receipt["payload"]
        if (
            attestation.get("schema") != "pm01_independent_receipt_audit_v1"
            or attestation.get("event_id") != first["event_id"]
            or attestation.get("raw_receipt_sha256") != first["raw_receipt_sha256"]
            or attestation.get("receipt_event_sha256") != receipt["sha"]
            or attestation.get("first_known_at") != first["first_known_at"]
        ):
            raise ValueError("AUDIT_RECEIPT_LINEAGE_MISMATCH")
        if (
            first["source_snapshot"]
            or first["source_stream"] != "HYPERX_DATA_API_WS_NOT_TRADING"
            or first["source_coverage"] != "PROSPECTIVE_RECEIPT_OBSERVED_BOOK_NOT_ATTESTED"
            or utc(first["source_event_at"]) > utc(first["locally_received_at"])
        ):
            raise ValueError("RECOVERED_OR_SNAPSHOT_NOT_VERIFIED")
        anchor = attestation.get("independent_clock_anchor_sha256")
        if (
            not isinstance(anchor, str)
            or not HEX64.fullmatch(anchor)
            or anchor in (receipt["sha"], first["raw_receipt_sha256"])
        ):
            raise ValueError("MISSING_INDEPENDENT_CLOCK_ANCHOR")
        if (
            attestation.get("auditor_role") != "INDEPENDENT_REVIEWER"
            or not attestation.get("auditor_id")
            or not attestation.get("clock_reconciled")
            or not attestation.get("continuity_reviewed")
        ):
            raise ValueError("UNVERIFIED_RECEIPT_CHAIN")
        audit_time = utc(attestation["audited_at"])
        if not utc(first["first_known_at"]) <= audit_time <= utc(recorded_at):
            raise ValueError("AUDIT_CLOCK_ORDER_VIOLATION")

    def audit_receipt(self, attestation: dict, signature_hex: str) -> str:
        rows = self.read()
        receipt = next(
            (
                x
                for x in rows
                if x["kind"] == "RECEIPT"
                and x["payload"]["event_id"] == attestation.get("event_id")
            ),
            None,
        )
        if receipt is None:
            raise ValueError("UNKNOWN_RECEIPT_AUDIT_TARGET")
        existing = next(
            (
                x
                for x in rows
                if x["kind"] == "AUDIT" and x["payload"]["event_id"] == attestation["event_id"]
            ),
            None,
        )
        if existing:
            if (
                existing["payload"]["attestation"] != attestation
                or existing["payload"]["signature_hex"] != signature_hex
            ):
                raise ValueError("CONFLICTING_INDEPENDENT_AUDIT")
            return existing["sha"]
        now = utc(self.clock_source()).isoformat()
        self._validate_audit(attestation, signature_hex, receipt, recorded_at=now)
        event = {
            "event_id": attestation["event_id"],
            "attestation": attestation,
            "signature_hex": signature_hex,
            "recorded_at": now,
        }
        return self._append("AUDIT", event)["row"]["sha"]

    def _validate_outcome(
        self, attestation: dict, signature_hex: str, receipt: dict, audit: dict, *, recorded_at: str
    ) -> None:
        if self.audit_public_key is None:
            raise ValueError("MISSING_INDEPENDENT_AUDIT_TRUST_ROOT")
        try:
            Ed25519PublicKey.from_public_bytes(self.audit_public_key).verify(
                bytes.fromhex(signature_hex), canonical(attestation)
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("INVALID_OUTCOME_SIGNATURE") from exc
        if (
            attestation.get("schema") != "pm02_independent_matched_outcome_v1"
            or attestation.get("receipt_audit_sha256") != audit["sha"]
            or attestation.get("source_event_id") != receipt["payload"]["event_id"]
            or not attestation.get("episode_id")
        ):
            raise ValueError("MATCHED_OUTCOME_LINEAGE_MISMATCH")
        for key in (
            "independent_source_digest",
            "market_source_digest",
            "follower_fill_evidence_sha256",
        ):
            value = attestation.get(key)
            if not isinstance(value, str) or not HEX64.fullmatch(value):
                raise ValueError("UNKNOWN_FOLLOWER_ECONOMICS")
        if (
            attestation.get("follower_economics_kind") != "AUDITED_MATCHED_FOLLOWER"
            or attestation.get("matched_control") is not True
            or attestation.get("source_conflict") is not False
            or attestation.get("missing_market") is not False
            or not isinstance(attestation.get("horizon_minutes"), int)
            or attestation["horizon_minutes"] not in (5, 15, 60)
        ):
            raise ValueError("UNKNOWN_FOLLOWER_ECONOMICS")
        exposure = attestation.get("signed_exposures_r")
        if (
            not isinstance(exposure, dict)
            or not exposure
            or any(not isinstance(k, str) or not k.startswith("hyperliquid:") for k in exposure)
        ):
            raise ValueError("UNKNOWN_SIGNED_EXPOSURES")
        for key in ("follower_net_r", "control_net_r", "tail_loss_r", "turnover_r"):
            try:
                x = Decimal(str(attestation[key]))
            except (InvalidOperation, KeyError) as exc:
                raise ValueError("UNKNOWN_FOLLOWER_ECONOMICS") from exc
            if not x.is_finite() or key in ("tail_loss_r", "turnover_r") and x < 0:
                raise ValueError("UNKNOWN_FOLLOWER_ECONOMICS")
        for x in exposure.values():
            try:
                if not Decimal(str(x)).is_finite():
                    raise ValueError("UNKNOWN_SIGNED_EXPOSURES")
            except InvalidOperation as exc:
                raise ValueError("UNKNOWN_SIGNED_EXPOSURES") from exc
        first = utc(receipt["payload"]["first_known_at"])
        decision = utc(attestation["decision_at"])
        outcome = utc(attestation["outcome_known_at"])
        reviewed = utc(attestation["audited_at"])
        # A later independent audit may verify an earlier sealed receipt;
        # it cannot move the original knowledge or decision clocks backward.
        if not first <= decision <= outcome <= reviewed <= utc(recorded_at):
            raise ValueError("OUTCOME_CLOCK_ORDER_VIOLATION")
        if outcome < decision + timedelta(minutes=attestation["horizon_minutes"]):
            raise ValueError("OUTCOME_HORIZON_NOT_MATURE")

    def record_matched_outcome(self, attestation: dict, signature_hex: str) -> str:
        rows = self.read()
        prior = next(
            (
                row
                for row in rows
                if row["kind"] == "OUTCOME"
                and row["payload"]["event_id"] == attestation.get("episode_id")
            ),
            None,
        )
        if prior:
            if (
                prior["payload"]["attestation"] != attestation
                or prior["payload"]["signature_hex"] != signature_hex
            ):
                raise ValueError("CONFLICTING_MATCHED_OUTCOME")
            return prior["sha"]
        receipt = next(
            (
                r
                for r in rows
                if r["kind"] == "RECEIPT"
                and r["payload"]["event_id"] == attestation.get("source_event_id")
            ),
            None,
        )
        audit = next(
            (
                r
                for r in rows
                if r["kind"] == "AUDIT"
                and r["payload"]["event_id"] == attestation.get("source_event_id")
            ),
            None,
        )
        if receipt is None or audit is None:
            raise ValueError("NO_INDEPENDENT_AUDITED_RECEIPT")
        now = utc(self.clock_source()).isoformat()
        self._validate_outcome(attestation, signature_hex, receipt, audit, recorded_at=now)
        record = {
            "event_id": attestation["episode_id"],
            "recorded_at": now,
            "attestation": attestation,
            "signature_hex": signature_hex,
        }
        return self._append("OUTCOME", record)["row"]["sha"]

    def _append(self, kind: str, payload: dict) -> dict:
        if self.lock.is_symlink():
            raise ValueError("UNSAFE_PROSPECTIVE_LOCK")
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            rows = self.read()
            prior = next(
                (
                    x
                    for x in rows
                    if x["kind"] == kind and x["payload"]["event_id"] == payload["event_id"]
                ),
                None,
            )
            if prior is not None:
                if prior["payload"] != payload:
                    # The first local receipt can never be rewritten after a reconnect.
                    raise ValueError("CONFLICTING_PROSPECTIVE_EVENT")
                return {"appended": False, "row": prior}
            when = utc(payload["recorded_at"])
            if rows and when < utc(rows[-1]["payload"]["recorded_at"]):
                raise ValueError("OUT_OF_ORDER_PROSPECTIVE_EVENT")
            previous = rows[-1]["sha"] if rows else "0" * 64
            row = {
                "sequence": len(rows) + 1,
                "previous_sha": previous,
                "kind": kind,
                "payload": payload,
            }
            row["sha"] = digest(row)
            blob = canonical(row) + b"\n"
            _file(self.journal) if self.journal.exists() else None
            wr = os.open(
                self.journal, os.O_APPEND | os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(wr, "ab", buffering=0) as stream:
                stream.write(blob)
                os.fsync(stream.fileno())
            return {"appended": True, "row": row}
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _receipt(self, path: Path, ingested_at: datetime) -> dict:
        _file(path)
        raw = path.read_bytes()
        if len(raw) > 20_000:
            raise ValueError("OVERSIZED_PRIVATE_RECEIPT")
        obj = json.loads(raw)
        if obj.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("UNSUPPORTED_RECEIPT_SCHEMA")
        wallet = obj["wallet"]
        if wallet not in self.manifest["cohort"] or (
            obj.get("source_identity_sha256") != self.manifest["cohort"][wallet]
        ):
            raise ValueError("COHORT_IDENTITY_MISMATCH")
        source_event_at = utc(obj["source_event_at"])
        local_at = utc(obj["locally_received_at"])
        if local_at > ingested_at + timedelta(seconds=1):
            raise ValueError("FUTURE_RECEIPT_CLOCK")
        if source_event_at > local_at + timedelta(seconds=5):
            raise ValueError("FUTURE_SOURCE_EVENT_CLOCK")
        if not obj.get("source_trade_id") or not str(obj["source_trade_id"]).isdigit():
            raise ValueError("INVALID_SOURCE_EVENT_ID")
        if obj.get("real_follower_order_sent") is not False or (
            obj.get("auto_promotion_authorized") is not False
        ):
            raise ValueError("RECEIPT_CANNOT_AUTHORIZE_TRADING")
        identity = {
            "wallet": wallet,
            "source_market": obj["source_market"],
            "source_trade_id": obj["source_trade_id"],
        }
        # The producer's original filename binds the underlying event identity.
        producer_identity = {
            "id": (
                obj["source_identity_sha256"],
                obj["source_market"],
                obj["source_trade_id"],
                obj["source_event_at"],
            )
        }
        expected_name = f"hyperx-observation-{digest(producer_identity)}.json"
        if path.name != expected_name:
            raise ValueError("RECEIPT_FILENAME_IDENTITY_MISMATCH")
        receipt_sha = sha256(raw).hexdigest()
        first_known = max(local_at, ingested_at)
        return {
            "event_id": digest(identity),
            "wallet": wallet,
            "source_identity_sha256": obj["source_identity_sha256"],
            "source_market": obj["source_market"],
            "source_trade_id": obj["source_trade_id"],
            "source_event_at": source_event_at.isoformat(),
            "locally_received_at": local_at.isoformat(),
            "first_known_at": first_known.isoformat(),
            "recorded_at": ingested_at.isoformat(),
            "source_stream": obj.get("stream_source"),
            "source_snapshot": obj.get("source_snapshot") is True,
            "source_coverage": obj.get("coverage"),
            "source_side": obj.get("source_side"),
            "source_fill_price": obj.get("source_fill_price"),
            "source_fill_quantity": obj.get("source_fill_quantity"),
            "raw_receipt_sha256": receipt_sha,
            "oracle_hindsight": False,
            "verified_first_known": False,
        }

    def ingest_folder(self, directory: Path) -> dict:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("UNSAFE_PRODUCER_RECEIPT_DIRECTORY")
        files = sorted(directory.glob("hyperx-observation-*.json"))
        now = utc(self.clock_source())
        ingested = 0
        for file in files:
            candidate = self._receipt(file, now)
            existing = next(
                (
                    entry
                    for entry in self.read()
                    if entry["kind"] == "RECEIPT"
                    and entry["payload"]["event_id"] == candidate["event_id"]
                ),
                None,
            )
            if existing:
                if existing["payload"]["raw_receipt_sha256"] != candidate["raw_receipt_sha256"]:
                    raise ValueError("CONFLICTING_SOURCE_EVENT_RECEIPT")
                continue
            ingested += int(self._append("RECEIPT", candidate)["appended"])
        return {
            "schema": "pm01_receipt_ingestion_v1",
            "ingested": ingested,
            "rejected": 0,
            "total_seen": len(files),
            "receipt_only_not_follower_economics": True,
            "ledger_head_sha256": self.read()[-1]["sha"] if self.read() else None,
        }

    @property
    def head_sha(self) -> str:
        records = self.read()
        return records[-1]["sha"] if records else "0" * 64

    def head_asof(self, asof: str) -> str:
        """PIT journal prefix: future attestations cannot enter an old decision hash."""
        t = utc(asof)
        known = [r for r in self.read() if utc(r["payload"]["recorded_at"]) <= t]
        return known[-1]["sha"] if known else "0" * 64

    def receipts_asof(self, asof: str) -> list[dict]:
        t = utc(asof)
        return [
            dict(row["payload"])
            for row in self.read()
            if row["kind"] == "RECEIPT" and utc(row["payload"]["first_known_at"]) <= t
        ]

    def pm02_rows_asof(self, asof: str) -> dict[str, list[dict]]:
        """Exact PM-02 consumer shape; only independently signed, as-of outcomes.

        The actual outcome-known time is the conservative ledger recording
        time, never the vendor's exchange event time.
        """
        t = utc(asof)
        rows = self.read()  # verifies all receipt/audit/outcome hashes and signatures
        receipts = {r["payload"]["event_id"]: r for r in rows if r["kind"] == "RECEIPT"}
        result: dict[str, list[dict]] = {}
        for row in rows:
            if row["kind"] != "OUTCOME" or utc(row["payload"]["recorded_at"]) > t:
                continue
            outcome = row["payload"]
            attestation = outcome["attestation"]
            receipt = receipts[attestation["source_event_id"]]["payload"]
            if utc(receipt["first_known_at"]) > t:
                continue
            wallet = receipt["wallet"]
            consumer = {
                "episode_id": attestation["episode_id"],
                "event_at": receipt["source_event_at"],
                "known_at": receipt["first_known_at"],
                "outcome_known_at": outcome["recorded_at"],
                "verified_first_known": True,
                "oracle_hindsight": False,
                "matched_control": True,
                "independent_source_digest": attestation["independent_source_digest"],
                "market_source_digest": attestation["market_source_digest"],
                "source_conflict": False,
                "missing_market": False,
                **{
                    key: attestation[key]
                    for key in (
                        "follower_net_r",
                        "control_net_r",
                        "tail_loss_r",
                        "turnover_r",
                        "signed_exposures_r",
                    )
                },
            }
            result.setdefault(wallet, []).append(consumer)
        return {
            k: sorted(v, key=lambda r: (r["event_at"], r["episode_id"]))
            for k, v in sorted(result.items())
        }
