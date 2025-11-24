"""
Agent Service Opik Tracing Integration

Provides distributed tracing capabilities using Comet Opik with graceful
fallback when unavailable. Simplified version for microservice architecture.
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any

from agent_service.infrastructure.logging import request_context, get_logger

# Try to import Opik SDK
try:
    import opik
    OPIK_AVAILABLE = True
except ImportError:
    OPIK_AVAILABLE = False
    logging.warning("Comet Opik SDK not available - tracing will be disabled")

logger = get_logger(__name__)


class OpikTracer:
    """
    Opik-based tracer with graceful fallback.

    This tracer provides distributed tracing capabilities using Comet Opik
    with graceful fallback to local logging when Opik is unavailable.

    Features:
    - Targeted tracing by user, session, or operation
    - Graceful degradation when Opik unavailable
    - Integration with RequestContext for correlation
    """

    def __init__(self):
        """Initialize OpikTracer with environment-based configuration."""
        self.opik_available = OPIK_AVAILABLE

        # Read configuration from environment
        self.opik_url = os.getenv("OPIK_URL", "http://localhost:8080")
        self.opik_workspace = os.getenv("OPIK_WORKSPACE", "faultmaven")
        self.opik_project = os.getenv("OPIK_PROJECT", "FaultMaven")
        self.opik_api_key = os.getenv("OPIK_API_KEY", "")

        # Tracing control flags
        self.track_disable = os.getenv("OPIK_TRACK_DISABLE", "false").lower() == "true"
        self.track_users = os.getenv("OPIK_TRACK_USERS", "")  # Comma-separated list
        self.track_sessions = os.getenv("OPIK_TRACK_SESSIONS", "")  # Comma-separated list
        self.track_operations = os.getenv("OPIK_TRACK_OPERATIONS", "")  # Comma-separated list

        # Initialize Opik if available and not disabled
        if self.opik_available and not self.track_disable:
            try:
                self._init_opik()
                logger.info(
                    "Opik tracer initialized",
                    url=self.opik_url,
                    workspace=self.opik_workspace,
                    project=self.opik_project
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Opik: {e}")
                self.opik_available = False
        elif self.track_disable:
            logger.info("Opik tracing disabled by configuration")

    def _init_opik(self):
        """Initialize Opik configuration."""
        if not OPIK_AVAILABLE:
            return

        try:
            # Configure Opik with environment settings
            opik.configure(
                api_url=self.opik_url,
                workspace=self.opik_workspace,
            )
        except Exception as e:
            logger.error(f"Opik configuration failed: {e}")
            raise

    @contextmanager
    def trace(self, operation: str, **tags):
        """
        Create a trace context for an operation.

        This context manager creates an Opik trace span with automatic error
        handling and graceful fallback when tracing is unavailable.

        Args:
            operation: Name of the operation being traced
            **tags: Additional tags to attach to the trace span

        Yields:
            Trace span object or None if tracing unavailable

        Example:
            >>> tracer = get_tracer()
            >>> with tracer.trace("llm_query", model="gpt-4") as span:
            ...     result = await llm.generate(prompt)
            ...     if span:
            ...         span.log({"result_length": len(result)})
        """
        start_time = time.time()
        span = None

        # Check if tracing should be enabled for this operation
        if not self._should_trace(operation):
            logger.debug(f"Tracing disabled for operation: {operation}")
            yield None
            self._record_fallback_metrics(operation, start_time)
            return

        if self.opik_available:
            try:
                # Get request context for correlation
                ctx = request_context.get()

                # Build trace tags
                trace_tags = {
                    "operation": operation,
                    "project": self.opik_project,
                    **tags
                }

                # Add correlation IDs from request context if available
                if ctx:
                    if ctx.correlation_id:
                        trace_tags["correlation_id"] = ctx.correlation_id
                    if ctx.session_id:
                        trace_tags["session_id"] = ctx.session_id
                    if ctx.user_id:
                        trace_tags["user_id"] = ctx.user_id
                    if ctx.case_id:
                        trace_tags["case_id"] = ctx.case_id

                # Create Opik span
                span = opik.track(name=operation, tags=trace_tags)

                with span:
                    logger.debug(f"Opik trace started: {operation}")
                    yield span

            except Exception as e:
                # Fallback - log warning but continue without tracing
                logger.warning(f"Opik tracing failed for operation '{operation}': {e}")
                self._record_fallback_metrics(operation, start_time, error=str(e))
                yield None
        else:
            # No Opik available - use fallback logging
            logger.debug(f"Fallback trace: {operation} (Opik unavailable)")
            self._record_fallback_metrics(operation, start_time)
            yield None

    def _should_trace(self, operation: str) -> bool:
        """
        Determine if tracing should be enabled for this operation.

        Supports:
        - Global disable: OPIK_TRACK_DISABLE=true
        - Target users: OPIK_TRACK_USERS=user1,user2,user3
        - Target sessions: OPIK_TRACK_SESSIONS=session1,session2
        - Target operations: OPIK_TRACK_OPERATIONS=llm_query,knowledge_search

        Args:
            operation: Operation name being traced

        Returns:
            True if tracing should be enabled, False otherwise
        """
        # Global disable check
        if self.track_disable:
            return False

        # Get current request context for targeted tracing
        ctx = request_context.get()

        # Check for targeted user tracing
        if self.track_users:
            target_user_list = [u.strip() for u in self.track_users.split(",") if u.strip()]
            if target_user_list:
                if not ctx or not ctx.user_id:
                    return False  # No user context, but targeting specific users
                if ctx.user_id not in target_user_list:
                    return False  # User not in target list

        # Check for targeted session tracing
        if self.track_sessions:
            target_session_list = [s.strip() for s in self.track_sessions.split(",") if s.strip()]
            if target_session_list:
                if not ctx or not ctx.session_id:
                    return False  # No session context, but targeting specific sessions
                if ctx.session_id not in target_session_list:
                    return False  # Session not in target list

        # Check for targeted operation tracing
        if self.track_operations:
            target_op_list = [op.strip() for op in self.track_operations.split(",") if op.strip()]
            if target_op_list:
                if operation not in target_op_list:
                    return False  # Operation not in target list

        return True  # Default to enabled if no restrictions apply

    def _record_fallback_metrics(self, operation: str, start_time: float, error: Optional[str] = None):
        """
        Record fallback metrics when Opik is unavailable.

        Args:
            operation: Operation name
            start_time: Operation start time
            error: Optional error message
        """
        duration = time.time() - start_time

        log_data = {
            "operation": operation,
            "duration_seconds": duration,
            "trace_fallback": True
        }

        if error:
            log_data["trace_error"] = error

        logger.debug("Operation trace fallback", **log_data)

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check for OpikTracer.

        Returns:
            Dictionary containing health status and configuration
        """
        health = {
            "opik_sdk_available": OPIK_AVAILABLE,
            "tracing_enabled": self.opik_available and not self.track_disable,
            "configuration": {
                "url": self.opik_url,
                "workspace": self.opik_workspace,
                "project": self.opik_project,
                "track_disable": self.track_disable,
                "targeted_tracing": {
                    "users": bool(self.track_users),
                    "sessions": bool(self.track_sessions),
                    "operations": bool(self.track_operations)
                }
            }
        }

        # Determine overall status
        if self.opik_available and not self.track_disable:
            health["status"] = "healthy"
        elif self.track_disable:
            health["status"] = "disabled"
        else:
            health["status"] = "degraded"  # Can still function with fallback logging

        return health


# Singleton tracer instance
_tracer: Optional[OpikTracer] = None


def get_tracer() -> OpikTracer:
    """
    Get the global OpikTracer instance.

    Factory function that ensures a single tracer instance is used
    throughout the application lifecycle.

    Returns:
        OpikTracer instance

    Example:
        >>> tracer = get_tracer()
        >>> with tracer.trace("my_operation") as span:
        ...     do_work()
    """
    global _tracer
    if _tracer is None:
        _tracer = OpikTracer()
    return _tracer
