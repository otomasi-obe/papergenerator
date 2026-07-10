# PaperFull Bug & Compliance Gap Report

Date: 2026-07-05
Scope: paperfull.app frontend, proxy server, static information pages, payment/refund/legal claims.

## Executive Summary

Audit found two categories:

1. **Operational bugs** — routing, CSP, caching, SEO, static-page behavior.
2. **Policy vs system gaps** — claims written in Terms/Privacy/Refund/FAQ/Contact that are not fully implemented in the web system.

Emergency login issue was caused by stale/zombie proxy process serving old CSP. That is already fixed.

---

## Priority List — Highest to Lowest

### P0 — Critical / Legal or Payment Risk

| ID | Issue | Area | Impact | Current Status | Recommended Fix |
|---|---|---|---|---|---|
| P0-1 | User account deletion is promised but no self-delete endpoint/UI exists | Privacy / PDP | Legal compliance gap under UU PDP | Not implemented | Add delete-account request or self-delete endpoint with audit trail |
| P0-2 | Data access/export rights are promised but no export endpoint exists | Privacy / PDP | Legal compliance gap | Not implemented | Add user data export endpoint/download |
| P0-3 | Restriction/object-to-processing rights are promised but no workflow exists | Privacy / PDP | Legal compliance gap | Not implemented | Add request workflow or make wording manual/email-based |
| P0-4 | Email notifications/policy update notices are promised but no email infrastructure exists | Privacy / Terms | User communication claim unsupported | Not implemented | Either implement email system or revise copy to manual website notice |
| P0-5 | Refund processing/review SLA is written but no refund backend/workflow exists | Refund | Payment dispute risk | Not implemented | Add manual refund request form/status or revise wording to email-only manual process |
| P0-6 | Double-charge detection is mentioned but no duplicate payment detection exists | Refund / Payment | User trust and dispute risk | Not implemented | Add idempotency/double-payment checks or revise wording |

### P1 — High / User Flow or Security

| ID | Issue | Area | Impact | Current Status | Recommended Fix |
|---|---|---|---|---|---|
| P1-1 | Static information page language switch only changes button label, not page content | Information pages | User sees broken language switch | Open | Add real ID/EN content switching or remove EN toggle |
| P1-2 | Contact form is implied/expected but contact page is static only | Contact | No structured support workflow | Not implemented | Add contact form endpoint or keep page as email/phone only |
| P1-3 | Admin account suspension/termination mentioned but no suspension feature exists | Terms/Admin | Abuse handling gap | Not implemented | Add user status/suspension field and admin action |
| P1-4 | Phone number collection claimed but user model has no phone field | Privacy | Incorrect privacy statement | Not implemented | Remove claim or add optional phone field |
| P1-5 | 17+ age eligibility stated but no age verification exists | Terms | Policy gap | Not implemented | Add checkbox confirmation at registration or revise wording |

### P2 — Medium / SEO, Security Hardening, Maintenance

| ID | Issue | Area | Impact | Current Status | Recommended Fix |
|---|---|---|---|---|---|
| P2-1 | Static pages missing full security headers compared with SPA | Static pages | Inconsistent hardening | Open | Apply shared security headers to static page handler |
| P2-2 | Sitemap missing public pages such as `/register`, `/pricing`, `/generate` | SEO | Reduced indexing quality | Open | Update sitemap with correct public pages only |
| P2-3 | Sitemap includes auth-gated/low-value pages like `/dashboard` | SEO | Search engines index poor pages | Open | Remove auth-required routes from sitemap |
| P2-4 | `privacy.md` missing in `public/page-content-md/` | Content maintenance | Future content scripts may miss privacy page | Open | Add privacy.md mirror |
| P2-5 | Static pages missing `og:image` | SEO/social sharing | Weak link previews | Open | Add `og:image` meta tags |
| P2-6 | Data retention cleanup for 2-year retention claim is not automated | Privacy | Operational/legal gap | Not implemented | Add scheduled cleanup or revise wording |
| P2-7 | Template request workflow mentioned but not implemented | FAQ/Product | User expectation gap | Not implemented | Add request form or revise copy to manual email |

### P3 — Low / UX, Edge Cases, Polish

| ID | Issue | Area | Impact | Current Status | Recommended Fix |
|---|---|---|---|---|---|
| P3-1 | `/terms.html`, `/refund.html`, etc. directly accessible and duplicate canonical pages | SEO | Duplicate content risk | Open | Redirect `.html` URLs to extensionless URLs |
| P3-2 | Very long URLs return 500 instead of 414 | Proxy | Poor error semantics | Open | Catch URI too long and return 414 |
| P3-3 | `href="#"` placeholder links may exist in static pages | UX | Click does nothing or jumps top | Open | Replace with real URLs or buttons |
| P3-4 | External Google Fonts on static pages are render-blocking | Performance | Small performance hit | Open | Use system fonts or preload/self-host |
| P3-5 | No server-side gzip/brotli outside Cloudflare path | Performance | Local/direct traffic slower | Open | Add compression or rely on Cloudflare only |
| P3-6 | Missing `Content-Length` headers | Performance/proxy compatibility | Minor efficiency issue | Open | Add file size to headers |

---

## Already Fixed Before This Report

| Issue | Fix |
|---|---|
| Login page blank/404-like behavior | Fixed CSP and killed zombie proxy process |
| CSP blocked cdn.jsdelivr.net / Google Fonts | Added allowed sources to HTTP CSP |
| Meta CSP leaked localhost:8001 | Removed meta CSP from index.html |
| Hashed JS assets cached only 1 hour | Fixed asset cache regex to support `/assets/js/...` |
| Trailing slash redirect dropped query params | Preserves `url.search` now |
| `.jpg` MIME was `image/jpg` | Changed to `image/jpeg` |
| Static page language button redirected to landing | Redirect removed, but content switching still not real |

---

## Recommended Fix Order — Easy to Hard

1. **Fix language switch on 5 information pages** — low code risk, high UX benefit.
2. **Update sitemap and add `privacy.md`** — low risk.
3. **Add `og:image` to static pages** — low risk.
4. **Apply full security headers to static pages** — medium risk, must test external fonts/maps.
5. **Redirect `.html` variants to canonical extensionless URLs** — medium SEO/routing risk.
6. **Fix long URL 414 handling** — low/medium proxy risk.
7. **Review legal copy to avoid unsupported claims** — safest short-term compliance fix.
8. **Build real request workflows: refund, account deletion/export, contact form** — higher complexity, requires backend/UI/database.

---

## Confirmation Policy Before Fixes

Before changing any bug, list:

- What will change
- Risk if changed
- How it will be tested
- Rollback path

Then wait for approval.
