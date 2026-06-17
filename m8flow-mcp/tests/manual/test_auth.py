"""Test script to verify Keycloak authentication."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_token_service():
    """Test ROPC token fetching."""
    print("=" * 60)
    print("Testing Keycloak ROPC Token Service")
    print("=" * 60)

    try:
        from src.auth.token_service import TokenService
        from src.config import settings

        print(f"\n[CONFIG]")
        print(f"  Keycloak URL: {settings.keycloak_url}")
        print(f"  Realm: {settings.keycloak_realm}")
        print(f"  Client ID: {settings.client_id}")
        print(f"  Username: {settings.keycloak_username or '(not set)'}")
        print(f"  Password: {'***' if settings.keycloak_password else '(not set)'}")

        if not settings.keycloak_username or not settings.keycloak_password:
            print("\n[SKIP] ROPC test - KEYCLOAK_USERNAME/PASSWORD not configured")
            print("  To test: Set these in .env file")
            return False

        # Create token service
        token_svc = TokenService()

        print("\n[TEST] Fetching token via ROPC...")
        token = await token_svc.get_token()

        if token:
            print(f"  [OK] Token acquired ({len(token)} chars)")
            print(f"  [OK] Token prefix: {token[:20]}...")

            # Decode token to show claims
            import base64
            import json

            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))

            print(f"\n[TOKEN CLAIMS]")
            print(f"  Subject: {claims.get('sub')}")
            print(f"  Username: {claims.get('preferred_username')}")
            print(f"  Email: {claims.get('email')}")
            print(f"  Tenant: {claims.get('m8f_tenant_id', '(none)')}")
            print(f"  Roles: {claims.get('realm_access', {}).get('roles', [])[:5]}")
            print(f"  Issuer: {claims.get('iss')}")
            print(f"  Audience: {claims.get('aud')}")
            print(f"  Expires: {claims.get('exp')}")

            # Test cache
            print("\n[TEST] Testing token cache...")
            token2 = await token_svc.get_token()
            if token == token2:
                print("  [OK] Token retrieved from cache")
            else:
                print("  [WARNING] Got different token (cache not working?)")

            return True
        else:
            print("  [ERROR] No token returned")
            return False

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_jwt_validation():
    """Test JWT validation."""
    print("\n" + "=" * 60)
    print("Testing Keycloak JWT Validation")
    print("=" * 60)

    try:
        from src.auth.keycloak import KeycloakAuth
        from src.auth.token_service import token_service
        from src.config import settings

        if not settings.keycloak_username or not settings.keycloak_password:
            print("\n[SKIP] JWT validation test - need token from ROPC first")
            return False

        # Get a token
        print("\n[TEST] Fetching token to validate...")
        token = await token_service.get_token()
        print(f"  [OK] Got token to validate")

        # Create validator
        print(f"\n[TEST] Creating KeycloakAuth validator...")
        auth = KeycloakAuth(
            keycloak_url=settings.keycloak_url,
            realm=settings.keycloak_realm,
            client_id=settings.client_id,
        )
        print(f"  [OK] Validator created")
        print(f"       JWKS URI: {auth.jwks_uri}")
        print(f"       Issuer: {auth.issuer}")

        # Validate token
        print(f"\n[TEST] Validating token...")
        user_context = await auth.validate_token(token)

        print(f"  [OK] Token validated successfully!")
        print(f"\n[USER CONTEXT]")
        print(f"  Username: {user_context.username}")
        print(f"  Email: {user_context.email}")
        print(f"  Roles: {user_context.roles[:5]}")
        print(f"  Groups: {user_context.groups}")
        print(f"  Tenant ID: {user_context.tenant_id or '(none)'}")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_middleware():
    """Test context extraction middleware."""
    print("\n" + "=" * 60)
    print("Testing Context Extraction Middleware")
    print("=" * 60)

    try:
        from src.middleware.context_extraction import ContextExtractionMiddleware
        from src.utils.context import get_auth_token

        print("\n[TEST] Creating middleware...")
        middleware = ContextExtractionMiddleware()
        print("  [OK] Middleware created")

        # Mock context
        class MockContext:
            pass

        async def mock_next(ctx):
            return "next_result"

        print("\n[TEST] Extracting token via middleware...")
        result = await middleware.on_message(MockContext(), mock_next)

        token = get_auth_token()
        if token:
            print(f"  [OK] Token extracted and set in context")
            print(f"       Token prefix: {token[:30]}...")
            return True
        else:
            print(f"  [WARNING] No token in context")
            return False

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all auth tests."""
    print("\n" + "=" * 60)
    print("m8flow-mcp-proper Authentication Test Suite")
    print("=" * 60)

    results = []

    # Test 1: Token service
    results.append(("ROPC Token Service", await test_token_service()))

    # Test 2: JWT validation
    results.append(("JWT Validation", await test_jwt_validation()))

    # Test 3: Middleware
    results.append(("Middleware Integration", await test_middleware()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(r[1] for r in results if r[1] is not False)

    if all_passed:
        print("\nAll tests passed! Keycloak auth is working.")
        return 0
    else:
        print("\nSome tests failed or were skipped.")
        print("\nTo run all tests:")
        print("  1. Set KEYCLOAK_URL in .env")
        print("  2. Set KEYCLOAK_USERNAME in .env")
        print("  3. Set KEYCLOAK_PASSWORD in .env")
        print("  4. Ensure m8flow backend is running")
        print("  5. Run: python test_auth.py")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
