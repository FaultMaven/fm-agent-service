#!/usr/bin/env python3
"""Auto-generate README.md from OpenAPI specification.

This script reads the OpenAPI spec generated from FastAPI and creates
a comprehensive README with endpoint documentation, examples, and statistics.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Any


def load_openapi_spec() -> Dict[str, Any]:
    """Load OpenAPI spec from docs/api/openapi.json"""
    spec_path = Path(__file__).parent.parent / "docs" / "api" / "openapi.json"

    if not spec_path.exists():
        raise FileNotFoundError(
            f"OpenAPI spec not found at {spec_path}. "
            "Run the app to generate it first."
        )

    with open(spec_path, 'r') as f:
        return json.load(f)


def generate_endpoint_table(spec: Dict[str, Any]) -> str:
    """Generate markdown table of endpoints"""
    endpoints = []

    for path, methods in spec.get('paths', {}).items():
        for method, details in methods.items():
            if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
                # Extract summary or use path as fallback
                summary = details.get('summary', path)

                endpoints.append({
                    'method': method.upper(),
                    'path': path,
                    'summary': summary
                })

    # Sort endpoints: health first, then by path
    def sort_key(e):
        if e['path'] == '/health':
            return (0, '')
        return (1, e['path'])

    endpoints.sort(key=sort_key)

    # Build markdown table
    table = "| Method | Endpoint | Description |\n"
    table += "|--------|----------|-------------|\n"

    for endpoint in endpoints:
        table += f"| {endpoint['method']} | `{endpoint['path']}` | {endpoint['summary']} |\n"

    return table


def extract_response_codes(spec: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Extract unique response codes and their descriptions across all endpoints"""
    response_info = {}

    for path, methods in spec.get('paths', {}).items():
        for method, details in methods.items():
            if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
                for code, response_details in details.get('responses', {}).items():
                    desc = response_details.get('description', 'No description')
                    if code not in response_info:
                        response_info[code] = set()
                    response_info[code].add(desc)

    return response_info


def generate_response_codes_section(spec: Dict[str, Any]) -> str:
    """Generate response codes documentation"""
    response_info = extract_response_codes(spec)

    if not response_info:
        return ""

    section = "\n## Common Response Codes\n\n"

    # Sort codes numerically
    for code in sorted(response_info.keys(), key=lambda x: int(x)):
        descriptions = list(response_info[code])
        section += f"- **{code}**: {descriptions[0]}\n"

    return section


def count_endpoints(spec: Dict[str, Any]) -> int:
    """Count total number of endpoints"""
    count = 0
    for path, methods in spec.get('paths', {}).items():
        for method in methods.keys():
            if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
                count += 1
    return count


def main():
    """Generate README.md from OpenAPI specification"""
    print("🚀 Generating README.md from OpenAPI specification...")

    # Load spec
    spec = load_openapi_spec()

    # Extract metadata
    info = spec.get('info', {})
    title = info.get('title', 'Agent Service')
    version = info.get('version', '2.0.0')
    description = info.get('description', 'FaultMaven AI Agent Orchestration Microservice')

    # Generate sections
    endpoint_table = generate_endpoint_table(spec)
    response_codes = generate_response_codes_section(spec)
    total_endpoints = count_endpoints(spec)
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    # Build README content
    readme_content = f"""# {title}

> **🤖 This README is auto-generated** from code on every commit.
> Last updated: **{timestamp}** | Total endpoints: **{total_endpoints}**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/faultmaven/fm-agent-service)
[![Auto-Docs](https://img.shields.io/badge/docs-auto--generated-success.svg)](.github/workflows/generate-docs.yml)

## Overview

**{description}** - Part of the FaultMaven troubleshooting platform.

The Agent Service is the core AI reasoning engine of FaultMaven. It orchestrates multi-step diagnostic conversations using a **milestone-based investigation engine** that breaks down complex troubleshooting into structured phases. The service integrates with knowledge bases through RAG, coordinates with other microservices (Case, Evidence, Knowledge), and provides intelligent, context-aware guidance.

**Key Features:**
- **Milestone-Based Investigation**: Structured diagnostic workflow (Understand → Hypothesize → Test → Resolve)
- **Multi-Provider LLM Support**: OpenAI, Anthropic, Groq, Gemini, Fireworks, OpenRouter with automatic fallback
- **RAG Integration**: Knowledge base search and synthesis (coming soon)
- **Stateless Design**: Each request contains full context (compatible with API Gateway session management)
- **Evidence Coordination**: Integrates with fm-evidence-service for artifact storage
- **Case Management**: Links investigations to persistent cases via fm-case-service
- **Provider Flexibility**: Task-specific provider routing with cost optimization

## Quick Start

### Using Docker (Recommended)

```bash
docker run -p 8006:8006 \\
  -e OPENAI_API_KEY=sk-... \\
  -e ANTHROPIC_API_KEY=sk-ant-... \\
  faultmaven/fm-agent-service:latest
```

The service will be available at `http://localhost:8006`.

### Using Docker Compose

See [faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy) for complete deployment with all FaultMaven services.

### Development Setup

```bash
# Clone repository
git clone https://github.com/FaultMaven/fm-agent-service.git
cd fm-agent-service

# Install dependencies (using Poetry)
poetry install

# Set up environment
cp .env.example .env
# Edit .env and add your API keys

# Run service
poetry run uvicorn agent_service.main:app --reload --port 8006
```

## API Endpoints

{endpoint_table}

**OpenAPI Documentation**: See [docs/api/openapi.json](docs/api/openapi.json) or [docs/api/openapi.yaml](docs/api/openapi.yaml) for complete API specification.
{response_codes}

## Configuration

Configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `fm-agent-service` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `PORT` | Service port | `8006` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `*` |

### LLM Provider Configuration

The agent service supports **6 LLM providers** with automatic fallback:

**Supported Providers:**
- **OpenAI** (GPT-4, GPT-4o, etc.)
- **Anthropic** (Claude 3.5 Sonnet, etc.)
- **Groq** (Llama 3.3, Mixtral - FREE tier available)
- **Gemini** (Google's Gemini models)
- **Fireworks** (Open source models)
- **OpenRouter** (Multi-provider aggregator)

**Basic Configuration:**

```env
# Configure one or more providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...
FIREWORKS_API_KEY=...
OPENROUTER_API_KEY=...
```

**Task-Specific Provider Routing (Optional):**

For cost optimization and performance, assign specific providers to different task types:

```env
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

## Milestone-Based Investigation Engine

The Agent Service uses a **structured investigation workflow** based on troubleshooting best practices:

### Investigation Phases

1. **Understand** - Gather context and clarify the problem
   - What's happening? When did it start?
   - What changed recently?
   - Collect initial evidence

2. **Hypothesize** - Develop theories about root causes
   - What could cause this?
   - What are the most likely explanations?
   - Prioritize hypotheses

3. **Test** - Validate hypotheses with evidence
   - Design diagnostic tests
   - Execute and collect results
   - Narrow down possibilities

4. **Resolve** - Implement and verify the fix
   - Apply solution
   - Verify resolution
   - Document learnings

### Stateless Context Management

Each agent request includes full conversation history and context:

```json
{{
  "session_id": "session_xyz789",
  "user_id": "user_123",
  "messages": [
    {{"role": "user", "content": "My API is returning 500 errors"}},
    {{"role": "assistant", "content": "Let's investigate. What endpoint is failing?"}}
  ],
  "current_milestone": "understand",
  "context": {{
    "problem_statement": "API 500 errors",
    "affected_systems": ["api-gateway", "database"]
  }}
}}
```

**Benefits:**
- No server-side session storage required
- Horizontal scaling without sticky sessions
- API Gateway handles persistence via fm-session-service

## Authorization

This service uses **trusted header authentication** from the FaultMaven API Gateway:

**Required Headers:**

- `X-User-ID` (required): Identifies the user making the request

**Optional Headers:**

- `X-User-Email`: User's email address
- `X-User-Roles`: User's roles (comma-separated)

**Security Model:**

- ✅ Service trusts headers set by upstream gateway
- ✅ All requests validated for X-User-ID presence
- ⚠️ Never expose this service directly to the internet

**Important**: This service should run behind the [fm-api-gateway](https://github.com/FaultMaven/faultmaven) which handles authentication and sets these headers.

## Architecture

```
┌─────────────────────────┐
│  FaultMaven API Gateway │  Handles authentication (Clerk)
│  (Port 8000)            │  Sets X-User-ID header
└───────────┬─────────────┘
            │ Trusted headers (X-User-ID)
            ↓
┌─────────────────────────┐
│  fm-agent-service       │  Milestone-based investigation
│  (Port 8006)            │  Multi-provider LLM orchestration
└─────┬─────────┬─────────┘
      │         │
      │         └──────────→ LLM Providers (OpenAI, Anthropic, Groq, etc.)
      │
      ↓
┌─────────────────────────┐
│  Related Services       │
│  - fm-case-service      │  Case management
│  - fm-evidence-service  │  Evidence storage
│  - fm-knowledge-service │  RAG knowledge base
└─────────────────────────┘
```

**Related Services:**
- fm-api-gateway (8000) - Authentication and routing
- fm-session-service (8001) - Session persistence
- fm-case-service (8003) - Case management
- fm-evidence-service (8004) - Evidence artifacts
- fm-knowledge-service (8002) - Knowledge base (future RAG integration)

**Storage Details:**

- **State**: Stateless (context in each request)
- **Session Persistence**: Handled by API Gateway → fm-session-service
- **Case Data**: Coordinated with fm-case-service
- **Evidence**: Coordinated with fm-evidence-service

## Testing

```bash
# Install dev dependencies
poetry install

# Run all tests
poetry run pytest

# Run with coverage report
poetry run pytest --cov=src --cov-report=html --cov-report=term

# Run specific test types
poetry run pytest tests/unit/ -v
poetry run pytest tests/integration/ -v
poetry run pytest tests/contract/ -v

# Run with debug output
poetry run pytest -vv -s
```

**Test Coverage Goals:**

- Unit tests: Core business logic (InvestigationEngine, MilestoneManager)
- Integration tests: LLM provider integration and fallback
- Contract tests: API contract validation
- Target coverage: >80%

## Development Workflow

```bash
# Format code with black
poetry run black src/ tests/

# Lint with flake8
poetry run flake8 src/ tests/

# Type check with mypy
poetry run mypy src/

# Run all quality checks
poetry run black src/ tests/ && poetry run flake8 src/ tests/ && poetry run mypy src/ && poetry run pytest
```

## Related Projects

- [faultmaven](https://github.com/FaultMaven/faultmaven) - Main backend with API Gateway and orchestration
- [faultmaven-copilot](https://github.com/FaultMaven/faultmaven-copilot) - Browser extension UI for troubleshooting
- [faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy) - Docker Compose deployment configurations
- [fm-session-service](https://github.com/FaultMaven/fm-session-service) - Investigation session management
- [fm-case-service](https://github.com/FaultMaven/fm-case-service) - Case management
- [fm-knowledge-service](https://github.com/FaultMaven/fm-knowledge-service) - Knowledge base and recommendations
- [fm-evidence-service](https://github.com/FaultMaven/fm-evidence-service) - Evidence artifact storage

## CI/CD

This repository uses **GitHub Actions** for automated documentation generation:

**Trigger**: Every push to `main` or `develop` branches (when API-related files change)

**Process**:
1. Generate OpenAPI spec (JSON + YAML)
2. Validate documentation completeness (fails if endpoints lack comprehensive descriptions)
3. Auto-generate this README from code
4. Create pull request with documentation updates

See [.github/workflows/generate-docs.yml](.github/workflows/generate-docs.yml) for implementation details.

**Documentation Guarantee**: This README is always in sync with the actual code. Any endpoint changes automatically trigger documentation updates.

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks (`poetry run pytest && poetry run black . && poetry run flake8`)
5. Commit with clear messages (`git commit -m 'feat: Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

**Code Style**: Black formatting, flake8 linting, mypy type checking
**Commit Convention**: Conventional Commits (feat/fix/docs/refactor/test/chore)

---

**📊 Documentation Statistics**
- Total endpoints: {total_endpoints}
- Last generated: {timestamp}
- OpenAPI spec version: {version}
- Generator: scripts/generate_readme.py
- CI/CD: GitHub Actions

*This README is automatically updated on every commit to ensure zero documentation drift.*
"""

    # Write README
    readme_path = Path(__file__).parent.parent / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    print(f"✅ README.md generated successfully")
    print(f"   Location: {readme_path}")
    print(f"   Total endpoints documented: {total_endpoints}")
    print(f"   Timestamp: {timestamp}")


if __name__ == "__main__":
    main()
