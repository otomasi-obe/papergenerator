# PaperFull Information Pages — Claims / System Gap Tracker

Date: 2026-07-05
Scope: `/terms`, `/refund`, `/privacy`, `/faq`, `/contact`

Purpose: keep a backlog of legal/policy/support claims that are written in public information pages but are not fully implemented in the product yet. Use this when adding future features.

## High Priority

| Page | Claim / Ketentuan | Current System Status | Future Implementation |
|---|---|---|---|
| Privacy | Pengguna dapat meminta penghapusan data pribadi, diproses maksimal 14 hari kerja | Manual email only; no endpoint/request tracking | Add data deletion request workflow, admin queue, SLA status |
| Privacy | Pengguna berhak meminta salinan/akses data pribadi | No export/download endpoint | Add user data export endpoint and downloadable file |
| Privacy | Pengguna berhak pembatasan pemrosesan dan keberatan pemrosesan data | No workflow | Add privacy request workflow or manual request tracking |
| Privacy | Perubahan kebijakan diinformasikan via email/platform | No email notification system; update banner is generic | Add policy notice system and/or email notification |
| Refund | Pengajuan refund direview maksimal 3 hari kerja | Manual email only; no refund ticket/status | Add refund request form/status/admin review queue |
| Refund | Refund diproses 3–7 hari kerja setelah disetujui | No gateway refund API integration | Add payment-gateway refund integration or manual payout tracking |
| Refund | Double charge qualifies for refund | No duplicate-payment detection | Add idempotency/double-payment detection by transaction ID/user/amount/time |
| Refund | Refund can be returned as Paperfull account balance | No wallet/balance system; only token/quota exists | Add wallet/refund credit model or remove this claim |

## Medium Priority

| Page | Claim / Ketentuan | Current System Status | Future Implementation |
|---|---|---|---|
| Terms | User must be 17+ or have guardian permission | No age checkbox / birthdate / guardian consent | Add registration checkbox or revise wording |
| Terms | Paperfull can suspend/terminate violating accounts | Admin has no suspend/ban status | Add `user.status` and admin suspend/restore action |
| Terms | Terms changes will be informed via platform | Generic update banner exists, no policy-specific notice | Add policy notice/changelog type |
| Privacy | Phone number is collected at registration | User model/register has no phone field | Remove claim or add optional phone field |
| Privacy | Internal access is monitored and logged | HTTP/API logs exist; no admin/personnel access audit | Add audit log for admin/user-data access |
| Contact | Support/refund help via contact | Email/phone only; no contact form/ticket | Add contact form endpoint or keep page email-only |
| FAQ | Users can request missing journal templates via contact | Manual only; no template request workflow | Add template request form/backlog |

## Low / Copy Mismatch

| Page | Issue | Recommended Copy Fix |
|---|---|---|
| FAQ | Says payment supports transfer bank, e-wallet, QRIS, credit/debit. Current visible flow mostly VA/QRIS/sandbox | Use generic: “metode pembayaran yang tersedia mengikuti payment gateway aktif” |
| Privacy | Mentions iPaymu/Xendit while migration is toward Faspay/DOKU | Use generic: “payment gateway mitra” |
| Refund | Duplicate numbering: section 3 repeated | Renumber sections |
| Refund | `<h2>6. Catatan` missing closing `</h2>` | Fix HTML |
| Static pages | `og:image` is before `<body>` but `</head>` is missing | Restore valid `</head>` structure |

## Short-term Recommendation

Before building backend features, revise public copy so it matches current operational reality:

1. Refund is manual via email/contact.
2. Data rights requests are manual via email/contact.
3. Remove phone collection claim unless phone field is added.
4. Remove wallet/saldo refund claim unless wallet exists.
5. Payment method wording should follow the active gateway.

## Long-term Feature Backlog

- Privacy request center: deletion/export/restriction/objection.
- Refund request system: request form, admin queue, SLA status, gateway refund integration.
- Contact/support ticket form.
- User suspension/admin moderation.
- Policy notice/email notification system.
- Optional phone field or remove all phone-collection claims.
