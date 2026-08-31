"""Guard test: every registered MCP tool must carry classification metadata.

Asserts that every tool registered by ``register_tools()`` declares a non-empty
``tags`` set and ``annotations`` with an explicit ``readOnlyHint`` (never
``None``). It builds the real FastMCP server rather than the lightweight
``MockFastMCP`` used by other unit tests, which discards
``tags``/``annotations``, so a future tool added without that metadata fails
loudly here instead of shipping unclassified.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from src.mcp_tools import register_tools


@pytest.fixture
def mcp() -> FastMCP:
    """Real FastMCP instance with every m8flow tool registered."""
    server = FastMCP("m8flow-test")
    register_tools(server)
    return server


@pytest.mark.asyncio
async def test_every_tool_has_tags_and_annotations(mcp: FastMCP):
    # NOTE: this fastmcp version (pinned in uv.lock) exposes tool enumeration
    # as the async FastMCP.list_tools() -> Sequence[Tool]; there is no
    # get_tools() on this release.
    tools = await mcp.list_tools()

    assert tools, "No tools were registered — register_tools() may be broken"

    missing_tags: list[str] = []
    missing_annotations: list[str] = []
    missing_read_only_hint: list[str] = []

    for tool in tools:
        name = tool.name
        if not tool.tags:
            missing_tags.append(name)
        if tool.annotations is None:
            missing_annotations.append(name)
        elif tool.annotations.readOnlyHint is None:
            missing_read_only_hint.append(name)

    failures = []
    if missing_tags:
        failures.append(f"missing non-empty tags: {sorted(missing_tags)}")
    if missing_annotations:
        failures.append(f"missing annotations: {sorted(missing_annotations)}")
    if missing_read_only_hint:
        failures.append(f"annotations.readOnlyHint left as None (must be True/False): {sorted(missing_read_only_hint)}")

    assert not failures, (
        "Every MCP tool must declare a non-empty tags set and annotations with an "
        "explicit readOnlyHint (see AGENTS.md tool classification / M8F-404). "
        "Offending tool(s):\n" + "\n".join(failures)
    )
