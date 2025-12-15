"""
FaultMaven Agent Service Microservice

FaultMaven AI Agent Orchestration Microservice
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_service.api.routes import agent
from agent_service.infrastructure.logging import LoggingMiddleware, get_logger

# Configure structured logging
logger = get_logger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Agent Service",
    description="FaultMaven AI Agent Orchestration Microservice - Milestone-based Investigation Engine",
    version="2.0.0"
)

# Add logging middleware (must be first to capture all requests)
app.add_middleware(LoggingMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(agent.router)


@app.get(
    "/health",
    summary="Health Check",
    description="""
Returns the health status of the Agent Service.

**Workflow**:
1. Checks service availability
2. Reports service metadata
3. Returns operational status

**Response Example**:
```json
{
  "status": "healthy",
  "service": "Agent Service",
  "version": "2.0.0"
}
```

**Use Cases**:
- Kubernetes liveness/readiness probes
- Load balancer health checks
- Service mesh health monitoring
- Docker Compose healthcheck

**Storage**: No database or external dependencies queried
**Rate Limits**: None
**Authorization**: None required (public endpoint)
    """,
    responses={
        200: {"description": "Service is healthy and operational"},
        500: {"description": "Service is unhealthy or experiencing issues"}
    }
)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Agent Service",
        "version": "0.1.0"
    }


@app.get(
    "/",
    summary="Service Information",
    description="""
Returns service metadata and API information for the Agent Service.

**Workflow**:
1. Client requests service information
2. Service returns metadata including name, version, and description
3. Useful for API discovery and version verification

**Response Example**:
```json
{
  "service": "Agent Service",
  "version": "2.0.0",
  "description": "FaultMaven AI Agent Orchestration Microservice"
}
```

**Use Cases**:
- API discovery and version checking
- Service registry integration
- Client compatibility verification
- Development and debugging

**Storage**: No database access (static metadata)
**Rate Limits**: None
**Authorization**: None required (public endpoint)
    """,
    responses={
        200: {"description": "Service information returned successfully"},
        500: {"description": "Internal server error"}
    }
)
async def root():
    """Root endpoint."""
    return {
        "service": "Agent Service Service",
        "version": "0.1.0",
        "description": "FaultMaven AI Agent Orchestration Microservice"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
