#!/bin/bash
# Test script for m8flow-mcp

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default values
TEST_PATH="${TEST_PATH:-tests/}"
COVERAGE="${COVERAGE:-true}"
VERBOSE="${VERBOSE:-false}"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --path)
      TEST_PATH="$2"
      shift 2
      ;;
    --no-coverage)
      COVERAGE="false"
      shift
      ;;
    --verbose)
      VERBOSE="true"
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --path PATH       Path to tests (default: tests/)"
      echo "  --no-coverage     Disable coverage report"
      echo "  --verbose         Verbose output"
      echo "  --help            Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

echo -e "${GREEN}Running m8flow-mcp tests${NC}"
echo -e "${YELLOW}Test path: ${TEST_PATH}${NC}"
echo -e "${YELLOW}Coverage: ${COVERAGE}${NC}"
echo ""

# Build pytest command
PYTEST_CMD="pytest ${TEST_PATH}"

if [ "${VERBOSE}" = "true" ]; then
  PYTEST_CMD="${PYTEST_CMD} -v"
fi

if [ "${COVERAGE}" = "true" ]; then
  PYTEST_CMD="${PYTEST_CMD} --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml"
fi

# Run tests
echo -e "${GREEN}Running tests...${NC}"
eval "${PYTEST_CMD}"

if [ $? -eq 0 ]; then
  echo ""
  echo -e "${GREEN}✓ All tests passed${NC}"

  if [ "${COVERAGE}" = "true" ]; then
    echo ""
    echo -e "${YELLOW}Coverage report generated:${NC}"
    echo "  - HTML: htmlcov/index.html"
    echo "  - XML: coverage.xml"
  fi
else
  echo -e "${RED}✗ Tests failed${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}Done!${NC}"
