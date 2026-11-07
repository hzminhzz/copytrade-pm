"""Real staging-only Grafana browser acceptance, with no financial data access."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

BASE = "http://127.0.0.1:13070"
QA = Path("/tmp/copytrade-grafana-phase1-qa")
VIEWPORTS = ((1280, 800), (390, 844), (430, 932))


def run() -> None:
    secret = os.environ["GRAFANA_ADMIN_PASSWORD"]
    QA.mkdir(parents=True, exist_ok=True, mode=0o700)
    for width, height in VIEWPORTS:
        options = Options()
        options.add_argument("-headless")
        options.enable_bidi = True
        browser = webdriver.Firefox(
            options=options,
            service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver"),
        )
        try:
            browser.set_page_load_timeout(50)
            browser.browsing_context.set_viewport(
                context=browser.current_window_handle,
                viewport={"width": width, "height": height},
                device_pixel_ratio=1,
            )
            actual = browser.execute_script("return [window.innerWidth,window.innerHeight]")
            assert actual == [width, height], (actual, width, height)
            browser.get(BASE + "/login")
            WebDriverWait(browser, 30).until(EC.presence_of_element_located((By.NAME, "user"))).send_keys("admin")
            WebDriverWait(browser, 20).until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(secret)
            WebDriverWait(browser, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))).click()
            browser.get(BASE + "/d/copytrade-risk-command-v1/risk-command-copytrade")
            deadline = time.monotonic() + 35
            body = ""
            while time.monotonic() < deadline:
                body = browser.find_element(By.TAG_NAME, "body").text
                if "Account risk" in body and "Guardian and broker" in body:
                    break
                time.sleep(0.5)
            assert "Account risk" in body and "Guardian and broker" in body, body[:800]
            browser.save_screenshot(str(QA / f"risk-{width}x{height}.png"))
            bounds = browser.execute_script(
                "return {viewport:window.innerWidth,scroll:document.documentElement.scrollWidth}"
            )
            print(f"{width}x{height} screenshot={QA / f'risk-{width}x{height}.png'} "
                  f"bounds={bounds} unavailable={body.count('UNAVAILABLE')}")
        finally:
            browser.quit()


if __name__ == "__main__":
    run()
