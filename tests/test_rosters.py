"""v1.8: roster builder — BattleScribe schema compiler, validation engine, exports (.ros checked against the
official BattleScribe XSD) and the private roster API linked to match setup."""
import io, json, os, pathlib, zipfile
import xml.etree.ElementTree as ET
import pytest
from api import teamdata as td
from api import rosterkit as rk

FIX = pathlib.Path(__file__).parent / 'fixtures'
GST = '''<gameSystem id="gs-1" name="Kill Team (2024)" revision="9" xmlns="http://www.battlescribe.net/schema/gameSystemSchema">
 <categoryEntries><categoryEntry id="cat-op" name="Operative"/><categoryEntry id="cat-lead" name="Leader"/></categoryEntries>
 <sharedSelectionEntries><selectionEntry id="eq-ammo" name="Ammo Cache" type="upgrade"/></sharedSelectionEntries>
</gameSystem>'''
MINMAX = lambda i, lo, hi: (f'<constraints><constraint id="{i}-min" type="min" value="{lo}" field="selections" scope="parent"/>'
                            f'<constraint id="{i}-max" type="max" value="{hi}" field="selections" scope="parent"/></constraints>')
CAT = f'''<catalogue id="cat-1" name="Testers" revision="3" gameSystemId="gs-1" xmlns="http://www.battlescribe.net/schema/catalogueSchema">
 <categoryEntries><categoryEntry id="cat-gun" name="Gunner"/></categoryEntries>
 <forceEntries><forceEntry id="force-1" name="Testers Kill Team"><categoryLinks>
  <categoryLink id="cl-op" targetId="cat-op" name="Operative">
   <constraints><constraint id="op-min" type="min" value="2" field="selections" scope="force"/><constraint id="op-max" type="max" value="2" field="selections" scope="force"/></constraints>
   <modifiers><modifier type="increment" field="op-max" value="1"><conditions><condition type="atLeast" value="1" field="selections" scope="force" childId="e-pet"/></conditions></modifier></modifiers>
  </categoryLink>
  <categoryLink id="cl-lead" targetId="cat-lead" name="Leader"><constraints><constraint id="ld-min" type="min" value="1" field="selections" scope="force"/><constraint id="ld-max" type="max" value="1" field="selections" scope="force"/></constraints></categoryLink>
  <categoryLink id="cl-gun" targetId="cat-gun" name="Gunner"><constraints><constraint id="gn-max" type="max" value="1" field="selections" scope="force"/></constraints></categoryLink>
 </categoryLinks></forceEntry></forceEntries>
 <selectionEntries>
  <selectionEntry id="e-boss" name="Boss" type="model">
   <categoryLinks><categoryLink id="x1" targetId="cat-lead" primary="true"/></categoryLinks>
   <profiles><profile id="p-boss" name="Boss" typeId="t-op" typeName="Operative"><characteristics><characteristic name="APL" typeId="c1">3</characteristic><characteristic name="Move" typeId="c2">6"</characteristic><characteristic name="Save" typeId="c3">4+</characteristic><characteristic name="Wounds" typeId="c4">12</characteristic></characteristics></profile></profiles>
   <rules><rule id="r-boss" name="Bossy"><description>Leads &amp; shouts.</description></rule></rules>
   <selectionEntryGroups><selectionEntryGroup id="g-melee" name="Melee Weapon" defaultSelectionEntryId="e-axe">{MINMAX("gm", 1, 1)}
    <selectionEntries><selectionEntry id="e-sword" name="Sword" type="upgrade"/><selectionEntry id="e-axe" name="Axe" type="upgrade"/></selectionEntries>
   </selectionEntryGroup></selectionEntryGroups>
   <entryLinks><entryLink id="l-pistol" targetId="e-pistol" name="Pistol" type="selectionEntry">{MINMAX("lp", 1, 1)}</entryLink></entryLinks>
  </selectionEntry>
  <selectionEntry id="e-trooper" name="Trooper" type="model">
   <categoryLinks><categoryLink id="x2" targetId="cat-op" primary="true"/></categoryLinks>
   <entryLinks><entryLink id="l-pistol2" targetId="e-pistol" type="selectionEntry">{MINMAX("lq", 1, 1)}</entryLink></entryLinks>
  </selectionEntry>
  <selectionEntry id="e-gunner" name="Gunner" type="model"><categoryLinks><categoryLink id="x3" targetId="cat-op"/><categoryLink id="x4" targetId="cat-gun"/></categoryLinks></selectionEntry>
  <selectionEntry id="e-pet" name="Pet" type="model" hidden="true">
   <categoryLinks><categoryLink id="x5" targetId="cat-op"/></categoryLinks>
   <modifiers><modifier type="set" field="hidden" value="false"><conditions><condition type="atLeast" value="1" field="selections" scope="force" childId="e-boss"/></conditions></modifier></modifiers>
  </selectionEntry>
 </selectionEntries>
 <entryLinks><entryLink id="l-eq" targetId="eq-ammo" name="Ammo Cache" type="selectionEntry"><constraints><constraint id="eq-max" type="max" value="1" field="selections" scope="roster"/></constraints></entryLink></entryLinks>
 <sharedSelectionEntries><selectionEntry id="e-pistol" name="Pistol" type="upgrade"><profiles><profile id="p-pistol" name="Pistol" typeId="t-w" typeName="Weapons"><characteristics><characteristic name="ATK" typeId="w1">4</characteristic><characteristic name="WR" typeId="w2">Range 8"</characteristic></characteristics></profile></profiles></selectionEntry></sharedSelectionEntries>
</catalogue>'''

def schema():
    return td.bs_parse(CAT, ET.fromstring(GST))['roster']

class Ids:
    def __init__(self): self.n = 0
    def __call__(self): self.n += 1; return f'u{self.n:06d}'

def sel(e, name, uid, n=1, kids=None, custom=None):
    node = next(x for x, _ in e.options(None).values() if x['n'] == name)
    out = {'uid': uid(), 'key': node['k'], 'n': n, 'sel': e.defaults(node, uid) if kids is None else kids}
    if custom: out['name'] = custom
    return out

def roster(*items, notes=''):
    return {'format': rk.FORMAT, 'selections': list(items), 'notes': notes}

def codes(r): return sorted(i['code'] for i in r['errors'])

def test_compiler_keys_links_and_constraints():
    s = schema()
    assert s['cat'] == {'id': 'cat-1', 'n': 'Testers', 'rev': '3'} and s['gs']['id'] == 'gs-1' and s['force']['id'] == 'force-1'
    assert [n['k'] for n in s['root']] == ['e-boss', 'e-trooper', 'e-gunner', 'e-pet', 'l-eq::eq-ammo']
    boss = s['root'][0]
    assert [(c['t'], c['k']) for c in boss['ch']] == [('group', 'g-melee'), ('upgrade', 'l-pistol::e-pistol')]
    assert boss['ch'][0]['def'] == 'e-axe' and [c['k'] for c in boss['ch'][0]['ch']] == ['e-sword', 'e-axe']
    assert boss['pc'] == 'cat-lead' and s['rules'][boss['r'][0]]['d'] == 'Leads & shouts.'
    assert s['root'][1]['ch'][0]['k'] == 'l-pistol2::e-pistol' and s['root'][3]['h'] == 1
    assert [c['n'] for c in s['force']['cats']] == ['Operative', 'Leader', 'Gunner'] and s['cats']['cat-gun'] == 'Gunner'

def test_defaults_and_valid_roster():
    e = rk.Engine(schema()); uid = Ids()
    boss = sel(e, 'Boss', uid)
    assert [k['key'] for k in boss['sel']] == ['e-axe', 'l-pistol::e-pistol']  # group default + mandatory link
    r = e.validate(roster(boss, sel(e, 'Trooper', uid), sel(e, 'Trooper', uid)))
    assert r['valid'] and r['operatives'] == 3 and not r['warnings']
    assert r['limits'] == [{'name': 'Operative', 'count': 2, 'min': 2, 'max': 2}, {'name': 'Leader', 'count': 1, 'min': 1, 'max': 1},
                           {'name': 'Gunner', 'count': 0, 'max': 1}]

def test_constraints_modifiers_and_issues():
    e = rk.Engine(schema()); uid = Ids()
    t = lambda: sel(e, 'Trooper', uid)
    r = e.validate(roster(sel(e, 'Boss', uid), t(), t(), sel(e, 'Gunner', uid)))
    assert codes(r) == ['category_max'] and r['errors'][0]['params'] == {'name': 'Operative', 'count': 3, 'max': 2}
    r = e.validate(roster(sel(e, 'Boss', uid), t(), sel(e, 'Gunner', uid), sel(e, 'Pet', uid)))  # pet: +1 operative, visible with a boss
    assert r['valid'] and r['limits'][0] == {'name': 'Operative', 'count': 3, 'min': 2, 'max': 3}
    r = e.validate(roster(t(), sel(e, 'Pet', uid)))
    assert codes(r) == ['category_min'] and [w['code'] for w in r['warnings']] == ['hidden']
    boss = sel(e, 'Boss', uid, kids=[{'uid': uid(), 'key': 'e-sword', 'n': 1}, {'uid': uid(), 'key': 'e-axe', 'n': 1}])
    r = e.validate(roster(boss, t(), t()))
    assert codes(r) == ['max', 'min'] and {i['uid'] for i in r['errors']} == {boss['uid']}
    assert {i['params']['name'] for i in r['errors']} == {'Melee Weapon', 'Pistol'}
    ammo = lambda: sel(e, 'Ammo Cache', uid)
    r = e.validate(roster(sel(e, 'Boss', uid), t(), t(), ammo(), ammo()))
    assert codes(r) == ['max'] and r['errors'][0]['params']['name'] == 'Ammo Cache' and r['operatives'] == 3
    r = e.validate(roster(sel(e, 'Boss', uid), t(), t(), {'uid': uid(), 'key': 'gone::entry', 'n': 1}))
    assert codes(r) == ['unknown_entry']

@pytest.mark.parametrize('bad,code', [
    ({'format': 'other/1', 'selections': []}, 'roster_format'),
    ({'selections': [{'uid': 'BAD', 'key': 'e-boss', 'n': 1}]}, 'roster_bad_uid'),
    ({'selections': [{'uid': 'aaaaaa', 'key': 'e-boss'}, {'uid': 'aaaaaa', 'key': 'e-boss'}]}, 'roster_bad_uid'),
    ({'selections': [{'uid': 'aaaaaa', 'key': 'e-boss', 'n': 0}]}, 'roster_bad_number'),
    ({'selections': [{'uid': 'aaaaaa', 'key': 'x' * 301}]}, 'roster_bad_key'),
    ({'selections': [{'uid': f'u{i:06d}', 'key': 'e-trooper'} for i in range(501)]}, 'roster_too_large'),
    ({'selections': 'nope'}, 'roster_invalid'),
])
def test_malformed_documents_are_rejected(bad, code):
    with pytest.raises(rk.RosterError) as e: rk.Engine(schema()).validate(bad)
    assert str(e.value) == code

def test_depth_limit():
    item = {'uid': 'd000000', 'key': 'e-boss'}
    for i in range(1, 10): item = {'uid': f'd{i:06d}', 'key': 'e-boss', 'sel': [item]}
    with pytest.raises(rk.RosterError, match='roster_too_deep'): rk.Engine(schema()).validate({'selections': [item]})

def test_exports_text_ros_rosz():
    s = schema(); e = rk.Engine(s); uid = Ids()
    data = roster(sel(e, 'Boss', uid, custom='Big <Boss>'), sel(e, 'Trooper', uid), sel(e, 'Trooper', uid), sel(e, 'Ammo Cache', uid), notes='Plan & notes')
    text = rk.to_text(s, data, 'Testers', 'Alpha')
    assert text.splitlines()[:3] == ['Testers — Alpha (3)', '1. Big <Boss> (Boss): Axe, Pistol', '2. Trooper: Pistol'] and text.endswith('Plan & notes')
    xml = rk.to_ros(s, data, 'Alpha & co', 'roster-1')
    from lxml import etree
    xsd = etree.XMLSchema(etree.parse(str(FIX / 'BattleScribe-roster-2.03.xsd')))
    doc = etree.fromstring(xml.encode())
    assert xsd.validate(doc), xsd.error_log
    ns = {'r': 'http://www.battlescribe.net/schema/rosterSchema'}
    assert doc.get('gameSystemId') == 'gs-1' and doc.get('name') == 'Alpha & co'
    f = doc.find('r:forces/r:force', ns); assert f.get('entryId') == 'force-1' and f.get('catalogueId') == 'cat-1'
    boss = f.find('r:selections/r:selection', ns)
    assert boss.get('customName') == 'Big <Boss>' and boss.get('type') == 'model'
    kids = boss.findall('r:selections/r:selection', ns)
    assert [(k.get('entryId'), k.get('entryGroupId')) for k in kids] == [('e-axe', 'g-melee'), ('l-pistol::e-pistol', None)]
    assert boss.find('r:categories/r:category[@primary="true"]', ns).get('entryId') == 'cat-lead'
    assert rk.to_ros(s, data, 'Alpha & co', 'roster-1') == xml  # deterministic ids
    z = zipfile.ZipFile(io.BytesIO(rk.to_rosz(s, data, 'Alpha', 'roster-1', 'Alpha.ros')))
    assert z.namelist() == ['Alpha.ros'] and z.read('Alpha.ros').decode() == rk.to_ros(s, data, 'Alpha', 'roster-1')

def test_real_schemas_compile_and_validate():
    """The bundle built from BSData (when available locally) must compile into schemas the engine can run."""
    path = os.getenv('KILLSTASS_TEAM_BUNDLE')
    if not path: pytest.skip('set KILLSTASS_TEAM_BUNDLE to a built bundle')
    b = json.load(open(path, encoding='utf-8'))
    for t in b['teams']:
        if not t.get('roster'): continue
        e = rk.Engine(t['roster']); uid = Ids()
        data = roster(*[{'uid': uid(), 'key': k, 'n': 1, 'sel': e.defaults(n, uid)} for k, (n, _) in e.options(None).items()])
        r = e.validate(data); assert r['operatives'] > 0, t['slug']
        assert not [i for i in r['errors'] if i['uid'] and i['code'] in ('min', 'unknown_entry')], t['slug']

# ---------------------------------------------------------------- API
def team_bundle():
    s = schema()
    return {'format': td.FORMAT, 'teams': [
        {'slug': 'angels-of-death', 'name': 'Angels of Death', 'data': {'operatives': [{'name': 'Boss'}]}, 'sources': {}, 'roster': s},
        {'slug': 'kommandos', 'name': 'Kommandos', 'data': {'operatives': [{'name': 'Nob'}]}, 'sources': {}}]}

def test_roster_api_and_match_link(clients):
    import psycopg
    from tests.test_integration import register, op, post
    from tests.test_quickstart import approved_ids, ver
    a, b = clients
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        td.load(team_bundle(), c)
        assert c.execute("SELECT roster_hash IS NOT NULL FROM team_data WHERE slug='angels-of-death'").fetchone()[0]
    register(a, 'rosterer'); register(b, 'stranger')
    assert a.get('/api/teams/kommandos/roster-schema').json()['detail'] == 'roster_schema_missing'
    r = a.get('/api/teams/angels-of-death/roster-schema'); assert r.status_code == 200 and r.json()['schema']['cat']['id'] == 'cat-1'
    assert a.get('/api/teams/angels-of-death/roster-schema', headers={'If-None-Match': r.headers['etag']}).status_code == 304
    assert a.post('/api/rosters', json=op(team_slug='kommandos', name='x')).json()['detail'] == 'roster_schema_missing'
    req = op(team_slug='angels-of-death', name='Alpha')
    rid = post(a, '/rosters', req)['id']; assert post(a, '/rosters', req)['id'] == rid  # idempotent create
    lst = a.get('/api/rosters').json()
    assert [x['name'] for x in lst['rosters']] == ['Alpha'] and lst['rosters'][0]['valid'] is False and lst['teams'][0]['slug'] == 'angels-of-death'
    e = rk.Engine(schema()); uid = Ids()
    data = roster(sel(e, 'Boss', uid), sel(e, 'Trooper', uid), sel(e, 'Trooper', uid))
    r = a.put(f'/api/rosters/{rid}', json={'version': 1, 'name': 'Alpha squad', 'data': data}).json()
    assert r['version'] == 2 and r['summary']['valid'] and r['summary']['operatives'] == 3 and r['stale'] is False
    assert a.put(f'/api/rosters/{rid}', json={'version': 1, 'name': 'x', 'data': data}).json()['detail'] == 'version_conflict'
    bad = a.put(f'/api/rosters/{rid}', json={'version': 2, 'name': 'x', 'data': {'selections': [{'uid': 'NO', 'key': 'e-boss'}]}})
    assert bad.status_code == 422 and bad.json()['detail'] == 'roster_bad_uid'
    for who in (b.get(f'/api/rosters/{rid}'), b.put(f'/api/rosters/{rid}', json={'version': 2, 'name': 'x', 'data': data}),
                b.get(f'/api/rosters/{rid}/export?format=ros'), b.request('DELETE', f'/api/rosters/{rid}', json={})):
        assert who.status_code == 404
    assert a.get(f'/api/rosters/{rid}/export').text.startswith('Angels of Death — Alpha squad (3)')
    ros = a.get(f'/api/rosters/{rid}/export?format=ros'); assert 'Alpha_squad.ros' in ros.headers['content-disposition']
    from lxml import etree
    assert etree.XMLSchema(etree.parse(str(FIX / 'BattleScribe-roster-2.03.xsd'))).validate(etree.fromstring(ros.content))
    assert zipfile.ZipFile(io.BytesIO(a.get(f'/api/rosters/{rid}/export?format=rosz').content)).namelist() == ['Alpha_squad.ros']
    assert a.get(f'/api/rosters/{rid}/export?format=json').json()['summary']['valid']
    v = a.get(f'/api/rosters/{rid}').json()['version']
    assert a.put(f'/api/rosters/{rid}', json={'version': v, 'name': 'Ваагх отряд', 'data': data}).status_code == 200
    for fmt in ('ros', 'rosz', 'json'):  # Cyrillic names: latin-1 safe header with RFC 5987 filename*
        x = a.get(f'/api/rosters/{rid}/export?format={fmt}'); cd = x.headers['content-disposition']
        assert x.status_code == 200 and f"filename*=UTF-8''%D0%92%D0%B0%D0%B0%D0%B3%D1%85_%D0%BE%D1%82%D1%80%D1%8F%D0%B4.{fmt}" in cd, cd
        assert 'filename="' in cd and cd.isascii()
    # match setup: own roster of the same team only
    _, ids = approved_ids(a)
    kommandos = next(t['catalog_id'] for t in a.get('/api/teams').json()['teams'] if t['slug'] == 'kommandos')
    mid = post(a, '/matches', op(kind='hotseat'))['id']
    base = dict(mission_id=ids['mission'], killzone_id=ids['zone'], team2_id=ids['team'], operative_count=3, tac_op_id=ids['tac'], primary_op='crit')
    r = a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), team1_id=kommandos, roster_id=rid, **base))
    assert r.json()['detail'] == 'roster_team_mismatch'
    r = a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), team1_id=ids['team'], roster_id=rid, **base)); assert r.status_code == 200, r.text
    r = a.put(f'/api/matches/{mid}/player-setup', json=op(version=ver(a, mid), slot=2, roster_id=rid, operative_count=3, tac_op_id=ids['tac'], primary_op='kill'))
    assert r.status_code == 200, r.text  # hot-seat owner may use own roster for the guest slot
    assert [p['roster_id'] for p in a.get('/api/matches/' + mid).json()['players']] == [rid, rid]
    other = post(b, '/rosters', op(team_slug='angels-of-death', name='Theirs'))['id']
    r = a.put(f'/api/matches/{mid}/setup', json=op(version=ver(a, mid), team1_id=ids['team'], roster_id=other, **base))
    assert r.json()['detail'] == 'roster_not_found'
    assert a.request('DELETE', f'/api/rosters/{rid}', json={}).json()['ok'] and a.get(f'/api/rosters/{rid}').status_code == 404
    assert [p['roster_id'] for p in a.get('/api/matches/' + mid).json()['players']] == [None, None]

def test_roster_limit(clients, monkeypatch):
    import psycopg
    from api import rosters
    from tests.test_integration import register, op, post
    a, _ = clients
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c: td.load(team_bundle(), c)
    register(a, 'collector'); monkeypatch.setattr(rosters, 'MAX_ROSTERS', 2)
    for i in range(2): post(a, '/rosters', op(team_slug='angels-of-death', name=f'R{i}'))
    assert a.post('/api/rosters', json=op(team_slug='angels-of-death', name='R3')).json()['detail'] == 'roster_limit'
