"""End-to-end coverage for the Connectors tab.

All cases are mock-backed (``page.route``) so they are deterministic and do not
require a running connector proxy. Each test reuses one logged-in session and
relies on per-test fixtures that reset routes, keeping cases independent.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT, VIEWPORT
from helpers.connectors import (
    USE_VIA_SERVICE_TASK_TEXT,
    close_operations_modal,
    connector_card_count,
    expect_connector_card,
    goto_connectors_directly,
    navigate_to_connectors,
    open_operations_modal,
    search_connectors,
)
from helpers.mocks import (
    ALL_MOCK_CONNECTORS,
    MOCK_CONNECTOR_HTTP,
    MOCK_CONNECTOR_SLACK,
    MOCK_CONNECTOR_SMTP,
)


# --- Visibility & permission gating ---------------------------------------


def test_connectors_tab_visible_for_authorized(mocked_connectors_page: Page) -> None:
    """An authorized user sees the Connectors nav item and can open the page."""
    page = mocked_connectors_page
    expect(page.get_by_test_id("nav-item-connectors")).to_be_visible()
    navigate_to_connectors(page)
    expect(page.get_by_test_id("connectors-page")).to_be_visible()


def test_restricted_user_redirected(restricted_connectors_page: Page) -> None:
    """A user without GET on connectors-grouped is redirected away and has no tab."""
    page = restricted_connectors_page
    # Nav item is hidden for users lacking the permission.
    expect(page.get_by_test_id("nav-item-connectors")).to_have_count(0)
    # Direct navigation redirects to home; the connectors page never renders.
    goto_connectors_directly(page)
    expect(page).not_to_have_url(re.compile(r"/connectors"))
    expect(page.get_by_test_id("connectors-page")).to_have_count(0)


# --- List / states --------------------------------------------------------


def test_connectors_list_loads(mocked_connectors_page: Page) -> None:
    """The grid renders exactly the mocked connectors."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    expect(
        page.get_by_test_id(f"connector-card-{MOCK_CONNECTOR_HTTP['id']}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    assert connector_card_count(page) == len(ALL_MOCK_CONNECTORS)


def test_empty_state(mocked_connectors_empty_page: Page) -> None:
    """An empty list shows the empty placeholder and hides the search box."""
    page = mocked_connectors_empty_page
    navigate_to_connectors(page)
    expect(page.get_by_test_id("connectors-empty")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    expect(page.get_by_test_id("connectors-search")).to_have_count(0)


def test_loading_state(mocked_connectors_loading_page: Page) -> None:
    """While the connectors request is in flight, a spinner is shown."""
    page = mocked_connectors_loading_page
    navigate_to_connectors(page)
    expect(page.get_by_role("progressbar").first).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    # No cards render while the request is pending.
    assert connector_card_count(page) == 0


def test_error_state(mocked_connectors_error_page: Page) -> None:
    """A failed connectors request surfaces the load-failed alert."""
    page = mocked_connectors_error_page
    navigate_to_connectors(page)
    expect(page.get_by_text("Could not load connectors", exact=False)).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )


# --- Card detail rendering ------------------------------------------------


def test_connector_card_details(mocked_connectors_page: Page) -> None:
    """Cards render name, avatar, description and the operation-count chip."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    expect_connector_card(page, MOCK_CONNECTOR_HTTP)
    expect_connector_card(page, MOCK_CONNECTOR_SMTP)


def test_operation_count_singular_and_plural(mocked_connectors_page: Page) -> None:
    """The chip uses the singular 'operation' for one op and plural otherwise."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    expect(
        page.get_by_test_id(f"connector-op-count-{MOCK_CONNECTOR_SLACK['id']}")
    ).to_contain_text("1 operation")
    expect(
        page.get_by_test_id(f"connector-op-count-{MOCK_CONNECTOR_HTTP['id']}")
    ).to_contain_text("3 operations")


def test_connector_description_fallback(mocked_connectors_page: Page) -> None:
    """A connector with no description shows the service-task fallback text."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    expect(
        page.get_by_test_id(f"connector-description-{MOCK_CONNECTOR_SLACK['id']}")
    ).to_have_text(USE_VIA_SERVICE_TASK_TEXT)


# --- Configure button -----------------------------------------------------


def test_configure_button_navigates(mocked_connectors_page: Page) -> None:
    """The Configure button routes to the secrets configuration page."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    configure = page.get_by_test_id(
        f"connector-configure-{MOCK_CONNECTOR_HTTP['id']}"
    )
    expect(configure).to_be_visible()
    configure.click()
    expect(page).to_have_url(re.compile(r"/configuration/secrets"))


def test_configure_button_hidden_without_secret_permission(
    mocked_connectors_configure_denied_page: Page,
) -> None:
    """Without secrets POST permission, Configure is hidden but View Operations stays."""
    page = mocked_connectors_configure_denied_page
    navigate_to_connectors(page)
    cid = MOCK_CONNECTOR_HTTP["id"]
    expect(page.get_by_test_id(f"connector-view-ops-{cid}")).to_be_visible()
    expect(page.get_by_test_id(f"connector-configure-{cid}")).to_have_count(0)


# --- Operations modal & navigation ----------------------------------------


def test_view_operations_modal(mocked_connectors_page: Page) -> None:
    """View Operations opens a modal listing the connector's operations."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    open_operations_modal(page, MOCK_CONNECTOR_HTTP["id"])
    first_op_id = MOCK_CONNECTOR_HTTP["operations"][0]["id"]
    expect(
        page.get_by_test_id(f"connector-operation-{first_op_id}")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    close_operations_modal(page)


# --- Search / filter ------------------------------------------------------


def test_search_filters_and_no_match(mocked_connectors_page: Page) -> None:
    """Searching narrows the grid; a non-matching term shows the no-match state."""
    page = mocked_connectors_page
    navigate_to_connectors(page)

    search_connectors(page, MOCK_CONNECTOR_SLACK["name"])
    expect(
        page.get_by_test_id(f"connector-card-{MOCK_CONNECTOR_SLACK['id']}")
    ).to_be_visible()
    expect(
        page.get_by_test_id(f"connector-card-{MOCK_CONNECTOR_HTTP['id']}")
    ).to_have_count(0)

    search_connectors(page, "zzz-no-such-connector")
    expect(page.get_by_test_id("connectors-no-match")).to_be_visible()


# --- Responsiveness & navigation persistence ------------------------------


def test_responsive_layout(mocked_connectors_page: Page) -> None:
    """Cards render on both desktop and a narrow mobile viewport."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    cid = MOCK_CONNECTOR_HTTP["id"]
    expect(page.get_by_test_id(f"connector-card-{cid}")).to_be_visible()

    page.set_viewport_size({"width": 390, "height": 844})
    try:
        expect(page.get_by_test_id(f"connector-card-{cid}")).to_be_visible()
        assert connector_card_count(page) == len(ALL_MOCK_CONNECTORS)
    finally:
        page.set_viewport_size(VIEWPORT)


def test_state_after_refresh(mocked_connectors_page: Page) -> None:
    """Reloading the connectors page keeps the route and re-renders the grid."""
    page = mocked_connectors_page
    navigate_to_connectors(page)
    page.reload()
    expect(page.get_by_test_id("connectors-page")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    expect(page).to_have_url(re.compile(r"/connectors"))
    expect(
        page.get_by_test_id(f"connector-card-{MOCK_CONNECTOR_HTTP['id']}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def test_state_after_back_navigation(mocked_connectors_page: Page) -> None:
    """Browser back/forward restores the expected page state."""
    page = mocked_connectors_page
    navigate_to_connectors(page)

    page.go_back()
    expect(page).not_to_have_url(re.compile(r"/connectors"))

    page.go_forward()
    expect(page).to_have_url(re.compile(r"/connectors"))
    expect(page.get_by_test_id("connectors-page")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    expect(
        page.get_by_test_id(f"connector-card-{MOCK_CONNECTOR_HTTP['id']}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
