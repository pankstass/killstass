"""v1.9: statistics additions — results by roster, game clock time, Elo rating among friends.

The rating uses confirmed friend matches between the viewer and the viewer's accepted friends (and
between those friends), oldest first: start 1500, K = 32. It is recomputed on every request.

v1.13: scope=all — the club rating: every confirmed friend match between two registered players plus the
hot-seat matches and quick records of a registered player against a local player (api/localplayers.py;
those are not confirmed by the opponent, so they count as soon as they are finished or saved). Players who
hide their profile take part in the calculation but are not listed (except for themselves)."""
from collections import defaultdict
from fastapi import Depends, Query
from . import main as core
from .domain import clock_state

START, K = 1500, 32


def roster_breakdown(c, where, args):
    return core.allrows(c, f'''SELECT mp.roster_id AS key,max(ro.name) AS label,count(*)::int games,
    count(*) FILTER(WHERE r.result='win')::int wins,count(*) FILTER(WHERE r.result='draw')::int draws,
    count(*) FILTER(WHERE r.result='loss')::int losses,round(avg(r.vp_for-r.vp_against),2) avg_diff
    FROM player_results r JOIN match_players mp ON mp.match_id=r.match_id AND mp.user_id=r.user_id
    JOIN rosters ro ON ro.id=mp.roster_id
    WHERE {where} GROUP BY mp.roster_id ORDER BY games DESC LIMIT 100''', args)


def clock_summary(c, where, args):
    """Average game time and, for chess/countdown clocks, the viewer's and the opponent's share."""
    rows = core.allrows(c, f'''SELECT r.match_id,mp.slot FROM player_results r
    JOIN match_players mp ON mp.match_id=r.match_id AND mp.user_id=r.user_id
    WHERE {where} AND EXISTS(SELECT 1 FROM match_clock_events e WHERE e.match_id=r.match_id)
    ORDER BY r.played_at DESC LIMIT 300''', args)
    if not rows:
        return {'games': 0}
    events = defaultdict(list)
    for e in core.allrows(c, '''SELECT id,match_id,action,mode,limit_seconds,slot,server_ts FROM match_clock_events
    WHERE match_id = ANY(%s) ORDER BY id''', ([str(r['match_id']) for r in rows],)):
        events[e['match_id']].append(e)
    now = core.one(c, 'SELECT clock_timestamp() AS now')['now']
    total, own, opp, split, longest = 0.0, 0.0, 0.0, 0, 0.0
    timed = 0
    for r in rows:
        s = clock_state(events[r['match_id']], now)
        if not s['total_seconds']:
            continue
        timed += 1
        total += s['total_seconds']
        longest = max(longest, s['total_seconds'])
        if s['mode'] in ('chess', 'countdown'):
            by = {x['slot']: x['elapsed_seconds'] for x in s['slots']}
            own += by.get(r['slot'], 0)
            opp += by.get(3 - r['slot'], 0)
            split += 1
    if not timed:
        return {'games': 0}
    return {'games': timed, 'avg_total_seconds': round(total / timed), 'max_total_seconds': round(longest),
            'split_games': split, 'avg_own_seconds': round(own / split) if split else None,
            'avg_opponent_seconds': round(opp / split) if split else None}


def elo(c, uid):
    circle = [uid] + [r['id'] for r in core.allrows(c, '''SELECT CASE WHEN requester_id=%s THEN recipient_id ELSE requester_id END AS id
    FROM friendships WHERE status='accepted' AND (requester_id=%s OR recipient_id=%s)''', (uid, uid, uid))]
    games = core.allrows(c, '''SELECT a.user_id AS a,b.user_id AS b,ta.vp AS va,tb.vp AS vb FROM matches m
    JOIN match_players a ON a.match_id=m.id AND a.slot=1 JOIN match_players b ON b.match_id=m.id AND b.slot=2
    JOIN player_totals ta ON ta.id=a.id JOIN player_totals tb ON tb.id=b.id
    WHERE m.kind='friend' AND m.status='confirmed' AND a.user_id = ANY(%s) AND b.user_id = ANY(%s)
    ORDER BY m.played_at,m.id''', (circle, circle))
    from .seasons import rate
    rating, record = rate(games, START, K)
    people = {r['id']: r for r in core.allrows(c, 'SELECT id,public_id,display_name FROM users WHERE id = ANY(%s)', (circle,))}
    out = [{'public_id': people[i]['public_id'], 'display_name': people[i]['display_name'], 'rating': round(rating[i]),
            'me': i == uid, **record[i]} for i in people if record[i]['games'] or i == uid]
    out.sort(key=lambda r: (-r['rating'], -r['games'], r['display_name']))
    for n, r in enumerate(out, 1):
        r['rank'] = n
    return {'players': out, 'games': len(games), 'start': START, 'k': K}


def club_elo(c, uid):
    """v1.13: the club rating; players are ('u', user id) or ('l', local player id)."""
    rows = core.allrows(c, '''SELECT a.user_id AS au,a.local_player_id AS al,b.user_id AS bu,b.local_player_id AS bl,
    ta.vp AS va,tb.vp AS vb FROM matches m
    JOIN match_players a ON a.match_id=m.id AND a.slot=1 JOIN match_players b ON b.match_id=m.id AND b.slot=2
    JOIN player_totals ta ON ta.id=a.id JOIN player_totals tb ON tb.id=b.id
    WHERE (m.kind='friend' AND m.status='confirmed' AND a.user_id IS NOT NULL AND b.user_id IS NOT NULL)
    OR (m.kind IN ('guest','hotseat') AND m.status='unconfirmed' AND a.user_id=m.created_by AND b.local_player_id IS NOT NULL)
    ORDER BY m.played_at,m.id''')
    key = lambda u_, l_: ('u', u_) if u_ is not None else ('l', str(l_))
    games = [{'a': key(r['au'], r['al']), 'b': key(r['bu'], r['bl']), 'va': r['va'], 'vb': r['vb']} for r in rows]
    from .seasons import rate
    rating, record = rate(games, START, K)
    users = [k[1] for k in record if k[0] == 'u']
    if ('u', uid) not in record:
        users.append(uid)
    people = {('u', r['id']): r for r in core.allrows(c, '''SELECT u.id,u.public_id,u.display_name,coalesce(p.hidden,false) AS hidden
    FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id = ANY(%s)''', (users,))}
    people |= {('l', str(r['id'])): r | {'public_id': None, 'hidden': False, 'local': True} for r in core.allrows(c,
               'SELECT id,name AS display_name FROM local_players WHERE id::text = ANY(%s)', ([k[1] for k in record if k[0] == 'l'],))}
    out = [{'public_id': p['public_id'], 'display_name': p['display_name'], 'rating': round(rating[k]), 'me': k == ('u', uid),
            'local': bool(p.get('local')), **record[k]}
           for k, p in people.items() if (record[k]['games'] or k == ('u', uid)) and (not p['hidden'] or k == ('u', uid))]
    out.sort(key=lambda r: (-r['rating'], -r['games'], r['display_name']))
    for n, r in enumerate(out, 1):
        r['rank'] = n
    return {'players': out[:500], 'games': len(games), 'start': START, 'k': K}


@core.app.get('/api/ratings')
def ratings(scope: str = Query('friends', pattern='^(friends|all)$'), u=Depends(core.user)):
    """Elo among friends (default) or across the club (scope=all, v1.13)."""
    with core.pool.connection() as c:
        return (club_elo if scope == 'all' else elo)(c, u['id']) | {'scope': scope}
