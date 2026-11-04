"""Read-only SHA-backed exact-minute audit of Phase 6B frozen instruments.

Runs on existing Parquet. Never generates prices, fills or risk outcomes.
Missing bars count as missing and no forward-filling is allowed.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from .pm_phase6b import START, END, _market_directory, fingerprint, safe_write_json


def expected_minutes(day: str, start: datetime, end: datetime) -> set[datetime]:
    date = datetime.fromisoformat(day).replace(tzinfo=UTC)
    left = max(date, start)
    right = min(date + timedelta(days=1), end)
    return {
        left + timedelta(minutes=i)
        for i in range(max(0, int((right - left).total_seconds() // 60)))
    }


def audit_one_day(
    market_root: Path, coin: str, day: str, *, start: datetime = START, end: datetime = END
) -> dict:
    family, expected_symbol = _market_directory(market_root, coin)
    expected = expected_minutes(day, start, end)
    if family is None:
        return {
            "status": expected_symbol,
            "expected_minutes": len(expected),
            "verified_minutes": 0,
            "missing_minutes": len(expected),
        }
    date = datetime.fromisoformat(day)
    folder = family / f"year={date.year:04d}" / f"month={date.month:02d}" / f"day={date.day:02d}"
    meta, parquet = folder / "source.json", folder / "data.parquet"
    base = {
        "expected_minutes": len(expected),
        "verified_minutes": 0,
        "missing_minutes": len(expected),
    }
    if not meta.is_file() or not parquet.is_file():
        return {**base, "status": "MISSING_MARKET_DAY"}
    try:
        doc = json.loads(meta.read_text())
        if (
            doc.get("exchange") not in {"hyperliquid_futures", "hyperliquid", "HYPERLIQUID"}
            or doc.get("source_symbol") != expected_symbol
            or doc.get("source_type") not in {"trades", "candles"}
        ):
            return {**base, "status": "INVALID_SOURCE_IDENTITY"}
        digest = fingerprint(parquet)
        if digest != doc.get("sha256"):
            return {**base, "status": "SHA256_MISMATCH"}
        import polars as pl

        frame = pl.read_parquet(
            parquet, columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"]
        )
        times = frame["timestamp"].to_list()
        if any(
            t.tzinfo is None
            or t.utcoffset() != timedelta(0)
            or t.second
            or t.microsecond
            or t.date().isoformat() != day
            for t in times
        ):
            return {**base, "status": "INVALID_MINUTE_CLOCK"}
        if len(set(times)) != len(times):
            return {**base, "status": "DUPLICATE_MINUTE"}
        if (frame["symbol"] != expected_symbol.split(":")[-1]).any():
            return {**base, "status": "WRONG_NATIVE_SYMBOL"}
        if frame.select(
            (
                (pl.col("low") <= 0)
                | (pl.col("high") < pl.col("low"))
                | (pl.col("low") > pl.min_horizontal("open", "close"))
                | (pl.col("high") < pl.max_horizontal("open", "close"))
                | (pl.col("volume") < 0)
                | pl.any_horizontal(
                    pl.col("open").is_null(),
                    pl.col("high").is_null(),
                    pl.col("low").is_null(),
                    pl.col("close").is_null(),
                )
            )
            .any()
            .alias("bad")
        )["bad"][0]:
            return {**base, "status": "INVALID_OHLCV"}
        actual = set(times) & expected
        missing = expected - actual
        return {
            "status": "EXACT_MINUTE_SHA_VERIFIED"
            if not missing
            else "PARTIAL_EXACT_MINUTE_SHA_VERIFIED",
            "expected_minutes": len(expected),
            "verified_minutes": len(actual),
            "missing_minutes": len(missing),
            "sha256": digest,
            "source_type": doc["source_type"],
            "extra_minutes_outside_window": len(set(times) - expected),
        }
    except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        return {**base, "status": "UNREADABLE_MARKET_DATA", "error_type": type(exc).__name__}


def audit_coverage(coverage: Path, market_root: Path, output: Path) -> dict:
    previous = json.loads(coverage.read_text())
    coins = sorted(previous["market_day_inventory"])
    data = {}
    for coin in coins:
        cursor = START.date()
        daily = []
        while cursor <= (END - timedelta(microseconds=1)).date():
            daily.append(
                {"day": cursor.isoformat(), **audit_one_day(market_root, coin, cursor.isoformat())}
            )
            cursor += timedelta(days=1)
        exp = sum(row["expected_minutes"] for row in daily)
        observed = sum(row["verified_minutes"] for row in daily)
        data[coin] = {
            "expected_minutes": exp,
            "verified_minutes": observed,
            "missing_or_invalid_minutes": exp - observed,
            "percent": round(100 * observed / exp, 5) if exp else None,
            "disqualified_days": [
                {
                    "day": row["day"],
                    "status": row["status"],
                    "missing_minutes": row["missing_minutes"],
                }
                for row in daily
                if row["status"] != "EXACT_MINUTE_SHA_VERIFIED"
            ],
            "validated_day_count": sum(
                row["status"].endswith("EXACT_MINUTE_SHA_VERIFIED") for row in daily
            ),
            "days": daily,
        }
    source_sha = fingerprint(coverage)
    aggregate = {
        "schema": "phase6b_exact_minute_sha_coverage_v1",
        "original_coverage_sha256": source_sha,
        "minutely_market_data_is_price_proxy_not_exchange_mark": True,
        "funding_not_reconstructed": True,
        "portfolio_equity_is_blocked": True,
        "instrument_count": len(coins),
        "instruments": data,
        "instrument_days_unweighted_coverage": None,
        "conclusion": "SOURCE_EQUITY_AND_WHOLE_BOOK_BLOCKED",
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    sha = safe_write_json(output / "native_minute_coverage.json", aggregate)
    return {
        "status": aggregate["conclusion"],
        "instrument_count": len(coins),
        "output": str(output / "native_minute_coverage.json"),
        "sha256": sha,
        "fully_covered_instruments": sum(
            not v["missing_or_invalid_minutes"] for v in data.values()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_coverage(args.coverage, args.market_root, args.output), indent=2))


if __name__ == "__main__":
    main()
