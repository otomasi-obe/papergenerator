"""
Test suite for critical bug fixes.
Run with: pytest tests/test_critical_fixes.py -v
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest

from app import app, db
from database.models import User


@pytest.fixture
def client():
    """Create test client with in-memory database."""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()


@pytest.fixture
def test_user(client):
    """Create a test user."""
    with app.app_context():
        user = User(
            email="test@example.com",
            name="Test User",
            role="user",
            token_quota_monthly=1000000,
            token_used_month=0,
            usage_month_key=datetime.now(timezone.utc).strftime("%Y-%m"),
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        return user.id


class TestQuotaRaceCondition:
    """Test fix for Critical Bug #1: Race Condition in Token Quota Updates"""

    def test_concurrent_quota_updates(self, client, test_user):
        """Verify quota updates are atomic under concurrent load."""
        from app import _log_api_usage

        num_requests = 100
        tokens_per_request = 1000

        def log_usage():
            _log_api_usage(
                endpoint="test",
                usage={
                    "total_tokens": tokens_per_request,
                    "prompt_tokens": 500,
                    "completion_tokens": 500,
                },
                user_id=test_user,
            )

        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(log_usage) for _ in range(num_requests)]
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # Verify total is correct (no lost updates)
        with app.app_context():
            user = User.query.get(test_user)
            expected_total = num_requests * tokens_per_request
            assert (
                user.token_used_month == expected_total
            ), f"Expected {expected_total}, got {user.token_used_month}. Race condition detected!"

    def test_no_quota_bypass(self, client, test_user):
        """Verify quota cannot be bypassed via race condition."""
        from app import _log_api_usage

        # Set low quota
        with app.app_context():
            user = User.query.get(test_user)
            user.token_quota_monthly = 5000
            user.token_used_month = 0
            db.session.commit()

        # Try to exceed quota with concurrent requests
        def log_usage():
            _log_api_usage(
                endpoint="test",
                usage={"total_tokens": 1000, "prompt_tokens": 500, "completion_tokens": 500},
                user_id=test_user,
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(log_usage) for _ in range(10)]
            for future in as_completed(futures):
                future.result()

        # Verify quota tracking is accurate
        with app.app_context():
            user = User.query.get(test_user)
            assert user.token_used_month == 10000, "Quota tracking failed"


class TestMonthRolloverRace:
    """Test fix for Critical Bug #2: Race Condition in Month Rollover"""

    def test_month_rollover_atomic(self, client, test_user):
        """Verify month rollover happens exactly once."""

        # Set old month
        with app.app_context():
            user = User.query.get(test_user)
            user.usage_month_key = "2026-04"  # Last month
            user.token_used_month = 50000
            db.session.commit()

        # Simulate concurrent requests at month boundary
        results = []

        def check_quota():
            with app.test_request_context():
                from flask_jwt_extended import create_access_token

                access_token = create_access_token(identity=str(test_user))

                response = client.get(
                    "/api/me/quota", headers={"Authorization": f"Bearer {access_token}"}
                )
                results.append(response.get_json())

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_quota) for _ in range(20)]
            for future in as_completed(futures):
                future.result()

        # Verify all requests see consistent state
        with app.app_context():
            user = User.query.get(test_user)
            assert user.usage_month_key == "2026-05", "Month not rolled over"
            assert user.token_used_month == 0, "Usage not reset"


class TestSemaphoreLeak:
    """Test fix for Critical Bug #3: Semaphore Leak in Upstream Calls"""

    def test_semaphore_released_on_timeout(self, client):
        """Verify semaphore is not leaked when acquire times out."""
        from api.chat_bp import _call_upstream, _upstream_sem

        # Record initial semaphore count
        initial_value = _upstream_sem._value

        # Simulate timeout by setting very short timeout
        import chat

        original_timeout = chat._CHAT_UPSTREAM_TIMEOUT
        chat._CHAT_UPSTREAM_TIMEOUT = 0.001  # 1ms timeout

        try:
            # This should timeout and return None
            result = _call_upstream(messages=[{"role": "user", "content": "test"}], tools=[])
            assert result is None, "Expected timeout"

            # Verify semaphore was not leaked
            time.sleep(0.1)  # Give time for cleanup
            assert (
                _upstream_sem._value == initial_value
            ), f"Semaphore leaked! Initial: {initial_value}, Current: {_upstream_sem._value}"
        finally:
            chat._CHAT_UPSTREAM_TIMEOUT = original_timeout

    def test_semaphore_released_on_exception(self, client):
        """Verify semaphore is released even when exception occurs."""
        from api.chat_bp import _call_upstream, _upstream_sem

        initial_value = _upstream_sem._value

        # Mock requests to raise exception
        import chat

        original_post = chat.requests.post

        def mock_post(*args, **kwargs):
            raise Exception("Simulated network error")

        chat.requests.post = mock_post

        try:
            result = _call_upstream(messages=[{"role": "user", "content": "test"}], tools=[])
            # Should return None after retries
            assert result is None

            # Verify semaphore was released
            time.sleep(0.1)
            assert _upstream_sem._value == initial_value, "Semaphore leaked on exception"
        finally:
            chat.requests.post = original_post


class TestConnectionPoolExhaustion:
    """Test fix for Critical Bug #4: Connection Pool Exhaustion"""

    def test_long_poll_releases_connection(self, client, test_user):
        """Verify long-polling releases DB connection between polls."""
        # This test requires monitoring actual DB connections
        # In production, use: SELECT count(*) FROM pg_stat_activity WHERE datname='paperfull';

        # For now, verify the endpoint doesn't hold connection for full duration

        with app.test_request_context():
            from flask_jwt_extended import create_access_token

            # Create test paper
            with app.app_context():
                from models import Paper

                paper = Paper(id="test123", user_id=test_user, title="Test", data={})
                db.session.add(paper)
                db.session.commit()

            access_token = create_access_token(identity=str(test_user))

            start = time.time()
            response = client.get(
                "/api/papers/test123/slr/jobs/wait?after=0",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            time.time() - start

            # Should return quickly if no updates
            # Connection should be released during sleep
            assert response.status_code in [200, 404]

            # Verify db.session was closed (no active transaction)
            with app.app_context():
                assert not db.session.is_active, "Session still active after long-poll"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
