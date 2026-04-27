import json
import os
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote

import pytest
from playwright.sync_api import expect, sync_playwright


PRICE_OUTPUT_DIR = Path(os.getenv("PRICE_OUTPUT_DIR", "test-results/prices"))


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):
        return

    PRICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for output_file in PRICE_OUTPUT_DIR.glob("*.txt"):
        output_file.unlink()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if hasattr(config, "workerinput") or not PRICE_OUTPUT_DIR.exists():
        return

    price_outputs = sorted(PRICE_OUTPUT_DIR.glob("*.txt"))
    if not price_outputs:
        return

    terminalreporter.section("device prices")
    for output_file in price_outputs:
        message = output_file.read_text(encoding="utf-8").strip()
        if message:
            terminalreporter.write_line(message)


@pytest.fixture
def page(request):
    browser_name = os.getenv("BROWSER", "chromium").strip().lower()
    headless = _env_flag("HEADLESS", True)
    timeout_ms = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "45000"))
    slow_mo_ms = int(os.getenv("SLOW_MO_MS", "0"))
    expect.set_options(timeout=timeout_ms)

    with sync_playwright() as playwright:
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise ValueError("BROWSER must be one of: chromium, firefox, webkit")

        run_on_lambdatest = _env_flag("RUN_ON_LAMBDATEST", False)
        if run_on_lambdatest:
            browser = connect_to_lambdatest(playwright, request.node.name, timeout_ms)
        else:
            browser_type = getattr(playwright, browser_name)
            browser = browser_type.launch(headless=headless, slow_mo=slow_mo_ms)

        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        test_page = context.new_page()
        test_page.set_default_timeout(timeout_ms)

        yield test_page

        if run_on_lambdatest:
            report_lambdatest_status(test_page, request.node)

        context.close()
        browser.close()


def connect_to_lambdatest(playwright, test_name: str, timeout_ms: int):
    username = os.getenv("LT_USERNAME") or os.getenv("LAMBDATEST_USERNAME")
    access_key = os.getenv("LT_ACCESS_KEY") or os.getenv("LAMBDATEST_ACCESS_KEY")

    if not username or not access_key:
        pytest.fail(
            "LambdaTest credentials are required when RUN_ON_LAMBDATEST=true. "
            "Set LT_USERNAME and LT_ACCESS_KEY."
        )

    capabilities = {
        "browserName": os.getenv("LT_BROWSER", "Chrome"),
        "browserVersion": os.getenv("LT_BROWSER_VERSION", "latest"),
        "platform": os.getenv("LT_PLATFORM", "Windows 10"),
        "build": os.getenv("LT_BUILD", "Amazon Device Cart Tests"),
        "name": test_name,
        "user": username,
        "accessKey": access_key,
        "console": True,
        "network": True,
        "playwrightversion": version("playwright"),
    }

    tunnel_name = os.getenv("LT_TUNNEL_NAME")
    if tunnel_name:
        capabilities["tunnel"] = True
        capabilities["tunnelName"] = tunnel_name

    endpoint = (
        "wss://cdp.lambdatest.com/playwright?capabilities="
        f"{quote(json.dumps(capabilities))}"
    )

    browser_type = playwright.chromium
    capability_browser = capabilities["browserName"].lower()
    if "firefox" in capability_browser:
        browser_type = playwright.firefox
    elif "webkit" in capability_browser:
        browser_type = playwright.webkit

    return browser_type.connect(endpoint, timeout=timeout_ms)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())


def report_lambdatest_status(page, node) -> None:
    report = getattr(node, "rep_call", None)
    if report is None:
        return

    status = "passed" if report.passed else "failed"
    remark = "Test passed" if report.passed else str(report.longrepr)
    action = {
        "action": "setTestStatus",
        "arguments": {"status": status, "remark": remark[:255]},
    }
    page.evaluate("_ => {}", f"lambdatest_action: {json.dumps(action)}")
