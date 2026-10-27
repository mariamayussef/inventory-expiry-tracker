import os, hashlib, secrets, json, time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import FastAPI, Depends, Request, Response, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .db import connection, migrate
from .schemas import StockRequest
from .domain import *
from .imports import read_upload, stage, commit_import, spreadsheet, PRODUCT_COLUMNS, STOCK_COLUMNS

hasher=PasswordHasher(); attempts=defaultdict(deque)
@asynccontextmanager
async def lifespan(app):
    migrate()
    with connection() as c: refresh_alerts(c)
    yield
app=FastAPI(title='Stockroom · Inventory & Expiry',version='1.0.0',lifespan=lifespan)

@app.middleware('http')
async def guard(request,call_next):
    if request.method in ('POST','PATCH','PUT','DELETE'):
        if int(request.headers.get('content-length','0'))>3*1024*1024: return JSONResponse({'detail':'Request exceeds 3 MB'},413)
        origin=request.headers.get('origin')
        allowed=os.getenv('ALLOWED_ORIGINS','http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000').split(',')
        if origin and origin not in allowed: return JSONResponse({'detail':'Origin is not permitted'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(psycopg.IntegrityError)
async def integrity(request,exc): return JSONResponse({'detail':'Database constraint conflict; refresh and review the record'},409)
@app.exception_handler(psycopg.DataError)
async def data_error(request,exc): return JSONResponse({'detail':'Invalid identifier or field value'},422)

def current(request:Request):
    token=request.cookies.get('stockroom_session','')
    with connection() as c:
        user=c.execute('''SELECT u.id,u.username,u.role FROM sessions s JOIN users u ON u.id=s.user_id
          WHERE s.token_hash=%s AND s.expires_at>now() AND u.active''',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not user: fail('Please sign in',401)
    return user

def admin(user=Depends(current)):
    if user['role']!='administrator': fail('Administrator role required',403)
    return user

def operator(user=Depends(current)):
    if user['role']=='viewer': fail('Read-only role',403)
    return user

@app.post('/api/login')
def login(data:dict,response:Response,request:Request):
    host=request.client.host; now=time.monotonic(); bucket=attempts[host]
    while bucket and bucket[0]<now-300: bucket.popleft()
    if len(bucket)>=15: fail('Too many sign-in attempts; retry in five minutes',429)
    bucket.append(now)
    with connection() as c:
        u=c.execute('SELECT * FROM users WHERE username=%s AND active',(str(data.get('username','')),)).fetchone()
        try:
            if not u: hasher.verify(hasher.hash('dummy-verification'),str(data.get('password',''))); fail('Invalid credentials',401)
            hasher.verify(u['password_hash'],str(data.get('password','')))
        except (VerificationError,InvalidHashError): fail('Invalid credentials',401)
        token=secrets.token_urlsafe(40)
        c.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],datetime.now(timezone.utc)+timedelta(hours=8)))
        response.set_cookie('stockroom_session',token,httponly=True,samesite='strict',secure=os.getenv('SECURE_COOKIES','false')=='true',max_age=28800,path='/')
        audit(c,u,'login',u['id'],{})
        return clean({k:u[k] for k in ('id','username','role')})

@app.post('/api/logout')
def logout(request:Request,response:Response,user=Depends(current)):
    with connection() as c: c.execute('DELETE FROM sessions WHERE token_hash=%s',(hashlib.sha256(request.cookies.get('stockroom_session','').encode()).hexdigest(),))
    response.delete_cookie('stockroom_session'); return {'ok':True}
@app.get('/api/me')
def me(user=Depends(current)): return clean(user)
@app.get('/api/health')
def health():
    with connection() as c: c.execute('SELECT 1')
    return {'status':'ok','database':'postgresql'}

@app.get('/api/settings')
def settings(user=Depends(current)):
    with connection() as c: return clean(dict(config(c),business_date=today(c),demo=bool(os.getenv('DEMO_TODAY'))))
@app.patch('/api/settings')
def update_settings(data:dict,user=Depends(admin)):
    tz=data.get('timezone','Europe/Istanbul')
    try: ZoneInfo(tz)
    except (ZoneInfoNotFoundError,ValueError,TypeError): fail('Unknown business timezone')
    days=data.get('minimum_shelf_days',0); alert=data.get('alert_days',30)
    if not isinstance(days,int) or not isinstance(alert,int) or not 0<=days<=3650 or not 0<=alert<=3650: fail('Day thresholds must be integers between 0 and 3650')
    with connection() as c:
        c.execute('UPDATE settings SET timezone=%s,minimum_shelf_days=%s,alert_days=%s WHERE id=1',(tz,days,alert)); audit(c,user,'settings_updated',1,data); refresh_alerts(c)
    return {'ok':True}
@app.get('/api/users')
def users(user=Depends(admin)):
    with connection() as c: return clean(c.execute('SELECT id,username,role,active FROM users ORDER BY username').fetchall())
@app.post('/api/users')
def create_user(data:dict,user=Depends(admin)):
    role=data.get('role'); password=str(data.get('password','')); username=str(data.get('username','')).strip()
    if role not in ('administrator','operator','viewer') or len(password)<12 or not username or len(username)>80: fail('Username, valid role and password of at least 12 characters required')
    with connection() as c:
        ident=uid(); c.execute('INSERT INTO users(id,username,password_hash,role) VALUES(%s,%s,%s,%s)',(ident,username,hasher.hash(password),role)); audit(c,user,'user_created',ident,{'username':username,'role':role})
    return {'id':ident}
@app.patch('/api/users/{ident}')
def update_user(ident:str,data:dict,user=Depends(admin)):
    if str(user['id'])==ident: fail('Use another administrator to change your own role or deactivate your account')
    role=data.get('role'); active=data.get('active',True)
    if role not in ('administrator','operator','viewer') or not isinstance(active,bool): fail('Valid role and active flag required')
    with connection() as c:
        old=c.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(ident,)).fetchone()
        if not old: fail('User not found',404)
        c.execute('UPDATE users SET role=%s,active=%s WHERE id=%s',(role,active,ident)); c.execute('DELETE FROM sessions WHERE user_id=%s',(ident,)); audit(c,user,'user_updated',ident,data)
    return {'ok':True}

@app.get('/api/products')
def products(q:str='',status:str='',user=Depends(current)):
    with connection() as c:
        ps=product_stock(c)
        return clean([p for p in ps if q.lower() in (p['name']+' '+p['sku']+' '+(p['barcode'] or '')).lower() and (not status or status=='low_stock' and p['low_stock'] or status=='active' and p['active'] or status=='archived' and not p['active'])])
@app.post('/api/products')
def new_product(data:dict,user=Depends(admin),idempotency_key:str=Header(default='')):
    with connection() as c: return idempotent(c,idempotency_key,{'product':data},user,lambda:create_product(c,data,user))
@app.patch('/api/products/{ident}')
def edit_product(ident:str,data:dict,user=Depends(admin)):
    with connection() as c:
        p=product(c,ident,True)
        allowed={'name','category','barcode','threshold','active'}
        if set(data)-allowed: fail('Only name, category, barcode, threshold and archive flag may be edited')
        updated=dict(p,**data)
        if not str(updated['name']).strip() or not isinstance(updated['active'],bool): fail('Name and active flag are required')
        threshold=quantity(updated['threshold'],p,False)
        c.execute('UPDATE products SET name=%s,category=%s,barcode=%s,threshold=%s,active=%s WHERE id=%s',(updated['name'],updated['category'],updated['barcode'] or None,threshold,updated['active'],ident)); audit(c,user,'product_updated',ident,data)
    return {'ok':True}
@app.get('/api/batches')
def batch_list(product_id:str|None=None,status:str='',q:str='',user=Depends(current)):
    with connection() as c:
        return clean([b for b in enriched_batches(c,product_id) if (not status or b['expiry_status']==status) and q.lower() in (b['name']+' '+b['sku']+' '+b['lot']).lower()])
@app.patch('/api/batches/{ident}/status')
def batch_status(ident:str,data:dict,user=Depends(admin)):
    status=data.get('status'); reason=str(data.get('reason','')).strip()
    if status not in ('available','quarantine','blocked','archived') or not reason: fail('Valid status and review reason required')
    with connection() as c:
        b=c.execute('SELECT * FROM batches WHERE id=%s',(ident,)).fetchone()
        if not b: fail('Batch not found',404)
        product(c,b['product_id'],True)
        c.execute('UPDATE batches SET status=%s WHERE id=%s',(status,ident)); audit(c,user,'batch_status',ident,data)
    return {'ok':True}

@app.post('/api/fefo')
def preview(data:dict,user=Depends(current)):
    with connection() as c:
        
        if not data.get('product_id'): fail('Product ID is required')
        p=product(c,data['product_id']); return clean(fefo(c,p,quantity(data.get('quantity'),p)))
@app.post('/api/movements')
def movement(data:StockRequest,user=Depends(operator),idempotency_key:str=Header(default='')):
    payload=data.model_dump(exclude_unset=True)
    with connection() as c: return idempotent(c,idempotency_key,payload,user,lambda:command(c,payload,user))
@app.get('/api/movements')
def movements(q:str='',product_id:str|None=None,batch_id:str|None=None,type:str='',user=Depends(current)):
    with connection() as c: return clean(movement_rows(c,q,product_id,batch_id,type))
def movement_rows(c,q='',product_id=None,batch_id=None,type=''):
    return c.execute('''SELECT m.*,p.sku,p.name,p.unit,b.lot,u.username AS actor_name FROM movements m
     JOIN products p ON p.id=m.product_id JOIN batches b ON b.id=m.batch_id JOIN users u ON u.id=m.actor
     WHERE (%s::uuid IS NULL OR m.product_id=%s::uuid) AND (%s::uuid IS NULL OR m.batch_id=%s::uuid)
     AND (%s='' OR m.type=%s) AND (p.name ILIKE %s OR p.sku ILIKE %s OR m.reference ILIKE %s OR b.lot ILIKE %s)
     ORDER BY m.recorded_at DESC,m.id DESC LIMIT 5000''',(product_id,product_id,batch_id,batch_id,type,type,*(['%'+q+'%']*4))).fetchall()

@app.get('/api/dashboard')
def dashboard(user=Depends(current)):
    with connection() as c:
        bs=enriched_batches(c); ps=product_stock(c); day=today(c); buckets={}
        for b in bs: buckets[b['expiry_status']]=buckets.get(b['expiry_status'],Decimal(0))+b['physical']
        return clean({'physical':sum((b['physical'] for b in bs),Decimal(0)),'usable':sum((b['usable'] for b in bs),Decimal(0)),'expired':buckets.get('expired',0),'quarantine':buckets.get('quarantine',0),'low_stock':sum(p['low_stock'] for p in ps),'product_count':len(ps),'soon_batches':sum(b['physical']>0 and b['expiry_date'] is not None and 0<=(b['expiry_date']-day).days<=config(c)['alert_days'] for b in bs),'buckets':buckets,'business_date':day,'attention':[b for b in bs if b['physical']>0 and b['expiry_status'] in ('expired','expires_today','within_7','within_30','quarantine')][:8],'recent':movement_rows(c)[:6]})
@app.get('/api/alerts')
def alerts(state:str='',kind:str='',user=Depends(current)):
    with connection() as c:
        refresh_alerts(c)
        return clean(c.execute("SELECT * FROM alerts WHERE (%s='' OR state=%s) AND (%s='' OR kind=%s) ORDER BY updated_at DESC",(state,state,kind,kind)).fetchall())
@app.post('/api/alerts/check')
def check_alerts(user=Depends(admin)):
    with connection() as c: return refresh_alerts(c)
@app.post('/api/alerts/{ident}/acknowledge')
def acknowledge(ident:str,user=Depends(operator)):
    with connection() as c:
        result=c.execute("UPDATE alerts SET state='acknowledged',acknowledged_by=%s WHERE id=%s AND state='open' RETURNING id",(user['id'],ident)).fetchone()
        if not result: fail('Alert is no longer open',409)
        audit(c,user,'alert_acknowledged',ident,{})
    return {'ok':True}
@app.get('/api/audit')
def audit_log(q:str='',user=Depends(current)):
    with connection() as c: return clean(c.execute('SELECT a.*,u.username FROM audit a LEFT JOIN users u ON u.id=a.actor WHERE a.action ILIKE %s OR a.entity_id ILIKE %s ORDER BY a.id DESC LIMIT 1000',('%'+q+'%','%'+q+'%')).fetchall())
@app.get('/api/reconcile')
def reconcile(user=Depends(admin)):
    with connection() as c:
        bs=enriched_batches(c); return clean({'source_of_truth':'sum of immutable movement effects','batches':len(bs),'negative_batches':[str(b['id']) for b in bs if b['physical']<0],'physical':sum((b['physical'] for b in bs),Decimal(0)),'ledger':c.execute('SELECT coalesce(sum(effect),0) AS q FROM movements').fetchone()['q']})
@app.post('/api/imports/preview')
async def preview_import(file:UploadFile=File(...),kind:str=Form(...),mapping:str=Form('{}'),date_format:str=Form('ISO'),user=Depends(admin)):
    try: m=json.loads(mapping)
    except ValueError: fail('Column mapping must be a JSON object')
    if not isinstance(m,dict): fail('Column mapping must be an object')
    content=await file.read(2*1024*1024+1)
    rows=read_upload(content,file.filename or '',m,date_format,kind)
    with connection() as c: return stage(c,kind,rows,user)
@app.post('/api/imports/{ident}/commit')
def finish_import(ident:str,data:dict,user=Depends(admin),idempotency_key:str=Header(default='')):
    if data.get('confirm') is not True: fail('Explicit confirmation required')
    with connection() as c: return idempotent(c,idempotency_key,{'import_id':ident,'confirm':True},user,lambda:commit_import(c,ident,user))
@app.get('/api/templates/{kind}')
def template(kind:str,format:str='csv',user=Depends(current)):
    if kind not in ('products','opening'): fail('Unknown template')
    columns=PRODUCT_COLUMNS if kind=='products' else STOCK_COLUMNS
    return download(spreadsheet([dict.fromkeys(columns,'')],format),kind+'-template',format)
def download(content,name,format):
    return Response(content,media_type='text/csv' if format=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}.{format}"'})
@app.get('/api/export/{kind}')
def export(kind:str,format:str='csv',q:str='',status:str='',product_id:str|None=None,batch_id:str|None=None,type:str='',user=Depends(current)):
    with connection() as c:
        if kind=='products': rows=[p for p in product_stock(c) if q.lower() in (p['name']+' '+p['sku']+' '+(p['barcode'] or '')).lower() and (not status or status=='low_stock' and p['low_stock'] or status=='active' and p['active'] or status=='archived' and not p['active'])]
        elif kind=='batches': rows=[b for b in enriched_batches(c,product_id) if (not status or b['expiry_status']==status) and q.lower() in (b['name']+' '+b['sku']+' '+b['lot']).lower()]
        elif kind=='movements': rows=movement_rows(c,q,product_id,batch_id,type)
        else: fail('Unknown export')
        meta={'business_timezone':config(c)['timezone'],'business_date':today(c).isoformat(),'expiry_policy':'expired when expiry_date < business_date','minimum_shelf_days':config(c)['minimum_shelf_days']}
        rows=[dict(row,**meta) for row in rows]
        return download(spreadsheet(rows,format),'stockroom-'+kind,format)

static=Path(__file__).parent.parent/'frontend'/'dist'
if static.exists(): app.mount('/',StaticFiles(directory=static,html=True),name='frontend')
