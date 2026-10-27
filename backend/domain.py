import os, json, hashlib
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from psycopg.types.json import Jsonb


def fail(message, status=422):
    raise HTTPException(status, message)

def uid(): return str(uuid4())
def serial(value):
    if isinstance(value, Decimal): return format(value, 'f')
    if isinstance(value, (datetime, date)): return value.isoformat()
    return str(value)
def clean(value): return json.loads(json.dumps(value, default=serial))
def audit(c, actor, action, entity, details):
    c.execute('INSERT INTO audit(actor,action,entity_id,details) VALUES(%s,%s,%s,%s)', (actor['id'], action, str(entity), Jsonb(clean(details))))
def config(c): return c.execute('SELECT * FROM settings WHERE id=1').fetchone()
def today(c):
    frozen = os.getenv('DEMO_TODAY')
    return date.fromisoformat(frozen) if frozen else datetime.now(timezone.utc).astimezone(ZoneInfo(config(c)['timezone'])).date()
def quantity(raw, product, positive=True):
    if isinstance(raw, (float, bool)): fail('Send quantities as exact decimal strings, never floating-point numbers')
    try: q = Decimal(str(raw))
    except (InvalidOperation, ValueError): fail('Invalid quantity')
    if not q.is_finite() or abs(q)>Decimal('999999999999999') or (q<=0 if positive else q<0): fail('Quantity must be finite, positive and within supported range')
    if q != q.quantize(Decimal('1') if product['whole_units'] else Decimal('.001')): fail('Whole units required' if product['whole_units'] else 'Maximum three decimal places')
    return q

def product(c, identifier, lock=False):
    p=c.execute('SELECT * FROM products WHERE id=%s'+(' FOR UPDATE' if lock else ''),(identifier,)).fetchone()
    if not p: fail('Product not found',404)
    return p

def product_by_sku(c, sku):
    p=c.execute('SELECT * FROM products WHERE sku=%s',(sku,)).fetchone()
    if not p: fail(f'Unknown SKU: {sku}')
    return p

def balance(c, batch):
    return c.execute('SELECT coalesce(sum(effect),0) AS q FROM movements WHERE batch_id=%s',(batch,)).fetchone()['q']
def batches(c, product_id=None):
    return c.execute('''SELECT b.*,p.sku,p.name,p.unit,p.active,p.expiry_tracked,p.whole_units,coalesce(sum(m.effect),0) AS physical
      FROM batches b JOIN products p ON p.id=b.product_id LEFT JOIN movements m ON m.batch_id=b.id
      WHERE (%s::uuid IS NULL OR b.product_id=%s::uuid) GROUP BY b.id,p.id ORDER BY b.expiry_date NULLS LAST,b.created_at,b.id''',(product_id,product_id)).fetchall()
def classification(b, day):
    if b['status']!='available': return b['status']
    if b['expiry_date'] is None: return 'non_expiring'
    days=(b['expiry_date']-day).days
    if days<0: return 'expired'
    if days==0: return 'expires_today'
    if days<=7: return 'within_7'
    if days<=30: return 'within_30'
    if days<=60: return 'within_60'
    if days<=90: return 'within_90'
    return 'healthy'
def eligible(b, day, minimum):
    return b['active'] and b['status']=='available' and (b['expiry_date'] is None or (b['expiry_date']-day).days>=minimum)
def enriched_batches(c, product_id=None):
    day=today(c); minimum=config(c)['minimum_shelf_days']
    return [dict(b,expiry_status=classification(b,day),days_remaining=(b['expiry_date']-day).days if b['expiry_date'] else None,usable=b['physical'] if eligible(b,day,minimum) else Decimal(0)) for b in batches(c,product_id)]
def product_stock(c):
    ps=c.execute('SELECT * FROM products ORDER BY name').fetchall(); bs=enriched_batches(c)
    for p in ps:
        own=[b for b in bs if b['product_id']==p['id']]
        p.update(physical=sum((b['physical'] for b in own),Decimal(0)),usable=sum((b['usable'] for b in own),Decimal(0)),batch_count=len(own))
        p['low_stock']=p['active'] and p['usable']<=p['threshold']
    return ps

def create_product(c, data, actor):
    sku=str(data.get('sku','')).strip(); name=str(data.get('name','')).strip()
    if not sku or not name: fail('SKU and product name are required')
    if len(sku)>80 or len(name)>200: fail('SKU max 80 characters; name max 200 characters')
    if not str(data.get('unit','each')).strip() or len(str(data.get('unit','each')))>30: fail('Base unit is required (maximum 30 characters)')
    if c.execute('SELECT 1 FROM products WHERE sku=%s OR (barcode IS NOT NULL AND barcode=%s)',(sku,data.get('barcode') or None)).fetchone(): fail('SKU or barcode already exists',409)
    whole=data.get('whole_units',True)
    if not isinstance(whole,bool) or not isinstance(data.get('expiry_tracked',True),bool): fail('Product flags must be booleans')
    threshold=quantity(data.get('threshold','10'),{'whole_units':whole},False)
    ident=uid()
    c.execute('INSERT INTO products(id,sku,name,category,barcode,unit,whole_units,expiry_tracked,threshold) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(ident,sku,name,data.get('category','General'),data.get('barcode') or None,data.get('unit','each'),whole,data.get('expiry_tracked',True),threshold))
    audit(c,actor,'product_created',ident,data)
    return {'id':ident}

def parse_date(value):
    if value in (None,''): return None
    try:
        text=str(value)
        if len(text)!=10: raise ValueError()
        return date.fromisoformat(text)
    except ValueError: fail('Use an ISO date: YYYY-MM-DD')
def get_batch(c,p,data,status='available'):
    lot=str(data.get('lot','')).strip()
    if not lot or len(lot)>100: fail('Lot code required (maximum 100 characters)')
    expiry=parse_date(data.get('expiry_date')); manufacture=parse_date(data.get('manufacture_date'))
    if p['expiry_tracked'] and not expiry: fail('Expiry date required for this product')
    if manufacture and expiry and manufacture>expiry: fail('Manufacture date must precede expiry date')
    b=c.execute('SELECT * FROM batches WHERE product_id=%s AND lot=%s',(p['id'],lot)).fetchone()
    if b:
        if b['expiry_date']!=expiry or (manufacture and manufacture!=b['manufacture_date']): fail('Lot date conflict: review the existing lot',409)
        if b['status']!=status: fail('Lot availability conflict: use a separate lot for quarantine',409)
        return b
    ident=uid()
    return c.execute('INSERT INTO batches(id,product_id,lot,expiry_date,manufacture_date,supplier,location,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(ident,p['id'],lot,expiry,manufacture,data.get('supplier',''),data.get('location',''),status)).fetchone()

def post(c,p,b,kind,q,effect,data,actor,source=None,reversal=None,import_id=None):
    if balance(c,b['id'])+effect<0: fail('Insufficient physical stock; refresh batch availability',409)
    ident=uid()
    c.execute('''INSERT INTO movements(id,product_id,batch_id,type,requested,effect,reference,reason,actor,source_issue,reversal_of,import_id)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(ident,p['id'],b['id'],kind,q,effect,data.get('reference',''),data['reason'],actor['id'],source,reversal,import_id))
    audit(c,actor,kind,ident,dict(data,batch_id=str(b['id']),effect=str(effect)))
    return ident

def fefo(c,p,q):
    bs=enriched_batches(c,p['id']); lines=[]; remaining=q
    for b in bs:
        take=min(remaining,b['usable'])
        if take>0:
            lines.append({'batch_id':str(b['id']),'lot':b['lot'],'quantity':str(take),'expiry_date':serial(b['expiry_date']) if b['expiry_date'] else None})
            remaining-=take
        if remaining==0: break
    return {'lines':lines,'requested':str(q),'shortfall':str(remaining),'available':str(q-remaining),'business_date':today(c).isoformat()}

def command(c,data,actor,import_id=None):
    kind=data.get('type'); admin=actor['role']=='administrator'
    if actor['role']=='viewer': fail('Read-only role',403)
    if kind not in ('receipt','opening','issue','customer_return','supplier_return','write_off','adjustment','reversal'): fail('Unsupported movement type')
    if kind in ('opening','adjustment','reversal','write_off') and not admin: fail('Administrator role required',403)
    if not str(data.get('reason','')).strip(): fail('A reason is required')
    if 'recorded_at' in data: fail('Backdating is disabled')
    
    if not data.get('product_id'): fail('Product ID is required')
    p=product(c,data['product_id'],True)
    if not p['active']: fail('Product is archived',409)
    if kind=='reversal':
        original=c.execute('SELECT * FROM movements WHERE id=%s AND product_id=%s',(data.get('movement_id'),p['id'])).fetchone()
        if not original: fail('Movement not found',404)
        if original['type'] in ('reversal','customer_return'): fail('Reverse returns using a reviewed write-off; reversals cannot be reversed')
        if c.execute('SELECT 1 FROM movements WHERE reversal_of=%s OR source_issue=%s',(original['id'],original['id'])).fetchone(): fail('Already reversed or has linked returns',409)
        b=c.execute('SELECT * FROM batches WHERE id=%s',(original['batch_id'],)).fetchone()
        ids=[post(c,p,b,kind,original['requested'],-original['effect'],data,actor,reversal=original['id'])]
    else:
        q=quantity(data.get('quantity'),p)
        if kind=='issue':
            suggestion=fefo(c,p,q)
            if Decimal(suggestion['shortfall'])>0: fail({'message':'Insufficient usable stock','suggestion':suggestion},409)
            expected=data.get('expected_lines')
            if expected is None: fail('Preview FEFO and confirm expected_lines before posting')
            normalized=lambda lines: [(str(x['batch_id']),str(Decimal(str(x['quantity'])).normalize())) for x in lines]
            if normalized(expected)!=normalized(suggestion['lines']): fail({'message':'Availability changed. Review the refreshed suggestion.','suggestion':suggestion},409)
            ids=[]
            for line in suggestion['lines']:
                b=c.execute('SELECT * FROM batches WHERE id=%s',(line['batch_id'],)).fetchone()
                n=Decimal(line['quantity']); ids.append(post(c,p,b,kind,n,-n,data,actor))
        elif kind=='customer_return':
            original=c.execute("SELECT * FROM movements WHERE id=%s AND product_id=%s AND type='issue'",(data.get('source_issue'),p['id'])).fetchone()
            if not original: fail('A valid source issue movement is required')
            returned=c.execute('SELECT coalesce(sum(requested),0) AS q FROM movements WHERE source_issue=%s',(original['id'],)).fetchone()['q']
            if c.execute('SELECT 1 FROM movements WHERE reversal_of=%s',(original['id'],)).fetchone() or returned+q>original['requested']: fail('Return exceeds the remaining eligible issue quantity',409)
            source=c.execute('SELECT * FROM batches WHERE id=%s',(original['batch_id'],)).fetchone()
            return_data=dict(data,lot='RETURN-'+uid()[:8],expiry_date=source['expiry_date'].isoformat() if source['expiry_date'] else None,manufacture_date=None)
            b=get_batch(c,p,return_data,'quarantine')
            ids=[post(c,p,b,kind,q,q,data,actor,source=original['id'])]
        elif kind in ('receipt','opening'):
            b=get_batch(c,p,data); ids=[post(c,p,b,kind,q,q,data,actor,import_id=import_id)]
        else:
            b=c.execute('SELECT * FROM batches WHERE id=%s AND product_id=%s',(data.get('batch_id'),p['id'])).fetchone()
            if not b: fail('Select a batch belonging to the product')
            effect=q if kind=='adjustment' and data.get('direction')=='add' else -q
            if kind=='adjustment' and data.get('direction') not in ('add','remove'): fail('Adjustment direction must be add or remove')
            ids=[post(c,p,b,kind,q,effect,data,actor)]
    return {'movement_ids':ids,'product_id':str(p['id'])}

def idempotent(c,key,data,actor,fn):
    if not key or len(key)>160: fail('Idempotency-Key required (1–160 characters)')
    c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(key,))
    fingerprint=hashlib.sha256(json.dumps(clean(data),sort_keys=True).encode()).hexdigest()
    old=c.execute('SELECT * FROM commands WHERE key=%s',(key,)).fetchone()
    if old:
        if old['fingerprint']!=fingerprint or old['actor']!=actor['id']: fail('Idempotency key was used with different input or actor',409)
        return old['response']
    result=clean(fn())
    c.execute('INSERT INTO commands(key,fingerprint,actor,response) VALUES(%s,%s,%s,%s)',(key,fingerprint,actor['id'],Jsonb(result)))
    return result

def refresh_alerts(c):
    c.execute('SELECT * FROM settings WHERE id=1 FOR UPDATE')
    day=today(c); desired={}; days=config(c)['alert_days']
    for p in product_stock(c):
        if p['low_stock']: desired['low:'+str(p['id'])]=('low_stock',p['id'],f"{p['name']}: {p['usable']} {p['unit']} usable; threshold {p['threshold']}")
    for b in enriched_batches(c):
        if b['physical']>0 and b['expiry_date'] and (b['expiry_date']-day).days<=days:
            desired['expiry:'+str(b['id'])]=('expiry',b['id'],f"{b['name']} · {b['lot']} · expires {b['expiry_date']} · {b['physical']} {b['unit']} physical")
    for key,(kind,entity,message) in desired.items():
        c.execute('''INSERT INTO alerts(id,condition_key,kind,entity_id,message,state) VALUES(%s,%s,%s,%s,%s,'open')
        ON CONFLICT(condition_key) DO UPDATE SET message=EXCLUDED.message,updated_at=now(),
        state=CASE WHEN alerts.state='resolved' THEN 'open' ELSE alerts.state END,
        acknowledged_by=CASE WHEN alerts.state='resolved' THEN NULL ELSE alerts.acknowledged_by END,
        occurrences=alerts.occurrences+CASE WHEN alerts.state='resolved' THEN 1 ELSE 0 END''',(uid(),key,kind,entity,message))
    c.execute("UPDATE alerts SET state='resolved',updated_at=now() WHERE NOT(condition_key=ANY(%s)) AND state<>'resolved'",(list(desired),))
    c.execute('UPDATE settings SET last_alert_run=now() WHERE id=1')
    return {'conditions':len(desired),'business_date':day.isoformat()}
