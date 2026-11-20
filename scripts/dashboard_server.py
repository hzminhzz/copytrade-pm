#!/usr/bin/env python3
"""Read-only HTTP projection for the Copytrade Ops Control Center.

SQLite and independent finance/release systems retain authority. This server
can neither write evidence nor infer trading qualification or authorization.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

WORKSPACE = Path(__file__).resolve().parents[1]
DIST = WORKSPACE / "ops" / "control-center" / "dist"
# The roster SQLite is the wallet/portfolio identity authority. The retired
# wallet_registry.sqlite path is no longer read; the legacy env/attribute names
# stay only so the pinned ops unit keeps a single configured database path.
REGISTRY_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_REGISTRY_DB",
        os.environ.get(
            "COPYTRADE_OPS_ROSTER_DB",
            "/home/quant/.local/share/copytrade/roster.sqlite",
        ),
    )
)
ROSTER_SCHEMA_VERSION = 1
PROJECTION_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_PROJECTION_DB",
        "/home/quant/.local/share/copytrade/projection.db",
    )
)
OPS_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_RECORDS_DB",
        "/home/quant/.local/share/copytrade/ops_dashboard.sqlite",
    )
)
HASHED_ASSET = re.compile(r"^/assets/[\w.-]+-[A-Za-z0-9_-]{8,}\.(?:js|css|svg|woff2?)$")
_STATE_CACHE: tuple[float, str, dict] | None = None
_STATE_CACHE_LOCK = threading.Lock()
_STATE_CACHE_SECONDS = 8.0
_OWNER_VIEW_CACHE: dict[tuple[str, str, str], tuple[float, dict]] = {}
_OWNER_VIEW_CACHE_LOCK = threading.Lock()
_OWNER_VIEW_CACHE_SECONDS = 8.0
# Fixed read-only input selectors; assert parity with PORTFOLIO_CONFIGS in tests.
_CHAPTER2_PORTFOLIOS = frozenset(
    {"A", "B", "C", "Combo2", "regime.macro/TriadA", "regime.macro/TriadChop"}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redacted_wallet(wallet: str) -> str:
    """Stable public display key; the operator surface never renders an address."""
    return "wallet:" + sha256(wallet.encode()).hexdigest()[:16]


def _iso_ms(stamp_ms: int | None) -> str | None:
    if stamp_ms is None:
        return None
    return datetime.fromtimestamp(int(stamp_ms) / 1000, timezone.utc).isoformat()


def readonly(db: Path) -> sqlite3.Connection:
    """Read live WAL snapshots without journaling, write capability or read pins."""
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def read_projection(db: Path) -> dict[str, str | None]:
    if not db.exists():
        return {}
    try:
        with closing(readonly(db)) as con:
            return {
                str(r["wallet_id"]).lower(): r["account_value"]
                for r in con.execute("SELECT wallet_id, account_value FROM expert_equity")
            }
    except (sqlite3.Error, OSError, TypeError) as exc:
        print(f"[ops] projection unavailable: {type(exc).__name__}", file=sys.stderr)
        return {}


def read_ops_records(db: Path) -> tuple[list[dict], list[dict]]:
    """Imported operator notes are not independently attested operational proof."""
    if not db.exists():
        return [], []
    try:
        with closing(readonly(db)) as con:
            records = []
            for r in con.execute(
                "SELECT * FROM ops_records ORDER BY updated_at DESC, id DESC LIMIT 500"
            ):
                records.append(
                    {
                        "id": r["id"],
                        "category": r["category"],
                        "title": r["title"],
                        "status": "pending",
                        "reportedStatus": r["status"],
                        "basis": r["basis"]
                        if r["basis"] in ("historical", "prospective", "paper", "unknown")
                        else "unknown",
                        "quality": "unverified",
                        "severity": r["severity"],
                        "owner": r["owner"],
                        "sourceRef": r["source_ref"],
                        "details": r["details"],
                        "createdAt": r["created_at"],
                        "updatedAt": r["updated_at"],
                    }
                )
            events = [
                {
                    "id": r["id"],
                    "entityType": r["entity_type"],
                    "entityId": r["entity_id"],
                    "action": r["action"],
                    "actor": r["actor"],
                    "createdAt": r["created_at"],
                }
                for r in con.execute(
                    "SELECT id, entity_type, entity_id, action, actor, created_at "
                    "FROM event_log ORDER BY id DESC LIMIT 100"
                )
            ]
            return records, events
    except (sqlite3.Error, OSError, TypeError) as exc:
        print(f"[ops] records unavailable: {type(exc).__name__}", file=sys.stderr)
        return [], []


def get_sqlite_state(
    registry_db: Path | None = None,
    projection_db: Path | None = None,
    ops_db: Path | None = None,
) -> dict:
    """One read-only roster transaction; no fabricated assessment or release.

    Wallet and portfolio identity come from committed roster seat books, not from
    the retired `wallet_registry.sqlite`. Row states stay `candidate` /
    `unverified`: a seat book is a research selection, never release or trading
    authority, and a public display key is a redacted wallet reference.
    """
    db = registry_db if registry_db is not None else REGISTRY_DB
    if not db.is_file():
        raise FileNotFoundError("Roster source unavailable")
    now = utc_now()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    equity = read_projection(projection_db if projection_db is not None else PROJECTION_DB)
    wallets: list[dict] = []
    portfolios: list[dict] = []
    observed_ms: int | None = None
    integrity = "FAILED"

    with closing(readonly(db)) as con:
        con.execute("BEGIN")  # pin one consistent read snapshot
        quick = con.execute("PRAGMA quick_check").fetchone()
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if (
            quick is not None
            and quick[0] == "ok"
            and con.execute("PRAGMA foreign_key_check").fetchone() is None
            and version is not None
            and str(version[0]) == str(ROSTER_SCHEMA_VERSION)
        ):
            integrity = "VERIFIED"
        vetoed = {
            str(r["wallet"])
            for r in con.execute(
                "SELECT wallet FROM vetoes WHERE revoked_ms IS NULL "
                "AND (expires_ms IS NULL OR expires_ms > ?)",
                (now_ms,),
            )
        }
        for account in con.execute(
            "SELECT account_id, MAX(sequence) AS sequence FROM books GROUP BY account_id"
            " ORDER BY account_id"
        ):
            book = con.execute(
                "SELECT as_of_ms, book_sha, payload FROM books WHERE account_id=? AND sequence=?",
                (account["account_id"], account["sequence"]),
            ).fetchone()
            if book is None:
                continue
            account_id = str(account["account_id"])
            sequence = int(account["sequence"])
            book_sha = str(book["book_sha"])
            as_of_ms = int(book["as_of_ms"])
            observed_ms = as_of_ms if observed_ms is None else max(observed_ms, as_of_ms)
            try:
                payload = json.loads(book["payload"])
            except (TypeError, ValueError) as exc:
                raise ValueError("ROSTER_BOOK_PAYLOAD_INVALID") from exc
            seats = payload.get("seats") if isinstance(payload, dict) else None
            members: list[str] = []
            for seat in seats if isinstance(seats, list) else []:
                lease = seat.get("lease") if isinstance(seat, dict) else None
                spec = seat.get("spec") if isinstance(seat, dict) else None
                if not isinstance(lease, dict) or not isinstance(spec, dict):
                    continue
                wallet = str(lease.get("wallet") or "")
                seat_id = str(spec.get("seat_id") or "")
                if not wallet or not seat_id:
                    continue
                members.append(_redacted_wallet(wallet))
                wallets.append(
                    {
                        "address": _redacted_wallet(wallet),  # opaque display key
                        # A seat label is the canonical roster identity, never an alias guess.
                        "alias": seat_id,
                        # Diagnostic market value only, never follower NAV.
                        "sourceEquityUsd": equity.get(wallet.lower()),
                        "eligibility": "ineligible" if wallet in vetoed else "pending",
                        "assessmentStatus": "candidate",
                        "edgeDecay": "unknown",
                        "drawdownPct": None,  # no authentic cash-flow-adjusted path
                        "evidenceQuality": "unverified",
                        "evidenceBasis": "prospective" if integrity == "VERIFIED" else "unknown",
                        "sourceRef": f"roster_book:{book_sha[:16]}",
                        "assessedAt": None,
                        "updatedAt": _iso_ms(as_of_ms) or now,
                        "registryMetadataJson": json.dumps(
                            {
                                "accountId": account_id,
                                "seatId": seat_id,
                                "generation": lease.get("generation"),
                                "owner": lease.get("owner"),
                                "receiptHealth": "unknown",
                            }
                        ),
                    }
                )
            draining = payload.get("draining") if isinstance(payload, dict) else None
            for entry in draining if isinstance(draining, list) else []:
                wallet = str(entry.get("wallet") or "") if isinstance(entry, dict) else ""
                if not wallet:
                    continue
                wallets.append(
                    {
                        "address": _redacted_wallet(wallet),
                        "alias": None,
                        "sourceEquityUsd": equity.get(wallet.lower()),
                        "eligibility": "ineligible" if wallet in vetoed else "pending",
                        "assessmentStatus": "draining",
                        "edgeDecay": "unknown",
                        "drawdownPct": None,
                        "evidenceQuality": "unverified",
                        "evidenceBasis": "unknown",
                        "sourceRef": f"roster_draining:{book_sha[:16]}",
                        "assessedAt": None,
                        "updatedAt": _iso_ms(as_of_ms) or now,
                        "registryMetadataJson": json.dumps(
                            {
                                "accountId": account_id,
                                "seatId": entry.get("seat_id") if isinstance(entry, dict) else None,
                                "owner": entry.get("owner") if isinstance(entry, dict) else None,
                                "reason": entry.get("reason") if isinstance(entry, dict) else None,
                                "receiptHealth": "unknown",
                            }
                        ),
                    }
                )
            portfolios.append(
                {
                    "id": f"{account_id}-v{sequence}",
                    "name": f"{account_id} (v{sequence})",
                    "state": "candidate",
                    "strategy": "SEALED_RESEARCH_SELECTION",
                    "walletAddressesJson": json.dumps(members),
                    "podCount": None,  # selected seats != running pods
                    "totalRiskUsd": None,  # Guardian, not the roster, owns this
                    "evidenceBasis": "prospective",
                    "evidenceQuality": "unverified",
                    "sourceRef": f"roster_book:{book_sha[:16]}",
                    "detailsJson": json.dumps(
                        {
                            "sequence": sequence,
                            "bookSha256": book_sha,
                            "selectionKnownAt": _iso_ms(as_of_ms),
                            "paperRunning": "UNKNOWN",
                            "tradingAuthorized": False,
                            "sizingContract": "FIXED_K_NATIVE_QUANTITY (policy only)",
                        }
                    ),
                    "updatedAt": _iso_ms(as_of_ms) or now,
                }
            )
        con.execute("ROLLBACK")  # close the explicitly bounded snapshot

    records, events = read_ops_records(ops_db if ops_db is not None else OPS_DB)
    receipt = {
        "snapshotId": f"sqlite-snapshot-{now}",
        "status": "pending" if integrity == "VERIFIED" else "failed",
        "producedAt": now,
        "receivedAt": now,
        "sourceObservedAt": _iso_ms(observed_ms) if observed_ms is not None else None,
        "sourceStatus": "VERIFIED" if integrity == "VERIFIED" else "FAILED",
        # This reader does not recompute the roster inventory SHA; never imply it.
        "inventorySha256": None,
        "sourceManifestSha256": None,
        "releaseStatus": None,
        "releaseRevision": None,
        "databaseIntegrity": integrity,
        "selectionKnownAt": _iso_ms(observed_ms) if observed_ms is not None else None,
        "selectionSha256": None,
        "selectionState": "SEALED_RESEARCH_ONLY",
        "paperRunning": "UNKNOWN",
        "scientificallyQualified": 0,
        "tradingAuthorized": 0,
        "walletTotal": len(wallets),
        "walletSynced": sum(w["alias"] is not None for w in wallets),
        "walletUnresolved": sum(w["alias"] is None for w in wallets),
        "portfolioCount": len(portfolios),
        "error": (
            "Committed roster seat books only: release admission, paper runtime and"
            " trading authority are verified elsewhere and are never inferred here."
        ),
    }
    return {
        "wallets": wallets,
        "portfolios": portfolios,
        "records": records,
        "events": events,
        "registrySync": {"latestAttempt": receipt, "latestAccepted": None},
        "runtime": {
            "dashboardRevision": os.environ.get("COPYTRADE_OPS_RELEASE_SHA"),
            "observerMode": "NO_TRADE",
            "trustedBrokerAuthority": False,
        },
    }


def cached_sqlite_state() -> dict:
    """Singleflight short-lived projection limits WAL readers and CPU load."""
    global _STATE_CACHE
    with _STATE_CACHE_LOCK:
        if not REGISTRY_DB.is_file():
            raise FileNotFoundError("Registry source unavailable")
        now = time.monotonic()
        authority = str(REGISTRY_DB.resolve())
        if (
            _STATE_CACHE is not None
            and _STATE_CACHE[1] == authority
            and now - _STATE_CACHE[0] < _STATE_CACHE_SECONDS
        ):
            return _STATE_CACHE[2]
        state = get_sqlite_state()
        _STATE_CACHE = (time.monotonic(), authority, state)
        return state


def _invoke_owner_cli(argv: list[str]) -> dict:
    """Invoke pinned source with a configured dependency-complete Python.

    The Ops HTTP daemon intentionally uses system Python without Pydantic.
    Never install packages or create a venv in the immutable running release.
    """
    configured = os.environ.get("COPYTRADE_OPS_OWNER_PYTHON")
    if not configured:
        raise FileNotFoundError("Owner interpreter not configured")
    python = Path(configured)
    if not python.is_absolute() or not python.is_file() or not os.access(python, os.X_OK):
        raise OSError("Owner interpreter unavailable")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE / "src")
    try:
        completed = subprocess.run(
            [str(python), "-m", "copytrade_pm.pm_operations", *argv],
            cwd=WORKSPACE,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OSError("Owner inspection timed out") from exc
    # Exit 2 means the owner could not complete the requested read, even when
    # it printed a structured error projection. Never promote that to HTTP 200.
    if completed.returncode != 0 or len(completed.stdout) > 256_000:
        raise OSError("Owner inspection failed")
    payload = json.loads(completed.stdout)
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "cwsa_chapter2_site_owner_view_v1"
        or payload.get("trading_authorized") is not False
        or payload.get("order_route") != "NONE"
    ):
        raise ValueError("Owner permission or schema unsupported")
    return payload


def chapter2_owner_view(portfolio: str, inspection: str) -> dict:
    """One bounded, redacted owner read; no HTTP caller file paths or mutation."""
    if not REGISTRY_DB.is_file():
        raise FileNotFoundError("Roster owner unavailable")
    argv = [
        "release",
        "chapter2",
        "site-view",
        "--portfolio",
        portfolio,
        "--inspection",
        inspection,
        "--roster-db",
        str(REGISTRY_DB),
    ]
    for flag, name in (
        ("--source-db", "COPYTRADE_OPS_CWSA_SOURCE_DB"),
        ("--paper-root", "COPYTRADE_OPS_CWSA_PAPER_ROOT"),
        ("--quote-db", "COPYTRADE_OPS_CWSA_QUOTE_DB"),
        ("--epoch", "COPYTRADE_OPS_CWSA_EPOCH"),
    ):
        configured = os.environ.get(name)
        if configured:
            argv.extend((flag, configured))
    result = _invoke_owner_cli(argv)
    if (result.get("scope") or {}).get("portfolio") != portfolio:
        raise ValueError("Owner scope mismatch")
    return result


def cached_chapter2_owner_view(portfolio: str, inspection: str) -> dict:
    """Singleflight bounded read prevents repeated public HTTP from pinning WAL."""
    key = (str(REGISTRY_DB.resolve()), portfolio, inspection)
    with _OWNER_VIEW_CACHE_LOCK:
        now = time.monotonic()
        hit = _OWNER_VIEW_CACHE.get(key)
        if hit is not None and now - hit[0] < _OWNER_VIEW_CACHE_SECONDS:
            return hit[1]
        value = chapter2_owner_view(portfolio, inspection)
        # At most six selected portfolio keys x two inspection modes.
        if len(_OWNER_VIEW_CACHE) >= 12:
            _OWNER_VIEW_CACHE.clear()
        _OWNER_VIEW_CACHE[key] = (time.monotonic(), value)
        return value


class DashboardHandler(SimpleHTTPRequestHandler):
    """No write methods, CORS entitlement, directory listing or private keys."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        print("[ops] " + format % args, file=sys.stderr)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            # Cloudflare JSD adds a request-specific inline bootstrap (dynamic Ray ID).
            # It cannot be SHA-allowlisted. Only this public NO_TRADE app needs it;
            # prohibit inline handler attributes and keep all remote script URLs
            # restricted to this origin. No authenticated API write path exists.
            "default-src 'self'; script-src 'self' 'unsafe-inline'; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        if not getattr(self, "_cache_set", False):
            self.send_header("Cache-Control", "no-store")
        self._cache_set = False
        super().end_headers()

    def send_json(self, data: object, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(data, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self._cache_set = True
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/owner-view":
            # Only a fixed Chapter 2 portfolio and inspection can be requested.
            # Reject repeated/extra parameters and caller-provided file paths.
            query = parse_qs(parsed.query, keep_blank_values=True)
            if (
                len(parsed.query) > 240
                or not set(query) <= {"portfolio", "inspection"}
                or len(query.get("portfolio", [])) != 1
                or len(query.get("inspection", ["evidence"])) != 1
                or query["portfolio"][0] not in _CHAPTER2_PORTFOLIOS
                or query.get("inspection", ["evidence"])[0] not in ("metadata", "evidence")
            ):
                self.send_json({"error": "Invalid owner-view scope"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                view = cached_chapter2_owner_view(
                    query["portfolio"][0], query.get("inspection", ["evidence"])[0]
                )
                self.send_json(view)
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                sqlite3.Error,
                json.JSONDecodeError,
            ) as exc:
                print(f"[ops] owner view unavailable: {type(exc).__name__}", file=sys.stderr)
                self.send_json(
                    {"status": "UNKNOWN", "error": "Owner evidence unavailable"},
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return
        if path == "/api/health":
            self.send_json(
                {
                    "status": "ok",
                    "mode": "NO_TRADE",
                    "revision": os.environ.get("COPYTRADE_OPS_RELEASE_SHA"),
                }
            )
            return
        if path in ("/api/state", "/api/records"):
            try:
                state = cached_sqlite_state()
                self.send_json(state if path == "/api/state" else state["records"])
            except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                print(f"[ops] source failure: {type(exc).__name__}", file=sys.stderr)
                self.send_json(
                    {"error": "Registry unavailable"}, status=HTTPStatus.SERVICE_UNAVAILABLE
                )
            return
        if path.startswith("/api/"):
            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if path in ("/", "/index.html"):
            self.path = "/index.html"
        elif path != "/favicon.svg" and not path.startswith("/assets/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not DIST.is_dir():
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Frontend build unavailable")
            return
        super().do_GET()

    def send_head(self):
        path = urlsplit(self.path).path
        if HASHED_ASSET.fullmatch(path):
            self._cache_set = True
            original = self.end_headers

            def _headers() -> None:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                original()

            self.end_headers = _headers
            try:
                return super().send_head()
            finally:
                self.end_headers = original
        return super().send_head()

    def do_POST(self) -> None:
        self.send_json({"error": "Read-only observer"}, status=HTTPStatus.FORBIDDEN)

    do_PATCH = do_POST
    do_PUT = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    if not DIST.joinpath("index.html").is_file():
        raise SystemExit(f"Cannot start: missing built dashboard at {DIST}")
    service = ThreadingHTTPServer((args.bind, args.port), DashboardHandler)
    service.daemon_threads = True
    try:
        service.serve_forever()
    finally:
        service.server_close()


if __name__ == "__main__":
    main()
