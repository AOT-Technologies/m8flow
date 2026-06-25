"""End-to-end internationalization (i18n) coverage.

Verifies the language selector, language switching, and that translated text is
applied across navigation, header/buttons, forms, tables, dialogs, and
validation messages -- plus unsupported-language fallback and layout integrity.

Conventions (match the rest of this suite):
- Stable ``data-testid`` locators only; no fragile text/CSS selectors.
- Deterministic waits via ``expect(...)`` and the language-switch barrier in
  ``helpers.i18n.change_language`` -- no ``time.sleep``.
- Expected strings come from the frontend translation JSON via
  ``helpers.i18n.translation`` -- never hardcoded here.

Most tests share the module-scoped ``authenticated_page`` (tenant admin) and set
the language they need at the start, so they are order-independent. The
default-language, unsupported-fallback, and login-page tests need a clean
pre-navigation state, so they use the function-scoped ``page`` fixture with
``login_with_language`` / ``seed_language``.
"""

from __future__ import annotations

import logging

import pytest
from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, ELEMENT_TIMEOUT, SHORT_TIMEOUT
from helpers.login import is_multi_tenant_mode, login
from helpers.waiters import wait_for_app_ready
from helpers.i18n import (
    DEFAULT_LANGUAGE,
    NAV_ITEM_KEYS,
    PRIMARY_TEST_LANGUAGE,
    SUPPORTED_LANGUAGES,
    UNSUPPORTED_LANGUAGE,
    assert_no_overflow,
    assert_translated,
    available_language_options,
    change_language,
    current_language,
    login_with_language,
    open_language_menu,
    seed_language,
    translation,
)

logger = logging.getLogger(__name__)

FR = PRIMARY_TEST_LANGUAGE


# --------------------------------------------------------------------------- #
# Language selector + switching
# --------------------------------------------------------------------------- #


def test_language_selector_visible(authenticated_page: Page) -> None:
    """The language button opens a menu listing the supported languages."""
    page = authenticated_page
    menu = open_language_menu(page)
    expect(menu).to_be_visible()
    assert available_language_options(page), "Language menu rendered no options."


def test_language_menu_lists_all_supported_languages(authenticated_page: Page) -> None:
    """Every supported locale is offered (order-independent)."""
    options = available_language_options(authenticated_page)
    assert sorted(options) == sorted(SUPPORTED_LANGUAGES), (
        f"Selector options {sorted(options)} != supported {sorted(SUPPORTED_LANGUAGES)}"
    )


def test_language_switch_persists(authenticated_page: Page) -> None:
    """Switching to French persists the choice (localStorage i18nextLng)."""
    page = authenticated_page
    change_language(page, FR)
    assert current_language(page) == FR
    # Switch back so the default-language behaviour is also exercised here.
    change_language(page, DEFAULT_LANGUAGE)
    assert current_language(page) == DEFAULT_LANGUAGE


# --------------------------------------------------------------------------- #
# Navigation / sidebar
# --------------------------------------------------------------------------- #


def _visible_nav_items(page: Page) -> dict[str, str]:
    """Return {nav_id: translation_key} for nav items currently rendered."""
    present = {}
    for nav_id, key in NAV_ITEM_KEYS.items():
        if page.get_by_test_id(f"nav-item-{nav_id}").count() > 0:
            present[nav_id] = key
    return present


def test_navigation_labels_translated_to_french(authenticated_page: Page) -> None:
    page = authenticated_page
    change_language(page, FR)
    present = _visible_nav_items(page)
    assert present, "No navigation items were rendered for this user."
    for nav_id, key in present.items():
        assert_translated(page.get_by_test_id(f"nav-item-{nav_id}"), FR, key)


def test_navigation_labels_translated_to_default(authenticated_page: Page) -> None:
    page = authenticated_page
    change_language(page, DEFAULT_LANGUAGE)
    present = _visible_nav_items(page)
    assert present, "No navigation items were rendered for this user."
    for nav_id, key in present.items():
        assert_translated(page.get_by_test_id(f"nav-item-{nav_id}"), DEFAULT_LANGUAGE, key)


# --------------------------------------------------------------------------- #
# Header / buttons
# --------------------------------------------------------------------------- #


def test_header_buttons_translated(authenticated_page: Page) -> None:
    """Header icon-button aria-labels and the sign-out link are translated."""
    page = authenticated_page
    change_language(page, FR)

    expect(page.get_by_test_id("nav-language-button")).to_have_attribute(
        "aria-label", translation(FR, "language")
    )
    expect(page.get_by_test_id("nav-user-actions-button")).to_have_attribute(
        "aria-label", translation(FR, "user_actions")
    )
    dark = page.get_by_test_id("nav-toggle-dark-mode-button")
    if dark.count() > 0:
        expect(dark).to_have_attribute("aria-label", translation(FR, "toggle_dark_mode"))

    # Sign-out link lives in the user profile popover (toggled by the button).
    panel = page.get_by_test_id("nav-user-profile-panel")
    page.get_by_test_id("nav-user-actions-button").click()
    expect(panel).to_be_visible()
    assert_translated(
        page.get_by_test_id("sign-out-button"), FR, "sign_out", exact=False
    )
    # Toggle the popover closed so the shared page is clean for the next test.
    page.get_by_test_id("nav-user-actions-button").click()
    expect(panel).to_be_hidden()


# --------------------------------------------------------------------------- #
# Forms (Templates page chrome) + tables + dialogs + validation
# --------------------------------------------------------------------------- #


def _open_templates(page: Page) -> None:
    page.goto(f"{BASE_URL}/templates")
    expect(page.get_by_test_id("template-filters-search-input")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )


def test_form_labels_and_placeholders_translated(authenticated_page: Page) -> None:
    """Templates search placeholder and filter/mode labels are translated."""
    page = authenticated_page
    _open_templates(page)
    change_language(page, FR)

    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    expect(search_input).to_have_attribute("placeholder", translation(FR, "search_templates"))

    assert_translated(
        page.get_by_test_id("template-gallery-mode-active"), FR, "active_templates"
    )
    assert_translated(
        page.get_by_test_id("template-gallery-mode-deleted"), FR, "deleted_templates"
    )


def test_table_headers_translated(authenticated_page: Page) -> None:
    """Template table headers (owned, t()-driven) are translated.

    Skips only if no templates exist to render the table body (the gallery shows
    an empty-state instead of a table) -- the headers themselves are owned and
    translated, so a populated env asserts them.
    """
    page = authenticated_page
    _open_templates(page)
    change_language(page, FR)
    page.get_by_test_id("template-gallery-view-table").click()

    table = page.get_by_test_id("template-gallery-table")
    if table.count() == 0 or not table.is_visible():
        pytest.skip("Template table not rendered (no templates in this environment).")

    headers = table.locator("thead th")
    header_texts = {headers.nth(i).inner_text().strip() for i in range(headers.count())}
    for key in ("name", "version", "category", "actions"):
        expected = translation(FR, key)
        assert expected in header_texts, (
            f"Expected translated header {expected!r} ({key}) in {header_texts}"
        )


def _open_import_dialog(page: Page):
    """Open the (reachable) Import-template-from-zip dialog; skip if user can't create."""
    _open_templates(page)
    btn = page.get_by_test_id("template-gallery-import-button")
    if btn.count() == 0:
        pytest.skip("Import button not available for this user (no create permission).")
    btn.click()
    dialog = page.get_by_test_id("import-template-dialog")
    expect(dialog).to_be_visible(timeout=ELEMENT_TIMEOUT)
    return dialog


def test_dialog_translated(authenticated_page: Page) -> None:
    """The import dialog's title and cancel button are translated."""
    page = authenticated_page
    change_language(page, FR)
    dialog = _open_import_dialog(page)
    try:
        assert_translated(dialog, FR, "import_template_from_zip", exact=False)
        assert_translated(
            page.get_by_test_id("import-template-cancel-button"), FR, "cancel"
        )
    finally:
        page.get_by_test_id("import-template-cancel-button").click()
        expect(dialog).to_be_hidden()


def test_validation_message_translated(authenticated_page: Page) -> None:
    """A client-side validation message in the import dialog is translated."""
    page = authenticated_page
    change_language(page, FR)
    dialog = _open_import_dialog(page)
    try:
        # Provide a name but no zip file -> "please select a zip file" validation.
        page.get_by_test_id("import-template-name-input").locator("input").fill(
            "i18n-validation-check"
        )
        page.get_by_test_id("import-template-submit-button").click()
        assert_translated(
            page.get_by_test_id("import-template-error-alert"),
            FR,
            "please_select_zip_file",
        )
    finally:
        page.get_by_test_id("import-template-cancel-button").click()
        expect(dialog).to_be_hidden()


# --------------------------------------------------------------------------- #
# Default language, unsupported fallback, login page (fresh-login fixtures)
# --------------------------------------------------------------------------- #


def test_default_language_is_english(page: Page) -> None:
    """With no seeded preference the app defaults to English (en-US)."""
    login(page)
    wait_for_app_ready(page)
    assert_translated(
        page.get_by_test_id("nav-item-home"), DEFAULT_LANGUAGE, "home"
    )


def test_unsupported_language_falls_back_to_default(page: Page) -> None:
    """An unsupported locale falls back to en-US (i18next fallbackLng)."""
    login_with_language(page, UNSUPPORTED_LANGUAGE)
    # i18next cannot resolve zz-ZZ, so UI renders the en-US fallback strings.
    assert_translated(
        page.get_by_test_id("nav-item-home"), DEFAULT_LANGUAGE, "home"
    )


def test_login_page_translated(page: Page) -> None:
    """The pre-login landing page honours the seeded language (French)."""
    seed_language(page, FR)
    if not is_multi_tenant_mode(page, timeout=SHORT_TIMEOUT):
        pytest.skip("Single-tenant mode: no shared-realm landing page to translate.")
    # is_multi_tenant_mode already navigated to BASE_URL with the seed applied.
    assert_translated(
        page.get_by_test_id("shared-realm-sign-in-button"), FR, "sign_in", exact=False
    )


# --------------------------------------------------------------------------- #
# Layout / overflow under translated text
# --------------------------------------------------------------------------- #


def test_translated_text_no_layout_overflow(authenticated_page: Page) -> None:
    """Translated nav/header text does not truncate, overflow, or leave the viewport."""
    page = authenticated_page
    change_language(page, FR)

    locators = [
        page.get_by_test_id(f"nav-item-{nav_id}") for nav_id in _visible_nav_items(page)
    ]
    for testid in ("nav-tenant-name", "nav-language-button", "nav-user-actions-button"):
        loc = page.get_by_test_id(testid)
        if loc.count() > 0 and loc.is_visible():
            locators.append(loc)

    assert locators, "Nothing rendered to check for overflow."
    for loc in locators:
        assert_no_overflow(loc)
