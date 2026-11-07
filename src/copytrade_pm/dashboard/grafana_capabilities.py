"""Publisher-only, bounded operational capabilities for native Grafana views.

All native reads occur on publisher cadence. The HTTP gateway never imports this module.
No account finance is reconstructed from research metadata or process liveness.
"""

from __future__ import annotations

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
    return {
        "status": status,
        "authority": authority,
        "source_observed_at": observed,
        "error_code": _text(error),
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


def validate_capabilities(value: object) -> dict:
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
        )
    return result


def _get(reader: object, method: str, *, kwargs: dict | None = None) -> dict:
    fn = getattr(reader, method, None)
    if fn is None:
        raise ValueError("READER_METHOD_UNAVAILABLE")
    answer = fn(**(kwargs or {}))
    if not isinstance(answer, dict):
        raise ValueError("NATIVE_READ_INVALID")
    return answer


def build_capabilities(reader: object) -> dict:
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
                    rows or unavailable(name)["rows"],
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
                        grade = "VERIFIED"
                        reason = (
                            "SINGLE_INTENT_UNCONFIRMED"
                            if entry.get("confirmed_fills", 0) == 0
                            else "CHECK_BROKER_RECEIPTS"
                        )
                        if (
                            type(entry.get("batch_decision_at")) is int
                            and entry["batch_decision_at"] > due
                        ):
                            reason = "DECISION_LATE"
                        if (
                            intent_groups.get((entry.get("decision_id"), entry.get("market")), 0)
                            > 1
                        ):
                            reason = "MULTIPLE_ORDER_INTENTS"
                            grade = "DEGRADED"
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
                    rows or unavailable(name)["rows"],
                    status="VERIFIED" if coherent else "UNKNOWN",
                    authority="protected_guardian_owner_receipts",
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
                            source_grade=status if status in STATES else "UNKNOWN",
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
                    status="UNKNOWN",
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
                    rows or unavailable(name)["rows"],
                    status=status if status in STATES else "UNKNOWN",
                    authority="canonical_sqlite_registry",
                    observed=_clock(source.get("source_observed_at")),
                    error=_text(source.get("error_code")),
                )
        except ValueError, TypeError, KeyError, OverflowError:
            result[name] = unavailable(name)
    return validate_capabilities(result)
