"""
Integration Tests: Health Check Endpoints
==========================================
Test health check endpoints with real database dependencies.
"""


class TestHealthIntegration:
    """Test health check endpoints with real dependencies."""

    def test_health_endpoint_returns_ok(self, client):
        """Test basic health check returns 200 OK."""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'timestamp' in data
        assert 'service' in data
        assert data['service'] == 'papergenerator'

    def test_healthz_with_database_check(self, client):
        """Test readiness check includes database connectivity."""
        response = client.get('/api/healthz')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
        assert 'checks' in data
        assert 'db' in data['checks']
        assert data['checks']['db']['ok'] is True

    def test_healthz_includes_disk_check(self, client):
        """Test readiness check includes disk space check."""
        response = client.get('/api/healthz')
        assert response.status_code == 200
        data = response.get_json()
        assert 'checks' in data
        assert 'disk' in data['checks']
        assert 'free_mb' in data['checks']['disk']
