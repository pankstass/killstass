"""v1.9: LAN tournaments — league (round robin) or Swiss pairing, standings and per-pairing matches.

The organizer (owner) creates a tournament with accepted friends and/or guest names. Results come from
the pairing's match (created by a participant from the pairing) or are entered by hand (organizer or
the two participants); a hand-entered result wins. Standings: 3/1/0 points, then VP scored, VP
difference, strength of schedule (opponents' points), seed. A bye counts as a win with 0 VP."""
import secrets
from uuid import UUID, uuid4
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core

FINAL = ('confirmed',)
POINTS = {'win': 3, 'draw': 1, 'loss': 0}
MAX_PLAYERS = 32


class TPlayer(core.Model):
    name: str = Field(default='', max_length=64)
    public_id: str | None = Field(default=None, min_length=8, max_length=8)


class TournamentCreate(core.Op):
    name: str = Field(min_length=1, max_length=80)
    format: str = Field(pattern='^(swiss|league)$')
    rounds: int | None = Field(default=None, ge=1, le=30)
    players: list[TPlayer] = Field(min_length=2, max_length=MAX_PLAYERS)


class TournamentAction(core.Op):
    version: int = Field(ge=1)
    action: str = Field(pattern='^(start|next_round|finish)$')


class TResult(core.Op):
    vp1: int | None = Field(default=None, ge=0, le=999)
    vp2: int | None = Field(default=None, ge=0, le=999)


class TDrop(core.Op):
    dropped: bool


class TMatch(core.Op):
    pass


def touch(c, tid):
    c.execute('UPDATE tournaments SET version=version+1,updated_at=now() WHERE id=%s', (str(tid),))


def load(c, tid, uid, lock=False):
    t = core.one(c, 'SELECT * FROM tournaments WHERE id=%s' + (' FOR UPDATE' if lock else ''), (str(tid),))
    if not t or (t['owner_id'] != uid and not core.one(c, 'SELECT 1 FROM tournament_players WHERE tournament_id=%s AND user_id=%s', (str(tid), uid))):
        core.fail(404, 'tournament_not_found')
    return t


def owner(t, uid):
    if t['owner_id'] != uid:
        core.fail(403, 'tournament_owner_only')


def match_vp(c, pairing, players):
    """(vp1, vp2) of the pairing's finished match, mapped to the pairing's players; None while open."""
    m = core.one(c, 'SELECT status,kind,created_by FROM matches WHERE id=%s', (str(pairing['match_id']),))
    if not m or not (m['status'] in FINAL or (m['kind'] == 'hotseat' and m['status'] == 'unconfirmed')):
        return None
    rows = core.allrows(c, 'SELECT p.user_id,t.vp FROM match_players p JOIN player_totals t ON t.id=p.id WHERE p.match_id=%s', (str(pairing['match_id']),))
    p1, p2 = players[pairing['player1_id']], players.get(pairing['player2_id'])
    vp = {}
    for r in rows:
        if r['user_id'] is not None and r['user_id'] == p1['user_id']:
            vp[1] = r['vp']
        elif r['user_id'] is not None and p2 and r['user_id'] == p2['user_id']:
            vp[2] = r['vp']
    for r in rows:  # the guest side of a hot-seat match
        if r['user_id'] is None:
            vp.setdefault(1 if p1['user_id'] is None else 2, r['vp'])
    return (vp[1], vp[2]) if 1 in vp and 2 in vp else None


def standings(players, pairings):
    table = {pid: {'player_id': pid, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'byes': 0, 'points': 0,
                   'vp_for': 0, 'vp_against': 0, 'opponents': []} for pid in players}
    for x in pairings:
        a, b = table.get(x['player1_id']), table.get(x['player2_id'])
        if b is None:
            a['byes'] += 1; a['wins'] += 1; a['points'] += POINTS['win']
            continue
        if x['vp1'] is None:
            continue
        for me, op, f, g in ((a, b, x['vp1'], x['vp2']), (b, a, x['vp2'], x['vp1'])):
            me['played'] += 1; me['vp_for'] += f; me['vp_against'] += g; me['opponents'].append(op['player_id'])
            r = 'win' if f > g else 'draw' if f == g else 'loss'
            me[{'win': 'wins', 'draw': 'draws', 'loss': 'losses'}[r]] += 1; me['points'] += POINTS[r]
    for row in table.values():
        row['diff'] = row['vp_for'] - row['vp_against']
        row['sos'] = sum(table[o]['points'] for o in row['opponents'])
    order = sorted(table.values(), key=lambda r: (-r['points'], -r['vp_for'], -r['diff'], -r['sos'], players[r['player_id']]['seed']))
    for i, row in enumerate(order, 1):
        row['rank'] = i
        row.pop('opponents')
    return order


def swiss(order, played, byes):
    """Pair neighbours in the standings without rematches (backtracking); the bye goes to the
    lowest-ranked player without one."""
    rest, bye = list(order), None
    if len(rest) % 2:
        bye = next((p for p in reversed(rest) if p not in byes), rest[-1])
        rest.remove(bye)
    budget = [20000]

    def solve(rem):
        if not rem:
            return []
        budget[0] -= 1
        if budget[0] < 0:
            return None
        a = rem[0]
        for i in range(1, len(rem)):
            if frozenset((a, rem[i])) in played:
                continue
            tail = solve(rem[1:i] + rem[i + 1:])
            if tail is not None:
                return [(a, rem[i])] + tail
        return None
    pairs = solve(rest)
    if pairs is None:  # rematches unavoidable
        pairs = [(rest[i], rest[i + 1]) for i in range(0, len(rest), 2)]
    return pairs + ([(bye, None)] if bye else [])


def round_robin(ids, rnd):
    """Circle method: seat 1 fixed, the rest rotates one step per round; None = bye."""
    arr = list(ids) + ([None] if len(ids) % 2 else [])
    n, k = len(arr), (rnd - 1) % (len(arr) - 1)
    rest = arr[1:]
    if k:
        rest = rest[-k:] + rest[:-k]
    line = [arr[0]] + rest
    pairs = []
    for i in range(n // 2):
        a, b = line[i], line[n - 1 - i]
        if a is None:
            a, b = b, None
        if a is not None:
            pairs.append((a, b))
    return pairs


def state(c, t, uid):
    players = {p['id']: p for p in core.allrows(c, '''SELECT tp.id,tp.user_id,tp.name,tp.seed,tp.dropped,u.public_id
    FROM tournament_players tp LEFT JOIN users u ON u.id=tp.user_id WHERE tp.tournament_id=%s ORDER BY tp.seed''', (str(t['id']),))}
    pairings = core.allrows(c, 'SELECT * FROM tournament_pairings WHERE tournament_id=%s ORDER BY round,table_no', (str(t['id']),))
    for x in pairings:
        x['source'] = 'manual' if x['vp1'] is not None else None
        if x['vp1'] is None and x['match_id']:
            vp = match_vp(c, x, players)
            if vp:
                x['vp1'], x['vp2'], x['source'] = vp[0], vp[1], 'match'
        if x['match_id']:
            x['match_status'] = (core.one(c, 'SELECT status FROM matches WHERE id=%s', (str(x['match_id']),)) or {}).get('status')
            # Only the two participants can open the match itself.
            mine = core.one(c, 'SELECT 1 FROM match_players WHERE match_id=%s AND user_id=%s', (str(x['match_id']), uid))
            if not mine:
                x['match_id'] = None
    mine = next((p['id'] for p in players.values() if p['user_id'] == uid), None)
    out = {k: t[k] for k in ('id', 'name', 'format', 'rounds', 'status', 'current_round', 'version', 'created_at')}
    out.update(is_owner=t['owner_id'] == uid, my_player_id=mine,
               owner_name=(core.one(c, 'SELECT display_name FROM users WHERE id=%s', (t['owner_id'],)) or {}).get('display_name'),
               players=[{k: p[k] for k in ('id', 'name', 'seed', 'dropped', 'public_id')} | {'is_user': p['user_id'] is not None} for p in players.values()],
               pairings=[{k: x.get(k) for k in ('id', 'round', 'table_no', 'player1_id', 'player2_id', 'vp1', 'vp2', 'source', 'match_id', 'match_status')} for x in pairings],
               standings=standings(players, pairings))
    return out


def pair_round(c, t, rnd):
    players = {p['id']: p for p in core.allrows(c, 'SELECT * FROM tournament_players WHERE tournament_id=%s ORDER BY seed', (str(t['id']),))}
    if t['format'] == 'league':
        pairs = []
        for a, b in round_robin(list(players), rnd):  # a dropped player's opponent gets a bye
            alive = [x for x in (a, b) if x is not None and not players[x]['dropped']]
            if alive:
                pairs.append((alive[0], alive[1] if len(alive) == 2 else None))
    else:
        active = [p for p in players if not players[p]['dropped']]
        if len(active) < 2:
            core.fail(409, 'tournament_too_small')
        old = core.allrows(c, 'SELECT player1_id,player2_id,vp1,vp2,match_id FROM tournament_pairings WHERE tournament_id=%s', (str(t['id']),))
        played = {frozenset((x['player1_id'], x['player2_id'])) for x in old if x['player2_id']}
        byes = {x['player1_id'] for x in old if not x['player2_id']}
        if rnd == 1:
            order = list(active)
            secrets.SystemRandom().shuffle(order)
        else:
            current = state(c, t, t['owner_id'])['standings']
            order = [r['player_id'] for r in current if r['player_id'] in active]
        pairs = swiss(order, played, byes)
    for i, (a, b) in enumerate(pairs, 1):
        c.execute('INSERT INTO tournament_pairings(tournament_id,round,table_no,player1_id,player2_id) VALUES(%s,%s,%s,%s,%s)', (str(t['id']), rnd, i, a, b))


def round_complete(c, t):
    s = state(c, t, t['owner_id'])
    return all(x['vp1'] is not None or x['player2_id'] is None for x in s['pairings'] if x['round'] == t['current_round'])


@core.app.get('/api/tournaments')
def list_tournaments(u=Depends(core.user)):
    with core.pool.connection() as c:
        return core.allrows(c, '''SELECT t.id,t.name,t.format,t.rounds,t.status,t.current_round,t.created_at,t.owner_id=%s AS is_owner,
        (SELECT count(*)::int FROM tournament_players p WHERE p.tournament_id=t.id) AS players
        FROM tournaments t WHERE t.owner_id=%s OR EXISTS(SELECT 1 FROM tournament_players p WHERE p.tournament_id=t.id AND p.user_id=%s)
        ORDER BY t.created_at DESC LIMIT 100''', (u['id'], u['id'], u['id']))


@core.app.post('/api/tournaments', status_code=201)
def create_tournament(p: TournamentCreate, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            if core.one(c, "SELECT count(*) AS n FROM tournaments WHERE owner_id=%s AND status<>'finished'", (u['id'],))['n'] >= 10:
                core.fail(429, 'too_many_tournaments')
            rows, seen = [], set()
            for pl in p.players:
                uid, name = None, pl.name.strip()
                if pl.public_id:
                    f = core.one(c, '''SELECT u.id,u.display_name FROM users u WHERE u.public_id=%s AND (u.id=%s OR EXISTS(SELECT 1 FROM friendships f
                    WHERE f.status='accepted' AND ((f.requester_id=%s AND f.recipient_id=u.id) OR (f.recipient_id=%s AND f.requester_id=u.id))))''',
                                 (pl.public_id.upper(), u['id'], u['id'], u['id']))
                    if not f:
                        core.fail(422, 'tournament_friend_required')
                    if f['id'] in seen:
                        core.fail(422, 'tournament_duplicate_player')
                    seen.add(f['id'])
                    uid, name = f['id'], name or f['display_name']
                if not name:
                    core.fail(422, 'tournament_player_name')
                rows.append((uid, name[:64]))
            n = len(rows)
            rounds = (n - 1 if n % 2 == 0 else n) if p.format == 'league' else (p.rounds or max(1, (n - 1).bit_length()))
            if rounds > 30:
                core.fail(422, 'tournament_rounds')
            tid = str(uuid4())
            c.execute('INSERT INTO tournaments(id,owner_id,name,format,rounds) VALUES(%s,%s,%s,%s,%s)', (tid, u['id'], p.name.strip(), p.format, rounds))
            for seed, (uid, name) in enumerate(rows, 1):
                c.execute('INSERT INTO tournament_players(tournament_id,user_id,name,seed) VALUES(%s,%s,%s,%s)', (tid, uid, name, seed))
                if uid and uid != u['id']:
                    core.notify(c, uid, 'tournament_added', tid)
            return {'id': tid}
        return core.operation(c, u, p, 'tournament:create', run)


@core.app.get('/api/tournaments/{tid}')
def get_tournament(tid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        return state(c, load(c, tid, u['id']), u['id'])


@core.app.delete('/api/tournaments/{tid}')
def delete_tournament(tid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        with c.transaction():
            owner(load(c, tid, u['id'], True), u['id'])
            c.execute('DELETE FROM tournaments WHERE id=%s', (str(tid),))
    return {'ok': True}


@core.app.post('/api/tournaments/{tid}/actions')
def tournament_action(tid: UUID, p: TournamentAction, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            t = load(c, tid, u['id'], True)
            owner(t, u['id'])
            if t['version'] != p.version:
                core.fail(409, 'version_conflict')
            if p.action == 'start':
                if t['status'] != 'draft':
                    core.fail(409, 'tournament_state')
                c.execute("UPDATE tournaments SET status='active',current_round=1 WHERE id=%s", (str(tid),))
                pair_round(c, {**t, 'status': 'active', 'current_round': 1}, 1)
            elif p.action == 'next_round':
                if t['status'] != 'active' or t['current_round'] >= t['rounds']:
                    core.fail(409, 'tournament_state')
                if not round_complete(c, t):
                    core.fail(409, 'tournament_round_open')
                c.execute('UPDATE tournaments SET current_round=current_round+1 WHERE id=%s', (str(tid),))
                pair_round(c, t, t['current_round'] + 1)
            else:
                if t['status'] != 'active':
                    core.fail(409, 'tournament_state')
                if not round_complete(c, t):
                    core.fail(409, 'tournament_round_open')
                c.execute("UPDATE tournaments SET status='finished' WHERE id=%s", (str(tid),))
                from . import seasons  # v1.10: «tournament wins» achievements
                for r in core.allrows(c, 'SELECT user_id FROM tournament_players WHERE tournament_id=%s AND user_id IS NOT NULL', (str(tid),)):
                    seasons.award(c, r['user_id'])
            touch(c, tid)
            return {'ok': True}
        return core.operation(c, u, p, 'tournament:' + str(tid), run)


def pairing(c, t, pid):
    x = core.one(c, 'SELECT * FROM tournament_pairings WHERE id=%s AND tournament_id=%s FOR UPDATE', (pid, str(t['id'])))
    if not x:
        core.fail(404, 'pairing_not_found')
    return x


@core.app.post('/api/tournaments/{tid}/pairings/{pid}/result')
def pairing_result(tid: UUID, pid: int, p: TResult, u=Depends(core.user)):
    """Hand-entered result (both VP) or clearing it (both null): organizer, or one of the two players."""
    if (p.vp1 is None) != (p.vp2 is None):
        core.fail(422, 'result_incomplete')
    with core.pool.connection() as c:
        def run():
            t = load(c, tid, u['id'], True)
            if t['status'] != 'active':
                core.fail(409, 'tournament_state')
            x = pairing(c, t, pid)
            if not x['player2_id']:
                core.fail(409, 'pairing_bye')
            if t['owner_id'] != u['id']:
                ids = {r['user_id'] for r in core.allrows(c, 'SELECT user_id FROM tournament_players WHERE id = ANY(%s)', ([x['player1_id'], x['player2_id']],))}
                if u['id'] not in ids or x['round'] != t['current_round']:
                    core.fail(403, 'tournament_owner_only')
            c.execute('UPDATE tournament_pairings SET vp1=%s,vp2=%s,reported_by=%s WHERE id=%s', (p.vp1, p.vp2, u['id'], pid))
            touch(c, tid)
            return {'ok': True}
        return core.operation(c, u, p, 'tournament-result:' + str(pid), run)


@core.app.post('/api/tournaments/{tid}/players/{plid}/drop')
def drop_player(tid: UUID, plid: int, p: TDrop, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            t = load(c, tid, u['id'], True)
            owner(t, u['id'])
            if t['status'] == 'finished':
                core.fail(409, 'tournament_state')
            if not core.one(c, 'UPDATE tournament_players SET dropped=%s WHERE id=%s AND tournament_id=%s RETURNING id', (p.dropped, plid, str(tid))):
                core.fail(404, 'player_not_found')
            touch(c, tid)
            return {'ok': True}
        return core.operation(c, u, p, 'tournament-drop:' + str(plid), run)


@core.app.post('/api/tournaments/{tid}/pairings/{pid}/match', status_code=201)
def pairing_match(tid: UUID, pid: int, p: TMatch, u=Depends(core.user)):
    """A participant opens the pairing's match: friend match (both users seated) or hot-seat vs the guest."""
    with core.pool.connection() as c:
        def run():
            t = load(c, tid, u['id'], True)
            if t['status'] != 'active':
                core.fail(409, 'tournament_state')
            x = pairing(c, t, pid)
            if x['round'] != t['current_round'] or not x['player2_id'] or x['vp1'] is not None:
                core.fail(409, 'pairing_closed')
            if x['match_id'] and core.one(c, "SELECT 1 FROM matches WHERE id=%s AND status<>'cancelled'", (str(x['match_id']),)):
                core.fail(409, 'pairing_has_match')
            pl = {r['id']: r for r in core.allrows(c, 'SELECT * FROM tournament_players WHERE id = ANY(%s)', ([x['player1_id'], x['player2_id']],))}
            me = next((r for r in pl.values() if r['user_id'] == u['id']), None)
            if not me:
                core.fail(403, 'pairing_not_player')
            other = next(r for r in pl.values() if r['id'] != me['id'])
            mid = str(uuid4())
            kind = 'friend' if other['user_id'] else 'hotseat'
            c.execute("INSERT INTO matches(id,created_by,kind,status,edition,setup) VALUES(%s,%s,%s,'setup','2024',%s)",
                      (mid, u['id'], kind, Jsonb({'edition': '2024', 'mission_id': None, 'mode': 'Турнир', 'tournament_id': str(tid)})))
            c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,1,%s,%s)', (mid, u['id'], u['display_name']))
            if other['user_id']:
                name = core.one(c, 'SELECT display_name FROM users WHERE id=%s', (other['user_id'],))['display_name']
                c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,2,%s,%s)', (mid, other['user_id'], name))
                core.notify(c, other['user_id'], 'tournament_match', mid)
            else:
                gid = str(uuid4())
                c.execute('INSERT INTO guest_opponents(id,owner_id,name) VALUES(%s,%s,%s)', (gid, u['id'], other['name']))
                c.execute('INSERT INTO match_players(match_id,slot,guest_id,display_name) VALUES(%s,2,%s,%s)', (mid, gid, other['name']))
            core.audit(c, mid, u, 'create', {}, {'kind': kind, 'edition': '2024', 'tournament_id': str(tid), 'pairing_id': pid})
            c.execute('UPDATE tournament_pairings SET match_id=%s WHERE id=%s', (mid, pid))
            touch(c, tid)
            return {'id': mid}
        return core.operation(c, u, p, 'tournament-match:' + str(pid), run)
