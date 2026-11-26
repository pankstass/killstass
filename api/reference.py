"""v1.1 catalogs and Approved Ops. All totals derive from primary database rows."""
import hashlib
import json
from uuid import UUID
from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from .domain import score_after, final_totals, redact_preview

class Primary(core.Op):
    version: int = Field(ge=1)
    primary_op: str = Field(pattern='^(crit|tac|kill)$')
    slot: int | None = Field(default=None,ge=1,le=2)

class Kills(core.Op):
    version: int = Field(ge=1)
    turning_point: int = Field(ge=1,le=4)
    delta: int = Field(ge=-40,le=40)
    slot: int | None = Field(default=None,ge=1,le=2)

class Reveal(core.Op):
    version: int = Field(ge=1)
    slot: int | None = Field(default=None,ge=1,le=2)

class Initiative(core.Op):
    version: int = Field(ge=1)
    turning_point: int = Field(ge=1,le=12)
    slot: int = Field(ge=1,le=2)

class PlayerSetup(core.Op):
    """Per-player (partly secret) setup; used for the guest slot of a hot-seat match."""
    version: int = Field(ge=1)
    slot: int = Field(ge=1,le=2)
    roster: str = Field(default='',max_length=4000)
    roster_id: UUID | None = None
    operative_count: int | None = Field(default=None,ge=1,le=40)
    operative_manual: bool = False  # v1.13: see Setup
    primary_op: str | None = Field(default=None,pattern='^(crit|tac|kill)$')
    tac_op_id: int | None = None
    aspect_counts: dict[str,int] = Field(default_factory=dict,max_length=3)


def official(c,cid,kind,edition):
    item=core.catalog(c,cid,kind,edition)
    if item['verification']!='verified': core.fail(422,'catalog_unverified')
    return item


def archetypes(team,counts,operative_count):
    conditional=team['config'].get('conditional_archetypes')
    if not conditional:return team['config']['archetypes']
    if not counts:return ['Seek & Destroy']
    if set(counts)!=set(conditional) or any(not isinstance(n,int) or n<0 or n>14 for n in counts.values()) or sum(counts.values())!=operative_count:
        core.fail(422,'aspect_counts_invalid')
    highest=max(counts.values())
    return ['Seek & Destroy']+[conditional[k] for k,n in counts.items() if n==highest and n>0]


def prepare_setup(c,m,p,u):
    mission=core.one(c,'SELECT * FROM catalogs WHERE id=%s',(p.mission_id,))
    if mission['config'].get('pack')!='approved2025':
        if m['scoring_mode']=='approved2025': core.fail(422,'pack_required')
        return
    if p.edition!='2024' or p.turns!=4: core.fail(422,'approved_requires_four_turns')
    for cid,kind in ((p.mission_id,'mission'),(p.killzone_id,'killzone'),(p.team1_id,'team'),(p.team2_id,'team')):
        official(c,cid,kind,p.edition)
    team_id=p.team1_id if core.one(c,'SELECT slot FROM match_players WHERE match_id=%s AND user_id=%s',(str(m['id']),u['id']))['slot']==1 else p.team2_id
    check_tac(c,p.tac_op_id,team_id,p.aspect_counts,p.operative_count,p.edition)
    c.execute("UPDATE matches SET scoring_mode='approved2025' WHERE id=%s",(str(m['id']),))
    c.execute('UPDATE match_players SET primary_op=%s,primary_committed=false,tac_op_id=%s,tac_revealed=false,aspect_counts=%s WHERE match_id=%s AND user_id=%s',(p.primary_op,p.tac_op_id,Jsonb(p.aspect_counts),str(m['id']),u['id']))


def check_tac(c,tac_op_id,team_id,counts,operative_count,edition):
    if not tac_op_id: return
    tac=official(c,tac_op_id,'tac_op',edition)
    team=official(c,team_id,'team',edition)
    if tac['config'].get('archetype') not in archetypes(team,counts,operative_count): core.fail(422,'tac_archetype_invalid')


def freeze_rules(c,m):
    if m['scoring_mode']!='approved2025': return
    pack=core.one(c,"SELECT * FROM catalogs WHERE code='2024-wahapedia-pack-approved2025' AND active AND verification='verified'")
    if not pack: core.fail(422,'rules_pack_missing')
    mission=official(c,m['mission_id'],'mission',m['edition'])
    official(c,m['killzone_id'],'killzone',m['edition'])
    tacs={}
    for p in core.allrows(c,'SELECT * FROM match_players WHERE match_id=%s',(str(m['id']),)):
        team=official(c,p['team_id'],'team',m['edition'])
        if p['operative_count'] is None or str(p['operative_count']) not in pack['config']['thresholds'] or not p['tac_op_id']:
            core.fail(422,'player_setup_incomplete')
        tac=official(c,p['tac_op_id'],'tac_op',m['edition'])
        if tac['config']['archetype'] not in archetypes(team,p['aspect_counts'],p['operative_count']): core.fail(422,'tac_archetype_invalid')
        tacs[str(p['id'])]={'id':tac['id'],'config':tac['config'],'content_hash':tac['content_hash']}
    sources=core.allrows(c,"SELECT id,config FROM catalogs WHERE active AND verification='verified' AND edition='2024' AND kind='source' AND config->>'pack'='approved2025'")
    source_map={str(s['id']):s['config']['component'] for s in sources}
    if sorted(source_map.values())!=['crit','tac']: core.fail(422,'sources_incomplete')
    snap={'pack':pack['code'],'content_hash':pack['content_hash'],'version':pack['rules_version'],'thresholds':pack['config']['thresholds'],
          'sources':source_map,'mission':mission['config'],'mission_hash':mission['content_hash'],'tacs':tacs}
    c.execute('UPDATE matches SET rules_snapshot=%s WHERE id=%s',(Jsonb(snap),str(m['id'])))


def require_primary(c,m):
    if m['scoring_mode']=='approved2025' and core.one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND NOT primary_committed',(str(m['id']),)):
        core.fail(422,'primary_not_committed')


def validate_score(c,m,player,tp,source_id,delta,old):
    if m['scoring_mode']=='legacy':
        # Retired demo sources remain usable for existing legacy matches only.
        source=core.one(c,"SELECT * FROM catalogs WHERE id=%s AND kind='source' AND edition=%s",(source_id,m['edition']))
        if not source or not (source['verification']=='legacy' or source['active']): core.fail(422,'catalog_invalid')
        return score_after(old,delta,min(999,int(source['config'].get('max_per_turn',999))))
    cfg=m['rules_snapshot'];component=cfg['sources'].get(str(source_id))
    if component not in ('crit','tac'): core.fail(422,'source_invalid_for_pack')
    rule=cfg['mission'] if component=='crit' else cfg['tacs'][str(player)]['config']
    cap=rule['per_turn_caps'][tp-1]
    value=score_after(old,delta,cap)
    total=core.one(c,'SELECT coalesce(sum(vp),0) AS n FROM turning_point_scores WHERE player_id=%s AND source_id=%s',(player,source_id))['n']
    if total-old+value>6: raise ValueError('component_cap_exceeded')
    return value


def enrich_snapshot(c,m,uid):
    totals={p['id']:p for p in core.allrows(c,'SELECT * FROM player_totals WHERE match_id=%s',(str(m['id']),))}
    ended=m['status'] in ('awaiting_confirmation','confirmed','disputed','unconfirmed')
    for p in m['players']:
        p.update({k:v for k,v in totals[p['id']].items() if k not in ('id','match_id')})
        # Reveals only that a secret choice exists, never which one (hot-seat "pass the device" UI).
        p['secret_set']=p['tac_op_id'] is not None
        if p['user_id'] is not None and p['user_id']!=uid: p['roster_id']=None  # rosters are private to their owner
        if p['user_id']!=uid and not ended:
            p['primary_op']=None
            if not p['tac_revealed']:p['tac_op_id']=None
    m['kills']=core.allrows(c,'SELECT k.* FROM operative_kills k JOIN match_players p ON p.id=k.player_id WHERE p.match_id=%s',(str(m['id']),))
    # Per-player rule snapshots contain secret selected Tac Op IDs. Never serialize them to the opponent.
    if m['scoring_mode']=='approved2025':
        m['rules_snapshot']={k:v for k,v in m['rules_snapshot'].items() if k!='tacs'}
    return m


@core.app.get('/api/reference/game-sequence')
def game_sequence(request:Request,edition:str=Query('2024',pattern='^(2021|2024)$'),u=Depends(core.user)):
    with core.pool.connection() as c:
        rows=core.allrows(c,"SELECT * FROM game_sequence WHERE edition=%s AND active AND verification='verified' ORDER BY phase_order,step_order",(edition,))
    if not rows:core.fail(404,'reference_not_verified')
    data={'edition':edition,'steps':rows,'retrieved_at':max(r['retrieved_at'] for r in rows),'rules_version':rows[0]['rules_version']}
    from fastapi.encoders import jsonable_encoder
    data=jsonable_encoder(data)
    tag='"'+hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()+'"'
    headers={'ETag':tag,'Cache-Control':'private, max-age=0, must-revalidate','Vary':'Cookie'}
    if request.headers.get('if-none-match')==tag:return Response(status_code=304,headers=headers)
    return JSONResponse(data,headers=headers)

@core.app.get('/api/reference/rules')
def rules(q:str=Query('',max_length=120),edition:str=Query('2024',pattern='^(2021|2024)$'),u=Depends(core.user)):
    with core.pool.connection() as c:
        return core.allrows(c,"SELECT * FROM catalogs WHERE kind='rule' AND edition=%s AND active AND verification='verified' AND (label ILIKE %s OR config->>'summary' ILIKE %s) ORDER BY label LIMIT 50",(edition,'%'+q+'%','%'+q+'%'))

@core.app.get('/api/stats/tac-ops')
def tac_stats(f:core.FilterParams=Depends(),u=Depends(core.user)):
    where,args=core.filters(u,*f.values)
    with core.pool.connection() as c:
        return core.allrows(c,'''SELECT p.tac_op_id,c.label,count(DISTINCT r.match_id) AS games,coalesce(sum(s.vp),0)::int AS vp,
        round(coalesce(sum(s.vp),0)::numeric/count(DISTINCT r.match_id),2) AS avg_vp
        FROM player_results r JOIN match_players p ON p.match_id=r.match_id AND p.user_id=r.user_id
        JOIN catalogs c ON c.id=p.tac_op_id LEFT JOIN turning_point_scores s ON s.player_id=p.id AND s.tac_op_id=p.tac_op_id
        WHERE '''+where+''' GROUP BY p.tac_op_id,c.label ORDER BY coalesce(sum(s.vp),0) DESC''',args)

@core.app.post('/api/matches/{mid}/primary')
def primary(mid:UUID,p:Primary,u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True);core.version(m,p.version)
            own=core.actor_player(c,m,u,p.slot)
            if m['scoring_mode']!='approved2025' or m['status']!='active' or m['current_turn']!=1 or own['primary_committed']:core.fail(409,'primary_closed')
            c.execute('UPDATE match_players SET primary_op=%s,primary_committed=true WHERE id=%s',(p.primary_op,own['id']))
            core.audit(c,mid,u,'primary_commit',{}, {'committed':True,'slot':own['slot']})
            return {'ok':True}
        return core.operation(c,u,p,'primary:'+str(mid),run)

@core.app.post('/api/matches/{mid}/reveal-tac')
def reveal_tac(mid:UUID,p:Reveal,u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True);core.version(m,p.version)
            if m['status']!='active' or m['scoring_mode']!='approved2025':core.fail(409,'scoring_closed')
            own=core.actor_player(c,m,u,p.slot)
            c.execute('UPDATE match_players SET tac_revealed=true WHERE id=%s',(own['id'],))
            core.audit(c,mid,u,'tac_reveal',{}, {'revealed':True,'slot':own['slot']})
            return {'ok':True}
        return core.operation(c,u,p,'tac-reveal:'+str(mid),run)

@core.app.post('/api/matches/{mid}/kills')
def kills(mid:UUID,p:Kills,u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True);core.version(m,p.version)
            if m['status']!='active' or m['scoring_mode']!='approved2025':core.fail(409,'scoring_closed')
            own=core.actor_player(c,m,u,p.slot)
            op=core.one(c,'SELECT id,operative_count FROM match_players WHERE match_id=%s AND slot<>%s',(str(mid),own['slot']))
            # v1.9: once the opponent's operatives are tracked, kills follow the tracker (api/tracker.py).
            if core.one(c,'SELECT 1 FROM match_operatives WHERE player_id=%s',(op['id'],)):core.fail(409,'kills_tracked')
            # Net incapacitated, not a lifetime kill counter: resurrection may require a negative correction.
            vals={k['turning_point']:k['delta'] for k in core.allrows(c,'SELECT * FROM operative_kills WHERE player_id=%s',(own['id'],))}
            old=vals.get(p.turning_point,0);vals[p.turning_point]=old+p.delta
            running=0
            for tp in range(1,5):
                running+=vals.get(tp,0)
                if not 0<=running<=op['operative_count']:core.fail(422,'kills_out_of_range')
            c.execute('INSERT INTO operative_kills VALUES(%s,%s,%s) ON CONFLICT(player_id,turning_point) DO UPDATE SET delta=excluded.delta',(own['id'],p.turning_point,old+p.delta))
            core.audit(c,mid,u,'kills',{'delta':old},{'delta':old+p.delta,'turning_point':p.turning_point,'player_id':own['id']})
            return {'ok':True}
        return core.operation(c,u,p,'kills:'+str(mid),run)

@core.app.put('/api/matches/{mid}/player-setup')
def player_setup(mid:UUID,p:PlayerSetup,u=Depends(core.user)):
    """Save one player's roster/count and secret Approved Ops choices without touching shared setup."""
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True);core.version(m,p.version)
            if m['status']!='setup': core.fail(409,'setup_closed')
            row=core.actor_player(c,m,u,p.slot)
            core.rosters.attach(c,u,row,p.roster_id,row['team_id'])
            # v1.13: roster, else the team's composition, else the typed number (api/teams.py).
            p.operative_count,source=core.teams.operative_count(c,p.roster_id,row['team_id'],p.operative_manual,p.operative_count)
            c.execute('UPDATE match_players SET roster=%s,operative_count=%s,operative_source=%s WHERE id=%s',(p.roster,p.operative_count,source,row['id']))
            if m['scoring_mode']=='approved2025':
                if not row['team_id']: core.fail(422,'setup_incomplete')
                check_tac(c,p.tac_op_id,row['team_id'],p.aspect_counts,p.operative_count,m['edition'])
                c.execute('UPDATE match_players SET primary_op=%s,primary_committed=false,tac_op_id=%s,tac_revealed=false,aspect_counts=%s WHERE id=%s',
                          (p.primary_op,p.tac_op_id,Jsonb(p.aspect_counts),row['id']))
            # Secret choices stay out of the immutable audit; record only that they changed.
            core.audit(c,mid,u,'player_setup',{}, {'slot':row['slot'],'secret_changed':m['scoring_mode']=='approved2025'})
            return {'ok':True}
        return core.operation(c,u,p,'player-setup:'+str(mid),run)

@core.app.post('/api/matches/{mid}/initiative')
def initiative(mid:UUID,p:Initiative,u=Depends(core.user)):
    """Record who won the initiative roll-off; any participant may set or correct it (audited)."""
    with core.pool.connection() as c:
        def run():
            m=core.member(c,mid,u['id'],True);core.version(m,p.version)
            if m['status']!='active' or p.turning_point>m['current_turn'] or p.turning_point>m['turns']: core.fail(409,'initiative_closed')
            old=core.one(c,'SELECT slot FROM turning_point_initiative WHERE match_id=%s AND turning_point=%s',(str(mid),p.turning_point))
            c.execute('''INSERT INTO turning_point_initiative(match_id,turning_point,slot,decided_by) VALUES(%s,%s,%s,%s)
            ON CONFLICT(match_id,turning_point) DO UPDATE SET slot=excluded.slot,decided_by=excluded.decided_by,created_at=now()''',(str(mid),p.turning_point,p.slot,u['id']))
            after={'slot':p.slot,'turning_point':p.turning_point}
            from . import command
            change=command.initiative_changed(c,m,p.turning_point,p.slot)  # v1.14: CP already granted for this TP
            if change: after['cp_change']=change
            core.audit(c,mid,u,'initiative',{'slot':old['slot'] if old else None},after)
            return {'ok':True}
        return core.operation(c,u,p,'initiative:'+str(mid),run)

@core.app.get('/api/matches/{mid}/preview')
def preview(mid:UUID,u=Depends(core.user)):
    """Count total points before finishing, last turning point only.

    Public components (Crit/Tac/Kill grade and the +1 kill bonus) for both players; the primary
    choice and its bonus only for the viewer's own slot. A hot-seat guest slot is never the viewer.
    """
    with core.pool.connection() as c:
        m=core.member(c,mid,u['id'])
        if m['status']!='active' or m['current_turn']!=m['turns']: core.fail(409,'preview_closed')
        rows=core.allrows(c,'''SELECT p.slot,p.user_id,p.display_name,p.primary_op,p.primary_committed,t.crit,t.tac,t.grade,t.raw_vp,t.incapacitated
        FROM match_players p JOIN player_totals t ON t.id=p.id WHERE p.match_id=%s ORDER BY p.slot''',(str(mid),))
        totals=final_totals(rows,m['scoring_mode'])
        players=[redact_preview({**r,**t},r['user_id']==u['id']) for r,t in zip(rows,totals)]
        return {'scoring_mode':m['scoring_mode'],'players':players,
                'ready':m['scoring_mode']!='approved2025' or all(r['primary_committed'] for r in rows)}
