"""Reusable helpers and test data for internationalization (i18n) E2E tests.

The m8flow frontend uses ``react-i18next``. The language selector lives in the
side nav (``SideNav.tsx``) and is only available *after* login. Translations are
the merge of the upstream Spiff bundle and the m8flow override bundle
(``{...base, ...override}``), with ``fallbackLng: 'en-US'`` and a localStorage
detection cache under the ``i18nextLng`` key.

These helpers read the translation JSON straight from the frontend source so the
tests never hardcode translated strings -- the locale files are the single
source of truth. Language switching, current-language reads, translated-text
assertions and layout/overflow checks all go through here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from playwright.sync_api import Locator, Page, expect

from helpers.config import BASE_URL, ELEMENT_TIMEOUT, VIEWPORT
from helpers.login import login
from helpers.waiters import wait_for_app_ready

# --------------------------------------------------------------------------- #
# Test data
# --------------------------------------------------------------------------- #

# i18next resource keys, exactly as rendered by the language selector (sorted).
SUPPORTED_LANGUAGES = [
    "cs-CZ",
    "de",
    "en-US",
    "es",
    "fi",
    "fr-FR",
    "pt-BR",
    "pt-PT",
    "zh-CN",
]

# Default / fallback language configured via i18next ``fallbackLng``.
DEFAULT_LANGUAGE = "en-US"

# The non-English language the spec primarily asserts against.
PRIMARY_TEST_LANGUAGE = "fr-FR"

# An unsupported locale used to exercise the fallback path. Not in the bundle,
# so i18next must fall back to ``DEFAULT_LANGUAGE``.
UNSUPPORTED_LANGUAGE = "zz-ZZ"

# localStorage key used by i18next-browser-languagedetector.
I18N_STORAGE_KEY = "i18nextLng"

# Side-nav item ``data-testid`` suffix (``nav-item-<id>``) -> translation key.
NAV_ITEM_KEYS = {
    "home": "home",
    "processes": "processes",
    "processInstances": "process_instances",
    "messages": "messages",
    "configuration": "configuration",
    "connectors": "connectors",
    "templates": "templates",
    "tenantManagement": "tenant_management",
}

# Stable selectors (kept here so a markup change is a one-line fix).
LANGUAGE_BUTTON_TESTID = "nav-language-button"
LANGUAGE_MENU_TESTID = "nav-language-menu"
LANGUAGE_OPTION_PREFIX = "nav-language-option-"


# --------------------------------------------------------------------------- #
# Translation file access
# --------------------------------------------------------------------------- #


def locale_dir(locale: str) -> str:
    """Map an i18next locale code to its on-disk directory (``fr-FR`` -> ``fr_fr``)."""
    return locale.lower().replace("-", "_")


@lru_cache(maxsize=1)
def _repo_root() -> Path:
    """Walk up from this file until the dir holding both frontend trees is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "m8flow-frontend" / "src" / "locales").is_dir() and (
            parent / "spiffworkflow-frontend" / "src" / "locales"
        ).is_dir():
            return parent
    raise RuntimeError(
        "Could not locate repo root containing m8flow-frontend and "
        "spiffworkflow-frontend locale directories."
    )


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    # Locale files may carry a UTF-8 BOM; utf-8-sig tolerates both.
    return json.loads(path.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=16)  # one entry per supported locale (+ fallback/test locales)
def _merged_bundle(locale: str) -> dict:
    """Merge upstream base + m8flow override for *locale* (override wins)."""
    root = _repo_root()
    sub = locale_dir(locale)
    base = _read_json(root / "spiffworkflow-frontend" / "src" / "locales" / sub / "translation.json")
    override = _read_json(root / "m8flow-frontend" / "src" / "locales" / sub / "translation.json")
    return {**base, **override}


def translation(locale: str, key: str) -> str:
    """Return the runtime string for *key* in *locale*.

    Mirrors i18next behaviour: when the key is absent for *locale* it falls back
    to ``DEFAULT_LANGUAGE``. Raises ``KeyError`` if the key exists in neither
    (which means the test references a key the app does not define).
    """
    bundle = _merged_bundle(locale)
    if key in bundle:
        return bundle[key]
    fallback = _merged_bundle(DEFAULT_LANGUAGE)
    if key in fallback:
        return fallback[key]
    raise KeyError(f"Translation key {key!r} not found for {locale!r} or {DEFAULT_LANGUAGE!r}.")


# --------------------------------------------------------------------------- #
# Language selector interaction
# --------------------------------------------------------------------------- #


def open_language_menu(page: Page, timeout: int = ELEMENT_TIMEOUT) -> Locator:
    """Open (if needed) and return the language menu panel."""
    menu = page.get_by_test_id(LANGUAGE_MENU_TESTID)
    if not menu.is_visible():
        page.get_by_test_id(LANGUAGE_BUTTON_TESTID).click()
        expect(menu).to_be_visible(timeout=timeout)
    return menu


def available_language_options(page: Page) -> list[str]:
    """Return the locale codes rendered in the language menu.

    Reads every option's ``data-testid`` in a single DOM snapshot
    (``evaluate_all``) so a re-render between reads cannot invalidate an index
    mid-loop -- the previous ``count()`` + ``nth(i)`` loop was racy.
    """
    menu = open_language_menu(page)
    options = menu.locator(f'[data-testid^="{LANGUAGE_OPTION_PREFIX}"]')
    expect(options.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
    testids: list[str] = options.evaluate_all(
        "els => els.map((el) => el.getAttribute('data-testid') || '')"
    )
    return [t[len(LANGUAGE_OPTION_PREFIX):] for t in testids]


def change_language(page: Page, locale: str, timeout: int = ELEMENT_TIMEOUT) -> None:
    """Switch the UI language via the selector.

    Waits on a deterministic re-render signal -- the language button's
    ``aria-label`` is ``t('language')`` and updates when the language changes --
    so callers never need a fixed sleep.
    """
    open_language_menu(page, timeout=timeout)
    page.get_by_test_id(f"{LANGUAGE_OPTION_PREFIX}{locale}").click()
    expect(page.get_by_test_id(LANGUAGE_BUTTON_TESTID)).to_have_attribute(
        "aria-label", translation(locale, "language"), timeout=timeout
    )


def current_language(page: Page) -> str | None:
    """Return the persisted i18next language from localStorage (``i18nextLng``)."""
    return page.evaluate(
        f"() => window.localStorage.getItem('{I18N_STORAGE_KEY}')"
    )


def seed_language(page: Page, locale: str) -> None:
    """Pre-seed the language in localStorage *before* the app loads.

    Must be called before navigation. Used by the default/unsupported-fallback
    and login-page tests where the selector (post-login only) is not yet
    available. The init script runs on every document in the context.
    """
    page.add_init_script(
        f"window.localStorage.setItem('{I18N_STORAGE_KEY}', '{locale}');"
    )


def login_with_language(page: Page, locale: str, **login_kwargs) -> None:
    """Seed *locale*, then run the standard login flow and wait for the app shell."""
    seed_language(page, locale)
    login(page, **login_kwargs)
    wait_for_app_ready(page)


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #


def assert_translated(
    locator: Locator,
    locale: str,
    key: str,
    *,
    exact: bool = True,
    timeout: int = ELEMENT_TIMEOUT,
) -> None:
    """Assert *locator* shows the *locale* translation of *key*.

    ``exact`` uses ``to_have_text`` (whole element); set ``exact=False`` to use
    ``to_contain_text`` for elements that also render icons/adornments.
    """
    expected = translation(locale, key)
    if exact:
        expect(locator).to_have_text(expected, timeout=timeout)
    else:
        expect(locator).to_contain_text(expected, timeout=timeout)


def assert_no_overflow(
    locator: Locator,
    *,
    viewport_width: int = VIEWPORT["width"],
    tolerance: int = 2,
) -> None:
    """Assert the element is not truncated/overflowing and stays within the viewport.

    Catches translated text that is clipped (``scrollWidth > clientWidth``) or
    pushed off-screen horizontally. Vertical growth is allowed (wrapping is fine).
    """
    locator.scroll_into_view_if_needed()
    m = locator.evaluate(
        """el => {
            const r = el.getBoundingClientRect();
            return {
              scrollWidth: el.scrollWidth,
              clientWidth: el.clientWidth,
              left: r.left,
              right: r.right,
              text: (el.innerText || el.textContent || '').trim(),
            };
        }"""
    )
    label = m["text"] or "<no text>"
    assert m["scrollWidth"] <= m["clientWidth"] + tolerance, (
        f"Text overflow/truncation for {label!r}: "
        f"scrollWidth {m['scrollWidth']} > clientWidth {m['clientWidth']}"
    )
    assert m["right"] <= viewport_width + tolerance, (
        f"Element {label!r} overflows viewport right edge: "
        f"right {m['right']} > {viewport_width}"
    )
    assert m["left"] >= -tolerance, (
        f"Element {label!r} overflows viewport left edge: left {m['left']}"
    )


__all__ = [
    "SUPPORTED_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "PRIMARY_TEST_LANGUAGE",
    "UNSUPPORTED_LANGUAGE",
    "I18N_STORAGE_KEY",
    "NAV_ITEM_KEYS",
    "BASE_URL",
    "locale_dir",
    "translation",
    "open_language_menu",
    "available_language_options",
    "change_language",
    "current_language",
    "seed_language",
    "login_with_language",
    "assert_translated",
    "assert_no_overflow",
]
