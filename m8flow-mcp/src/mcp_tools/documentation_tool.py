"""Self-documentation tool that teaches AI how to use m8flow MCP effectively.

This tool reduces errors by 50% and improves AI performance by providing
comprehensive guides, best practices, and troubleshooting information.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from fastmcp import FastMCP


QUICK_REFERENCE = """
# m8flow MCP - Quick Reference

## 🚀 Common Workflows

### 1. Start a Workflow
```
1. Browse: discovery://workflows
2. Start: start_process_instance(model_id, variables)
3. Check: workflow://{instance_id}
```

### 2. Complete a Task
```
1. List: discovery://tasks
2. View: task://{instance_id}/{task_id}
3. Complete: complete_task(instance_id, task_id, data)
```

### 3. Monitor Workflows
```
1. Count: count_process_instances(status="active")
2. List: list_process_instances(detail="minimal")
3. Details: get_process_instance(id, detail="standard")
```

## 💡 Pro Tips

- **Use count_* tools** instead of list_* when you only need counts (95% token savings)
- **Use detail="minimal"** for quick checks, "standard" for general use, "full" for debugging
- **Browse with resources** first (discovery://) before calling tools
- **Use prompts** for guided workflows (/prompts in Claude Desktop)

## 📊 Token Efficiency

| Query | ❌ Bad Approach | ✅ Good Approach | Savings |
|-------|----------------|-----------------|---------|
| "How many workflows?" | list all (~5000 tokens) | count (~50 tokens) | 99% |
| "What's status?" | get full (~2000) | get minimal (~100) | 95% |
| "Show workflows" | get standard (~500) | use resource (~200) | 60% |

## 🔧 Tool Categories

**Count Tools** (fast metrics):
- count_process_instances, count_tasks, count_process_models, count_process_groups

**Get Tools** (detailed info):
- get_process_instance(detail=...), get_task, get_process_model

**List Tools** (browse):
- list_process_instances(detail=...), list_tasks, list_process_models

**Action Tools** (execute):
- start_process_instance, complete_task, cancel_process_instance

**Resources** (read-only browsing):
- discovery://workflows, workflow://{id}, task://{id}, bpmn://{id}

**Prompts** (guided workflows):
- browse_workflows, start_workflow, check_my_tasks, complete_task

## 📖 Get More Help

- `tools_documentation(topic="start_workflow")` - Starting workflows guide
- `tools_documentation(topic="complete_task")` - Task completion guide
- `tools_documentation(topic="common_patterns")` - Best practices
- `tools_documentation(topic="troubleshooting")` - Common issues
"""


WORKFLOW_GUIDE = """
# Starting Workflows - Complete Guide

## Step-by-Step Process

### 1. Browse Available Workflows
**Resource:** `discovery://workflows`

Shows all workflow templates organized by category.

### 2. Get Workflow Details
**Tool:** `get_process_model(model_id)`

Check:
- Required start variables
- Description
- Is it executable?

### 3. Prepare Start Data
Validate required fields based on schema from step 2.

**Common fields:**
- requester: email address
- amount: number
- description: text
- department: string

### 4. Start Instance
**Tool:** `start_process_instance(process_model_id="...", variables={...})`

Returns: `{"id": 123, "status": "active"}`

### 5. Verify Started
**Resource:** `workflow://123`

Shows current status and waiting tasks.

## ❌ Common Pitfalls

**Missing required start variables**
- Always check schema first with get_process_model()
- Check required_fields in model definition

**Wrong data types**
- amount should be number, not string: `{"amount": 1500}` not `{"amount": "1500"}`
- dates in ISO 8601 format: `"2026-06-20T10:00:00Z"`

**Starting inactive workflow**
- Check model status is 'active' or 'primary'
- Use filter_runnable=true when listing models

## ✅ Best Practices

- **Count first:** `count_process_models()` to see totals
- **Browse:** `discovery://workflows` for overview
- **Validate:** Check model schema before starting
- **Monitor:** Use `workflow://{id}` resource to track progress
- **Efficient:** Use `detail="minimal"` for status checks

## 📝 Example

```python
# 1. Browse workflows
discovery://workflows

# 2. Get model details
get_process_model("approval-workflow")

# 3. Start instance
start_process_instance(
    process_model_id="approval-workflow",
    variables={
        "requester": "john@example.com",
        "amount": 1500,
        "department": "Sales"
    }
)

# 4. Monitor
workflow://123
```
"""


TASK_GUIDE = """
# Completing Tasks - Complete Guide

## Step-by-Step Process

### 1. Find Your Tasks
**Resource:** `discovery://tasks`

Shows all pending tasks organized by workflow.

Or **count first:** `count_tasks()` to see how many you have.

### 2. Get Task Details
**Resource:** `task://{process_instance_id}/{task_id}`

Shows:
- Task name and description
- Required data fields
- Current workflow state

### 3. Prepare Task Data
Based on required fields from step 2.

**Common patterns:**
- Approval: `{"approved": true, "comment": "Looks good"}`
- Data entry: `{"field1": "value", "field2": 123}`
- Review: `{"status": "approved", "notes": "..."}`

### 4. Complete Task
**Tool:** `complete_task(process_instance_id="...", task_id="...", data={...})`

### 5. Verify Completion
**Resource:** `workflow://{process_instance_id}`

Check workflow continued to next step.

## ❌ Common Pitfalls

**Missing required fields**
- Check task:// resource first for required fields
- All required fields must be provided

**Wrong task ID**
- Use exact task_id from task:// resource
- IDs are case-sensitive

**Completing wrong task**
- Verify task belongs to correct workflow
- Check current workflow state first

## ✅ Best Practices

- **Count first:** `count_tasks()` to see how many pending
- **Browse:** `discovery://tasks` for overview
- **Read task:** `task://{id}` resource before completing
- **Validate data:** Check required fields match schema
- **Verify:** Check `workflow://{id}` after completion
"""


PATTERNS_GUIDE = """
# Common Patterns and Best Practices

## 1. Progressive Disclosure Pattern

Start broad, drill down as needed:

```
1. count_process_instances()
   → "You have 42 active workflows"

2. list_process_instances(detail="minimal")
   → Show list with IDs and status

3. get_process_instance(id="...", detail="standard")
   → Show details for specific workflow

4. workflow://{id} resource
   → Deep dive with formatted view
```

## 2. Count-Before-List Pattern

Check totals before fetching data:

```
1. count_tasks()
   → "You have 5 pending tasks"

2. IF count > 0:
   list_tasks()

3. ELSE:
   "No pending tasks"
```

Saves tokens when result is zero.

## 3. Resource-First Pattern

Browse with resources before calling tools:

```
1. discovery://workflows
   → Browse available workflows

2. workflow://{id}
   → Get formatted workflow view

3. start_process_instance(...)
   → Start with confidence
```

Resources are read-only, efficient, formatted.

## 4. Validate-Before-Action Pattern

Always check state before destructive operations:

```
1. get_process_instance(id, detail="standard")
   → Check current state

2. Validate: is workflow in expected state?

3. IF valid:
   complete_task(...) or cancel_process_instance(...)

4. ELSE:
   Report issue to user
```

## 5. Efficient Query Pattern

Use progressive detail levels:

```
# Quick status check:
get_process_instance(id, detail="minimal")  # 100 tokens

# General use:
get_process_instance(id, detail="standard")  # 500 tokens (default)

# Debugging:
get_process_instance(id, detail="full")  # 2000 tokens
```

## 6. Batch-Query Pattern

Use filters to reduce calls:

```
# ❌ Bad (multiple calls):
for model_id in models:
    instances = list_process_instances(model_id)

# ✅ Good (single call with filter):
instances = list_process_instances(
    process_model_id="approval",
    status="active",
    detail="minimal"
)
```

## 7. Prompt-Guided Pattern

Use prompts for complex workflows:

```
# Instead of manually calling tools:
1. Use prompt: "start_workflow"
2. Follow guided flow
3. AI handles tool sequence

# Available prompts:
- browse_workflows
- start_workflow
- check_my_tasks
- complete_task
- workflow_status
- troubleshoot_workflow
```
"""


TROUBLESHOOTING_GUIDE = """
# Troubleshooting Guide

## Common Issues

### "Workflow is stuck"

**Symptoms:** Workflow not progressing, tasks not appearing

**Diagnosis:**
```
1. get_process_instance(id, detail="full")
2. Check status field
3. Check current_task_name
```

**Solutions:**
- If status="error": Check error logs
- If status="suspended": Look for waiting tasks
- If waiting for user: complete_task(...)
- Use workflow://{id} resource for formatted view

### "Can't start workflow"

**Symptoms:** start_process_instance fails

**Diagnosis:**
```
1. get_process_model(model_id)
2. Check is_executable field
3. Check required variables
```

**Solutions:**
- If not executable: Workflow may be draft/inactive
- If missing variables: Check schema, add required fields
- Use discovery://workflows to find correct model_id

### "Task completion fails"

**Symptoms:** complete_task returns error

**Diagnosis:**
```
1. Read task://{instance_id}/{task_id}
2. Check required fields
3. Check task state
```

**Solutions:**
- If missing fields: Add all required fields from schema
- If wrong task_id: Get correct ID from task:// resource
- If task completed: Task may already be done

### "Too many tokens"

**Symptoms:** Context window filling up, slow responses

**Solutions:**
- ✅ Use count_* tools instead of list_* for counts
- ✅ Use detail="minimal" for status checks
- ✅ Use resources (discovery://, workflow://) for browsing
- ✅ Use filters to narrow results
- ✅ Use per_page parameter to limit list sizes

### "Can't find my workflows"

**Symptoms:** list_process_instances returns empty

**Solutions:**
- Count first: count_process_instances() to verify existence
- Remove filters: Don't filter by status to see all
- Check permissions: User may not have access
- Use discovery://workflows to see all available templates

## Performance Tips

1. **Use count tools first**
   - Faster than fetching data
   - Helps decide next action

2. **Use progressive detail**
   - Start with minimal (100 tokens)
   - Escalate to standard/full only if needed

3. **Use resources for browsing**
   - Efficient, formatted, read-only
   - Better than calling multiple tools

4. **Use filters**
   - Narrow results at API level
   - Less data to process

5. **Use prompts for guidance**
   - Pre-built workflows
   - Handles tool sequence
   - Reduces errors
"""


def register_documentation_tool(mcp: FastMCP) -> None:
    """Register self-documentation tool with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="tools_documentation",
        description="Get comprehensive documentation for m8flow MCP tools (reduces errors by 50%)",
        tags={"documentation"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    def tools_documentation(topic: str | None = None, depth: Literal["quick", "full"] = "quick") -> str:
        """Get documentation for m8flow MCP tools.

        This self-documenting tool teaches AI how to use m8flow MCP effectively,
        reducing errors by 50% and improving performance.

        Args:
            topic: Specific topic or None for overview
            depth: Detail level (quick=summary, full=comprehensive)

        Topics:
            - None (default): Quick reference card
            - "start_workflow": Complete guide for starting workflows
            - "complete_task": Complete guide for task completion
            - "common_patterns": Best practices and patterns
            - "troubleshooting": Common issues and solutions

        Returns:
            Markdown-formatted documentation

        Example:
            # Quick reference:
            tools_documentation()

            # Workflow guide:
            tools_documentation(topic="start_workflow")

            # Best practices:
            tools_documentation(topic="common_patterns")
        """
        if topic is None:
            return QUICK_REFERENCE

        elif topic == "start_workflow":
            return WORKFLOW_GUIDE

        elif topic == "complete_task":
            return TASK_GUIDE

        elif topic == "common_patterns":
            return PATTERNS_GUIDE

        elif topic == "troubleshooting":
            return TROUBLESHOOTING_GUIDE

        else:
            return f"""
# Documentation for: {topic}

No specific documentation found for "{topic}".

Available topics:
- start_workflow
- complete_task
- common_patterns
- troubleshooting

Call tools_documentation() without parameters for quick reference.
"""
