#!/usr/bin/env python3
"""Publish a read-only, provenance-bound copytrade-pm SQLite snapshot to the Site."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_WALLET_ROWS = 1000
MAX_BODY_BYTES = 2 * 1024 * 1024


def run_json(*args: str) -> Any:
    candidates = [value for value in (os.environ.get("COPYTRADE_UV_BIN"), shutil.which("uv")) if value]
    candidates.append(str(Path.home() / ".local" / "bin" / "uv"))
    uv = next((str(Path(value).resolve()) for value in candidates if Path(value).is_file()), None)
    if uv is None:
        raise RuntimeError("uv executable is not available on PATH or in ~/.local/bin")
    command = [uv, "run", "--frozen", "--no-sync", "--group", "dev", *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode not in (0, 2):
        message = result.stderr.strip()[-1000:] or f"command exited {result.returncode}"
        raise RuntimeError(f"Read-only registry command failed: {Path(args[0]).name}: {message}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Registry command returned invalid JSON: {Path(args[0]).name}") from exc


def envelope(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} response is not an object")
    if value.get("error_code"):
        raise RuntimeError(f"{name} response has error_code={value['error_code']}")
    if not isinstance(value.get("data"), dict):
        raise RuntimeError(f"{name} response has no data object")
    if not isinstance(value.get("source"), dict):
        raise RuntimeError(f"{name} response has no source receipt")
    return value


def read_wallet_inventory() -> dict[str, Any]:
    page_size = 100
    first = envelope(run_json("copytrade-pm", "wallets", "list", "--limit", str(page_size), "--offset", "0"), "wallets")
    data = first["data"]
    total = data.get("total")
    rows = data.get("wallets")
    if not isinstance(total, int) or total < 0 or total > MAX_WALLET_ROWS or not isinstance(rows, list):
        raise RuntimeError("Wallet inventory is malformed or exceeds the bounded export limit")
    if len(rows) > page_size:
        raise RuntimeError("Wallet inventory page exceeded its requested limit")
    merged = list(rows)
    for offset in range(page_size, total, page_size):
        page = envelope(run_json("copytrade-pm", "wallets", "list", "--limit", str(page_size), "--offset", str(offset)), "wallets")
        page_data = page["data"]
        if page.get("status") != first.get("status") or page["source"].get("sha256") != first["source"].get("sha256") or page_data.get("total") != total:
            raise RuntimeError("Wallet inventory changed during pagination; retry on the next run")
        page_rows = page_data.get("wallets")
        if not isinstance(page_rows, list) or len(page_rows) > page_size:
            raise RuntimeError("Wallet inventory page is malformed")
        merged.extend(page_rows)
    if len(merged) != total:
        raise RuntimeError(f"Wallet inventory is incomplete: received {len(merged)} of {total}")
    data["wallets"] = merged
    return first


def canonical_alias_wallets(wallet_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = wallet_data.get("wallets")
    total = wallet_data.get("total")
    if not isinstance(rows, list) or not isinstance(total, int) or total != len(rows):
        raise RuntimeError("Wallet inventory is truncated or malformed")
    exported: list[dict[str, Any]] = []
    seen: set[str] = set()
    unresolved = {"unaliased": 0, "ambiguous": 0, "identity_not_bound": 0, "duplicate_alias": 0}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Wallet inventory contains a malformed row")
        alias = row.get("alias")
        identity_state = row.get("identity_state")
        ambiguous = row.get("ambiguous_alias_count", 1)
        reasons: list[str] = []
        if not isinstance(alias, str) or not alias.strip():
            reasons.append("unaliased")
        if isinstance(alias, str) and re.fullmatch(r"0x[a-fA-F0-9]{40}", alias.strip()):
            unresolved["address_like_alias"] += 1
            continue
        if identity_state != "EVIDENCE_BOUND":
            reasons.append("identity_not_bound")
        if not isinstance(ambiguous, int) or ambiguous != 0:
            reasons.append("ambiguous")
        if reasons:
            for reason in reasons:
                unresolved[reason] += 1
            continue
        alias = alias.strip()
        if alias in seen:
            unresolved["duplicate_alias"] += 1
            exported = [item for item in exported if item["alias"] != alias]
            seen.discard(alias)
            continue
        seen.add(alias)
        exported.append({
            "alias": alias,
            "identityState": identity_state,
            "ambiguousAliasCount": ambiguous,
            "registryMetadata": {
                "cohorts": row.get("cohorts") if isinstance(row.get("cohorts"), list) else [],
                "excluded": row.get("excluded") is True,
                "configured": row.get("configured") is True,
                "subscribed": row.get("subscribed") is True,
                "receiptHealth": row.get("receipt_health") or "UNKNOWN",
                "runtimeAdmitted": row.get("runtime_admitted") or "UNKNOWN",
                "tradingAuthorized": row.get("trading_authorized") is True,
                "portfolioMemberships": row.get("portfolio_memberships") if isinstance(row.get("portfolio_memberships"), list) else [],
                "aliases": [
                    {"namespace": alias_row.get("namespace"), "knownAt": alias_row.get("known_at")}
                    for alias_row in row.get("aliases", [])
                    if isinstance(alias_row, dict)
                ],
            },
        })
    unresolved["total_unresolved"] = max(0, total - len(exported))
    return exported, unresolved


def build_snapshot() -> dict[str, Any]:
    doctor = run_json("copytrade-wallet-registry", "doctor")
    status = run_json("copytrade-wallet-registry", "status")
    wallet_envelope = read_wallet_inventory()
    portfolio_envelope = envelope(run_json("copytrade-pm", "portfolios", "current"), "portfolios")
    release = run_json("python", "scripts/registry_release.py", "verify")

    if doctor.get("database_integrity") != "VERIFIED":
        raise RuntimeError("SQLite integrity is not VERIFIED; no snapshot was published")
    inventory_sha = doctor.get("inventory_sha256")
    if not isinstance(inventory_sha, str) or len(inventory_sha) != 64:
        raise RuntimeError("Doctor did not return a valid inventory SHA-256")
    wallet_source_sha = wallet_envelope["source"].get("sha256")
    portfolio_source_sha = portfolio_envelope["source"].get("sha256")
    if wallet_source_sha != inventory_sha or portfolio_source_sha != inventory_sha:
        raise RuntimeError("Registry inventory changed during export; retry on the next run")
    if wallet_envelope.get("status") != portfolio_envelope.get("status"):
        raise RuntimeError("Wallet and portfolio freshness states disagree; retry on the next run")

    wallet_data = wallet_envelope["data"]
    portfolio_data = portfolio_envelope["data"]
    if wallet_data.get("schema") != "wallet_registry_private_inventory_v1":
        raise RuntimeError("Unsupported native wallet inventory schema")
    if wallet_data.get("addresses_redacted") is not True:
        raise RuntimeError("Native inventory did not confirm that raw addresses are redacted")
    source_wallets = wallet_data.get("wallets")
    if not isinstance(source_wallets, list) or len(source_wallets) != wallet_data.get("total"):
        raise RuntimeError("Wallet inventory did not return its full bounded row set")
    wallets, unresolved_reasons = canonical_alias_wallets(wallet_data)

    current = portfolio_data.get("portfolios")
    if not isinstance(current, list) or not current:
        raise RuntimeError("Current research portfolio selection is empty or malformed")
    portfolios: list[dict[str, Any]] = []
    seen_portfolios: set[str] = set()
    for row in current:
        if not isinstance(row, dict):
            raise RuntimeError("Current selection contains a malformed portfolio")
        portfolio_id = row.get("portfolio_id")
        version = row.get("version")
        members = row.get("members")
        if not isinstance(portfolio_id, str) or not portfolio_id.strip() or not isinstance(version, int) or not isinstance(members, list):
            raise RuntimeError("Current selection is missing a portfolio ID, version, or member list")
        row_id = f"{portfolio_id.strip()}@v{version}"
        if row_id in seen_portfolios:
            raise RuntimeError("Current selection contains duplicate portfolio versions")
        seen_portfolios.add(row_id)
        portfolios.append({
            "id": row_id,
            "name": portfolio_id.strip(),
            "version": version,
            "priority": row.get("priority"),
            "role": row.get("role") or "UNKNOWN",
            "members": [value.strip() for value in members if isinstance(value, str) and value.strip()],
            "aliasResolutionComplete": row.get("alias_resolution_complete") is True,
            "definitionSha256": row.get("definition_sha256") or "",
            "paperRunning": row.get("paper_running") or "UNKNOWN",
            "tradingAuthorized": row.get("trading_authorized") is True,
        })

    release_status = release.get("result") if isinstance(release, dict) else None
    release_revision = release.get("revision") if isinstance(release, dict) else None
    source_observed_at = wallet_envelope["source"].get("observed_at")
    source = {
        "authority": "copytrade-pm SQLite wallet registry",
        "status": str(wallet_envelope.get("status") or "UNKNOWN").upper(),
        "observedAt": source_observed_at,
        "schema": wallet_data.get("schema"),
        "registrySchemaVersion": doctor.get("schema_version"),
        "inventorySha256": inventory_sha,
        "databaseIntegrity": doctor.get("database_integrity"),
        "releaseStatus": release_status or "UNKNOWN",
        "releaseRevision": release_revision or None,
        "selectionKnownAt": portfolio_data.get("selection_known_at"),
        "selectionSha256": portfolio_data.get("selection_sha256"),
        "selectionState": portfolio_data.get("selection_state") or "UNKNOWN",
        "paperRunning": portfolio_data.get("paper_running") or "UNKNOWN",
        "scientificallyQualified": portfolio_envelope.get("scientifically_qualified") is True,
        "tradingAuthorized": portfolio_envelope.get("trading_authorized") is True,
        "walletTotal": wallet_data.get("total", 0),
        "addressesRedacted": wallet_data.get("addresses_redacted") is True,
        "unresolvedWalletReasons": unresolved_reasons,
        "registryCounts": status.get("counts", {}) if isinstance(status, dict) else {},
    }
    return {
        "schema": "copytrade_ops_registry_snapshot_v1",
        "snapshotId": str(uuid.uuid4()),
        "producedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "source": source,
        "wallets": wallets,
        "portfolios": portfolios,
    }


def publish(snapshot: dict[str, Any]) -> dict[str, Any]:
    site_url = os.environ.get("COPYTRADE_SITE_URL", "").rstrip("/")
    access_token = os.environ.get("COPYTRADE_SITE_ACCESS_TOKEN", "")
    secret = os.environ.get("COPYTRADE_SITE_INGEST_SECRET", "")
    if not site_url.startswith("https://") or not access_token or not secret:
        raise RuntimeError("Site URL and both private Site credentials must be configured")
    body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise RuntimeError("Snapshot exceeds the publisher's 2 MiB limit")
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"{site_url}/api/ingest/registry",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "OAI-Sites-Authorization": f"Bearer {access_token}",
            "x-registry-timestamp": timestamp,
            "x-registry-signature": f"sha256={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read(16_384).decode("utf-8"))
            return {"httpStatus": response.status, **result}
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"Site ingestion returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Site ingestion could not be reached: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="read and validate the current registry without sending data")
    args = parser.parse_args()
    try:
        snapshot = build_snapshot()
        summary = {
            "snapshotId": snapshot["snapshotId"],
            "sourceStatus": snapshot["source"]["status"],
            "inventorySha256": snapshot["source"]["inventorySha256"],
            "walletTotal": snapshot["source"]["walletTotal"],
            "walletsResolved": len(snapshot["wallets"]),
            "walletsUnresolved": max(0, snapshot["source"]["walletTotal"] - len(snapshot["wallets"])),
            "portfolios": [row["id"] for row in snapshot["portfolios"]],
            "dryRun": args.dry_run,
        }
        if not args.dry_run:
            summary["siteResponse"] = publish(snapshot)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception as exc:  # The timer logs a short, non-secret failure reason.
        print(f"site_registry_sync: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
