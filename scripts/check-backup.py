"""Local development verification: dump and restore to a NEW temporary database."""
import os,subprocess,hashlib,json,shutil
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from backend.db import URL,connection
from backend.domain import clean,uid
dump=shutil.which('pg_dump'); restore=shutil.which('pg_restore')
if not dump or not restore: raise SystemExit('Install PostgreSQL 18 client tools (pg_dump and pg_restore) to run backup verification; bundled development binaries contain only the server.')
backup=Path('.local/demo-verification.dump')
subprocess.run([dump,'--dbname',URL,'-Fc','-f',str(backup)],check=True)
backup.chmod(0o600)
name='inventory_restore_check_'+uid().replace('-','')[:8]
with psycopg.connect(URL,autocommit=True) as c: c.execute('CREATE DATABASE '+name)
restore_url=URL.rsplit('/',1)[0]+'/'+name
subprocess.run([restore,'--dbname',restore_url,'--no-owner',str(backup)],check=True)
def snapshot(url):
    with psycopg.connect(url,row_factory=dict_row) as c:
        records=c.execute('SELECT * FROM movements ORDER BY id').fetchall()
        return len(records),hashlib.sha256(json.dumps(clean(records),sort_keys=True).encode()).hexdigest()
a=snapshot(URL);b=snapshot(restore_url);assert a==b
print('PASS: pg_dump → pg_restore to',name,';',a[0],'immutable ledger records, identical SHA-256',a[1])
# Only remove the fresh verification database created by this script, never the source.
with psycopg.connect(URL,autocommit=True) as c: c.execute('DROP DATABASE '+name)
