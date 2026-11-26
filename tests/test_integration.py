from uuid import uuid4
from datetime import datetime,timezone

PASS='test-password-strong-123'
def register(c,name):
    r=c.post('/api/auth/register',json={'login':name,'display_name':name,'password':PASS})
    assert r.status_code==201,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    return c.get('/api/auth/me').json()
def op(**args):return {'request_id':str(uuid4()),**args}
def post(c,path,data):
    r=c.post('/api'+path,json=data);assert r.status_code<300,r.text;return r.json()
def catalogs(c):
    data=c.get('/api/catalogs').json()
    return {kind:[r['id'] for r in data if r['edition']=='2024' and r['kind']==kind] for kind in ('team','mission','killzone','source')}
def ready_match(a,b):
    ua=register(a,'alpha');ub=register(b,'bravo');cats=catalogs(a)
    post(a,'/friends',{'public_id':ub['public_id']})
    post(b,'/friends/'+ua['public_id'],{'action':'accept'})
    ch=post(a,'/challenges',op(public_id=ub['public_id']))
    result=post(b,'/challenges/'+ch['id'],op(action='accepted'));mid=result['match_id']
    m=a.get('/api/matches/'+mid).json()
    # Historical fixture: simulate a match saved by v1.0 BEFORE catalog retirement.
    # No production route may select inactive catalogs for a new setup.
    import os,psycopg
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
        legacy={r[0]:r[1] for r in conn.execute("SELECT code,id FROM catalogs WHERE verification='legacy'").fetchall()}
        conn.execute('UPDATE matches SET mission_id=%s,killzone_id=%s WHERE id=%s',(legacy['2024-mission'],legacy['2024-zone'],mid))
        conn.execute('UPDATE match_players SET team_id=CASE slot WHEN 1 THEN %s ELSE %s END WHERE match_id=%s',(legacy['2024-team-a'],legacy['2024-team-b'],mid))
        conn.execute("INSERT INTO match_audit(match_id,actor_id,action,before_data,after_data) VALUES(%s,%s,'setup','{}','{}')",(mid,ua['id']))
        conn.execute('UPDATE matches SET version=version+1 WHERE id=%s',(mid,))
        cats['source']=[legacy['2024-vp-critical']]
    m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='start'))
    return ua,ub,mid,cats

def test_authentication_csrf_login_and_logout(clients):
    a,b=clients;u=register(a,'alpha')
    assert len(u['public_id'])==8
    assert b.get('/api/auth/me').status_code==401
    assert a.post('/api/auth/logout',json={},headers={'X-CSRF-Token':'bad'}).status_code==403
    assert a.post('/api/auth/logout',json={},headers={'Origin':'https://evil.invalid'}).status_code==403
    post(a,'/auth/logout',{})
    assert a.get('/api/auth/me').status_code==401
    assert a.post('/api/auth/login',json={'identity':'alpha','password':'bad'}).status_code==401
    assert a.post('/api/auth/login',json={'identity':'alpha','password':PASS}).status_code==200

def test_finish_confirmation_idempotency_and_stats(clients):
    a,b=clients;ua,ub,mid,cats=ready_match(a,b)
    m=a.get('/api/matches/'+mid).json()
    p=op(version=m['version'],turning_point=1,source_id=cats['source'][0],delta=3)
    post(a,'/matches/'+mid+'/scores',p);post(a,'/matches/'+mid+'/scores',p)
    m=a.get('/api/matches/'+mid).json();assert m['players'][0]['vp']==3
    assert a.post('/api/matches/'+mid+'/scores',json=op(version=1,turning_point=1,source_id=cats['source'][0],delta=1)).status_code==409
    post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='finish'))
    assert a.get('/api/stats').json()['summary']['games']==0
    m=b.get('/api/matches/'+mid).json()
    assert a.post('/api/matches/'+mid+'/actions',json=op(version=m['version'],action='confirm')).status_code==409
    post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='confirm'))
    sa=a.get('/api/stats').json();sb=b.get('/api/stats').json()
    assert sa['summary']['games']==1 and sa['summary']['wins']==1
    assert sa['summary']['avg_for']==3 and sa['summary']['avg_diff']==3
    assert sa['streak']=={'best':1,'current':1}
    assert sb['summary']['losses']==1 and sb['summary']['avg_against']==3
    assert len(a.get('/api/matches/'+mid+'/audit').json())==6  # v1.14: + cp_start (2CP after the equipment reveal)
    assert a.get('/api/export?format=csv').status_code==200

def test_guest_privacy_exports_and_anonymization(clients):
    a,b=clients;ua=register(a,'alpha');register(b,'bravo');cats=catalogs(a)
    p=op(guest_name='=UNTRUSTED',team1_id=cats['team'][0],team2_id=cats['team'][1],mission_id=cats['mission'][0],killzone_id=cats['killzone'][0],vp_for=7,vp_against=4,played_at=datetime.now(timezone.utc).isoformat())
    mid=post(a,'/quick-matches',p)['id'];assert post(a,'/quick-matches',p)['id']==mid
    assert b.get('/api/matches/'+mid).status_code==404
    assert b.get('/api/stats').json()['summary']['games']==0
    assert a.get('/api/stats').json()['summary']['games']==1
    assert "'=UNTRUSTED" in a.get('/api/export?format=csv').text
    assert a.get('/api/history?from_date=2026-02-31').status_code==422

def test_dispute_and_account_deletion(clients):
    a,b=clients;ua,ub,mid,cats=ready_match(a,b)
    m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='finish'))
    m=b.get('/api/matches/'+mid).json();post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='dispute'))
    assert b.get('/api/stats').json()['summary']['games']==0
    m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='reopen'))
    m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='finish'))
    m=b.get('/api/matches/'+mid).json();post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='confirm'))
    r=a.request('DELETE','/api/profile',json={'password':PASS});assert r.status_code==200,r.text
    m=b.get('/api/matches/'+mid).json();assert m['players'][0]['display_name']=='Удалённый игрок'
    assert m['players'][0]['user_id'] is None
    assert b.get('/api/stats').json()['summary']['games']==1

def test_concurrent_updates_blocking_and_rate_limit(clients):
    from concurrent.futures import ThreadPoolExecutor
    a,b=clients;ua,ub,mid,cats=ready_match(a,b)
    m=a.get('/api/matches/'+mid).json()
    pa=op(version=m['version'],turning_point=1,source_id=cats['source'][0],delta=1)
    pb=op(version=m['version'],turning_point=1,source_id=cats['source'][0],delta=2)
    with ThreadPoolExecutor(2) as executor:
        fa=executor.submit(a.post,'/api/matches/'+mid+'/scores',json=pa)
        fb=executor.submit(b.post,'/api/matches/'+mid+'/scores',json=pb)
        assert sorted([fa.result().status_code,fb.result().status_code])==[200,409]
    ch=post(a,'/challenges',op(public_id=ub['public_id']))
    post(b,'/friends/'+ua['public_id'],{'action':'block'})
    rows=a.get('/api/challenges').json();assert next(c for c in rows if c['id']==ch['id'])['status']=='cancelled'
    assert a.post('/api/friends',json={'public_id':ub['public_id']}).status_code==403
    assert a.post('/api/challenges',json=op(public_id=ub['public_id'])).status_code==403
    for i in range(16):
        response=b.post('/api/auth/login',json={'identity':'missing','password':'invalid'})
    assert response.status_code==429

def test_statistics_aggregates_filters_and_streaks(clients):
    a,b=clients;register(a,'alpha');cats=catalogs(a)
    for day,vp_for,vp_against in [('2026-01-01',5,1),('2026-01-02',5,1),('2026-02-01',0,2),('2026-02-02',4,1)]:
        post(a,'/quick-matches',op(guest_name='Гость',team1_id=cats['team'][0],team2_id=cats['team'][1],mission_id=cats['mission'][0],killzone_id=cats['killzone'][0],vp_for=vp_for,vp_against=vp_against,played_at=day+'T12:00:00+03:00'))
    data=a.get('/api/stats').json();s=data['summary']
    assert (s['games'],s['wins'],s['draws'],s['losses'],s['win_rate'])==(4,3,0,1,75)
    assert (s['avg_for'],s['avg_against'],s['avg_diff'])==(3.5,1.25,2.25)
    assert data['streak']=={'best':2,'current':1}
    assert len(data['trend'])==2
    filtered=a.get('/api/stats?from_date=2026-02-01&to_date=2026-02-28&kind=guest').json()
    assert filtered['summary']['games']==2 and filtered['summary']['win_rate']==50
    assert filtered['summary']['avg_diff']==0.5
    assert data['breakdown']['team_id'][0]['games']==4
    assert data['breakdown']['opponent_id']==[]
