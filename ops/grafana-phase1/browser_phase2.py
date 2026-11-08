"""Grafana Phase 2 disposable staging browser verification at actual CSS viewports.

Runs on the local obscura CDP server; no Selenium or geckodriver is required.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from obscura_cdp import Browser  # noqa: E402

BASE = f"https://{os.environ['GRAFANA_TAILNET_HOST']}:8444"
QA = Path("/tmp/copytrade-grafana-phase2-qa")
ROUTES = (
    ("copytrade-risk-command-v1", "ACCOUNT EVIDENCE COVERAGE", "UNAVAILABLE"),
    (
        "copytrade-pods-portfolio-v1",
        "PORTFOLIO STATE IS NOT A RUNNING ACCOUNT",
        "REGISTRY_READ_FAILED",
    ),
    # The row marker tracks the projection's current execution state; it was
    # NATIVE_EVIDENCE_UNAVAILABLE before the publisher began reporting an empty
    # receipt set.
    ("copytrade-execution-v1", "EXECUTION", "NO_VERIFIED_RECEIPTS"),
    ("copytrade-health-incidents-v1", "HEALTH", "UNKNOWN"),
    ("copytrade-wallet-explorer-v1", "WALLET", "WALLET_INVENTORY_READ_FAILED"),
)
VIEWPORTS = ((1280, 800), (390, 844), (430, 932))


def run() -> None:
    QA.mkdir(parents=True, exist_ok=True, mode=0o700)
    for width, height in VIEWPORTS:
        with Browser() as browser:
            browser.viewport(width, height)
            for uid, marker, row_marker in ROUTES:
                browser.get(f"{BASE}/d/{uid}")
                deadline = time.monotonic() + 45
                body = ""
                while time.monotonic() < deadline:
                    body = browser.body()
                    if (
                        marker in body
                        and row_marker in body
                        and ("CAPABILITY PROVENANCE" in body or uid == "copytrade-risk-command-v1")
                    ):
                        break
                    time.sleep(0.5)
                if row_marker not in body and uid != "copytrade-risk-command-v1":
                    scrolled = browser.eval(
                        """(() => {
                          const panels = [...document.querySelectorAll('[data-viz-panel-key]')]
                            .filter((p) => p.innerText.includes('BOUNDED EVIDENCE'));
                          if (!panels.length) return false;
                          panels[panels.length - 1].scrollIntoView({block: 'center'});
                          return true;
                        })()"""
                    )
                    if scrolled:
                        for _ in range(25):
                            body = browser.body()
                            if row_marker in body:
                                break
                            time.sleep(0.3)
                assert marker in body and row_marker in body, (uid, body[:1400])
                assert "Sign in to Grafana" not in body, (uid, body[:400])
                if uid != "copytrade-risk-command-v1":
                    assert "CAPABILITY PROVENANCE" in body, (uid, body[:1000])
                    assert "BOUNDED EVIDENCE" in body, (uid, body[:1000])
                bounds = browser.eval(
                    "({viewport: window.innerWidth, scroll: document.documentElement.scrollWidth})"
                )
                assert bounds["scroll"] <= bounds["viewport"], (uid, width, bounds)
                path = QA / f"{uid}-{width}x{height}.png"
                browser.screenshot(path)
                print(f"PASS {uid} {width}x{height} overflow=NO screenshot={path}")


if __name__ == "__main__":
    run()
