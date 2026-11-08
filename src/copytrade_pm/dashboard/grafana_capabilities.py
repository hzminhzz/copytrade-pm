"""Publisher-only, bounded operational capabilities for native Grafana views.

All native reads occur on publisher cadence. The HTTP gateway never imports this module.
No account finance is reconstructed from research metadata or process liveness.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

CAPABILITY_SCHEMA = "grafana_operational_capabilities_v1"
FIELDS = {
    "portfolios": (
        "portfolio",
        "research_state",
        "deployment_state",
        "runtime_state",
        "members",
        "fixed_k",
        "exposure",
        "loss_used",
        "budget",
        "grade",
        "reason",
    ),
    "execution": (
        "intent",
        "decision",
        "market",
        "source_event_ms",
        "first_known_ms",
        "due_ms",
        "decision_ms",
        "intent_ms",
        "accept_ms",
        "fill_ms",
        "reconcile_ms",
        "fills",
        "grade",
        "reason",
    ),
    "health": ("component", "reported_state", "source_grade", "source_time", "authority", "reason"),
    "wallets": (
        "alias",
        "cohort",
        "excluded",
        "research_state",
        "inventory",
        "asof",
        "grade",
        "reason",
    ),
}
MAX_ROWS = {"portfolios": 25, "execution": 25, "health": 18, "wallets": 50}
STATES = {"VERIFIED", "DEGRADED", "STALE", "BLOCKED", "UNKNOWN", "UNAVAILABLE"}
MAX_TEXT = 96
# A market order can legitimately fill a few seconds after the due instant.
# Beyond this bound the latest owner-authenticated fill is an execution exception.
FILL_LATENESS_MS = 5_000


def _text(value: object) -> str | None:
    from .evidence_plane import safe_text

    if value is None:
        return None
    if type(value) not in (str, int, bool):
        return None
    text = str(value)
    # Identifiers and private free-text cannot be emitted.
    if safe_text(text, MAX_TEXT) != text:
        from .evidence_plane import EvidenceInvalid

        raise EvidenceInvalid("UNSAFE_NATIVE_PROJECTION_TEXT")
    return text


def _clock(value: object) -> str | None:
    from .evidence_plane import parse_utc

    return value if parse_utc(value) else None


def _rows(
    name: str,
    rows: list[dict],
    *,
    status: str,
    authority: str,
    observed: str | None = None,
    error: str | None = None,
    completeness: str | None = None,
) -> dict:
    from .evidence_plane import EvidenceInvalid

    if name not in FIELDS or status not in STATES or len(rows) > MAX_ROWS[name]:
        raise EvidenceInvalid("OPERATIONAL_CAPABILITY_SCOPE")
    if _text(authority) != authority or (observed is not None and _clock(observed) is None):
        raise EvidenceInvalid("OPERATIONAL_CAPABILITY_AUTHORITY")
    clean = []
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != set(FIELDS[name]):
            raise EvidenceInvalid("OPERATIONAL_ROW_SHAPE")
        item: dict[str, Any] = {}
        for field in FIELDS[name]:
            value = raw[field]
            if field.endswith("_ms") or field == "fills":
                if value is not None and (
                    type(value) is not int or value < 0 or value > 9_999_999_999_999
                ):
                    raise EvidenceInvalid("OPERATIONAL_INTEGER")
                item[field] = value
            elif field == "excluded":
                if value is not None and type(value) is not bool:
                    raise EvidenceInvalid("OPERATIONAL_BOOLEAN")
                item[field] = value
            elif field in {"source_time", "asof"}:
                if value is not None and _clock(value) is None:
                    raise EvidenceInvalid("OPERATIONAL_CLOCK")
                item[field] = value
            elif value is None:
                item[field] = None
            elif _text(value) != value:
                raise EvidenceInvalid("OPERATIONAL_PRIVATE_OR_UNSAFE_TEXT")
            else:
                item[field] = value
        if "grade" in item and item["grade"] not in STATES:
            raise EvidenceInvalid("OPERATIONAL_ROW_GRADE")
        if "source_grade" in item and item["source_grade"] not in STATES:
            raise EvidenceInvalid("OPERATIONAL_ROW_GRADE")
        clean.append(item)
    if completeness is None:
        completeness = (
            "COMPLETE"
            if clean and status == "VERIFIED"
            else (
                "EMPTY"
                if status == "VERIFIED" and not clean
                else "UNAVAILABLE"
                if status == "UNAVAILABLE"
                else "INCOMPLETE"
            )
        )
    if completeness not in {"COMPLETE", "EMPTY", "INCOMPLETE", "UNAVAILABLE"}:
        raise EvidenceInvalid("OPERATIONAL_COMPLETENESS_INVALID")
    if status == "VERIFIED" and completeness not in {"COMPLETE", "EMPTY"}:
        raise EvidenceInvalid("OPERATIONAL_CONTRADICTORY_COMPLETENESS")
    if status == "VERIFIED" and any(
        item.get("grade", item.get("source_grade", "UNKNOWN")) != "VERIFIED" for item in clean
    ):
        raise EvidenceInvalid("OPERATIONAL_CONTRADICTORY_VERIFICATION")
    if status in {"UNKNOWN", "UNAVAILABLE", "STALE", "BLOCKED"} and any(
        item.get("grade", item.get("source_grade")) == "VERIFIED" for item in clean
    ):
        raise EvidenceInvalid("OPERATIONAL_CONTRADICTORY_PARENT")
    if status == "VERIFIED" and observed is None:
        raise EvidenceInvalid("OPERATIONAL_VERIFIED_MISSING_SOURCE_CLOCK")
    return {
        "status": status,
        "authority": authority,
        "source_observed_at": observed,
        "error_code": _text(error),
        "completeness": completeness,
        "rows": clean,
    }


def unavailable(name: str, reason: str = "NATIVE_EVIDENCE_UNAVAILABLE") -> dict:
    authority = {
        "portfolios": "wallet_registry_and_protected_guardian",
        "execution": "protected_guardian_execution_receipts",
        "health": "independent_operational_sources",
        "wallets": "canonical_sqlite_registry",
    }[name]
    row = dict.fromkeys(FIELDS[name])
    if name == "portfolios":
        row.update(
            portfolio="NO_VERIFIED_PORTFOLIO",
            research_state="UNKNOWN",
            deployment_state="UNKNOWN",
            runtime_state="UNKNOWN",
            grade="UNAVAILABLE",
            reason=reason,
        )
    elif name == "execution":
        row.update(intent="NO_VERIFIED_RECEIPTS", grade="UNAVAILABLE", reason=reason)
    elif name == "health":
        row.update(
            component="CAPABILITY_UNAVAILABLE",
            reported_state="UNKNOWN",
            source_grade="UNAVAILABLE",
            authority=authority,
            reason=reason,
        )
    else:
        row.update(alias="REGISTRY_UNAVAILABLE", grade="UNAVAILABLE", reason=reason)
    return _rows(name, [row], status="UNAVAILABLE", authority=authority, error=reason)


def validate_capabilities(value: object, *, asof: datetime | None = None) -> dict:
    from .evidence_plane import EvidenceInvalid

    if (
        not isinstance(value, dict)
        or value.get("schema") != CAPABILITY_SCHEMA
        or set(value) != {"schema", *FIELDS}
    ):
        raise EvidenceInvalid("OPERATIONAL_SCHEMA_INVALID")
    result = {"schema": CAPABILITY_SCHEMA}
    for name in FIELDS:
        item = value[name]
        if not isinstance(item, dict) or set(item) != {
            "status",
            "authority",
            "source_observed_at",
            "error_code",
            "completeness",
            "rows",
        }:
            raise EvidenceInvalid("OPERATIONAL_SECTION_INVALID")
        result[name] = _rows(
            name,
            item["rows"],
            status=item["status"],
            authority=item["authority"],
            observed=item["source_observed_at"],
            error=item["error_code"],
            completeness=item["completeness"],
        )
        if asof is not None:
            from .evidence_plane import parse_utc

            times = [result[name]["source_observed_at"]]
            times.extend(row.get("source_time") for row in result[name]["rows"])
            times.extend(row.get("asof") for row in result[name]["rows"])
            if any(parse_utc(t) > asof for t in times if t is not None):
                raise EvidenceInvalid("FUTURE_CAPABILITY_SOURCE_CLOCK")
    return result


def age_capabilities(value: dict, *, now: datetime, published: datetime, max_age: int) -> dict:
    """The only row/section freshness transition policy; never refresh from HTTP time."""
    from .evidence_plane import parse_utc

    aged = validate_capabilities(value)
    publisher_stale = (now - published).total_seconds() > max_age
    for name in FIELDS:
        section = aged[name]
        source = parse_utc(section["source_observed_at"])
        section_stale = publisher_stale or (
            source is not None and (now - source).total_seconds() > max_age
        )
        for row in section["rows"]:
            row_time = parse_utc(row.get("source_time")) if row.get("source_time") else None
            row_stale = section_stale or (
                row_time is not None and (now - row_time).total_seconds() > max_age
            )
            if row_stale:
                for field in ("grade", "source_grade"):
                    if row.get(field) == "VERIFIED":
                        row[field] = "STALE"
                if section["status"] == "VERIFIED" or row_time is not None:
                    section_stale = True
        if section_stale:
            if section["status"] == "VERIFIED":
                section["status"] = "STALE"
            if section["status"] == "DEGRADED":
                section["status"] = "STALE"
            section["error_code"] = "EVIDENCE_AGE_EXCEEDED"
            section["completeness"] = "INCOMPLETE"
    return aged


def operational_incident(capabilities: dict) -> bool:
    """Only authenticated observed faults, not routine unavailable optional sources."""
    for row in capabilities.get("health", {}).get("rows", []):
        if row.get("source_grade") == "VERIFIED" and row.get("reported_state") in {
            "HALTED",
            "FAILED",
            "DIVERGENT",
            "ERROR",
            "STOPPED",
            "INACTIVE",
        }:
            return True
    return any(
        row.get("grade") == "DEGRADED"
        and row.get("reason")
        in {
            "MULTIPLE_ORDER_INTENTS",
            "FILL_LATE_BROKER_RECEIPT",
            "DECISION_LATE",
            "TRUNCATED_NATIVE_RECEIPTS",
            "DUPLICATE_BROKER_FILL_ID",
        }
        for row in capabilities.get("execution", {}).get("rows", [])
    )


def _get(reader: object, method: str, *, kwargs: dict | None = None) -> dict:
    fn = getattr(reader, method, None)
    if fn is None:
        raise ValueError("READER_METHOD_UNAVAILABLE")
    answer = fn(**(kwargs or {}))
    if not isinstance(answer, dict):
        raise ValueError("NATIVE_READ_INVALID")
    return answer


def _execution_observed(source: dict) -> str | None:
    """An owner capture clock, never the observer's own retrieval time."""
    from .evidence_plane import parse_utc

    sources = source.get("sources")
    if not isinstance(sources, dict):
        return None
    clocks = []
    identities = set()
    for key in ("status", "portfolio", "intent", "broker"):
        item = sources.get(key)
        if not isinstance(item, dict) or item.get("status") != "VERIFIED":
            return None
        observed = _clock(item.get("source_observed_at"))
        if observed is None:
            return None
        clocks.append(observed)
        identities.add(
            (
                item.get("account_binding_sha"),
                item.get("revision"),
                item.get("journal_sequence"),
                item.get("captured_at"),
            )
        )
    if len(identities) != 1 or any(value is None for value in next(iter(identities))):
        return None
    return min(clocks, key=lambda t: parse_utc(t))


def _source_time_valid(section: dict, *, asof: datetime) -> bool:
    from .evidence_plane import parse_utc

    values = [section.get("source_observed_at")]
    for row in section.get("rows", []):
        values.extend((row.get("source_time"), row.get("asof")))
    return all(t is None or (parse_utc(t) is not None and parse_utc(t) <= asof) for t in values)


def qualify_capabilities(value: dict, *, asof: datetime) -> dict:
    """Quarantine a future-dated capability without discarding independent evidence."""
    result = validate_capabilities(value)
    for name in FIELDS:
        if not _source_time_valid(result[name], asof=asof):
            result[name] = unavailable(name, "CAUSALLY_INVALID_SOURCE_CLOCK")
    return validate_capabilities(result, asof=asof)


def build_capabilities(reader: object, *, asof: datetime | None = None) -> dict:
    """Separate read failures by capability. Never promote availability by guess."""
    result: dict = {"schema": CAPABILITY_SCHEMA}
    for name, method, kwargs in (
        ("portfolios", "portfolio_explorer", {"limit": 25}),
        ("execution", "execution_monitor", {}),
        ("health", "health", {}),
        ("wallets", "wallets", {"limit": 50}),
    ):
        try:
            source = _get(reader, method, kwargs=kwargs)
            if name == "portfolios":
                records = source.get("records") or []
                status = source.get("status", "UNKNOWN")
                rows = []
                for record in records[:25]:
                    if not isinstance(record, dict):
                        continue
                    fixed_k = record.get("signed_fixed_k")
                    rows.append(
                        dict(
                            portfolio=_text(record.get("portfolio_id")),
                            research_state=_text(record.get("research_state")) or "UNKNOWN",
                            deployment_state="UNKNOWN",
                            runtime_state="UNKNOWN",
                            members=_text(len(record.get("members") or [])),
                            fixed_k="SIGNED_PRESENT"
                            if isinstance(fixed_k, dict) and fixed_k
                            else "UNAVAILABLE",
                            exposure=None,
                            loss_used=None,
                            budget=None,
                            grade=status if status in STATES else "UNKNOWN",
                            reason="NO_VERIFIED_OWNER_POD_FINANCE",
                        )
                    )
                result[name] = _rows(
                    name,
                    rows if status == "VERIFIED" else rows or unavailable(name)["rows"],
                    status=status if status in STATES else "UNKNOWN",
                    authority="canonical_sqlite_research_metadata",
                    observed=_clock(source.get("catalog", {}).get("source_observed_at"))
                    if isinstance(source.get("catalog"), dict)
                    else None,
                    error=_text(source.get("error_code")),
                )
            elif name == "execution":
                coherent = source.get("coherent_capture") is True
                entries = source.get("intents") or []
                intent_groups = {}
                for entry in entries:
                    if isinstance(entry, dict):
                        key = (entry.get("decision_id"), entry.get("market"))
                        if all(isinstance(x, str) and x for x in key):
                            intent_groups[key] = intent_groups.get(key, 0) + 1
                rows = []
                for entry in entries[:25]:
                    if not isinstance(entry, dict):
                        continue
                    first, due = entry.get("first_known_at"), entry.get("batch_due_ms")
                    reason = "NO_VERIFIED_CAUSAL_LINK"
                    grade = "UNKNOWN"
                    if (
                        coherent
                        and type(first) is int
                        and type(due) is int
                        and due == first + 300_000
                    ):
                        # Owner receipts, never the planned schedule, qualify execution.
                        decision = entry.get("batch_decision_at")
                        accepted = entry.get("broker_acceptance_at")
                        filled = entry.get("broker_fill_at")
                        intent_at = entry.get("guardian_intent_at_ms")
                        if (
                            intent_groups.get((entry.get("decision_id"), entry.get("market")), 0)
                            > 1
                        ):
                            grade, reason = "DEGRADED", "MULTIPLE_ORDER_INTENTS"
                        elif type(decision) is int and decision > due:
                            grade, reason = "DEGRADED", "DECISION_LATE"
                        elif type(intent_at) is int and intent_at < due:
                            grade, reason = "DEGRADED", "INTENT_BEFORE_DUE"
                        elif (
                            type(filled) is int
                            and entry.get("fill_trace_status") == "VERIFIED_OWNER_FILL_ID"
                            and filled > due + FILL_LATENESS_MS
                        ):
                            grade, reason = "DEGRADED", "FILL_LATE_BROKER_RECEIPT"
                        elif accepted is None:
                            grade, reason = (
                                "UNKNOWN",
                                "SINGLE_INTENT_UNCONFIRMED"
                                if not entry.get("confirmed_fills")
                                else "BROKER_ACCEPTANCE_UNAVAILABLE",
                            )
                        elif (
                            type(accepted) is int
                            and accepted >= due
                            and type(filled) is int
                            and filled >= accepted
                            and source.get("reconciliation") == "RECONCILED"
                            and entry.get("fill_trace_status") == "VERIFIED_OWNER_FILL_ID"
                        ):
                            grade, reason = "VERIFIED", "RECONCILED_SINGLE_MARKET_ORDER"
                        else:
                            grade, reason = "UNKNOWN", "BROKER_EXECUTION_UNQUALIFIED"
                    if source.get("truncated") or source.get("duplicate_fill_identity"):
                        grade, reason = (
                            "DEGRADED",
                            "TRUNCATED_NATIVE_RECEIPTS"
                            if source.get("truncated")
                            else "DUPLICATE_BROKER_FILL_ID",
                        )
                    rows.append(
                        dict(
                            intent=_text(entry.get("intent_id")),
                            decision=_text(entry.get("decision_id")),
                            market=_text(entry.get("market")),
                            source_event_ms=entry.get("source_event_at"),
                            first_known_ms=first,
                            due_ms=due,
                            decision_ms=entry.get("batch_decision_at"),
                            intent_ms=entry.get("guardian_intent_at_ms"),
                            accept_ms=entry.get("broker_acceptance_at"),
                            fill_ms=entry.get("broker_fill_at"),
                            reconcile_ms=entry.get("reconciliation_at_ms"),
                            fills=entry.get("confirmed_fills") if coherent else None,
                            grade=grade,
                            reason=reason,
                        )
                    )
                result[name] = _rows(
                    name,
                    rows if coherent else rows or unavailable(name)["rows"],
                    status="DEGRADED"
                    if source.get("truncated") or any(r["grade"] == "DEGRADED" for r in rows)
                    else "VERIFIED"
                    if coherent
                    and all(r["grade"] == "VERIFIED" for r in rows)
                    and _execution_observed(source) is not None
                    else "UNKNOWN",
                    authority="protected_guardian_owner_receipts",
                    observed=_execution_observed(source),
                    error="TRUNCATED_NATIVE_RECEIPTS" if source.get("truncated") else None,
                )
            elif name == "health":
                rows = []
                for component in ("guardian", "broker", "observer", "watchdog", "market"):
                    item = source.get(component)
                    if not isinstance(item, dict):
                        continue
                    status = item.get("status", "UNKNOWN")
                    rows.append(
                        dict(
                            component=component,
                            reported_state=_text(item.get("state")) or "UNKNOWN",
                            source_grade=(
                                "BLOCKED"
                                if status == "VERIFIED"
                                and _clock(item.get("source_observed_at")) is None
                                else status
                                if status in STATES
                                else "UNKNOWN"
                            ),
                            source_time=_clock(item.get("source_observed_at")),
                            authority=_text(item.get("authority")) or "unverified_source",
                            reason=_text(
                                item.get("error_code")
                                or item.get("reason")
                                or item.get("limitation")
                            ),
                        )
                    )
                for svc, item in list((source.get("services") or {}).items())[:12]:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        dict(
                            component=_text(svc),
                            reported_state=_text(item.get("os_active_state")) or "UNKNOWN",
                            source_grade="UNKNOWN",
                            source_time=None,
                            authority="os_systemd_liveness_only",
                            reason="OS_PROCESS_NOT_FINANCIAL_CERTAINTY",
                        )
                    )
                result[name] = _rows(
                    name,
                    rows or unavailable(name)["rows"],
                    status="DEGRADED"
                    if any(r["source_grade"] == "VERIFIED" for r in rows)
                    else "UNKNOWN",
                    authority="independent_operational_observations",
                    observed=_clock(source.get("retrieved_at")),
                )
            else:
                data = source.get("data") if isinstance(source.get("data"), dict) else {}
                status = source.get("status", "UNKNOWN")
                rows = []
                for item in (data.get("wallets") or [])[:50]:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        dict(
                            alias=_text(item.get("alias")),
                            cohort=_text(item.get("cohort")),
                            excluded=item.get("excluded")
                            if type(item.get("excluded")) is bool
                            else None,
                            research_state="RESEARCH_ONLY",
                            inventory=_text(source.get("inventory_sha256")),
                            asof=_clock(source.get("source_observed_at")),
                            grade=status if status in STATES else "UNKNOWN",
                            reason=_text(source.get("error_code")),
                        )
                    )
                result[name] = _rows(
                    name,
                    rows if status == "VERIFIED" else rows or unavailable(name)["rows"],
                    status=status if status in STATES else "UNKNOWN",
                    authority="canonical_sqlite_registry",
                    observed=_clock(source.get("source_observed_at")),
                    error=_text(source.get("error_code")),
                )
        except ValueError, TypeError, KeyError, OverflowError, RuntimeError:
            result[name] = unavailable(name)
    return (
        qualify_capabilities(result, asof=asof)
        if asof is not None
        else validate_capabilities(result)
    )
