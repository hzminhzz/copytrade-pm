"""Grafana Phase 2 disposable staging Firefox verification at actual CSS viewports."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

BASE = f"https://{os.environ['GRAFANA_TAILNET_HOST']}:8444"
QA = Path("/tmp/copytrade-grafana-phase2-qa")
ROUTES = (
    ("copytrade-risk-command-v1", "ACCOUNT EVIDENCE COVERAGE", "UNAVAILABLE"),
    (
        "copytrade-pods-portfolio-v1",
        "PORTFOLIO STATE IS NOT A RUNNING ACCOUNT",
        "REGISTRY_READ_FAILED",
    ),
    ("copytrade-execution-v1", "EXECUTION", "NATIVE_EVIDENCE_UNAVAILABLE"),
    ("copytrade-health-incidents-v1", "HEALTH", "UNKNOWN"),
    ("copytrade-wallet-explorer-v1", "WALLET", "WALLET_INVENTORY_READ_FAILED"),
)
VIEWPORTS = ((1280, 800), (390, 844), (430, 932))


def run() -> None:
    QA.mkdir(parents=True, exist_ok=True, mode=0o700)
    for width, height in VIEWPORTS:
        options = Options()
        options.add_argument("-headless")
        browser = webdriver.Firefox(
            options=options,
            service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver"),
        )
        try:
            browser.set_page_load_timeout(60)
            browser.set_window_size(width, height)
            for uid, marker, row_marker in ROUTES:
                browser.get(f"{BASE}/d/{uid}")
                deadline = time.monotonic() + 45
                body = ""
                while time.monotonic() < deadline:
                    body = browser.find_element(By.TAG_NAME, "body").text
                    if (
                        marker in body
                        and row_marker in body
                        and ("CAPABILITY PROVENANCE" in body or uid == "copytrade-risk-command-v1")
                    ):
                        break
                    time.sleep(0.5)
                if row_marker not in body and uid != "copytrade-risk-command-v1":
                    panel = browser.find_elements(
                        By.XPATH, "//*[contains(text(), 'BOUNDED EVIDENCE')]"
                    )
                    if panel:
                        browser.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", panel[-1]
                        )
                    for _ in range(25):
                        body = browser.find_element(By.TAG_NAME, "body").text
                        if row_marker in body:
                            break
                        time.sleep(0.3)
                assert marker in body and row_marker in body, (uid, body[:1400])
                assert "Sign in to Grafana" not in body, (uid, body[:400])
                if uid != "copytrade-risk-command-v1":
                    assert "CAPABILITY PROVENANCE" in body, (uid, body[:1000])
                    assert "BOUNDED EVIDENCE" in body, (uid, body[:1000])
                bounds = browser.execute_script(
                    "return {viewport: window.innerWidth, scroll: document.documentElement.scrollWidth}"
                )
                assert bounds["scroll"] <= bounds["viewport"], (uid, width, bounds)
                path = QA / f"{uid}-{width}x{height}.png"
                browser.save_screenshot(str(path))
                print(f"PASS {uid} {width}x{height} overflow=NO screenshot={path}")
        finally:
            browser.quit()


if __name__ == "__main__":
    run()
