"""End-to-end PM-02 CLI reads sealed ledger without touching PM-01 v2."""

from hashlib import sha256
import json
import sys

import pytest

from copytrade_pm.pm02_audit import canonical, read_previous
from copytrade_pm.pm_manager import main
from copytrade_pm.pm_prospective_cli import run
from test_pm_prospective_cli import init_cli
from test_pm_prospective_pm02_contract import pm01_v2
from test_pm_prospective_ledger import IMPORTED


def pm01_private_fixture(tmp_path):
    data = canonical(pm01_v2())
    sha = sha256(data).hexdigest()
    file = tmp_path / f"pm01-synthetic-{sha[:20]}.json"
    file.write_bytes(data)
    return file


def test_pm02_cli_consumes_empty_sealed_journal_without_rewriting_pm01(
    tmp_path,
    monkeypatch,
    capsys,
):
    args, root, _signer, _public = init_cli(monkeypatch, tmp_path)
    run(["init", *args])
    pm01 = pm01_private_fixture(tmp_path)
    before = pm01.read_bytes()
    output = tmp_path / "output"
    cli = [
        "copytrade-pm-rank",
        "--pm01",
        str(pm01),
        "--asof",
        IMPORTED.isoformat(),
        "--out",
        str(output),
        "--prospective-ledger",
        str(root),
        "--research-root",
        str(tmp_path),
        "--auditor-public-key",
        str(tmp_path / "auditor.pub"),
    ]
    monkeypatch.setattr(sys, "argv", cli)
    main()
    info = json.loads(capsys.readouterr().out)
    assert info["qualified"] == 0
    assert all(seat["state"] == "EMPTY" for seat in info["seats"])
    report = read_previous(output / f"pm02-{info['sha256']}.json")
    assert report["audit_chain"]["prospective_ledger_head_sha256"] == "0" * 64
    assert report["untrusted_prospective_input"] is False
    assert report["cards"][0]["prospective"]["n"] == 0
    assert pm01.read_bytes() == before


def test_pm02_cli_fails_on_partial_prospective_ledger_args(tmp_path, monkeypatch):
    pm01 = pm01_private_fixture(tmp_path)
    cli = [
        "copytrade-pm-rank",
        "--pm01",
        str(pm01),
        "--asof",
        IMPORTED.isoformat(),
        "--out",
        str(tmp_path / "output"),
        "--prospective-ledger",
        str(tmp_path / "missing"),
    ]
    monkeypatch.setattr(sys, "argv", cli)
    with pytest.raises(ValueError, match="PROSPECTIVE_LEDGER_REQUIRES"):
        main()
    assert not (tmp_path / "output").exists()
