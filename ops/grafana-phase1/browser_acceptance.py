"""Independent staging-only browser acceptance through Tailscale Serve owner ingress.

Runs on the local obscura CDP server; no Selenium or geckodriver is required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from obscura_cdp import Browser  # noqa: E402

HOST = os.environ["GRAFANA_TAILNET_HOST"]
BASE = f"https://{HOST}:8444"
QA = Path("/tmp/copytrade-grafana-phase1-qa")
VIEWPORTS = ((1280, 800), (390, 844), (430, 932))
ROUTES = (
    ("copytrade-risk-command-v1", "risk-command-copytrade", "LIVE SOURCE"),
    ("copytrade-synthetic-qa-v1", "synthetic-risk-command-evidence-qa", "SYNTHETIC FIXTURE"),
)


def assert_diagnostic_after_scroll(browser: Browser, expected_error: str) -> None:
    """Exercise the actual mobile table scroll, not a weaker status surrogate."""
    result = browser.eval(
        """(() => {
          let moved = 0;
          let total = 0;
          let valueHeader = false;
          for (const panel of document.querySelectorAll('[data-viz-panel-key]')) {
            const title = panel.querySelector('h2')?.textContent || '';
            if (!['Guardian and broker certainty', 'Account risk — exact numbers or unavailable']
                .includes(title)) continue;
            const grid = [...panel.querySelectorAll('[role="grid"]')]
              .find(element => element.getAttribute('aria-hidden') !== 'true');
            if (!grid) continue;
            total++;
            if ([...grid.querySelectorAll('[role="columnheader"]')]
                .some(cell => cell.textContent?.trim() === 'Value')) valueHeader = true;
            if (grid.scrollWidth > grid.clientWidth + 10) {
              grid.scrollLeft = grid.scrollWidth;
              if (grid.scrollLeft > 0) moved++;
            }
          }
          return {total, moved, valueHeader};
        })()"""
    )
    assert result is not None and result["moved"] >= 1 and result["valueHeader"], (
        "EVIDENCE_TABLE_NOT_HORIZONTALLY_SCROLLABLE",
        result,
    )
    # A page-wide text assertion can pass from an unrelated panel. Restrict
    # the error check to the two source tables whose columns we just scrolled.
    expression = """(() => {
      const titles = ['Guardian and broker certainty',
                      'Account risk — exact numbers or unavailable'];
      return [...document.querySelectorAll('[data-viz-panel-key]')]
        .some(panel => titles.includes(panel.querySelector('h2')?.textContent || '') &&
                       panel.innerText.includes(ERROR_TOKEN));
    })()""".replace("ERROR_TOKEN", json.dumps(expected_error))
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if browser.eval(expression):
            return
        time.sleep(0.15)
    raise AssertionError(f"EVIDENCE_DIAGNOSTIC_NOT_RENDERED_AFTER_SCROLL: {expected_error}")


def run() -> None:
    QA.mkdir(parents=True, exist_ok=True, mode=0o700)
    timings = []
    for width, height in VIEWPORTS:
        with Browser() as browser:
            browser.viewport(width, height)
            for uid, slug, expected in ROUTES:
                started = time.perf_counter()
                browser.get(BASE + f"/d/{uid}/{slug}")
                deadline = time.monotonic() + 38
                body = ""
                # Verify the visible summary first; below 1024px, also scroll
                # the virtualized table to verify its diagnostic rather than
                # silently dropping the original acceptance assertion.
                wide = width >= 1024
                while time.monotonic() < deadline:
                    body = browser.body()
                    if expected == "SYNTHETIC FIXTURE":
                        expected_state = "HALTED" in body and "RECONCILED" in body
                        if wide:
                            expected_state = expected_state and "SYNTHETIC_STALE" in body
                    else:
                        expected_state = "INCOMPLETE" in body and "UNAVAILABLE" in body
                        if wide:
                            expected_state = expected_state and (
                                "PROTECTED_CAPTURE_UNAVAILABLE" in body
                            )
                    if "Account risk" in body and "Guardian" in body and expected_state:
                        break
                    time.sleep(0.6)
                assert "Account risk" in body and "Guardian" in body, body[:1200]
                elapsed_ms = (time.perf_counter() - started) * 1000
                timings.append(elapsed_ms)
                assert "Sign in to Grafana" not in body, body[:250]
                if expected == "SYNTHETIC FIXTURE":
                    assert "HALTED" in body and "VERIFIED" in body, body[:1800]
                    assert "GUARDIAN · REPORTED STATE\nHALTED" in body, body[:1000]
                    assert "BROKER · RECONCILIATION\nRECONCILED" in body, body[:1000]
                    if wide:
                        assert "SYNTHETIC_STALE" in body, body[:1800]
                else:
                    assert "INCOMPLETE" in body and "UNAVAILABLE" in body, body[:1800]
                    assert "GUARDIAN · REPORTED STATE\nUNAVAILABLE" in body, body[:1000]
                    assert "BROKER · RECONCILIATION\nUNAVAILABLE" in body, body[:1000]
                    if wide:
                        assert "PROTECTED_CAPTURE_UNAVAILABLE" in body, body[:1800]
                browser.screenshot(QA / f"{uid}-{width}x{height}.png")
                if not wide:
                    expected_error = (
                        "SYNTHETIC_STALE"
                        if expected == "SYNTHETIC FIXTURE"
                        else "PROTECTED_CAPTURE_UNAVAILABLE"
                    )
                    assert_diagnostic_after_scroll(browser, expected_error)
                    browser.screenshot(QA / f"{uid}-{width}x{height}-diagnostic.png")
                bounds = browser.eval(
                    "({viewport: window.innerWidth, scroll: document.documentElement.scrollWidth})"
                )
                assert bounds["scroll"] <= bounds["viewport"], bounds
                print(
                    f"{uid} {width}x{height} no_overflow=YES "
                    f"body_unavailable={body.count('UNAVAILABLE')} "
                    f"render_ms={elapsed_ms:.0f}"
                )
                if uid == "copytrade-synthetic-qa-v1" and width == 1280:
                    timeline_panel = browser.eval(
                        """(() => {
                          const label = [...document.querySelectorAll('*')].find(
                            (e) => e.children.length === 0 &&
                                   e.textContent.includes('SYNTHETIC evidence state timeline'));
                          if (!label) return null;
                          label.scrollIntoView({block: 'center'});
                          const panel = label.closest('[data-viz-panel-key]');
                          return panel ? panel.innerText : null;
                        })()"""
                    )
                    assert timeline_panel is not None, "TIMELINE_PANEL_MISSING"
                    time.sleep(1.5)
                    timeline_panel = browser.eval(
                        """(() => {
                          const label = [...document.querySelectorAll('*')].find(
                            (e) => e.children.length === 0 &&
                                   e.textContent.includes('SYNTHETIC evidence state timeline'));
                          const panel = label && label.closest('[data-viz-panel-key]');
                          return panel ? panel.innerText : null;
                        })()"""
                    )
                    assert timeline_panel is not None, "TIMELINE_PANEL_MISSING"
                    assert "Data does not have a time field" not in timeline_panel
                    assert "No data" not in timeline_panel
                    browser.screenshot(QA / "synthetic-timeline-1280x800.png")
    if timings:
        ordered = sorted(timings)
        p95 = ordered[max(0, int(0.95 * len(ordered) + 0.95) - 1)]
        print(
            f"actual_render_n={len(timings)} p50_ms={statistics.median(timings):.0f} "
            f"p95_nearest_rank_ms={p95:.0f}"
        )


if __name__ == "__main__":
    run()
