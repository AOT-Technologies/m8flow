"""Post-auth redirect validation to prevent open redirects.

Login, tenant finalization, login_return, and logout accept a caller-supplied
``redirect_url``. Prefer same-app relative paths; absolute URLs must match an
explicit origin allowlist derived from configured frontend/CORS origins.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from m8flow_backend.errors import ApiError

# Keep in sync with app.py local UI defaults (designer :6853, frontend :6841, Vite).
_DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:6841",
    "http://127.0.0.1:6841",
    "http://localhost:6853",
    "http://127.0.0.1:6853",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

_SAFE_FALLBACK_PATH = "/"


def _normalize_origin(raw: str) -> str | None:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return None
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def allowed_redirect_origins() -> frozenset[str]:
    """Origins safe for post-login / post-logout browser redirects."""
    origins: set[str] = set()
    for default in _DEFAULT_ALLOWED_ORIGINS:
        normalized = _normalize_origin(default)
        if normalized:
            origins.add(normalized)

    for key in (
        "M8FLOW_BACKEND_URL_FOR_FRONTEND",
        "M8FLOW_BACKEND_URL_FRONTEND",
        "M8FLOW_FRONTEND_BASE_URL",
        "M8FLOW_APP_PUBLIC_BASE_URL",
        "M8FLOW_KEYCLOAK_ADDITIONAL_LOGOUT_REDIRECT_URIS",
    ):
        raw = os.environ.get(key) or ""
        # ADDITIONAL_LOGOUT may be space/comma separated.
        for part in raw.replace(" ", ",").split(","):
            normalized = _normalize_origin(part)
            if normalized:
                origins.add(normalized)

    cors_raw = os.environ.get("M8FLOW_BACKEND_CORS_ALLOW_ORIGINS") or ""
    for part in cors_raw.split(","):
        normalized = _normalize_origin(part)
        if normalized:
            origins.add(normalized)

    return frozenset(origins)


def is_safe_redirect_url(redirect_url: str, *, allowed_origins: frozenset[str] | None = None) -> bool:
    """True when ``redirect_url`` is a relative app path or an allowlisted absolute URL."""
    if not redirect_url or not isinstance(redirect_url, str):
        return False
    # Block header/CRLF injection and backslash normalization tricks before strip.
    if any(ch in redirect_url for ch in ("\r", "\n", "\\", "\0")):
        return False
    candidate = redirect_url.strip()
    if not candidate:
        return False

    # Relative application path only (not protocol-relative //evil.example).
    if candidate.startswith("/") and not candidate.startswith("//"):
        parsed = urlparse(candidate)
        return parsed.scheme == "" and parsed.netloc == ""

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowlist = allowed_origins if allowed_origins is not None else allowed_redirect_origins()
    return origin in allowlist


def require_safe_redirect_url(redirect_url: str) -> str:
    """Return a validated redirect URL or raise ``ApiError`` (400)."""
    candidate = (redirect_url or "").strip()
    if not candidate:
        raise ApiError("redirect_url_required", "redirect_url is required", 400)
    if not is_safe_redirect_url(candidate):
        raise ApiError(
            "invalid_redirect_url",
            "redirect_url must be a relative application path or an allowlisted origin.",
            400,
        )
    return candidate


def safe_redirect_or_fallback(redirect_url: str | None) -> str:
    """Re-check a previously stored redirect; fall back to ``/`` if unsafe."""
    candidate = (redirect_url or "").strip()
    if candidate and is_safe_redirect_url(candidate):
        return candidate
    return _SAFE_FALLBACK_PATH
