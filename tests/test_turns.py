"""v1.3: initiative per turning point and the privacy-safe "count total points" preview."""
from tests.test_integration import register,post,op
from tests.test_quickstart import approved_ids,ver
from tests.test_catalog_ops import approved_match

def play_to_tp4(a,b,mid,crit):
    for tp in (2,3,4):
        post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='turn',turning_point=tp))
        post(a,'/matches/'+mid+'/scores',op(version=ver(a,mid),turning_point=tp,source_id=crit,delta=1))
        post(b,'/matches/'+mid+'/kills',op(version=ver(b,mid),turning_point=tp,delta=1))

def test_initiative_record_correct_and_limits(clients):
    a,b=clients;mid,data=approved_match(a,b)
    post(a,'/matches/'+mid+'/initiative',op(version=ver(a,mid),turning_point=1,slot=2))
    # The opponent may correct it; both changes are audited.
    post(b,'/matches/'+mid+'/initiative',op(version=ver(b,mid),turning_point=1,slot=1))
    m=a.get('/api/matches/'+mid).json()
    assert m['initiatives']==[{'turning_point':1,'slot':1}]
    assert [x['after_data']['slot'] for x in a.get('/api/matches/'+mid+'/audit').json() if x['action']=='initiative']==[1,2]
    # Future turning point is refused; stale version conflicts.
    r=a.post('/api/matches/'+mid+'/initiative',json=op(version=m['version'],turning_point=2,slot=1));assert r.status_code==409
    r=a.post('/api/matches/'+mid+'/initiative',json=op(version=m['version']-1,turning_point=1,slot=1));assert r.json()['detail']=='version_conflict'

def test_preview_hides_opponent_primary_and_matches_final(clients):
    a,b=clients;mid,data=approved_match(a,b)
    crit=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    assert a.get('/api/matches/'+mid+'/preview').json()['detail']=='preview_closed'
    play_to_tp4(a,b,mid,crit)
    pa=a.get('/api/matches/'+mid+'/preview').json();pb=b.get('/api/matches/'+mid+'/preview').json()
    assert pa['ready']
    own,opp=pa['players']
    assert own['primary_op']=='crit' and own['primary_bonus']==2 and own['vp']==own['base']+2
    assert opp['primary_op'] is None and opp['primary_bonus'] is None and opp['vp'] is None
    assert opp['kill']==opp['grade']+opp['kill_bonus'] and opp['kill_bonus']==1
    assert pb['players'][1]['primary_op']=='kill' and pb['players'][0]['primary_op'] is None
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='finish'))
    final=a.get('/api/matches/'+mid).json()['players']
    assert final[0]['vp']==own['vp'] and final[1]['vp']==pb['players'][1]['vp']

def test_hotseat_preview_never_discloses_guest_primary(clients):
    a,_=clients;register(a,'alpha');data,ids=approved_ids(a)
    mid=post(a,'/matches',op(kind='hotseat'))['id']
    a.put('/api/matches/'+mid+'/setup',json=op(version=ver(a,mid),mission_id=ids['mission'],killzone_id=ids['zone'],team1_id=ids['team'],team2_id=ids['team'],operative_count=6,tac_op_id=ids['tac'],primary_op='crit'))
    a.put('/api/matches/'+mid+'/player-setup',json=op(version=ver(a,mid),slot=2,operative_count=6,tac_op_id=ids['tac'],primary_op='kill'))
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='start'))
    post(a,'/matches/'+mid+'/initiative',op(version=ver(a,mid),turning_point=1,slot=2))
    for slot in (1,2):post(a,'/matches/'+mid+'/primary',op(version=ver(a,mid),primary_op='crit',slot=slot))
    for tp in (2,3,4):post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='turn',turning_point=tp))
    guest=a.get('/api/matches/'+mid+'/preview').json()['players'][1]
    assert guest['primary_op'] is None and guest['vp'] is None
