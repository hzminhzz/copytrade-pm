"""Private, non-authoritative trading oversight. No finance, registry or broker writers."""

__all__ = ["DashboardReader"]


def __getattr__(name: str):
    if name == "DashboardReader":
        from .adapter import DashboardReader

        return DashboardReader
    raise AttributeError(name)
