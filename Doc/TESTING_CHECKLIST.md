# Testing Checklist - Paper Generation Chat Fix

**Bug Fix:** Replace raw PROPOSAL JSON with user-friendly messages in chat  
**Date:** 2026-05-22  
**Files Changed:** `frontend/src/stores/chat.js`

---

## Pre-Deployment Checklist

### 1. Build Verification
- [x] Frontend builds without errors: `npm run build`
- [ ] Backend tests pass: `pytest backend/tests/`
- [ ] No console errors in browser dev tools
- [ ] No TypeScript/ESLint warnings

### 2. Code Review
- [x] Helper function handles all 20+ proposal types
- [x] Tool result handler correctly replaces raw JSON
- [x] No breaking changes to existing functionality
- [x] Code follows project conventions

---

## Manual Testing Scenarios

### Test 1: Paper Generation via Chat ⭐ CRITICAL
**Steps:**
1. Open a paper in the editor
2. Navigate to Chat tab
3. Create a new chat or open existing one
4. Send message: "Generate a paper about machine learning optimization"
5. Wait for AI to call `GenerateFullPaper` tool

**Expected Result:**
- ✅ Chat shows: `✓ Paper generation started (job: [job_id]). Editor akan auto-load hasilnya.`
- ✅ Progress bubble appears below the message
- ✅ NO raw JSON like `<<PROPOSAL>>{"kind":"paper_progress",...}` is visible
- ✅ Paper data loads into editor when job completes
- ✅ Paper is saved to database correctly

**Failure Indicators:**
- ❌ Raw JSON visible in chat
- ❌ No confirmation message shown
- ❌ Paper doesn't load into editor
- ❌ Console errors

---

### Test 2: Literature Search (SLR)
**Steps:**
1. In chat, send: "Search for papers about neural networks"
2. Wait for AI to call `RunSLR` or `AddLiterature` tool

**Expected Result:**
- ✅ Chat shows: `✓ Literature search started for "neural networks". Check Literature tab untuk hasilnya.`
- ✅ Literature tab opens automatically
- ✅ Search results appear in Literature tab
- ✅ NO raw JSON visible

---

### Test 3: Section Proposals
**Steps:**
1. In chat, send: "Write an introduction section about AI ethics"
2. Wait for AI to call `ProposeSection` tool

**Expected Result:**
- ✅ Chat shows: `✓ Section [N] proposal: "[title]"`
- ✅ Preview panel shows the proposed section
- ✅ Accept/Reject buttons work correctly
- ✅ NO raw JSON visible

---

### Test 4: Title/Abstract/Keywords Proposals
**Steps:**
1. Send: "Suggest a better title for this paper"
2. Send: "Write an abstract"
3. Send: "Suggest keywords"

**Expected Result:**
- ✅ Title: `✓ Title proposal: "[title text]"`
- ✅ Abstract: `✓ Abstract proposal (XXX chars)`
- ✅ Keywords: `✓ Keywords proposal: keyword1, keyword2, keyword3 +N more`
- ✅ Preview panel shows proposals
- ✅ NO raw JSON visible

---

### Test 5: Chart Generation
**Steps:**
1. Send: "Create a bar chart comparing accuracy metrics"
2. Wait for AI to call `GenerateChart` tool

**Expected Result:**
- ✅ Chat shows: `✓ Chart generated: "[chart title]"`
- ✅ Chart preview appears inline
- ✅ Accept/Regenerate buttons work
- ✅ NO raw JSON visible

---

### Test 6: File Upload and Review
**Steps:**
1. Upload a large PDF file (>5000 words)
2. AI should call `ReviewLargeFile` tool

**Expected Result:**
- ✅ Chat shows: `✓ File review: [filename] (XXXX words)`
- ✅ File review card appears with head/tail preview
- ✅ Action buttons (Cite, Summarize, Extract) work
- ✅ NO raw JSON visible

---

### Test 7: Validation Errors
**Steps:**
1. Try to generate paper without literature (if possible)
2. AI should return validation error

**Expected Result:**
- ✅ Chat shows: `⚠ [error message]`
- ✅ Warning banner appears with helpful message
- ✅ Retry/SLR action buttons work
- ✅ NO raw JSON visible

---

### Test 8: Journal Template Switch
**Steps:**
1. Send: "Switch to IEEE template"
2. AI calls `ProposeJournal` tool

**Expected Result:**
- ✅ Chat shows: `✓ Journal template switched to: IEEE`
- ✅ Editor updates to IEEE template
- ✅ NO raw JSON visible

---

### Test 9: DOCX Export
**Steps:**
1. Send: "Export this paper to DOCX"
2. AI calls `RequestExportDocx` tool

**Expected Result:**
- ✅ Chat shows: `✓ DOCX export started. File akan tersedia di tab Export.`
- ✅ Export tab opens (if implemented)
- ✅ DOCX file is generated
- ✅ NO raw JSON visible

---

### Test 10: Tool Error Handling
**Steps:**
1. Trigger a tool error (e.g., network timeout, invalid arguments)
2. Expand "Show Details" in the error message

**Expected Result:**
- ✅ Error message is user-friendly
- ✅ "Show Details" shows friendly message (not raw JSON)
- ✅ Error details are helpful for debugging
- ✅ NO raw PROPOSAL JSON visible even in details

---

## Regression Testing

### Critical Paths to Verify
- [ ] Paper generation still saves to database correctly
- [ ] Editor still loads generated papers
- [ ] All chat functionality works (send message, streaming, etc.)
- [ ] Tool calls execute correctly
- [ ] Proposals can be accepted/rejected
- [ ] Literature search works
- [ ] File uploads work
- [ ] Image generation works (if applicable)
- [ ] Multi-chat switching works
- [ ] Chat history persists correctly

### Edge Cases
- [ ] Very long paper titles (>100 chars)
- [ ] Papers with many keywords (>10)
- [ ] Large file uploads
- [ ] Rapid successive tool calls
- [ ] Network interruptions during tool execution
- [ ] Browser refresh during paper generation
- [ ] Multiple papers open simultaneously

---

## Browser Compatibility Testing

Test in the following browsers:
- [ ] Chrome/Chromium (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest, macOS)
- [ ] Edge (latest)
- [ ] Mobile Safari (iOS)
- [ ] Mobile Chrome (Android)

---

## Performance Testing

### Metrics to Monitor
- [ ] Chat message rendering time (<100ms)
- [ ] Tool result processing time (<50ms)
- [ ] Memory usage (no leaks after 50+ messages)
- [ ] Network payload size (proposals should be small)

### Load Testing
- [ ] 100+ messages in a single chat
- [ ] 10+ tool calls in rapid succession
- [ ] Multiple chats open simultaneously
- [ ] Large paper data (50+ sections)

---

## Accessibility Testing

- [ ] Screen reader announces tool results correctly
- [ ] Keyboard navigation works (Tab, Enter, Escape)
- [ ] Focus management is correct
- [ ] Color contrast meets WCAG AA standards
- [ ] Tool result messages are readable

---

## Security Testing

- [ ] No sensitive data in tool results (API keys, tokens, etc.)
- [ ] XSS protection (tool results are sanitized)
- [ ] CSRF tokens work correctly
- [ ] User can only see their own papers/chats
- [ ] Tool calls are properly authenticated

---

## Deployment Steps

### 1. Pre-Deployment
```bash
# Backup database
pg_dump paperfull > backup_$(date +%Y%m%d_%H%M%S).sql

# Run tests
cd /home/sirobo/papergenerator/backend
pytest tests/

# Build frontend
cd /home/sirobo/papergenerator/frontend
npm run build
```

### 2. Deployment
```bash
# Deploy frontend
cd /home/sirobo/papergenerator/frontend
npm run build
# Copy dist/ to production server

# Restart backend (if needed)
sudo systemctl restart paperfull-backend

# Clear CDN cache (if applicable)
```

### 3. Post-Deployment Verification
- [ ] Visit production site
- [ ] Test paper generation via chat
- [ ] Check browser console for errors
- [ ] Monitor error logs for 1 hour
- [ ] Check database for correct paper data

### 4. Rollback Plan (if needed)
```bash
# Revert frontend
git checkout HEAD~1 frontend/src/stores/chat.js
npm run build
# Deploy previous build

# Restore database (if needed)
psql paperfull < backup_YYYYMMDD_HHMMSS.sql
```

---

## Success Criteria

### Must Have ✅
- [x] No raw PROPOSAL JSON visible in chat
- [ ] All tool results show friendly messages
- [ ] Paper generation works end-to-end
- [ ] Paper data saves to database correctly
- [ ] No console errors
- [ ] No breaking changes to existing features

### Nice to Have 🎯
- [ ] Improved error messages
- [ ] Better loading indicators
- [ ] Smoother animations
- [ ] Faster tool result processing

---

## Known Issues / Limitations

### Current Limitations
- Tool results in "Show Details" section still show the friendly message (not raw data)
  - This is intentional - raw data is no longer useful to users
  - Developers can still see raw data in Network tab

### Future Improvements
- Add i18n support for friendly messages (currently mixed ID/EN)
- Add more detailed progress information for long-running jobs
- Add ability to cancel tool execution
- Add tool result history/replay

---

## Sign-Off

### Testing Completed By
- [ ] Developer: _________________ Date: _______
- [ ] QA: _________________ Date: _______
- [ ] Product Owner: _________________ Date: _______

### Deployment Approved By
- [ ] Tech Lead: _________________ Date: _______
- [ ] DevOps: _________________ Date: _______

### Production Verification
- [ ] Verified in production: _________________ Date: _______
- [ ] No critical errors in logs: _________________ Date: _______
- [ ] User feedback collected: _________________ Date: _______

---

## Contact

**For issues or questions:**
- Developer: [Your Name]
- Bug Report: https://github.com/Kilo-Org/kilocode/issues
- Documentation: /home/sirobo/papergenerator/BUG_FIX_SUMMARY.md
