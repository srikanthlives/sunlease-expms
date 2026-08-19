# Multi-stage build for optimized final image
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./
RUN npm run build

# Python backend image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app ./app

# Copy built frontend dist from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Shared entrypoint (also used for bare-metal dev - see README.md)
COPY startup.sh ./startup.sh
RUN chmod +x ./startup.sh

# Create data directory for uploads/database (kept outside the app code dir
# so it survives image rebuilds when mounted as a volume)
RUN mkdir -p /app/data

# Default DB/upload locations if not overridden by the deployment platform
ENV EXPMS_DATABASE_URL=sqlite:////app/data/expms.db
ENV EXPMS_UPLOAD_DIR=/app/data/uploads

# Tells startup.sh it's running inside this image (deps/frontend already
# built) rather than bare metal - more reliable than checking /.dockerenv,
# which some container platforms (e.g. Railway) don't create.
ENV EXPMS_RUNNING_IN_DOCKER=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application
CMD ["./startup.sh"]
