#!/usr/bin/env python3
"""Auto-generate dynamic sections of README.md from OpenAPI specification.

This script uses a template-based approach:
- README_TEMPLATE.md contains human-editable prose (owned by developers)
- This script injects dynamic API data into placeholders (owned by automation)

Placeholders in template:
- <!-- GENERATED:BADGE_LINE --> : Auto-update timestamp and endpoint count
- <!-- GENERATED:API_TABLE --> : Endpoint table from OpenAPI spec
- <!-- GENERATED:RESPONSE_CODES --> : Common HTTP response codes
- <!-- GENERATED:STATS --> : Documentation statistics footer

Usage:
  Copy this file to scripts/generate_readme.py in your service.
  Create README_TEMPLATE.md with placeholders.
  The workflow will inject dynamic content on each run.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, Any


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


def load_template() -> str:
    """Load README template file"""
    template_path = Path(__file__).parent.parent / "README_TEMPLATE.md"

    if not template_path.exists():
        raise FileNotFoundError(
            f"README template not found at {template_path}. "
            "Create README_TEMPLATE.md with placeholders."
        )

    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_endpoint_table(spec: Dict[str, Any]) -> str:
    """Generate markdown table of endpoints"""
    endpoints = []

    for path, methods in spec.get('paths', {}).items():
        for method, details in methods.items():
            if method.lower() in ['get', 'post', 'put', 'delete', 'patch']:
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

    section = "## Common Response Codes\n\n"

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


def generate_badge_line(total_endpoints: int, timestamp: str) -> str:
    """Generate the auto-update badge line"""
    return f"> **Auto-generated API docs** | Last updated: **{timestamp}** | Endpoints: **{total_endpoints}**"


def generate_stats_footer(total_endpoints: int, timestamp: str, version: str) -> str:
    """Generate documentation statistics footer"""
    return f"""**Documentation Statistics**
- Total endpoints: {total_endpoints}
- Last generated: {timestamp}
- OpenAPI spec version: {version}
- Generator: scripts/generate_readme.py
- Template: README_TEMPLATE.md

*API sections are automatically updated on every commit. Prose sections are human-editable.*"""


def inject_content(template: str, replacements: Dict[str, str]) -> str:
    """Inject generated content into template placeholders"""
    result = template

    for placeholder, content in replacements.items():
        # Match <!-- GENERATED:PLACEHOLDER --> pattern
        pattern = rf'<!-- GENERATED:{placeholder} -->'
        result = re.sub(pattern, content, result)

    return result


def main():
    """Generate README.md by injecting dynamic content into template"""
    print("Generating README.md from template + OpenAPI specification...")

    # Load inputs
    spec = load_openapi_spec()
    template = load_template()

    # Extract metadata
    info = spec.get('info', {})
    version = info.get('version', '1.0.0')

    # Generate dynamic content
    total_endpoints = count_endpoints(spec)
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    replacements = {
        'BADGE_LINE': generate_badge_line(total_endpoints, timestamp),
        'API_TABLE': generate_endpoint_table(spec),
        'RESPONSE_CODES': generate_response_codes_section(spec),
        'STATS': generate_stats_footer(total_endpoints, timestamp, version),
    }

    # Inject into template
    readme_content = inject_content(template, replacements)

    # Write README
    readme_path = Path(__file__).parent.parent / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)

    print(f"README.md generated successfully")
    print(f"   Location: {readme_path}")
    print(f"   Total endpoints documented: {total_endpoints}")
    print(f"   Timestamp: {timestamp}")
    print(f"   Template: README_TEMPLATE.md")


if __name__ == "__main__":
    main()
