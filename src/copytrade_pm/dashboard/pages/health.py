"""Independent evidence of Guardian, watchdog, sources and observer health."""
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
        "# Operations · System health\n"
        "[Overview](/) · [System health](/health) · [Research / Wallets](/research)\n\n"
        "A healthy browser or active PID does **not** establish healthy Guardian finance."
    )
    refresh = mo.ui.refresh(options=["10s", "30s", "60s"], default_interval="10s",
                            label="Health refresh")
    refresh
    return (refresh,)


@app.cell
def _(DashboardReader, refresh):
    _ = refresh.value
    report = DashboardReader().health()
    return (report,)


@app.cell
def _(mo, report):
    from copytrade_pm.dashboard.views import health_view

    health_view(mo, report)


if __name__ == "__main__":
    app.run()
