#!/bin/bash

# MxWhisper Deployment Script
# This script builds the Docker image and starts the services

set -e

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

# Show usage information
show_usage() {
    echo "MxWhisper Deployment Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -b, --build      Build the Docker image before starting"
    echo "  -d, --down       Stop and remove containers"
    echo "  -l, --logs       Show logs after starting"
    echo "  -s, --service SERVICE  Show logs for specific service (api|worker)"
    echo ""
    echo "Examples:"
    echo "  $0                # Start services (assumes image exists)"
    echo "  $0 --build        # Build image and start services"
    echo "  $0 --down         # Stop all services"
    echo "  $0 --logs         # Start and show all logs"
    echo "  $0 --logs --service api  # Show only API logs"
}

# Build the Docker image
build_image() {
    log_info "Building Docker image..."
    if ./build-image.sh; then
        log_success "Image built successfully"
    else
        log_error "Failed to build image"
        exit 1
    fi
}

# Start the services
start_services() {
    log_info "Starting MxWhisper services..."
    cd docker
    if docker compose up -d; then
        log_success "Services started successfully"
        log_info "API available at: http://localhost:8000"
        log_info "API docs at: http://localhost:8000/docs"
    else
        log_error "Failed to start services"
        exit 1
    fi
    cd ..
}

# Stop the services
stop_services() {
    log_info "Stopping MxWhisper services..."
    cd docker
    if docker compose down; then
        log_success "Services stopped successfully"
    else
        log_error "Failed to stop services"
        exit 1
    fi
    cd ..
}

# Show logs
show_logs() {
    local service="$1"
    log_info "Showing logs..."
    cd docker
    if [[ -n "$service" ]]; then
        case "$service" in
            api)
                docker compose logs -f mxwhisper
                ;;
            worker)
                docker compose logs -f mxwhisper-worker
                ;;
            *)
                log_error "Unknown service: $service. Use 'api' or 'worker'"
                exit 1
                ;;
        esac
    else
        docker compose logs -f
    fi
    cd ..
}

# Main function
main() {
    local build=false
    local down=false
    local logs=false
    local service=""

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -b|--build)
                build=true
                shift
                ;;
            -d|--down)
                down=true
                shift
                ;;
            -l|--logs)
                logs=true
                shift
                ;;
            -s|--service)
                service="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Handle stop command
    if [[ "$down" == "true" ]]; then
        stop_services
        exit 0
    fi

    # Build if requested
    if [[ "$build" == "true" ]]; then
        build_image
    fi

    # Start services
    start_services

    # Show logs if requested
    if [[ "$logs" == "true" ]]; then
        show_logs "$service"
    fi
}

# Run main function with all arguments
main "$@"