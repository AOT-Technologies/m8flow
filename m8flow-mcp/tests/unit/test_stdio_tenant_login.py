"""stdio tenant selection must never block the MCP handshake."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

from src.auth import stdio_tenant_login as stl

TWO_TENANTS = [{"alias": "a"}, {"alias": "b"}]


def test_multi_tenant_prompt_does_not_block_startup():
    release = threading.Event()
    finalized: list[str] = []

    def slow_prompt(_memberships):
        release.wait(5)  # a user who has not picked a tenant yet
        return "b"

    with (
        patch.object(stl, "_initial_token", return_value="tok"),
        patch.object(stl, "organization_memberships", return_value=TWO_TENANTS),
        patch.object(stl, "get_process_selected_session", return_value=None),
        patch.object(stl, "_prompt_via_loopback", side_effect=slow_prompt),
        patch.object(stl, "_finalize_sync", side_effect=lambda _t, alias: finalized.append(alias)),
    ):
        started = time.monotonic()
        stl.run_stdio_tenant_selection()
        assert time.monotonic() - started < 1  # returned while the prompt is still open
        assert finalized == []

        release.set()
        for _ in range(50):
            if finalized:
                break
            time.sleep(0.05)
    assert finalized == ["b"]


def test_single_tenant_is_finalized_before_serving():
    with (
        patch.object(stl, "_initial_token", return_value="tok"),
        patch.object(stl, "organization_memberships", return_value=[{"alias": "only"}]),
        patch.object(stl, "_finalize_sync") as finalize,
    ):
        stl.run_stdio_tenant_selection()
    finalize.assert_called_once_with("tok", "only")


def test_selection_pending_flag_spans_the_background_prompt():
    from src.auth import tenant_selection as ts

    release = threading.Event()
    states: list[str | None] = []

    def slow_prompt(_memberships):
        states.append(ts.get_process_selection_pending())
        release.wait(5)
        return "b"

    with (
        patch.object(stl, "_initial_token", return_value="tok"),
        patch.object(stl, "organization_memberships", return_value=TWO_TENANTS),
        patch.object(stl, "get_process_selected_session", return_value=None),
        patch.object(stl, "_prompt_via_loopback", side_effect=slow_prompt),
        patch.object(stl, "_finalize_sync"),
    ):
        stl.run_stdio_tenant_selection()
        assert ts.get_process_selection_pending() is not None  # pending right after startup
        release.set()
        for _ in range(50):
            if ts.get_process_selection_pending() is None:
                break
            time.sleep(0.05)
    assert states == [""]
    assert ts.get_process_selection_pending() is None  # cleared once the picker finishes
