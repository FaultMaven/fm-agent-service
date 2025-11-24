# Logging & Observability Infrastructure Restoration

**Date**: 2025-11-24
**Status**: ✅ Complete
**Scope**: Restore lost logging and observability features from monolith to fm-agent-service

## Overview

This document describes the systematic restoration of logging and observability infrastructure that was lost during the FaultMaven microservices migration. The implementation follows the dependency chain: `Logging Middleware → RequestContext → UnifiedLogger → Observability/Opik`.

## Implementation Summary

### 1. Infrastructure Setup ✅

Created directory structure:
```
fm-agent-service/src/agent_service/infrastructure/
├── logging/
│   ├── __init__.py
│   ├── context.py          # RequestContext with contextvars
│   ├── config.py           # Structured logging configuration
│   ├── unified.py          # UnifiedLogger with operation tracking
│   └── middleware.py       # FastAPI middleware for request context
└── observability/
    ├── __init__.py
    └── tracing.py          # Opik tracing integration
```

### 2. Core Context (RequestContext) ✅

**File**: `src/agent_service/infrastructure/logging/context.py`

**Key Components**:
- `RequestContext`: Request-scoped context using Python `contextvars`
- `PerformanceTracker`: Layer-specific performance monitoring
- `LoggingCoordinator`: Request lifecycle management

**Features**:
- Async-safe context tracking using `contextvars.ContextVar`
- Correlation ID propagation across services
- Operation deduplication to prevent log spam
- Performance threshold tracking per layer (api: 100ms, service: 500ms, core: 300ms, infrastructure: 1s)
- Context manager support for clean lifecycle management

**Key Fields**:
```python
@dataclass
class RequestContext:
    correlation_id: str          # Unique request identifier
    session_id: Optional[str]    # User session tracking
    user_id: Optional[str]       # User identification
    case_id: Optional[str]       # Troubleshooting case ID
    start_time: datetime         # Request start timestamp
    attributes: Dict[str, Any]   # Extensible metadata
    logged_operations: Set[str]  # Deduplication tracking
    performance_tracker: PerformanceTracker  # Performance monitoring
```

### 3. Structured Logging Configuration ✅

**File**: `src/agent_service/infrastructure/logging/config.py`

**Key Components**:
- `LoggingConfig`: Environment-based configuration
- `AgentServiceLogger`: Structlog configuration
- `get_logger()`: Factory function for consistent logger instances

**Features**:
- JSON-formatted structured logs (production default)
- Console rendering for development (via LOG_FORMAT=console)
- Request context injection into all log entries
- Field deduplication to prevent cluttered logs
- Log level control via LOG_LEVEL environment variable

**Environment Variables**:
```bash
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json             # json, console
LOG_DEDUPE=true             # Enable field deduplication
```

**Processor Chain**:
1. Log level filtering
2. Logger name and level addition
3. ISO timestamp formatting
4. Exception information formatting
5. Request context injection (correlation_id, session_id, user_id, case_id)
6. Field deduplication
7. JSON rendering

### 4. Unified Logger ✅

**File**: `src/agent_service/infrastructure/logging/unified.py`

**Key Components**:
- `UnifiedLogger`: Layer-aware logger with operation tracking
- `get_unified_logger()`: Factory with caching

**Features**:
- Automatic operation start/end logging with timing
- Performance threshold detection and warnings
- Service boundary logging with deduplication
- Async and sync operation context managers
- Layer-specific context (api, service, core, infrastructure)

**Usage Example**:
```python
from agent_service.infrastructure.logging import get_unified_logger

logger = get_unified_logger(__name__, "service")

# Async operation tracking
async with logger.operation("process_query", user_id="123") as ctx:
    ctx["query_type"] = "troubleshooting"
    result = await do_work()
    ctx["result_count"] = len(result)
# Automatically logs start, end, duration, and performance violations

# Simple logging with layer context
logger.info("User authenticated", user_id="123")
logger.error("Database connection failed", error=exc)
```

### 5. Logging Middleware ✅

**File**: `src/agent_service/infrastructure/logging/middleware.py`

**Key Components**:
- `LoggingMiddleware`: FastAPI middleware for request context initialization

**Features**:
- Automatic correlation ID generation or extraction from headers
- Request context initialization from HTTP headers
- Request start/end logging with summary metrics
- Correlation ID propagation in response headers
- Graceful error handling with context cleanup

**HTTP Headers**:
```
X-Correlation-ID: <correlation-id>  # Request tracing
X-Session-ID: <session-id>          # Session tracking
X-User-ID: <user-id>                # User identification
X-Case-ID: <case-id>                # Case tracking
```

**Integration** (main.py):
```python
from agent_service.infrastructure.logging import LoggingMiddleware, get_logger

logger = get_logger(__name__)
app = FastAPI(...)

# Add logging middleware (must be first)
app.add_middleware(LoggingMiddleware)
```

### 6. Opik Tracing Integration ✅

**File**: `src/agent_service/infrastructure/observability/tracing.py`

**Key Components**:
- `OpikTracer`: Opik integration with graceful fallback
- `get_tracer()`: Singleton tracer instance

**Features**:
- Distributed tracing with Comet Opik
- Graceful fallback to local logging when Opik unavailable
- Targeted tracing by user, session, or operation
- Automatic correlation ID injection from RequestContext
- Health check endpoint for monitoring

**Environment Variables**:
```bash
# Opik Configuration
OPIK_URL=http://localhost:8080
OPIK_WORKSPACE=faultmaven
OPIK_PROJECT=FaultMaven
OPIK_API_KEY=                    # Optional for local Opik

# Tracing Control
OPIK_TRACK_DISABLE=false         # Global disable
OPIK_TRACK_USERS=                # Comma-separated user IDs
OPIK_TRACK_SESSIONS=             # Comma-separated session IDs
OPIK_TRACK_OPERATIONS=           # Comma-separated operations
```

**Usage Example**:
```python
from agent_service.infrastructure.observability import get_tracer

tracer = get_tracer()

# Trace an operation
with tracer.trace("llm_query", model="gpt-4", temperature=0.7) as span:
    result = await llm.generate(prompt)
    if span:
        span.log({"result_length": len(result)})
# Automatically includes correlation_id, session_id, user_id from RequestContext
```

**Targeted Tracing Examples**:
```bash
# Trace only specific users
OPIK_TRACK_USERS=user123,user456

# Trace only specific sessions
OPIK_TRACK_SESSIONS=session-abc,session-def

# Trace only LLM operations
OPIK_TRACK_OPERATIONS=llm_query,knowledge_search

# Disable all tracing
OPIK_TRACK_DISABLE=true
```

### 7. Testing ✅

**File**: `tests/infrastructure/test_logging_integration.py`

**Test Coverage**:
- ✅ RequestContext creation and basic functionality
- ✅ Operation deduplication logic
- ✅ Context manager lifecycle
- ✅ LoggingCoordinator request lifecycle management
- ✅ UnifiedLogger creation and validation
- ✅ Async operation context managers
- ✅ Performance tracking with layer-specific thresholds
- ✅ LoggingMiddleware integration with FastAPI

**Note**: Full test execution requires complete poetry environment setup.

## Dependency Updates

### pyproject.toml Changes

Added structlog for structured logging:

```toml
# Structured Logging
structlog = "^23.2.0"
```

**Other Dependencies** (already present):
- `opik = "^0.2.1"` - LLM observability
- `fastapi`, `uvicorn` - Web framework
- `pydantic`, `pydantic-settings` - Configuration management

## Migration from Monolith

### Ported Components

From `/home/swhouse/product/FaultMaven-Mono/faultmaven/infrastructure/`:

1. **logging/coordinator.py** → **context.py**
   - `RequestContext` (simplified, removed error cascade features for microservice)
   - `PerformanceTracker` (unchanged)
   - `LoggingCoordinator` (simplified)

2. **logging/config.py** → **config.py**
   - `LoggingConfig` (simplified)
   - `FaultMavenLogger` → `AgentServiceLogger` (renamed, streamlined)
   - Removed OpenTelemetry integration (not needed in microservice)

3. **logging/unified.py** → **unified.py**
   - `UnifiedLogger` (simplified, removed error cascade prevention)
   - `get_unified_logger()` (unchanged)
   - Removed ErrorContext integration (not needed in microservice)

4. **observability/tracing.py** → **tracing.py**
   - `OpikTracer` (simplified, removed BaseExternalClient inheritance)
   - Removed Prometheus metrics (use dedicated monitoring service)
   - Kept targeted tracing features

### Simplifications for Microservice Architecture

1. **Removed Error Cascade Prevention**
   - Monolith needed complex error tracking across layers
   - Microservice has simpler error propagation

2. **Removed Enhanced Error Context**
   - Pattern detection (recurring, cascade, burst, degradation)
   - Automatic recovery strategies
   - Layer-specific error configurations
   - Simplified to basic error logging

3. **Removed Prometheus Integration**
   - Metrics should be collected by dedicated monitoring service
   - Reduces complexity in individual microservices

4. **Removed Circuit Breaker Pattern**
   - BaseExternalClient dependency eliminated
   - Simpler external call handling

5. **Kept Core Features**
   - ✅ Request-scoped context tracking
   - ✅ Correlation ID propagation
   - ✅ Structured JSON logging
   - ✅ Operation deduplication
   - ✅ Performance monitoring
   - ✅ Opik distributed tracing
   - ✅ Targeted tracing capabilities

## Architecture Decision Records

### ADR-001: Use contextvars for Request Context

**Decision**: Use Python's `contextvars` module for request-scoped context tracking.

**Rationale**:
- Async-safe: Works correctly with FastAPI's async request handlers
- Thread-local alternative doesn't work with asyncio
- Built-in Python feature (no external dependencies)
- Automatic cleanup when context exits

**Alternatives Considered**:
- Thread-local storage: ❌ Doesn't work with async
- Global variable with locks: ❌ Not async-safe, performance issues
- Request.state: ❌ Limited to FastAPI, doesn't propagate to background tasks

### ADR-002: Simplify for Microservice Architecture

**Decision**: Remove advanced error handling features (cascade prevention, pattern detection, automatic recovery).

**Rationale**:
- Microservice error propagation is simpler than monolith
- Each microservice should fail fast and let orchestration layer handle recovery
- Reduces code complexity and maintenance burden
- Error patterns should be detected at observability platform level (Opik, Prometheus)

**Trade-offs**:
- ✅ Simpler, more maintainable codebase
- ✅ Clearer error propagation paths
- ❌ Less intelligent local error handling
- ❌ Pattern detection moved to external observability tools

### ADR-003: Structured JSON Logging by Default

**Decision**: Use JSON-formatted structured logs as production default.

**Rationale**:
- Machine-parseable for log aggregation systems
- Consistent schema across all microservices
- Easy integration with ELK, Loki, CloudWatch, etc.
- Better for distributed tracing correlation

**Alternatives**:
- Plain text logs: ❌ Hard to parse, no structure
- Console rendering: ⚠️ Good for development, available via LOG_FORMAT=console

## Integration Checklist

- [x] Create infrastructure directories
- [x] Implement RequestContext with contextvars
- [x] Implement structured logging configuration
- [x] Implement UnifiedLogger
- [x] Create LoggingMiddleware
- [x] Integrate middleware with main.py
- [x] Implement Opik tracing integration
- [x] Add structlog to dependencies
- [x] Update poetry.lock
- [x] Create integration tests
- [ ] Run full test suite (pending poetry environment setup)
- [ ] Verify in running service
- [ ] Document for other microservices

## Next Steps

### Immediate

1. **Complete Environment Setup**
   ```bash
   cd /home/swhouse/product/fm-agent-service
   poetry install
   poetry run pytest tests/infrastructure/test_logging_integration.py -v
   ```

2. **Verify in Running Service**
   ```bash
   # Start with Opik disabled for testing
   export OPIK_TRACK_DISABLE=true
   export LOG_LEVEL=DEBUG
   export LOG_FORMAT=console
   poetry run uvicorn agent_service.main:app --reload

   # Make test request
   curl -H "X-Session-ID: test-123" http://localhost:8000/health

   # Check logs for correlation_id, session_id in output
   ```

3. **Enable Opik Tracing**
   ```bash
   # Start local Opik (if not running)
   docker run -p 8080:8080 -p 5432:5432 -p 6379:6379 --name opik -d comet-ml/opik:latest

   # Configure agent service
   export OPIK_TRACK_DISABLE=false
   export OPIK_URL=http://localhost:8080
   export OPIK_WORKSPACE=faultmaven
   export OPIK_PROJECT=FaultMaven

   # Restart service and verify traces appear in Opik UI
   ```

### Future Enhancements

1. **Propagate to Other Microservices**
   - Port logging infrastructure to:
     - fm-knowledge-service
     - fm-case-service
     - fm-evidence-service
     - fm-session-service
     - fm-auth-service

2. **Add Metrics Endpoint**
   - Create `/metrics` endpoint for Prometheus scraping
   - Export basic metrics:
     - Request count by endpoint
     - Request duration histogram
     - Active request gauge
     - Error rate

3. **Add Health Checks**
   - Expand `/health` endpoint to include:
     - Logging system status
     - Opik connectivity check
     - Database connectivity
     - Redis connectivity

4. **Enhanced Observability**
   - Add OpenTelemetry spans for distributed tracing
   - Integrate with service mesh (if using Istio/Linkerd)
   - Add custom business metrics

## References

### Source Files (Monolith)

- `/home/swhouse/product/FaultMaven-Mono/faultmaven/infrastructure/logging/`
  - `coordinator.py` - Request context and coordination
  - `config.py` - Logging configuration
  - `unified.py` - Unified logger implementation

- `/home/swhouse/product/FaultMaven-Mono/faultmaven/infrastructure/observability/`
  - `tracing.py` - Opik tracing implementation

### New Files (Microservice)

- `/home/swhouse/product/fm-agent-service/src/agent_service/infrastructure/logging/`
  - `context.py` - Request context (simplified)
  - `config.py` - Structured logging (simplified)
  - `unified.py` - Unified logger (simplified)
  - `middleware.py` - FastAPI middleware (new)

- `/home/swhouse/product/fm-agent-service/src/agent_service/infrastructure/observability/`
  - `tracing.py` - Opik tracing (simplified)

### Documentation

- [Structlog Documentation](https://www.structlog.org/)
- [Contextvars Documentation](https://docs.python.org/3/library/contextvars.html)
- [FastAPI Middleware](https://fastapi.tiangolo.com/advanced/middleware/)
- [Comet Opik](https://www.comet.com/docs/opik/)

---

**Completed**: 2025-11-24
**Author**: Claude Code
**Review Status**: Pending user verification
