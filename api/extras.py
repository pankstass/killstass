"""v1.5 utilities: read-only result links (LAN) and local feedback for the server operator."""
import secrets
from uuid import UUID
from fastapi import Depends, Request
from pydantic import Field
from . import main as core
from . import clock

ENDED=('awaiting_confirmation','confirmed','disputed','unconfirmed')

class Feedback(core.Model):
    message: str = Field(min_length=1,max_length=2000)
    page: str = Field(default='',max_length=200)

def summary(c,mid):
    """Public result card: names, teams, mission, totals. No user IDs, public IDs, notes or rosters."""
    m=core.one(c,'SELECT id,kind,status,edition,mission_id,killzone_id,played_at,turns,scoring_mode FROM matches WHERE id=%s',(str(mid),))
    rows={r['id']:r for r in core.allrows(c,'SELECT id,code,label FROM catalogs WHERE id = ANY(%s)',
            ([x for x in (m['mission_id'],m['killzone_id']) if x]+[r['team_id'] for r in core.allrows(c,'SELECT team_id FROM match_players WHERE match_id=%s AND team_id IS NOT NULL',(str(mid),))],))}
    labels={k:r['label'] for k,r in rows.items()}
    codes={k:r['code'] for k,r in rows.items()}  # v1.6: lets the client show English catalog names
    players=core.allrows(c,'''SELECT p.slot,p.display_name,p.team_id,p.primary_op,t.crit,t.tac,t.kill,t.primary_bonus,t.vp
    FROM match_players p JOIN player_totals t ON t.id=p.id WHERE p.match_id=%s ORDER BY p.slot''',(str(mid),))
    turns=core.allrows(c,'''SELECT p.slot,s.turning_point,sum(s.vp)::int AS vp FROM turning_point_scores s JOIN match_players p ON p.id=s.player_id
    WHERE p.match_id=%s GROUP BY 1,2 ORDER BY 2,1''',(str(mid),))
    for p in players:
        tid=p.pop('team_id'); p['team']=labels.get(tid); p['team_code']=codes.get(tid)
        if m['scoring_mode']!='approved2025': p.update(crit=None,tac=None,kill=None,primary_bonus=None,primary_op=None)
    k=clock.load(c,mid)
    return {'status':m['status'],'kind':m['kind'],'edition':m['edition'],'played_at':m['played_at'],'turns':m['turns'],
            'scoring_mode':m['scoring_mode'],'mission':labels.get(m['mission_id']),'killzone':labels.get(m['killzone_id']),
            'mission_code':codes.get(m['mission_id']),'killzone_code':codes.get(m['killzone_id']),
            'players':players,'turn_scores':turns,
            'clock':{'mode':k['mode'],'total_seconds':k['total_seconds'],'slots':k['slots']} if k['mode'] else None}

def ended(c,mid,u):
    m=core.member(c,mid,u['id'],True)
    if m['status'] not in ENDED: core.fail(409,'share_unavailable')
    return m

@core.app.get('/api/matches/{mid}/share')
def share_state(mid:UUID,u=Depends(core.user)):
    with core.pool.connection() as c:
        core.member(c,mid,u['id'])
        row=core.one(c,'SELECT created_at FROM match_shares WHERE match_id=%s',(str(mid),))
        return {'active':bool(row),'created_at':row['created_at'] if row else None}

@core.app.post('/api/matches/{mid}/share',status_code=201)
def share_create(mid:UUID,u=Depends(core.user)):
    """Create or replace the read-only link. The token is returned once and never stored in clear text
    (deliberately outside the idempotency table, which keeps results verbatim)."""
    with core.pool.connection() as c:
        ended(c,mid,u)
        token=secrets.token_urlsafe(18)
        c.execute('''INSERT INTO match_shares(token_hash,match_id,created_by) VALUES(%s,%s,%s)
        ON CONFLICT(match_id) DO UPDATE SET token_hash=excluded.token_hash,created_by=excluded.created_by,created_at=now()''',
                  (core.digest(token),str(mid),u['id']))
        return {'token':token}

@core.app.delete('/api/matches/{mid}/share')
def share_revoke(mid:UUID,u=Depends(core.user)):
    with core.pool.connection() as c:
        core.member(c,mid,u['id'])
        c.execute('DELETE FROM match_shares WHERE match_id=%s',(str(mid),))
        return {'ok':True}

@core.app.get('/api/shared/{token}')
def shared(token:str,request:Request):
    """No login: anyone in the LAN with the link sees the result card of an ended match."""
    core.limit(request,'shared',120)
    if not 16<=len(token)<=64: core.fail(404,'share_not_found')
    with core.pool.connection() as c:
        row=core.one(c,'''SELECT s.match_id FROM match_shares s JOIN matches m ON m.id=s.match_id
        WHERE s.token_hash=%s AND m.status = ANY(%s)''',(core.digest(token),list(ENDED)))
        if not row: core.fail(404,'share_not_found')
        return summary(c,row['match_id'])

@core.app.post('/api/feedback',status_code=201)
def feedback(p:Feedback,request:Request,u=Depends(core.user)):
    core.limit(request,'feedback',10)
    with core.pool.connection() as c:
        c.execute('INSERT INTO feedback(user_id,page,message) VALUES(%s,%s,%s)',(u['id'],p.page,p.message.strip() or '-'))
    return {'ok':True}
