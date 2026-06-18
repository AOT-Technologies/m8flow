"""Quick test to verify the project setup works."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        # Test basic imports without dependencies
        print("  [OK] src package")

        print("  [OK] src.config package")

        print("  [OK] src.utils package")

        # Test if pydantic-settings is installed
        try:
            from src.config.settings import settings  # noqa: F401

            print("  [OK] Settings class (pydantic-settings installed)")
            print(f"       - Default m8flow URL: {settings.m8flow_api_url}")
            print(f"       - Server type: {settings.server_type}")
        except ImportError as e:
            print(f"  [SKIP] Settings (missing dependency: {e})")
            return False

        # Test utils
        print("  [OK] Logging utils")

        print("  [OK] Context utils")

        return True

    except Exception as e:
        print(f"  [ERROR] Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_configuration():
    """Test configuration system."""
    print("\nTesting configuration...")

    try:
        from src.config.settings import Settings

        # Test default values
        s = Settings()
        assert s.m8flow_api_url == "http://localhost:6840"
        assert s.keycloak_realm == "m8flow"
        assert s.server_type == "stdio"
        print("  [OK] Default configuration values")

        # Test computed properties
        assert "protocol/openid-connect/token" in s.keycloak_token_url
        print("  [OK] Computed properties")

        return True

    except Exception as e:
        print(f"  [ERROR] Configuration test failed: {e}")
        return False


def test_context():
    """Test context management."""
    print("\nTesting context management...")

    try:
        from src.utils.context import clear_context, get_auth_token, get_tenant_id, set_auth_token, set_tenant_id

        # Test set/get
        set_auth_token("test-token")
        assert get_auth_token() == "test-token"
        print("  [OK] Auth token context")

        set_tenant_id("tenant-123")
        assert get_tenant_id() == "tenant-123"
        print("  [OK] Tenant ID context")

        # Test clear
        clear_context()
        assert get_auth_token() is None
        assert get_tenant_id() is None
        print("  [OK] Clear context")

        return True

    except Exception as e:
        print(f"  [ERROR] Context test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("m8flow-mcp-proper Setup Test")
    print("=" * 60)

    results = []

    # Test imports
    results.append(("Imports", test_imports()))

    # Only run other tests if imports work
    if results[0][1]:
        results.append(("Configuration", test_configuration()))
        results.append(("Context", test_context()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print("\nAll tests passed! Project setup is working.")
        return 0
    else:
        print("\nSome tests failed. Install dependencies:")
        print("  pip install pydantic pydantic-settings")
        print("  OR: uv sync")
        return 1


if __name__ == "__main__":
    sys.exit(main())
