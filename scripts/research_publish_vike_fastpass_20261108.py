"""Publish staged Vike research receipts to an immutable owner-private generation.

No SQLite mutation, no first-known clock invention and no trading authorization.
A committed research script may be reviewed and repeated; raw payloads stay private.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

ROOT = Path("/home/quant/.local/share/copytrade/reports/fastpass-july-nov-recovery-20261108")
STAGED = Path(".workspace")
PREFIXES = ("vike-recovery-20261108-", "vike-trades-20261108-")


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _write_new(target: Path, contents: bytes) -> None:
    fd = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def _read_stage() -> tuple[list[dict], str]:
    inputs = []
    for path in sorted(STAGED.glob("vike-*-20261108-*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        if not path.name.startswith(PREFIXES):
            continue
        raw = path.read_bytes()
        doc = json.loads(raw)
        if doc.get("schema") not in {
            "vike_hl_wallet_fills_mcp_page_v1",
            "vike_hl_wallet_fills_mcp_pages_v1",
            "vike_hl_wallet_fills_mcp_chunk_v1",
            "vike_hl_wallet_closed_trades_mcp_chunk_v1",
        }:
            raise ValueError(f"Invalid MCP research schema: {path.name}")
        data = doc.get("data") if doc.get("data") is not None else doc
        rows = data.get("items", data.get("trades", []))
        if not isinstance(rows, list):
            raise ValueError(f"Unrecognized Vike payload: {path.name}")
        inputs.append({
            "filename": path.name,
            "path": path,
            "sha256": sha256(raw).hexdigest(),
            "byte_length": len(raw),
            "rows": len(rows),
            "wallet_alias": doc.get("wallet_alias"),
            "type": doc["schema"],
            "request_start": doc.get("requested_start"),
            "request_end": doc.get("requested_end"),
            "next_cursor_exists": bool(data.get("nextCursor")),
        })
    if not inputs:
        raise ValueError("No staged Vike files")
    collection = sha256(_canonical([(x["filename"], x["sha256"]) for x in inputs])).hexdigest()
    return inputs, collection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    inputs, collection = _read_stage()
    target = ROOT / f"g-{collection[:20]}"
    summary = {
        "schema": "copytrade_fastpass_vike_immutable_recovery_v1",
        "generation_sha256": collection,
        "data_origin": "VIKE_MCP_RETROSPECTIVE_SOURCE",
        "source_clock": "EXCHANGE_EVENT_NOT_FOLLOWER_FIRST_KNOWN",
        "first_known_at": None,
        "financial_certified_real": False,
        "scientifically_qualified": False,
        "trading_authorized": False,
        "wallet_count": len({x["wallet_alias"] for x in inputs if x["wallet_alias"]}),
        "raw_file_count": len(inputs),
        "stored_rows_including_mixed_fills_and_trades": sum(x["rows"] for x in inputs),
        "files": [
            {
                k: x[k] for k in (
                    "filename", "sha256", "byte_length", "rows",
                    "wallet_alias", "type", "request_start", "request_end",
                    "next_cursor_exists",
                )
            }
            for x in inputs
        ],
    }
    manifest = _canonical(summary) + b"\n"
    print(json.dumps({
        "generation": collection, "raw_file_count": len(inputs),
        "wallet_count": summary["wallet_count"],
        "source_rows_not_deduplicated": summary["stored_rows_including_mixed_fills_and_trades"],
        "private_destination": str(target), "publish": bool(args.publish),
    }, sort_keys=True))
    if not args.publish:
        return
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.stat().st_mode & 0o077:
        raise RuntimeError("Private root permissions too open")
    if target.exists():
        old = target / "manifest.json"
        if not old.is_file() or old.read_bytes() != manifest:
            raise RuntimeError("Immutable generation collision or changed manifest")
        for x in inputs:
            p = target / "raw" / x["filename"]
            if not p.is_file() or sha256(p.read_bytes()).hexdigest() != x["sha256"]:
                raise RuntimeError("Existing immutable generation content mismatch")
        print("VERIFIED_EXISTING_GENERATION")
        return
    target.mkdir(mode=0o700)
    raw_dir = target / "raw"
    raw_dir.mkdir(mode=0o700)
    try:
        for x in inputs:
            _write_new(raw_dir / x["filename"], x["path"].read_bytes())
            if sha256((raw_dir / x["filename"]).read_bytes()).hexdigest() != x["sha256"]:
                raise RuntimeError("Postwrite source digest mismatch")
        _write_new(target / "manifest.json", manifest)
        dfd = os.open(target, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception:
        # Leave private partial generation for inspection; never erase unknown content.
        raise
    print("PUBLISHED_VERIFIED_PRIVATE_GENERATION")


if __name__ == "__main__":
    main()
