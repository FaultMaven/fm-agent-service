"""
Agent Service Unified Logging System

Provides a unified logging interface with consistent, deduplicated logging
across all application layers with performance tracking.

Simplified version suitable for microservice architecture.
"""

import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Dict, Iterator, Optional
from datetime import datetime, timezone

from .context import request_context, LoggingCoordinator
from .config import get_logger


class UnifiedLogger:
    """
    Unified logger that provides consistent logging patterns across all application layers.

    This class integrates with the logging infrastructure to provide:
    - Automatic deduplication of log entries
    - Performance tracking with layer-specific thresholds
    - Unified operation logging with timing
    - Context-aware logging

    Attributes:
        logger_name: Name of the logger instance
        layer: Application layer (api, service, core, infrastructure)
        logger: Underlying structlog logger
        coordinator: Logging coordinator for request management
    """

    def __init__(self, logger_name: str, layer: str):
        """
        Initialize unified logger for specific layer.

        Args:
            logger_name: Name for the logger (typically module or class name)
            layer: Application layer (api, service, core, infrastructure)
        """
        self.logger_name = logger_name
        self.layer = layer
        self.logger = get_logger(logger_name)
        self.coordinator = LoggingCoordinator()

    def log_boundary(
        self,
        operation: str,
        direction: str,
        data: Optional[Dict[str, Any]] = None,
        **extra_fields
    ) -> None:
        """
        Log service boundary crossings with automatic deduplication.

        This method logs when data crosses service boundaries (inbound/outbound)
        and prevents duplicate logging for the same boundary crossing within
        a request context.

        Args:
            operation: Name of the operation (e.g., "process_query", "get_knowledge")
            direction: Direction of boundary crossing ("inbound" or "outbound")
            data: Optional data payload information (sanitized)
            **extra_fields: Additional fields to include in log
        """
        # Generate unique operation key for deduplication
        operation_key = f"{self.layer}.boundary.{operation}.{direction}"

        # Check if already logged in current request context
        ctx = request_context.get()
        if ctx and ctx.has_logged(operation_key):
            return

        # Prepare log data
        log_data = {
            "event_type": "service_boundary",
            "layer": self.layer,
            "operation": operation,
            "direction": direction,
            "boundary_key": operation_key,
            **extra_fields
        }

        # Add data payload information if provided (should be pre-sanitized)
        if data:
            log_data["payload_info"] = {
                "type": type(data).__name__,
                "size": len(str(data)) if data else 0,
                "keys": list(data.keys()) if isinstance(data, dict) else None
            }

        # Log with deduplication
        message = f"Service boundary {direction}: {operation}"
        if ctx:
            # Use coordinator for deduplication
            LoggingCoordinator.log_once(
                operation_key=operation_key,
                logger=self.logger,
                level="info",
                message=message,
                **log_data
            )
        else:
            # Fallback logging without coordination
            self.logger.info(message, **log_data)

    @asynccontextmanager
    async def operation(
        self,
        operation_name: str,
        **context_fields
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Context manager for unified operation logging with timing and error handling.

        This async context manager provides:
        - Automatic operation start/end logging
        - Performance timing with threshold checking
        - Context field management
        - Resource cleanup

        Args:
            operation_name: Name of the operation being performed
            **context_fields: Additional context fields for the operation

        Yields:
            Dictionary containing operation context that can be updated during execution

        Example:
            >>> async with logger.operation("process_user_query", user_id="123") as ctx:
            ...     ctx["query_type"] = "troubleshooting"
            ...     result = await some_async_operation()
            ...     ctx["result_count"] = len(result)
        """
        start_time = time.time()
        operation_key = f"{self.layer}.operation.{operation_name}"

        # Initialize operation context
        operation_context = {
            "operation": operation_name,
            "layer": self.layer,
            "start_time": datetime.now(timezone.utc).isoformat(),
            **context_fields
        }

        # Get request context for coordination
        request_ctx = request_context.get()

        try:
            # Log operation start (with deduplication)
            start_key = f"{operation_key}.start"
            if request_ctx and not request_ctx.has_logged(start_key):
                self.logger.info(
                    f"Operation started: {operation_name}",
                    event_type="operation_start",
                    operation_key=operation_key,
                    **operation_context
                )
                request_ctx.mark_logged(start_key)
            elif not request_ctx:
                self.logger.info(
                    f"Operation started: {operation_name}",
                    event_type="operation_start",
                    operation_key=operation_key,
                    **operation_context
                )

            # Yield context for caller to modify
            yield operation_context

        except Exception as error:
            # Calculate duration for error logging
            duration = time.time() - start_time

            # Log error
            self.logger.error(
                f"Operation failed: {operation_name}",
                event_type="operation_error",
                operation_key=operation_key,
                error_message=str(error),
                error_type=type(error).__name__,
                duration_seconds=duration,
                **operation_context
            )

            # Re-raise the exception
            raise

        else:
            # Calculate final duration
            duration = time.time() - start_time

            # Record performance timing
            performance_violation = False
            threshold = 1.0  # Default threshold

            if request_ctx and request_ctx.performance_tracker:
                violation, threshold = request_ctx.performance_tracker.record_timing(
                    self.layer, operation_name, duration
                )
                performance_violation = violation

            # Update context with final timing
            operation_context.update({
                "end_time": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "performance_violation": performance_violation,
                "threshold_seconds": threshold
            })

            # Log operation completion (with deduplication)
            end_key = f"{operation_key}.end"
            log_level = "warning" if performance_violation else "info"

            if request_ctx and not request_ctx.has_logged(end_key):
                log_method = getattr(self.logger, log_level)
                log_method(
                    f"Operation completed: {operation_name}",
                    event_type="operation_end",
                    operation_key=operation_key,
                    **operation_context
                )
                request_ctx.mark_logged(end_key)
            elif not request_ctx:
                log_method = getattr(self.logger, log_level)
                log_method(
                    f"Operation completed: {operation_name}",
                    event_type="operation_end",
                    operation_key=operation_key,
                    **operation_context
                )

    @contextmanager
    def operation_sync(
        self,
        operation_name: str,
        **context_fields
    ) -> Iterator[Dict[str, Any]]:
        """
        Synchronous version of operation context manager.

        Provides the same functionality as the async operation() method
        but for synchronous operations.

        Args:
            operation_name: Name of the operation being performed
            **context_fields: Additional context fields for the operation

        Yields:
            Dictionary containing operation context that can be updated during execution
        """
        start_time = time.time()
        operation_key = f"{self.layer}.operation.{operation_name}"

        # Initialize operation context
        operation_context = {
            "operation": operation_name,
            "layer": self.layer,
            "start_time": datetime.now(timezone.utc).isoformat(),
            **context_fields
        }

        # Get request context for coordination
        request_ctx = request_context.get()

        try:
            # Log operation start (with deduplication)
            start_key = f"{operation_key}.start"
            if request_ctx and not request_ctx.has_logged(start_key):
                self.logger.info(
                    f"Operation started: {operation_name}",
                    event_type="operation_start",
                    operation_key=operation_key,
                    **operation_context
                )
                request_ctx.mark_logged(start_key)
            elif not request_ctx:
                self.logger.info(
                    f"Operation started: {operation_name}",
                    event_type="operation_start",
                    operation_key=operation_key,
                    **operation_context
                )

            # Yield context for caller to modify
            yield operation_context

        except Exception as error:
            # Calculate duration for error logging
            duration = time.time() - start_time

            # Log error
            self.logger.error(
                f"Operation failed: {operation_name}",
                event_type="operation_error",
                operation_key=operation_key,
                error_message=str(error),
                error_type=type(error).__name__,
                duration_seconds=duration,
                **operation_context
            )

            # Re-raise the exception
            raise

        else:
            # Calculate final duration
            duration = time.time() - start_time

            # Record performance timing
            performance_violation = False
            threshold = 1.0  # Default threshold

            if request_ctx and request_ctx.performance_tracker:
                violation, threshold = request_ctx.performance_tracker.record_timing(
                    self.layer, operation_name, duration
                )
                performance_violation = violation

            # Update context with final timing
            operation_context.update({
                "end_time": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "performance_violation": performance_violation,
                "threshold_seconds": threshold
            })

            # Log operation completion (with deduplication)
            end_key = f"{operation_key}.end"
            log_level = "warning" if performance_violation else "info"

            if request_ctx and not request_ctx.has_logged(end_key):
                log_method = getattr(self.logger, log_level)
                log_method(
                    f"Operation completed: {operation_name}",
                    event_type="operation_end",
                    operation_key=operation_key,
                    **operation_context
                )
                request_ctx.mark_logged(end_key)
            elif not request_ctx:
                log_method = getattr(self.logger, log_level)
                log_method(
                    f"Operation completed: {operation_name}",
                    event_type="operation_end",
                    operation_key=operation_key,
                    **operation_context
                )

    def debug(self, message: str, **extra_fields) -> None:
        """Log debug message with layer context."""
        self.logger.debug(message, layer=self.layer, **extra_fields)

    def info(self, message: str, **extra_fields) -> None:
        """Log info message with layer context."""
        self.logger.info(message, layer=self.layer, **extra_fields)

    def warning(self, message: str, **extra_fields) -> None:
        """Log warning message with layer context."""
        self.logger.warning(message, layer=self.layer, **extra_fields)

    def error(self, message: str, error: Optional[Exception] = None, **extra_fields) -> None:
        """Log error message with optional exception details."""
        error_data = {"layer": self.layer, **extra_fields}

        if error:
            error_data.update({
                "error_message": str(error),
                "error_type": type(error).__name__
            })

        self.logger.error(message, **error_data)

    def critical(self, message: str, error: Optional[Exception] = None, **extra_fields) -> None:
        """Log critical message with optional exception details."""
        error_data = {"layer": self.layer, **extra_fields}

        if error:
            error_data.update({
                "error_message": str(error),
                "error_type": type(error).__name__
            })

        self.logger.critical(message, **error_data)


# Global logger instances cache to avoid recreating loggers
_logger_instances: Dict[str, UnifiedLogger] = {}


def get_unified_logger(name: str, layer: str) -> UnifiedLogger:
    """
    Factory function to get or create a unified logger instance.

    This function ensures that logger instances are reused for the same
    name and layer combination, preventing resource waste and maintaining
    consistency.

    Args:
        name: Logger name (typically module or class name)
        layer: Application layer (api, service, core, infrastructure)

    Returns:
        UnifiedLogger instance configured for the specified name and layer

    Example:
        >>> logger = get_unified_logger(__name__, "service")
        >>> async with logger.operation("process_data") as ctx:
        ...     ctx["items_processed"] = 10
    """
    # Validate layer
    valid_layers = {"api", "service", "core", "infrastructure"}
    if layer not in valid_layers:
        raise ValueError(f"Invalid layer '{layer}'. Must be one of: {valid_layers}")

    # Create cache key
    cache_key = f"{name}:{layer}"

    # Return existing instance or create new one
    if cache_key not in _logger_instances:
        _logger_instances[cache_key] = UnifiedLogger(name, layer)

    return _logger_instances[cache_key]


def clear_logger_cache() -> None:
    """
    Clear the logger instance cache.

    This function is primarily used for testing to ensure clean state
    between test runs.
    """
    global _logger_instances
    _logger_instances.clear()
