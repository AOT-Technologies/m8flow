"""Full E2E coverage for the 'Save as Template' feature on the Process Model page.
"""

from __future__ import annotations

import logging
import re
from typing import Generator

import pytest
from faker import Faker as _Faker
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    ELEMENT_TIMEOUT,
    NAV_TIMEOUT,
    PAGE_DATA_TIMEOUT,
    SHORT_TIMEOUT,
)
from helpers.process_group_setup import navigate_into_process_group
from helpers.templates import navigate_to_templates
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Single shared session – ALL tests in this file use this one fixture.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def page(editor_page: Page) -> Generator[Page, None, None]:  # type: ignore[override]
    """Module-scoped editor session shared by every test in this file.
    """
    yield editor_page


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------
_fake = _Faker()
# Unique names/IDs per run — prevents conflicts if a previous run's cleanup failed.
_TEMPLATE_NAME = f"{_fake.first_name()} Template Automation"
_PM_DISPLAY_NAME = f"{_fake.last_name()} Process Automation"
_PM_FROM_TEMPLATE_ID = f"tpl-from-tpl-{_fake.lexify('????').lower()}"

_TEMPLATE_DESC = "Created by browser automation for Save-as-Template E2E coverage."
_TEMPLATE_CATEGORY = "Automation"
_TEMPLATE_TAGS = "e2e, automation"

# Shared state across tests in this module.
_STATE: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _navigate_to_source_pm(page: Page) -> None:
    """Navigate to the source process model and wait for the page to settle."""
    pm_url = _STATE.get("pm_url")
    if not pm_url:
        pytest.skip("Source PM URL not set — setup test may have failed.")
    page.goto(pm_url)
    wait_for_app_ready(page)
    page.get_by_test_id("save-as-template-button").wait_for(
        state="visible", timeout=PAGE_DATA_TIMEOUT
    )


def _navigate_to_template_detail(page: Page, template_name: str) -> None:
    """Search for template by name in the gallery, then click into its detail page."""
    navigate_to_templates(page)
    wait_for_app_ready(page)

    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    search_input.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    search_input.fill(template_name)
    wait_for_app_ready(page)

    card_title = page.get_by_test_id(f"template-card-{template_name}")
    expect(card_title).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    card_title.click()
    expect(page.get_by_test_id("template-export-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    wait_for_app_ready(page)


def _open_save_as_template_modal(page: Page) -> None:
    """Navigate to the source PM and open the Save-as-Template dialog."""
    _navigate_to_source_pm(page)
    page.get_by_test_id("save-as-template-button").click()
    expect(page.get_by_test_id("save-as-template-dialog")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )


def _fill_template_form(
    page: Page,
    *,
    name: str = "",
    description: str = "",
    category: str = "",
    tags: str = "",
    visibility: str = "PRIVATE",
) -> None:
    """Fill fields in the Save-as-Template dialog."""
    if name:
        page.get_by_test_id("save-as-template-name-input").locator("input").fill(name)
    if description:
        page.get_by_test_id("save-as-template-description-input").locator(
            "textarea"
        ).first.fill(description)
    if category:
        page.get_by_test_id("save-as-template-category-input").locator("input").fill(
            category
        )
    if tags:
        page.get_by_test_id("save-as-template-tags-input").locator("input").fill(tags)
    if visibility != "PRIVATE":
        page.get_by_test_id("save-as-template-visibility-select").click()
        page.locator(f'[role="option"][data-value="{visibility}"]').click()
        # Wait for the dropdown to fully close before continuing.
        page.locator('[role="listbox"]').wait_for(state="hidden", timeout=SHORT_TIMEOUT)


def _delete_process_model_at_url(page: Page, pm_url: str) -> None:
    """Navigate to the given process model URL and delete it via the actions menu.
    """
    page.goto(pm_url)
    wait_for_app_ready(page)
    more_btn = page.get_by_test_id("more-actions-button")
    more_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    more_btn.click()
    delete_item = page.get_by_test_id("delete-process-model-menu-item")
    delete_item.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    delete_item.click()
    # useConfirmationDialog renders the confirm button with confirmText=t('delete') — "Delete".
    # Scope to the dialog to avoid matching other buttons on the page.
    dialog = page.get_by_role("dialog")
    dialog.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    dialog.get_by_role("button", name="Delete").click()
    wait_for_app_ready(page)


# ---------------------------------------------------------------------------
# Setup – create the source process model (runs first)
# ---------------------------------------------------------------------------


def test_setup_create_source_process_model(page: Page) -> None:
    """Create the process model that will be used as the template source."""
    logger.info("SETUP: navigating into Test Process Group to create source PM.")
    navigate_into_process_group(page)

    add_btn = page.get_by_test_id("add-process-model-button")
    add_btn.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    add_btn.click()
    wait_for_app_ready(page)

    page.get_by_test_id("process-model-display-name-input").locator("input").fill(
        _PM_DISPLAY_NAME
    )

    page.get_by_test_id("process-model-submit-button").click()
    # Wait for the PM show page — save-as-template-button is only rendered there.
    # NAV_TIMEOUT covers the backend create + frontend redirect (~1-2 s typical).
    expect(page.get_by_test_id("save-as-template-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(page)

    _STATE["pm_url"] = page.url.split("?", 1)[0]
    logger.info("SETUP PASSED: Source PM created at %s", _STATE["pm_url"])


# ---------------------------------------------------------------------------
# 1 – button visible for editor
# ---------------------------------------------------------------------------


def test_save_as_template_button_visible_for_editor(page: Page) -> None:
    """Editor user sees the 'Save as Template' button on the process model page."""
    logger.info("TEST 1: checking Save-as-Template button visibility for editor.")
    _navigate_to_source_pm(page)
    expect(page.get_by_test_id("save-as-template-button")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info("TEST 1 PASSED: save-as-template-button is visible for editor on process model page.")


# ---------------------------------------------------------------------------
# 2 – modal opens and shows all fields + all three visibility options
# ---------------------------------------------------------------------------


def test_save_as_template_modal_opens(page: Page) -> None:
    """The dialog opens with all form fields and all three visibility options."""
    logger.info("TEST 2: opening Save-as-Template modal and checking all fields.")
    _open_save_as_template_modal(page)

    expect(page.get_by_test_id("save-as-template-name-input")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_test_id("save-as-template-description-input")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_test_id("save-as-template-category-input")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_test_id("save-as-template-tags-input")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_test_id("save-as-template-submit-button")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )

    # Verify all three visibility options are present in the select.
    page.get_by_test_id("save-as-template-visibility-select").click()
    for value in ("PRIVATE", "TENANT", "PUBLIC"):
        expect(page.locator(f'[role="option"][data-value="{value}"]')).to_be_visible(
            timeout=SHORT_TIMEOUT
        )
    page.keyboard.press("Escape")
    page.locator('[role="listbox"]').wait_for(state="hidden", timeout=SHORT_TIMEOUT)

    page.get_by_test_id("save-as-template-cancel-button").click()
    expect(page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    wait_for_app_ready(page)
    logger.info(
        "TEST 2 PASSED: modal opened with all fields; PRIVATE/TENANT/PUBLIC options visible; cancel closed dialog."
    )


# ---------------------------------------------------------------------------
# 3 – required field validation
# ---------------------------------------------------------------------------


def test_save_as_template_required_fields_validation(page: Page) -> None:
    """Submitting with an empty name shows the 'Name is required' error alert."""
    logger.info("TEST 3: verifying required-field validation (empty name).")
    _open_save_as_template_modal(page)

    page.get_by_test_id("save-as-template-submit-button").click()

    error_alert = page.get_by_test_id("save-as-template-error-alert")
    expect(error_alert).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(error_alert).to_contain_text("Name is required")

    page.get_by_test_id("save-as-template-cancel-button").click()
    expect(page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    wait_for_app_ready(page)
    logger.info("TEST 3 PASSED: empty-name submission shows 'Name is required' error alert.")


# ---------------------------------------------------------------------------
# 4 – cancel flow
# ---------------------------------------------------------------------------


def test_save_as_template_cancel_flow(page: Page) -> None:
    """Filling the form then cancelling closes the dialog without creating a template."""
    logger.info("TEST 4: verifying cancel flow — fill name then cancel.")
    _open_save_as_template_modal(page)

    page.get_by_test_id("save-as-template-name-input").locator("input").fill(
        "This template should not be saved"
    )
    page.get_by_test_id("save-as-template-cancel-button").click()

    expect(page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    wait_for_app_ready(page)
    # Confirm we stayed on the process model page (button still visible).
    expect(page.get_by_test_id("save-as-template-button")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info(
        "TEST 4 PASSED: cancel closed the dialog; process model page still showing."
    )


# ---------------------------------------------------------------------------
# 5 – save with all valid fields (TENANT visibility)
# ---------------------------------------------------------------------------


def test_save_as_template_with_valid_details(page: Page) -> None:
    """Saving with name, description, category, comma-separated tags and TENANT
    visibility creates the template and closes the dialog."""
    logger.info(
        "TEST 5: creating template '%s' with all fields (TENANT visibility).",
        _TEMPLATE_NAME,
    )
    _open_save_as_template_modal(page)

    _fill_template_form(
        page,
        name=_TEMPLATE_NAME,
        description=_TEMPLATE_DESC,
        category=_TEMPLATE_CATEGORY,
        tags=_TEMPLATE_TAGS,
        visibility="TENANT",
    )
    page.get_by_test_id("save-as-template-submit-button").click()

    # Wait for dialog to close — file fetching + upload can be slow.
    expect(page.get_by_test_id("save-as-template-dialog")).not_to_be_visible(
        timeout=NAV_TIMEOUT
    )
    wait_for_app_ready(page)
    logger.info("TEST 5 PASSED: template '%s' created; modal closed.", _TEMPLATE_NAME)


# ---------------------------------------------------------------------------
# 6 – template appears in gallery
# ---------------------------------------------------------------------------


def test_template_appears_in_gallery(page: Page) -> None:
    """Search for the newly created template in the gallery and verify it appears."""
    logger.info("TEST 6: searching for template '%s' in gallery.", _TEMPLATE_NAME)
    navigate_to_templates(page)
    wait_for_app_ready(page)

    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    search_input.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    search_input.fill(_TEMPLATE_NAME)
    wait_for_app_ready(page)

    expect(page.get_by_test_id(f"template-card-{_TEMPLATE_NAME}")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    logger.info("TEST 6 PASSED: template card '%s' found via search.", _TEMPLATE_NAME)


# ---------------------------------------------------------------------------
# 7 – gallery card shows all added properties
# ---------------------------------------------------------------------------


def test_template_gallery_shows_all_properties(page: Page) -> None:
    """The gallery card displays name, description, category chip, tag chips and
    the TENANT visibility label."""
    logger.info("TEST 7: verifying gallery card shows all template properties.")
    navigate_to_templates(page)
    wait_for_app_ready(page)

    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    search_input.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    search_input.fill(_TEMPLATE_NAME)
    wait_for_app_ready(page)

    name_label = page.get_by_test_id(f"template-card-{_TEMPLATE_NAME}")
    expect(name_label).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(name_label).to_have_text(_TEMPLATE_NAME)

    # Description (first 40 chars — cards may truncate long descriptions).
    expect(
        page.get_by_text(_TEMPLATE_DESC[:40], exact=False).first
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)

    # Category chip: "Category: Automation"
    expect(
        page.get_by_text(f"Category: {_TEMPLATE_CATEGORY}", exact=False).first
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)

    # Tag chips (comma-split "e2e, automation" → two chips).
    expect(page.get_by_text("e2e", exact=True).first).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_text("automation", exact=True).first).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )

    # Visibility chip: t("tenant") = "Tenant" in English.
    expect(page.get_by_text("Tenant", exact=True).first).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info(
        "TEST 7 PASSED: gallery card shows name, description, category, tags and visibility."
    )


# ---------------------------------------------------------------------------
# 8 – template includes BPMN files
# ---------------------------------------------------------------------------


def test_template_has_bpmn_files(page: Page) -> None:
    """The template detail page shows a file list with at least one .bpmn entry."""
    logger.info("TEST 8: verifying template detail page lists BPMN files.")
    _navigate_to_template_detail(page, _TEMPLATE_NAME)

    expect(page.get_by_test_id("template-file-list-table")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    bpmn_rows = page.locator('[data-testid^="template-file-row-"][data-testid$=".bpmn"]')
    expect(bpmn_rows.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("TEST 8 PASSED: BPMN file row present in template detail.")


# ---------------------------------------------------------------------------
# 9 – template metadata on detail page
# ---------------------------------------------------------------------------


def test_template_metadata_on_detail_page(page: Page) -> None:
    """The template modeler page shows name, description excerpt, category chip and
    the editable visibility select (template is still a draft at this point)."""
    logger.info("TEST 9: verifying template metadata on detail page.")
    _navigate_to_template_detail(page, _TEMPLATE_NAME)

    expect(page.get_by_text(_TEMPLATE_NAME, exact=True).first).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(
        page.get_by_text(_TEMPLATE_DESC[:40], exact=False).first
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(
        page.get_by_text(f"Category: {_TEMPLATE_CATEGORY}", exact=False).first
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    # Draft templates show an editable visibility select, not a read-only chip.
    expect(page.get_by_test_id("template-visibility-select")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info(
        "TEST 9 PASSED: name, description, category and visibility select visible on detail page."
    )


# ---------------------------------------------------------------------------
# 10 – create process model from published template
# ---------------------------------------------------------------------------


def test_create_process_model_from_template(page: Page) -> None:
    """Publish the template then create a new process model from it.
    """
    logger.info("TEST 11: publishing template and creating process model from it.")
    _navigate_to_template_detail(page, _TEMPLATE_NAME)

    # Must be disabled on a draft template.
    create_btn = page.get_by_test_id("template-create-process-model-button")
    expect(create_btn).to_be_disabled(timeout=ELEMENT_TIMEOUT)

    # Publish.
    page.get_by_test_id("template-publish-button").click()
    expect(
        page.get_by_text("Template published successfully.", exact=False)
    ).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.get_by_test_id("template-publish-button")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    _STATE["template_published"] = "true"
    logger.info("Template published; 'Create Process Model' button should now be enabled.")

    # Now enabled.
    expect(create_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
    create_btn.click()

    dialog = page.get_by_test_id("create-process-model-from-template-dialog")
    expect(dialog).to_be_visible(timeout=ELEMENT_TIMEOUT)

    # Select the Test Process Group via Autocomplete.
    group_input = (
        page.get_by_test_id("create-from-template-group-select").locator("input")
    )
    group_input.fill("Test Process Group")
    page.get_by_role("option", name=re.compile(r"Test Process Group", re.I)).first.click()

    # Overwrite the auto-generated process model identifier with a unique ID.
    # fill() replaces the entire input content without needing a prior select-all.
    id_input = page.get_by_test_id("create-from-template-id-input").locator("input")
    

    page.get_by_test_id("create-from-template-submit-button").click()

    # TemplateModelerPage navigates to the new PM after ~1.5 s delay.
    page.wait_for_url(re.compile(r"/process-models/"), timeout=NAV_TIMEOUT)
    wait_for_app_ready(page)
    _STATE["pm_from_template_url"] = page.url.split("?", 1)[0]
    logger.info(
        "TEST 11 PASSED: process model from template created at %s",
        _STATE["pm_from_template_url"],
    )


# ---------------------------------------------------------------------------
# 12 – provenance link on the process model created from the template
# ---------------------------------------------------------------------------


def test_provenance_link_on_process_model_from_template(page: Page) -> None:
    """A process model created from a template shows a provenance link referencing
    the source template name."""
    logger.info("TEST 12: verifying provenance link on process model created from template.")
    pm_url = _STATE.get("pm_from_template_url")
    if not pm_url:
        pytest.skip(
            "PM-from-template URL not recorded — "
            "test_create_process_model_from_template may have failed."
        )

    page.goto(pm_url)
    wait_for_app_ready(page)

    provenance = page.get_by_test_id("template-provenance-link")
    expect(provenance).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(provenance).to_contain_text(_TEMPLATE_NAME)
    logger.info(
        "TEST 12 PASSED: provenance link visible and references '%s'.", _TEMPLATE_NAME
    )


# ---------------------------------------------------------------------------
# 13 – delete the template from the template page
# ---------------------------------------------------------------------------


def test_delete_created_template(default_admin_page: Page) -> None:
    """Delete the template created in test 5 using the default admin session (admin/admin).
    """
    logger.info(
        "TEST 13: deleting template '%s' as default admin.", _TEMPLATE_NAME
    )
    _navigate_to_template_detail(default_admin_page, _TEMPLATE_NAME)

    delete_btn = default_admin_page.get_by_test_id("template-delete-button")
    delete_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    expect(delete_btn).to_be_enabled(timeout=ELEMENT_TIMEOUT)
    delete_btn.click()

    expect(
        default_admin_page.get_by_test_id("delete-template-confirm-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    default_admin_page.get_by_test_id("delete-template-confirm-button").click()
    wait_for_app_ready(default_admin_page)

    # Confirm the card is gone from the gallery.
    navigate_to_templates(default_admin_page)
    wait_for_app_ready(default_admin_page)
    expect(
        default_admin_page.get_by_test_id(f"template-card-{_TEMPLATE_NAME}")
    ).not_to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    _STATE["template_deleted"] = "true"
    logger.info(
        "TEST 13 PASSED: template '%s' deleted by admin; card no longer in gallery.",
        _TEMPLATE_NAME,
    )


# ---------------------------------------------------------------------------
# Cleanup – delete process models (runs last)
# ---------------------------------------------------------------------------


def test_cleanup(page: Page) -> None:
    """Delete both process models created during this session.
    Step 1 — source PM: the process model created in setup and used to save as a template.
    Step 2 — PM from template: the process model created from the published template in TEST 11.
    """
    logger.info("TEST CLEANUP: starting — will delete source PM then PM-from-template.")

    # Step 1: delete the source process model (created in setup, used to save as template).
    pm_url = _STATE.get("pm_url")
    if pm_url:
        try:
            _delete_process_model_at_url(page, pm_url)
            logger.info("CLEANUP STEP 1 PASSED: source PM deleted (%s).", pm_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CLEANUP STEP 1 FAILED: could not delete source PM: %s", exc)
    else:
        logger.warning("CLEANUP STEP 1 SKIPPED: pm_url not set — setup test may have failed.")

    # Step 2: delete the process model created from the template (TEST 11).
    pm_from_template_url = _STATE.get("pm_from_template_url")
    if pm_from_template_url:
        try:
            _delete_process_model_at_url(page, pm_from_template_url)
            logger.info(
                "CLEANUP STEP 2 PASSED: PM-from-template deleted (%s).", pm_from_template_url
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "CLEANUP STEP 2 FAILED: could not delete PM-from-template: %s", exc
            )
    else:
        logger.warning(
            "CLEANUP STEP 2 SKIPPED: pm_from_template_url not set — TEST 11 may have failed."
        )

    logger.info("TEST CLEANUP DONE.")
