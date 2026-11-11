"""Reversible, owner-only cutover to a clean V4 sixteen-portfolio NO_TRADE paper run.

Does not stop official sources, Vike prices, Guardian or any broker. Never deletes
or rewrites historical journals; archives their *final hashes* after quiescence.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path("/home/quant/.local/share/copytrade")
RELEASES = ROOT / "releases"
STATE = ROOT / "prospective/v4-canonical-sixteen-1111"
UNIT = Path.home() / ".config/systemd/user/copytrade-v4-canonical-sixteen-1111.service"
NAME = UNIT.name
SOURCE = "copytrade-v4-sixteen-source-0911.service"
PRICE = "copytrade-v4-minute-0811.service"
OLD = (
    ("copytrade-v4-paper-p1-0811.service", "v4-paper-p1-0811"),
    ("copytrade-v4-paper-p14-0811.service", "v4-paper-p14-0811"),
    ("copytrade-v4-paper-p16-0811.service", "v4-paper-p16-0811"),
    ("copytrade-v4-sixteen-paper-0911.service", "v4-paper-sixteen-0911"),
    ("copytrade-pydnative-v4-sixteen-paper-0911.service", "pydnative-v4-paper-sixteen-0911"),
)
REGISTRY = ROOT / "registry/wallet_registry.sqlite"
SOURCE_DB = ROOT / "prospective/v4-selected-sixteen-0911/paper-events.sqlite3"
PRICE_DB = ROOT / "prospective/v4-minute-0811/paper-events.sqlite3"
CAMPAIGN = Path(
    "/home/quant/dev/copytrade-pm/data/private/gemini_phase3_phase4_eligibility_20261104.json"
)
CAMPAIGN_SHA = "7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f"
CATALOG_NAME = "docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json"
LABEL = "canonical_20261111"
SHA = re.compile(r"^[0-9a-f]{40}$")


def run(*cmd: str, cwd: Path | None = None, timeout: int = 90) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} returned {p.returncode}: {p.stderr[-900:]}")
    return p.stdout.strip()


def unit_status(name: str) -> dict:
    raw = run(
        "systemctl", "--user", "show", name, "-p", "ActiveState", "-p", "MainPID", "-p", "ExecStart"
    )
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def root_for(sha: str) -> Path:
    if not SHA.fullmatch(sha):
        raise ValueError("INVALID_RELEASE_SHA")
    return RELEASES / f"v4-canonical-{sha[:12]}"


def assert_staged(sha: str) -> Path:
    release = root_for(sha)
    if release.is_symlink() or not release.is_dir() or release.stat().st_mode & 0o077:
        raise RuntimeError("RELEASE_NOT_PRIVATE")
    if (release / "source.sha").read_text().strip() != sha:
        raise RuntimeError("RELEASE_SOURCE_SHA_MISMATCH")
    if not (release / ".venv/bin/python").is_file():
        raise RuntimeError("RELEASE_NOT_INSTALLED")
    return release


def stage(sha: str) -> dict:
    repo = Path(__file__).resolve().parents[1]
    if run("git", "rev-parse", "HEAD", cwd=repo) != sha:
        raise RuntimeError("RELEASE_MUST_BE_CHECKOUT_HEAD")
    if run("git", "status", "--porcelain", cwd=repo):
        raise RuntimeError("CLEAN_GIT_WORKTREE_REQUIRED")
    release = root_for(sha)
    if release.exists():
        assert_staged(sha)
        return {"status": "ALREADY_STAGED", "release": str(release)}
    if shutil.disk_usage(RELEASES).free < 5 * 1024**3:
        raise RuntimeError("INSUFFICIENT_FREE_DISK")
    release.mkdir(mode=0o700, parents=False, exist_ok=False)
    files = run("git", "ls-files", "-z", cwd=repo).split("\0")
    for name in files:
        if not name:
            continue
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("INVALID_TRACKED_PATH")
        source = repo / path
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("SYMLINK_OR_MISSING_SOURCE")
        target = release / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    run(
        "uv",
        "sync",
        "--frozen",
        "--no-dev",
        "--extra",
        "source",
        "--extra",
        "market",
        cwd=release,
        timeout=250,
    )
    marker = release / "source.sha"
    with open(marker, "x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(sha + "\n")
    assert_staged(sha)
    return {"status": "STAGED_ONLY", "release": str(release), "trading_authorized": False}


def args_for(release: Path) -> list[str]:
    return [
        str(release / ".venv/bin/python"),
        "-m",
        "copytrade_pm.pm_v4_sixteen_paper",
        "--registry-db",
        str(REGISTRY),
        "--source-db",
        str(SOURCE_DB),
        "--price-db",
        str(PRICE_DB),
        "--propr-catalog",
        str(release / CATALOG_NAME),
        "--campaign-manifest",
        str(CAMPAIGN),
        "--campaign-sha256",
        CAMPAIGN_SHA,
        "--state-root",
        str(STATE),
        "--poll-seconds",
        "2",
        "--run-label",
        LABEL,
        "--paper-risk-profile",
        "CHALLENGE_TRAILING_8PCT",
    ]


def unit_text(release: Path, sha: str) -> str:
    exe = " ".join(args_for(release))
    return f"""[Unit]
Description=V4 canonical sixteen research paper, NO BROKER ({sha[:12]})
After={SOURCE} {PRICE}
Wants={SOURCE} {PRICE}
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={release}
ExecStart={exe}
Restart=on-failure
RestartSec=15
TimeoutStopSec=65
KillSignal=SIGTERM
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=COPYTRADE_PAPER_RELEASE_SHA={sha}
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={STATE}
MemoryMax=2G
CPUQuota=90%
TasksMax=128

[Install]
WantedBy=default.target
"""


def check_sources() -> None:
    if (
        unit_status(SOURCE)["ActiveState"] != "active"
        or unit_status(PRICE)["ActiveState"] != "active"
    ):
        raise RuntimeError("SOURCE_AND_PRICE_MUST_BE_ACTIVE")
    for p in (REGISTRY, SOURCE_DB, PRICE_DB, CAMPAIGN):
        if p.is_symlink() or not p.is_file():
            raise RuntimeError(f"MISSING_REQUIRED_SOURCE: {p}")
    if shutil.disk_usage(ROOT).free < 5 * 1024**3:
        raise RuntimeError("INSUFFICIENT_DISK_HEADROOM")


def hash_file(path: Path) -> str:
    dig = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            dig.update(chunk)
    return dig.hexdigest()


def archive_old_heads() -> dict:
    """Call only with all historical paper consumers stopped."""
    for name, _ in OLD:
        stat = unit_status(name)
        if stat["ActiveState"] == "active" or stat["MainPID"] != "0":
            raise RuntimeError("OLD_PAPER_CONSUMER_STILL_WRITING")
    rows = []
    for name, folder in OLD:
        base = ROOT / "prospective" / folder
        journals = sorted(base.glob("**/events.jsonl"))
        if len(journals) != (16 if "sixteen" in folder else 1):
            raise RuntimeError(f"OLD_LEDGER_COUNT_UNEXPECTED: {name} {len(journals)}")
        for journal in journals:
            manifest = journal.with_name("manifest.json")
            if not manifest.is_file():
                raise RuntimeError("MISSING_LEDGER_MANIFEST")
            rows.append(
                {
                    "service": name,
                    "journal_relative": str(journal.relative_to(ROOT)),
                    "events_bytes": journal.stat().st_size,
                    "events_sha256": hash_file(journal),
                    "manifest_sha256": hash_file(manifest),
                }
            )
    if len(rows) != 35:
        raise RuntimeError("HISTORICAL_LEDGER_COUNT_NOT_35")
    root = ROOT / "campaign-archives"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt = root / f"old-paper-heads-before-{LABEL}-{stamp}.json"
    body = {
        "basis": "READONLY_FINAL_HEAD_RECEIPTS",
        "at_utc": datetime.now(UTC).isoformat(),
        "historical_ledgers": len(rows),
        "old_roots_preserved_in_place": True,
        "trade_route": "NONE",
        "journals": rows,
    }
    with open(receipt, "x") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(body, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return {"receipt": str(receipt), "historical_ledgers": len(rows)}


def verify_fresh_root() -> dict:
    manifests = sorted(STATE.glob("*/p*_v4_sixteen_" + LABEL + "/manifest.json")) + sorted(
        STATE.glob("*/e*_v4_sixteen_" + LABEL + "/manifest.json")
    )
    # The glob can cover 1+16 only if the run label/namespace is duplicated.
    if len(manifests) != 16:
        raise RuntimeError(f"CANONICAL_MANIFEST_COUNT_INVALID:{len(manifests)}")
    for p in manifests:
        m = json.loads(p.read_text())
        rule = m["rulebook"]
        if (
            rule["initial_balance"] != "10000"
            or rule["daily_loss"] != "500"
            or rule["static_loss"] is not None
            or rule["trailing_loss"] != "800"
            or rule.get("trailing_cap") is not None
            or rule["account_terms_confirmed"]
            or "TRAILING_8PCT" not in rule["source"]
        ):
            raise RuntimeError(f"UNEXPECTED_RISK_PROFILE:{p}")
        events = p.parent / "events.jsonl"
        if events.is_symlink() or not events.is_file():
            raise RuntimeError("NONPRIVATE_LEDGER_EVENT_PATH")
        with events.open() as stream:
            for line in stream:
                row = json.loads(line)["event"]
                if row["kind"] == "PM04_PAPER_EXECUTE" and row["first_known_at"] < m["started_at"]:
                    raise RuntimeError("PRESTART_SOURCE_REPLAY_ADMITTED")
    return {"new_ledgers": len(manifests), "risk_profile": "CHALLENGE_TRAILING_8PCT"}


def cutover(sha: str) -> dict:
    release = assert_staged(sha)
    check_sources()
    if UNIT.exists() or UNIT.is_symlink() or STATE.exists():
        raise RuntimeError("CANONICAL_RUN_OR_UNIT_ALREADY_EXISTS")
    # Fail closed if preexisting old consumers are absent/unknown.
    for name, _ in OLD:
        if unit_status(name)["ActiveState"] not in ("active", "inactive", "failed"):
            raise RuntimeError("OLD_UNIT_UNKNOWN")
    # No irreversible data deletion; record original enablement for restoration.
    enabled = {
        name: subprocess.run(
            ["systemctl", "--user", "is-enabled", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        ).stdout.strip()
        for name, _ in OLD
    }
    for name, _ in OLD:
        run("systemctl", "--user", "stop", name)
        run("systemctl", "--user", "disable", name)
    receipt = archive_old_heads()
    STATE.mkdir(mode=0o700)
    cmd = args_for(release) + ["--once"]
    run(*cmd, cwd=release, timeout=140)
    fresh = verify_fresh_root()
    UNIT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(UNIT, "x") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(unit_text(release, sha))
        f.flush()
        os.fsync(f.fileno())
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", NAME)
    run("systemctl", "--user", "start", NAME)
    time.sleep(3)
    current = unit_status(NAME)
    if current["ActiveState"] != "active" or int(current["MainPID"]) <= 0:
        run("systemctl", "--user", "stop", NAME)
        raise RuntimeError("CANONICAL_SERVICE_NOT_ACTIVE")
    check_sources()
    return {
        "status": "DEPLOYED_NO_BROKER",
        "release_sha": sha,
        "source_coverage": "DEGRADED_FIXED_7_OF_14",
        "previous_enablement": enabled,
        **receipt,
        **fresh,
        "pid": int(current["MainPID"]),
        "state_root": str(STATE),
    }


def rollback() -> dict:
    if not UNIT.is_file():
        raise RuntimeError("CANONICAL_UNIT_NOT_INSTALLED")
    run("systemctl", "--user", "stop", NAME)
    run("systemctl", "--user", "disable", NAME)
    return {
        "status": "CANONICAL_PAPER_STOPPED",
        "ledgers_preserved": str(STATE),
        "historical_paper_not_auto_restored": True,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--phase", choices=("plan", "stage", "cutover", "verify", "rollback"), default="plan"
    )
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    release = root_for(a.expected_sha)
    if a.phase == "plan":
        check_sources()
        result = {
            "status": "PLAN_ONLY",
            "release": str(release),
            "old": {name: unit_status(name)["ActiveState"] for name, _ in OLD},
            "source": unit_status(SOURCE)["ActiveState"],
            "trade_route": "NONE",
        }
    elif a.phase == "verify":
        result = {**verify_fresh_root(), "runtime": unit_status(NAME)}
    elif not a.apply:
        result = {
            "status": "DRY_RUN",
            "phase": a.phase,
            "release": str(release),
            "will_touch": "five PAPER units only; not source, market or broker",
        }
    elif a.phase == "stage":
        result = stage(a.expected_sha)
    elif a.phase == "cutover":
        result = cutover(a.expected_sha)
    else:
        result = rollback()
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
