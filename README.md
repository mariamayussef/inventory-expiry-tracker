# Stockroom · Inventory & Product Expiry Tracker

A single-warehouse inventory and product expiry application. React + TypeScript, FastAPI, PostgreSQL. Stock totals come from an immutable database ledger; the dashboard reflects recorded stock movements. Fictional demo data is opt-in.

## Local demo

After setup, open **http://127.0.0.1:8000** and sign in with the administrator account you created. No account credentials or local database are included in this repository. The optional demo seed creates 24 fictional products; use `DEMO_TODAY=2026-10-27` to reproduce its dated scenarios.

See [GitHub upload instructions](docs/GITHUB_SETUP.md) for publishing the source repository.

## Non-Docker setup

Requirements: Python 3.12, Node 22+, pnpm 10 or 11, PostgreSQL 18 (or the included development-only binary launcher).

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.lock
pnpm install
pnpm --dir frontend build
```

Choose a database:

```sh
# Terminal 1: optional bundled PostgreSQL binary launcher.
# Uses persistent .local/postgres, loopback only, port 55432.
# Development-only database credentials: inventory / inventory.
pnpm db:local
```

Or create an empty `inventory` database on your own PostgreSQL server and set `DATABASE_URL`. The API defaults to the development launcher URL `postgresql://inventory:inventory@127.0.0.1:55432/inventory`. Production must set a private URL and unique credentials.

```sh
# Terminal 2: EMPTY production-style setup (prompts for a unique password)
source .venv/bin/activate
python -m backend.db
python -m backend.manage admin --username admin
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Alternatively, for a **fresh, empty demo database**, replace the admin command with:

```sh
export DEMO_TODAY=2026-10-27
python -m backend.manage demo --username mariam
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Keep `DEMO_TODAY` consistent for seed, API, and worker. Without it, the server uses the current date in the configured business timezone. Bootstrap refuses to reset an existing account or reseed a populated catalog. `BOOTSTRAP_PASSWORD` can supply a password non-interactively; it is never printed. Do not put secrets in shell history or source control.

```sh
# Terminal 3: scheduled in-app checks, every 300 seconds by default
source .venv/bin/activate
python -m backend.worker
# Frontend development, if needed (proxies API, same-origin session):
pnpm --dir frontend dev
```

After initial setup, `DEMO_TODAY=2026-10-27 bash scripts/start-local.sh` starts the local database (if needed), API and alert worker together. Stop existing API/worker processes before using this helper. Omit the date override for operational use.

## Docker Compose

Copy `.env.example` to `.env`, set a unique URL-safe `POSTGRES_PASSWORD`, and run:

```sh
docker compose up --build -d
docker compose exec api python -m backend.manage admin --username admin
# Or, ONLY for an empty demo database:
# set DEMO_TODAY=2026-10-27 in .env before startup
# docker compose exec api python -m backend.manage demo --username mariam
```

Open http://localhost:8000. PostgreSQL has a persistent named volume and no exposed host port. The API and worker apply versioned SQL migrations under an advisory lock. Docker itself was unavailable in the build environment; use the locally verified path above if troubleshooting. Compose configuration is supplied but was not executed here.

## Demo walkthrough

1. Sign in. Overview shows database-derived stock and distinct quantity buckets.
2. Products → search `STK-1002` or scan its barcode using a keyboard scanner. Open the detail drawer to inspect lots.
3. Receive stock → select Whole milk, a new lot, explicit expiry, positive exact quantity, and reason → review → confirm.
4. Movements → Issue / return / adjust → select product and quantity → preview FEFO → review lots → confirm. The preview is not a reservation.
5. Expiry tracker → filter Expired or Expires today → inspect a lot → Export downloads the same filter.
6. From an issue movement, Return creates a linked quarantine lot. Administrator opens that batch and records a review reason to release or retain it; write-off is a separate movement.
7. Imports & exports → download a template → map columns if needed → validate → inspect all errors → explicitly confirm the atomic commit.
8. Alerts → acknowledge an alert. Settings → reconcile the ledger. Audit log records actors, reasons, UTC timestamps, and affected IDs.

## Tests

```sh
# The bundled launcher creates a separate inventory_test database.
TEST_DATABASE_URL=postgresql://inventory:inventory@127.0.0.1:55432/inventory_test \
  .venv/bin/python -m pytest backend/tests -q
pnpm --dir frontend build
# Requires local demo login file and Chrome (CHROME_PATH overrides executable).
node scripts/e2e.mjs
```

Tests refuse a database name not starting with `inventory_test`. They TRUNCATE that disposable database; never point them at real stock. E2E posts clearly labelled demo movements into the demo database. See [test results](docs/TEST_RESULTS.md) for actual execution evidence.

## Delivered behavior

- Catalog, SKU/barcode lookup, archival, physical vs usable quantities, batch and product detail drawers.
- Receipt/opening, FEFO split issue, linked quarantined return, supplier return, write-off, admin adjustment, guarded reversal.
- Product row locks, transaction-wide picks/imports, idempotent commands, exact Decimal + PostgreSQL NUMERIC, immutable ledger triggers.
- Inclusive expiry dates, configurable timezone/minimum shelf life, deterministic FEFO, receipt-order fallback for undated stock.
- CSV/XLSX templates, column mapping, explicit date formats, staged preview, atomic opening/master imports, safe exports.
- In-app alert reconciliation, deduplication/acknowledgement/resolution/retrigger, scheduled worker and visible last-run status.
- Administrator/operator/viewer API permissions, Argon2 passwords, hashed expiring session tokens, HttpOnly SameSite cookies, origin restrictions.
- Settings, team account creation/role/deactivation, searchable audit trail, reconciliation, local persistence, Docker/local instructions.

## Boundaries

One organization and warehouse. Fractions support three decimal places; no pack conversions or backdating. Product base unit, precision and expiry policy are fixed after stock is posted. Imports support separate new master data and opening stock, not arbitrary historical movement editing. Dashboard sums across mixed base units are explicitly labelled count summaries. Lists/exports of movements are capped at 5,000 rows; audit is capped at 1,000 (no pagination yet). Expiry is a filterable table, not a month-grid calendar. Email is intentionally disabled; no messages are sent.

Settings and master-data writes are audited but do not share the stock-command idempotency contract; product creation does support idempotency. There is no user password reset UI, MFA, production distributed rate limiting, or live multiuser push updates. The login throttle runs within a single application process. An internet deployment needs HTTPS, `SECURE_COOKIES=true`, explicit origins, private database access, secrets management, monitoring, and a deployment security review. No public deployment or paid resources were created.

[Data model](docs/DATA_MODEL.md) · [Stock rules](docs/STOCK_RULES.md) · [Imports & exports](docs/IMPORT_EXPORT.md) · [Backup/restore](docs/BACKUP_RESTORE.md)
