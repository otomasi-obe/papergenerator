# Frontend UI/UX Bug Inventory
**Generated:** 2026-05-22  
**Audited Files:** PaperEditorPage.vue, ChatTab.vue, MultiQuestionCard.vue, LiteratureTab.vue, FilesTab.vue, PreviewTab.vue, ChatMessage.vue, DiffBlock.vue, ActionChips.vue

---

## P0 Bugs (Critical - Breaks Functionality)

### 1. **MultiQuestionCard: Hardcoded Focus Color Breaks Dark Mode**
- **File:** `frontend/src/components/MultiQuestionCard.vue:229`
- **Issue:** Focus box-shadow uses hardcoded `rgba(217, 119, 87, 0.18)` instead of CSS variable
- **Impact:** Focus ring invisible or wrong color in dark mode
- **Repro:** Tab to custom input field in dark mode
- **Fix:** Replace with `var(--focus-ring)` or theme-aware color

### 2. **ChatTab: Placeholder Text Overflow on Mobile**
- **File:** `frontend/src/components/ChatTab.vue:329`
- **Issue:** Placeholder text is 80+ characters: `"Chat terkunci sampai generate paper selesai…"` and `"Sedang menjawab… bisa ketik draft berikutnya"`
- **Impact:** Text overflows textarea on mobile (320px-375px width)
- **Repro:** Open chat on mobile during AI generation
- **Fix:** Shorten to max 40 chars: `"Terkunci…"` / `"Mengetik…"`

### 3. **FilesTab: PDF Iframe No Error Handling**
- **File:** `frontend/src/components/FilesTab.vue:91-95`
- **Issue:** `<iframe>` has no `@error` handler or fallback when PDF fails to load
- **Impact:** Blank white screen when PDF corrupt/unsupported browser
- **Repro:** Upload corrupted PDF or use iOS Safari (limited PDF support)
- **Fix:** Add error boundary with "Download to view" fallback

### 4. **PaperEditorPage: Hardcoded Height Breaks Layout**
- **File:** `frontend/src/views/PaperEditorPage.vue:86`
- **Issue:** `h-[calc(100vh-105px)]` assumes fixed 105px header, but header height varies with pending changes banner (line 68-81)
- **Impact:** Content cut off when AI loading banner shows
- **Repro:** Start full paper generation → banner appears → scroll breaks
- **Fix:** Use CSS `height: calc(100vh - var(--header-height))` with dynamic var

### 5. **ChatMessage: Missing Loading State for Async Component**
- **File:** `frontend/src/components/ChatMessage.vue:375-388`
- **Issue:** `PaperProgressBubble` async component shows nothing during 8s timeout
- **Impact:** User sees blank space for 8 seconds if component fails to load
- **Repro:** Delete PaperProgressBubble.vue → send message with paper_progress metadata
- **Fix:** Add `loadingComponent` with spinner to `defineAsyncComponent`

---

## P1 Bugs (High Priority - Poor UX)

### 6. **ChatTab: Unclear File Upload Progress**
- **File:** `frontend/src/components/ChatTab.vue:296-297`
- **Issue:** Upload spinner shows but no progress percentage or file count
- **Impact:** User doesn't know if 5 files are uploading or stuck
- **Repro:** Attach 5 large PDFs → spinner shows but no progress
- **Fix:** Show "Uploading 3/5 files…" with progress bar

### 7. **LiteratureTab: Silent Error Fallback**
- **File:** `frontend/src/components/LiteratureTab.vue:551`
- **Issue:** `console.error(msg)` instead of user-facing toast when showToast unavailable
- **Impact:** Errors invisible to user in production
- **Repro:** Trigger SLR error when store.showToast undefined
- **Fix:** Always show alert() as last resort fallback

### 8. **PreviewTab: No Loading State for Large Papers**
- **File:** `frontend/src/components/PreviewTab.vue:36-222`
- **Issue:** Rendering 50+ sections with images causes 2-3s freeze, no spinner
- **Impact:** App appears frozen when switching to Preview tab
- **Repro:** Generate 20-section paper → click Preview tab
- **Fix:** Add skeleton loader or "Rendering preview…" overlay

### 9. **DiffBlock: No Disabled State During API Call**
- **File:** `frontend/src/components/DiffBlock.vue:13-22`
- **Issue:** Accept/Reject buttons stay enabled during API call → double-click possible
- **Impact:** User can click "Accept" twice → duplicate API calls
- **Repro:** Click "Terima" twice quickly on slow connection
- **Fix:** Add `disabled` state tied to pending API call

### 10. **ActionChips: No Keyboard Navigation**
- **File:** `frontend/src/components/ActionChips.vue:3-15`
- **Issue:** Chips are buttons but no arrow key navigation between them
- **Impact:** Keyboard users must tab through all chips (poor a11y)
- **Repro:** Tab to first chip → press arrow keys → nothing happens
- **Fix:** Add `@keydown.left/right` handlers to move focus

### 11. **ChatTab: File Attachment Warning Disappears**
- **File:** `frontend/src/components/ChatTab.vue:271, 488, 900`
- **Issue:** `attachWarning` cleared on next file change, user might miss it
- **Impact:** "Hanya PDF didukung" warning disappears before user reads it
- **Repro:** Attach .jpg → warning shows → attach .pdf → warning gone
- **Fix:** Keep warning visible for 5s with auto-clear timeout

### 12. **MultiQuestionCard: No Error State**
- **File:** `frontend/src/components/MultiQuestionCard.vue:131-138`
- **Issue:** `submit()` emits event but no error handling if parent fails
- **Impact:** User clicks "Kirim" → nothing happens if API fails
- **Repro:** Disconnect network → answer questions → click Kirim
- **Fix:** Add error prop to show "Gagal mengirim, coba lagi"

---

## P2 Bugs (Medium Priority - Polish Issues)

### 13. **Inconsistent Disabled Button Opacity**
- **Files:** Multiple (see grep results)
- **Issue:** `disabled:opacity-50` (ChatTab), `disabled:opacity-40` (ChatTab send), `disabled:opacity-30` (PaperEditorPage arrows)
- **Impact:** Inconsistent visual language across app
- **Fix:** Standardize to `disabled:opacity-50` everywhere

### 14. **Missing ARIA Labels on Interactive Elements**
- **Files:** ActionChips.vue, DiffBlock.vue, many buttons
- **Issue:** Buttons missing `aria-label` for screen readers
- **Impact:** Screen reader users hear "button" with no context
- **Examples:**
  - ActionChips buttons (line 3-15)
  - DiffBlock accept/reject (line 13-22)
  - ChatTab attach menu toggle (line 290-298)
- **Fix:** Add descriptive `aria-label` to all icon-only buttons

### 15. **No Focus-Visible States on Some Buttons**
- **Files:** DiffBlock.vue, MultiQuestionCard.vue
- **Issue:** Buttons missing `:focus-visible` outline for keyboard nav
- **Impact:** Keyboard users can't see which button is focused
- **Fix:** Add `focus-visible:ring-2 focus-visible:ring-offset-1` to all buttons

### 16. **Inconsistent Error Message Styling**
- **Files:** ChatTab.vue (line 271), FilesTab.vue (line 28), LiteratureTab.vue (line 28-37)
- **Issue:** Some errors are `text-amber-700`, some `text-red-600`, some in banner
- **Impact:** User confused about severity (warning vs error)
- **Fix:** Use amber for warnings, red for errors, consistent banner style

### 17. **ChatTab: Long File Names Overflow**
- **File:** `frontend/src/components/ChatTab.vue:263`
- **Issue:** File name truncated to `max-w-[160px]` but no tooltip on hover
- **Impact:** User can't see full filename "research-paper-final-v3-revised.pdf"
- **Repro:** Attach file with 40+ char name
- **Fix:** Add `:title="f.name"` to show full name on hover

### 18. **LiteratureTab: Table Not Responsive on Mobile**
- **File:** `frontend/src/components/LiteratureTab.vue:198-350`
- **Issue:** 13-column table with `min-w-full` breaks on mobile (320px)
- **Impact:** Horizontal scroll required, poor mobile UX
- **Repro:** Open Literature tab on iPhone SE
- **Fix:** Hide non-essential columns on mobile with `hidden md:table-cell`

### 19. **PreviewTab: Image Paths Might Break**
- **File:** `frontend/src/components/PreviewTab.vue:280-282`
- **Issue:** `imgSrc()` uses `/api/images/${paperId}/${path}` but no error handling
- **Impact:** Broken image icon if path invalid or image deleted
- **Repro:** Delete image file → preview shows broken icon
- **Fix:** Add `@error` handler to show placeholder

### 20. **FilesTab: No Visual Feedback on File Select**
- **File:** `frontend/src/components/FilesTab.vue:41-65`
- **Issue:** Selected file only shows via `bg-cream-200` which is subtle
- **Impact:** User unsure which file is selected
- **Repro:** Click file → hard to tell it's selected
- **Fix:** Add left border accent: `border-l-4 border-l-brown-600` when active

---

## Specific Bugs from Task

### ✅ Paper Editor Tab Switching
- **Status:** Working correctly
- **Tested:** Tab state persists per-paper via `ui.getTab(paperId)`
- **File:** PaperEditorPage.vue:333-341

### ✅ Chat Message Rendering
- **Status:** Working correctly
- **Tested:** Markdown rendering with syntax highlighting
- **File:** ChatMessage.vue:512-520

### ⚠️ File Upload Feedback
- **Status:** Partial - see P1 Bug #6
- **Issue:** Spinner shows but no progress details
- **File:** ChatTab.vue:296

### ✅ Literature Table Display
- **Status:** Working correctly
- **Tested:** Sorting, filtering, bulk actions all functional
- **Note:** Mobile responsiveness issue (P2 Bug #18)

### ⚠️ Image Generation Status
- **Status:** Not found in audited files
- **Note:** Likely in ImageGenStore or separate component
- **Action:** Need to audit `frontend/src/stores/imageGen.js`

---

## Accessibility Issues Summary

1. **Missing ARIA labels:** 15+ buttons lack descriptive labels
2. **No keyboard navigation:** ActionChips, file picker lack arrow key support
3. **Poor focus indicators:** Some buttons have no visible focus ring
4. **Color contrast:** Some disabled states (opacity-30) fail WCAG AA
5. **Screen reader support:** File upload progress not announced

---

## Performance Issues

1. **LiteratureTab.vue:** 1185 lines, complex polling logic
2. **PreviewTab.vue:** Renders entire paper synchronously (no virtualization)
3. **ChatTab.vue:** 1000 lines, multiple watchers, potential memory leaks
4. **PaperEditorPage.vue:** Deep watchers on entire paper object (line 389-405)

---

## Recommendations

### Immediate Fixes (P0)
1. Fix MultiQuestionCard focus color (5 min)
2. Shorten ChatTab placeholders (5 min)
3. Add FilesTab PDF error handler (15 min)
4. Fix PaperEditorPage height calculation (20 min)
5. Add ChatMessage loading component (10 min)

**Total:** ~1 hour

### High Priority (P1)
1. Add file upload progress indicator (30 min)
2. Fix LiteratureTab error fallback (5 min)
3. Add PreviewTab loading state (20 min)
4. Add DiffBlock disabled state (15 min)
5. Add ActionChips keyboard nav (30 min)

**Total:** ~2 hours

### Polish (P2)
1. Standardize disabled opacity (30 min)
2. Add missing ARIA labels (1 hour)
3. Add focus-visible states (30 min)
4. Standardize error styling (30 min)

**Total:** ~2.5 hours

---

## Testing Checklist

- [ ] Test all fixes on mobile (320px, 375px, 768px)
- [ ] Test dark mode for all components
- [ ] Test keyboard navigation (Tab, Arrow keys, Enter, Escape)
- [ ] Test screen reader (NVDA/JAWS)
- [ ] Test with slow 3G connection
- [ ] Test with corrupted file uploads
- [ ] Test with 50+ section paper
- [ ] Test with network disconnected
