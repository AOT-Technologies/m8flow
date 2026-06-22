"""Page Object Model for the Template Details (modeler) page and its version selector.

Wraps a Playwright ``Page`` and exposes high-level actions/queries for the
``TemplateModelerPage`` view (``m8flow-frontend/src/views/TemplateModelerPage.tsx``)
and the version-selector ``Select`` rendered above it.
"""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from helpers.config import BASE_URL, ELEMENT_TIMEOUT, NAV_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.templates import navigate_to_templates, open_template


class TemplateDetailsPage:
    """High-level interactions with a single template's detail page."""

    VERSION_SELECT = "template-version-select"
    EXPORT_BUTTON = "template-export-button"
    FILE_LIST_TABLE = "template-file-list-table"

    def __init__(self, page: Page) -> None:
        self.page = page

    # -- navigation ----------------------------------------------------------

    def open(self, template_id: int) -> "TemplateDetailsPage":
        """Navigate directly to ``/templates/<id>`` and wait for it to load."""
        self.page.goto(f"{BASE_URL.rstrip('/')}/templates/{template_id}")
        self.wait_for_loaded()
        return self

    def open_via_gallery(self, card_id: int | str) -> "TemplateDetailsPage":
        """Open a template from its gallery card.

        ``card_id`` matches the ``template-card-<card_id>`` test id. The gallery
        collapses a key to its latest version, so this lands on the latest.
        """
        navigate_to_templates(self.page)
        open_template(self.page, str(card_id))
        return self

    def wait_for_loaded(self) -> None:
        expect(self.page.get_by_test_id(self.EXPORT_BUTTON)).to_be_visible(
            timeout=PAGE_DATA_TIMEOUT
        )

    def current_template_id(self) -> int:
        """Parse the template id out of the current URL."""
        m = re.search(r"/templates/(\d+)", self.page.url)
        assert m, f"No /templates/<id> in URL: {self.page.url}"
        return int(m.group(1))

    # -- version selector ----------------------------------------------------

    @property
    def version_select(self) -> Locator:
        return self.page.get_by_test_id(self.VERSION_SELECT)

    def expect_selector_visible(self) -> None:
        expect(self.version_select).to_be_visible(timeout=ELEMENT_TIMEOUT)

    def expect_selector_hidden(self) -> None:
        # Selector only renders when >1 version exists; assert it never appears.
        expect(self.version_select).to_have_count(0)

    def current_version_text(self) -> str:
        """Text shown in the closed selector (the selected ``renderValue``)."""
        return self.version_select.inner_text().strip()

    def expect_current_version(self, version_label: str) -> None:
        expect(self.version_select).to_contain_text(version_label, timeout=ELEMENT_TIMEOUT)

    def _open_dropdown(self) -> None:
        self.version_select.click()
        self.page.get_by_role("option").first.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)

    def _option(self, version_label: str) -> Locator:
        return self.page.get_by_role("option", name=re.compile(version_label))

    def select_version(self, version_label: str) -> None:
        """Open the dropdown and pick the option matching ``version_label``.

        Returns once the URL has navigated to the selected version's detail page.
        """
        current_id = self.current_template_id()
        self._open_dropdown()
        self._option(version_label).first.click()
        # Navigation happens only when picking a different version's id.
        self.page.wait_for_url(
            lambda url: bool(re.search(r"/templates/(\d+)", url))
            and int(re.search(r"/templates/(\d+)", url).group(1)) != current_id,
            timeout=NAV_TIMEOUT,
        )
        self.wait_for_loaded()

    def option_text(self, version_label: str) -> str:
        """Full text of a version's dropdown option (includes its status chip)."""
        self._open_dropdown()
        text = self._option(version_label).first.inner_text()
        # Close the dropdown without changing selection.
        self.page.keyboard.press("Escape")
        return text

    def expect_option_chip(self, version_label: str, chip_text: str) -> None:
        assert chip_text in self.option_text(version_label), (
            f"Expected chip {chip_text!r} on option {version_label!r}"
        )

    def expect_current_marker_on(self, version_label: str) -> None:
        """Assert the 'current' caption (en: ``(current)``) sits on the option."""
        assert "current" in self.option_text(version_label).lower(), (
            f"Expected the current-version marker on option {version_label!r}"
        )

    # -- metadata ------------------------------------------------------------

    def _chip(self, prefix: str) -> Locator:
        # Chips render as e.g. "Version: V1"; match the visible label text.
        return self.page.get_by_text(re.compile(rf"^{re.escape(prefix)}:"))

    def version_chip(self) -> str:
        return self._chip("Version").first.inner_text().strip()

    def status_chip(self) -> str:
        return self._chip("Status").first.inner_text().strip()

    def category_chip(self) -> str:
        return self._chip("Category").first.inner_text().strip()

    def visibility_chip(self) -> str:
        # Only present for published templates; drafts show an editable select.
        return self._chip("Visibility").first.inner_text().strip()

    def name_text(self, name: str) -> Locator:
        return self.page.get_by_text(name, exact=False).first

    def description_text(self, snippet: str) -> Locator:
        return self.page.get_by_text(snippet, exact=False).first

    # -- files ---------------------------------------------------------------

    def expect_file_row(self, file_name: str) -> None:
        expect(self.page.get_by_test_id(f"template-file-row-{file_name}")).to_be_visible(
            timeout=ELEMENT_TIMEOUT
        )

    def expect_no_file_row(self, file_name: str) -> None:
        expect(self.page.get_by_test_id(f"template-file-row-{file_name}")).to_have_count(0)

    def open_file(self, file_name: str) -> str:
        """Click a file's view button, navigate to it, and return its API body.

        Captures the ``.../templates/<id>/files/<file>`` response so callers can
        assert the BPMN/XML content served for the current version.
        """
        with self.page.expect_response(
            lambda r: "/files/" in r.url and r.request.method == "GET"
        ) as resp_info:
            self.page.get_by_test_id(f"template-file-view-button-{file_name}").click()
        return resp_info.value.text()

    # -- error states --------------------------------------------------------

    def expect_invalid_id_error(self) -> None:
        expect(self.page.get_by_text("Invalid template ID")).to_be_visible(
            timeout=PAGE_DATA_TIMEOUT
        )
        expect(self.page.get_by_test_id(self.EXPORT_BUTTON)).to_have_count(0)

    def expect_load_error(self) -> None:
        expect(self.page.get_by_role("alert")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        expect(self.page.get_by_test_id(self.EXPORT_BUTTON)).to_have_count(0)
