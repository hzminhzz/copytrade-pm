"""Consistent read-only production metadata handoff; no broker or signing authority."""

from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from . import wallet_registry as registry
from . import wallet_registry_portfolios as portfolios


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def export_metadata(
    db: Path,
    portfolio_id: str,
    asof: str,
    *,
    version: int | None = None,
    sizing_policy: str = "FIXED_K_NATIVE_QUANTITY",
    _connection: sqlite3.Connection | None = None,
) -> dict:
    """Hash logical rows from one query-only transaction, never a live WAL file.

    Complete source scope is always required. Leader NAV is required only for
    explicit legacy allocation-over-NAV sizing. Preserve that export's wire
    representation so existing signed policy digests remain verifiable.
    """
    if sizing_policy not in {"FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV"}:
        raise ValueError("SIZING_POLICY")
    _ms(asof)
    with (
        closing(registry.connect(db, False)) if _connection is None else nullcontext(_connection)
    ) as con:
        if not con.in_transaction:
            con.execute("BEGIN")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("REGISTRY_INTEGRITY")
        if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("REGISTRY_FOREIGN_KEYS")
        if con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] != 8:
            raise ValueError("REGISTRY_SCHEMA")
        fingerprint = sha256()
        for table in registry.AUTHORITATIVE_INVENTORY_TABLES:
            rows = sorted(
                json.dumps(row, sort_keys=True, separators=(",", ":"))
                for row in con.execute(f"SELECT * FROM {table}").fetchall()
            )
            fingerprint.update(table.encode("ascii") + b"\0")
            for row in rows:
                fingerprint.update(row.encode() + b"\n")
        selected = portfolios.select_asof(con, portfolio_id, asof, version=version)
        blockers = ["SOURCE_ACCOUNT_SCOPE_UNVERIFIED"]
        blockers.append(
            "SOURCE_BOOK_NAV_ATTESTATION_MISSING"
            if sizing_policy == "ALLOCATION_OVER_LIVE_NAV"
            else "SOURCE_POSITION_SCOPE_ATTESTATION_MISSING"
        )
        members = []
        if selected.get("state") == "UNKNOWN_AT_ASOF":
            blockers.append("PORTFOLIO_UNKNOWN_AT_ASOF")
        else:
            seal_time = selected["selection_known_at"]
            for alias in selected["members"]:
                records = con.execute(
                    "SELECT DISTINCT w.wallet_id,w.address,a.known_at FROM wallet_aliases a "
                    "JOIN wallets w USING(wallet_id) WHERE a.alias=? AND a.known_at<=? "
                    "ORDER BY a.known_at DESC,w.wallet_id",
                    (alias, seal_time),
                ).fetchall()
                ids = {r[0] for r in records}
                if len(ids) != 1:
                    blockers.append("MEMBER_IDENTITY_UNKNOWN_AT_SEAL")
                    members.append(
                        {"pod_id": alias, "source_identity": None, "identity_known_at_ms": None}
                    )
                    continue
                wallet_id, identity, _ = records[0]
                frozen_id = con.execute(
                    "SELECT wallet_id FROM portfolio_memberships "
                    "WHERE portfolio_id=? AND version=? AND member_alias=?",
                    (portfolio_id, selected["version"], alias),
                ).fetchone()[0]
                if frozen_id is not None and frozen_id != wallet_id:
                    raise ValueError("SEALED_MEMBER_IDENTITY_DRIFT")
                members.append(
                    {
                        "pod_id": alias,
                        "source_identity": identity,
                        "identity_known_at_ms": min(_ms(r[2]) for r in records),
                    }
                )
        result = {
            "schema": "research_portfolio_export_v1",
            "portfolio_id": portfolio_id,
            "version": selected.get("version"),
            "asof_ms": _ms(asof),
            "selection_known_at_ms": (
                _ms(selected["selection_known_at"]) if selected.get("selection_known_at") else None
            ),
            "research_commit": selected.get("source_commit"),
            "decision_sha256": selected.get("source_doc_sha256"),
            "sealed_definition_sha256": selected.get("definition_sha256"),
            "registry_inventory_sha256": fingerprint.hexdigest(),
            "members": members,
            "state": "BLOCKED",
            "blockers": sorted(set(blockers)),
            "batch_seconds": 300,
            "sizing_policy": sizing_policy,
            "order_route": "NONE",
            "trading_authorized": False,
        }
        result["export_sha256"] = sha256(canonical(result)).hexdigest()
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=registry.DB)
    parser.add_argument("--portfolio", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--version", type=int)
    parser.add_argument(
        "--sizing-policy",
        default="FIXED_K_NATIVE_QUANTITY",
        choices=("FIXED_K_NATIVE_QUANTITY", "ALLOCATION_OVER_LIVE_NAV"),
    )
    parser.add_argument("--private-output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = export_metadata(
            args.db,
            args.portfolio,
            args.asof,
            version=args.version,
            sizing_policy=args.sizing_policy,
        )
        if args.private_output:
            path = args.private_output
            if path.exists() or not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
                raise ValueError("OUTPUT_REQUIRES_NEW_FILE_IN_PRIVATE_DIRECTORY")
            import os

            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical(result))
                stream.flush()
                os.fsync(stream.fileno())
        # Only this redacted view can appear in an operator log.
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "schema",
                        "state",
                        "blockers",
                        "export_sha256",
                        "registry_inventory_sha256",
                        "trading_authorized",
                    )
                },
                sort_keys=True,
            )
        )
        return 2 if result["state"] == "BLOCKED" else 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(
            json.dumps(
                {"state": "BLOCKED", "reason": str(exc), "trading_authorized": False},
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
