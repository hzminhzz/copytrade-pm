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
    mo.md("# Research · Portfolio Explorer\n[Overview](/) · [Wallets](/research) · "
          "[Portfolios](/portfolios) · [Performance](/performance) · [Research lab](/lab)")
    asof = mo.ui.text(label="Optional exact UTC as-of", value="", max_length=45)
    query = mo.ui.run_button(label="Read canonical portfolios")
    mo.hstack([asof, query], justify="start")
    return asof, query


@app.cell
def _(DashboardReader, asof, query):
    outcome = DashboardReader().portfolio_explorer(asof=asof.value.strip() or None) if query.value else None
    return (outcome,)


@app.cell
def _(mo, outcome):
    from copytrade_pm.dashboard.phase2_views import portfolio_view
    portfolio_view(mo, outcome) if outcome else mo.md(
        "Use **Read canonical portfolios**. No selection or registry records are changed."
    )


if __name__ == "__main__":
    app.run()
