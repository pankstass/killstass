"""v1.2: match invites by code and single-device hot-seat matches (PostgreSQL integration)."""
import os
from uuid import uuid4
import psycopg
from tests.test_integration import register,post,op

def pick(data,kind,code):return next(r['id'] for r in data if r['kind']==kind and r['code'].endswith(code))

def approved_ids(c):
    data=c.get('/api/catalogs').json()
    return data,dict(team=pick(data,'team','team-angel-of-death'),mission=pick(data,'mission','mission-secure'),
        zone=pick(data,'killzone','volkus-1'),tac=pick(data,'tac_op','tac-op-rout'),
        crit=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit'))

def ver(c,mid):return c.get('/api/matches/'+mid).json()['version']

def test_register_without_display_name_uses_login(clients):
    a,_=clients
    r=a.post('/api/auth/register',json={'login':'solo','password':'test-password-strong-123'})
    assert r.status_code==201,r.text
    a.headers['X-CSRF-Token']=r.json()['csrf']
    assert a.get('/api/auth/me').json()['display_name']=='solo'

def test_invite_join_flow_without_friendship(clients):
    a,b=clients;ua=register(a,'alpha')
    mid=post(a,'/matches',op(kind='friend'))['id']
    # Start is impossible until somebody joins.
    r=a.post('/api/matches/'+mid+'/actions',json=op(version=ver(a,mid),action='start'))
    assert r.status_code in (409,422),r.text
    inv=post(a,'/matches/'+mid+'/invite',op())
    assert len(inv['code'])==6
    assert a.get('/api/matches/'+mid).json()['invite']['code']==inv['code']
    # A new code replaces the old one.
    inv2=post(a,'/matches/'+mid+'/invite',op())
    assert inv2['code']!=inv['code']
    ub=register(b,'bravo')
    assert b.post('/api/invites/'+inv['code']+'/join',json=op()).status_code==404
    assert a.post('/api/invites/'+inv2['code']+'/join',json=op()).status_code==409  # own match
    assert b.get('/api/matches/'+mid).status_code==404  # not a member yet
    joined=post(b,'/invites/'+inv2['code'].lower()+'/join',op())
    assert joined['match_id']==mid
    m=b.get('/api/matches/'+mid).json()
    assert m['players'][1]['user_id']==ub['id'] and m['players'][1]['display_name']=='bravo'
    assert m['invite'] is None
    # Used code cannot be reused; the match is full now.
    assert b.post('/api/invites/'+inv2['code']+'/join',json=op()).json()['match_id']==mid  # idempotent for the joiner
    r=a.post('/api/matches/'+mid+'/invite',json=op());assert r.status_code==409 and r.json()['detail']=='match_full'
    assert any(n['kind']=='match_joined' for n in a.get('/api/notifications').json())
    # Opponent is a regular friend-kind participant: may write only own slot.
    r=b.put('/api/matches/'+mid+'/player-setup',json=op(version=ver(b,mid),slot=1,roster='x'))
    assert r.status_code==403 and r.json()['detail']=='slot_forbidden'

def test_invite_expiry_block_and_cancel(clients):
    a,b=clients;ua=register(a,'alpha');ub=register(b,'bravo')
    mid=post(a,'/matches',op(kind='friend'))['id']
    code=post(a,'/matches/'+mid+'/invite',op())['code']
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
        conn.execute("UPDATE match_invites SET expires_at=now()-interval '1 minute' WHERE code=%s",(code,))
    r=b.post('/api/invites/'+code+'/join',json=op());assert r.status_code==410 and r.json()['detail']=='invite_expired'
    code=post(a,'/matches/'+mid+'/invite',op())['code']
    post(a,'/friends/'+ub['public_id'],{'action':'block'})
    assert b.post('/api/invites/'+code+'/join',json=op()).status_code==403
    post(a,'/friends/'+ub['public_id'],{'action':'unblock'})
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='cancel'))
    r=b.post('/api/invites/'+code+'/join',json=op());assert r.status_code==404
    assert all(m['id']!=mid for m in a.get('/api/live-matches').json())

def test_hotseat_full_approved_match_counts_for_owner_only(clients):
    a,b=clients;ua=register(a,'alpha');ub=register(b,'bravo')
    data,ids=approved_ids(a)
    mid=post(a,'/matches',op(kind='hotseat',guest_name='Вася'))['id']
    assert b.get('/api/matches/'+mid).status_code==404
    r=a.put('/api/matches/'+mid+'/setup',json=op(version=ver(a,mid),mission_id=ids['mission'],killzone_id=ids['zone'],team1_id=ids['team'],team2_id=ids['team'],operative_count=6,tac_op_id=ids['tac'],primary_op='crit'))
    assert r.status_code==200,r.text
    # Start without the guest's secret setup is refused.
    assert a.post('/api/matches/'+mid+'/actions',json=op(version=ver(a,mid),action='start')).status_code==422
    r=a.put('/api/matches/'+mid+'/player-setup',json=op(version=ver(a,mid),slot=2,operative_count=6,tac_op_id=ids['tac'],primary_op='kill'))
    assert r.status_code==200,r.text
    m=a.get('/api/matches/'+mid).json()
    guest=m['players'][1]
    assert guest['user_id'] is None and guest['secret_set'] and guest['primary_op'] is None and guest['tac_op_id'] is None
    assert not any('kill' in str(x['after_data']) and 'primary' in str(x['after_data']) for x in a.get('/api/matches/'+mid+'/audit').json())
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='start'))
    for slot,primary in ((None,'crit'),(2,'kill')):
        post(a,'/matches/'+mid+'/primary',op(version=ver(a,mid),primary_op=primary,**({'slot':slot} if slot else {})))
    for tp in (2,3,4):
        post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='turn',turning_point=tp))
        post(a,'/matches/'+mid+'/scores',op(version=ver(a,mid),turning_point=tp,source_id=ids['crit'],delta=1))
        post(a,'/matches/'+mid+'/scores',op(version=ver(a,mid),turning_point=tp,source_id=ids['crit'],delta=1,slot=2))
        post(a,'/matches/'+mid+'/scores',op(version=ver(a,mid),turning_point=tp,cp=2,slot=2))
    for _ in range(6): post(a,'/matches/'+mid+'/kills',op(version=ver(a,mid),turning_point=4,delta=1,slot=2))
    r=a.post('/api/matches/'+mid+'/kills',json=op(version=ver(a,mid),turning_point=4,delta=1,slot=2));assert r.status_code==422
    # Confirm/dispute make no sense without a remote opponent.
    assert a.post('/api/matches/'+mid+'/actions',json=op(version=ver(a,mid),action='confirm')).status_code==409
    assert post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='finish'))['status']=='unconfirmed'
    m=a.get('/api/matches/'+mid).json()
    me,guest=m['players']
    assert m['status']=='unconfirmed' and guest['primary_op']=='kill'
    assert me['crit']==3 and me['primary_bonus']==2 and me['vp']==5
    assert guest['crit']==3 and guest['incapacitated']==6 and guest['kill']>0 and guest['vp']>me['vp']
    # Locked after finish.
    assert a.post('/api/matches/'+mid+'/scores',json=op(version=m['version'],turning_point=4,cp=1)).status_code==409
    h=a.get('/api/history').json()
    assert h['total']==1 and h['items'][0]['kind']=='hotseat' and h['items'][0]['result']=='loss' and h['items'][0]['opponent_name']=='Вася'
    assert a.get('/api/stats?kind=hotseat').json()['summary']['games']==1
    assert b.get('/api/history').json()['total']==0

def test_hotseat_slot_rules_and_account_deletion(clients):
    a,b=clients;ua=register(a,'alpha');ub=register(b,'bravo')
    mid=post(a,'/matches',op(kind='hotseat'))['id']
    assert a.post('/api/matches/'+mid+'/invite',json=op()).status_code==409
    code_match=post(a,'/matches',op(kind='friend'))['id']
    code=post(a,'/matches/'+code_match+'/invite',op())['code']
    post(b,'/invites/'+code+'/join',op())
    # The creator cannot write a registered opponent's slot.
    r=a.put('/api/matches/'+code_match+'/player-setup',json=op(version=ver(a,code_match),slot=2,roster='x'))
    assert r.status_code==403
    r=a.put('/api/matches/'+mid+'/player-setup',json=op(version=ver(a,mid),slot=2,roster='гость',operative_count=7))
    assert r.status_code==200
    assert a.get('/api/matches/'+mid).json()['players'][1]['roster']=='гость'
    r=a.request('DELETE','/api/profile',json={'password':'test-password-strong-123'});assert r.status_code==200
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM matches WHERE id=%s',(mid,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM matches WHERE id=%s',(code_match,)).fetchone()[0]==1

def test_open_setup_limit(clients):
    a,_=clients;register(a,'alpha')
    for _ in range(10): post(a,'/matches',op(kind='hotseat'))
    r=a.post('/api/matches',json=op(kind='hotseat'));assert r.status_code==429 and r.json()['detail']=='too_many_open_matches'
