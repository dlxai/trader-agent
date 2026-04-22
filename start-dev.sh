#!/bin/bash

# JMWL Trading Platform - Development Startup Script
# Usage: ./start-dev.sh [backend|frontend|all]

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  JMWL Trading Platform${NC}"
    echo -e "${BLUE}  Development Server${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

start_backend() {
    echo -e "${YELLOW}Starting Backend (Python FastAPI)...${NC}"
    cd packages/backend-py
    mkdir -p logs
    poetry run uvicorn src.main:app --reload --port 3001 > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo -e "${GREEN}✓ Backend started at http://localhost:3001${NC}"
    echo -e "${GREEN}  API Docs: http://localhost:3001/docs${NC}"
    echo -e "${GREEN}  Logs: packages/backend-py/logs/backend.log${NC}"
    cd ../..
}

start_frontend() {
    echo -e "${YELLOW}Starting Frontend (React + Vite)...${NC}"
    cd packages/frontend
    npm run dev &
    FRONTEND_PID=$!
    echo -e "${GREEN}✓ Frontend started at http://localhost:5173${NC}"
    cd ../..
}

print_usage() {
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  ./start-dev.sh backend   - Start backend only"
    echo -e "  ./start-dev.sh frontend  - Start frontend only"
    echo -e "  ./start-dev.sh all       - Start both (default)"
    echo ""
}

# Main
print_header

case "${1:-all}" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    all)
        start_backend
        echo ""
        start_frontend
        ;;
    help|--help|-h)
        print_usage
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        print_usage
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  All services started!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Wait for all background processes
wait
