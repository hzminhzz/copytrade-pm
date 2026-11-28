"""Native systemd lifecycle, configuration and operational failure contracts."""

import asyncio
from contextlib import closing, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from copytrade_pm import pm_appliance as appliance
from copytrade_pm.pm_appliance_config import load_config, verify_config
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import canonical
from copytrade_pm.roster import RosterStore
from roster_fixture import add_account
from test_checkpoint_runtime import configuration


def configured(tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    parents, _, _, source = configuration()
    checkpoint = root / "checkpoint.json"
    checkpoint.write_bytes(canonical(source))
    checkpoint.chmod(0o600)
    with RosterStore(root / "roster.sqlite", create=True) as roster:
        add_account(roster, "A", parents)
    config = {
        "schema": "copytrade_appliance_v1",
        "sources": {
            "canonical": {
                "state": "source",
                "portfolios": ["A"],
                "checkpoint_config": "checkpoint.json",
                "checkpoint_sha256": sha256(checkpoint.read_bytes()).hexdigest(),
            }
        },
        "papers": {
            "owner": {
                "state": "paper",
                "source": "canonical",
                "run_label": "fixture",
                "portfolios": {
                    "A": {"folder": "A", "members": list(parents), "starting_balance": "10000"}
                },
                "approval": None,
            }
        },
        "quotes": {
            "state": "quotes",
            "instruments": ["hyperliquid/mainnet:perp:default/BTC"],
            "poll_seconds": 2,
        },
        "health": {
            "max_wallets": 512,
            "deep_wallets": 12,
            "weight_per_minute": 600,
            "calendar": "*-*-* 04:00:00 UTC",
        },
    }
    path = root / "appliance.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    return root, config


def rewrite(root, config):
    (root / "appliance.json").write_text(json.dumps(config))


def test_configuration_reuses_existing_owner_paths_and_validates_without_writes(tmp_path):
    root, _ = configured(tmp_path)
    config = load_config(root)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    verified = verify_config(config)
    assert verified["sources"] == {"canonical": 1}
    assert verified["paper"] == {"owner": {"portfolios": 1, "signed": 0}}
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "fault", ["traversal", "absolute", "symlink", "overlap", "nested", "pin", "calendar", "public"]
)
def test_invalid_configuration_refuses_before_worker_writes(tmp_path, fault):
    root, raw = configured(tmp_path)
    if fault == "traversal":
        raw["sources"]["canonical"]["state"] = "../external"
    elif fault == "absolute":
        raw["papers"]["owner"]["state"] = str(tmp_path / "external")
    elif fault == "symlink":
        (root / "paper").symlink_to(tmp_path, target_is_directory=True)
    elif fault == "overlap":
        raw["quotes"]["state"] = "source"
    elif fault == "nested":
        raw["quotes"]["state"] = "paper/A"
    elif fault == "pin":
        raw["sources"]["canonical"]["checkpoint_sha256"] = "a" * 64
    elif fault == "calendar":
        raw["health"]["calendar"] = "*-*-* 29:00:00 UTC"
    else:
        (root / "appliance.json").chmod(0o644)
    rewrite(root, raw)
    with pytest.raises(ValueError):
        load_config(root)
    assert not (root / "source").exists()


def test_dry_reconcile_has_no_unit_or_state_mutation(tmp_path, monkeypatch):
    root, _ = configured(tmp_path)
    config = load_config(root)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(
        appliance, "_command", lambda *a, **k: pytest.fail("dry-run spawned a command")
    )
    result = appliance.reconcile(config, checkout=tmp_path / "checkout")
    assert result["state"] == "DRY_RUN"
    assert len(result["changed_units"]) == 6
    assert not (home / ".config").exists()
    assert not (root / "runtime").exists()


def test_reconcile_one_checkout_environment_revision_and_external_source_alias(
    tmp_path, monkeypatch
):
    root, _ = configured(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    checkout = tmp_path / "checkout"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    commands = []
    monkeypatch.setattr(appliance, "_command", lambda argv, **kw: commands.append(argv) or "")
    result = appliance.reconcile(load_config(root), checkout=checkout, apply=True)
    assert result["state"] == "RECONCILED"
    units = home / ".config/systemd/user"
    for role in (*appliance.ROLES, "health"):
        content = (units / ("copytrade-pm-" + role + ".service")).read_text()
        assert str(checkout / ".venv/bin/python") in content
        assert "Environment=COPYTRADE_RELEASE_SHA=" + "a" * 40 in content
        assert "PartOf=copytrade-pm.target" in content
        if role != "health":
            assert "Type=notify" in content
            assert "NotifyAccess=main" in content
    assert "Alias=" + appliance.SOURCE_ALIAS in (units / "copytrade-pm-source.service").read_text()
    assert commands[-1] == [
        "systemctl",
        "--user",
        "enable",
        appliance.TARGET,
        "copytrade-pm-source.service",
    ]
    assert not any("prop-" in part for command in commands for part in command)


@pytest.mark.parametrize("folder", ["checkout", "checkout with spaces"])
def test_rendered_units_are_accepted_by_native_systemd(tmp_path, folder):
    analyzer = shutil.which("systemd-analyze")
    if analyzer is None:
        pytest.skip("native systemd parser is unavailable")
    root, _ = configured(tmp_path)
    checkout = tmp_path / folder
    python = checkout / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    paths = []
    for name, content in appliance.render_units(
        load_config(root), checkout=checkout, sha="a" * 40
    ).items():
        path = unit_dir / name
        path.write_text(content)
        paths.append(str(path))
    result = subprocess.run(
        [analyzer, "--user", "verify", *paths],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_status_distinguishes_active_processes_from_missing_source_and_quotes(
    tmp_path, monkeypatch
):
    root, _ = configured(tmp_path)
    for folder in ("source", "paper/A", "quotes"):
        PaperJournal(root / folder)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "uv.lock").write_text("locked")
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    monkeypatch.setattr(
        appliance, "_unit_state", lambda _: {"ActiveState": "active", "MainPID": "99999999"}
    )
    result = appliance.status(load_config(root), checkout=checkout)
    assert result["state"] == "DEGRADED"
    assert "SOURCE_SCOPE_MISMATCH:canonical" in result["blockers"]
    assert "SOURCE_STALE:canonical" in result["blockers"]
    assert any(item.startswith("QUOTE_STALE:") for item in result["blockers"])
    assert result["trading_authorized"] is False
    assert result["scientifically_qualified"] is False


def test_software_update_rejects_unmerged_candidate_before_stopping_services(tmp_path, monkeypatch):
    from copytrade_pm import pm_ci_receipt

    root, _ = configured(tmp_path)
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(pm_ci_receipt, "validate_receipt", lambda *args: [])
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        raise RuntimeError("candidate not merged")

    monkeypatch.setattr(appliance, "_command", command)
    with pytest.raises(RuntimeError, match="not merged"):
        appliance.update(
            load_config(root),
            tmp_path / "candidate",
            tmp_path / "receipt",
            checkout=tmp_path / "checkout",
            apply=True,
        )
    assert calls == [["git", "merge-base", "--is-ancestor", "a" * 40, "origin/main"]]


@pytest.mark.parametrize("recovery_fails", [False, True])
def test_software_rollback_never_rewinds_owner_journals(tmp_path, monkeypatch, recovery_fails):
    from copytrade_pm import pm_ci_receipt

    root, _ = configured(tmp_path)
    journal = PaperJournal(root / "source")
    with closing(sqlite3.connect(journal.path)) as db:
        before = db.iterdump()
        evidence = list(before)
    checkout, candidate = tmp_path / "checkout", tmp_path / "candidate"
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    monkeypatch.setattr(
        appliance, "revision", lambda path: ("b" if path == candidate else "a") * 40
    )
    monkeypatch.setattr(pm_ci_receipt, "validate_receipt", lambda *args: [])
    monkeypatch.setattr(appliance, "_preflight", lambda *a, **k: None)
    baseline = {
        "revision": "a" * 40,
        "config_sha256": load_config(root).sha256,
        "blockers": [],
        "sources": {},
        "quotes": {},
        "papers": {},
        "workers": {
            role: {"running_revision": "a" * 40, "ready_at": "now", "MainPID": "1"}
            for role in appliance.ROLES
        },
    }
    monkeypatch.setattr(appliance, "status", lambda *a, **k: baseline)
    monkeypatch.setattr(appliance, "_start", lambda *a, **k: baseline)
    monkeypatch.setattr(appliance, "_await_activation", lambda *a, **k: baseline)
    calls = []
    syncs = []

    def sync(*args):
        syncs.append(args)
        if len(syncs) == 1 or recovery_fails:
            raise RuntimeError("simulated environment failure")

    def command(argv, **kwargs):
        calls.append(argv)
        return ""

    monkeypatch.setattr(appliance, "_sync_environment", sync)
    monkeypatch.setattr(appliance, "_command", command)
    expected = "RECOVERY_FAILED" if recovery_fails else "ROLLED_BACK"
    with pytest.raises(RuntimeError, match=expected):
        appliance.update(
            load_config(root), candidate, tmp_path / "receipt", checkout=checkout, apply=True
        )
    assert ["git", "switch", "--detach", "a" * 40] in calls
    with closing(sqlite3.connect(journal.path)) as db:
        assert list(db.iterdump()) == evidence
    assert json.loads((root / "runtime/update.json").read_text())["state"] == expected
    assert len(syncs) == 2


def test_environment_sync_uses_direct_binding_and_requires_actual_interpreter(
    tmp_path, monkeypatch
):
    checkout = tmp_path / "checkout"
    environment = tmp_path / "staged"
    commands = []
    monkeypatch.setattr(
        appliance, "_command", lambda argv, **kwargs: commands.append((argv, kwargs)) or ""
    )
    with pytest.raises(RuntimeError, match="APPLIANCE_ENVIRONMENT_MISSING"):
        appliance._sync_environment(checkout, environment)
    argv, kwargs = commands[0]
    assert argv[:2] == ["uv", "sync"]
    assert kwargs["env_overrides"] == {"UV_PROJECT_ENVIRONMENT": str(environment)}
    python = environment / "bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    appliance._sync_environment(checkout, environment, check=True)
    assert commands[-1][0][-1] == "--check"


def test_native_preflight_rejects_wrong_executable_and_invalid_unit(tmp_path, monkeypatch):
    root, _ = configured(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    checkout = tmp_path / "checkout"
    python = checkout / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    config = load_config(root)
    sha = "a" * 40
    units = appliance.render_units(config, checkout=checkout, sha=sha)
    appliance._verify_units(units, config=config, checkout=checkout, sha=sha)
    bad = dict(units)
    name = "copytrade-pm-paper.service"
    bad[name] = bad[name].replace(f'"{python}"', '"/bin/false"')
    with pytest.raises(ValueError, match="UNIT_BINDING:paper"):
        appliance._verify_units(bad, config=config, checkout=checkout, sha=sha)
    bad = dict(units)
    bad[name] = bad[name].replace("MemoryMax=2G", "MemoryMax=not-a-size")
    # A malformed timer/service may be reported as a warning by native
    # systemd, so test an invalid dependency that must fail verification.
    bad[name] = bad[name].replace(
        "After=network-online.target",
        "Requires=missing-ah-test.service\nAfter=network-online.target",
    )
    with pytest.raises(RuntimeError, match="systemd-analyze"):
        appliance._verify_units(bad, config=config, checkout=checkout, sha=sha)
    assert not (home / ".config").exists()


def test_activation_requires_advancing_evidence_and_preserves_existing_gap(tmp_path):
    from copy import deepcopy

    root, _ = configured(tmp_path)
    config = load_config(root)
    baseline = {
        "revision": "a" * 40,
        "config_sha256": config.sha256,
        "blockers": ["SOURCE_COVERAGE_GAP:canonical"],
        "workers": {
            role: {"MainPID": "1", "running_revision": "a" * 40, "ready_at": "old"}
            for role in appliance.ROLES
        },
        "sources": {"canonical": {"scope_checkpoints": {"scope": 100}}},
        "quotes": {"BTC": {"cursor": 10}},
        "papers": {
            "owner": {
                "A": {
                    "manifest_sha": "manifest",
                    "account_id": "account",
                    "financial_cursor": 4,
                    "observation_cursor": 100,
                    "finance_scan_cursors": {"owner": 90},
                }
            }
        },
    }
    observed = deepcopy(baseline)
    observed["revision"] = "b" * 40
    observed["workers"] = {
        role: {"MainPID": "2", "running_revision": "b" * 40, "ready_at": "new"}
        for role in appliance.ROLES
    }
    observed["sources"]["canonical"]["scope_checkpoints"]["scope"] = 200
    observed["quotes"]["BTC"]["cursor"] = 11
    assert not appliance._activation_blockers(config, baseline, observed, "b" * 40)
    # The existing gap excuses observation advancement only, never rewind,
    # a new gap, process drift or financial progress loss.
    observed["papers"]["owner"]["A"]["financial_cursor"] = 3
    observed["quotes"]["BTC"]["cursor"] = 10
    observed["workers"]["paper"]["ready_at"] = ""
    observed["blockers"].append("SOURCE_COVERAGE_GAP:new")
    assert set(appliance._activation_blockers(config, baseline, observed, "b" * 40)) == {
        "ACTIVATION_PAPER_CONTINUITY:A",
        "ACTIVATION_QUOTE_NOT_ADVANCING:BTC",
        "ACTIVATION_WORKER_IDENTITY:paper",
        "SOURCE_COVERAGE_GAP:new",
    }


def test_discovery_imports_no_providers_or_store_writers():
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys; sys.path.insert(0," + repr(str(root / "src")) + "); "
        "from copytrade_pm.pm_capabilities import validate; "
        "assert validate()['status']=='VERIFIED'; "
        "assert not {'ccxt','polars','pydantic','sqlite3','cryptography'} & set(sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=15,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )
    assert result.returncode == 0, result.stderr


def test_reconcile_refuses_old_source_before_writing_any_unit(tmp_path, monkeypatch):
    root, _ = configured(tmp_path)
    home = tmp_path / "home"
    units = home / ".config/systemd/user"
    units.mkdir(parents=True)
    old = units / appliance.SOURCE_ALIAS
    old.write_text("old independent release")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    monkeypatch.setattr(appliance, "_command", lambda *a, **k: pytest.fail("unit mutation"))
    with pytest.raises(ValueError, match="LEGACY_SOURCE_UNIT_NOT_RETIRED"):
        appliance.reconcile(load_config(root), checkout=tmp_path, apply=True)
    assert list(units.iterdir()) == [old]
    assert old.read_text() == "old independent release"


def test_native_readiness_requires_current_process_and_configuration(tmp_path, monkeypatch):
    from copytrade_pm.pm_appliance_workers import _ready

    root, _ = configured(tmp_path)
    config = load_config(root)
    receipt = root / "runtime/source.json"
    appliance._private_json(
        receipt,
        {
            "pid": os.getpid(),
            "revision": "a" * 40,
            "config_sha256": config.sha256,
            "phase": "STARTING",
        },
    )
    path = str(tmp_path / "notify.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
        listener.bind(path)
        listener.settimeout(1)
        monkeypatch.setenv("NOTIFY_SOCKET", path)
        _ready(config, "source")
        assert listener.recv(64) == b"READY=1"
    assert json.loads(receipt.read_text())["phase"] == "READY"
    appliance._private_json(receipt, {"pid": -1, "config_sha256": config.sha256})
    with pytest.raises(ValueError, match="READINESS_IDENTITY"):
        _ready(config, "source")


def test_paper_owners_progress_independently_and_cancel_drains_before_unlock(tmp_path, monkeypatch):
    from copytrade_pm import pm_appliance_workers as workers
    from copytrade_pm import pm_cwsa_source_observer as source

    root, _ = configured(tmp_path)
    blocked, fast, release = threading.Event(), threading.Event(), threading.Event()
    held = []

    @contextmanager
    def lease(path):
        held.append(path)
        try:
            yield
        finally:
            held.remove(path)

    def slow_poll():
        blocked.set()
        assert release.wait(5)

    monkeypatch.setattr(source, "source_lease", lease)
    monkeypatch.setattr(workers, "_ready", lambda *_: None)
    monkeypatch.setattr(
        workers,
        "paper_consumers",
        lambda _: [SimpleNamespace(poll_once=slow_poll), SimpleNamespace(poll_once=fast.set)],
    )

    async def scenario():
        task = asyncio.create_task(workers.paper(load_config(root), asyncio.Event(), once=True))
        try:
            assert await asyncio.to_thread(blocked.wait, 2)
            assert await asyncio.to_thread(fast.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert held and not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert held == []

    asyncio.run(scenario())


def test_failed_health_capture_is_visible_with_active_timer(tmp_path, monkeypatch):
    root, _ = configured(tmp_path)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "uv.lock").write_text("locked")
    monkeypatch.setattr(appliance, "revision", lambda *_: "a" * 40)
    monkeypatch.setattr(appliance, "_clean", lambda *_: None)
    monkeypatch.setattr(
        appliance,
        "_unit_state",
        lambda name: {
            "ActiveState": "active" if name.endswith(".timer") else "failed",
            "MainPID": "0",
            "Result": "exit-code" if name.endswith("health.service") else "success",
        },
    )
    result = appliance.status(load_config(root), checkout=checkout)
    assert "HEALTH_CAPTURE_FAILED" in result["blockers"]
    assert "HEALTH_TIMER_NOT_RUNNING" not in result["blockers"]
