"""家教小铺 — isolated, persistent sandbox. No real payment gateway is enabled."""
import hashlib
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

DB_PATH = os.getenv('DATABASE_PATH', str(Path(__file__).parent / 'data' / 'sandbox.sqlite3'))
FRONTEND = Path(os.getenv('FRONTEND_PATH', str(Path(__file__).parent.parent / 'jiajiao-shop-frontend'))).resolve()
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
ALLOWED_HOSTS = set(os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver,jiajiao.mychangliapp.cn,jiajiao-admin.mychangliapp.cn').split(','))
if os.getenv('APP_MODE', 'sandbox') != 'sandbox':
    raise RuntimeError('Real-money operation is not implemented. APP_MODE must remain sandbox.')
app = FastAPI(title='家教小铺 API', version='0.1.0', docs_url=None, redoc_url=None)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=16000)
rate_lock = threading.Lock()
rate_buckets = {}

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'customer', merchant_shop TEXT);
        CREATE TABLE IF NOT EXISTS shops(id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, slug TEXT NOT NULL, name TEXT NOT NULL, city TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, deposit INTEGER NOT NULL DEFAULT 0, UNIQUE(workspace,slug));
        CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, shop_id TEXT NOT NULL REFERENCES shops(id), title TEXT NOT NULL, subject TEXT NOT NULL, grade TEXT NOT NULL, district TEXT NOT NULL, schedule TEXT NOT NULL, hourly INTEGER NOT NULL, fee INTEGER NOT NULL, deposit INTEGER NOT NULL, description TEXT NOT NULL, contact TEXT NOT NULL, stock INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active', created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, listing_id TEXT NOT NULL REFERENCES listings(id), shop_id TEXT NOT NULL REFERENCES shops(id), status TEXT NOT NULL, fee INTEGER NOT NULL, deposit INTEGER NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL, idempotency TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', UNIQUE(workspace,idempotency));
        CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, order_id TEXT, kind TEXT NOT NULL, amount INTEGER NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, action TEXT NOT NULL, entity TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS order_workspace ON orders(workspace,created);
        CREATE INDEX IF NOT EXISTS listing_workspace ON listings(workspace,shop_id);
        ''')

init_db()


def uid(prefix):
    return prefix + secrets.token_hex(8)


def event(c, w, action, entity):
    c.execute('INSERT INTO events(workspace,action,entity,created) VALUES(?,?,?,?)', (w, action, entity, int(time.time())))


def seed(c, w):
    shop_id = uid('s_')
    c.execute('INSERT INTO shops VALUES(?,?,?,?,?,?,?,?)', (shop_id,w,'qinghe','青禾家教','成都','把热爱带进课堂，让每一份认真都被看见。','active',200000))
    other = uid('s_')
    c.execute('INSERT INTO shops VALUES(?,?,?,?,?,?,?,?)', (other,w,'shiguang','拾光家教','成都','大学生家教服务，专注每一次成长。','pending',0))
    rows = [
        ('高一数学 · 基础巩固与提升','数学','高中','武侯区','周六 14:00–16:00',120,68,100,'希望找到耐心、表达清晰的同学，梳理函数与集合知识，协助建立解题思路。每周一次，每次两小时。'),
        ('初二英语 · 阅读与口语陪练','英语','初中','锦江区','周日 10:00–12:00',100,58,100,'侧重阅读理解与口语表达，希望善于鼓励学生，能设计轻松的课堂互动。每周一次，每次两小时。'),
        ('小学数学 · 学习习惯培养','数学','小学','双流区','周三、周五 19:00–20:30',80,38,50,'从日常作业出发，帮助学生养成审题与检查习惯。每周两次，每次一个半小时。'),
        ('高二物理 · 力学专题辅导','物理','高中','成华区','周六 09:00–11:00',150,78,100,'围绕力学知识梳理与典型题训练展开，要求能清楚解释推导过程。每周一次，每次两小时。'),
        ('初三化学 · 知识梳理','化学','初中','郫都区','周日 15:00–17:00',110,58,100,'梳理化学基础概念，关注实验过程与错题复盘。希望有条理、认真负责。每周一次，每次两小时。'),
        ('小学语文 · 阅读与写作','语文','小学','温江区','周六 10:00–11:30',85,38,50,'陪伴阅读、练习表达，通过小任务提升阅读兴趣。每周一次，每次一个半小时。'),
    ]
    now = int(time.time())
    for i, row in enumerate(rows):
        title,subject,grade,district,schedule,hourly,fee,deposit,desc = row
        c.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (uid('l_'),w,shop_id,title,subject,grade,district,schedule,hourly*100,fee*100,deposit*100,desc,'演示联系人：林老师\n演示微信：DEMO-QINGHE\n联系后请核对课程时间与接单条件。此内容仅用于流程体验。',1,'active',now-i*3600))
    c.execute('UPDATE workspaces SET merchant_shop=? WHERE id=?', (shop_id,w))
    event(c,w,'创建演示空间',shop_id)
    return shop_id


def fail(code, text):
    raise HTTPException(code, text)


def session(c, req, roles=None):
    token = req.cookies.get('jx_session','')
    w = c.execute('SELECT * FROM workspaces WHERE token_hash=? AND expires>?', (hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    if not w: fail(401,'体验已过期，请刷新页面重新开始')
    if roles and w['role'] not in roles: fail(403,'当前身份没有此操作权限')
    if req.method not in ('GET','HEAD') and not secrets.compare_digest(req.headers.get('x-csrf-token','').encode(), w['csrf'].encode()):
        fail(403,'请求校验失败，请刷新后重试')
    return w


def expire_orders(c,w):
    c.execute("UPDATE orders SET status='expired',updated=? WHERE workspace=? AND status='pending' AND created<?", (int(time.time()),w,int(time.time())-900))


def available(c,l):
    used = c.execute("SELECT COUNT(*) FROM orders WHERE listing_id=? AND status IN ('pending','paid','disputed','completed')", (l['id'],)).fetchone()[0]
    return max(0,l['stock']-used)


def listing_json(c,l):
    d = dict(l)
    d.pop('contact',None)
    d.pop('workspace',None)
    d['available'] = available(c,l)
    return d


def order_json(c,o):
    d = dict(o)
    d.pop('workspace',None)
    d.pop('idempotency',None)
    l = c.execute('SELECT * FROM listings WHERE id=?',(o['listing_id'],)).fetchone()
    s = c.execute('SELECT name FROM shops WHERE id=?',(o['shop_id'],)).fetchone()
    d.update(title=l['title'],subject=l['subject'],shop_name=s['name'],total=o['fee']+o['deposit'])
    d['delivery'] = l['contact'] if o['status'] in ('paid','completed','disputed') else None
    d['deposit_status'] = {'pending':'待缴纳','expired':'未缴纳','cancelled':'未缴纳','paid':'冻结中','disputed':'争议冻结','completed':'已退回','refunded':'已退回'}[o['status']]
    return d


@app.middleware('http')
async def protection(req, call_next):
    host = req.url.hostname or ''
    if host not in ALLOWED_HOSTS:
        return JSONResponse({'detail':'访问域名不受支持'},400)
    if req.method not in ('GET','HEAD'):
        origin = req.headers.get('origin')
        if origin and origin != str(req.base_url).rstrip('/'):
            return JSONResponse({'detail':'跨站请求已拒绝'},403)
        try:
            length = int(req.headers.get('content-length', '0'))
            if length < 0:
                raise ValueError
        except ValueError:
            return JSONResponse({'detail':'请求无效'},400)
        if length > 16000:
            return JSONResponse({'detail':'请求内容过长'},413)
        key = (req.client.host if req.client else 'unknown',req.url.path == '/api/session')
        now = time.time()
        with rate_lock:
            hits = [t for t in rate_buckets.get(key,[]) if now-t<60]
            if len(hits) >= (20 if key[1] else 120):
                return JSONResponse({'detail':'操作过于频繁，请稍后重试'},429)
            hits.append(now)
            rate_buckets[key] = hits
            if len(rate_buckets)>10000:
                for k in list(rate_buckets):
                    if not rate_buckets[k] or now-rate_buckets[k][-1]>60: del rate_buckets[k]
    res = await call_next(req)
    res.headers['X-Content-Type-Options']='nosniff'
    res.headers['Referrer-Policy']='same-origin'
    res.headers['X-Frame-Options']='DENY'
    res.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    res.headers['Cache-Control']='no-store' if req.url.path.startswith('/api') else 'no-cache'
    res.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return res


@app.get('/api/health')
def health():
    with db() as c: c.execute('SELECT 1')
    return {'status':'ok','mode':'sandbox','payments':'disabled','version':'0.1.0'}


@app.post('/api/session')
def start_session(req: Request):
    token = req.cookies.get('jx_session','')
    with db() as c:
        w = c.execute('SELECT * FROM workspaces WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        if not w:
            # Expired data is purged in dependency order, keeping all runtime data out of source trees.
            expired = [r[0] for r in c.execute('SELECT id FROM workspaces WHERE expires<?',(int(time.time()),)).fetchall()]
            for old in expired:
                for table in ('events','ledger','orders','listings','shops','workspaces'):
                    c.execute(f'DELETE FROM {table} WHERE {"id" if table=="workspaces" else "workspace"}=?',(old,))
            if c.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0]>=3000: fail(503,'体验人数较多，请稍后再试')
            token = secrets.token_urlsafe(32)
            wid = uid('w_')
            c.execute('INSERT INTO workspaces(id,token_hash,csrf,expires) VALUES(?,?,?,?)',(wid,hashlib.sha256(token.encode()).hexdigest(),secrets.token_urlsafe(24),int(time.time())+7*86400))
            seed(c,wid)
            w = c.execute('SELECT * FROM workspaces WHERE id=?',(wid,)).fetchone()
        res = JSONResponse({'mode':'sandbox','csrf':w['csrf'],'role':w['role'],'merchant_shop':w['merchant_shop'],'expires':w['expires']})
        res.set_cookie('jx_session',token,httponly=True,secure=COOKIE_SECURE,samesite='strict',max_age=7*86400)
        return res


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)

class Role(StrictModel):
    role: Literal['customer','merchant','platform']
    shop_id: str | None = None

@app.post('/api/demo/role')
def switch_role(data:Role,req:Request):
    with db() as c:
        w=session(c,req)
        shop_id=data.shop_id or w['merchant_shop']
        if data.shop_id:
            s=c.execute("SELECT * FROM shops WHERE id=? AND workspace=? AND status='active'",(data.shop_id,w['id'])).fetchone()
            if not s: fail(404,'店铺不存在或尚未开通')
        c.execute('UPDATE workspaces SET role=?,merchant_shop=? WHERE id=?',(data.role,shop_id,w['id']))
        return {'role':data.role,'merchant_shop':shop_id}

@app.get('/api/shops/{slug}')
def get_shop(slug:str,req:Request):
    with db() as c:
        w=session(c,req)
        expire_orders(c,w['id'])
        s=c.execute("SELECT * FROM shops WHERE slug=? AND workspace=? AND status='active'",(slug,w['id'])).fetchone()
        if not s: fail(404,'店铺不存在或尚未开通，请向商家确认入口')
        ls=c.execute("SELECT * FROM listings WHERE shop_id=? AND status='active' ORDER BY created DESC",(s['id'],)).fetchall()
        shop=dict(s); shop.pop('workspace')
        return {'shop':shop,'listings':[listing_json(c,l) for l in ls]}

class NewOrder(StrictModel):
    listing_id: str
    idempotency_key: str = Field(min_length=16,max_length=80)
    accepted: Literal[True]

@app.post('/api/orders',status_code=201)
def create_order(data:NewOrder,req:Request):
    with db() as c:
        w=session(c,req,('customer',)); expire_orders(c,w['id'])
        prior=c.execute('SELECT * FROM orders WHERE workspace=? AND idempotency=?',(w['id'],data.idempotency_key)).fetchone()
        if prior:
            if prior['listing_id']!=data.listing_id: fail(409,'请求编号已用于另一订单')
            return order_json(c,prior)
        l=c.execute("SELECT l.* FROM listings l JOIN shops s ON s.id=l.shop_id WHERE l.id=? AND l.workspace=? AND l.status='active' AND s.status='active'",(data.listing_id,w['id'])).fetchone()
        if not l: fail(404,'该家教单已下架')
        if not available(c,l): fail(409,'该家教单已被接走，请选择其他订单')
        now=int(time.time()); oid=uid('JJ')
        c.execute('INSERT INTO orders(id,workspace,listing_id,shop_id,status,fee,deposit,created,updated,idempotency) VALUES(?,?,?,?,?,?,?,?,?,?)',(oid,w['id'],l['id'],l['shop_id'],'pending',l['fee'],l['deposit'],now,now,data.idempotency_key))
        event(c,w['id'],'创建订单',oid)
        return order_json(c,c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())

@app.get('/api/orders')
def my_orders(req:Request):
    with db() as c:
        w=session(c,req,('customer',)); expire_orders(c,w['id'])
        return [order_json(c,o) for o in c.execute('SELECT * FROM orders WHERE workspace=? ORDER BY created DESC',(w['id'],)).fetchall()]

class OrderAction(StrictModel):
    action: Literal['pay','cancel','complete','dispute','refund','reject_refund']
    reason: str = Field(default='',max_length=500)

@app.post('/api/orders/{oid}/action')
def act_order(oid:str,data:OrderAction,req:Request):
    with db() as c:
        w=session(c,req); expire_orders(c,w['id'])
        o=c.execute('SELECT * FROM orders WHERE id=? AND workspace=?',(oid,w['id'])).fetchone()
        if not o: fail(404,'订单不存在')
        is_admin=data.action in ('refund','reject_refund')
        if w['role']!=('platform' if is_admin else 'customer'): fail(403,'当前身份没有此操作权限')
        if data.action in ('dispute','refund','reject_refund') and len(data.reason)<4: fail(422,'请填写至少 4 个字的处理说明')
        mapping={'pay':('pending','paid'),'cancel':('pending','cancelled'),'complete':('paid','completed'),'dispute':('paid','disputed'),'refund':('disputed','refunded'),'reject_refund':('disputed','paid')}
        before,after=mapping[data.action]
        if o['status']==after and data.action not in ('dispute','reject_refund'): return order_json(c,o)
        if o['status']!=before: fail(409,'订单状态已变化，请刷新后重试')
        c.execute('UPDATE orders SET status=?,updated=?,reason=? WHERE id=?',(after,int(time.time()),data.reason,oid))
        if data.action=='pay':
            for kind,amount in [('info_fee_hold',o['fee']),('deposit_hold',o['deposit'])]:
                c.execute('INSERT INTO ledger(workspace,order_id,kind,amount,created) VALUES(?,?,?,?,?)',(w['id'],oid,kind,amount,int(time.time())))
        if data.action in ('complete','refund'):
            c.execute('INSERT INTO ledger(workspace,order_id,kind,amount,created) VALUES(?,?,?,?,?)',(w['id'],oid,'deposit_return',-o['deposit'],int(time.time())))
            if data.action=='refund':
                c.execute('INSERT INTO ledger(workspace,order_id,kind,amount,created) VALUES(?,?,?,?,?)',(w['id'],oid,'info_fee_refund',-o['fee'],int(time.time())))
            else:
                c.execute('INSERT INTO ledger(workspace,order_id,kind,amount,created) VALUES(?,?,?,?,?)',(w['id'],oid,'info_fee_settled',o['fee'],int(time.time())))
        event(c,w['id'],{'pay':'模拟支付并交付','cancel':'取消订单','complete':'确认完成，退回保证金','dispute':'申请平台介入','refund':'同意退款','reject_refund':'驳回退款，恢复履约'}[data.action],oid)
        return order_json(c,c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())

class ShopApplication(StrictModel):
    name: str = Field(min_length=2,max_length=30)
    city: str = Field(min_length=2,max_length=20)
    description: str = Field(min_length=5,max_length=200)

@app.post('/api/applications',status_code=201)
def apply_shop(data:ShopApplication,req:Request):
    with db() as c:
        w=session(c,req)
        if c.execute('SELECT COUNT(*) FROM shops WHERE workspace=?',(w['id'],)).fetchone()[0]>=20: fail(400,'每个演示空间最多创建 20 家店铺')
        sid=uid('s_'); slug=secrets.token_urlsafe(9).lower()
        c.execute('INSERT INTO shops VALUES(?,?,?,?,?,?,?,?)',(sid,w['id'],slug,data.name,data.city,data.description,'pending',0))
        event(c,w['id'],'提交入驻申请',sid)
        return {'id':sid,'status':'pending','name':data.name}

class ShopAction(StrictModel):
    action: Literal['approve','reject','suspend','resume']

@app.post('/api/shops/{sid}/action')
def act_shop(sid:str,data:ShopAction,req:Request):
    with db() as c:
        w=session(c,req,('platform',))
        s=c.execute('SELECT * FROM shops WHERE id=? AND workspace=?',(sid,w['id'])).fetchone()
        if not s: fail(404,'店铺不存在')
        before,after={'approve':('pending','active'),'reject':('pending','rejected'),'suspend':('active','suspended'),'resume':('suspended','active')}[data.action]
        if s['status']!=before: fail(409,'店铺状态已变化')
        c.execute('UPDATE shops SET status=? WHERE id=?',(after,sid))
        event(c,w['id'],{'approve':'审核通过并开铺','reject':'驳回入驻','suspend':'暂停店铺','resume':'恢复店铺'}[data.action],sid)
        return {'status':after,'slug':s['slug']}

class ListingInput(StrictModel):
    title:str=Field(min_length=4,max_length=60)
    subject:Literal['数学','英语','语文','物理','化学','其他']
    grade:Literal['小学','初中','高中','其他']
    district:str=Field(min_length=2,max_length=30)
    schedule:str=Field(min_length=3,max_length=80)
    hourly:int=Field(ge=100,le=200000)
    fee:int=Field(ge=0,le=100000)
    deposit:int=Field(ge=0,le=100000)
    description:str=Field(min_length=10,max_length=1000)
    stock:int=Field(ge=1,le=10)

@app.post('/api/listings',status_code=201)
def publish_listing(data:ListingInput,req:Request):
    with db() as c:
        w=session(c,req,('merchant',))
        s=c.execute("SELECT * FROM shops WHERE id=? AND workspace=? AND status='active'",(w['merchant_shop'],w['id'])).fetchone()
        if not s: fail(403,'店铺尚未开通或已暂停')
        if c.execute('SELECT COUNT(*) FROM listings WHERE workspace=?',(w['id'],)).fetchone()[0]>=100: fail(400,'演示空间最多发布 100 个家教单')
        lid=uid('l_')
        c.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(lid,w['id'],s['id'],data.title,data.subject,data.grade,data.district,data.schedule,data.hourly,data.fee,data.deposit,data.description,'演示联系人：店铺老师\n演示微信：DEMO-SHOP\n此处展示交付模板，未录入真实个人信息。',data.stock,'active',int(time.time())))
        event(c,w['id'],'发布家教单',lid)
        return {'id':lid}

class ListingAction(StrictModel):
    status:Literal['active','hidden']

@app.patch('/api/listings/{lid}')
def toggle_listing(lid:str,data:ListingAction,req:Request):
    with db() as c:
        w=session(c,req,('merchant',))
        l=c.execute('SELECT * FROM listings WHERE id=? AND workspace=? AND shop_id=?',(lid,w['id'],w['merchant_shop'])).fetchone()
        if not l: fail(404,'家教单不存在')
        c.execute('UPDATE listings SET status=? WHERE id=?',(data.status,lid))
        event(c,w['id'],'上架家教单' if data.status=='active' else '下架家教单',lid)
        return {'status':data.status}

@app.post('/api/merchant/deposit')
def merchant_deposit(req:Request):
    with db() as c:
        w=session(c,req,('merchant',))
        s=c.execute("SELECT * FROM shops WHERE id=? AND workspace=? AND status='active'",(w['merchant_shop'],w['id'])).fetchone()
        if not s: fail(404,'店铺未开通')
        if s['deposit']==0:
            c.execute('UPDATE shops SET deposit=200000 WHERE id=?',(s['id'],))
            event(c,w['id'],'模拟缴纳商家保证金',s['id'])
        return {'deposit':200000,'mode':'sandbox'}

@app.get('/api/workbench')
def workbench(req:Request):
    with db() as c:
        w=session(c,req,('merchant','platform')); expire_orders(c,w['id'])
        scope='workspace=?'; args=[w['id']]
        if w['role']=='merchant': scope+=' AND shop_id=?'; args.append(w['merchant_shop'])
        orders=c.execute(f'SELECT * FROM orders WHERE {scope} ORDER BY created DESC',args).fetchall()
        listings=c.execute(f'SELECT * FROM listings WHERE {scope} ORDER BY created DESC',args).fetchall()
        shopq='workspace=?'+(' AND id=?' if w['role']=='merchant' else '')
        shops=[dict(s) for s in c.execute(f'SELECT * FROM shops WHERE {shopq}',args).fetchall()]
        for s in shops: s.pop('workspace')
        events=[dict(e) for e in c.execute('SELECT action,entity,created FROM events WHERE workspace=? ORDER BY id DESC LIMIT 30',(w['id'],)).fetchall()] if w['role']=='platform' else []
        ledger=[dict(e) for e in c.execute('SELECT l.kind,l.amount,l.created,l.order_id FROM ledger l JOIN orders o ON l.order_id=o.id WHERE o.'+scope.replace(' AND shop_id',' AND o.shop_id')+' ORDER BY l.id DESC LIMIT 100',args).fetchall()]
        held=sum(o['deposit'] for o in orders if o['status'] in ('paid','disputed'))
        settled=sum(o['fee'] for o in orders if o['status']=='completed')
        return {'shops':shops,'listings':[listing_json(c,l) for l in listings],'orders':[order_json(c,o) for o in orders], 'events':events,'ledger':ledger,'stats':{'orders':len(orders),'held_deposits':held,'settled_fees':settled,'disputes':sum(o['status']=='disputed' for o in orders),'active_shops':sum(s['status']=='active' for s in shops)}}

@app.get('/robots.txt')
def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('User-agent: *\nDisallow: /\n')

@app.get('/{path:path}')
def frontend(path:str):
    if path.startswith('api/'): fail(404,'接口不存在')
    target=(FRONTEND/path).resolve()
    if target.is_relative_to(FRONTEND) and target.is_file() and target.suffix in ('.html','.js','.css','.svg','.png','.ico','.webp'):
        return FileResponse(target)
    if '.' in path: fail(404,'文件不存在')
    return FileResponse(FRONTEND/'index.html')
