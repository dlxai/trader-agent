#!/bin/bash

# =============================================================================
# WestGardeng AutoTrader - Development Start Script
# =============================================================================
# This script starts all development services in parallel with proper
# log formatting and process management.
# =============================================================================

set -m

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=${BACKEND_PORT:-3001}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
BACKEND_DIR="packages/backend"
FRONTEND_DIR="packages/frontend"

# Process IDs
BACKEND_PID=""
FRONTEND_PID=""

# Helper functions
log_backend() {
    echo -e "${BLUE}[BACKEND]${NC} $1"
}

log_frontend() {
    echo -e "${MAGENTA}[FRONTEND]${NC} $1"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         WestGardeng AutoTrader - Development Server                   ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Kill process on a specific port
kill_port() {
    local port=$1
    local pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$pid" ]; then
        log_warn "Killing process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null || true
    fi
}

# Cleanup function
cleanup() {
    echo ""
    log_info "Shutting down services..."

    if [ -n "$FRONTEND_PID" ]; then
        log_frontend "Stopping (PID: $FRONTEND_PID)"
        kill -TERM $FRONTEND_PID 2>/dev/null || true
        wait $FRONTEND_PID 2>/dev/null || true
    fi

    if [ -n "$BACKEND_PID" ]; then
        log_backend "Stopping (PID: $BACKEND_PID)"
        kill -TERM $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi

    log_info "All services stopped"
    exit 0
}

# Setup trap for cleanup
trap cleanup SIGINT SIGTERM EXIT

# Wait for service to be ready
wait_for_service() {
    local name=$1
    local port=$2
    local max_attempts=${3:-30}
    local attempt=0

    echo -n "Waiting for $name on port $port..."

    while [ $attempt -lt $max_attempts ]; do
        if check_port $port; then
            echo -e " ${GREEN}ready${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
        echo -n "."
    done

    echo -e " ${RED}timeout${NC}"
    return 1
}

# Main execution
main() {
    print_header

    # Check if .env exists
    if [ ! -f ".env" ]; then
        log_warn ".env file not found, copying from .env.example"
        cp .env.example .env
        log_info "Created .env file. Please review and update the configuration."
    fi

    # Check for free ports
    if check_port $BACKEND_PORT; then
        log_warn "Port $BACKEND_PORT is already in use"
        kill_port $BACKEND_PORT
    fi

    if check_port $FRONTEND_PORT; then
        log_warn "Port $FRONTEND_PORT is already in use"
        kill_port $FRONTEND_PORT
    fi

    # Start backend
    log_backend "Starting on port $BACKEND_PORT"
    cd $BACKEND_DIR
    pnpm dev &
    BACKEND_PID=$!
    cd - > /dev/null
    log_backend "Started with PID: $BACKEND_PID"

    # Wait for backend to be ready
    if ! wait_for_service "backend" $BACKEND_PORT; then
        log_error "Backend failed to start"
        exit 1
    fi

    # Start frontend
    log_frontend "Starting on port $FRONTEND_PORT"
    cd $FRONTEND_DIR
    pnpm dev &
    FRONTEND_PID=$!
    cd - > /dev/null
    log_frontend "Started with PID: $FRONTEND_PID"

    # Wait for frontend to be ready
    if ! wait_for_service "frontend" $FRONTEND_PORT; then
        log_error "Frontend failed to start"
        exit 1
    fi

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║         All services are running!                              ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  Frontend: http://localhost:$FRONTEND_PORT                              ║${NC}"
    echo -e "${GREEN}║  Backend:  http://localhost:$BACKEND_PORT/api                          ║${NC}"
    echo -e "${GREEN}║  Health:   http://localhost:$BACKEND_PORT/api/health                     ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    echo ""

    # Wait for processes
    wait
}

# Run main
main "$@"
