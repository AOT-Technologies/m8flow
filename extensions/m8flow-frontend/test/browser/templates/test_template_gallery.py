"""Templates gallery: layout, search, filters, pagination (live UI / real API)."""

from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT, SHORT_TIMEOUT
from helpers.templates import navigate_to_templates
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)


def _pagination_root(page: Page):
    return page.locator('[data-testid="template-gallery-pagination"]')


def _template_cards(page: Page):
    # TemplateCard root has both data-testid and id. Child title typography also
    # uses a template-card-* test id, so match roots only to avoid false hits.
    return page.locator('div[data-testid^="template-card-"][id^="template-card-"]')


def _gallery_table_rows(page: Page):
    return page.locator('[data-testid^="template-gallery-row-"]')


def _open_clean_gallery(page: Page) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/templates?page=1&per_page=50")
    wait_for_app_ready(page)
    expect(page.get_by_test_id("template-gallery-view-mode-toggle")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )


def _skip_if_gallery_empty(page: Page) -> None:
    _open_clean_gallery(page)
    page.get_by_test_id("template-gallery-view-card").click()
    if _template_cards(page).count() == 0:
        pytest.skip("Template gallery has no cards — seed templates or enable sample load.")


def _first_card_title_line(page: Page) -> str:
    """First line of the first card (title row), for search narrowing."""
    text = _template_cards(page).first.inner_text()
    line = (text.split("\n")[0] or "").strip()
    if not line:
        pytest.skip("Could not read title from first template card.")
    return line


@pytest.mark.parametrize("view", ["card", "table"])
def test_template_gallery_layout_card_and_list(authenticated_page: Page, view: str) -> None:
    """Gallery card grid vs table toggle shows table rows with view actions."""
    logger.info("Gallery view mode=%s", view)
    page = authenticated_page
    _skip_if_gallery_empty(page)

    navigate_to_templates(page)

    if view == "table":
        page.get_by_test_id("template-gallery-view-table").click()
        expect(page.get_by_test_id("template-gallery-table")).to_be_visible(
            timeout=PAGE_DATA_TIMEOUT,
        )
        row = _gallery_table_rows(page).first
        expect(row).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        view_btn = page.locator('[data-testid^="template-gallery-view-button-"]').first
        expect(view_btn).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        page.get_by_test_id("template-gallery-view-card").click()
        expect(_template_cards(page).first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    else:
        page.get_by_test_id("template-gallery-view-card").click()
        expect(_template_cards(page).first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        page.get_by_test_id("template-gallery-view-card").click()
    logger.info("Assertions passed for %s", view)


def test_template_gallery_search(authenticated_page: Page) -> None:
    """Search debounces and narrows templates using text from a real card."""
    page = authenticated_page
    _skip_if_gallery_empty(page)
    navigate_to_templates(page)
    page.get_by_test_id("template-gallery-view-card").click()

    title_line = _first_card_title_line(page)
    needle = title_line[:40] if len(title_line) > 40 else title_line
    logger.info("Filter by search text derived from first card: %r", needle)

    before = _template_cards(page).count()
    page.get_by_test_id("template-filters-search-input").locator("input").fill(needle)
    page.wait_for_timeout(400)

    after = _template_cards(page).count()
    assert after >= 1, "Search should leave at least the matching template visible."
    assert after <= before, "Search should not increase the number of cards."
    expect(_template_cards(page).first).to_contain_text(
        re.compile(re.escape(needle[: min(12, len(needle))]), re.I),
    )
    logger.info("Search narrowed gallery (before=%s after=%s)", before, after)


def test_template_gallery_filter_category(authenticated_page: Page) -> None:
    """Category filter: only templates with that category remain (when categories exist)."""
    page = authenticated_page
    _skip_if_gallery_empty(page)
    navigate_to_templates(page)

    category_select = page.get_by_test_id("template-filters-category-select")
    category_select.click()
    opts = page.get_by_role("option")
    try:
        opts.nth(1).wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("No template categories in this environment.")
    label = opts.nth(1).inner_text().strip()
    opts.nth(1).click()
    wait_for_app_ready(page)

    before_guess = _template_cards(page).count()
    assert before_guess >= 1, f"Expected at least one template in category {label!r}"

    for i in range(min(5, _template_cards(page).count())):
        expect(_template_cards(page).nth(i)).to_contain_text(label, timeout=PAGE_DATA_TIMEOUT)
    logger.info("Category filter applied: %r", label)


def test_template_gallery_filter_visibility(authenticated_page: Page) -> None:
    """Visibility filter: Public shows only templates with the public chip label."""
    page = authenticated_page
    _skip_if_gallery_empty(page)
    navigate_to_templates(page)

    page.get_by_test_id("template-filters-visibility-select").click()
    page.get_by_role("option", name=re.compile(r"^public$", re.I)).click()
    wait_for_app_ready(page)
    page.wait_for_timeout(350)

    n = _template_cards(page).count()
    assert n >= 1, "Expected at least one PUBLIC template (common after sample load)."
    for i in range(min(5, n)):
        expect(_template_cards(page).nth(i)).to_contain_text(
            re.compile(r"public", re.I),
            timeout=PAGE_DATA_TIMEOUT,
        )
    logger.info("Visibility=Public filter applied; %s card(s) visible.", n)


def test_template_gallery_pagination_next_page(authenticated_page: Page) -> None:
    """Pagination advances URL ``page`` when more results exist."""
    logger.info("pagination: per_page=2, next page")
    page = authenticated_page
    _skip_if_gallery_empty(page)

    page.goto(f"{BASE_URL.rstrip('/')}/templates?page=1&per_page=2")
    wait_for_app_ready(page)
    expect(page.get_by_test_id("template-gallery-view-mode-toggle")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    page.get_by_test_id("template-gallery-view-card").click()

    if _template_cards(page).count() < 2:
        pytest.skip("Need at least 2 templates for per_page=2 pagination.")

    next_btn = _pagination_root(page).get_by_role("button", name=re.compile("next", re.I))
    if next_btn.is_disabled():
        pytest.skip("Pagination next is disabled — not enough pages for this test.")
    next_btn.click()
    expect(page).to_have_url(re.compile(r"[?&]page=2"))

    expect(_template_cards(page).first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Page 2 loaded.")


def test_template_gallery_per_page_selection(authenticated_page: Page) -> None:
    """Changing rows-per-page updates ``per_page`` in the URL."""
    logger.info("Setting rows per page to 25")
    page = authenticated_page
    _skip_if_gallery_empty(page)
    navigate_to_templates(page)

    rows_select = _pagination_root(page).get_by_role("combobox").first
    rows_select.click()
    page.get_by_role("option", name="25").click()

    expect(page).to_have_url(re.compile(r"[?&]per_page=25"))
    logger.info("URL contains per_page=25")
