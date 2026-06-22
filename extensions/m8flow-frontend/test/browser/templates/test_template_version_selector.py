"""E2E coverage for the Template Version Selector on the Template Details page.

All tests are fully mock-backed (see ``templates/conftest.py`` fixtures), so they
are deterministic, independent, and safe to run in parallel. They exercise both
positive flows (switching versions, metadata/file/BPMN updates, state retention)
and negative flows (invalid id, non-existent version).
"""
import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL
from helpers.mocks import (
    MISSING_TEMPLATE_ID,
    MOCK_TEMPLATE_PUBLISHED,
    MOCK_TEMPLATE_V2,
    PUBLISHED_V1_MARKER,
    PUBLISHED_V2_MARKER,
)
from helpers.template_details_page import TemplateDetailsPage

logger = logging.getLogger(__name__)

# Published family ids (key ``test-template-published``): V1 published, V2 draft.
PUBLISHED_V1_ID = int(MOCK_TEMPLATE_PUBLISHED["id"])  # 4
PUBLISHED_V2_ID = int(MOCK_TEMPLATE_V2["id"])  # 5


def test_latest_version_selected_by_default(mocked_published_multi_version: Page) -> None:
    """Opening the template from the gallery lands on the latest version (V2)."""
    details = TemplateDetailsPage(mocked_published_multi_version)
    # The gallery collapses the key to its highest id (V2 = latest).
    details.open_via_gallery(PUBLISHED_V2_ID)

    expect(details.page).to_have_url(re.compile(rf"/templates/{PUBLISHED_V2_ID}(?:/|\?|$)"))
    details.expect_current_version("V2")
    details.expect_current_marker_on("V2")
    logger.info("Latest version V2 selected by default")


def test_version_selector_visible_when_multiple_versions(
    mocked_published_multi_version: Page,
) -> None:
    """The selector is shown when a template has more than one version."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)
    details.expect_selector_visible()


def test_version_selector_hidden_for_single_version(mocked_single_version: Page) -> None:
    """The selector is not rendered for a template with a single version."""
    details = TemplateDetailsPage(mocked_single_version).open(1)
    details.expect_selector_hidden()


def test_switching_version_updates_details(mocked_published_multi_version: Page) -> None:
    """Switching V2 -> V1 navigates and refreshes the metadata for that version."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)

    # V2 is a draft.
    assert "V2" in details.version_chip()
    assert "DRAFT" in details.status_chip()

    details.select_version("V1")

    expect(details.page).to_have_url(re.compile(rf"/templates/{PUBLISHED_V1_ID}(?:/|\?|$)"))
    assert "V1" in details.version_chip()
    assert "PUBLISHED" in details.status_chip()
    details.expect_current_version("V1")


def test_bpmn_content_changes_with_version(mocked_published_multi_version: Page) -> None:
    """The served BPMN/XML and the file set differ between versions."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)

    # V2 ships only the BPMN file.
    details.expect_file_row("released.bpmn")
    details.expect_no_file_row("form.json")
    v2_xml = details.open_file("released.bpmn")
    assert PUBLISHED_V2_MARKER in v2_xml
    assert PUBLISHED_V1_MARKER not in v2_xml

    # Back to the detail page, switch to V1, which adds form.json.
    details.open(PUBLISHED_V1_ID)
    details.expect_file_row("released.bpmn")
    details.expect_file_row("form.json")
    v1_xml = details.open_file("released.bpmn")
    assert PUBLISHED_V1_MARKER in v1_xml
    assert PUBLISHED_V2_MARKER not in v1_xml


def test_metadata_updates_for_selected_version(mocked_published_multi_version: Page) -> None:
    """Name, version, status, category and description reflect the selected version."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)
    expect(details.name_text("Published Test Template")).to_be_visible()
    assert "V2" in details.version_chip()
    assert "Production" in details.category_chip()
    expect(details.description_text("Draft of V2")).to_be_visible()

    details.select_version("V1")
    assert "V1" in details.version_chip()
    assert "PUBLISHED" in details.status_chip()
    # Published templates render visibility as a read-only chip.
    assert "TENANT" in details.visibility_chip()
    expect(details.description_text("A published template")).to_be_visible()


def test_older_version_is_viewable(mocked_published_multi_version: Page) -> None:
    """An older version (V1) opens directly and is marked current."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V1_ID)
    details.expect_selector_visible()
    details.expect_current_version("V1")
    details.expect_current_marker_on("V1")


def test_invalid_version_id_shows_error(mocked_published_multi_version: Page) -> None:
    """A non-numeric template id shows the 'Invalid template ID' error."""
    page = mocked_published_multi_version
    page.goto(f"{BASE_URL.rstrip('/')}/templates/not-a-number")
    TemplateDetailsPage(page).expect_invalid_id_error()


def test_nonexistent_version_returns_not_found(mocked_template_not_found: Page) -> None:
    """A 404 from the detail endpoint surfaces an error alert, not the template."""
    page = mocked_template_not_found
    page.goto(f"{BASE_URL.rstrip('/')}/templates/{MISSING_TEMPLATE_ID}")
    TemplateDetailsPage(page).expect_load_error()


def test_selector_chips_public_vs_private(
    mocked_published_multi_version: Page,
) -> None:
    """Published family shows Published/Draft chips per version in the dropdown."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)
    details.expect_option_chip("V1", "Published")
    details.expect_option_chip("V2", "Draft")


def test_selector_chips_private_family(mocked_private_multi_version: Page) -> None:
    """A private (all-draft) family shows a Draft chip on every version."""
    details = TemplateDetailsPage(mocked_private_multi_version).open(7)
    details.expect_selector_visible()
    details.expect_option_chip("V1", "Draft")
    details.expect_option_chip("V2", "Draft")


def test_version_state_retained_on_navigation(mocked_published_multi_version: Page) -> None:
    """After switching to V1 and opening a file, going back keeps V1 selected."""
    details = TemplateDetailsPage(mocked_published_multi_version).open(PUBLISHED_V2_ID)
    details.select_version("V1")
    expect(details.page).to_have_url(re.compile(rf"/templates/{PUBLISHED_V1_ID}(?:/|\?|$)"))

    # Drill into the BPMN file, then navigate back.
    details.open_file("released.bpmn")
    expect(details.page).to_have_url(re.compile(rf"/templates/{PUBLISHED_V1_ID}/files/"))
    details.page.go_back()

    details.wait_for_loaded()
    expect(details.page).to_have_url(re.compile(rf"/templates/{PUBLISHED_V1_ID}(?:/|\?|$)"))
    details.expect_current_version("V1")
