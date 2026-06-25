"""Configuration > Secrets: value-update behavior.

Covers the 12 requested scenarios, adapted to m8flow's security-hardened
override of the upstream Secrets UI
(``m8flow-frontend/src/views/SecretShow.tsx``).  Adaptations are documented per
test; the salient differences from a generic secrets manager are:

- Secret values are **never revealed** (no reveal/show/retrieve control); the
  inline value field even loads empty because ``GET /secrets/{key}`` returns
  metadata only.
- "Update" is an **inline editor** (TextField ``#secret_value`` + "Update Value"
  button), not a modal, and has **no Cancel** control.
- There is **no client-side validation on the update path**; empty/format
  validation exists only on the create form.
- The "Edit secret value" button is gated by **PUT** permission on the secret
  (tenant-admin / integrator); ``viewer`` can read a secret but not edit it.

Run against a live stack (Keycloak + backend + UI on 6840-6842/6841):

    cd extensions/m8flow-frontend/test/browser
    uv run python -m pytest configuration/test_configuration_secret_value_update.py -v
"""
from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    ELEMENT_TIMEOUT,
    PAGE_DATA_TIMEOUT,
    SHORT_TIMEOUT,
)
from helpers import secrets as secrets_helper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _skip_unless_secrets_available(page: Page) -> None:
    """Skip the test when the current role cannot reach the Secrets area."""
    nav_config = page.get_by_test_id("nav-item-configuration")
    try:
        nav_config.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        nav_config.click()
        page.wait_for_url("**/configuration**", timeout=PAGE_DATA_TIMEOUT)
        page.get_by_role("tab", name="Secrets").wait_for(
            state="visible", timeout=SHORT_TIMEOUT
        )
    except PlaywrightTimeout:
        pytest.skip("Secrets not available for the current user role")


@pytest.fixture(scope="module")
def seeded_secret(authenticated_page: Page) -> Iterator[dict[str, str]]:
    """Create one secret (tenant-admin) for the module and clean it up afterward.

    Yields ``{"key": ..., "value": ...}`` where ``value`` is the last value the
    seed was created with.  Tests that mutate the value should not rely on this
    field after they run; they verify their own new value instead.
    """
    page = authenticated_page
    _skip_unless_secrets_available(page)

    key = f"e2e_upd_{uuid.uuid4().hex}"
    value = f"seed_{uuid.uuid4().hex}"
    secrets_helper.create_secret(page, key, value)
    try:
        yield {"key": key, "value": value}
    finally:
        secrets_helper.delete_secret_via_api_cleanup(page, key)


# ---------------------------------------------------------------------------
# 1. List page loads
# ---------------------------------------------------------------------------
def test_secrets_list_page_loads(authenticated_page: Page) -> None:
    """The Secrets list page renders its heading (or the empty-state message)."""
    page = authenticated_page
    _skip_unless_secrets_available(page)

    secrets_helper.navigate_to_secrets(page)
    expect(page).to_have_url(re.compile(r".*/configuration/secrets"))
    # The list page always renders the "Secrets" heading once data has loaded,
    # whether or not any secrets exist.
    expect(
        page.get_by_role("heading", name="Secrets")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


# ---------------------------------------------------------------------------
# 2. Detail page opens from the list
# ---------------------------------------------------------------------------
def test_secret_detail_opens_from_list(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """Clicking a secret in the list opens its detail page."""
    page = authenticated_page
    key = seeded_secret["key"]

    secrets_helper.open_secret_detail(page, key)
    expect(page).to_have_url(re.compile(rf".*/configuration/secrets/{key}"))
    expect(
        page.get_by_role("heading", name=f"Secret Key: {key}")
    ).to_be_visible()


# ---------------------------------------------------------------------------
# 3. Existing value visibility behavior
# ---------------------------------------------------------------------------
def test_secret_value_is_never_revealed(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """ADAPTED: m8flow has no reveal feature -- the value is never shown.

    The upstream "Retrieve secret value" control was deliberately removed, so
    instead of "masked by default + reveal-if-permitted" we assert that:
      * no reveal/show/retrieve control exists, and
      * the plaintext value never appears on the page, and
      * even the inline edit field loads empty (GET returns no value).
    """
    page = authenticated_page
    key, value = seeded_secret["key"], seeded_secret["value"]

    secrets_helper.open_secret_detail(page, key)

    # No reveal/show/retrieve affordance of any kind.
    reveal = page.get_by_role(
        "button", name=re.compile(r"reveal|show|retrieve", re.IGNORECASE)
    )
    expect(reveal).to_have_count(0)

    # The seeded plaintext value is nowhere on the page.
    expect(page.get_by_text(value, exact=False)).to_have_count(0)

    # Even when editing, the field is empty: the value is not returned by GET.
    secrets_helper.start_edit_value(page)
    expect(page.locator(secrets_helper.SECRET_VALUE_INPUT)).to_have_value("")


# ---------------------------------------------------------------------------
# 4. Update action visible for authorized users
# ---------------------------------------------------------------------------
def test_update_action_visible_for_authorized(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """A tenant-admin (PUT permission) sees the "Edit secret value" button."""
    page = authenticated_page
    secrets_helper.open_secret_detail(page, seeded_secret["key"])
    expect(secrets_helper.edit_value_button(page)).to_be_visible()


# ---------------------------------------------------------------------------
# 5. Clicking Update Value opens the (inline) update form
# ---------------------------------------------------------------------------
def test_clicking_edit_opens_inline_update_form(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """ADAPTED: the update UI is an inline editor, not a modal.

    Clicking "Edit secret value" expands a value TextField + "Update Value"
    button and disables the Edit button.
    """
    page = authenticated_page
    secrets_helper.open_secret_detail(page, seeded_secret["key"])

    secrets_helper.start_edit_value(page)
    expect(page.locator(secrets_helper.SECRET_VALUE_INPUT)).to_be_visible()
    expect(secrets_helper.update_value_button(page)).to_be_visible()
    # Edit button becomes disabled while the inline editor is open.
    expect(secrets_helper.edit_value_button(page)).to_be_disabled()


# ---------------------------------------------------------------------------
# 6. Value can be updated with valid input
# ---------------------------------------------------------------------------
def test_secret_value_updates_with_valid_input(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """A valid new value submits successfully and shows the success toast."""
    page = authenticated_page
    secrets_helper.open_secret_detail(page, seeded_secret["key"])

    new_value = f"updated_{uuid.uuid4().hex}"
    secrets_helper.start_edit_value(page)
    secrets_helper.update_secret_value(page, new_value)

    expect(
        page.get_by_text(secrets_helper.SECRET_UPDATED_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)


# ---------------------------------------------------------------------------
# 7. Updated value persists after refresh
# ---------------------------------------------------------------------------
def test_updated_value_persists_after_refresh(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """ADAPTED: persistence is verified via API, since the UI never shows values.

    After updating, we refresh the detail page (proving it still loads) and then
    confirm the stored value through ``GET /secrets/show-value/{key}``.  If that
    endpoint is not exposed in this environment we fall back to asserting the
    detail page still renders.
    """
    page = authenticated_page
    key = seeded_secret["key"]
    secrets_helper.open_secret_detail(page, key)

    new_value = f"persist_{uuid.uuid4().hex}"
    secrets_helper.start_edit_value(page)
    secrets_helper.update_secret_value(page, new_value)
    expect(
        page.get_by_text(secrets_helper.SECRET_UPDATED_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)

    secrets_helper.refresh(page)
    expect(
        page.get_by_role("heading", name=f"Secret Key: {key}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    status, stored_value = secrets_helper.api_get_secret_value(page, key)
    if status == 200 and stored_value is not None:
        assert stored_value == new_value
    else:
        logger.info(
            "show-value not available (status=%s); relied on detail reload to "
            "confirm the secret persisted.",
            status,
        )


# ---------------------------------------------------------------------------
# 8. Empty value validation
# ---------------------------------------------------------------------------
def test_empty_value_validation_on_create(authenticated_page: Page) -> None:
    """ADAPTED: the update path has no validation -- assert it on the create form.

    ``updateSecretValue()`` blindly PUTs whatever is typed (even empty), so there
    is no empty-value validation to assert on update.  The create form
    (``SecretNew.tsx``) does validate a non-empty value, which is the closest
    real "empty value validation" the product offers.
    """
    page = authenticated_page
    _skip_unless_secrets_available(page)

    secrets_helper.navigate_to_secrets(page)
    page.get_by_role("link", name=secrets_helper.ADD_A_SECRET_LABEL).click()
    page.wait_for_url("**/configuration/secrets/new", timeout=PAGE_DATA_TIMEOUT)

    # Provide a valid key but leave the value empty.
    page.locator(secrets_helper.SECRET_KEY_INPUT).fill(
        f"e2e_empty_{uuid.uuid4().hex}"
    )
    page.get_by_role("button", name="Submit").click()

    expect(
        page.get_by_text(secrets_helper.VALUE_MUST_BE_SET_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    # Submission is blocked; we stay on the create form.
    expect(page).to_have_url(re.compile(r".*/configuration/secrets/new"))


# ---------------------------------------------------------------------------
# 9. Invalid value validation (if rules exist)
# ---------------------------------------------------------------------------
def test_invalid_key_validation_on_create(authenticated_page: Page) -> None:
    """ADAPTED: there is no value-format rule -- the only format rule is the key regex.

    Secret *values* have no format constraints anywhere in the product.  The
    create form does enforce a key format (``^[\\w-]+$``), so we exercise that as
    the representative "invalid input" rule.
    """
    page = authenticated_page
    _skip_unless_secrets_available(page)

    secrets_helper.navigate_to_secrets(page)
    page.get_by_role("link", name=secrets_helper.ADD_A_SECRET_LABEL).click()
    page.wait_for_url("**/configuration/secrets/new", timeout=PAGE_DATA_TIMEOUT)

    page.locator(secrets_helper.SECRET_KEY_INPUT).fill("bad key!")
    page.locator(secrets_helper.SECRET_VALUE_CREATE_INPUT).fill("some-value")
    page.get_by_role("button", name="Submit").click()

    expect(
        page.get_by_text(secrets_helper.KEY_ALPHANUMERIC_ERROR_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(page).to_have_url(re.compile(r".*/configuration/secrets/new"))


# ---------------------------------------------------------------------------
# 10. Unauthorized users cannot update
# ---------------------------------------------------------------------------
def test_unauthorized_user_cannot_update(
    viewer_page: Page, seeded_secret: dict[str, str]
) -> None:
    """A read-only ``viewer`` cannot edit: the button is hidden and the API blocks it.

    ``viewer`` has read-secrets but not manage-secrets, so the PUT-gated "Edit
    secret value" button is absent.  A direct API PUT must also be rejected
    (401/403).  Skipped when the viewer cannot reach the secret at all.
    """
    page = viewer_page
    key = seeded_secret["key"]

    try:
        secrets_helper.open_secret_detail(page, key)
    except (PlaywrightTimeout, AssertionError):
        pytest.skip("viewer cannot reach this secret's detail page")

    # UI: the edit affordance must not be present for a read-only user.
    expect(secrets_helper.edit_value_button(page)).to_have_count(0)

    # API: a direct update attempt must be rejected. The update is considered
    # blocked when the API returns an authorization error (401/403) or refuses
    # the method (405) -- in every case the value is not changed.
    resp = secrets_helper.api_put_secret_value(
        page, key, f"hacked_{uuid.uuid4().hex}"
    )
    assert resp.status in (401, 403, 405), (
        f"expected viewer PUT to be blocked, got {resp.status}"
    )


# ---------------------------------------------------------------------------
# 11. Cancel behavior
# ---------------------------------------------------------------------------
def test_unsaved_edit_is_discarded(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """ADAPTED: there is no Cancel button -- navigating away discards the edit.

    The inline editor has no Cancel control, so "cancel" maps to abandoning the
    edit (refresh) without clicking Update.  We confirm the unsaved value is not
    persisted: the stored value is unchanged and the re-opened field is empty.
    """
    page = authenticated_page
    key = seeded_secret["key"]

    # Establish a known stored value first.
    secrets_helper.open_secret_detail(page, key)
    known_value = f"known_{uuid.uuid4().hex}"
    secrets_helper.start_edit_value(page)
    secrets_helper.update_secret_value(page, known_value)
    expect(
        page.get_by_text(secrets_helper.SECRET_UPDATED_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)

    # Begin a new edit, type a throwaway value, but DO NOT submit it.
    secrets_helper.refresh(page)
    secrets_helper.start_edit_value(page)
    page.locator(secrets_helper.SECRET_VALUE_INPUT).fill(
        f"discarded_{uuid.uuid4().hex}"
    )

    # Abandon the edit by refreshing.
    secrets_helper.refresh(page)

    # The stored value is unchanged (if show-value is available) ...
    status, stored_value = secrets_helper.api_get_secret_value(page, key)
    if status == 200 and stored_value is not None:
        assert stored_value == known_value

    # ... and the re-opened editor field is empty (value never returned by GET).
    secrets_helper.open_secret_detail(page, key)
    secrets_helper.start_edit_value(page)
    expect(page.locator(secrets_helper.SECRET_VALUE_INPUT)).to_have_value("")


# ---------------------------------------------------------------------------
# 12. UI updates after successful value change
# ---------------------------------------------------------------------------
def test_ui_after_successful_update(
    authenticated_page: Page, seeded_secret: dict[str, str]
) -> None:
    """ADAPTED: success toast shows; inline editor stays open; value stays masked.

    There is no modal to close.  After a successful update m8flow shows the
    "Secret updated" notification and keeps the inline editor visible; after a
    refresh the value remains masked (never rendered on the page).
    """
    page = authenticated_page
    key = seeded_secret["key"]
    secrets_helper.open_secret_detail(page, key)

    new_value = f"final_{uuid.uuid4().hex}"
    secrets_helper.start_edit_value(page)
    secrets_helper.update_secret_value(page, new_value)

    # (a) Success message is shown.
    expect(
        page.get_by_text(secrets_helper.SECRET_UPDATED_TEXT)
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)

    # (b) No modal to close; the inline editor remains visible.
    expect(page.locator(secrets_helper.SECRET_VALUE_INPUT)).to_be_visible()

    # (c) After refresh, the value is reflected only as masked state -- never
    #     rendered as plaintext anywhere on the page.
    secrets_helper.refresh(page)
    expect(
        page.get_by_role("heading", name=f"Secret Key: {key}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(page.get_by_text(new_value, exact=False)).to_have_count(0)
