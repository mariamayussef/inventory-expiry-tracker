import os
os.environ['DATABASE_URL']=os.getenv('TEST_DATABASE_URL','postgresql://inventory:inventory@127.0.0.1:55432/inventory_test')
if not os.environ['DATABASE_URL'].rsplit('/',1)[-1].startswith('inventory_test'): raise RuntimeError('Tests require a disposable inventory_test database')
os.environ['DEMO_TODAY']='2026-10-27'
import hashlib
from datetime import datetime,timezone,timedelta
import pytest
from fastapi.testclient import TestClient
from backend.app import app,attempts,hasher
from backend.db import connection,migrate
from backend.domain import uid

@pytest.fixture(scope='session',autouse=True)
def schema(): migrate()
@pytest.fixture
def clients():
    with connection() as c:
        c.execute('TRUNCATE sessions,users,products,batches,imports,movements,commands,audit,alerts RESTART IDENTITY CASCADE')
        c.execute("UPDATE settings SET timezone='Europe/Istanbul',minimum_shelf_days=0,alert_days=30,last_alert_run=NULL WHERE id=1")
        users={}; cs={}
        for role in ['administrator','operator','viewer']:
            ident=uid(); token='test-'+role
            c.execute('INSERT INTO users(id,username,password_hash,role) VALUES(%s,%s,%s,%s)',(ident,role,hasher.hash('test-password-123') if role=='administrator' else 'unused',role))
            c.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',(hashlib.sha256(token.encode()).hexdigest(),ident,datetime.now(timezone.utc)+timedelta(hours=1)))
            cs[role]=TestClient(app);cs[role].cookies.set('stockroom_session',token); users[role]=ident
    attempts.clear()
    yield cs
    for client in cs.values():client.close()
@pytest.fixture
def client(clients): return clients['administrator']
def product(client,**kw):
    r=client.post('/api/products',json={'sku':'P-'+uid()[:8],'name':'Example product','threshold':'5',**kw},headers={'Idempotency-Key':uid()});assert r.status_code==200,r.text;return r.json()['id']
def move(client,p,kind='receipt',quantity='10',**kw):
    data={'type':kind,'product_id':p,'quantity':quantity,'reason':'Integration test','lot':'LOT-A','expiry_date':'2026-12-31',**kw}
    return client.post('/api/movements',json=data,headers={'Idempotency-Key':kw.pop('key',uid())})
def issue(client,p,quantity='1',**kw):
    suggestion=client.post('/api/fefo',json={'product_id':p,'quantity':quantity}).json()
    return move(client,p,'issue',quantity,expected_lines=suggestion['lines'],**kw)
