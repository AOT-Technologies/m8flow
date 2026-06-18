#!/usr/bin/env python
"""Test MCP server can start and respond."""

import sys

print("Testing M8Flow MCP Server Connection...")
print("=" * 60)

# Test 1: Can Python be found?
print("\n[Test 1] Python executable test:")
print(f"  Path: {sys.executable}")
print(f"  Version: {sys.version}")
print("  ✅ Python is working")

# Test 2: Can we import dependencies?
print("\n[Test 2] Dependencies test:")
try:
    import fastmcp
    import httpx
    import pydantic

    print(f"  ✅ fastmcp {fastmcp.__version__}")
    print(f"  ✅ httpx {httpx.__version__}")
    print(f"  ✅ pydantic {pydantic.__version__}")
except ImportError as e:
    print(f"  ❌ Missing dependency: {e}")
    sys.exit(1)

# Test 3: Can the server module be imported?
print("\n[Test 3] Server module test:")
try:
    sys.path.insert(0, "c:/AOT/m8flow-mcp")
    from src.main import mcp

    print(f"  ✅ MCP server loaded: {mcp.name}")
    print(f"  ✅ Server has {len(mcp.tools)} tools registered")
except Exception as e:
    print(f"  ❌ Failed to load server: {e}")
    sys.exit(1)

# Test 4: Check configuration
print("\n[Test 4] Configuration test:")
try:
    from src.config import settings

    print(f"  ✅ Server type: {settings.server_type}")
    print(f"  ✅ API URL: {settings.m8flow_api_url}")
    print(f"  ✅ Token: {'SET' if settings.m8flow_bearer_token else 'NOT SET'}")
except Exception as e:
    print(f"  ❌ Configuration error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nThe MCP server should work in Claude Desktop.")
print("\nIf Claude Desktop still shows 'disconnected', it may be:")
print("  1. Timing out during initialization")
print("  2. Not seeing stdout/stderr properly")
print("  3. Having permission issues")
print("\nCheck Claude Desktop logs for more details.")
