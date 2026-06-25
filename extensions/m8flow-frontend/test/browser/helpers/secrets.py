"""Reusable helpers for the Configuration > Secrets UI.

The browser suite is helper-based (module-level functions taking a ``Page``)
rather than class-based page objects -- see ``helpers/login.py``.  These helpers
encapsulate the navigation, create, edit and update flows for secrets plus thin
``page.request`` wrappers for setup/cleanup and authorization assertions.

Ground truth for the m8flow override (``m8flow-frontend/src/views/SecretShow.tsx``):
- Secret values are never revealed; the value field even loads empty on edit.
- "Update" is an inline editor (TextField ``#secret_value`` + "Update Value"
  button), not a modal, and has no Cancel control.
- The "Edit secret value" button is gated by PUT permission on the secret.
"""
from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import APIResponse, Page, expect

from helpers.config import (
    API_PREFIX,
    PAGE_DATA_TIMEOUT,
    SHORT_TIMEOUT,
)
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

# Exact English labels (spiffworkflow-frontend/src/locales/en_us/translation.json).
EDIT_SECRET_VALUE_LABEL = "Edit secret value"
UPDATE_VALUE_LABEL = "Update Value"
ADD_A_SECRET_LABEL = "Add a secret"
SECRET_UPDATED_TEXT = "Secret updated"
NO_SECRETS_TEXT = "No Secrets to Display"
VALUE_MUST_BE_SET_TEXT = "The value must be set"
KEY_ALPHANUMERIC_ERROR_TEXT = (
    "The key must be alphanumeric characters and underscores"
)

# Locators for the inline editor on the secret detail page.
SECRET_VALUE_INPUT = "#secret_value"
# Locators for the create form.
SECRET_KEY_INPUT = "#secret-key"
SECRET_VALUE_CREATE_INPUT = "#secret-value-label"


# ---------------------------------------------------------------------------
# UI flows
# ---------------------------------------------------------------------------
def navigate_to_secrets(page: Page) -> None:
    """Open Configuration > Secrets from the side nav.

    Mirrors the navigation in ``test_configuration_secrets_create.py``.
    """
    page.get_by_test_id("nav-item-configuration").click()
    page.wait_for_url("**/configuration**", timeout=PAGE_DATA_TIMEOUT)
    page.get_by_role("tab", name="Secrets").click()
    page.wait_for_url("**/configuration/secrets**", timeout=PAGE_DATA_TIMEOUT)


def create_secret(page: Page, key: str, value: str) -> None:
    """Create a secret via the UI create form, leaving the browser on its detail page.

    The MUI value field is filled through its label id (``#secret-value-label``)
    -- the same quirk used by the existing create test.
    """
    navigate_to_secrets(page)
    page.get_by_role("link", name=ADD_A_SECRET_LABEL).click()
    page.wait_for_url("**/configuration/secrets/new", timeout=PAGE_DATA_TIMEOUT)
    page.locator(SECRET_KEY_INPUT).fill(key)
    page.locator(SECRET_VALUE_CREATE_INPUT).fill(value)
    page.get_by_role("button", name="Submit").click()
    page.wait_for_url(
        f"**/configuration/secrets/{key}", timeout=PAGE_DATA_TIMEOUT
    )
    logger.info("Created secret %s via UI.", key)


def open_secret_detail(page: Page, key: str) -> None:
    """From the secrets list, click into a secret's detail page and assert it loaded."""
    navigate_to_secrets(page)
    page.get_by_role("link", name=key, exact=True).first.click()
    page.wait_for_url(
        f"**/configuration/secrets/{key}", timeout=PAGE_DATA_TIMEOUT
    )
    expect(
        page.get_by_role("heading", name=f"Secret Key: {key}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def edit_value_button(page: Page):
    """Locator for the "Edit secret value" button (gated by PUT permission)."""
    return page.get_by_role("button", name=EDIT_SECRET_VALUE_LABEL)


def update_value_button(page: Page):
    """Locator for the inline "Update Value" submit button."""
    return page.get_by_role("button", name=UPDATE_VALUE_LABEL)


def start_edit_value(page: Page) -> None:
    """Click "Edit secret value" and wait for the inline value editor to appear."""
    edit_value_button(page).click()
    page.locator(SECRET_VALUE_INPUT).wait_for(
        state="visible", timeout=SHORT_TIMEOUT
    )


def update_secret_value(page: Page, value: str) -> None:
    """Type a new value into the inline editor and submit it."""
    page.locator(SECRET_VALUE_INPUT).fill(value)
    update_value_button(page).click()


def refresh(page: Page) -> None:
    """Reload the page and wait for the app shell to be ready again."""
    page.reload()
    wait_for_app_ready(page)


# ---------------------------------------------------------------------------
# API helpers (setup / cleanup / authorization assertions)
# ---------------------------------------------------------------------------
def _auth_headers(page: Page) -> dict[str, str]:
    """Build an Authorization header from the ``access_token`` cookie.

    The frontend's HttpService reads the ``access_token`` cookie and sends it as
    ``Authorization: Bearer <token>`` (see UserService.getAccessToken).  We
    replicate that for ``page.request`` calls so they carry the same identity.
    """
    headers: dict[str, str] = {}
    for c in page.context.cookies():
        if c.get("name") == "access_token" and c.get("value"):
            headers["Authorization"] = f"Bearer {c['value']}"
            break
    return headers


def api_get_secret_value(page: Page, key: str) -> tuple[int, Any]:
    """Fetch the decrypted value via ``GET /v1.0/secrets/show-value/{key}``.

    Returns ``(status_code, value_or_None)``.  The m8flow UI does not surface
    this endpoint, but it is the only way to verify a value actually persisted.
    Returns ``value=None`` when the call is not 200 or the body has no value.
    """
    resp = page.request.get(
        f"{API_PREFIX}/secrets/show-value/{key}",
        headers=_auth_headers(page),
    )
    if not resp.ok:
        return resp.status, None
    try:
        body = resp.json()
    except Exception:
        return resp.status, None
    if isinstance(body, dict):
        return resp.status, body.get("value")
    return resp.status, body


def api_put_secret_value(page: Page, key: str, value: str) -> APIResponse:
    """Attempt a direct ``PUT /v1.0/secrets/{key}`` value update.

    Used to assert that unauthorized roles are blocked at the API even if they
    bypass the (hidden) UI control.
    """
    return page.request.put(
        f"{API_PREFIX}/secrets/{key}",
        headers=_auth_headers(page),
        data={"value": value},
    )


def api_delete_secret(page: Page, key: str) -> APIResponse:
    """Delete a secret via ``DELETE /v1.0/secrets/{key}``."""
    return page.request.delete(
        f"{API_PREFIX}/secrets/{key}",
        headers=_auth_headers(page),
    )


def delete_secret_via_api_cleanup(page: Page, key: str) -> None:
    """Best-effort teardown: delete a secret, swallowing any error."""
    try:
        api_delete_secret(page, key)
    except Exception as error:  # noqa: BLE001 - cleanup must never fail a test
        logger.warning("Cleanup failed for secret %s: %s", key, error)
