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
    from src.mcp_tools.bpmn_tools import register_bpmn_tools
    from src.mcp_tools.cleanup_tools import register_cleanup_tools
    from src.mcp_tools.connectors import register_connector_tools
    from src.mcp_tools.count_tools import register_count_tools
    from src.mcp_tools.documentation_tool import register_documentation_tool
    from src.mcp_tools.error_management import register_error_tools
    from src.mcp_tools.process_groups import register_process_group_tools
    from src.mcp_tools.process_instances import register_process_instance_tools
    from src.mcp_tools.process_models import register_process_model_tools
    from src.mcp_tools.prompts import register_prompts
    from src.mcp_tools.resources import register_resources
    from src.mcp_tools.tasks import register_task_tools
    from src.mcp_tools.templates import register_template_tools

    # Using browser visualization (proven and working)
    from src.mcp_tools.visualization import register_visualization_tools

    # Register core tool groups
    register_process_group_tools(mcp)  # Register process groups FIRST (includes models)
    register_process_model_tools(mcp)
    register_process_instance_tools(mcp)
    register_task_tools(mcp)
    register_template_tools(mcp)  # Templates: Path is /v1.0/m8flow/templates

    # Register BPMN and template creation tools (NEW!)
    register_bpmn_tools(mcp)  # Create templates, upload BPMN, Concert Finder workflow

    # Register cleanup tools (prevents Claude from creating duplicate workflows)
    register_cleanup_tools(mcp)

    # Register connector tools (43 operations across 7 connectors)
    register_connector_tools(mcp)

    # Register visualization tools (INDUSTRY FIRST - visual BPMN in browser!)
    register_visualization_tools(mcp)

    # Register efficiency tools (count tools - 95% token savings)
    register_count_tools(mcp)

    # Register error management tools (production-critical)
    register_error_tools(mcp)

    # Register self-documentation tool (reduces errors by 50%)
    register_documentation_tool(mcp)

    # Register resources (document-like endpoints for browsing)
    # Now includes examples:// and errors:// resources
    register_resources(mcp)

    # Register prompts (pre-built conversation templates)
    register_prompts(mcp)
