# Multi-stage build for optimized frontend

# Stage 1: Install dependencies only (for better caching)
FROM node:20-alpine as dependencies

WORKDIR /app

# Copy package files
COPY package.json npm-shrinkwrap.json ./

# Install dependencies
RUN npm ci --only=production=false

# Stage 2: Build application
FROM node:20-alpine as builder

WORKDIR /app

# Copy dependencies from previous stage
COPY --from=dependencies /app/node_modules ./node_modules

# Copy source code
COPY . .

# Build argument for API URL (can be overridden in docker-compose)
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Build argument for Clerk Publishable Key
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY

# Build production bundle
RUN npm run build

# Stage 3: Serve with nginx
FROM nginx:alpine

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1

# nginx runs as non-root by default in the alpine image
# Start nginx
CMD ["nginx", "-g", "daemon off;"]
