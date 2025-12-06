# FM Agent Service

> **Part of [FaultMaven](https://github.com/FaultMaven/faultmaven)** —
> The AI-Powered Troubleshooting Copilot

An AI copilot that helps you diagnose and resolve technical issues through clear, step-by-step guidance.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/faultmaven/fm-agent-service)

## Overview

The Agent Service is the core AI reasoning engine of FaultMaven. It orchestrates multi-step diagnostic conversations, integrates with knowledge bases through RAG, and coordinates with other microservices (Case, Evidence, Knowledge) to guide users through systematic troubleshooting workflows.

## API Endpoints

See `src/agent_service/api/routes/` for implementation details.

## Local Development

### Prerequisites

- Python 3.11+
- Poetry
- Docker & Docker Compose

### Setup

```bash
# Install dependencies
poetry install

# Start infrastructure
docker-compose up -d redis

# Run migrations (if applicable)


# Start service
poetry run uvicorn src.agent_service.main:app --reload
```

### Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test types
poetry run pytest tests/unit/
poetry run pytest tests/integration/
poetry run pytest tests/contract/
```

## Docker Deployment

```bash
# Build image
docker-compose build

# Run full stack
docker-compose up

# Access service
curl http://localhost:8006/health
```

## Environment Variables

See `.env.example` for required configuration.

### LLM Provider Configuration

The agent service supports 6 LLM providers with automatic fallback:

- **OpenAI** (GPT-4, GPT-4o, etc.)
- **Anthropic** (Claude 3.5 Sonnet, etc.)
- **Groq** (Llama 3.3, Mixtral - FREE tier available)
- **Gemini** (Google's Gemini models)
- **Fireworks** (Open source models)
- **OpenRouter** (Multi-provider aggregator)

**Basic Configuration:**

```bash
# Configure one or more providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
```

**Task-Specific Provider Routing (Optional):**

For cost optimization and performance, you can assign specific providers to different task types:

```bash
# Main diagnostic conversations
CHAT_PROVIDER=openai
CHAT_MODEL=gpt-4o

# Visual evidence processing (future)
MULTIMODAL_PROVIDER=gemini
MULTIMODAL_MODEL=gemini-1.5-pro

# Knowledge base RAG queries (future)
SYNTHESIS_PROVIDER=groq
SYNTHESIS_MODEL=llama-3.1-8b-instant  # Fast and FREE!

# Disable fallback (fail instead of trying next provider)
STRICT_PROVIDER_MODE=false
```

**Task Types:**

- `chat` - Main diagnostic conversations (currently implemented)
- `multimodal` - Visual evidence processing (future: image analysis)
- `synthesis` - Knowledge base RAG queries (future: document Q&A)

If task-specific providers are not configured, the service uses automatic fallback across all available providers.

## Database Schema



## Events Published

See `SERVICE_EXTRACTION_MAP.md` for event specifications.

## Events Consumed

See `SERVICE_EXTRACTION_MAP.md` for event subscriptions.

## Contributing

See our [Contributing Guide](https://github.com/FaultMaven/.github/blob/main/CONTRIBUTING.md) for detailed guidelines.

## Support

- **Discussions:** [GitHub Discussions](https://github.com/FaultMaven/faultmaven/discussions)
- **Issues:** [GitHub Issues](https://github.com/FaultMaven/fm-agent-service/issues)

## Related Projects

- **[faultmaven](https://github.com/FaultMaven/faultmaven)** - Main repository and documentation
- **[faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy)** - Deployment configurations
- **[fm-case-service](https://github.com/FaultMaven/fm-case-service)** - Case management service
- **[fm-knowledge-service](https://github.com/FaultMaven/fm-knowledge-service)** - Knowledge base service
- **[fm-evidence-service](https://github.com/FaultMaven/fm-evidence-service)** - Evidence management service

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
