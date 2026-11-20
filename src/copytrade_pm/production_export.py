"""Consistent read-only production metadata handoff; no broker or signing authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .roster.sealed import select_sealed_book, timestamp_ms
from .roster.store import DEFAULT_ROSTER_PATH, RosterStore


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def export_metadata(
    db: Path,
    portfolio_id: str,
    asof: str,
    *,
    version: int | None = None,
    sizing_policy: str = "FIXED_K_NATIVE_QUANTITY",
) -> dict:
    """Export the immutable book/lease identity for independent review."""
    if sizing_policy != "FIXED_K_NATIVE_QUANTITY":
        raise ValueError("SIZING_POLICY")
    with RosterStore(db) as store:
        selected = select_sealed_book(
            store, portfolio_id, timestamp_ms(asof), require_attestation=False
        )
    if version is not None and version != selected.version:
        raise ValueError("SELECTION_MEMBER_DRIFT")
    return selected.metadata()


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Mount the read-only metadata export options onto an existing subparser."""
    parser.add_argument("--db", type=Path, default=DEFAULT_ROSTER_PATH)
    parser.add_argument("--portfolio", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--version", type=int)
    parser.add_argument(
        "--sizing-policy",
        default="FIXED_K_NATIVE_QUANTITY",
        choices=("FIXED_K_NATIVE_QUANTITY",),
    )
    parser.add_argument("--private-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(add_arguments(argparse.ArgumentParser(description=__doc__)).parse_args(argv))


def run(args: argparse.Namespace) -> int:
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
