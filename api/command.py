"""v1.14: command points of the Ready step and ploys on the board (Kill Team 2024 core rules).

Ready step: each player gains 1CP; in each turning point after the first, the player who doesn't have initiative
gains 2CP instead — one tap per turning point (match_cp_grants keeps it to once; «Undo last» reverts it). A changed
initiative after that moves the extra CP to the new player. Ploys: spending CP on a strategy or firefight ploy of
the player's team or on Command Re-roll records it in the match protocol (match_ploys); using a ploy other than
Command Re-roll twice in a turning point needs an explicit repeat (the client warns first)."""
from uuid import UUID
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from . import equipment
from . import tracker

COMMAND_REROLL = 'Command Re-roll'


class CpGrant(core.Op):
    version: int = Field(ge=1)
    turning_point: int = Field(ge=1, le=12)


class PloyUse(core.Op):
    version: int = Field(ge=1)
    slot: int | None = Field(default=None, ge=1, le=2)
    kind: str = Field(pattern='^(strategy|firefight)$')
    name: str = Field(min_length=1, max_length=120)
    cost: int = Field(default=1, ge=0, le=3)
    repeat: bool = False


def gains_for(tp, initiative):
    return {1: 1, 2: 1} if tp == 1 else {initiative: 1, 3 - initiative: 2}


def initiative_slot(c, m, tp):
    r = core.one(c, 'SELECT slot FROM turning_point_initiative WHERE match_id=%s AND turning_point=%s', (str(m['id']), tp))
    return r['slot'] if r else (m['initiative'] if tp == 1 else None)


def cp_at(c, player_id, tp):
    """(cp, row exists): the saved value of the turning point, else the last earlier one (CP carry over)."""
    own = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (player_id, tp))
    if own:
        return own['cp'], True
    prev = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point<%s ORDER BY turning_point DESC LIMIT 1',
                    (player_id, tp))
    return (prev['cp'] if prev else 0), False


def set_cp(c, player_id, tp, cp):
    c.execute('''INSERT INTO turning_point_states(player_id,turning_point,cp) VALUES(%s,%s,%s)
        ON CONFLICT(player_id,turning_point) DO UPDATE SET cp=excluded.cp''', (player_id, tp, cp))


def restore_cp(c, player_id, tp, cp, existed):
    """Undo: back to the value before; a row the change created goes away when it holds nothing else."""
    if not existed and core.one(c, "SELECT 1 FROM turning_point_states WHERE player_id=%s AND turning_point=%s AND notes=''", (player_id, tp)):
        c.execute('DELETE FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (player_id, tp))
    else:
        c.execute('UPDATE turning_point_states SET cp=%s WHERE player_id=%s AND turning_point=%s', (cp, player_id, tp))


def initiative_changed(c, m, tp, slot):
    """Called by POST /initiative: the Ready step of tp was granted with the other initiative → move the extra CP.
    Returns the change for the audit (undo reverts it with the initiative), or None."""
    mid = str(m['id'])
    g = core.one(c, 'SELECT gains FROM match_cp_grants WHERE match_id=%s AND turning_point=%s FOR UPDATE', (mid, tp))
    if not g or tp < 2:
        return None
    old = {int(k): v for k, v in (g['gains'] or {}).items()}
    new = gains_for(tp, slot)
    if old == new:
        return None
    change = {}
    for p in core.allrows(c, 'SELECT id,slot FROM match_players WHERE match_id=%s ORDER BY slot', (mid,)):
        before, _ = cp_at(c, p['id'], tp)
        after = max(0, min(99, before + new[p['slot']] - old.get(p['slot'], 0)))
        set_cp(c, p['id'], tp, after)
        change[str(p['id'])] = [before, after]
    c.execute('UPDATE match_cp_grants SET gains=%s WHERE match_id=%s AND turning_point=%s',
              (Jsonb({str(k): v for k, v in new.items()}), mid, tp))
    return {'cp': change, 'gains': [{str(k): v for k, v in old.items()}, {str(k): v for k, v in new.items()}]}


def revert_initiative_cp(c, m, f):
    ch = f.get('cp_change')
    if not ch:
        return
    tp = f['turning_point']
    for pid, (before, after) in ch['cp'].items():
        cur = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (int(pid), tp))
        tracker.conflict(cur and cur['cp'] == after)
        c.execute('UPDATE turning_point_states SET cp=%s WHERE player_id=%s AND turning_point=%s', (before, int(pid), tp))
    c.execute('UPDATE match_cp_grants SET gains=%s WHERE match_id=%s AND turning_point=%s',
              (Jsonb(ch['gains'][0]), str(m['id']), tp))


def revert(c, m, a):
    """«Undo last» for cp_grant and ploy (called from tracker.revert)."""
    b, f = a['before_data'] or {}, a['after_data'] or {}
    mid = str(m['id'])
    if a['action'] == 'cp_grant':
        tp = f['turning_point']
        for pid, after in f['cp'].items():
            cur = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (int(pid), tp))
            tracker.conflict(cur and cur['cp'] == after)
        for pid in f['cp']:
            restore_cp(c, int(pid), tp, b['cp'][pid], int(pid) in (b.get('rows') or []))
        c.execute('DELETE FROM match_cp_grants WHERE match_id=%s AND turning_point=%s', (mid, tp))
    elif a['action'] == 'ploy':
        tp, pid = f['turning_point'], f['player_id']
        tracker.conflict(core.one(c, 'SELECT 1 FROM match_ploys WHERE id=%s AND match_id=%s', (f['ploy_id'], mid)))
        if f.get('cost'):
            cur = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (pid, tp))
            tracker.conflict(cur and cur['cp'] == f['cp'])
            restore_cp(c, pid, tp, b['cp'], b.get('row', True))
        c.execute('DELETE FROM match_ploys WHERE id=%s', (f['ploy_id'],))


def team_ploys(c, team_id):
    team = tracker.team_row(c, team_id)
    data = (team or {}).get('data') or {}
    return {k: [str(x.get('name', '')) for x in data.get(k + '_ploys', []) if x.get('name')] for k in ('strategy', 'firefight')}


@core.app.post('/api/matches/{mid}/cp')
def cp_grant(mid: UUID, p: CpGrant, u=Depends(core.user)):
    """The Ready step of the current turning point: +1CP each; from TP2 the player without initiative +2."""
    with core.pool.connection() as c:
        def run():
            m = core.member(c, mid, u['id'], True)
            core.version(m, p.version)
            if m['status'] != 'active' or p.turning_point != m['current_turn']:
                core.fail(409, 'cp_closed')
            if m['edition'] != '2024':
                core.fail(422, 'cp_edition')
            slot = initiative_slot(c, m, p.turning_point)
            if not slot:
                core.fail(409, 'initiative_required')
            gains = gains_for(p.turning_point, slot)
            equipment.grant(c, m, u, p.turning_point, gains)
            return {'ok': True, 'gains': {str(k): v for k, v in gains.items()}}
        return core.operation(c, u, p, 'cp:' + str(mid), run)


@core.app.post('/api/matches/{mid}/ploys')
def ploy_use(mid: UUID, p: PloyUse, u=Depends(core.user)):
    """Spend CP on a ploy at the current turning point and record it in the protocol."""
    with core.pool.connection() as c:
        def run():
            m = core.member(c, mid, u['id'], True)
            core.version(m, p.version)
            if m['status'] != 'active':
                core.fail(409, 'ploy_closed')
            player = equipment._target(c, m, u, p.slot)
            name = p.name.strip()
            if name == COMMAND_REROLL:
                if p.kind != 'firefight':
                    core.fail(422, 'ploy_unknown')
            elif name not in team_ploys(c, player['team_id'])[p.kind]:
                core.fail(422, 'ploy_unknown')
            tp = m['current_turn']
            if name != COMMAND_REROLL and not p.repeat and core.one(
                    c, 'SELECT 1 FROM match_ploys WHERE player_id=%s AND turning_point=%s AND name=%s', (player['id'], tp, name)):
                core.fail(409, 'ploy_repeat')
            cp, existed = cp_at(c, player['id'], tp)
            if cp < p.cost:
                core.fail(422, 'cp_insufficient')
            if p.cost:
                set_cp(c, player['id'], tp, cp - p.cost)
            pid = core.one(c, '''INSERT INTO match_ploys(match_id,player_id,turning_point,kind,name,cost,used_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id''', (str(mid), player['id'], tp, p.kind, name, p.cost, u['id']))['id']
            core.audit(c, mid, u, 'ploy', {'cp': cp, 'row': existed},
                       {'player_id': player['id'], 'slot': player['slot'], 'turning_point': tp, 'ploy_id': pid, 'kind': p.kind,
                        'name': name, 'cost': p.cost, 'cp': cp - p.cost, 'repeat': p.repeat})
            return {'ok': True, 'id': pid, 'cp': cp - p.cost}
        return core.operation(c, u, p, 'ploy:' + str(mid), run)


@core.app.get('/api/stats/ploys')
def ploy_stats(f: core.FilterParams = Depends(), u=Depends(core.user)):
    """The viewer's ploys in the filtered matches: uses, games, CP spent."""
    where, args = core.filters(u, *f.values)
    with core.pool.connection() as c:
        return core.allrows(c, '''SELECT y.name,y.kind,count(*)::int AS uses,count(DISTINCT y.match_id)::int AS games,
        coalesce(sum(y.cost),0)::int AS cp FROM player_results r JOIN match_players p ON p.match_id=r.match_id AND p.user_id=r.user_id
        JOIN match_ploys y ON y.player_id=p.id WHERE ''' + where + ''' GROUP BY y.name,y.kind ORDER BY count(*) DESC,y.name LIMIT 50''', args)
