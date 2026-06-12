"""Centralized configuration for all browser tests.

Every configurable value (URLs, credentials, timeouts, browser settings)
lives here so test files and helpers can ``from helpers.config import ...``
instead of scattering env lookups and magic numbers.
"""
import os

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# Keep this aligned with m8flow-frontend/vite.config.ts default PORT.
BASE_URL = os.getenv("E2E_URL", "http://localhost:6841")

# Relative API prefix on the frontend origin (Vite proxies ``/v1.0`` to the backend).
# Must match ``VITE_BACKEND_BASE_URL`` (see ``m8flow-frontend/vite.config.ts``).
API_PREFIX = os.getenv("BROWSER_TEST_API_PREFIX", "/v1.0")

# ---------------------------------------------------------------------------
# Default login (tenant-admin)
# ---------------------------------------------------------------------------
DEFAULT_USERNAME = os.getenv("BROWSER_TEST_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("BROWSER_TEST_PASSWORD", "admin")
DEFAULT_TENANT = os.getenv("BROWSER_TEST_TENANT", "m8flow")

# ---------------------------------------------------------------------------
# Role credentials (initial Keycloak password = username)
# ---------------------------------------------------------------------------
SUPER_ADMIN_USERNAME = os.getenv("BROWSER_TEST_SUPER_ADMIN_USERNAME", "super-admin")
SUPER_ADMIN_PASSWORD = os.getenv("BROWSER_TEST_SUPER_ADMIN_PASSWORD", "super-admin")
MASTER_REALM_IDENTIFIER = os.getenv("M8FLOW_KEYCLOAK_MASTER_REALM", "master")

NO_ROLE_USERNAME = os.getenv("BROWSER_TEST_NO_ROLE_USERNAME", "no-role")
NO_ROLE_PASSWORD = os.getenv("BROWSER_TEST_NO_ROLE_PASSWORD", "no-role")
CROSS_TENANT_USERNAME = os.getenv("BROWSER_TEST_CROSS_TENANT_USERNAME", "qatest-user")
CROSS_TENANT_PASSWORD = os.getenv("BROWSER_TEST_CROSS_TENANT_PASSWORD", "qatest-user")
CROSS_TENANT_LOGIN_TENANT = os.getenv("BROWSER_TEST_CROSS_TENANT_LOGIN_TENANT", "acme")

ROLE_USERS = {
    "editor":   {"username": "editor",   "password": os.getenv("BROWSER_TEST_EDITOR_PASSWORD",   "editor")},
    "viewer":   {"username": "viewer",   "password": os.getenv("BROWSER_TEST_VIEWER_PASSWORD",   "viewer")},
    "reviewer": {"username": "reviewer", "password": os.getenv("BROWSER_TEST_REVIEWER_PASSWORD", "reviewer")},
}

# Substring match for the Form-Driven / IT Support sample in the gallery.
# Auto-loaded zips use ``sample_template_loader._derive_display_name`` (hyphens →
# spaces, ``.title()``), so the card shows e.g. "Form Driven Approval …" not
# "Form-Driven Approval". Override with ``BROWSER_TEST_SAMPLE_TEMPLATE_SUBSTRING``.
SAMPLE_TEMPLATE_NAME_SUBSTRING = os.getenv(
    "BROWSER_TEST_SAMPLE_TEMPLATE_SUBSTRING",
    "Form Driven",
)


def lane_owner_identifier(username: str) -> str:
    """Return ``username@tenant`` for sample template script assignees."""

    return f"{username}@{DEFAULT_TENANT}"


# ---------------------------------------------------------------------------
# Timeouts (milliseconds)
# ---------------------------------------------------------------------------
KC_TIMEOUT = 30_000
POST_LOGIN_TIMEOUT = 30_000
APP_READY_TIMEOUT = 30_000
NAV_TIMEOUT = 45_000
PAGE_DATA_TIMEOUT = 15_000
ELEMENT_TIMEOUT = 10_000
SHORT_TIMEOUT = 5_000

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
MAX_LOGIN_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# Browser context
# ---------------------------------------------------------------------------
VIEWPORT = {"width": 1280, "height": 720}
