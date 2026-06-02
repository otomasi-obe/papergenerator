"""Tests for rate limit monitoring and metrics.

Tests verify that rate limit metrics are correctly tracked and exported to
Prometheus, and that the Grafana dashboard is valid.
"""
import json
from pathlib import Path
from unittest.mock import patch

from prometheus_client import REGISTRY


def test_rate_limit_metrics_exist():
    """Test that rate limit metrics are registered in Prometheus."""
    from monitoring.observability_v2 import (
        RATE_LIMIT_BREACHES,
        RATE_LIMIT_CURRENT_USAGE,
        RATE_LIMIT_REQUESTS,
    )

    assert RATE_LIMIT_REQUESTS is not None
    assert RATE_LIMIT_BREACHES is not None
    assert RATE_LIMIT_CURRENT_USAGE is not None

    metric_names = [m.name for m in REGISTRY.collect()]
    assert 'rate_limit_requests_total' in metric_names
    assert 'rate_limit_breaches_total' in metric_names
    assert 'rate_limit_current_usage' in metric_names


def test_rate_limit_requests_metric_on_success(client):
    """Test that RATE_LIMIT_REQUESTS increments on successful requests."""
    from monitoring.observability_v2 import RATE_LIMIT_REQUESTS

    before = RATE_LIMIT_REQUESTS.labels(endpoint='health', status='allowed')._value.get()

    response = client.get('/api/health')
    assert response.status_code == 200

    after = RATE_LIMIT_REQUESTS.labels(endpoint='health', status='allowed')._value.get()
    assert after > before, "Metric should increment on successful request"


def test_rate_limit_requests_metric_on_blocked(client, app):
    """Test that RATE_LIMIT_REQUESTS increments with status=blocked on 429."""
    from monitoring.observability_v2 import RATE_LIMIT_REQUESTS

    with app.test_request_context():
        from flask import Response

        before_blocked = RATE_LIMIT_REQUESTS.labels(
            endpoint='test_endpoint',
            status='blocked'
        )._value.get()

        response = Response(status=429)
        response.status_code = 429

        with patch('flask.request') as mock_request:
            mock_request.endpoint = 'test_endpoint'
            mock_request.path = '/api/test'

            from app import _security_headers
            _security_headers(response)

        after_blocked = RATE_LIMIT_REQUESTS.labels(
            endpoint='test_endpoint',
            status='blocked'
        )._value.get()

        assert after_blocked > before_blocked, "Metric should increment on 429 response"


def test_rate_limit_breaches_metric_on_breach(app):
    """Test that RATE_LIMIT_BREACHES increments when rate limit handler is called."""
    from app import rate_limit_handler
    from monitoring.observability_v2 import RATE_LIMIT_BREACHES

    with app.test_request_context('/api/test'):
        from flask import request
        request.endpoint = 'test_endpoint'

        before = RATE_LIMIT_BREACHES.labels(
            endpoint='test_endpoint',
            limit_type='ip'
        )._value.get()

        response = rate_limit_handler(None)

        after = RATE_LIMIT_BREACHES.labels(
            endpoint='test_endpoint',
            limit_type='ip'
        )._value.get()

        assert response.status_code == 429
        assert after > before, "RATE_LIMIT_BREACHES should increment on breach"


def test_rate_limit_metrics_labels():
    """Test that metrics have correct labels."""
    from monitoring.observability_v2 import (
        RATE_LIMIT_BREACHES,
        RATE_LIMIT_CURRENT_USAGE,
        RATE_LIMIT_REQUESTS,
    )

    assert RATE_LIMIT_REQUESTS._labelnames == ('endpoint', 'status')
    assert RATE_LIMIT_BREACHES._labelnames == ('endpoint', 'limit_type')
    assert RATE_LIMIT_CURRENT_USAGE._labelnames == ('endpoint', 'identifier')


def test_rate_limit_metrics_types():
    """Test that metrics are of correct Prometheus types."""
    from prometheus_client import Counter, Gauge

    from monitoring.observability_v2 import (
        RATE_LIMIT_BREACHES,
        RATE_LIMIT_CURRENT_USAGE,
        RATE_LIMIT_REQUESTS,
    )

    assert isinstance(RATE_LIMIT_REQUESTS, Counter)
    assert isinstance(RATE_LIMIT_BREACHES, Counter)
    assert isinstance(RATE_LIMIT_CURRENT_USAGE, Gauge)


def test_grafana_dashboard_json_valid():
    """Test that Grafana dashboard JSON is valid and well-formed."""
    dashboard_path = Path(__file__).parent.parent.parent / 'infra' / 'grafana' / 'dashboards' / 'rate-limits.json'

    assert dashboard_path.exists(), f"Dashboard not found at {dashboard_path}"

    with open(dashboard_path, 'r') as f:
        dashboard = json.load(f)

    assert dashboard['title'] == 'PaperFull — Rate Limit Monitoring'
    assert dashboard['uid'] == 'paperfull-rate-limits'
    assert 'panels' in dashboard
    assert len(dashboard['panels']) >= 5, "Dashboard should have at least 5 panels"

    for panel in dashboard['panels']:
        assert 'title' in panel
        assert 'type' in panel
        assert 'datasource' in panel
        assert 'targets' in panel
        assert len(panel['targets']) > 0


def test_grafana_dashboard_queries():
    """Test that Grafana dashboard queries reference correct metrics."""
    dashboard_path = Path(__file__).parent.parent.parent / 'infra' / 'grafana' / 'dashboards' / 'rate-limits.json'

    with open(dashboard_path, 'r') as f:
        dashboard = json.load(f)

    all_queries = []
    for panel in dashboard['panels']:
        for target in panel['targets']:
            if 'expr' in target:
                all_queries.append(target['expr'])

    queries_str = ' '.join(all_queries)

    assert 'rate_limit_breaches_total' in queries_str
    assert 'rate_limit_requests_total' in queries_str


def test_metrics_endpoint_includes_rate_limit_metrics(client):
    """Test that /api/metrics endpoint exposes rate limit metrics."""
    response = client.get('/api/metrics')
    assert response.status_code == 200

    content = response.data.decode('utf-8')

    assert 'rate_limit_requests_total' in content
    assert 'rate_limit_breaches_total' in content
    assert 'rate_limit_current_usage' in content


def test_rate_limit_handler_returns_correct_response(app):
    """Test that rate_limit_handler returns proper JSON error response."""
    from app import rate_limit_handler

    with app.test_request_context('/api/test'):
        from flask import request
        request.endpoint = 'test_endpoint'

        response = rate_limit_handler(None)

        assert response.status_code == 429
        data = json.loads(response.data)
        assert 'error' in data
        assert 'code' in data
        assert 'category' in data
        assert data['error'] == 'Terlalu banyak request'


def test_security_headers_tracks_metrics_safely(client, app):
    """Test that _security_headers tracks metrics without breaking on errors."""

    with patch('monitoring.observability_v2.RATE_LIMIT_REQUESTS') as mock_metric:
        mock_metric.labels.side_effect = Exception("Metric error")

        response = client.get('/api/health')

        assert response.status_code == 200, "Request should succeed even if metrics fail"


def test_rate_limit_metrics_documentation():
    """Test that metrics have proper documentation strings."""
    from monitoring.observability_v2 import (
        RATE_LIMIT_BREACHES,
        RATE_LIMIT_CURRENT_USAGE,
        RATE_LIMIT_REQUESTS,
    )

    assert RATE_LIMIT_REQUESTS._documentation
    assert RATE_LIMIT_BREACHES._documentation
    assert RATE_LIMIT_CURRENT_USAGE._documentation

    assert 'rate limiter' in RATE_LIMIT_REQUESTS._documentation.lower()
    assert 'violations' in RATE_LIMIT_BREACHES._documentation.lower()
    assert 'usage' in RATE_LIMIT_CURRENT_USAGE._documentation.lower()
