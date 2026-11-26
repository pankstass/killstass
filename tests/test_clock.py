"""v1.4: server-side game clock shared by both phones."""
import time
from tests.test_integration import register,post,op
from tests.test_quickstart import approved_ids,ver
from tests.test_catalog_ops import approved_match
from tests.test_turns import play_to_tp4

def clk(c,mid,**kw):
    r=c.post('/api/matches/'+mid+'/clock',json=op(**kw));return r

def test_chess_clock_shared_and_independent_of_version(clients):
    a,b=clients;mid,_=approved_match(a,b)
    assert a.get('/api/matches/'+mid).json()['clock']['mode'] is None
    v=ver(a,mid)
    assert clk(a,mid,action='start').json()['detail']=='clock_not_configured'
    r=clk(a,mid,action='configure',mode='chess');assert r.status_code==200,r.text
    r=clk(a,mid,action='start',slot=1).json();assert r['clock']['running'] and r['clock']['active_slot']==1
    time.sleep(0.2)
    r=clk(b,mid,action='switch',slot=1).json();assert r['changed'] and r['clock']['active_slot']==2
    assert clk(a,mid,action='switch',slot=1).json()['changed'] is False  # second phone pressed too late: no-op
    s=b.get('/api/matches/'+mid+'/clock').json()
    assert s['slots'][0]['elapsed_seconds']>=0.2 and s['seq']>=3 and 'server_now' in s
    assert ver(a,mid)==v  # clock never bumps matches.version
    assert clk(a,mid,action='configure',mode='stopwatch').json()['detail']=='clock_running'
    replay=op(action='pause');assert a.post('/api/matches/'+mid+'/clock',json=replay).json()['changed']
    assert a.post('/api/matches/'+mid+'/clock',json=replay).json()['changed']  # idempotent replay returns stored result
    assert not a.get('/api/matches/'+mid+'/clock').json()['running']

def test_finish_pauses_clock_and_freezes_times(clients):
    a,b=clients;mid,data=approved_match(a,b)
    crit=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    clk(a,mid,action='configure',mode='countdown',limit_minutes=30);clk(a,mid,action='start',slot=2)
    play_to_tp4(a,b,mid,crit)
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='finish'))
    s1=a.get('/api/matches/'+mid+'/clock').json();time.sleep(0.15);s2=a.get('/api/matches/'+mid+'/clock').json()
    assert not s1['running'] and s1['slots'][1]['elapsed_seconds']==s2['slots'][1]['elapsed_seconds']>0
    assert s1['slots'][1]['remaining_seconds']<1800
    assert clk(a,mid,action='start').json()['detail']=='clock_closed'

def test_clock_rights_and_validation(clients):
    a,b=clients;register(a,'alpha');register(b,'bravo');data,ids=approved_ids(a)
    mid=post(a,'/matches',op(kind='hotseat'))['id']
    assert clk(a,mid,action='configure',mode='chess').json()['detail']=='clock_closed'  # setup: not yet
    assert clk(b,mid,action='configure',mode='chess').status_code==404
    a.put('/api/matches/'+mid+'/setup',json=op(version=ver(a,mid),mission_id=ids['mission'],killzone_id=ids['zone'],team1_id=ids['team'],team2_id=ids['team'],operative_count=6,tac_op_id=ids['tac'],primary_op='crit'))
    a.put('/api/matches/'+mid+'/player-setup',json=op(version=ver(a,mid),slot=2,operative_count=6,tac_op_id=ids['tac'],primary_op='kill'))
    post(a,'/matches/'+mid+'/actions',op(version=ver(a,mid),action='start'))
    assert clk(a,mid,action='configure',mode='countdown').json()['detail']=='clock_limit_invalid'
    assert clk(a,mid,action='configure',mode='lightning').status_code==422
    assert clk(a,mid,action='configure',mode='stopwatch').status_code==200
    assert clk(a,mid,action='start').json()['clock']['active_slot'] is None
    assert clk(a,mid,action='switch',slot=1).json()['detail']=='clock_mode_invalid'
