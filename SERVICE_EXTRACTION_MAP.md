# Agent Service Extraction Map

## Source Files (from FaultMaven monolith)

| Monolith File | Destination | Action |
|---------------|-------------|--------|
| faultmaven/services/agentic/orchestration/agent_service.py | src/agent_service/domain/services/orchestrator.py | Extract agent orchestration |
| faultmaven/services/agentic/engines/*.py | src/agent_service/domain/engines/ | Extract processing engines |
| faultmaven/services/agentic/management/*.py | src/agent_service/domain/management/ | Extract state/tool management |
| faultmaven/services/agentic/safety/*.py | src/agent_service/domain/safety/ | Extract safety layers |
| faultmaven/core/agent/agent.py | src/agent_service/domain/agent.py | Extract LangGraph agent |
| faultmaven/tools/*.py | src/agent_service/domain/tools/ | Extract agent tools |
| faultmaven/api/v1/routes/agent.py | src/agent_service/api/routes/agent.py | Extract API endpoints |

## Database Tables (exclusive ownership)

| Table Name | Source Schema | Action |
|------------|---------------|--------|
| agent_tool_calls | 001_initial_hybrid_schema.sql | Optional - audit logging |

## Events Published

| Event Name | AsyncAPI Schema | Trigger |
|------------|-----------------|---------|
| agent.query.received.v1 | contracts/asyncapi/agent-events.yaml | POST /v1/agent/chat |
| agent.tool.executed.v1 | contracts/asyncapi/agent-events.yaml | Tool execution |
| agent.response.generated.v1 | contracts/asyncapi/agent-events.yaml | Response synthesis complete |

## Events Consumed

| Event Name | Source Service | Action |
|------------|----------------|--------|
| case.created.v1 | Case Service | Initialize agent for new case |
| session.created.v1 | Session Service | Set up agent context |

## API Dependencies

| Dependency | Purpose | Fallback Strategy |
|------------|---------|-------------------|
| Auth Service | Validate user tokens | Circuit breaker (deny if down) |
| Case Service | Get case context | Circuit breaker (return 503) |
| Session Service | Get session state | Circuit breaker (return 503) |
| Knowledge Service | Search knowledge base | Circuit breaker (skip KB results) |
| Investigation Service | Get investigation state | Circuit breaker (degraded mode) |
| Evidence Service | Retrieve evidence | Circuit breaker (degraded mode) |

## External Dependencies

| Dependency | Purpose | Fallback Strategy |
|------------|---------|-------------------|
| LLM Providers | AI reasoning | Multi-provider fallback chain |
| Presidio | PII redaction | Local regex fallback |
| Opik | LLM observability | Continue without tracing |

## Migration Checklist

- [ ] Extract domain models (AgentState, ToolCall, Response)
- [ ] Extract business logic (7-component agentic framework)
- [ ] Extract API routes (chat, tool execution)
- [ ] Extract LLM integration (multi-provider routing)
- [ ] Implement event publishing (outbox pattern)
- [ ] Implement event consumption (inbox pattern)
- [ ] Add circuit breakers for all dependencies
- [ ] Implement multi-provider LLM fallback
- [ ] Write unit tests (80%+ coverage)
- [ ] Write integration tests (LLM + dependencies)
- [ ] Write contract tests (provider verification)
