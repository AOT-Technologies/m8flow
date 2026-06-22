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

# Direct backend origin for API assertions. The frontend's ``config.tsx`` derives
# the backend base URL on localhost as ``{frontend_port - 1}`` (e.g. 6841 -> 6840)
# and the app calls the backend DIRECTLY there (not via the Vite proxy), so test
# API calls must target the backend origin too. Cookies are domain-``localhost``
# (port-agnostic), so the auth cookie is sent to both ports.
from urllib.parse import urlparse as _urlparse  # noqa: E402

_FE = _urlparse(BASE_URL)
_BACKEND_PORT = (_FE.port - 1) if _FE.port else None
BACKEND_BASE_URL = os.getenv("BROWSER_TEST_BACKEND_URL") or (
    f"{_FE.scheme}://{_FE.hostname}:{_BACKEND_PORT}" if _BACKEND_PORT else BASE_URL
)

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
# Group-based task assignment (tasks/ suite)
# ---------------------------------------------------------------------------
# The "Single Approval - ( WFH Approval Process with Timeout )" sample template
# assigns its tasks to Keycloak groups via BPMN lanes (no secrets required):
#   * "Submit WFH Request"  -> Submitters
#   * "Review WFH Request"  -> Approvers
# The group-visibility assertions target the Review task (Approvers lane).
# ``sample_template_loader._derive_display_name`` STRIPS the parenthetical from
# the zip filename (``re.sub(r"\s*\([^)]*\)\s*", " ", stem)``), so the gallery
# card for this template is "Single Approval" -- it does NOT contain "WFH".
# Match on the surviving (and unique) display name instead.
WFH_TEMPLATE_NAME_SUBSTRING = os.getenv("BROWSER_TEST_WFH_TEMPLATE_SUBSTRING", "Single Approval")

# BPMN lane names == Keycloak group identifiers (see sample_templates/README.md).
ASSIGNED_GROUP_NAME = os.getenv("BROWSER_TEST_ASSIGNED_GROUP", "Approvers")
SUBMITTER_GROUP_NAME = os.getenv("BROWSER_TEST_SUBMITTER_GROUP", "Submitters")

# Initiator: starts the instance and submits the request form (Submitters lane).
# ``submitter`` is seeded into the Submitters group and may start processes.
INITIATOR_USER = {
    "username": os.getenv("BROWSER_TEST_INITIATOR_USERNAME", "submitter"),
    "password": os.getenv("BROWSER_TEST_INITIATOR_PASSWORD", "submitter"),
}

# Approvers member #1: seeded into the Approvers org group; the ``reviewer``
# permission group grants ``manage-tasks`` so this user can complete the task.
APPROVER_1_USER = {
    "username": os.getenv("BROWSER_TEST_APPROVER_1_USERNAME", "reviewer"),
    "password": os.getenv("BROWSER_TEST_APPROVER_1_PASSWORD", "reviewer"),
}

# Approvers member #2 (second-member visibility check). Default seeding puts
# only one user in each org group, so by default this REUSES the existing
# Approvers member (member #1) in an independent browser session -- confirming
# group-member visibility is not tied to a single session. Set
# BROWSER_TEST_APPROVER_2_USERNAME to a genuinely distinct user (also added to
# the Approvers group) for a stricter multi-user check.
APPROVER_2_USERNAME = os.getenv("BROWSER_TEST_APPROVER_2_USERNAME", APPROVER_1_USER["username"])
APPROVER_2_PASSWORD = os.getenv("BROWSER_TEST_APPROVER_2_PASSWORD", APPROVER_1_USER["password"])
APPROVER_2_USER = {"username": APPROVER_2_USERNAME, "password": APPROVER_2_PASSWORD}

# True when member #2 is a genuinely distinct user from member #1.
APPROVER_2_IS_DISTINCT = APPROVER_2_USERNAME != APPROVER_1_USER["username"]

# Negative case: a user with general task permissions who is NOT in Approvers.
# ``editor`` is seeded into Designers (not Approvers), so any "task not visible"
# result is attributable to group membership rather than a blanket permission
# denial -- a stronger negative assertion than using a read-only viewer.
NON_MEMBER_USER = {
    "username": os.getenv("BROWSER_TEST_NON_MEMBER_USERNAME", "editor"),
    "password": os.getenv("BROWSER_TEST_NON_MEMBER_PASSWORD", "editor"),
}


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
