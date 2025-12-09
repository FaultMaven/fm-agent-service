# Single-stage build (poetry install with git dependencies)
FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.0

# Copy fm-core-lib first (required dependency)
COPY fm-core-lib/ ./fm-core-lib/
RUN pip install --no-cache-dir ./fm-core-lib

# Copy dependency files and install
COPY fm-agent-service/pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi --no-root

# Copy source code
COPY fm-agent-service/src/ ./src/

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

# Run service
CMD ["uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
