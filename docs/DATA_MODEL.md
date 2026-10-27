# Data model

`backend/migrations/001_initial.sql` is the initial versioned schema. `python -m backend.db` applies missing migrations inside a transaction protected by a PostgreSQL advisory lock. Add numbered SQL files for future migrations; do not edit already-applied migrations.

| Table | Meaning and constraints |
| --- | --- |
| products | UUID, unique SKU, optional unique barcode, name/category/base unit, whole-unit flag, expiry flag, low-stock threshold, archive flag |
| batches | UUID, product FK, unique product + lot, manufacture/expiry dates, supplier, location, available/quarantine/blocked/archived status, creation timestamp |
| movements | Immutable UUID, product and batch FKs, movement type, positive requested quantity, signed effect, reference/reason, actor, UTC timestamp, source issue/reversal/import FKs |
| commands | Unique idempotency key, canonical request fingerprint, actor, stored JSON response; saved in same transaction as stock |
| imports | UUID, bounded normalized rows, validation errors, staging actor/time, commit timestamp |
| users / sessions | Role and Argon2 password hash; opaque tokens stored only as SHA-256 digests with expiry |
| audit | Append-only through API, actor, action, affected record ID, details/reason, recorded timestamp |
| alerts | Unique entity + condition key, kind, message, open/acknowledged/resolved state, acknowledgement actor, occurrence count |
| settings | Single row: business timezone, minimum shelf life, alert window, last successful check |

## Source of truth

**Physical balance = SUM(movements.effect) by batch.** Product physical stock is the sum of its batch balances. There is deliberately no cached balance table. Read endpoints derive usable balances from physical stock plus status, active flag, business date, and minimum shelf life.

Stock commands lock the product row before reading or writing its batches/ledger. This serializes all commands for that product, including quarantine release and archival, while allowing different products to transact independently. Split FEFO picks remain within one transaction. Opening imports lock affected products in UUID order. Idempotency-key advisory locking serializes duplicate requests before the fingerprint check. Rollback removes the command response along with stock changes if any line fails.

Database triggers reject UPDATE/DELETE of movements and prevent established unit/precision/expiry-policy changes. Normal API paths expose no destructive stock-history endpoints. Database owners remain powerful: restrict direct database access, use backups, and never operate via ad hoc ledger edits.

There are no cost, invoice, accounting, personal contact, marketplace, or tenant tables.
