# Performance Testing Infrastructure

## Overview

Performance testing framework menggunakan Locust untuk load testing API endpoints Paper Generator.

## Setup

### Prerequisites
- Python 3.8+
- Locust installed: `pip install locust`
- Flask app running on `http://localhost:5000`

### Installation
```bash
pip install locust --user
```

## Running Tests

### Option 1: Automated Test Runner (Recommended)
```bash
cd /home/sirobo/papergenerator
python3 backend/tests/performance/run_performance_tests.py
```

This will run 3 scenarios:
- **Normal Load:** 10 users, 60 seconds
- **Peak Load:** 25 users, 60 seconds  
- **Stress Test:** 50 users, 60 seconds

### Option 2: Manual Locust Run
```bash
cd /home/sirobo/papergenerator
locust -f backend/tests/performance/locustfile.py --host http://localhost:5000
```

Then open browser to `http://localhost:8089` for web UI.

### Option 3: Headless Mode
```bash
locust -f backend/tests/performance/locustfile.py \
  --headless \
  --users 10 \
  --spawn-rate 1 \
  --run-time 60s \
  --host http://localhost:5000
```

## Test Scenarios

### Endpoints Tested
1. **GET /api/health** - Health check (weight: 10)
2. **POST /api/generate** - Generate section (weight: 5)
3. **POST /api/generate-full** - Generate full paper (weight: 2)
4. **GET /api/papers** - List papers (weight: 3)

### Load Profiles

#### Normal Load
- Concurrent users: 10
- Duration: 60 seconds
- Spawn rate: 1 user/second
- Purpose: Baseline performance

#### Peak Load
- Concurrent users: 25
- Duration: 60 seconds
- Spawn rate: 2 users/second
- Purpose: Simulate peak traffic

#### Stress Test
- Concurrent users: 50
- Duration: 60 seconds
- Spawn rate: 5 users/second
- Purpose: Find breaking point

## Reports

Reports are generated in `backend/tests/performance/reports/`:
- `{scenario}.html` - HTML report with graphs
- `{scenario}_stats.csv` - Request statistics
- `{scenario}_failures.csv` - Failure logs
- `summary_{timestamp}.json` - Test summary

## Metrics

### Key Metrics Collected
- **Response Time:** Average, median, p95, p99, max
- **Throughput:** Requests per second (RPS)
- **Error Rate:** Percentage of failed requests
- **Rate Limiting:** 429 responses tracked

### Expected Performance (with AI mocking)
| Endpoint | Expected p95 | Expected RPS |
|----------|-------------|--------------|
| /api/health | < 10ms | 100+ |
| /api/generate | < 50ms | 50+ |
| /api/generate-full | < 100ms | 20+ |

## Configuration

### Environment Variables
- `MOCK_AI_RESPONSES=1` - Enable AI mocking for fast tests
- `AIOTOMASI_APIKEY` - API key (set to mock value for testing)

### AI Mocking
Tests use AI mocking (`MOCK_AI_RESPONSES=1`) to avoid:
- Slow external API calls (7-8 seconds per request)
- API costs
- Network dependencies

Rate limiting is still enforced even with mocking.

## Troubleshooting

### Flask App Not Running
```bash
cd /home/sirobo/papergenerator/backend
python3 app.py
```

### Rate Limiting Blocks Tests
This is expected behavior. Tests track 429 responses as successful.

### Locust Not Found
```bash
pip install locust --user
export PATH=$PATH:~/.local/bin
```

## Future Enhancements
- CI/CD integration
- Distributed testing
- Real-world scenarios (without mocking)
- Performance regression detection
