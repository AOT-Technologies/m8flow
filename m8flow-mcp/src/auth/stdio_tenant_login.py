"""Interactive tenant selection for stdio mode.

stdio has no browser in the request path, so on startup — when the authenticated user
belongs to more than one tenant — we briefly open a local loopback page for the user to
pick a tenant, then authenticate that tenant via the same backend finalization the web
app uses (``tenant_selection.finalize_tenant``). Single-tenant users are finalized
automatically with no prompt.

This is best-effort and time-bounded: if no selection is made (headless, no browser, or
timeout) we proceed without a selection and tenant-scoped tools surface a clear
"select a tenant" message rather than a raw Access Denied.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.auth.tenant_selection import (
    finalize_tenant,
    get_process_selected_session,
    organization_memberships,
    render_selection_page,
    set_process_selected_session,
)
from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Bounded so we never hang the MCP stdio handshake indefinitely.
_SELECTION_TIMEOUT_SECONDS = 120

# Cap the accepted POST body; the form only carries a short tenant alias, so anything
# larger is malformed/hostile. Loopback-only, but bound it anyway.
_MAX_POST_BODY_BYTES = 64 * 1024


def run_stdio_tenant_selection() -> None:
    """Resolve the active tenant for a stdio session before serving requests."""
    token = _initial_token()
    if not token:
        return

    memberships = organization_memberships(token)
    if not memberships:
        # No organization memberships: single-tenant/service token — nothing to select.
        return

    if len(memberships) == 1:
        _finalize_sync(token, memberships[0]["alias"])
        return

    if get_process_selected_session():
        return  # Already selected earlier in this process.

    alias = _prompt_via_loopback(memberships)
    if alias:
        _finalize_sync(token, alias)
    else:
        logger.warning(
            "No tenant selected for this multi-tenant stdio session; "
            "tenant-scoped operations will ask you to select a tenant."
        )


def _initial_token() -> str | None:
    """Return the raw shared-realm token for the configured stdio identity."""
    raw = os.getenv("M8FLOW_BEARER_TOKEN") or os.getenv("FORMSFLOW_BEARER_TOKEN") or settings.m8flow_bearer_token
    if raw:
        return raw[7:] if raw.startswith("Bearer ") else raw

    if settings.has_ropc_credentials:
        try:
            from src.auth.token_service import token_service

            return token_service.get_token_sync()
        except Exception as exc:  # pragma: no cover - depends on Keycloak availability
            logger.warning("Could not acquire a token for stdio tenant selection: %s", exc)
    return None


def _finalize_sync(token: str, alias: str) -> None:
    """Finalize a tenant (blocking) and store it for the process."""
    try:
        finalized = asyncio.run(finalize_tenant(token, alias))
    except Exception as exc:  # pragma: no cover - depends on backend availability
        logger.warning("Tenant finalization failed for alias=%s: %s", alias, exc)
        return
    if finalized is not None:
        set_process_selected_session(finalized)
        logger.info("stdio tenant selected: alias=%s tenant_id=%s", alias, finalized.tenant_id)


def _prompt_via_loopback(memberships: list[dict[str, Any]]) -> str | None:
    """Open a one-shot local page for tenant selection; return the chosen alias."""
    import webbrowser

    valid_aliases = {m["alias"] for m in memberships if m.get("alias")}
    page = render_selection_page(memberships, action="/", method="post")
    selected: dict[str, str] = {}
    done = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._send_html(page)

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                length = 0
            if length < 0 or length > _MAX_POST_BODY_BYTES:
                self._send_html("<h1>Invalid tenant selection.</h1>", status=400)
                return
            # errors="replace": malformed bytes on the socket must not raise here.
            body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
            tenant = urllib.parse.parse_qs(body).get("tenant", [""])[0].strip()
            if tenant and tenant in valid_aliases:
                selected["alias"] = tenant
                self._send_html("<h1>Tenant selected. You can close this tab.</h1>")
                done.set()
            else:
                self._send_html("<h1>Invalid tenant selection.</h1>", status=400)

        def log_message(self, *args: Any) -> None:  # noqa: D401 - silence default stderr spam
            return

        def _send_html(self, content: str, status: int = 200) -> None:
            data = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    except OSError as exc:  # pragma: no cover - can't bind loopback
        logger.warning("Could not start local tenant selection server: %s", exc)
        return None

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    # Log (to stderr) so the user can open it manually; never write to stdout in stdio mode.
    logger.warning("Multiple tenants available. Open %s to select a tenant.", url)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    with contextlib.suppress(Exception):  # pragma: no cover - headless
        webbrowser.open(url)

    try:
        done.wait(_SELECTION_TIMEOUT_SECONDS)
    finally:
        server.shutdown()
        server.server_close()

    return selected.get("alias")
