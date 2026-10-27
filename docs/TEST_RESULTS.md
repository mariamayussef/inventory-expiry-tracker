# Actual validation results

Executed locally on **2026-10-27** against **real PostgreSQL 18.4**, using the persistent local binary launcher. Main demo and disposable integration-test databases are separate. No SQLite/in-memory database substitute was used.

## Automated integration suite

Command: `.venv/bin/python -m pytest backend/tests -q`

**25 passed**, approximately 3.4 seconds. One third-party deprecation warning: Starlette's test client references AnyIO's deprecated BlockingPortal alias. No application test failures remain.

| Acceptance area | Actual checks |
| --- | --- |
| Ledger and reconciliation | Receipt → two issues → exact remaining batch/product stock; summed batch and ledger effects agree |
| Concurrency | Two real concurrent transactions compete for the same final 5 units; one 200, one 409, final balance 0 |
| Duplicate commands | Same key/input returns identical response, different input 409; single ledger write |
| FEFO | Early expiry, deterministic ties, split pick, shortfall, stale preview 409 with refreshed suggestion and no partial post |
| Date boundaries | Expiry today usable at minimum zero; Istanbul/UTC date split at 21:01 UTC; minimum shelf life excludes today |
| Restrictions | Expired/quarantined stock physically retained and excluded from picks; dashboard category precedence |
| Returns/corrections | Linked return limit, quarantine release, write-off, supplier deduction, issue-with-return reversal rejection, duplicate reversal rejection |
| Precision and dates | Whole-unit fractions, zero/negative/NaN/Infinity, excessive scale, JSON floats, invalid dates/order, lot-date conflicts, established unit change rejection |
| Imports | Preview has no stock effect; duplicate rows; mapped headers; selected date interpretation; XLSX; unknown SKU; atomic rollback after revalidation failure; safe retry |
| Alerts | Dedup, acknowledgement preservation, resolve, reopen and occurrence increment |
| Authorization | Viewer and operator blocked on administrative/product/settings/status/import/user/stock routes; viewer blocked on movements and acknowledgement; permitted operator flows succeed |
| Exports/security | Active product filter, formula escaping CSV/XLSX, timezone metadata; session login/logout, cookie flags, origin rejection, unauthenticated access denial |
| Input boundaries | Declared unit injection, backdating, malformed movement and missing FEFO product rejected |
| Non-expiring stock | Creation-order fallback and null-expiry eligibility |
| Immutability | Database rejects direct movement UPDATE; stock survives independent connection lifecycle |

Tests reset only a database whose name begins with `inventory_test`.

## Frontend build

`pnpm --dir frontend build`: **passed**. TypeScript strict type check and Vite production bundle both succeed (1,578 transformed modules). Dependency install from the final pnpm lockfile also succeeded. Python modules compiled successfully. Exact resolved Python versions are in `backend/requirements.lock`; JavaScript versions in `pnpm-lock.yaml`.

## Browser E2E

`node scripts/e2e.mjs`: **passed** using actual headless Google Chrome against http://127.0.0.1:8000.

Login → receive 12 Whole milk units into a new explicitly dated lot → review/confirm → issue 2 units using a confirmed FEFO suggestion → expiry review → Expired filter → matching downloadable CSV with timezone metadata. No browser exceptions. The test posts labelled fictional demo movements; it does not operate on private records.

Desktop screenshots were inspected. The mobile check uses a 390 × 844 viewport, waits for responsive transition completion, and asserts no page-level horizontal overflow. Wide data tables scroll within their containers. `scripts/ui-smoke.mjs` additionally exercises all nine views, mobile navigation and status filtering. Screenshots live under `.local/screenshots/` (ignored).

Initial browser checks caught a missing accessible select label and a test navigation race; both were corrected before the successful run. Requests from superseded frontend views are now discarded to prevent stale list results during navigation.

## Real shutdown/restart

Stopped both the application and PostgreSQL, restarted the same `.local/postgres` directory, and compared the entire ordered ledger and every batch balance using `scripts/check-persistence.py`.

**Passed:** 37 posted movements, physical total **2500.000**, same SHA-256 digest before and after:

```
6b08255b95c487768412eb0efff9ab1ce695d309e5e6daea50883309908cd68f
```

Later E2E runs intentionally add more demo movements, so current demo totals can differ from this recorded restart checkpoint. No stock was automatically removed due to expiry. The separate alert worker was started and reported a successful check for business date 2026-10-27.

## Not executed / practical limits

- Docker Compose build/start: **not executed**, because Docker is absent on this machine. Dockerfile/Compose and a separate empty-production bootstrap path are supplied.
- Logical backup/restore: **not executed**. The development binary package contains server tools only, and pg_dump/pg_restore are not installed. The verification attempt stopped before creating a dump or restore database. Install PostgreSQL 18 client tools and run `scripts/check-backup.py`; documented Docker/local backup procedures are in BACKUP_RESTORE.md.
- No public deployment, real emails, paid infrastructure, real customer pilot, load/penetration testing, measured business savings, or production operational certification.
- Movement list/export limit is 5,000; audit is 1,000; imports are 500 rows/2 MB. No pagination, password-reset UI, distributed auth throttle, camera scanner, or arbitrary historical movement import. Expiry uses a table instead of a month grid.
