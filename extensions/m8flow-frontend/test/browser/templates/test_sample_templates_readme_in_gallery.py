"""Live UI check: templates documented in ``m8flow-backend/sample_templates/README.md`` appear in the gallery.

Requires backend sample load (e.g. ``M8FLOW_LOAD_SAMPLE_TEMPLATES=true``) or manual
imports. Substrings in ``helpers.sample_templates_readme`` follow
``sample_template_loader._derive_display_name`` (not the README description alone).
"""

from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT
from helpers.sample_templates_readme import SAMPLE_TEMPLATE_README_ROWS, SampleTemplateReadmeRow
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

_GALLERY_URL = f"{BASE_URL.rstrip('/')}/templates?per_page=50&page=1"


def _gallery_has_any_cards(page: Page) -> bool:
    return page.locator('[data-testid^="template-card-"]').count() > 0


def _open_gallery(page: Page) -> None:
    page.goto(_GALLERY_URL)
    wait_for_app_ready(page)
    expect(page.get_by_test_id("template-gallery-view-mode-toggle")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    page.get_by_test_id("template-gallery-view-card").click()


@pytest.fixture(scope="module")
def live_gallery_page(authenticated_page: Page) -> Page:
    """Tenant-admin session; gallery opened once (card view, wide page size)."""
    page = authenticated_page
    _open_gallery(page)
    if not _gallery_has_any_cards(page):
        pytest.skip(
            "Template gallery is empty — enable sample template loading per "
            "m8flow-backend/sample_templates/README.md (e.g. M8FLOW_LOAD_SAMPLE_TEMPLATES) "
            "or import the zips.",
        )
    return page


def test_sample_templates_gallery_not_empty(live_gallery_page: Page) -> None:
    """Sanity check that seeds or imports produced at least one card."""
    assert _gallery_has_any_cards(live_gallery_page)


@pytest.mark.parametrize(
    "row",
    SAMPLE_TEMPLATE_README_ROWS,
    ids=[r.slug for r in SAMPLE_TEMPLATE_README_ROWS],
)
def test_readme_sample_template_visible_in_gallery(
    live_gallery_page: Page,
    row: SampleTemplateReadmeRow,
) -> None:
    """Each README catalogue entry should match some visible template card."""
    page = live_gallery_page
    page.goto(_GALLERY_URL)
    wait_for_app_ready(page)
    expect(page.get_by_test_id("template-gallery-view-mode-toggle")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    page.get_by_test_id("template-gallery-view-card").click()

    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    search_input.fill(row.ui_substring)
    page.wait_for_timeout(500)

    card = page.locator('[data-testid^="template-card-"]').filter(
        has_text=re.compile(re.escape(row.ui_substring), re.I)
    )
    try:
        expect(card.first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    except AssertionError:
        logger.error(
            "No card matched substring %r (readme slug=%s). "
            "If the backend template name differs, update "
            "helpers.sample_templates_readme.SAMPLE_TEMPLATE_README_ROWS.",
            row.ui_substring,
            row.slug,
        )
        raise
