"""v1.10: TV screen (#tv/<key>) — live matches with score, turning point and clock, recent results,
tournament standings, the season table and the next game night. Read-only and without a session:
an administrator creates a screen in #admin and opens its link on the TV; deleting the screen revokes it.
Players who hide their profile are shown without a name."""
import secrets
from fastapi import Depends, Request
from pydantic import Field
from uuid import UUID
from . import main as core
from . import clock as clockmod


class ScreenIn(core.Model):
    label: str = Field(min_length=1, max_length=60)
    tournament_id: UUID | None = None


@core.app.get('/api/admin/tv')
def screens(u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        return core.allrows(c, '''SELECT s.id,s.label,s.key,s.tournament_id,t.name AS tournament_name,s.created_at,s.last_seen_at
        FROM tv_screens s LEFT JOIN tournaments t ON t.id=s.tournament_id ORDER BY s.id''')


@core.app.post('/api/admin/tv', status_code=201)
def create_screen(p: ScreenIn, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        if p.tournament_id and not core.one(c, 'SELECT 1 FROM tournaments WHERE id=%s', (str(p.tournament_id),)):
            core.fail(404, 'tournament_not_found')
        return core.one(c, 'INSERT INTO tv_screens(label,key,tournament_id,created_by) VALUES(%s,%s,%s,%s) RETURNING id,label,key,tournament_id',
                        (p.label.strip(), secrets.token_urlsafe(24), str(p.tournament_id) if p.tournament_id else None, u['id']))


@core.app.delete('/api/admin/tv/{sid}')
def delete_screen(sid: int, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        if not core.one(c, 'DELETE FROM tv_screens WHERE id=%s RETURNING id', (sid,)):
            core.fail(404, 'tv_not_found')
    return {'ok': True}


def screen(c, key, request):
    s = core.one(c, 'SELECT * FROM tv_screens WHERE key=%s', (key,)) if 24 <= len(key) <= 64 else None
    if not s:
        c.rollback()
        core.limit(request, 'tv-miss', 30)
        core.fail(404, 'tv_not_found')
    c.execute("UPDATE tv_screens SET last_seen_at=now() WHERE id=%s AND (last_seen_at IS NULL OR last_seen_at<now()-interval '1 minute')", (s['id'],))
    return s


def hidden_ids(c):
    return {r['user_id'] for r in core.allrows(c, 'SELECT user_id FROM user_profiles WHERE hidden')}


def hidden_public(c):
    return {r['public_id'] for r in core.allrows(c, 'SELECT u.public_id FROM users u JOIN user_profiles p ON p.user_id=u.id WHERE p.hidden')}


def label(c, cid):
    row = cid and core.one(c, 'SELECT code,label FROM catalogs WHERE id=%s', (cid,))
    return {'code': row['code'], 'label': row['label']} if row else None


def player_rows(c, mid, hidden):
    rows = core.allrows(c, '''SELECT p.slot,p.user_id,p.display_name,p.team_id,t.vp,u.public_id,(a.user_id IS NOT NULL) AS has_avatar
    FROM match_players p JOIN player_totals t ON t.id=p.id LEFT JOIN users u ON u.id=p.user_id LEFT JOIN avatars a ON a.user_id=p.user_id
    WHERE p.match_id=%s ORDER BY p.slot''', (str(mid),))
    out = []
    for r in rows:
        secret = r['user_id'] in hidden
        out.append({'slot': r['slot'], 'name': None if secret else r['display_name'], 'vp': r['vp'], 'team': label(c, r['team_id']),
                    'avatar': r['public_id'] if r['has_avatar'] and not secret else None})
    return out


@core.app.get('/api/tv/{key}')
def tv(key: str, request: Request):
    from . import seasons
    with core.pool.connection() as c:
        s = screen(c, key, request)
        hidden = hidden_ids(c)
        live = []
        for m in core.allrows(c, '''SELECT id,kind,status,mission_id,killzone_id,current_turn,turns,played_at,updated_at FROM matches
        WHERE status IN ('active','awaiting_confirmation') AND updated_at > now() - interval '12 hours' ORDER BY played_at NULLS LAST LIMIT 12'''):
            clk = clockmod.load(c, m['id'])
            live.append({'id': str(m['id'])[:8], 'status': m['status'], 'kind': m['kind'], 'turn': m['current_turn'], 'turns': m['turns'],
                         'mission': label(c, m['mission_id']), 'killzone': label(c, m['killzone_id']), 'players': player_rows(c, m['id'], hidden),
                         'clock': clk if clk['mode'] else None})
        recent = []
        for m in core.allrows(c, '''SELECT id,mission_id,updated_at FROM matches WHERE status IN ('confirmed','unconfirmed') AND kind<>'guest'
        AND updated_at > now() - interval '6 hours' ORDER BY updated_at DESC LIMIT 6'''):
            recent.append({'mission': label(c, m['mission_id']), 'at': m['updated_at'], 'players': player_rows(c, m['id'], hidden)})
        from .tournaments import state
        secret = hidden_public(c)
        tours = []
        where = 'id=%s' if s['tournament_id'] else "status='active'"
        for t in core.allrows(c, f'SELECT * FROM tournaments WHERE {where} ORDER BY created_at DESC LIMIT 2',
                              (str(s['tournament_id']),) if s['tournament_id'] else ()):
            st = state(c, t, None)
            names = {p['id']: None if p.get('public_id') in secret else p['name'] for p in st['players']}
            tours.append({'name': t['name'], 'format': t['format'], 'status': t['status'], 'round': t['current_round'], 'rounds': t['rounds'],
                          'standings': [{'rank': r['rank'], 'name': names.get(r['player_id']), 'points': r['points'], 'wins': r['wins'],
                                         'draws': r['draws'], 'losses': r['losses'], 'diff': r['diff'], 'vp_for': r['vp_for']} for r in st['standings'][:10]],
                          'pairings': [{'table': x['table_no'], 'a': names.get(x['player1_id']), 'b': names.get(x['player2_id']) if x['player2_id'] else None,
                                        'vp1': x['vp1'], 'vp2': x['vp2'], 'status': x['match_status']}
                                       for x in st['pairings'] if x['round'] == t['current_round']]})
        cur = seasons.current_season(c)
        season = None
        if cur:
            top = [r for r in seasons.table(c, cur)['players'] if r['user_id'] not in hidden][:10]
            season = {'name': cur['name'], 'ends_on': cur['ends_on'],
                      'players': [{'rank': n, 'name': r['display_name'], 'rating': r['rating'], 'games': r['games']} for n, r in enumerate(top, 1)]}
        n = core.one(c, '''SELECT * FROM game_nights WHERE status='planned' AND ends_at > now() AND starts_at < now() + interval '7 days'
        ORDER BY starts_at LIMIT 1''')
        night = None
        if n:
            people = core.allrows(c, '''SELECT u.id,u.display_name,r.team_id FROM game_night_rsvps r JOIN users u ON u.id=r.user_id
            WHERE r.night_id=%s AND r.answer='yes' ORDER BY r.updated_at''', (str(n['id']),))
            pairs = core.allrows(c, '''SELECT g.table_no,g.a_id,g.b_id,a.display_name AS a,b.display_name AS b FROM game_night_pairs g
            LEFT JOIN users a ON a.id=g.a_id LEFT JOIN users b ON b.id=g.b_id WHERE g.night_id=%s ORDER BY g.table_no''', (str(n['id']),)) if n['pairs_published_at'] else []
            night = {'title': n['title'], 'starts_at': n['starts_at'], 'ends_at': n['ends_at'], 'place': n['place'], 'capacity': n['capacity'],
                     'attendees': [{'name': None if p['id'] in hidden else p['display_name'], 'team': label(c, p['team_id'])} for p in people],
                     'pairs': [{'table': x['table_no'], 'a': None if x['a_id'] in hidden else x['a'],
                                'b': None if x['b_id'] in hidden else x['b'], 'bye': x['b_id'] is None} for x in pairs]}
        now = core.one(c, 'SELECT clock_timestamp() AS now')['now']
    return {'label': s['label'], 'server_now': now.isoformat(), 'matches': live, 'recent': recent, 'tournaments': tours,
            'season': season, 'night': night}


@core.app.get('/api/tv/{key}/avatar/{public_id}')
def tv_avatar(key: str, public_id: str, request: Request):
    from .accounts import avatar_response
    with core.pool.connection() as c:
        screen(c, key, request)
        row = core.one(c, '''SELECT a.mime,a.data,a.sha256 FROM avatars a JOIN users u ON u.id=a.user_id
        LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.public_id=%s AND NOT coalesce(p.hidden,false)''', (public_id.upper(),))
    if not row:
        core.fail(404, 'avatar_not_found')
    return avatar_response(row, request)
