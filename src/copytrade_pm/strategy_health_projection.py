"""Bounded, aggregate-only strategy health projection (never imports finance owners)."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

SCHEMA = "strategy_health_grafana_v1"
NAME = "strategy-health.json"
MAX_SIZE = 131072
MAX_AGE_SECONDS = 900


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def project(assessment, *, published_at: datetime) -> bytes:
    """Allowlist only aggregate counters. Never serialize strategy identity or source SHA."""
    if published_at.tzinfo is None or published_at.utcoffset() != timedelta(0):
        raise ValueError("STRATEGY_PROJECTION_UTC")
    if not assessment.report_sha256 or assessment.report_sha256 == "0" * 64:
        raise ValueError("STRATEGY_REPORT_UNSEALED")
    from .strategy_health import canonical_report

    canonical_report(assessment)
    if published_at < assessment.as_of:
        raise ValueError("PROJECTION_BEFORE_ASSESSMENT")
    counts = {}
    for item in assessment.opportunities:
        counts[item.state] = counts.get(item.state, 0) + 1
    data = {
        "schema": SCHEMA,
        "published_at": published_at.isoformat(),
        "as_of": assessment.as_of.isoformat(),
        "read_only": True,
        "trading_authorized": False,
        "source_availability": assessment.source_observability,
        "opportunity_count": len(assessment.opportunities),
        "opportunity_states": counts,
        "unknown_gap_intervals": len(assessment.missing_intervals),
        "follower_net_comparable": assessment.follower_economics.net_comparable,
        "portfolio_contribution_status": assessment.portfolio_contribution.status,
        "warning_class": (
            "UNCALIBRATED_ADVISORY"
            if assessment.advisory.status in {"EARLY_WARNING", "PERSISTENT_WARNING"}
            else "UNKNOWN"
        ),
        "economic_advisory_status": assessment.advisory.status,
        "last_dated_warning": (
            assessment.advisory.last_warning_at.isoformat()
            if assessment.advisory.last_warning_at is not None
            else None
        ),
        "assessability": (
            "INSUFFICIENT_EVIDENCE"
            if assessment.advisory.current_assessability == "UNKNOWN"
            else assessment.advisory.current_assessability
        ),
        "operational_incident_count": len(assessment.operational_incidents),
        "operational_priority": (
            "CRITICAL_RISK_EXPOSED"
            if any(x.priority == "CRITICAL_RISK_EXPOSED" for x in assessment.operational_incidents)
            else "ELEVATED"
            if any(x.priority == "ELEVATED" for x in assessment.operational_incidents)
            else "OBSERVATION"
            if assessment.operational_incidents
            else "NONE"
        ),
        "evidence_class": assessment.follower_economics.evidence_class,
        "provisional_thresholds": True,
        "synthetic": assessment.follower_economics.evidence_class == "RESEARCH_SYNTHETIC",
    }
    data["generation_sha256"] = sha256(canonical(data)).hexdigest()
    payload = canonical(data)
    if len(payload) > MAX_SIZE:
        raise ValueError("STRATEGY_PROJECTION_TOO_LARGE")
    return payload


def publish(directory: Path, payload: bytes) -> None:
    from .pm_private_io import publish_atomic_public

    data = _validate(payload)
    if data["schema"] != SCHEMA:
        raise ValueError("STRATEGY_PROJECTION_SCHEMA")
    publish_atomic_public(directory, payload, name=NAME)
    path = directory / NAME
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(payload):
            raise ValueError("STRATEGY_PROJECTION_FILE_INVALID")
        if os.read(fd, MAX_SIZE + 1) != payload:
            raise ValueError("STRATEGY_PROJECTION_CHECKSUM")
        os.fchmod(fd, 0o644)
    finally:
        os.close(fd)


def _validate(raw: bytes) -> dict:
    if not 0 < len(raw) <= MAX_SIZE:
        raise ValueError("STRATEGY_PROJECTION_SIZE")
    obj = json.loads(raw)
    keys = {
        "schema",
        "published_at",
        "as_of",
        "read_only",
        "trading_authorized",
        "source_availability",
        "opportunity_count",
        "opportunity_states",
        "unknown_gap_intervals",
        "follower_net_comparable",
        "portfolio_contribution_status",
        "warning_class",
        "last_dated_warning",
        "assessability",
        "provisional_thresholds",
        "synthetic",
        "evidence_class",
        "economic_advisory_status",
        "operational_incident_count",
        "operational_priority",
    }
    if not isinstance(obj, dict) or set(obj) != keys | {"generation_sha256"}:
        raise ValueError("STRATEGY_PROJECTION_UNAPPROVED_FIELD")
    sha = obj.pop("generation_sha256")
    if not isinstance(sha, str) or sha != sha256(canonical(obj)).hexdigest():
        raise ValueError("STRATEGY_PROJECTION_HASH_INVALID")
    if (
        obj["schema"] != SCHEMA
        or obj["read_only"] is not True
        or obj["trading_authorized"] is not False
    ):
        raise ValueError("STRATEGY_PROJECTION_UNSAFE")
    if (
        obj["evidence_class"]
        not in {"UNKNOWN", "RESEARCH_SYNTHETIC", "PROSPECTIVE_SHADOW", "AUTHENTIC_BROKER"}
        or type(obj["synthetic"]) is not bool
        or obj["synthetic"] != (obj["evidence_class"] == "RESEARCH_SYNTHETIC")
        or obj["provisional_thresholds"] is not True
    ):
        raise ValueError("STRATEGY_PROJECTION_CLASS")
    if obj["source_availability"] not in {
        "UNKNOWN",
        "VERIFIED_CONTINUOUS",
        "GAP",
        "INCOMPLETE_SCOPE",
        "STALE",
    }:
        raise ValueError("STRATEGY_SOURCE_STATE")
    if obj["warning_class"] not in {"UNKNOWN", "UNCALIBRATED_ADVISORY"}:
        raise ValueError("STRATEGY_WARNING_STATE")
    if obj["economic_advisory_status"] not in {
        "INSUFFICIENT_EVIDENCE",
        "NONE",
        "EARLY_WARNING",
        "PERSISTENT_WARNING",
    }:
        raise ValueError("STRATEGY_ADVISORY_INVALID")
    if obj["assessability"] not in {
        "UNKNOWN",
        "STALE",
        "INSUFFICIENT_EVIDENCE",
        "PROVISIONAL_LOOK_AVAILABLE",
        "INSUFFICIENT_EVIDENCE_FOR_WARNING_CLEARANCE",
    }:
        raise ValueError("STRATEGY_WARNING_ASSESSABILITY_INVALID")
    if obj["last_dated_warning"] is not None:
        at = datetime.fromisoformat(obj["last_dated_warning"].replace("Z", "+00:00"))
        if at.tzinfo is None or at.utcoffset() != timedelta(0):
            raise ValueError("STRATEGY_WARNING_CLOCK_INVALID")
    if (
        obj["operational_priority"]
        not in {"NONE", "OBSERVATION", "ELEVATED", "CRITICAL_RISK_EXPOSED"}
        or type(obj["operational_incident_count"]) is not int
        or not 0 <= obj["operational_incident_count"] <= 512
    ):
        raise ValueError("STRATEGY_OPERATIONS_INVALID")
    if bool(obj["operational_incident_count"]) != (obj["operational_priority"] != "NONE"):
        raise ValueError("STRATEGY_OPERATIONS_COUNT_INVALID")
    if obj["portfolio_contribution_status"] not in {
        "UNKNOWN",
        "SYNTHETIC_COMPARISON",
        "VERIFIED_PROSPECTIVE",
    }:
        raise ValueError("STRATEGY_MARGINAL_STATE")
    if type(obj["follower_net_comparable"]) is not bool:
        raise ValueError("STRATEGY_FOLLOWER_STATE")
    if any(
        type(obj[k]) is not int or not 0 <= obj[k] <= 10000
        for k in ("opportunity_count", "unknown_gap_intervals")
    ):
        raise ValueError("STRATEGY_BAD_COUNTER")
    if (
        not isinstance(obj["opportunity_states"], dict)
        or any(
            k
            not in {
                "OBSERVED",
                "PENDING",
                "ADMITTED",
                "REJECTED",
                "EXPIRED",
                "CANCELED",
                "OPEN",
                "PARTIAL",
                "UNRESOLVED",
                "REALIZED",
            }
            or type(v) is not int
            or not 0 <= v <= 10000
            for k, v in obj["opportunity_states"].items()
        )
        or sum(obj["opportunity_states"].values()) != obj["opportunity_count"]
    ):
        raise ValueError("STRATEGY_STATE_COUNTS")
    for key in ("published_at", "as_of"):
        dt = datetime.fromisoformat(obj[key].replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError("STRATEGY_PROJECTION_UTC")
    if datetime.fromisoformat(obj["as_of"]) > datetime.fromisoformat(obj["published_at"]):
        raise ValueError("STRATEGY_PROJECTION_TIME_ORDER")
    if canonical({**obj, "generation_sha256": sha}) != raw:
        raise ValueError("STRATEGY_PROJECTION_NONCANONICAL")
    obj["generation_sha256"] = sha
    return obj


def read(directory: Path, *, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("STRATEGY_PROJECTION_UTC")
    path = directory / NAME
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SIZE:
            raise ValueError("STRATEGY_PROJECTION_FILE_INVALID")
        raw = os.read(fd, MAX_SIZE + 1)
        if len(raw) != info.st_size:
            raise ValueError("STRATEGY_PROJECTION_TRUNCATED")
    finally:
        os.close(fd)
    data = _validate(raw)
    age = (now - datetime.fromisoformat(data["published_at"])).total_seconds()
    if age < 0 or age > MAX_AGE_SECONDS:
        raise ValueError("STRATEGY_PROJECTION_STALE")
    data["publication_age_seconds"] = age
    return data
