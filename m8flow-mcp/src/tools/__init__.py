"""MCP tool registry for m8flow.

Every tool module uses the @tool decorator to self-register.
Call register_all() once at startup to trigger imports,
then use get_tool() / list_tools() from the server layer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Internal registry — populated by the @tool decorator
# ---------------------------------------------------------------------------

_registry: dict[str, ToolDefinition] = {}


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata + handler for a single MCP tool."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON-Schema describing accepted params
    required_roles: list[str]  # user must hold *any one* of these roles
    handler: Callable[[dict[str, Any], str], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Decorator used by tool modules
# ---------------------------------------------------------------------------


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    required_roles: list[str] | None = None,
) -> Callable[[Callable[[dict[str, Any], str], Awaitable[Any]]], Callable[[dict[str, Any], str], Awaitable[Any]]]:
    """Register an async function as an MCP tool.

    The decorated function must have the signature::

        async def handler(params: dict, token: str) -> Any

    Args:
        name: Tool name (used in MCP protocol)
        description: Human-readable description for LLM
        parameters: JSON Schema for tool parameters
        required_roles: List of roles that can use this tool (default: all)

    Example:
        @tool(
            name="list_tasks",
            description="List user tasks",
            parameters={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "default": 1}
                }
            },
            required_roles=["viewer", "admin"]
        )
        async def list_tasks(params: dict, token: str):
            ...
    """

    def decorator(
        func: Callable[[dict[str, Any], str], Awaitable[Any]],
    ) -> Callable[[dict[str, Any], str], Awaitable[Any]]:
        _registry[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            required_roles=required_roles or [],  # Empty list = no restrictions
            handler=func,
        )
        return func

    return decorator


# ---------------------------------------------------------------------------
# Public helpers consumed by server.py
# ---------------------------------------------------------------------------


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool definition by name."""
    return _registry.get(name)


def list_tools() -> list[ToolDefinition]:
    """List all registered tools."""
    return list(_registry.values())


def register_all() -> None:
    """Import every tool module so their @tool decorators execute."""
    # Import all tool modules to trigger decorator execution
    from src.tools import process_instances, process_models, tasks  # noqa: F401


__all__ = [
    "tool",
    "ToolDefinition",
    "get_tool",
    "list_tools",
    "register_all",
]
