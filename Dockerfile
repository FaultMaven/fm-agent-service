# FaultMaven Agent Service - PUBLIC Open Source Version
# Apache 2.0 License

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.0

# Copy fm-core-lib first (required dependency)
COPY fm-core-lib/ ./fm-core-lib/

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Export dependencies to requirements.txt (no dev dependencies)
# Fallback to manual list if poetry export fails due to path dependencies
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --without dev || \
    echo "fastapi>=0.104.0\nuvicorn[standard]>=0.24.0\npydantic>=2.4.0\npydantic-settings>=2.0.0\nredis>=5.0.0\nhttpx>=0.28.1\nopentelemetry-api>=1.20.0\nopentelemetry-sdk>=1.20.0\nprometheus-client>=0.18.0\npython-json-logger>=2.0.0\nlanggraph>=0.1.2\nopik>=0.2.1\nstructlog>=23.2.0\ntenacity>=8.3.0" > requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install fm-core-lib FIRST (needed by requirements.txt if poetry export didn't fallback)
COPY --from=builder /app/fm-core-lib/ ./fm-core-lib/
RUN pip install --no-cache-dir ./fm-core-lib

# Copy requirements and install
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=2)"

# Run service
CMD ["uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
