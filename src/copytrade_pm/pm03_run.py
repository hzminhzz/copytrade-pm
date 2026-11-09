"""Replay-first PM-03 shadow run: no live trading interfaces.

Every decision is committed as a causal, content-hashed event. Recovery always
recomputes the account from the manifest and ledger, even if a checkpoint exists.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from decimal import Decimal as D
from pathlib import Path
import json
from zoneinfo import ZoneInfo

from .pm03_account import Account, Instrument, RiskState, Rulebook, clock, digest, number
from .pm03_execution import CostModel, MarketObservation, execute_targets
from .pm03_memory import Event, Ledger, _atomic_private
from .pm03_risk import RiskEvidence, RiskPolicy, classify

MODES = ("RESEARCH_SYNTHETIC", "HISTORICAL_HINDSIGHT", "PROSPECTIVE_OBSERVED")


def _positions(rows: dict[str, dict[str, str]]) -> dict[str, dict[Instrument, D]]:
    return {
        pm: {Instrument.parse(k): number(v) for k, v in book.items()} for pm, book in rows.items()
    }


def _prices(rows: dict[str, str]) -> dict[Instrument, D]:
    return {Instrument.parse(k): number(v) for k, v in rows.items()}


def _safebook(book: dict[str, dict[Instrument, D]]) -> dict:
    return {
        pm: {k.key: str(q) for k, q in sorted(positions.items())}
        for pm, positions in sorted(book.items())
    }


def _evidence(row: dict) -> RiskEvidence:
    typed = dict(row)
    for k in ("stressed_liquidity_loss", "hedge_break_loss"):
        typed[k] = number(typed.get(k, "0"))
    return RiskEvidence(**typed)


def _cost_model(row: dict) -> CostModel:
    typed = dict(row)
    for k in (
        "fee_bps",
        "full_spread_bps",
        "slippage_bps",
        "impact_bps_at_full_participation",
        "max_participation",
    ):
        typed[k] = number(typed[k])
    return CostModel(**typed)


def _quotes(rows: list[dict]) -> dict[Instrument, MarketObservation]:
    result = {}
    for raw in rows:
        obj = dict(raw)
        inst = Instrument.parse(obj.pop("instrument"))
        if inst in result:
            raise ValueError("DUPLICATE_MARKET_ID")
        obj["mark"] = number(obj["mark"])
        if obj.get("volume_base") is not None:
            obj["volume_base"] = number(obj["volume_base"])
        result[inst] = MarketObservation(inst, **obj)
    return result


class ShadowRun:
    """One isolated shadow-run directory, independent of PM-01/02 runtimes."""

    def __init__(
        self,
        root: Path,
        *,
        run_id: str,
        rulebook: Rulebook,
        started_at: str,
        mode: str,
        pm01_sha: str,
        pm02_sha: str,
        market_manifest_sha: str,
        policy: RiskPolicy | None = None,
    ):
        if not run_id or "/" in run_id or run_id in (".", ".."):
            raise ValueError("UNSAFE_RUN_ID")
        if mode not in MODES:
            raise ValueError("UNKNOWN_RESEARCH_MODE")
        clock(started_at)
        if clock(started_at) < clock(rulebook.observed_at):
            raise ValueError("RULEBOOK_NOT_YET_KNOWN")
        if not all(
            len(x) == 64 and all(c in "0123456789abcdef" for c in x)
            for x in (pm01_sha, pm02_sha, market_manifest_sha)
        ):
            raise ValueError("MISSING_SOURCE_SHA_LINEAGE")
        self.ledger = Ledger(root / run_id)
        self.policy = policy or RiskPolicy()
        self.manifest = {
            "schema": "pm03_shadow_run_v1",
            "run_id": run_id,
            "mode": mode,
            "started_at": started_at,
            "rulebook": rulebook.to_dict(),
            "rulebook_sha": rulebook.sha,
            "pm01_sha": pm01_sha,
            "pm02_sha": pm02_sha,
            "market_manifest_sha": market_manifest_sha,
            "risk_policy": {f.name: str(getattr(self.policy, f.name)) for f in fields(RiskPolicy)},
        }
        self.ledger._secure_file(self.ledger.path / "manifest.json")
        _atomic_private(
            self.ledger.path / "manifest.json",
            json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode(),
        )
        self.initial_rulebook = rulebook
        self.account = Account.start(rulebook, started_at)
        self.last_event_id: str | None = None
        self.last_event_time = started_at
        self.restore()

    def _apply(self, account: Account, event: Event) -> dict:
        account._prepare_risk_semantics(event.payload.get("risk_semantics_version", 1))
        if event.payload.get("run_id") != self.manifest["run_id"]:
            raise ValueError("CROSS_RUN_EVENT")
        if clock(event.decision_at) < clock(self.manifest["started_at"]):
            raise ValueError("EVENT_PRECEDES_START")
        if clock(event.decision_at) < clock(account.rulebook.observed_at):
            raise ValueError("RULEBOOK_FROM_FUTURE")
        if event.payload.get("rulebook_sha") != account.rulebook.sha:
            raise ValueError("RETROACTIVE_RULEBOOK_CHANGE")
        input_row = event.payload["input"]
        kind = event.kind
        result = {}
        if kind.startswith("PM04_"):
            from .pm04_shadow import apply_pm04

            result = apply_pm04(account, event, self.policy, self.manifest["mode"])
        elif kind == "MARK":
            if not input_row.get("state_known", False):
                account.risk = RiskState.HALT
                account.halt_reason = "UNKNOWN_ACCOUNT_OBSERVATION"
                result = {"status": "HALT_UNKNOWN"}
            else:
                account.mark(_prices(input_row["prices"]), event.decision_at)
                account.verify()
                result = {"status": "MARKED", "stage_passed": account.stage_passed}
        elif kind == "DECISION":
            candidates = _positions(input_row["proposed"])
            obs = _quotes(input_row["observations"])
            evidence = _evidence(input_row["evidence"])
            if evidence.input_status != self.manifest["mode"]:
                raise ValueError("RESEARCH_MODE_MISMATCH")
            if any(clock(q.first_known_at) > clock(event.first_known_at) for q in obs.values()):
                raise ValueError("MARKET_OBSERVATION_NOT_YET_KNOWN")
            if evidence.input_status == "PROSPECTIVE_OBSERVED" and (
                self.manifest["pm01_sha"] == digest("unknown")
                or self.manifest["pm02_sha"] == digest("unknown")
            ):
                raise ValueError("MISSING_PROSPECTIVE_EVIDENCE")
            shocks = tuple(_prices(sc) for sc in input_row["shocks"])
            tracked = set(account.quantities) | {
                k for book in account.pm_quantities.values() for k, q in book.items() if q
            }
            if tracked - set(obs):
                account.risk = RiskState.HALT
                account.halt_reason = "MISSING_EXISTING_POSITION_MARK"
            elif evidence.account_state_known and evidence.market_state_known:
                account.mark({k: q.mark for k, q in obs.items()}, event.decision_at)
            else:
                account.risk = RiskState.HALT
                account.halt_reason = "UNKNOWN_AUTHORITATIVE_ACCOUNT_OR_MARKET"
            decision = classify(
                account,
                candidates,
                {k: q.mark for k, q in obs.items()},
                shocks,
                evidence,
                self.policy,
            )
            may_simulate = (
                account.rulebook.confirmed
                and evidence.trusted
                and evidence.account_state_known
                and evidence.market_state_known
                and evidence.market_coverage_valid
                and not evidence.pending_unknown_orders
                # Future real PM-02 qualification flags alone cannot confer
                # positional authority without an audited PM-01 target contract.
                and evidence.input_status == "RESEARCH_SYNTHETIC"
            )
            execution = execute_targets(
                account,
                decision["approved"],
                obs,
                _cost_model(input_row["costs"]),
                decision_at=event.decision_at,
                hypothetical_fill_at=event.hypothetical_fill_at,
                permitted=may_simulate,
            )
            result = {
                "risk": {
                    k: value for k, value in decision.items() if k not in ("approved", "proposed")
                },
                "approved": _safebook(decision["approved"]),
                "execution": execution,
            }
        elif kind == "FUNDING":
            local_day = (
                clock(event.decision_at)
                .astimezone(ZoneInfo(account.rulebook.timezone))
                .date()
                .isoformat()
            )
            if local_day != account.daily_key:
                raise ValueError("MISSING_DAILY_RESET_MARK_BEFORE_FUNDING")
            account.post_funding(
                number(input_row["amount"]),
                {pm: number(v) for pm, v in input_row["allocated"].items()},
            )
            result = {"status": "FUNDING_RECORDED"}
        elif kind == "MANUAL_RESET":
            if not input_row.get("operator_id") or not input_row.get("authorization_reference"):
                raise ValueError("MISSING_MANUAL_AUTHORIZATION")
            account.manual_reset(
                authorization=input_row["authorization_reference"], as_of=event.decision_at
            )
            result = {"status": "SIMULATED_MANUAL_RESET"}
        elif kind == "STAGE":
            next_book = Rulebook.from_dict(input_row["next_rulebook"])
            if not next_book.confirmed:
                raise ValueError("UNCONFIRMED_STAGE_TERMS")
            account.advance_stage(next_book, as_of=event.decision_at)
            result = {"status": "SIMULATED_STAGE_TRANSITION"}
        elif kind == "HALT":
            account.risk = RiskState.HALT
            account.halt_reason = input_row.get("reason") or "MANUAL_SHADOW_HALT"
            result = {"status": "HALT_LATCHED"}
        else:
            raise ValueError("UNKNOWN_EVENT_KIND")
        if account.pm04_state and not kind.startswith("PM04_"):
            from .pm04_shadow import on_account_event

            on_account_event(account, kind, input_row, event.decision_at)
        return result

    def restore(self) -> dict:
        account = Account.start(self.initial_rulebook, self.manifest["started_at"])
        last = None
        last_time = self.manifest["started_at"]
        for row in self.ledger.read():
            event = Event(**row["event"])
            result = self._apply(account, event)
            post_sha = digest({"account": account.snapshot(), "result": result})
            if post_sha != event.payload.get("post_state_sha"):
                raise ValueError("REPLAY_POST_STATE_DIVERGENCE")
            trace = event.payload.get("tool_trace")
            if trace != {
                "action": f"pm03.shadow.{event.kind.lower()}",
                "status": "OK",
                "executed_at": event.decision_at,
                "input_sha": event.source_sha,
                "output_sha": post_sha,
                "rulebook_sha": account.rulebook.sha,
            }:
                raise ValueError("MISSING_OR_CONFLICTING_TOOL_TRACE")
            last = event.event_id
            last_time = event.decision_at
        self.account = account
        self.last_event_id = last
        self.last_event_time = last_time
        return self.state()

    def record(self, event: Event) -> dict:
        event.validate()
        current_rows = self.ledger.read()
        expected_head = current_rows[-1]["sha"] if current_rows else "0" * 64
        if current_rows and self.last_event_id != current_rows[-1]["event"]["event_id"]:
            raise ValueError("STALE_RUN_PROCESS_REOPEN_REQUIRED")
        old = next((r for r in current_rows if r["event"]["event_id"] == event.event_id), None)
        if old is not None:
            prior = dict(old["event"])
            payload = dict(prior.pop("payload"))
            claimed = dict(event.to_dict())
            new_payload = dict(claimed.pop("payload"))
            if "risk_semantics_version" in new_payload and (
                type(new_payload["risk_semantics_version"]) is not int
                or new_payload["risk_semantics_version"] != payload.get("risk_semantics_version", 1)
            ):
                raise ValueError("CONFLICTING_EVENT_REVISION")
            for derived in ("post_state_sha", "tool_trace", "risk_semantics_version"):
                payload.pop(derived, None)
                new_payload.pop(derived, None)
            if prior != claimed or payload != new_payload:
                raise ValueError("CONFLICTING_EVENT_REVISION")
            return self.restore()
        if clock(event.decision_at) < clock(self.last_event_time):
            raise ValueError("OUT_OF_ORDER_EVENT")
        if (
            type(event.payload.get("risk_semantics_version", 2)) is not int
            or event.payload.get("risk_semantics_version", 2) != 2
        ):
            raise ValueError("LEGACY_RISK_SEMANTICS_READ_ONLY")
        event = replace(event, payload={**event.payload, "risk_semantics_version": 2})
        staged = deepcopy(self.account)
        result = self._apply(staged, event)
        payload = dict(event.payload)
        payload["post_state_sha"] = digest({"account": staged.snapshot(), "result": result})
        payload["tool_trace"] = {
            "action": f"pm03.shadow.{event.kind.lower()}",
            "status": "OK",
            "executed_at": event.decision_at,
            "input_sha": event.source_sha,
            "output_sha": payload["post_state_sha"],
            "rulebook_sha": staged.rulebook.sha,
        }
        sealed = Event(**{**event.to_dict(), "payload": payload})
        self.ledger.append(sealed, expected_head=expected_head)
        # If killed after append and before assignment, restore() replays it.
        self.account = staged
        self.last_event_id = sealed.event_id
        self.last_event_time = sealed.decision_at
        return self.state()

    def state(self) -> dict:
        return {
            "schema": "pm03_run_state_v1",
            "run_id": self.manifest["run_id"],
            "research_mode": self.manifest["mode"],
            "as_of": self.last_event_time,
            "last_processed_event": self.last_event_id,
            "pm01_artifact_sha": self.manifest["pm01_sha"],
            "pm02_artifact_sha": self.manifest["pm02_sha"],
            "rulebook_sha": self.account.rulebook.sha,
            "market_source_manifest_sha": self.manifest["market_manifest_sha"],
            "account": self.account.snapshot(),
            "quality_gates": {
                "contracts_confirmed": self.account.rulebook.account_terms_confirmed,
                "live_authorization": False,
            },
            "unresolved_blockers": [
                "NO_LIVE_BROKER_AUTHORIZATION",
                "NO_SCIENTIFIC_QUALIFIED_WALLET"
                if self.manifest["mode"] != "RESEARCH_SYNTHETIC"
                else "SYNTHETIC_ONLY",
            ],
        }

    def checkpoint(self) -> str:
        return self.ledger.checkpoint(self.state())

    def verify_checkpoint(self, sha: str) -> dict:
        checkpoint = self.ledger.load_checkpoint(sha)
        current = self.restore()
        if checkpoint != current:
            raise ValueError("CHECKPOINT_REPLAY_STATE_MISMATCH")
        return current
