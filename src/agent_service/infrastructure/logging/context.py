"""
Agent Service Request Context

Provides request-scoped context tracking using contextvars for async operations.
Simplified version suitable for microservice architecture.
"""

from contextvars import ContextVar
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class RequestContext:
    """
    Request-scoped context for correlation tracking and logging coordination.

    This class manages all request-related context and prevents duplicate logging
    operations through operation tracking.

    Attributes:
        correlation_id: Unique identifier for request tracing across services
        session_id: Optional session identifier for user tracking
        user_id: Optional user identifier
        case_id: Optional troubleshooting case identifier
        start_time: Request start timestamp for duration tracking
        attributes: Additional request-scoped metadata (extensible)
        logged_operations: Set of logged operation keys for deduplication
        performance_tracker: Performance monitoring with layer-specific thresholds
    """
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: Dict[str, Any] = field(default_factory=dict)
    logged_operations: Set[str] = field(default_factory=set)
    performance_tracker: Optional['PerformanceTracker'] = None

    def has_logged(self, operation_key: str) -> bool:
        """
        Check if an operation has already been logged to prevent duplicates.

        Args:
            operation_key: Unique key identifying the operation

        Returns:
            True if operation has been logged, False otherwise
        """
        return operation_key in self.logged_operations

    def mark_logged(self, operation_key: str) -> None:
        """
        Mark an operation as logged to prevent future duplicates.

        Args:
            operation_key: Unique key identifying the operation
        """
        self.logged_operations.add(operation_key)

    def __enter__(self):
        """Enter the context manager - set this context as active."""
        request_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager - clear the active context."""
        request_context.set(None)
        return False


class PerformanceTracker:
    """
    Track performance metrics across layers with configurable thresholds.

    This class monitors operation performance and flags slow operations
    based on layer-specific thresholds, enabling proactive performance
    monitoring and alerting.
    """

    def __init__(self):
        """Initialize with default performance thresholds per layer."""
        self.layer_timings: Dict[str, float] = {}
        self.thresholds = {
            'api': 0.1,           # 100ms - API should be fast
            'service': 0.5,       # 500ms - Service orchestration
            'core': 0.3,          # 300ms - Core domain logic
            'infrastructure': 1.0  # 1s - External calls can be slower
        }

    def record_timing(self, layer: str, operation: str, duration: float) -> tuple[bool, float]:
        """
        Record timing and return if it exceeds threshold.

        Args:
            layer: Layer name (api, service, core, infrastructure)
            operation: Operation name
            duration: Operation duration in seconds

        Returns:
            Tuple of (exceeds_threshold, threshold_value)
        """
        key = f"{layer}.{operation}"
        self.layer_timings[key] = duration

        threshold = self.thresholds.get(layer, 1.0)
        exceeds_threshold = duration > threshold

        return exceeds_threshold, threshold


# Thread-safe context variable for request context
# This works across async operations using Python's contextvars
request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    'request_context',
    default=None
)


class LoggingCoordinator:
    """
    Coordinates all logging for a request lifecycle.

    This class manages request-scoped logging context and provides methods
    for coordinated logging across all application layers. It ensures that
    each request has a single point of coordination for all logging activities.
    """

    def __init__(self):
        """Initialize the logging coordinator."""
        self.context: Optional[RequestContext] = None

    def start_request(self, **initial_context) -> RequestContext:
        """
        Initialize request context - called ONCE per request.

        This method should be called at the beginning of each request to establish
        the logging context that will be used throughout the request lifecycle.

        Args:
            **initial_context: Initial context attributes (session_id, user_id, etc.)

        Returns:
            RequestContext: The initialized request context
        """
        # Separate known RequestContext fields from arbitrary attributes
        known_fields = {
            'correlation_id', 'session_id', 'user_id', 'case_id', 'start_time'
        }

        # Extract known fields for RequestContext constructor
        context_args = {k: v for k, v in initial_context.items() if k in known_fields}

        # Extract additional attributes
        additional_attrs = {k: v for k, v in initial_context.items() if k not in known_fields}

        # Create context with known fields
        self.context = RequestContext(**context_args)

        # Add additional attributes to the attributes dict
        if additional_attrs:
            self.context.attributes.update(additional_attrs)

        # Initialize performance tracker
        self.context.performance_tracker = PerformanceTracker()

        # Set as active context
        request_context.set(self.context)
        return self.context

    def end_request(self) -> Dict[str, Any]:
        """
        Finalize request - returns metrics for single summary log.

        This method should be called at the end of each request to generate
        a summary of the request's logging activity and performance metrics.

        Returns:
            Dict containing request summary metrics
        """
        if not self.context:
            return {}

        duration = (datetime.now(timezone.utc) - self.context.start_time).total_seconds()

        # Calculate performance violations
        performance_violations = 0
        if self.context.performance_tracker:
            for timing_key, timing_value in self.context.performance_tracker.layer_timings.items():
                layer = timing_key.split('.')[0]
                threshold = self.context.performance_tracker.thresholds.get(layer, 1.0)
                if timing_value > threshold:
                    performance_violations += 1

        summary = {
            'correlation_id': self.context.correlation_id,
            'duration_seconds': duration,
            'operations_logged': len(self.context.logged_operations),
            'performance_violations': performance_violations,
            **self.context.attributes
        }

        # Clear context
        request_context.set(None)
        self.context = None

        return summary

    @staticmethod
    def get_context() -> Optional[RequestContext]:
        """
        Get current request context.

        Returns:
            Current RequestContext if available, None otherwise
        """
        return request_context.get()

    @staticmethod
    def log_once(operation_key: str, logger, level: str,
                 message: str, **extra) -> None:
        """
        Log an operation only if it hasn't been logged yet.

        This method prevents duplicate logging by checking if the operation
        has already been logged in the current request context.

        Args:
            operation_key: Unique key identifying the operation
            logger: Logger instance to use (structlog BoundLogger)
            level: Log level (debug, info, warning, error, critical)
            message: Log message
            **extra: Additional fields to include in log
        """
        ctx = request_context.get()
        if ctx and not ctx.has_logged(operation_key):
            # Get the logging method for the specified level
            log_method = getattr(logger, level.lower(), logger.info)
            log_method(message, **extra)
            # Mark as logged to prevent duplicates
            ctx.mark_logged(operation_key)
