"""Redacted, bounded health view derived from a validated immutable report.

The gateway reads only this publisher-produced snapshot; no registry import.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import os
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .wallet_health import HealthReport


def canonical(value: object) -> bytes:
    # Keep the Docker projection process stdlib-only, independent of the
    # private registry, Pydantic models, providers and financial sources.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


SCHEMA = "wallet_health_grafana_v1"
MAX_SIZE = 131072


def project(report: HealthReport, *, published_at: datetime) -> bytes:
    if published_at.tzinfo is None or published_at.utcoffset() != timedelta(0):
        raise ValueError("UTC_PUBLISH_REQUIRED")
    counts: dict[str, int] = {}
    rows = []
    for finding in report.findings:
        counts[finding.recommendation] = counts.get(finding.recommendation, 0) + 1
        rows.append(
            {
                "wallet_ref": sha256(
                    (report.registry_asof_identity_sha256 + ":" + str(finding.wallet_id)).encode()
                ).hexdigest()[:16],
                "eligibility": finding.eligibility,
                "source": finding.source_integrity,
                "capital": finding.capital_attribution,
                "activity": finding.activity,
                "edge": finding.edge,
                "copyability": finding.copyability,
                "portfolio_contribution": finding.portfolio_contribution,
                "recommendation": finding.recommendation,
                "evidence_count": len(finding.evidence_hashes),
            }
        )
    data = {
        "schema": SCHEMA,
        "as_of": report.as_of.isoformat(),
        "published_at": published_at.isoformat(),
        "source_sha256": sha256(canonical(report.model_dump(mode="json"))).hexdigest(),
        "synthetic": report.synthetic,
        "trading_authorized": False,
        "wallet_count": len(rows),
        "alert_counts": counts,
        "wallets": rows,
    }
    data["generation_sha256"] = sha256(canonical(data)).hexdigest()
    raw = canonical(data)
    if len(raw) > MAX_SIZE:
        raise ValueError("HEALTH_PROJECTION_TOO_LARGE")
    return raw


def publish(directory: Path, payload: bytes) -> None:
    """Use existing hash-checked, atomic publisher without modifying its gateway."""
    from .dashboard.evidence_plane import publish_atomic

    # This name is deliberately a separate publisher-authorized projection.
    publish_atomic(directory, payload, name="wallet-health.json")


def read(directory: Path, *, now: datetime) -> dict:
    """Fixed name, no symlink, bounded size, SHA and schema verification."""
    now = now.astimezone(UTC)
    fd = os.open(directory / "wallet-health.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size > MAX_SIZE or s.st_size == 0:
            raise ValueError("INVALID_HEALTH_PUBLICATION")
        raw = os.read(fd, MAX_SIZE + 1)
        if len(raw) != s.st_size:
            raise ValueError("TRUNCATED_HEALTH_PUBLICATION")
    finally:
        os.close(fd)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("INVALID_HEALTH_PUBLICATION_TYPE")
    digest = data.pop("generation_sha256", None)
    if set(data) != {
        "schema",
        "as_of",
        "published_at",
        "source_sha256",
        "synthetic",
        "trading_authorized",
        "wallet_count",
        "alert_counts",
        "wallets",
    }:
        raise ValueError("UNAPPROVED_HEALTH_PUBLICATION_FIELD")
    if not isinstance(digest, str) or digest != sha256(canonical(data)).hexdigest():
        raise ValueError("HEALTH_HASH_INVALID")
    if data.get("schema") != SCHEMA or data.get("trading_authorized") is not False:
        raise ValueError("HEALTH_SCHEMA_INVALID")
    published = datetime.fromisoformat(data["published_at"])
    as_of = datetime.fromisoformat(data["as_of"])
    if any(x.utcoffset() != timedelta(0) for x in (published, as_of)):
        raise ValueError("HEALTH_CLOCK_INVALID")
    if published > now or as_of > published:
        raise ValueError("FUTURE_HEALTH_EVIDENCE")
    if type(data["synthetic"]) is not bool or not isinstance(data["source_sha256"], str):
        raise ValueError("UNSAFE_HEALTH_META")
    if len(data["source_sha256"]) != 64 or any(
        c not in "0123456789abcdef" for c in data["source_sha256"]
    ):
        raise ValueError("UNSAFE_HEALTH_SOURCE_HASH")
    if (
        type(data["wallet_count"]) is not int
        or data["wallet_count"] < 0
        or not isinstance(data["wallets"], list)
        or len(data["wallets"]) != data["wallet_count"]
    ):
        raise ValueError("INVALID_HEALTH_COUNT")
    if not isinstance(data["alert_counts"], dict) or any(
        k
        not in {
            "REVIEW_REQUIRED",
            "CAPITAL_FLOOR_BREACH",
            "INACTIVE",
            "EDGE_WARNING",
            "INSUFFICIENT_EVIDENCE",
            "RECOVERY_REVIEW",
            "HEALTHY",
        }
        or type(v) is not int
        or v < 0
        for k, v in data["alert_counts"].items()
    ):
        raise ValueError("UNSAFE_HEALTH_ALERTS")
    allowed = {
        "wallet_ref",
        "eligibility",
        "source",
        "capital",
        "activity",
        "edge",
        "copyability",
        "portfolio_contribution",
        "recommendation",
        "evidence_count",
    }
    for row in data["wallets"]:
        if (
            not isinstance(row, dict)
            or set(row) != allowed
            or not isinstance(row["wallet_ref"], str)
            or len(row["wallet_ref"]) != 16
            or any(c not in "0123456789abcdef" for c in row["wallet_ref"])
            or type(row["evidence_count"]) is not int
            or row["evidence_count"] < 0
            or row["eligibility"] not in {"ELIGIBLE", "CAPITAL_FLOOR_BREACH", "UNKNOWN"}
            or row["source"] not in {"AVAILABLE", "STALE", "UNKNOWN"}
            or row["capital"] not in {"RECONCILED", "UNRECONCILED", "UNKNOWN"}
            or row["activity"] not in {"ACTIVE", "INACTIVE", "UNKNOWN"}
            or row["edge"]
            not in {"EARLY_WARNING", "PERSISTENT_WARNING", "NO_WARNING", "INSUFFICIENT_EVIDENCE"}
            or row["copyability"]
            not in {"RETROSPECTIVE_ONLY", "PROSPECTIVE_OBSERVED", "INSUFFICIENT_EVIDENCE"}
            or row["portfolio_contribution"] != "UNKNOWN"
            or row["recommendation"]
            not in {
                "REVIEW_REQUIRED",
                "CAPITAL_FLOOR_BREACH",
                "INACTIVE",
                "EDGE_WARNING",
                "INSUFFICIENT_EVIDENCE",
                "RECOVERY_REVIEW",
                "HEALTHY",
            }
        ):
            raise ValueError("UNSAFE_HEALTH_ROW")
    # Publisher time does not refresh the underlying daily assessment.
    data["stale"] = now - as_of > timedelta(days=2)
    if data["stale"]:
        data["alert_counts"] = {"STALE_ASSESSMENT": data["wallet_count"]}
    unknown_count = sum(row["eligibility"] == "UNKNOWN" for row in data["wallets"])
    data["monitoring"] = {
        "health_evidence_fault": int(
            data["stale"]
            or unknown_count > 0
            or any(
                row["recommendation"] in {"CAPITAL_FLOOR_BREACH", "EDGE_WARNING", "REVIEW_REQUIRED"}
                for row in data["wallets"]
            )
        ),
        "health_unknown_count": unknown_count,
    }
    data["generation_sha256"] = digest
    return data


def main(argv: list[str] | None = None) -> None:
    """Publish an existing content-addressed private report to the redacted bridge."""
    import argparse
    from .wallet_health import HealthReport

    parser = argparse.ArgumentParser(description="Publish verified research-only health evidence")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--publish-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.report.is_symlink() or not args.report.is_file():
        raise ValueError("PRIVATE_HEALTH_REPORT_NOT_REGULAR")
    raw = args.report.read_bytes()
    if len(raw) > 4 * 1024 * 1024 or args.report.name != (
        "wallet-health-" + sha256(raw).hexdigest() + ".json"
    ):
        raise ValueError("PRIVATE_HEALTH_REPORT_SHA_INVALID")
    report = HealthReport.model_validate_json(raw)
    payload = project(report, published_at=datetime.now(UTC))
    publish(args.publish_dir, payload)
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "wallet_count": len(report.findings),
                "source_sha256": sha256(raw).hexdigest(),
                "redacted_projection_sha256": sha256(payload).hexdigest(),
                "trading_authorized": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
