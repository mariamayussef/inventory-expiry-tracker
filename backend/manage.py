"""Explicit local bootstrap. Never creates a default production password."""
import os, argparse, getpass
from datetime import timedelta
from argon2 import PasswordHasher
from .db import migrate, connection
from .domain import uid, today, create_product, command, refresh_alerts

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['admin','demo']);parser.add_argument('--username',default='admin');args=parser.parse_args()
    migrate(); password=os.getenv('BOOTSTRAP_PASSWORD') or getpass.getpass('New administrator password (12+ characters): ')
    if len(password)<12: raise SystemExit('Password must be at least 12 characters')
    with connection() as c:
        if c.execute('SELECT 1 FROM users WHERE username=%s',(args.username,)).fetchone(): raise SystemExit('Username already exists; bootstrap does not reset passwords')
        actor={'id':uid(),'role':'administrator','username':args.username}
        c.execute('INSERT INTO users(id,username,password_hash,role) VALUES(%s,%s,%s,%s)',(actor['id'],args.username,PasswordHasher().hash(password),'administrator'))
        if args.action=='admin': print('Administrator created. Production inventory remains empty.');return
        if c.execute('SELECT 1 FROM products').fetchone(): raise SystemExit('Demo seed requires an empty product catalog')
        day=today(c)
        items=[('Rolled oats','Dry goods','kg',False),('Whole milk','Dairy','each',True),('Greek yogurt','Dairy','each',True),('Orange juice','Beverages','each',True),('Tomato passata','Pantry','each',True),('Ground coffee','Beverages','each',True),('Brown rice','Dry goods','kg',False),('Chickpeas','Pantry','each',True),('Olive oil','Pantry','each',True),('Almond butter','Pantry','each',True),('Cheddar cheese','Dairy','kg',False),('Green tea','Beverages','each',True),('Dried apricots','Dry goods','kg',False),('Coconut milk','Pantry','each',True),('Dark chocolate','Snacks','each',True),('Sea salt crackers','Snacks','each',True),('Maple syrup','Pantry','each',True),('Lentil soup','Pantry','each',True),('Sparkling water','Beverages','each',True),('Couscous','Dry goods','kg',False),('Strawberry jam','Pantry','each',True),('Baking flour','Dry goods','kg',False),('Honey','Pantry','each',True),('Paper bags','Supplies','each',True)]
        for i,(name,category,unit,whole) in enumerate(items):
            p=create_product(c,{'sku':f'STK-{1001+i}','name':name,'category':category,'unit':unit,'whole_units':whole,'expiry_tracked':i!=23,'threshold':'15','barcode':f'20000000{i:05d}'},actor)
            if i==20: continue
            offsets=[-4,0,3,6,18,28,45,75,150]; offset=offsets[i%len(offsets)]
            q='6' if i%7==0 else str(40+i*7)
            data={'type':'opening','product_id':p['id'],'quantity':q,'lot':f'DEMO-{i+1:03d}-A','expiry_date':(day+timedelta(days=offset)).isoformat() if i!=23 else None,'supplier':'Fictional demo supplier','location':f'{chr(65+i%4)}-{i%6+1:02d}','reference':'DEMO-OPENING','reason':'Fictional demo opening balance'}
            command(c,data,actor)
            if i%3==0:
                command(c,dict(data,quantity='25',lot=f'DEMO-{i+1:03d}-B',expiry_date=(day+timedelta(days=100+i)).isoformat()),actor)
        # A real linked return supplies the quarantine demonstration.
        p=c.execute("SELECT * FROM products WHERE sku='STK-1006'").fetchone()
        from .domain import fefo,quantity
        suggestion=fefo(c,p,quantity('5',p))
        issue=command(c,{'type':'issue','product_id':str(p['id']),'quantity':'5','expected_lines':suggestion['lines'],'reason':'Fictional demo dispatch','reference':'DEMO-ISSUE-001'},actor)
        command(c,{'type':'customer_return','product_id':str(p['id']),'quantity':'3','source_issue':issue['movement_ids'][0],'reason':'Fictional demo return awaiting inspection'},actor)
        refresh_alerts(c)
        print(f'Created 24 fictional products and dated batches relative to {day}. Username: {args.username}')
if __name__=='__main__': main()
