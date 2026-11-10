"""Strategy-health v2 redacted projection and v1 HTTP isolation."""

from datetime import UTC, datetime, timedelta
import json

import pytest
from copytrade_pm.dashboard.grafana_projection import create_app
from copytrade_pm.strategy_health_projection import (
    project,
    publish,
    read,
    canonical,
    NAME,
)
from test_strategy_health_v2 import NOW, assessment
from copytrade_pm.strategy_health import seal

TestClient = pytest.importorskip("starlette.testclient").TestClient


TOKEN = "x" * 40


def _client(directory):
    return TestClient(
        create_app(token=TOKEN, snapshot_dir=directory, allowed_host="localhost"),
        base_url="http://localhost",
    )


def test_strategy_projection_aggregate_private_safe(tmp_path):
    payload = project(seal(assessment()), published_at=NOW)
    assert NAME == "strategy-health.json"
    assert b"S035" not in payload
    assert b"selected_portfolio" not in payload
    assert b"source_account_sha256" not in payload
    assert b"wallet_address" not in payload
    publish(tmp_path, payload)
    assert read(tmp_path, now=NOW)["opportunity_count"] == 0
    with _client(tmp_path) as client:
        uri = "/v1/strategy-health"
        assert client.get(uri).status_code == 403
        headers = {"authorization": "Bearer " + TOKEN}
        # Direct projection is stale versus actual wall time; this is correct fail-closed.
        assert client.get(uri, headers=headers).status_code == 503
        assert client.post(uri, headers=headers).status_code == 405
        assert client.put(uri, headers=headers).status_code == 405
        assert client.delete(uri, headers=headers).status_code == 405
        assert client.get(uri + "?write=true", headers=headers).status_code == 400
        assert client.get("/v1/wallet-health", headers=headers).status_code == 503
        assert client.get("/v1/unknown", headers=headers).status_code == 404


def test_projection_corrupt_leak_and_stale_fail_closed(tmp_path):
    payload = project(seal(assessment()), published_at=NOW)
    publish(tmp_path, payload)
    with pytest.raises(ValueError, match="STALE"):
        read(tmp_path, now=NOW + timedelta(hours=1))
    tamper = json.loads(payload)
    tamper["source_address"] = "0x" + "b" * 40
    tamper["generation_sha256"] = "0" * 64
    (tmp_path / NAME).write_bytes(canonical(tamper))
    with pytest.raises(ValueError, match="UNAPPROVED_FIELD"):
        read(tmp_path, now=NOW)


def test_projection_uses_current_publication_time(tmp_path):
    current = datetime.now(UTC)
    # Build a real current-asof report with the existing frozen campaign.
    source = assessment().model_copy(update={"as_of": current, "created_at": current})
    report = seal(source)
    payload = project(report, published_at=current)
    publish(tmp_path, payload)
    assert read(tmp_path, now=current)["schema"] == "strategy_health_grafana_v1"
    with _client(tmp_path) as client:
        headers = {"authorization": "Bearer " + TOKEN}
        response = client.get("/v1/strategy-health", headers=headers)
        assert response.status_code == 200
        assert response.json()["trading_authorized"] is False
        assert response.json()["assessability"] == "INSUFFICIENT_EVIDENCE"
