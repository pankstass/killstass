"""v1.5: read-only result links and local feedback."""
import os
import psycopg
from fastapi.testclient import TestClient
from api.main import app,ORIGIN
from tests.test_integration import register,post,op,PASS
from tests.test_quickstart import ver
from tests.test_catalog_ops import approved_match
from tests.test_turns import play_to_tp4

def finished(a,b):
    mid,data=approved_match(a,b)
    crit=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    play_to_tp4(a,b,mid,crit)
    return mid

def test_share_link_public_view_replace_and_revoke(clients):
    a,b=clients;mid,data=approved_match(a,b)
    assert a.post('/api/matches/'+mid+'/share',json={}).json()['detail']=='share_unavailable'  # active: nothing to share yet
    crit=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    play_to_tp4(a,b,mid,crit)
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='finish'))
    r=a.post('/api/matches/'+mid+'/share',json={});assert r.status_code==201,r.text
    token=r.json()['token'];assert len(token)>=20
    assert a.get('/api/matches/'+mid+'/share').json()['active']
    anon=TestClient(app,base_url=ORIGIN)  # no `with`: lifespan would close the shared pool
    if True:
        s=anon.get('/api/shared/'+token);assert s.status_code==200,s.text
        body=s.json();text=s.text
        assert body['status']=='awaiting_confirmation' and body['mission'] and len(body['players'])==2
        assert {p['primary_op'] for p in body['players']}=={'crit','kill'}  # ended: primary is public
        assert body['mission_code'] and all(p['team_code'] for p in body['players'])  # v1.6: codes for English labels
        assert sum(x['vp'] for x in body['turn_scores'] if x['slot']==1)==3
        for secret in ('user_id','public_id','roster','notes','csrf'): assert secret not in text
        token2=post(b,'/matches/'+mid+'/share',{})['token']
        assert anon.get('/api/shared/'+token).status_code==404 and anon.get('/api/shared/'+token2).status_code==200
        assert anon.get('/api/shared/short').status_code==404
        assert b.request('DELETE','/api/matches/'+mid+'/share',json={}).status_code==200
        assert anon.get('/api/shared/'+token2).status_code==404
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        assert c.execute('SELECT count(*) FROM match_shares').fetchone()[0]==0
        # only the hash is stored
        post(a,'/matches/'+mid+'/share',{})
        assert len(c.execute('SELECT token_hash FROM match_shares').fetchone()[0])==64

def test_share_requires_membership(clients):
    a,b=clients;mid=finished(a,b)
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='finish'))
    c=TestClient(app,base_url=ORIGIN,headers={'Origin':ORIGIN})
    if True:
        register(c,'charlie')
        assert c.post('/api/matches/'+mid+'/share',json={}).status_code==404
        assert c.get('/api/matches/'+mid+'/share').status_code==404

def test_feedback_validation_and_account_deletion(clients):
    a,_=clients;register(a,'alpha')
    assert a.post('/api/feedback',json={'message':'Нужен таймер на 90 минут','page':'#match'}).status_code==201
    assert a.post('/api/feedback',json={'message':''}).status_code==422
    assert a.post('/api/feedback',json={'message':'x'*2001}).status_code==422
    assert a.post('/api/feedback',json={'message':'ok','extra':1}).status_code==422
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        assert c.execute('SELECT count(*) FROM feedback').fetchone()[0]==1
        r=a.request('DELETE','/api/profile',json={'password':PASS});assert r.status_code==200,r.text
        assert c.execute('SELECT count(*) FROM feedback').fetchone()[0]==0
