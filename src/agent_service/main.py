"""
FaultMaven Agent Service Microservice

FaultMaven AI Agent Orchestration Microservice
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from agent_service.api.routes import agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Agent Service",
    description="FaultMaven AI Agent Orchestration Microservice - Milestone-based Investigation Engine",
    version="2.0.0"
)

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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Agent Service",
        "version": "0.1.0"
    }


@app.get("/")
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
