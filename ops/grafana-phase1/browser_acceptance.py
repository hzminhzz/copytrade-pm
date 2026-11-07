"""Independent staging-only Firefox acceptance through Tailscale Serve owner ingress."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import statistics
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

HOST = os.environ["GRAFANA_TAILNET_HOST"]
BASE = f"https://{HOST}:8444"
QA = Path("/tmp/copytrade-grafana-phase1-qa")
VIEWPORTS = ((1280, 800), (390, 844), (430, 932))
ROUTES = (
    ("copytrade-risk-command-v1", "risk-command-copytrade", "LIVE SOURCE"),
    ("copytrade-synthetic-qa-v1", "synthetic-risk-command-evidence-qa", "SYNTHETIC FIXTURE"),
)


def run() -> None:
    QA.mkdir(parents=True, exist_ok=True, mode=0o700)
    timings = []
    for width, height in VIEWPORTS:
        options = Options()
        options.add_argument("-headless")
        options.enable_bidi = True
        browser = webdriver.Firefox(
            options=options,
            service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver"),
        )
        try:
            browser.set_page_load_timeout(55)
            browser.browsing_context.set_viewport(
                context=browser.current_window_handle,
                viewport={"width": width, "height": height},
                device_pixel_ratio=1,
            )
            actual = browser.execute_script("return [window.innerWidth,window.innerHeight]")
            assert actual == [width, height], (actual, width, height)
            for uid, slug, expected in ROUTES:
                started = time.perf_counter()
                browser.get(BASE + f"/d/{uid}/{slug}")
                deadline = time.monotonic() + 38
                body = ""
                while time.monotonic() < deadline:
                    body = browser.find_element(By.TAG_NAME, "body").text
                    expected_state = (
                        "SYNTHETIC_STALE" in body and "VERIFIED" in body
                        if expected == "SYNTHETIC FIXTURE"
                        else "PROTECTED_CAPTURE_UNAVAILABLE" in body and "INCOMPLETE" in body
                    )
                    if "Account risk" in body and "Guardian" in body and expected_state:
                        break
                    time.sleep(0.6)
                assert "Account risk" in body and "Guardian" in body, body[:1200]
                elapsed_ms = (time.perf_counter() - started) * 1000
                timings.append(elapsed_ms)
                assert "Sign in to Grafana" not in body, body[:250]
                if expected == "SYNTHETIC FIXTURE":
                    assert "SYNTHETIC_STALE" in body and "VERIFIED" in body, body[:1800]
                    assert "GUARDIAN · REPORTED STATE\nHALTED" in body, body[:1000]
                    assert "BROKER · RECONCILIATION\nRECONCILED" in body, body[:1000]
                else:
                    assert "PROTECTED_CAPTURE_UNAVAILABLE" in body and "INCOMPLETE" in body, body[
                        :1800
                    ]
                    assert "GUARDIAN · REPORTED STATE\nUNAVAILABLE" in body, body[:1000]
                    assert "BROKER · RECONCILIATION\nUNAVAILABLE" in body, body[:1000]
                browser.save_screenshot(str(QA / f"{uid}-{width}x{height}.png"))
                bounds = browser.execute_script(
                    "return {viewport:window.innerWidth,scroll:document.documentElement.scrollWidth}"
                )
                assert bounds["scroll"] <= bounds["viewport"], bounds
                print(
                    f"{uid} {width}x{height} no_overflow=YES "
                    f"body_unavailable={body.count('UNAVAILABLE')} "
                    f"render_ms={elapsed_ms:.0f}"
                )
                if uid == "copytrade-synthetic-qa-v1" and width == 1280:
                    timeline = browser.find_element(
                        By.XPATH, "//*[contains(text(), 'SYNTHETIC evidence state timeline')]"
                    )
                    browser.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", timeline
                    )
                    time.sleep(1.5)
                    timeline_panel = timeline.find_element(By.XPATH, "./../../../..").text
                    assert "Data does not have a time field" not in timeline_panel
                    assert "No data" not in timeline_panel
                    browser.save_screenshot(str(QA / "synthetic-timeline-1280x800.png"))
        finally:
            browser.quit()
    if timings:
        ordered = sorted(timings)
        p95 = ordered[max(0, int(0.95 * len(ordered) + 0.95) - 1)]
        print(
            f"actual_render_n={len(timings)} p50_ms={statistics.median(timings):.0f} "
            f"p95_nearest_rank_ms={p95:.0f}"
        )


if __name__ == "__main__":
    run()
