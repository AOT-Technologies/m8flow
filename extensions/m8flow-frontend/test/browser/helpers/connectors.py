"""Connectors-tab page helpers (functional "page object").

Mirrors the style of :mod:`helpers.templates`: small functions that drive the
Connectors view and assert on its stable ``data-testid`` locators.
"""
from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT, ELEMENT_TIMEOUT
from helpers.waiters import wait_for_app_ready

# English fallback shown when a connector has no description
# (translation key ``use_via_service_task``). Kept in sync with
# m8flow-frontend/src/locales/en_us/translation.json.
USE_VIA_SERVICE_TASK_TEXT = "Use in a Service Task in your process model."

CARD_TESTID_PREFIX = "connector-card-"


def _connectors_url() -> str:
    return f"{BASE_URL.rstrip('/')}/connectors"


def navigate_to_connectors(page: Page) -> None:
    """Click the Connectors nav item and wait for the page to render."""
    wait_for_app_ready(page)
    page.get_by_test_id("nav-item-connectors").click()
    page_root = page.get_by_test_id("connectors-page")
    try:
        expect(page_root).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    except AssertionError:
        # Shared-session runs can occasionally leave us on another route after
        # the nav click; hard-navigate as a fallback.
        goto_connectors_directly(page)
        expect(page_root).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(page).to_have_url(re.compile(r"/connectors"))


def goto_connectors_directly(page: Page) -> None:
    """Navigate straight to /connectors (refresh / restricted-access tests)."""
    page.goto(_connectors_url())
    wait_for_app_ready(page)


def open_operations_modal(page: Page, connector_id: str) -> None:
    """Click a card's 'View Operations' button and wait for the modal."""
    page.get_by_test_id(f"connector-view-ops-{connector_id}").click()
    expect(
        page.get_by_test_id("connector-operations-modal")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)


def close_operations_modal(page: Page) -> None:
    """Close the operations modal via its Close button."""
    modal = page.get_by_test_id("connector-operations-modal")
    modal.get_by_role("button", name="Close").click()
    expect(modal).to_be_hidden(timeout=ELEMENT_TIMEOUT)


def search_connectors(page: Page, term: str) -> None:
    """Type a term into the connectors search box."""
    box = page.get_by_test_id("connectors-search").locator("input")
    box.fill(term)


def connector_card_count(page: Page) -> int:
    """Return the number of rendered connector cards."""
    return page.locator(f'[data-testid^="{CARD_TESTID_PREFIX}"]').count()


def expected_op_count_label(connector: dict[str, Any]) -> str:
    """The text shown in the operation-count chip for *connector*."""
    count = connector["operationCount"]
    unit = "operation" if count == 1 else "operations"
    return f"{count} {unit}"


def expect_connector_card(page: Page, connector: dict[str, Any]) -> None:
    """Assert that *connector* renders a card with correct details.

    Validates the card container, name, avatar (aria-label), description (or
    the service-task fallback when empty) and the operation-count chip.
    """
    cid = connector["id"]
    expect(
        page.get_by_test_id(f"connector-card-{cid}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    expect(page.get_by_test_id(f"connector-name-{cid}")).to_have_text(
        connector["name"]
    )

    # Avatar renders with aria-label set to the connector display name.
    expect(
        page.get_by_test_id(f"connector-card-{cid}").get_by_label(connector["name"])
    ).to_be_visible()

    expected_description = connector["description"] or USE_VIA_SERVICE_TASK_TEXT
    expect(
        page.get_by_test_id(f"connector-description-{cid}")
    ).to_have_text(expected_description)

    expect(
        page.get_by_test_id(f"connector-op-count-{cid}")
    ).to_contain_text(expected_op_count_label(connector))
