"""Evidence-qualified operational and research dashboard presentation.

All tables are non-selecting, non-exporting read-only projections.
"""
from __future__ import annotations

from typing import Any

from .views import clean, evidence_table


def _table(mo, rows: list[dict], *, page_size: int = 20):
    return mo.ui.table(rows or [{"Evidence": "UNAVAILABLE"}], selection=None,
                       show_download=False, show_search=False,
                       pagination=True, page_size=page_size)


def risk_view(mo, report: dict[str, Any]):
    measures = [
        {"Metric": clean(name), "Value": clean(value.get("value")),
         "Evidence": clean(value.get("status")), "Unit": clean(value.get("unit"))}
        for name, value in report["metrics"].items()
    ]
    pods = [
        {"Pod": clean(p.get("pod_id")), "Loss used": clean(p.get("loss_used")),
         "Budget": "UNAVAILABLE (not in operator projection)",
         "Utilization": "UNKNOWN"}
        for p in report["pod_losses"]
    ]
    return mo.vstack([
        mo.md("# Operations · Guardian risk status"),
        mo.md("**Read-only.** Values come from Guardian; chart-derived risk and "
              "implied contractual budget limits are prohibited."),
        mo.md("## Account equity, floors and headroom"), _table(mo, measures),
        mo.md("## Per-pod loss usage"), _table(mo, pods),
        mo.md(f"**Pod budget:** {clean(report['pod_budget_status'])}. "
              f"{clean(report['pod_budget_reason'])}. "
              "A $200 trigger does not guarantee a $200 realized maximum."),
        mo.md(f"**Gross/net exposure:** {clean(report['exposure']['status'])}. "
              f"**Reservations:** {clean(report['reservation_count'])}."),
        mo.md(f"**Guardian HALTs:** {clean(report['guardian_halts'])}. "
              f"**Broker reconciliation:** {clean(report['reconciliation'])}."),
        mo.md("## Owner read provenance"), evidence_table(mo, report["sources"]),
    ])


def execution_view(mo, report: dict[str, Any]):
    intents = []
    for i in report["intents"]:
        intents.append({
            "Intent ID": clean(i.get("intent_id")),
            "Decision ID": clean(i.get("decision_id")),
            "Causal link": clean(i.get("decision_link")),
            "Market": clean(i.get("market")),
            "Quantity": clean(i.get("quantity")),
            "Filled (owner)": clean(i.get("filled")),
            "Status": clean(i.get("status")),
            "Guardian intent ms": clean(i.get("guardian_intent_at_ms")),
            "Broker epoch": clean(i.get("broker_epoch")),
            "Broker fill": "UNKNOWN",
            "Reconciliation ms": clean(i.get("reconciliation_at_ms")),
        })
    decisions = [
        {"Decision": clean(i.get("decision_id")), "Release": clean(i.get("release_sha")),
         "Status": clean(i.get("status")), "Pod count": clean(i.get("pod_count")),
         "Reasons": clean(i.get("reasons"))}
        for i in report["decisions"]
    ]
    return mo.vstack([
        mo.md("# Operations · Execution monitor"),
        mo.md("**Read-only. No broker actions.** Source event, first-known receipt, "
              "five-minute batch, acceptance and broker fill clocks are UNKNOWN "
              "unless their owner exposes verified durable records."),
        mo.md(f"**Capture coherence:** {clean(report['link_status'])} · "
              f"**Broker certainty:** {clean(report['reconciliation'])} · "
              f"**Truncated:** {clean(report['truncated'])}."),
        mo.md("## Guardian decisions"), _table(mo, decisions),
        mo.md("## Durable intents"), _table(mo, intents),
        mo.md("**Target vs actual positions:** UNAVAILABLE — the operator projection "
              "does not expose authenticated matched position books."),
        mo.md("**Timeout and unknown broker outcomes are not confirmed failed orders.**"),
        mo.md("## Owner read provenance"), evidence_table(mo, report["sources"]),
    ])


def portfolio_view(mo, report: dict[str, Any]):
    rows = []
    for item in report["records"]:
        rows.append({
            "Portfolio": clean(item["portfolio_id"]), "Version": clean(item["version"]),
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
        })
    return mo.vstack([
        mo.md("# Research · Portfolio explorer"),
        mo.md("SQLite owns versioned research identity. **SAVED and RESEARCH_SELECTED "
              "never establish DEPLOYED or RUNNING_OBSERVED.**"),
        mo.md(f"**Catalog status:** {clean(report['status'])} · "
              f"**Known portfolios:** {clean(report.get('total'))} · "
              f"**As-of:** {clean(report.get('asof'))} · "
              f"**Truncated:** {clean(report.get('truncated'))}."),
        _table(mo, rows, page_size=15),
        mo.md("## Native provenance"),
        evidence_table(mo, {"SQLite catalog": report["catalog"],
                            "Research selection": report["selection"]}),
        mo.md("**Release/actual runtime membership:** UNKNOWN without an independently "
              "verified portfolio-specific release binding and fresh runtime evidence."),
    ])


def research_view(mo, report: dict[str, Any]):
    rows = []
    payload = report.get("data") or {}
    for item in payload.get("reports", []) if isinstance(payload, dict) else []:
        rows.append({
            "Job": clean(item.get("job_id")),
            "Cache key": clean(item.get("cache_key")),
            "Job SHA": clean(item.get("job_sha256")),
            "Report SHA": clean(item.get("report_sha256")),
            "Kind": clean(item.get("kind")),
            "Research": clean(item.get("research_status")),
            "Finance": clean(item.get("financial_status")),
            "Clock": clean(item.get("clock_basis")),
            "Blockers": clean(item.get("blockers")),
            "Scientific": "NOT QUALIFIED",
            "Trading": "NOT AUTHORIZED",
        })
    return mo.vstack([
        mo.md("# Research · Immutable research lab"),
        mo.md("Catalog is scoped to an **owner-configured** cache root and contains "
              "only SHA-verified canonical job reports. No job launcher, arbitrary path "
              "browser or hidden on-demand recomputation is available."),
        mo.md(f"**Read status:** {clean(report.get('status'))} · "
              f"**Error:** {clean(report.get('error_code'))} · "
              f"**Total:** {clean(payload.get('total') if isinstance(payload, dict) else None)}."),
        _table(mo, rows),
        mo.md("**Contract EV:** SCENARIO_ONLY / UNAVAILABLE in this immutable job catalog. "
              "No complete owner-verified follower tape is provided to this viewer; "
              "the native contract selector remains an offline read-only tool."),
        mo.md("## Source provenance"),
        evidence_table(mo, {"Immutable report catalog": report}),
    ])


def performance_view(mo, report: dict[str, Any]):
    return mo.vstack([
        mo.md("# Research · Financial performance"),
        mo.md("**Historical financial series: UNAVAILABLE.** The approved Guardian "
              "operator captures expose current finance, not a coherent historical "
              "equity/drawdown/pod PnL tape. A synthetic curve would misrepresent "
              "follower economics."),
        mo.md("## Current metrics (not chart history)"),
        _table(mo, [
            {"Metric": clean(name), "Owner value": clean(item.get("value")),
             "Evidence": clean(item.get("status"))}
            for name, item in report.get("metrics", {}).items()
        ]),
        mo.md("## Source limitations"),
        mo.md("Historical source-wallet, modeled follower, paper/shadow, Demo, and "
              "broker-executed series must remain separate. Verified, UTC-bounded "
              "native tapes are required for brushing, linked filters and comparisons. "
              "No financial point is interpolated or synthesized to populate a chart."),
    ])
