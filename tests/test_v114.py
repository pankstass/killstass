"""v1.14: the operative card of the roster (rules of the selected options), the menu groups (GET /api/nav-summary),
equipment (secret selection, reveal and 2CP at the start), command points of the Ready step, ploys on the board
(protocol, repeat warning, Command Re-roll, undo, statistics), the browser error log (POST /api/client-errors,
#admin) and Firefox/WebKit for the browser tests; migration 016."""
import copy
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


def prof(name, kind, *chars):
    return {'n': name, 't': kind, 'ti': 't-' + kind[:3].lower(), 'c': [[k, f'c{i}', v] for i, (k, v) in enumerate(chars)]}


PROFILES = {
    'pe-ammo': prof('1x Ammo Cache', 'Equipment', ('Equipment', 'Set up an Ammo Cache marker in your territory.')),
    'pa-resupply': prof('AMMO RESUPPLY 1AP', 'Unique Actions', ('Unique Action', 'Re-roll one of your attack dice.')),
    'pe-gren': prof('Explosive Grenades', 'Equipment', ('Equipment', 'Friendly operatives can use the grenades below.')),
    'pw-frag': prof('⌖ Frag grenade', 'Weapons', ('ATK', '4'), ('HIT', '4+'), ('DMG', '2/4'), ('WR', 'Range 6", Blast 2", Saturate')),
    'pw-krak': prof('⌖ Krak grenade', 'Weapons', ('ATK', '4'), ('HIT', '4+'), ('DMG', '4/5'), ('WR', 'Range 6", Piercing 1, Saturate')),
    'pe-mines': prof('1x Mines', 'Equipment', ('Equipment', 'Set up a Mines marker.')),
    'pe-wire': prof('1x Razor Wire', 'Equipment', ('Equipment', 'Razor wire is Exposed and Obstructing terrain.')),
    'pe-barr': prof('2x Light Barricades', 'Equipment', ('Equipment', 'Light terrain, except the feet.')),
    'pe-seal': prof('Purity Seals', 'Equipment', ('Equipment', 'Once per battle, re-roll a failed save.')),
    # v1.14 (Т2): rules of the operative and of an option, for the roster card
    'pr-lead': prof('Commander', 'Abilities', ('Ability', 'Friendly operatives within 3" gain 1APL.')),
    'pr-axe': prof('CLEAVE 1AP', 'Unique Actions', ('Unique Action', 'Inflict 2 damage on an enemy within control range.')),
}
EQUIPMENT_ROOT = {'k': 'eqref', 'id': 'eqref', 'n': 'Equipment Reference', 't': 'upgrade', 'ch': [
    {'k': 'g-uni', 'id': 'g-uni', 'n': 'Universal Equipment', 't': 'group', 'ch': [
        {'k': 'u-ammo', 'id': 'u-ammo', 'n': 'Ammo Cache', 't': 'upgrade', 'p': ['pe-ammo', 'pa-resupply']},
        {'k': 'u-gren', 'id': 'u-gren', 'n': 'Explosive Grenades', 't': 'upgrade', 'p': ['pe-gren', 'pw-frag', 'pw-krak']},
        {'k': 'u-mines', 'id': 'u-mines', 'n': 'Mines', 't': 'upgrade', 'p': ['pe-mines']},
        {'k': 'u-mines2', 'id': 'u-mines2', 'n': 'Mines', 't': 'upgrade', 'p': ['pe-mines']},  # listed twice: one option
        {'k': 'g-sub', 'id': 'g-sub', 'n': 'Barricades', 't': 'group', 'ch': [
            {'k': 'u-barr', 'id': 'u-barr', 'n': 'Light Barricades', 't': 'upgrade', 'p': ['pe-barr']}]},
        {'k': 'u-wire', 'id': 'u-wire', 'n': 'Razor Wire', 't': 'upgrade', 'p': ['pe-wire']}]},
    {'k': 'g-fac', 'id': 'g-fac', 'n': 'Faction Equipment', 't': 'group', 'ch': [
        {'k': 'f-seal', 'id': 'f-seal', 'n': 'Purity Seals', 't': 'upgrade', 'p': ['pe-seal']}]}]}
PLOYS = {'strategy_ploys': [{'name': 'Hold the Line', 'body': [{'k': 'p', 't': 'Friendly operatives are not obscured.'}]},
                            {'name': 'Advance', 'body': [{'k': 'p', 't': 'Add 1" to Move.'}]}],
         'firefight_ploys': [{'name': 'Quick Reflexes', 'body': [{'k': 'p', 't': 'Use after an enemy shoots.'}]}]}


def equipment_schema(rules=True):
    from tests.test_rosters import schema
    s = schema()
    s['profiles'].update(PROFILES)
    s['root'].append(copy.deepcopy(EQUIPMENT_ROOT))
    if rules:
        boss = next(n for n in s['root'] if n.get('k') == 'e-boss')
        boss['p'] = boss.get('p', []) + ['pr-lead']
        axe = next(c for g in boss['ch'] if g.get('t') == 'group' for c in g['ch'] if c['k'] == 'e-axe')
        axe['p'] = axe.get('p', []) + ['pr-axe']
    return s


def load(teams=None):
    """The test team (angels-of-death) with an equipment reference and ploys; optionally more teams."""
    from tests.test_v19 import bundle
    b = bundle()
    b['teams'][0]['roster'] = equipment_schema()
    b['teams'][0]['data'].update(copy.deepcopy(PLOYS))
    b['teams'] += teams or []
    with db() as c:
        td.load(b, c)
    from api import equipment
    equipment._UNIVERSAL.clear()
    return b


# ------------------------------------------------------------------ equipment options from the schema
def test_schema_items_groups_profiles_and_weapons():
    from api.equipment import schema_items
    items = schema_items(equipment_schema())
    assert [(i['key'], i['group']) for i in items] == [
        ('u:ammo-cache', 'universal'), ('u:explosive-grenades', 'universal'), ('u:mines', 'universal'),
        ('u:light-barricades', 'universal'), ('u:razor-wire', 'universal'), ('f:purity-seals', 'faction')]
    ammo = items[0]
    assert ammo['rules'] == [
        {'name': '1x Ammo Cache', 'type': 'equipment', 'text': 'Set up an Ammo Cache marker in your territory.'},
        {'name': 'AMMO RESUPPLY 1AP', 'type': 'action', 'text': 'Re-roll one of your attack dice.'}]
    gren = items[1]
    assert gren['weapons'] == [
        {'name': 'Frag grenade', 'type': 'ranged', 'atk': '4', 'hit': '4+', 'dmg': '2/4', 'wr': 'Range 6", Blast 2", Saturate'},
        {'name': 'Krak grenade', 'type': 'ranged', 'atk': '4', 'hit': '4+', 'dmg': '4/5', 'wr': 'Range 6", Piercing 1, Saturate'}]
    assert [r['type'] for r in gren['rules']] == ['equipment']
    assert schema_items(None) == [] and schema_items({'root': [{'n': 'Boss', 't': 'model'}]}) == []


def test_options_fall_back_to_another_schema_and_the_team_reference(clients):
    from api import equipment, main as core
    from tests.test_quickstart import approved_ids
    from tests.test_integration import register
    a, _ = clients
    register(a, 'eqopts')
    other = {'slug': 'kommandos', 'name': 'Kommandos', 'sources': {}, 'roster': None,
             'data': {'operatives': [{'name': 'Boy', 'stats': {'apl': '2'}}],
                      'equipment': [{'name': 'Choppas', 'body': [{'k': 'lore', 't': 'Big.'}, {'k': 'p', 't': '+1 Atk in melee.'}]},
                                    {'name': 'Bomb Squigs', 'body': [{'k': 'p', 't': 'A squig with a bomb.'}]}]}}
    load([other])
    data, ids = approved_ids(a)
    kommandos = next(r['id'] for r in data if r['kind'] == 'team' and r['code'].endswith('team-kommandos'))
    with core.pool.connection() as c:
        own = equipment.options(c, ids['team'])
        assert [i['key'] for i in own] == ['u:ammo-cache', 'u:explosive-grenades', 'u:mines', 'u:light-barricades',
                                           'u:razor-wire', 'f:purity-seals']
        fallback = equipment.options(c, kommandos)
        assert [i['key'] for i in fallback] == ['u:ammo-cache', 'u:explosive-grenades', 'u:mines', 'u:light-barricades',
                                                'u:razor-wire', 'f:choppas', 'f:bomb-squigs']
        assert fallback[5]['rules'] == [{'name': 'Choppas', 'type': 'equipment', 'text': '+1 Atk in melee.'}]  # no lore
        assert equipment.resolve(c, kommandos, ['f:choppas', 'u:mines'])[0]['name'] == 'Choppas'
        for keys, code in ((['u:mines', 'u:mines'], 'equipment_repeat'), (['u:nope'], 'equipment_unknown'),
                           (['u:mines', 'u:ammo-cache', 'u:razor-wire', 'f:choppas', 'f:bomb-squigs'], 'equipment_limit')):
            with pytest.raises(ValueError, match=code):
                equipment.resolve(c, kommandos, keys)


# ------------------------------------------------------------------ equipment: secret until the start, 2CP
def friend_setup(a, b):
    from tests.test_integration import op, post, register
    from tests.test_quickstart import approved_ids, ver
    ua, ub = register(a, 'alpha'), register(b, 'bravo')
    post(a, '/friends', {'public_id': ub['public_id']})
    post(b, '/friends/' + ua['public_id'], {'action': 'accept'})
    ch = post(a, '/challenges', op(public_id=ub['public_id']))
    mid = post(b, '/challenges/' + ch['id'], op(action='accepted'))['match_id']
    _, ids = approved_ids(a)
    base = dict(edition='2024', mission_id=ids['mission'], killzone_id=ids['zone'], team1_id=ids['team'],
                team2_id=ids['team'], operative_count=6, operative_manual=True, tac_op_id=ids['tac'], initiative=1)
    for c, prim in ((a, 'crit'), (b, 'kill')):
        r = c.put(f'/api/matches/{mid}/setup', json=op(version=ver(c, mid), primary_op=prim, **base))
        assert r.status_code == 200, r.text
    return ua, ub, mid, ids


def test_equipment_is_secret_until_the_start_then_2cp(clients):
    from tests.test_integration import op, post
    from tests.test_quickstart import ver
    a, b = clients
    load()
    ua, ub, mid, ids = friend_setup(a, b)
    put = lambda c, keys, **kw: c.put(f'/api/matches/{mid}/equipment', json=op(version=ver(c, mid), keys=keys, **kw))
    d = a.get(f'/api/matches/{mid}/equipment').json()
    assert d['slot'] == 1 and d['max'] == 4 and d['selected'] == [] and len(d['options']) == 6
    assert b.get(f'/api/matches/{mid}/equipment?slot=1').status_code == 403  # only own slots
    assert put(b, ['u:mines'], slot=1).status_code == 403
    secret = ['u:explosive-grenades', 'u:ammo-cache', 'f:purity-seals', 'u:razor-wire']
    assert put(a, secret).status_code == 200
    assert put(a, secret + ['u:mines']).status_code == 422  # at most four
    assert put(a, ['u:mines', 'u:mines']).json()['detail'] == 'equipment_repeat'
    assert put(a, ['u:what']).json()['detail'] == 'equipment_unknown'
    assert put(b, ['u:mines']).status_code == 200
    assert a.get(f'/api/matches/{mid}/equipment').json()['selected'] == secret
    # The opponent sees how many, never which ones — neither in the match nor in its audit.
    m = b.get('/api/matches/' + mid).json()
    assert [(p['slot'], p['equipment'], p['equipment_count']) for p in m['players']][0] == (1, [], 4)
    own = a.get('/api/matches/' + mid).json()['players'][0]
    assert [i['name'] for i in own['equipment']] == ['Explosive Grenades', 'Ammo Cache', 'Purity Seals', 'Razor Wire']
    audit = b.get(f'/api/matches/{mid}/audit').json()
    entries = [x for x in audit if x['action'] == 'equipment']
    assert {(x['after_data']['slot'], x['after_data']['count']) for x in entries} == {(1, 4), (2, 1)}
    assert 'Grenades' not in json.dumps(audit) and 'Purity' not in json.dumps(audit)
    # The start reveals both selections at once (as stored then) and gives each player 2CP.
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='start'))
    m = b.get('/api/matches/' + mid).json()
    assert [[i['key'] for i in p['equipment']] for p in m['players']] == [secret, ['u:mines']]
    gren = m['players'][0]['equipment'][0]
    assert [w['name'] for w in gren['weapons']] == ['Frag grenade', 'Krak grenade']
    assert sorted((s['turning_point'], s['cp']) for s in m['turn_states']) == [(1, 2), (1, 2)]
    assert m['cp_grants'] == [{'turning_point': 0, 'gains': {'1': 2, '2': 2}}]
    reveal = [x for x in b.get(f'/api/matches/{mid}/audit').json() if x['action'] == 'equipment_reveal'][0]
    assert reveal['after_data']['equipment'] == {'1': ['Explosive Grenades', 'Ammo Cache', 'Purity Seals', 'Razor Wire'],
                                                 '2': ['Mines']}
    assert put(a, ['u:mines']).json()['detail'] == 'equipment_closed'
    assert m['undo'] is None or m['undo']['action'] not in ('cp_start', 'equipment_reveal')  # the start itself is not undone


def test_equipment_and_cp_only_in_kill_team_2024(clients):
    from api import equipment, main as core
    from tests.test_integration import op, post
    from tests.test_quickstart import ver
    a, b = clients
    load()
    ua, _, mid, _ = friend_setup(a, b)
    edition = lambda e: db().__enter__().execute("UPDATE matches SET edition=%s,version=version+1 WHERE id=%s", (e, mid)).connection.commit()
    edition('2021')  # a Kill Team 2021 match (the rule depends on the edition only)
    r = a.put(f'/api/matches/{mid}/equipment', json=op(version=ver(a, mid), keys=['u:mines']))
    assert r.status_code == 422 and r.json()['detail'] == 'equipment_edition'
    with core.pool.connection() as c:
        equipment.on_start(c, {'edition': '2021', 'id': mid}, ua)  # nothing to reveal, no CP
        assert core.one(c, 'SELECT count(*)::int AS n FROM match_cp_grants WHERE match_id=%s', (mid,))['n'] == 0
    edition('2024')
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='start'))
    edition('2021')
    r = a.post(f'/api/matches/{mid}/cp', json=op(version=ver(a, mid), turning_point=1))
    assert r.status_code == 422 and r.json()['detail'] == 'cp_edition'


# ------------------------------------------------------------------ CP of the Ready step
def started_hotseat(a):
    from tests.test_integration import op, post
    from tests.test_quickstart import approved_ids, ver
    _, ids = approved_ids(a)
    mid = post(a, '/matches', op(kind='hotseat', guest_name='Гость'))['id']
    base = dict(mission_id=ids['mission'], killzone_id=ids['zone'], team1_id=ids['team'], team2_id=ids['team'],
                operative_count=6, operative_manual=True, tac_op_id=ids['tac'], primary_op='crit', initiative=1)
    assert a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), **base)).status_code == 200
    r = a.put(f'/api/matches/{mid}/player-setup', json=op(version=ver(a, mid), slot=2, operative_count=6,
                                                           operative_manual=True, tac_op_id=ids['tac'], primary_op='kill'))
    assert r.status_code == 200, r.text
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='start'))
    return mid


def cps(c, mid, tp):
    m = c.get('/api/matches/' + mid).json()
    ids = {p['id']: p['slot'] for p in m['players']}
    best = {}
    for s in sorted(m['turn_states'], key=lambda s: s['turning_point']):
        if s['turning_point'] <= tp:
            best[ids[s['player_id']]] = s['cp']
    return best.get(1, 0), best.get(2, 0)


def test_cp_per_turning_point_once_initiative_and_undo(clients):
    from tests.test_integration import op, post, register
    from tests.test_quickstart import ver
    a, _ = clients
    register(a, 'cpready')
    load()
    mid = started_hotseat(a)
    grant = lambda tp: a.post(f'/api/matches/{mid}/cp', json=op(version=ver(a, mid), turning_point=tp))
    assert cps(a, mid, 1) == (2, 2)
    assert grant(2).json()['detail'] == 'cp_closed'  # only the current turning point
    assert grant(1).json() == {'ok': True, 'gains': {'1': 1, '2': 1}}
    assert cps(a, mid, 1) == (3, 3)
    assert grant(1).json()['detail'] == 'cp_granted'  # once per turning point
    # TP2: the player without initiative gains 2CP — only once the initiative is known.
    for slot in (1, 2):
        post(a, f'/matches/{mid}/primary', op(version=ver(a, mid), primary_op='crit', slot=slot))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='turn', turning_point=2))
    assert grant(2).json()['detail'] == 'initiative_required'
    post(a, f'/matches/{mid}/initiative', op(version=ver(a, mid), turning_point=2, slot=2))
    assert grant(2).json()['gains'] == {'2': 1, '1': 2}
    assert cps(a, mid, 2) == (5, 4)
    # A changed initiative moves the extra CP; undo puts it back.
    post(a, f'/matches/{mid}/initiative', op(version=ver(a, mid), turning_point=2, slot=1))
    assert cps(a, mid, 2) == (4, 5)
    m = a.get('/api/matches/' + mid).json()
    assert {g['turning_point']: g['gains'] for g in m['cp_grants']}[2] == {'1': 1, '2': 2}
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    assert cps(a, mid, 2) == (5, 4)
    m = a.get('/api/matches/' + mid).json()
    assert m['undo']['action'] == 'initiative' or m['undo']['action'] == 'cp_grant'
    # Undo of the grant itself: back to the CP before it, the step can be taken again.
    while m['undo'] and m['undo']['action'] != 'cp_grant':
        post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
        m = a.get('/api/matches/' + mid).json()
    post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
    assert cps(a, mid, 2) == (3, 3) and 2 not in {g['turning_point'] for g in a.get('/api/matches/' + mid).json()['cp_grants']}


# ------------------------------------------------------------------ ploys
def test_ploys_protocol_repeat_reroll_undo_and_stats(clients):
    from tests.test_integration import op, post, register
    from tests.test_quickstart import ver
    a, b = clients
    register(a, 'ployer')
    load()
    mid = started_hotseat(a)
    use = lambda name, kind='strategy', **kw: a.post(f'/api/matches/{mid}/ploys',
                                                     json=op(version=ver(a, mid), kind=kind, name=name, **kw))
    r = use('Hold the Line').json()
    assert r['ok'] and r['cp'] == 1 and isinstance(r['id'], int)
    assert cps(a, mid, 1) == (1, 2)
    r = use('Hold the Line')
    assert r.status_code == 409 and r.json()['detail'] == 'ploy_repeat'
    assert use('Hold the Line', repeat=True).json()['cp'] == 0
    assert use('Command Re-roll', 'firefight').json()['detail'] == 'cp_insufficient'
    assert use('Command Re-roll', 'firefight', slot=2).status_code == 200  # the guest's CP (hot-seat)
    assert use('Command Re-roll', 'firefight', slot=2).status_code == 200  # Command Re-roll repeats freely
    assert use('Quick Reflexes', 'strategy').json()['detail'] == 'ploy_unknown'  # a firefight ploy
    assert use('Command Re-roll', 'strategy').json()['detail'] == 'ploy_unknown'
    assert use('Not a ploy', 'firefight').json()['detail'] == 'ploy_unknown'
    assert use('Quick Reflexes', 'firefight', slot=2, cost=0).json()['cp'] == 0
    m = a.get('/api/matches/' + mid).json()
    assert [(y['slot'], y['name'], y['kind'], y['cost'], y['turning_point']) for y in m['ploys']] == [
        (1, 'Hold the Line', 'strategy', 1, 1), (1, 'Hold the Line', 'strategy', 1, 1),
        (2, 'Command Re-roll', 'firefight', 1, 1), (2, 'Command Re-roll', 'firefight', 1, 1),
        (2, 'Quick Reflexes', 'firefight', 0, 1)]
    assert cps(a, mid, 1) == (0, 0)
    # «Undo last» removes the ploy and gives the CP back (the zero-cost one first).
    for expect in ((0, 0), (0, 1)):
        m = a.get('/api/matches/' + mid).json()
        assert m['undo']['action'] == 'ploy'
        post(a, f'/matches/{mid}/undo', op(audit_id=m['undo']['id']))
        assert cps(a, mid, 1) == expect
    assert len(a.get('/api/matches/' + mid).json()['ploys']) == 3
    audit = [x for x in a.get(f'/api/matches/{mid}/audit').json() if x['action'] == 'ploy']
    assert audit[0]['after_data']['name'] == 'Hold the Line' or audit[-1]['after_data']['name'] == 'Hold the Line'
    # Statistics count the ploys of confirmed matches (a hot-seat concession ends the match at once).
    assert a.get('/api/stats/ploys').json() == []
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='concede', slot=2))
    rows = a.get('/api/stats/ploys').json()
    assert rows == [{'name': 'Hold the Line', 'kind': 'strategy', 'uses': 2, 'games': 1, 'cp': 2}]
    assert use('Advance').json()['detail'] == 'ploy_closed'
    assert b.get('/api/stats/ploys').status_code == 401


# ------------------------------------------------------------------ the roster card (Т2)
def test_roster_sheet_lists_the_rules_of_the_selected_options(clients):
    from tests.test_integration import op, post, register
    from tests.test_rosters import Ids, sel, roster
    from api import rosterkit as rk
    a, _ = clients
    register(a, 'carder')
    b = load()
    e = rk.Engine(b['teams'][0]['roster'])
    axe = sel(e, 'Boss', Ids())
    assert [k['key'] for k in axe['sel']] == ['e-axe', 'l-pistol::e-pistol']  # the default melee weapon
    sword = copy.deepcopy(axe)
    sword['sel'][0]['key'] = 'e-sword'
    sheet = lambda boss: a.get('/api/rosters/' + post(a, '/rosters', op(team_slug='angels-of-death', name='Card',
                                                                        data=roster(boss)))['id'] + '/sheet').json()['operatives']
    ops = sheet(axe)
    assert [o['name'] for o in ops] == ['Boss']
    # the model's own rules, then those of the selected option (an axe brings its unique action, a sword nothing)
    assert [(x['name'], x['type'], x['text']) for x in ops[0]['abilities']] == [
        ('Commander', '', 'Friendly operatives within 3" gain 1APL.')]
    assert [x['name'] for x in ops[0]['actions']] == ['CLEAVE 1AP']
    assert [x['name'] for x in sheet(sword)[0]['actions']] == []
    assert ops[0]['keywords'] == ['LEADER']


# ------------------------------------------------------------------ menu groups
def test_nav_summary_counts_what_waits_for_the_player(clients):
    from tests.test_integration import op, post, register
    a, b = clients
    assert b.get('/api/nav-summary').status_code == 401
    ua, ub = register(a, 'navone'), register(b, 'navtwo')
    s = a.get('/api/nav-summary').json()
    assert set(s) == {'history', 'stats', 'friends', 'nights', 'tournaments', 'rosters', 'maps'}
    assert s['friends'] == {'friends': 0, 'challenges': 0, 'requests': 0} and s['history']['to_confirm'] == 0
    post(b, '/friends', {'public_id': ua['public_id']})
    assert a.get('/api/nav-summary').json()['friends']['requests'] == 1
    post(a, '/friends/' + ub['public_id'], {'action': 'accept'})
    post(b, '/challenges', op(public_id=ua['public_id']))
    s = a.get('/api/nav-summary').json()
    assert s['friends'] == {'friends': 1, 'challenges': 1, 'requests': 0}


def test_sections_table_and_routes():
    sections, app = read('web/sections.js'), read('web/app.js')
    groups = re.findall(r'id: "([a-z]+)"', sections[:sections.index('export const SECTIONS')])
    assert groups[:6] == ['overview', 'muster', 'results', 'club', 'rules', 'profile']
    routes = set(re.findall(r'^\s{2}"?([a-z]+)"?:', app[app.index('const ROUTES'):app.index('};', app.index('const ROUTES'))], re.M))
    items = {x for grp in re.findall(r'items: \[([^\]]*)\]', sections) for x in re.findall(r'"([a-z]+)"', grp)}
    assert items == {'rosters', 'maps', 'history', 'stats', 'friends', 'nights', 'tournaments', 'reference', 'core', 'teams'}
    assert (items | {'muster', 'results', 'club', 'rules', 'overview', 'profile'}) <= routes
    for lang in ('en', 'ru'):
        d = json.loads(read(f'web/i18n/{lang}.json'))
        for k in ('muster', 'results', 'club', 'rules', 'grp_musterHint', 'grp_resultsHint', 'grp_clubHint', 'navAttention'):
            assert d.get(k), (lang, k)


# ------------------------------------------------------------------ browser error log
def test_client_errors_scrubbed_deduplicated_and_for_admins(clients):
    from tests.test_integration import op, post, register
    a, b = clients
    report = {'kind': 'error', 'message': 'TypeError: x is undefined at https://ks.test/app.js?v=1#frag',
              'source': 'https://ks.test/web/board.js?token=abc', 'page': 'match', 'version': '1.14.0',
              'stack': 'at draw (https://ks.test/web/board.js?x=1:10:5)\n reset code ' + 'Q' * 40}
    assert b.post('/api/client-errors', json=report).status_code == 202  # anonymous: the sign-in page counts too
    assert b.post('/api/client-errors', json=report).status_code == 202
    assert b.post('/api/client-errors', json={**report, 'page': 'Match/1'}).status_code == 422
    assert b.post('/api/client-errors', json={'message': 'x' * 3000}).status_code == 422
    assert b.post('/api/client-errors', content=b'{"message":"' + b'x' * 17000 + b'"}',
                  headers={'Content-Type': 'application/json'}).status_code == 413
    register(a, 'erradmin')
    assert a.get('/api/admin/client-errors').status_code == 403
    with db() as c:
        c.execute("UPDATE users SET is_admin=true WHERE login='erradmin'")
        rows = c.execute('SELECT message,source,stack,count,user_id FROM client_errors').fetchall()
    assert len(rows) == 1
    message, source, stack, count, uid = rows[0]
    assert message == 'TypeError: x is undefined at https://ks.test/app.js' and source == 'https://ks.test/web/board.js'
    assert '?x=1' not in stack and 'Q' * 32 not in stack and '…' in stack and count == 2 and uid is None
    post(a, '/client-errors', {'kind': 'rejection', 'message': 'Error: failed', 'page': 'overview', 'version': '1.14.0'})
    d = a.get('/api/admin/client-errors').json()
    assert d['keep_days'] == 30 and d['total'] == {'n': 2, 'events': 3}
    assert [(x['kind'], x['count'], x['login']) for x in d['items']] == [('rejection', 1, 'erradmin'), ('error', 2, None)]
    assert a.get('/api/admin/overview').json()['counts']['client_errors_week'] == 3
    assert post(a, '/admin/client-errors/clear', op()) == {'ok': True, 'deleted': 2}
    assert a.get('/api/admin/client-errors').json()['items'] == []


def test_client_errors_are_rate_limited(clients):
    from api import clienterrors
    _, b = clients
    codes = [b.post('/api/client-errors', json={'message': f'Error {i}', 'page': 'overview'}).status_code
             for i in range(clienterrors.PER_WINDOW + 1)]
    assert codes[:-1] == [202] * clienterrors.PER_WINDOW and codes[-1] == 429


# ------------------------------------------------------------------ migration 016 and the client
def test_migration_016():
    from api.main import MIGRATIONS
    assert '016_v114.sql' in MIGRATIONS
    sql = read('db/migrations/016_v114.sql')
    assert 'DROP ' not in sql.upper()  # additive: a rollback of the code keeps working
    with db() as c:
        cols = {(r[0], r[1]) for r in c.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'")}
        assert {('match_players', 'equipment'), ('match_cp_grants', 'gains'), ('match_ploys', 'name'), ('match_ploys', 'cost'),
                ('client_errors', 'fingerprint'), ('client_errors', 'count')} <= cols
        assert c.execute("SELECT count(*) FROM schema_migrations WHERE version='016_v114.sql'").fetchone()[0] == 1
        grants = {r[0] for r in c.execute("""SELECT privilege_type FROM information_schema.role_table_grants
            WHERE table_name='client_errors' AND grantee='killstass_app'""")}
        assert not grants or {'SELECT', 'INSERT', 'UPDATE', 'DELETE'} <= grants


def test_client_wiring():
    main, board, attack = read('web/main.js'), read('web/board.js'), read('web/attack.js')
    assert 'initErrors' in main and 'initEquipment' in main and 'initPloys' in main
    calls = main[main.index('initErrors,'):]
    assert calls.index('initErrors') < calls.index('initEquipment')  # the error log listens before anything else
    assert 'equipmentBox' in board and '"ploys-open"' in board and 'cpGrantRow' in read('web/turns.js')
    assert 'equipmentWeapons' in attack and '[ge]:' in attack
    errors = read('web/errors.js')
    assert '/api/client-errors' in errors and 'keepalive' in errors and 'unhandledrejection' in errors
    assert '"admin-err-clear"' in read('web/admin.js') and '/admin/client-errors' in read('web/admin.js')
    assert 'id="alert"' in read('web/icons.svg') and 'id="pack"' in read('web/icons.svg')
    helpers, docker = read('tests/e2e/helpers.mjs'), read('scripts/e2e-docker.sh')
    assert 'E2E_BROWSER' in helpers and 'firefox' in helpers and 'webkit' in helpers
    assert 'E2E_BROWSERS' in docker and '-e E2E_BROWSER=' in docker
    en, ru = (json.loads(read(f'web/i18n/{x}.json')) for x in ('en', 'ru'))
    assert set(en) == set(ru) and set(en['errors']) == set(ru['errors'])
    for k in ('equipment', 'equipHint', 'equipCount', 'equipSave', 'cpGrant', 'cpReady', 'ploys', 'ployRepeatConfirm',
              'ployLog', 'ployStats', 'ad_errors', 'ad_errorsHint', 'ad_errClear', 'ad_errorsWeek'):
        assert en.get(k) and ru.get(k), k
    for code in ('equipment_limit', 'equipment_repeat', 'equipment_unknown', 'equipment_closed', 'equipment_edition',
                 'cp_granted', 'cp_closed', 'cp_edition', 'initiative_required', 'ploy_repeat', 'ploy_unknown',
                 'ploy_closed', 'cp_insufficient'):
        assert en['errors'].get(code) and ru['errors'].get(code), code
