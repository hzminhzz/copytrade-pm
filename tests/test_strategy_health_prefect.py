"""Track B optional Prefect adapter: original private-report idempotency and authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import errno
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from copytrade_pm.strategy_health import (
    Campaign,
    StrategyAssessment,
    StrategyScope,
    WeeklyLook,
    canonical_report,
    publish,
    read,
    seal,
)
from copytrade_pm.strategy_health_jobs import (
    HealthJob,
    HealthManifest,
    output_receipt_json,
    read_manifest,
    run_private_job,
    run_without_prefect,
)

NOW = datetime(2026, 11, 10, 8, tzinfo=UTC)
H = "a" * 64


@pytest.fixture(scope="module", autouse=True)
def _prefect_test_logging():
    # Prefect's short-lived loopback server can log during pytest capture
    # shutdown; keep test-only logging handlers from using closed streams.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PREFECT_LOGGING_LEVEL", "CRITICAL")
        patch.setenv("PREFECT_LOGGING_INTERNAL_LEVEL", "CRITICAL")
        yield


def _private(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    path.chmod(0o600)
    return sha256(data).hexdigest()


def _fixture(tmp_path: Path, *, selected: bool = True, look: bool = False):
    input_dir = tmp_path / "original"
    output_dir = tmp_path / "track-b-prefect-staging"
    input_dir.mkdir(mode=0o700)
    output_dir.mkdir(mode=0o700)
    scope = StrategyScope(
        tier="SELECTED" if selected else "DISCOVERY",
        source_alias="WALLET-PRIVATE-DO-NOT-LOG",
        source_account_sha256=H,
        registry_asof_sha256=H,
        **(
            {
                "selected_portfolio": "P1",
                "selection_seal_sha256": H,
                "dex_census_sha256": H,
                "selection_known_at": NOW - timedelta(days=2),
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "k_version": "k1",
                "k_policy_sha256": H,
                "frozen_k": Decimal("0.125"),
            }
            if selected
            else {}
        ),
    )
    scheduled_at = NOW - timedelta(days=1)
    campaign = Campaign(
        campaign_id="research-campaign",
        trial_family_sha256=H,
        frozen_at=NOW - timedelta(days=3),
        trial_count=3,
        rejected_trials=1,
        weekly_look_ids=("week1",) if look else (),
        weekly_look_schedule=(scheduled_at,) if look else (),
    )
    report = seal(StrategyAssessment(created_at=NOW, as_of=NOW, strategy=scope, campaign=campaign))
    private_report_path = input_dir / "assessment.json"
    publish(report, private_report_path)

    data = {
        "report_path": private_report_path,
        "report_sha256": sha256(canonical_report(report)).hexdigest(),
    }
    if look:
        weekly = WeeklyLook(
            look_id="week1",
            scheduled_at=scheduled_at,
            performed_at=NOW,
            evidence_sha256="b" * 64,
        )
        path = input_dir / "weekly.json"
        data.update(
            weekly_look_path=path,
            weekly_look_sha256=_private(path, weekly.model_dump_json().encode()),
        )
    job = HealthJob.model_validate(data)
    manifest_path = input_dir / "manifest.json"
    manifest = HealthManifest(output_dir=output_dir, jobs=(job,))
    manifest_sha = _private(manifest_path, manifest.model_dump_json(by_alias=True).encode())
    return manifest_path, manifest_sha, output_dir, job


def test_private_report_replay_is_content_addressed_and_never_claims_authority(tmp_path):
    manifest_path, sha, output, job = _fixture(tmp_path)
    first = run_without_prefect(manifest_path, sha)[0]
    second = run_without_prefect(manifest_path, sha)[0]
    assert first.publication == "PUBLISHED"
    assert second.publication == "EXISTING_VERIFIED"
    assert first.report_sha256 == second.report_sha256
    assert first.output_sha256 == second.output_sha256
    assert first.trading_authorized is False
    assert first.source_finance_authenticated is False
    assert first.scientifically_qualified is False
    assert len(list(output.iterdir())) == 1
    target = output / (first.output_sha256 + ".json")
    assert sha256(target.read_bytes()).hexdigest() == first.output_sha256
    assert target.stat().st_mode & 0o777 == 0o600
    report = read(target)
    assert {x.window_days for x in report.windows} == {7, 30, 90}
    assert report.advisory.status == "INSUFFICIENT_EVIDENCE"
    assert job.report_sha256 != first.output_sha256
    assert "WALLET-PRIVATE-DO-NOT-LOG" not in json.dumps(output_receipt_json(first))


def test_weekly_look_is_persisted_as_unqualified_provisional_assessment(tmp_path):
    path, sha, output, job = _fixture(tmp_path, look=True)
    result = run_private_job(job, output)
    report = read(output / (result.output_sha256 + ".json"))
    assert len(report.weekly_looks) == 1
    assert report.advisory.status == "INSUFFICIENT_EVIDENCE"
    assert "SELECTED_SOURCE_NOT_CONTINUOUS" in report.advisory.reasons
    assert report.scientifically_qualified is False
    assert result.publication == "PUBLISHED"
    assert read_manifest(path, sha).jobs == (job,)


def test_input_pin_or_private_permissions_fail_before_any_output(tmp_path):
    path, sha, output, job = _fixture(tmp_path)
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        read_manifest(path, "0" * 64)
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        run_private_job(job.model_copy(update={"report_sha256": "0" * 64}), output)
    assert not list(output.iterdir())
    os.chmod(job.report_path, 0o644)
    with pytest.raises(ValueError, match="PRIVATE_FILE_INVALID"):
        run_private_job(job, output)
    assert not list(output.iterdir())


def test_private_input_directory_must_be_owned_and_private(tmp_path):
    _, _, output, job = _fixture(tmp_path)
    job.report_path.parent.chmod(0o755)
    with pytest.raises(ValueError, match="PRIVATE_INPUT_DIRECTORY_INVALID"):
        run_private_job(job, output)
    assert not list(output.iterdir())


def test_crash_after_immutable_commit_resumes_without_duplicate(tmp_path, monkeypatch):
    from copytrade_pm import strategy_health_jobs

    _, _, output, job = _fixture(tmp_path)
    real = strategy_health_jobs.publish

    def simulated_crash(report, path):
        real(report, path)
        raise OSError("SIMULATED_PROCESS_DEATH_POST_COMMIT")

    monkeypatch.setattr(strategy_health_jobs, "publish", simulated_crash)
    with pytest.raises(OSError, match="SIMULATED_PROCESS_DEATH"):
        run_private_job(job, output)
    assert len(list(output.iterdir())) == 1
    monkeypatch.setattr(strategy_health_jobs, "publish", real)
    result = run_private_job(job, output)
    assert result.publication == "EXISTING_VERIFIED"
    assert len(list(output.iterdir())) == 1


def test_tampered_result_fails_closed_no_overwrite(tmp_path):
    _, _, output, job = _fixture(tmp_path)
    result = run_private_job(job, output)
    target = output / (result.output_sha256 + ".json")
    before = target.read_bytes()
    target.write_bytes(before.replace(b"research-campaign", b"forgedxx-campaign"))
    with pytest.raises(ValueError, match="REPORT|NONCANONICAL"):
        run_private_job(job, output)
    assert len(list(output.iterdir())) == 1


def test_protected_and_arbitrary_output_paths_are_rejected(tmp_path):
    _, _, output, job = _fixture(tmp_path)
    arbitrary = tmp_path / "arbitrary-output"
    arbitrary.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="OUTPUT_STAGING_ONLY"):
        run_private_job(job, arbitrary)
    protected = tmp_path / "prospective" / "track-b-prefect-staging"
    protected.parent.mkdir(mode=0o700)
    protected.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="OUTPUT_STAGING_ONLY"):
        run_private_job(job, protected)
    assert not list(output.iterdir())
    assert not list(protected.iterdir())


def test_manifest_duplicates_and_symlink_output_rejected(tmp_path):
    path, sha, output, job = _fixture(tmp_path)
    assert read_manifest(path, sha).jobs == (job,)
    with pytest.raises(ValueError, match="DUPLICATE_JOB"):
        HealthManifest(output_dir=output, jobs=(job, job))
    shortcut = tmp_path / "linked-staging"
    shortcut.symlink_to(output)
    with pytest.raises(ValueError, match="OUTPUT_SYMLINK"):
        run_private_job(job, shortcut)
    assert not list(output.iterdir())


def test_prefect_flow_executes_independent_tasks_without_exposing_wallet(tmp_path):
    pytest.importorskip("prefect")
    from copytrade_pm.strategy_health_prefect import run_prefect

    path, _, output, job = _fixture(tmp_path)
    other_input = read(job.report_path)
    changed = StrategyAssessment.model_validate(
        {
            **other_input.model_dump(),
            "report_sha256": "0" * 64,
            "strategy": other_input.strategy.model_copy(
                update={"source_alias": "SECOND-PRIVATE-DO-NOT-LOG"}
            ),
        }
    )
    second = seal(changed)
    other_path = job.report_path.parent / "second.json"
    publish(second, other_path)
    other_job = HealthJob(
        report_path=other_path,
        report_sha256=sha256(canonical_report(second)).hexdigest(),
    )
    manifest = HealthManifest(output_dir=output, jobs=(job, other_job))
    expected_sha = _private(path, manifest.model_dump_json(by_alias=True).encode())
    receipt = run_prefect(path, expected_sha)
    assert receipt["job_count"] == 2
    assert receipt["read_only"] is True
    assert receipt["trading_authorized"] is False
    assert receipt["scientifically_qualified"] is False
    assert [row["publication"] for row in receipt["reports"]] == ["PUBLISHED", "PUBLISHED"]
    assert len(list(output.iterdir())) == 2
    oracle = run_without_prefect(path, expected_sha)
    assert [item.output_sha256 for item in oracle] == [
        item["output_sha256"] for item in receipt["reports"]
    ]
    assert all(item.publication == "EXISTING_VERIFIED" for item in oracle)
    assert "WALLET-PRIVATE-DO-NOT-LOG" not in json.dumps(receipt)
    assert "SECOND-PRIVATE-DO-NOT-LOG" not in json.dumps(receipt)


def test_prefect_retries_transient_io_and_commits_once(tmp_path, monkeypatch):
    pytest.importorskip("prefect")
    from copytrade_pm import strategy_health_prefect
    from prefect.settings import PREFECT_SERVER_ANALYTICS_ENABLED

    path, sha, output, _ = _fixture(tmp_path)
    original = strategy_health_prefect.run_private_job
    attempts = []

    def fail_once(job, directory):
        assert PREFECT_SERVER_ANALYTICS_ENABLED.value() is False
        attempts.append(job.identity_sha256)
        if len(attempts) == 1:
            raise OSError(errno.EBUSY, "sensitive-path-should-not-be-logged")
        return original(job, directory)

    monkeypatch.setattr(strategy_health_prefect, "run_private_job", fail_once)
    result = strategy_health_prefect.run_prefect(path, sha)
    assert len(attempts) == 2
    assert result["reports"][0]["publication"] == "PUBLISHED"
    assert len(list(output.iterdir())) == 1


def test_prefect_remote_api_configuration_fails_closed(tmp_path):
    pytest.importorskip("prefect")
    from prefect.settings import PREFECT_API_URL, temporary_settings
    from copytrade_pm.strategy_health_prefect import run_prefect

    path, sha, output, _ = _fixture(tmp_path)
    with temporary_settings(updates={PREFECT_API_URL: "https://prefect.example.invalid/api"}):
        with pytest.raises(ValueError, match="REMOTE_PREFECT_API_DISABLED"):
            run_prefect(path, sha)
    assert not list(output.iterdir())
