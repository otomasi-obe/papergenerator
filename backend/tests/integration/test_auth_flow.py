"""
Integration Tests: Authentication Flow
=======================================
Test complete authentication flows including register, login, logout.
"""


class TestAuthenticationFlow:
    """Test complete authentication flows."""

    def test_register_new_user(self, client):
        """Test user registration creates new user and returns token."""
        register_data = {
            'name': 'New User',
            'email': 'newuser@example.com',
            'password': 'SecurePass123!'
        }
        response = client.post('/api/auth/register', json=register_data)

        assert response.status_code == 201
        data = response.get_json()
        assert 'user' in data
        assert data['user']['email'] == 'newuser@example.com'
        assert data['user']['name'] == 'New User'
        assert 'access_token_cookie' in response.headers.get('Set-Cookie', '')

    def test_register_duplicate_email(self, client, test_user):
        """Test registration with existing email returns 409 Conflict."""
        register_data = {
            'name': 'Another User',
            'email': 'test@example.com',
            'password': 'AnotherPass123!'
        }
        response = client.post('/api/auth/register', json=register_data)

        assert response.status_code == 409
        data = response.get_json()
        assert 'error' in data

    def test_register_invalid_password(self, client):
        """Test registration with weak password returns 400."""
        register_data = {
            'name': 'New User',
            'email': 'newuser2@example.com',
            'password': 'weak'
        }
        response = client.post('/api/auth/register', json=register_data)

        assert response.status_code == 400

    def test_login_with_valid_credentials(self, client, test_user):
        """Test login with valid credentials returns token."""
        login_data = {
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        }
        response = client.post('/api/auth/login', json=login_data)

        assert response.status_code == 200
        data = response.get_json()
        assert 'user' in data
        assert data['user']['email'] == 'test@example.com'
        assert 'access_token_cookie' in response.headers.get('Set-Cookie', '')

    def test_login_with_invalid_password(self, client, test_user):
        """Test login with wrong password returns 401."""
        login_data = {
            'email': 'test@example.com',
            'password': 'WrongPassword123!'
        }
        response = client.post('/api/auth/login', json=login_data)

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data

    def test_login_with_nonexistent_user(self, client):
        """Test login with non-existent email returns 401."""
        login_data = {
            'email': 'nonexistent@example.com',
            'password': 'SomePassword123!'
        }
        response = client.post('/api/auth/login', json=login_data)

        assert response.status_code == 401

    def test_access_protected_endpoint_without_auth(self, client):
        """Test accessing protected endpoint without authentication returns 401."""
        response = client.get('/api/auth/me')

        assert response.status_code == 401

    def test_access_protected_endpoint_with_auth(self, client, test_user):
        """Test accessing protected endpoint with valid token returns user data."""
        login_response = client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })
        assert login_response.status_code == 200

        response = client.get('/api/auth/me')

        assert response.status_code == 200
        data = response.get_json()
        assert data['email'] == 'test@example.com'
        assert data['name'] == 'Test User'

    def test_complete_auth_lifecycle(self, client):
        """Test complete authentication lifecycle: register -> login -> access -> logout."""
        register_data = {
            'name': 'Lifecycle User',
            'email': 'lifecycle@example.com',
            'password': 'LifecyclePass123!'
        }
        response = client.post('/api/auth/register', json=register_data)
        assert response.status_code == 201

        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = response.get_json()
        assert data['email'] == 'lifecycle@example.com'

        response = client.post('/api/auth/logout')
        assert response.status_code == 200

        response = client.get('/api/auth/me')
        assert response.status_code == 401
