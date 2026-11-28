"""Native systemd/Git/uv rollback falsifier using frozen owner journal copies.

The fixture redirects the systemd target to a unique transient service and
replaces provider polling with verified source and financial replay. The real
update transaction, exact CI receipt, Git fast-forward/detach, offline frozen
environment, unit readiness, durable update receipts and journal-prefix checks
are exercised. It never stops or writes production units or contacts a broker.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from benchmark_appliance_restore import copy_journal, source_restore
from copytrade_pm import pm_appliance as appliance
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_appliance_config import load_config


ROOT = Path(__file__).resolve().parents[1]
WORKER = """
import json,os,socket,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from benchmark_appliance_restore import source_restore
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm03_account import digest
import copytrade_pm
assert Path(copytrade_pm.__file__).resolve().is_relative_to(Path.cwd()/'src')
proof={'pid':os.getpid(),'revision':sys.argv[2],
       'source':digest(source_restore(PaperJournal(Path(sys.argv[3])))),
       'paper':digest(PaperJournal(Path(sys.argv[4])).restore(sys.argv[5]))}
Path(sys.argv[6]).write_text(json.dumps(proof))
if sys.argv[7]=='fail':
    raise SystemExit(73)
with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
    addr=os.environ['NOTIFY_SOCKET']
    sock.connect('\\0'+addr[1:] if addr.startswith('@') else addr)
    sock.sendall(b'READY=1')
while True:
    time.sleep(1)
"""


def native(*argv: str, cwd: Path | None = None) -> str:
    return appliance._command(list(argv), cwd=cwd, timeout=120)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("--baseline", required=True)
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    original = load_config(args.snapshot.resolve())
    target = appliance.revision(ROOT)
    appliance._clean(ROOT)
    source = original.sources["liquid12"]
    paper = original.papers["liquid12"]
    pid, portfolio = next(iter(paper["portfolios"].items()))
    folder = portfolio["folder"]
    # The user systemd manager may see a different /tmp mount from the
    # invoking DevSpace process. Use a private home-backed temporary tree.
    with TemporaryDirectory(prefix="copytrade-ah-native-", dir=Path.home() / ".cache") as temp:
        root = Path(temp)
        state = root / "state"
        state.mkdir(mode=0o700)
        source_path = state / source["state"]
        paper_path = state / paper["state"] / folder
        for path in (source_path, paper_path):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        sj = copy_journal(original.path(source["state"]) / "paper-events.sqlite3", source_path)
        pj = copy_journal(
            original.path(paper["state"]) / folder / "paper-events.sqlite3", paper_path
        )
        config = replace(original, root=state)
        expected = {"source": digest(source_restore(sj)), "paper": digest(pj.restore(folder))}
        checkout = root / "checkout"
        native("git", "clone", "--shared", "--no-checkout", str(ROOT), str(checkout))
        native("git", "switch", "--detach", args.baseline, cwd=checkout)
        native("git", "update-ref", "refs/remotes/origin/main", target, cwd=checkout)
        appliance._sync_environment(checkout, checkout / ".venv")
        names: list[str] = []
        active = ""
        rollback_fault = False
        proof_file = root / "worker.json"

        def start(fault: bool) -> dict:
            nonlocal active
            active = f"copytrade-ah-test-{os.getpid()}-{len(names)}.service"
            names.append(active)
            # update() stops only this unique native test service.
            appliance.TARGET = active
            proof_file.unlink(missing_ok=True)
            native(
                "systemd-run",
                "--user",
                "--unit",
                active,
                "--property=Type=notify",
                "--property=TimeoutStartSec=90",
                "--property=Restart=no",
                f"--working-directory={checkout}",
                str(checkout / ".venv/bin/python"),
                "-I",
                "-c",
                WORKER,
                str(ROOT / "scripts"),
                appliance.revision(checkout),
                str(source_path),
                str(paper_path),
                folder,
                str(proof_file),
                "fail" if fault else "ready",
            )
            return status(config, checkout=checkout)

        def status(_config, *, checkout: Path) -> dict:
            observed = appliance._unit_state(active)
            with closing(sqlite3.connect(sj.path.as_uri() + "?mode=ro", uri=True)) as db:
                heads = db.execute("SELECT stream,state,head FROM cwsa_heads").fetchall()
                checkpoints = dict(
                    db.execute(
                        "SELECT stream,MAX(checkpoint_ms) FROM cwsa_outcomes GROUP BY stream"
                    )
                )
            with closing(sqlite3.connect(pj.path.as_uri() + "?mode=ro", uri=True)) as db:
                cursor, account, manifest = db.execute(
                    "SELECT cursor,account_id,manifest_sha FROM runs WHERE run_id=?", (folder,)
                ).fetchone()
                head = db.execute(
                    "SELECT chain_sha FROM events WHERE run_id=? AND seq=?", (folder, cursor)
                ).fetchone()
                wave = db.execute(
                    "SELECT checkpoint_ms,receipt_sha FROM chapter2_wave_receipts ORDER BY checkpoint_ms DESC LIMIT 1"
                ).fetchone()
                scans = dict(db.execute("SELECT owner,checkpoint_ms FROM chapter2_finance_scan"))
            return {
                "revision": appliance.revision(checkout),
                "config_sha256": config.sha256,
                "blockers": [],
                "order_route": "NONE",
                "trading_authorized": False,
                "observed_at": datetime.now(UTC).isoformat(),
                "workers": {role: dict(observed) for role in appliance.ROLES},
                "sources": {
                    "liquid12": {
                        "scope_checkpoints": checkpoints,
                        "scope_heads": {
                            key: [json.loads(raw)["sequence"], sha] for key, raw, sha in heads
                        },
                    }
                },
                "papers": {
                    "liquid12": {
                        pid: {
                            "account_id": account,
                            "manifest_sha": manifest,
                            "financial_cursor": cursor,
                            "financial_head_sha": head[0],
                            "observation_cursor": wave[0],
                            "observation_head_sha": wave[1],
                            "finance_scan_cursors": scans,
                            "configured_approval": True,
                            "order_route": "NONE",
                        }
                    }
                },
                "quotes": {},
            }

        def preflight(_config, active_checkout, candidate, before, wanted):
            assert active_checkout == checkout and candidate == ROOT
            assert appliance.revision(checkout) == before
            assert appliance.revision(ROOT) == wanted
            # The fixture deliberately has no installed appliance target.
            # Native production preflight is exercised separately.
            appliance._sync_environment(checkout, checkout / ".venv", check=True)

        def await_native(_config, active_checkout, baseline, wanted, observed):
            proof = json.loads(proof_file.read_text())
            assert appliance.revision(active_checkout) == proof["revision"] == wanted
            assert observed["workers"]["paper"]["ActiveState"] == "active"
            assert int(observed["workers"]["paper"]["MainPID"]) == proof["pid"]
            assert {k: proof[k] for k in expected} == expected
            appliance._verify_prefixes(config, baseline)
            return observed

        def start_candidate(_config, *, checkout: Path):
            return start(appliance.revision(checkout) == target or rollback_fault)

        original_target = appliance.TARGET
        receipts = []
        try:
            start(False)
            with (
                patch.object(appliance, "_preflight", preflight),
                patch.object(appliance, "status", status),
                patch.object(appliance, "_start", start_candidate),
                patch.object(appliance, "_await_activation", await_native),
            ):
                for recovery_fails in (False, True):
                    rollback_fault = recovery_fails
                    try:
                        appliance.update(
                            config, ROOT, args.receipt.resolve(), checkout=checkout, apply=True
                        )
                    except RuntimeError as exc:
                        expected_state = "RECOVERY_FAILED" if recovery_fails else "ROLLED_BACK"
                        if expected_state not in str(exc):
                            raise
                        receipt = json.loads((state / "runtime/update.json").read_text())
                        assert receipt["state"] == expected_state
                        assert appliance.revision(checkout) == args.baseline
                        assert digest(source_restore(sj)) == expected["source"]
                        assert digest(pj.restore(folder)) == expected["paper"]
                        receipts.append(
                            {
                                "state": expected_state,
                                "revision": appliance.revision(checkout),
                                "native_unit": active,
                                "journal_parity": True,
                            }
                        )
                    else:
                        raise AssertionError("FAULT_WAS_ACCEPTED")
        finally:
            appliance.TARGET = original_target
            for unit in names:
                subprocess.run(
                    ["systemctl", "--user", "stop", unit], capture_output=True, timeout=30
                )
                subprocess.run(
                    ["systemctl", "--user", "reset-failed", unit], capture_output=True, timeout=30
                )
        print(
            json.dumps(
                {
                    "candidate": target,
                    "results": receipts,
                    "source_and_paper": expected,
                    "scope": "native transient service; fixture provider polling and target binding",
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
