"""Read-only account-risk landing page; never a financial execution control."""
import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from copytrade_pm.dashboard.adapter import DashboardReader
    return mo, DashboardReader


@app.cell
def _(mo):
    mo.md(
        "# Operations · Account risk\n"
        "**Read-only. No trading controls.** "
        "[Overview](/) · [Execution](/execution) · [Risk](/risk) · "
        "[System health](/health) · [Wallets](/research) · "
        "[Portfolios](/portfolios) · [Performance](/performance) · [Research lab](/lab)\n\n"
        "Metrics are authoritative only to the degree indicated by their source status."
    )
    refresh = mo.ui.refresh(options=["5s", "10s", "30s"], default_interval="5s",
                            label="Overview refresh (UI polling only)")
    refresh
    return (refresh,)


@app.cell
def _(DashboardReader, refresh):
    _ = refresh.value
    report = DashboardReader().overview()
    return (report,)


@app.cell
def _(mo, report):
    from copytrade_pm.dashboard.views import overview_cards, evidence_table

    mo.vstack([
        mo.md("## Account and risk headroom"),
        overview_cards(mo, report),
        mo.md("## Guardian and broker provenance"),
        evidence_table(mo, report["sources"]),
        mo.md("## Incidents"),
        mo.md("\n".join("- " + reason for reason in report["incidents"])
              if report["incidents"] else "UNKNOWN — no independently verified incident feed"),
        mo.md(
            "**Portfolio identity:** UNKNOWN until verified installed/release/runtime evidence. "
            "Research selection is not deployment."
        ),
    ])


if __name__ == "__main__":
    app.run()
