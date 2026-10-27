import io,csv,hashlib
from decimal import Decimal
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook,load_workbook
from backend.app import app
from backend.db import connection
from backend.domain import uid,classification
from conftest import product,move,issue

def test_receipt_multiple_issues_reconciliation(client):
    p=product(client);assert move(client,p,quantity='20').status_code==200
    assert issue(client,p,'6').status_code==200;assert issue(client,p,'9').status_code==200
    b=client.get('/api/batches').json()[0]; assert Decimal(b['physical'])==5
    ps=client.get('/api/products').json();assert Decimal(ps[0]['usable'])==5
    r=client.get('/api/reconcile').json();assert r['physical']==r['ledger'] and r['negative_batches']==[]

def test_concurrent_last_units(client):
    p=product(client);move(client,p,quantity='5')
    lines=client.post('/api/fefo',json={'product_id':p,'quantity':'5'}).json()['lines']
    def deduct(_):
        with TestClient(app) as other:
            other.cookies.update(client.cookies)
            return move(other,p,'issue','5',expected_lines=lines).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(deduct,range(2)))
    assert sorted(results)==[200,409]
    assert Decimal(client.get('/api/batches').json()[0]['physical'])==0

def test_idempotent_and_conflicting_reuse(client):
    p=product(client);data={'type':'receipt','product_id':p,'quantity':'8','lot':'ONE','expiry_date':'2027-01-01','reason':'Receive'};headers={'Idempotency-Key':uid()}
    a=client.post('/api/movements',json=data,headers=headers); b=client.post('/api/movements',json=data,headers=headers)
    assert a.status_code==b.status_code==200 and a.json()==b.json()
    assert client.post('/api/movements',json={**data,'quantity':'9'},headers=headers).status_code==409
    assert len(client.get('/api/movements').json())==1

def test_fefo_order_ties_split_shortfall_and_stale(client):
    p=product(client)
    for lot,expiry in [('LATE','2026-12-01'),('EARLY','2026-10-28'),('TIE','2026-10-28')]:assert move(client,p,quantity='3',lot=lot,expiry_date=expiry).status_code==200
    suggest=lambda n:client.post('/api/fefo',json={'product_id':p,'quantity':n}).json()
    lines=suggest('7')['lines'];assert [x['lot'] for x in lines]==['EARLY','TIE','LATE'];assert [Decimal(x['quantity']) for x in lines]==[3,3,1]
    assert Decimal(suggest('10')['shortfall'])==1
    assert issue(client,p,'2').status_code==200
    stale=move(client,p,'issue','7',expected_lines=lines);assert stale.status_code==409 and 'suggestion' in stale.json()['detail']
    assert Decimal(client.get('/api/reconcile').json()['physical'])==7

def test_expiry_quarantine_and_minimum_shelf(client):
    p=product(client)
    move(client,p,lot='EXPIRED',expiry_date='2026-10-26',quantity='3')
    move(client,p,lot='TODAY',expiry_date='2026-10-27',quantity='4')
    move(client,p,lot='SOON',expiry_date='2026-10-29',quantity='5')
    bs=client.get('/api/batches').json();assert bs[0]['expiry_status']=='expired';assert bs[1]['expiry_status']=='expires_today'
    assert Decimal(client.get('/api/products').json()[0]['physical'])==12
    assert Decimal(client.get('/api/products').json()[0]['usable'])==9
    assert client.patch('/api/settings',json={'minimum_shelf_days':1}).status_code==200
    assert Decimal(client.get('/api/products').json()[0]['usable'])==5
    client.patch('/api/batches/'+bs[2]['id']+'/status',json={'status':'quarantine','reason':'Inspection'})
    assert Decimal(client.get('/api/products').json()[0]['usable'])==0
    assert Decimal(client.get('/api/products').json()[0]['physical'])==12

def test_timezone_midnight_boundary(client,monkeypatch):
    from backend import domain
    monkeypatch.delenv('DEMO_TODAY')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,26,21,1,tzinfo=timezone.utc)
    with patch.object(domain,'datetime',Clock):
        assert client.get('/api/settings').json()['business_date']=='2026-10-27'
        client.patch('/api/settings',json={'timezone':'UTC'})
        assert client.get('/api/settings').json()['business_date']=='2026-10-26'

def test_return_limits_release_writeoff_and_reversal(client):
    p=product(client);move(client,p,quantity='10'); issued=issue(client,p,'5').json()['movement_ids'][0]
    ret=move(client,p,'customer_return','3',source_issue=issued);assert ret.status_code==200
    assert move(client,p,'customer_return','3',source_issue=issued).status_code==409
    bs=client.get('/api/batches').json(); quarantined=next(b for b in bs if b['status']=='quarantine')
    assert Decimal(quarantined['usable'])==0
    assert move(client,p,'reversal',movement_id=issued).status_code==409
    assert client.patch('/api/batches/'+quarantined['id']+'/status',json={'status':'available','reason':'Inspected packaging'}).status_code==200
    assert move(client,p,'write_off','1',batch_id=quarantined['id']).status_code==200
    assert Decimal(client.get('/api/reconcile').json()['physical'])==7
    r=move(client,p,quantity='2',lot='SECOND').json()['movement_ids'][0]
    assert move(client,p,'reversal',movement_id=r).status_code==200
    assert move(client,p,'reversal',movement_id=r).status_code==409
    assert move(client,p,'supplier_return','100',batch_id=quarantined['id']).status_code==409

@pytest.mark.parametrize('q',['0','-1','1.5','NaN','Infinity','0.0001'])
def test_invalid_whole_quantities(client,q):
    p=product(client);assert move(client,p,quantity=q).status_code==422

def test_exact_fractions_dates_units_and_archive(client):
    p=product(client,whole_units=False,unit='kg')
    assert move(client,p,quantity='1.125').status_code==200
    assert move(client,p,quantity='0.0001').status_code==422
    assert move(client,p,quantity=1.2).status_code==422
    assert move(client,p,expiry_date='2027-01-01').status_code==409
    assert move(client,p,lot='INVALID',expiry_date='2026-02-30').status_code==422
    assert move(client,p,lot='WRONG',manufacture_date='2027-01-01').status_code==422
    assert client.patch('/api/products/'+p,json={'unit':'each'}).status_code==422
    with connection() as c:
        with pytest.raises(Exception):
            with c.transaction():c.execute("UPDATE products SET unit='each' WHERE id=%s",(p,))
    assert client.patch('/api/products/'+p,json={'active':False}).status_code==200
    assert issue(client,p).status_code==409
    assert Decimal(client.get('/api/products').json()[0]['physical'])==Decimal('1.125')

def preview(client,text,kind='opening',**fields):
    return client.post('/api/imports/preview',data={'kind':kind,**fields},files={'file':('stock.csv',text,'text/csv')})
def test_import_preview_commit_retry_and_duplicate(client):
    p=product(client,sku='EXAMPLE');text='sku,lot,expiry_date,quantity\nEXAMPLE,OPEN,2027-01-01,12\n'
    staged=preview(client,text).json();assert staged['can_commit'];assert client.get('/api/batches').json()==[]
    endpoint='/api/imports/'+staged['id']+'/commit';hdr={'Idempotency-Key':uid()}
    assert client.post(endpoint,json={'confirm':False},headers=hdr).status_code==422
    a=client.post(endpoint,json={'confirm':True},headers=hdr);b=client.post(endpoint,json={'confirm':True},headers=hdr)
    assert a.status_code==b.status_code==200 and a.json()==b.json()
    assert client.post(endpoint,json={'confirm':True},headers={'Idempotency-Key':uid()}).status_code==200
    assert Decimal(client.get('/api/reconcile').json()['physical'])==12
    duplicate=preview(client,text+'EXAMPLE,OPEN,2027-01-01,12\n').json();assert not duplicate['can_commit'] and duplicate['errors'][0]['row']==3

def test_atomic_import_revalidation_failure(client):
    p=product(client,sku='A');product(client,sku='B')
    s=preview(client,'sku,lot,expiry_date,quantity\nA,LOT,2027-01-01,2\nB,LOT,2027-01-01,2\n').json();assert s['can_commit']
    b=next(p for p in client.get('/api/products').json() if p['sku']=='B');client.patch('/api/products/'+b['id'],json={'active':False})
    assert client.post('/api/imports/'+s['id']+'/commit',json={'confirm':True},headers={'Idempotency-Key':uid()}).status_code==409
    assert client.get('/api/batches').json()==[] and client.get('/api/movements').json()==[]

def test_mapping_explicit_dates_xlsx_and_unknown_sku(client):
    product(client,sku='A')
    r=preview(client,'Code,Lot,Date,Q\nA,MAPPED,31/12/2026,2\n',mapping='{"sku":"Code","lot":"Lot","expiry_date":"Date","quantity":"Q"}',date_format='DD/MM/YYYY').json();assert r['can_commit']
    assert not preview(client,'sku,lot,expiry_date,quantity\nA,AMBIG,12/01/2027,2\n').json()['can_commit']
    assert not preview(client,'sku,lot,expiry_date,quantity\nUNKNOWN,LOT,2027-01-01,2\n').json()['can_commit']
    wb=Workbook();wb.active.append(['sku','name','whole_units','expiry_tracked']);wb.active.append(['XLSX','Workbook product','true','false']);out=io.BytesIO();wb.save(out)
    r=client.post('/api/imports/preview',data={'kind':'products'},files={'file':('file.xlsx',out.getvalue())});assert r.status_code==200 and r.json()['can_commit']

def test_alert_dedup_ack_resolve_retrigger(client):
    p=product(client,threshold='5');first=client.get('/api/alerts').json();assert len(first)==1
    a=first[0];assert client.post('/api/alerts/'+a['id']+'/acknowledge').status_code==200
    client.post('/api/alerts/check');assert client.get('/api/alerts').json()[0]['state']=='acknowledged'
    move(client,p,quantity='10');assert client.get('/api/alerts').json()[0]['state']=='resolved'
    issue(client,p,'8');again=client.get('/api/alerts').json();assert len(again)==1 and again[0]['state']=='open' and again[0]['occurrences']==2

@pytest.mark.parametrize('role',['viewer','operator'])
def test_administrative_authorization(clients,role):
    c=clients[role];admin=clients['administrator'];p=product(admin);move(admin,p);batch=admin.get('/api/batches').json()[0]['id']
    for path,method,data in [('/products','POST',{'sku':'DENIED','name':'Denied'}),('/settings','PATCH',{}),('/products/'+p,'PATCH',{'active':False}),('/batches/'+batch+'/status','PATCH',{'status':'available','reason':'Review'}),('/users','POST',{}),('/users/'+p,'PATCH',{}),('/imports/'+uid()+'/commit','POST',{'confirm':True}),('/alerts/check','POST',{})]:
        assert c.request(method,'/api'+path,json=data,headers={'Idempotency-Key':uid()}).status_code==403,path
    for kind in ['opening','adjustment','write_off','reversal']:
        assert move(c,p,kind,batch_id=batch).status_code==403
    assert c.post('/api/imports/preview',data={'kind':'products'},files={'file':('file.csv','sku,name\nA,B\n')}).status_code==403
    if role=='viewer':
        for kind in ['receipt','issue','customer_return','supplier_return']:assert move(c,p,kind).status_code==403
        alert=admin.get('/api/alerts').json()
        # A stock-affecting command always requires both an authenticated writer and valid input.
        assert c.post('/api/alerts/'+uid()+'/acknowledge').status_code==403

def test_operator_receipt_issue_return_and_supplier_return(clients):
    a=clients['administrator'];c=clients['operator'];p=product(a)
    assert move(c,p).status_code==200
    result=issue(c,p,'4');assert result.status_code==200
    assert move(c,p,'customer_return','1',source_issue=result.json()['movement_ids'][0]).status_code==200
    batch=next(b for b in c.get('/api/batches').json() if b['status']=='available')
    assert move(c,p,'supplier_return','1',batch_id=batch['id']).status_code==200

def test_exports_filters_safe_cells_ledger_immutable_and_reconnect(client):
    p=product(client,sku='SAFE',name='=HYPERLINK("evil")');move(client,p)
    product(client,sku='OTHER',name='Other')
    csvdata=client.get('/api/export/products?q=SAFE').content.decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(csvdata)));assert len(rows)==1 and rows[0]['name'].startswith("'=") and rows[0]['business_timezone']=='Europe/Istanbul'
    xlsx=client.get('/api/export/products?q=SAFE&format=xlsx');wb=load_workbook(io.BytesIO(xlsx.content));assert wb.active.cell(2,3).data_type!='f'
    m=client.get('/api/movements').json()[0]
    with connection() as c:
        with pytest.raises(Exception):
            with c.transaction(): c.execute('UPDATE movements SET effect=1 WHERE id=%s',(m['id'],))
    with connection() as c: assert c.execute('SELECT sum(effect) AS q FROM movements').fetchone()['q']==10
    assert client.get('/api/export/batches?status=expired').status_code==200

def test_login_logout_csrf_and_unauthenticated(client):
    with TestClient(app) as c:
        assert c.get('/api/products').status_code==401
        assert c.post('/api/login',json={'username':'administrator','password':'wrong'}).status_code==401
        r=c.post('/api/login',json={'username':'administrator','password':'test-password-123'});assert r.status_code==200
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
        assert c.post('/api/movements',json={},headers={'Origin':'https://evil.example'}).status_code==403
        assert c.post('/api/logout').status_code==200 and c.get('/api/me').status_code==401

def test_nonexpiring_fallback_and_dashboard_precedence(client):
    p=product(client,expiry_tracked=False)
    move(client,p,lot='FIRST',expiry_date=None,quantity='3');move(client,p,lot='SECOND',expiry_date=None,quantity='4')
    s=client.post('/api/fefo',json={'product_id':p,'quantity':'4'}).json();assert [x['lot'] for x in s['lines']]==['FIRST','SECOND']
    expired=product(client);move(client,expired,expiry_date='2026-01-01',quantity='2');b=next(b for b in client.get('/api/batches').json() if b['product_id']==expired)
    client.patch('/api/batches/'+b['id']+'/status',json={'status':'quarantine','reason':'Hold expired stock'})
    d=client.get('/api/dashboard').json();assert Decimal(d['expired'])==0 and Decimal(d['quarantine'])==2 and Decimal(d['physical'])==9

def test_request_validation_and_inconsistent_units(client):
    p=product(client)
    assert move(client,p,unit='case').status_code==422
    assert client.post('/api/movements',json={},headers={'Idempotency-Key':uid()}).status_code==422
    assert client.post('/api/fefo',json={}).status_code==422
    assert move(client,p,recorded_at='2020-01-01').status_code==422
