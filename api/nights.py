"""v1.10: game nights — date and place, who comes and with which team, pairs per table, calendar export.

Any player can organise a night; the organiser and administrators edit it, generate and publish pairs.
Pairs: attendees who answered «yes», ordered by the current season rating (club-wide Elo without a season),
neighbours play each other, rematches from the last nights are avoided, an odd player gets a bye.
Calendar: one night as .ics, or a personal subscription feed /api/calendar/<token>.ics (only a hash of the
token is stored; the link is shown once and can be replaced)."""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import Depends, Request
from fastapi.responses import Response
from pydantic import Field, field_validator, model_validator
from psycopg.types.json import Jsonb
from . import main as core

ANSWERS = ('yes', 'maybe', 'no')


class NightIn(core.Op):
    title: str = Field(min_length=1, max_length=80)
    starts_at: datetime
    ends_at: datetime
    place: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1000)
    capacity: int | None = Field(default=None, ge=2, le=64)

    @field_validator('starts_at', 'ends_at')
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None:
            raise ValueError('timezone_required')
        return v.astimezone(timezone.utc)

    @model_validator(mode='after')
    def order(self):
        if self.ends_at <= self.starts_at or self.ends_at - self.starts_at > timedelta(hours=24):
            raise ValueError('night_dates_invalid')
        return self


class NightUpdate(NightIn):
    version: int = Field(ge=1)
    status: str = Field(default='planned', pattern='^(planned|cancelled)$')


class Rsvp(core.Op):
    answer: str = Field(pattern='^(yes|maybe|no)$')
    team_id: int | None = None
    comment: str = Field(default='', max_length=140)


class PairsCmd(core.Op):
    version: int = Field(ge=1)
    action: str = Field(pattern='^(generate|publish|clear|set)$')
    pairs: list[list[str | None]] = Field(default_factory=list, max_length=32)


class PairMatch(core.Op):
    pass


def load(c, nid, lock=False):
    n = core.one(c, 'SELECT * FROM game_nights WHERE id=%s' + (' FOR UPDATE' if lock else ''), (str(nid),))
    if not n:
        core.fail(404, 'night_not_found')
    return n


def can_edit(n, u):
    return n['organizer_id'] == u['id'] or bool(u.get('is_admin'))


def editor(n, u):
    if not can_edit(n, u):
        core.fail(403, 'night_organizer_only')


def touch(c, nid):
    c.execute('UPDATE game_nights SET version=version+1,updated_at=now() WHERE id=%s', (str(nid),))


def attendees(c, nid):
    return core.allrows(c, '''SELECT u.id,u.public_id,u.display_name,r.answer,r.team_id,r.comment,r.updated_at,
    coalesce(p.hidden,false) AS hidden FROM game_night_rsvps r JOIN users u ON u.id=r.user_id
    LEFT JOIN user_profiles p ON p.user_id=u.id WHERE r.night_id=%s ORDER BY r.answer,r.updated_at''', (str(nid),))


def detail(c, n, u):
    people = attendees(c, n['id'])
    pairs = core.allrows(c, '''SELECT g.id,g.table_no,g.match_id,a.public_id AS a_id,a.display_name AS a_name,
    b.public_id AS b_id,b.display_name AS b_name,(SELECT status FROM matches WHERE id=g.match_id) AS match_status,
    (g.a_id=%s OR g.b_id=%s) AS mine FROM game_night_pairs g LEFT JOIN users a ON a.id=g.a_id LEFT JOIN users b ON b.id=g.b_id
    WHERE g.night_id=%s ORDER BY g.table_no''', (u['id'], u['id'], str(n['id'])))
    editable = can_edit(n, u)
    if not editable and not n['pairs_published_at']:
        pairs = []
    for x in pairs:
        if not x['mine']:
            x['match_id'] = None
    mine = next((p for p in people if p['id'] == u['id']), None)
    org = core.one(c, 'SELECT display_name,public_id FROM users WHERE id=%s', (n['organizer_id'],)) if n['organizer_id'] else None
    out = {k: n[k] for k in ('id', 'title', 'starts_at', 'ends_at', 'place', 'notes', 'capacity', 'status', 'pairs_published_at', 'version')}
    return out | {'organizer': org, 'can_edit': editable,
                  'counts': {a: sum(1 for p in people if p['answer'] == a) for a in ANSWERS},
                  'my': mine and {k: mine[k] for k in ('answer', 'team_id', 'comment')},
                  'attendees': [{k: p[k] for k in ('public_id', 'display_name', 'answer', 'team_id', 'comment')} for p in people],
                  'pairs': pairs}


@core.app.get('/api/nights')
def nights(scope: str = 'upcoming', u=Depends(core.user)):
    cond, order = ('n.ends_at > now()', 'n.starts_at') if scope != 'past' else ('n.ends_at <= now()', 'n.starts_at DESC')
    with core.pool.connection() as c:
        return core.allrows(c, f'''SELECT n.id,n.title,n.starts_at,n.ends_at,n.place,n.status,n.capacity,n.pairs_published_at,
        o.display_name AS organizer_name,
        (SELECT count(*)::int FROM game_night_rsvps r WHERE r.night_id=n.id AND r.answer='yes') AS yes,
        (SELECT count(*)::int FROM game_night_rsvps r WHERE r.night_id=n.id AND r.answer='maybe') AS maybe,
        (SELECT answer FROM game_night_rsvps r WHERE r.night_id=n.id AND r.user_id=%s) AS my_answer
        FROM game_nights n LEFT JOIN users o ON o.id=n.organizer_id WHERE {cond} ORDER BY {order} LIMIT 50''', (u['id'],))


@core.app.post('/api/nights', status_code=201)
def create_night(p: NightIn, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            if p.ends_at < datetime.now(timezone.utc):
                core.fail(422, 'night_in_past')
            if core.one(c, "SELECT count(*)::int AS n FROM game_nights WHERE organizer_id=%s AND ends_at>now() AND status='planned'", (u['id'],))['n'] >= 10:
                core.fail(429, 'too_many_nights')
            nid = str(uuid4())
            c.execute('''INSERT INTO game_nights(id,organizer_id,title,starts_at,ends_at,place,notes,capacity) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                      (nid, u['id'], p.title.strip(), p.starts_at, p.ends_at, p.place.strip(), p.notes, p.capacity))
            c.execute("INSERT INTO game_night_rsvps(night_id,user_id,answer) VALUES(%s,%s,'yes')", (nid, u['id']))
            for r in core.allrows(c, 'SELECT id FROM users WHERE id<>%s', (u['id'],)):  # the whole club is invited
                core.notify(c, r['id'], 'night_created', nid)
            return {'id': nid}
        return core.operation(c, u, p, 'night:create', run)


@core.app.get('/api/nights/{nid}')
def get_night(nid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        return detail(c, load(c, nid), u)


@core.app.put('/api/nights/{nid}')
def update_night(nid: UUID, p: NightUpdate, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            n = load(c, nid, True)
            editor(n, u)
            core.version(n, p.version)
            c.execute('''UPDATE game_nights SET title=%s,starts_at=%s,ends_at=%s,place=%s,notes=%s,capacity=%s,status=%s WHERE id=%s''',
                      (p.title.strip(), p.starts_at, p.ends_at, p.place.strip(), p.notes, p.capacity, p.status, str(nid)))
            touch(c, nid)
            kind = 'night_cancelled' if p.status == 'cancelled' and n['status'] != 'cancelled' else \
                'night_changed' if (p.starts_at, p.ends_at, p.place.strip()) != (n['starts_at'], n['ends_at'], n['place']) else None
            if kind:
                for r in core.allrows(c, "SELECT user_id FROM game_night_rsvps WHERE night_id=%s AND answer<>'no' AND user_id<>%s", (str(nid), u['id'])):
                    core.notify(c, r['user_id'], kind, nid)
            return {'ok': True}
        return core.operation(c, u, p, 'night:' + str(nid), run)


@core.app.post('/api/nights/{nid}/rsvp')
def rsvp(nid: UUID, p: Rsvp, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            n = load(c, nid, True)
            if n['status'] != 'planned' or n['ends_at'] < datetime.now(timezone.utc):
                core.fail(409, 'night_closed')
            if p.team_id is not None and not core.one(c, "SELECT 1 FROM catalogs WHERE id=%s AND kind='team'", (p.team_id,)):
                core.fail(422, 'catalog_invalid')
            if p.answer == 'yes' and n['capacity']:
                taken = core.one(c, "SELECT count(*)::int AS n FROM game_night_rsvps WHERE night_id=%s AND answer='yes' AND user_id<>%s", (str(nid), u['id']))['n']
                if taken >= n['capacity']:
                    core.fail(409, 'night_full')
            c.execute('''INSERT INTO game_night_rsvps(night_id,user_id,answer,team_id,comment) VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(night_id,user_id) DO UPDATE SET answer=excluded.answer,team_id=excluded.team_id,comment=excluded.comment,updated_at=now()''',
                      (str(nid), u['id'], p.answer, p.team_id, p.comment.strip()))
            if p.answer != 'yes':  # a player who does not come leaves the table plan
                c.execute('UPDATE game_night_pairs SET a_id=b_id,b_id=NULL WHERE night_id=%s AND a_id=%s', (str(nid), u['id']))
                c.execute('UPDATE game_night_pairs SET b_id=NULL WHERE night_id=%s AND b_id=%s', (str(nid), u['id']))
                c.execute('DELETE FROM game_night_pairs WHERE night_id=%s AND a_id IS NULL', (str(nid),))
            touch(c, nid)
            return {'ok': True}
        return core.operation(c, u, p, 'night-rsvp:' + str(nid), run)


def ratings(c):
    """Pairing order: the current season table, otherwise club-wide Elo over all confirmed friend matches."""
    from . import seasons
    s = seasons.current_season(c) or {'starts_on': datetime(2000, 1, 1).date(), 'ends_on': datetime(2100, 1, 1).date(),
                                       'k_factor': 32, 'start_rating': 1500}
    return {r['user_id']: r['rating'] for r in seasons.table(c, s)['players']}, s.get('start_rating', 1500)


def generate(c, n):
    people = [p for p in attendees(c, n['id']) if p['answer'] == 'yes']
    if len(people) < 2:
        core.fail(409, 'night_too_small')
    rating, start = ratings(c)
    order = sorted((p['id'] for p in people), key=lambda i: (-rating.get(i, start), secrets.randbelow(1000)))
    recent = core.allrows(c, '''SELECT g.a_id,g.b_id FROM game_night_pairs g JOIN game_nights n ON n.id=g.night_id
    WHERE n.id<>%s AND n.starts_at > %s - interval '60 days' AND n.starts_at < %s''', (str(n['id']), n['starts_at'], n['starts_at']))
    played = {frozenset((x['a_id'], x['b_id'])) for x in recent if x['a_id'] and x['b_id']}
    byes = {x['a_id'] for x in recent if not x['b_id']}
    from .tournaments import swiss
    return swiss(order, played, byes)


def store(c, nid, pairs):
    c.execute('DELETE FROM game_night_pairs WHERE night_id=%s', (str(nid),))
    for i, (a, b) in enumerate(pairs, 1):
        c.execute('INSERT INTO game_night_pairs(night_id,table_no,a_id,b_id) VALUES(%s,%s,%s,%s)', (str(nid), i, a, b))


@core.app.post('/api/nights/{nid}/pairs')
def pairs(nid: UUID, p: PairsCmd, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            n = load(c, nid, True)
            editor(n, u)
            core.version(n, p.version)
            if n['status'] != 'planned':
                core.fail(409, 'night_closed')
            if p.action == 'generate':
                store(c, nid, generate(c, n))
                c.execute('UPDATE game_nights SET pairs_published_at=NULL WHERE id=%s', (str(nid),))
            elif p.action == 'set':
                ids = {r['public_id']: r['id'] for r in attendees(c, nid) if r['answer'] == 'yes'}
                seen, rows = set(), []
                for pair in p.pairs:
                    if len(pair) != 2 or pair[0] not in ids or (pair[1] is not None and pair[1] not in ids):
                        core.fail(422, 'pairs_invalid')
                    one = [ids[pair[0]], ids[pair[1]] if pair[1] else None]
                    if any(x in seen for x in one if x) or one[0] == one[1]:
                        core.fail(422, 'pairs_invalid')
                    seen.update(x for x in one if x)
                    rows.append(one)
                store(c, nid, rows)
            elif p.action == 'clear':
                store(c, nid, [])
                c.execute('UPDATE game_nights SET pairs_published_at=NULL WHERE id=%s', (str(nid),))
            else:
                rows = core.allrows(c, 'SELECT a_id,b_id FROM game_night_pairs WHERE night_id=%s', (str(nid),))
                if not rows:
                    core.fail(409, 'pairs_empty')
                c.execute('UPDATE game_nights SET pairs_published_at=now() WHERE id=%s', (str(nid),))
                for r in rows:
                    for x in (r['a_id'], r['b_id']):
                        if x and x != u['id']:
                            core.notify(c, x, 'night_pairs', nid)
            touch(c, nid)
            return {'ok': True}
        return core.operation(c, u, p, 'night-pairs:' + str(nid), run)


@core.app.post('/api/nights/{nid}/pairs/{pid}/match', status_code=201)
def pair_match(nid: UUID, pid: int, p: PairMatch, u=Depends(core.user)):
    """One of the two players opens the friend match of their table."""
    with core.pool.connection() as c:
        def run():
            n = load(c, nid, True)
            x = core.one(c, 'SELECT * FROM game_night_pairs WHERE id=%s AND night_id=%s FOR UPDATE', (pid, str(nid)))
            if not x or not n['pairs_published_at'] or not x['b_id']:
                core.fail(409, 'pairing_closed')
            if u['id'] not in (x['a_id'], x['b_id']):
                core.fail(403, 'pairing_not_player')
            if x['match_id'] and core.one(c, "SELECT 1 FROM matches WHERE id=%s AND status<>'cancelled'", (str(x['match_id']),)):
                return {'id': str(x['match_id'])}
            other = x['b_id'] if x['a_id'] == u['id'] else x['a_id']
            mid = str(uuid4())
            c.execute("INSERT INTO matches(id,created_by,kind,status,edition,setup) VALUES(%s,%s,'friend','setup','2024',%s)",
                      (mid, u['id'], Jsonb({'edition': '2024', 'mission_id': None, 'mode': 'Игровой вечер', 'night_id': str(nid)})))
            c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,1,%s,%s)', (mid, u['id'], u['display_name']))
            name = core.one(c, 'SELECT display_name FROM users WHERE id=%s', (other,))['display_name']
            c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,2,%s,%s)', (mid, other, name))
            # Teams announced in the RSVP become the default choice of the setup.
            for slot, who in ((1, u['id']), (2, other)):
                c.execute('''UPDATE match_players SET team_id=(SELECT r.team_id FROM game_night_rsvps r JOIN catalogs k ON k.id=r.team_id
                WHERE r.night_id=%s AND r.user_id=%s AND k.active) WHERE match_id=%s AND slot=%s''', (str(nid), who, mid, slot))
            core.audit(c, mid, u, 'create', {}, {'kind': 'friend', 'edition': '2024', 'night_id': str(nid), 'table': x['table_no']})
            c.execute('UPDATE game_night_pairs SET match_id=%s WHERE id=%s', (mid, pid))
            core.notify(c, other, 'night_match', mid)
            return {'id': mid}
        return core.operation(c, u, p, 'night-match:' + str(pid), run)


# ------------------------------------------------------------------ calendar (RFC 5545)
def ics_text(v):
    return str(v or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r\n', '\n').replace('\n', '\\n')


def fold(line):
    """Lines longer than 75 octets continue on the next line after one space (never inside a UTF-8 sequence)."""
    raw, out, limit = line.encode(), [], 75
    while len(raw) > limit:
        cut = limit
        while 0x80 <= raw[cut] < 0xC0:
            cut -= 1
        out.append(raw[:cut].decode())
        raw, limit = raw[cut:], 74
    out.append(raw.decode())
    return '\r\n '.join(out)


def stamp(v):
    return v.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def vevent(c, n, prefix=''):
    people = [p for p in attendees(c, n['id']) if p['answer'] == 'yes']
    lines = [f"{len(people)} ✓: " + ', '.join(p['display_name'] for p in people)] if people else []
    if n['pairs_published_at']:
        for x in core.allrows(c, '''SELECT g.table_no,a.display_name AS a,b.display_name AS b FROM game_night_pairs g
        LEFT JOIN users a ON a.id=g.a_id LEFT JOIN users b ON b.id=g.b_id WHERE g.night_id=%s ORDER BY g.table_no''', (str(n['id']),)):
            lines.append(f"#{x['table_no']}: {x['a'] or '—'} — {x['b'] or 'bye'}")
    if n['notes']:
        lines.append(n['notes'])
    rows = ['BEGIN:VEVENT', f"UID:night-{n['id']}@killstass", f"DTSTAMP:{stamp(n['updated_at'])}",
            f"DTSTART:{stamp(n['starts_at'])}", f"DTEND:{stamp(n['ends_at'])}", f"SUMMARY:{ics_text(prefix + n['title'])}",
            f"SEQUENCE:{n['version'] - 1}", f"STATUS:{'CANCELLED' if n['status'] == 'cancelled' else 'CONFIRMED'}",
            f"URL:{core.ORIGIN}/#nights/{n['id']}"]
    if n['place']:
        rows.append(f"LOCATION:{ics_text(n['place'])}")
    if lines:
        rows.append(f"DESCRIPTION:{ics_text(chr(10).join(lines))}")
    return rows + ['END:VEVENT']


def calendar(events, name='KILLSTASS'):
    rows = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//KILLSTASS//Game nights//RU', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
            f'X-WR-CALNAME:{ics_text(name)}', 'X-WR-TIMEZONE:Europe/Moscow'] + [r for e in events for r in e] + ['END:VCALENDAR']
    return '\r\n'.join(fold(r) for r in rows) + '\r\n'


def ics_response(body, filename):
    return Response(body, media_type='text/calendar; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@core.app.get('/api/nights/{nid}/calendar.ics')
def night_ics(nid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        n = load(c, nid)
        return ics_response(calendar([vevent(c, n)]), 'killstass-night.ics')


class TokenCmd(core.Op):
    pass


@core.app.post('/api/calendar/token', status_code=201)
def calendar_token(p: TokenCmd, u=Depends(core.user)):
    """A new private feed link (the previous one stops working). Not idempotent on purpose: the token is shown once."""
    token = secrets.token_urlsafe(24)
    with core.pool.connection() as c:
        c.execute('''INSERT INTO calendar_tokens(user_id,token_hash) VALUES(%s,%s)
        ON CONFLICT(user_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=now()''', (u['id'], core.digest(token)))
    return {'path': f'/api/calendar/{token}.ics'}


@core.app.delete('/api/calendar/token')
def calendar_revoke(u=Depends(core.user)):
    with core.pool.connection() as c:
        c.execute('DELETE FROM calendar_tokens WHERE user_id=%s', (u['id'],))
    return {'ok': True}


@core.app.get('/api/calendar/token')
def calendar_status(u=Depends(core.user)):
    with core.pool.connection() as c:
        row = core.one(c, 'SELECT created_at FROM calendar_tokens WHERE user_id=%s', (u['id'],))
    return {'active': bool(row), 'created_at': row and row['created_at']}


@core.app.get('/api/calendar/{token}.ics')
def calendar_feed(token: str, request: Request):
    """Subscription feed: nights of the last 60 days and all upcoming ones, except those the player declined."""
    core.limit(request, 'calendar', 120)
    with core.pool.connection() as c:
        owner = core.one(c, 'SELECT user_id FROM calendar_tokens WHERE token_hash=%s', (core.digest(token),))
        if not owner:
            core.fail(404, 'calendar_not_found')
        events = []
        for n in core.allrows(c, '''SELECT n.*,r.answer FROM game_nights n LEFT JOIN game_night_rsvps r ON r.night_id=n.id AND r.user_id=%s
        WHERE n.starts_at > now() - interval '60 days' AND r.answer IS DISTINCT FROM 'no' ORDER BY n.starts_at LIMIT 200''', (owner['user_id'],)):
            events.append(vevent(c, n, '' if n['answer'] == 'yes' else '? '))
        return ics_response(calendar(events), 'killstass.ics')
