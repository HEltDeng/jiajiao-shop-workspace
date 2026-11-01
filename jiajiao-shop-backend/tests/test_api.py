import importlib.util
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

os.environ['DATABASE_PATH'] = '/tmp/jiajiao-test-' + secrets.token_hex(6) + '.sqlite3'
spec = importlib.util.spec_from_file_location('shop_app',Path(__file__).parents[1]/'app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@pytest.fixture
def client():
    module.rate_buckets.clear()
    with TestClient(module.app) as c:
        info=c.post('/api/session',json={}).json()
        c.headers['X-CSRF-Token']=info['csrf']
        yield c


def shop(c):
    r=c.get('/api/shops/qinghe'); assert r.status_code==200
    return r.json()


def order(c,lid=None,key=None):
    lid=lid or shop(c)['listings'][0]['id']
    return c.post('/api/orders',json={'listing_id':lid,'idempotency_key':key or secrets.token_hex(16),'accepted':True})


def role(c,r,shop_id=None):
    response=c.post('/api/demo/role',json={'role':r,**({'shop_id':shop_id} if shop_id else {})})
    assert response.status_code==200, response.text


def action(c,oid,name,reason=''):
    return c.post(f'/api/orders/{oid}/action',json={'action':name,'reason':reason})


def test_delivery_hidden_and_server_prices(client):
    listing=shop(client)['listings'][0]
    assert 'contact' not in listing
    r=client.post('/api/orders',json={'listing_id':listing['id'],'idempotency_key':secrets.token_hex(16),'accepted':True,'fee':1})
    assert r.status_code==422
    o=order(client).json()
    assert o['fee']==listing['fee'] and o['delivery'] is None
    paid=action(client,o['id'],'pay').json()
    assert paid['status']=='paid' and 'DEMO' in paid['delivery']


def test_completion_idempotent_and_ledger(client):
    o=order(client).json(); oid=o['id']
    assert action(client,oid,'pay').status_code==200
    assert action(client,oid,'pay').status_code==200
    assert action(client,oid,'complete').status_code==200
    assert action(client,oid,'complete').status_code==200
    assert action(client,oid,'dispute','信息不准确').status_code==409
    role(client,'platform')
    w=client.get('/api/workbench').json()
    assert len(w['ledger'])==4
    assert w['stats']['held_deposits']==0
    assert w['stats']['settled_fees']==o['fee']


def test_full_refund_requires_platform_and_reason(client):
    o=order(client).json(); oid=o['id']
    action(client,oid,'pay')
    assert action(client,oid,'dispute','坏').status_code==422
    assert action(client,oid,'dispute','联系信息不符合约定').status_code==200
    assert action(client,oid,'complete').status_code==409
    assert action(client,oid,'refund','核实后同意退回').status_code==403
    role(client,'merchant')
    assert action(client,oid,'refund','核实后同意退回').status_code==403
    role(client,'platform')
    assert action(client,oid,'refund','核实后同意退回').status_code==200
    assert action(client,oid,'refund','核实后同意退回').status_code==200
    w=client.get('/api/workbench').json()
    assert len(w['ledger'])==4 and sum(l['amount'] for l in w['ledger'])==0
    assert w['stats']['disputes']==0


def test_cross_workspace_isolation(client):
    listing=shop(client)['listings'][0]; oid=order(client).json()['id']
    with TestClient(module.app) as other:
        s=other.post('/api/session',json={}).json(); other.headers['X-CSRF-Token']=s['csrf']
        assert order(other,listing['id']).status_code==404
        assert action(other,oid,'pay').status_code==404
        role(other,'platform')
        assert other.get('/api/workbench').json()['orders']==[]


def test_csrf_origin_and_permissions(client):
    assert client.get('/api/workbench').status_code==403
    assert client.post('/api/demo/role',json={'role':'platform'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/api/session',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    assert client.get('/robots.txt').text=='User-agent: *\nDisallow: /\n'


@pytest.mark.parametrize('length', [None, '1'])
def test_body_limit_counts_streamed_bytes(client, length):
    headers = {'Content-Type': 'application/json'}
    if length is not None:
        headers['Content-Length'] = length
    response = client.post('/api/demo/role', headers=headers,
                           content=iter([b'{"role":"customer"}', b' ' * 16000]))
    assert response.status_code == 413


@pytest.mark.parametrize('length', ['invalid', '-1'])
def test_invalid_content_length_is_rejected(client, length):
    response = client.post('/api/demo/role', content=b'{}',
                           headers={'Content-Length': length})
    assert response.status_code == 400


def test_body_at_limit_preserves_normal_role_switch(client):
    body = b'{"role":"merchant"}'
    response = client.post('/api/demo/role', content=body.ljust(16000, b' '),
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 200
    assert response.json()['role'] == 'merchant'


def test_non_ascii_csrf_is_denied_without_server_error(client):
    response = client.post('/api/demo/role', json={'role': 'merchant'},
                           headers={b'x-csrf-token': b'\xff'})
    assert response.status_code == 403


def test_idempotency_and_stock_race(client):
    lid=shop(client)['listings'][0]['id']; key=secrets.token_hex(16)
    first=order(client,lid,key).json()
    repeat=order(client,lid,key).json()
    assert first['id']==repeat['id']
    assert order(client,lid).status_code==409
    action(client,first['id'],'cancel')
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda _:order(client,lid).status_code,range(2)))
    assert sorted(codes)==[201,409]


def test_expiry_releases_inventory(client):
    lid=shop(client)['listings'][0]['id']; o=order(client,lid).json()
    with module.db() as c: c.execute('UPDATE orders SET created=created-1000 WHERE id=?',(o['id'],))
    assert action(client,o['id'],'pay').status_code==409
    assert order(client,lid).status_code==201


def test_shop_onboarding_merchant_scope_and_publish(client):
    req=client.post('/api/applications',json={'name':'测试家教','city':'成都','description':'用心服务每一次成长'})
    sid=req.json()['id']
    assert client.post(f'/api/shops/{sid}/action',json={'action':'approve'}).status_code==403
    role(client,'platform')
    r=client.post(f'/api/shops/{sid}/action',json={'action':'approve'}); assert r.status_code==200
    slug=r.json()['slug']
    role(client,'merchant',sid)
    w=client.get('/api/workbench').json()
    assert len(w['shops'])==1 and w['listings']==[] and w['orders']==[]
    orig=shop(client)['listings'][0]
    assert client.patch('/api/listings/'+orig['id'],json={'status':'hidden'}).status_code==404
    data={'title':'初中数学专项辅导','subject':'数学','grade':'初中','district':'武侯区','schedule':'周六下午','hourly':10000,'fee':5000,'deposit':10000,'description':'帮助学生复习基础知识并完成课后练习','stock':1}
    assert client.post('/api/listings',json=data).status_code==201
    assert len(client.get('/api/shops/'+slug).json()['listings'])==1
    assert client.post('/api/merchant/deposit').json()['deposit']==200000
    role(client,'platform')
    assert client.post(f'/api/shops/{sid}/action',json={'action':'suspend'}).status_code==200
    assert client.get('/api/shops/'+slug).status_code==404


def test_static_spa_security_and_real_money_disabled(client):
    assert client.get('/s/qinghe').status_code==200
    assert client.get('/app.py').status_code==404
    assert client.get('/api/missing').status_code==404
    assert client.get('/api/health').json()['payments']=='disabled'
    assert 'noindex' in client.get('/').headers['X-Robots-Tag']
    assert client.get('/api/orders').headers['Cache-Control']=='no-store'


def test_unauthenticated_api_denied():
    with TestClient(module.app) as c:
        assert c.get('/api/shops/qinghe').status_code==401
        assert c.get('/api/orders').status_code==401
