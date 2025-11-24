"""
Agent Service Logging Middleware

FastAPI middleware for request-scoped logging context initialization.
"""

import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .context import LoggingCoordinator
from .config import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to initialize request-scoped logging context.

    This middleware:
    - Creates a unique correlation ID for each request
    - Initializes RequestContext with user/session information from headers
    - Ensures logging context is available throughout request lifecycle
    - Logs request summary at completion
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and initialize logging context.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Initialize logging coordinator
        coordinator = LoggingCoordinator()

        # Extract correlation ID from header or generate new one
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        # Extract user/session info from headers (if available)
        session_id = request.headers.get("X-Session-ID")
        user_id = request.headers.get("X-User-ID")
        case_id = request.headers.get("X-Case-ID")

        # Start request context
        ctx = coordinator.start_request(
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=user_id,
            case_id=case_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None
        )

        # Log request start
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=user_id,
            case_id=case_id
        )

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers for tracing
            response.headers["X-Correlation-ID"] = correlation_id

            # End request and get summary
            summary = coordinator.end_request()

            # Log request summary
            logger.info(
                "Request completed",
                status_code=response.status_code,
                **summary
            )

            return response

        except Exception as e:
            # Log error
            logger.error(
                "Request failed",
                error_message=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id
            )

            # End request even on error
            coordinator.end_request()

            # Re-raise exception
            raise
