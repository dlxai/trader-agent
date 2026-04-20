#!/bin/bash

# =============================================================================
# WestGardeng AutoTrader - Database Migration Script
# =============================================================================
# This script handles database migrations, seeds, and other database
# operations for the WestGardeng AutoTrader backend.
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="packages/backend"
DATABASE_PATH="${BACKEND_DIR}/data/autotrader.db"
MIGRATIONS_DIR="${BACKEND_DIR}/src/db/migrations"
SEEDS_DIR="${BACKEND_DIR}/src/db/seeds"

# Helper functions
print_header() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         WestGardeng AutoTrader - Database Manager                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if running in correct directory
check_directory() {
    if [ ! -d "$BACKEND_DIR" ]; then
        print_error "Backend directory not found. Are you in the project root?"
        exit 1
    fi
}

# Create necessary directories
create_directories() {
    mkdir -p "$(dirname "$DATABASE_PATH")"
    mkdir -p "$MIGRATIONS_DIR"
    mkdir -p "$SEEDS_DIR"
}

# Show database status
show_status() {
    print_info "Checking database status..."

    if [ ! -f "$DATABASE_PATH" ]; then
        print_warning "Database does not exist yet"
        return
    fi

    local size=$(du -h "$DATABASE_PATH" | cut -f1)
    print_success "Database exists at: $DATABASE_PATH"
    print_info "Size: $size"

    # Try to get migration status using Node.js
    if command -v node &> /dev/null; then
        node -e "
            try {
                const fs = require('fs');
                const path = require('path');
                const dbPath = '$DATABASE_PATH';

                if (fs.existsSync(dbPath)) {
                    const stats = fs.statSync(dbPath);
                    console.log('Last modified:', stats.mtime.toISOString());
                }
            } catch (e) {
                // Ignore errors
            }
        " 2>/dev/null || true
    fi
}

# Run migrations
run_migrations() {
    print_info "Running database migrations..."

    if [ ! -d "$MIGRATIONS_DIR" ]; then
        print_warning "Migrations directory does not exist"
        return
    fi

    # Count migration files
    local migration_count=$(find "$MIGRATIONS_DIR" -name "*.sql" -o -name "*.ts" -o -name "*.js" 2>/dev/null | wc -l)

    if [ "$migration_count" -eq 0 ]; then
        print_warning "No migration files found"
        return
    fi

    print_info "Found $migration_count migration files"

    # Try to run migrations using the backend's migration system
    if pnpm --filter @jmwl/backend exec tsx scripts/migrate.ts 2>/dev/null; then
        print_success "Migrations completed successfully"
    else
        print_warning "Migration command failed or not available"
        print_info "You may need to run migrations manually"
    fi
}

# Run seeds
run_seeds() {
    print_info "Running database seeds..."

    if [ ! -d "$SEEDS_DIR" ]; then
        print_warning "Seeds directory does not exist"
        return
    fi

    local seed_count=$(find "$SEEDS_DIR" -name "*.ts" -o -name "*.js" 2>/dev/null | wc -l)

    if [ "$seed_count" -eq 0 ]; then
        print_warning "No seed files found"
        return
    fi

    print_info "Found $seed_count seed files"

    if pnpm --filter @jmwl/backend exec tsx scripts/seed.ts 2>/dev/null; then
        print_success "Seeds completed successfully"
    else
        print_warning "Seed command failed or not available"
    fi
}

# Reset database
reset_database() {
    print_warning "This will DELETE all data in the database!"
    read -p "Are you sure you want to continue? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Database reset cancelled"
        return
    fi

    print_info "Resetting database..."

    if [ -f "$DATABASE_PATH" ]; then
        rm "$DATABASE_PATH"
        print_success "Database file removed"
    fi

    # Also remove WAL files
    if [ -f "$DATABASE_PATH-wal" ]; then
        rm "$DATABASE_PATH-wal"
    fi

    if [ -f "$DATABASE_PATH-shm" ]; then
        rm "$DATABASE_PATH-shm"
    fi

    print_success "Database reset complete"

    # Run migrations and seeds on fresh database
    run_migrations
    run_seeds
}

# Show help
show_help() {
    cat << EOF
WestGardeng AutoTrader - Database Management Script

Usage: $0 [command]

Commands:
    status      Show database status and information
    migrate     Run database migrations
    seed        Run database seeds
    reset       Reset the database (DANGER: Deletes all data!)
    setup       Full setup (migrations + seeds)
    help        Show this help message

If no command is provided, the script will show status by default.

Examples:
    $0 status           # Check database status
    $0 migrate          # Run migrations
    $0 setup            # Full database setup

EOF
}

# Main execution
main() {
    local command="${1:-status}"

    print_header

    # Check if running in correct directory
    check_directory

    # Create necessary directories
    create_directories

    case "$command" in
        status)
            show_status
            ;;
        migrate|migrations)
            run_migrations
            ;;
        seed|seeds)
            run_seeds
            ;;
        reset)
            reset_database
            ;;
        setup)
            show_status
            echo ""
            run_migrations
            echo ""
            run_seeds
            echo ""
            print_success "Database setup complete!"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Run main
main "$@"
