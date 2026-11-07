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
    refresh = mo.ui.refresh(
        options=["10s", "30s", "60s"], default_interval="10s", label="Health refresh"
    )
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

    from copytrade_pm.dashboard.notifications import dashboard_status
    from pathlib import Path
    import os

    notification_path = os.getenv("DASHBOARD_NOTIFICATION_STATE_FILE")
    delivery = dashboard_status(Path(notification_path) if notification_path else None)
    mo.vstack(
        [
            mo.md(
                f"**Independent delivery:** {delivery['status']} / "
                f"{delivery['external_delivery']}; source {delivery['source_status']}. "
                f"Records: {len(delivery['incidents'])}; "
                f"error: {delivery['error_code'] or 'NONE'}."
            ),
            health_view(mo, report),
        ]
    )


if __name__ == "__main__":
    app.run()
