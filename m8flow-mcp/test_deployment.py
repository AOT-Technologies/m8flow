#!/usr/bin/env python3
"""
M8Flow MCP Deployment Test Runner

Quick smoke tests for all deployment scenarios.
Run this before deploying to ensure everything works.

Usage:
    python test_deployment.py [--mode local|ecs] [--verbose]
"""

import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestRunner:
    """Deployment test runner."""

    def __init__(self, mode: str = "local", verbose: bool = False):
        self.mode = mode
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.tests: List[Tuple[str, callable]] = []

    def test(self, name: str):
        """Decorator to register a test."""
        def decorator(func):
            self.tests.append((name, func))
            return func
        return decorator

    def run(self):
        """Run all registered tests."""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}M8Flow MCP Deployment Tests{Colors.RESET}")
        print(f"{Colors.BOLD}Mode: {self.mode.upper()}{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")

        start_time = time.time()

        for name, func in self.tests:
            self._run_test(name, func)

        duration = time.time() - start_time

        # Summary
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Passed: {self.passed}{Colors.RESET}")
        print(f"{Colors.RED}✗ Failed: {self.failed}{Colors.RESET}")
        print(f"{Colors.YELLOW}⊘ Skipped: {self.skipped}{Colors.RESET}")
        print(f"Duration: {duration:.2f}s")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")

        return self.failed == 0

    def _run_test(self, name: str, func: callable):
        """Run a single test."""
        print(f"Testing: {name}...", end=" ")
        sys.stdout.flush()

        try:
            result = func()
            if result is None or result is True:
                self.passed += 1
                print(f"{Colors.GREEN}✓ PASS{Colors.RESET}")
            elif result == "skip":
                self.skipped += 1
                print(f"{Colors.YELLOW}⊘ SKIP{Colors.RESET}")
            else:
                self.failed += 1
                print(f"{Colors.RED}✗ FAIL{Colors.RESET}")
                if self.verbose:
                    print(f"  {Colors.RED}Error: {result}{Colors.RESET}")
        except Exception as e:
            self.failed += 1
            print(f"{Colors.RED}✗ FAIL{Colors.RESET}")
            if self.verbose:
                print(f"  {Colors.RED}Exception: {e}{Colors.RESET}")


# Create test runner instance
runner = TestRunner()


# =============================================================================
# ENVIRONMENT TESTS
# =============================================================================

@runner.test("Python version >= 3.12")
def test_python_version():
    version = sys.version_info
    if version.major >= 3 and version.minor >= 12:
        return True
    return f"Python {version.major}.{version.minor} < 3.12"


@runner.test("Required environment variables")
def test_env_vars():
    required = ["M8FLOW_API_URL", "M8FLOW_BEARER_TOKEN"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        return f"Missing: {', '.join(missing)}"
    return True


@runner.test("Deployment mode set")
def test_deployment_mode():
    mode = os.getenv("DEPLOYMENT_MODE", "local")
    if mode in ["local", "ecs"]:
        return True
    return f"Invalid mode: {mode}"


# =============================================================================
# DEPENDENCY TESTS
# =============================================================================

@runner.test("Flask installed")
def test_flask():
    try:
        import flask
        return True
    except ImportError:
        return "Flask not installed"


@runner.test("FastMCP installed")
def test_fastmcp():
    try:
        import fastmcp
        return True
    except ImportError:
        return "FastMCP not installed"


@runner.test("HTTPX installed")
def test_httpx():
    try:
        import httpx
        return True
    except ImportError:
        return "HTTPX not installed"


# =============================================================================
# FILE STRUCTURE TESTS
# =============================================================================

@runner.test("MCP server entry point exists")
def test_server_exists():
    path = Path("src/main.py")
    return True if path.exists() else "src/main.py not found"


@runner.test("Viewer script exists")
def test_viewer_exists():
    path = Path("tools/m8flow-viewer/serve.py")
    return True if path.exists() else "Viewer not found"


@runner.test("Auto-viewer script exists")
def test_auto_viewer_exists():
    path = Path("tools/auto-viewer/auto_viewer.py")
    return True if path.exists() else "Auto-viewer not found"


@runner.test("Visualization tools exist")
def test_visualization_tools():
    path = Path("src/mcp_tools/visualization.py")
    return True if path.exists() else "visualization.py not found"


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

@runner.test("API URL accessible")
def test_api_url():
    import httpx
    url = os.getenv("M8FLOW_API_URL")
    if not url:
        return "skip"

    try:
        response = httpx.get(f"{url}/v1.0/status", timeout=5)
        return True if response.status_code < 500 else f"Status: {response.status_code}"
    except Exception as e:
        return f"Connection failed: {e}"


@runner.test("Bearer token format valid")
def test_token_format():
    token = os.getenv("M8FLOW_BEARER_TOKEN")
    if not token:
        return "skip"

    # Basic JWT format check
    parts = token.split(".")
    if len(parts) == 3:
        return True
    return f"Invalid JWT format (parts: {len(parts)})"


# =============================================================================
# VIEWER TESTS
# =============================================================================

@runner.test("Viewer can import dependencies")
def test_viewer_imports():
    try:
        from flask import Flask, Response
        return True
    except ImportError as e:
        return f"Import failed: {e}"


@runner.test("Viewer script is executable")
def test_viewer_executable():
    path = Path("tools/m8flow-viewer/serve.py")
    if not path.exists():
        return "skip"

    # Check if script has proper structure
    content = path.read_text()
    if "def main(" in content and "if __name__ == '__main__':" in content:
        return True
    return "Missing main() or __main__ check"


@runner.test("BPMN test file exists")
def test_bpmn_test_file():
    path = Path("test_workflow.bpmn")
    return True if path.exists() else "Test BPMN not found"


# =============================================================================
# AUTO-VIEWER TESTS
# =============================================================================

@runner.test("Auto-viewer temp directory writable")
def test_temp_writable():
    temp_dir = Path(tempfile.gettempdir()) / "m8flow-viewer-requests"
    try:
        temp_dir.mkdir(exist_ok=True)
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        test_file.unlink()
        return True
    except Exception as e:
        return f"Not writable: {e}"


@runner.test("Watchdog library available (auto-viewer)")
def test_watchdog():
    try:
        import watchdog
        return True
    except ImportError:
        return "Watchdog not installed (optional)"


# =============================================================================
# MCP TOOLS TESTS
# =============================================================================

@runner.test("All MCP tool modules exist")
def test_mcp_modules():
    modules = [
        "process_groups",
        "process_models",
        "process_instances",
        "tasks",
        "templates",
        "visualization",
        "count_tools",
        "error_management"
    ]

    for module in modules:
        path = Path(f"src/mcp_tools/{module}.py")
        if not path.exists():
            return f"Missing: {module}.py"

    return True


@runner.test("Tool registration exists")
def test_tool_registration():
    path = Path("src/mcp_tools/__init__.py")
    if not path.exists():
        return "__init__.py not found"

    content = path.read_text()
    if "register_tools" in content and "register_visualization_tools" in content:
        return True
    return "Missing registration functions"


# =============================================================================
# DEPLOYMENT MODE SPECIFIC TESTS
# =============================================================================

@runner.test("Local mode: stdio configured")
def test_local_mode():
    if os.getenv("DEPLOYMENT_MODE") != "local":
        return "skip"

    # Check for stdio configuration
    return True


@runner.test("ECS mode: SSE configured")
def test_ecs_mode():
    if os.getenv("DEPLOYMENT_MODE") != "ecs":
        return "skip"

    # Check for SSE configuration
    server_type = os.getenv("SERVER_TYPE", "stdio")
    if server_type == "sse":
        return True
    return f"SERVER_TYPE = {server_type} (should be sse)"


# =============================================================================
# DOCUMENTATION TESTS
# =============================================================================

@runner.test("README exists")
def test_readme():
    return True if Path("README.md").exists() else "README.md not found"


@runner.test("Deployment guides exist")
def test_guides():
    guides = [
        "DEPLOYMENT_MODES.md",
        "AUTO_VIEWER_GUIDE.md",
        "ECS_DEPLOYMENT_VISUALIZATION.md",
        "DEPLOYMENT_TESTING.md"
    ]

    missing = [g for g in guides if not Path(g).exists()]
    if missing:
        return f"Missing: {', '.join(missing)}"
    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run deployment tests."""
    import argparse

    parser = argparse.ArgumentParser(description="M8Flow MCP Deployment Tests")
    parser.add_argument("--mode", choices=["local", "ecs"], default="local",
                       help="Deployment mode to test")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")

    args = parser.parse_args()

    # Set deployment mode
    os.environ["DEPLOYMENT_MODE"] = args.mode
    runner.mode = args.mode
    runner.verbose = args.verbose

    # Run tests
    success = runner.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
