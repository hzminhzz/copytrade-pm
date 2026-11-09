"""Opt-in V4 historical 1m follower *estimates*, never first-known SHADOW evidence.

Immutable v1 offline contracts remain untouched. This v2 path supports complete,
continuous flat-to-flat source episodes; partial/rebalanced episodes are BLOCKED.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from math import isfinite
import json
from pathlib import Path
from time import perf_counter

from .pm03_account import Instrument
from .pm_offline_cache import ImmutableCache
from .pm_offline_manifest import ManifestBlocked, ManifestInvalid, _safe_file
from .pm_offline_oracle import _json_bytes
from .pm_offline_oracle_market import (
    DAY_MS,
    _day_record,
    _join_instrument,
    MAX_MARKET_DAYS,
)
from .pm_offline_repository import (
    ADDRESS,
    GROUPS,
    MAX_SOURCE_FILE,
    _hash_file,
    native_instrument,
    _clock,
)
from .pm_vike_minute import EstimatedMinuteExecutionModel

SCHEMA = "pm_v4_wallet_screen_job_v2"
REPORT = "pm_v4_wallet_screen_report_v2"
POLICY = "V4_HISTORICAL_ORACLE_FIXED_K_NATIVE_1M_PROXY_V1"
SCENARIOS = ("BASE", "DELAYED", "ADVERSE")
MINUTE = 60_000
SHA = set("0123456789abcdef")
MAX_V2_SOURCE_FILES = 1000
MAX_V2_SOURCE_ROWS = 3_000_000


def _v2_source_files(source_root: Path) -> list[Path]:
    """Separate bounded v2 cohort enumeration; never change frozen v1 limits."""
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ManifestInvalid("UNSAFE_OR_MISSING_RESEARCH_SOURCE_ROOT")
    paths = []
    for group in GROUPS:
        directory = root / group
        if directory.is_symlink() or not directory.is_dir():
            raise ManifestBlocked(f"MISSING_SOURCE_GROUP_{group.upper()}")
        candidates = sorted(directory.glob("*.json"))
        if not candidates:
            raise ManifestBlocked(f"EMPTY_SOURCE_GROUP_{group.upper()}")
        paths.extend(candidates)
    if len(paths) > MAX_V2_SOURCE_FILES:
        raise ManifestBlocked("V4_SOURCE_FILE_BUDGET_EXCEEDED")
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_FILE:
            raise ManifestBlocked("UNSAFE_OR_OVERSIZED_SOURCE_FILE")
    return paths


def _v2_source_digest(source_root: Path) -> str:
    hashes = sorted(_hash_file(path) for path in _v2_source_files(source_root))
    return _sha(json.dumps(hashes, separators=(",", ":")).encode())


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def v4_instrument_key(oracle_native: str) -> str:
    """Preserve native market/DEX through the offline colon -> PM03 slash seam."""
    if not isinstance(oracle_native, str):
        raise ManifestInvalid("INVALID_V4_NATIVE_IDENTITY")
    parts = oracle_native.split(":", 4)
    if len(parts) != 5 or parts[:3] != ["hyperliquid", "mainnet", "perp"]:
        raise ManifestInvalid("INVALID_V4_NATIVE_IDENTITY")
    dex, symbol = parts[3:]
    raw = symbol if dex == "default" else f"{dex}:{symbol}"
    if native_instrument(raw) != oracle_native:
        raise ManifestInvalid("INVALID_V4_NATIVE_IDENTITY")
    return Instrument("hyperliquid", f"mainnet:perp:{dex}", symbol).key


def _num(value: object) -> float | None:
    try:
        number = Decimal(str(value))
    except InvalidOperation, TypeError, ValueError:
        return None
    if not number.is_finite():
        return None
    converted = float(number)
    return converted if isfinite(converted) else None


def _job(job: dict) -> dict:
    required = {
        "schema",
        "study_id",
        "kind",
        "clock_basis",
        "start",
        "end",
        "source_collection_sha256",
        "k_policy_path",
        "k_policy_sha256",
    }
    if not isinstance(job, dict) or set(job) != required:
        raise ManifestInvalid("INVALID_V4_SCREEN_MANIFEST")
    if (
        job["schema"] != SCHEMA
        or job["kind"] != "V4_HISTORICAL_WALLET_SCREEN"
        or job["clock_basis"] != "HISTORICAL_ORACLE"
    ):
        raise ManifestInvalid("INVALID_V4_SCREEN_POLICY")
    if (
        not isinstance(job["study_id"], str)
        or not 1 <= len(job["study_id"]) <= 96
        or not all(c.isascii() and (c.isalnum() or c in "._-") for c in job["study_id"])
    ):
        raise ManifestInvalid("INVALID_V4_SCREEN_ID")
    for key in ("source_collection_sha256", "k_policy_sha256"):
        if (
            not isinstance(job[key], str)
            or len(job[key]) != 64
            or any(c not in SHA for c in job[key])
        ):
            raise ManifestInvalid("INVALID_V4_SCREEN_SHA")
    begin, end = _clock(job["start"]), _clock(job["end"])
    if (
        begin >= end
        or (end - begin).total_seconds() > 120 * 86400
        or begin.time() != datetime.min.time()
        or end.time() != datetime.min.time()
    ):
        raise ManifestInvalid("INVALID_V4_SCREEN_WINDOW")
    return job


def _policy(root: Path, job: dict) -> tuple[dict, str]:
    path = _safe_file(root, job["k_policy_path"])
    raw = path.read_bytes()
    if _sha(raw) != job["k_policy_sha256"]:
        raise ManifestBlocked("V4_FROZEN_K_POLICY_SHA_MISMATCH")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ManifestInvalid("INVALID_V4_FROZEN_K_POLICY") from exc
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "asof", "wallets", "markets"}
        or doc["schema"] != "v4_screen_frozen_k_policy_v1"
    ):
        raise ManifestInvalid("INVALID_V4_FROZEN_K_POLICY")
    asof = _clock(doc["asof"])
    if asof >= _clock(job["start"]):
        raise ManifestBlocked("FUTURE_K_POLICY_CUTOFF")
    if not isinstance(doc["wallets"], dict) or not isinstance(doc["markets"], dict):
        raise ManifestInvalid("INVALID_V4_K_OR_MARKET_RULES")
    for account, value in doc["wallets"].items():
        if len(account) != 64 or any(c not in SHA for c in account):
            raise ManifestInvalid("INVALID_V4_K_WALLET_IDENTITY")
        if not isinstance(value, dict) or set(value) != {"k", "known_at", "provenance_sha256"}:
            raise ManifestInvalid("INVALID_V4_K_PROVENANCE")
        ratio = _num(value["k"])
        if ratio is None or not 0 < ratio <= 10 or _clock(value["known_at"]) > asof:
            raise ManifestBlocked("MISSING_CAUSALLY_FROZEN_K")
        if (
            not isinstance(value["provenance_sha256"], str)
            or len(value["provenance_sha256"]) != 64
            or any(c not in SHA for c in value["provenance_sha256"])
        ):
            raise ManifestInvalid("INVALID_V4_K_PROVENANCE")
    for market, rule in doc["markets"].items():
        try:
            if native_instrument(":".join(market.split(":")[3:])) != market:
                raise ValueError
        except (ValueError, ManifestInvalid) as exc:
            raise ManifestInvalid("INVALID_V4_MARKET_IDENTITY") from exc
        if not isinstance(rule, dict) or set(rule) != {"step", "minimum_notional", "max_notional"}:
            raise ManifestInvalid("INVALID_V4_MARKET_RULE")
        if any(_num(rule[k]) is None or _num(rule[k]) <= 0 for k in rule):
            raise ManifestInvalid("INVALID_V4_MARKET_RULE")
    return doc, _sha(raw)


def _source(source_root: Path, start: int, end: int):
    """Bounded JSON decoding, then vectorized episode reconstruction in Polars."""
    import polars as pl

    rows = []
    invalid = Counter()
    untrusted = set()
    accounts = set()
    seen = set()
    for path in _v2_source_files(source_root):
        raw = path.read_bytes()
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            raise ManifestBlocked("INVALID_V4_SOURCE_JSON") from exc
        if (
            not isinstance(doc, dict)
            or not ADDRESS.fullmatch(str(doc.get("address", "")))
            or not isinstance(doc.get("fills"), list)
        ):
            raise ManifestBlocked("INVALID_V4_SOURCE_FILE")
        account = _sha(doc["address"].lower().encode())
        if account in accounts:
            raise ManifestBlocked("DUPLICATE_V4_SOURCE_WALLET")
        accounts.add(account)
        for ordinal, fill in enumerate(doc["fills"]):
            if not isinstance(fill, dict):
                invalid["MALFORMED_FILL"] += 1
                continue
            stamp = fill.get("time")
            if type(stamp) is not int or not start <= stamp < end:
                continue
            try:
                market = native_instrument(fill.get("coin"))
            except ManifestInvalid:
                invalid["UNSUPPORTED_SOURCE_MARKET"] += 1
                continue
            tid = fill.get("tid")
            if not isinstance(tid, (str, int)) or isinstance(tid, bool):
                invalid["MISSING_TID"] += 1
                continue
            identity = (account, market, str(tid))
            if identity in seen:
                invalid["DUPLICATE_TID"] += 1
                # Duplicated event identity makes chain continuity uncertain.
                invalid["SOURCE_CHAIN_UNTRUSTED"] += 1
                untrusted.add((account, market))
                continue
            seen.add(identity)
            size, before = (
                _num(fill.get("sz")),
                _num(fill.get("startPosition", fill.get("start_position"))),
            )
            if fill.get("side") not in ("A", "B") or size is None or size <= 0 or before is None:
                invalid["UNKNOWN_SOURCE_POSITION"] += 1
                untrusted.add((account, market))
                continue
            rows.append(
                {
                    "account": account,
                    "instrument": market,
                    "ms": stamp,
                    "source_order": ordinal,
                    "event_id": str(tid),
                    "before": before,
                    "after": before + size * (1 if fill["side"] == "B" else -1),
                    "source_px": _num(fill.get("px")),
                }
            )
            if len(rows) > MAX_V2_SOURCE_ROWS:
                raise ManifestBlocked("V4_SOURCE_EVENT_BUDGET")
    if not rows:
        return (
            pl.DataFrame(schema={"account": pl.String, "instrument": pl.String}),
            dict(invalid),
            len(accounts),
            untrusted,
        )
    frame = pl.DataFrame(rows).sort(["account", "instrument", "ms", "source_order", "event_id"])
    # Every nonflat source transition must agree with the preceding known state.
    frame = frame.with_columns(
        pl.col("after").shift(1).over(["account", "instrument"]).alias("prev_after"),
        (pl.col("before").abs() < 1e-9).cast(pl.Int64).alias("new_episode"),
    ).with_columns(
        pl.col("new_episode").cum_sum().over(["account", "instrument"]).alias("episode"),
        (
            (pl.col("prev_after").is_not_null())
            & ((pl.col("before") - pl.col("prev_after")).abs() > 1e-7)
        ).alias("chain_gap"),
    )
    return frame, dict(invalid), len(accounts), untrusted


def _episodes(frame, *, end_ms: int, untrusted: set):
    import polars as pl

    if "episode" not in frame.columns:
        return pl.DataFrame(), {}
    groups = ["account", "instrument", "episode"]
    chunks = (
        frame.group_by(groups)
        .agg(
            pl.col("ms").first().alias("t0"),
            pl.col("ms").last().alias("exit_event_ms"),
            pl.col("before").first().alias("opening_before"),
            pl.col("after").last().alias("ending_after"),
            pl.col("source_px").first().alias("source_mark"),
            pl.col("chain_gap").any().alias("chain_gap"),
            pl.len().alias("source_fills"),
            (pl.col("after").abs() < 1e-9).sum().alias("flat_events"),
            pl.col("ms").alias("event_ms"),
            pl.col("after").alias("event_after"),
        )
        .with_columns(
            ((pl.col("t0") + 300_000) // MINUTE + 1).mul(MINUTE).alias("base_ms"),
            ((pl.col("exit_event_ms") // MINUTE) + 1).mul(MINUTE).alias("exit_ms"),
        )
        .with_columns((pl.col("base_ms") + MINUTE).alias("delayed_ms"))
    )
    # Conservative complete-episode seam: any later rebalance or early close is
    # blocked instead of pretending a fill is an atomic complete SourceBook.
    rows = chunks.explode("event_ms", "event_after")
    later = rows.group_by(groups).agg(
        ((pl.col("event_ms") > pl.col("base_ms")) & (pl.col("event_ms") < pl.col("exit_event_ms")))
        .any()
        .alias("late_rebalance"),
        pl.col("event_after")
        .filter(pl.col("event_ms") < pl.col("base_ms"))
        .last()
        .alias("target_base"),
        pl.col("event_after")
        .filter(pl.col("event_ms") < pl.col("delayed_ms"))
        .last()
        .alias("target_delayed"),
    )
    chunks = chunks.drop("event_ms", "event_after").join(later, on=groups)
    if untrusted:
        compromised = pl.DataFrame(
            [
                {"account": a, "instrument": m, "untrusted_source": True}
                for a, m in sorted(untrusted)
            ]
        )
        chunks = chunks.join(compromised, on=["account", "instrument"], how="left")
        chunks = chunks.with_columns(pl.col("untrusted_source").fill_null(False))
    else:
        chunks = chunks.with_columns(pl.lit(False).alias("untrusted_source"))
    chunks = chunks.with_columns(
        pl.when(pl.col("untrusted_source"))
        .then(pl.lit("UNTRUSTED_SOURCE_CHAIN"))
        .when(pl.col("opening_before").abs() > 1e-9)
        .then(pl.lit("UNKNOWN_OPENING_POSITION"))
        .when(pl.col("chain_gap"))
        .then(pl.lit("BROKEN_SOURCE_CHAIN"))
        .when((pl.col("ending_after").abs() > 1e-9) | (pl.col("flat_events") != 1))
        .then(pl.lit("RIGHT_CENSORED_OR_MULTIPLE_FLATS"))
        .when(pl.col("exit_event_ms") <= pl.col("base_ms"))
        .then(pl.lit("CLOSED_BEFORE_ELIGIBILITY"))
        .when(pl.col("late_rebalance"))
        .then(pl.lit("UNMODELED_LATE_REBALANCE"))
        .when((pl.col("target_base").is_null()) | (pl.col("target_delayed").is_null()))
        .then(pl.lit("UNKNOWN_ENTRY_TARGET"))
        .when(pl.col("exit_ms") >= end_ms)
        .then(pl.lit("RIGHT_CENSORED"))
        .otherwise(pl.lit("SUPPORTED_EPISODE"))
        .alias("source_status")
    )
    return chunks, {
        r["source_status"]: r["len"] for r in chunks.group_by("source_status").len().to_dicts()
    }


def _actions(episodes):
    import polars as pl

    common = [
        "account",
        "instrument",
        "episode",
        "t0",
        "exit_event_ms",
        "source_mark",
        "source_fills",
        "target_base",
        "target_delayed",
    ]
    frames = []
    for leg, col in (
        ("BASE_ENTRY", "base_ms"),
        ("DELAYED_ENTRY", "delayed_ms"),
        ("EXIT", "exit_ms"),
    ):
        frames.append(
            episodes.select(*common, pl.col(col).alias("execute_ms")).with_columns(
                pl.lit(leg).alias("leg")
            )
        )
    return pl.concat(frames).with_columns((pl.col("execute_ms") // DAY_MS).alias("day_number"))


def _join_actions(actions, market_root: Path):
    import polars as pl

    actions = actions.with_row_index("action_id").with_columns(
        pl.col("action_id").cast(pl.String).alias("account_sha256"),
        pl.lit(0).cast(pl.Int64).alias("delay_minutes"),
        pl.lit(1).cast(pl.Int64).alias("source_fill_count"),
        pl.col("t0").alias("first_event_ms"),
        pl.col("exit_event_ms").alias("last_event_ms"),
    )
    needed = {
        (r["instrument"], r["day_number"])
        for r in actions.select("instrument", "day_number").unique().to_dicts()
    }
    needed |= {
        (r["instrument"], r["day_number"] - 1)
        for r in actions.filter(pl.col("execute_ms") % DAY_MS == 0)
        .select("instrument", "day_number")
        .unique()
        .to_dicts()
    }
    if len(needed) > MAX_MARKET_DAYS:
        raise ManifestBlocked("EXCEEDS_BOUNDED_NATIVE_DAY_SCAN")
    pinned = {key: _day_record(market_root, *key) for key in sorted(needed)}
    fingerprint = _sha(
        _json_bytes({f"{inst}@{day}": v for (inst, day), v in sorted(pinned.items())})
    )
    parts = []
    for (instrument,), group in actions.partition_by(
        "instrument", as_dict=True, maintain_order=False
    ).items():
        try:
            parts.append(_join_instrument(market_root, instrument, group, pinned))
        except ManifestBlocked as exc:
            if exc.code != "INVALID_NATIVE_1M_DAY":
                raise
            # A malformed day is not a free price or zero-capacity order.
            parts.append(
                group.with_columns(
                    pl.lit(None).cast(pl.Float64).alias("next_open_float_screen_only"),
                    pl.lit(None).cast(pl.Float64).alias("prior_base_volume_screen_only"),
                    pl.lit("INVALID_NATIVE_1M_DAY").alias("match_status"),
                ).drop("day_number")
            )
    columns = (
        "account_sha256",
        "instrument",
        "execute_ms",
        "next_open_float_screen_only",
        "prior_base_volume_screen_only",
        "match_status",
    )
    market = pl.concat([part.select(columns) for part in parts])
    complete = actions.join(market, on=["account_sha256", "instrument", "execute_ms"], how="left")
    return complete.sort(["account", "instrument", "episode", "leg"]), fingerprint, len(needed)


def _economics(matched, policy: dict, *, scenarios: tuple[str, ...], engine: str = "streaming"):
    """Three vectorized scenario projections on one prepared market panel."""
    import polars as pl

    if engine not in {"streaming", "in-memory"}:
        raise ManifestInvalid("INVALID_V4_POLARS_ENGINE")

    account_rules = pl.DataFrame(
        [{"account": a, "k": float(v["k"])} for a, v in sorted(policy["wallets"].items())],
        schema={"account": pl.String, "k": pl.Float64},
    )
    market_rules = pl.DataFrame(
        [
            {"instrument": m, **{key: float(value) for key, value in rule.items()}}
            for m, rule in sorted(policy["markets"].items())
        ],
        schema={
            "instrument": pl.String,
            "step": pl.Float64,
            "minimum_notional": pl.Float64,
            "max_notional": pl.Float64,
        },
    )
    joined = (
        matched.lazy()
        .join(account_rules.lazy(), on="account", how="left")
        .join(market_rules.lazy(), on="instrument", how="left")
    )
    policy_cost = EstimatedMinuteExecutionModel()
    fee_bps = float(policy_cost.fee)
    spread_bps = float(policy_cost.spread)
    slippage_bps = float(policy_cost.slippage)
    impact_bps = float(policy_cost.impact)
    max_participation = float(policy_cost.cap)
    outputs = []
    for scenario in scenarios:
        entry = "DELAYED_ENTRY" if scenario == "DELAYED" else "BASE_ENTRY"
        entry_quotes = joined.filter(pl.col("leg") == entry).select(
            "account",
            "instrument",
            "episode",
            pl.col("next_open_float_screen_only").alias("entry_reference_price"),
        )
        selected = (
            joined.filter(pl.col("leg").is_in([entry, "EXIT"]))
            .join(entry_quotes, on=["account", "instrument", "episode"], how="left")
            .with_columns(
                pl.when(pl.col("leg") == "EXIT")
                .then(
                    -pl.col("target_delayed") if scenario == "DELAYED" else -pl.col("target_base")
                )
                .otherwise(
                    pl.col("target_delayed") if scenario == "DELAYED" else pl.col("target_base")
                )
                .alias("source_order_qty")
            )
            .with_columns(
                (
                    pl.col("source_order_qty")
                    * pl.col("k")
                    * pl.col("source_mark")
                    / pl.col("entry_reference_price")
                ).alias("raw_qty"),
            )
            .with_columns(
                (
                    (pl.col("raw_qty").abs() / pl.col("step")).floor()
                    * pl.col("step")
                    * pl.col("raw_qty").sign()
                ).alias("quantity")
            )
            .with_columns(
                (pl.col("quantity").abs() / pl.col("prior_base_volume_screen_only")).alias(
                    "participation"
                ),
            )
            .with_columns(
                pl.when(pl.col("k").is_null())
                .then(pl.lit("MISSING_FROZEN_K"))
                .when(pl.col("step").is_null())
                .then(pl.lit("MISSING_MARKET_RULE"))
                .when(
                    (pl.lit(scenario == "DELAYED"))
                    & (pl.col("exit_event_ms") <= pl.col("execute_ms"))
                    & (pl.col("leg") == entry)
                )
                .then(pl.lit("CLOSED_BEFORE_DELAYED_ENTRY"))
                .when(pl.col("source_mark").is_null() | (pl.col("source_mark") <= 0))
                .then(pl.lit("INVALID_SOURCE_MARK"))
                .when(pl.col("match_status") != "MATCHED_SCREEN_ONLY")
                .then(pl.col("match_status"))
                .when(pl.col("prior_base_volume_screen_only") <= 0)
                .then(pl.lit("ZERO_PRIOR_VOLUME"))
                .when(pl.col("quantity").is_null() | (pl.col("quantity").abs() < pl.col("step")))
                .then(pl.lit("REJECTED_NATIVE_AMOUNT"))
                .when(
                    (pl.col("quantity") * pl.col("next_open_float_screen_only")).abs()
                    < pl.col("minimum_notional")
                )
                .then(pl.lit("REJECTED_MIN_NOTIONAL"))
                .when(
                    (pl.col("quantity") * pl.col("next_open_float_screen_only")).abs()
                    > pl.col("max_notional")
                )
                .then(pl.lit("REJECTED_GROSS_MARKET_CAP"))
                .when(pl.col("participation") > max_participation)
                .then(pl.lit("UNPRICEABLE_CAPACITY"))
                .otherwise(pl.lit("FILLED_ESTIMATE"))
                .alias("leg_status")
            )
            .with_columns(
                (
                    spread_bps
                    + slippage_bps
                    + impact_bps * pl.col("participation") / max_participation
                    + (10.0 if scenario == "ADVERSE" else 0.0)
                ).alias("execution_cost_bps"),
            )
            .with_columns(
                (
                    pl.col("next_open_float_screen_only")
                    * (1 + pl.col("quantity").sign() * pl.col("execution_cost_bps") / 10000)
                ).alias("modeled_price"),
            )
            .with_columns(
                (pl.col("quantity").abs() * pl.col("modeled_price") * fee_bps / 10000).alias("fee"),
                pl.lit(scenario).alias("scenario"),
            )
        )
        outputs.append(selected)
    result = (
        pl.concat(outputs)
        .collect(engine=engine)
        .sort(["scenario", "account", "instrument", "episode", "leg"])
    )
    group = ["scenario", "account", "instrument", "episode"]
    # All economics exist only for complete entry+exit legs; no invented flat.
    aggregate = (
        result.group_by(group)
        .agg(
            pl.len().alias("legs"),
            (pl.col("leg_status") == "FILLED_ESTIMATE").all().alias("both_filled"),
            pl.col("leg_status")
            .filter(pl.col("leg_status") != "FILLED_ESTIMATE")
            .first()
            .alias("blocked_reason"),
            pl.col("quantity").sum().alias("net_quantity"),
            (pl.col("quantity") * pl.col("modeled_price")).sum().alias("turnover_signed"),
            pl.col("fee").sum().alias("fees"),
            pl.col("t0").first().alias("t0"),
            pl.col("source_fills").first().alias("source_fills"),
        )
        .with_columns(
            pl.when(
                pl.col("both_filled")
                & (pl.col("legs") == 2)
                & (pl.col("net_quantity").abs() < 1e-7)
            )
            .then(-pl.col("turnover_signed") - pl.col("fees"))
            .otherwise(None)
            .alias("estimated_net_pnl")
        )
        .with_columns(
            pl.when(pl.col("estimated_net_pnl").is_not_null())
            .then(pl.lit("ESTIMATED_HISTORICAL_FOLLOWER_PROXY"))
            .otherwise(pl.col("blocked_reason").fill_null("UNRECONCILED_TARGET"))
            .alias("outcome")
        )
        .sort(group)
    )
    return aggregate


def run_v4_screen(
    job: dict,
    *,
    input_root: Path,
    source_root: Path,
    market_root: Path,
    cache_root: Path,
    scenarios: tuple[str, ...] = SCENARIOS,
) -> dict:
    import polars as pl

    _job(job)
    if (
        not scenarios
        or any(s not in SCENARIOS for s in scenarios)
        or len(set(scenarios)) != len(scenarios)
    ):
        raise ManifestInvalid("INVALID_V4_SCENARIOS")
    if not Path(market_root).is_dir() or Path(market_root).is_symlink():
        raise ManifestInvalid("UNSAFE_V4_MARKET_ROOT")
    t0 = perf_counter()
    policy, policy_sha = _policy(input_root, job)
    source_sha = _v2_source_digest(source_root)
    if source_sha != job["source_collection_sha256"]:
        raise ManifestBlocked("V4_SOURCE_COLLECTION_SHA_MISMATCH")
    start = int(_clock(job["start"]).timestamp() * 1000)
    end = int(_clock(job["end"]).timestamp() * 1000)
    source, invalid, wallet_count, untrusted = _source(source_root, start, end)
    if _v2_source_digest(source_root) != source_sha:
        raise ManifestBlocked("V4_SOURCE_CHANGED_DURING_SCREEN")
    if "episode" in source.columns:
        episodes, source_counts = _episodes(source, end_ms=end, untrusted=untrusted)
        supported = episodes.filter(pl.col("source_status") == "SUPPORTED_EPISODE")
    else:
        episodes = pl.DataFrame()
        supported = pl.DataFrame()
        source_counts = {}
    prep_seconds = perf_counter() - t0
    market_sha = _sha(b"EMPTY_MARKET_PANEL_V1")
    market_days = 0
    if not supported.is_empty():
        matched, market_sha, market_days = _join_actions(_actions(supported), market_root)
        economics = _economics(matched, policy, scenarios=scenarios)
    else:
        economics = pl.DataFrame()
    elapsed = perf_counter() - t0
    summary = []
    for account in sorted(source["account"].unique().to_list()) if not source.is_empty() else []:
        subset = episodes.filter(pl.col("account") == account) if not episodes.is_empty() else None
        count = subset.height if subset is not None else 0
        eligible = (
            subset.filter(pl.col("source_status") == "SUPPORTED_EPISODE").height
            if subset is not None
            else 0
        )
        wallet_result = {
            "account_sha256": account,
            "episodes": count,
            "supported_episodes": eligible,
            "observation_days": source.filter(pl.col("account") == account)
            .select((pl.col("ms") // DAY_MS).n_unique())
            .item(),
            "source_episode_coverage": round(eligible / count, 8) if count else None,
            "native_markets": sorted(
                source.filter(pl.col("account") == account)["instrument"].unique().to_list()
            ),
            "scenarios": {},
        }
        for scenario in scenarios:
            group = (
                economics.filter((pl.col("account") == account) & (pl.col("scenario") == scenario))
                if not economics.is_empty()
                else None
            )
            valid = (
                group.filter(pl.col("estimated_net_pnl").is_not_null())
                if group is not None
                else None
            )
            filled = valid.height if valid is not None else 0
            recent = valid.filter(pl.col("t0") >= end - 7 * DAY_MS) if filled else None
            wallet_result["scenarios"][scenario] = {
                "estimated_net_pnl": round(float(valid["estimated_net_pnl"].sum()), 8)
                if filled
                else None,
                "estimated_complete_episodes": filled,
                "blocked_episodes": (group.height - filled) if group is not None else 0,
                "recent_7d_complete_episodes": recent.height if recent is not None else 0,
                "recent_7d_net_pnl": round(float(recent["estimated_net_pnl"].sum()), 8)
                if recent is not None and recent.height
                else None,
            }
        base = wallet_result["scenarios"].get("BASE", {})
        delayed = wallet_result["scenarios"].get("DELAYED", {})
        adverse = wallet_result["scenarios"].get("ADVERSE", {})
        base_pnl = base.get("estimated_net_pnl")
        wallet_result["sensitivity"] = {
            "delayed_minus_base_usd": round(delayed["estimated_net_pnl"] - base_pnl, 8)
            if base_pnl is not None and delayed.get("estimated_net_pnl") is not None
            else None,
            "adverse_minus_base_usd": round(adverse["estimated_net_pnl"] - base_pnl, 8)
            if base_pnl is not None and adverse.get("estimated_net_pnl") is not None
            else None,
        }
        summary.append(wallet_result)
    summary.sort(
        key=lambda r: (
            r["scenarios"].get("BASE", {}).get("estimated_net_pnl") is None,
            -(r["scenarios"].get("BASE", {}).get("estimated_net_pnl") or 0),
            -r["supported_episodes"],
            r["account_sha256"],
        )
    )
    results = {
        "schema": REPORT,
        "job_kind": job["kind"],
        "job_id": job["study_id"],
        "clock_basis": "HISTORICAL_ORACLE_PROXY_NOT_FIRST_KNOWN",
        "sizing_policy": "FROZEN_FIXED_K_NATIVE_QUANTITY",
        "execution_cost_policy": {
            "model": "EstimatedMinuteExecutionModel",
            "fee_bps_per_side": str(EstimatedMinuteExecutionModel().fee),
            "half_spread_bps": str(EstimatedMinuteExecutionModel().spread),
            "slippage_bps": str(EstimatedMinuteExecutionModel().slippage),
            "impact_bps_at_cap": str(EstimatedMinuteExecutionModel().impact),
            "max_participation_prior_complete_minute": str(EstimatedMinuteExecutionModel().cap),
            "adverse_extra_bps_per_side": "10",
        },
        "status": "ESTIMATED_HISTORICAL_FOLLOWER_PROXY_RESEARCH_ONLY",
        "scientifically_qualified": False,
        "authorized_for_trading": False,
        "financial_certified_real": False,
        "deployed": False,
        "order_route": "NONE",
        "scenario_definitions": list(scenarios),
        "source_collection_sha256": source_sha,
        "k_policy_sha256": policy_sha,
        "market_fingerprint_sha256": market_sha,
        "source_accounts": wallet_count,
        "accounts_with_in_window_events": len(summary),
        "source_fill_rows": source.height,
        "episode_candidates": episodes.height,
        "source_blockers": dict(sorted({**invalid, **source_counts}.items())),
        "economic_outcomes": (
            {r["outcome"]: r["len"] for r in economics.group_by("outcome").len().to_dicts()}
            if not economics.is_empty()
            else {}
        ),
        "market_input_days": market_days,
        "supported_episodes": supported.height,
        "source_episode_coverage": (
            round(supported.height / episodes.height, 8) if not episodes.is_empty() else None
        ),
        "market_matched_action_count": (
            int((matched["match_status"] == "MATCHED_SCREEN_ONLY").sum())
            if not supported.is_empty()
            else 0
        ),
        "market_candidate_action_count": (matched.height if not supported.is_empty() else 0),
        "market_action_coverage": (
            round(
                float((matched["match_status"] == "MATCHED_SCREEN_ONLY").sum()) / matched.height, 8
            )
            if not supported.is_empty() and matched.height
            else None
        ),
        "estimated_episode_results": int(economics["estimated_net_pnl"].is_not_null().sum())
        if not economics.is_empty()
        else 0,
        "wallet_ranking": summary,
        "shortlist_handoff": "PM03_PM04_SEPARATE_EXPLICIT_SHORTLIST_ONLY",
        "eligible_shortlist_wallets": [
            r["account_sha256"]
            for r in summary
            if r["scenarios"].get("BASE", {}).get("estimated_net_pnl") is not None
            and r["scenarios"]["BASE"]["estimated_complete_episodes"] > 0
        ],
    }
    encoded = _json_bytes(results)
    software_sha = _sha(
        b"".join(
            (Path(__file__).resolve().parent / name).read_bytes()
            for name in (
                "pm_v4_fast_screen.py",
                "pm_offline_job.py",
                "pm_offline_oracle_market.py",
                "pm_offline_market.py",
                "pm_offline_repository.py",
                "pm_offline_cache.py",
                "pm_shadow.py",
                "pm_vike_minute.py",
            )
        )
    )
    published = ImmutableCache(
        cache_root, max_object_bytes=64 * 1024 * 1024, min_free_bytes=1024 * 1024 * 1024
    ).publish(
        "v4_screen_report",
        {
            "source": source_sha,
            "policy": policy_sha,
            "market": market_sha,
            "software": software_sha,
            "job": _sha(_json_bytes(job)),
            "scenarios": _sha(_json_bytes({"items": scenarios})),
        },
        version=REPORT,
        content=encoded,
    )
    return {
        **results,
        "report_sha256": _sha(encoded),
        "report_cache_key": published["key"],
        "report_cache_status": published["status"],
        "runtime_seconds": round(elapsed, 6),
        "source_prepare_seconds": round(prep_seconds, 6),
    }


def run_from_manifest(
    job: dict,
    *,
    input_root: Path,
    source_root: Path | None,
    market_root: Path,
    cache_root: Path,
    workers: int = 1,
) -> dict:
    if source_root is None:
        raise ManifestInvalid("MISSING_REAL_SOURCE_ROOT")
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ManifestInvalid("INVALID_BOUNDED_WORKER_COUNT")
    return run_v4_screen(
        job,
        input_root=input_root,
        source_root=source_root,
        market_root=market_root,
        cache_root=cache_root,
    )


def shortlist_for_pm03(report: dict, account_sha256s: list[str]) -> dict:
    """Explicit stage-2 handoff, not a substitute for PM03/PM04 accounting."""
    if (
        not isinstance(report, dict)
        or report.get("schema") != REPORT
        or report.get("scientifically_qualified") is not False
        or not isinstance(account_sha256s, list)
        or not account_sha256s
        or len(set(account_sha256s)) != len(account_sha256s)
    ):
        raise ManifestInvalid("INVALID_V4_SHORTLIST_HANDOFF")
    volatile = {
        "report_sha256",
        "report_cache_key",
        "report_cache_status",
        "runtime_seconds",
        "source_prepare_seconds",
    }
    if report.get("report_sha256") != _sha(
        _json_bytes({k: v for k, v in report.items() if k not in volatile})
    ):
        raise ManifestBlocked("V4_SHORTLIST_REPORT_HASH_MISMATCH")
    if report.get("authorized_for_trading") is not False or report.get("order_route") != "NONE":
        raise ManifestBlocked("V4_SHORTLIST_UNSAFE_FINANCIAL_AUTHORITY")
    available = set(report.get("eligible_shortlist_wallets", ()))
    if not set(account_sha256s) <= available:
        raise ManifestBlocked("V4_SHORTLIST_MISSING_COMPLETED_BASE_ECONOMICS")
    selected = sorted(account_sha256s)
    return {
        "schema": "pm_v4_screen_pm03_shortlist_handoff_v1",
        "authority": "SEPARATE_PM03_PM04_FINANCIAL_SIMULATION_REQUIRED",
        "clock_basis": "HISTORICAL_ORACLE_PROXY",
        "research_only": True,
        "no_order_route": True,
        "wallet_sha256s": selected,
        "native_v4_instruments_by_wallet": {
            account: sorted(
                v4_instrument_key(market)
                for market in next(
                    row for row in report["wallet_ranking"] if row["account_sha256"] == account
                )["native_markets"]
            )
            for account in selected
        },
        "screen_report_sha256": report["report_sha256"],
        "source_sha256": report["source_collection_sha256"],
        "market_sha256": report["market_fingerprint_sha256"],
        "fixed_k_policy_sha256": report["k_policy_sha256"],
    }
