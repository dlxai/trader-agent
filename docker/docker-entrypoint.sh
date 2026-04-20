#!/bin/sh

# =============================================================================
# WestGardeng AutoTrader Frontend - Docker Entrypoint Script
# =============================================================================
# This script substitutes environment variables in the built JavaScript files
# at container startup, allowing runtime configuration without rebuilding.
# =============================================================================

set -e

echo "Starting WestGardeng AutoTrader Frontend..."

# List of environment variables to substitute
ENV_VARS="VITE_API_URL VITE_WS_URL VITE_APP_NAME VITE_APP_VERSION"

# Function to escape special characters for sed
escape_for_sed() {
    echo "$1" | sed 's/[&/\]/\\&/g'
}

# Substitute environment variables in all JS files
echo "Substituting environment variables..."
for VAR in $ENV_VARS; do
    # Get the value of the environment variable
    VALUE=$(eval echo "\$$VAR")

    if [ -n "$VALUE" ]; then
        echo "  $VAR=$VALUE"

        # Escape the value for sed
        ESCAPED_VALUE=$(escape_for_sed "$VALUE")

        # Find and replace in all JS files
        find /usr/share/nginx/html -type f \( -name "*.js" -o -name "*.html" \) -exec \
            sed -i "s|__${VAR}__|${ESCAPED_VALUE}|g" {} \;
    fi
done

# Also handle runtime config injection via a config.js file
echo "Creating runtime config..."
cat > /usr/share/nginx/html/config.js << EOF
window.__RUNTIME_CONFIG__ = {
  VITE_API_URL: "${VITE_API_URL:-/api}",
  VITE_WS_URL: "${VITE_WS_URL:-/ws}",
  VITE_APP_NAME: "${VITE_APP_NAME:-WestGardeng AutoTrader}",
  VITE_APP_VERSION: "${VITE_APP_VERSION:-0.3.0}"
};
EOF

echo "Environment configuration complete."
echo ""

# Execute the CMD from the Dockerfile
exec "$@"
