"""Portfolio x prop-contract EV screening, using the native read-only registry.

This is a model selection tool, never a broker/account execution or qualification route.
The only admissible economic inputs are explicit complete joint *follower* MTM
interval PnL tapes. No vendor fill/event-time economics are inferred here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .contract_actuary import CONTRACTS, simulate
from .wallet_registry import DB
from . import pm_operations as operations

if TYPE_CHECKING:
    import numpy as np

SCHEMA = "copytrade_portfolio_net_pnl_tape_v1"
RESULT = "copytrade_portfolio_contract_ev_v1"
RULES_VERSION = "user_archetypes_20261105_unverified_v1"
COSTS = ("commissions", "spread", "slippage", "funding", "market_impact")
SOURCE_STATUSES = frozenset(
    {"HISTORICAL_HYPOTHETICAL", "SYNTHETIC_FIXTURE", "PROSPECTIVE_FOLLOWER_UNATTESTED"}
)
FUNDAMENTAL_UNKNOWNS = (
    "Account-specific rulebook and withdrawal enforcement unverified",
    "Payout eligibility and trailing-floor lock/reset may differ by provider",
    "Finite evaluation/funded horizons are scenario choices, not verified expiries",
    "No independently signed follower economics, OOS evidence or approval",
    "Block bootstrap is not an executable portfolio path or continuity guarantee",
)
RULE_UNKNOWNS = {
    "A Flex": (
        "Green-day profit threshold unspecified",
        "Challenge max-DD static vs trailing/sampling unspecified",
        "Contract leverage/withdrawal conditions unspecified",
    ),
    "B Sprint": (
        "Green-day profit threshold unspecified",
        "Challenge max-DD static vs trailing/sampling unspecified",
        "Withdrawal conditions unspecified",
    ),
    "C 2-Step": (
        "Funded daily-stop rule unspecified",
        "Funded payout schedule unspecified",
        "Trailing sampling and cap unspecified",
        "Phase reset mechanics unspecified",
    ),
}


def _canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rules_catalog() -> dict:
    rules = []
    for contract in CONTRACTS:
        payload = asdict(contract)
        rules.append(
            {
                "id": contract.name,
                "configuration": payload,
                "rule_sha256": sha256(_canonical(payload)).hexdigest(),
                "rule_authority": "USER_SUPPLIED_UNVERIFIED_ARCHETYPE",
                "missing_terms": list(RULE_UNKNOWNS[contract.name]),
                "account_trading_authorized": False,
            }
        )
    return {
        "schema": "copytrade_contract_rule_catalog_v1",
        "rule_set_version": RULES_VERSION,
        "rules_sha256": sha256(_canonical(rules)).hexdigest(),
        "contracts": rules,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


@dataclass(frozen=True)
class JointTape:
    portfolio_id: str
    definition_sha256: str
    members: tuple[str, ...]
    source_status: str
    asof: str
    sha256: str
    first_interval_utc: str
    end_exclusive_utc: str
    step_minutes: int
    days: int
    peak_gross_leverage: float | None
    increments: np.ndarray  # [days, UTC steps, pods], never independently resampled


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("INVALID_TAPE_TIMESTAMP")
    try:
        out = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_TAPE_TIMESTAMP") from exc
    if out.tzinfo is None or out.utcoffset() != timedelta(0):
        raise ValueError("TAPE_REQUIRES_UTC_TIMESTAMP")
    return out.astimezone(UTC)


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("INVALID_PNL_VALUE")
    try:
        amount = float(value)
    except ValueError as exc:
        raise ValueError("INVALID_PNL_VALUE") from exc
    if not math.isfinite(amount):
        raise ValueError("NONFINITE_PNL_VALUE")
    return amount


def load_tape(path: Path, *, min_days: int = 42) -> JointTape:
    """Read full synchronous UTC per-pod *net follower* MTM, fail closed on gaps.

    Timestamps mark the START of each interval; its PnL becomes known at
    the END. This input is not an authenticating source signature.
    """
    # Keep the native operator module importable without optional NumPy.
    import numpy as np

    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("MISSING_OR_UNSAFE_PORTFOLIO_TAPE")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_PORTFOLIO_TAPE_JSON") from exc
    required = {
        "schema",
        "portfolio_id",
        "portfolio_definition_sha256",
        "members",
        "source_status",
        "observed_at",
        "pnl_basis",
        "initial_capital_usd",
        "step_minutes",
        "costs_included",
        "rows",
        "peak_gross_leverage",
    }
    if not isinstance(data, dict) or set(data) != required or data["schema"] != SCHEMA:
        raise ValueError("INVALID_PORTFOLIO_TAPE_SCHEMA")
    if data["pnl_basis"] != "FOLLOWER_NET_MARK_TO_MARKET_USD":
        raise ValueError("LEADER_OR_REALIZED_ONLY_PNL_NOT_ADMISSIBLE")
    if data["source_status"] not in SOURCE_STATUSES:
        raise ValueError("UNREVIEWED_TAPE_PROVENANCE")
    if _number(data["initial_capital_usd"]) != 10000:
        raise ValueError("TAPE_MUST_BE_NORMALIZED_TO_10000_EQUITY")
    if not isinstance(data["portfolio_id"], str) or not data["portfolio_id"]:
        raise ValueError("MISSING_PORTFOLIO_ID")
    identity = data["portfolio_definition_sha256"]
    if (
        not isinstance(identity, str)
        or len(identity) != 64
        or any(c not in "0123456789abcdef" for c in identity)
    ):
        raise ValueError("MISSING_PORTFOLIO_DEFINITION_SHA")
    members = data["members"]
    if (
        not isinstance(members, list)
        or not 2 <= len(members) <= 10
        or any(not isinstance(member, str) or not member for member in members)
        or len(set(members)) != len(members)
    ):
        raise ValueError("INVALID_PORTFOLIO_MEMBERS")
    costs = data["costs_included"]
    if (
        not isinstance(costs, dict)
        or set(costs) != set(COSTS)
        or not all(costs[k] is True for k in COSTS)
    ):
        raise ValueError("INCOMPLETE_EXECUTION_ECONOMICS")
    step = data["step_minutes"]
    if type(step) is not int or step < 1 or 1440 % step != 0:
        raise ValueError("INTERVAL_MUST_DIVIDE_UTC_DAY")
    periods = 1440 // step
    rows = data["rows"]
    if (
        not isinstance(rows, list)
        or len(rows) < min_days * periods
        or len(rows) % periods != 0
        or len(rows) > 366 * periods
    ):
        raise ValueError("INSUFFICIENT_OR_EXCESSIVE_CONTIGUOUS_TAPE")
    first = _utc(rows[0]["timestamp"])
    if first.time() != datetime.min.time():
        raise ValueError("TAPE_MUST_START_UTC_MIDNIGHT")
    observed = _utc(data["observed_at"])
    increments = np.empty((len(rows), len(members)), dtype=np.float64)
    last = first - timedelta(minutes=step)
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"timestamp", "pnl_by_member"}:
            raise ValueError("INVALID_PNL_ROW")
        timestamp = _utc(row["timestamp"])
        if timestamp != last + timedelta(minutes=step):
            raise ValueError("GAPPED_DUPLICATED_OR_UNSORTED_PORTFOLIO_PNL")
        values = row["pnl_by_member"]
        if not isinstance(values, dict) or set(values) != set(members):
            raise ValueError("MISSING_OR_UNEXPECTED_POD_PNL")
        increments[i] = [_number(values[member]) for member in members]
        last = timestamp
    if observed < last + timedelta(minutes=step):
        raise ValueError("TAPE_OBSERVED_BEFORE_LAST_MTM_AVAILABLE")
    leverage = data["peak_gross_leverage"]
    if leverage is not None:
        leverage = _number(leverage)
        if leverage < 0:
            raise ValueError("NEGATIVE_GROSS_LEVERAGE")
    return JointTape(
        portfolio_id=data["portfolio_id"],
        definition_sha256=identity,
        members=tuple(members),
        source_status=data["source_status"],
        asof=observed.isoformat(),
        sha256=sha256(raw).hexdigest(),
        first_interval_utc=first.isoformat(),
        end_exclusive_utc=(last + timedelta(minutes=step)).isoformat(),
        step_minutes=step,
        days=len(rows) // periods,
        peak_gross_leverage=leverage,
        increments=increments.reshape(-1, periods, len(members)),
    )


class JointBlockBootstrap:
    """Sample *joint* consecutive calendar-day blocks, preserving pod correlation."""

    def __init__(
        self,
        tape: JointTape,
        *,
        paths: int,
        max_days: int,
        block_days: int,
        seed: int,
    ) -> None:
        import numpy as np

        if type(block_days) is not int or not 3 <= block_days <= tape.days // 2:
            raise ValueError("INVALID_BLOCK_DAYS_FOR_TAPE")
        if not 1 <= paths <= 250_000 or not 1 <= max_days <= 1460:
            raise ValueError("INVALID_BOOTSTRAP_SIZE")
        self.block_days = block_days
        self.series = tape.increments.sum(axis=2)
        self.starts = np.random.default_rng(seed).integers(
            0,
            tape.days - block_days + 1,
            size=((max_days + block_days - 1) // block_days, paths),
            dtype=np.int32,
        )

    def __call__(self, day: int, step: int) -> np.ndarray:
        return self.series[self.starts[day // self.block_days] + day % self.block_days, step]


def _registry_identity(portfolio_id: str, *, db: Path, asof: str | None) -> dict:
    if (
        not isinstance(portfolio_id, str)
        or "/" not in portfolio_id
        and portfolio_id not in {"P1", "P14", "P16", "Combo2"}
    ):
        # A bare "B" or "E6" is ambiguous across namespaces.
        raise ValueError("NAMESPACE_QUALIFIED_PORTFOLIO_REQUIRED")
    doctor = operations._doctor(db)
    if doctor["status"] != "VERIFIED":
        raise ValueError("REGISTRY_SOURCE_PARITY_NOT_VERIFIED")
    generation = operations._generation(db)
    if generation["status"] != "CURRENT":
        raise ValueError("REGISTRY_GENERATION_NOT_CURRENT")
    cmd = ["portfolio", portfolio_id]
    if asof is not None:
        cmd += ["--asof", _utc(asof).isoformat()]
    record = operations._registry_query(db, cmd).get(portfolio_id)
    if not isinstance(record, dict) or record.get("state") in {
        "UNKNOWN_AT_ASOF",
        "NOT_REGISTERED_AT_ASOF",
    }:
        raise ValueError("PORTFOLIO_NOT_REGISTERED_AT_ASOF")
    if not record.get("source_sealed") or not record.get("definition_sha256"):
        raise ValueError("PORTFOLIO_SOURCE_NOT_SEALED")
    return {
        "portfolio_id": portfolio_id,
        "definition_sha256": record["definition_sha256"],
        "members": sorted(record["members"]),
        "version": record["version"],
        "selection_known_at": record["selection_known_at"],
        "registry_generation_sha256": generation["sha"],
        "registry_observed_at": generation["observed_at"],
        "registry_state": record.get("state"),
        "trading_authorized": False,
    }


def compare_contracts(
    tape: JointTape,
    portfolio: dict,
    *,
    paths: int = 100_000,
    seed: int = 20261105,
    block_days: int = 7,
    evaluation_days: int = 180,
    funded_days: int = 180,
    evaluation_scales: tuple[float, ...] = (0.5, 1.0),
    funded_scales: tuple[float, ...] = (0.25, 0.5),
    extra_daily_cost: float = 0.0,
    discount_rate: float = 0.0,
    max_no_first_payout_probability: float = 1.0,
) -> dict:
    """Rank modeled contract EV with an evidence boundary and NO_BUY alternative."""
    if (
        tape.portfolio_id != portfolio["portfolio_id"]
        or tape.definition_sha256 != portfolio["definition_sha256"]
        or sorted(tape.members) != portfolio["members"]
    ):
        raise ValueError("PORTFOLIO_TAPE_IDENTITY_OR_MEMBERSHIP_MISMATCH")
    if type(paths) is not int or not 1 <= paths <= 250_000:
        raise ValueError("INVALID_PATH_COUNT")
    if any(type(v) is not int or not 1 <= v <= 365 for v in (evaluation_days, funded_days)):
        raise ValueError("INVALID_SCENARIO_HORIZON")
    grids = (*evaluation_scales, *funded_scales)
    if (
        not grids
        or not evaluation_scales
        or not funded_scales
        or any(not math.isfinite(k) or not 0 < k <= 2 for k in grids)
    ):
        raise ValueError("INVALID_SIZING_GRID")
    if not math.isfinite(extra_daily_cost) or extra_daily_cost < 0:
        raise ValueError("INVALID_ADDITIONAL_EXECUTION_COST")
    if not math.isfinite(discount_rate) or discount_rate < 0:
        raise ValueError("INVALID_DISCOUNT_RATE")
    if (
        not math.isfinite(max_no_first_payout_probability)
        or not 0 <= max_no_first_payout_probability <= 1
    ):
        raise ValueError("INVALID_RUIN_PROBABILITY_CONSTRAINT")
    if tape.step_minutes > 60 and tape.source_status != "SYNTHETIC_FIXTURE":
        raise ValueError("MARK_TO_MARKET_SAMPLING_TOO_COARSE_FOR_CONTRACT_BARRIERS")
    bootstrap = JointBlockBootstrap(
        tape,
        paths=paths,
        max_days=evaluation_days * 2 + funded_days,
        block_days=block_days,
        seed=seed,
    )
    rulebook = rules_catalog()
    scored: list[dict] = []
    for contract in CONTRACTS:
        for eval_k in sorted(set(evaluation_scales)):
            for funded_k in sorted(set(funded_scales)):
                if contract.name == "B Sprint" and tape.peak_gross_leverage is None:
                    scored.append(
                        {
                            "contract": contract.name,
                            "evaluation_k": eval_k,
                            "funded_k": funded_k,
                            "status": "BLOCKED_LEVERAGE_UNKNOWN",
                        }
                    )
                    continue
                if (
                    contract.name == "B Sprint"
                    and max(eval_k, funded_k) * tape.peak_gross_leverage > 25
                ):
                    scored.append(
                        {
                            "contract": contract.name,
                            "evaluation_k": eval_k,
                            "funded_k": funded_k,
                            "status": "BLOCKED_LEVERAGE_LIMIT",
                        }
                    )
                    continue
                record = simulate(
                    contract,
                    paths=paths,
                    seed=seed,
                    evaluation_days=evaluation_days,
                    funded_days=funded_days,
                    steps_per_day=tape.increments.shape[1],
                    daily_sigma=math.sqrt(tape.increments.shape[1]),
                    daily_mu=0.0,
                    daily_cost=extra_daily_cost,
                    phase_bet_sizes=(eval_k,) * len(contract.targets) + (funded_k,),
                    discount_rate_annual=discount_rate,
                    innovations=bootstrap,
                )
                lcb = record["net_ev"] - 1.96 * record["payout_standard_error"]
                scored.append(
                    {
                        **record,
                        "evaluation_k": eval_k,
                        "funded_k": funded_k,
                        "status": "SCENARIO_ONLY",
                        "satisfies_no_first_payout_limit": bool(
                            record["no_first_payout"] <= max_no_first_payout_probability
                        ),
                        "net_ev_lower_95_usd": round(lcb, 4),
                        "positive_ev_lower_95": bool(lcb > 0),
                        "leverage_screened_from_tape": (
                            tape.peak_gross_leverage is not None
                            if contract.name == "B Sprint"
                            else False
                        ),
                        "leverage_independently_verified": False,
                        "unresolved_terms": list(RULE_UNKNOWNS[contract.name]),
                    }
                )
    candidates = [s for s in scored if s["status"] == "SCENARIO_ONLY"]
    ordered = sorted(
        (s for s in candidates if s["satisfies_no_first_payout_limit"]),
        key=lambda r: (-r["net_ev"], r["contract"], r["evaluation_k"], r["funded_k"]),
    )
    best_by_contract = {}
    for candidate in ordered:
        best_by_contract.setdefault(
            candidate["contract"],
            {
                key: candidate[key]
                for key in (
                    "contract",
                    "evaluation_k",
                    "funded_k",
                    "net_ev",
                    "roi_pct",
                    "funded_probability",
                    "first_payout_probability",
                    "conditional_cost_to_fund",
                    "mean_payout",
                    "ruin_before_first_payout",
                    "no_first_payout",
                    "net_ev_lower_95_usd",
                )
            },
        )
    complete = not any(row["status"].startswith("BLOCKED") for row in scored)
    risk_feasible = bool(ordered)
    winner = ordered[0] if complete and risk_feasible else None
    return {
        "schema": RESULT,
        "status": "SCENARIO_ONLY" if complete else "BLOCKED",
        "complete_contract_comparison": complete,
        "risk_constraint_feasible": risk_feasible,
        "portfolio": portfolio,
        "tape": {
            "sha256": tape.sha256,
            "source_status": tape.source_status,
            "observed_at": tape.asof,
            "history_days": tape.days,
            "first_interval_utc": tape.first_interval_utc,
            "end_exclusive_utc": tape.end_exclusive_utc,
            "step_minutes": tape.step_minutes,
            "pod_count": len(tape.members),
            "cost_components_complete": True,
        },
        "rules": {
            "version": RULES_VERSION,
            "sha256": rulebook["rules_sha256"],
            "verified_provider_terms": False,
        },
        "scenario": {
            "paths": paths,
            "seed": seed,
            "block_days": block_days,
            "evaluation_days_per_stage": evaluation_days,
            "funded_horizon_days": funded_days,
            "evaluation_scales": sorted(set(evaluation_scales)),
            "funded_scales": sorted(set(funded_scales)),
            "extra_daily_cost": extra_daily_cost,
            "discount_rate_annual": discount_rate,
            "max_no_first_payout_probability": max_no_first_payout_probability,
            "sampling": "JOINT_CONSECUTIVE_DAY_BLOCKS_WITH_REPLACEMENT",
        },
        "best_by_contract": best_by_contract,
        "best_modeled_choice": (
            {
                k: winner[k]
                for k in (
                    "contract",
                    "evaluation_k",
                    "funded_k",
                    "net_ev",
                    "net_ev_lower_95_usd",
                    "funded_probability",
                    "first_payout_probability",
                    "no_first_payout",
                    "ruin_before_first_payout",
                    "conditional_cost_to_fund",
                    "mean_payout",
                    "roi_pct",
                )
            }
            if winner
            else None
        ),
        "positive_scenario_ev": bool(winner and winner["net_ev_lower_95_usd"] > 0),
        "scenario_decision": (
            "POSITIVE_SCENARIO_BUT_NOT_PURCHASE_AUTHORIZED"
            if winner and winner["net_ev_lower_95_usd"] > 0
            else "NO_BUY_OR_INCOMPLETE_EVIDENCE"
        ),
        "purchase_decision": "NO_AUTHORIZED_PURCHASE_RECOMMENDATION",
        "scorecard": scored,
        "limitations": list(FUNDAMENTAL_UNKNOWNS),
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def compare_portfolios(
    portfolio_ids: list[str],
    tapes: list[Path] | None = None,
    *,
    db: Path = DB,
    asof: str | None = None,
    **options: Any,
) -> dict:
    """Read current sealed portfolios; missing PnL is a BLOCKED row, not fake EV."""
    if not portfolio_ids or len(set(portfolio_ids)) != len(portfolio_ids):
        raise ValueError("MISSING_OR_DUPLICATED_PORTFOLIO_ID")
    if tapes and len(tapes) != len(portfolio_ids):
        raise ValueError("ONE_TAPE_PER_PORTFOLIO_REQUIRED")
    outcomes: list[dict] = []
    for i, portfolio_id in enumerate(portfolio_ids):
        try:
            portfolio = _registry_identity(portfolio_id, db=db, asof=asof)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            outcomes.append(
                {
                    "portfolio_id": portfolio_id,
                    "status": "BLOCKED",
                    "error_code": str(exc),
                    "scorecard": [],
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                }
            )
            continue
        if not tapes:
            outcomes.append(
                {
                    "portfolio_id": portfolio_id,
                    "portfolio": portfolio,
                    "status": "BLOCKED",
                    "error_code": "MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE",
                    "scorecard": [],
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                }
            )
            continue
        try:
            tape = load_tape(tapes[i])
            outcomes.append(compare_contracts(tape, portfolio, **options))
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            outcomes.append(
                {
                    "portfolio_id": portfolio_id,
                    "portfolio": portfolio,
                    "status": "BLOCKED",
                    "error_code": str(exc),
                    "scorecard": [],
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                }
            )
    available = [
        row
        for row in outcomes
        if (row["status"] == "SCENARIO_ONLY" and row["best_modeled_choice"] is not None)
    ]
    # Never promote a partial selection over portfolios with missing economics.
    windows = {
        (
            r["tape"]["first_interval_utc"],
            r["tape"]["end_exclusive_utc"],
            r["tape"]["step_minutes"],
            r["tape"]["source_status"],
        )
        for r in available
    }
    matched_windows = len(windows) <= 1
    all_present = bool(available) and len(available) == len(outcomes) and matched_windows
    best = max(available, key=lambda x: x["best_modeled_choice"]["net_ev"]) if all_present else None
    return {
        "schema": "copytrade_contract_portfolio_comparison_v1",
        "status": "SCENARIO_ONLY" if all_present else "BLOCKED",
        "rule_catalog": rules_catalog(),
        "comparisons": outcomes,
        "best_modeled_portfolio_contract": (
            {"portfolio_id": best["portfolio"]["portfolio_id"], **best["best_modeled_choice"]}
            if best
            else None
        ),
        "selection_coverage_complete": all_present,
        "portfolio_window_alignment_verified": matched_windows,
        "comparison_blockers": (
            [] if matched_windows else ["UNMATCHED_PNL_WINDOWS_OR_SAMPLE_CLOCKS_ACROSS_PORTFOLIOS"]
        ),
        "purchase_decision": "NO_AUTHORIZED_PURCHASE_RECOMMENDATION",
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
