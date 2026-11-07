"""One run-only Marimo application; eight lazy, embedded read-only views.

Only this notebook is mounted in ASGI. The separately defined view notebooks
are embedded within its kernel, never exposed as independent web servers.
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    from copytrade_pm.dashboard.navigation import nav
    from copytrade_pm.dashboard.pages.overview import app as overview_app
    from copytrade_pm.dashboard.pages.execution import app as execution_app
    from copytrade_pm.dashboard.pages.risk import app as risk_app
    from copytrade_pm.dashboard.pages.health import app as health_app
    from copytrade_pm.dashboard.pages.registry import app as registry_app
    from copytrade_pm.dashboard.pages.portfolios import app as portfolios_app
    from copytrade_pm.dashboard.pages.performance import app as performance_app
    from copytrade_pm.dashboard.pages.lab import app as lab_app

    return (
        mo,
        nav,
        overview_app,
        execution_app,
        risk_app,
        health_app,
        registry_app,
        portfolios_app,
        performance_app,
        lab_app,
    )


@app.cell
def _(
    mo,
    nav,
    overview_app,
    execution_app,
    risk_app,
    health_app,
    registry_app,
    portfolios_app,
    performance_app,
    lab_app,
):
    # All views are lazy: unselected routes do not access Guardian or SQLite.
    # Authenticated UI-element updates remain reactive inside embedded views.
    def embed_view(view, heading):
        async def render():
            return mo.vstack([mo.md(f"## {heading}"), (await view.embed()).output])

        return render

    mo.vstack(
        [
            mo.md("**Read-only risk oversight. No trading controls.**"),
            nav(mo, mo.query_params()),
            mo.routes(
                {
                    "#/": embed_view(overview_app, "Operations · Account risk"),
                    "#/execution": embed_view(execution_app, "Operations · Execution"),
                    "#/risk": embed_view(risk_app, "Operations · Risk"),
                    "#/health": embed_view(health_app, "Operations · System health"),
                    "#/research": embed_view(registry_app, "Research · Canonical wallets"),
                    "#/portfolios": embed_view(portfolios_app, "Research · Portfolios"),
                    "#/performance": embed_view(performance_app, "Research · Performance"),
                    "#/lab": embed_view(lab_app, "Research · Immutable reports"),
                    mo.routes.CATCH_ALL: embed_view(overview_app, "Operations · Account risk"),
                }
            ),
        ]
    )


if __name__ == "__main__":
    app.run()
