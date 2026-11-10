"""Daily, read-only, point-in-time wallet-health research (issue #256 Track B).

Provider observations are independently captured input, not account authority.
The public report omits addresses and never updates registry or trading state.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import wallet_registry as registry

SCHEMA = "wallet_health_assessment_v1"
UNKNOWN = "UNKNOWN"


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class FinancialEvidence(Strict):
    """All values are USD in a declared *selected-account* scope."""

    account_scope: str
    known_at: datetime
    observed_at: datetime
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening_equity: Decimal | None = None
    closing_equity: Decimal | None = None
    deposits: Decimal | None = None
    withdrawals: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl_change: Decimal | None = None
    fees: Decimal | None = None
    funding: Decimal | None = None
    liquidation_verified: bool | None = None
    last_trade_at: datetime | None = None
    activity_complete: bool = False
    source_continuity_verified: bool = False
    capital_verified: bool = False
    complete_flows: bool = False
    complete_pnl: bool = False

    @model_validator(mode="after")
    def validate_evidence(self):
        for stamp in (self.known_at, self.observed_at, self.last_trade_at):
            if stamp is not None:
                _utc(stamp)
        if self.known_at < self.observed_at:
            raise ValueError("KNOWLEDGE_PRECEDES_OBSERVATION")
        if self.account_scope.strip() == "":
            raise ValueError("ACCOUNT_SCOPE_REQUIRED")
        if self.last_trade_at is not None and self.last_trade_at > self.known_at:
            raise ValueError("FUTURE_LAST_TRADE")
        if any(
            x is not None and not x.is_finite()
            for x in (
                self.opening_equity,
                self.closing_equity,
                self.deposits,
                self.withdrawals,
                self.realized_pnl,
                self.unrealized_pnl_change,
                self.fees,
                self.funding,
            )
        ):
            raise ValueError("NONFINITE_FINANCIAL_EVIDENCE")
        if any(
            x is not None and x < 0
            for x in (
                self.opening_equity,
                self.closing_equity,
                self.deposits,
                self.withdrawals,
                self.fees,
            )
        ):
            raise ValueError("INVALID_UNSIGNED_FINANCIAL_AMOUNT")
        return self


class FollowerEpisode(Strict):
    account_scope: str
    known_at: datetime
    completed_at: datetime
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    net_follower_pnl_usd: Decimal
    costs_complete: bool
    coverage_complete: bool
    kind: Literal["RETROSPECTIVE_ESTIMATE", "AUTHENTIC_PROSPECTIVE"]
    # Each episode represents an independent, flat-to-flat decision.
    episode_id: str

    @model_validator(mode="after")
    def causal(self):
        _utc(self.known_at)
        _utc(self.completed_at)
        if self.known_at < self.completed_at:
            raise ValueError("FUTURE_EPISODE")
        return self


class WalletFinding(Strict):
    wallet_id: int
    account_scope: str
    source_integrity: Literal["AVAILABLE", "STALE", "UNKNOWN"]
    eligibility: Literal["ELIGIBLE", "CAPITAL_FLOOR_BREACH", "UNKNOWN"]
    activity: Literal["ACTIVE", "INACTIVE", "UNKNOWN"]
    capital_attribution: Literal["RECONCILED", "UNRECONCILED", "UNKNOWN"]
    unexplained_equity_change_usd: Decimal | None
    trading_pnl_usd: Decimal | None
    net_capital_flow_usd: Decimal | None
    liquidation: Literal["VERIFIED", "NOT_OBSERVED", "UNKNOWN"]
    edge: Literal["EARLY_WARNING", "PERSISTENT_WARNING", "NO_WARNING", "INSUFFICIENT_EVIDENCE"]
    copyability: Literal["RETROSPECTIVE_ONLY", "PROSPECTIVE_OBSERVED", "INSUFFICIENT_EVIDENCE"]
    windows: dict[str, dict[str, str | int | None]]
    portfolio_contribution: Literal["UNKNOWN"] = "UNKNOWN"
    recommendation: Literal[
        "REVIEW_REQUIRED",
        "CAPITAL_FLOOR_BREACH",
        "INACTIVE",
        "EDGE_WARNING",
        "INSUFFICIENT_EVIDENCE",
        "RECOVERY_REVIEW",
        "HEALTHY",
    ]
    reasons: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()


class HealthReport(Strict):
    schema_version: Literal["wallet_health_assessment_v1"] = SCHEMA
    as_of: datetime
    registry_asof_identity_sha256: str
    policy_version: Literal["wallet_health_policy_v1"] = "wallet_health_policy_v1"
    source_mode: Literal["READ_ONLY_REGISTRY_AND_IMPORTED_EVIDENCE"] = (
        "READ_ONLY_REGISTRY_AND_IMPORTED_EVIDENCE"
    )
    synthetic: bool
    eligible_registry_wallets: int
    assessed_wallets: int
    evidence_requests: int
    provider_budget: int
    findings: tuple[WalletFinding, ...]
    scientifically_qualified: Literal[False] = False
    trading_authorized: Literal[False] = False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC_AS_OF_REQUIRED")
    return value.astimezone(UTC)


def registry_universe(db: Path, as_of: datetime) -> tuple[list[int], str]:
    """Deduplicated registered identity as-of; no mutable registry access."""
    cutoff = _utc(as_of).isoformat()
    with closing(registry.connect(db, False)) as con:
        con.execute("BEGIN")
        ids = [
            int(row[0])
            for row in con.execute(
                """SELECT DISTINCT w.wallet_id FROM wallets w
                   JOIN cohort_memberships m ON m.wallet_id=w.wallet_id
                   WHERE m.known_at<=?
                     AND NOT EXISTS (
                       SELECT 1 FROM exclusions x
                       WHERE x.wallet_id=w.wallet_id AND x.known_at<=?)
                   ORDER BY w.wallet_id""",
                (cutoff, cutoff),
            )
        ]
        # Identity-only digest is time-bound, avoiding later knowledge leaking
        # into historical assessment provenance.
        digest = sha256(json.dumps([cutoff, ids], separators=(",", ":")).encode()).hexdigest()
    return ids, digest


def _attribution(f: FinancialEvidence | None):
    if f is None:
        return UNKNOWN, None, None, None, UNKNOWN
    liquid = (
        "VERIFIED"
        if f.liquidation_verified is True
        else ("NOT_OBSERVED" if f.liquidation_verified is False else UNKNOWN)
    )
    net_flow = (
        f.deposits - f.withdrawals if f.deposits is not None and f.withdrawals is not None else None
    )
    pnl_values = (f.realized_pnl, f.unrealized_pnl_change, f.fees, f.funding)
    pnl = (
        f.realized_pnl + f.unrealized_pnl_change - f.fees + f.funding
        if all(v is not None for v in pnl_values) and f.complete_pnl
        else None
    )
    if (
        net_flow is None
        or pnl is None
        or not f.complete_flows
        or f.opening_equity is None
        or f.closing_equity is None
    ):
        return UNKNOWN, None, pnl, net_flow, liquid
    residual = f.closing_equity - f.opening_equity - net_flow - pnl
    return (
        ("RECONCILED" if abs(residual) <= Decimal("0.01") else "UNRECONCILED"),
        residual,
        pnl,
        net_flow,
        liquid,
    )


def bulk_windows(
    episodes: dict[int, list[FollowerEpisode]],
    *,
    as_of: datetime,
) -> dict[tuple[int, str, int], dict]:
    """Cost-complete PIT episode windows, aggregated once using Polars.

    Falls back to the same deterministic decimal accumulation when the
    optional market extra is unavailable. No result qualifies an edge.
    """
    rows = []
    for wallet_id, values in episodes.items():
        for e in values:
            if e.known_at > as_of or e.completed_at > as_of:
                continue
            if not (e.costs_complete and e.coverage_complete):
                continue
            rows.append((wallet_id, e))
    if not rows:
        return {}

    # Deduplicate by wallet/account/episode and choose the last *known*
    # revision, never the last economic event in retrospective history.
    unique: dict[tuple[int, str, str], FollowerEpisode] = {}
    for wallet_id, e in sorted(
        rows, key=lambda item: (item[1].known_at, item[1].source_sha256, item[1].episode_id)
    ):
        key = (wallet_id, e.account_scope, e.episode_id)
        existing = unique.get(key)
        if existing is not None and existing.known_at == e.known_at and existing != e:
            raise ValueError("CONFLICTING_EPISODE_REVISIONS")
        unique[key] = e
    prepared = [
        {
            "wallet_id": wallet_id,
            "scope": scope,
            "completed_at": e.completed_at,
            "pnl": str(e.net_follower_pnl_usd),
            "kind": e.kind,
        }
        for (wallet_id, scope, _), e in unique.items()
    ]
    try:
        import polars as pl
    except ImportError:
        # Keep the minimal core working without a mandatory data-plane library.
        result: dict[tuple[int, str, int], dict] = {}
        for days in (7, 30, 90):
            cutoff = as_of - timedelta(days=days)
            groups: dict[tuple[int, str], list[dict]] = {}
            for entry in prepared:
                if entry["completed_at"] >= cutoff:
                    groups.setdefault((entry["wallet_id"], entry["scope"]), []).append(entry)
            for (wallet_id, scope), items in groups.items():
                result[(wallet_id, scope, days)] = {
                    "episodes": len(items),
                    "distinct_days": len({x["completed_at"].date() for x in items}),
                    "pnl": sum((Decimal(x["pnl"]) for x in items), Decimal(0)),
                    "prospective": any(x["kind"] == "AUTHENTIC_PROSPECTIVE" for x in items),
                }
        return result

    df = pl.DataFrame(prepared).with_columns(
        pl.col("pnl").cast(pl.Decimal(38, 8)),
        pl.col("completed_at").dt.date().alias("completed_date"),
    )
    result = {}
    for days in (7, 30, 90):
        summary = (
            df.filter(pl.col("completed_at") >= as_of - timedelta(days=days))
            .group_by(["wallet_id", "scope"])
            .agg(
                pl.len().alias("episodes"),
                pl.col("completed_date").n_unique().alias("distinct_days"),
                pl.col("pnl").sum().alias("pnl"),
                (pl.col("kind") == "AUTHENTIC_PROSPECTIVE").any().alias("prospective"),
            )
        )
        for item in summary.iter_rows(named=True):
            result[(item["wallet_id"], item["scope"], days)] = {
                "episodes": item["episodes"],
                "distinct_days": item["distinct_days"],
                "pnl": item["pnl"],
                "prospective": item["prospective"],
            }
    return result


def assess(
    db: Path,
    *,
    as_of: datetime,
    financial: dict[int, FinancialEvidence] | None = None,
    episodes: dict[int, list[FollowerEpisode]] | None = None,
    provider_budget: int = 500,
    synthetic: bool = False,
) -> HealthReport:
    as_of = _utc(as_of)
    if provider_budget < 0:
        raise ValueError("INVALID_PROVIDER_BUDGET")
    ids, inventory_sha = registry_universe(db, as_of)
    financial = financial or {}
    episodes = episodes or {}
    findings = []
    requests = 0
    aggregates = bulk_windows(episodes, as_of=as_of)
    for wallet_id in ids:
        # Strict bounded budget; missing observations still get an explicit row.
        has_input = wallet_id in financial or wallet_id in episodes
        allowed = has_input and requests < provider_budget
        if allowed:
            requests += 1
        f = financial.get(wallet_id) if allowed else None
        if f is not None and (f.known_at > as_of or f.observed_at > as_of):
            f = None
        usable = f is not None and as_of - f.known_at <= timedelta(days=2)
        verified_capital = usable and f.capital_verified
        attribution, residual, pnl, flow, liquidation = _attribution(
            f if verified_capital else None
        )
        eligibility = UNKNOWN
        if verified_capital and f.closing_equity is not None and f.account_scope:
            eligibility = (
                "ELIGIBLE" if f.closing_equity >= Decimal("1000") else "CAPITAL_FLOOR_BREACH"
            )
        provided_scopes = {
            e.account_scope
            for e in episodes.get(wallet_id, [])
            if allowed and e.known_at <= as_of and e.completed_at <= as_of
        }
        unambiguous_scope = (
            f.account_scope
            if usable
            else next(iter(provided_scopes))
            if len(provided_scopes) == 1
            else None
        )
        es = [
            e
            for e in episodes.get(wallet_id, [])
            if allowed
            and e.known_at <= as_of
            and e.completed_at <= as_of
            and unambiguous_scope is not None
            and e.account_scope == unambiguous_scope
        ]
        windows: dict[str, dict[str, str | int | None]] = {}
        has_warning = False
        persistent = False
        qualified_kinds = set()
        activity = UNKNOWN
        for days in (7, 30, 90):
            stats = aggregates.get((wallet_id, unambiguous_scope, days), {}) if allowed else {}
            episode_count = stats.get("episodes", 0)
            days_covered = stats.get("distinct_days", 0)
            # Diagnostic only; not a test of statistical edge significance.
            enough = episode_count >= 5 and days_covered >= 5
            net = stats.get("pnl", Decimal(0))
            windows[str(days)] = {
                "independent_episodes": episode_count,
                "distinct_days": days_covered,
                "status": "DIAGNOSTIC" if enough else "INSUFFICIENT_EVIDENCE",
                "net_follower_pnl_usd": str(net) if enough else None,
            }
            if enough:
                qualified_kinds.add(
                    "AUTHENTIC_PROSPECTIVE" if stats["prospective"] else "RETROSPECTIVE_ESTIMATE"
                )
                if net < 0 and days in (7, 30):
                    has_warning = True
                    persistent = persistent or days == 30
        recent = [e for e in es if e.completed_at >= as_of - timedelta(days=30)]
        if recent:
            activity = "ACTIVE"
        elif usable and f.activity_complete:
            if f.last_trade_at is None or f.last_trade_at < as_of - timedelta(days=30):
                activity = "INACTIVE"
            else:
                activity = "ACTIVE"
        edge = (
            "PERSISTENT_WARNING"
            if persistent
            else "EARLY_WARNING"
            if has_warning
            else "NO_WARNING"
            if windows["30"]["status"] == "DIAGNOSTIC"
            else "INSUFFICIENT_EVIDENCE"
        )
        # A retrospective majority must not be promoted to a prospective
        # diagnosis by mixing in one asserted prospective episode.
        prospect = [e for e in es if e.kind == "AUTHENTIC_PROSPECTIVE"]
        prospect_days = {
            e.completed_at.date() for e in prospect if e.costs_complete and e.coverage_complete
        }
        copy = (
            "PROSPECTIVE_OBSERVED"
            if len({e.episode_id for e in prospect if e.costs_complete and e.coverage_complete})
            >= 5
            and len(prospect_days) >= 5
            else "RETROSPECTIVE_ONLY"
            if qualified_kinds
            else "INSUFFICIENT_EVIDENCE"
        )
        reasons = []
        if has_input and not allowed:
            reasons.append("PROVIDER_BUDGET_EXHAUSTED")
        if not usable:
            reasons.append("MISSING_OR_STALE_CAPITAL_EVIDENCE")
        if usable and not f.source_continuity_verified:
            reasons.append("SOURCE_CONTINUITY_NOT_VERIFIED")
        if usable and not f.capital_verified:
            reasons.append("CAPITAL_EVIDENCE_NOT_VERIFIED")
        if len(provided_scopes) > 1 and not usable:
            reasons.append("AMBIGUOUS_ACCOUNT_SCOPE")
        if attribution == UNKNOWN:
            reasons.append("UNRECONCILED_OR_INCOMPLETE_FINANCIAL_COMPONENTS")
        if edge == "INSUFFICIENT_EVIDENCE":
            reasons.append("INSUFFICIENT_FOLLOWER_EPISODES")
        if eligibility == "CAPITAL_FLOOR_BREACH":
            recommendation = "CAPITAL_FLOOR_BREACH"
        elif attribution == "UNRECONCILED":
            recommendation = "REVIEW_REQUIRED"
        elif activity == "INACTIVE":
            recommendation = "INACTIVE"
        elif edge in {"EARLY_WARNING", "PERSISTENT_WARNING"}:
            recommendation = "EDGE_WARNING"
        elif eligibility == "ELIGIBLE" and attribution == "RECONCILED" and edge == "NO_WARNING":
            recommendation = "HEALTHY"
        else:
            recommendation = "INSUFFICIENT_EVIDENCE"
        findings.append(
            WalletFinding(
                wallet_id=wallet_id,
                account_scope=unambiguous_scope or UNKNOWN,
                source_integrity=(
                    "AVAILABLE"
                    if usable and f.source_continuity_verified
                    else "STALE"
                    if f and not usable
                    else UNKNOWN
                ),
                eligibility=eligibility,
                activity=activity,
                capital_attribution=attribution,
                unexplained_equity_change_usd=residual,
                trading_pnl_usd=pnl,
                net_capital_flow_usd=flow,
                liquidation=liquidation,
                edge=edge,
                copyability=copy,
                windows=windows,
                recommendation=recommendation,
                reasons=tuple(reasons),
                evidence_hashes=tuple(
                    sorted(
                        {
                            x
                            for x in (
                                (f.source_sha256 if usable else None),
                                *(e.source_sha256 for e in es),
                            )
                            if x is not None
                        }
                    )
                ),
            )
        )
    return HealthReport(
        as_of=as_of,
        registry_asof_identity_sha256=inventory_sha,
        synthetic=synthetic,
        eligible_registry_wallets=len(ids),
        assessed_wallets=len(findings),
        evidence_requests=requests,
        provider_budget=provider_budget,
        findings=tuple(findings),
    )


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def report_bytes(report: HealthReport) -> bytes:
    return canonical(report.model_dump(mode="json"))


def save_immutable(report: HealthReport, directory: Path) -> Path:
    """Create-once content addressed report. Never rewrite an existing report."""
    raw = report_bytes(report)
    digest = sha256(raw).hexdigest()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise PermissionError("PRIVATE_REPORT_DIRECTORY_REQUIRED")
    path = directory / f"wallet-health-{digest}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_REPORT_COLLISION")
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only wallet registry health research")
    p.add_argument("--db", type=Path, default=registry.DB)
    p.add_argument("--as-of", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--provider-budget", type=int, default=500)
    p.add_argument("--evidence", type=Path, help="Private, independently captured JSON evidence")
    p.add_argument(
        "--publish-dir", type=Path, help="Optional read-only Grafana projection destination"
    )
    args = p.parse_args(argv)
    financial = {}
    episodes = {}
    if args.evidence is not None:
        raw = args.evidence.read_bytes()
        data = json.loads(raw)
        if (
            set(data) != {"schema", "financial", "episodes", "synthetic"}
            or data["schema"] != "wallet_health_input_v1"
        ):
            raise ValueError("INVALID_HEALTH_INPUT")
        for entry in data["financial"]:
            wallet_id = entry["wallet_id"]
            if type(wallet_id) is not int or wallet_id in financial:
                raise ValueError("DUPLICATE_FINANCIAL_WALLET")
            financial[wallet_id] = FinancialEvidence.model_validate_json(
                json.dumps({k: v for k, v in entry.items() if k != "wallet_id"})
            )
        for entry in data["episodes"]:
            wallet_id = entry["wallet_id"]
            if type(wallet_id) is not int:
                raise ValueError("INVALID_EPISODE_WALLET")
            episodes.setdefault(wallet_id, []).append(
                FollowerEpisode.model_validate_json(
                    json.dumps({k: v for k, v in entry.items() if k != "wallet_id"})
                )
            )
    else:
        data = {"synthetic": False}
    report = assess(
        args.db,
        as_of=datetime.fromisoformat(args.as_of.replace("Z", "+00:00")),
        financial=financial,
        episodes=episodes,
        synthetic=data["synthetic"],
        provider_budget=args.provider_budget,
    )
    path = save_immutable(report, args.out)
    if args.publish_dir is not None:
        from .wallet_health_projection import project, publish

        publish(args.publish_dir, project(report, published_at=datetime.now(UTC)))
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "report_sha256": path.stem.split("-")[-1],
                "wallets": report.assessed_wallets,
                "evidence_requests": report.evidence_requests,
                "report": str(path),
                "trading_authorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
