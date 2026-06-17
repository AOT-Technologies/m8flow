#!/usr/bin/env python
"""Test if JWT contains tenant ID."""

import asyncio
import sys
from src.auth.token_service import token_service
from src.auth.rbac import decode_jwt_payload

async def check_jwt_tenant():
    """Check if JWT token contains tenant ID."""
    print("="*60)
    print("JWT Tenant ID Check")
    print("="*60)
    print()

    # Get token
    try:
        print("[1/2] Getting JWT token from Keycloak...")
        token = await token_service.get_token()
        print(f"[OK] Token acquired (length: {len(token)})")
        print()
    except Exception as e:
        print(f"[ERROR] Failed to get token: {e}")
        return 1

    # Decode JWT
    try:
        print("[2/2] Checking for tenant ID in JWT...")
        claims = decode_jwt_payload(token)

        print("\n" + "="*60)
        print("JWT Claims Found:")
        print("="*60)

        # Key claims
        important_claims = [
            'sub', 'preferred_username', 'email', 'name',
            'm8f_tenant_id', 'tenantId', 'tenant_id', 'tenant',
            'realm_access', 'resource_access'
        ]

        for key in important_claims:
            if key in claims:
                value = claims[key]
                if isinstance(value, dict):
                    print(f"  {key}: {list(value.keys())}")
                else:
                    print(f"  {key}: {value}")

        print("="*60)
        print()

        # Check for tenant
        tenant_fields = ['m8f_tenant_id', 'tenantId', 'tenant_id', 'tenant', 'organization_id']
        tenant_id = None
        found_field = None

        for field in tenant_fields:
            if field in claims:
                tenant_id = claims[field]
                found_field = field
                break

        if tenant_id:
            print(f"[OK] TENANT ID FOUND: {found_field} = '{tenant_id}'")
            print()
            print("="*60)
            print("Result: JWT is configured correctly for multi-tenancy!")
            print("="*60)
            print()
            print("Your m8flow-mcp-proper will:")
            print(f"  - Extract tenant: '{tenant_id}'")
            print(f"  - Add header: x-m8flow-tenant-id: {tenant_id}")
            print("  - Isolate data by tenant automatically")
            print()
            return 0
        else:
            print("[WARNING] NO TENANT ID FOUND IN JWT!")
            print()
            print("="*60)
            print("Result: JWT does NOT contain tenant information")
            print("="*60)
            print()
            print("Multi-tenancy will NOT work until you configure Keycloak:")
            print()
            print("Steps:")
            print("  1. Go to Keycloak Admin Console")
            print("     http://localhost:6842/admin")
            print()
            print("  2. Select realm: m8flow")
            print()
            print("  3. Add user attribute:")
            print("     Users -> akhilaus -> Attributes tab")
            print("     Key: m8f_tenant_id")
            print("     Value: your-tenant-name (e.g., 'acme-corp')")
            print()
            print("  4. Create protocol mapper:")
            print("     Clients -> m8flow-mcp -> Client scopes -> Mappers")
            print("     Add mapper -> User Attribute")
            print("     - Name: Tenant ID Mapper")
            print("     - User Attribute: m8f_tenant_id")
            print("     - Token Claim Name: m8f_tenant_id")
            print("     - Add to ID token: ON")
            print("     - Add to access token: ON")
            print()
            print("  5. Re-run this script to verify")
            print()
            print("OR use fallback:")
            print("  Add to .env: DEFAULT_TENANT_ID=default-tenant")
            print()
            print("See: JWT_TENANT_VERIFICATION.md for detailed instructions")
            print()
            return 1

    except Exception as e:
        print(f"[ERROR] Failed to decode JWT: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(check_jwt_tenant()))
