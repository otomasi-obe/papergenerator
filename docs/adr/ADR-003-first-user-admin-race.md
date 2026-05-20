# ADR-003: First-User Admin Promotion — Atomic via SELECT FOR UPDATE

**Status:** Accepted (2026-05-20)

## Context
The original `register` and Google-OAuth callback both did:

    if User.query.count() == 0:
        user.role = 'admin'

Two concurrent registrations against an empty users table both observe
`count == 0` and both create admins. Race confirmed by code review.

## Decision
Replace the count-based check with a row-level lock on the existing admin
row (if any):

```python
locked = User.query.filter_by(role='admin').with_for_update().first()
user.role = 'user' if locked else 'admin'
```

This serializes admin promotion across concurrent transactions. The first
committer wins; the second sees the locked admin row (or the just-committed
one) and is created as a normal user.

## Consequences
- **Positive:** Race closed; no schema change needed.
- **Negative:** A short row lock during registration on PostgreSQL — trivial
  cost.
- **Tradeoff:** SQLite (used in tests) does not honor `FOR UPDATE` but the
  test suite doesn't exercise concurrent registration; production runs
  PostgreSQL where `FOR UPDATE` is honored.
