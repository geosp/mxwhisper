#!/bin/bash

# MxWhisper Docker Image Build Script
# This script builds the Docker image for the MxWhisper application

set -e

# Configuration
IMAGE_NAME="mxwhisper"
DOCKERFILE_PATH="docker/Dockerfile"
BUILD_CONTEXT="."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
}

# Build the Docker image
build_image() {
    log_info "Building Docker image: $IMAGE_NAME"
    log_info "Dockerfile: $DOCKERFILE_PATH"
    log_info "Build context: $BUILD_CONTEXT"

    if docker build -f "$DOCKERFILE_PATH" -t "$IMAGE_NAME" "$BUILD_CONTEXT"; then
        log_success "Docker image '$IMAGE_NAME' built successfully"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
}

# Show usage information
show_usage() {
    echo "MxWhisper Docker Build Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -n, --no-cache Build without using cache"
    echo "  -t, --tag TAG  Tag the image with additional tag"
    echo ""
    echo "Examples:"
    echo "  $0                    # Build with default settings"
    echo "  $0 --no-cache         # Build without cache"
    echo "  $0 --tag v1.0.0       # Build and tag as v1.0.0"
}

# Main function
main() {
    local use_cache=true
    local additional_tag=""

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -n|--no-cache)
                use_cache=false
                shift
                ;;
            -t|--tag)
                additional_tag="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    log_info "Starting MxWhisper Docker image build"

    # Check prerequisites
    check_docker

    # Build the image
    if [[ "$use_cache" == "false" ]]; then
        log_info "Building without cache"
        docker build --no-cache -f "$DOCKERFILE_PATH" -t "$IMAGE_NAME" "$BUILD_CONTEXT"
    else
        build_image
    fi

    # Tag with additional tag if provided
    if [[ -n "$additional_tag" ]]; then
        log_info "Tagging image as: $additional_tag"
        docker tag "$IMAGE_NAME" "$additional_tag"
        log_success "Image tagged as '$additional_tag'"
    fi

    # Show image information
    log_info "Built image details:"
    docker images "$IMAGE_NAME"

    log_success "Build completed successfully!"
}

# Run main function with all arguments
main "$@"