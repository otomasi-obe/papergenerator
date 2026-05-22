# Logging System Implementation Plan
**PaperFull Application**  
**Version:** 1.0  
**Date:** 2026-05-22

---

## Implementation Roadmap

### Phase 1: Critical Log Rotation (Days 1-2) ⚠️ URGENT

**Goal:** Prevent disk exhaustion from 359MB unrotated log file

**Tasks:**
1. ✅ Backup current app.log
2. ✅ Create logs directory structure
3. ✅ Update observability.py with rotation
4. ✅ Test rotation mechanism
5. ✅ Deploy to production

**Files to Modify:**
- `backend/observability.py`

**Files to Create:**
- `backend/logs/` directory

**Estimated Time:** 4 hours  
**Risk Level:** Low  
**Can Deploy Independently:** Yes

---

### Phase 2: Centralized Logger Module (Days 3-5)

**Goal:** Create unified logging interface with context injection

**Tasks:**
1. ✅ Create logger.py module
2. ✅ Add context injection middleware
3. ✅ Create logger factory with auto-context
4. ✅ Add performance tracking decorators
5. ✅ Add error categorization helpers
6. ✅ Write unit tests

**Files to Create:**
- `backend/logger.py`
- `backend/context_middleware.py`
- `backend/tests/test_logger.py`

**Files to Modify:**
- `backend/app.py` (integrate middleware)

**Estimated Time:** 8 hours  
**Risk Level:** Low  
**Can Deploy Independently:** Yes

---

### Phase 3: Migrate Core Modules (Days 6-8)

**Goal:** Replace print() and standardize logging in high-traffic modules

**Priority Order:**
1. `app.py` (13 print statements)
2. `generate_paper_chunked.py` (12 print statements)
3. `chat.py` (existing logging, add context)
4. `auth.py` (existing logging, add context)
5. `files_bp.py` (existing logging, add context)

**Tasks per Module:**
1. ✅ Replace print() with logger calls
2. ✅ Add structured context to existing logs
3. ✅ Add error categorization
4. ✅ Add performance tracking
5. ✅ Test in staging

**Estimated Time:** 12 hours  
**Risk Level:** Medium  
**Can Deploy Independently:** Yes (per module)

---

### Phase 4: Frontend Logger Service (Days 9-11)

**Goal:** Centralized frontend logging with backend reporting

**Tasks:**
1. ✅ Create logger.js service
2. ✅ Add backend endpoint /api/logs/frontend
3. ✅ Implement error batching
4. ✅ Add performance tracking
5. ✅ Migrate console.warn/error calls
6. ✅ Test error reporting flow

**Files to Create:**
- `frontend/src/utils/logger.js`
- `frontend/src/api/logs.js`
- `backend/logs_bp.py`

**Files to Modify:**
- `frontend/src/stores/user.js`
- `frontend/src/stores/paperJobs.js`
- `frontend/src/views/AdminPage.vue`
- `frontend/src/views/FilesPage.vue`
- `frontend/src/views/DashboardPage.vue`
- `backend/app.py` (register blueprint)

**Estimated Time:** 10 hours  
**Risk Level:** Low  
**Can Deploy Independently:** Yes

---

### Phase 5: Error Categorization (Days 12-14)

**Goal:** Systematic error classification and tracking

**Tasks:**
1. ✅ Define error taxonomy
2. ✅ Add categorization to logger
3. ✅ Update error handlers across modules
4. ✅ Add Prometheus metrics
5. ✅ Create error dashboard queries

**Files to Modify:**
- `backend/logger.py`
- `backend/observability.py`
- All error handling code

**Estimated Time:** 8 hours  
**Risk Level:** Low  
**Can Deploy Independently:** Yes

---

### Phase 6: Performance Monitoring (Days 15-17)

**Goal:** Track slow operations and bottlenecks

**Tasks:**
1. ✅ Add database query tracking
2. ✅ Add file processing tracking
3. ✅ Add frontend performance tracking
4. ✅ Set up performance alerts
5. ✅ Create performance dashboard

**Files to Modify:**
- `backend/logger.py`
- `backend/models.py` (query tracking)
- `frontend/src/utils/logger.js`

**Estimated Time:** 10 hours  
**Risk Level:** Low  
**Can Deploy Independently:** Yes

---

### Phase 7: Cleanup & Documentation (Days 18-20)

**Goal:** Finalize migration and document system

**Tasks:**
1. ✅ Remove all remaining print() statements
2. ✅ Standardize logger names
3. ✅ Create log analysis scripts
4. ✅ Write developer documentation
5. ✅ Create runbook for operations

**Files to Create:**
- `backend/log_analysis/error_summary.py`
- `backend/log_analysis/perf_report.py`
- `docs/LOGGING_GUIDE.md`
- `docs/LOGGING_RUNBOOK.md`

**Estimated Time:** 8 hours  
**Risk Level:** None  
**Can Deploy Independently:** Yes

---

## Total Timeline

**Estimated Duration:** 20 working days (4 weeks)  
**Critical Path:** Phase 1 → Phase 2 → Phase 3  
**Parallel Work:** Phases 4, 5, 6 can overlap after Phase 2

---

## Deployment Strategy

### Rolling Deployment

**Week 1:**
- Day 1-2: Deploy Phase 1 (log rotation) - CRITICAL
- Day 3-5: Deploy Phase 2 (logger module)

**Week 2:**
- Day 6-8: Deploy Phase 3 (migrate core modules, one per day)
- Day 9-11: Deploy Phase 4 (frontend logger)

**Week 3:**
- Day 12-14: Deploy Phase 5 (error categorization)
- Day 15-17: Deploy Phase 6 (performance monitoring)

**Week 4:**
- Day 18-20: Deploy Phase 7 (cleanup & docs)

### Rollback Plan

Each phase is independently deployable. If issues arise:

1. **Phase 1:** Revert observability.py, restart app
2. **Phase 2:** Remove middleware registration, restart app
3. **Phase 3:** Revert individual module changes
4. **Phase 4:** Disable frontend error reporting
5. **Phase 5:** No rollback needed (additive)
6. **Phase 6:** No rollback needed (additive)

---

## Testing Strategy

### Unit Tests

**Coverage Requirements:**
- Logger module: 90%+
- Context middleware: 80%+
- Error categorization: 85%+

**Test Files:**
- `backend/tests/test_logger.py`
- `backend/tests/test_context_middleware.py`
- `frontend/tests/unit/logger.spec.js`

### Integration Tests

**Scenarios:**
1. Log rotation triggers at midnight
2. Context injection works across requests
3. Frontend errors reach backend
4. Performance tracking captures slow operations
5. Error categorization works end-to-end

### Load Tests

**Verify:**
- Logging overhead < 5ms per request
- No memory leaks from log buffering
- Rotation doesn't block requests
- Frontend batching works under load

---

## Monitoring & Alerts

### Critical Alerts

**Disk Space:**
```bash
# Alert if logs directory > 500MB
du -sm /home/sirobo/papergenerator/backend/logs | awk '$1 > 500'
```

**Log Rotation Failure:**
```bash
# Alert if app.log > 100MB (rotation not working)
find backend/logs -name "app.log" -size +100M
```

**Error Rate Spike:**
```promql
# Alert if error rate > 10/min
rate(log_errors_total[1m]) > 10
```

### Performance Alerts

**Slow Operations:**
```promql
# Alert if 95th percentile > 2s
histogram_quantile(0.95, http_request_duration_seconds) > 2
```

**Frontend Error Rate:**
```promql
# Alert if frontend errors > 5/min
rate(frontend_errors_total[1m]) > 5
```

---

## Success Criteria

### Phase 1 Success Criteria
- ✅ app.log rotates daily
- ✅ Compressed archives created
- ✅ Old logs deleted after 7 days
- ✅ No disk space issues
- ✅ No application downtime

### Phase 2 Success Criteria
- ✅ Logger module functional
- ✅ Context injection works
- ✅ Unit tests pass
- ✅ No performance degradation

### Phase 3 Success Criteria
- ✅ Zero print() in migrated modules
- ✅ All logs include context
- ✅ Error categorization working
- ✅ No regressions in functionality

### Phase 4 Success Criteria
- ✅ Frontend errors reach backend
- ✅ Batching works correctly
- ✅ No console spam in production
- ✅ Performance tracking functional

### Phase 5 Success Criteria
- ✅ All errors categorized
- ✅ Metrics exported to Prometheus
- ✅ Error dashboard functional

### Phase 6 Success Criteria
- ✅ Slow operations tracked
- ✅ Performance alerts working
- ✅ Dashboard shows metrics

### Phase 7 Success Criteria
- ✅ Documentation complete
- ✅ Team trained
- ✅ Runbook validated

---

## Resource Requirements

### Development
- 1 Backend Developer (full-time, 4 weeks)
- 1 Frontend Developer (part-time, 1 week)
- 1 DevOps Engineer (part-time, 1 week)

### Infrastructure
- No additional servers required
- Disk space: +200MB for logs
- Monitoring: Existing Prometheus/Grafana

### Tools
- Python logging library (built-in)
- No new dependencies required

---

## Risk Assessment

### High Risk Items
1. **Log rotation failure** → Disk full → Application crash
   - **Mitigation:** Thorough testing, monitoring, manual backup

2. **Performance overhead** → Slow requests → User complaints
   - **Mitigation:** Async logging, benchmarking, load testing

### Medium Risk Items
1. **Breaking changes** → Application errors → Rollback needed
   - **Mitigation:** Gradual migration, backward compatibility, testing

2. **Frontend log spam** → Backend overload → Rate limiting needed
   - **Mitigation:** Client-side filtering, batching, rate limits

### Low Risk Items
1. **Log format changes** → Dashboard breaks → Update queries
   - **Mitigation:** Backward compatible format, versioning

2. **Disk space growth** → Cleanup needed → Automated retention
   - **Mitigation:** Automated cleanup, monitoring, alerts

---

## Communication Plan

### Stakeholder Updates

**Weekly Status Report:**
- Progress on each phase
- Blockers and risks
- Upcoming deployments
- Metrics and KPIs

**Deployment Notifications:**
- 24 hours before deployment
- Deployment window
- Expected impact
- Rollback plan

### Team Training

**Developer Training:**
- How to use new logger API
- Best practices for structured logging
- Error categorization guidelines
- Performance tracking usage

**Operations Training:**
- Log rotation mechanism
- Monitoring and alerts
- Troubleshooting guide
- Runbook walkthrough

---

## Post-Implementation Review

### Week 1 After Completion
- Review metrics and KPIs
- Identify issues and improvements
- Gather team feedback
- Update documentation

### Month 1 After Completion
- Analyze log data patterns
- Optimize retention policies
- Tune performance thresholds
- Create additional dashboards

### Quarter 1 After Completion
- Full system audit
- Cost-benefit analysis
- Plan next improvements
- Update roadmap

---

## Appendix: Quick Reference

### Deploy Phase 1 (Log Rotation)
```bash
cd /home/sirobo/papergenerator
git pull origin main
sudo systemctl restart papergenerator
# Verify rotation working
ls -lh backend/logs/
```

### Deploy Phase 2 (Logger Module)
```bash
cd /home/sirobo/papergenerator
git pull origin main
pip install -r backend/requirements.txt  # If new deps
sudo systemctl restart papergenerator
# Verify context injection
tail -f backend/logs/app.log | jq .
```

### Deploy Phase 4 (Frontend Logger)
```bash
cd /home/sirobo/papergenerator/frontend
npm run build
# Deploy built files
sudo systemctl reload nginx
```

### Rollback Commands
```bash
# Rollback to previous version
git revert HEAD
sudo systemctl restart papergenerator

# Emergency: restore backup log
cp backend/app.log.backup backend/app.log
```

### Verify Deployment
```bash
# Check logs are rotating
ls -lh backend/logs/app.log*

# Check context injection
curl -H "Authorization: Bearer $TOKEN" \
  https://paperfull.app/api/me | \
  jq .

# Check frontend errors reaching backend
grep "papergenerator.frontend" backend/logs/app.log
```

---

**Document Status:** Ready for Implementation  
**Next Review:** After Phase 1 Completion  
**Owner:** Backend Team Lead  
**Approvers:** CTO, DevOps Lead
