"""Cross-repository synthetic vectors emitted by the actual CWSA producer."""

from hashlib import sha256
import json
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.v4_source_export import export_checkpoint_packet
from test_checkpoint_journal import register, sample
from test_checkpoint_source import ADDRESS, BOUNDARY, scope


def vectors():
    key = Ed25519PrivateKey.from_private_bytes(b"c" * 32)
    with tempfile.TemporaryDirectory() as directory:
        journal = PaperJournal(Path(directory) / "paper")
        policy = register(journal)
        other_address = "0x" + "b" * 40
        other = scope().model_copy(
            update={
                "source_id": "fixture-other",
                "account_sha": sha256(other_address.encode()).hexdigest(),
                "generation": "d" * 64,
            }
        )
        journal.register_checkpoint_source(
            other, policy, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1
        )
        result = {"policy": policy.model_dump(mode="json"), "sources": []}
        for sc, address, quantities in (
            (scope(), ADDRESS, ["2", "3", "1", "-2", "0"]),
            (other, other_address, ["-2", "-3", "-1", "2", "0"]),
        ):
            packets, cursor = [], 0
            for index, quantity in enumerate(quantities):
                boundary = BOUNDARY + index * 300000
                journal.append_checkpoint_sample(
                    policy.epoch,
                    sample(journal, boundary, quantity, source_scope=sc, address=address),
                    boundary + 101,
                )
                packet = export_checkpoint_packet(
                    journal, sc, policy, signer=key, after_cursor=cursor, issued_ms=boundary + 102
                )
                packets.append(packet)
                cursor = len(journal.checkpoint_history(sc, policy.epoch))
            result["sources"].append({"scope": sc.model_dump(mode="json"), "packets": packets})
        return result


if __name__ == "__main__":
    print(json.dumps(vectors(), sort_keys=True, separators=(",", ":")))
