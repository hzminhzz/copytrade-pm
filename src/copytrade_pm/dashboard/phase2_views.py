"""Evidence-qualified operational and research dashboard presentation.

All tables are non-selecting, non-exporting read-only projections.
"""

from __future__ import annotations

from typing import Any

from .views import clean, evidence_table


def _table(mo, rows: list[dict], *, page_size: int = 20):
    return mo.ui.table(
        rows or [{"Evidence": "UNAVAILABLE"}],
        selection=None,
        show_download=False,
        show_search=False,
        pagination=True,
        page_size=page_size,
    )


def risk_view(mo, report: dict[str, Any]):
    measures = [
        {
            "Metric": clean(name),
            "Value": clean(value.get("value")),
            "Evidence": clean(value.get("status")),
            "Unit": clean(value.get("unit")),
        }
        for name, value in report["metrics"].items()
    ]
    pods = [
        {
            "Pod": clean(p.get("pod_id")),
            "Loss used": clean(p.get("loss_used")),
            "Budget": "UNAVAILABLE (not in operator projection)",
            "Utilization": "UNKNOWN",
        }
        for p in report["pod_losses"]
    ]
    return mo.vstack(
        [
            mo.md("# Operations · Guardian risk status"),
            mo.md(
                "**Read-only.** Values come from Guardian; chart-derived risk and "
                "implied contractual budget limits are prohibited."
            ),
            mo.md("## Account equity, floors and headroom"),
            _table(mo, measures),
            mo.md("## Per-pod loss usage"),
            _table(mo, pods),
            mo.md(
                f"**Pod budget:** {clean(report['pod_budget_status'])}. "
                f"{clean(report['pod_budget_reason'])}. "
                "A $200 trigger does not guarantee a $200 realized maximum."
            ),
            mo.md(
                f"**Owner-mark gross exposure:** {clean(report['exposure'].get('gross'))} · "
                f"**Net:** {clean(report['exposure'].get('net'))} · "
                f"**Evidence:** {clean(report['exposure']['status'])} · "
                f"**Reservations:** {clean(report['reservation_count'])}."
            ),
            mo.md(
                f"**Guardian HALTs:** {clean(report['guardian_halts'])}. "
                f"**Broker reconciliation:** {clean(report['reconciliation'])}."
            ),
            mo.md("## Owner read provenance"),
            evidence_table(mo, report["sources"]),
        ]
    )


def execution_view(mo, report: dict[str, Any]):
    intents = []
    for i in report["intents"]:
        intents.append(
            {
                "Intent ID": clean(i.get("intent_id")),
                "Decision ID": clean(i.get("decision_id")),
                "Causal link": clean(i.get("decision_link")),
                "Market": clean(i.get("market")),
                "Quantity": clean(i.get("quantity")),
                "Filled (owner)": clean(i.get("filled")),
                "Status": clean(i.get("status")),
                "Source event ms": clean(i.get("source_event_at")),
                "First-known ms": clean(i.get("first_known_at")),
                "Batch due ms": clean(i.get("batch_due_ms")),
                "Batch decision ms": clean(i.get("batch_decision_at")),
                "Guardian decision ms": clean(i.get("guardian_decision_at_ms")),
                "Guardian intent ms": clean(i.get("guardian_intent_at_ms")),
                "Broker epoch": clean(i.get("broker_epoch")),
                "Broker accepted ms": clean(i.get("broker_acceptance_at")),
                "Broker known-fill ms": clean(i.get("broker_fill_at")),
                "Fill evidence": clean(i.get("fill_trace_status")),
                "Reconciliation ms": clean(i.get("reconciliation_at_ms")),
            }
        )
    decisions = [
        {
            "Decision": clean(i.get("decision_id")),
            "Release": clean(i.get("release_sha")),
            "Status": clean(i.get("status")),
            "Pod count": clean(i.get("pod_count")),
            "Reasons": clean(i.get("reasons")),
        }
        for i in report["decisions"]
    ]
    receipts = [
        {
            "Decision": clean(r.get("decision_id")),
            "Receipt hash": clean(r.get("receipt_sha")),
            "Source event ms": clean(r.get("source_event_ms")),
            "Source known ms": clean(r.get("source_known_ms")),
            "Local first-known ms": clean(r.get("first_known_ms")),
            "5m due ms": clean(r.get("batch_due_ms")),
            "Batch decision ms": clean(r.get("batch_decision_ms")),
        }
        for r in report.get("source_events", [])
    ]
    return mo.vstack(
        [
            mo.md("# Operations · Execution monitor"),
            mo.md(
                "**Read-only. No broker actions.** All causal timestamps originate in "
                "verified owner receipts. Missing clocks and broker acceptance remain UNKNOWN; "
                "similar timestamps are never sufficient to join records."
            ),
            mo.md(
                f"**Capture coherence:** {clean(report['link_status'])} · "
                f"**Broker certainty:** {clean(report['reconciliation'])} · "
                f"**Duplicate fill identities:** {clean(report.get('duplicate_fill_identity'))} · "
                f"**Truncated:** {clean(report['truncated'])}."
            ),
            mo.md("## Source receipt to batch"),
            _table(mo, receipts),
            mo.md("## Guardian decisions"),
            _table(mo, decisions),
            mo.md("## Durable intents and fills"),
            _table(mo, intents),
            mo.md(
                "**Target vs actual positions:** UNAVAILABLE — the operator projection "
                "does not expose authenticated matched position books."
            ),
            mo.md("**Timeout and unknown broker outcomes are not confirmed failed orders.**"),
            mo.md("## Owner read provenance"),
            evidence_table(mo, report["sources"]),
        ]
    )


def portfolio_view(mo, report: dict[str, Any]):
    rows = []
    for item in report["records"]:
        rows.append(
            {
                "Portfolio": clean(item["portfolio_id"]),
                "Version": clean(item["version"]),
                "Research state": clean(item["research_state"]),
                "Deployment": clean(item["deployment_state"]),
                "Running": clean(item["runtime_state"]),
                "Known UTC": clean(item["selection_known_at"]),
                "Members": ", ".join(map(clean, item["members"])),
                "Exclusions": clean(item.get("exclusions")),
                "Account scope": clean(item.get("account_scope")),
                "Market scope": clean(item.get("market_scope")),
                "Fixed-k parameters": clean(item.get("signed_fixed_k")),
                "Sealed": item["source_sealed"],
                "Source state": clean(item["source_state"]),
                "Sizing contract": clean(item["sizing_contract"]),
                "Definition SHA": clean(item["definition_sha256"]),
            }
        )
    return mo.vstack(
        [
            mo.md("# Research · Portfolio explorer"),
            mo.md(
                "SQLite owns versioned research identity. **SAVED and RESEARCH_SELECTED "
                "never establish DEPLOYED or RUNNING_OBSERVED.**"
            ),
            mo.md(
                f"**Catalog status:** {clean(report['status'])} · "
                f"**Known portfolios:** {clean(report.get('total'))} · "
                f"**Matches:** {clean(report.get('total_matches'))} · "
                f"**Offset:** {clean(report.get('offset'))} · "
                f"**As-of:** {clean(report.get('asof'))} · "
                f"**Truncated:** {clean(report.get('truncated'))}."
            ),
            _table(mo, rows, page_size=15),
            mo.md("## Native provenance"),
            evidence_table(
                mo, {"SQLite catalog": report["catalog"], "Research selection": report["selection"]}
            ),
            mo.md(
                "**Release/actual runtime membership:** UNKNOWN without an independently "
                "verified portfolio-specific release binding and fresh runtime evidence."
            ),
        ]
    )


def research_view(mo, report: dict[str, Any], contract_rules: dict[str, Any] | None = None):
    rows = []
    payload = report.get("data") or {}
    for item in payload.get("reports", []) if isinstance(payload, dict) else []:
        rows.append(
            {
                "Job": clean(item.get("job_id")),
                "Cache key": clean(item.get("cache_key")),
                "Job SHA": clean(item.get("job_sha256")),
                "Report SHA": clean(item.get("report_sha256")),
                "Input binding": clean(item.get("input_binding_sha256")),
                "Market binding": clean(item.get("market_binding_sha256")),
                "Source fingerprints": clean(item.get("source_fingerprints")),
                "UTC start": clean(item.get("utc_start")),
                "UTC end": clean(item.get("utc_end")),
                "Sealed portfolio": clean(item.get("sealed_portfolio_id")),
                "Kind": clean(item.get("kind")),
                "Research": clean(item.get("research_status")),
                "Finance": clean(item.get("financial_status")),
                "Clock": clean(item.get("clock_basis")),
                "Blockers": clean(item.get("blockers")),
                "Scientific": "NOT QUALIFIED",
                "Trading": "NOT AUTHORIZED",
            }
        )
    rules = contract_rules.get("data") if isinstance(contract_rules, dict) else {}
    rules = rules if isinstance(rules, dict) else {}
    scenarios = [
        {
            "Contract": clean(item.get("id")),
            "Rule SHA": clean(item.get("rule_sha256")),
            "Authority": clean(item.get("rule_authority")),
            "Missing provider terms": clean(item.get("missing_terms")),
            "Qualification": "SCENARIO_ONLY",
            "Configuration": clean(item.get("configuration")),
        }
        for item in rules.get("contracts", [])
        if isinstance(item, dict)
    ]
    return mo.vstack(
        [
            mo.md("# Research · Immutable research lab"),
            mo.md(
                "Catalog is scoped to an **owner-configured** cache root and contains "
                "only SHA-verified canonical job reports. No job launcher, arbitrary path "
                "browser or hidden on-demand recomputation is available."
            ),
            mo.md(
                f"**Read status:** {clean(report.get('status'))} · "
                f"**Error:** {clean(report.get('error_code'))} · "
                f"**Total:** {clean(payload.get('total') if isinstance(payload, dict) else None)}."
            ),
            _table(mo, rows),
            mo.md("## Native contract-rule scenarios (not executed EV results)"),
            mo.md(
                f"**Rule status:** {clean(rules.get('status'))} · "
                f"**Rules SHA:** {clean(rules.get('rules_sha256'))}. "
                "No owner-verified follower EV comparison is available here."
            ),
            _table(mo, scenarios),
            mo.md(
                "These user-supplied archetypes have unverified provider terms, "
                "and no scenario is a scientifically qualified follower result. "
                "The native offline contract comparator is never invoked by this UI."
            ),
            mo.md("## Source provenance"),
            evidence_table(mo, {"Immutable report catalog": report}),
        ]
    )


def performance_view(mo, report: dict[str, Any], history: dict[str, Any] | None = None):
    history = history or {}
    contents = [
        mo.md("# Research · Evidence-qualified financial performance"),
        mo.md("## Current Guardian metrics (not historical economic qualification)"),
        _table(
            mo,
            [
                {
                    "Metric": clean(name),
                    "Owner value": clean(item.get("value")),
                    "Evidence": clean(item.get("status")),
                }
                for name, item in report.get("metrics", {}).items()
            ],
        ),
        mo.md(f"## Owner-verified SHADOW history · {clean(history.get('status', 'UNAVAILABLE'))}"),
    ]
    points = history.get("points", [])
    if history.get("status") == "VERIFIED_OWNER_SHADOW_TAIL" and points:
        from .chart_data import linked_chart

        contents.extend(
            [
                mo.md(
                    "Owner-observed **SHADOW** equity, risk floors, headroom and "
                    "unrealized values. These are not broker-executed follower PnL. "
                    "UTC brushing stays inside the browser."
                ),
                linked_chart(points),
            ]
        )
    else:
        contents.append(
            mo.md(
                f"**Historical finance UNAVAILABLE/BLOCKED:** "
                f"{clean(history.get('error_code', 'NO_VERIFIED_OWNER_CAPTURE'))}. "
                "No chart is synthesized from static risk values."
            )
        )
    contents.extend(
        [
            mo.md("## Evidence limitations"),
            mo.md(
                "This owner projection is a bounded tail and may not include all prior "
                "financial extrema. Separate historical source wallets, modeled follower, "
                "Demo, and broker-executed series cannot be conflated with SHADOW data. "
                "Chart floats cannot define contractual risk or trading authorization."
            ),
        ]
    )
    return mo.vstack(contents)
