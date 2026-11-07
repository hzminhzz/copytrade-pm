"""Bounded presentation helpers for read-only financial and operational evidence."""

from __future__ import annotations

from collections import Counter
from html import escape
from typing import Any


def clean(value: object) -> str:
    return escape(str(value if value is not None else "UNKNOWN"), quote=True)


def evidence_table(mo, sources: dict[str, dict[str, Any]]):
    return mo.ui.table(
        [
            {
                "Capability": clean(item.get("capability")),
                "Status": clean(item.get("status")),
                "Authority": clean(item.get("authority")),
                "Observed UTC": clean(item.get("source_observed_at")),
                "Captured UTC": clean(item.get("captured_at")),
                "Read UTC": clean(item.get("retrieved_at")),
                "Schema": clean(item.get("source_schema")),
                "Release SHA": clean(item.get("revision")),
                "Sequence": clean(item.get("journal_sequence")),
                "Error": clean(item.get("error_code")),
            }
            for item in sources.values()
        ],
        pagination=True,
        page_size=8,
        selection=None,
        show_download=False,
        show_search=False,
    )


def overview_cards(mo, report: dict[str, Any]):
    labels = {
        "equity": "Account equity",
        "headroom": "Guardian headroom",
        "daily_headroom": "Daily headroom",
        "trailing_headroom": "Trailing headroom",
    }
    cards = [
        mo.stat(
            clean(metric["value"]) if metric["value"] is not None else "UNKNOWN",
            label=f"{label} [{clean(metric['status'])}]",
            bordered=True,
        )
        for key, label in labels.items()
        for metric in [report["metrics"][key]]
    ]
    status = report["sources"]["status"]
    broker = report["sources"]["broker"]
    for source, key, label in (
        (status, "state", "Guardian state"),
        (broker, "certainty", "Broker certainty"),
    ):
        grade = source.get("status", "UNKNOWN")
        value = clean((source.get("data") or {}).get(key))
        if grade == "STALE":
            value += " (last observed)"
        elif grade != "VERIFIED":
            value = "UNKNOWN"
        cards.append(mo.stat(value, label=f"{label} [{clean(grade)}]", bordered=True))
    return mo.vstack(
        [
            mo.hstack(cards[:2], justify="start", wrap=True),
            mo.hstack(cards[2:4], justify="start", wrap=True),
            mo.hstack(cards[4:], justify="start", wrap=True),
            mo.md(
                "**Current exposure:** "
                + clean(
                    (
                        (report["sources"]["risk"].get("data") or {}).get("exposure")
                        if report["sources"]["risk"]["status"] == "VERIFIED"
                        else None
                    )
                )
                + " (UNKNOWN unless independently present in owner capture)."
            ),
            mo.md("**Pod health:** UNKNOWN unless independently reported by Guardian."),
            mo.md(
                f"Retrieved UTC: {clean(report['retrieved_at'])}. No synthetic financial snapshots."
            ),
        ]
    )


def registry_view(mo, outcome: dict[str, Any] | None):
    if outcome is None:
        return mo.md("Press **Query registry** to read canonical SQLite.")
    intro = mo.md(
        f"**Status:** {clean(outcome['status'])} · "
        f"**Inventory SHA:** {clean(outcome.get('inventory_sha256'))} · "
        f"**Source UTC:** {clean(outcome.get('source_observed_at'))} · "
        f"**Read UTC:** {clean(outcome['retrieved_at'])}\n\n"
        "Wallets are research metadata; private addresses and exclusion reasons are omitted."
    )
    data = outcome.get("data")
    if not isinstance(data, dict):
        return mo.vstack([intro, mo.md(f"Unavailable: {clean(outcome.get('error_code'))}")])
    rows = data.get("wallets", [])
    if not isinstance(rows, list):
        return mo.vstack([intro, mo.md("BLOCKED: invalid wallet response")])
    visible = [
        {
            "Alias": clean(item.get("alias")),
            "Aliases": ", ".join(
                clean(alias.get("alias")) for alias in item.get("aliases", [])[:8]
            ),
            "Identity": clean(item.get("identity_state")),
            "Cohorts": ", ".join(clean(group) for group in item.get("cohorts", [])[:12]),
            "Excluded": item.get("excluded"),
            "Subscribed": item.get("subscribed"),
            "Snapshot UTC": clean(item.get("monitoring_snapshot_known_at")),
            "Portfolio links (research)": ", ".join(
                f"{clean(p.get('portfolio_id'))}@{clean(p.get('version'))}"
                for p in item.get("portfolio_memberships", [])[:8]
            ),
        }
        for item in rows[:100]
        if isinstance(item, dict)
    ]
    return mo.vstack(
        [
            intro,
            mo.md(
                f"**Matches:** {clean(data.get('total'))} · "
                f"**Offset:** {clean(data.get('offset'))} · "
                f"**Page rows:** {len(visible)} · **As-of:** {clean(data.get('asof'))}"
            ),
            mo.ui.table(
                visible or [{"Result": "NO_MATCHING_WALLETS"}],
                selection=None,
                pagination=True,
                page_size=20,
                show_download=False,
                show_search=False,
            ),
        ]
    )


def health_view(mo, report: dict[str, Any]):
    records = [
        {
            "Component": key,
            "Evidence": report[key]["status"],
            "OS state": "NOT_APPLICABLE",
            "Observed UTC": clean(report[key].get("source_observed_at")),
            "Authority": clean(report[key].get("authority")),
        }
        for key in ("guardian", "broker", "observer")
    ]
    records.extend(
        {
            "Component": name,
            "Evidence": item["state"],
            "OS state": clean(item.get("os_active_state")),
            "Observed UTC": "OS query only",
            "Authority": "systemd (not finance)",
        }
        for name, item in report["services"].items()
    )
    records.extend(
        [
            {
                "Component": "watchdog",
                "Evidence": report["watchdog"]["status"],
                "OS state": "NOT_APPLICABLE",
                "Observed UTC": clean(report["watchdog"].get("source_observed_at")),
                "Authority": "Guardian-reported (not independent)",
            },
            {
                "Component": "executable market",
                "Evidence": report["market"]["status"],
                "OS state": "NOT_APPLICABLE",
                "Observed UTC": "UNKNOWN",
                "Authority": "NOT_ATTESTED",
            },
        ]
    )
    import altair as alt
    import polars as pl

    counts = Counter(record["Evidence"] for record in records)
    chart_data = pl.DataFrame(
        [{"evidence": status, "count": number} for status, number in sorted(counts.items())],
        schema={"evidence": pl.String, "count": pl.Int64},
    )
    chart = (
        alt.Chart(alt.InlineData(values=chart_data.to_dicts()))
        .mark_bar()
        .encode(
            x=alt.X("evidence:N", title="Observed evidence classification"),
            y=alt.Y("count:Q", title="Components"),
            tooltip=["evidence:N", "count:Q"],
        )
        .properties(height=180, title="Source-reported status (not financial authority)")
    )
    incidents = report.get("incidents") or []
    return mo.vstack(
        [
            mo.md("## Source and OS observations"),
            mo.ui.table(
                records,
                pagination=True,
                page_size=20,
                selection=None,
                show_download=False,
                show_search=False,
            ),
            chart,
            mo.md("## Existing Guardian incidents"),
            mo.md(
                "\n".join("- " + clean(item) for item in incidents)
                if incidents
                else "UNKNOWN — no independent incident feed"
            ),
            mo.md(
                "**Browser liveness, PIDs and public source receipts cannot establish "
                "healthy Guardian finance or broker certainty.**"
            ),
        ]
    )
