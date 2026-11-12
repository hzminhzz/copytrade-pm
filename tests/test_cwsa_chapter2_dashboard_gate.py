"""Authenticated deployed-endpoint proof must distinguish public copies and stale data."""

from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
import json

from copytrade_pm.pm_cwsa_chapter2_gate import (
    EXPECTED_PORTFOLIOS,
    _dashboard,
)

URL = "https://private.example/chapter2/evidence.json"
SHA = "a" * 40


class Response:
    status = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.data).encode()


def evidence(date):
    return {
        "schema": "cwsa_chapter2_evidence_projection_v1",
        "release_sha": SHA,
        "source_heads_sha256": "f" * 64,
        "generated_at": date.isoformat(),
        "portfolios": {
            pid: {"financial_admission": "BLOCKED_EVIDENCE"} for pid in EXPECTED_PORTFOLIOS
        },
        "trading_authorized": False,
    }


def test_missing_smoke_authentication_never_passes():
    assert _dashboard(URL, SHA, None).state == "BLOCKED_EVIDENCE"
    assert _dashboard("http://private.example", SHA, None).state == "FAIL"


def test_public_endpoint_fails_even_if_bearer_response_has_valid_json(tmp_path, monkeypatch):
    import copytrade_pm.pm_cwsa_chapter2_gate as gate

    key = tmp_path / "token"
    key.write_text("local-unit-test-secret")
    key.chmod(0o600)
    monkeypatch.setattr(
        gate, "urlopen", lambda request, timeout: Response(evidence(datetime.now(UTC)))
    )
    result = _dashboard(URL, SHA, key)
    assert result.state == "FAIL"
    assert result.detail == "DASHBOARD_PUBLIC_UNAUTHENTICATED_ACCESS"


def test_auth_boundary_and_lineage_pass_with_challenged_anonymous_request(tmp_path, monkeypatch):
    import copytrade_pm.pm_cwsa_chapter2_gate as gate

    key = tmp_path / "token"
    key.write_text("unit-test-secret")
    key.chmod(0o600)
    sample = evidence(datetime.now(UTC))

    def fake_get(request, timeout):
        if request.get_header("Authorization") == "Bearer unit-test-secret":
            return Response(sample)
        raise HTTPError(URL, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(gate, "urlopen", fake_get)
    assert _dashboard(URL, SHA, key).state == "PASS"
    sample["generated_at"] = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    assert _dashboard(URL, SHA, key).detail == "DEPLOYED_DASHBOARD_DATA_STALE"
    sample["generated_at"] = datetime.now(UTC).isoformat()
    sample["release_sha"] = "b" * 40
    assert _dashboard(URL, SHA, key).detail == "DEPLOYED_DASHBOARD_DATA_LINEAGE_MISMATCH"


def test_world_readable_token_fails_closed(tmp_path):
    token = tmp_path / "token"
    token.write_text("never-send")
    token.chmod(0o644)
    assert _dashboard(URL, SHA, token).state == "FAIL"
