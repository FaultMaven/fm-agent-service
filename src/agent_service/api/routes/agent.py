"""Agent API Routes

Provides chat endpoint for AI troubleshooting agent.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field

from fm_core_lib.models import Case
from fm_core_lib.clients import CaseServiceClient
from agent_service.core.investigation.milestone_engine import MilestoneEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatAttachment(BaseModel):
    """File attachment for chat message."""
    file_id: str
    filename: str
    mime_type: str
    size_bytes: int


class AgentChatRequest(BaseModel):
    """Request body for agent chat endpoint."""
    message: str = Field(..., min_length=1, max_length=10000)
    attachments: Optional[List[ChatAttachment]] = None


class AgentChatResponse(BaseModel):
    """Response from agent chat endpoint."""
    agent_response: str
    case_id: str
    turn_number: int
    milestones_completed: List[str] = []
    progress_made: bool
    status_transitioned: bool
    current_status: str
    timestamp: str


# ============================================================================
# Dependencies
# ============================================================================

async def get_case_service_client() -> CaseServiceClient:
    """Get CaseServiceClient instance."""
    # TODO: Get base_url from environment variable
    return CaseServiceClient(base_url="http://fm-case-service:8003")


async def get_milestone_engine(
    case_client: CaseServiceClient = Depends(get_case_service_client),
) -> MilestoneEngine:
    """Get MilestoneEngine instance with dependencies."""
    # Phase 6.2: Multi-provider with automatic fallback
    # Tries: OpenAI → Anthropic → Fireworks (based on available API keys)
    from agent_service.infrastructure.llm.multi_provider import MultiProviderLLM
    llm_provider = MultiProviderLLM()

    return MilestoneEngine(
        llm_provider=llm_provider,
        case_service_client=case_client,
        trace_enabled=True
    )


async def get_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
) -> str:
    """Extract user ID from X-User-ID header (added by API Gateway)."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required (should be added by API Gateway)",
        )
    return x_user_id


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/chat/{case_id}", response_model=AgentChatResponse)
async def agent_chat(
    case_id: str,
    request: AgentChatRequest,
    user_id: str = Depends(get_user_id),
    case_client: CaseServiceClient = Depends(get_case_service_client),
    engine: MilestoneEngine = Depends(get_milestone_engine),
):
    """Process agent chat message for a case.

    This endpoint:
    1. Retrieves the case from case-service via HTTP
    2. Processes the turn using MilestoneEngine
    3. Returns agent response and metadata

    The case is updated via HTTP client (stateless service).

    Args:
        case_id: Case identifier
        request: Chat message and optional attachments
        user_id: User ID from X-User-ID header
        case_client: Case service HTTP client
        engine: Milestone engine instance

    Returns:
        AgentChatResponse: Agent response and turn metadata

    Raises:
        HTTPException: If case not found or unauthorized
    """
    try:
        # Step 1: Retrieve case via HTTP
        logger.info(f"Processing chat for case {case_id}, user {user_id}")
        case = await case_client.get_case(case_id)

        # Step 2: Authorization check
        if case.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this case"
            )

        # Step 3: Convert attachments to dict format
        attachments_dict = None
        if request.attachments:
            attachments_dict = [att.model_dump() for att in request.attachments]

        # Step 4: Process turn with MilestoneEngine
        result = await engine.process_turn(
            case=case,
            user_message=request.message,
            attachments=attachments_dict
        )

        # Step 5: Build response
        metadata = result["metadata"]
        response = AgentChatResponse(
            agent_response=result["agent_response"],
            case_id=case_id,
            turn_number=metadata["turn_number"],
            milestones_completed=metadata.get("milestones_completed", []),
            progress_made=metadata.get("progress_made", False),
            status_transitioned=metadata.get("status_transitioned", False),
            current_status=result["case_updated"].status.value,
            timestamp=metadata["timestamp"]
        )

        logger.info(
            f"Chat processed for case {case_id}, turn {metadata['turn_number']}, "
            f"progress: {metadata.get('progress_made', False)}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process chat for case {case_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat: {str(e)}"
        )


@router.get("/health")
async def agent_health():
    """Agent service health check."""
    return {
        "status": "healthy",
        "service": "agent",
        "version": "2.0",
        "engine": "milestone-based"
    }
