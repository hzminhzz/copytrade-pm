#!/usr/bin/env python3
"""Offline appliance acceptance on online-backup copies of authentic owner journals.

This is a verification tool, not a deployer. Originals are opened read-only.
New snapshots must not exist; --verify-existing rechecks a separate saved copy.
No provider calls or signing occur.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_appliance_config import load_config, verify_config
from copytrade_pm.pm_appliance_workers import paper_consumers
from copytrade_pm.pm_cwsa_source_observer import load_checkpoint_configuration
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_source_selection import selected_parents
from copytrade_pm.roster.observations import import_registry


def copy_db(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("ORIGINAL_JOURNAL_REQUIRED")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination)) as saved:
            original.backup(saved, pages=2048, sleep=0.02)
            if saved.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("SNAPSHOT_INTEGRITY")
    destination.chmod(0o600)


def copy_owner(source: Path, destination: Path) -> None:
    copy_db(source / "paper-events.sqlite3", destination / "paper-events.sqlite3")
    # Raw evidence is immutable and content addressed. Copy bytes, never link
    # originals into a mutable falsifier or replay workspace.
    for name in ("source-evidence-v2", "wire-evidence", "originals"):
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name)
    print(json.dumps({"copied": source.name}), flush=True)


def financial(checkout: Path, owner: Path, run_id: str) -> dict:
    code = """
import json,sys
from pathlib import Path
import copytrade_pm.pm_forward_journal as journal
expected=Path(sys.argv[1]).resolve()/"src"
if not Path(journal.__file__).resolve().is_relative_to(expected):
    raise ValueError("LEGACY_IMPORT_BINDING")
print(json.dumps(journal.PaperJournal(Path(sys.argv[2])).restore(sys.argv[3]),sort_keys=True))
"""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["PYTHONPATH"] = str(checkout / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [str(checkout / ".venv/bin/python"), "-c", code, str(checkout), str(owner), run_id],
        cwd=checkout,
        env=env,
        check=True,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return json.loads(result.stdout)


def candidate_identity() -> dict:
    root = Path(__file__).resolve().parents[1]
    import copytrade_pm.pm_forward_journal as module

    if not Path(module.__file__).resolve().is_relative_to(root / "src"):
        raise ValueError("CANDIDATE_IMPORT_BINDING")

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args],
            cwd=root,
            text=True,
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        ).strip()

    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("PARITY_REQUIRES_CLEAN_COMMITTED_CANDIDATE")
    return {
        "revision": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "python": sys.version,
    }


def verify(args: argparse.Namespace) -> dict:
    candidate = candidate_identity()
    started = time.monotonic()
    original = load_config(args.state_root)
    saved = args.snapshot_root.expanduser().absolute()
    if (
        saved.is_symlink()
        or saved == original.root
        or saved.is_relative_to(original.root / "prospective")
    ):
        raise ValueError("SEPARATE_SNAPSHOT_REQUIRED")
    if saved.exists() != args.verify_existing:
        raise ValueError("SNAPSHOT_EXISTENCE_MISMATCH")
    if not args.verify_existing:
        saved.mkdir(parents=True, mode=0o700)
    legacy = {}
    for mapping in args.legacy_checkout:
        name, separator, path = mapping.partition("=")
        if not separator or name in legacy:
            raise ValueError("LEGACY_CHECKOUT_MAPPING")
        legacy[name] = Path(path).absolute()
    if set(legacy) != set(original.papers):
        raise ValueError("EVERY_FINANCIAL_OWNER_REQUIRES_ORIGINAL_INTERPRETER")
    if not args.verify_existing:
        shutil.copy2(original.root / "appliance.json", saved / "appliance.json")
        copy_db(original.roster, saved / "roster.sqlite")
        for item in original.sources.values():
            pin = original.path(item["checkpoint_config"])
            target = saved / pin.relative_to(original.root)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(pin, target)
            copy_owner(original.path(item["state"]), saved / item["state"])
        for item in original.papers.values():
            if item["approval"]:
                pin = original.path(item["approval"]["path"])
                target = saved / pin.relative_to(original.root)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(pin, target)
            for portfolio in item["portfolios"].values():
                relative = Path(item["state"]) / portfolio["folder"]
                copy_owner(original.path(str(relative)), saved / relative)
        copy_owner(original.path(original.quotes["state"]), saved / original.quotes["state"])
    elif load_config(saved).sha256 != original.sha256:
        raise ValueError("SNAPSHOT_CONFIGURATION_DRIFT")
    before = {}
    for name, item in original.papers.items():
        for pid, portfolio in item["portfolios"].items():
            owner = saved / item["state"] / portfolio["folder"]
            before[pid] = financial(legacy[name], owner, portfolio["folder"])
    adoption = import_registry(
        args.registry_snapshot,
        args.sha256,
        saved / "roster.sqlite",
        at_ms=time.time_ns() // 1_000_000,
        apply=True,
    )
    config = load_config(saved)
    verified = verify_config(config)
    source_proofs = {}
    for name, item in config.sources.items():
        parents = selected_parents(
            config.roster, portfolios=tuple(item["portfolios"]), as_of=datetime.now(UTC).isoformat()
        )
        policy = load_checkpoint_configuration(
            config.path(item["checkpoint_config"]), item["checkpoint_sha256"], parents
        )
        journal = PaperJournal(config.path(item["state"]))
        counts, heads = [], []
        for scope in policy.scopes.values():
            history = journal.checkpoint_history(scope, policy.policy.epoch)
            counts.append(len(history))
            heads.append(digest(history[-1].model_dump(mode="json")) if history else None)
        source_proofs[name] = {
            "scopes": len(counts),
            "transitions": sum(counts),
            "heads_sha256": digest(heads),
        }
        print(json.dumps({"source_verified": name, **source_proofs[name]}), flush=True)
    consumers = paper_consumers(config)
    print(
        json.dumps({"stage": "CONSUMERS_RESTORED", "elapsed_seconds": time.monotonic() - started}),
        flush=True,
    )
    results = {}
    for consumer in consumers:
        for pid, journal in consumer.journals.items():
            state = journal.restore(consumer.configs[pid]["folder"])
            if state != before[pid]:
                raise ValueError("FINANCIAL_REPLAY_DRIFT:" + pid)
            results[pid] = {
                "cursor": state["cursor"],
                "state_sha256": digest(state),
                "account_id": state["account"]["account_id"]
                if "account_id" in state["account"]
                else None,
                "mandates": len(consumer.approved[pid].mandates) if pid in consumer.approved else 0,
            }
        print(
            json.dumps(
                {
                    "stage": "FINANCIAL_PARITY",
                    "owners": list(consumer.journals),
                    "elapsed_seconds": time.monotonic() - started,
                }
            ),
            flush=True,
        )
        consumer.poll_once()
        for pid, journal in consumer.journals.items():
            if journal.restore(consumer.configs[pid]["folder"]) != before[pid]:
                raise ValueError("FROZEN_INPUT_REPOLL_CHANGED_FINANCE:" + pid)
    # Restart the generic consumer against the same frozen inputs.
    for consumer in paper_consumers(config):
        for pid, journal in consumer.journals.items():
            if journal.restore(consumer.configs[pid]["folder"]) != before[pid]:
                raise ValueError("RESTART_FINANCIAL_DRIFT:" + pid)
    if candidate_identity() != candidate:
        raise ValueError("CANDIDATE_CHANGED_DURING_PARITY")
    report = {
        "schema": "copytrade_appliance_authentic_parity_v1",
        "candidate": candidate,
        "elapsed_seconds": time.monotonic() - started,
        "state": "VERIFIED",
        "observed_at": datetime.now(UTC).isoformat(),
        "original_root": str(original.root),
        "snapshot_root": str(saved),
        "original_interpreters": {key: str(value) for key, value in legacy.items()},
        "config": verified,
        "adoption": adoption,
        "sources": source_proofs,
        "papers": results,
        "limitations": [
            "Owner snapshots have independent cutoffs",
            "No economic qualification",
            "No trading authorization",
        ],
        "order_route": "NONE",
    }
    receipt = saved / "parity.json"
    receipt.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    receipt.chmod(0o600)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--registry-snapshot", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--legacy-checkout", action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
