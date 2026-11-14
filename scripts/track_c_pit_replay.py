"""Track C retrospective as-of risk replay over the existing V4 Polars engine.

One July pre-window calibration and August-November historical-oracle OOS window.
This is a counterfactual PIT *data-cutoff* study, not a historical signed release:
the portfolio rosters were selected later and vendor positions were obtained
retrospectively. Reuse PM-V4 pricing, fee, participation and incomplete-episode
rules. Never convert independent episode results into full PM03 portfolio MTM.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_k_recalibration import KResearchInput, Trial, evaluate_k
from copytrade_pm.pm_offline_repository import _clock
from copytrade_pm.pm_v4_fast_screen import (
    RETRO_SCHEMA,
    SCENARIOS,
    _actions,
    _economics,
    _episodes,
    _job,
    _join_actions,
    _retro_policy,
    _source,
    _v2_source_digest,
)
from copytrade_pm.pm_source_campaign_roster import load_campaign
from scripts.research_vike_prewindow_k import checked_publish

D = Decimal
TRAIN_TO_OOS = "COUNTERFACTUAL_ASOF_RISK_ONLY_PORTFOLIO_SELECTED_AFTER_OOS"
BLOCKERS = (
    "NO_AUTHENTIC_HISTORICAL_FIRST_KNOWN",
    "NO_COMPLETE_PM03_ACCOUNT_MTM_OR_FUNDING",
    "NO_INDEPENDENT_PORTFOLIO_CORRELATION_OR_STRESS",
    "HISTORIC_MARKET_LOTS_NOT_AUTHENTICATED",
    "RETROSPECTIVE_PORTFOLIO_SELECTION",
)


def risk_k(record: dict, pod_budget: Decimal, *, cutoff: str) -> Decimal:
    """Pre-window gross stress policy; never use OOS PnL to set k."""
    if not pod_budget.is_finite() or pod_budget <= 0:
        raise ValueError("INVALID_POD_BUDGET")
    if _clock(record["last_observed_at"]) >= _clock(cutoff):
        raise ValueError("PIT_LOOKAHEAD_PREWINDOW_OBSERVATION")
    gross = D(record["max_observed_gross_usd"])
    if not gross.is_finite() or gross <= 0:
        raise ValueError("INVALID_PIT_TRAINING_GROSS")
    expected = min(D("1"), pod_budget / (D("0.20") * gross))
    return expected.quantize(D("0.000000000001"), rounding=ROUND_DOWN)


def load_supplemental_july(
    *,
    root: Path | None,
    policy: dict,
    account_hashes: dict[str, dict[str, str]],
    filename_prefix: str = "trackc-july",
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Recover missing prewindow risk observations; never overwrite frozen evidence.

    Source is a retrospectively acquired Vike hourly snapshot aggregation.
    These assertions do not independently authenticate the original vendor
    pages and can never promote a k change or historical portfolio economics.
    """
    original = dict(policy["wallets"])
    receipts: dict[str, dict] = {}
    if root is None:
        return original, receipts
    if filename_prefix not in {"trackc-july", "trackc-late"}:
        raise ValueError("UNKNOWN_SUPPLEMENTAL_EVIDENCE_FAMILY")
    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("UNSAFE_SUPPLEMENTAL_CALIBRATION_DIRECTORY")
    expected = {
        pod: account for mapping in account_hashes.values() for pod, account in mapping.items()
    }
    files = sorted(directory.glob(f"{filename_prefix}-*-hourly.json"))
    if not files or len(files) > 32:
        raise ValueError("MISSING_OR_EXCESSIVE_SUPPLEMENTAL_RECEIPTS")
    seen: set[str] = set()
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
            raise ValueError("UNSAFE_SUPPLEMENTAL_RECEIPT")
        raw = path.read_bytes()
        doc = json.loads(raw)
        alias = doc.get("wallet_alias")
        account = sha256(str(doc.get("wallet_address", "")).lower().encode()).hexdigest()
        if (
            doc.get("schema") != "vike_precalibration_hourly_receipt_v1"
            or alias not in expected
            or expected[alias] != account
            or path.name != f"{filename_prefix}-{alias}-hourly.json"
            or account in seen
            or account in original
            or doc.get("source") != "Vike Hyperliquid positions historic 1h via connector"
            or doc.get("resolution") is not None  # old v1 source envelope has no resolution
        ):
            raise ValueError("SUPPLEMENTAL_WALLET_OR_ORIGINAL_K_IDENTITY_MISMATCH")
        seen.add(account)
        if _clock(doc["start"]) != _clock(policy["training_start"]) or _clock(
            doc["end_exclusive"]
        ) != _clock(policy["training_end"]):
            raise ValueError("SUPPLEMENTAL_TRAINING_WINDOW_CHANGED")
        pages = doc.get("pages")
        hours = doc.get("hours")
        if (
            not isinstance(pages, list)
            or not pages
            or not isinstance(hours, list)
            or not doc.get("complete_pages")
            or doc.get("failed_validation")
            or doc.get("invalid") != 0
            or doc.get("duplicates") != 0
            or any(page.get("remaining") != (i < len(pages) - 1) for i, page in enumerate(pages))
            or sum(page["position_rows"] for page in pages) != doc.get("total_position_rows")
            or len(hours) != doc.get("total_observed_hours")
            or sum(hour["positions"] for hour in hours) != doc["total_position_rows"]
        ):
            raise ValueError("SUPPLEMENTAL_PAGINATION_OR_VALIDATION_INCOMPLETE")
        previous = None
        observed = []
        hourly_gross: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for hour in hours:
            ts = _clock(hour["ts"])
            if not (_clock(policy["training_start"]) <= ts < _clock(policy["training_end"])):
                raise ValueError("SUPPLEMENTAL_FUTURE_OR_OUTSIDE_WINDOW")
            if previous is not None and ts <= previous:
                raise ValueError("SUPPLEMENTAL_DUPLICATE_OR_UNORDERED_HOUR")
            previous = ts
            try:
                gross = Decimal(str(hour["gross_usd"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("SUPPLEMENTAL_NONFINITE_GROSS") from exc
            if (
                not gross.is_finite()
                or gross < 0
                or type(hour["positions"]) is not int
                or hour["positions"] < 1
            ):
                raise ValueError("SUPPLEMENTAL_INVALID_HOURLY_POSITION")
            observed.append(gross)
            hourly_gross[ts.isoformat()[:13]] += gross
        measured = max(observed, default=Decimal(0))
        if abs(measured - Decimal(str(doc["max_observed_gross_usd"]))) > Decimal("0.000001"):
            raise ValueError("SUPPLEMENTAL_MAX_GROSS_MISMATCH")
        # Distinct market/DEX rows can have slightly different snapshot minute
        # within the same UTC hour. Summing such groups is conservative: it
        # can overstate exposure, never credit a missed leg as diversification.
        conservative = max(hourly_gross.values(), default=Decimal(0))
        days = len({hour["ts"][:10] for hour in hours})
        status = "PREWINDOW_COMPLETE_PAGE_PROXY_ONLY"
        if not measured or days < 7 or len(hours) < 24:
            status = "NO_ELIGIBLE_PREWINDOW_POSITION_OBSERVATIONS"
        receipts[alias] = {
            "wallet_sha256": account,
            "file_sha256": sha256(raw).hexdigest(),
            "position_rows": doc["total_position_rows"],
            "observation_days": days,
            "snapshots": len(hours),
            "max_observed_gross_usd": str(measured),
            "conservative_hourly_gross_usd": str(conservative),
            "status": status,
        }
        if status != "PREWINDOW_COMPLETE_PAGE_PROXY_ONLY":
            continue
        original[account] = {
            "max_observed_gross_usd": str(conservative),
            "observation_days": days,
            "snapshots": len(hours),
            "first_observed_at": hours[0]["ts"],
            "last_observed_at": hours[-1]["ts"],
            "evidence_sha256": sha256(raw).hexdigest(),
        }
    return original, receipts


def track_c_abstention(
    *,
    portfolio_id: str,
    portfolio_sha: str,
    pod: str,
    address_sha: str,
    current: Decimal,
    candidate: Decimal,
    pod_budget: Decimal,
    as_of: str,
    source_sha: str,
    calibration_sha: str,
    last_training_observed: str,
) -> dict:
    """Run the actual Track C evaluator with *missing* finance, not invented zeros."""
    trial = Trial(
        trial_id=f"track-c-pit-{portfolio_id}-{pod}",
        candidate_id=pod,
        selection_as_of=as_of,
        status="ACCEPTED",
        evidence_sha256=calibration_sha,
        variant_k=candidate,
    )
    envelope = KResearchInput(
        portfolio_version=portfolio_id + "/v4-paper",
        portfolio_definition_sha256=portfolio_sha,
        pod_id=pod,
        selected_account_sha256=address_sha,
        sizing_policy_version="FIXED_K_NATIVE_QUANTITY/v4-paper",
        as_of=as_of,
        current_frozen_k=current,
        candidate_k=candidate,
        cost_policy_version="V4_PAPER_SEPARATE_FROM_MINUTE_PROXY",
        risk_policy_version="TRACK_C_PIT_GROSS_STRESS_V1",
        source_sha256=source_sha,
        trial_roster_sha256=digest([trial.model_dump(mode="json")]),
        trials=(trial,),
        windows=(),
        paired_control_blocks=(),
        pod_loss_budget_usd=pod_budget,
        follower_equity_usd=D("10000"),
        max_gross_notional_usd=D("20000"),
        max_market_notional_usd=D("5000"),
        daily_headroom_usd=D("500"),
        trailing_headroom_usd=D("800"),
        source_quantities={},
        source_marks={},
        follower_marks={},
        stress_shocks=(),
        adverse_price_extra_loss_usd=D("0"),
        latency_extra_loss_usd=D("0"),
        lot_notional_valid=False,
        unresolved_financial_effects=True,
        portfolio_correlation_checked=False,
        evidence_expired=_clock(as_of) - _clock(last_training_observed) > timedelta(days=45),
        finance_frame=None,
        coverage_missing=BLOCKERS,
    )
    proposal = evaluate_k(envelope)
    return {
        "proposal_sha256": proposal.identity_sha256,
        "decision": proposal.decision,
        "reason_codes": list(proposal.reasons),
        "release_eligible": False,
        "trade_authorized": False,
        "candidate_is_still_hypothetical": True,
    }


def summarize_outcomes(economics, *, end_ms: int) -> dict[str, dict[str, dict]]:
    """Wallet-only completed-episode diagnostics. No joint PM03 equity calculation."""
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    rows = defaultdict(list)
    for r in economics.iter_rows(named=True):
        rows[(r["account"], r["scenario"])].append(r)
    for (wallet, scenario), parts in rows.items():
        done = [x for x in parts if x["estimated_net_pnl"] is not None]
        blocked = Counter(x["outcome"] for x in parts if x["estimated_net_pnl"] is None)
        recent = [x for x in done if x["t0"] >= end_ms - 7 * 86400 * 1000]
        grouped[wallet][scenario] = {
            "priced_complete_episodes": len(done),
            "blocked_episodes": len(parts) - len(done),
            "blocked_reasons": dict(sorted(blocked.items())),
            "completed_episode_net_usd": round(sum(x["estimated_net_pnl"] for x in done), 8)
            if done
            else None,
            "recent_7d_net_usd": round(sum(x["estimated_net_pnl"] for x in recent), 8)
            if recent
            else None,
        }
    return dict(grouped)


def build_report(
    *,
    manifest: Path,
    registry_db: Path,
    jobfile: Path,
    source_root: Path,
    market_root: Path,
    input_root: Path,
    as_of: str,
    supplemental_root: Path | None = None,
    late_supplemental_root: Path | None = None,
) -> dict:
    import polars as pl

    now = _clock(as_of)
    if now.tzinfo is None:
        raise ValueError("ASOF_UTC_REQUIRED")
    root = input_root.resolve(strict=True)
    job_path = jobfile.resolve(strict=True)
    if root not in job_path.parents or jobfile.is_symlink():
        raise ValueError("RESEARCH_JOB_OUTSIDE_PINNED_INPUT_ROOT")
    job = _job(json.loads(job_path.read_bytes()))
    if job["schema"] != RETRO_SCHEMA:
        raise ValueError("EXPECTED_RETROSPECTIVE_JULY_POLICY")
    policyfile = input_root / job["k_policy_path"]
    if policyfile.is_symlink() or policyfile.parent.resolve() != root:
        raise ValueError("UNSAFE_PREWINDOW_POLICY")
    policy_raw = policyfile.read_bytes()
    if sha256(policy_raw).hexdigest() != job["k_policy_sha256"]:
        raise ValueError("PREWINDOW_POLICY_SHA_DRIFT")
    policy = _retro_policy(json.loads(policy_raw), job)
    if _clock(policy["training_end"]) > _clock(job["start"]):
        raise ValueError("PIT_TRAIN_WINDOW_OVERLAP")
    if now < _clock(policy["generated_at"]):
        raise ValueError("CANNOT_PRETEND_RESEARCH_POLICY_ALREADY_EXISTED")
    campaign = load_campaign(manifest=manifest, registry_db=registry_db, at=as_of)
    calibration, supplemental_receipts = load_supplemental_july(
        root=supplemental_root,
        policy=policy,
        account_hashes=campaign.account_hashes,
    )
    late_receipts: dict[str, dict] = {}
    if late_supplemental_root is not None:
        if not _clock(policy["training_end"]) < _clock(job["start"]):
            raise ValueError("NO_SEPARATE_PRE_EVALUATION_LATE_TRAINING_WINDOW")
        # An exact later training interval may fill *only* previously missing
        # wallets; it never competes with an original July k or tunes on OOS.
        calibration, late_receipts = load_supplemental_july(
            root=late_supplemental_root,
            policy={
                "wallets": calibration,
                "training_start": policy["training_end"],
                "training_end": job["start"],
            },
            account_hashes=campaign.account_hashes,
            filename_prefix="trackc-late",
        )
    source_sha = _v2_source_digest(source_root)
    if source_sha != job["source_collection_sha256"]:
        raise ValueError("SOURCE_COLLECTION_DRIFT")
    start_ms = int(_clock(job["start"]).timestamp() * 1000)
    end_ms = int(_clock(job["end"]).timestamp() * 1000)
    source, invalid, source_accounts, untrusted = _source(source_root, start_ms, end_ms)
    if source.is_empty():
        raise ValueError("NO_HISTORICAL_SOURCE_EVENTS")
    episodes, counts = _episodes(source, end_ms=end_ms, untrusted=untrusted)
    supported = episodes.filter(pl.col("source_status") == "SUPPORTED_EPISODE")
    if supported.is_empty():
        raise ValueError("NO_SUPPORTED_SOURCE_EPISODES")
    matched, market_sha, matched_days = _join_actions(_actions(supported), market_root)
    if _v2_source_digest(source_root) != source_sha:
        raise ValueError("SOURCE_COLLECTION_CHANGED_DURING_REPLAY")

    # Source cap at the *historical calibration cutoff* only. Do not cap using
    # current Gemini k; that was selected after the evaluation window.
    risk_budgets = sorted(
        {D(loss) for profile in campaign.profiles.values() for loss in profile.losses}
    )
    by_budget: dict[str, dict[str, dict[str, dict]]] = {}
    budget_k: dict[str, dict[str, D]] = {}
    for budget in risk_budgets:
        rates = {}
        for sha, record in calibration.items():
            rates[sha] = risk_k(record, budget, cutoff=job["start"])
        budget_key = str(budget)
        budget_k[budget_key] = rates
        selected = set(rates)
        subset = matched.filter(pl.col("account").is_in(selected))
        if subset.is_empty():
            by_budget[budget_key] = {}
            continue
        econ = _economics(
            subset,
            {"wallets": {k: {"k": str(v)} for k, v in rates.items()}, "markets": policy["markets"]},
            scenarios=SCENARIOS,
        )
        by_budget[budget_key] = summarize_outcomes(econ, end_ms=end_ms)

    portfolios = {}
    for pid, profile in campaign.profiles.items():
        sha_by_pod = campaign.account_hashes[pid]
        pods = {}
        for pod, old, budget in zip(
            profile.source_ids, profile.k_by_pod, profile.losses, strict=True
        ):
            addr_sha = sha_by_pod[pod]
            b = D(budget)
            bucket = str(b)
            record = calibration.get(addr_sha)
            historic = by_budget[bucket].get(addr_sha, {})
            if record is None:
                pods[pod] = {
                    "source_account_sha256": addr_sha,
                    "current_paper_k": old,
                    "asof_risk_k": None,
                    "pit_status": (
                        "BLOCKED_NO_PRE_EVALUATION_CALIBRATION"
                        if late_supplemental_root is not None
                        else "BLOCKED_NO_JULY_CALIBRATION"
                    ),
                    "track_c": None,
                    "scenarios": {},
                }
                continue
            candidate = budget_k[bucket][addr_sha]
            pods[pod] = {
                "source_account_sha256": addr_sha,
                "current_paper_k": old,
                "asof_risk_k": str(candidate),
                "pit_status": "COUNTERFACTUAL_PREWINDOW_K_ESTIMABLE",
                "training_observation_days": record["observation_days"],
                "calibration_last_observed_at": record["last_observed_at"],
                **(
                    {
                        "calibration_vintage": (
                            "AUGUST_TO_OCTOBER_LATE_MISSING_ONLY"
                            if addr_sha
                            in {
                                r["wallet_sha256"]
                                for r in late_receipts.values()
                                if r["status"] == "PREWINDOW_COMPLETE_PAGE_PROXY_ONLY"
                            }
                            else "ORIGINAL_JULY_TRAINING"
                        )
                    }
                    if late_supplemental_root is not None
                    else {}
                ),
                "track_c": track_c_abstention(
                    portfolio_id=pid,
                    portfolio_sha=campaign.seals[pid]["definition_sha256"],
                    pod=pod,
                    address_sha=addr_sha,
                    current=D(old),
                    candidate=candidate,
                    pod_budget=b,
                    as_of=as_of,
                    source_sha=source_sha,
                    calibration_sha=job["k_policy_sha256"],
                    last_training_observed=record["last_observed_at"],
                ),
                "scenarios": historic,
            }
        missing = [k for k, v in pods.items() if v["pit_status"].startswith("BLOCKED")]
        portfolios[pid] = {
            "definition_sha256": campaign.seals[pid]["definition_sha256"],
            "portfolio_after_oos_selection": True,
            "review_flags": list(campaign.flags[pid]),
            "pod_count": len(pods),
            "risk_budget_usd": profile.nominal_risk,
            "calibrated_pods": len(pods) - len(missing),
            "missing_pods": missing,
            "full_portfolio_pnl_usd": None,
            "max_trailing_drawdown_usd": None,
            "challenge_pass_rate": None,
            "status": "PARTIAL_HISTORICAL_EPISODES_NOT_PM03_MTM",
            "pods": pods,
        }

    return {
        "schema": "track_c_pit_v4_replay_report_v1",
        "classification": TRAIN_TO_OOS,
        "as_of": as_of,
        "training_start": policy["training_start"],
        "training_end_exclusive": policy["training_end"],
        "evaluation_start": job["start"],
        "evaluation_end_exclusive": job["end"],
        "policy_created_at": policy["generated_at"],
        "source_collection_sha256": source_sha,
        "k_policy_sha256": job["k_policy_sha256"],
        "supplemental_receipts": supplemental_receipts,
        **(
            {
                "late_supplemental_receipts": late_receipts,
                "late_training_start": policy["training_end"],
                "late_training_end_exclusive": job["start"],
            }
            if late_supplemental_root is not None
            else {}
        ),
        "supplemental_pages_are_retrospective_vendor_assertions": True,
        "calibrated_wallets_original": len(policy["wallets"]),
        "calibrated_wallets_with_supplement": len(calibration),
        "market_fingerprint_sha256": market_sha,
        "campaign_sha256": campaign.manifest_sha256,
        "risk_method": {
            "budget_usd": "per portfolio pod, current paper campaign",
            "shock_fraction": "0.20",
            "no_post_cutoff_performance_used_to_calibrate_k": True,
        },
        "cost_model": "NATIVE_V4_ESTIMATED_MINUTE_BASE_DELAYED_ADVERSE",
        "portfolio_count": len(portfolios),
        "source_wallets": source_accounts,
        "source_events": source.height,
        "source_episodes": episodes.height,
        "supported_episodes": supported.height,
        "market_input_days": matched_days,
        "source_blockers": dict(sorted({**invalid, **counts}.items())),
        "portfolio_risk_jointly_modeled": False,
        "financing_verified": False,
        "first_known_historical_attested": False,
        "historical_signed_release": False,
        "track_c_runtime_activated": False,
        "scientifically_qualified": False,
        "trading_authorized": False,
        "order_route": "NONE",
        "limitations": [
            "No authentic first-known source timestamps or historical signed k release",
            "16 rosters were selected after the historical test window; OOS portfolio selection impossible",
            "Only closed uninterrupted source episodes are priceable; blocked episodes are not zero PnL",
            "Historical venue lot sizes are unverified research proxies",
            "No complete joint PM03/PM04 portfolio MTM, funding, leverage or challenge-breach tape",
            "Track C evaluator must abstain without authentic PM03 finance; never auto-activate k",
            "Supplemental Vike hourly aggregates are fully paged but raw original response bytes/signatures are not independently authenticated",
        ],
        "portfolios": portfolios,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--registry-db", type=Path, required=True)
    p.add_argument("--jobfile", type=Path, required=True)
    p.add_argument("--input-root", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--market-root", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--supplemental-root", type=Path, default=None)
    p.add_argument("--late-supplemental-root", type=Path, default=None)
    p.add_argument("--as-of", required=True)
    args = p.parse_args()
    report = build_report(
        **{key: value for key, value in vars(args).items() if key != "output_root"}
    )
    root = args.output_root
    if root.is_symlink():
        raise ValueError("UNSAFE_OUTPUT_ROOT")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    path, sha = checked_publish(root, "track-c-pit-16", report)
    print(
        json.dumps(
            {
                "status": "PUBLISHED_RESEARCH_ONLY",
                "path": str(path),
                "sha256": sha,
                "portfolio_count": report["portfolio_count"],
                "portfolios_with_complete_calibration": sum(
                    not x["missing_pods"] for x in report["portfolios"].values()
                ),
                "source_episodes": report["source_episodes"],
                "supported_episodes": report["supported_episodes"],
                "active_k_changed": False,
                "scientifically_qualified": False,
                "trading_authorized": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
