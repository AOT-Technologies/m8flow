#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interactive demo of m8flow MCP tools."""

import asyncio
import json
import sys
import os

# Fix Windows console encoding
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.api_client import M8flowAPIClient
from src.config import settings
from src.utils.context import set_auth_token, set_tenant_id


async def demo_tools():
    """Demonstrate m8flow MCP tools functionality."""

    print("=" * 80)
    print("M8FLOW MCP TOOLS - INTERACTIVE DEMO")
    print("=" * 80)
    print()

    # Setup
    token = settings.m8flow_bearer_token
    if not token:
        print("❌ No token configured in .env")
        return

    # Decode token to get tenant ID
    import base64
    parts = token.split('.')
    if len(parts) == 3:
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded)
        tenant_id = claims.get('m8flow_tenant_id')
        username = claims.get('preferred_username')

        print(f"👤 User: {username}")
        print(f"🏢 Tenant: {tenant_id}")
        print(f"🔗 API: {settings.m8flow_api_url}")
        print()

        # Set context (simulating middleware)
        set_auth_token(f"Bearer {token}")
        if tenant_id:
            set_tenant_id(tenant_id)

    client = M8flowAPIClient()

    # Menu
    while True:
        print()
        print("=" * 80)
        print("AVAILABLE OPERATIONS:")
        print("=" * 80)
        print()
        print("Process Models:")
        print("  1. List Process Models")
        print("  2. Get Process Model Details")
        print("  3. Create Process Model")
        print()
        print("Process Instances:")
        print("  4. List Process Instances")
        print("  5. Start Process Instance")
        print("  6. Get Process Instance Details")
        print()
        print("Tasks:")
        print("  7. List Tasks")
        print("  8. Get Task Details")
        print()
        print("Other:")
        print("  0. Exit")
        print()

        try:
            choice = input("Select operation (0-8): ").strip()

            if choice == "0":
                print("\n👋 Goodbye!")
                break

            elif choice == "1":
                # List Process Models
                print("\n📋 Listing Process Models...")
                result = await client.get("/v1.0/process-models", token, params={"page": 1, "per_page": 10})

                if "results" in result:
                    models = result["results"]
                    print(f"\n✅ Found {len(models)} process models:")
                    for i, model in enumerate(models, 1):
                        print(f"\n  {i}. {model.get('display_name', 'N/A')}")
                        print(f"     ID: {model.get('id', 'N/A')}")
                        print(f"     Description: {model.get('description', 'N/A')}")

                    if result.get("pagination"):
                        pag = result["pagination"]
                        print(f"\n  📊 Total: {pag.get('total', 0)} | Page: {pag.get('page', 1)} of {pag.get('pages', 0)}")
                else:
                    print(f"\n❌ Error: {result.get('error', 'Unknown error')}")

            elif choice == "2":
                # Get Process Model Details
                model_id = input("\nEnter process model ID: ").strip()
                if model_id:
                    print(f"\n🔍 Getting details for model '{model_id}'...")
                    result = await client.get(f"/v1.0/process-models/{model_id}", token)

                    if "error" not in result:
                        print("\n✅ Process Model Details:")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"\n❌ Error: {result['error']}")

            elif choice == "3":
                # Create Process Model
                print("\n➕ Create New Process Model")
                identifier = input("Enter identifier (e.g., 'my-workflow'): ").strip()
                display_name = input("Enter display name: ").strip()
                description = input("Enter description (optional): ").strip()

                if identifier and display_name:
                    data = {
                        "id": identifier,
                        "display_name": display_name,
                        "description": description or None,
                    }
                    print(f"\n📤 Creating process model...")
                    result = await client.post("/v1.0/process-models", token, data=data)

                    if "error" not in result:
                        print("\n✅ Process model created successfully!")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"\n❌ Error: {result['error']}")
                else:
                    print("\n❌ Identifier and display name are required")

            elif choice == "4":
                # List Process Instances
                print("\n📋 Listing Process Instances...")
                result = await client.get("/v1.0/process-instances", token, params={"page": 1, "per_page": 10})

                if "results" in result:
                    instances = result["results"]
                    print(f"\n✅ Found {len(instances)} process instances:")
                    for i, inst in enumerate(instances, 1):
                        print(f"\n  {i}. Instance #{inst.get('id', 'N/A')}")
                        print(f"     Model: {inst.get('process_model_identifier', 'N/A')}")
                        print(f"     Status: {inst.get('status', 'N/A')}")

                    if result.get("pagination"):
                        pag = result["pagination"]
                        print(f"\n  📊 Total: {pag.get('total', 0)} | Page: {pag.get('page', 1)} of {pag.get('pages', 0)}")
                else:
                    print(f"\n❌ Error: {result.get('error', 'Unknown error')}")

            elif choice == "5":
                # Start Process Instance
                model_id = input("\nEnter process model ID: ").strip()
                if model_id:
                    variables_str = input("Enter variables (JSON, optional): ").strip()
                    variables = {}
                    if variables_str:
                        try:
                            variables = json.loads(variables_str)
                        except:
                            print("⚠️  Invalid JSON, using empty variables")

                    print(f"\n🚀 Starting process instance for model '{model_id}'...")
                    data = {"variables": variables} if variables else {}
                    result = await client.post(f"/v1.0/process-models/{model_id}/process-instances", token, data=data)

                    if "error" not in result:
                        print("\n✅ Process instance started!")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"\n❌ Error: {result['error']}")

            elif choice == "6":
                # Get Process Instance Details
                instance_id = input("\nEnter process instance ID: ").strip()
                if instance_id:
                    print(f"\n🔍 Getting details for instance '{instance_id}'...")
                    result = await client.get(f"/v1.0/process-instances/{instance_id}", token)

                    if "error" not in result:
                        print("\n✅ Process Instance Details:")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"\n❌ Error: {result['error']}")

            elif choice == "7":
                # List Tasks
                print("\n📋 Listing Tasks...")
                result = await client.get("/v1.0/tasks", token, params={"page": 1, "per_page": 10})

                if "results" in result:
                    tasks = result["results"]
                    print(f"\n✅ Found {len(tasks)} tasks:")
                    for i, task in enumerate(tasks, 1):
                        print(f"\n  {i}. Task '{task.get('name', 'N/A')}'")
                        print(f"     ID: {task.get('id', 'N/A')}")
                        print(f"     Process Instance: {task.get('process_instance_id', 'N/A')}")
                        print(f"     Assignee: {task.get('assignee', 'Unassigned')}")

                    if result.get("pagination"):
                        pag = result["pagination"]
                        print(f"\n  📊 Total: {pag.get('total', 0)} | Page: {pag.get('page', 1)} of {pag.get('pages', 0)}")
                else:
                    print(f"\n❌ Error: {result.get('error', 'Unknown error')}")

            elif choice == "8":
                # Get Task Details
                instance_id = input("\nEnter process instance ID: ").strip()
                task_id = input("Enter task ID: ").strip()
                if instance_id and task_id:
                    print(f"\n🔍 Getting details for task '{task_id}'...")
                    result = await client.get(f"/v1.0/process-instances/{instance_id}/tasks/{task_id}", token)

                    if "error" not in result:
                        print("\n✅ Task Details:")
                        print(json.dumps(result, indent=2))
                    else:
                        print(f"\n❌ Error: {result['error']}")

            else:
                print("\n❌ Invalid choice. Please select 0-8.")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {type(e).__name__}: {e}")

    print()


if __name__ == "__main__":
    print("\n🚀 Starting m8flow MCP Tools Demo...")
    print("   (Press Ctrl+C to exit at any time)\n")
    asyncio.run(demo_tools())
