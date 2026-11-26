"""v1.9: single version source, operative tracker with automatic kills, undo, opponent roster,
BattleScribe/New Recruit import, statistics additions, Elo among friends, LAN tournaments, admin API."""
import base64
import io
import json
import os
import pathlib
import re
import zipfile
import pytest
from api import rosterkit as rk
from api import teamdata as td

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()


# ------------------------------------------------------------------ static: one version everywhere
def test_version_has_one_source():
    assert re.fullmatch(r'\d+\.\d+\.\d+', VERSION)
    index = (ROOT / 'web/index.html').read_text()
    assert index.count('{{VERSION}}') == 4 and '?v=' not in index and 'type="module"' in index
    for f in (ROOT / 'web').glob('*.js'):
        text = f.read_text()
        assert not re.search(r'\?v=|["\'`]\d+\.\d+\.\d+["\'`]', text), f.name
    for f in (ROOT / 'web/i18n').glob('*.json'):
        assert 'appVersion' not in json.loads(f.read_text()), f.name
    assert json.loads((ROOT / 'package.json').read_text())['version'] == VERSION
    assert json.loads((ROOT / 'docs/openapi.json').read_text())['info']['version'] == VERSION
    assert 'COPY VERSION /app/VERSION' in (ROOT / 'api/Dockerfile').read_text()
    assert 'COPY . /work' in (ROOT / 'tests/Dockerfile').read_text()  # v1.10: the whole project, VERSION included
    assert (ROOT / 'UPDATE-INFO.md').read_text().startswith(f'# KILLSTASS v{VERSION} ')
    assert (ROOT / 'README.md').read_text().startswith(f'# KILLSTASS {VERSION}\n')


def test_migrations_listed_in_api():
    files = sorted(p.name for p in (ROOT / 'db/migrations').glob('*.sql'))
    text = (ROOT / 'api/main.py').read_text()
    listed = re.findall(r"'(\d{3}_[a-z0-9_]+\.sql)'", text[text.index('MIGRATIONS'):text.index('MIGRATIONS') + 800])
    assert listed == files


def test_update_runs_smoke_checks_before_restart():
    update = (ROOT / 'scripts/update.sh').read_text()
    smoke = (ROOT / 'scripts/smoke.sh').read_text()
    assert update.index('smoke.sh --pre') < update.index('docker compose stop proxy api')
    assert update.index('smoke.sh --post') > update.rindex('up -d --wait')
    assert 'caddy validate' in smoke and '/api/health' in smoke and 'schema_migrations' in smoke and 'VERSION' in smoke
    caddy = (ROOT / 'proxy/Caddyfile').read_text()
    assert '?Cache-Control "no-store"' in caddy and 'header @versioned' not in caddy
    assert '@rosterimport path /api/rosters/import' in caddy
    imp = caddy.index('request_body @rosterimport {')
    assert 'max_size 1MB' in caddy[imp:caddy.index('}', imp)]


# ------------------------------------------------------------------ pure helpers
def test_swiss_avoids_rematches_and_gives_one_bye():
    from api.tournaments import swiss, round_robin, standings
    pairs = swiss([1, 2, 3, 4, 5], {frozenset((1, 2))}, {5})
    flat = [x for p in pairs for x in p if x]
    assert sorted(flat) == [1, 2, 3, 4, 5] and (1, 2) not in pairs and pairs[-1] == (4, None)
    assert swiss([1, 2], {frozenset((1, 2))}, set()) == [(1, 2)]  # unavoidable rematch
    games = set()
    for rnd in range(1, 6):
        for a, b in round_robin([1, 2, 3, 4, 5, 6], rnd):
            assert b is not None and frozenset((a, b)) not in games
            games.add(frozenset((a, b)))
    assert len(games) == 15
    byes = [p for rnd in range(1, 4) for p in round_robin([1, 2, 3], rnd) if p[1] is None]
    assert sorted(b[0] for b in byes) == [1, 2, 3]
    players = {1: {'seed': 1}, 2: {'seed': 2}, 3: {'seed': 3}}
    table = standings(players, [{'player1_id': 1, 'player2_id': 2, 'vp1': 10, 'vp2': 12},
                                {'player1_id': 3, 'player2_id': None, 'vp1': None, 'vp2': None}])
    assert [r['player_id'] for r in table] == [2, 3, 1] and table[0]['points'] == 3 and table[1]['byes'] == 1


# ------------------------------------------------------------------ API
def bundle():
    from tests.test_rosters import schema
    return {'format': td.FORMAT, 'teams': [
        {'slug': 'angels-of-death', 'name': 'Angels of Death', 'sources': {}, 'roster': schema(),
         'data': {'operatives': [{'name': 'Boss', 'stats': {'apl': '3', 'move': '6"', 'save': '4+', 'wounds': '12'},
                                  'weapons': [{'name': 'Bolt pistol', 'type': 'ranged', 'atk': '4', 'hit': '3+', 'dmg': '3/4', 'wr': 'Range 8"'}]},
                                 {'name': 'Trooper', 'stats': {'apl': '2', 'move': '6"', 'save': '4+', 'wounds': '3'}}]}}]}


def roster_data():
    from tests.test_rosters import Ids, sel, roster
    e = rk.Engine(bundle()['teams'][0]['roster'])
    uid = Ids()
    return roster(sel(e, 'Boss', uid), sel(e, 'Trooper', uid), sel(e, 'Trooper', uid))


def hotseat_with_roster(a, operative_count=5):
    import psycopg
    from tests.test_integration import op, post
    from tests.test_quickstart import approved_ids, ver
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        td.load(bundle(), c)
    rid = post(a, '/rosters', op(team_slug='angels-of-death', name='Alpha', data=roster_data()))['id']
    _, ids = approved_ids(a)
    mid = post(a, '/matches', op(kind='hotseat', guest_name='Гость'))['id']
    base = dict(mission_id=ids['mission'], killzone_id=ids['zone'], team1_id=ids['team'], team2_id=ids['team'],
                operative_count=5, operative_manual=True, tac_op_id=ids['tac'], primary_op='crit')
    r = a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), roster_id=rid, **base))
    assert r.status_code == 200, r.text
    r = a.put(f'/api/matches/{mid}/player-setup', json=op(version=ver(a, mid), slot=2, operative_count=operative_count, tac_op_id=ids['tac'], primary_op='kill'))
    assert r.status_code == 200, r.text
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='start'))
    return mid, ids, rid


def tracker(c, mid, **kw):
    from tests.test_integration import op
    return c.post(f'/api/matches/{mid}/operatives', json=op(**kw))


def test_health_index_and_versioned_static(clients):
    a, _ = clients
    h = a.get('/api/health').json()
    assert h == {'status': 'ok', 'version': VERSION, 'migrations': len(list((ROOT / 'db/migrations').glob('*.sql')))}
    page = a.get('/')
    assert page.status_code == 200 and f'content="{VERSION}"' in page.text and '{{' not in page.text
    assert a.get('/', headers={'If-None-Match': page.headers['etag']}).status_code == 304
    assert a.get(f'/static/v/{VERSION}/main.js').status_code == 200
    assert a.get(f'/static/v/{VERSION}/i18n/ru.json').json()['login']
    assert a.get('/static/v/0.0.1/main.js').status_code == 404
    assert a.get('/api/openapi.json').json()['info']['version'] == VERSION


def test_tracker_kills_undo_and_roster(clients):
    from tests.test_integration import register, op, post
    from tests.test_quickstart import ver
    a, b = clients
    register(a, 'tracker')
    mid, ids, rid = hotseat_with_roster(a)
    m = a.get('/api/matches/' + mid).json()
    ops = [o for o in m['operatives'] if o['slot'] == 1]
    assert [o['name'] for o in ops] == ['Boss', 'Trooper 1', 'Trooper 2']
    assert ops[0]['wounds'] == ops[0]['wounds_max'] == 12 and ops[0]['stats']['save'] == '4+' and ops[0]['card'] == 'Boss'
    assert [w['name'] for w in ops[0]['weapons']] == ['Pistol'] and ops[1]['wounds_max'] == 3  # stats from the datacard
    assert m['tracker_seq'] == 0 and m['undo'] is None
    assert tracker(a, mid, action='populate').json()['detail'] == 'tracker_not_empty'
    assert tracker(a, mid, action='populate', slot=2).json()['detail'] == 'roster_required'
    assert tracker(a, mid, action='add', slot=2, card='Nobody').json()['detail'] == 'card_unknown'
    g1 = tracker(a, mid, action='add', slot=2, card='Trooper').json()['ids'][0]
    g2 = tracker(a, mid, action='add', slot=2, name='Pet', wounds_max=2).json()['ids'][0]
    g3 = tracker(a, mid, action='add', slot=2, name='Spare').json()['ids'][0]
    extra = [tracker(a, mid, action='add', slot=2, name=f'Extra {i}').json()['ids'][0] for i in (1, 2, 3)]
    version = ver(a, mid)
    # 3 wounds: incapacitated in TP 1, so slot 1 (the opponent) incapacitated one enemy operative.
    r = tracker(a, mid, action='wounds', operative_id=g1, delta=-5); assert r.status_code == 200, r.text
    m = a.get('/api/matches/' + mid).json()
    assert m['version'] == version and m['tracker_seq'] > 0  # tracker taps never bump matches.version
    victim = next(o for o in m['operatives'] if o['id'] == g1)
    assert victim['wounds'] == 0 and victim['incapacitated_tp'] == 1 and m['players'][0]['incapacitated'] == 1
    assert m['undo']['action'] == 'operative' and m['undo']['name'] == 'Trooper' and m['undo']['wounds'] == [3, 0]
    r = a.post(f'/api/matches/{mid}/kills', json=op(version=version, turning_point=1, delta=1))
    assert r.status_code == 409 and r.json()['detail'] == 'kills_tracked'
    for x in [g2] + extra:
        assert tracker(a, mid, action='wounds', operative_id=x, delta=-2).status_code == 200
    r = tracker(a, mid, action='wounds', operative_id=g3, delta=-1)  # sixth kill > operative_count 5
    assert r.status_code == 422 and r.json()['detail'] == 'kills_out_of_range'
    assert tracker(a, mid, action='order', operative_id=ops[0]['id'], order='engage').json()['changed']
    assert tracker(a, mid, action='activate', operative_id=ops[0]['id'], activated=True).json()['changed']
    assert not tracker(a, mid, action='activate', operative_id=ops[0]['id'], activated=True).json()['changed']
    boss = next(o for o in a.get('/api/matches/' + mid).json()['operatives'] if o['id'] == ops[0]['id'])
    assert boss['order_token'] == 'engage' and boss['activated_tp'] == 1
    # revive: the kill goes away again
    tracker(a, mid, action='wounds', operative_id=g1, delta=1)
    assert a.get('/api/matches/' + mid).json()['players'][0]['incapacitated'] == 4
    # undo the revive, then a stale undo id is refused
    m = a.get('/api/matches/' + mid).json()
    assert m['undo']['wounds'] == [0, 1]
    assert a.post(f'/api/matches/{mid}/undo', json=op(audit_id=m['undo']['id'] - 1)).json()['detail'] == 'undo_conflict'
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    m = a.get('/api/matches/' + mid).json()
    assert next(o for o in m['operatives'] if o['id'] == g1)['wounds'] == 0 and m['players'][0]['incapacitated'] == 5
    assert m['undo']['action'] == 'operative' and m['undo']['change'] == 'activate'
    # turn, initiative, score and CP undo (newest first)
    post(a, f'/matches/{mid}/primary', op(version=ver(a, mid), primary_op='crit'))
    post(a, f'/matches/{mid}/primary', op(version=ver(a, mid), primary_op='kill', slot=2))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='turn', turning_point=2))
    post(a, f'/matches/{mid}/initiative', op(version=ver(a, mid), turning_point=2, slot=2))
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=2, source_id=ids['crit'], delta=1))
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=2, cp=3))
    m = a.get('/api/matches/' + mid).json()
    assert m['undo']['action'] == 'score' and m['undo']['cp'] == [0, 3]
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    m = a.get('/api/matches/' + mid).json()
    assert m['undo']['vp'] == [0, 1] and not any(s['cp'] for s in m['turn_states'] if s['turning_point'] == 2)
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    m = a.get('/api/matches/' + mid).json()
    assert m['players'][0]['crit'] == 0 and m['undo']['action'] == 'initiative'
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    m = a.get('/api/matches/' + mid).json()
    assert not [i for i in m['initiatives'] if i['turning_point'] == 2] and m['undo']['turn'] == [1, 2]
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    assert a.get('/api/matches/' + mid).json()['current_turn'] == 1
    # remove an incapacitated operative: its kill is taken away; undo restores both
    tracker(a, mid, action='remove', operative_id=g2)
    m = a.get('/api/matches/' + mid).json()
    assert m['players'][0]['incapacitated'] == 4 and g2 not in [o['id'] for o in m['operatives']]
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    m = a.get('/api/matches/' + mid).json()
    assert m['players'][0]['incapacitated'] == 5 and next(o for o in m['operatives'] if o['id'] == g2)['incapacitated_tp'] == 1
    # the player's roster as played
    r = a.get(f'/api/matches/{mid}/players/1/roster').json()
    assert r['team_slug'] == 'angels-of-death' and r['roster_name'] == 'Alpha' and [o['name'] for o in r['operatives']][:1] == ['Boss']
    assert b.get(f'/api/matches/{mid}/players/1/roster').status_code == 401
    register(b, 'outsider')
    assert b.get(f'/api/matches/{mid}/players/1/roster').status_code == 404
    assert tracker(b, mid, action='wounds', operative_id=g1, delta=1).status_code == 404


def test_tracker_permissions_in_friend_match(clients):
    from tests.test_integration import ready_match
    a, b = clients
    ua, ub, mid, cats = ready_match(a, b)
    mine = tracker(a, mid, action='add', name='Alpha one', wounds_max=7).json()['ids'][0]
    theirs = tracker(b, mid, action='add', name='Bravo one', wounds_max=8).json()['ids'][0]
    assert tracker(b, mid, action='add', slot=1, name='Sneaky').json()['detail'] == 'slot_forbidden'
    assert tracker(b, mid, action='wounds', operative_id=mine, delta=-1).json()['detail'] == 'slot_forbidden'
    assert tracker(b, mid, action='wounds', operative_id=theirs, delta=-8).status_code == 200
    m = a.get('/api/matches/' + mid).json()
    assert {o['name']: o['wounds'] for o in m['operatives']} == {'Alpha one': 7, 'Bravo one': 0}
    assert m['players'][0]['incapacitated'] == 0  # legacy scoring: no automatic Kill Op
    assert a.get('/api/matches/' + mid).json()['undo'] is None or a.get('/api/matches/' + mid).json()['undo']['name'] == 'Alpha one'
    assert b.get('/api/matches/' + mid).json()['undo']['name'] == 'Bravo one'
    assert a.get(f'/api/matches/{mid}/players/2/roster').status_code == 200


def test_opponent_roster_hidden_until_start(clients):
    from tests.test_integration import op, post, register
    a, b = clients
    ua, ub = register(a, 'alpha'), register(b, 'bravo')
    post(a, '/friends', {'public_id': ub['public_id']})
    post(b, '/friends/' + ua['public_id'], {'action': 'accept'})
    ch = post(a, '/challenges', op(public_id=ub['public_id']))
    mid = post(b, '/challenges/' + ch['id'], op(action='accepted'))['match_id']
    assert a.get('/api/matches/' + mid).json()['status'] == 'setup'
    hidden = b.get(f'/api/matches/{mid}/players/1/roster')
    assert hidden.status_code == 403 and hidden.json()['detail'] == 'roster_hidden'
    assert a.get(f'/api/matches/{mid}/players/2/roster').json()['detail'] == 'roster_hidden'
    assert a.get(f'/api/matches/{mid}/players/1/roster').status_code == 200
    assert b.get(f'/api/matches/{mid}/players/2/roster').status_code == 200

def test_roster_import_ros_rosz_and_guards(clients):
    import psycopg
    from tests.test_integration import register, op, post
    a, _ = clients
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        td.load(bundle(), c)
    register(a, 'importer')
    schema, data = bundle()['teams'][0]['roster'], roster_data()
    xml = rk.to_ros(schema, data, 'Imported', 'r-1')
    def imp(raw, filename='x.ros', **kw):
        return a.post('/api/rosters/import', json=op(filename=filename, data_b64=base64.b64encode(raw).decode(), **kw))
    r = imp(xml.encode()); assert r.status_code == 201, r.text
    j = r.json()
    assert j['team_slug'] == 'angels-of-death' and j['name'] == 'Imported' and j['skipped'] == [] and j['valid'] and j['operatives'] == 3
    got = a.get('/api/rosters/' + j['id']).json()['data']['selections']
    keys = lambda items: [(i['key'], i['n'], keys(i.get('sel', []))) for i in items]
    assert keys(got) == keys(data['selections'])
    rosz = rk.to_rosz(schema, data, 'Zipped', 'r-2', 'z.ros')
    assert imp(rosz, 'z.rosz', name='Из архива').json()['name'] == 'Из архива'
    # unknown entries are skipped and reported; ids fall back to the last segment and to names
    odd = xml.replace('entryId="e-trooper"', 'entryId="zzz::e-trooper"', 1).replace('entryId="e-boss"', 'entryId="nope"').replace('name="Pistol"', 'name="Pistol"', 1)
    odd = odd.replace('<selections>', '<selections><selection id="q" name="Ghost" entryId="ghost" number="1" type="model"/>', 1)
    j = imp(odd.encode()).json()
    assert j['skipped'] == ['Ghost'] and j['operatives'] == 3
    bad = xml.replace('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "y">]>')
    assert imp(bad.encode()).json()['detail'] == 'import_invalid'
    assert imp(b'not xml at all').json()['detail'] == 'import_invalid'
    assert imp(b'<catalogue xmlns="x"/>').json()['detail'] == 'import_not_roster'
    other = xml.replace('catalogueId="cat-1"', 'catalogueId="other"').replace('catalogueName="Testers"', 'catalogueName="Other"')
    assert imp(other.encode()).json()['detail'] == 'import_team_unknown'
    assert imp(other.encode(), team_slug='angels-of-death').status_code == 201
    assert imp(b'x' * (720 * 1024)).json()['detail'] == 'import_too_large'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('big.ros', b' ' * (5 * 1024 * 1024))
    assert imp(buf.getvalue(), 'big.rosz').json()['detail'] == 'import_too_large'
    r = a.post('/api/rosters/import', content=b'{' + b' ' * (1024 * 1024 + 10) + b'}', headers={'Content-Type': 'application/json'})
    assert r.status_code == 413
    r = a.post('/api/rosters', content=b'{' + b' ' * (300 * 1024) + b'}', headers={'Content-Type': 'application/json'})
    assert r.status_code == 413


def test_stats_rosters_clock_and_ratings(clients):
    import psycopg
    from tests.test_integration import register, op, post, ready_match
    from tests.test_quickstart import ver
    a, b = clients
    ua, ub, mid, cats = ready_match(a, b)
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=1, source_id=cats['source'][0], delta=3))
    post(a, f'/matches/{mid}/clock', op(action='configure', mode='chess'))
    post(a, f'/matches/{mid}/clock', op(action='start', slot=1))
    post(a, f'/matches/{mid}/clock', op(action='switch', slot=1))
    post(a, f'/matches/{mid}/clock', op(action='pause'))
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:  # pretend the turns took 10 and 5 minutes
        ids = [r[0] for r in c.execute('SELECT id FROM match_clock_events WHERE match_id=%s ORDER BY id', (mid,)).fetchall()]
        c.execute("UPDATE match_clock_events SET server_ts=now()-interval '15 minutes' WHERE id=%s", (ids[1],))
        c.execute("UPDATE match_clock_events SET server_ts=now()-interval '5 minutes' WHERE id=%s", (ids[2],))
        c.execute("UPDATE match_clock_events SET server_ts=now() WHERE id=%s", (ids[3],))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='finish'))
    post(b, f'/matches/{mid}/actions', op(version=ver(b, mid), action='confirm'))
    s = a.get('/api/stats').json()
    assert s['summary']['wins'] == 1 and s['breakdown']['roster_id'] == []
    k = s['clock']
    assert k['games'] == 1 and k['split_games'] == 1 and 890 <= k['avg_total_seconds'] <= 910
    assert 590 <= k['avg_own_seconds'] <= 610 and 290 <= k['avg_opponent_seconds'] <= 310
    r = a.get('/api/ratings').json()
    assert r['games'] == 1 and [(p['display_name'], p['rating'], p['wins']) for p in r['players']] == [('alpha', 1516, 1), ('bravo', 1484, 0)]
    assert b.get('/api/ratings').json()['players'][1]['me']


def test_stats_by_roster(clients):
    from tests.test_integration import register, op, post
    from tests.test_quickstart import ver
    a, _ = clients
    register(a, 'rosterstats')
    mid, ids, rid = hotseat_with_roster(a)
    post(a, f'/matches/{mid}/primary', op(version=ver(a, mid), primary_op='crit'))
    post(a, f'/matches/{mid}/primary', op(version=ver(a, mid), primary_op='kill', slot=2))
    for tp in (2, 3, 4):
        post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='turn', turning_point=tp))
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=4, source_id=ids['crit'], delta=2))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='finish'))
    rows = a.get('/api/stats').json()['breakdown']['roster_id']
    assert [(r['key'], r['label'], r['games'], r['wins']) for r in rows] == [(rid, 'Alpha', 1, 1)]


def test_tournaments_swiss_league_results_and_matches(clients):
    from tests.test_integration import register, op, post
    a, b = clients
    ua, ub = register(a, 'organizer'), register(b, 'friendly')
    players = [{'public_id': ua['public_id']}, {'public_id': ub['public_id']}, {'name': 'Гость 1'}, {'name': 'Гость 2'}]
    assert a.post('/api/tournaments', json=op(name='Cup', format='swiss', players=players)).json()['detail'] == 'tournament_friend_required'
    post(a, '/friends', {'public_id': ub['public_id']}); post(b, '/friends/' + ua['public_id'], {'action': 'accept'})
    tid = post(a, '/tournaments', op(name='Cup', format='swiss', players=players))['id']
    t = a.get(f'/api/tournaments/{tid}').json()
    assert t['rounds'] == 2 and t['status'] == 'draft' and t['is_owner'] and [p['name'] for p in t['players']] == ['organizer', 'friendly', 'Гость 1', 'Гость 2']
    tb = b.get(f'/api/tournaments/{tid}').json()
    assert not tb['is_owner'] and tb['my_player_id'] == t['players'][1]['id'] and [x['name'] for x in b.get('/api/tournaments').json()] == ['Cup']
    assert b.post(f'/api/tournaments/{tid}/actions', json=op(version=t['version'], action='start')).json()['detail'] == 'tournament_owner_only'
    post(a, f'/tournaments/{tid}/actions', op(version=t['version'], action='start'))
    t = a.get(f'/api/tournaments/{tid}').json()
    r1 = [x for x in t['pairings'] if x['round'] == 1]
    assert len(r1) == 2 and sorted(p for x in r1 for p in (x['player1_id'], x['player2_id'])) == sorted(p['id'] for p in t['players'])
    assert a.post(f'/api/tournaments/{tid}/actions', json=op(version=t['version'], action='next_round')).json()['detail'] == 'tournament_round_open'
    ids = {p['name']: p['id'] for p in t['players']}
    for x in r1:
        if ids['friendly'] in (x['player1_id'], x['player2_id']):
            # a participant reports their own game; the other pairing is reported by the organizer
            first = x['player1_id'] == ids['friendly']
            post(b, f"/tournaments/{tid}/pairings/{x['id']}/result", op(vp1=15 if first else 9, vp2=9 if first else 15))
        else:
            post(a, f"/tournaments/{tid}/pairings/{x['id']}/result", op(vp1=12, vp2=12))
    t = a.get(f'/api/tournaments/{tid}').json()
    assert t['standings'][0]['player_id'] == ids['friendly'] and t['standings'][0]['points'] == 3
    post(a, f'/tournaments/{tid}/actions', op(version=t['version'], action='next_round'))
    t = a.get(f'/api/tournaments/{tid}').json()
    r2 = [x for x in t['pairings'] if x['round'] == 2]
    first = {frozenset((x['player1_id'], x['player2_id'])) for x in r1}
    assert len(r2) == 2 and not first & {frozenset((x['player1_id'], x['player2_id'])) for x in r2}
    # a participant opens the pairing's match (friend match with both seated, or hot-seat vs the guest)
    mine = next(x for x in r2 if ids['organizer'] in (x['player1_id'], x['player2_id']))
    mid = post(a, f"/tournaments/{tid}/pairings/{mine['id']}/match", op())['id']
    m = a.get('/api/matches/' + mid).json()
    assert m['status'] == 'setup' and m['setup']['tournament_id'] == tid
    assert a.post(f"/api/tournaments/{tid}/pairings/{mine['id']}/match", json=op()).json()['detail'] == 'pairing_has_match'
    other = next(x for x in r2 if x is not mine)
    if ids['friendly'] not in (other['player1_id'], other['player2_id']):
        assert a.post(f"/api/tournaments/{tid}/pairings/{other['id']}/match", json=op()).json()['detail'] == 'pairing_not_player'
    for x in r2:
        post(a, f"/tournaments/{tid}/pairings/{x['id']}/result", op(vp1=10, vp2=8))
    t = a.get(f'/api/tournaments/{tid}').json()
    assert a.post(f'/api/tournaments/{tid}/actions', json=op(version=t['version'], action='next_round')).json()['detail'] == 'tournament_state'
    post(a, f'/tournaments/{tid}/actions', op(version=t['version'], action='finish'))
    t = a.get(f'/api/tournaments/{tid}').json()
    assert t['status'] == 'finished' and sum(r['played'] for r in t['standings']) == 8
    # league with an odd number: everybody gets one bye, everybody meets everybody
    lid = post(a, '/tournaments', op(name='League', format='league', players=[{'name': n} for n in 'ABC']))['id']
    t = a.get(f'/api/tournaments/{lid}').json(); assert t['rounds'] == 3
    post(a, f'/tournaments/{lid}/actions', op(version=t['version'], action='start'))
    for rnd in (1, 2, 3):
        t = a.get(f'/api/tournaments/{lid}').json()
        for x in t['pairings']:
            if x['round'] == rnd and x['player2_id']:
                post(a, f"/tournaments/{lid}/pairings/{x['id']}/result", op(vp1=5, vp2=3))
        t = a.get(f'/api/tournaments/{lid}').json()
        post(a, f'/tournaments/{lid}/actions', op(version=t['version'], action='next_round' if rnd < 3 else 'finish'))
    t = a.get(f'/api/tournaments/{lid}').json()
    assert all(r['played'] == 2 and r['byes'] == 1 for r in t['standings'])
    assert b.get(f'/api/tournaments/{lid}').status_code == 404
    assert a.request('DELETE', f'/api/tournaments/{lid}', json={}).json()['ok']


def test_admin_api_and_flag_protection(clients):
    import psycopg
    from tests.test_integration import register, op, post
    a, b = clients
    ua = register(a, 'operator'); register(b, 'player')
    post(b, '/feedback', {'message': 'Кнопка не работает', 'page': 'match'})
    assert a.get('/api/admin/overview').json()['detail'] == 'admin_only'
    assert a.get('/api/auth/me').json()['is_admin'] is False
    with psycopg.connect(os.environ['DATABASE_URL']) as c:  # runtime role: no privilege on the flag
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('UPDATE users SET is_admin=true WHERE id=%s', (ua['id'],))
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        c.execute('UPDATE users SET is_admin=true WHERE id=%s', (ua['id'],))
    o = a.get('/api/admin/overview').json()
    assert o['version'] == VERSION and o['counts']['users'] == 2 and o['counts']['feedback_open'] == 1 and o['migrations']
    f = a.get('/api/admin/feedback').json()
    assert f['total'] == 1 and f['items'][0]['login'] == 'player' and f['items'][0]['message'] == 'Кнопка не работает'
    post(a, f"/admin/feedback/{f['items'][0]['id']}", op(handled=True))
    assert a.get('/api/admin/feedback').json()['total'] == 0 and a.get('/api/admin/feedback?status=all').json()['total'] == 1
    assert [u['login'] for u in a.get('/api/admin/users?q=play').json()['items']] == ['player']
    assert b.get('/api/admin/users').status_code == 403
