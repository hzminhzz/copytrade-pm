"""Bounded canonical SQLite portfolio explorer."""

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
    asof = mo.ui.text(label="Optional exact UTC as-of", value="", max_length=45)
    name_filter = mo.ui.text(label="Portfolio ID contains", value="", max_length=96)
    page = mo.ui.number(start=1, stop=101, value=1, step=1, label="Page (25 rows)")
    query = mo.ui.run_button(label="Read canonical portfolios")
    mo.vstack(
        [mo.hstack([asof, name_filter], justify="start"), mo.hstack([page, query], justify="start")]
    )
    return asof, name_filter, page, query


@app.cell
def _(DashboardReader, asof, name_filter, page, query):
    outcome = (
        DashboardReader().portfolio_explorer(
            asof=asof.value.strip() or None,
            query=name_filter.value.strip() or None,
            limit=25,
            offset=(int(page.value) - 1) * 25,
        )
        if query.value
        else None
    )
    return (outcome,)


@app.cell
def _(mo, outcome):
    from copytrade_pm.dashboard.phase2_views import portfolio_view

    body = (
        portfolio_view(mo, outcome)
        if outcome
        else mo.md(
            "Use **Read canonical portfolios**. No selection or registry records are changed."
        )
    )
    body


if __name__ == "__main__":
    app.run()
