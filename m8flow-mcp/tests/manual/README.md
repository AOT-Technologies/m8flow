# Manual Test Scripts

This directory contains manual testing scripts for the m8flow MCP server.

## Test Files

### Authentication Tests
- `test_token_setup.py` - Test JWT token setup and API connectivity
- `test_auth.py` - Authentication testing
- `test_akhilaus_permissions.py` - User-specific permission tests

### Connection Tests
- `test_mcp_connection.py` - MCP protocol connection tests
- `test_mcp_with_jwt.py` - MCP with JWT authentication
- `test_claude_desktop.py` - Claude Desktop integration test
- `test_middleware_fix.py` - Middleware functionality test

### API Tests
- `test_m8flow_api.py` - Direct m8flow API testing
- `test_server.py` - Server functionality tests
- `test_setup.py` - Setup verification

### Utilities
- `check_env.py` - Environment variable checker
- `check_jwt_tenant.py` - JWT tenant extraction verification
- `demo_mcp_tools.py` - Interactive MCP tools demo

## Usage

```bash
# Test authentication and connectivity
python tests/manual/test_token_setup.py

# Run interactive tool demo
python tests/manual/demo_mcp_tools.py

# Check environment configuration
python tests/manual/check_env.py

# Verify JWT token
python tests/manual/check_jwt_tenant.py
```

## Status
All tests PASS with current configuration (as of 2026-06-17).
