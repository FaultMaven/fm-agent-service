"""
Integration tests for logging infrastructure.

Tests the complete logging stack: RequestContext, UnifiedLogger, and middleware.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_service.infrastructure.logging import (
    RequestContext,
    request_context,
    LoggingCoordinator,
    UnifiedLogger,
    get_unified_logger,
    LoggingMiddleware
)


def test_request_context_creation():
    """Test RequestContext creation and basic functionality."""
    ctx = RequestContext(
        session_id="test-session",
        user_id="test-user",
        case_id="test-case"
    )

    assert ctx.correlation_id is not None
    assert ctx.session_id == "test-session"
    assert ctx.user_id == "test-user"
    assert ctx.case_id == "test-case"
    assert len(ctx.logged_operations) == 0


def test_request_context_deduplication():
    """Test operation deduplication in RequestContext."""
    ctx = RequestContext()

    operation_key = "test.operation"

    # First check should return False
    assert not ctx.has_logged(operation_key)

    # Mark as logged
    ctx.mark_logged(operation_key)

    # Second check should return True
    assert ctx.has_logged(operation_key)


def test_request_context_as_context_manager():
    """Test RequestContext as context manager."""
    ctx = RequestContext(session_id="test-session")

    # Before entering context, request_context should be None
    assert request_context.get() is None

    # Enter context
    with ctx:
        # Inside context, request_context should be set
        active_ctx = request_context.get()
        assert active_ctx is not None
        assert active_ctx.session_id == "test-session"

    # After exiting context, request_context should be None again
    assert request_context.get() is None


def test_logging_coordinator_lifecycle():
    """Test LoggingCoordinator request lifecycle management."""
    coordinator = LoggingCoordinator()

    # Start request with context
    ctx = coordinator.start_request(
        session_id="test-session",
        user_id="test-user",
        custom_field="custom_value"
    )

    # Verify context was created and set
    assert ctx.session_id == "test-session"
    assert ctx.user_id == "test-user"
    assert ctx.attributes["custom_field"] == "custom_value"
    assert request_context.get() == ctx

    # End request and get summary
    summary = coordinator.end_request()

    # Verify summary contains expected data
    assert "correlation_id" in summary
    assert "duration_seconds" in summary
    assert "operations_logged" in summary
    assert summary["custom_field"] == "custom_value"

    # Verify context was cleared
    assert request_context.get() is None


def test_unified_logger_creation():
    """Test UnifiedLogger creation with factory function."""
    logger = get_unified_logger(__name__, "service")

    assert logger.logger_name == __name__
    assert logger.layer == "service"


def test_unified_logger_invalid_layer():
    """Test UnifiedLogger rejects invalid layer names."""
    with pytest.raises(ValueError, match="Invalid layer"):
        get_unified_logger(__name__, "invalid_layer")


@pytest.mark.asyncio
async def test_unified_logger_operation_context():
    """Test UnifiedLogger operation context manager."""
    logger = get_unified_logger(__name__, "service")

    # Set up request context
    coordinator = LoggingCoordinator()
    ctx = coordinator.start_request(session_id="test-session")

    # Test operation context
    async with logger.operation("test_operation", test_field="test_value") as op_ctx:
        # Verify operation context contains expected fields
        assert op_ctx["operation"] == "test_operation"
        assert op_ctx["layer"] == "service"
        assert op_ctx["test_field"] == "test_value"
        assert "start_time" in op_ctx

    # Verify performance tracking was recorded
    assert ctx.performance_tracker is not None
    assert len(ctx.performance_tracker.layer_timings) > 0

    # Clean up
    coordinator.end_request()


@pytest.mark.asyncio
async def test_logging_middleware_integration():
    """Test LoggingMiddleware with FastAPI application."""
    # Create minimal FastAPI app
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_endpoint():
        # Verify request context is available inside endpoint
        ctx = request_context.get()
        assert ctx is not None
        return {
            "correlation_id": ctx.correlation_id,
            "session_id": ctx.session_id
        }

    # Create test client with AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Make request with custom headers
        response = await client.get(
            "/test",
            headers={
                "X-Session-ID": "test-session-123",
                "X-User-ID": "test-user-456",
                "X-Correlation-ID": "test-correlation-789"
            }
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["correlation_id"] == "test-correlation-789"
        assert data["session_id"] == "test-session-123"

        # Verify correlation ID is in response headers
        assert "X-Correlation-ID" in response.headers
        assert response.headers["X-Correlation-ID"] == "test-correlation-789"


def test_performance_tracker():
    """Test PerformanceTracker with layer-specific thresholds."""
    from agent_service.infrastructure.logging import PerformanceTracker

    tracker = PerformanceTracker()

    # Test within threshold (API: 100ms)
    violation, threshold = tracker.record_timing("api", "fast_op", 0.05)
    assert not violation
    assert threshold == 0.1

    # Test exceeding threshold (API: 100ms)
    violation, threshold = tracker.record_timing("api", "slow_op", 0.5)
    assert violation
    assert threshold == 0.1

    # Test different layer threshold (infrastructure: 1s)
    violation, threshold = tracker.record_timing("infrastructure", "external_call", 0.8)
    assert not violation
    assert threshold == 1.0

    # Verify timings were recorded
    assert "api.fast_op" in tracker.layer_timings
    assert "api.slow_op" in tracker.layer_timings
    assert "infrastructure.external_call" in tracker.layer_timings
