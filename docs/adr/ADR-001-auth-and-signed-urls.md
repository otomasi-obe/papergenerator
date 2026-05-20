# ADR-001: Authentication — JWT Bearer + Short HMAC Signed URLs

**Status:** Accepted (2026-05-20)

## Context
PaperFull serves user-uploaded images, PDFs, and DOCX files referenced from
`<img src>` / `<a href>` / `<iframe src>` tags. Browsers do **not** send
`Authorization` headers for these element types, so the codebase historically
embedded the bearer JWT directly into the URL via `?t=<jwt>`.

This is dangerous: the JWT is logged into nginx access logs (`%(r)s` includes
the query string), browser history, and any cross-origin `Referer`. With a
30-day non-expiring access token, a single leaked URL = 30 days of full account
takeover.

## Decision
Adopt **HMAC-SHA256 signed resource URLs** (`?s=<token>`) for image and file
endpoints, and keep the existing `?t=<jwt>` path live as a deprecated
backward-compat shim until v2.

The signed token format:

    <expiry_unix>.<user_id>.<hex_digest>

where `digest = HMAC-SHA256(SIGNED_URL_SECRET, "scope|resource_id|user_id|expiry")`.

Tokens are:
- **Short-lived** — default TTL 600s, max 3600s.
- **Scoped** — bind to a specific `(scope, paper_id, resource_id)` tuple.
- **Non-revocable individually** — but auto-expire; rotating
  `SIGNED_URL_SECRET` invalidates all live tokens.
- **Stateless** — no DB lookup; verified by recomputing the HMAC.

Endpoint added: `POST /api/papers/<paper_id>/sign` returns `{url, expires_in}`
for the frontend to embed.

## Alternatives Considered
- **Move JWT to httpOnly cookie** — closes localStorage exfil but breaks the
  frontend's existing axios interceptor model and complicates CSRF. Bigger
  refactor; deferred to ADR-005.
- **Pre-signed S3-style URLs only on a CDN** — overkill for this scale.
- **Status quo (`?t=<jwt>`)** — known broken; rejected.

## Consequences
- **Positive:** Image/file URLs no longer leak the bearer JWT into logs,
  history, or referer. Tokens auto-expire. Rotation is one env var.
- **Negative:** Frontend must call `/sign` before embedding URLs. One extra
  request per paper load. Existing live links keep working via the legacy
  `?t=<jwt>` path until removed.
- **Tradeoff:** stateless tokens cannot be individually revoked; relies on
  short TTL.
