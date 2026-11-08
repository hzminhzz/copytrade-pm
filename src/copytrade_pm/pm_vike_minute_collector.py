"""One shared read-only Vike latest-minute collector for research paper pricing.

Writes only versioned price observations to a separate private PaperJournal.
A minute close is NOT a limit-order-book quote or proven executable liquidity.
No wallet selection, broker access or production cutover is performed here.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from time import monotonic, sleep
from urllib import error, parse, request

from .pm_forward_journal import PaperJournal
from .pm_vike_minute import minute_latest

URL = "https://data.vike.io/v1/hyperliquid/ohlcv/latest"
MAX_RESPONSE_BYTES = 16_000_000


def fetch_latest(*, api_key: str, timeout: float = 15) -> tuple[dict, str]:
    if not api_key:
        raise ValueError("VIKE_PRICE_KEY_MISSING")
    url = URL + "?" + parse.urlencode({"market": "perp", "interval": "1m"})
    req = request.Request(
        url, method="GET",
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            received_at = datetime.now(UTC).isoformat()
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("VIKE_PRICE_PROVIDER_UNAVAILABLE") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("VIKE_PRICE_RESPONSE_TOO_LARGE")
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("VIKE_PRICE_RESPONSE_INVALID_JSON") from exc
    if not isinstance(doc, dict):
        raise ValueError("VIKE_PRICE_RESPONSE_INVALID")
    return doc, received_at


def parse_markets(value: str) -> frozenset[str]:
    if not isinstance(value, str):
        raise ValueError("VIKE_PRICE_SELECTED_MARKETS_INVALID")
    markets = [part.strip() for part in value.split(",")]
    if not markets or any(not item or len(item) > 40 for item in markets):
        raise ValueError("VIKE_PRICE_SELECTED_MARKETS_INVALID")
    if len(set(markets)) != len(markets):
        raise ValueError("VIKE_PRICE_DUPLICATE_SELECTED_MARKET")
    # The native identity must be preserved, including lowercase HIP-3 DEX.
    from .pm_vike_minute import native_instrument

    for item in markets:
        native_instrument(item)
    return frozenset(markets)


def collect_once(
    journal: PaperJournal, *,
    doc: dict, received_at: str, markets: frozenset[str],
) -> dict:
    if not markets:
        raise ValueError("VIKE_PRICE_NO_SELECTED_MARKETS")
    available = minute_latest(doc, received_at=received_at)
    missing = sorted(markets - available.keys())
    recorded = duplicate = 0
    for market in sorted(markets & available.keys()):
        outcome = journal.append_vike_minute(available[market])
        if outcome["status"] == "RECORDED_ESTIMATED_PRICE_ONLY":
            recorded += 1
        else:
            duplicate += 1
    return {
        "schema": "vike_minute_collector_receipt_v1",
        "first_known_at": received_at,
        "selected_markets": len(markets),
        "recorded": recorded,
        "duplicates": duplicate,
        "missing_native_markets": missing,
        "status": "OBSERVED_PRICES_ONLY" if not missing else "BLOCKED_INCOMPLETE_MARKET_SCOPE",
        "order_route": "NONE",
        "broker_executed": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-root", required=True, type=Path)
    p.add_argument("--markets", required=True, help="Native names, e.g. BTC,ETH,xyz:BRENTOIL")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--cadence-seconds", type=int, default=20)
    args = p.parse_args()
    if not 10 <= args.cadence_seconds <= 120:
        p.error("--cadence-seconds must be 10..120")
    markets = parse_markets(args.markets)
    key = os.getenv("VIKE_API_KEY")
    if not key:
        print(json.dumps({
            "status": "BLOCKED_DEDICATED_VIKE_API_KEY_MISSING",
            "state_created": False, "order_route": "NONE",
        }))
        return 2
    # Always a distinct root from original source/CCXT and v3 account journals.
    if args.state_root.is_symlink():
        raise ValueError("VIKE_PRICE_ROOT_SYMLINK")
    journal = PaperJournal(args.state_root)
    while True:
        began = monotonic()
        try:
            doc, stamp = fetch_latest(api_key=key)
            result = collect_once(journal, doc=doc, received_at=stamp, markets=markets)
        except (ValueError, KeyError, TypeError) as exc:
            result = {
                "schema": "vike_minute_collector_receipt_v1",
                "status": "BLOCKED_PRICE_COLLECTOR",
                "reason_class": type(exc).__name__,
                "order_route": "NONE",
            }
        print(json.dumps(result, sort_keys=True), flush=True)
        if not args.watch:
            return 0 if result["status"] == "OBSERVED_PRICES_ONLY" else 2
        sleep(max(0.1, args.cadence_seconds - (monotonic() - began)))


if __name__ == "__main__":
    raise SystemExit(main())
