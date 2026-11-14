"""Offline, read-only Track B v2 release candidate attestation.

This verifies a candidate private report against a separately published redacted
projection. It does not provision Grafana, create a deployment, alter the
registry, replay broker trades or activate notifications.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .strategy_health import read as read_private_report
from .strategy_health_projection import (
    NAME as PROJECTION_NAME,
    project,
    read as read_projection,
)

SCHEMA = "track_b_v2_nonactivating_release_candidate_v1"
MAX_V1_BYTES = 131072

PUBLICATION_AUTHORITY = "strategy-health-v2-private-publication"
BINDING_SCHEMA = "strategy_health_publication_binding_v1"
MAX_BINDING_BYTES = 16384


def _verify_aggregate(projection_directory: Path, report, observed: dict) -> bytes:
    published_at = datetime.fromisoformat(observed["published_at"])
    generated = project(report, published_at=published_at)
    path = projection_directory / PROJECTION_NAME
    if path.is_symlink():
        raise ValueError("PROJECTION_SYMLINK_FORBIDDEN")
    if sha256(path.read_bytes()).digest() != sha256(generated).digest():
        raise ValueError("REDACTED_PROJECTION_ORIGINAL_MISMATCH")
    return generated


def create_private_binding(
    private_report: Path,
    projection_directory: Path,
    *,
    private_binding_path: Path,
    publisher_alias: str,
    signer,
) -> str:
    """Owner-authored offline Ed25519 intent receipt; never exposed to Grafana.

    Public endpoint retains an anonymous aggregate. This private independent
    artifact connects exact original report bytes to exact publication bytes.
    """
    from .pm_private_io import atomic_private_output
    from .production_manifest import canonical, sign

    if not publisher_alias or len(publisher_alias) > 80 or not publisher_alias.isascii():
        raise ValueError("PUBLICATION_PUBLISHER_IDENTITY_INVALID")
    report = read_private_report(private_report)
    raw = (projection_directory / PROJECTION_NAME).read_bytes()
    observed = json.loads(raw)
    verified = _verify_aggregate(projection_directory, report, observed)
    if verified != raw:
        raise ValueError("PUBLICATION_AGGREGATE_INVALID")
    payload = {
        "schema": BINDING_SCHEMA,
        "publisher_alias": publisher_alias,
        "report_sha256": sha256(private_report.read_bytes()).hexdigest(),
        "report_seal_sha256": report.report_sha256,
        "projection_sha256": sha256(verified).hexdigest(),
        "publication_generation_sha256": observed["generation_sha256"],
        "published_at": observed["published_at"],
        "nonactivating": True,
        "trading_authorized": False,
        "synthetic_report_claim": False,
    }
    envelope = sign(payload, signer, PUBLICATION_AUTHORITY)
    atomic_private_output(private_binding_path, canonical(envelope))
    return envelope["sha256"]


def _read_private_binding(path: Path, key) -> dict:
    from .production_manifest import canonical, verify

    if path.is_symlink():
        raise ValueError("PUBLICATION_BINDING_SYMLINK")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o777 != 0o600
            or (not 0 < info.st_size <= MAX_BINDING_BYTES)
        ):
            raise ValueError("PUBLICATION_BINDING_PRIVATE_MODE_REQUIRED")
        raw = os.read(fd, MAX_BINDING_BYTES + 1)
        if len(raw) != info.st_size:
            raise ValueError("PUBLICATION_BINDING_TRUNCATED")
    finally:
        os.close(fd)
    obj = json.loads(raw)
    if raw != canonical(obj):
        raise ValueError("PUBLICATION_BINDING_NONCANONICAL")
    payload = verify(obj, key, PUBLICATION_AUTHORITY)
    if (
        set(payload)
        != {
            "schema",
            "publisher_alias",
            "report_sha256",
            "report_seal_sha256",
            "projection_sha256",
            "publication_generation_sha256",
            "published_at",
            "nonactivating",
            "trading_authorized",
            "synthetic_report_claim",
        }
        or payload["schema"] != BINDING_SCHEMA
        or payload["nonactivating"] is not True
        or payload["trading_authorized"] is not False
        or payload["synthetic_report_claim"] is not False
    ):
        raise ValueError("PUBLICATION_BINDING_SCHEMA_INVALID")
    return payload


def _read_protected_v1(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("V1_SNAPSHOT_NOT_A_REGULAR_FILE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= MAX_V1_BYTES:
            raise ValueError("V1_SNAPSHOT_INVALID_SIZE")
        raw = os.read(fd, MAX_V1_BYTES + 1)
        if len(raw) != meta.st_size:
            raise ValueError("V1_SNAPSHOT_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get("schema") != "wallet_health_grafana_v1":
        raise ValueError("V1_SNAPSHOT_SCHEMA_INVALID")
    return sha256(raw).hexdigest()


def attest(
    private_report: Path,
    projection_directory: Path,
    *,
    as_of: datetime,
    wallet_health_v1: Path,
    private_binding: Path,
    publisher_public_key,
) -> dict:
    if as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
        raise ValueError("ATTEST_ASOF_UTC_REQUIRED")
    original = read_private_report(private_report)
    projected = read_projection(projection_directory, now=as_of)
    if original.as_of > as_of:
        raise ValueError("ATTEST_ORIGINAL_FUTURE")
    generated = _verify_aggregate(projection_directory, original, projected)
    binding = _read_private_binding(private_binding, publisher_public_key)
    if private_report.parent.stat().st_mode & 0o777 != 0o700:
        raise ValueError("PRIVATE_ASSESSMENT_DIRECTORY_NOT_0700")
    if private_binding.parent.stat().st_mode & 0o777 != 0o700:
        raise ValueError("PRIVATE_BINDING_DIRECTORY_NOT_0700")
    private_bytes = private_report.read_bytes()
    if (
        binding["report_sha256"] != sha256(private_bytes).hexdigest()
        or binding["report_seal_sha256"] != original.report_sha256
        or binding["projection_sha256"] != sha256(generated).hexdigest()
        or binding["publication_generation_sha256"] != projected["generation_sha256"]
        or binding["published_at"] != projected["published_at"]
    ):
        raise ValueError("PRIVATE_PUBLICATION_BINDING_ORIGINAL_MISMATCH")
    v1_sha = _read_protected_v1(wallet_health_v1)
    return {
        "schema": SCHEMA,
        "private_assessment_sha256": sha256(private_bytes).hexdigest(),
        "publisher_identity": binding["publisher_alias"],
        "private_publication_binding_signature_verified": True,
        "private_report_seal_sha256": original.report_sha256,
        "redacted_projection_sha256": sha256(generated).hexdigest(),
        "projection_generation_sha256": projected["generation_sha256"],
        "wallet_health_v1_existing_sha256": v1_sha,
        "assessment_private_mode": "0700/0600",
        "source_finance_authenticated": False,
        "scientifically_qualified": False,
        "deployed": False,
        "owner_paging_active": False,
        "trading_authorized": False,
        "activation_allowed": False,
        "requires_independent_deployment_authorization": True,
        "requires_original_source_and_market_finance_proof": True,
        "requires_real_cadence_and_notification_route_proof": True,
    }


def main(argv: list[str] | None = None) -> int:
    """Print a JSON-only read-only receipt; no write flags exist."""
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-report", required=True, type=Path)
    p.add_argument("--projection-dir", required=True, type=Path)
    p.add_argument("--as-of", required=True)
    p.add_argument("--v1-wallet-health", required=True, type=Path)
    p.add_argument("--private-binding", required=True, type=Path)
    p.add_argument("--publisher-public-key", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_path = args.publisher_public_key
        if public_path.is_symlink() or not public_path.is_file():
            raise ValueError("PINNED_PUBLISHER_PUBLIC_KEY_MISSING")
        public = Ed25519PublicKey.from_public_bytes(public_path.read_bytes())
        receipt = attest(
            args.private_report,
            args.projection_dir,
            as_of=datetime.fromisoformat(args.as_of.replace("Z", "+00:00")),
            wallet_health_v1=args.v1_wallet_health,
            private_binding=args.private_binding,
            publisher_public_key=public,
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "CANDIDATE_REJECTED",
                    "reason": type(exc).__name__,
                    "deployed": False,
                    "trading_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
