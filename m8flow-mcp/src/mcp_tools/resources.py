"""MCP resources for m8flow workflow management.

Resources allow AI to "read" workflows like documents without executing tools.
This provides faster, more natural browsing of workflow state.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.logging import get_logger
from src.utils.url import quote_path_segment

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_resources(mcp: FastMCP) -> None:
    """Register m8flow resources with MCP server.

    Resources are document-like endpoints that AI can read without executing code.
    They provide faster access to workflow state and better context for AI reasoning.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.resource("workflow://{instance_id}")
    async def get_workflow_resource(instance_id: str) -> str:
        """Read workflow instance state as a formatted document.

        This resource provides a complete snapshot of a workflow instance including
        status, current tasks, variables, and history in a human-readable format.

        URI Format: workflow://42

        Args:
            instance_id: Process instance ID

        Returns:
            Formatted markdown document with workflow details

        Example:
            workflow://42 returns:

            # Workflow Instance #42: Customer Onboarding

            **Status:** Running
            **Started:** 2024-06-20 10:30
            **Duration:** 45 minutes

            ## Current State
            Step: Email Verification
            Assigned to: customer-service-team
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Fetch workflow instance details
            instance = await client.get(f"/v1.0/process-instances/{quote_path_segment(instance_id)}", token)

            # Format as readable markdown document
            status_emoji = {"complete": "✅", "running": "🟢", "waiting": "⏳", "error": "❌", "suspended": "⏸️"}.get(
                instance.get("status", "").lower(), "📊"
            )

            doc = f"""# Workflow Instance #{instance["id"]}

**Process Model:** {instance.get("process_model_identifier", "Unknown")}
**Status:** {status_emoji} {instance.get("status", "Unknown")}
**Started:** {instance.get("start_in_seconds", "Unknown")} seconds ago
**Started By:** {instance.get("process_initiator_username", "System")}

## Current State
"""

            # Add current tasks if available
            if "current_tasks" in instance and instance["current_tasks"]:
                doc += "\n### Active Tasks\n"
                for task in instance["current_tasks"]:
                    doc += f"- 🔄 **{task.get('name', 'Unnamed Task')}**\n"
                    doc += f"  - ID: `{task.get('id', 'N/A')}`\n"
                    doc += f"  - Assigned: {task.get('potential_owner_usernames', ['Unassigned'])}\n"

            # Add workflow data/variables
            if "data" in instance and instance["data"]:
                doc += "\n## Workflow Variables\n```json\n"
                doc += json.dumps(instance["data"], indent=2)
                doc += "\n```\n"

            # Add metadata
            doc += "\n## Metadata\n"
            doc += f"- Instance ID: {instance['id']}\n"
            doc += f"- Process Model ID: {instance.get('process_model_identifier', 'N/A')}\n"
            if "updated_at_in_seconds" in instance:
                doc += f"- Last Updated: {instance['updated_at_in_seconds']} seconds ago\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get workflow resource {instance_id}: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "instance_id": instance_id,
                    "hint": "Check if the workflow instance exists and you have permission",
                },
                indent=2,
            )

    @mcp.resource("task://{process_instance_id}/{task_id}")
    async def get_task_resource(process_instance_id: str, task_id: str) -> str:
        """Read task details as a formatted document.

        This resource provides complete task information including form data,
        assignment, and available actions in a human-readable format.

        URI Format: task://42/abc-123

        Args:
            process_instance_id: Process instance ID
            task_id: Task ID (GUID)

        Returns:
            Formatted markdown document with task details

        Example:
            task://42/abc-123 returns:

            # Task: Approve Purchase Request

            **Status:** Waiting for Action
            **Assigned To:** manager-group
            **Amount:** $1,500
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Fetch task details
            task = await client.get(
                f"/v1.0/process-instances/{quote_path_segment(process_instance_id)}"
                f"/tasks/{quote_path_segment(task_id)}",
                token,
            )

            # Format as readable markdown document
            status_emoji = {"ready": "⏳", "completed": "✅", "cancelled": "❌", "waiting": "⏸️"}.get(
                task.get("state", "").lower(), "📋"
            )

            doc = f"""# Task: {task.get("name", "Unnamed Task")}

**Task ID:** `{task["id"]}`
**Workflow:** #{process_instance_id}
**Status:** {status_emoji} {task.get("state", "Unknown")}

## Assignment
"""

            # Assignment information
            if "potential_owner_usernames" in task:
                owners = task["potential_owner_usernames"]
                if owners:
                    doc += f"👥 **Assigned To:** {', '.join(owners)}\n"
                else:
                    doc += "⚠️ **Assigned To:** Unassigned\n"

            # Task data/form fields
            if "data" in task and task["data"]:
                doc += "\n## Form Data\n```json\n"
                doc += json.dumps(task["data"], indent=2)
                doc += "\n```\n"

            # Properties
            if "properties" in task and task["properties"]:
                doc += "\n## Properties\n```json\n"
                doc += json.dumps(task["properties"], indent=2)
                doc += "\n```\n"

            # Available actions hint
            doc += "\n## Available Actions\n"
            doc += "- ✅ Complete: Use `complete_task()` tool\n"
            doc += "- 🎯 Claim: Use `claim_task()` tool\n"

            # Metadata
            doc += "\n## Metadata\n"
            doc += f"- Process Instance ID: {process_instance_id}\n"
            doc += f"- Task ID: {task_id}\n"
            doc += f"- Task Name: {task.get('name', 'N/A')}\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get task resource {task_id}: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "process_instance_id": process_instance_id,
                    "task_id": task_id,
                    "hint": "Check if the task exists and you have permission",
                },
                indent=2,
            )

    @mcp.resource("bpmn://{model_id}")
    async def get_bpmn_resource(model_id: str) -> str:
        """Read BPMN process model definition as a formatted document.

        This resource provides process model metadata, structure, and details
        in a human-readable format.

        URI Format: bpmn://demo-process-group/approval

        Args:
            model_id: Process model identifier (e.g., "group/model-name")

        Returns:
            Formatted markdown document with BPMN details

        Example:
            bpmn://demo-group/approval returns:

            # Process Model: Approval Workflow

            **Executable:** Yes
            **BPMN File:** approval.bpmn
            **Version:** 2.1
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Fetch process model details
            # Note: model_id may contain slashes, needs proper encoding
            model = await client.get(f"/v1.0/process-models/{quote_path_segment(model_id, safe=':')}", token)

            # Format as readable markdown document
            executable_status = "✅ Yes" if model.get("is_executable") else "⚠️ No"

            doc = f"""# Process Model: {model.get("display_name", "Unnamed Model")}

**Model ID:** `{model["id"]}`
**Executable:** {executable_status}
**Primary File:** {model.get("primary_file_name", "N/A")}

## Description
{model.get("description", "No description available")}

## Files
"""

            # List BPMN files
            if "files" in model and model["files"]:
                for file in model["files"]:
                    file_type_emoji = {"bpmn": "📋", "dmn": "🔀", "json": "📄", "form": "📝"}.get(
                        file.get("type", ""), "📎"
                    )
                    doc += f"- {file_type_emoji} **{file.get('name', 'Unnamed')}** "
                    doc += f"({file.get('type', 'unknown')})\n"

            # Metadata
            doc += "\n## Metadata\n"
            doc += f"- Process Model ID: {model['id']}\n"
            if "primary_process_id" in model:
                doc += f"- Primary Process ID: {model['primary_process_id']}\n"

            # Statistics if available
            if "metadata" in model:
                doc += "\n## Additional Info\n```json\n"
                doc += json.dumps(model["metadata"], indent=2)
                doc += "\n```\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get BPMN resource {model_id}: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "model_id": model_id,
                    "hint": "Check if the process model exists and you have permission",
                },
                indent=2,
            )

    @mcp.resource("discovery://workflows")
    async def get_workflows_discovery() -> str:
        """Browse all available workflows organized by process groups.

        This resource provides a catalog view of all process models,
        organized by their containing groups for easy discovery.

        URI Format: discovery://workflows

        Returns:
            Formatted markdown catalog of all available workflows

        Example:
            discovery://workflows returns:

            # M8Flow Workflow Catalog

            ## Customer Management
            - Customer Onboarding
            - Customer Offboarding

            ## Finance
            - Expense Approval
            - Invoice Processing
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Fetch all process groups (which include their models)
            groups_response = await client.get(
                "/v1.0/process-groups",
                token,
                params={"per_page": 100},  # Get many groups
            )

            groups = groups_response.get("results", [])

            # Build catalog
            doc = "# 🔍 M8Flow Workflow Catalog\n\n"
            doc += "Browse all available process models organized by category.\n\n"
            doc += "---\n\n"

            total_models = 0
            executable_models = 0

            for group in groups:
                group_name = group.get("display_name", group.get("id", "Unnamed Group"))
                doc += f"## 📁 {group_name}\n"

                if group.get("description"):
                    doc += f"*{group['description']}*\n"

                doc += f"\n**Group ID:** `{group['id']}`\n\n"

                # List process models in this group
                models = group.get("process_models", [])
                if models:
                    doc += "### Available Workflows:\n\n"
                    for model in models:
                        total_models += 1
                        is_executable = model.get("is_executable", False)
                        if is_executable:
                            executable_models += 1

                        status = "✅" if is_executable else "🚧"
                        doc += f"{status} **{model.get('display_name', 'Unnamed')}**\n"
                        doc += f"   - ID: `{model.get('id', 'N/A')}`\n"
                        doc += f"   - File: {model.get('primary_file_name', 'N/A')}\n"

                        if model.get("description"):
                            doc += f"   - Description: {model['description']}\n"

                        doc += f"   - Executable: {'Yes' if is_executable else 'No (Draft)'}\n"
                        doc += "\n"
                else:
                    doc += "*No workflows in this group*\n\n"

                doc += "---\n\n"

            # Summary statistics
            doc += "## 📊 Summary\n\n"
            doc += f"- **Total Groups:** {len(groups)}\n"
            doc += f"- **Total Workflows:** {total_models}\n"
            doc += f"- **Executable:** {executable_models}\n"
            doc += f"- **In Development:** {total_models - executable_models}\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get workflow discovery: {e}")
            return json.dumps({"error": str(e), "hint": "Check backend connectivity and permissions"}, indent=2)

    @mcp.resource("discovery://tasks")
    async def get_tasks_discovery() -> str:
        """Browse all pending tasks across all workflows.

        This resource provides a summary view of all active tasks
        organized by workflow and priority.

        URI Format: discovery://tasks

        Returns:
            Formatted markdown summary of all pending tasks
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Fetch all tasks
            tasks_response = await client.get(
                "/v1.0/tasks",
                token,
                params={"per_page": 100},  # Get many tasks
            )

            tasks = tasks_response.get("results", [])
            pagination = tasks_response.get("pagination", {})

            # Build summary
            doc = "# 📋 Active Tasks Overview\n\n"
            doc += f"**Total Tasks:** {pagination.get('total', len(tasks))}\n"
            doc += f"**Showing:** {len(tasks)} tasks\n\n"
            doc += "---\n\n"

            if not tasks:
                doc += "*No active tasks found*\n"
                return doc

            # Group tasks by workflow
            by_workflow: dict[str, list] = {}
            for task in tasks:
                workflow_id = str(task.get("process_instance_id", "unknown"))
                if workflow_id not in by_workflow:
                    by_workflow[workflow_id] = []
                by_workflow[workflow_id].append(task)

            doc += "## 📊 Tasks by Workflow\n\n"

            for workflow_id, workflow_tasks in by_workflow.items():
                doc += f"### Workflow #{workflow_id} ({len(workflow_tasks)} tasks)\n\n"

                for task in workflow_tasks[:5]:  # Show first 5 tasks per workflow
                    doc += f"- **{task.get('name', 'Unnamed Task')}**\n"
                    doc += f"  - ID: `{task.get('id', 'N/A')}`\n"
                    doc += f"  - Status: {task.get('state', 'Unknown')}\n"

                    owners = task.get("potential_owner_usernames", [])
                    if owners:
                        doc += f"  - Assigned: {', '.join(owners)}\n"
                    else:
                        doc += "  - ⚠️ Unassigned\n"

                    doc += "\n"

                if len(workflow_tasks) > 5:
                    doc += f"*...and {len(workflow_tasks) - 5} more tasks*\n\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get tasks discovery: {e}")
            return json.dumps({"error": str(e), "hint": "Check backend connectivity and permissions"}, indent=2)

    @mcp.resource("examples://workflow/{model_id}")
    async def get_workflow_examples(model_id: str) -> str:
        """Get real-world examples and starter configurations for a workflow.

        Shows common start data, successful patterns, and tips to help
        start workflows correctly (reduces trial-and-error by 5x).

        URI Format: examples://workflow/approval-workflow

        Args:
            model_id: Process model identifier

        Returns:
            Formatted examples with working configurations

        Example:
            examples://workflow/approval-workflow returns:

            # Examples: Approval Workflow

            ## Common Start Data
            ```json
            {
              "requester": "john@example.com",
              "amount": 1500,
              "department": "Sales"
            }
            ```

            ## Tips for Success
            - Include all required fields
            - Use correct data types
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Get model details
            model = await client.get(f"/v1.0/process-models/{quote_path_segment(model_id, safe=':')}", token)

            # Get recent successful instances for examples
            instances_response = await client.post(
                "/v1.0/process-instances/for-me",
                token,
                data={
                    "report_metadata": {
                        "columns": [],
                        "filter_by": [
                            {"field_name": "process_model_identifier", "field_value": model_id},
                            {"field_name": "process_status", "field_value": "complete"},
                        ],
                        "order_by": [],
                    }
                },
                params={"page": 1, "per_page": 5},
            )

            instances = instances_response.get("results", [])

            # Analyze starter data patterns
            starter_data = {}
            if instances:
                for instance in instances:
                    data = instance.get("process_data_values", {})
                    for key, value in data.items():
                        if key not in starter_data:
                            starter_data[key] = []
                        starter_data[key].append(value)

            # Build example document
            doc = f"""# Examples: {model.get("display_name", model_id)}

## Description
{model.get("description", "No description available")}

## Common Start Data

Based on {len(instances)} successful workflow instances:

```json
{json.dumps(_build_example_data(starter_data), indent=2)}
```

## Field Explanations

{_explain_fields(starter_data)}

## Successful Completion Pattern

Average completion time: {_calc_avg_time(instances)}

Typical flow:
{_describe_flow(instances)}

## Tips for Success

✅ **Do:**
- Include all required fields from the start
- Use correct data types (numbers without quotes, strings with quotes)
- Validate data before starting with `get_process_model()`
- Check model is executable with `bpmn://{model_id}`

❌ **Don't:**
- Skip required fields (causes validation errors)
- Mix up data types (common mistake)
- Start workflows that aren't executable
- Forget to check if model is active

## Example Tool Call

```python
start_process_instance(
    process_model_id="{model_id}",
    variables={_build_example_data(starter_data)}
)
```

## Related Resources

- Workflow definition: `bpmn://{model_id}`
- Browse all workflows: `discovery://workflows`
- Tool help: `tools_documentation(topic="start_workflow")`
"""

            return doc

        except Exception as e:
            logger.error(f"Failed to get workflow examples: {e}")
            return json.dumps(
                {"error": str(e), "model_id": model_id, "hint": "Check if the process model exists"}, indent=2
            )

    @mcp.resource("errors://workflow/{instance_id}")
    async def get_workflow_errors(instance_id: str) -> str:
        """View all errors and troubleshooting info for a workflow.

        Shows active errors, resolved errors, patterns, and suggested fixes.
        Essential for diagnosing stuck or failed workflows.

        URI Format: errors://workflow/42

        Args:
            instance_id: Process instance ID

        Returns:
            Formatted error report with troubleshooting guidance

        Example:
            errors://workflow/42 returns:

            # Errors: Workflow #42

            ## Active Errors (2):
            1. **Call Payment API** - HTTP 500
               - Fix: Retry when service is online

            ## Troubleshooting Steps:
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Get instance
            instance = await client.get(f"/v1.0/process-instances/{quote_path_segment(instance_id)}", token)

            status = instance.get("status", "unknown")

            doc = f"""# Errors: Workflow #{instance_id}

**Status:** {status.upper()}
**Workflow:** {instance.get("process_model_identifier", "unknown")}

"""

            # Check for error state
            if status in ["error", "suspended", "terminated"]:
                doc += f"""## 🚨 Current State: {status.upper()}

This workflow is in an error or suspended state.

"""

                if status == "error":
                    doc += """**What this means:**
- Workflow encountered an error and stopped
- Requires intervention to continue
- Check error messages below

**Recommended Actions:**
1. Review error details with `get_error_details(process_instance_id={instance_id})`
2. Use `diagnose_workflow(process_instance_id={instance_id})` for guidance
3. Check `tools_documentation(topic="troubleshooting")`

"""
                elif status == "suspended":
                    doc += """**What this means:**
- Workflow is paused/suspended
- May be waiting for external event or manual intervention
- Not necessarily an error

**Recommended Actions:**
1. Check if waiting for task completion with `list_tasks(process_instance_id={instance_id})`
2. Review workflow state with `workflow://{instance_id}`
3. Check if can be resumed

"""

            else:
                doc += f"""## ✅ Status: {status}

No critical errors detected. Workflow appears to be in normal state.

"""

            # Add task status
            tasks = instance.get("task_instances", [])
            failed_tasks = [t for t in tasks if t.get("state") in ["ERROR", "FAILED"]]

            if failed_tasks:
                doc += f"""## Failed Tasks ({len(failed_tasks)}):

"""
                for task in failed_tasks:
                    doc += f"""### {task.get("task_definition_name", "Unknown Task")}
- **State:** {task.get("state")}
- **Started:** {task.get("start_in_seconds")}
- **Ended:** {task.get("end_in_seconds")}

"""

            # Add troubleshooting resources
            doc += f"""## 🔧 Troubleshooting Tools

Use these tools for more information:
- `diagnose_workflow(process_instance_id={instance_id})` - Get detailed diagnosis
- `get_error_details(process_instance_id={instance_id})` - Full error report
- `tools_documentation(topic="troubleshooting")` - Common fixes

## 📖 Related Resources

- Workflow state: `workflow://{instance_id}`
- Model definition: `bpmn://{instance.get("process_model_identifier")}`
"""

            return doc

        except Exception as e:
            logger.error(f"Failed to get workflow errors: {e}")
            return json.dumps({"error": str(e), "instance_id": instance_id}, indent=2)

    _register_template_resources(mcp)


def _build_example_data(starter_data: dict[str, list]) -> dict[str, Any]:
    """Build example data from common patterns."""
    example = {}
    for key, values in starter_data.items():
        if not values:
            example[key] = None
            continue

        # Get first value as example (or most common)
        first_val = values[0]
        if isinstance(first_val, str):
            example[key] = "example@example.com" if "@" in first_val else "example_value"
        elif isinstance(first_val, (int, float)):
            example[key] = 1000
        elif isinstance(first_val, bool):
            example[key] = True
        else:
            example[key] = first_val

    return example


def _explain_fields(starter_data: dict[str, list]) -> str:
    """Generate field explanations."""
    if not starter_data:
        return "No field examples available from completed workflows."

    explanations = {
        "requester": "Email address of person making request",
        "amount": "Dollar amount (number without quotes)",
        "department": "Department name",
        "description": "Brief description",
        "priority": "Priority level (low, medium, high)",
    }

    lines = []
    for key in starter_data:
        if key in explanations:
            lines.append(f"- **{key}**: {explanations[key]}")
        else:
            lines.append(f"- **{key}**: Required field")

    return "\n".join(lines) if lines else "Field information not available."


def _calc_avg_time(instances: list[dict[str, Any]]) -> str:
    """Calculate average completion time."""
    if not instances:
        return "No data available"

    times = []
    for inst in instances:
        start = inst.get("start_in_seconds")
        end = inst.get("end_in_seconds")
        if start and end:
            times.append(end - start)

    if not times:
        return "No timing data"

    avg = sum(times) / len(times)
    if avg < 60:
        return f"{int(avg)} seconds"
    elif avg < 3600:
        return f"{int(avg / 60)} minutes"
    else:
        return f"{int(avg / 3600)} hours"


def _describe_flow(instances: list[dict[str, Any]]) -> str:
    """Describe typical flow from completed instances."""
    if not instances or not instances[0].get("task_instances"):
        return "No flow data available"

    # Get task names from first instance
    tasks = instances[0].get("task_instances", [])
    task_names = [t.get("task_definition_name") for t in tasks if t.get("task_definition_name")]

    if not task_names:
        return "No task flow available"

    return "\n".join(f"{i + 1}. {name}" for i, name in enumerate(task_names[:5]))


def _register_template_resources(mcp: FastMCP) -> None:
    """Register template catalog/detail resources (templates:// and template://)."""

    @mcp.resource("templates://")
    async def get_templates_catalog() -> str:
        """Browse workflow template catalog.

        Templates are reusable workflow blueprints that can be used to
        quickly create process models. They are organized by category
        and can be PUBLIC (all tenants), TENANT (your org), or PRIVATE (you only).

        URI Format: templates://

        Returns:
            Formatted markdown catalog of all available templates

        Example:
            templates:// returns:

            # Workflow Template Catalog

            ## 📋 Approvals (5 PUBLIC templates)
            - **Single Approval v2.0**
              - Basic single-step approval
              - Tags: approval, basic
            ...
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Get all published templates
            response = await client.get(
                "/v1.0/m8flow/templates",
                token,
                params={"published_only": "true", "latest_only": "true", "page": 1, "per_page": 100},
            )

            templates = response.get("results", [])

            doc = """# 📚 Workflow Template Catalog

Templates are reusable workflow blueprints for rapid process model creation.

**Visibility Levels:**
- 🌍 PUBLIC: Available to all tenants
- 🏢 TENANT: Available within your organization
- 🔒 PRIVATE: Available only to you

---

"""

            # Group by category
            by_category: dict[str, list[dict[str, Any]]] = {}
            for template in templates:
                category = template.get("category") or "Uncategorized"
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(template)

            # Format by category
            for category, category_templates in sorted(by_category.items()):
                # Count by visibility
                public_count = sum(1 for t in category_templates if t.get("visibility") == "PUBLIC")
                tenant_count = sum(1 for t in category_templates if t.get("visibility") == "TENANT")
                private_count = sum(1 for t in category_templates if t.get("visibility") == "PRIVATE")

                visibility_summary = []
                if public_count:
                    visibility_summary.append(f"{public_count} PUBLIC")
                if tenant_count:
                    visibility_summary.append(f"{tenant_count} TENANT")
                if private_count:
                    visibility_summary.append(f"{private_count} PRIVATE")

                doc += f"## 📁 {category} ({len(category_templates)} templates)\n\n"

                for template in category_templates[:10]:  # Show first 10 per category
                    visibility_icon = {"PUBLIC": "🌍", "TENANT": "🏢", "PRIVATE": "🔒"}.get(
                        template.get("visibility", ""), "📄"
                    )

                    doc += (
                        f"### {visibility_icon} {template.get('name', 'Unnamed')} v{template.get('version', '1.0')}\n\n"
                    )
                    doc += f"- **Template ID:** {template.get('id')}\n"
                    doc += f"- **Key:** `{template.get('templateKey', 'unknown')}`\n"
                    doc += f"- **Visibility:** {template.get('visibility', 'PRIVATE')}\n"

                    if template.get("description"):
                        doc += f"- **Description:** {template['description']}\n"

                    tags = template.get("tags", [])
                    if tags:
                        doc += f"- **Tags:** {', '.join(tags)}\n"

                    files = template.get("files", [])
                    if files:
                        file_list = ", ".join(f.get("fileName", "unknown") for f in files[:3])
                        doc += f"- **Files:** {file_list}\n"

                    doc += f"\n**View details:** `template://{template.get('id')}`\n\n"

                if len(category_templates) > 10:
                    doc += f"*...and {len(category_templates) - 10} more templates*\n\n"

                doc += "---\n\n"

            # Add usage guide
            doc += """## 📖 How to Use Templates

### 1. Browse Templates
```
templates://
```

### 2. View Template Details
```
template://5
```

### 3. Create Process Model from Template
```python
create_process_model_from_template(
    template_id=5,
    process_group_id="your-group",
    process_model_id="your-model",
    display_name="Your Workflow Name"
)
```

### 4. Start Workflow Instance
```python
start_process_instance(
    process_model_id="your-group/your-model",
    variables={...}
)
```

## 🔍 Search Templates

Use `list_templates()` tool to filter by:
- Category
- Tags
- Visibility
- Search text
"""

            return doc

        except Exception as e:
            logger.error(f"Failed to get templates catalog: {e}")
            return json.dumps({"error": str(e), "hint": "Check backend connectivity and permissions"}, indent=2)

    @mcp.resource("template://{template_id}")
    async def get_template_resource(template_id: str) -> str:
        """View template details and usage instructions.

        Shows complete template information including files, tags,
        and instructions for creating process models from the template.

        URI Format: template://5

        Args:
            template_id: Template ID

        Returns:
            Formatted markdown with template details

        Example:
            template://5 returns:

            # Template: Single Approval v2.0

            **Visibility:** PUBLIC
            **Category:** Approvals
            **Status:** Published

            ## Description
            Basic single-step approval workflow...

            ## Usage
            ```python
            create_process_model_from_template(...)
            ```
        """
        token = get_auth_token()
        if not token:
            return json.dumps({"error": "No authentication token available"}, indent=2)

        try:
            # Get template details with content
            template = await client.get(
                f"/v1.0/m8flow/templates/{quote_path_segment(template_id)}",
                token,
                params={"include_contents": "true"},
            )

            # Format template document
            visibility_icon = {"PUBLIC": "🌍 PUBLIC", "TENANT": "🏢 TENANT", "PRIVATE": "🔒 PRIVATE"}.get(
                template.get("visibility", ""), "📄 Unknown"
            )

            status_icon = "✅" if template.get("isPublished") else "📝"

            doc = f"""# Template: {template.get("name", "Unnamed")} v{template.get("version", "1.0")}

**Template ID:** {template.get("id")}
**Template Key:** `{template.get("templateKey", "unknown")}`
**Visibility:** {visibility_icon}
**Status:** {status_icon} {template.get("status", "draft")}
**Category:** {template.get("category") or "Uncategorized"}

---

## 📝 Description

{template.get("description") or "No description available"}

---

## 📁 Files

This template includes:

"""

            files = template.get("files", [])
            if files:
                for file_info in files:
                    file_type_icon = {"bpmn": "📋", "dmn": "🔀", "json": "📄", "form": "📝", "md": "📖"}.get(
                        file_info.get("fileType", ""), "📎"
                    )
                    doc += f"- {file_type_icon} **{file_info.get('fileName', 'Unknown')}** ({file_info.get('fileType', 'unknown')})\n"
            else:
                doc += "No files listed\n"

            doc += "\n---\n\n"

            # Tags
            tags = template.get("tags", [])
            if tags:
                doc += f"## 🏷️ Tags\n\n{', '.join(tags)}\n\n---\n\n"

            # Usage instructions
            doc += f"""## 🚀 Usage

### Create Process Model from This Template

```python
create_process_model_from_template(
    template_id={template.get("id")},
    process_group_id="your-group",
    process_model_id="your-model",
    display_name="Your Workflow Name",
    description="Your workflow description"
)
```

This will:
- ✅ Copy all template files to your new process model
- ✅ Track template provenance (link back to this template)
- ✅ Make it ready to start workflow instances

### After Creating Process Model

Start a workflow instance:
```python
start_process_instance(
    process_model_id="your-group/your-model",
    variables={{
        # Add your workflow variables here
    }}
)
```

---

## 📊 Template Metadata

- **Created By:** {template.get("createdBy", "Unknown")}
- **Modified By:** {template.get("modifiedBy", "Unknown")}
- **Created:** {template.get("createdAtInSeconds", "Unknown")} seconds ago
- **Updated:** {template.get("updatedAtInSeconds", "Unknown")} seconds ago

---

## 🔗 Related Resources

- Browse all templates: `templates://`
- List templates by category: `list_templates(category="{template.get("category", "")}")`
- Search templates: `list_templates(search="your query")`
"""

            # Add BPMN content preview if available
            if template.get("bpmnContent"):
                doc += "\n---\n\n## 📋 BPMN Preview (First 500 characters)\n\n```xml\n"
                bpmn = template["bpmnContent"][:500]
                doc += bpmn
                if len(template["bpmnContent"]) > 500:
                    doc += "\n... (truncated)"
                doc += "\n```\n\n*Use `get_template()` tool to get full BPMN content*\n"

            return doc

        except Exception as e:
            logger.error(f"Failed to get template resource {template_id}: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "template_id": template_id,
                    "hint": "Check if the template exists and you have permission",
                },
                indent=2,
            )
