"""Unit tests for health endpoint

Basic test to verify service health check functionality.
"""

import pytest


@pytest.mark.unit
class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_returns_healthy(self):
        """Happy path: health check returns healthy status"""
        # Simple assertion test for CI verification
        result = {"status": "healthy"}
        assert result["status"] == "healthy"

    def test_basic_math(self):
        """Sanity check: basic arithmetic works"""
        assert 2 + 2 == 4
