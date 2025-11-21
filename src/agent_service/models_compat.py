"""
Temporary compatibility models for migration from monolithic to microservices.
These were originally in faultmaven.models.api and faultmaven.models.agentic.
TODO: Migrate to fm-core-lib or agent_service/domain/models once architecture is finalized.
"""

from enum import Enum


class ResponseType(str, Enum):
    """Response type classification"""
    CLARIFICATION_REQUEST = "clarification_request"
    PLAN_PROPOSAL = "plan_proposal"
    SOLUTION_READY = "solution_ready"
    NEEDS_MORE_DATA = "needs_more_data"
    ESCALATION_REQUIRED = "escalation_required"
    CONFIRMATION_REQUEST = "confirmation_request"
    ANSWER = "answer"


class QueryIntent(str, Enum):
    """User query intent classification"""
    TROUBLESHOOT = "troubleshoot"
    EXPLAIN = "explain"
    RECOMMEND = "recommend"
    ANALYZE = "analyze"
