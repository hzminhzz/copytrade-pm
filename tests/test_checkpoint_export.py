from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import verify
from copytrade_pm.v4_source_export import export_checkpoint_packet
from test_checkpoint_journal import register, sample
from test_checkpoint_source import BOUNDARY, scope


def test_export_preserves_source_ids_and_original_hashes(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    journal.append_checkpoint_sample(policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101)
    changed = journal.append_checkpoint_sample(
        policy.epoch, sample(journal, BOUNDARY + 300_000, "3"), BOUNDARY + 300_101
    )
    key = Ed25519PrivateKey.generate()
    packet = export_checkpoint_packet(
        journal, scope(), policy, signer=key, after_cursor=0, issued_ms=BOUNDARY + 300_102
    )
    body = verify(packet, key.public_key(), "cwsa-checkpoint-v3")
    assert body["transitions"][-1]["effect"]["signal_id"] == changed.signal_id
    assert body["policy"] == policy.model_dump(mode="json")
    assert len(body["transitions"]) == 3
    assert body["originals"]
    assert body["trading_authorized"] is False


def test_native_request_preimage_binds_the_selected_account(tmp_path):
    from test_checkpoint_source import ADDRESS

    journal = PaperJournal(tmp_path / "paper")
    candidate = sample(journal, BOUNDARY)
    for receipt in candidate.receipts:
        assert receipt.request.user == ADDRESS
        assert receipt.request.type == "clearinghouseState"


def test_existing_spool_publishes_an_immutable_checkpoint_packet(tmp_path):
    from copytrade_pm.v4_source_spool import capture_checkpoint_once

    journal = PaperJournal(tmp_path / "paper")
    policy = register(journal)
    journal.append_checkpoint_sample(policy.epoch, sample(journal, BOUNDARY), BOUNDARY + 101)
    key = Ed25519PrivateKey.generate()
    seed, public = tmp_path / "seed", tmp_path / "public"
    seed.write_bytes(key.private_bytes_raw())
    public.write_bytes(key.public_key().public_bytes_raw())
    seed.chmod(0o600)
    public.chmod(0o600)
    root = tmp_path / "spool"
    root.mkdir(mode=0o700)
    arguments = dict(
        journal=journal,
        scope=scope(),
        policy=policy,
        root=root,
        signing_key=seed,
        public_key=public,
        after_cursor=0,
        issued_ms=BOUNDARY + 102,
    )
    first = capture_checkpoint_once(**arguments)
    assert capture_checkpoint_once(**arguments) == first
    assert len(list((root / "outbox").glob("*.json"))) == 1
    assert first["cursor"] == 2
    assert first["trading_authorized"] is False
