"""MCP tools for m8flow workflow management."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_tools(mcp: "FastMCP") -> None:
    """Register all m8flow tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """
    # Import tool registration functions
    from src.mcp_tools.process_groups import register_process_group_tools
    from src.mcp_tools.process_instances import register_process_instance_tools
    from src.mcp_tools.process_models import register_process_model_tools
    from src.mcp_tools.tasks import register_task_tools

    # Register each tool group
    register_process_group_tools(mcp)  # Register process groups FIRST (includes models)
    register_process_model_tools(mcp)
    register_process_instance_tools(mcp)
    register_task_tools(mcp)
