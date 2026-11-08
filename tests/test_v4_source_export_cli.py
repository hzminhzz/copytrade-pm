"""Run the same source signer CLI used by the isolated read-only export."""

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.v4_source_export import main
from test_pm_forward_observed_paper import ADDRESSES
from test_v4_source_export import observer, source_event


def private(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def test_operator_pinned_key_and_cursor_bootstrap_prevent_replayed_entry(tmp_path):
    journal, obs = observer(tmp_path)
    key = Ed25519PrivateKey.generate()
    selected = private(tmp_path / "selected.json", json.dumps({"S035": ADDRESSES["S035"]}).encode())
    signing_key = private(tmp_path / "source.key", key.private_bytes_raw())
    public_key = private(tmp_path / "source.pub", key.public_key().public_bytes_raw())
    state = tmp_path / "cursors.json"

    def invoke(output):
        return main(
            [
                "--journal-db",
                str(journal.path),
                "--selected-json",
                str(selected),
                "--source-signing-key",
                str(signing_key),
                "--source-public-key",
                str(public_key),
                "--cursor-state",
                str(state),
                "--private-output",
                str(output),
            ]
        )

    source_event(obs, 10, 20)
    first = tmp_path / "first.json"
    assert invoke(first) == 0
    assert json.loads(first.read_text())["events"]["S035"] == []
    assert json.loads(state.read_text())["S035"] == 3
    source_event(obs, 20, 25)
    second = tmp_path / "second.json"
    assert invoke(second) == 0
    assert len(json.loads(second.read_text())["events"]["S035"]) == 1
    assert json.loads(state.read_text())["S035"] == 4
    # Output immutability and key mismatch fail without advancing the cursor.
    assert invoke(second) == 2
    assert json.loads(state.read_text())["S035"] == 4
    signing_key.chmod(0o644)
    assert invoke(tmp_path / "third.json") == 2
    assert not (tmp_path / "third.json").exists()
