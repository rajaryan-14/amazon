import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin

import pytest
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect


LOGGER = logging.getLogger(__name__)
AMAZON_URL = os.getenv("AMAZON_URL", "https://www.amazon.com")
AMAZON_ZIP = os.getenv("AMAZON_ZIP", "10001").strip()
MAX_PRODUCT_ATTEMPTS = int(os.getenv("MAX_PRODUCT_ATTEMPTS", "8"))
PRICE_PATTERN = re.compile(r"([$€£¥₹]\s*\d|(?:USD|INR|EUR|GBP|JPY)\s*\d)", re.I)
PRODUCT_LINK_SELECTORS = [
    "[data-cy='title-recipe'] a",
    "a.a-link-normal.s-line-clamp-2",
    "a.a-link-normal.s-link-style.a-text-normal",
    "a.s-no-outline",
]


@dataclass(frozen=True)
class AddedDevice:
    title: str
    price: str


@pytest.mark.amazon
def test_case_1_search_iphone_add_to_cart_and_print_price(page: Page):
    device = search_add_to_cart_and_return_price(
        page,
        [
            os.getenv("IPHONE_QUERY", "Simple Mobile iPhone"),
            "iPhone SE prepaid",
            "Apple iPhone prepaid",
        ],
        re.compile(r"\biPhone\b", re.I),
    )

    report_price("test_case_1_iphone", f"Test Case 1 - iPhone price: {device.price}")
    LOGGER.info("Test Case 1 - added item: %s | price: %s", device.title, device.price)


@pytest.mark.amazon
def test_case_2_search_galaxy_add_to_cart_and_print_price(page: Page):
    device = search_add_to_cart_and_return_price(
        page,
        os.getenv("GALAXY_QUERY", "Samsung Galaxy unlocked smartphone"),
        re.compile(r"\bGalaxy\b", re.I),
    )

    report_price("test_case_2_galaxy", f"Test Case 2 - Galaxy device price: {device.price}")
    LOGGER.info("Test Case 2 - added item: %s | price: %s", device.title, device.price)


def report_price(file_stem: str, message: str) -> None:
    print(message, flush=True)
    output_dir = Path(os.getenv("PRICE_OUTPUT_DIR", "test-results/prices"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{file_stem}.txt"
    output_file.write_text(f"{message}\n", encoding="utf-8")


def search_add_to_cart_and_return_price(
    page: Page,
    search_terms: str | list[str],
    expected_title: re.Pattern[str],
) -> AddedDevice:
    terms = [search_terms] if isinstance(search_terms, str) else list(dict.fromkeys(search_terms))

    for search_term in terms:
        device = try_search_add_to_cart_and_return_price(page, search_term, expected_title)
        if device:
            return device

    pytest.fail(
        f"Could not add a priced item to the cart for search terms {terms!r}. "
        "Amazon may have changed the page, blocked automation, or returned unavailable items."
    )


def try_search_add_to_cart_and_return_price(
    page: Page,
    search_term: str,
    expected_title: re.Pattern[str],
) -> Optional[AddedDevice]:
    open_amazon_and_search(page, search_term)

    before_count = read_cart_count(page)
    result_count = page.locator("div[data-component-type='s-search-result']").count()
    if result_count == 0:
        return None

    for index in range(min(result_count, MAX_PRODUCT_ATTEMPTS)):
        card = page.locator("div[data-component-type='s-search-result']").nth(index)
        title = text_or_none(card.locator("h2 span").first)
        price = price_from_locator(card)
        add_button = first_visible(
            [
                card.get_by_role("button", name=re.compile(r"add to cart", re.I)),
                card.locator("input[name='submit.addToCart']"),
                card.locator("button[name='submit.addToCart']"),
                card.locator("button:has-text('Add to cart')"),
                card.locator("button:has-text('Add to Cart')"),
            ]
        )

        if not title or not expected_title.search(title) or not price or add_button is None:
            continue

        if click_and_confirm_add(page, add_button, before_count):
            return AddedDevice(title=title, price=price)

    candidates = collect_product_page_candidates(page)
    for title, price, href in candidates[:MAX_PRODUCT_ATTEMPTS]:
        page.goto(urljoin(AMAZON_URL, href), wait_until="domcontentloaded")
        assert_not_amazon_challenge(page)

        product_title = text_or_none(page.locator("#productTitle").first) or title
        product_price = product_page_price(page) or price
        add_button = first_visible(
            [
                page.locator("#add-to-cart-button"),
                page.locator("input[name='submit.add-to-cart']"),
                page.locator("input[name='submit.addToCart']"),
                page.get_by_role("button", name=re.compile(r"add to cart", re.I)),
            ]
        )

        if (
            expected_title.search(product_title)
            and add_button
            and click_and_confirm_add(page, add_button, before_count)
        ):
            return AddedDevice(title=product_title, price=product_price)

    return None


def open_amazon_and_search(page: Page, search_term: str) -> None:
    page.goto(AMAZON_URL, wait_until="domcontentloaded")
    assert_not_amazon_challenge(page)
    dismiss_optional_cookie_prompt(page)
    set_delivery_zip(page)

    search_box = page.locator("#twotabsearchtextbox")
    expect(search_box).to_be_visible()
    search_box.fill(search_term)
    page.locator("#nav-search-submit-button").click()
    page.wait_for_load_state("domcontentloaded")

    assert_not_amazon_challenge(page)
    try:
        expect(page.locator("div[data-component-type='s-search-result']").first).to_be_visible()
    except AssertionError:
        page.goto(f"{AMAZON_URL}/s?k={quote_plus(search_term)}", wait_until="domcontentloaded")
        assert_not_amazon_challenge(page)
        expect(page.locator("div[data-component-type='s-search-result']").first).to_be_visible()


def collect_product_page_candidates(page: Page) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    results = page.locator("div[data-component-type='s-search-result']")

    for index in range(min(results.count(), MAX_PRODUCT_ATTEMPTS)):
        card = results.nth(index)
        title = text_or_none(card.locator("h2 span").first)
        price = price_from_locator(card)
        href = product_href_from_card(card)

        if title and price and href:
            candidates.append((title, price, href))

    return candidates


def product_href_from_card(card: Locator) -> Optional[str]:
    for selector in PRODUCT_LINK_SELECTORS:
        href = attribute_or_none(card.locator(selector).first, "href")
        if href and not href.startswith("javascript:"):
            return href

    return None


def click_and_confirm_add(page: Page, add_button: Locator, before_count: int) -> bool:
    try:
        add_button.click()
        dismiss_optional_protection_prompt(page)
        return wait_until_cart_updates(page, before_count)
    except PlaywrightTimeoutError:
        return False


def wait_until_cart_updates(page: Page, before_count: int) -> bool:
    deadline = time.monotonic() + 20
    confirmation = page.get_by_text(re.compile(r"added to cart|added to basket", re.I))

    while time.monotonic() < deadline:
        assert_not_amazon_challenge(page)

        if read_cart_count(page) > before_count:
            return True

        try:
            if confirmation.first.is_visible(timeout=1000):
                return True
        except PlaywrightTimeoutError:
            pass

        dismiss_optional_protection_prompt(page)
        page.wait_for_timeout(500)

    return False


def read_cart_count(page: Page) -> int:
    count_text = text_or_none(page.locator("#nav-cart-count").first)
    if not count_text:
        return 0

    match = re.search(r"\d+", count_text)
    return int(match.group()) if match else 0


def product_page_price(page: Page) -> Optional[str]:
    for selector in [
        "#corePrice_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        ".a-price .a-offscreen",
    ]:
        price = text_or_none(page.locator(selector).first)
        if looks_like_price(price):
            return price

    return None


def price_from_locator(locator: Locator) -> Optional[str]:
    for selector in [".a-price .a-offscreen", ".a-price-whole"]:
        price = text_or_none(locator.locator(selector).first)
        if looks_like_price(price):
            return price

    return None


def first_visible(locators: list[Locator]) -> Optional[Locator]:
    for locator in locators:
        try:
            for index in range(min(locator.count(), 5)):
                candidate = locator.nth(index)
                if candidate.is_visible(timeout=1000) and candidate.is_enabled(timeout=1000):
                    return candidate
        except PlaywrightTimeoutError:
            continue

    return None


def dismiss_optional_cookie_prompt(page: Page) -> None:
    for selector in [
        "#sp-cc-accept",
        "input[name='accept']",
        "button:has-text('Accept')",
        "button:has-text('Continue shopping')",
    ]:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1500):
                button.click()
                return
        except PlaywrightTimeoutError:
            continue


def set_delivery_zip(page: Page) -> None:
    if not AMAZON_ZIP:
        return

    try:
        location_button = first_visible(
            [
                page.locator("#glow-ingress-block"),
                page.locator("#nav-global-location-popover-link"),
                page.locator("#nav-global-location-slot"),
            ]
        )
        if location_button is None:
            return

        location_button.click()
        zip_input = page.locator("#GLUXZipUpdateInput").first
        expect(zip_input).to_be_visible()
        zip_input.fill(AMAZON_ZIP)

        update_button = first_visible(
            [
                page.locator("#GLUXZipUpdate"),
                page.get_by_role("button", name=re.compile(r"apply|update", re.I)),
            ]
        )
        if update_button is None:
            return

        update_button.click()
        page.wait_for_timeout(2500)

        close_button = first_visible(
            [
                page.locator("#GLUXConfirmClose"),
                page.locator("button[name='glowDoneButton']"),
                page.locator("input[name='glowDoneButton']"),
                page.get_by_role("button", name=re.compile(r"done|continue", re.I)),
            ]
        )
        if close_button:
            close_button.click()

        page.wait_for_timeout(2500)
    except PlaywrightTimeoutError:
        LOGGER.warning("Could not set Amazon delivery ZIP to %s.", AMAZON_ZIP)


def dismiss_optional_protection_prompt(page: Page) -> None:
    for selector in [
        "input[aria-labelledby='attachSiNoCoverage-announce']",
        "#attachSiNoCoverage input",
        "button:has-text('No Thanks')",
        "button:has-text('No, thanks')",
        "input[value='No Thanks']",
    ]:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1000):
                button.click()
                page.wait_for_timeout(500)
                return
        except PlaywrightTimeoutError:
            continue


def assert_not_amazon_challenge(page: Page) -> None:
    body_text = text_or_none(page.locator("body").first) or ""
    challenge_patterns = [
        "enter the characters you see below",
        "sorry, we just need to make sure you're not a robot",
        "type the characters you see in this image",
    ]

    if any(pattern in body_text.lower() for pattern in challenge_patterns):
        pytest.fail(
            "Amazon displayed an anti-automation challenge. "
            "Re-run later, use headed mode, or complete the challenge manually in a real browser session."
        )


def text_or_none(locator: Locator) -> Optional[str]:
    try:
        if locator.count() == 0:
            return None
        text = locator.text_content(timeout=3000)
    except PlaywrightTimeoutError:
        return None

    return normalize_text(text)


def attribute_or_none(locator: Locator, attribute_name: str) -> Optional[str]:
    try:
        if locator.count() == 0:
            return None
        return locator.get_attribute(attribute_name, timeout=3000)
    except PlaywrightTimeoutError:
        return None


def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def looks_like_price(value: Optional[str]) -> bool:
    return bool(value and PRICE_PATTERN.search(value))
