"""
Integration tests for API rate limiting functionality.

Tests verify that Flask-Limiter rate limiting is correctly enforced across
all rate-limited endpoints, with proper error responses, reset behavior,
and multi-user isolation.

Rate-limited endpoints:
- /api/health: EXEMPT (no limit)
- auth_bp (login, register): 10/min
- /api/generate: 20/min
- /api/generate-full: 10/min
- /api/upload-pdfs: 20/min
- /api/upload-image: 30/min
"""
import time

import pytest


@pytest.fixture(scope='module')
def rate_limiting_app():
    """Flask app with rate limiting ENABLED for testing."""
    from app import app as flask_app
    from database.models import db

    original_config = flask_app.config.copy()

    flask_app.config.update({
        'TESTING': True,
        'RATELIMIT_ENABLED': True,
        'RATELIMIT_STORAGE_URI': 'memory://',
        'WTF_CSRF_ENABLED': False,
        'JWT_COOKIE_CSRF_PROTECT': False,
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

    flask_app.config.update(original_config)


@pytest.fixture
def rate_limiting_client(rate_limiting_app):
    """Test client with rate limiting enabled."""
    return rate_limiting_app.test_client()


@pytest.fixture
def rl_test_user(rate_limiting_app):
    """Create test user for rate limiting tests."""
    from database.models import User, db

    with rate_limiting_app.app_context():
        user = User(
            name='RateLimit Test User',
            email='ratelimit@example.com',
            role='user'
        )
        user.set_password('TestPassword123!')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        yield user

        user = db.session.get(User, user_id)
        if user:
            db.session.delete(user)
            db.session.commit()


@pytest.fixture
def rl_auth_token(rate_limiting_app, rl_test_user):
    """Generate JWT token for rate limiting test user."""
    from flask_jwt_extended import create_access_token

    with rate_limiting_app.app_context():
        token = create_access_token(identity=str(rl_test_user.id))
        return token


@pytest.fixture
def rl_auth_headers(rl_auth_token):
    """Authorization headers for rate limiting tests."""
    return {
        'Authorization': f'Bearer {rl_auth_token}'
    }


@pytest.fixture(autouse=True)
def reset_rate_limits(rate_limiting_app):
    """Reset rate limit storage between tests to ensure isolation."""
    yield
    try:
        from app import limiter
        limiter.reset()
    except (ImportError, AttributeError) as e:
        # Limiter may not be available in all test contexts
        import logging
        logging.getLogger(__name__).debug(f"Could not reset rate limiter: {e}")


def make_requests(client, method, endpoint, count, headers=None, json_data=None):
    """Helper: make N requests to an endpoint and return responses."""
    responses = []
    for i in range(count):
        if method.upper() == 'GET':
            resp = client.get(endpoint, headers=headers)
        elif method.upper() == 'POST':
            resp = client.post(endpoint, headers=headers, json=json_data or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        responses.append(resp)
    return responses


def assert_rate_limit_error(response):
    """Helper: verify response is a proper rate limit error."""
    assert response.status_code == 429, f"Expected 429, got {response.status_code}"
    data = response.get_json()
    assert data is not None, "Response should have JSON body"
    assert data.get('code') == 'RATE_LIMIT_EXCEEDED', f"Expected RATE_LIMIT_EXCEEDED, got {data.get('code')}"
    assert data.get('category') == 'RATE_LIMIT', f"Expected RATE_LIMIT category, got {data.get('category')}"


def get_retry_after(response):
    """Helper: extract retry_after from rate limit error response."""
    data = response.get_json()
    if data and 'details' in data and 'retry_after' in data['details']:
        return data['details']['retry_after']
    return None


class TestRateLimitEnforcement:
    """Test that rate limits are correctly enforced on endpoints."""

    def test_health_endpoint_exempt_from_rate_limit(self, rate_limiting_client):
        """Test /api/health is exempt from rate limiting."""
        responses = make_requests(rate_limiting_client, 'GET', '/api/health', 100)

        for resp in responses:
            assert resp.status_code == 200, f"Health check should never be rate limited, got {resp.status_code}"

    def test_generate_endpoint_enforces_20_per_minute(self, rate_limiting_client, rl_auth_headers):
        """Test /api/generate enforces 20 requests/minute limit."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 201, 202, 400, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 20, f"Expected 20 successful requests, got {success_count}"
        assert rate_limited_count == 1, f"Expected 1 rate limited request, got {rate_limited_count}"
        assert_rate_limit_error(responses[-1])

    def test_generate_full_endpoint_enforces_10_per_minute(self, rate_limiting_client, rl_auth_headers):
        """Test /api/generate-full enforces 10 requests/minute limit."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate-full',
            11,
            headers=rl_auth_headers,
            json_data={'title': 'test'}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 201, 202, 400, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 10, f"Expected 10 successful requests, got {success_count}"
        assert rate_limited_count == 1, f"Expected 1 rate limited request, got {rate_limited_count}"
        assert_rate_limit_error(responses[-1])

    def test_upload_pdfs_enforces_20_per_minute(self, rate_limiting_client, rl_auth_headers):
        """Test /api/upload-pdfs enforces 20 requests/minute limit."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/upload-pdfs',
            21,
            headers=rl_auth_headers,
            json_data={}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 201, 400, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 20, f"Expected 20 successful requests, got {success_count}"
        assert rate_limited_count == 1, f"Expected 1 rate limited request, got {rate_limited_count}"
        assert_rate_limit_error(responses[-1])

    def test_upload_image_enforces_30_per_minute(self, rate_limiting_client, rl_auth_headers):
        """Test /api/upload-image enforces 30 requests/minute limit."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/upload-image',
            31,
            headers=rl_auth_headers,
            json_data={}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 201, 400, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 30, f"Expected 30 successful requests, got {success_count}"
        assert rate_limited_count == 1, f"Expected 1 rate limited request, got {rate_limited_count}"
        assert_rate_limit_error(responses[-1])

    def test_auth_endpoints_enforce_10_per_minute(self, rate_limiting_client):
        """Test auth blueprint endpoints enforce 10 requests/minute limit."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/auth/login',
            11,
            json_data={'email': 'test@example.com', 'password': 'wrong'}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 400, 401, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 10, f"Expected 10 successful requests, got {success_count}"
        assert rate_limited_count == 1, f"Expected 1 rate limited request, got {rate_limited_count}"
        assert_rate_limit_error(responses[-1])


class TestRateLimitExceeded:
    """Test rate limit exceeded error responses."""

    def test_rate_limit_exceeded_returns_429(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit exceeded returns 429 status code."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        assert responses[-1].status_code == 429

    def test_rate_limit_error_includes_retry_after(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit error includes retry_after in response details."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        data = responses[-1].get_json()
        assert 'details' in data, "Error response should include details"
        assert 'retry_after' in data['details'], "Details should include retry_after"
        assert isinstance(data['details']['retry_after'], int), "retry_after should be integer"
        assert data['details']['retry_after'] > 0, "retry_after should be positive"

    def test_rate_limit_error_message_format(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit error has correct message format."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        data = responses[-1].get_json()
        assert 'message' in data, "Error should include message"
        assert isinstance(data['message'], str), "Message should be string"
        assert len(data['message']) > 0, "Message should not be empty"

    def test_rate_limit_error_code_is_correct(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit error has correct error code."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        data = responses[-1].get_json()
        assert data['code'] == 'RATE_LIMIT_EXCEEDED'
        assert data['category'] == 'RATE_LIMIT'


class TestRateLimitReset:
    """Test rate limit reset behavior after time window."""

    def test_rate_limit_resets_after_window(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit resets after 60 second window."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate-full',
            11,
            headers=rl_auth_headers,
            json_data={'title': 'test'}
        )

        assert responses[-1].status_code == 429, "Should be rate limited"

        time.sleep(61)

        response = rate_limiting_client.post(
            '/api/generate-full',
            headers=rl_auth_headers,
            json={'title': 'test after reset'}
        )

        assert response.status_code in [200, 201, 202, 400, 422], \
            f"Should succeed after reset, got {response.status_code}"

    def test_multiple_requests_within_limit_succeed(self, rate_limiting_client, rl_auth_headers):
        """Test multiple requests within limit all succeed."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            20,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        for i, resp in enumerate(responses):
            assert resp.status_code in [200, 201, 202, 400, 422], \
                f"Request {i+1}/20 should succeed, got {resp.status_code}"

    def test_requests_after_partial_usage_succeed(self, rate_limiting_client, rl_auth_headers):
        """Test requests succeed after partial rate limit usage."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            10,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        for resp in responses:
            assert resp.status_code in [200, 201, 202, 400, 422]

        more_responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            10,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        for resp in more_responses:
            assert resp.status_code in [200, 201, 202, 400, 422], \
                "Remaining requests within limit should succeed"


class TestRateLimitMultiUser:
    """Test rate limiting with multiple users/IPs."""

    def test_different_ips_have_separate_limits(self, rate_limiting_app, rl_auth_headers):
        """Test different IP addresses have independent rate limits."""
        client1 = rate_limiting_app.test_client()
        client2 = rate_limiting_app.test_client()

        with rate_limiting_app.test_request_context(environ_base={'REMOTE_ADDR': '1.1.1.1'}):
            make_requests(
                client1,
                'POST',
                '/api/generate-full',
                10,
                headers=rl_auth_headers,
                json_data={'title': 'test'}
            )

        with rate_limiting_app.test_request_context(environ_base={'REMOTE_ADDR': '2.2.2.2'}):
            response2 = client2.post(
                '/api/generate-full',
                headers=rl_auth_headers,
                json={'title': 'test from different IP'}
            )

        assert response2.status_code in [200, 201, 202, 400, 422], \
            f"Different IP should have fresh limit, got {response2.status_code}"

    def test_same_ip_shares_limit_across_requests(self, rate_limiting_client, rl_auth_headers):
        """Test same IP shares rate limit across all requests."""
        make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            15,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        responses2 = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            6,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        success_count = sum(1 for r in responses2 if r.status_code in [200, 201, 202, 400, 422])
        rate_limited_count = sum(1 for r in responses2 if r.status_code == 429)

        assert success_count == 5, f"Should have 5 requests left (20-15), got {success_count}"
        assert rate_limited_count == 1, f"Should be rate limited on 21st request, got {rate_limited_count}"


class TestRateLimitBackends:
    """Test rate limiting with different storage backends."""

    def test_memory_backend_rate_limiting(self, rate_limiting_client, rl_auth_headers):
        """Test rate limiting works with memory:// backend."""
        responses = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            21,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        success_count = sum(1 for r in responses if r.status_code in [200, 201, 202, 400, 422])
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 20, "Memory backend should enforce 20/min limit"
        assert rate_limited_count == 1, "Memory backend should rate limit 21st request"

    def test_rate_limiting_storage_persistence(self, rate_limiting_client, rl_auth_headers):
        """Test rate limit state persists across requests in same window."""
        make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            10,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        time.sleep(1)

        responses2 = make_requests(
            rate_limiting_client,
            'POST',
            '/api/generate',
            11,
            headers=rl_auth_headers,
            json_data={'prompt': 'test'}
        )

        success_count = sum(1 for r in responses2 if r.status_code in [200, 201, 202, 400, 422])
        rate_limited_count = sum(1 for r in responses2 if r.status_code == 429)

        assert success_count == 10, "Should have 10 requests left (20-10)"
        assert rate_limited_count == 1, "Should be rate limited on 21st total request"
