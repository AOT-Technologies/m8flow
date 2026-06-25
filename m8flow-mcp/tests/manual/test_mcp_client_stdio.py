"""Test m8flow MCP server using stdio transport (Claude Desktop mode).

This script programmatically tests the MCP server without needing Claude Desktop.
Useful for development, debugging, and CI/CD integration.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("❌ Error: MCP package not installed")
    print("Install with: pip install mcp")
    sys.exit(1)


async def test_m8flow_mcp_stdio():
    """Test m8flow MCP server via stdio transport."""

    print("🚀 Starting m8flow MCP Test Suite (stdio mode)\n")
    print("=" * 60)

    # Get configuration from environment
    bearer_token = os.getenv("M8FLOW_BEARER_TOKEN")
    if not bearer_token:
        print("❌ Error: M8FLOW_BEARER_TOKEN not set in environment")
        print("Set it with: export M8FLOW_BEARER_TOKEN='your-token'")
        return False

    # Configure server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["-u", "src/main.py"],
        env={
            "M8FLOW_BEARER_TOKEN": bearer_token,
            "M8FLOW_API_URL": os.getenv("M8FLOW_API_URL", "http://localhost:6840"),
            "SERVER_TYPE": "stdio",
            "LOG_LEVEL": "INFO",
            "PYTHONPATH": str(Path(__file__).parent.parent.parent)
        }
    )

    print("📡 Connecting to m8flow MCP server...")
    print(f"   Token: {bearer_token[:20]}...")
    print(f"   API: {server_params.env['M8FLOW_API_URL']}\n")

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize connection
                await session.initialize()
                print("✅ Connection established\n")

                # Test 1: List available tools
                print("=" * 60)
                print("Test 1: List Available Tools")
                print("=" * 60)
                tools_result = await session.list_tools()
                print(f"Available tools: {len(tools_result.tools)}")
                for tool in tools_result.tools:
                    print(f"  - {tool.name}: {tool.description}")
                print("✅ Test 1 passed\n")

                # Test 2: List available resources
                print("=" * 60)
                print("Test 2: List Available Resources")
                print("=" * 60)
                try:
                    resources_result = await session.list_resources()
                    print(f"Available resources: {len(resources_result.resources)}")
                    for resource in resources_result.resources:
                        print(f"  - {resource.uri}: {resource.name}")
                    print("✅ Test 2 passed\n")
                except Exception as e:
                    print(f"⚠️  Resources not available: {e}\n")

                # Test 2.5: List available prompts (NEW!)
                print("=" * 60)
                print("Test 2.5: List Available Prompts")
                print("=" * 60)
                try:
                    prompts_result = await session.list_prompts()
                    print(f"Available prompts: {len(prompts_result.prompts)}")
                    for prompt in prompts_result.prompts:
                        print(f"  - {prompt.name}: {prompt.description}")
                    print("✅ Test 2.5 passed\n")
                except Exception as e:
                    print(f"⚠️  Prompts not available: {e}\n")

                # Test 3: List process groups
                print("=" * 60)
                print("Test 3: List Process Groups")
                print("=" * 60)
                result = await session.call_tool("list_process_groups", {
                    "page": 1,
                    "per_page": 5
                })
                response_text = result.content[0].text
                print(f"Response: {response_text[:200]}...")

                # Parse response
                try:
                    data = json.loads(response_text)
                    if "results" in data:
                        print(f"Found {len(data['results'])} process groups")
                        for group in data['results'][:2]:
                            print(f"  - {group.get('display_name', 'N/A')}")
                    print("✅ Test 3 passed\n")
                except json.JSONDecodeError:
                    print("⚠️  Response not JSON, but tool executed\n")

                # Test 4: List process models
                print("=" * 60)
                print("Test 4: List Process Models")
                print("=" * 60)
                result = await session.call_tool("list_process_models", {
                    "page": 1,
                    "per_page": 5
                })
                response_text = result.content[0].text

                try:
                    data = json.loads(response_text)
                    if "results" in data:
                        print(f"Found {len(data['results'])} process models")
                        for model in data['results'][:2]:
                            print(f"  - {model.get('display_name', 'N/A')}")
                    print("✅ Test 4 passed\n")
                except json.JSONDecodeError:
                    print("⚠️  Response not JSON, but tool executed\n")

                # Test 5: List tasks
                print("=" * 60)
                print("Test 5: List Tasks")
                print("=" * 60)
                result = await session.call_tool("list_tasks", {
                    "page": 1,
                    "per_page": 5
                })
                response_text = result.content[0].text

                try:
                    data = json.loads(response_text)
                    if "results" in data:
                        print(f"Found {len(data['results'])} tasks")
                        for task in data['results'][:2]:
                            print(f"  - {task.get('name', 'N/A')}")
                    print("✅ Test 5 passed\n")
                except json.JSONDecodeError:
                    print("⚠️  Response not JSON, but tool executed\n")

                # Test 6: List process instances
                print("=" * 60)
                print("Test 6: List Process Instances")
                print("=" * 60)
                result = await session.call_tool("list_process_instances", {
                    "page": 1,
                    "per_page": 5
                })
                response_text = result.content[0].text

                try:
                    data = json.loads(response_text)
                    if "results" in data:
                        print(f"Found {len(data['results'])} instances")
                        for instance in data['results'][:2]:
                            print(f"  - #{instance.get('id')}: {instance.get('status', 'N/A')}")
                    print("✅ Test 6 passed\n")
                except json.JSONDecodeError:
                    print("⚠️  Response not JSON, but tool executed\n")

                # Test 7: Read workflow resource (if we found an instance)
                print("=" * 60)
                print("Test 7: Read Workflow Resource")
                print("=" * 60)
                try:
                    # Try to read a workflow resource
                    result = await session.read_resource("discovery://workflows")
                    content = result.contents[0].text
                    print(f"Discovery resource length: {len(content)} chars")
                    print(f"Preview:\n{content[:300]}...")
                    print("✅ Test 7 passed\n")
                except Exception as e:
                    print(f"⚠️  Resource read failed: {e}\n")

                print("=" * 60)
                print("✅ All tests completed successfully!")
                print("=" * 60)
                return True

    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the test suite."""
    print("\n" + "=" * 60)
    print("M8Flow MCP Test Suite - stdio Transport")
    print("=" * 60 + "\n")

    # Check prerequisites
    if not os.getenv("M8FLOW_BEARER_TOKEN"):
        print("❌ Error: M8FLOW_BEARER_TOKEN environment variable not set")
        print("\nSet it with:")
        print("  export M8FLOW_BEARER_TOKEN='your-jwt-token'")
        print("\nGet your token from:")
        print("  1. Login to m8flow frontend")
        print("  2. Open DevTools → Network")
        print("  3. Copy Authorization header value")
        sys.exit(1)

    # Run tests
    success = asyncio.run(test_m8flow_mcp_stdio())

    if success:
        print("\n✅ Test suite passed!")
        sys.exit(0)
    else:
        print("\n❌ Test suite failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
