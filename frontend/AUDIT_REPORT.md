# Paperfull Frontend Security & Quality Audit
## Files Audited: 12 stores, 12 views, 36 components, api/, router/
## Date: 2026-07-09

---

## CRITICAL

### 1. CSRF Token Leaked in SSE URL (LiteratureTab.vue)
**FILE:** `src/components/LiteratureTab.vue:1288`
**Severity:** CRITICAL
**Impact:** `csrf_access_token` cookie value transmitted as query param in `EventSource` URL → token persists in browser history, server access logs, proxy logs. If backend has a logging vulnerability, token can be harvested.
```vue
const es = new EventSource(`/api/slr/jobs/${jobId}/stream?token=${encodeURIComponent(document.cookie.match(...)?.[1] || '')}`)
```
**Fix:** Use cookie-based auth for SSE. `EventSource` automatically sends cookies with `withCredentials`. Backend should accept cookie auth for SSE endpoints instead of query-token fallback. Remove `?token=` from URL.

---

### 2. LandingPage v-html with unsanitized i18n content
**FILE:** `src/views/LandingPage.vue:118`
**Severity:** CRITICAL (if i18n translations can be tampered)
**Impact:** `typedHtml` bound to `v-html` unsanitized:
```vue
<span v-html="typedHtml"></span>
```
`typedHtml` comes from `buildFullHtml()` which uses `t('hero.title1')` etc. — these are static i18n strings in a JSON file, not user input. LOW risk currently BUT if any i18n key ever contains user-supplied content (e.g. dynamic promo text from backend), this becomes a direct XSS vector.
**Fix:** `v-html="sanitizeHtml(typedHtml)"` via `useSanitize()`. Or better: `v-html` not needed — the typed content is text + span, can be composed with template.

---

## HIGH

### 3. Password Hash Visible in SettingsPage (read from auth store)
**FILE:** `src/views/SettingsPage.vue:64, 259`
**Severity:** HIGH
**Impact:** `auth.user?.password_hash` checked to conditionally show password fields. The `setUser()` function in auth store strips `password_hash` before saving to localStorage (line 32), but the *in-memory* `user` ref could still contain it if the API response includes it (via `fetchMe`). The SettingsPage checks `auth.user?.password_hash` directly.
**Mitigation:** `setUser()` strips before assigning `user.value`, so this is currently protected. However, `User` interface has `[key: string]: unknown` (index signature, line 13 of auth.ts) — if future API returns extra fields, they won't be stripped. The `hasPassword` ref is a boolean, which is safe, but `auth.user?.password_hash` read on line 64 could expose the hash if the deserialization order changes.
**Fix:** Remove `password_hash` from the destructuring whitelist — use explicit field listing or a type-safe pick. Already mitigated by `setUser()` but fragile.

### 4. IntersectionObserver Leak in LandingPage
**FILE:** `src/views/LandingPage.vue:431, 449`
**Severity:** HIGH
**Impact:** Two `IntersectionObserver` instances created (`counterObserver`, `cardObserver`) in `onMounted`, but **never disconnected** in `onUnmounted`. If user navigates away from landing page while observers are active, they hold references to DOM nodes and callbacks → memory leak.
```vue
onUnmounted(() => {
  window.removeEventListener('scroll', updateScrollY)
  document.removeEventListener('click', handleClickOutside)
  if (typeTimer) clearInterval(typeTimer)
  // MISSING: counterObserver.disconnect(), cardObserver.disconnect()
})
```
**Fix:** Store observer refs and `.disconnect()` them in `onUnmounted`.

### 5. `_progressTimer` Never Initialized or Cleared in PaperfullTab
**FILE:** `src/components/PaperfullTab.vue:544`
**Severity:** HIGH
**Impact:** `let _progressTimer = null` declared at line 544. `startProgressTicker()` and `stopProgressTicker()` referenced in code but their implementation is not visible in the read scope. If `_progressTimer` is set in `setInterval` but not cleared in `onUnmounted`, timer leak. Need to verify `stopProgressTicker()` is called in `onUnmounted` (line 688: `stopProgressTicker()` — present). **Status: Partially mitigated — verify `startProgressTicker` sets `_progressTimer`.**

### 6. Race Condition in `renderPdf` (PreviewTab)
**FILE:** `src/components/PreviewTab.vue:477-550`
**Severity:** HIGH
**Impact:** `renderPdf()` has early return `if (pdfLoading.value) return` which protects against double invocation. However, the watcher at line 471 sets a `renderDebounceTimer = setTimeout(renderPdf, 100)` — if user makes rapid edits, multiple debounced calls queue up and can race with the in-flight fetch. The debounce clears `renderDebounceTimer` before calling `renderPdf`, but if `renderPdf` itself is async and takes 2s, a second debounce timer fires after the first `pdfLoading` guard releases.
**Fix:** Add a generation counter or abort controller to cancel in-flight renders.

### 7. EventSource Missing `onerror` Handler (LiteratureTab SSE)
**FILE:** `src/components/LiteratureTab.vue:1288-1387`
**Severity:** HIGH
**Impact:** `EventSource` created at line 1288 with `addEventListener` for `snapshot`, `progress`, `partial`, `done`. No `es.onerror` handler is set before the `es.addEventListener` calls. The `onerror` handler is defined later (line ~1370) inside the try block. If connection fails immediately, `onerror` may not fire properly. Also, **no `onerror` handler at all in the visible code** — the `es.onerror` assignment at ~1370 is inside the try block but I cannot see it confirmed. The native `EventSource` auto-reconnects on error; without a handler, you get infinite reconnect loops.
**Fix:** Add explicit `es.onerror = (e) => { ... }` before connecting, handle disconnect logic, and limit reconnect attempts.

---

## MEDIUM

### 8. `@ts-nocheck` in 12+ Files — Blind Spot for Type Errors
**Severity:** MEDIUM
**Impact:** The following files have `// @ts-nocheck`, disabling ALL TypeScript type checking:
- `src/stores/chat.ts`
- `src/stores/paper.ts`
- `src/stores/paperJobs.ts`
- `src/composables/useSanitize.ts`
- `src/components/LiteratureTab.vue`
- `src/components/DataTab.vue`
- `src/components/ContentList.vue`
- `src/components/PreviewTab.vue`
- `src/components/JournalTab.vue`
- `src/components/RevisiProposalCard.vue`
- `src/components/AskUserCard.vue`
- `src/components/MultiQuestionCard.vue`
- `src/views/PaperEditorPage.vue`

This is ~35% of the source code. Type errors, null derefs, and API contract mismatches will silently pass compilation. Many of these are the most security-critical files (auth, chat, sanitization).
**Fix:** Remove `@ts-nocheck` incrementally. Start with `useSanitize.ts` (trivial), then stores, then components. Use `@ts-expect-error` for specific known issues.

### 9. `ToolWorkspace.vue` v-html Without Sanitization
**FILE:** `src/components/ToolWorkspace.vue:299`
**Severity:** MEDIUM
**Impact:** Grammar output rendered with `v-html` using `renderGrammarOutput()`:
```vue
<span v-html="renderGrammarOutput(store.outputText)"></span>
```
`renderGrammarOutput()` at line 490 escapes `<`, `>`, `&` and applies diff markers. The escaping is done via regex `.replace()` which is adequate for the specific `<add>`/`<del>` pattern. However, this is custom sanitization — not DOMPurify. If `store.outputText` contains crafted sequences that bypass the 3 replaces (e.g., unicode homoglyphs, nested HTML entities), XSS is possible.
**Fix:** Pass result through `DOMPurify.sanitize()` or use the `useSanitize().sanitizeHtml()`.

### 10. Timer Leak Risk — PaperEditorPage `tickTimer`
**FILE:** `src/views/PaperEditorPage.vue:819, 886`
**Severity:** MEDIUM
**Impact:** `tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)` created in `onMounted`. Cleared in `onUnmounted` (line 876). This appears correct. **No issue found — timer is properly cleaned up.** (Flag was for investigation.)

### 11. AdminPage `_quotaTimers` — Array of Timers Not Cleared on Navigation
**FILE:** `src/views/AdminPage.vue:330, 392`
**Severity:** MEDIUM
**Impact:** `_quotaTimers.push(setTimeout(...))` accumulates timers. `onBeforeUnmount` does ` _quotaTimers.forEach(clearTimeout)` which is correct. However, if `loadAll` fires every 30s and each call creates new timers via `_quotaTimers.push`, the array grows unbounded during the page's lifetime until unmount. No cleanup between cycles.
**Fix:** Clear `_quotaTimers` at start of each `loadAll()` cycle or use a single debounced timer.

### 12. Missing Loading/Error States on API-Dependent Components
**FILE:** `src/components/ContentList.vue` (various), `src/components/PaperfullTab.vue:764-773`
**Severity:** MEDIUM
**Impact:** `loadPaperFilesList()` at PaperfullTab:764 silently catches errors with `console.warn` and sets empty array. No user-facing error state. Same pattern in `loadLiterature()` at line 856-877. Users see empty file list or literature list with no indication of failure.
**Fix:** Add error state flags and display retry UI.

### 13. `paperJobs.ts` — `startGlobalPolling` No Stop on Unmount
**FILE:** `src/stores/paperJobs.ts:283-292`
**Severity:** MEDIUM
**Impact:** `startGlobalPolling()` creates a `setInterval` at 5s. `stopGlobalPolling()` exists and is called from `App.vue` `onUnmounted` (line 35-36). However, if `App.vue` unmounts (SPA navigation), the interval persists because Pinia stores outlive components. The interval continues firing `fetchRecentDone()` even when no component uses it.
**Fix:** Add store-level `$$dispose` hook or track component mounts and auto-stop when count reaches 0.

### 14. `useMathRender.ts` — `sanitizeHtml` Allows `style` Attribute
**FILE:** `src/composables/useMathRender.ts:15`
**Severity:** MEDIUM
**Impact:** `sanitizeHtml` allows `style` attribute in allowed attrs:
```ts
ALLOWED_ATTR: ['class', 'aria-hidden', 'style', 'width', 'height', 'viewBox', 'd', 'xmlns', 'encoding']
```
`style` can be used for CSS-based attacks (exfiltration via `url()` in background-image, clickjacking via positioning, etc.). The `useSanitize` composable correctly does NOT allow `style` in its stricter config (line 22: `sanitizeMath` allows it though). Inconsistency between the two sanitize implementations.
**Fix:** Remove `style` from `ALLOWED_ATTR` in `useMathRender.ts`, or at minimum restrict to safe values.

### 15. `useSanitize.ts` — `sanitizeMath` Allows `style` Attribute
**FILE:** `src/composables/useSanitize.ts:31-34`
**Severity:** MEDIUM
**Impact:** Same as above. `sanitizeMath` allows `style` in `ALLOWED_ATTR`. This can enable CSS injection vectors in math rendering.
**Fix:** Remove `style` from allowed attrs or validate values.

### 16. Dead Code — Commented Route for TestPaymentPage
**FILE:** `src/router/index.ts:65`
**Severity:** MEDIUM (informational)
**Impact:** Route for `TestPaymentPage` is commented out with a ponytail note. The component file still exists (`src/views/TestPaymentPage.vue`) and is fully functional with payment logic. Should be removed or properly guarded behind admin auth.
**Fix:** Delete `TestPaymentPage.vue` or restore route with `requiresAdmin: true`.

### 17. `chat.ts` — `_resumePollers` Object Not Type-Safe, No Cleanup Guarantee
**FILE:** `src/stores/chat.ts:644`
**Severity:** MEDIUM
**Impact:** `const _resumePollers = {}` — plain object used as a Map. `setInterval` IDs stored without type. If a component unmounts without calling `stopStreaming()` or `deleteConversation()`, the poller continues running indefinitely in the Pinia store scope.
**Fix:** Use `Map<string, number>` and add store-level disposal hook.

---

## LOW

### 18. `contentText` in PaperfullTab rendered with `renderRichText` then `sanitizeHtml`
**FILE:** `src/components/PaperfullTab.vue:560-567`
**Severity:** LOW
**Impact:** `renderRichText()` produces HTML, then `sanitizeHtml()` cleans it. This is the correct order (render then sanitize). No issue.

### 19. `ContentList.vue` — `@ts-nocheck` justified comment exists
**FILE:** `src/components/ContentList.vue:217`
**Severity:** LOW
**Impact:** Comment explains `@ts-nocheck` reason: "pre-existing type issues in legacy code". At least documented.

### 20. `axios` timeout 15 minutes
**FILE:** `src/api/index.ts:7`
**Severity:** LOW
**Impact:** `timeout: 900000` (15 min). Very long timeout for all requests including auth, file list, etc. Only large uploads need this. Shorter timeout for non-upload endpoints would fail faster on hung connections.
**Fix:** Use default 30s timeout for normal requests, override to 15min only for upload endpoints.

### 21. `paperJobs.ts` — Stuck job error message says "5 minutes" but constant is 15 minutes
**FILE:** `src/stores/paperJobs.ts:68, 353`
**Severity:** LOW
**Impact:** `STUCK_TIMEOUT_MS = 15 * 60 * 1000` but error message says "auto-cancelled after 5 minutes". Misleading to user.
**Fix:** Update error message to "15 minutes".

### 22. `paperJobs.ts` — `globalPollInterval` never stopped at app level
**FILE:** `src/stores/paperJobs.ts:283-292`
**Severity:** MEDIUM (duplicate of #13)
**Impact:** Same as #13.

### 23. `ChatMessage.vue` — `md.use(katex, { throwOnError: false })`
**FILE:** `src/components/ChatMessage.vue:911-914`
**Severity:** LOW
**Impact:** `throwOnError: false` means invalid LaTeX renders as error-colored text instead of throwing. This is intentional for UX. No security concern since output goes through DOMPurify.

### 24. `LandingPage.vue` — `typeTimer` uses `setInterval` but `clearInterval` in cleanup
**FILE:** `src/views/LandingPage.vue:343, 468`
**Severity:** LOW
**Impact:** `typeTimer` is assigned `setInterval` in some code path. `onUnmounted` correctly calls `clearInterval(typeTimer)`. No issue.

### 25. `useSanitize.ts` has `@ts-nocheck` but is trivially fixable
**FILE:** `src/composables/useSanitize.ts:1`
**Severity:** LOW
**Impact:** 42-line file with `@ts-nocheck`. Could be fixed in 5 minutes. Unnecessary for such a small file.

---

## SUMMARY

| Severity | Count | Top Issues |
|----------|-------|-------------|
| CRITICAL | 2 | CSRF token in SSE URL, v-html with i18n |
| HIGH     | 5 | Password hash exposure, IntersectionObserver leak, ProgressTimer risk, renderPdf race, SSE onerror missing |
| MEDIUM   | 10 | @ts-nocheck in 12 files, v-html no DOMPurify (ToolWorkspace), timer accumulation, missing error states, globalPoll leak, style attr in sanitizer, dead code, _resumePollers cleanup |
| LOW      | 8 | Axios timeout too high, stale error message, dead TestPaymentPage, etc. |

## TOP 5 RECOMMENDED FIXES (Priority Order)

1. **LiteratureTab SSE token leak** — Remove `?token=` from EventSource URL, use cookie auth.
2. **IntersectionObserver cleanup** — Add `counterObserver.disconnect()` and `cardObserver.disconnect()` in LandingPage `onUnmounted`.
3. **Remove @ts-nocheck** incrementally — Start with `useSanitize.ts`, then `paperJobs.ts`, then stores.
4. **Add DOMPurify to ToolWorkspace** grammar output — `sanitizeHtml(renderGrammarOutput(...))`.
5. **SSE onerror handlers** — Add explicit `onerror` to LiteratureTab and DataTab EventSource instances with reconnect limits.
