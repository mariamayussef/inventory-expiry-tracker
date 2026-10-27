# Backup and restore

Back up the entire PostgreSQL database, not just product quantities. Ledger, command keys, import stages, audit records, alert states and settings must be recovered consistently. Backups also contain authentication material; restrict permissions and encrypt off-device backups.

## Docker

```sh
mkdir -p backups
chmod 700 backups
docker compose exec -T db pg_dump -U inventory -d inventory -Fc > backups/inventory.dump
# Stop API and worker before restoring into an EMPTY database:
docker compose stop api worker
# Use a new target database to avoid mutating the only surviving copy.
docker compose exec db createdb -U inventory inventory_restore
docker compose exec -T db pg_restore -U inventory -d inventory_restore --no-owner < backups/inventory.dump
```

Point DATABASE_URL at the restored database, start API, sign in and run Settings → reconciliation. Verify physical total equals ledger total, zero negative batches, expected users/movements/import counts. Check that failed/unfinished imports did not become posted. Review in-app alerts against the current business date. Only switch operational traffic after verification. Do not run demo seeding on restored data.

## Local PostgreSQL

```sh
pg_dump "$DATABASE_URL" -Fc -f /secure/path/inventory.dump
createdb inventory_restore
pg_restore --no-owner --dbname=postgresql://USER:PASS@127.0.0.1:55432/inventory_restore /secure/path/inventory.dump
```

Install PostgreSQL client tools separately for this local procedure: the optional development binary package contains only the server, initdb, and pg_ctl. Use pg_dump/pg_restore versions equal to or newer than the server. After installing them, `PYTHONPATH=. .venv/bin/python scripts/check-backup.py` can verify a dump/restore using a new disposable database. The `.local/postgres` directory persists across launcher shutdowns; do not copy a running cluster directory as a substitute for a logical backup.

Never use `docker compose down -v` or delete `.local/postgres` unless you intend to destroy that database and have a verified backup. Normal `docker compose down` preserves the volume. Test a restore periodically; a backup file alone is not proof of recoverability.

## Restart verification

See `docs/TEST_RESULTS.md` for actual before/after database restart totals and browser checks for the recorded validation run.
