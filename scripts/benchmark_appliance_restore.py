"""Profile verified source/finance replay on disposable copies of frozen journals."""

from __future__ import annotations

import argparse
from contextlib import closing
import cProfile
from hashlib import sha256
import json
from pathlib import Path
import pstats
import sqlite3
from tempfile import TemporaryDirectory
import time

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_appliance_config import load_config
from copytrade_pm.pm_checkpoint_journal import CwsaPolicy
from copytrade_pm.pm_checkpoint_source import CheckpointScope
from copytrade_pm.pm_forward_journal import PaperJournal


def copy_journal(source: Path, destination: Path) -> PaperJournal:
    destination.mkdir(mode=0o700)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination / "paper-events.sqlite3")) as copied:
            original.backup(copied)
    return PaperJournal(destination)


def source_restore(journal: PaperJournal) -> dict:
    with closing(sqlite3.connect(journal.path.as_uri() + "?mode=ro", uri=True)) as db:
        scopes = db.execute("SELECT scope,policy FROM cwsa_heads ORDER BY stream").fetchall()
    heads = []
    transitions = 0
    for raw_scope, raw_policy in scopes:
        history = journal.checkpoint_history(
            CheckpointScope.model_validate_json(raw_scope),
            CwsaPolicy.model_validate_json(raw_policy).epoch,
        )
        transitions += len(history)
        heads.append(digest(history[-1].model_dump(mode="json")) if history else None)
    return {"scopes": len(scopes), "transitions": transitions, "heads_sha256": digest(heads)}


def measure(label: str, callback, repeats: int) -> dict:
    result = callback()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        if callback() != result:
            raise ValueError("RESTORE_NOT_IDEMPOTENT:" + label)
        samples.append(time.perf_counter() - start)
    profile = cProfile.Profile()
    if profile.runcall(callback) != result:
        raise ValueError("PROFILE_REPLAY_DRIFT:" + label)
    print("PROFILE", label, flush=True)
    pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(20)
    return {
        "seconds": samples,
        "result_sha256": digest(result),
        "cursor": result.get("cursor"),
        "transitions": result.get("transitions"),
    }


def reject_tamper(journal: PaperJournal, sql: str, callback) -> str:
    # Only the disposable copy is writable. The original frozen input is
    # never altered, including when a replay fails.
    with journal.writer() as db:
        db.execute(sql)
    try:
        callback()
    except ValueError as exc:
        return str(exc)
    raise ValueError("TAMPER_WENT_UNDETECTED")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--source", default="v4pod3")
    parser.add_argument("--paper", default="liquid12")
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    config = load_config(args.snapshot.resolve())
    source = config.path(config.sources[args.source]["state"]) / "paper-events.sqlite3"
    paper = config.papers[args.paper]
    portfolio = next(iter(paper["portfolios"].values()))
    finance = config.path(paper["state"]) / portfolio["folder"] / "paper-events.sqlite3"
    with TemporaryDirectory(prefix="copytrade-restore-benchmark-") as temp:
        root = Path(temp)
        source_journal = copy_journal(source, root / "source")
        paper_journal = copy_journal(finance, root / "paper")
        reports = {
            "source": measure("source", lambda: source_restore(source_journal), args.repeats),
            "paper": measure(
                "paper", lambda: paper_journal.restore(portfolio["folder"]), args.repeats
            ),
        }
        reports["source"]["tamper_detection"] = reject_tamper(
            source_journal,
            "UPDATE cwsa_transitions SET sha=printf('%064d',0) WHERE seq=1",
            lambda: source_restore(source_journal),
        )
        reports["paper"]["tamper_detection"] = reject_tamper(
            paper_journal,
            "UPDATE events SET input_sha=printf('%064d',0) WHERE seq=1",
            lambda: paper_journal.restore(portfolio["folder"]),
        )
        print(
            json.dumps(
                {
                    "inputs": {
                        name: sha256(path.read_bytes()).hexdigest()
                        for name, path in (("source", source), ("paper", finance))
                    },
                    "reports": reports,
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
