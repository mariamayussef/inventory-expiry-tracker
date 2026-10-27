"""Run before and after stopping/restarting PostgreSQL; compares complete ledger digest."""
import sys,json,hashlib
from pathlib import Path
from backend.db import connection
from backend.domain import clean
with connection() as c:
    movements=c.execute('SELECT * FROM movements ORDER BY id').fetchall()
    batches=c.execute('SELECT batch_id,sum(effect) AS physical FROM movements GROUP BY batch_id ORDER BY batch_id').fetchall()
    snapshot={'movements':len(movements),'ledger_digest':hashlib.sha256(json.dumps(clean(movements),sort_keys=True).encode()).hexdigest(),'batches':clean(batches),'physical':str(sum(row['physical'] for row in batches))}
path=Path('.local/persistence-before.json')
if sys.argv[1]=='before':
    path.write_text(json.dumps(snapshot,indent=2));print('BEFORE:',snapshot['movements'],'movements, physical',snapshot['physical'],snapshot['ledger_digest'])
else:
    assert json.loads(path.read_text())==snapshot,'Persistence mismatch'
    print('PASS AFTER RESTART:',snapshot['movements'],'movements, physical',snapshot['physical'],snapshot['ledger_digest'])
