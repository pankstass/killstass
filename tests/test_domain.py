from datetime import datetime,timedelta,timezone
import pytest
from api.domain import challenge_transition,match_transition,outcome,score_after
NOW=datetime(2026,10,26,tzinfo=timezone.utc)

@pytest.mark.parametrize('own,other,result',[(5,2,'win'),(2,2,'draw'),(0,2,'loss')])
def test_outcome(own,other,result): assert outcome(own,other)==result

def test_challenge_lifecycle():
    assert challenge_transition('pending','accepted',False,NOW+timedelta(hours=1),NOW)=='accepted'
    assert challenge_transition('pending','accepted',False,NOW,NOW)=='expired'
    with pytest.raises(ValueError):challenge_transition('pending','accepted',True,NOW+timedelta(hours=1),NOW)
    with pytest.raises(ValueError):challenge_transition('accepted','cancelled',True,NOW+timedelta(hours=1),NOW)

def test_match_lifecycle():
    assert match_transition('setup','start')=='active'
    assert match_transition('active','finish')=='awaiting_confirmation'
    with pytest.raises(ValueError):match_transition('awaiting_confirmation','confirm',True)
    assert match_transition('awaiting_confirmation','dispute',False)=='disputed'
    assert match_transition('disputed','reopen')=='active'
    assert match_transition('awaiting_confirmation','confirm',False)=='confirmed'
    with pytest.raises(ValueError):match_transition('confirmed','finish')

def test_scores():
    assert score_after(2,-1,3)==1
    for old,delta in [(0,-1),(3,1)]:
        with pytest.raises(ValueError):score_after(old,delta,3)


def test_hotseat_and_cancel_transitions():
    import pytest
    from datetime import datetime, timedelta, timezone
    from api.domain import match_transition, slot_allowed, invite_state
    assert match_transition('active','finish',kind='hotseat')=='unconfirmed'
    for action in ('confirm','dispute','reopen'):
        with pytest.raises(ValueError): match_transition('awaiting_confirmation','confirm',kind='hotseat')
    assert match_transition('setup','cancel',is_creator=True)=='cancelled'
    with pytest.raises(ValueError): match_transition('setup','cancel',is_creator=False)
    with pytest.raises(ValueError): match_transition('active','cancel',is_creator=True)
    assert slot_allowed(5,5,'friend',False)
    assert slot_allowed(None,5,'hotseat',True)
    assert not slot_allowed(None,5,'friend',True)
    assert not slot_allowed(7,5,'hotseat',True)
    now=datetime.now(timezone.utc)
    assert invite_state(now+timedelta(hours=1),None,now)=='open'
    with pytest.raises(ValueError): invite_state(now-timedelta(seconds=1),None,now)
    with pytest.raises(ValueError): invite_state(now+timedelta(hours=1),now,now)


def test_final_totals_preview_and_redaction():
    from api.domain import final_totals, redact_preview
    p1={'crit':5,'tac':2,'grade':3,'raw_vp':0,'primary_op':'crit','primary_committed':True}
    p2={'crit':1,'tac':4,'grade':2,'raw_vp':0,'primary_op':'kill','primary_committed':True}
    a,b=final_totals([p1,p2],'approved2025')
    assert a['kill']==4 and a['kill_bonus']==1 and a['primary_bonus']==3 and a['vp']==14
    assert b['kill']==2 and b['primary_bonus']==1 and b['vp']==8
    assert final_totals([{**p1,'primary_committed':False},p2],'approved2025')[0]['primary_bonus']==0
    assert final_totals([{**p1,'raw_vp':9},{**p2,'raw_vp':4}],'legacy')[0]['vp']==9
    hidden=redact_preview({**p2,**b},False)
    assert hidden['primary_op'] is None and hidden['primary_bonus'] is None and hidden['vp'] is None and hidden['base']==7


def test_clock_state_modes_and_commands():
    from datetime import datetime, timedelta, timezone
    from api.domain import clock_state, clock_command
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    at = lambda s: t0 + timedelta(seconds=s)
    ev = lambda i, a, s, **k: {'id': i, 'action': a, 'server_ts': at(s), 'mode': k.get('mode'), 'limit_seconds': k.get('limit'), 'slot': k.get('slot')}
    empty = clock_state([], at(0))
    assert empty['mode'] is None and empty['seq'] == 0
    try: clock_command(empty, 'start'); assert False
    except ValueError as e: assert str(e) == 'clock_not_configured'
    chess = [ev(1, 'configure', 0, mode='chess'), ev(2, 'start', 10, slot=2), ev(3, 'switch', 40, slot=2), ev(4, 'pause', 100)]
    s = clock_state(chess, at(500))
    assert not s['running'] and s['total_seconds'] == 90 and [x['elapsed_seconds'] for x in s['slots']] == [60, 30]
    running = clock_state(chess[:3], at(50))
    assert running['active_slot'] == 1 and running['slots'][0]['elapsed_seconds'] == 10
    assert clock_command(running, 'switch', 2) is None  # repeated press of the side that already ended
    assert clock_command(running, 'switch', 1)['slot'] == 1
    assert clock_command(running, 'start') is None and clock_command(s, 'pause') is None
    for args, code in ((('configure', None, 'chess'), 'clock_running'), (('switch',), 'clock_slot_required')):
        try: clock_command(running, *args); assert False
        except ValueError as e: assert str(e) == code
    cd = clock_state([ev(1, 'configure', 0, mode='countdown', limit=60), ev(2, 'start', 0, slot=1)], at(75))
    assert cd['slots'][0]['remaining_seconds'] == -15 and cd['slots'][1]['remaining_seconds'] == 60
    try: clock_command(empty, 'configure', None, 'countdown', None); assert False
    except ValueError as e: assert str(e) == 'clock_limit_invalid'
    sw = clock_state([ev(1, 'configure', 0, mode='stopwatch'), ev(2, 'start', 5), ev(3, 'pause', 20), ev(4, 'start', 30)], at(40))
    assert sw['total_seconds'] == 25 and sw['active_slot'] is None and sw['running']
    try: clock_command(sw, 'switch', 1); assert False
    except ValueError as e: assert str(e) == 'clock_mode_invalid'
    reset = clock_state(chess + [ev(5, 'configure', 600, mode='stopwatch')], at(700))
    assert reset['total_seconds'] == 0 and not reset['started'] and reset['seq'] == 5
