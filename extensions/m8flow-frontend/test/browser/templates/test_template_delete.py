"""E2E coverage for template delete and restore functionality.

Scope
-----
* Admin creates two published templates (TENANT and PUBLIC visibility) plus a
  draft template, all used to exercise delete / restore paths.
* Editor permission checks run in both the list view (more-actions menu) and
  the template detail page for every template type.
* Admin delete + restore flows are verified for both TENANT and PUBLIC templates.
* Draft hard-delete is verified separately.
* An additional "editor capability" section creates a PM under the editor
  account inside the shared Test Process Group, walks through draft-delete
  permissions, publish, published-delete permissions, and admin soft-delete.

Session model
-------------
* ``page`` fixture = single module-scoped admin session (wraps
  ``default_admin_page``).
* ``editor_page`` fixture = single module-scoped editor session (from
  conftest).  Both sessions live for the entire module.
"""

from __future__ import annotations

import logging
import re
from typing import Generator

import pytest
from faker import Faker as _Faker
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    BASE_URL,
    ELEMENT_TIMEOUT,
    NAV_TIMEOUT,
    PAGE_DATA_TIMEOUT,
    SHORT_TIMEOUT,
)
from helpers.process_group_setup import (
    TEST_PROCESS_GROUP_ID,
    navigate_into_process_group,
)
from helpers.templates import search_templates
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def page(default_admin_page: Page) -> Generator[Page, None, None]:  # type: ignore[override]
    """Module-scoped admin session shared by every test in this file."""
    yield default_admin_page


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_fake = _Faker()

# Admin-owned templates
_PM_DISPLAY_NAME = f"{_fake.last_name()} Delete Tests Automation"
_DRAFT_TEMPLATE_NAME = f"{_fake.first_name()} Draft Automation"
_PUBLISHED_TENANT_TEMPLATE_NAME = f"{_fake.first_name()} Tenant Published Automation"
_PUBLISHED_PUBLIC_TEMPLATE_NAME = f"{_fake.first_name()} Public Published Automation"

# Editor capability section
_EDITOR_PM_DISPLAY_NAME = f"{_fake.last_name()} Editor Delete PM Automation"
_EDITOR_TEMPLATE_NAME = f"{_fake.first_name()} Editor Template Automation"

_TEMPLATE_DESC = "Created by browser automation for template delete E2E coverage."
_TEMPLATE_CATEGORY = "Automation"

# Shared mutable state — populated during setup, consumed by tests and cleanup.
_STATE: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_template_list_response(response) -> bool:  # noqa: ANN001
    """True for the gallery list endpoint (has query string, not a detail URL)."""
    return "/m8flow/templates?" in response.url


def _search_gallery(page: Page, name: str) -> None:
    """Fill the gallery search input and wait for the filtered fetch to land.

    Thin wrapper over the shared ``search_templates`` helper so the debounced
    search-response wait stays in one place.
    """
    search_templates(page, name)


def _navigate_to_template_detail(page: Page, template_name: str) -> None:
    """Search for template in the Active gallery, click card to open detail page.

    Uses a hard navigation so the gallery remounts with default state (card
    view, Active tab) regardless of what a previous test left behind.
    """
    _go_to_active_tab(page)
    _search_gallery(page, template_name)
    card = page.get_by_test_id(f"template-card-{template_name}")
    expect(card).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    card.click()
    expect(page.get_by_test_id("template-export-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    wait_for_app_ready(page)


def _open_delete_dialog(page: Page, template_name: str) -> None:
    """Navigate to template detail and click delete — leaves dialog open."""
    _navigate_to_template_detail(page, template_name)
    delete_btn = page.get_by_test_id("template-delete-button")
    delete_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
    delete_btn.click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)


def _delete_template_from_detail(page: Page, template_name: str) -> None:
    """Delete a template from its detail page and wait for gallery redirect."""
    _open_delete_dialog(page, template_name)
    page.get_by_test_id("delete-template-confirm-button").click()
    # Wait for the gallery view-mode toggle, which only renders on the gallery page.
    # wait_for_url("/templates") would match the detail URL immediately (false positive).
    page.get_by_test_id("template-gallery-view-mode-toggle").wait_for(
        state="visible", timeout=NAV_TIMEOUT,
    )
    wait_for_app_ready(page)


def _go_to_deleted_tab(page: Page) -> None:
    """Hard-navigate to the templates gallery and switch to the Deleted tab.

    page.goto() forces a full remount (default card view / Active tab), then
    the Deleted toggle click is wrapped in expect_response so the deleted-only
    fetch lands before the caller searches.  Without this, the mode-change
    fetch and the search fetch race, and the slower unfiltered response can
    overwrite the filtered one (useTemplates has no request cancellation).
    """
    page.goto(f"{BASE_URL.rstrip('/')}/templates")
    wait_for_app_ready(page)
    deleted_tab = page.get_by_test_id("template-gallery-mode-deleted")
    deleted_tab.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    with page.expect_response(
        lambda r: _is_template_list_response(r) and "deleted_only=true" in r.url,
        timeout=PAGE_DATA_TIMEOUT,
    ):
        deleted_tab.click()
    wait_for_app_ready(page)


def _go_to_active_tab(page: Page) -> None:
    """Hard-navigate to the templates gallery (Active tab is the default).

    page.goto() forces a full remount so view mode resets to card and the tab
    resets to Active regardless of previous test state.  Waits for the mount
    fetch so subsequent searches don't race against it.
    """
    try:
        with page.expect_response(
            _is_template_list_response, timeout=PAGE_DATA_TIMEOUT
        ):
            page.goto(f"{BASE_URL.rstrip('/')}/templates")
    except PlaywrightTimeout:
        pass
    wait_for_app_ready(page)


def _open_row_menu(page: Page, template_name: str) -> None:
    """Switch to table view and open the more-actions menu for the named row.

    Targets the row by template name instead of `.first` so a stale row from a
    previous render (or junk data from old runs) is never clicked by mistake.
    """
    _switch_to_table_view(page)
    row = page.get_by_role("row").filter(has_text=template_name)
    more_btn = row.locator('[data-testid^="template-gallery-more-actions-"]').first
    more_btn.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    more_btn.click()


def _switch_to_table_view(page: Page) -> None:
    """Switch the gallery to table/list view."""
    table_btn = page.get_by_test_id("template-gallery-view-table")
    try:
        table_btn.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        table_btn.click()
        wait_for_app_ready(page)
    except PlaywrightTimeout:
        pass


def _restore_template_from_deleted_tab(page: Page, template_name: str) -> None:
    """Navigate to Deleted tab, search, and restore the named template.

    The more-actions button is scoped to the row containing *template_name*
    so the restore can never target a stale or unrelated deleted template.
    """
    _go_to_deleted_tab(page)
    _search_gallery(page, template_name)
    _open_row_menu(page, template_name)
    page.get_by_test_id("template-row-restore-action").click()
    expect(
        page.get_by_test_id("restore-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(
        page.get_by_test_id("restore-template-confirm-dialog")
    ).to_contain_text("will be restored and become active again.", timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("restore-template-confirm-button").click()
    expect(
        page.get_by_role("alert").filter(
            has_text=re.compile(r"restored successfully", re.I)
        ).first
    ).to_be_visible(timeout=NAV_TIMEOUT)
    wait_for_app_ready(page)


def _try_delete_template(page: Page, name: str) -> None:
    """Best-effort deletion regardless of template state.

    Uses SHORT_TIMEOUT existence probes so the cleanup loop stays fast when
    templates are already gone after a partial or failed test run.

    Flow:
    1. Navigate to Active gallery, search, probe for card (5 s).
       Found  → click through to detail and delete; return.
    2. Navigate to Deleted tab, search, probe for card (5 s).
       Found  → restore via more-actions, then delete from detail; return.
    3. Neither found → log and skip.
    """
    # -- Probe Active gallery --------------------------------------------------
    _go_to_active_tab(page)
    _search_gallery(page, name)
    card = page.get_by_test_id(f"template-card-{name}")
    try:
        card.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pass  # not in Active — check Deleted tab
    else:
        try:
            card.click()
            expect(page.get_by_test_id("template-export-button")).to_be_visible(
                timeout=PAGE_DATA_TIMEOUT
            )
            wait_for_app_ready(page)
            delete_btn = page.get_by_test_id("template-delete-button")
            delete_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
            expect(delete_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
            delete_btn.click()
            expect(
                page.get_by_test_id("delete-template-confirm-dialog")
            ).to_be_visible(timeout=ELEMENT_TIMEOUT)
            page.get_by_test_id("delete-template-confirm-button").click()
            page.get_by_test_id("template-gallery-view-mode-toggle").wait_for(
                state="visible", timeout=NAV_TIMEOUT
            )
            wait_for_app_ready(page)
            logger.info("CLEANUP: template '%s' deleted from Active gallery.", name)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "CLEANUP: found '%s' in Active but failed to delete it: %s", name, exc
            )

    # -- Probe Deleted tab -----------------------------------------------------
    _go_to_deleted_tab(page)
    _search_gallery(page, name)
    card = page.get_by_test_id(f"template-card-{name}")
    try:
        card.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        logger.info("CLEANUP: template '%s' not found in either tab — skipping.", name)
        return

    # Found in Deleted tab — restore then delete.
    try:
        _open_row_menu(page, name)
        page.get_by_test_id("template-row-restore-action").click()
        expect(
            page.get_by_test_id("restore-template-confirm-dialog")
        ).to_be_visible(timeout=ELEMENT_TIMEOUT)
        page.get_by_test_id("restore-template-confirm-button").click()
        expect(
            page.get_by_role("alert")
            .filter(has_text=re.compile(r"restored successfully", re.I))
            .first
        ).to_be_visible(timeout=NAV_TIMEOUT)
        wait_for_app_ready(page)
        _delete_template_from_detail(page, name)
        logger.info("CLEANUP: template '%s' restored and deleted.", name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "CLEANUP: failed to restore/delete '%s' from Deleted tab: %s", name, exc
        )


def _delete_source_pm(page: Page) -> None:
    """Delete the source process model stored in _STATE['pm_url']."""
    pm_url = _STATE.get("pm_url")
    if not pm_url:
        logger.warning("CLEANUP: pm_url not set — source PM was never created.")
        return
    try:
        page.goto(pm_url)
        wait_for_app_ready(page)
        more_btn = page.get_by_test_id("more-actions-button")
        more_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        more_btn.click()
        page.get_by_test_id("delete-process-model-menu-item").wait_for(
            state="visible", timeout=ELEMENT_TIMEOUT
        )
        page.get_by_test_id("delete-process-model-menu-item").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        dialog.get_by_role("button", name="Delete").click()
        wait_for_app_ready(page)
        logger.info("CLEANUP: source PM deleted (%s).", pm_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CLEANUP: could not delete source PM: %s", exc)


def _delete_pm_at_url(page: Page, pm_url: str, label: str = "PM") -> None:
    """Delete a process model at a known URL. Logs failures without raising."""
    try:
        page.goto(pm_url)
        wait_for_app_ready(page)
        more_btn = page.get_by_test_id("more-actions-button")
        more_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        more_btn.click()
        page.get_by_test_id("delete-process-model-menu-item").wait_for(
            state="visible", timeout=ELEMENT_TIMEOUT
        )
        page.get_by_test_id("delete-process-model-menu-item").click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        dialog.get_by_role("button", name="Delete").click()
        wait_for_app_ready(page)
        logger.info("CLEANUP: %s deleted (%s).", label, pm_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CLEANUP: could not delete %s (%s): %s", label, pm_url, exc)


def _delete_test_process_group(page: Page) -> None:
    """Delete the shared Test Process Group so it doesn't leak across runs.

    A leftover group (its identifier is fixed) makes the next run's setup try to
    re-create it, hit a duplicate-identifier rejection, and fail. Must run after
    the process models inside it are removed — the backend refuses to delete a
    non-empty group. Logs failures without raising.
    """
    group_url = f"{BASE_URL.rstrip('/')}/process-groups/{TEST_PROCESS_GROUP_ID}"
    try:
        page.goto(group_url)
        wait_for_app_ready(page)
        delete_btn = page.get_by_test_id("delete-process-group-button")
        delete_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        delete_btn.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        dialog.get_by_role("button", name="Delete").click()
        wait_for_app_ready(page)
        logger.info("CLEANUP: Test Process Group deleted (%s).", group_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "CLEANUP: could not delete Test Process Group (%s): %s", group_url, exc
        )


def _save_template_from_pm(
    page: Page,
    *,
    name: str,
    visibility: str = "TENANT",
) -> None:
    """Open Save-as-Template modal from the source PM and submit the form."""
    pm_url = _STATE.get("pm_url")
    if not pm_url:
        pytest.skip("Source PM URL not set — setup may have failed.")
    page.goto(pm_url)
    wait_for_app_ready(page)
    page.get_by_test_id("save-as-template-button").wait_for(
        state="visible", timeout=PAGE_DATA_TIMEOUT
    )
    page.get_by_test_id("save-as-template-button").click()
    expect(page.get_by_test_id("save-as-template-dialog")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    page.get_by_test_id("save-as-template-name-input").locator("input").fill(name)
    page.get_by_test_id("save-as-template-description-input").locator(
        "textarea"
    ).first.fill(_TEMPLATE_DESC)
    page.get_by_test_id("save-as-template-category-input").locator("input").fill(
        _TEMPLATE_CATEGORY
    )
    if visibility != "PRIVATE":
        page.get_by_test_id("save-as-template-visibility-select").click()
        page.locator(f'[role="option"][data-value="{visibility}"]').click()
        page.locator('[role="listbox"]').wait_for(state="hidden", timeout=SHORT_TIMEOUT)
    page.get_by_test_id("save-as-template-submit-button").click()
    expect(page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(page)


def _publish_template(page: Page, template_name: str) -> None:
    """Navigate to the template detail and click Publish."""
    _navigate_to_template_detail(page, template_name)
    page.get_by_test_id("template-publish-button").click()
    expect(
        page.get_by_text("Template published successfully.", exact=False)
    ).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.get_by_test_id("template-publish-button")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    wait_for_app_ready(page)


def _update_template_visibility(page: Page, template_name: str, visibility: str) -> None:
    """On the detail page, change the visibility and save.

    Only works on DRAFT templates — the visibility select is replaced by a
    read-only chip once the template is published.
    """
    _navigate_to_template_detail(page, template_name)
    vis_select = page.get_by_test_id("template-visibility-select")
    vis_select.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    vis_select.click()
    option = page.locator(f'[role="option"][data-value="{visibility}"]')
    option.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    option.click()
    page.locator('[role="listbox"]').wait_for(state="hidden", timeout=SHORT_TIMEOUT)
    save_btn = page.get_by_test_id("template-save-visibility-button")
    save_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    save_btn.click()
    expect(
        page.get_by_text("successfully", exact=False)
    ).to_be_visible(timeout=NAV_TIMEOUT)
    wait_for_app_ready(page)


# ---------------------------------------------------------------------------
# Setup – source PM + all three admin templates (all inside Test Process Group)
# ---------------------------------------------------------------------------


def test_setup_create_source_pm(page: Page) -> None:
    """Create the source process model used to generate admin test templates."""
    logger.info("SETUP 1: creating source PM '%s'.", _PM_DISPLAY_NAME)
    navigate_into_process_group(page)
    add_btn = page.get_by_test_id("add-process-model-button")
    add_btn.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    add_btn.click()
    wait_for_app_ready(page)
    page.get_by_test_id("process-model-display-name-input").locator("input").fill(
        _PM_DISPLAY_NAME
    )
    page.get_by_test_id("process-model-submit-button").click()
    expect(page.get_by_test_id("save-as-template-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(page)
    _STATE["pm_url"] = page.url.split("?", 1)[0]
    logger.info("SETUP 1 PASSED: source PM at %s.", _STATE["pm_url"])


def test_setup_create_draft_template(page: Page) -> None:
    """Admin saves source PM as a TENANT-visible draft template."""
    logger.info("SETUP 2: creating draft template '%s'.", _DRAFT_TEMPLATE_NAME)
    _save_template_from_pm(page, name=_DRAFT_TEMPLATE_NAME, visibility="TENANT")
    logger.info("SETUP 2 PASSED: draft template '%s' created.", _DRAFT_TEMPLATE_NAME)


def test_setup_create_and_publish_tenant_template(page: Page) -> None:
    """Admin creates a TENANT-visible template and publishes it."""
    logger.info(
        "SETUP 3: creating and publishing TENANT template '%s'.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _save_template_from_pm(
        page, name=_PUBLISHED_TENANT_TEMPLATE_NAME, visibility="TENANT"
    )
    _publish_template(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    logger.info(
        "SETUP 3 PASSED: TENANT template '%s' published.", _PUBLISHED_TENANT_TEMPLATE_NAME
    )


def test_setup_create_and_publish_public_template(page: Page) -> None:
    """Admin creates a TENANT draft, changes visibility to PUBLIC, then publishes.

    The visibility selector is only rendered while the template is still a draft
    (``!template.isPublished``), so the visibility must be updated before publishing.
    """
    logger.info(
        "SETUP 4: creating and publishing PUBLIC template '%s'.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _save_template_from_pm(
        page, name=_PUBLISHED_PUBLIC_TEMPLATE_NAME, visibility="TENANT"
    )
    _update_template_visibility(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME, "PUBLIC")
    _publish_template(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    logger.info(
        "SETUP 4 PASSED: PUBLIC template '%s' created and published.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )


# ---------------------------------------------------------------------------
# SECTION A – Admin sees enabled delete button on all template types
# ---------------------------------------------------------------------------


def test_admin_delete_button_visible_and_enabled(page: Page) -> None:
    """Admin user sees an enabled delete button on draft, TENANT, and PUBLIC templates."""
    logger.info("TEST 1: verifying admin delete button is enabled on all template types.")

    for template_name, label in (
        (_DRAFT_TEMPLATE_NAME, "draft"),
        (_PUBLISHED_TENANT_TEMPLATE_NAME, "TENANT published"),
        (_PUBLISHED_PUBLIC_TEMPLATE_NAME, "PUBLIC published"),
    ):
        _navigate_to_template_detail(page, template_name)
        delete_btn = page.get_by_test_id("template-delete-button")
        expect(delete_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
        expect(delete_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
        logger.info("  admin delete button enabled for %s template.", label)

    logger.info("TEST 1 PASSED: admin delete button enabled for all template types.")


# ---------------------------------------------------------------------------
# SECTION B – Editor permissions in list view (more-actions menu)
# ---------------------------------------------------------------------------


def test_editor_list_view_delete_disabled_tenant_template(
    editor_page: Page,
) -> None:
    """Editor sees the delete action disabled in the list view for a TENANT published template."""
    logger.info(
        "TEST 2: editor list view — delete disabled for TENANT template '%s'.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _go_to_active_tab(editor_page)
    _search_gallery(editor_page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    _open_row_menu(editor_page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    delete_action = editor_page.get_by_test_id("template-row-delete-action")
    expect(delete_action).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_action).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    editor_page.keyboard.press("Escape")
    wait_for_app_ready(editor_page)
    logger.info(
        "TEST 2 PASSED: editor list view delete disabled for TENANT template."
    )


def test_editor_list_view_delete_disabled_public_template(
    editor_page: Page,
) -> None:
    """Editor sees the delete action disabled in the list view for a PUBLIC published template."""
    logger.info(
        "TEST 3: editor list view — delete disabled for PUBLIC template '%s'.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _go_to_active_tab(editor_page)
    _search_gallery(editor_page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    _open_row_menu(editor_page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    delete_action = editor_page.get_by_test_id("template-row-delete-action")
    expect(delete_action).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_action).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    editor_page.keyboard.press("Escape")
    wait_for_app_ready(editor_page)
    logger.info(
        "TEST 3 PASSED: editor list view delete disabled for PUBLIC template."
    )


# ---------------------------------------------------------------------------
# SECTION C – Editor permissions on the detail page
# ---------------------------------------------------------------------------


def test_editor_detail_delete_disabled_tenant_template(
    editor_page: Page,
) -> None:
    """Editor sees the delete button disabled on the detail page of a TENANT published template."""
    logger.info(
        "TEST 4: editor detail page — delete disabled for TENANT template '%s'.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _navigate_to_template_detail(editor_page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    delete_btn = editor_page.get_by_test_id("template-delete-button")
    expect(delete_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    logger.info(
        "TEST 4 PASSED: editor detail delete disabled for TENANT template."
    )


def test_editor_detail_delete_disabled_public_template(
    editor_page: Page,
) -> None:
    """Editor sees the delete button disabled on the detail page of a PUBLIC published template."""
    logger.info(
        "TEST 5: editor detail page — delete disabled for PUBLIC template '%s'.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _navigate_to_template_detail(editor_page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    delete_btn = editor_page.get_by_test_id("template-delete-button")
    expect(delete_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    logger.info(
        "TEST 5 PASSED: editor detail delete disabled for PUBLIC template."
    )


# ---------------------------------------------------------------------------
# SECTION D – Delete confirmation dialog behaviour
# ---------------------------------------------------------------------------


def test_delete_confirmation_modal_appears(page: Page) -> None:
    """Clicking the delete button on a template detail page shows the confirm dialog."""
    logger.info("TEST 6: verifying delete confirmation dialog appears.")
    _navigate_to_template_detail(page, _DRAFT_TEMPLATE_NAME)
    page.get_by_test_id("template-delete-button").click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(
        page.get_by_test_id("delete-template-cancel-button")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(
        page.get_by_test_id("delete-template-confirm-button")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("delete-template-cancel-button").click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).not_to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("TEST 6 PASSED: delete confirmation dialog appears and closes.")


def test_draft_delete_dialog_shows_permanent_warning(page: Page) -> None:
    """The delete dialog for an unpublished template warns about permanent deletion."""
    logger.info("TEST 7: verifying draft delete dialog text.")
    _navigate_to_template_detail(page, _DRAFT_TEMPLATE_NAME)
    page.get_by_test_id("template-delete-button").click()
    dialog = page.get_by_test_id("delete-template-confirm-dialog")
    expect(dialog).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(dialog).to_contain_text("permanently deleted", timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("delete-template-cancel-button").click()
    logger.info(
        "TEST 7 PASSED: draft delete dialog contains 'permanently deleted'."
    )


def test_cancel_delete_keeps_template_active(page: Page) -> None:
    """Clicking Cancel on the delete dialog leaves the template unchanged."""
    logger.info("TEST 8: verifying cancel delete keeps template active.")
    _navigate_to_template_detail(page, _DRAFT_TEMPLATE_NAME)
    page.get_by_test_id("template-delete-button").click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("delete-template-cancel-button").click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).not_to_be_visible(timeout=ELEMENT_TIMEOUT)
    _go_to_active_tab(page)
    _search_gallery(page, _DRAFT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_DRAFT_TEMPLATE_NAME}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 8 PASSED: cancel delete leaves template in Active gallery.")


def test_published_delete_dialog_shows_soft_delete_message(page: Page) -> None:
    """The delete dialog for a published template explains it will be soft-deleted."""
    logger.info("TEST 9: verifying published delete dialog text.")
    _navigate_to_template_detail(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    page.get_by_test_id("template-delete-button").click()
    dialog = page.get_by_test_id("delete-template-confirm-dialog")
    expect(dialog).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(dialog).to_contain_text("soft-deleted", timeout=ELEMENT_TIMEOUT)
    expect(dialog).to_contain_text("Deleted tab", timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("delete-template-cancel-button").click()
    logger.info(
        "TEST 9 PASSED: published delete dialog contains soft-delete explanation."
    )


# ---------------------------------------------------------------------------
# SECTION E – Error handling (route mock)
# ---------------------------------------------------------------------------


def test_delete_failure_shows_error_message(page: Page) -> None:
    """When the delete API call fails with 500 the gallery shows an error alert."""
    logger.info("TEST 10: verifying error alert shown when delete API returns 500.")
    _go_to_active_tab(page)
    _search_gallery(page, _DRAFT_TEMPLATE_NAME)

    # Mock: let GET calls through but fail any DELETE on the templates endpoint.
    # TemplateService.deleteTemplate uses backendPath() which strips the /v1.0
    # prefix, so the real URL is {BACKEND_BASE_URL}/m8flow/templates/{id}.
    page.route(
        re.compile(r"/m8flow/templates/\d+"),
        lambda route: (
            route.fulfill(
                status=500,
                content_type="application/json",
                body='{"message": "Internal Server Error"}',
            )
            if route.request.method == "DELETE"
            else route.continue_()
        ),
    )

    _open_row_menu(page, _DRAFT_TEMPLATE_NAME)
    page.get_by_test_id("template-row-delete-action").click()
    expect(
        page.get_by_test_id("delete-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("delete-template-confirm-button").click()

    try:
        expect(
            page.get_by_role("alert")
            .filter(has_text=re.compile(r"fail|error|Internal", re.I))
            .first
        ).to_be_visible(timeout=NAV_TIMEOUT)
    finally:
        # Always remove the mock so it does not leak into subsequent tests.
        page.unroute_all(behavior="ignoreErrors")
    wait_for_app_ready(page)

    # Template must still exist in Active gallery after the failed delete.
    _go_to_active_tab(page)
    _search_gallery(page, _DRAFT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_DRAFT_TEMPLATE_NAME}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info(
        "TEST 10 PASSED: error alert shown; template still present after failed delete."
    )


# ---------------------------------------------------------------------------
# SECTION F – Delete and restore TENANT published template
# ---------------------------------------------------------------------------


def test_delete_tenant_published_template(page: Page) -> None:
    """Confirming delete on the TENANT published template soft-deletes it."""
    logger.info(
        "TEST 11: soft-deleting TENANT template '%s'.", _PUBLISHED_TENANT_TEMPLATE_NAME
    )
    _delete_template_from_detail(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    logger.info("TEST 11 PASSED: TENANT template deleted; redirected to gallery.")


def test_deleted_tenant_template_not_in_active_gallery(page: Page) -> None:
    """After soft-deletion the TENANT template is absent from the Active tab."""
    logger.info(
        "TEST 12: verifying '%s' absent from Active gallery.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _go_to_active_tab(page)
    _search_gallery(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_PUBLISHED_TENANT_TEMPLATE_NAME}")
    ).not_to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 12 PASSED: deleted TENANT template not in Active gallery.")


def test_deleted_tenant_template_visible_in_deleted_tab(page: Page) -> None:
    """After soft-deletion the TENANT template appears in the Deleted tab."""
    logger.info(
        "TEST 13: verifying '%s' visible in Deleted tab.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _go_to_deleted_tab(page)
    _search_gallery(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    # Soft delete renames the template to "<name>_deleted_<timestamp>" on the
    # backend, so match the card testid by prefix rather than exact name.
    expect(
        page.locator(
            f'[data-testid^="template-card-{_PUBLISHED_TENANT_TEMPLATE_NAME}"]'
        ).first
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 13 PASSED: soft-deleted TENANT template visible in Deleted tab.")


def test_restore_tenant_template_from_deleted_tab(page: Page) -> None:
    """Admin restores the soft-deleted TENANT template from the Deleted tab."""
    logger.info(
        "TEST 14: restoring TENANT template '%s' from Deleted tab.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _restore_template_from_deleted_tab(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    logger.info("TEST 14 PASSED: TENANT template restored from Deleted tab.")


def test_restored_tenant_template_in_active_gallery(page: Page) -> None:
    """After restoration the TENANT template is visible in the Active tab again."""
    logger.info(
        "TEST 15: verifying restored TENANT template '%s' in Active gallery.",
        _PUBLISHED_TENANT_TEMPLATE_NAME,
    )
    _go_to_active_tab(page)
    _search_gallery(page, _PUBLISHED_TENANT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_PUBLISHED_TENANT_TEMPLATE_NAME}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 15 PASSED: restored TENANT template visible in Active gallery.")


# ---------------------------------------------------------------------------
# SECTION G – Delete and restore PUBLIC published template
# ---------------------------------------------------------------------------


def test_delete_public_published_template(page: Page) -> None:
    """Confirming delete on the PUBLIC published template soft-deletes it."""
    logger.info(
        "TEST 16: soft-deleting PUBLIC template '%s'.", _PUBLISHED_PUBLIC_TEMPLATE_NAME
    )
    _delete_template_from_detail(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    logger.info("TEST 16 PASSED: PUBLIC template deleted; redirected to gallery.")


def test_deleted_public_template_not_in_active_gallery(page: Page) -> None:
    """After soft-deletion the PUBLIC template is absent from the Active tab."""
    logger.info(
        "TEST 17: verifying '%s' absent from Active gallery.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _go_to_active_tab(page)
    _search_gallery(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_PUBLISHED_PUBLIC_TEMPLATE_NAME}")
    ).not_to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 17 PASSED: deleted PUBLIC template not in Active gallery.")


def test_deleted_public_template_visible_in_deleted_tab(page: Page) -> None:
    """After soft-deletion the PUBLIC template appears in the Deleted tab."""
    logger.info(
        "TEST 18: verifying '%s' visible in Deleted tab.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _go_to_deleted_tab(page)
    _search_gallery(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    # Soft delete renames the template to "<name>_deleted_<timestamp>" on the
    # backend, so match the card testid by prefix rather than exact name.
    expect(
        page.locator(
            f'[data-testid^="template-card-{_PUBLISHED_PUBLIC_TEMPLATE_NAME}"]'
        ).first
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 18 PASSED: soft-deleted PUBLIC template visible in Deleted tab.")


def test_restore_public_template_from_deleted_tab(page: Page) -> None:
    """Admin restores the soft-deleted PUBLIC template from the Deleted tab."""
    logger.info(
        "TEST 19: restoring PUBLIC template '%s' from Deleted tab.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _restore_template_from_deleted_tab(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    logger.info("TEST 19 PASSED: PUBLIC template restored from Deleted tab.")


def test_restored_public_template_in_active_gallery(page: Page) -> None:
    """After restoration the PUBLIC template is visible in the Active tab again."""
    logger.info(
        "TEST 20: verifying restored PUBLIC template '%s' in Active gallery.",
        _PUBLISHED_PUBLIC_TEMPLATE_NAME,
    )
    _go_to_active_tab(page)
    _search_gallery(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_PUBLISHED_PUBLIC_TEMPLATE_NAME}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 20 PASSED: restored PUBLIC template visible in Active gallery.")


# ---------------------------------------------------------------------------
# SECTION H – Draft permanent delete
# ---------------------------------------------------------------------------


def test_delete_draft_template_permanently(page: Page) -> None:
    """Deleting an unpublished draft template removes it permanently."""
    logger.info(
        "TEST 21: permanently deleting draft template '%s'.", _DRAFT_TEMPLATE_NAME
    )
    _delete_template_from_detail(page, _DRAFT_TEMPLATE_NAME)
    logger.info("TEST 21 PASSED: draft template deleted and redirected to gallery.")


def test_permanently_deleted_draft_absent_from_all_tabs(page: Page) -> None:
    """A permanently deleted draft does not appear in Active or Deleted tabs."""
    logger.info(
        "TEST 22: verifying draft '%s' absent from both gallery tabs.",
        _DRAFT_TEMPLATE_NAME,
    )
    _go_to_active_tab(page)
    _search_gallery(page, _DRAFT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_DRAFT_TEMPLATE_NAME}")
    ).not_to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    _go_to_deleted_tab(page)
    _search_gallery(page, _DRAFT_TEMPLATE_NAME)
    expect(
        page.get_by_test_id(f"template-card-{_DRAFT_TEMPLATE_NAME}")
    ).not_to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info(
        "TEST 22 PASSED: permanently deleted draft absent from all gallery tabs."
    )


# ---------------------------------------------------------------------------
# SECTION I – Editor capability: own template lifecycle
#
# The editor creates their own PM inside the shared Test Process Group,
# saves it as a template, and exercises all delete permission paths:
#   • Draft mode  → editor CAN delete their own draft (list view + detail page)
#   • Published   → editor CANNOT delete a published template (list view + detail)
#   • Admin soft-deletes the published template ("unpublishes" it from the
#     active gallery) to end the lifecycle.
# ---------------------------------------------------------------------------


def test_editor_creates_own_pm(editor_page: Page) -> None:
    """Editor creates a process model inside the shared Test Process Group."""
    logger.info(
        "TEST 23 (EDITOR SETUP): editor creating PM '%s'.", _EDITOR_PM_DISPLAY_NAME
    )
    # Use the shared Test Process Group — accessible to all roles, so the editor
    # can see add-process-model-button without needing explicit group permissions.
    navigate_into_process_group(editor_page)
    add_btn = editor_page.get_by_test_id("add-process-model-button")
    add_btn.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    add_btn.click()
    wait_for_app_ready(editor_page)
    editor_page.get_by_test_id("process-model-display-name-input").locator(
        "input"
    ).fill(_EDITOR_PM_DISPLAY_NAME)
    editor_page.get_by_test_id("process-model-submit-button").click()
    expect(editor_page.get_by_test_id("save-as-template-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(editor_page)
    _STATE["editor_pm_url"] = editor_page.url.split("?", 1)[0]
    logger.info(
        "TEST 23 PASSED: editor PM created at %s.", _STATE["editor_pm_url"]
    )


def test_editor_saves_pm_as_draft_template(editor_page: Page) -> None:
    """Editor saves their PM as a TENANT-visible draft template."""
    logger.info(
        "TEST 24 (EDITOR SETUP): editor saving PM as draft template '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    editor_pm_url = _STATE.get("editor_pm_url")
    if not editor_pm_url:
        pytest.skip("Editor PM URL not set — TEST 23 may have failed.")
    editor_page.goto(editor_pm_url)
    wait_for_app_ready(editor_page)
    editor_page.get_by_test_id("save-as-template-button").wait_for(
        state="visible", timeout=PAGE_DATA_TIMEOUT
    )
    editor_page.get_by_test_id("save-as-template-button").click()
    expect(editor_page.get_by_test_id("save-as-template-dialog")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    editor_page.get_by_test_id("save-as-template-name-input").locator("input").fill(
        _EDITOR_TEMPLATE_NAME
    )
    editor_page.get_by_test_id("save-as-template-description-input").locator(
        "textarea"
    ).first.fill(_TEMPLATE_DESC)
    editor_page.get_by_test_id("save-as-template-category-input").locator(
        "input"
    ).fill(_TEMPLATE_CATEGORY)
    # TENANT visibility (default)
    editor_page.get_by_test_id("save-as-template-visibility-select").click()
    editor_page.locator('[role="option"][data-value="TENANT"]').click()
    editor_page.locator('[role="listbox"]').wait_for(
        state="hidden", timeout=SHORT_TIMEOUT
    )
    editor_page.get_by_test_id("save-as-template-submit-button").click()
    expect(editor_page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(editor_page)
    logger.info(
        "TEST 24 PASSED: editor draft template '%s' created.", _EDITOR_TEMPLATE_NAME
    )


def test_editor_can_delete_own_draft_list_view(editor_page: Page) -> None:
    """Editor sees the delete action ENABLED in the list view for their own draft template."""
    logger.info(
        "TEST 25: editor list view — delete ENABLED for own draft '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    _go_to_active_tab(editor_page)
    _search_gallery(editor_page, _EDITOR_TEMPLATE_NAME)
    _open_row_menu(editor_page, _EDITOR_TEMPLATE_NAME)
    delete_action = editor_page.get_by_test_id("template-row-delete-action")
    expect(delete_action).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_action).to_be_enabled(timeout=ELEMENT_TIMEOUT)
    # Close menu without deleting — template is needed for subsequent tests.
    editor_page.keyboard.press("Escape")
    wait_for_app_ready(editor_page)
    logger.info(
        "TEST 25 PASSED: editor list view delete enabled for own draft."
    )


def test_editor_can_delete_own_draft_detail_page(editor_page: Page) -> None:
    """Editor sees the delete button ENABLED on the detail page of their own draft template."""
    logger.info(
        "TEST 26: editor detail page — delete ENABLED for own draft '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    _navigate_to_template_detail(editor_page, _EDITOR_TEMPLATE_NAME)
    delete_btn = editor_page.get_by_test_id("template-delete-button")
    expect(delete_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
    # Do NOT delete — template is needed for publish tests.
    logger.info(
        "TEST 26 PASSED: editor detail delete enabled for own draft."
    )


def test_editor_publishes_own_template(editor_page: Page) -> None:
    """Editor publishes their own template."""
    logger.info(
        "TEST 27: editor publishing template '%s'.", _EDITOR_TEMPLATE_NAME
    )
    _publish_template(editor_page, _EDITOR_TEMPLATE_NAME)
    logger.info(
        "TEST 27 PASSED: editor template '%s' published.", _EDITOR_TEMPLATE_NAME
    )


def test_editor_cannot_delete_own_published_list_view(editor_page: Page) -> None:
    """After publishing, the editor's delete action is DISABLED in the list view."""
    logger.info(
        "TEST 28: editor list view — delete DISABLED for own published template '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    _go_to_active_tab(editor_page)
    _search_gallery(editor_page, _EDITOR_TEMPLATE_NAME)
    _open_row_menu(editor_page, _EDITOR_TEMPLATE_NAME)
    delete_action = editor_page.get_by_test_id("template-row-delete-action")
    expect(delete_action).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_action).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    editor_page.keyboard.press("Escape")
    wait_for_app_ready(editor_page)
    logger.info(
        "TEST 28 PASSED: editor list view delete disabled for own published template."
    )


def test_editor_cannot_delete_own_published_detail_page(editor_page: Page) -> None:
    """After publishing, the editor's delete button is DISABLED on the detail page."""
    logger.info(
        "TEST 29: editor detail page — delete DISABLED for own published template '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    _navigate_to_template_detail(editor_page, _EDITOR_TEMPLATE_NAME)
    delete_btn = editor_page.get_by_test_id("template-delete-button")
    expect(delete_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_disabled(timeout=ELEMENT_TIMEOUT)
    logger.info(
        "TEST 29 PASSED: editor detail delete disabled for own published template."
    )


def test_admin_soft_deletes_editor_published_template(page: Page) -> None:
    """Admin soft-deletes (unpublishes from the active gallery) the editor's published template."""
    logger.info(
        "TEST 30: admin soft-deleting editor's published template '%s'.",
        _EDITOR_TEMPLATE_NAME,
    )
    _delete_template_from_detail(page, _EDITOR_TEMPLATE_NAME)
    logger.info(
        "TEST 30 PASSED: editor's published template soft-deleted (moved to Deleted tab)."
    )


def test_editor_template_visible_in_deleted_tab(page: Page) -> None:
    """After admin soft-delete, the editor's template appears in the Deleted tab."""
    logger.info(
        "TEST 31: verifying editor's template '%s' in Deleted tab.",
        _EDITOR_TEMPLATE_NAME,
    )
    _go_to_deleted_tab(page)
    _search_gallery(page, _EDITOR_TEMPLATE_NAME)
    # Soft delete renames the template to "<name>_deleted_<timestamp>" on the
    # backend, so match the card testid by prefix rather than exact name.
    expect(
        page.locator(
            f'[data-testid^="template-card-{_EDITOR_TEMPLATE_NAME}"]'
        ).first
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("TEST 31 PASSED: editor's template visible in Deleted tab.")


# ---------------------------------------------------------------------------
# Cleanup – delete ALL created data
#
# Each step is independent: a failure in one step does not prevent the others.
#   Step 1 – editor's template (in Deleted tab after TEST 30)
#   Step 2 – TENANT published template (in Active after TEST 15 restore)
#   Step 3 – PUBLIC published template (in Active after TEST 20 restore)
#   Step 4 – draft template (may already be gone after TEST 21)
#   Step 5 – editor's PM (created in shared Test Process Group; admin deletes)
#   Step 6 – admin source PM
# ---------------------------------------------------------------------------


def test_cleanup(page: Page) -> None:
    """Delete every template and process model / group created by this module."""
    logger.info("TEST CLEANUP: removing all data created by this module.")

    # Step 1: editor's template (likely in Deleted tab; _try_delete_template handles it).
    _try_delete_template(page, _EDITOR_TEMPLATE_NAME)

    # Step 2: TENANT published template (restored in TEST 15 → Active gallery).
    _try_delete_template(page, _PUBLISHED_TENANT_TEMPLATE_NAME)

    # Step 3: PUBLIC published template (restored in TEST 20 → Active gallery).
    _try_delete_template(page, _PUBLISHED_PUBLIC_TEMPLATE_NAME)

    # Step 4: draft template (may already be gone if TEST 21 passed).
    _try_delete_template(page, _DRAFT_TEMPLATE_NAME)

    # Step 5: editor's process model.
    editor_pm_url = _STATE.get("editor_pm_url")
    if editor_pm_url:
        _delete_pm_at_url(page, editor_pm_url, label="editor PM")

    # Step 6: admin source process model.
    _delete_source_pm(page)

    # Step 7: the shared Test Process Group is now empty — remove it so it does
    # not leak across runs and break the next run's setup with a duplicate create.
    _delete_test_process_group(page)

    logger.info("TEST CLEANUP DONE.")
