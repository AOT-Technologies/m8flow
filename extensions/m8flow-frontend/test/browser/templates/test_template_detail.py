"""Template detail (modeler) page: metadata, files, export, publish, versions, import, visibility."""

import logging
import re
import zipfile
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.mocks import MOCK_TEMPLATE_V2
from helpers.templates import navigate_to_templates

logger = logging.getLogger(__name__)


def _open_template_by_id(page: Page, template_id: int) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/templates/{template_id}")
    expect(page.get_by_test_id("template-export-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )


def test_template_detail_page_loads(mocked_templates_page: Page) -> None:
    """Detail page shows export, template name, and stays on the template route."""
    logger.info("test_template_detail_page_loads: open template 1 from gallery")
    page = mocked_templates_page
    navigate_to_templates(page)
    page.get_by_test_id("template-card-1").click()

    expect(page.get_by_test_id("template-export-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    expect(page.get_by_text("Private Test Template", exact=False).first).to_be_visible()
    expect(page).to_have_url(re.compile(r"/templates/1"))
    logger.info("Template Details route and title verified")


def test_template_files_section_and_view(mocked_templates_page: Page) -> None:
    """Files table lists BPMN/JSON; view opens the file route (diagram or form)."""
    logger.info("open template 1, assert files, open BPMN viewer")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    expect(page.get_by_test_id("template-file-list-table")).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(page.get_by_test_id("template-file-row-process.bpmn")).to_be_visible()

    page.get_by_test_id("template-file-view-button-process.bpmn").click()
    expect(page).to_have_url(re.compile(r"/templates/1/files/process\.bpmn"))
    logger.info("Navigated to BPMN file route")


def test_template_file_form_view(mocked_templates_page: Page) -> None:
    """JSON form files open the form editor route."""
    logger.info("Open form.json editor for template 1")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    page.get_by_test_id("template-file-view-button-form.json").click()
    expect(page).to_have_url(re.compile(r"/templates/1/form/form\.json"))
    expect(page.get_by_test_id("template-file-save-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    logger.info("Form editor visible")


def test_template_export_download(mocked_templates_page: Page) -> None:
    """Export triggers a ZIP download."""
    logger.info("Expect ZIP download from export button")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    with page.expect_download(timeout=15_000) as dl:
        page.get_by_test_id("template-export-button").click()
    assert dl.value.suggested_filename.endswith(".zip")
    logger.info("Download filename %r", dl.value.suggested_filename)


def test_template_publish_success(mocked_templates_page: Page) -> None:
    """Publish issues PUT and shows a success alert."""
    logger.info("Publish draft template 1")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    page.get_by_test_id("template-publish-button").click()
    expect(page.get_by_text("Template published successfully.", exact=False)).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    expect(page.get_by_test_id("template-publish-button")).not_to_be_visible()
    logger.info("Success alert shown, publish hidden")


def test_template_version_selector_navigates(mocked_templates_page_multi_version: Page) -> None:
    """When multiple versions exist, switching the version select loads that template id."""
    vid = int(MOCK_TEMPLATE_V2["id"])
    logger.info(
        "Open template id=%s, switch to V1 (id=4)",
        vid,
    )
    page = mocked_templates_page_multi_version
    _open_template_by_id(page, vid)

    expect(page.get_by_test_id("template-version-select")).to_be_visible(timeout=ELEMENT_TIMEOUT)
    page.get_by_test_id("template-version-select").click()
    page.get_by_role("option", name=re.compile(r"V1")).first.click()

    expect(page).to_have_url(re.compile(r"/templates/4(?:/|\?|$)"))


@pytest.mark.parametrize("visibility", ["TENANT", "PUBLIC"])
def test_template_visibility_save(mocked_templates_page: Page, visibility: str) -> None:
    """Visibility select + save calls PUT and shows confirmation (from default Private)."""
    logger.info("Set visibility to %s", visibility)
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    page.get_by_test_id("template-visibility-select").click()
    page.locator(f'[role="option"][data-value="{visibility}"]').click()
    page.get_by_test_id("template-save-visibility-button").click()

    expect(page.get_by_text("Visibility updated successfully.", exact=False)).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info("Saved %s", visibility)


def test_template_visibility_can_save_private(mocked_templates_page: Page) -> None:
    """After widening visibility, the user can save back to Private."""
    logger.info("Template visibility can be saved as PUBLIC then PRIVATE")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    page.get_by_test_id("template-visibility-select").click()
    page.locator('[role="option"][data-value="PUBLIC"]').click()
    page.get_by_test_id("template-save-visibility-button").click()
    expect(page.get_by_text("Visibility updated successfully.", exact=False)).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )

    page.get_by_test_id("template-visibility-select").click()
    page.locator('[role="option"][data-value="PRIVATE"]').click()
    page.get_by_test_id("template-save-visibility-button").click()
    expect(page.get_by_text("Visibility updated successfully.", exact=False)).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info("Completed visibility save test")


def test_template_import_from_zip(mocked_templates_page: Page, tmp_path: Path) -> None:
    """Import modal accepts a zip and navigates to the created template detail."""
    logger.info("test_template_import_from_zip: build zip under %s", tmp_path)
    page = mocked_templates_page
    navigate_to_templates(page)

    zip_path = tmp_path / "tpl.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "process.bpmn",
            '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        )

    page.get_by_test_id("template-gallery-import-button").click()
    expect(page.get_by_test_id("import-template-dialog")).to_be_visible()

    page.get_by_test_id("import-template-name-input").locator("input").fill("Zip Import Flow")
    page.locator('[data-testid="import-template-choose-file-button"] input[type="file"]').set_input_files(
        str(zip_path)
    )
    page.get_by_test_id("import-template-submit-button").click()

    expect(page.get_by_test_id("template-export-button")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(page).to_have_url(re.compile(r"/templates/88888"))
    logger.info("Landed on imported template detail")


def test_template_file_download_row_action(mocked_templates_page: Page) -> None:
    """Per-file download icon fetches the file blob as a download."""
    logger.info("Download process.bpmn row action")
    page = mocked_templates_page
    _open_template_by_id(page, 1)

    with page.expect_download(timeout=15_000) as dl:
        page.get_by_test_id("template-file-download-button-process.bpmn").click()
    assert dl.value.suggested_filename == "process.bpmn"
    logger.info(
        "Suggested filename %r",
        dl.value.suggested_filename,
    )
