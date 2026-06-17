#!/bin/bash
# Deployment script for m8flow-mcp

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default values
ENVIRONMENT="${ENVIRONMENT:-production}"
COMPOSE_FILE="docker-compose.yml"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --env)
      ENVIRONMENT="$2"
      shift 2
      ;;
    --dev)
      ENVIRONMENT="development"
      COMPOSE_FILE="docker-compose.dev.yml"
      shift
      ;;
    --stop)
      ACTION="stop"
      shift
      ;;
    --restart)
      ACTION="restart"
      shift
      ;;
    --logs)
      ACTION="logs"
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --env ENV      Environment (production|development) (default: production)"
      echo "  --dev          Shortcut for development environment"
      echo "  --stop         Stop the services"
      echo "  --restart      Restart the services"
      echo "  --logs         Show logs"
      echo "  --help         Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

echo -e "${GREEN}m8flow-mcp Deployment${NC}"
echo -e "${YELLOW}Environment: ${ENVIRONMENT}${NC}"
echo -e "${YELLOW}Compose file: ${COMPOSE_FILE}${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
  echo -e "${RED}Error: .env file not found${NC}"
  echo -e "${YELLOW}Copy sample.env to .env and configure it first${NC}"
  exit 1
fi

# Execute action
case "${ACTION}" in
  stop)
    echo -e "${GREEN}Stopping services...${NC}"
    docker compose -f "${COMPOSE_FILE}" down
    ;;
  restart)
    echo -e "${GREEN}Restarting services...${NC}"
    docker compose -f "${COMPOSE_FILE}" restart
    ;;
  logs)
    echo -e "${GREEN}Showing logs...${NC}"
    docker compose -f "${COMPOSE_FILE}" logs -f
    ;;
  *)
    echo -e "${GREEN}Starting services...${NC}"
    docker compose -f "${COMPOSE_FILE}" up -d --build

    if [ $? -eq 0 ]; then
      echo ""
      echo -e "${GREEN}✓ Services started successfully${NC}"
      echo ""
      echo -e "${YELLOW}Check status:${NC}"
      docker compose -f "${COMPOSE_FILE}" ps
      echo ""
      echo -e "${YELLOW}View logs:${NC}"
      echo "  docker compose -f ${COMPOSE_FILE} logs -f"
      echo ""
      echo -e "${YELLOW}Health check:${NC}"
      sleep 5
      if curl -f http://localhost:8000/health 2>/dev/null; then
        echo -e "${GREEN}✓ Health check passed${NC}"
      else
        echo -e "${YELLOW}⚠ Health check not available yet (container still starting)${NC}"
      fi
    else
      echo -e "${RED}✗ Failed to start services${NC}"
      exit 1
    fi
    ;;
esac

echo ""
echo -e "${GREEN}Done!${NC}"
