"""Presentation of available actual financial history, never synthetic accounting."""
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
    refresh = mo.ui.refresh(options=["30s", "60s"], default_interval="30s",
                            label="Current risk display refresh (not historical tape)")
    refresh
    return (refresh,)


@app.cell
def _(DashboardReader, refresh):
    _ = refresh.value
    reader = DashboardReader()
    status = reader.risk_status()
    history = reader.performance_history(risk_report=status)
    return status, history


@app.cell
def _(mo, status, history):
    from copytrade_pm.dashboard.phase2_views import performance_view
    performance_view(mo, status, history)


if __name__ == "__main__":
    app.run()
