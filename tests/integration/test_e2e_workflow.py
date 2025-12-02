"""End-to-end integration tests for FaultMaven workflow.

Tests the complete flow:
1. User authentication
2. Case creation
3. Agent chat
4. Evidence addition
5. Case closure

Note: These tests require all services to be running.
"""

import asyncio
import os
import pytest
from typing import Optional

# Test configuration
AUTH_SERVICE_URL = os.getenv("FM_AUTH_SERVICE_URL", "http://localhost:8001")
CASE_SERVICE_URL = os.getenv("FM_CASE_SERVICE_URL", "http://localhost:8000")
AGENT_SERVICE_URL = os.getenv("FM_AGENT_SERVICE_URL", "http://localhost:8000")

# Test user
TEST_USER = {
    "username": "test_user_qa",
    "email": "qa@faultmaven.test",
    "display_name": "QA Test User"
}


class TestE2EWorkflow:
    """End-to-end workflow tests."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test environment."""
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.case_id: Optional[str] = None

    async def test_01_user_registration(self):
        """Test user registration flow."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{AUTH_SERVICE_URL}/api/v1/auth/dev-register",
                json=TEST_USER
            )

            assert response.status == 201, f"Registration failed: {await response.text()}"

            data = await response.json()
            assert "access_token" in data
            assert "user" in data
            assert data["user"]["username"] == TEST_USER["username"]

            self.access_token = data["access_token"]
            self.user_id = data["user"]["user_id"]

            print(f"✅ User registered: {self.user_id}")

    async def test_02_user_login(self):
        """Test user login flow."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{AUTH_SERVICE_URL}/api/v1/auth/dev-login",
                json={"username": TEST_USER["username"]}
            )

            assert response.status == 200, f"Login failed: {await response.text()}"

            data = await response.json()
            assert "access_token" in data

            self.access_token = data["access_token"]
            self.user_id = data["user"]["user_id"]

            print(f"✅ User logged in: {self.user_id}")

    async def test_03_create_case(self):
        """Test case creation."""
        import aiohttp

        if not self.access_token:
            pytest.skip("No access token - run login test first")

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{CASE_SERVICE_URL}/api/v1/cases",
                headers={"X-User-ID": self.user_id},
                json={
                    "title": "QA Test: Redis Connection Timeouts",
                    "description": "Testing case creation for QA",
                    "severity": "high"
                }
            )

            assert response.status == 201, f"Case creation failed: {await response.text()}"

            data = await response.json()
            assert "case_id" in data
            assert data["title"] == "QA Test: Redis Connection Timeouts"

            self.case_id = data["case_id"]

            print(f"✅ Case created: {self.case_id}")

    async def test_04_agent_chat(self):
        """Test agent chat endpoint."""
        import aiohttp

        if not self.case_id:
            pytest.skip("No case - run case creation test first")

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{AGENT_SERVICE_URL}/api/v1/agent/chat/{self.case_id}",
                headers={"X-User-ID": self.user_id},
                json={
                    "message": "I'm experiencing Redis connection timeouts. Can you help?"
                }
            )

            # May fail if LLM not configured - that's OK for testing structure
            if response.status == 200:
                data = await response.json()
                assert "agent_response" in data
                assert "turn_number" in data
                print(f"✅ Agent chat successful: turn {data['turn_number']}")
            elif response.status == 500:
                error = await response.text()
                if "OPENAI_API_KEY" in error or "not available" in error:
                    print("⚠️  Agent chat skipped: LLM not configured (expected in test environment)")
                    pytest.skip("LLM not configured")
                else:
                    pytest.fail(f"Agent chat failed: {error}")
            else:
                pytest.fail(f"Unexpected status {response.status}: {await response.text()}")

    async def test_05_add_evidence(self):
        """Test adding evidence to case."""
        import aiohttp

        if not self.case_id:
            pytest.skip("No case - run case creation test first")

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{CASE_SERVICE_URL}/api/v1/cases/{self.case_id}/data",
                headers={"X-User-ID": self.user_id},
                json={
                    "content": "ERROR: Connection timeout to redis://prod:6379",
                    "source": "application logs",
                    "category": "error_message"
                }
            )

            assert response.status == 200, f"Add evidence failed: {await response.text()}"

            print(f"✅ Evidence added to case {self.case_id}")

    async def test_06_close_case(self):
        """Test closing a case."""
        import aiohttp

        if not self.case_id:
            pytest.skip("No case - run case creation test first")

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"{CASE_SERVICE_URL}/api/v1/cases/{self.case_id}/close",
                headers={"X-User-ID": self.user_id},
                json={
                    "reason": "QA test completed",
                    "resolution_notes": "Test case closed successfully"
                }
            )

            assert response.status == 200, f"Close case failed: {await response.text()}"

            data = await response.json()
            assert data["status"] == "closed"

            print(f"✅ Case closed: {self.case_id}")


@pytest.mark.asyncio
async def test_full_e2e_workflow():
    """Run full end-to-end workflow test."""
    test_instance = TestE2EWorkflow()
    await test_instance.setup()

    try:
        # Run tests in sequence
        await test_instance.test_01_user_registration()
        await test_instance.test_03_create_case()
        await test_instance.test_04_agent_chat()
        await test_instance.test_05_add_evidence()
        await test_instance.test_06_close_case()

        print("\n✅ Full E2E workflow test PASSED")

    except Exception as e:
        print(f"\n❌ E2E workflow test FAILED: {e}")
        raise


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_full_e2e_workflow())
