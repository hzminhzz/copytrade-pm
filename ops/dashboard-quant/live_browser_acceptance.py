"""Real Firefox acceptance against the installed private Tailscale HTTPS service.

Reads the viewer credential from its private local env file; never prints it.
No writes to the canonical registry or protected finance.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import statistics
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

CONFIG = Path("/home/quant/.config/copytrade-dashboard/private.env")
ARTIFACTS = Path("/home/quant/.local/share/copytrade-dashboard/qa")


def private_base() -> str:
    for line in CONFIG.read_text().splitlines():
        if line.startswith("DASHBOARD_ALLOWED_HOSTS="):
            hostname = line.partition("=")[2].split(",", 1)[0]
            if hostname.endswith(".ts.net"):
                return "https://" + hostname + ":8443"
    raise RuntimeError("PRIVATE_TAILNET_HOST_MISSING")


BASE = private_base()
VIEW_ROUTES = (
    ("#/", "Operations · Account risk", "Account and risk headroom"),
    ("#/execution", "Operations · Execution", "Execution"),
    ("#/risk", "Operations · Risk", "Guardian"),
    ("#/health", "Operations · System health", "Independent delivery"),
    ("#/research", "Research · Canonical wallets", "Query registry"),
    ("#/portfolios", "Research · Portfolios", "Read canonical portfolios"),
    ("#/performance", "Research · Performance", "Performance"),
    ("#/lab", "Research · Immutable reports", "Query verified research reports"),
)


def private_secret() -> str:
    for line in CONFIG.read_text().splitlines():
        if line.startswith("DASHBOARD_ACCESS_SECRET="):
            return line.split("=", 1)[1]
    raise RuntimeError("PRIVATE_DASHBOARD_SECRET_MISSING")


def await_body(driver, title: str, marker: str, deadline: float = 30.0) -> str:
    until = time.monotonic() + deadline
    body = ""
    while time.monotonic() < until:
        body = driver.find_element(By.TAG_NAME, "body").text
        if title in body and marker in body:
            return body
        time.sleep(0.3)
    raise AssertionError(f"ROUTE_NOT_RENDERED {title}: {body[:400]}")


def main() -> None:
    ARTIFACTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    times: list[float] = []
    count = 0
    for width, height in ((390, 844), (430, 932), (1280, 800)):
        opts = Options()
        opts.add_argument("-headless")
        opts.enable_bidi = True
        driver = webdriver.Firefox(
            options=opts,
            service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver"),
        )
        try:
            driver.set_page_load_timeout(40)
            driver.browsing_context.set_viewport(
                context=driver.current_window_handle,
                viewport={"width": width, "height": height},
                device_pixel_ratio=1,
            )
            assert driver.execute_script("return [window.innerWidth, window.innerHeight]") == [
                width,
                height,
            ]
            # Start at the root, as a first-time Omarchy browser would.
            # It must show the private login form, not ACCESS_DENIED.
            driver.get(BASE + "/")
            assert driver.current_url == BASE + "/login", driver.current_url
            assert "Private risk viewer" in driver.page_source
            assert "ACCESS_DENIED" not in driver.page_source
            driver.find_element(By.NAME, "secret").send_keys(private_secret())
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            await_body(driver, "Operations · Account risk", "Account and risk headroom")
            for fragment, title, marker in VIEW_ROUTES:
                start = time.perf_counter()
                driver.get(BASE + "/" + fragment)
                body = await_body(driver, title, marker)
                times.append((time.perf_counter() - start) * 1000)
                assert "Read-only" in body, (width, fragment)
                assert driver.execute_script("return window.innerWidth") == width
                assert driver.execute_script("return window.innerHeight") == height
                assert (
                    driver.execute_script("return document.documentElement.scrollWidth")
                    <= width + 5
                ), (width, fragment)
                assert "0x" not in driver.current_url
                file = (
                    ARTIFACTS / f"live-{width}x{height}-{fragment.lstrip('#/') or 'overview'}.png"
                )
                assert driver.save_screenshot(str(file))
                count += 1
            if width == 1280:
                driver.get(BASE + "/#/research")
                await_body(driver, "Research · Canonical wallets", "Query registry")
                button = driver.execute_script(
                    """
                    function find(root) {
                      for (const el of root.querySelectorAll('*')) {
                        if (el.tagName === 'BUTTON' &&
                            (el.textContent || '').trim() === 'Query registry') return el;
                        if (el.shadowRoot) {
                          const inside = find(el.shadowRoot);
                          if (inside) return inside;
                        }
                      }
                      return null;
                    }
                    return find(document);
                    """
                )
                assert button is not None, "REGISTRY_QUERY_BUTTON_MISSING"
                button.click()
                until = time.monotonic() + 25
                while time.monotonic() < until:
                    text = driver.find_element(By.TAG_NAME, "body").text
                    if "Inventory SHA:" in text or "Unavailable:" in text:
                        break
                    time.sleep(0.3)
                assert "Inventory SHA:" in text or "Unavailable:" in text
                print(
                    "REGISTRY_LIVE_QUERY_STATUS",
                    "inventory" if "Inventory SHA:" in text else "unavailable",
                )
        finally:
            driver.quit()

    p50 = statistics.median(times)
    p95 = sorted(times)[int(0.95 * (len(times) - 1))]
    result = {
        "schema": "quant_dashboard_live_browser_v1",
        "url": BASE,
        "viewports": ["390x844", "430x932", "1280x800"],
        "views_checked": count,
        "screenshot_count": count,
        "route_render_p50_ms": round(p50, 1),
        "route_render_p95_ms": round(p95, 1),
        "production_release": "29d006131662-aa94784c356f",
        "credential_printed": False,
    }
    (ARTIFACTS / "live-browser-receipt.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
