# Frontend Bug Fixes - QA Testing Checklist

**Before deploying to production, verify all items below:**

## ✅ P0 Bug Fixes Verification

### 1. MultiQuestionCard - Dark Mode Focus Ring
- [ ] Open chat in dark mode
- [ ] Send message that triggers multi-question card
- [ ] Tab to custom input field
- [ ] **Verify:** Focus ring is visible (blue glow)
- [ ] Switch to light mode and verify focus ring still works

### 2. ChatTab - Mobile Placeholder Text
- [ ] Open DevTools, set viewport to 320px width (iPhone SE)
- [ ] Open chat tab
- [ ] Start paper generation (to trigger "Terkunci saat generate…")
- [ ] **Verify:** Placeholder text doesn't overflow textarea
- [ ] Test at 375px (iPhone 12) and 768px (iPad)

### 3. FilesTab - PDF Error Handling
- [ ] Upload a valid PDF file
- [ ] **Verify:** PDF displays in iframe
- [ ] Test on iOS Safari (if available)
- [ ] If PDF fails to load, **verify:** Download button appears
- [ ] Click download button, **verify:** PDF downloads
- [ ] Upload corrupted PDF, **verify:** Error UI shows

### 4. PaperEditorPage - Dynamic Height
- [ ] Open paper editor
- [ ] Start full paper generation
- [ ] **Verify:** AI loading banner appears at top
- [ ] **Verify:** Content area shrinks to accommodate banner
- [ ] **Verify:** No content is cut off or hidden
- [ ] Wait for generation to complete
- [ ] **Verify:** Content area expands back to full height

### 5. ChatMessage - Async Component Loading
- [ ] Send message that triggers paper progress bubble
- [ ] **Verify:** Loading spinner appears (after 200ms)
- [ ] **Verify:** "Memuat progress…" text visible
- [ ] **Verify:** No blank space during load
- [ ] Wait for component to load
- [ ] **Verify:** Progress bubble displays correctly

## ✅ P1 Bug Fixes Verification

### 6. ChatTab - Upload Progress
- [ ] Attach 5 PDF files to chat
- [ ] **Verify:** Button shows spinner during upload
- [ ] Hover over upload button
- [ ] **Verify:** Tooltip shows "Uploading 2/5…" (or similar)
- [ ] Wait for upload to complete
- [ ] **Verify:** Button returns to normal state

### 7. LiteratureTab - Error Fallback
- [ ] Open browser console
- [ ] Trigger SLR error (disconnect network, then run SLR)
- [ ] **Verify:** Alert dialog appears with error message
- [ ] **Verify:** Error also logged to console
- [ ] Reconnect network and verify normal operation

### 8. DiffBlock - Disabled State
- [ ] Generate paper with AI suggestions
- [ ] Go to Preview tab
- [ ] Find a diff block with Accept/Reject buttons
- [ ] Click "Terima" button quickly twice
- [ ] **Verify:** Button disables after first click
- [ ] **Verify:** Only one API call is made (check Network tab)
- [ ] **Verify:** Button re-enables after API completes

### 9. ChatTab - Warning Timeout
- [ ] Try to attach a .jpg file to chat
- [ ] **Verify:** Warning "Hanya PDF didukung" appears
- [ ] Wait 5 seconds
- [ ] **Verify:** Warning disappears automatically
- [ ] Attach valid PDF
- [ ] **Verify:** No warning appears

### 10. ActionChips - Keyboard Navigation
- [ ] Send message that shows action chips (e.g., after SLR completes)
- [ ] Tab to first chip
- [ ] Press Right Arrow key
- [ ] **Verify:** Focus moves to next chip
- [ ] Press Left Arrow key
- [ ] **Verify:** Focus moves to previous chip
- [ ] Press Home key
- [ ] **Verify:** Focus jumps to first chip
- [ ] Press End key
- [ ] **Verify:** Focus jumps to last chip
- [ ] Press Enter on focused chip
- [ ] **Verify:** Chip action triggers

### 11. FilesTab - PDF Error Reset
- [ ] Upload corrupted PDF (error UI shows)
- [ ] Upload valid PDF
- [ ] **Verify:** Error UI disappears
- [ ] **Verify:** Valid PDF displays correctly

## 🎨 Visual Regression Testing

### Dark Mode
- [ ] Test all fixed components in dark mode
- [ ] Verify colors are correct (no hardcoded light colors)
- [ ] Verify focus rings visible
- [ ] Verify text contrast meets WCAG AA

### Mobile Responsive
- [ ] Test at 320px (iPhone SE)
- [ ] Test at 375px (iPhone 12)
- [ ] Test at 768px (iPad)
- [ ] Test at 1024px (iPad Pro)
- [ ] Verify no horizontal scroll
- [ ] Verify all buttons tappable (min 44x44px)

### Keyboard Navigation
- [ ] Tab through entire page
- [ ] Verify focus visible on all interactive elements
- [ ] Verify no keyboard traps
- [ ] Verify logical tab order

## ♿ Accessibility Testing

### Screen Reader (NVDA/JAWS)
- [ ] Navigate to ActionChips
- [ ] **Verify:** "Option 1 of 4: [label]" announced
- [ ] Navigate to upload button during upload
- [ ] **Verify:** "Uploading 2 of 5 files" announced
- [ ] Navigate to DiffBlock buttons
- [ ] **Verify:** "Accept change" and "Reject change" announced

### Keyboard Only
- [ ] Complete entire workflow without mouse
- [ ] Upload files using keyboard
- [ ] Navigate action chips with arrows
- [ ] Accept/reject diffs with keyboard

## 🐛 Edge Cases

### Network Conditions
- [ ] Test file upload on slow 3G
- [ ] **Verify:** Progress indicator updates
- [ ] Test API calls with network disconnected
- [ ] **Verify:** Error messages appear

### Large Data
- [ ] Generate paper with 50+ sections
- [ ] Open Preview tab
- [ ] **Verify:** No UI freeze (or loading state shows)
- [ ] Upload 5 large PDFs (5MB+ each)
- [ ] **Verify:** Progress indicator accurate

### Browser Compatibility
- [ ] Test on Chrome (latest)
- [ ] Test on Firefox (latest)
- [ ] Test on Safari (latest)
- [ ] Test on iOS Safari (if available)
- [ ] Test on Android Chrome (if available)

## 📊 Performance

### Bundle Size
- [ ] Check dist/ folder size
- [ ] **Verify:** Increase is < 5 KB gzip
- [ ] Run Lighthouse audit
- [ ] **Verify:** Performance score unchanged

### Build Time
- [ ] Run `npm run build`
- [ ] **Verify:** Completes in < 10 seconds
- [ ] **Verify:** No errors or warnings

## 🚀 Deployment Checklist

- [ ] All P0 fixes verified
- [ ] All P1 fixes verified
- [ ] Visual regression tests pass
- [ ] Accessibility tests pass
- [ ] Edge cases tested
- [ ] Performance acceptable
- [ ] Build passes
- [ ] Git commit created with clear message
- [ ] PR created with link to this checklist
- [ ] Code review completed
- [ ] Staging deployment successful
- [ ] Smoke tests on staging pass
- [ ] Production deployment approved

## 📝 Notes

**Tester Name:** _______________  
**Date:** _______________  
**Environment:** _______________  
**Browser:** _______________  
**OS:** _______________  

**Issues Found:**
- 
- 
- 

**Sign-off:** _______________
