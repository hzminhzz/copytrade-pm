"""Opt-in real Firefox + Marimo viewport smoke (run with --with selenium).

Spawns a disposable localhost run-only ASGI process. Never connects to a
protected Guardian, registry writer, broker, or production service.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

pytest.importorskip("selenium")
webdriver = importlib.import_module("selenium.webdriver")
By = importlib.import_module("selenium.webdriver.common.by").By
Keys = importlib.import_module("selenium.webdriver.common.keys").Keys
Options = importlib.import_module("selenium.webdriver.firefox.options").Options
Service = importlib.import_module("selenium.webdriver.firefox.service").Service

KEY = "x" * 64
VIEW_ROUTES = [
    ("#/", "Operations · Account risk", "Account and risk headroom"),
    ("#/execution", "Operations · Execution", "Execution"),
    ("#/risk", "Operations · Risk", "Guardian"),
    ("#/health", "Operations · System health", "Independent delivery"),
    ("#/research", "Research · Canonical wallets", "Query registry"),
    ("#/portfolios", "Research · Portfolios", "Read canonical portfolios"),
    ("#/performance", "Research · Performance", "Performance"),
    ("#/lab", "Research · Immutable reports", "Query verified research reports"),
]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def local_server():
    port = _port()
    url = f"http://localhost:{port}"
    env = {
        **os.environ,
        "DASHBOARD_ACCESS_SECRET": KEY,
        "DASHBOARD_ALLOWED_HOSTS": "localhost",
        "DASHBOARD_ALLOWED_ORIGINS": url,
        "DASHBOARD_GUARDIAN_CAPTURE_ROOT": "/nonexistent-dashboard-guardian-capture",
        "DASHBOARD_NOTIFICATION_STATE_FILE": "",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "copytrade_pm.dashboard.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "--no-access-log",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(70):
            if proc.poll() is not None:
                raise AssertionError("Disposable Marimo ASGI failed to start")
            try:
                with urlopen(url + "/login", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise AssertionError("Disposable Marimo ASGI timeout")
        yield url
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.fixture
def firefox():
    options = Options()
    options.add_argument("-headless")
    options.enable_bidi = True
    driver = webdriver.Firefox(
        options=options, service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver")
    )
    try:
        driver.set_page_load_timeout(30)
        yield driver
    finally:
        driver.quit()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932), (1280, 800)])
def test_private_mobile_routes_and_navigation(local_server, firefox, width, height):
    # Outer-window resizing is clamped by Firefox and includes browser chrome.
    # BiDi sets the actual CSS viewport, including phone widths below 500 px.
    firefox.browsing_context.set_viewport(
        context=firefox.current_window_handle,
        viewport={"width": width, "height": height},
        device_pixel_ratio=1,
    )
    assert firefox.execute_script("return [window.innerWidth, window.innerHeight]") == [
        width,
        height,
    ]
    firefox.get(local_server + "/login")
    assert "Private risk viewer" in firefox.page_source
    firefox.find_element(By.NAME, "secret").send_keys(KEY)
    firefox.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    for _ in range(80):
        if firefox.current_url.rstrip("/") == local_server:
            break
        time.sleep(0.25)
    assert firefox.current_url.rstrip("/") == local_server, firefox.page_source[:500]
    for _ in range(60):
        if "Account risk" in firefox.find_element(By.TAG_NAME, "body").text:
            break
        time.sleep(0.25)
    body_text = firefox.find_element(By.TAG_NAME, "body").text
    assert "Account risk" in body_text, (firefox.current_url, body_text[:2000])
    assert "Read-only" in body_text
    assert "UNKNOWN" in body_text or "UNAVAILABLE" in body_text
    assert firefox.find_elements(
        By.CSS_SELECTOR, "nav[aria-label='Read-only dashboard navigation']"
    )
    doc_width = firefox.execute_script("return document.documentElement.scrollWidth;")
    inner_width = firefox.execute_script("return window.innerWidth;")
    # Critical content must not create top-level horizontal scrolling.
    assert doc_width <= inner_width + 5, (doc_width, inner_width, width)
    assert "0x" not in firefox.current_url
    target = local_server + "/health?utc=7d&token=SECRET-LEAK&portfolio=gemini.phase5%2FP1%403"
    firefox.get(target)
    for _ in range(50):
        if "Independent delivery" in firefox.find_element(By.TAG_NAME, "body").text:
            break
        time.sleep(0.25)
    assert "Independent delivery" in firefox.find_element(By.TAG_NAME, "body").text
    navs = firefox.find_elements(
        By.CSS_SELECTOR, "nav[aria-label='Read-only dashboard navigation']"
    )
    assert navs
    assert "SECRET-LEAK" not in navs[0].get_attribute("outerHTML")
    assert "SECRET-LEAK" not in firefox.current_url
    assert "portfolio=gemini.phase5" in navs[0].get_attribute("outerHTML")
    artifact_dir = os.getenv("DASHBOARD_BROWSER_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        assert firefox.save_screenshot(str(Path(artifact_dir) / f"phase3-{width}x{height}.png"))

    # Exercise every view at the exact phone/desktop viewport, with safe scope.
    for fragment, title, marker in VIEW_ROUTES:
        firefox.get(local_server + "/?utc=7d&portfolio=gemini.phase5%2FP1%403" + fragment)
        for _ in range(80):
            body = firefox.find_element(By.TAG_NAME, "body").text
            if title in body and marker in body:
                break
            time.sleep(0.25)
        assert title in body and marker in body, (width, fragment, body[:1800])
        assert firefox.execute_script("return [window.innerWidth, window.innerHeight]") == [
            width,
            height,
        ]
        assert firefox.execute_script("return document.documentElement.scrollWidth") <= width + 5, (
            width,
            fragment,
        )
        if artifact_dir:
            route_name = fragment.removeprefix("#/") or "overview"
            assert firefox.save_screenshot(
                str(Path(artifact_dir) / f"final-{width}x{height}-{route_name}.png")
            )


@pytest.mark.parametrize(
    "fragment,title,marker",
    VIEW_ROUTES,
)
def test_single_app_eight_lazy_views(local_server, firefox, fragment, title, marker):
    firefox.get(local_server + "/login")
    firefox.find_element(By.NAME, "secret").send_keys(KEY)
    firefox.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    firefox.get(local_server + "/" + fragment)
    for _ in range(80):
        body = firefox.find_element(By.TAG_NAME, "body").text
        if title in body and marker in body:
            break
        time.sleep(0.25)
    body = firefox.find_element(By.TAG_NAME, "body").text
    assert title in body, (fragment, body[:1800])
    assert marker in body, (fragment, body[:1800])
    assert (
        len(
            firefox.find_elements(
                By.CSS_SELECTOR, "nav[aria-label='Read-only dashboard navigation']"
            )
        )
        == 1
    )


def test_twenty_fresh_document_sessions_do_not_mix_views(local_server, firefox):
    firefox.get(local_server + "/login")
    firefox.find_element(By.NAME, "secret").send_keys(KEY)
    firefox.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    for iteration in range(20):
        fragment, expected, unexpected = (
            ("#/health", "Independent delivery", "Account and risk headroom")
            if iteration % 2
            else ("#/", "Account and risk headroom", "Independent delivery:")
        )
        # Each get creates a new app document and Marimo frontend session,
        # while the same server process remains alive for all 20 iterations.
        firefox.get(local_server + "/" + fragment)
        for _ in range(60):
            body = firefox.find_element(By.TAG_NAME, "body").text
            if expected in body:
                break
            time.sleep(0.25)
        body = firefox.find_element(By.TAG_NAME, "body").text
        assert expected in body, (iteration, fragment, body[:1400])
        assert unexpected not in body, (iteration, fragment, body[:1400])


def test_same_document_hash_navigation_keyboard_and_reload(local_server, firefox):
    firefox.get(local_server + "/login")
    firefox.find_element(By.NAME, "secret").send_keys(KEY)
    firefox.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    for fragment, title, marker in (
        ("#/health", "Operations · System health", "Independent delivery"),
        ("#/research", "Research · Canonical wallets", "Query registry"),
        ("#/", "Operations · Account risk", "Account and risk headroom"),
    ):
        # Click the actual authenticated nav link without a page reload.
        selector = "nav[aria-label='Read-only dashboard navigation'] a[href$='" + fragment + "']"
        for _ in range(60):
            links = firefox.find_elements(By.CSS_SELECTOR, selector)
            if links:
                break
            time.sleep(0.25)
        assert links, (fragment, firefox.find_element(By.TAG_NAME, "body").text[:1200])
        link = links[0]
        assert link.get_attribute("tabindex") != "-1"
        if fragment == "#/health":
            link.send_keys(Keys.ENTER)
        else:
            link.click()
        for _ in range(80):
            body = firefox.find_element(By.TAG_NAME, "body").text
            if title in body and marker in body:
                break
            time.sleep(0.25)
        assert title in body and marker in body, (fragment, body[:1500])
        assert firefox.current_url.endswith(fragment)
    firefox.refresh()
    for _ in range(60):
        body = firefox.find_element(By.TAG_NAME, "body").text
        if "Account and risk headroom" in body:
            break
        time.sleep(0.25)
    assert "Account and risk headroom" in body


def test_two_simultaneous_clients_keep_independent_active_views(local_server, firefox):
    options = Options()
    options.add_argument("-headless")
    second = webdriver.Firefox(
        options=options,
        service=Service(shutil.which("geckodriver") or "/snap/bin/geckodriver"),
    )
    try:
        for driver, route in ((firefox, "#/health"), (second, "#/")):
            driver.get(local_server + "/login")
            driver.find_element(By.NAME, "secret").send_keys(KEY)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            driver.get(local_server + "/" + route)
        for _ in range(80):
            health_body = firefox.find_element(By.TAG_NAME, "body").text
            overview_body = second.find_element(By.TAG_NAME, "body").text
            if (
                "Independent delivery" in health_body
                and "Account and risk headroom" in overview_body
            ):
                break
            time.sleep(0.25)
        assert "Independent delivery" in health_body
        assert "Account and risk headroom" not in health_body
        assert "Account and risk headroom" in overview_body
        assert "Independent delivery:" not in overview_body
        second.refresh()
        for _ in range(80):
            overview_body = second.find_element(By.TAG_NAME, "body").text
            if "Account and risk headroom" in overview_body:
                break
            time.sleep(0.25)
        assert "Account and risk headroom" in overview_body
        assert "Independent delivery" in firefox.find_element(By.TAG_NAME, "body").text
    finally:
        second.quit()


def test_embedded_registry_query_button_is_reactive(local_server, firefox):
    firefox.get(local_server + "/login")
    firefox.find_element(By.NAME, "secret").send_keys(KEY)
    firefox.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    firefox.get(local_server + "/#/research")
    for _ in range(60):
        if "Press Query registry" in firefox.find_element(By.TAG_NAME, "body").text:
            break
        time.sleep(0.25)
    # marimo.ui.run_button lives in a nested web-component shadow DOM.
    button = firefox.execute_script("""
        function findButton(root) {
            for (const el of root.querySelectorAll('*')) {
                if (el.tagName === 'BUTTON' &&
                    (el.innerText || el.textContent || '').includes('Query registry')) {
                    return el;
                }
                if (el.shadowRoot) {
                    const found = findButton(el.shadowRoot);
                    if (found) return found;
                }
            }
            return null;
        }
        return findButton(document);
    """)
    assert button is not None, firefox.find_element(By.TAG_NAME, "body").text[:1400]
    button.click()
    for _ in range(80):
        body = firefox.find_element(By.TAG_NAME, "body").text
        if "Inventory SHA:" in body or "Unavailable:" in body:
            break
        time.sleep(0.25)
    assert "Inventory SHA:" in body or "Unavailable:" in body, body[:1800]
