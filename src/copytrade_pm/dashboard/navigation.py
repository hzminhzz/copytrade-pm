"""Conservative shared navigation with non-sensitive, bounded URL scope.

Only versioned research portfolio IDs and fixed UTC windows may travel in URLs.
No account IDs, wallet addresses, session tokens, or arbitrary time strings.
"""

from __future__ import annotations

from html import escape
import re
from typing import Mapping
from urllib.parse import urlencode

PORTFOLIO = re.compile(
    r"(?!0[xX])[A-Za-z][A-Za-z0-9_.-]{0,31}/"
    r"(?!0[xX])[A-Za-z][A-Za-z0-9_.-]{0,31}@"
    r"[A-Za-z0-9_.-]{1,20}\Z"
)
WINDOWS = ("24h", "7d", "30d", "90d")
ROUTES = (
    ("#/", "Overview"),
    ("#/execution", "Execution"),
    ("#/risk", "Risk"),
    ("#/health", "Health"),
    ("#/research", "Wallets"),
    ("#/portfolios", "Portfolios"),
    ("#/performance", "Performance"),
    ("#/lab", "Research Lab"),
)
# Old page URLs redirect to the single app; links use only hash routes.
LEGACY_PATHS = {"/" + route[2:] + "/": route for route, _ in ROUTES if route != "#/"}


def valid_scope(values: Mapping[str, object]) -> dict[str, str]:
    """Drop invalid/unknown parameters rather than repeating them in HTML or URLs."""
    result: dict[str, str] = {}
    window = values.get("utc")
    if isinstance(window, str) and window in WINDOWS:
        result["utc"] = window
    portfolio = values.get("portfolio")
    if isinstance(portfolio, str) and PORTFOLIO.fullmatch(portfolio):
        result["portfolio"] = portfolio
    return result


def navigation_html(scope: Mapping[str, object] | None = None) -> str:
    """HTML links are fixed to native routes; query values are strictly validated."""
    params = valid_scope(scope or {})
    suffix = "?" + urlencode(params) if params else ""
    links = "".join(
        f'<a href="{escape("/" + suffix + route, quote=True)}" '
        f'style="display:inline-block;padding:0.5rem 0.6rem;margin:0.2rem;'
        f"border:1px solid currentColor;border-radius:0.5rem;"
        f'text-decoration:none"'
        f">{escape(name)}</a>"
        for route, name in ROUTES
    )
    label = (
        f"Research scope {escape(params.get('portfolio', 'none'))}; "
        f"UTC window {escape(params.get('utc', 'not selected'))}. "
        "Filters are navigational context only and never change an account."
    )
    return (
        '<nav aria-label="Read-only dashboard navigation" '
        'style="max-width:100%;white-space:normal;overflow-wrap:anywhere">'
        + links
        + '</nav><p style="font-size:0.85rem">'
        + label
        + "</p>"
    )


def nav(mo, scope: Mapping[str, object] | None = None):
    return mo.Html(navigation_html(scope))
