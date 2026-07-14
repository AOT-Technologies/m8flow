"""MCP Prompts for m8flow - Pre-built conversation templates.

Prompts are reusable conversation starters that guide users through
common m8flow workflows. They combine resources and tools into
guided experiences.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_prompts(mcp: "FastMCP") -> None:
    """Register all m8flow prompts with the MCP server.

    Prompts are conversation templates that guide users through
    common workflows by combining resources and tools.
    """

    @mcp.prompt()
    def browse_workflows():
        """Browse all available workflows organized by category."""
        return {
            "name": "browse_workflows",
            "description": "Browse and explore available workflow templates",
            "arguments": [],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """Show me all available workflows in m8flow.

Please read the discovery://workflows resource and show me:
1. All workflow categories
2. Workflow names and descriptions
3. Which ones are executable

Format the results in a clear, organized way.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def start_workflow():
        """Start a new workflow instance with guided steps."""
        return {
            "name": "start_workflow",
            "description": "Start a new workflow instance (guided)",
            "arguments": [
                {
                    "name": "workflow_id",
                    "description": "Process model identifier (e.g., 'demo-group/approval')",
                    "required": False,
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """I want to start a new workflow instance.

Please help me:
1. If I haven't specified a workflow_id, show me available workflows using discovery://workflows
2. Once we have a workflow_id, start it using start_process_instance tool
3. After starting, show me the workflow status using workflow://{instance_id} resource
4. Tell me what tasks are waiting

Walk me through this step by step.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def check_my_tasks():
        """View and manage my pending tasks."""
        return {
            "name": "check_my_tasks",
            "description": "View all my pending tasks",
            "arguments": [],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """Show me all my pending tasks.

Please:
1. Read discovery://tasks resource to get task overview
2. Show me each task with:
   - Task name
   - Which workflow it belongs to
   - When it was created
   - What action is needed

If I have many tasks, organize them by workflow.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def complete_task():
        """Complete a workflow task with guided steps."""
        return {
            "name": "complete_task",
            "description": "Complete a task (guided)",
            "arguments": [
                {"name": "process_instance_id", "description": "Workflow instance ID", "required": False},
                {"name": "task_id", "description": "Task ID or name", "required": False},
            ],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """I want to complete a workflow task.

Please help me:
1. If I haven't specified which task, read discovery://tasks to show available tasks
2. Once we identify the task, read task://{process_instance_id}/{task_id} to see details
3. Ask me for any required data
4. Complete the task using complete_task tool
5. Show updated workflow status using workflow://{process_instance_id}

Guide me through this process.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def workflow_status():
        """Check the status of a workflow instance."""
        return {
            "name": "workflow_status",
            "description": "Check workflow instance status",
            "arguments": [{"name": "instance_id", "description": "Workflow instance ID", "required": True}],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """Show me the status of workflow instance {instance_id}.

Please:
1. Read workflow://{instance_id} resource
2. Show me:
   - Current status
   - Started when
   - Current step/task
   - What's waiting for action
   - Recent activity

Format it in a clear, easy-to-understand way.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def understand_bpmn():
        """Understand how a workflow is designed."""
        return {
            "name": "understand_bpmn",
            "description": "Understand workflow design and structure",
            "arguments": [
                {
                    "name": "model_id",
                    "description": "Process model identifier (e.g., 'demo-group/approval')",
                    "required": False,
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """Explain how this workflow works.

Please:
1. If model_id not specified, show available workflows from discovery://workflows
2. Read bpmn://{model_id} resource to see the workflow definition
3. Explain:
   - What this workflow does
   - What are the main steps
   - What decisions are made
   - What tasks require human action
   - What happens automatically

Explain it in simple terms, like you're teaching someone who's never seen BPMN.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def create_workflow():
        """Create a new workflow template (guided)."""
        return {
            "name": "create_workflow",
            "description": "Create a new workflow template",
            "arguments": [],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """I want to create a new workflow template.

Please help me:
1. First, show me existing process groups using list_process_groups tool
2. Ask me:
   - Should I use an existing group or create a new one?
   - What should the workflow be called?
   - What should it do?
3. Guide me through creating the process model
4. Show me next steps for adding BPMN definition

Walk me through this step by step.""",
                    },
                }
            ],
        }

    @mcp.prompt()
    def troubleshoot_workflow():
        """Troubleshoot a stuck or failing workflow."""
        return {
            "name": "troubleshoot_workflow",
            "description": "Troubleshoot workflow issues",
            "arguments": [
                {"name": "instance_id", "description": "Workflow instance ID that has issues", "required": True}
            ],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": """Help me troubleshoot workflow instance {instance_id}.

Please investigate:
1. Read workflow://{instance_id} to see current state
2. Check for:
   - Is it stuck? Where?
   - Are there errors?
   - What tasks are waiting?
   - How long has it been in this state?
3. Read bpmn:// for the model to understand what should happen
4. Suggest possible solutions:
   - What actions can I take?
   - What might be blocking it?
   - Should I complete a task manually?

Give me a clear diagnosis and action plan.""",
                    },
                }
            ],
        }
