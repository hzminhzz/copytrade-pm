"""Bounded, non-authoritative HTTP presentation of DashboardReader account risk.

No raw query, wallet lookup, financial mutation, or journal access is exposed.
Configure a private, randomly generated GRAFANA_PROJECTION_TOKEN and a loopback
listener. This boundary is *not* sufficient by itself to contain Infinity SSRF.
"""
from __future__ import annotations

import hmac
import json
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .adapter import DashboardReader

ALLOWED_PATH = "/v1/account-risk"
MAX_BYTES = 32768


def _rows(snapshot: dict) -> list[dict]:
    """A fixed, redacted schema: never serialize raw native account data."""
    sources = snapshot["sources"]
    risk = sources["risk"]
    status = sources["status"]
    broker = sources["broker"]
    status_data = status.get("data") if status["status"] in {"VERIFIED", "STALE"} else None
    broker_data = broker.get("data") if broker["status"] == "VERIFIED" else None
    status_data = status_data if isinstance(status_data, dict) else {}
    broker_data = broker_data if isinstance(broker_data, dict) else {}
    metrics = snapshot["metrics"]

    def row(name: str, value: object, grade: str, source: dict) -> dict:
        # String-only financial values: charts must not coerce missing to zero.
        return {
            "metric": name,
            "value": value,
            "grade": grade,
            "authority": source["authority"],
            "source_observed_at": source.get("source_observed_at"),
            "captured_at": source.get("captured_at"),
            "retrieved_at": source.get("retrieved_at"),
            "revision": source.get("revision"),
            "journal_sequence": source.get("journal_sequence"),
            "evidence_error": source.get("error_code"),
        }

    result = [
        row("Guardian state", status_data.get("state"), status["status"], status),
        row("Broker certainty", broker_data.get("certainty"), broker["status"], broker),
    ]
    for key, label in [
        ("equity", "Account equity"),
        ("headroom", "Account headroom"),
        ("daily_headroom", "Daily headroom"),
        ("trailing_headroom", "Trailing headroom"),
    ]:
        metric = metrics[key]
        result.append(row(label, metric["value"], metric["status"], risk))
    result.append(
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
    return result


def build_projection(reader: DashboardReader) -> dict:
    snapshot = reader.overview()
    rows = _rows(snapshot)
    incident_codes = [x for x in snapshot["incidents"] if isinstance(x, str)][:40]
    if any(item["grade"] != "VERIFIED" for item in rows):
        coverage = "INCOMPLETE"
    else:
        coverage = "VERIFIED"
    return {
        "schema": "grafana_account_risk_v1",
        "generated_at": snapshot["retrieved_at"],
        "coverage": coverage,
        "synthetic": False,
        "trading_authorized": False,
        "metrics": rows,
        "incidents": [{"code": code, "priority": "REPORTED"} for code in incident_codes],
        "evidence_note": (
            "Protected finance unavailable or unverified; absence of evidence "
            "is not evidence of healthy risk."
            if coverage != "VERIFIED"
            else "Source-certified snapshot; viewer cannot authorize trading."
        ),
    }


def create_app(
    *, token: str, reader: DashboardReader | None = None,
    allowed_host: str = "localhost",
) -> Starlette:
    if not isinstance(token, str) or len(token) < 32 or len(token) > 512:
        raise ValueError("GRAFANA_PROJECTION_TOKEN_REQUIRES_32_TO_512_CHARS")
    if any(ord(x) < 33 or ord(x) > 126 for x in token):
        raise ValueError("GRAFANA_PROJECTION_TOKEN_INVALID")
    if allowed_host not in {"localhost", "projection"}:
        raise ValueError("GRAFANA_PROJECTION_UNAPPROVED_HOST")
    native = reader or DashboardReader()

    async def account(request: Request) -> Response:
        authorization = request.headers.get("authorization", "")
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            return JSONResponse({"error": "ACCESS_DENIED"}, status_code=403)
        if request.headers.get("content-length") not in (None, "0"):
            return JSONResponse({"error": "BODY_NOT_ALLOWED"}, status_code=400)
        if request.query_params:
            return JSONResponse({"error": "QUERY_NOT_SUPPORTED"}, status_code=400)
        if request.headers.get("host", "").split(":")[0] not in {"localhost", "127.0.0.1", allowed_host}:
            return JSONResponse({"error": "HOST_NOT_ALLOWED"}, status_code=403)
        result = build_projection(native)
        payload = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
        if len(payload) > MAX_BYTES:
            return JSONResponse({"error": "PROJECTION_TOO_LARGE"}, status_code=503)
        return Response(
            payload, media_type="application/json",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def forbidden(request: Request) -> Response:
        return JSONResponse({"error": "METHOD_NOT_ALLOWED"}, status_code=405)

    return Starlette(routes=[Route(ALLOWED_PATH, account, methods=["GET"]),
                              Route(ALLOWED_PATH, forbidden, methods=["POST", "PUT", "PATCH", "DELETE"])])


def app_from_environment() -> Starlette:
    token = os.environ.get("GRAFANA_PROJECTION_TOKEN", "")
    return create_app(token=token, allowed_host="projection")


# Lazy import: no environment secret is needed merely to import this module.
class _LazyApp:
    def __init__(self):
        self.instance = None

    async def __call__(self, scope, receive, send):
        if self.instance is None:
            self.instance = app_from_environment()
        await self.instance(scope, receive, send)


app = _LazyApp()
