#!/bin/bash

# =============================================================================
# WestGardeng AutoTrader - Setup Script
# =============================================================================
# This script sets up the development environment for the WestGardeng AutoTrader
# monorepo. Run this after cloning the repository.
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         WestGardeng AutoTrader - Development Setup                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${YELLOW}➤${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Node.js version
check_node_version() {
    print_step "Checking Node.js version..."

    if ! command_exists node; then
        print_error "Node.js is not installed. Please install Node.js >= 20.0.0"
        exit 1
    fi

    NODE_VERSION=$(node --version | cut -d 'v' -f 2)
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d '.' -f 1)

    if [ "$NODE_MAJOR" -lt 20 ]; then
        print_error "Node.js version $NODE_VERSION is too old. Please upgrade to >= 20.0.0"
        exit 1
    fi

    print_success "Node.js $NODE_VERSION detected"
}

# Check pnpm version
check_pnpm_version() {
    print_step "Checking pnpm version..."

    if ! command_exists pnpm; then
        print_error "pnpm is not installed. Please install pnpm >= 9.0.0"
        echo "   Run: npm install -g pnpm"
        exit 1
    fi

    PNPM_VERSION=$(pnpm --version)
    PNPM_MAJOR=$(echo "$PNPM_VERSION" | cut -d '.' -f 1)

    if [ "$PNPM_MAJOR" -lt 9 ]; then
        print_warning "pnpm version $PNPM_VERSION is older than recommended. Consider upgrading to >= 9.0.0"
    fi

    print_success "pnpm $PNPM_VERSION detected"
}

# Install dependencies
install_dependencies() {
    print_step "Installing dependencies..."

    if ! pnpm install --frozen-lockfile; then
        print_warning "Frozen lockfile failed, trying without..."
        pnpm install
    fi

    print_success "Dependencies installed"
}

# Setup environment files
setup_environment() {
    print_step "Setting up environment files..."

    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_success "Created .env from .env.example"
            print_warning "Please update .env with your actual configuration values"
        else
            print_warning "No .env.example found. Please create .env manually"
        fi
    else
        print_success ".env already exists"
    fi
}

# Setup database
setup_database() {
    print_step "Setting up database..."

    # Create data directory if it doesn't exist
    mkdir -p packages/backend/data

    # Run migrations
    if pnpm --filter @jmwl/backend exec tsx scripts/migrate.ts 2>/dev/null; then
        print_success "Database migrations completed"
    else
        print_warning "Database migrations skipped or failed"
    fi

    # Run seeds
    if pnpm --filter @jmwl/backend exec tsx scripts/seed.ts 2>/dev/null; then
        print_success "Database seeded"
    else
        print_warning "Database seeding skipped or failed"
    fi
}

# Setup Git hooks
setup_git_hooks() {
    print_step "Setting up Git hooks..."

    if [ -d ".git" ]; then
        # Setup husky if it's in dependencies
        if pnpm exec husky install 2>/dev/null; then
            print_success "Git hooks configured"
        else
            print_warning "Husky not configured (optional)"
        fi
    else
        print_warning "Not a Git repository"
    fi
}

# Verify installation
verify_installation() {
    print_step "Verifying installation..."

    local has_errors=0

    # Check TypeScript compilation
    if ! pnpm typecheck >/dev/null 2>&1; then
        print_warning "TypeScript type checking has issues"
        has_errors=1
    fi

    # Check if we can build
    if ! pnpm build:backend >/dev/null 2>&1; then
        print_warning "Backend build has issues"
        has_errors=1
    fi

    if [ "$has_errors" -eq 0 ]; then
        print_success "Installation verified successfully"
    else
        print_warning "Installation completed with warnings"
    fi
}

# Print final instructions
print_final_instructions() {
    echo ""
    print_header
    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo -e "  1. ${YELLOW}Update your .env file${NC} with your actual configuration"
    echo -e "  2. ${YELLOW}Start development:${NC}"
    echo ""
    echo -e "     ${BLUE}pnpm dev${NC}           # Start both frontend and backend"
    echo -e "     ${BLUE}pnpm dev:backend${NC}   # Start backend only"
    echo -e "     ${BLUE}pnpm dev:frontend${NC}  # Start frontend only"
    echo ""
    echo -e "  3. ${YELLOW}Open${NC} http://localhost:5173 for the frontend"
    echo -e "  4. ${YELLOW}API${NC} is available at http://localhost:3001"
    echo ""
    echo -e "${BLUE}Documentation:${NC}"
    echo -e "  - Architecture: ${BLUE}ARCHITECTURE_ANALYSIS.md${NC}"
    echo -e "  - API Docs: http://localhost:3001/api/docs (when running)"
    echo ""
    echo -e "${YELLOW}Need help?${NC} Open an issue on GitHub."
    echo ""
}

# Main execution
main() {
    print_header

    # Check prerequisites
    check_node_version
    check_pnpm_version

    # Install and setup
    install_dependencies
    setup_environment
    setup_database
    setup_git_hooks

    # Verify
    verify_installation

    # Print final instructions
    print_final_instructions
}

# Run main function
main "$@"
