"""Read-only SHA-verified immutable research report catalog browser."""
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
    job_id = mo.ui.text(label="Exact job ID (optional)", value="", max_length=96)
    page = mo.ui.number(start=1, stop=201, value=1, step=1, label="Page (50 rows)")
    query = mo.ui.run_button(label="Query verified research reports")
    mo.hstack([job_id, page, query], justify="start")
    return job_id, page, query


@app.cell
def _(DashboardReader, job_id, page, query):
    if query.value:
        reader = DashboardReader()
        outcome = reader.research_reports(
            run_id=job_id.value.strip() or None, limit=50,
            offset=(int(page.value) - 1) * 50,
        )
        rules = reader.contract_rules()
    else:
        outcome = None
        rules = None
    return outcome, rules


@app.cell
def _(mo, outcome, rules):
    from copytrade_pm.dashboard.phase2_views import research_view
    body = research_view(mo, outcome, rules) if outcome else mo.md(
        "Use **Query verified research reports**. No research job is executed."
    )
    body


if __name__ == "__main__":
    app.run()
