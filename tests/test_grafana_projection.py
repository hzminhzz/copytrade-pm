"""Grafana HTTP projection contracts; all data originates from controlled fixtures."""
import asyncio

import httpx
import pytest

from copytrade_pm.dashboard.grafana_projection import (
    build_projection, create_app,
)

TOKEN = "x" * 48
NOW = "2026-11-07T10:00:00+00:00"


def source(status="VERIFIED", **kwargs):
    return {
        "authority": "prop-production.operator",
        "status": status,
        "source_observed_at": NOW,
        "captured_at": NOW,
        "retrieved_at": NOW,
        "revision": "a" * 64,
        "journal_sequence": 3,
        "error_code": None,
        "data": {},
        **kwargs,
    }


def snapshot(*, value="0", grade="VERIFIED", source_grade="VERIFIED"):
    risk = source(source_grade)
    return {
        "retrieved_at": NOW,
        "sources": {
            "status": source(data={"state": "HALTED", "halts": ["BROKER_STALE"]}),
            "broker": source(data={"certainty": "UNKNOWN"}),
            "risk": risk,
        },
        "metrics": {
            "equity": {"value": value, "status": grade},
            "headroom": {"value": "12.50", "status": grade},
            "daily_headroom": {"value": None, "status": "UNKNOWN"},
            "trailing_headroom": {"value": None, "status": "UNKNOWN"},
        },
        "incidents": ["BROKER_STALE"],
        "membership_authority": "UNKNOWN_UNTIL_VERIFIED_INSTALLED_AND_RUNTIME_RELEASE",
    }


class Reader:
    def __init__(self, data=None):
        self.data = data or snapshot()
        self.calls = 0

    def overview(self):
        self.calls += 1
        return self.data


def test_decimal_zero_and_missing_are_distinct():
    payload = build_projection(Reader())
    by_name = {item["metric"]: item for item in payload["metrics"]}
    assert by_name["Account equity"]["value"] == "0"
    assert by_name["Account equity"]["grade"] == "VERIFIED"
    assert by_name["Daily headroom"]["value"] is None
    assert by_name["Daily headroom"]["grade"] == "UNKNOWN"
    assert payload["trading_authorized"] is False
    assert payload["synthetic"] is False
    assert payload["incidents"] == [{"code": "BROKER_STALE", "priority": "REPORTED"}]


@pytest.mark.parametrize("grade", ["BLOCKED", "UNAVAILABLE", "STALE", "UNKNOWN", "DEGRADED"])
def test_financial_uncertainty_never_implies_zero(grade):
    data = snapshot(value=None, grade=grade, source_grade=grade)
    payload = build_projection(Reader(data))
    value = next(x for x in payload["metrics"] if x["metric"] == "Account equity")
    assert value["value"] is None
    assert value["grade"] == grade
    assert payload["coverage"] == "INCOMPLETE"


def test_http_auth_and_method_scope():
    asyncio.run(check_http_auth_and_method_scope())


async def check_http_auth_and_method_scope():
    reader = Reader()
    transport = httpx.ASGITransport(app=create_app(token=TOKEN, reader=reader))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for method, path, options, expected in [
            ("GET", "/v1/account-risk", {}, 403),
            ("GET", "/v1/account-risk", {"headers": {"Authorization": "Bearer bad"}}, 403),
            ("GET", "/v1/account-risk?path=/etc/passwd", {"headers": {"Authorization": f"Bearer {TOKEN}"}}, 400),
            ("POST", "/v1/account-risk", {"headers": {"Authorization": f"Bearer {TOKEN}"}}, 405),
            ("GET", "/etc/passwd", {"headers": {"Authorization": f"Bearer {TOKEN}"}}, 404),
            ("GET", "/v1/account-risk", {"headers": {"Authorization": f"Bearer {TOKEN}", "Host": "external.host"}}, 403),
            ("GET", "/v1/account-risk", {"headers": {"Authorization": f"Bearer {TOKEN}"}}, 200),
        ]:
            response = await client.request(method, path, **options)
            assert response.status_code == expected, (method, path, response.text)
        assert reader.calls == 1


def test_extraneous_methods_and_large_output_fail_closed():
    from copytrade_pm.dashboard.grafana_projection import MAX_BYTES

    oversize = snapshot()
    oversize["metrics"]["equity"]["value"] = "9" * MAX_BYTES
    reader = Reader(oversize)

    async def exercise():
        transport = httpx.ASGITransport(app=create_app(token=TOKEN, reader=reader))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            request_headers = {"Authorization": f"Bearer {TOKEN}"}
            too_large = await client.get("/v1/account-risk", headers=request_headers)
            assert too_large.status_code == 503
            assert "PROJECTION_TOO_LARGE" in too_large.text
            for method in ("PUT", "PATCH", "DELETE"):
                response = await client.request(method, "/v1/account-risk", headers=request_headers)
                assert response.status_code == 405
            assert reader.calls == 1

    asyncio.run(exercise())


def test_token_validation():
    with pytest.raises(ValueError):
        create_app(token="short")
    with pytest.raises(ValueError):
        create_app(token="z" * 32 + "\n")
