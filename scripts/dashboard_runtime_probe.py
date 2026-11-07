"""Read-only, bounded dashboard baseline. No credentials, writes or service actions.

Run as an authorized operator to compare six protected services before/after
dashboard work. This probe does not verify the journal hash chain or grant finance.
Its only SQL reads metadata and the last 64 event identities/timestamps.
"""

import json
import os
from pathlib import Path
import resource
import sqlite3
import subprocess
import time

UNITS = tuple(
    "prop-production-" + name + ".service"
    for name in ("guardian", "broker", "planner", "observer", "bybit-observer", "watchdog")
)
ROOT = Path("/var/lib/prop-production")


def metadata(path):
    try:
        st = path.stat()
        return {
            "mode": oct(st.st_mode & 0o777),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
        }
    except OSError as exc:
        return {"error": type(exc).__name__}


def main():
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
    output = {
        "schema": "dashboard_runtime_probe_v1",
        "captured_at_ms": time.time_ns() // 1000000,
        "read_only": True,
        "euid": os.geteuid(),
    }
    props = (
        "Id",
        "MainPID",
        "NRestarts",
        "ActiveState",
        "SubState",
        "User",
        "Group",
        "ExecMainStartTimestampMonotonic",
        "MemoryCurrent",
        "CPUUsageNSec",
        "MemoryMax",
        "TasksMax",
        "CPUQuotaPerSecUSec",
    )
    result = subprocess.run(
        ["systemctl", "show", *UNITS, *["--property=" + p for p in props]],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    )
    output["units"] = [
        dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        for block in result.stdout.strip().split("\n\n")
    ]
    release = Path("/opt/prop-production/current")
    output["protected_release_path"] = str(release.resolve())
    try:
        output["protected_commit"] = (release / "COMMIT").read_text().strip()
        output["protected_compatibility"] = json.loads((release / "compatibility.json").read_text())
    except (OSError, ValueError) as exc:
        output["protected_metadata_error"] = type(exc).__name__
    output["paths"] = {
        str(p): metadata(p)
        for p in (
            ROOT,
            ROOT / "guardian",
            ROOT / "guardian/account.sqlite",
            ROOT / "guardian/account.sqlite-wal",
            ROOT / "guardian/account.sqlite-shm",
            Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite"),
        )
    }
    output["health"] = {}
    for role in ("guardian", "propr", "bybit", "planner"):
        path = ROOT / "health" / role / "heartbeat.json"
        item = {"file": metadata(path)}
        try:
            if path.stat().st_size > 131072:
                raise ValueError("oversized")
            payload = json.loads(path.read_text())
            item["fields"] = {
                k: payload[k]
                for k in (
                    "schema",
                    "role",
                    "status",
                    "heartbeat_ms",
                    "at_ms",
                    "observed_at_ms",
                    "journal_sequence",
                    "sequence",
                    "last_progress_ms",
                    "mode",
                )
                if k in payload and isinstance(payload[k], (str, int, bool, type(None)))
            }
        except (OSError, ValueError) as exc:
            item["error"] = type(exc).__name__
        output["health"][role] = item
    journal = ROOT / "guardian/account.sqlite"
    try:
        with sqlite3.connect(f"file:{journal}?mode=ro", uri=True, timeout=1) as con:
            con.execute("PRAGMA query_only=ON")
            output["journal_mode"] = con.execute("PRAGMA journal_mode").fetchone()[0]
            output["journal_tail"] = [
                {"sequence": seq, "kind": kind, "at_ms": at, "sha": sha}
                for seq, kind, at, sha in con.execute(
                    "SELECT seq,kind,at_ms,sha FROM events ORDER BY seq DESC LIMIT 64"
                )
            ]
            output["journal_validation"] = "METADATA_ONLY_NOT_HASH_CHAIN_VERIFICATION"
    except (OSError, sqlite3.Error) as exc:
        output["journal_error"] = type(exc).__name__
    output["memory"] = {
        line.split(":")[0]: line.split(":")[1].strip()
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.split(":")[0] in {"MemTotal", "MemAvailable", "SwapFree"}
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
