# Playwright MCP Test Agent for Paper Generation

Comprehensive test suite for paper generation workflow using Playwright MCP tools.

## Overview

This test suite validates the paper generation system across different user knowledge levels and interaction patterns. Tests are designed to be executed by an AI agent with access to Playwright MCP tools.

## Test Files

### 1. `test_playwright_paper_generation.py`
Main test specification file containing test scenarios for:
- **Beginner User**: Step-by-step guided workflow with many questions
- **Intermediate User**: Partial info provided, needs some guidance
- **Advanced User**: Comprehensive info upfront, fast-track generation
- **Hybrid Literature**: File upload + AI-assisted paper discovery
- **Error Handling**: Edge cases and error recovery
- **Concurrent Users**: Multiple simultaneous paper generations

### 2. `playwright_mcp_runner.py`
Test runner with detailed step-by-step scenario definitions in JSON format. Each scenario includes:
- Action sequence (navigate, click, type, wait, verify)
- Expected outcomes
- Verification criteria
- Timeout configurations

## Test Scenarios

### Beginner User Workflow
**Goal**: Verify system guides confused users through paper creation

**Flow**:
1. User expresses confusion: "Saya bingung mau nulis paper tentang apa"
2. AI asks about field/topic/interests
3. User provides vague interest: "AI dan machine learning"
4. AI asks for more specific details
5. User narrows down: "deep learning untuk image recognition"
6. AI provides structure suggestions
7. User confirms and requests generation
8. Paper is generated successfully

**Expected Behavior**:
- AI asks clarifying questions
- AI provides guidance and suggestions
- AI helps narrow down topic
- Paper generated with appropriate structure

### Intermediate User Workflow
**Goal**: Verify system handles users with partial information

**Flow**:
1. User provides topic + some details upfront
2. AI acknowledges and asks for missing details (methodology, evaluation)
3. User provides additional information
4. AI proceeds to generation with minimal back-and-forth
5. Paper is generated successfully

**Expected Behavior**:
- AI recognizes provided information
- AI asks only for missing critical details
- Faster path to generation than beginner

### Advanced User Workflow
**Goal**: Verify system fast-tracks comprehensive information

**Flow**:
1. User provides complete information (title, abstract, methodology, results)
2. AI acknowledges completeness
3. AI proceeds directly to generation
4. Paper is generated successfully

**Expected Behavior**:
- AI recognizes comprehensive input
- Minimal or no follow-up questions
- Fastest path to generation

### Hybrid Literature Workflow
**Goal**: Verify system integrates uploaded files with AI-found papers

**Flow**:
1. User uploads literature files (PDF, BibTeX)
2. User requests AI to find additional papers
3. AI analyzes uploaded files
4. AI searches for related papers
5. User requests SLR generation
6. Paper integrates both sources

**Expected Behavior**:
- AI extracts info from uploaded files
- AI finds relevant additional papers
- Generated paper includes both sources
- Proper citation and integration

## Running Tests

### Prerequisites
1. Application must be running at `http://localhost:5173`
2. Backend API must be accessible
3. Test user account must exist
4. Playwright MCP tools must be available

### Execution Methods

#### Method 1: AI Agent Execution (Recommended)
The AI agent with Playwright MCP tools reads the test scenarios and executes them:

```bash
# The AI agent will:
# 1. Read test scenario from playwright_mcp_runner.py
# 2. Execute each step using Playwright MCP tools
# 3. Verify outcomes
# 4. Report results
```

#### Method 2: Manual Execution
Run individual test functions:

```bash
cd backend/tests
python test_playwright_paper_generation.py
```

#### Method 3: Pytest Integration
Run with pytest for better reporting:

```bash
pytest backend/tests/test_playwright_paper_generation.py -v
pytest backend/tests/test_playwright_paper_generation.py::test_beginner_user_workflow -v
```

## Test Verification Points

Each test verifies:

### 1. Navigation & Authentication
- ✓ Application loads successfully
- ✓ Login works correctly
- ✓ Dashboard is accessible
- ✓ Editor page loads

### 2. Chat Interaction
- ✓ Messages are sent successfully
- ✓ AI responds within timeout
- ✓ Responses are contextually appropriate
- ✓ Response quality matches user level

### 3. Paper Generation
- ✓ Generation is triggered correctly
- ✓ Progress indicators appear
- ✓ Generation completes within timeout
- ✓ Paper structure is created

### 4. Content Quality
- ✓ Paper has all required sections
- ✓ Content is relevant to topic
- ✓ References are included
- ✓ Format matches template (IEEE, etc.)

## Timeout Configuration

| Operation | Timeout | Reason |
|-----------|---------|--------|
| Page load | 10s | Network + rendering |
| AI response | 30s | LLM inference time |
| Literature search | 60s | External API calls |
| Paper generation | 300s (5min) | Full paper generation |

## Error Handling

Tests handle common failure scenarios:
- Network timeouts
- API errors
- Invalid input
- Generation failures
- Concurrent access issues

## Test Data

### Sample Messages

**Beginner**:
```
"Saya bingung mau nulis paper tentang apa. Bisa bantu?"
"Saya tertarik dengan AI dan machine learning"
"Mungkin tentang deep learning untuk image recognition"
```

**Intermediate**:
```
"Saya ingin menulis paper tentang CNN untuk klasifikasi gambar medis. 
Saya sudah punya dataset X-ray dan ingin membandingkan beberapa arsitektur."
```

**Advanced**:
```
Complete specification with title, abstract, methodology, results, and conclusions
```

## Expected AI Response Patterns

### Beginner Level
- Questions: "Bidang apa yang Anda minati?"
- Guidance: "Bagaimana kalau kita fokus ke..."
- Suggestions: "Saya sarankan struktur seperti ini..."

### Intermediate Level
- Acknowledgment: "Baik, topik yang menarik..."
- Clarification: "Bisa jelaskan lebih detail tentang metodologi?"
- Confirmation: "Saya akan buatkan paper dengan struktur..."

### Advanced Level
- Recognition: "Informasi yang Anda berikan sudah lengkap..."
- Minimal questions: "Apakah ada preferensi format tertentu?"
- Direct action: "Saya akan mulai generate paper..."

## Troubleshooting

### Test Fails: "Navigation timeout"
- Check if application is running
- Verify URL is correct
- Check network connectivity

### Test Fails: "AI response timeout"
- Check backend API status
- Verify LLM service is running
- Check API rate limits

### Test Fails: "Generation timeout"
- Increase timeout value
- Check backend worker status
- Verify Redis/queue is running

### Test Fails: "Element not found"
- Take snapshot to see current page state
- Check if UI has changed
- Update element selectors

## Continuous Integration

To integrate with CI/CD:

```yaml
# .github/workflows/playwright-tests.yml
name: Playwright MCP Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start application
        run: |
          docker-compose up -d
          sleep 10
      - name: Run Playwright tests
        run: |
          pytest backend/tests/test_playwright_paper_generation.py -v
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: test-results/
```

## Metrics & Reporting

Tests track:
- Execution time per scenario
- Success/failure rate
- AI response quality
- Generation completion rate
- Error types and frequency

## Future Enhancements

- [ ] Add visual regression testing
- [ ] Test mobile responsive design
- [ ] Add performance benchmarks
- [ ] Test accessibility compliance
- [ ] Add load testing scenarios
- [ ] Test offline functionality
- [ ] Add multi-language support tests

## Contributing

When adding new tests:
1. Follow existing test structure
2. Add clear documentation
3. Include expected outcomes
4. Set appropriate timeouts
5. Add verification points
6. Handle errors gracefully

## License

Same as parent project.

## Support

For issues or questions:
- Check troubleshooting section
- Review test logs
- Check application logs
- Contact development team
