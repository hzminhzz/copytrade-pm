"""Reproducible nonactivating release receipt and v1 byte stability."""

from datetime import UTC, datetime, timedelta
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.strategy_health import publish as publish_private, seal
from copytrade_pm.strategy_health_projection import project, publish as publish_redacted
from copytrade_pm.strategy_release_candidate import attest, main, create_private_binding
from test_strategy_health_v2 import assessment


def test_release_receipt_matches_private_and_redacted_without_writes(tmp_path, capsys):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    public = tmp_path / "read-only"
    public.mkdir()
    now = datetime.now(UTC)
    report = seal(assessment().model_copy(update={"as_of": now, "created_at": now}))
    private = root / "report.json"
    publish_private(report, private)
    publish_redacted(public, project(report, published_at=now))
    v1 = public / "wallet-health.json"
    v1.write_text(json.dumps({"schema": "wallet_health_grafana_v1"}, sort_keys=True))
    signer = Ed25519PrivateKey.generate()
    binding = root / "signed-publication.json"
    create_private_binding(
        private,
        public,
        private_binding_path=binding,
        publisher_alias="track-b-offline-owner",
        signer=signer,
    )
    public_key = root / "publisher-key.raw"
    public_key.write_bytes(signer.public_key().public_bytes_raw())
    originals = {p: p.read_bytes() for p in (private, public / "strategy-health.json", v1, binding)}
    receipt = attest(
        private,
        public,
        as_of=now,
        wallet_health_v1=v1,
        private_binding=binding,
        publisher_public_key=signer.public_key(),
    )
    assert receipt["schema"] == "track_b_v2_nonactivating_release_candidate_v1"
    assert receipt["assessment_private_mode"] == "0700/0600"
    assert receipt["private_publication_binding_signature_verified"] is True
    assert receipt["publisher_identity"] == "track-b-offline-owner"
    assert len(receipt["private_report_seal_sha256"]) == 64
    assert len(receipt["wallet_health_v1_existing_sha256"]) == 64
    assert receipt["deployed"] is False
    assert receipt["trading_authorized"] is False
    assert receipt["owner_paging_active"] is False
    assert receipt["requires_independent_deployment_authorization"] is True
    assert {p: p.read_bytes() for p in originals} == originals
    assert (
        main(
            [
                "--private-report",
                str(private),
                "--projection-dir",
                str(public),
                "--as-of",
                now.isoformat(),
                "--v1-wallet-health",
                str(v1),
                "--private-binding",
                str(binding),
                "--publisher-public-key",
                str(public_key),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["private_assessment_sha256"] == receipt["private_assessment_sha256"]
    assert {p: p.read_bytes() for p in originals} == originals


def test_release_refuses_stale_private_mismatch_and_nondurable_modes(tmp_path, capsys):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    public = tmp_path / "public"
    public.mkdir()
    now = datetime.now(UTC)
    report = seal(assessment().model_copy(update={"as_of": now, "created_at": now}))
    other = seal(
        assessment().model_copy(
            update={
                "as_of": now,
                "created_at": now,
                "campaign": assessment().campaign.model_copy(update={"campaign_id": "different"}),
            }
        )
    )
    private = root / "one.json"
    publish_private(report, private)
    publish_redacted(public, project(other, published_at=now))
    signer = Ed25519PrivateKey.generate()
    private_other = root / "other.json"
    publish_private(other, private_other)
    binding = root / "signed-publication.json"
    create_private_binding(
        private_other,
        public,
        private_binding_path=binding,
        publisher_alias="track-b-test-owner",
        signer=signer,
    )
    public_key = root / "publisher-key.raw"
    public_key.write_bytes(signer.public_key().public_bytes_raw())
    v1 = public / "wallet-health.json"
    v1.write_text(json.dumps({"schema": "wallet_health_grafana_v1"}))
    with pytest.raises(ValueError, match="PRIVATE_PUBLICATION_BINDING_ORIGINAL_MISMATCH"):
        attest(
            private,
            public,
            as_of=now,
            wallet_health_v1=v1,
            private_binding=binding,
            publisher_public_key=signer.public_key(),
        )
    assert (
        main(
            [
                "--private-report",
                str(private),
                "--projection-dir",
                str(public),
                "--as-of",
                now.isoformat(),
                "--v1-wallet-health",
                str(v1),
                "--private-binding",
                str(binding),
                "--publisher-public-key",
                str(public_key),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "CANDIDATE_REJECTED"
    publish_redacted(public, project(report, published_at=now + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="STALE|FUTURE"):
        attest(
            private,
            public,
            as_of=now + timedelta(hours=1),
            wallet_health_v1=v1,
            private_binding=binding,
            publisher_public_key=signer.public_key(),
        )
    import os

    os.chmod(root, 0o755)
    with pytest.raises(ValueError, match="PRIVATE_ASSESSMENT_DIRECTORY"):
        attest(
            private,
            public,
            as_of=now + timedelta(seconds=1),
            wallet_health_v1=v1,
            private_binding=binding,
            publisher_public_key=signer.public_key(),
        )
