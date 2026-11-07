"""Canonical private SQLite wallet browser, bounded and address-redacted."""
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
        "# Research · Canonical wallet registry\n"
        "[Overview](/) · [Execution](/execution) · [Risk](/risk) · "
        "[Health](/health) · [Wallet registry](/research) · "
        "[Portfolios](/portfolios) · [Performance](/performance) · [Research lab](/lab)\n\n"
        "SQLite identities are research metadata, not deployed portfolios."
    )
    query = mo.ui.text(label="Alias contains (max 96 characters)", value="", max_length=96)
    cohort = mo.ui.text(label="Cohort (exact)", value="", max_length=96)
    excluded = mo.ui.dropdown({"All": None, "Excluded": True, "Not excluded": False},
                              label="Exclusions", value="All")
    page = mo.ui.number(start=1, stop=101, value=1, step=1, label="Page (50 rows)")
    run = mo.ui.run_button(label="Query registry")
    mo.vstack([mo.hstack([query, cohort], justify="start"),
               mo.hstack([excluded, page, run], justify="start")])
    return query, cohort, excluded, page, run


@app.cell
def _(DashboardReader, query, cohort, excluded, page, run):
    # Demand-triggered only: editing a field does not run a database query.
    if run.value:
        outcome = DashboardReader().wallets(
            query=query.value.strip() or None, cohort=cohort.value.strip() or None,
            excluded=excluded.value, limit=50, offset=(int(page.value) - 1) * 50,
        )
    else:
        outcome = None
    return (outcome,)


@app.cell
def _(mo, outcome):
    from copytrade_pm.dashboard.views import registry_view

    from copytrade_pm.dashboard.navigation import nav
    mo.vstack([mo.md("# Research · Canonical wallet registry"),
               nav(mo, mo.query_params()), registry_view(mo, outcome)])


if __name__ == "__main__":
    app.run()
