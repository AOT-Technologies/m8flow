"""Test m8flow MCP server using SSE transport (remote/HTTP mode).

This script tests the MCP server when running in remote mode (HTTP).
Useful for testing remote deployments, Cursor integration, and HTTP clients.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    print("❌ Error: MCP package not installed")
    print("Install with: pip install mcp")
    sys.exit(1)


async def test_m8flow_mcp_sse():
    """Test m8flow MCP server via SSE (HTTP) transport."""

    print("🚀 Starting m8flow MCP Test Suite (SSE/HTTP mode)\n")
    print("=" * 60)

    # Get configuration
    server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
    bearer_token = os.getenv("M8FLOW_BEARER_TOKEN")

    if not bearer_token:
        print("❌ Error: M8FLOW_BEARER_TOKEN not set in environment")
        print("Set it with: export M8FLOW_BEARER_TOKEN='your-token'")
        return False

    print("📡 Connecting to m8flow MCP server...")
    print(f"   URL: {server_url}")
    print(f"   Token: {bearer_token[:20]}...\n")

    print("⚠️  Make sure the MCP server is running in remote mode:")
    print("   cd m8flow-mcp")
    print("   export SERVER_TYPE=remote")
    print("   python src/main.py\n")

    try:
        async with sse_client(server_url) as (read_stream, write_stream):
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
                for tool in tools_result.tools[:5]:  # Show first 5
                    print(f"  - {tool.name}: {tool.description}")
                if len(tools_result.tools) > 5:
                    print(f"  ... and {len(tools_result.tools) - 5} more tools")
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

                # Test 3: Test a simple tool call
                print("=" * 60)
                print("Test 3: Call list_process_groups Tool")
                print("=" * 60)
                result = await session.call_tool("list_process_groups", {
                    "page": 1,
                    "per_page": 3
                })
                response_text = result.content[0].text
                print(f"Response length: {len(response_text)} chars")

                try:
                    data = json.loads(response_text)
                    if "results" in data:
                        print(f"Found {len(data['results'])} process groups")
                    print("✅ Test 3 passed\n")
                except json.JSONDecodeError:
                    print("⚠️  Response not JSON, but tool executed\n")

                # Test 4: Test resource reading
                print("=" * 60)
                print("Test 4: Read Discovery Resource")
                print("=" * 60)
                try:
                    result = await session.read_resource("discovery://workflows")
                    content = result.contents[0].text
                    print(f"Discovery resource length: {len(content)} chars")
                    print(f"Preview:\n{content[:200]}...")
                    print("✅ Test 4 passed\n")
                except Exception as e:
                    print(f"⚠️  Resource read failed: {e}\n")

                print("=" * 60)
                print("✅ All SSE/HTTP tests completed!")
                print("=" * 60)
                return True

    except ConnectionError as e:
        print(f"\n❌ Connection failed: {e}")
        print("\n💡 Make sure the MCP server is running in remote mode:")
        print("   cd m8flow-mcp")
        print("   export SERVER_TYPE=remote")
        print("   export M8FLOW_BEARER_TOKEN='your-token'")
        print("   python src/main.py")
        return False
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the test suite."""
    print("\n" + "=" * 60)
    print("M8Flow MCP Test Suite - SSE/HTTP Transport")
    print("=" * 60 + "\n")

    # Check prerequisites
    if not os.getenv("M8FLOW_BEARER_TOKEN"):
        print("❌ Error: M8FLOW_BEARER_TOKEN environment variable not set")
        print("\nSet it with:")
        print("  export M8FLOW_BEARER_TOKEN='your-jwt-token'")
        sys.exit(1)

    # Run tests
    success = asyncio.run(test_m8flow_mcp_sse())

    if success:
        print("\n✅ Test suite passed!")
        sys.exit(0)
    else:
        print("\n❌ Test suite failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
