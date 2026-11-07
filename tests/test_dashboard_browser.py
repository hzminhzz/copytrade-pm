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
Options = importlib.import_module("selenium.webdriver.firefox.options").Options
Service = importlib.import_module("selenium.webdriver.firefox.service").Service

KEY = "x" * 64


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
        [sys.executable, "-m", "uvicorn", "copytrade_pm.dashboard.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--workers", "1",
         "--no-access-log"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
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
    firefox.set_window_size(width, height)
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
        if "Account risk" in firefox.page_source:
            break
        time.sleep(0.25)
    assert "Account risk" in firefox.page_source, firefox.find_element(
        By.TAG_NAME, "body").text[:2000]
    assert "Read-only" in firefox.page_source
    assert "UNKNOWN" in firefox.page_source or "UNAVAILABLE" in firefox.page_source
    assert firefox.find_elements(By.CSS_SELECTOR, "nav[aria-label='Read-only dashboard navigation']")
    doc_width = firefox.execute_script(
        "return document.documentElement.scrollWidth;"
    )
    inner_width = firefox.execute_script("return window.innerWidth;")
    # Critical content must not create top-level horizontal scrolling.
    assert doc_width <= inner_width + 5, (doc_width, inner_width, width)
    assert "0x" not in firefox.current_url
    target = local_server + "/health?utc=7d&token=SECRET-LEAK&portfolio=gemini.phase5%2FP1%403"
    firefox.get(target)
    for _ in range(50):
        if "Independent delivery" in firefox.page_source:
            break
        time.sleep(0.25)
    assert "Independent delivery" in firefox.page_source
    navs = firefox.find_elements(By.CSS_SELECTOR,
                                 "nav[aria-label='Read-only dashboard navigation']")
    assert navs
    assert "SECRET-LEAK" not in navs[0].get_attribute("outerHTML")
    assert "SECRET-LEAK" not in firefox.current_url
    assert "portfolio=gemini.phase5" in navs[0].get_attribute("outerHTML")
    artifact_dir = os.getenv("DASHBOARD_BROWSER_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        assert firefox.save_screenshot(
            str(Path(artifact_dir) / f"phase3-{width}x{height}.png")
        )
