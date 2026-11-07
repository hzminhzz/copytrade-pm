"""One-way operational evidence plane.

A publisher reads the existing DashboardReader on a bounded cadence and atomically
publishes a *presentation-only* snapshot. A consumer verifies the published
generation without opening ANY native registry, Guardian or broker interface.

The SHA256 detects torn/corrupted snapshots. It is NOT a signature of protected
financial authority; original reader/capture validation remains authoritative.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable


def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        return None
    return parsed.astimezone(UTC)


def safe_text(value: object, maximum: int) -> str | None:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        return None
    if re.search(r"0x[0-9a-fA-F]{40}", value):
        return None
    return value


def safe_decimal(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 42:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or abs(number.as_tuple().exponent) > 18:
        return None
    return value


SCHEMA = "copytrade_evidence_generation_v1"
PAYLOAD_SCHEMA = "grafana_account_risk_v1"
MAX_SIZE = 32_768
MAX_AGE_SECONDS = 45
METRICS = (
    "Guardian state",
    "Broker certainty",
    "Account equity",
    "Account headroom",
    "Daily headroom",
    "Trailing headroom",
    "Portfolio membership",
)
FINANCE = frozenset(METRICS[2:6])
GRADES = frozenset({"VERIFIED", "DEGRADED", "STALE", "BLOCKED", "UNKNOWN", "UNAVAILABLE"})


class EvidenceInvalid(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _safe_projection(value: dict) -> dict:
    """Validate a fixed public representation; fail closed on any unexpected data."""
    if value.get("schema") != PAYLOAD_SCHEMA or value.get("trading_authorized") is not False:
        raise EvidenceInvalid("BAD_PROJECTION_IDENTITY")
    if type(value.get("synthetic")) is not bool:
        raise EvidenceInvalid("MISSING_SYNTHETIC_FLAG")
    rows = value.get("metrics")
    if not isinstance(rows, list) or [x.get("metric") for x in rows if isinstance(x, dict)] != list(
        METRICS
    ):
        raise EvidenceInvalid("METRIC_SCOPE_INVALID")
    if len(rows) != len(METRICS):
        raise EvidenceInvalid("METRIC_COUNT_INVALID")
    clean = []
    for entry in rows:
        if not isinstance(entry, dict) or entry.get("grade") not in GRADES:
            raise EvidenceInvalid("METRIC_GRADE_INVALID")
        metric = entry["metric"]
        value_text = entry.get("value")
        grade = entry["grade"]
        if metric in FINANCE:
            if value_text is not None and (
                not isinstance(value_text, str) or safe_decimal(value_text) != value_text
            ):
                raise EvidenceInvalid("INVALID_DECIMAL")
            if grade != "VERIFIED" and value_text is not None:
                # Stale snapshots are allowed to carry past verified numbers only
                # through the consumer downgrade path, never at publication.
                raise EvidenceInvalid("FINANCE_VALUE_WITHOUT_VERIFICATION")
        elif value_text is not None:
            if safe_text(value_text, 96) != value_text:
                raise EvidenceInvalid("UNSAFE_NONFINANCIAL_VALUE")
        if grade == "VERIFIED" and metric in FINANCE and value_text is None:
            raise EvidenceInvalid("VERIFIED_MISSING_FINANCE")
        authority = entry.get("authority")
        if not isinstance(authority, str) or safe_text(authority, 100) != authority:
            raise EvidenceInvalid("INVALID_AUTHORITY")
        observed = entry.get("source_observed_at")
        captured = entry.get("captured_at")
        retrieved = entry.get("retrieved_at")
        if any(t is not None and parse_utc(t) is None for t in (observed, captured, retrieved)):
            raise EvidenceInvalid("INVALID_SOURCE_CLOCK")
        if grade == "VERIFIED" and observed is None:
            raise EvidenceInvalid("VERIFIED_WITHOUT_OBSERVATION")
        seq = entry.get("journal_sequence")
        if seq is not None and (type(seq) is not int or seq < 0):
            raise EvidenceInvalid("INVALID_SEQUENCE")
        revision = entry.get("revision")
        if revision is not None and (
            not isinstance(revision, str) or not re.fullmatch("[0-9a-f]{64}", revision)
        ):
            raise EvidenceInvalid("INVALID_REVISION")
        binding = entry.get("account_binding_sha")
        if binding is not None and (
            not isinstance(binding, str) or not re.fullmatch("[0-9a-f]{64}", binding)
        ):
            raise EvidenceInvalid("INVALID_ACCOUNT_BINDING")
        error = entry.get("evidence_error")
        if error is not None and safe_text(error, 128) != error:
            raise EvidenceInvalid("INVALID_EVIDENCE_ERROR")
        clean.append(
            {
                "metric": metric,
                "value": value_text,
                "grade": grade,
                "authority": authority,
                "source_observed_at": observed,
                "captured_at": captured,
                "retrieved_at": retrieved,
                "revision": revision,
                "journal_sequence": seq,
                "account_binding_sha": binding,
                "evidence_error": error,
            }
        )
    incidents = value.get("incidents", [])
    if not isinstance(incidents, list) or len(incidents) > 40:
        raise EvidenceInvalid("INCIDENT_SCOPE_INVALID")
    safe_incidents = []
    for incident in incidents:
        if not isinstance(incident, dict) or safe_text(incident.get("code"), 96) != incident.get(
            "code"
        ):
            raise EvidenceInvalid("INVALID_INCIDENT")
        safe_incidents.append({"code": incident["code"], "priority": "REPORTED"})
    observed = parse_utc(value.get("generated_at"))
    if observed is None:
        raise EvidenceInvalid("INVALID_GENERATED_CLOCK")
    for entry in clean:
        first = parse_utc(entry["source_observed_at"]) if entry["source_observed_at"] else None
        captured = parse_utc(entry["captured_at"]) if entry["captured_at"] else None
        retrieved = parse_utc(entry["retrieved_at"]) if entry["retrieved_at"] else None
        if any(t is not None and t > observed for t in (first, captured, retrieved)):
            raise EvidenceInvalid("FUTURE_SOURCE_CLOCK")
        if first is not None and captured is not None and first > captured:
            raise EvidenceInvalid("REGRESSED_SOURCE_CLOCK")
    verified_finance = [
        entry for entry in clean if entry["metric"] in FINANCE and entry["grade"] == "VERIFIED"
    ]
    if verified_finance:
        reference = clean[0]
        broker = clean[1]

        def identity(row):
            return (
                row["account_binding_sha"],
                row["revision"],
                row["journal_sequence"],
                row["captured_at"],
            )

        if (
            reference["grade"] != "VERIFIED"
            or broker["grade"] != "VERIFIED"
            or not reference["account_binding_sha"]
            or not reference["revision"]
            or not reference["captured_at"]
            or identity(reference) != identity(broker)
            or any(identity(entry) != identity(reference) for entry in verified_finance)
        ):
            raise EvidenceInvalid("UNBOUND_FINANCIAL_BOOK")
    history = value.get("history")
    if history is not None and not value["synthetic"]:
        raise EvidenceInvalid("LIVE_HISTORY_UNSUPPORTED")
    if value["synthetic"]:
        if not isinstance(history, list) or not 1 <= len(history) <= 10:
            raise EvidenceInvalid("FIXTURE_HISTORY_INVALID")
        for item in history:
            if (
                not isinstance(item, dict)
                or item.get("grade") not in GRADES
                or parse_utc(item.get("time")) is None
                or parse_utc(item["time"]) > observed
                or item.get("source") != "SYNTHETIC_ONLY"
            ):
                raise EvidenceInvalid("FIXTURE_HISTORY_INVALID")
    return {
        **({"history": history} if value["synthetic"] else {}),
        "schema": PAYLOAD_SCHEMA,
        "generated_at": value["generated_at"],
        "coverage": "VERIFIED" if all(r["grade"] == "VERIFIED" for r in clean) else "INCOMPLETE",
        "synthetic": value["synthetic"],
        "trading_authorized": False,
        "metrics": clean,
        "incidents": safe_incidents,
        "evidence_note": (
            "SYNTHETIC FIXTURE - NOT LIVE TRADING OR FINANCE"
            if value["synthetic"]
            else "Only published source evidence; no viewer-side financial authority."
        ),
    }


def encode_generation(projection: dict, *, now: datetime | None = None) -> bytes:
    now = now or _utc_now()
    if now.tzinfo is None or now.utcoffset().total_seconds() != 0:
        raise EvidenceInvalid("NON_UTC_PUBLISH_CLOCK")
    sanitized = _safe_projection(projection)
    if parse_utc(sanitized["generated_at"]) > now:
        raise EvidenceInvalid("FUTURE_READ_CLOCK")
    document = {
        "schema": SCHEMA,
        "published_at": now.isoformat(),
        "max_age_seconds": MAX_AGE_SECONDS,
        "projection": sanitized,
    }
    document["generation_sha256"] = sha256(_canonical(document)).hexdigest()
    result = _canonical(document)
    if len(result) > MAX_SIZE:
        raise EvidenceInvalid("PUBLISHED_EVIDENCE_TOO_LARGE")
    return result


def publish_atomic(directory: Path, payload: bytes, *, name: str = "account-risk.json") -> None:
    """Only the publisher has a writable mount; committed snapshots replace atomically."""
    if name not in {"account-risk.json", "fixture-states.json"}:
        raise EvidenceInvalid("UNAPPROVED_OUTPUT_NAME")
    if len(payload) > MAX_SIZE:
        raise EvidenceInvalid("PUBLISHED_EVIDENCE_TOO_LARGE")
    directory.mkdir(parents=True, exist_ok=True, mode=0o755)
    # Do not follow replacement symlinks and never name temp files from client input.
    temp = directory / f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, directory / name)
        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        temp.unlink(missing_ok=True)


def read_generation(
    directory: Path, *, name: str = "account-risk.json", now: datetime | None = None
) -> dict:
    """Snapshot-only read: no DashboardReader/native imports or filesystem paths from HTTP."""
    if name not in {"account-risk.json", "fixture-states.json"}:
        raise EvidenceInvalid("UNAPPROVED_READ_NAME")
    now = now or _utc_now()
    path = directory / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise EvidenceInvalid("EVIDENCE_UNAVAILABLE") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or not (0 < file_stat.st_size <= MAX_SIZE):
            raise EvidenceInvalid("INVALID_SNAPSHOT_FILE")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_SIZE + 1)
        if len(raw) != file_stat.st_size:
            raise EvidenceInvalid("SNAPSHOT_CHANGED")
    finally:
        os.close(fd)
    try:
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise EvidenceInvalid("INVALID_SNAPSHOT_DOCUMENT")
        digest = document.pop("generation_sha256", None)
        if not isinstance(digest, str) or sha256(_canonical(document)).hexdigest() != digest:
            raise EvidenceInvalid("SNAPSHOT_HASH_MISMATCH")
        if document.get("schema") != SCHEMA or document.get("max_age_seconds") != MAX_AGE_SECONDS:
            raise EvidenceInvalid("SNAPSHOT_SCHEMA_MISMATCH")
        published = parse_utc(document.get("published_at"))
        if published is None or published > now:
            raise EvidenceInvalid("SNAPSHOT_CLOCK_INVALID")
        projection = _safe_projection(document["projection"])
        if projection["synthetic"] != (name == "fixture-states.json"):
            raise EvidenceInvalid("FIXTURE_LIVE_BOUNDARY")
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise EvidenceInvalid("EVIDENCE_CORRUPT") from exc

    # Derive freshness from the publication clock, never from HTTP refresh.
    age = (now - published).total_seconds()
    observed_ages = [
        (now - parse_utc(r["source_observed_at"])).total_seconds()
        for r in projection["metrics"]
        if r["grade"] == "VERIFIED" and r["source_observed_at"] is not None
    ]
    stale = age > MAX_AGE_SECONDS or any(x > MAX_AGE_SECONDS for x in observed_ages)
    if stale:
        for row in projection["metrics"]:
            if row["grade"] == "VERIFIED":
                row["grade"] = "STALE"
                row["evidence_error"] = "EVIDENCE_AGE_EXCEEDED"
        projection["coverage"] = "INCOMPLETE"
        projection["evidence_note"] = "STALE PUBLISHED EVIDENCE - DO NOT INFER LIVE RISK"
    projection["published_at"] = published.isoformat()
    projection["publication_age_seconds"] = round(age, 2)
    projection["generation_sha256"] = digest
    return projection


def no_evidence(reason: str, now: datetime | None = None) -> dict:
    """Fail-closed error projection: never return fictitious healthy numeric data."""
    now = now or _utc_now()
    if reason not in {"EVIDENCE_UNAVAILABLE", "EVIDENCE_CORRUPT", "PUBLISHER_FAILED"}:
        reason = "EVIDENCE_CORRUPT"
    return {
        "schema": PAYLOAD_SCHEMA,
        "generated_at": now.isoformat(),
        "published_at": None,
        "publication_age_seconds": None,
        "generation_sha256": None,
        "coverage": "INCOMPLETE",
        "synthetic": False,
        "trading_authorized": False,
        "metrics": [
            {
                "metric": m,
                "value": None,
                "grade": "UNAVAILABLE" if reason == "EVIDENCE_UNAVAILABLE" else "BLOCKED",
                "authority": "operational-evidence-plane",
                "source_observed_at": None,
                "captured_at": None,
                "retrieved_at": now.isoformat(),
                "revision": None,
                "journal_sequence": None,
                "account_binding_sha": None,
                "evidence_error": reason,
            }
            for m in METRICS
        ],
        "incidents": [{"code": reason, "priority": "REPORTED"}],
        "evidence_note": reason + " - NO VERIFIED FINANCE",
    }


def fixture_projection(*, now: datetime | None = None) -> dict:
    """Explicitly synthetic, QA-only display matrix. Never an observed account."""
    now = now or _utc_now()
    base = no_evidence("EVIDENCE_UNAVAILABLE", now=now)
    rows = base["metrics"]
    identities = {
        "authority": "synthetic_fixture.NEVER_LIVE",
        "source_observed_at": now.isoformat(),
        "captured_at": now.isoformat(),
        "retrieved_at": now.isoformat(),
        "revision": "f" * 64,
        "journal_sequence": 0,
        "account_binding_sha": "d" * 64,
    }
    for index, (grade, value) in enumerate(
        (
            ("VERIFIED", "HALTED"),
            ("VERIFIED", "RECONCILED"),
            ("VERIFIED", "0"),
            ("STALE", None),
            ("BLOCKED", None),
            ("UNAVAILABLE", None),
            ("UNKNOWN", None),
        )
    ):
        rows[index].update(
            grade=grade,
            value=value,
            evidence_error=None if grade == "VERIFIED" else "SYNTHETIC_" + grade,
            **identities,
        )
    base.update(
        synthetic=True,
        generated_at=now.isoformat(),
        incidents=[{"code": "SYNTHETIC_BROKER_STALE", "priority": "REPORTED"}],
        history=[
            {
                "time": (now - timedelta(seconds=60 - i * 15)).isoformat(),
                "grade": grade,
                "source": "SYNTHETIC_ONLY",
            }
            for i, grade in enumerate(("VERIFIED", "UNKNOWN", "STALE", "BLOCKED", "UNAVAILABLE"))
        ],
        evidence_note="SYNTHETIC FIXTURE - NOT LIVE TRADING OR FINANCE",
    )
    return base


def publish_once(
    directory: Path, reader=None, *, clock: Callable[[], datetime] = _utc_now
) -> bytes:
    from .adapter import DashboardReader
    from .grafana_projection import build_projection

    trusted_reader = reader if reader is not None else DashboardReader()
    result = build_projection(trusted_reader)
    payload = encode_generation(result, now=clock())
    publish_atomic(directory, payload)
    return payload


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Single-writer evidence publisher; no trading calls"
    )
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 5 <= args.interval <= 60:
        parser.error("interval must be 5..60 seconds")
    while True:
        try:
            publish_once(args.dir)
            fixture = encode_generation(fixture_projection(), now=_utc_now())
            publish_atomic(args.dir, fixture, name="fixture-states.json")
        except Exception as exc:
            # A failed publisher leaves the prior generation visibly STALE.
            print(f"EVIDENCE_PUBLICATION_FAILED:{type(exc).__name__}", flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
