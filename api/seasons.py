"""v1.10: Elo seasons and achievements.

Seasons (administrator, #admin): a date range in Moscow time with its own K factor and start rating.
The season table is club-wide: every confirmed friend match between two registered players inside the
range counts, oldest first. Players who hide their profile take part in the calculation but are not listed.

Achievements: a fixed set of rules with an administrator-chosen threshold, optionally limited to one season.
They are awarded when a match is confirmed (hot-seat: finished, quick record: saved), when a tournament
ends, and on the player page (silently, for results recorded before the achievement existed)."""
from collections import defaultdict
from datetime import date
from fastapi import Depends
from pydantic import Field, model_validator
from . import main as core

RULES = ('matches', 'wins', 'win_streak', 'comeback', 'big_win', 'opponents', 'teams', 'tournament_wins', 'nights')
ICONS = ('trophy', 'flag', 'bolt', 'star', 'crosshair', 'skull', 'shield', 'heart', 'target', 'dice', 'clock',
         'people', 'book', 'melee', 'eye', 'check', 'chart', 'grid', 'palette', 'lock')
MSK = "AT TIME ZONE 'Europe/Moscow'"


def rate(games, start, k):
    """Elo over (a, b, va, vb) games in order. Returns ratings and win/draw/loss records."""
    rating = defaultdict(lambda: float(start))
    record = defaultdict(lambda: {'games': 0, 'wins': 0, 'draws': 0, 'losses': 0})
    for g in games:
        ra, rb = rating[g['a']], rating[g['b']]
        ea = 1 / (1 + 10 ** ((rb - ra) / 400))
        sa = 1.0 if g['va'] > g['vb'] else 0.5 if g['va'] == g['vb'] else 0.0
        rating[g['a']] = ra + k * (sa - ea)
        rating[g['b']] = rb + k * ((1 - sa) - (1 - ea))
        for who, s in ((g['a'], sa), (g['b'], 1 - sa)):
            rec = record[who]
            rec['games'] += 1
            rec['wins' if s == 1 else 'draws' if s == 0.5 else 'losses'] += 1
    return rating, record


def status(s, today=None):
    today = today or date.today()
    return 'upcoming' if s['starts_on'] > today else 'past' if s['ends_on'] < today else 'current'


def current_season(c):
    return core.one(c, f'''SELECT * FROM seasons WHERE starts_on <= (now() {MSK})::date AND ends_on >= (now() {MSK})::date
    ORDER BY starts_on DESC LIMIT 1''')


def table(c, s, viewer_id=None, limit=500):
    games = core.allrows(c, f'''SELECT a.user_id AS a,b.user_id AS b,ta.vp AS va,tb.vp AS vb FROM matches m
    JOIN match_players a ON a.match_id=m.id AND a.slot=1 JOIN match_players b ON b.match_id=m.id AND b.slot=2
    JOIN player_totals ta ON ta.id=a.id JOIN player_totals tb ON tb.id=b.id
    WHERE m.kind='friend' AND m.status='confirmed' AND a.user_id IS NOT NULL AND b.user_id IS NOT NULL
    AND m.played_at >= %s::date::timestamp {MSK} AND m.played_at < (%s::date+1)::timestamp {MSK}
    ORDER BY m.played_at,m.id''', (s['starts_on'], s['ends_on']))
    rating, record = rate(games, s['start_rating'], s['k_factor'])
    ids = list(record)
    people = {r['id']: r for r in core.allrows(c, '''SELECT u.id,u.public_id,u.display_name,coalesce(p.hidden,false) AS hidden,
    a.sha256 FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id LEFT JOIN avatars a ON a.user_id=u.id
    WHERE u.id = ANY(%s)''', (ids,))}
    rows = [{'public_id': people[i]['public_id'], 'display_name': people[i]['display_name'], 'rating': round(rating[i]),
             'avatar': people[i]['sha256'][:16] if people[i]['sha256'] else None, 'me': i == viewer_id, 'user_id': i, **record[i]}
            for i in ids if i in people and (not people[i]['hidden'] or i == viewer_id)]
    rows.sort(key=lambda r: (-r['rating'], -r['games'], r['display_name']))
    for n, r in enumerate(rows, 1):
        r['rank'] = n
    return {'players': rows[:limit], 'games': len(games)}


def public_season(s):
    return {k: s[k] for k in ('id', 'name', 'starts_on', 'ends_on', 'k_factor', 'start_rating')} | {'status': status(s)}


@core.app.get('/api/seasons')
def seasons(u=Depends(core.user)):
    with core.pool.connection() as c:
        rows = core.allrows(c, 'SELECT * FROM seasons ORDER BY starts_on DESC')
        cur = current_season(c)
    return {'seasons': [public_season(s) for s in rows], 'current_id': cur['id'] if cur else None}


@core.app.get('/api/seasons/{sid}/ratings')
def season_ratings(sid: int, u=Depends(core.user)):
    with core.pool.connection() as c:
        s = core.one(c, 'SELECT * FROM seasons WHERE id=%s', (sid,))
        if not s:
            core.fail(404, 'season_not_found')
        t = table(c, s, u['id'])
    for r in t['players']:
        r.pop('user_id')
    return {'season': public_season(s), **t}


def player_season(c, uid):
    s = current_season(c)
    if not s:
        return None
    row = next((r for r in table(c, s, uid)['players'] if r['user_id'] == uid), None)
    out = {'id': s['id'], 'name': s['name'], 'starts_on': s['starts_on'], 'ends_on': s['ends_on'], 'start_rating': s['start_rating']}
    return out | ({k: row[k] for k in ('rating', 'rank', 'games', 'wins', 'draws', 'losses')} if row else {'rating': None, 'rank': None, 'games': 0})


# ------------------------------------------------------------------ achievements
def facts(c, uid):
    """Everything the rules need about one player, in chronological order."""
    results = core.allrows(c, f'''SELECT match_id,played_at,(played_at {MSK})::date AS day,result,vp_for,vp_against,opponent_id,team_id
    FROM player_results WHERE user_id=%s ORDER BY played_at,match_id''', (uid,))
    deficits = defaultdict(int)  # largest deficit after a turning point in matches the player won
    rows = core.allrows(c, '''SELECT s.player_id=mp.id AS mine,p.match_id,s.turning_point,sum(s.vp)::int AS vp
    FROM player_results r JOIN match_players mp ON mp.match_id=r.match_id AND mp.user_id=r.user_id
    JOIN match_players p ON p.match_id=r.match_id JOIN turning_point_scores s ON s.player_id=p.id
    WHERE r.user_id=%s AND r.result='win' GROUP BY 1,2,3 ORDER BY 2,3''', (uid,))
    per = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        per[r['match_id']][r['turning_point']][0 if r['mine'] else 1] += r['vp']
    for mid, tps in per.items():
        mine = theirs = 0
        for tp in sorted(tps):
            mine += tps[tp][0]
            theirs += tps[tp][1]
            deficits[mid] = max(deficits[mid], theirs - mine)
    nights = core.allrows(c, f'''SELECT n.id,(n.starts_at {MSK})::date AS day FROM game_night_rsvps r JOIN game_nights n ON n.id=r.night_id
    WHERE r.user_id=%s AND r.answer='yes' AND n.status='planned' AND n.ends_at<now() ORDER BY n.starts_at''', (uid,))
    return {'results': results, 'deficits': deficits, 'nights': nights, 'tournaments': tournament_wins(c, uid)}


def tournament_wins(c, uid):
    from .tournaments import state
    days = []
    for t in core.allrows(c, f'''SELECT t.*,(t.created_at {MSK})::date AS day FROM tournaments t
    WHERE t.status='finished' AND EXISTS(SELECT 1 FROM tournament_players p WHERE p.tournament_id=t.id AND p.user_id=%s)''', (uid,)):
        st = state(c, t, uid)
        top = st['standings'][0] if st['standings'] else None
        if top and top['player_id'] == st['my_player_id'] and top['played']:
            days.append({'id': t['id'], 'day': t['day']})
    return days


def evaluate(rule, threshold, f, season=None):
    """(progress value, earned, match_id) for one rule; `season` limits the facts to its dates."""
    inside = (lambda d: season['starts_on'] <= d <= season['ends_on']) if season else (lambda d: True)
    res = [r for r in f['results'] if r['day'] and inside(r['day'])]
    count_at = lambda items: (items[threshold - 1]['match_id'] if len(items) >= threshold else None)
    if rule == 'matches':
        return len(res), len(res) >= threshold, count_at(res)
    if rule == 'wins':
        wins = [r for r in res if r['result'] == 'win']
        return len(wins), len(wins) >= threshold, count_at(wins)
    if rule == 'win_streak':
        best = run = 0
        hit = None
        for r in res:
            run = run + 1 if r['result'] == 'win' else 0
            if run >= threshold and hit is None:
                hit = r['match_id']
            best = max(best, run)
        return best, best >= threshold, hit
    if rule in ('comeback', 'big_win'):
        wins = [r for r in res if r['result'] == 'win']
        score = (lambda r: f['deficits'].get(r['match_id'], 0)) if rule == 'comeback' else (lambda r: r['vp_for'] - r['vp_against'])
        hit = next((r['match_id'] for r in wins if score(r) >= threshold), None)
        return max([score(r) for r in wins] or [0]), hit is not None, hit
    if rule == 'opponents':
        seen = []
        for r in res:
            if r['opponent_id'] and r['opponent_id'] not in seen:
                seen.append(r['opponent_id'])
        return len(seen), len(seen) >= threshold, None
    if rule == 'teams':
        seen = []
        for r in res:
            if r['team_id'] and r['team_id'] not in seen:
                seen.append(r['team_id'])
        return len(seen), len(seen) >= threshold, None
    items = [x for x in f['tournaments' if rule == 'tournament_wins' else 'nights'] if inside(x['day'])]
    return len(items), len(items) >= threshold, None


def award(c, uid, quiet=False):
    """Grant every active achievement the player qualifies for; returns the new codes."""
    todo = core.allrows(c, '''SELECT a.*,s.starts_on,s.ends_on FROM achievements a LEFT JOIN seasons s ON s.id=a.season_id
    WHERE a.active AND NOT EXISTS(SELECT 1 FROM user_achievements x WHERE x.user_id=%s AND x.achievement_id=a.id)''', (uid,))
    if not todo:
        return []
    f = facts(c, uid)
    new = []
    for a in todo:
        _, earned, mid = evaluate(a['rule'], a['threshold'], f, a if a['season_id'] else None)
        if earned and core.one(c, '''INSERT INTO user_achievements(user_id,achievement_id,match_id) VALUES(%s,%s,%s)
        ON CONFLICT DO NOTHING RETURNING achievement_id''', (uid, a['id'], str(mid) if mid else None)):
            new.append(a['code'])
            if not quiet:
                core.notify(c, uid, 'achievement', a['code'])
    return new


def award_match(c, mid):
    for r in core.allrows(c, 'SELECT user_id FROM match_players WHERE match_id=%s AND user_id IS NOT NULL', (str(mid),)):
        award(c, r['user_id'])


def player_achievements(c, uid):
    rows = core.allrows(c, '''SELECT a.id,a.code,a.title_ru,a.title_en,a.description_ru,a.description_en,a.icon,a.rule,a.threshold,
    a.season_id,s.name AS season_name,s.starts_on,s.ends_on,x.earned_at,x.match_id FROM achievements a
    LEFT JOIN seasons s ON s.id=a.season_id LEFT JOIN user_achievements x ON x.achievement_id=a.id AND x.user_id=%s
    WHERE a.active OR x.user_id IS NOT NULL ORDER BY x.earned_at IS NULL,a.position,a.id''', (uid,))
    f = facts(c, uid) if any(r['earned_at'] is None for r in rows) else None
    for r in rows:
        if r['earned_at'] is None:
            r['progress'] = evaluate(r['rule'], r['threshold'], f, r if r['season_id'] else None)[0]
        for k in ('starts_on', 'ends_on'):
            r.pop(k)
    return rows


@core.app.get('/api/achievements')
def achievements(u=Depends(core.user)):
    with core.pool.connection() as c:
        award(c, u['id'], quiet=True)
        return {'items': player_achievements(c, u['id']),
                'holders': {r['achievement_id']: r['n'] for r in core.allrows(c, 'SELECT achievement_id,count(*)::int AS n FROM user_achievements GROUP BY 1')}}


# ------------------------------------------------------------------ administrator
class SeasonIn(core.Model):
    name: str = Field(min_length=1, max_length=60)
    starts_on: date
    ends_on: date
    k_factor: int = Field(default=24, ge=4, le=64)
    start_rating: int = Field(default=1500, ge=100, le=3000)

    @model_validator(mode='after')
    def order(self):
        if self.ends_on < self.starts_on:
            raise ValueError('season_dates_invalid')
        return self


class AchievementIn(core.Model):
    code: str = Field(pattern='^[a-z0-9_]{2,40}$')
    title_ru: str = Field(min_length=1, max_length=60)
    title_en: str = Field(default='', max_length=60)
    description_ru: str = Field(default='', max_length=200)
    description_en: str = Field(default='', max_length=200)
    icon: str = Field(default='star', pattern='^[a-z-]{2,20}$')
    rule: str = Field(pattern='^(' + '|'.join(RULES) + ')$')
    threshold: int = Field(default=1, ge=1, le=1000)
    season_id: int | None = None
    active: bool = True
    position: int = Field(default=100, ge=0, le=10000)


def season_body(c, p, sid=None):
    clash = core.one(c, '''SELECT name FROM seasons WHERE daterange(starts_on,ends_on,'[]') && daterange(%s,%s,'[]')
    AND id IS DISTINCT FROM %s''', (p.starts_on, p.ends_on, sid))
    if clash:
        core.fail(409, 'season_overlap')


@core.app.get('/api/admin/seasons')
def admin_seasons(u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        rows = core.allrows(c, 'SELECT * FROM seasons ORDER BY starts_on DESC')
        return {'seasons': [public_season(s) | {'games': table(c, s)['games']} for s in rows], 'icons': ICONS, 'rules': RULES}


@core.app.post('/api/admin/seasons', status_code=201)
def create_season(p: SeasonIn, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        season_body(c, p)
        row = core.one(c, '''INSERT INTO seasons(name,starts_on,ends_on,k_factor,start_rating,created_by) VALUES(%s,%s,%s,%s,%s,%s)
        RETURNING *''', (p.name.strip(), p.starts_on, p.ends_on, p.k_factor, p.start_rating, u['id']))
        return public_season(row)


@core.app.put('/api/admin/seasons/{sid}')
def update_season(sid: int, p: SeasonIn, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        season_body(c, p, sid)
        row = core.one(c, '''UPDATE seasons SET name=%s,starts_on=%s,ends_on=%s,k_factor=%s,start_rating=%s WHERE id=%s RETURNING *''',
                       (p.name.strip(), p.starts_on, p.ends_on, p.k_factor, p.start_rating, sid))
        if not row:
            core.fail(404, 'season_not_found')
        return public_season(row)


@core.app.delete('/api/admin/seasons/{sid}')
def delete_season(sid: int, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        if core.one(c, 'SELECT 1 FROM achievements WHERE season_id=%s LIMIT 1', (sid,)):
            core.fail(409, 'season_in_use')
        if not core.one(c, 'DELETE FROM seasons WHERE id=%s RETURNING id', (sid,)):
            core.fail(404, 'season_not_found')
    return {'ok': True}


@core.app.get('/api/admin/achievements')
def admin_achievements(u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        return {'items': core.allrows(c, '''SELECT a.*,(SELECT count(*)::int FROM user_achievements x WHERE x.achievement_id=a.id) AS holders
        FROM achievements a ORDER BY a.position,a.id'''), 'icons': ICONS, 'rules': RULES}


def check_achievement(c, p):
    if p.icon not in ICONS:
        core.fail(422, 'achievement_icon_invalid')
    if p.season_id is not None and not core.one(c, 'SELECT 1 FROM seasons WHERE id=%s', (p.season_id,)):
        core.fail(422, 'season_not_found')


FIELDS = ('code', 'title_ru', 'title_en', 'description_ru', 'description_en', 'icon', 'rule', 'threshold', 'season_id', 'active', 'position')


@core.app.post('/api/admin/achievements', status_code=201)
def create_achievement(p: AchievementIn, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        check_achievement(c, p)
        try:
            return core.one(c, f'''INSERT INTO achievements({",".join(FIELDS)}) VALUES({",".join(["%s"] * len(FIELDS))}) RETURNING *''',
                            tuple(getattr(p, k) for k in FIELDS))
        except core.errors.UniqueViolation:
            core.fail(409, 'achievement_code_taken')


@core.app.put('/api/admin/achievements/{aid}')
def update_achievement(aid: int, p: AchievementIn, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        check_achievement(c, p)
        old = core.one(c, 'SELECT * FROM achievements WHERE id=%s', (aid,))
        if not old:
            core.fail(404, 'achievement_not_found')
        if old['builtin'] and (p.code != old['code'] or p.rule != old['rule']):
            core.fail(409, 'achievement_builtin')
        try:
            return core.one(c, f'''UPDATE achievements SET {",".join(k + "=%s" for k in FIELDS)} WHERE id=%s RETURNING *''',
                            tuple(getattr(p, k) for k in FIELDS) + (aid,))
        except core.errors.UniqueViolation:
            core.fail(409, 'achievement_code_taken')


@core.app.delete('/api/admin/achievements/{aid}')
def delete_achievement(aid: int, u=Depends(core.admin_user)):
    """Built-in achievements are switched off instead (they keep their code for future releases)."""
    with core.pool.connection() as c:
        old = core.one(c, 'SELECT builtin FROM achievements WHERE id=%s', (aid,))
        if not old:
            core.fail(404, 'achievement_not_found')
        if old['builtin']:
            core.fail(409, 'achievement_builtin')
        c.execute('DELETE FROM achievements WHERE id=%s', (aid,))
    return {'ok': True}


@core.app.post('/api/admin/achievements/recompute')
def recompute(u=Depends(core.admin_user)):
    """Grant achievements for results recorded earlier (no notifications)."""
    with core.pool.connection() as c:
        n = 0
        for r in core.allrows(c, 'SELECT id FROM users ORDER BY id'):
            n += len(award(c, r['id'], quiet=True))
    return {'awarded': n}
