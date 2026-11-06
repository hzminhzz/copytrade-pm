"""Provisional market-wide Hyperliquid public wallet fills, no execution route.

Official WsTrade.users is [buyer, seller]. Unlike the CCXT trade cache, the
native public feed includes counterparties, but it has no globally complete
sequence proof, leader NAV, or subaccount/hedge attestation. Every receipt is
therefore D4 *candidate evidence*, never an admitted financial paper order.
The first streaming batch after a (re)subscription is a discarded baseline.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
from time import monotonic
from typing import Any, Callable, Mapping
from uuid import uuid4

from .pm03_account import Instrument, clock, digest, number
from .pm_e4_prospective import WS_URL
from .pm_forward_journal import PaperJournal
from .pm_forward_portfolios import _verify_sealed_definition_sha

ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
MAX_NATIVE_MARKETS = 8  # legacy per-WS shard size, preserved for existing configurations
MAX_NATIVE_SOCKET_MARKETS = 128  # explicit physical socket group, not the global universe
MAX_TOTAL_MARKETS = 256
MAX_PARALLEL_SHARDS = 5
MAX_FRAME_BYTES = 2_000_000
MAX_VOLUME_SAMPLE_TRADES = 100_000  # diagnostic cap; never a venue-complete tape
NATIVE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
NATIVE_DEX = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def native_coin(instrument: Instrument) -> str:
    if instrument.venue != "hyperliquid" or not instrument.market.startswith("mainnet:perp:"):
        raise ValueError("PUBLIC_TRADE_NOT_HYPERLIQUID_PERP")
    dex = instrument.market.removeprefix("mainnet:perp:")
    if NATIVE_DEX.fullmatch(dex) is None or NATIVE_TOKEN.fullmatch(instrument.symbol) is None:
        raise ValueError("PUBLIC_TRADE_INVALID_NATIVE_COIN")
    if dex == "default":
        return instrument.symbol
    return dex + ":" + instrument.symbol


def _bounded_market_universe(instruments: tuple[Instrument, ...]) -> tuple[Instrument, ...]:
    if not instruments or len(instruments) > MAX_TOTAL_MARKETS:
        raise ValueError("PUBLIC_TRADE_MARKET_UNIVERSE_LIMIT")
    coins = [native_coin(instrument) for instrument in instruments]
    if len(coins) != len(set(coins)):
        raise ValueError("PUBLIC_TRADE_DUPLICATE_MARKET")
    return tuple(sorted(instruments, key=lambda inst: inst.key))


def load_public_market_allowlist(path: Path) -> tuple[Instrument, ...]:
    """Read an explicit versioned perp-only market selection, never infer from CSV."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
        raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_UNAVAILABLE")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != "paper_public_market_allowlist_v1"
        ):
            raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_SCHEMA_INVALID")
        keys = payload.get("instruments")
        if not isinstance(keys, list) or not keys or len(keys) > 128:
            raise ValueError("PUBLIC_TRADE_MARKET_UNIVERSE_LIMIT")
        if not all(isinstance(key, str) for key in keys):
            raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_ID_INVALID")
        return _bounded_market_universe(tuple(Instrument.parse(key) for key in keys))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_UNREADABLE") from exc


def load_public_market_shards(path: Path) -> tuple[tuple[str, tuple[Instrument, ...]], ...]:
    """Load explicit operator shard identities, preserving the declared market order.

    V1 flat allowlists retain their previous automatic sorted sharding policy.
    V2 carries user-selected 8-market groups and their unique stable names.
    No market is silently substituted, dropped, or duplicated.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
        raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_UNAVAILABLE")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PUBLIC_TRADE_MARKET_ALLOWLIST_UNREADABLE") from exc
    if not isinstance(payload, dict):
        raise ValueError("PUBLIC_TRADE_MARKET_SHARDS_SCHEMA_INVALID")
    if payload.get("schema") == "paper_public_market_allowlist_v1":
        universe = load_public_market_allowlist(path)
        return tuple(
            (
                f"auto_shard_{i // MAX_NATIVE_MARKETS + 1:02d}",
                universe[i : i + MAX_NATIVE_MARKETS],
            )
            for i in range(0, len(universe), MAX_NATIVE_MARKETS)
        )
    schema = payload.get("schema")
    if schema not in {"paper_public_market_shards_v1", "paper_public_physical_sockets_v1"}:
        raise ValueError("PUBLIC_TRADE_MARKET_SHARDS_SCHEMA_INVALID")
    physical = schema == "paper_public_physical_sockets_v1"
    group_defs = payload.get("physical_sockets" if physical else "shards")
    if not isinstance(group_defs, list) or not (
        len(group_defs) == 3 if physical else 1 <= len(group_defs) <= 16
    ):
        raise ValueError("PUBLIC_TRADE_MARKET_SHARD_COUNT_INVALID")
    if physical:
        sha = payload.get("source_snapshot_sha256")
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or payload.get("propr_order_ids_attested") is not False
            or payload.get("paper_admitted") is not False
        ):
            raise ValueError("PUBLIC_TRADE_PROPR_DISPLAY_PROVENANCE_REQUIRED")
    result: list[tuple[str, tuple[Instrument, ...]]] = []
    names: set[str] = set()
    for item in group_defs:
        if not isinstance(item, dict) or set(item) != {"name", "instruments"}:
            raise ValueError("PUBLIC_TRADE_MARKET_SHARD_FIELDS_INVALID")
        name, raw = item["name"], item["instruments"]
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{1,63}", name) is None
            or name in names
        ):
            raise ValueError("PUBLIC_TRADE_MARKET_SHARD_NAME_INVALID_OR_DUPLICATE")
        if (
            not isinstance(raw, list)
            or not 1 <= len(raw) <= (MAX_NATIVE_SOCKET_MARKETS if physical else MAX_NATIVE_MARKETS)
            or any(not isinstance(x, str) for x in raw)
        ):
            raise ValueError("PUBLIC_TRADE_MARKET_SHARD_SIZE_INVALID")
        names.add(name)
        instruments = tuple(Instrument.parse(x) for x in raw)
        for inst in instruments:
            native_coin(inst)
        result.append((name, instruments))
    universe = tuple(inst for _, group in result for inst in group)
    _bounded_market_universe(universe)
    if physical:
        if payload.get("native_market_count") != len(universe):
            raise ValueError("PUBLIC_TRADE_PROPR_NATIVE_MARKET_COUNT_DRIFT")
        categories = payload.get("display_category_counts")
        if (
            not isinstance(categories, dict)
            or payload.get("display_market_count") != sum(categories.values())
            or payload["display_market_count"] - len(universe)
            != payload.get("deduplicated_display_symbols")
            or len(result[0][1]) != 8
            or any(
                inst.market != "mainnet:perp:default" for _, group in result[:2] for inst in group
            )
            or any(inst.market != "mainnet:perp:xyz" for inst in result[2][1])
        ):
            raise ValueError("PUBLIC_TRADE_PROPR_SOCKET_CATEGORY_DRIFT")
        logical = payload.get("logical_reporting_groups", [])
        if not isinstance(logical, list) or any(
            not isinstance(group, dict)
            or not isinstance(group.get("instruments"), list)
            or any(key not in {i.key for i in universe} for key in group["instruments"])
            for group in logical
        ):
            raise ValueError("PUBLIC_TRADE_PROPR_LOGICAL_GROUP_DRIFT")
    return tuple(result)


def validate_public_market_catalog(
    instruments: tuple[Instrument, ...],
    *,
    info: Callable[[dict], tuple[Any, bytes, str]] | None = None,
    allow_partial: bool = False,
) -> dict:
    """Validate every configured native perp against current official /info metadata.

    This is a current availability preflight, not a historical PIT listing or
    source wallet's historical activity. Failed/unavailable markets abort.
    """
    from .pm_e4_prospective import _guarded_info

    selected = _bounded_market_universe(instruments)
    provider = _guarded_info if info is None else info
    dexs: dict[str, set[str]] = {}
    for inst in selected:
        dex = inst.market.removeprefix("mainnet:perp:")
        dexs.setdefault(dex, set()).add(native_coin(inst))
    proofs, unavailable = [], []
    for dex in sorted(dexs):
        request = {"type": "meta"} if dex == "default" else {"type": "meta", "dex": dex}
        payload, raw, response_sha = provider(request)
        if not isinstance(payload, dict) or not isinstance(payload.get("universe"), list):
            raise ValueError("PUBLIC_TRADE_CATALOG_SCHEMA_INVALID")
        actual = {}
        for row in payload["universe"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise ValueError("PUBLIC_TRADE_CATALOG_ENTRY_INVALID")
            if row["name"] in actual:
                raise ValueError("PUBLIC_TRADE_CATALOG_DUPLICATE_COIN")
            actual[row["name"]] = row
        invalid = sorted(
            coin
            for coin in dexs[dex]
            if coin not in actual or actual[coin].get("isDelisted") is True
        )
        if invalid and not allow_partial:
            raise ValueError("PUBLIC_TRADE_CATALOG_MARKET_UNAVAILABLE:" + ",".join(invalid))
        unavailable.extend(invalid)
        if not isinstance(response_sha, str) or len(response_sha) != 64:
            raise ValueError("PUBLIC_TRADE_CATALOG_PROVENANCE_INVALID")
        if not isinstance(raw, bytes):
            raise ValueError("PUBLIC_TRADE_CATALOG_RAW_MISSING")
        from hashlib import sha256

        if sha256(raw).hexdigest() != response_sha:
            raise ValueError("PUBLIC_TRADE_CATALOG_SHA_MISMATCH")
        proofs.append({"dex": dex, "catalog_sha256": response_sha, "markets": len(dexs[dex])})
    return {
        "schema": "paper_public_market_catalog_preflight_v1",
        "status": "PARTIAL_MARKETS_AVAILABLE"
        if unavailable
        else "ALL_MARKETS_PRESENT_AT_PREFLIGHT",
        "markets_verified": len(selected) - len(unavailable),
        "unavailable_markets": sorted(unavailable),
        "catalog_proofs": proofs,
        "source_complete": False,
        "paper_admitted": False,
    }


def registry_watched_addresses(
    db_path: Path, portfolio_ids: tuple[str, ...], *, as_of: str
) -> dict[str, str]:
    """Resolve sealed portfolios from SQLite, never a Markdown alias map.

    Addresses are used in process memory only. The journal writes numeric
    wallet references, not the underlying private roster.
    """
    if not portfolio_ids or len(portfolio_ids) != len(set(portfolio_ids)):
        raise ValueError("PUBLIC_TRADE_PORTFOLIO_CENSUS_INVALID")
    clock(as_of)
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("PUBLIC_TRADE_REGISTRY_MISSING")
    conn = sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    watched: dict[str, str] = {}
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")  # one consistent SQLite registry generation across portfolios
        for pid in portfolio_ids:
            seal = conn.execute(
                "SELECT version, definition_sha256, selection_known_at "
                "FROM portfolio_seals WHERE portfolio_id=? "
                "ORDER BY version DESC LIMIT 1",
                (pid,),
            ).fetchone()
            if seal is None or clock(seal["selection_known_at"]) > clock(as_of):
                raise ValueError("PUBLIC_TRADE_PORTFOLIO_NOT_SEALED_ASOF")
            definition_sha = seal["definition_sha256"]
            if (
                not isinstance(definition_sha, str)
                or len(definition_sha) != 64
                or any(c not in "0123456789abcdef" for c in definition_sha)
            ):
                raise ValueError("PUBLIC_TRADE_UNVERIFIED_PORTFOLIO_SEAL")
            version = seal["version"]
            members = conn.execute(
                "SELECT p.member_alias,p.wallet_id,w.address,w.venue,w.network "
                "FROM portfolio_memberships p LEFT JOIN wallets w "
                "ON p.wallet_id=w.wallet_id "
                "WHERE p.portfolio_id=? AND p.version=? ORDER BY p.member_alias",
                (pid, version),
            ).fetchall()
            if not members or any(row["wallet_id"] is None for row in members):
                raise ValueError("PUBLIC_TRADE_PORTFOLIO_IDENTITY_UNRESOLVED")
            _verify_sealed_definition_sha(
                conn,
                pid,
                version,
                tuple(row["member_alias"] for row in members),
                seal["definition_sha256"],
            )
            for row in members:
                if row["venue"] != "hyperliquid" or row["network"] != "mainnet":
                    raise ValueError("PUBLIC_TRADE_NON_HL_WALLET")
                address = row["address"].lower()
                if ADDRESS.fullmatch(address) is None:
                    raise ValueError("PUBLIC_TRADE_WALLET_ADDRESS_INVALID")
                excluded = conn.execute(
                    "SELECT 1 FROM exclusions WHERE wallet_id=? LIMIT 1",
                    (row["wallet_id"],),
                ).fetchone()
                denylist_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='propfirm_exclusions'"
                ).fetchone()
                if denylist_exists is not None:
                    additional = conn.execute(
                        "SELECT 1 FROM propfirm_exclusions WHERE wallet_id=? LIMIT 1",
                        (row["wallet_id"],),
                    ).fetchone()
                    if additional is not None:
                        raise ValueError("PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED")
                if excluded is not None:
                    raise ValueError("PUBLIC_TRADE_WALLET_EXCLUDED")
                ref = "wallet:" + str(row["wallet_id"])
                if address in watched and watched[address] != ref:
                    raise ValueError("PUBLIC_TRADE_ADDRESS_IDENTITY_CONFLICT")
                watched[address] = ref
    finally:
        conn.close()
    return watched


def normalize_native_trade(
    raw: Mapping[str, Any],
    *,
    instrument: Instrument,
    watched: Mapping[str, str],
    first_known_at: str,
    stream_epoch: str,
) -> list[dict]:
    """Two signed wallet fills per public trade if both parties are watched."""
    if raw.get("coin") != native_coin(instrument):
        raise ValueError("PUBLIC_TRADE_COIN_IDENTITY_MISMATCH")
    users = raw.get("users")
    if (
        not isinstance(users, (tuple, list))
        or len(users) != 2
        or any(not isinstance(addr, str) for addr in users)
    ):
        raise ValueError("PUBLIC_TRADE_BUYER_SELLER_UNKNOWN")
    buyer, seller = (addr.lower() for addr in users)
    if ADDRESS.fullmatch(buyer) is None or ADDRESS.fullmatch(seller) is None:
        raise ValueError("PUBLIC_TRADE_COUNTERPARTY_INVALID")
    if raw.get("side") not in ("B", "A"):
        raise ValueError("PUBLIC_TRADE_AGGRESSOR_UNKNOWN")
    stamp, tid = raw.get("time"), raw.get("tid")
    if type(stamp) is not int or stamp <= 0 or type(tid) is not int or tid < 0:
        raise ValueError("PUBLIC_TRADE_NATIVE_ID_INVALID")
    source_at = datetime.fromtimestamp(stamp / 1000, tz=UTC).isoformat()
    if clock(source_at) > clock(first_known_at):
        raise ValueError("PUBLIC_TRADE_FUTURE_SOURCE_CLOCK")
    price, size = number(raw.get("px")), number(raw.get("sz"))
    if price <= 0 or size <= 0:
        raise ValueError("PUBLIC_TRADE_PRICE_SIZE_INVALID")
    tx_hash = raw.get("hash")
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise ValueError("PUBLIC_TRADE_TRANSACTION_HASH_INVALID")
    if (
        not isinstance(stream_epoch, str)
        or len(stream_epoch) != 32
        or any(c not in "0123456789abcdef" for c in stream_epoch)
    ):
        raise ValueError("PUBLIC_TRADE_STREAM_EPOCH_INVALID")

    matched = [
        (address, side, qty)
        for address, side, qty in ((buyer, "BUY", size), (seller, "SELL", -size))
        if address in watched
    ]
    if not matched:
        # Validate the public trade above, but avoid expensive watchlist/raw
        # hashing for every unrelated exchange trade across many markets.
        return []
    first_known_at = clock(first_known_at).astimezone(UTC).isoformat(timespec="microseconds")
    trade_sha = digest(dict(raw))
    # Bind each receipt to the complete in-memory SQLite-resolved watchlist.
    # Numeric registry wallet IDs are generation-local, not global identities.
    watchlist_sha = digest(sorted(watched.items()))
    results = []
    for address, side, qty in matched:
        wallet_key = watched[address]
        if not wallet_key.startswith("wallet:") or not wallet_key[7:].isdecimal():
            raise ValueError("PUBLIC_TRADE_NOT_CANONICAL_REGISTRY_WALLET")
        results.append(
            {
                "schema": "paper_public_wallet_trade_v1",
                "wallet_key": wallet_key,
                "instrument": instrument.key,
                "source_timestamp_ms": stamp,
                "native_tid": tid,
                "event_key": digest([instrument.key, stamp, tid, wallet_key, side]),
                "source_event_at": source_at,
                "first_known_at": first_known_at,
                "stream_epoch": stream_epoch,
                "wallet_side": side,
                "signed_qty": str(qty),
                "price": str(price),
                "source_trade_sha": trade_sha,
                "watchlist_sha": watchlist_sha,
                "evidence_class": "PUBLIC_TRADE_PROVISIONAL_NO_NAV",
                "provider_signed": False,
                "source_account_complete": False,
                "paper_admitted": False,
                "order_route": "NONE",
            }
        )
    return results


class PersistentPublicMarket:
    """Reuse canonical PR118 wallet-side receipts on a retained native socket."""

    def __init__(
        self,
        journal: PaperJournal,
        instrument: Instrument,
        watched: dict,
        *,
        scope_sha: str,
        max_ids: int = 2000,
    ):
        from .pm_forward_stream_journal import StreamProgress

        native_coin(instrument)
        if not 2 <= max_ids <= 10000:
            raise ValueError("PUBLIC_NATIVE_ID_BUFFER_INVALID")
        self.journal, self.instrument, self.watched = journal, instrument, watched
        self.scope_sha, self.max_ids = scope_sha, max_ids
        self.progress = StreamProgress(journal, "public:" + instrument.key)
        self.epoch = None
        # Restart always takes a fresh excluded baseline. The canonical wallet
        # receipts provide durable deduplication; this bounded cache is local.
        self._seen = {}

    def begin(self, known_at: str) -> dict:
        epoch = uuid4().hex
        state = {
            **self.progress.checkpoint,
            "baseline_valid": False,
            "subscription_acknowledged": False,
            "transport": "CONNECTING",
            "scope_sha": self.scope_sha,
            "last_transport_at": known_at,
            "watchlist_sha": digest(sorted(self.watched.items())),
        }
        result = self.progress.commit(
            self.progress.propose(
                epoch=epoch,
                kind="GAP",
                known_at=known_at,
                checkpoint=state,
                details={"reason": "CONNECT_OR_PROCESS_RESTART"},
            )
        )
        self.epoch = epoch
        self._seen = {}
        return result

    def transport(self, known_at: str) -> dict:
        if self.progress.head["event"] and clock(known_at) <= clock(
            self.progress.head["event"]["first_known_at"]
        ):
            return {"status": "TRANSPORT_ALREADY_OBSERVED", "order_route": "NONE"}
        state = {
            **self.progress.checkpoint,
            "transport": "CONNECTED",
            "last_transport_at": known_at,
        }
        return self.progress.commit(
            self.progress.propose(
                epoch=self.epoch,
                kind="TRANSPORT",
                known_at=known_at,
                checkpoint=state,
            )
        )

    def gap(self, known_at: str, reason: str) -> dict:
        state = {
            **self.progress.checkpoint,
            "baseline_valid": False,
            "transport": "DEGRADED",
            "gap_reason": reason,
        }
        return self.progress.commit(
            self.progress.propose(
                epoch=self.epoch,
                kind="GAP",
                known_at=known_at,
                checkpoint=state,
                details={"reason": reason},
            )
        )

    def observe(
        self,
        rows: list[dict],
        known_at: str,
        *,
        snapshot: bool = False,
        raw_sha: str | None = None,
        raw_text: str | None = None,
    ) -> dict:
        if self.epoch is None or not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError("PUBLIC_NATIVE_FRAME_INVALID")
        prior = self.progress.checkpoint
        baseline = not prior.get("baseline_valid", False) or snapshot
        seen = dict(self._seen)
        events, fresh = [], 0
        latest = prior.get("last_native_ms", 0)
        for row in rows:
            # Normalize even unselected counterparties: malformed market data
            # cannot quietly qualify the frame or advance continuity.
            normalized = normalize_native_trade(
                row,
                instrument=self.instrument,
                watched=self.watched,
                first_known_at=known_at,
                stream_epoch=self.epoch,
            )
            identity = digest([self.instrument.key, row["time"], row["tid"]])
            trade_sha = digest(row)
            old = seen.get(identity)
            if old is not None and old != trade_sha:
                raise ValueError("PUBLIC_NATIVE_TRADE_ID_CONFLICT")
            if not baseline and old is None and row["time"] < latest:
                raise ValueError("PUBLIC_NATIVE_EVENT_CLOCK_REGRESSION")
            if old is None:
                fresh += 1
                if not baseline:
                    events.extend(normalized)
                seen[identity] = trade_sha
            latest = max(latest, row["time"])
        if not baseline and not fresh:
            return {
                "new_receipts": 0,
                "status": "DUPLICATE_PUBLIC_NATIVE_FRAME",
                "order_route": "NONE",
            }
        state = {
            **prior,
            "baseline_valid": True,
            "transport": "CONNECTED",
            "last_transport_at": known_at,
            "last_market_trade_at": known_at,
            "last_native_ms": latest,
            "recent_ids_sha": digest(list(seen.items())[-self.max_ids :]),
            "recent_ids_count": min(len(seen), self.max_ids),
            "scope_sha": self.scope_sha,
            "trade_volume_complete": False,
            "matched_proposal_count": prior.get("matched_proposal_count", 0) + len(events),
        }
        event = self.progress.propose(
            epoch=self.epoch,
            kind="BASELINE" if baseline else "OBSERVATION",
            known_at=known_at,
            checkpoint=state,
            raw_sha=raw_sha or digest(rows),
            source_at=datetime.fromtimestamp(latest / 1000, UTC).isoformat() if rows else None,
            details={
                "native_trades": rows,
                "native_wire": raw_text,
                "baseline_excluded": baseline,
                "timing_policy": "FIRST_SIGNAL_PLUS_5M",
                "candidate_count": len(events),
                "native_trade_count": len(rows),
            },
        )
        if events:
            result = self.progress.commit(
                event,
                lambda e: self.journal.append_public_wallet_trades(
                    events,
                    stream_event=e,
                ),
            )
        else:
            self.progress.commit(event)
            result = {"new_receipts": 0, "order_route": "NONE"}
        self._seen = dict(list(seen.items())[-self.max_ids :])
        return {**result, "baseline_excluded": baseline, "paper_admitted": False}


def reconcile_public_wallet_fills(
    *,
    journal: PaperJournal,
    watched: Mapping[str, str],
    start_at: str,
    end_at: str,
    required_markets: tuple[Instrument, ...],
    info=None,
    now=lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
) -> dict:
    """Independent public REST comparison, recorded only as later audit evidence.

    The bounded API response does not prove exchange-wide completeness. No
    recovered row is inserted into the prospective candidate/source tables.
    """
    from contextlib import closing
    from hashlib import sha256
    import sqlite3
    from .pm_e4_prospective import _guarded_info
    from .pm_forward_stream_journal import StreamProgress

    start, end = clock(start_at), clock(end_at)
    if not 0 <= (end - start).total_seconds() <= 86400 or len(watched) > 10:
        raise ValueError("PUBLIC_RECONCILIATION_WINDOW_OR_ACCOUNT_BOUND")
    provider = info or _guarded_info
    markets = {native_coin(inst): inst for inst in required_markets}
    summary = {
        "schema": "paper_public_fill_reconciliation_v1",
        "start_at": start_at,
        "end_at": end_at,
        "independent_matches": 0,
        "recovered_later": 0,
        "unresolved": 0,
        "outside_scope": 0,
        "accounts_checked": 0,
        "comparison_complete": False,
        "comparison_scope": "ONLY_OFFICIAL_API_RETURNED_ROWS",
        "financial_events_committed": 0,
        "order_route": "NONE",
    }
    for address, wallet in sorted(watched.items(), key=lambda item: item[1]):
        if (
            ADDRESS.fullmatch(address) is None
            or re.fullmatch(r"wallet:[1-9][0-9]*", wallet) is None
        ):
            raise ValueError("PUBLIC_RECONCILIATION_CANONICAL_IDENTITY_REQUIRED")
        response, raw, sha = provider(
            {
                "type": "userFillsByTime",
                "user": address,
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
                "aggregateByTime": False,
            }
        )
        known = now()  # Actual later availability, never the original trade timestamp.
        if clock(known) < end or not isinstance(raw, bytes) or sha256(raw).hexdigest() != sha:
            raise ValueError("PUBLIC_RECONCILIATION_RESPONSE_CLOCK_OR_SHA_INVALID")
        if not isinstance(response, list) or len(response) > 2000:
            raise ValueError("PUBLIC_RECONCILIATION_RESPONSE_SHAPE_UNSUPPORTED")
        with closing(
            sqlite3.connect("file:" + str(journal.path.resolve()) + "?mode=ro", uri=True)
        ) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            candidates = {}
            for payload, payload_sha in db.execute(
                "SELECT payload,payload_sha FROM public_wallet_trade_receipts WHERE wallet_key=?",
                (wallet,),
            ):
                candidate = json.loads(payload)
                if digest(candidate) != payload_sha:
                    raise ValueError("PUBLIC_RECONCILIATION_CANDIDATE_DIVERGENCE")
                if start <= clock(candidate["source_event_at"]) <= end:
                    candidates[candidate["event_key"]] = candidate
        outcomes, seen, matched = [], {}, set()
        counts = {
            "independent_matches": 0,
            "recovered_later": 0,
            "unresolved": 0,
            "outside_scope": 0,
        }
        for fill in response:
            if not isinstance(fill, dict):
                raise ValueError("PUBLIC_RECONCILIATION_FILL_SCHEMA_INVALID")
            coin, tid, at = fill.get("coin"), fill.get("tid"), fill.get("time")
            if type(tid) is not int or type(at) is not int or fill.get("side") not in {"A", "B"}:
                raise ValueError("PUBLIC_RECONCILIATION_FILL_IDENTITY_UNKNOWN")
            source_at = datetime.fromtimestamp(at / 1000, UTC).isoformat()
            if not start <= clock(source_at) <= end:
                raise ValueError("PUBLIC_RECONCILIATION_OUTSIDE_REQUESTED_WINDOW")
            price, amount = number(fill.get("px")), number(fill.get("sz"))
            if price <= 0 or amount <= 0:
                raise ValueError("PUBLIC_RECONCILIATION_FILL_PRICE_SIZE_INVALID")
            side = "BUY" if fill["side"] == "B" else "SELL"
            identity = digest([coin, tid, at, side])
            stable = digest([coin, tid, at, side, str(price), str(amount)])
            if identity in seen:
                if seen[identity] != stable:
                    raise ValueError("PUBLIC_RECONCILIATION_CONFLICTING_OFFICIAL_ID")
                continue
            seen[identity] = stable
            inst = markets.get(coin)
            if inst is None:
                counts["outside_scope"] += 1
                continue
            key = digest([inst.key, at, tid, wallet, side])
            candidate = candidates.get(key)
            if candidate is None:
                status, counter = "RECOVERED_AT_LATER_TIME", "recovered_later"
            elif number(candidate["price"]) != price or number(candidate["signed_qty"]) != (
                amount if side == "BUY" else -amount
            ):
                status, counter = "UNRESOLVED_NATIVE_ID_CONFLICT", "unresolved"
            else:
                status, counter = "INDEPENDENT_MATCH", "independent_matches"
                matched.add(key)
            counts[counter] += 1
            outcomes.append(
                {
                    "event_key": key,
                    "instrument": inst.key,
                    "source_event_at": source_at,
                    "official_native_tid": tid,
                    "recovery_first_known_at": known,
                    "original_candidate_first_known_at": candidate["first_known_at"]
                    if candidate
                    else None,
                    "classification": status,
                    "signal_eligible": False,
                    "official_fill_sha": digest(fill),
                }
            )
        for key in sorted(candidates.keys() - matched):
            if not any(row["event_key"] == key for row in outcomes):
                counts["unresolved"] += 1
                outcomes.append(
                    {
                        "event_key": key,
                        "classification": "UNRESOLVED_NO_OFFICIAL_MATCH",
                        "recovery_first_known_at": known,
                        "signal_eligible": False,
                    }
                )
        progress = StreamProgress(journal, "reconcile:" + wallet)
        event = progress.propose(
            epoch=uuid4().hex,
            kind="RECONCILIATION",
            known_at=known,
            checkpoint={
                "last_checked_end_at": end_at,
                "comparison_complete": False,
                "history_limit_reached": len(response) == 2000,
                **counts,
            },
            raw_sha=sha,
            details={
                "start_at": start_at,
                "end_at": end_at,
                "rows": outcomes,
                "official_response": response,
                "signal_eligible": False,
            },
        )
        progress.commit(event)
        for key, value in counts.items():
            summary[key] += value
        summary["accounts_checked"] += 1
    summary["live_match_status"] = (
        "INDEPENDENT_WATCHED_MATCH_OBSERVED"
        if summary["independent_matches"]
        else "LIVE_MATCH_UNKNOWN"
    )
    return summary


async def capture_bounded_native_trades(
    *,
    instruments: tuple[Instrument, ...],
    watched: Mapping[str, str],
    journal: PaperJournal,
    duration_seconds: float = 10,
    max_frames: int = 500,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
    journal_write_lock: asyncio.Lock | None = None,
    max_markets_per_socket: int = MAX_NATIVE_MARKETS,
) -> dict:
    """Shared public WS, bounded transport; default retains legacy 8 markets."""
    if (
        not 1 <= max_markets_per_socket <= MAX_NATIVE_SOCKET_MARKETS
        or not instruments
        or len(instruments) > max_markets_per_socket
    ):
        raise ValueError("PUBLIC_TRADE_MAX_MARKET_SHARD_EXCEEDED")
    if not (0.5 <= duration_seconds <= 120 and 1 <= max_frames <= 50000):
        raise ValueError("PUBLIC_TRADE_CAPTURE_BOUNDS_INVALID")
    if not watched or any(ADDRESS.fullmatch(addr) is None for addr in watched):
        raise ValueError("PUBLIC_TRADE_WATCHLIST_INVALID")
    markets = {native_coin(inst): inst for inst in instruments}
    if len(markets) != len(instruments):
        raise ValueError("PUBLIC_TRADE_DUPLICATE_MARKET")
    if connect is None:
        import websockets

        connect = websockets.connect

    epoch = uuid4().hex
    baselined: set[str] = set()
    volume_seen: dict[tuple[str, int, int], str] = {}
    volume_base = {inst.key: Decimal(0) for inst in instruments}
    volume_notional = {inst.key: Decimal(0) for inst in instruments}
    stats = {
        inst.key: {
            "frames": 0,
            "baseline_messages": 0,
            "active_messages": 0,
            "public_trade_rows": 0,
            "matched_wallet_sides": 0,
            "new_wallet_receipts": 0,
            "observed_unique_trade_rows": 0,
            "duplicate_public_trade_rows": 0,
            "volume_sample_truncated": False,
        }
        for inst in instruments
    }

    async def _journal_call(action: Callable[..., Any], **kwargs: Any) -> dict:
        if journal_write_lock is None:
            return await asyncio.to_thread(action, **kwargs)
        async with journal_write_lock:
            return await asyncio.to_thread(action, **kwargs)

    received = accepted = matches = 0
    started = monotonic()
    failure = None
    try:
        async with connect(
            WS_URL,
            open_timeout=12,
            close_timeout=5,
            ping_interval=15,
            ping_timeout=12,
            max_size=MAX_FRAME_BYTES,
        ) as ws:
            for coin in markets:
                await ws.send(
                    json.dumps(
                        {
                            "method": "subscribe",
                            "subscription": {"type": "trades", "coin": coin},
                        }
                    )
                )
            while received < max_frames:
                remain = duration_seconds - (monotonic() - started)
                if remain <= 0:
                    break
                try:
                    wire = await asyncio.wait_for(ws.recv(), timeout=remain)
                except TimeoutError:
                    break
                known = now()  # stamp on reception, before decoding and SQLite I/O
                received += 1
                if not isinstance(wire, str) or len(wire.encode()) > MAX_FRAME_BYTES:
                    raise ValueError("PUBLIC_TRADE_FRAME_INVALID")
                envelope = json.loads(wire)
                if not isinstance(envelope, dict):
                    raise ValueError("PUBLIC_TRADE_ENVELOPE_INVALID")
                if envelope.get("channel") == "subscriptionResponse":
                    continue
                if envelope.get("channel") == "error":
                    raise ValueError("PUBLIC_TRADE_SUBSCRIPTION_REJECTED")
                if envelope.get("channel") != "trades":
                    raise ValueError("PUBLIC_TRADE_UNEXPECTED_CHANNEL")
                rows = envelope.get("data")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("PUBLIC_TRADE_WS_BATCH_INVALID")
                baseline_coins = set()
                received_coins = set()
                for trade in rows:
                    if not isinstance(trade, dict) or trade.get("coin") not in markets:
                        raise ValueError("PUBLIC_TRADE_UNSUBSCRIBED_COIN")
                    received_coins.add(trade["coin"])
                    if trade["coin"] not in baselined:
                        baseline_coins.add(trade["coin"])
                for coin in received_coins:
                    stats[markets[coin].key]["frames"] += 1
                    if coin in baseline_coins:
                        stats[markets[coin].key]["baseline_messages"] += 1
                    elif envelope.get("isSnapshot") is not True:
                        stats[markets[coin].key]["active_messages"] += 1
                for coin in sorted(baseline_coins):
                    await _journal_call(
                        journal.append_public_trade_gap,
                        instrument=markets[coin].key,
                        stream_epoch=epoch,
                        observed_at=known,
                        reason="INITIAL_BASELINE",
                    )
                baselined.update(baseline_coins)
                by_instrument: dict[str, list[dict]] = {}
                for trade in rows:
                    coin = trade["coin"]
                    # Discard the whole first batch per market, not just its first trade.
                    if coin in baseline_coins or envelope.get("isSnapshot") is True:
                        continue
                    inst = markets[coin]
                    stats[inst.key]["public_trade_rows"] += 1
                    events = normalize_native_trade(
                        trade,
                        instrument=inst,
                        watched=watched,
                        first_known_at=known,
                        stream_epoch=epoch,
                    )
                    stats[inst.key]["matched_wallet_sides"] += len(events)
                    by_instrument.setdefault(inst.key, []).extend(events)
                    # Public venue trades are a bounded diagnostic sample.
                    # Deduplicate repeated native IDs (including non-watched
                    # counterparties) without fabricating continuous volume.
                    trade_id = (inst.key, trade["time"], trade["tid"])
                    row_sha = digest(dict(trade))
                    prior_sha = volume_seen.get(trade_id)
                    if prior_sha is not None:
                        if prior_sha != row_sha:
                            raise ValueError("PUBLIC_TRADE_VOLUME_ID_CONFLICT")
                        stats[inst.key]["duplicate_public_trade_rows"] += 1
                    elif len(volume_seen) >= MAX_VOLUME_SAMPLE_TRADES:
                        # Continue wallet receipt capture normally, but mark
                        # volume incomplete rather than overrun local memory.
                        stats[inst.key]["volume_sample_truncated"] = True
                    else:
                        volume_seen[trade_id] = row_sha
                        stats[inst.key]["observed_unique_trade_rows"] += 1
                        qty = number(trade["sz"])
                        volume_base[inst.key] += qty
                        volume_notional[inst.key] += qty * number(trade["px"])
                for inst_key in sorted(by_instrument):
                    events = by_instrument[inst_key]
                    if events:
                        result = await _journal_call(
                            journal.append_public_wallet_trades, events=events
                        )
                        accepted += result["new_receipts"]
                        matches += len(events)
                        stats[inst_key]["new_wallet_receipts"] += result["new_receipts"]
    except asyncio.CancelledError:
        failure = "DISCONNECT"
        raise
    except Exception:
        failure = "INTEGRITY_FAILURE"
        raise
    finally:
        closed_at = now()
        for inst in instruments:
            await _journal_call(
                journal.append_public_trade_gap,
                instrument=inst.key,
                stream_epoch=epoch,
                observed_at=closed_at,
                reason=failure or "BOUNDED_CAPTURE_ENDED",
            )

    return {
        "schema": "paper_public_market_wallet_trade_capture_v1",
        "status": "PROVISIONAL_OBSERVATION_ONLY",
        "stream_epoch": epoch,
        "frames_received": received,
        "matched_wallet_sides": matches,
        "new_wallet_receipts": accepted,
        "baseline_markets": len(baselined),
        "all_markets_baselined": len(baselined) == len(markets),
        "market_stats": {
            inst.key: {
                **stats[inst.key],
                "observed_unique_base_volume": str(volume_base[inst.key]),
                "observed_unique_quote_notional": str(volume_notional[inst.key]),
                "volume_evidence": "BOUNDED_POST_BASELINE_WS_SAMPLE_NOT_COMPLETE_VOLUME",
                "volume_capacity_attested": False,
                "status": (
                    "ACTIVE_AFTER_BASELINE"
                    if stats[inst.key]["active_messages"] > 0
                    else "BASELINE_ONLY"
                    if inst.key in {markets[c].key for c in baselined}
                    else "NO_MARKET_FRAMES"
                ),
            }
            for inst in sorted(instruments, key=lambda inst: inst.key)
        },
        "coverage_complete": False,
        "whole_wallet_nav_attested": False,
        "paper_admitted": False,
        "order_route": "NONE",
    }


def plan_latest_public_utc_bucket(
    *,
    journal: PaperJournal,
    instruments: tuple[Instrument, ...],
    wallet_keys: tuple[str, ...],
    as_of: str,
    timing_policy: str = "UTC_BUCKET_CLOSE",
) -> dict:
    """Run one deterministic, durable, NONFINANCIAL UTC scheduling cycle.

    This reads only candidate trade receipts. It does not infer an opening
    position, account NAV, executable follower quantity or virtual fill.
    """
    if timing_policy not in {"UTC_BUCKET_CLOSE", "UTC_BUCKET_PLUS_5M"}:
        raise ValueError("PUBLIC_BUCKET_POLICY_UNSUPPORTED")
    if not instruments or len(instruments) > MAX_NATIVE_SOCKET_MARKETS:
        raise ValueError("PUBLIC_BUCKET_MARKET_LIMIT")
    if not wallet_keys or len(wallet_keys) > 50 or len(set(wallet_keys)) != len(wallet_keys):
        raise ValueError("PUBLIC_BUCKET_WALLET_LIMIT")
    if any(not x.startswith("wallet:") or not x[7:].isdecimal() for x in wallet_keys):
        raise ValueError("PUBLIC_BUCKET_CANONICAL_ID_REQUIRED")
    checked = clock(as_of).astimezone(UTC)
    boundary = checked.replace(minute=(checked.minute // 5) * 5, second=0, microsecond=0)
    offset = timedelta(minutes=5 if timing_policy == "UTC_BUCKET_CLOSE" else 10)
    bucket_start = boundary - offset
    due_at = bucket_start + offset
    outcome = []
    for instrument in sorted(instruments, key=lambda x: x.key):
        native_coin(instrument)
        for wallet_key in sorted(wallet_keys):
            report = journal.observed_utc_net_delta(
                wallet_key,
                instrument.key,
                bucket_start_at=bucket_start.isoformat(),
                as_of=as_of,
            )
            if report["status"] == "WAIT":
                raise ValueError("PUBLIC_BUCKET_DUE_BEFORE_END")
            if report["event_count"] == 0 and report["late_event_count"] == 0:
                continue
            journal.audit_public_wallet_trade_tape(wallet_key, instrument.key)
            try:
                seal = journal.persist_observed_utc_bucket(report)
                status = seal["status"]
            except ValueError as exc:
                if "CORRECTION" not in str(exc):
                    raise
                # An already-sealed bucket cannot be changed by a late fill.
                # Keep the original record and report the discrepancy.
                status = "BLOCKED_IMMUTABLE_BUCKET_CORRECTION_REQUIRED"
            quote = journal.first_eligible_quote_after(
                instrument.key,
                due_at=due_at.isoformat(),
                checked_at=as_of,
            )
            outcome.append(
                {
                    "wallet_key": wallet_key,
                    "instrument": instrument.key,
                    "batch_start_at": bucket_start.isoformat(),
                    "batch_end_at": (bucket_start + timedelta(minutes=5)).isoformat(),
                    "due_at": due_at.isoformat(),
                    "event_count": report["event_count"],
                    "late_event_count": report["late_event_count"],
                    "observed_net_delta": report["net_position_delta"],
                    "observed_gross_turnover": report["gross_observed_turnover"],
                    "source_gap_count": report["gap_count"],
                    "bucket_status": status,
                    "quote_status": quote["status"],
                    "quote_sha": quote.get("quote_sha"),
                    "paper_admitted": False,
                    "paper_executed": False,
                }
            )
    return {
        "schema": "paper_public_utc_bucket_scheduler_v1",
        "as_of": as_of,
        "timing_policy": timing_policy,
        "window_start_at": bucket_start.isoformat(),
        "due_at": due_at.isoformat(),
        "buckets": outcome,
        "result_count": len(outcome),
        "whole_wallet_nav_attested": False,
        "market_capacity_attested": False,
        "financial_events_committed": 0,
        "paper_running": False,
        "order_route": "NONE",
    }


def _resolve_market_shards(
    selected: tuple[Instrument, ...],
    configured_shards: tuple[tuple[str, tuple[Instrument, ...]], ...] | None,
) -> tuple[tuple[str, tuple[Instrument, ...]], ...]:
    if configured_shards is None:
        return tuple(
            (
                f"auto_shard_{i // MAX_NATIVE_MARKETS + 1:02d}",
                selected[i : i + MAX_NATIVE_MARKETS],
            )
            for i in range(0, len(selected), MAX_NATIVE_MARKETS)
        )
    if not 1 <= len(configured_shards) <= 16:
        raise ValueError("PUBLIC_TRADE_MARKET_SHARD_COUNT_INVALID")
    flat = []
    names = set()
    for name, chunk in configured_shards:
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{1,63}", name) is None
            or name in names
            or not 1 <= len(chunk) <= MAX_NATIVE_SOCKET_MARKETS
        ):
            raise ValueError("PUBLIC_TRADE_MARKET_SHARD_LAYOUT_INVALID")
        names.add(name)
        flat.extend(chunk)
    if tuple(sorted(inst.key for inst in flat)) != tuple(inst.key for inst in selected):
        raise ValueError("PUBLIC_TRADE_MARKET_SHARD_SELECTION_MISMATCH")
    return configured_shards


async def capture_sharded_native_trades(
    *,
    instruments: tuple[Instrument, ...],
    watched: Mapping[str, str],
    journal: PaperJournal,
    duration_seconds: float = 10,
    max_frames: int = 500,
    max_parallel_shards: int = 2,
    configured_shards: tuple[tuple[str, tuple[Instrument, ...]], ...] | None = None,
    connect: Callable[..., Any] | None = None,
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
) -> dict:
    """Capture up to 256 perps across explicit ≤128-market physical sockets.

    The shared SQLite writer lock serializes journal appends. Each shard keeps
    its own first-known transport epoch and explicit baseline/reconnect gaps.
    Partial failure propagates, never returns an 'all markets' success.
    """
    selected = _bounded_market_universe(instruments)
    if not 1 <= max_parallel_shards <= MAX_PARALLEL_SHARDS:
        raise ValueError("PUBLIC_TRADE_SHARD_CONCURRENCY_INVALID")
    chunks = _resolve_market_shards(selected, configured_shards)
    gate = asyncio.Semaphore(max_parallel_shards)
    writer = asyncio.Lock()

    async def _capture(shard_index: int, shard_name: str, shard: tuple[Instrument, ...]) -> dict:
        async with gate:
            report = await capture_bounded_native_trades(
                instruments=shard,
                watched=watched,
                journal=journal,
                duration_seconds=duration_seconds,
                max_frames=max_frames,
                connect=connect,
                now=now,
                journal_write_lock=writer,
                max_markets_per_socket=max(MAX_NATIVE_MARKETS, len(shard)),
            )
        return {
            "shard_index": shard_index,
            "shard_name": shard_name,
            "instruments": [inst.key for inst in shard],
            "report": report,
        }

    shards = await asyncio.gather(
        *(_capture(index, name, chunk) for index, (name, chunk) in enumerate(chunks))
    )
    stats = {}
    for shard in shards:
        stats.update(shard["report"]["market_stats"])
    return {
        "schema": "paper_public_market_wallet_trade_sharded_capture_v1",
        "status": "PROVISIONAL_OBSERVATION_ONLY",
        "market_selection_sha": digest([inst.key for inst in selected]),
        "shard_layout_sha": digest(
            [[name, [inst.key for inst in group]] for name, group in chunks]
        ),
        "watchlist_sha": digest(sorted(watched.items())),
        "market_count": len(selected),
        "shard_count": len(shards),
        "max_markets_per_shard": max(len(group) for _, group in chunks),
        "max_parallel_shards": max_parallel_shards,
        "baseline_markets": sum(s["report"]["baseline_markets"] for s in shards),
        "all_markets_baselined": all(s["report"]["all_markets_baselined"] for s in shards),
        "frames_received": sum(s["report"]["frames_received"] for s in shards),
        "matched_wallet_sides": sum(s["report"]["matched_wallet_sides"] for s in shards),
        "new_wallet_receipts": sum(s["report"]["new_wallet_receipts"] for s in shards),
        "market_stats": dict(sorted(stats.items())),
        "shard_reports": [
            {
                "shard_index": s["shard_index"],
                "shard_name": s["shard_name"],
                "instruments": s["instruments"],
                "stream_epoch": s["report"]["stream_epoch"],
                "frames_received": s["report"]["frames_received"],
                "baseline_markets": s["report"]["baseline_markets"],
            }
            for s in shards
        ],
        "coverage_complete": False,
        "whole_wallet_nav_attested": False,
        "paper_admitted": False,
        "financial_events_committed": 0,
        "order_route": "NONE",
    }


def plan_sharded_utc_buckets(
    *,
    instruments: tuple[Instrument, ...],
    wallet_keys: tuple[str, ...],
    journal: PaperJournal,
    as_of: str,
    timing_policy: str = "UTC_BUCKET_CLOSE",
    configured_shards: tuple[tuple[str, tuple[Instrument, ...]], ...] | None = None,
) -> dict:
    """Run all selected market UTC observations; one fixed as-of for all shards."""
    selected = _bounded_market_universe(instruments)
    groups = _resolve_market_shards(selected, configured_shards)
    reports = [
        plan_latest_public_utc_bucket(
            journal=journal,
            instruments=market_group,
            wallet_keys=wallet_keys,
            as_of=as_of,
            timing_policy=timing_policy,
        )
        for _, market_group in groups
    ]
    return {
        "schema": "paper_public_utc_bucket_sharded_scheduler_v1",
        "market_selection_sha": digest([inst.key for inst in selected]),
        "shard_layout_sha": digest(
            [[name, [inst.key for inst in group]] for name, group in groups]
        ),
        "market_count": len(selected),
        "shard_count": len(reports),
        "shard_names": [name for name, _ in groups],
        "as_of": as_of,
        "timing_policy": timing_policy,
        "window_start_at": reports[0]["window_start_at"],
        "due_at": reports[0]["due_at"],
        "buckets": [bucket for report in reports for bucket in report["buckets"]],
        "result_count": sum(report["result_count"] for report in reports),
        "whole_wallet_nav_attested": False,
        "market_capacity_attested": False,
        "financial_events_committed": 0,
        "paper_running": False,
        "order_route": "NONE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only provisional public wallet trades; NO paper fills"
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--portfolio", action="append", required=True)
    market_selection = parser.add_mutually_exclusive_group(required=True)
    market_selection.add_argument("--instrument", action="append")
    market_selection.add_argument("--market-file", type=Path)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("observe", "plan"), default="observe")
    parser.add_argument(
        "--timing-policy",
        choices=("UTC_BUCKET_CLOSE", "UTC_BUCKET_PLUS_5M"),
        default="UTC_BUCKET_CLOSE",
    )
    parser.add_argument("--duration-seconds", type=float, default=10)
    parser.add_argument("--max-frames", type=int, default=500)
    parser.add_argument("--parallel-shards", type=int, default=2)
    parser.add_argument(
        "--ack-shared-ip-connection-budget",
        action="store_true",
        help="Explicit acknowledgement required for parallel Propr physical sockets",
    )
    parser.add_argument(
        "--propr-snapshot",
        type=Path,
        help="Required for Propr public 3-socket layout; verifies exact source bytes",
    )
    args = parser.parse_args()
    if not args.state_root.is_absolute() or any(
        part in {".devspace", ".git"} for part in args.state_root.resolve().parts
    ):
        parser.error("state root must be an absolute private non-worktree path")
    configured_shards = load_public_market_shards(args.market_file) if args.market_file else None
    if args.market_file:
        market_payload = json.loads(args.market_file.read_text(encoding="utf-8"))
        if market_payload.get("schema") == "paper_public_physical_sockets_v1":
            if (
                args.mode == "observe"
                and args.parallel_shards > 1
                and not args.ack_shared_ip_connection_budget
            ):
                parser.error(
                    "parallel Propr sockets require --ack-shared-ip-connection-budget "
                    "after independently checking all users of the shared public IP"
                )
            if args.propr_snapshot is None:
                parser.error("--propr-snapshot is required for a Propr 3-socket layout")
            from .pm_forward_propr_universe import verify_propr_display_layout

            verify_propr_display_layout(args.propr_snapshot, market_payload)
    instruments = (
        _bounded_market_universe(tuple(inst for _, shard in configured_shards for inst in shard))
        if configured_shards is not None
        else _bounded_market_universe(tuple(Instrument.parse(x) for x in args.instrument))
    )
    # Validate live /info metadata before creating an evidence journal or WS sessions.
    catalog = validate_public_market_catalog(instruments) if args.mode == "observe" else None
    watched = registry_watched_addresses(
        args.registry,
        tuple(args.portfolio),
        as_of=datetime.now(UTC).isoformat(),
    )
    journal = PaperJournal(args.state_root)
    if args.mode == "plan":
        report = plan_sharded_utc_buckets(
            journal=journal,
            instruments=instruments,
            wallet_keys=tuple(sorted(set(watched.values()))),
            as_of=datetime.now(UTC).isoformat(timespec="microseconds"),
            timing_policy=args.timing_policy,
            configured_shards=configured_shards,
        )
    else:
        report = asyncio.run(
            capture_sharded_native_trades(
                instruments=instruments,
                watched=watched,
                journal=journal,
                duration_seconds=args.duration_seconds,
                max_frames=args.max_frames,
                max_parallel_shards=args.parallel_shards,
                configured_shards=configured_shards,
            )
        )
        report["market_catalog_preflight"] = catalog
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
