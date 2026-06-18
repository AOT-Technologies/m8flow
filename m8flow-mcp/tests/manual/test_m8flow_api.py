#!/usr/bin/env python
"""Quick test script to call m8flow API directly."""

import asyncio
import sys

from src.api_client import M8flowAPIClient
from src.auth.token_service import token_service
from src.config import settings


async def test_list_process_models():
    """Test listing process models."""
    print(f"Connecting to m8flow at: {settings.m8flow_api_url}")
    print(f"Keycloak: {settings.keycloak_url}")
    print()

    # Get authentication token
    try:
        print("[AUTH] Getting authentication token...")
        token = await token_service.get_token()
        print(f"[OK] Token acquired (length: {len(token)})")
        print()
    except Exception as e:
        print(f"[ERROR] Failed to get token: {e}")
        return 1

    # Create API client
    client = M8flowAPIClient()

    # Test list process models
    try:
        print("[API] Listing process models...")
        result = await client.get("/v1.0/process-models", token, params={"page": 1, "per_page": 10})

        print("[OK] Success!")
        print()
        print("Response:")
        print(f"  Total: {result.get('pagination', {}).get('total', 0)} process models")
        print(f"  Pages: {result.get('pagination', {}).get('pages', 0)}")

        results = result.get("results", [])
        if results:
            print("\n  Models found:")
            for model in results[:5]:  # Show first 5
                print(f"    - {model.get('id')} ({model.get('display_name')})")
        else:
            print("\n  No process models found (empty system)")

        return 0

    except Exception as e:
        print(f"[ERROR] Failed to list process models: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(test_list_process_models()))
