"""v1.4 game clock: stopwatch, chess (toggle) and countdown, derived from server-side events.

Clock commands are idempotent (request_id) but deliberately not tied to matches.version: a chess clock
switch must never make the opponent's next score command fail with version_conflict. Phones learn about
clock changes through the separate SSE event `clock` (sequence = last event id).
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import Depends
from pydantic import Field
from . import main as core
from .domain import clock_state, clock_command

class ClockCommand(core.Op):
    action: str = Field(pattern='^(configure|start|pause|switch)$')
    mode: str | None = Field(default=None,pattern='^(stopwatch|chess|countdown)$')
    limit_minutes: int | None = Field(default=None,ge=1,le=600)
    slot: int | None = Field(default=None,ge=1,le=2)
    # v1.10: moment of the tap for commands queued by an offline phone (start/pause/switch).
    at: datetime | None = None

def load(c,mid):
    row=core.one(c,'SELECT clock_timestamp() AS now')
    events=core.allrows(c,'SELECT id,action,mode,limit_seconds,slot,server_ts FROM match_clock_events WHERE match_id=%s ORDER BY id',(str(mid),))
    return {**clock_state(events,row['now']),'server_now':row['now'].isoformat()}

def seq(c,mid):
    return core.one(c,'SELECT coalesce(max(id),0) AS n FROM match_clock_events WHERE match_id=%s',(str(mid),))['n']

def append(c,mid,u,event,at=None):
    if at is None:
        c.execute('INSERT INTO match_clock_events(match_id,action,mode,limit_seconds,slot,actor_id) VALUES(%s,%s,%s,%s,%s,%s)',
                  (str(mid),event['action'],event['mode'],event['limit_seconds'],event['slot'],u['id']))
    else:
        c.execute('INSERT INTO match_clock_events(match_id,action,mode,limit_seconds,slot,actor_id,server_ts) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                  (str(mid),event['action'],event['mode'],event['limit_seconds'],event['slot'],u['id'],at))

def replay_time(c,mid,at):
    """An offline tap keeps its own moment, clamped between the last clock event (order) and now (max 6 hours back)."""
    if at is None: return None
    row=core.one(c,'SELECT clock_timestamp() AS now,(SELECT max(server_ts) FROM match_clock_events WHERE match_id=%s) AS last',(str(mid),))
    at=at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    low=max(x for x in (row['last'],row['now']-timedelta(hours=6)) if x is not None)
    return min(max(at,low),row['now'])

def auto_pause(c,mid,u):
    """Finishing a match stops a running clock so the final times are frozen."""
    if load(c,mid)['running']:
        append(c,mid,u,{'action':'pause','mode':None,'limit_seconds':None,'slot':None})

@core.app.get('/api/matches/{mid}/clock')
def get_clock(mid:UUID,u=Depends(core.user)):
    with core.pool.connection() as c:
        core.member(c,mid,u['id'])
        return load(c,mid)

@core.app.post('/api/matches/{mid}/clock')
def clock_cmd(mid:UUID,p:ClockCommand,u=Depends(core.user)):
    """Any participant (hot-seat: the device owner) controls the shared clock of an active match."""
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True)
            if m['status']!='active': core.fail(409,'clock_closed')
            try: event=clock_command(load(c,mid),p.action,p.slot,p.mode,p.limit_minutes*60 if p.limit_minutes else None)
            except ValueError as e: core.fail(409,str(e))
            if event: append(c,mid,u,event,replay_time(c,mid,p.at) if p.action!='configure' else None)
            return {'ok':True,'changed':event is not None}
        result=core.operation(c,u,p,'clock:'+str(mid),run)
        return {**result,'clock':load(c,mid)}
