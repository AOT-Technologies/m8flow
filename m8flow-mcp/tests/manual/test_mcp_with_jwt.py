"""
Test MCP server with the new JWT token
"""
import asyncio
import os
from src.api_client import M8flowAPIClient
from src.config import settings

async def test_connection():
    """Test connection to m8flow backend with JWT token"""
    print("=" * 70)
    print("TESTING MCP SERVER WITH NEW JWT TOKEN")
    print("=" * 70)
    print()

    # Get token from environment
    token = os.getenv("M8FLOW_BEARER_TOKEN")
    if not token:
        print("[ERROR] M8FLOW_BEARER_TOKEN not found in environment")
        return

    print(f"[CONFIG]")
    print(f"  API URL: {settings.m8flow_api_url}")
    print(f"  Token: {token[:50]}...{token[-20:]}")
    print()

    # Create API client
    client = M8flowAPIClient()

    # Test 1: List process models
    print("[TEST 1] Listing process models...")
    try:
        result = await client.get("/v1.0/process-models", token, params={"page": 1, "per_page": 5})
        if "results" in result:
            print(f"  [SUCCESS] Found {len(result.get('results', []))} process models")
            for model in result.get('results', [])[:3]:
                print(f"    - {model.get('id', 'N/A')}: {model.get('display_name', 'N/A')}")
        else:
            print(f"  [RESULT] {result}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    print()

    # Test 2: List process instances
    print("[TEST 2] Listing process instances...")
    try:
        result = await client.get("/v1.0/process-instances", token, params={"page": 1, "per_page": 5})
        if "results" in result:
            print(f"  [SUCCESS] Found {len(result.get('results', []))} process instances")
            for instance in result.get('results', [])[:3]:
                print(f"    - Instance {instance.get('id', 'N/A')}: {instance.get('status', 'N/A')}")
        else:
            print(f"  [RESULT] {result}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    print()

    # Test 3: List tasks
    print("[TEST 3] Listing tasks...")
    try:
        result = await client.get("/v1.0/tasks", token, params={"page": 1, "per_page": 5})
        if "results" in result:
            print(f"  [SUCCESS] Found {len(result.get('results', []))} tasks")
            for task in result.get('results', [])[:3]:
                print(f"    - Task {task.get('id', 'N/A')}: {task.get('name', 'N/A')}")
        else:
            print(f"  [RESULT] {result}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    print()

    print("=" * 70)
    print("TESTING COMPLETE")
    print("=" * 70)
    print()
    print("If all tests passed, the MCP server is working correctly!")
    print("You can now use it with Claude Desktop or other MCP clients.")

if __name__ == "__main__":
    asyncio.run(test_connection())
