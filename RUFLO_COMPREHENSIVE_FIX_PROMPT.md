# PaperFull - Comprehensive Fix dengan MCP Ruflo
**Generated**: 2026-05-23  
**Project**: /home/sirobo/papergenerator  
**Objective**: Fix semua outstanding issues sampai production-ready

---

## Phase 0: Intelligence & Context Setup

### 1. Guidance System - Recommend Strategy
```
mcp__ruflo__guidance_recommend(
  task="Fix PaperFull academic paper generator: 43 documented bugs, 5 critical P0 issues (E2E auth, form validation, UI localization, registration hang, test infrastructure), need production-ready state with full test coverage"
)
```

### 2. Store Project Context ke Memory
```
# Store project overview
mcp__ruflo__memory_store(
  key="paperfull-overview",
  value="AI-powered academic paper generator. Flask backend + Vue3 frontend. Already audited: 48 bugs fixed, 43 remaining. Tech: PostgreSQL, Redis, RQ, Playwright E2E. Critical: auth state mismatch, form validation missing, test infrastructure broken.",
  namespace="project-context",
  tags=["paperfull", "audit-complete", "production-prep"]
)

# Store tech stack
mcp__ruflo__memory_store(
  key="paperfull-stack",
  value="Backend: Flask 3.1, PostgreSQL, Redis 5.0, RQ 1.16, Playwright 1.49, Gunicorn. Frontend: Vue 3.5, Vite 6.1, Pinia 2.3, Tailwind 3.4. Monitoring: Prometheus, Sentry. Testing: Playwright E2E, Vitest unit.",
  namespace="project-context",
  tags=["tech-stack", "dependencies"]
)

# Store critical issues
mcp__ruflo__memory_store(
  key="paperfull-p0-issues",
  value="P0 Issues: 1) E2E auth state mismatch (API cookies not in browser context), 2) Form validation missing (no error messages), 3) UI localization mismatch (tests expect EN, app uses ID), 4) Registration hangs (networkidle never reached), 5) Test infrastructure bugs (beforeAll/afterAll lifecycle)",
  namespace="project-context",
  tags=["critical", "p0", "blockers"]
)

# Store outstanding work
mcp__ruflo__memory_store(
  key="paperfull-remaining-work",
  value="43 documented bugs (medium/low priority) ready to apply. Need: apply fixes, expand test coverage (medical/CS/EE workflows), performance monitoring dashboard, CI/CD automation, i18n implementation.",
  namespace="project-context",
  tags=["backlog", "technical-debt"]
)
```

### 3. Search Similar Patterns
```
mcp__ruflo__memory_search(
  query="E2E authentication state management Playwright Flask session cookies",
  namespace="patterns",
  threshold=0.7,
  limit=5
)

mcp__ruflo__memory_search(
  query="Vue form validation real-time error messages UX",
  namespace="patterns",
  threshold=0.7,
  limit=5
)
```

---

## Phase 1: Intelligent Task Routing

### 1. Route P0 Tasks ke Optimal Model
```
# Route authentication fix
mcp__ruflo__hooks_route(
  task="Fix E2E authentication state mismatch: Playwright browser context not receiving Flask session cookies set via API. Need storageState persistence or test-mode bypass.",
  context="Flask-JWT-Extended backend, Vue3 frontend, Playwright E2E tests"
)

# Route form validation
mcp__ruflo__hooks_route(
  task="Implement client-side form validation with real-time error messages for Vue3 forms. Need validation rules, error display, accessibility compliance.",
  context="Vue3 Composition API, Pinia state, beginner-friendly UX"
)

# Route test infrastructure
mcp__ruflo__hooks_route(
  task="Fix Playwright test infrastructure: beforeAll/afterAll lifecycle issues, browser context cleanup, incomplete test execution.",
  context="Playwright 1.49, 10 test suites, 7 currently failing due to infrastructure"
)
```

### 2. Get Workflow Template
```
mcp__ruflo__guidance_workflow(
  type="bugfix"
)
```

---

## Phase 2: Swarm Initialization & Agent Spawning

### 1. Initialize Hierarchical Swarm
```
mcp__ruflo__swarm_init(
  topology="hierarchical",
  maxAgents=15,
  strategy="specialized",
  config={
    "consensus": "raft",
    "sharedMemory": true,
    "antiDrift": true,
    "costTracking": true
  }
)
```

### 2. Spawn Specialized Agents

#### Queen Agent (Coordinator)
```
mcp__ruflo__agent_spawn(
  agentType="coordinator",
  model="sonnet",
  task="Coordinate PaperFull comprehensive fix: manage 15 specialist agents, track progress, ensure quality, report status",
  config={
    "role": "queen",
    "capabilities": ["orchestration", "reporting", "quality-gate"]
  }
)
```

#### P0 Critical Fixes (3 agents)
```
# Agent 1: Authentication Specialist
mcp__ruflo__agent_spawn(
  agentType="security-specialist",
  model="sonnet",
  task="Fix E2E authentication: implement Playwright storageState for Flask-JWT session persistence. Test with all 10 E2E suites.",
  config={
    "priority": "P0",
    "domain": "authentication",
    "files": ["backend/app.py", "frontend/e2e/fixtures/auth.js"]
  }
)

# Agent 2: Form Validation Specialist
mcp__ruflo__agent_spawn(
  agentType="frontend-specialist",
  model="sonnet",
  task="Implement Vue3 form validation: real-time error messages, validation rules, WCAG compliance. Focus on beginner UX.",
  config={
    "priority": "P0",
    "domain": "frontend-ux",
    "files": ["frontend/src/components/forms/*.vue"]
  }
)

# Agent 3: Test Infrastructure Specialist
mcp__ruflo__agent_spawn(
  agentType="test-specialist",
  model="sonnet",
  task="Fix Playwright test infrastructure: beforeAll/afterAll hooks, browser context lifecycle, test execution completion.",
  config={
    "priority": "P0",
    "domain": "testing",
    "files": ["frontend/e2e/**/*.spec.js", "playwright.config.js"]
  }
)
```

#### P1 High Priority (4 agents)
```
# Agent 4: UI Localization
mcp__ruflo__agent_spawn(
  agentType="frontend-specialist",
  model="haiku",
  task="Add data-testid attributes to all interactive elements. Make tests language-agnostic.",
  config={
    "priority": "P1",
    "domain": "testing-infrastructure"
  }
)

# Agent 5: Registration Flow
mcp__ruflo__agent_spawn(
  agentType="fullstack-specialist",
  model="sonnet",
  task="Fix registration networkidle hang: investigate loading states, add proper error handling, ensure page transitions complete.",
  config={
    "priority": "P1",
    "domain": "authentication-flow"
  }
)

# Agent 6: Load Testing
mcp__ruflo__agent_spawn(
  agentType="performance-specialist",
  model="haiku",
  task="Complete load testing: concurrent users, queue management, bottleneck identification.",
  config={
    "priority": "P1",
    "domain": "performance"
  }
)

# Agent 7: Chaos Testing
mcp__ruflo__agent_spawn(
  agentType="reliability-specialist",
  model="haiku",
  task="Complete chaos testing: error scenarios, recovery mechanisms, data integrity verification.",
  config={
    "priority": "P1",
    "domain": "reliability"
  }
)
```

#### P2 Medium Priority (5 agents)
```
# Agent 8-12: Bug Fix Specialists (parallel)
for i in range(5):
  mcp__ruflo__agent_spawn(
    agentType="bug-fix-specialist",
    model="haiku",
    task=f"Apply documented bug fixes batch {i+1}/5: ~9 bugs per agent from 43 remaining medium/low priority bugs.",
    config={
      "priority": "P2",
      "domain": "bug-fixes",
      "batch": i+1
    }
  )
```

#### P3 Monitoring & Observability (2 agents)
```
# Agent 13: Performance Monitoring
mcp__ruflo__agent_spawn(
  agentType="sre-specialist",
  model="haiku",
  task="Set up performance monitoring dashboard: Prometheus metrics, Grafana dashboards, alerting rules.",
  config={
    "priority": "P3",
    "domain": "observability"
  }
)

# Agent 14: Test Coverage Expansion
mcp__ruflo__agent_spawn(
  agentType="test-specialist",
  model="haiku",
  task="Expand E2E test coverage: medical workflow, CS/IoT workflow, EE workflow tests.",
  config={
    "priority": "P3",
    "domain": "testing"
  }
)
```

#### Agent 15: Documentation & Reporting
```
mcp__ruflo__agent_spawn(
  agentType="documentation-specialist",
  model="haiku",
  task="Generate comprehensive documentation: API docs, deployment guide, troubleshooting guide, user manual.",
  config={
    "priority": "P3",
    "domain": "documentation"
  }
)
```

---

## Phase 3: Task Management & Workflow

### 1. Create Master Task List
```
# P0 Tasks
mcp__ruflo__task_create(
  type="bugfix",
  description="Fix E2E authentication state mismatch",
  priority="critical",
  assignTo=["agent-1-auth"],
  tags=["p0", "authentication", "testing"]
)

mcp__ruflo__task_create(
  type="feature",
  description="Implement form validation with error messages",
  priority="critical",
  assignTo=["agent-2-forms"],
  tags=["p0", "ux", "validation"]
)

mcp__ruflo__task_create(
  type="bugfix",
  description="Fix Playwright test infrastructure",
  priority="critical",
  assignTo=["agent-3-test-infra"],
  tags=["p0", "testing", "infrastructure"]
)

# P1 Tasks
mcp__ruflo__task_create(
  type="refactor",
  description="Add data-testid attributes for language-agnostic tests",
  priority="high",
  assignTo=["agent-4-localization"],
  tags=["p1", "testing", "i18n"]
)

mcp__ruflo__task_create(
  type="bugfix",
  description="Fix registration networkidle hang",
  priority="high",
  assignTo=["agent-5-registration"],
  tags=["p1", "authentication", "ux"]
)

# P2 Tasks (43 bug fixes)
mcp__ruflo__task_create(
  type="bugfix",
  description="Apply 43 documented medium/low priority bug fixes",
  priority="normal",
  assignTo=["agent-8", "agent-9", "agent-10", "agent-11", "agent-12"],
  tags=["p2", "bug-fixes", "technical-debt"]
)
```

### 2. Create Systematic Workflow
```
mcp__ruflo__workflow_create(
  name="paperfull-comprehensive-fix",
  description="Systematic fix workflow: P0 → P1 → P2 → P3 with quality gates",
  steps=[
    {
      "name": "p0-critical-fixes",
      "type": "parallel",
      "config": {
        "agents": ["agent-1", "agent-2", "agent-3"],
        "timeout": 14400000,  # 4 hours
        "qualityGate": "all-tests-pass"
      }
    },
    {
      "name": "p0-verification",
      "type": "task",
      "config": {
        "action": "run-e2e-tests",
        "successCriteria": ">=80% pass rate"
      }
    },
    {
      "name": "p1-high-priority",
      "type": "parallel",
      "config": {
        "agents": ["agent-4", "agent-5", "agent-6", "agent-7"],
        "timeout": 10800000  # 3 hours
      }
    },
    {
      "name": "p2-bug-fixes",
      "type": "parallel",
      "config": {
        "agents": ["agent-8", "agent-9", "agent-10", "agent-11", "agent-12"],
        "timeout": 14400000  # 4 hours
      }
    },
    {
      "name": "p3-monitoring-docs",
      "type": "parallel",
      "config": {
        "agents": ["agent-13", "agent-14", "agent-15"],
        "timeout": 7200000  # 2 hours
      }
    },
    {
      "name": "final-verification",
      "type": "task",
      "config": {
        "action": "full-test-suite",
        "successCriteria": ">=95% pass rate"
      }
    }
  ],
  variables={
    "projectRoot": "/home/sirobo/papergenerator",
    "testTimeout": 300000,
    "qualityThreshold": 0.95
  }
)
```

### 3. Execute Workflow
```
mcp__ruflo__workflow_execute(
  workflowId="paperfull-comprehensive-fix",
  variables={
    "startTime": "2026-05-23T07:30:00Z",
    "notifyOnComplete": true,
    "generateReport": true
  }
)
```

---

## Phase 4: Browser Automation & E2E Testing

### 1. Record Baseline Session
```
mcp__ruflo__browser_session_record(
  url="http://localhost:5173",
  task="Record baseline user journey: register → login → create paper → generate → download",
  session="paperfull-baseline-v1"
)
```

### 2. Test Authentication Fix
```
# After Agent 1 completes auth fix
mcp__ruflo__browser_session_replay(
  session="paperfull-baseline-v1",
  rvf_path=".ruflo/browser-sessions/paperfull-baseline-v1.rvf",
  url_override="http://localhost:5173"
)
```

### 3. Automated E2E Verification
```
# Run all 10 E2E test suites
for suite in ["business", "mobile", "power-user", "beginner", "cs-iot", "ee", "medical", "complete", "load", "chaos"]:
  mcp__ruflo__browser_template_apply(
    name=f"e2e-{suite}-test"
  )
```

---

## Phase 5: Intelligence & Learning

### 1. Start Learning Trajectory
```
mcp__ruflo__hooks_intelligence_trajectory-start(
  task="PaperFull comprehensive fix: P0-P3 systematic repair",
  agent="coordinator-queen"
)
```

### 2. Record Each Fix Step
```
# After each agent completes
mcp__ruflo__hooks_intelligence_trajectory-step(
  trajectoryId="paperfull-fix-trajectory",
  action="fixed-authentication-state-mismatch",
  result="E2E tests now pass with storageState persistence",
  quality=0.95
)
```

### 3. Store Successful Patterns
```
mcp__ruflo__hooks_intelligence_pattern-store(
  pattern="Playwright E2E auth with Flask-JWT: use storageState to persist session cookies across browser contexts. Set in beforeAll, reuse in tests.",
  type="testing-pattern",
  confidence=0.95,
  metadata={
    "framework": "playwright",
    "backend": "flask-jwt",
    "solution": "storageState"
  }
)
```

### 4. End Trajectory & Learn
```
mcp__ruflo__hooks_intelligence_trajectory-end(
  trajectoryId="paperfull-fix-trajectory",
  success=true,
  feedback="All P0 issues resolved, 95% test pass rate achieved"
)
```

### 5. Generate Embeddings for Future Search
```
mcp__ruflo__embeddings_generate(
  text="PaperFull academic paper generator: Flask backend, Vue3 frontend, Playwright E2E, authentication state management, form validation, test infrastructure fixes",
  hyperbolic=true,
  normalize=true
)
```

---

## Phase 6: Monitoring & Observability

### 1. Performance Metrics
```
mcp__ruflo__performance_benchmark(
  suite="all",
  iterations=100,
  warmup=true
)
```

### 2. System Health Check
```
mcp__ruflo__system_health(
  components=["memory", "agents", "tasks", "swarm"],
  deep=true,
  fix=false
)
```

### 3. Agent Load Balancing
```
mcp__ruflo__coordination_load_balance(
  action="distribute",
  algorithm="adaptive",
  task="remaining-bug-fixes"
)
```

---

## Phase 7: Consensus & Quality Gates

### 1. Hive-Mind Consensus on Completion
```
mcp__ruflo__hive-mind_consensus(
  action="propose",
  strategy="raft",
  type="completion-approval",
  value={
    "allP0Fixed": true,
    "testPassRate": 0.95,
    "securityScore": 0.90,
    "performanceScore": 0.85
  }
)
```

### 2. Vote from All Agents
```
# Each agent votes
for agentId in range(1, 16):
  mcp__ruflo__hive-mind_consensus(
    action="vote",
    proposalId="completion-approval",
    voterId=f"agent-{agentId}",
    vote=true
  )
```

### 3. Check Consensus Status
```
mcp__ruflo__hive-mind_consensus(
  action="status",
  proposalId="completion-approval"
)
```

---

## Phase 8: Session Management & Persistence

### 1. Save Session State
```
mcp__ruflo__session_save(
  name="paperfull-comprehensive-fix-2026-05-23",
  description="Complete fix session: 15 agents, P0-P3 systematic repair, 95% test pass rate",
  includeAgents=true,
  includeTasks=true,
  includeMemory=true
)
```

### 2. Export Session for Backup
```
mcp__ruflo__session_export(
  sessionId="paperfull-comprehensive-fix-2026-05-23",
  outputPath="/home/sirobo/papergenerator/backups/ruflo-session-2026-05-23.json",
  includeMemory=true
)
```

---

## Phase 9: Final Reporting & Documentation

### 1. Generate Comprehensive Report
```
mcp__ruflo__hooks_metrics(
  period="24h",
  includeV3=true
)
```

### 2. Task Summary
```
mcp__ruflo__task_summary()
```

### 3. Swarm Health Report
```
mcp__ruflo__swarm_health(
  swarmId="paperfull-fix-swarm"
)
```

### 4. Agent Performance Report
```
mcp__ruflo__agent_list(
  status="all",
  includeTerminated=true
)
```

### 5. Memory Statistics
```
mcp__ruflo__memory_detailed-stats()
```

---

## Phase 10: Cleanup & Optimization

### 1. Optimize Memory
```
mcp__ruflo__hive-mind_optimize-memory(
  qualityThreshold=0.7
)
```

### 2. Cleanup Expired Entries
```
mcp__ruflo__memory_cleanup(
  dryRun=false,
  namespace="project-context"
)
```

### 3. Shutdown Swarm
```
mcp__ruflo__swarm_shutdown(
  swarmId="paperfull-fix-swarm",
  graceful=true
)
```

---

## Expected Outcomes

### Quality Metrics
- **Test Pass Rate**: 95%+ (from 20%)
- **Security Score**: 90%+ (from 85%)
- **Performance Score**: 85%+ (from 60%)
- **Code Coverage**: 80%+ (from 30%)
- **Bug Count**: 0 critical, <5 medium (from 43)

### Deliverables
1. ✅ All P0 issues fixed (authentication, validation, test infrastructure)
2. ✅ All P1 issues fixed (localization, registration, load/chaos testing)
3. ✅ 43 documented bugs applied
4. ✅ Performance monitoring dashboard
5. ✅ Comprehensive documentation
6. ✅ 95%+ E2E test coverage
7. ✅ Production-ready deployment

### Timeline
- **Phase 0-2**: 1 hour (setup, routing, spawning)
- **Phase 3-4**: 4 hours (P0 fixes + verification)
- **Phase 5-6**: 3 hours (P1 fixes + testing)
- **Phase 7-8**: 4 hours (P2 bug fixes)
- **Phase 9-10**: 2 hours (P3 monitoring + cleanup)
- **Total**: ~14 hours (with 15 parallel agents)

---

## Usage Instructions

### Quick Start
```bash
# 1. Navigate to project
cd /home/sirobo/papergenerator

# 2. Start Ruflo MCP server (if not running)
ruflo mcp start

# 3. Execute this prompt via Claude Code with MCP Ruflo enabled
# Copy-paste sections sequentially or use workflow automation

# 4. Monitor progress
mcp__ruflo__task_list(status="all")
mcp__ruflo__swarm_status()

# 5. Check completion
mcp__ruflo__task_summary()
```

### Manual Execution
Execute each phase sequentially, waiting for completion before proceeding to next phase.

### Automated Execution
Use workflow system to execute all phases automatically with quality gates.

---

**Generated**: 2026-05-23  
**For**: PaperFull Academic Paper Generator  
**By**: Kiro AI with MCP Ruflo Integration  
**Status**: Ready to Execute
