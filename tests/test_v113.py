"""v1.13: conceding a match (10:0, confirmed by the opponent), local players (people without an account) in the club
rating, the operative count from the roster or the team (typed in only by choice), tooltips of game terms and weapon
rules (GET /api/reference/terms), the core rules without page numbers and change marks; migration 015."""
import json
import os
import pathlib
import re
import pytest
from api import teamdata as td

ROOT = pathlib.Path(__file__).resolve().parents[1]
read = lambda p: (ROOT / p).read_text(encoding='utf-8')


def db():
    import psycopg
    return psycopg.connect(os.environ['TEST_DATABASE_URL'])


def builder():
    from tests.test_v112 import builder as b
    return b()


# ------------------------------------------------------------------ tooltips: terms of the core rules
def test_terms_reference_the_core_rules():
    doc = json.loads(read('api/data/core-rules.json'))
    terms = doc['terms']
    ids = [x['id'] for x in terms]
    assert len(ids) == len(set(ids)) and len(ids) >= 60
    assert {x['kind'] for x in terms} == {'term', 'terrain', 'action', 'weapon'}
    assert {'control-range', 'obscured', 'valid-target', 'cover', 'visible', 'engage', 'conceal', 'heavy-terrain',
            'dash', 'charge', 'weapon-piercing-x', 'weapon-lethal-x', 'weapon-balanced', 'weapon-saturate'} <= set(ids)
    sections = {s['id']: s for c in doc['chapters'] for s in c['sections']}
    b = builder()
    quoted = set()  # the definable text of the document: paragraphs, list items, action effects and conditions
    for sec in sections.values():
        for u in b.section_units(sec):
            if 'action' in u:
                quoted |= {e['x'] for e in u['eff']} | {y['x'] for e in u['eff'] for y in e.get('sub', [])} | {c['x'] for c in u['cond']}
            else:
                quoted.add(b.tidy(u['x']))
    for x in terms:
        assert x['name'] and x['ru'] and re.search('[а-яё]', x['ru'], re.I), x['id']
        assert x['sec'] in sections and x['where'] and x['where_ru'], x['id']
        assert x['def'] and all(re.sub(r'^(?:- |\d+\) |▶ |◆ )', '', p) in quoted for p in x['def']), x['id']  # quoted, never retold
        assert x['alias'], x['id']
        for a in x['alias']:
            re.compile(a['re'])
            assert a['t'] in ('s', 'i', None) and a['w'] in ('i', None) and (a['t'] or a['w']), x['id']
    by = {x['id']: x for x in terms}

    def finds(tid, text, where):
        for a in by[tid]['alias']:
            flag = a['w'] if where == 'wr' else a['t']
            if flag and re.search(a['re'], text, re.I if flag == 'i' else 0): return True
        return False
    assert finds('control-range', 'It is within Control Range of an enemy', 'text')
    assert finds('obscured', 'the target is obscured', 'text') and finds('valid-target', 'select a valid target', 'text')
    assert finds('weapon-piercing-x', 'Piercing 1', 'wr') and finds('weapon-piercing-x', 'piercing 2', 'wr')
    assert finds('weapon-range-x', 'Range 6"', 'wr') and finds('weapon-blast-x', 'Blast 2"', 'wr')
    assert finds('weapon-lethal-x', 'Lethal 5+', 'wr') and not finds('weapon-lethal-x', 'a lethal blow', 'text')
    assert not finds('weapon-heavy', 'Heavy terrain', 'text') or finds('heavy-terrain', 'Heavy terrain', 'text')


def test_terms_endpoint(clients):
    from tests.test_integration import register
    a, b = clients
    assert b.get('/api/reference/terms').status_code == 401
    register(a, 'terms')
    r = a.get('/api/reference/terms')
    doc = json.loads(read('api/data/core-rules.json'))
    assert r.status_code == 200 and r.json() == {'version': doc['version'], 'terms': doc['terms']}
    assert r.headers['etag'] == f'"terms-{doc["version"]}"' and 'private' in r.headers['cache-control']
    assert a.get('/api/reference/terms', headers={'If-None-Match': r.headers['etag']}).status_code == 304
    assert len(r.content) < 120_000


def test_core_rules_without_pages_and_change_marks():
    doc = json.loads(read('api/data/core-rules.json'))
    assert doc['format'] == 2 and 'pages' not in json.dumps(doc.get('source', {}))
    text = json.dumps(doc, ensure_ascii=False)
    assert '"page"' not in text and '"upd"' not in text and '@upd' not in text
    for f in (ROOT / 'tools/core-rules/src').glob('*.md'):
        src = f.read_text(encoding='utf-8')
        assert '@upd' not in src and not re.search(r'^@section [^|\n]+\|[^|\n]+\|[^|\n]+\|', src, re.M), f.name
    hub = read('web/corerules.js')
    assert 'cr-updated' not in hub and 'pageRef' not in hub


# ------------------------------------------------------------------ operative count: roster, team, typed
def selection(*lines, extra=''):
    return [{'title': 'Operatives', 'body': [{'k': 'p', 't': '1 BOSS operative and the following:' + extra}]
             + [{'k': 'li', 't': x} for x in lines]}]


def test_team_size_needs_both_sources():
    from api.teams import composition, schema_size, selection_size
    from tests.test_rosters import schema
    s = schema()
    assert schema_size(s) == 3  # Operative min = max = 2, plus the leader
    assert selection_size(selection('1 BOSS operative', '2 TROOPER operatives')) == 3
    assert composition(selection('1 BOSS operative', '2 TROOPER operatives'), s) == (3, False)
    assert composition(selection('1 BOSS operative', '3 TROOPER operatives'), s) == (None, False)  # the sources disagree
    assert composition(selection('1 BOSS operative', '2 TROOPER operatives', extra=' a PET counts as two'), s) == (3, True)
    every = [{'body': [{'k': 'li', 't': '1 BOSS operative'}, {'k': 'li', 't': 'Every operative in the following list:'},
                       {'k': 'li2', 't': 'GUNNER'}, {'k': 'li2', 't': 'TROOPER'}]}]
    assert selection_size(every) == 3 and composition([], s) == (None, False) and composition(every, None) == (None, False)


def load_team(size_lines=('1 BOSS operative', '2 TROOPER operatives')):
    from tests.test_v19 import bundle
    b = bundle()
    b['teams'][0]['data']['selection'] = selection(*size_lines)
    with db() as c:
        td.load(b, c)


def test_operative_count_from_roster_team_or_typed(clients):
    from tests.test_integration import register, op, post
    from tests.test_quickstart import approved_ids, ver
    from tests.test_v19 import roster_data
    a, _ = clients
    register(a, 'counter')
    load_team()
    t = next(x for x in a.get('/api/teams').json()['teams'] if x['slug'] == 'angels-of-death')
    assert t['team_size'] == 3 and t['team_size_varies'] is False
    _, ids = approved_ids(a)
    mid = post(a, '/matches', op(kind='hotseat', guest_name='Гость'))['id']
    base = dict(mission_id=ids['mission'], killzone_id=ids['zone'], team1_id=ids['team'], team2_id=ids['team'],
                tac_op_id=ids['tac'], primary_op='crit')
    player = lambda slot: a.get('/api/matches/' + mid).json()['players'][slot - 1]
    setup = lambda **kw: a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), **base, **kw))
    # No roster: the team's composition, whatever was typed (the box shows the number, «Change» types it in).
    assert setup(operative_count=9).status_code == 200
    assert (player(1)['operative_count'], player(1)['operative_source']) == (3, 'team')
    assert setup(operative_count=9, operative_manual=True).status_code == 200
    assert (player(1)['operative_count'], player(1)['operative_source']) == (9, 'manual')
    assert setup(operative_manual=True).status_code == 200  # nothing typed: back to the team
    assert (player(1)['operative_count'], player(1)['operative_source']) == (3, 'team')
    # A roster wins over the team; its count follows the roster until the start.
    rid = post(a, '/rosters', op(team_slug='angels-of-death', name='Alpha', data=roster_data()))['id']
    with db() as c:
        c.execute("UPDATE rosters SET summary=jsonb_set(summary,'{operatives}','4') WHERE id=%s", (rid,))
    assert setup(roster_id=rid, operative_count=9).status_code == 200
    assert (player(1)['operative_count'], player(1)['operative_source']) == (4, 'roster')
    # The guest slot (hot-seat): the same rules on /player-setup.
    r = a.put(f'/api/matches/{mid}/player-setup', json=op(version=ver(a, mid), slot=2, tac_op_id=ids['tac'], primary_op='kill'))
    assert r.status_code == 200, r.text
    assert (player(2)['operative_count'], player(2)['operative_source']) == (3, 'team')
    audit = [x for x in a.get(f'/api/matches/{mid}/audit').json() if x['action'] == 'setup'][0]  # the latest first
    assert audit['after_data']['operative_source'] == 'roster' and audit['after_data']['operatives'] == 4
    r = a.put(f'/api/matches/{mid}/player-setup', json=op(version=ver(a, mid), slot=2, tac_op_id=ids['tac'], primary_op='kill',
                                                           operative_count=6, operative_manual=True))
    assert r.status_code == 200 and (player(2)['operative_count'], player(2)['operative_source']) == (6, 'manual')
    with db() as c:  # the roster is edited before the start (the kill thresholds need 5..14 operatives)
        c.execute("UPDATE rosters SET summary=jsonb_set(summary,'{operatives}','5') WHERE id=%s", (rid,))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='start'))
    assert (player(1)['operative_count'], player(1)['operative_source']) == (5, 'roster')
    assert (player(2)['operative_count'], player(2)['operative_source']) == (6, 'manual')
    # A team without an agreed size: typed in, or nothing.
    load_team(('1 BOSS operative', '5 TROOPER operatives'))
    assert next(x for x in a.get('/api/teams').json()['teams'] if x['slug'] == 'angels-of-death')['team_size'] is None
    mid = post(a, '/matches', op(kind='hotseat', guest_name='Гость'))['id']
    assert setup(operative_count=6).status_code == 200
    assert (player(1)['operative_count'], player(1)['operative_source']) == (6, 'manual')
    assert setup().status_code == 200
    assert (player(1)['operative_count'], player(1)['operative_source']) == (None, None)


# ------------------------------------------------------------------ conceding
def test_concede_friend_match_needs_the_opponent(clients):
    from tests.test_integration import op, post, ready_match
    from tests.test_quickstart import ver
    a, b = clients
    ua, ub, mid, cats = ready_match(a, b)
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=1, source_id=cats['source'][0], delta=5))
    assert post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='concede')) == {'status': 'awaiting_confirmation'}
    m = a.get('/api/matches/' + mid).json()
    assert m['conceded_slot'] == 1 and m['submitted_by'] == ua['id'] and [p['vp'] for p in m['players']] == [0, 10]
    r = a.post(f'/api/matches/{mid}/actions', json=op(version=ver(a, mid), action='confirm'))
    assert r.status_code == 409  # the player who conceded cannot confirm it
    assert a.post(f'/api/matches/{mid}/actions', json=op(version=ver(a, mid), action='concede')).status_code == 409
    # Disputed and reopened: the match goes on without the concession.
    post(b, f'/matches/{mid}/actions', op(version=ver(b, mid), action='dispute'))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='reopen'))
    m = a.get('/api/matches/' + mid).json()
    assert m['status'] == 'active' and m['conceded_slot'] is None and [p['vp'] for p in m['players']] == [5, 0]
    # The opponent concedes this time; the other player confirms: 10:0 in the statistics and the rating.
    post(b, f'/matches/{mid}/actions', op(version=ver(b, mid), action='concede'))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='confirm'))
    m = a.get('/api/matches/' + mid).json()
    assert m['status'] == 'confirmed' and m['conceded_slot'] == 2 and [p['vp'] for p in m['players']] == [10, 0]
    s = a.get('/api/stats').json()['summary']
    assert (s['wins'], s['losses']) == (1, 0)
    assert b.get('/api/stats').json()['summary']['losses'] == 1
    assert [(p['display_name'], p['wins']) for p in a.get('/api/ratings').json()['players']] == [('alpha', 1), ('bravo', 0)]
    audit = a.get(f'/api/matches/{mid}/audit').json()
    assert [x['after_data'].get('conceded_slot') for x in audit if x['action'] == 'concede'] == [2, 1]


def test_concede_hotseat_for_either_player(clients):
    from tests.test_integration import op, post, register
    from tests.test_quickstart import ver
    from tests.test_v19 import hotseat_with_roster
    a, _ = clients
    register(a, 'hot')
    mid, ids, rid = hotseat_with_roster(a)
    assert post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='concede', slot=2)) == {'status': 'unconfirmed'}
    m = a.get('/api/matches/' + mid).json()
    assert m['conceded_slot'] == 2 and [p['vp'] for p in m['players']] == [10, 0]
    assert a.get('/api/stats').json()['summary']['wins'] == 1
    mid, *_ = hotseat_with_roster(a)
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='concede'))  # no slot: the device owner
    assert a.get('/api/matches/' + mid).json()['conceded_slot'] == 1
    assert a.get('/api/stats').json()['summary']['losses'] == 1
    assert a.post(f'/api/matches/{mid}/actions', json=op(version=ver(a, mid), action='concede', slot=3)).status_code == 422


# ------------------------------------------------------------------ local players and the club rating
def quick(c, name, vp_for, vp_against, local=True):
    from tests.test_integration import op, post
    from tests.test_quickstart import approved_ids
    _, ids = approved_ids(c)
    return post(c, '/quick-matches', op(guest_name=name, local=local, team1_id=ids['team'], team2_id=ids['team'],
                                         mission_id=ids['mission'], killzone_id=ids['zone'], vp_for=vp_for,
                                         vp_against=vp_against, played_at='2026-11-01T18:00:00+03:00'))['id']


def test_local_players_and_the_club_rating(clients, monkeypatch):
    from tests.test_integration import register, op, post, ready_match
    from tests.test_quickstart import ver
    a, b = clients
    ua, ub, mid, cats = ready_match(a, b)  # a friend match: alpha beats bravo
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=1, source_id=cats['source'][0], delta=3))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='finish'))
    post(b, f'/matches/{mid}/actions', op(version=ver(b, mid), action='confirm'))
    m1 = quick(a, 'Иван  Петров', 2, 10)
    m2 = quick(a, 'иван петров', 3, 12)
    m3 = quick(b, 'ИВАН ПЕТРОВ', 12, 3)  # the same person for every account (case, spaces, ё)
    quick(a, 'Разовый гость', 10, 0, local=False)
    lp = a.get('/api/local-players').json()['items']
    assert [(x['name'], x['matches']) for x in lp] == [('Иван Петров', 3)]
    with db() as c:
        rows = c.execute('SELECT m.id::text,p.local_player_id::text,p.display_name FROM match_players p JOIN matches m ON m.id=p.match_id '
                         'WHERE p.slot=2 AND m.id::text = ANY(%s) ORDER BY m.created_at', ([m1, m2, m3],)).fetchall()
    assert {r[1] for r in rows} == {lp[0]['id']} and {r[2] for r in rows} == {'Иван Петров'}
    quick(a, 'Пётр', 1, 0)
    assert {x['name'] for x in b.get('/api/local-players').json()['items']} == {'Иван Петров', 'Пётр'}
    quick(b, 'петр', 0, 1)  # ё = е: Пётр again
    assert [x['matches'] for x in a.get('/api/local-players').json()['items'] if x['name'] == 'Пётр'] == [2]
    # Friends: registered players only; the club: local players too (marked), the default stays «friends».
    f = a.get('/api/ratings').json()
    assert f['scope'] == 'friends' and f['games'] == 1 and {p['display_name'] for p in f['players']} == {'alpha', 'bravo'}
    r = a.get('/api/ratings?scope=all').json()
    assert r['scope'] == 'all' and r['games'] == 6 and r['start'] == 1500 and r['k'] == 32
    by = {p['display_name']: p for p in r['players']}
    assert set(by) == {'alpha', 'bravo', 'Иван Петров', 'Пётр'}
    assert by['Иван Петров']['local'] and by['Иван Петров']['public_id'] is None and by['Иван Петров']['games'] == 3
    assert (by['Иван Петров']['wins'], by['Иван Петров']['losses']) == (2, 1) and not by['alpha']['local']
    assert by['alpha']['me'] and [p['rank'] for p in r['players']] == [1, 2, 3, 4]
    assert a.get('/api/ratings?scope=world').status_code == 422
    # A hidden profile takes part but is not listed (except for its owner).
    with db() as c:
        c.execute('INSERT INTO user_profiles(user_id,hidden) VALUES(%s,true) ON CONFLICT(user_id) DO UPDATE SET hidden=true', (ub['id'],))
    assert 'bravo' not in {p['display_name'] for p in a.get('/api/ratings?scope=all').json()['players']}
    assert [p['me'] for p in b.get('/api/ratings?scope=all').json()['players'] if p['display_name'] == 'bravo'] == [True]
    # Hot-seat matches against a local player count once finished.
    mid = post(a, '/matches', op(kind='hotseat', guest_name='иван петров', local=True))['id']
    assert a.get('/api/matches/' + mid).json()['players'][1]['display_name'] == 'Иван Петров'
    assert a.get('/api/ratings?scope=all').json()['games'] == 6  # not started yet
    from tests.test_v19 import hotseat_with_roster
    mid, *_ = hotseat_with_roster(a)
    with db() as c:  # the same as a hot-seat match created with local=True (the setup helper names the guest «Гость»)
        c.execute('UPDATE match_players SET local_player_id=%s WHERE match_id=%s AND slot=2', (lp[0]['id'], mid))
    assert a.get('/api/ratings?scope=all').json()['games'] == 6  # active
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='concede', slot=2))
    r = a.get('/api/ratings?scope=all').json()
    assert r['games'] == 7 and [p['games'] for p in r['players'] if p['display_name'] == 'Иван Петров'] == [4]
    # Administrators: the list and deleting (the matches keep the name, but leave the rating).
    assert a.get('/api/admin/local-players').status_code == 403
    with db() as c:
        c.execute('UPDATE users SET is_admin=true WHERE id=%s', (ua['id'],))
    items = a.get('/api/admin/local-players').json()['items']
    ivan = next(x for x in items if x['name'] == 'Иван Петров')
    assert ivan['matches'] == 5 and ivan['created_by_name'] == 'alpha' and ivan['last_played']
    delete = lambda c: c.request('DELETE', '/api/admin/local-players/' + ivan['id'], json={})
    assert delete(a).json() == {'ok': True}
    assert delete(a).status_code == 404 and delete(b).status_code == 403
    assert 'Иван Петров' not in {p['display_name'] for p in a.get('/api/ratings?scope=all').json()['players']}
    assert a.get('/api/matches/' + m1).json()['players'][1]['display_name'] == 'Иван Петров'
    assert a.get('/api/ratings?scope=all').json()['games'] == 3  # the friend match and Пётр
    # Limits: a name is required; one account creates at most PER_USER players.
    from api import localplayers
    monkeypatch.setattr(localplayers, 'PER_USER', 1)
    from tests.test_quickstart import approved_ids
    _, ids = approved_ids(a)
    r = a.post('/api/quick-matches', json=op(guest_name='Новенький', local=True, team1_id=ids['team'], team2_id=ids['team'],
                                              mission_id=ids['mission'], killzone_id=ids['zone'], vp_for=1, vp_against=0,
                                              played_at='2026-11-01T18:00:00+03:00'))
    assert r.status_code == 429 and r.json()['detail'] == 'too_many_local_players'
    assert quick(a, 'пётр', 2, 2)  # an existing name is not a new player


# ------------------------------------------------------------------ migration 015 and the client
def test_migration_015():
    from api.main import MIGRATIONS
    assert '015_v113.sql' in MIGRATIONS
    sql = read('db/migrations/015_v113.sql')
    assert 'DROP ' not in sql.upper().replace('DROP NOT NULL', '')  # additive: a rollback of the code keeps working
    with db() as c:
        cols = {(r[0], r[1]) for r in c.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'")}
        assert {('matches', 'conceded_slot'), ('match_players', 'operative_source'), ('match_players', 'local_player_id'),
                ('local_players', 'name'), ('local_players', 'created_by')} <= cols
        idx = c.execute("SELECT indexdef FROM pg_indexes WHERE indexname='local_players_name'").fetchone()[0]
        assert 'UNIQUE' in idx and 'ks_fold' in idx
        assert c.execute("SELECT count(*) FROM schema_migrations WHERE version='015_v113.sql'").fetchone()[0] == 1


def test_client_wiring():
    board, app, admin = read('web/board.js'), read('web/app.js'), read('web/admin.js')
    assert 'concedePanel' in board and 'data-kind="concede"' in board and 'concededNote' in board
    assert '"ratings-scope"' in app and 'scope=' in app and 'localField()' in app
    assert '"admin-local-delete"' in admin and '/admin/local-players/' in admin
    assert 'list="local-players"' in read('web/localplayers.js')
    calc = read('web/attackcalc.js')
    assert 'GRENADES' in calc and 'Blast 2"' in calc and 'Piercing 1' in calc
    assert 'id="surrender"' in read('web/icons.svg')
    for lang in ('en', 'ru'):
        d = json.loads(read(f'web/i18n/{lang}.json'))
        for k in ('concede', 'concededText', 'ratings_all', 'ratingsAllHint', 'localPlayer', 'localBadge', 'ad_locals',
                  'ad_localDeleteConfirm', 'opCountTeam', 'opCountRoster', 'atkGrenades'):
            assert d.get(k), (lang, k)
