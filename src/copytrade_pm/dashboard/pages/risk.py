"""Guardian authoritative risk display; no broker or HALT command."""
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
    mo.md("# Operations · Risk\n[Overview](/) · [Execution](/execution) · "
          "[Risk](/risk) · [Health](/health) · [Portfolios](/portfolios) · "
          "[Performance](/performance) · [Research lab](/lab)")
    refresh = mo.ui.refresh(options=["10s", "30s", "60s"], default_interval="10s",
                            label="Risk refresh (read-only)")
    refresh
    return (refresh,)


@app.cell
def _(DashboardReader, refresh):
    _ = refresh.value
    report = DashboardReader().risk_status()
    return (report,)


@app.cell
def _(mo, report):
    from copytrade_pm.dashboard.phase2_views import risk_view
    risk_view(mo, report)


if __name__ == "__main__":
    app.run()
