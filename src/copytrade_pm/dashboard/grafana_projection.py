"""Fixed, read-only HTTP gateway for *published* operational evidence.

The HTTP process does not create or import DashboardReader, access financial
journals, query private SQLite, or invoke publisher code. For each HTTP request
it reads only one pre-published, hash-checked file from a read-only mount.
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from datetime import UTC, datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    from .adapter import DashboardReader

ALLOWED_PATH = "/v1/account-risk"
FIXTURE_PATH = "/v1/fixture-states"
HEALTH_PATH = "/v1/wallet-health"
STRATEGY_HEALTH_PATH = "/v1/strategy-health"
MAX_BYTES = 131_072


def build_projection(
    reader: "DashboardReader", *, clock: Callable[[], datetime] | None = None
) -> dict:
    """Publisher-only adapter. The HTTP gateway never calls this function."""
    from .adapter import safe_text, safe_decimal

    snapshot = reader.overview()
    sources = snapshot["sources"]
    risk, status, broker = (sources[name] for name in ("risk", "status", "broker"))
    status_data = status.get("data") if status["status"] in {"VERIFIED", "STALE"} else None
    broker_data = broker.get("data") if broker["status"] == "VERIFIED" else None
    status_data = status_data if isinstance(status_data, dict) else {}
    broker_data = broker_data if isinstance(broker_data, dict) else {}

    def row(name: str, value: object, grade: str, source: dict) -> dict:
        if value is not None and name in {
            "Account equity",
            "Account headroom",
            "Daily headroom",
            "Trailing headroom",
        }:
            value = safe_decimal(value)
        elif value is not None:
            value = safe_text(value, 96)
        if value is None and grade == "VERIFIED":
            grade = "UNKNOWN"
        return {
            "metric": name,
            "value": value,
            "grade": grade,
            "authority": source.get("authority", "UNKNOWN"),
            "source_observed_at": source.get("source_observed_at"),
            "captured_at": source.get("captured_at"),
            "retrieved_at": source.get("retrieved_at"),
            "revision": source.get("revision"),
            "journal_sequence": source.get("journal_sequence"),
            "account_binding_sha": source.get("account_binding_sha"),
            "evidence_error": source.get("error_code"),
        }

    metrics = snapshot["metrics"]
    rows = [
        row("Guardian state", status_data.get("state"), status["status"], status),
        row("Broker certainty", broker_data.get("certainty"), broker["status"], broker),
    ]
    for key, label in (
        ("equity", "Account equity"),
        ("headroom", "Account headroom"),
        ("daily_headroom", "Daily headroom"),
        ("trailing_headroom", "Trailing headroom"),
    ):
        metric = metrics[key]
        rows.append(row(label, metric["value"], metric["status"], risk))
    rows.append(
        row(
            "Portfolio membership",
            None,
            "UNKNOWN",
            {
                "authority": "installed-release-and-Guardian-observer",
                "retrieved_at": snapshot["retrieved_at"],
                "error_code": snapshot["membership_authority"],
            },
        )
    )
    incidents = [
        {"code": safe_text(x, 96), "priority": "REPORTED"}
        for x in snapshot.get("incidents", [])[:40]
        if safe_text(x, 96)
    ]
    from .grafana_capabilities import build_capabilities, qualify_capabilities
    from .evidence_plane import parse_utc

    # Capture all independent reads first. Publisher generation is the end of
    # this bounded read cycle, never the timestamp of its first overview read.
    capabilities = build_capabilities(reader)
    generated = clock() if clock is not None else parse_utc(snapshot["retrieved_at"])
    capabilities = qualify_capabilities(capabilities, asof=generated)
    return {
        "capabilities": capabilities,
        "schema": "grafana_account_risk_v1",
        "generated_at": generated.isoformat(),
        "coverage": "VERIFIED" if all(r["grade"] == "VERIFIED" for r in rows) else "INCOMPLETE",
        "synthetic": False,
        "trading_authorized": False,
        "metrics": rows,
        "incidents": incidents,
        "evidence_note": "Only publisher-validated evidence. No viewer trading authority.",
    }


def create_app(
    *,
    token: str,
    snapshot_dir: Path,
    allowed_host: str = "projection",
    allow_fixture: bool = False,
) -> Starlette:
    if not isinstance(token, str) or not 32 <= len(token) <= 512:
        raise ValueError("GRAFANA_PROJECTION_TOKEN_REQUIRES_32_TO_512_CHARS")
    if any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("GRAFANA_PROJECTION_TOKEN_INVALID")
    if allowed_host not in {"projection", "localhost"}:
        raise ValueError("GRAFANA_PROJECTION_UNAPPROVED_HOST")
    if not isinstance(snapshot_dir, Path) or not snapshot_dir.is_absolute():
        raise ValueError("GRAFANA_PROJECTION_ABSOLUTE_SNAPSHOT_DIR_REQUIRED")
    from .evidence_plane import read_generation, no_evidence, EvidenceInvalid

    async def fixed_read(request: Request) -> Response:
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            return JSONResponse({"error": "ACCESS_DENIED"}, status_code=403)
        if request.headers.get("transfer-encoding") or request.headers.get(
            "content-length"
        ) not in (None, "0"):
            return JSONResponse({"error": "BODY_NOT_ALLOWED"}, status_code=400)
        if request.query_params:
            return JSONResponse({"error": "QUERY_NOT_SUPPORTED"}, status_code=400)
        if request.headers.get("host", "").split(":")[0] not in {
            allowed_host,
            "127.0.0.1" if allowed_host == "localhost" else allowed_host,
        }:
            return JSONResponse({"error": "HOST_NOT_ALLOWED"}, status_code=403)
        if request.url.path == HEALTH_PATH:
            from copytrade_pm.wallet_health_projection import read as read_health

            try:
                result = read_health(snapshot_dir, now=datetime.now().astimezone())
            except OSError, ValueError, KeyError, TypeError, UnicodeDecodeError:
                return JSONResponse({"error": "HEALTH_EVIDENCE_UNAVAILABLE"}, status_code=503)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        if request.url.path == STRATEGY_HEALTH_PATH:
            from copytrade_pm.strategy_health_projection import read as read_strategy_health

            try:
                result = read_strategy_health(snapshot_dir, now=datetime.now(UTC))
            except OSError, ValueError, KeyError, TypeError, UnicodeDecodeError:
                return JSONResponse(
                    {"error": "STRATEGY_HEALTH_EVIDENCE_UNAVAILABLE"}, status_code=503
                )
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        name = "fixture-states.json" if request.url.path == FIXTURE_PATH else "account-risk.json"
        try:
            result = read_generation(snapshot_dir, name=name)
        except EvidenceInvalid as exc:
            cause = str(exc)
            result = no_evidence(
                cause
                if cause in {"EVIDENCE_UNAVAILABLE", "EVIDENCE_CORRUPT"}
                else "EVIDENCE_CORRUPT"
            )
        # Grafana Stat requires a numeric field for dependable reduction. This
        # code is a fixed presentation ordinal, not financial evidence or a
        # health computation. It is derived only from the validated grade.
        grades = {
            "VERIFIED": 1,
            "DEGRADED": 2,
            "STALE": 3,
            "BLOCKED": 4,
            "UNKNOWN": 5,
            "UNAVAILABLE": 6,
        }
        for metric in result["metrics"]:
            metric["evidence_code"] = grades[metric["grade"]]
            # Observed state is not the same as verification of its source.
            # In particular: a VERIFIED report of HALTED or UNKNOWN must
            # never produce a green/healthy headline.
            if metric["grade"] == "VERIFIED":
                if metric["metric"] == "Guardian state":
                    metric["evidence_code"] = {
                        "HALTED": 11,
                        "RUNNING": 12,
                        "STANDBY": 13,
                        "NO_TRADE": 14,
                        "BLOCKED": 15,
                    }.get(metric["value"], 16)
                elif metric["metric"] == "Broker certainty":
                    metric["evidence_code"] = {
                        "RECONCILED": 21,
                        "DIVERGENT": 22,
                        "NOT_RECONCILED": 22,
                        "STALE": 3,
                        "UNKNOWN": 5,
                    }.get(metric["value"], 23)
        # Independent Grafana-managed alert evaluation consumes validated,
        # gateway-derived numeric failure flags. These are presentation
        # indicators, never evidence of Guardian financial health.
        published_age = result.get("publication_age_seconds")
        capabilities = result.get("capabilities") or {}
        from .grafana_capabilities import operational_incident
        from .evidence_plane import FINANCE

        finance = [r for r in result["metrics"] if r["metric"] in FINANCE]
        # Account membership is optional presentation context, not a fifth
        # critical finance metric. Missing optional operational sources are not incidents.
        result["monitoring"] = {
            "generation_fault": int(
                not isinstance(published_age, (int, float))
                or published_age > 45
                or result.get("generation_sha256") is None
            ),
            "account_evidence_fault": int(any(r["grade"] in {"STALE", "BLOCKED"} for r in finance)),
            "operational_evidence_fault": int(operational_incident(capabilities)),
        }
        payload = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
        if len(payload) > MAX_BYTES:
            return JSONResponse({"error": "PROJECTION_TOO_LARGE"}, status_code=503)
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Evidence-Coverage": result["coverage"],
            },
        )

    routes = [
        Route(ALLOWED_PATH, fixed_read, methods=["GET"]),
        Route(HEALTH_PATH, fixed_read, methods=["GET"]),
        Route(STRATEGY_HEALTH_PATH, fixed_read, methods=["GET"]),
    ]
    if allow_fixture:
        routes.append(Route(FIXTURE_PATH, fixed_read, methods=["GET"]))
    return Starlette(routes=routes)


def app_from_environment() -> Starlette:
    token = os.environ.get("GRAFANA_PROJECTION_TOKEN", "")
    directory = Path(os.environ.get("GRAFANA_EVIDENCE_ROOT", "/evidence"))
    return create_app(
        token=token,
        snapshot_dir=directory,
        allowed_host="projection",
        allow_fixture=os.environ.get("GRAFANA_STAGING_FIXTURES", "") == "1",
    )


class _LazyApp:
    def __init__(self) -> None:
        self.instance = None

    async def __call__(self, scope, receive, send) -> None:
        if self.instance is None:
            self.instance = app_from_environment()
        await self.instance(scope, receive, send)


app = _LazyApp()
