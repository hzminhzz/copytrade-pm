"""One-way evidence plane and HTTP gateway contract / adversarial tests."""

from __future__ import annotations

# Optional-dependency guards must precede imports of the HTTP gateway.
# ruff: noqa: E402

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx", reason="dashboard optional extra")
pytest.importorskip("starlette", reason="dashboard optional extra")

from copytrade_pm.dashboard import evidence_plane as ep
from copytrade_pm.dashboard.grafana_projection import (
    build_projection,
    create_app,
    ALLOWED_PATH,
    FIXTURE_PATH,
)

TOKEN = "x" * 48
T0 = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def source(grade="VERIFIED", **kwargs):
    return {
        "authority": "prop-production.operator",
        "status": grade,
        "source_observed_at": T0.isoformat(),
        "captured_at": T0.isoformat(),
        "retrieved_at": T0.isoformat(),
        "revision": "a" * 64,
        "journal_sequence": 3,
        "account_binding_sha": "d" * 64,
        "error_code": None,
        "data": {},
        **kwargs,
    }


def snapshot(*, value="0", grade="VERIFIED", source_grade="VERIFIED"):
    return {
        "retrieved_at": T0.isoformat(),
        "sources": {
            "status": source(data={"state": "HALTED", "halts": ["BROKER_STALE"]}),
            "broker": source(data={"certainty": "UNKNOWN"}),
            "risk": source(source_grade),
        },
        "metrics": {
            "equity": {"value": value, "status": grade},
            "headroom": {"value": "12.50" if grade == "VERIFIED" else None, "status": grade},
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


def produce(directory: Path, reader: Reader | None = None, *, now=T0):
    reader = reader or Reader()
    blob = ep.publish_once(directory, reader=reader, clock=lambda: now)
    return reader, blob


def test_zero_vs_missing_and_authority_preserved(tmp_path):
    reader, raw = produce(tmp_path)
    assert reader.calls == 1
    assert len(raw) < ep.MAX_SIZE
    published = ep.read_generation(tmp_path, now=T0)
    by_name = {r["metric"]: r for r in published["metrics"]}
    assert by_name["Account equity"]["value"] == "0"
    assert by_name["Account equity"]["grade"] == "VERIFIED"
    assert by_name["Daily headroom"]["value"] is None
    assert by_name["Daily headroom"]["grade"] == "UNKNOWN"
    assert by_name["Account headroom"]["value"] == "12.50"
    assert by_name["Account equity"]["journal_sequence"] == 3
    assert by_name["Account equity"]["revision"] == "a" * 64
    assert published["trading_authorized"] is False
    assert published["synthetic"] is False
    assert published["incidents"] == [{"code": "BROKER_STALE", "priority": "REPORTED"}]


@pytest.mark.parametrize("grade", ["BLOCKED", "UNAVAILABLE", "STALE", "UNKNOWN", "DEGRADED"])
def test_unverified_finance_never_appears_as_zero(tmp_path, grade):
    produce(tmp_path, Reader(snapshot(value=None, grade=grade, source_grade=grade)))
    result = ep.read_generation(tmp_path, now=T0)
    metric = next(r for r in result["metrics"] if r["metric"] == "Account equity")
    assert metric["value"] is None
    assert metric["grade"] == grade
    assert result["coverage"] == "INCOMPLETE"


@pytest.mark.parametrize(
    "invalid",
    ["future_time", "bad_decimal", "unverified_finance", "unknown_metric", "missing_grade"],
)
def test_publisher_blocks_invalid_projection(invalid):
    data = build_projection(Reader())
    if invalid == "future_time":
        data["generated_at"] = (T0 + timedelta(minutes=1)).isoformat()
    elif invalid == "bad_decimal":
        data["metrics"][2]["value"] = "not money"
    elif invalid == "unverified_finance":
        data["metrics"][2]["grade"] = "UNAVAILABLE"
    elif invalid == "unknown_metric":
        data["metrics"][0]["metric"] = "Execute order"
    else:
        data["metrics"][0]["grade"] = "HEALTHY"
    with pytest.raises(ep.EvidenceInvalid):
        ep.encode_generation(data, now=T0)


def test_stale_publication_downgrades_verified_finance(tmp_path):
    produce(tmp_path)
    item = ep.read_generation(tmp_path, now=T0 + timedelta(seconds=ep.MAX_AGE_SECONDS + 2))
    metric = next(r for r in item["metrics"] if r["metric"] == "Account equity")
    assert metric["value"] == "0"  # last observed, not a fresh value or null
    assert metric["grade"] == "STALE"
    assert metric["evidence_error"] == "EVIDENCE_AGE_EXCEEDED"
    assert item["coverage"] == "INCOMPLETE"


def test_corruption_and_symlink_do_not_read_outside(tmp_path):
    produce(tmp_path)
    target = tmp_path / "account-risk.json"
    raw = json.loads(target.read_bytes())
    raw["projection"]["metrics"][2]["value"] = "10000"
    target.write_text(json.dumps(raw))
    with pytest.raises(ep.EvidenceInvalid, match="EVIDENCE_CORRUPT"):
        ep.read_generation(tmp_path, now=T0)
    target.unlink()
    outside = tmp_path / "private.txt"
    outside.write_text("SENSITIVE_PRIVATE_FILE")
    target.symlink_to(outside)
    with pytest.raises(ep.EvidenceInvalid, match="EVIDENCE_UNAVAILABLE"):
        ep.read_generation(tmp_path, now=T0)


def test_atomic_generations_under_concurrent_read(tmp_path):
    produce(tmp_path)
    other = Reader(snapshot(value="2.00"))
    failures = []

    def writer():
        for i in range(30):
            ep.publish_once(tmp_path, reader=other, clock=lambda: T0 + timedelta(milliseconds=i))

    def read_many():
        for i in range(70):
            try:
                result = ep.read_generation(tmp_path, now=T0 + timedelta(seconds=2))
                value = result["metrics"][2]["value"]
                assert value in {"0", "2.00"}
                assert len(result["generation_sha256"]) == 64
            except Exception as exc:
                failures.append(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(writer)] + [pool.submit(read_many) for _ in range(3)]
        for task in tasks:
            task.result()
    assert not failures, failures[:2]


def test_response_on_no_evidence_fails_closed(tmp_path):
    answer = ep.no_evidence("EVIDENCE_UNAVAILABLE", now=T0)
    assert answer["metrics"][2]["grade"] == "UNAVAILABLE"
    assert answer["metrics"][2]["value"] is None
    assert answer["coverage"] == "INCOMPLETE"


def test_http_reads_only_published_snapshot(tmp_path, monkeypatch):
    reader, _ = produce(tmp_path)
    from copytrade_pm.dashboard import adapter

    def forbidden(*_args, **_kwargs):
        raise AssertionError("HTTP_INVOKED_AUTHORITY_READER")

    monkeypatch.setattr(adapter.DashboardReader, "overview", forbidden)

    async def exercise():
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(
                    token=TOKEN,
                    snapshot_dir=tmp_path,
                    allowed_host="localhost",
                )
            ),
            base_url="http://localhost",
        )
        async with client:
            for method, path, headers, expected in [
                ("GET", ALLOWED_PATH, {}, 403),
                ("GET", ALLOWED_PATH, {"Authorization": "Bearer wrong"}, 403),
                (
                    "GET",
                    ALLOWED_PATH + "?path=/etc/passwd",
                    {"Authorization": f"Bearer {TOKEN}"},
                    400,
                ),
                ("GET", "/etc/passwd", {"Authorization": f"Bearer {TOKEN}"}, 404),
                ("GET", FIXTURE_PATH, {"Authorization": f"Bearer {TOKEN}"}, 404),
                (
                    "GET",
                    ALLOWED_PATH,
                    {"Authorization": f"Bearer {TOKEN}", "Host": "external.host"},
                    403,
                ),
                ("POST", ALLOWED_PATH, {"Authorization": f"Bearer {TOKEN}"}, 405),
                ("PUT", ALLOWED_PATH, {"Authorization": f"Bearer {TOKEN}"}, 405),
                ("PATCH", ALLOWED_PATH, {"Authorization": f"Bearer {TOKEN}"}, 405),
                ("DELETE", ALLOWED_PATH, {"Authorization": f"Bearer {TOKEN}"}, 405),
                ("GET", ALLOWED_PATH, {"Authorization": f"Bearer {TOKEN}"}, 200),
            ]:
                response = await client.request(method, path, headers=headers)
                assert response.status_code == expected, (method, path, response.text)
            answer = response.json()
            assert answer["metrics"][2]["value"] == "0"
            assert answer["published_at"] is not None

    asyncio.run(exercise())
    assert reader.calls == 1  # exactly one publisher read; zero HTTP-triggered reads


def test_gateway_missing_generation_returns_nonhealthy(tmp_path):
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="localhost")
            ),
            base_url="http://localhost",
        ) as client:
            response = await client.get(ALLOWED_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
            assert response.status_code == 200
            assert response.json()["coverage"] == "INCOMPLETE"
            assert response.json()["metrics"][2]["value"] is None
            assert response.json()["metrics"][2]["grade"] == "UNAVAILABLE"

    asyncio.run(exercise())


def test_gateway_concurrency_and_cancellation(tmp_path):
    reader, _ = produce(tmp_path)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="localhost")
            ),
            base_url="http://localhost",
        ) as client:
            header = {"Authorization": f"Bearer {TOKEN}"}
            results = await asyncio.gather(
                *[client.get(ALLOWED_PATH, headers=header) for _ in range(50)]
            )
            assert all(r.status_code == 200 for r in results)
            task = asyncio.create_task(client.get(ALLOWED_PATH, headers=header))
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(exercise())
    assert reader.calls == 1


def test_synthetic_fixture_is_separate_and_explicit(tmp_path):
    fixture = ep.fixture_projection(now=T0)
    assert fixture["synthetic"] is True
    assert [x["grade"] for x in fixture["metrics"]] == [
        "VERIFIED",
        "VERIFIED",
        "VERIFIED",
        "STALE",
        "BLOCKED",
        "UNAVAILABLE",
        "UNKNOWN",
    ]
    assert fixture["metrics"][2]["value"] == "0"
    assert len(fixture["history"]) == 5
    payload = ep.encode_generation(fixture, now=T0)
    ep.publish_atomic(tmp_path, payload, name="fixture-states.json")
    observed = ep.read_generation(tmp_path, name="fixture-states.json", now=T0)
    assert observed["synthetic"] is True
    assert observed["history"][-1]["grade"] == "UNAVAILABLE"
    assert observed["evidence_note"].startswith("SYNTHETIC")

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(
                    token=TOKEN,
                    snapshot_dir=tmp_path,
                    allowed_host="localhost",
                    allow_fixture=True,
                )
            ),
            base_url="http://localhost",
        ) as client:
            reply = await client.get(FIXTURE_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
            assert reply.status_code == 200
            assert reply.json()["synthetic"] is True
            real = await client.get(ALLOWED_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
            assert real.json()["synthetic"] is False
            assert real.json()["metrics"][2]["value"] is None

    asyncio.run(exercise())


def test_account_binding_release_and_timestamps_fail_closed():
    for mismatch in ("account", "release", "sequence", "timestamp"):
        value = build_projection(Reader())
        if mismatch == "account":
            value["metrics"][2]["account_binding_sha"] = "b" * 64
        elif mismatch == "release":
            value["metrics"][2]["revision"] = "c" * 64
        elif mismatch == "sequence":
            value["metrics"][2]["journal_sequence"] = 4
        else:
            value["metrics"][2]["source_observed_at"] = (T0 + timedelta(seconds=2)).isoformat()
        with pytest.raises(ep.EvidenceInvalid):
            ep.encode_generation(value, now=T0)


def test_oversized_http_get_is_rejected_without_read(tmp_path):
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(
                    token=TOKEN,
                    snapshot_dir=tmp_path,
                    allowed_host="localhost",
                )
            ),
            base_url="http://localhost",
        ) as client:
            r = await client.request(
                "GET",
                ALLOWED_PATH,
                content=b"x" * 50000,
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert r.status_code == 400
            assert "BODY_NOT_ALLOWED" in r.text

    asyncio.run(exercise())


def test_reported_halt_and_unknown_broker_are_not_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(ep, "_utc_now", lambda: T0)
    produce(tmp_path)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="localhost")
            ),
            base_url="http://localhost",
        ) as client:
            response = await client.get(ALLOWED_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
            assert response.status_code == 200
            metrics = response.json()["metrics"]
            # VALIDATED source evidence is not the same as a safe underlying state.
            assert metrics[0]["grade"] == "VERIFIED"
            assert metrics[0]["value"] == "HALTED"
            assert metrics[0]["evidence_code"] == 11
            assert metrics[1]["grade"] == "VERIFIED"
            assert metrics[1]["value"] == "UNKNOWN"
            assert metrics[1]["evidence_code"] == 5

    asyncio.run(exercise())


def test_token_validation(tmp_path):
    with pytest.raises(ValueError):
        create_app(token="short", snapshot_dir=tmp_path)
    with pytest.raises(ValueError):
        create_app(token="z" * 32 + "\n", snapshot_dir=tmp_path)
    with pytest.raises(ValueError):
        create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="attacker")
