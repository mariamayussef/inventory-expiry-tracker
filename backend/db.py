import os
from pathlib import Path
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

URL = os.getenv('DATABASE_URL', 'postgresql://inventory:inventory@127.0.0.1:55432/inventory')
@contextmanager
def connection():
    with psycopg.connect(URL, row_factory=dict_row) as c:
        yield c

def migrate():
    with connection() as c:
        c.execute('SELECT pg_advisory_xact_lock(1902101)')
        exists = c.execute("SELECT to_regclass('public.schema_migrations') AS t").fetchone()['t']
        for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
            version = int(path.name.split('_')[0])
            if not exists or not c.execute('SELECT 1 FROM schema_migrations WHERE version=%s', (version,)).fetchone():
                c.execute(path.read_text())
                exists = True

if __name__ == '__main__':
    migrate()
    print('Migrations applied')
