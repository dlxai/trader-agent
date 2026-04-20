# =============================================================================
# WestGardeng AutoTrader Frontend Dockerfile
# Multi-stage build with Nginx for production serving
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base Image
# -----------------------------------------------------------------------------
FROM node:20-alpine AS base

# Install pnpm
RUN npm install -g pnpm@10

# Create app directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Dependencies
# -----------------------------------------------------------------------------
FROM base AS deps

# Copy workspace configuration
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy frontend package.json
COPY packages/frontend/package.json ./packages/frontend/

# Install dependencies
RUN pnpm install --frozen-lockfile

# -----------------------------------------------------------------------------
# Stage 3: Development
# -----------------------------------------------------------------------------
FROM base AS development

WORKDIR /app

# Copy installed dependencies
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/frontend/node_modules ./packages/frontend/node_modules

# Copy source code
COPY packages/frontend ./packages/frontend
COPY pnpm-workspace.yaml package.json ./
COPY tsconfig.base.json ./

# Set environment
ENV NODE_ENV=development
ENV VITE_API_URL=http://localhost:3000

# Expose Vite dev server port
EXPOSE 5173

# Start development server with hot reload
CMD ["pnpm", "--filter", "@jmwl/frontend", "dev", "--", "--host"]

# -----------------------------------------------------------------------------
# Stage 4: Builder (Production Build)
# -----------------------------------------------------------------------------
FROM base AS builder

WORKDIR /app

# Copy installed dependencies
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/packages/frontend/node_modules ./packages/frontend/node_modules

# Copy source code
COPY packages/frontend ./packages/frontend
COPY pnpm-workspace.yaml package.json ./
COPY tsconfig.base.json ./

# Build the application
ENV NODE_ENV=production
RUN pnpm --filter @jmwl/frontend build

# -----------------------------------------------------------------------------
# Stage 5: Production (Nginx)
# -----------------------------------------------------------------------------
FROM nginx:1.25-alpine AS production

# Install required packages for envsubst
RUN apk add --no-cache gettext

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY packages/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built application from builder
COPY --from=builder /app/packages/frontend/dist /usr/share/nginx/html

# Create entrypoint script for environment variable substitution
RUN echo '#!/bin/sh\n\
# Replace environment variables in nginx config\n\
export API_URL=${API_URL:-http://backend:3000}\n\
export WS_URL=${WS_URL:-ws://backend:3000}\n\
envsubst < /etc/nginx/conf.d/default.conf > /etc/nginx/conf.d/default.conf.tmp\n\
mv /etc/nginx/conf.d/default.conf.tmp /etc/nginx/conf.d/default.conf\n\
nginx -g "daemon off;"' > /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh

# Set proper permissions
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

# Start nginx with entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
