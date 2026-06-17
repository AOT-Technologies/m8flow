#!/bin/bash
# Build script for m8flow-mcp Docker images

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
IMAGE_NAME="${IMAGE_NAME:-m8flow/m8flow-mcp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DOCKERFILE="${DOCKERFILE:-Dockerfile.production}"
PLATFORM="${PLATFORM:-linux/amd64}"
BUILD_ARGS=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --dev)
      DOCKERFILE="Dockerfile"
      IMAGE_TAG="dev"
      shift
      ;;
    --production)
      DOCKERFILE="Dockerfile.production"
      shift
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --push)
      PUSH_IMAGE="true"
      shift
      ;;
    --no-cache)
      NO_CACHE="--no-cache"
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --tag TAG           Image tag (default: latest)"
      echo "  --dev               Build development image"
      echo "  --production        Build production image (default)"
      echo "  --platform PLATFORM Build platform (default: linux/amd64)"
      echo "  --push              Push image to registry"
      echo "  --no-cache          Build without cache"
      echo "  --help              Show this help message"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${GREEN}Building m8flow-mcp Docker image${NC}"
echo -e "${YELLOW}Image: ${FULL_IMAGE_NAME}${NC}"
echo -e "${YELLOW}Dockerfile: ${DOCKERFILE}${NC}"
echo -e "${YELLOW}Platform: ${PLATFORM}${NC}"
echo ""

# Build the image
echo -e "${GREEN}Building image...${NC}"
docker buildx build \
  --file "${DOCKERFILE}" \
  --tag "${FULL_IMAGE_NAME}" \
  --platform "${PLATFORM}" \
  ${NO_CACHE} \
  --load \
  .

if [ $? -eq 0 ]; then
  echo -e "${GREEN}✓ Image built successfully: ${FULL_IMAGE_NAME}${NC}"
else
  echo -e "${RED}✗ Build failed${NC}"
  exit 1
fi

# Push if requested
if [ "${PUSH_IMAGE}" = "true" ]; then
  echo -e "${GREEN}Pushing image to registry...${NC}"
  docker push "${FULL_IMAGE_NAME}"

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image pushed successfully${NC}"
  else
    echo -e "${RED}✗ Push failed${NC}"
    exit 1
  fi
fi

# Show image info
echo ""
echo -e "${GREEN}Image details:${NC}"
docker images | grep "${IMAGE_NAME}" | grep "${IMAGE_TAG}"

echo ""
echo -e "${GREEN}Done!${NC}"
