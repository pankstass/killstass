from datetime import datetime, timezone
from tests.test_integration import register, op, post, catalogs

def body(c, opponent):
    cats=catalogs(c)
    return op(opponent_public_id=opponent, team1_id=cats['team'][0], team2_id=cats['team'][1], mission_id=cats['mission'][0], killzone_id=cats['killzone'][0], vp_for=17, vp_against=11, played_at=datetime.now(timezone.utc).isoformat())

def test_recorded_match_confirmation_and_idempotency(clients):
    a,b=clients; ua=register(a,'alpha'); ub=register(b,'bravo')
    p=body(a,ub['public_id']); mid=post(a,'/quick-matches',p)['id']
    assert post(a,'/quick-matches',p)['id']==mid
    m=b.get('/api/matches/'+mid).json()
    assert m['recorded_result'] and m['status']=='awaiting_confirmation'
    assert any(n['kind']=='match_awaiting_confirmation' and str(n['resource_id'])==mid for n in b.get('/api/notifications').json())
    assert [x['vp'] for x in m['players']]==[17,11]
    assert a.get('/api/stats').json()['summary']['games']==0
    assert b.get('/api/stats').json()['summary']['games']==0
    assert a.post('/api/matches/'+mid+'/actions',json=op(version=m['version'],action='confirm')).status_code==409
    post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='confirm'))
    sa=a.get('/api/stats').json()['summary']; sb=b.get('/api/stats').json()['summary']
    assert sa['games']==1 and sa['wins']==1 and sa['avg_for']==17
    assert sb['games']==1 and sb['losses']==1 and sb['avg_for']==11

def test_recorded_dispute_cancel_and_validation(clients):
    a,b=clients; ua=register(a,'alpha'); ub=register(b,'bravo')
    p=body(a,ub['public_id']); mid=post(a,'/quick-matches',p)['id']
    m=b.get('/api/matches/'+mid).json();post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='dispute'))
    m=a.get('/api/matches/'+mid).json()
    assert a.post('/api/matches/'+mid+'/actions',json=op(version=m['version'],action='reopen')).status_code==409
    assert b.post('/api/matches/'+mid+'/actions',json=op(version=m['version'],action='cancel')).status_code==409
    post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='cancel'))
    assert a.get('/api/stats').json()['summary']['games']==0
    assert a.post('/api/quick-matches',json=body(a,ua['public_id'])).status_code==404
    p=body(a,ub['public_id']);p['local']=True
    assert a.post('/api/quick-matches',json=p).status_code==422
    post(b,'/friends/'+ua['public_id'],{'action':'block'})
    assert a.post('/api/quick-matches',json=body(a,ub['public_id'])).status_code==403
