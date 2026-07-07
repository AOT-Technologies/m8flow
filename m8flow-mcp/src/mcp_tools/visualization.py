"""
Visualization tools for M8Flow MCP.

Provides workflow visualization by returning BPMN XML content.
"""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.url import quote_path_segment

client = M8flowAPIClient()


async def view_workflow(process_model_id: str) -> str:
    """Get BPMN XML content for a workflow.

    Returns the BPMN XML content that can be visualized using external tools
    or saved to a file for viewing in BPMN editors.

    Args:
        process_model_id: Process model identifier (e.g., "demo-process-group/simple")

    Returns:
        BPMN XML content or error message

    Example:
        view_workflow("demo-process-group/single-approval")
        # Returns BPMN XML content
    """
    token = get_auth_token()
    modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

    # Get process model to find BPMN file
    model = await client.get(f"/v1.0/process-models/{modified_id}", token)

    # Get first .bpmn file (usually matches model ID)
    bpmn_filename = f"{model['id']}.bpmn"

    # Get BPMN file content
    file_response = await client.get(
        f"/v1.0/process-models/{modified_id}/files/{quote_path_segment(bpmn_filename)}", token
    )

    bpmn_xml = file_response.get("file_contents", "")

    if not bpmn_xml or not bpmn_xml.strip():
        return f"❌ Error: No BPMN content found for {process_model_id}"

    # Save to temp file for easy access
    temp_file = Path(tempfile.gettempdir()) / f"m8flow_{process_model_id.replace('/', '_')}.bpmn"
    temp_file.write_text(bpmn_xml, encoding="utf-8")

    return f"""✅ BPMN Content Retrieved

📄 Workflow: {process_model_id}
💾 Saved to: {temp_file}

BPMN XML:
{bpmn_xml}

To visualize, use any BPMN viewer tool or open the saved file."""


async def view_workflow_from_template(template_id: int) -> str:
    """Get BPMN XML content for a template.

    Returns the BPMN XML content from a template that can be visualized
    using external tools.

    Args:
        template_id: Template ID (e.g., 1)

    Returns:
        BPMN XML content or error message

    Example:
        view_workflow_from_template(1)
        # Returns template BPMN XML content
    """
    token = get_auth_token()

    # Get template with BPMN content
    template = await client.get(f"/v1.0/m8flow/templates/{template_id}", token, params={"include_bpmn": "true"})

    bpmn_xml = template.get("bpmnContent", "")

    if not bpmn_xml or not bpmn_xml.strip():
        return f"❌ Error: No BPMN content found for template {template_id}"

    # Save to temp file
    temp_file = Path(tempfile.gettempdir()) / f"m8flow_template_{template_id}.bpmn"
    temp_file.write_text(bpmn_xml, encoding="utf-8")

    template_name = template.get("name", f"Template {template_id}")

    return f"""✅ BPMN Content Retrieved

📄 Template: {template_name}
💾 Saved to: {temp_file}

BPMN XML:
{bpmn_xml}

To visualize, use any BPMN viewer tool or open the saved file."""


async def view_process_instance(process_model_id: str, process_instance_id: int) -> str:
    """Get BPMN XML content for a specific process instance.

    Returns the workflow BPMN with execution state information.

    Args:
        process_model_id: Process model identifier
        process_instance_id: Process instance ID

    Returns:
        BPMN XML content or error message

    Example:
        view_process_instance("demo-process-group/simple", 114)
        # Returns instance BPMN XML content
    """
    token = get_auth_token()
    modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

    # Get process instance (includes bpmn_xml_file_contents)
    instance = await client.get(f"/v1.0/process-instances/{modified_id}/{process_instance_id}", token)

    bpmn_xml = instance.get("bpmn_xml_file_contents", "")

    if not bpmn_xml or not bpmn_xml.strip():
        # Fallback to model BPMN
        model = await client.get(f"/v1.0/process-models/{modified_id}", token)
        bpmn_filename = f"{model['id']}.bpmn"
        file_response = await client.get(
            f"/v1.0/process-models/{modified_id}/files/{quote_path_segment(bpmn_filename)}", token
        )
        bpmn_xml = file_response.get("file_contents", "")

    if not bpmn_xml or not bpmn_xml.strip():
        return f"❌ Error: No BPMN content found for instance {process_instance_id}"

    # Save to temp file
    temp_file = Path(tempfile.gettempdir()) / f"m8flow_instance_{process_instance_id}.bpmn"
    temp_file.write_text(bpmn_xml, encoding="utf-8")

    status = instance.get("status", "unknown")

    return f"""✅ BPMN Content Retrieved

📄 Instance: #{process_instance_id}
📊 Status: {status}
💾 Saved to: {temp_file}

BPMN XML:
{bpmn_xml}

To visualize, use any BPMN viewer tool or open the saved file."""


def register_visualization_tools(mcp: "FastMCP") -> None:
    """Register visualization tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """
    mcp.tool()(view_workflow)
    mcp.tool()(view_workflow_from_template)
    mcp.tool()(view_process_instance)
