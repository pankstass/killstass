"""v1.12: the «Rules» section (Quick Reference, Core Rules and Faction Rules behind one menu item), the Core Rules
document (tools/core-rules → api/data/core-rules.json → GET /api/reference/core-rules), ready-made Volkus terrain
on killzone boards (web/killzones.js, boards.layout / layout_swap, migration 014) and the disclaimer removed."""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
read = lambda p: (ROOT / p).read_text(encoding='utf-8')


def db():
    import psycopg
    return psycopg.connect(os.environ['TEST_DATABASE_URL'])


def builder():
    spec = importlib.util.spec_from_file_location('core_rules_build', ROOT / 'tools/core-rules/build.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def js_layouts():
    """id, kz, n, set, s1, depth of every layout in web/killzones.js (the order of the generated fields)."""
    text = read('web/killzones.js')
    rows = re.findall(r'id: "([^"]+)",\s*kz: "([^"]+)",\s*n: (\d+),\s*set: "([^"]+)",\s*s1: "([^"]+)",\s*depth: (\d+)', text)
    return [{'id': i, 'kz': kz, 'n': int(n), 'set': s, 's1': s1, 'depth': int(d)} for i, kz, n, s, s1, d in rows]


# ------------------------------------------------------------------ Core Rules: sources, document, endpoint
def test_core_rules_built_from_sources(tmp_path):
    ok = subprocess.run([sys.executable, 'tools/core-rules/build.py', '--check'], cwd=ROOT, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    b = builder()
    changed = []
    for src in b.SOURCES:
        dst = tmp_path / pathlib.Path(src).name
        text = pathlib.Path(src).read_text(encoding='utf-8')
        dst.write_text(text.replace('Kill Team', 'Kill  Team', 1) if not changed else text, encoding='utf-8')
        changed.append(str(dst))
    stale = subprocess.run([sys.executable, 'tools/core-rules/build.py', '--check', str(ROOT / 'api/data/core-rules.json'), *changed],
                           cwd=ROOT, capture_output=True, text=True)
    assert stale.returncode == 1 and 'not built from the current sources' in stale.stderr


def test_core_rules_source_format(tmp_path):
    src = tmp_path / 'demo.md'
    src.write_text('\n'.join([
        '@chapter demo | Demo | Демо', '@section first | First Rule | Первое правило', '## Heading',  # v1.13: no page
        'Text with **bold**.', 'Another paragraph.', '- bullet', '1) numbered',
        '@action Dash | 1AP', '+ Move 3".', '? Not within control range.', '@end', '@table', '| A | B |', '| 1 | 2 |', '@end']),
        encoding='utf-8')
    doc, _ = builder().document([str(src)])
    sec = doc['chapters'][0]['sections'][0]
    assert (doc['chapters'][0]['id'], doc['chapters'][0]['ru'], sec['id'], sec['ru']) == ('demo', 'Демо', 'first', 'Первое правило')
    assert 'page' not in sec
    kinds = [x['t'] for x in sec['blocks']]
    assert kinds == ['h', 'p', 'p', 'ul', 'ol', 'action', 'table']
    assert sec['blocks'][0]['id'] == 'first--heading'
    assert sec['blocks'][1] == {'t': 'p', 'x': 'Text with **bold**.'} and sec['blocks'][2] == {'t': 'p', 'x': 'Another paragraph.'}
    assert sec['blocks'][5]['ap'] == '1AP' and sec['blocks'][5]['cond'] == [{'x': 'Not within control range.'}]
    assert sec['blocks'][6] == {'t': 'table', 'head': ['A', 'B'], 'rows': [['1', '2']]}
    assert re.fullmatch(r'[0-9a-f]{12}', doc['version'])


def test_core_rules_document():
    doc = json.loads(read('api/data/core-rules.json'))
    assert doc['format'] == 2 and re.fullmatch(r'[0-9a-f]{12}', doc['version'])  # v1.13: format 2
    assert [c['id'] for c in doc['chapters']] == ['rules', 'principles', 'killzones', 'missions', 'appendix']
    sections = [s for c in doc['chapters'] for s in c['sections']]
    ids = [s['id'] for s in sections]
    assert len(ids) == len(set(ids)) and len(ids) >= 40
    assert {'strategy', 'firefight', 'actions', 'shoot', 'fight', 'cover', 'obscured', 'terrain-types', 'volkus',
            'gallowdark', 'bheta-decima', 'setup', 'weapon-rules'} <= set(ids)
    assert not any('page' in s for s in sections)  # v1.13: no PDF pages
    assert all(s['title'] and s['ru'] and s['blocks'] for s in sections)
    text = json.dumps(doc, ensure_ascii=False)
    assert '"upd"' not in text and '"book"' not in text.replace('"book": "Warhammer', '')  # v1.13: current rules, no marks
    anchors = re.findall(r'"id": "([^"]+--[^"]+)"', text)
    assert len(anchors) == len(set(anchors))


def test_core_rules_endpoint(clients):
    from tests.test_integration import register
    a, _ = clients
    assert a.get('/api/reference/core-rules').status_code == 401
    register(a, 'reader')
    r = a.get('/api/reference/core-rules')
    doc = json.loads(read('api/data/core-rules.json'))
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/json')
    assert r.json() == doc
    assert r.headers['etag'] == f'"core-{doc["version"]}"'
    assert 'private' in r.headers['cache-control'] and 'Cookie' in r.headers['vary']
    again = a.get('/api/reference/core-rules', headers={'If-None-Match': r.headers['etag']})
    assert again.status_code == 304 and again.content == b'' and again.headers['etag'] == r.headers['etag']
    assert a.get('/api/reference/core-rules', headers={'If-None-Match': '"core-0"'}).status_code == 200


# ------------------------------------------------------------------ ready-made terrain: data
def test_layout_lists_in_step():
    from api.boards import LAYOUTS, KILLZONE_LAYOUTS, LAYOUT_SIZE
    js = js_layouts()
    assert [x['id'] for x in js] == list(LAYOUTS)
    assert {x['id']: (x['s1'], x['depth']) for x in js} == LAYOUTS
    assert [x['id'] for x in js if x['set'] == 'ao2025'] == [f'volkus-2025-{n}' for n in range(1, 7)]
    assert set(KILLZONE_LAYOUTS.values()) <= set(LAYOUTS) and LAYOUT_SIZE == (30.0, 22.0)
    seeds = read('db/migrations/004_verified_catalog.sql')
    assert all(code in seeds for code in KILLZONE_LAYOUTS)  # the Volkus maps of the catalogue
    text = read('web/killzones.js')
    assert text.count('labels: [') == text.count('obj: [') == len(js)
    for letters in re.findall(r'labels: \[(.*?)\]\s*,\s*obj', text, re.S):
        assert sorted(re.findall(r'\["([A-Z])"', letters)) == list('ABCDEFGHIJKLMN')
    for obj in re.findall(r'obj: \[(.*?)\]\s*,\s*\}', text, re.S):
        assert sorted(int(s) for s in re.findall(r'\[[\d.]+, [\d.]+, (\d)\]', obj)) == [0, 1, 2]


# ------------------------------------------------------------------ ready-made terrain: boards
def test_free_board_with_layout(clients):
    import psycopg
    from tests.test_integration import op, post, register
    a, _ = clients
    register(a, 'mapper')
    bid = post(a, '/boards', op(title='Volkus', width=22, height=30, layout='volkus-2025-2'))['id']
    b = a.get(f'/api/boards/{bid}').json()
    assert (b['width'], b['height'], b['layout'], b['swap']) == (30, 22, 'volkus-2025-2', False)
    assert b['frames'][0]['state']['tokens'] == []
    assert [x['layout'] for x in a.get('/api/boards').json()] == ['volkus-2025-2']
    assert a.post('/api/boards', json=op(layout='volkus-2025-9')).json()['detail'] == 'layout_unknown'
    assert a.post('/api/boards', json=op(layout='Volkus 1')).status_code == 422
    plain = a.get(f"/api/boards/{post(a, '/boards', op(width=22, height=30, swap=True))['id']}").json()
    assert (plain['width'], plain['height'], plain['layout'], plain['swap']) == (22, 30, None, False)  # no terrain, no swap
    patch = lambda body: a.patch(f'/api/boards/{bid}', json=body)
    assert patch({'swap': True}).json()['swap'] is True
    r = patch({'layout': 'volkus-example-3', 'width': 22, 'height': 30}).json()
    assert (r['layout'], r['swap'], r['width'], r['height']) == ('volkus-example-3', True, 30, 22)  # the size follows the terrain
    assert patch({'layout': 'volkus-2025-7'}).json()['detail'] == 'layout_unknown'
    r = patch({'layout': ''}).json()
    assert (r['layout'], r['swap'], r['width'], r['height']) == (None, False, 30, 22)
    assert patch({'width': 24, 'height': 24}).json()['width'] == 24
    with db() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("UPDATE boards SET layout='Bad id!' WHERE id=%s", (bid,))


def side_xy(board, frame=0):
    tokens = next(f for f in board['frames'] if f['frame'] == frame)['state']['tokens']
    return {s: sorted((t['x'], t['y']) for t in tokens if t['side'] == s) for s in (1, 2)}


def test_match_board_on_a_volkus_map(clients):
    from tests.test_integration import op, post, ready_match
    a, b = clients
    ua, ub, mid, _ = ready_match(a, b)
    with db() as c:
        kz = c.execute("SELECT id FROM catalogs WHERE code='2024-wahapedia-killzone-volkus-1'").fetchone()[0]
        c.execute('UPDATE matches SET killzone_id=%s WHERE id=%s', (kz, mid))
    bid = post(a, '/boards', op(match_id=mid))['id']
    board = b.get(f'/api/boards/{bid}').json()
    assert (board['layout'], board['swap'], board['width'], board['height']) == ('volkus-2025-1', False, 30, 22)
    xy = side_xy(board)
    assert xy[1] and xy[2] and {x for x, _ in xy[1]} == {1.5} and {x for x, _ in xy[2]} == {28.5}  # inside the drop zones
    assert all(0 < y < 22 for s in (1, 2) for _, y in xy[s]) and len({y for _, y in xy[1]}) == len(xy[1])
    # player 2 moves one operative of the deployment; then player 1 takes the other drop zone
    frame0 = board['frames'][0]
    tokens = frame0['state']['tokens']
    moved = next(t for t in tokens if t['side'] == 1)
    moved.update(x=4.0, y=5.0)
    assert b.put(f'/api/boards/{bid}/frames/0', json={'version': frame0['version'], 'state': {'tokens': tokens}}).status_code == 200
    r = b.patch(f'/api/boards/{bid}', json={'swap': True}).json()
    assert r['swap'] is True and r['frames'][0]['version'] == frame0['version'] + 2
    after = {t['id']: t for t in r['frames'][0]['state']['tokens']}
    assert (after[moved['id']]['x'], after[moved['id']]['y']) == (4.0, 5.0)  # a moved token stays put
    assert {t['x'] for t in after.values() if t['side'] == 1 and t['id'] != moved['id']} == {28.5}
    assert {t['x'] for t in after.values() if t['side'] == 2} == {1.5}
    # map 4: drop zones along the long edges (3" deep); player 1 still swapped -> top edge
    xy = side_xy(a.patch(f'/api/boards/{bid}', json={'layout': 'volkus-2025-4'}).json())
    assert {y for x, y in xy[1] if (x, y) != (4.0, 5.0)} == {1.5} and {y for _, y in xy[2]} == {20.5}
    # without terrain: the old deployment along the bottom (player 1) and the top edge
    r = a.patch(f'/api/boards/{bid}', json={'layout': ''}).json()
    xy = side_xy(r)
    assert r['layout'] is None and r['swap'] is False
    assert {y for x, y in xy[1] if (x, y) != (4.0, 5.0)} == {20.5} and {y for _, y in xy[2]} == {1.5}
    assert b.patch(f'/api/boards/{bid}', json={'layout': 'nope'}).json()['detail'] == 'layout_unknown'
    # a new board of the match may be asked for without terrain
    assert a.request('DELETE', f'/api/boards/{bid}', json={}).json()['ok']
    bare = b.get(f"/api/boards/{post(b, '/boards', op(match_id=mid, layout=''))['id']}").json()
    assert bare['layout'] is None and {y for _, y in side_xy(bare)[1]} == {20.5} and {y for _, y in side_xy(bare)[2]} == {1.5}


def test_match_board_follows_the_tracked_operatives(clients):
    """More than 12 operatives along a short edge stand in two columns, all inside the drop zone."""
    from tests.test_integration import op, post, ready_match
    from api.boards import deployment
    a, b = clients
    _, _, mid, _ = ready_match(a, b)
    with db() as c:
        c.execute('UPDATE match_players SET operative_count=14 WHERE match_id=%s', (mid,))
        from psycopg.rows import dict_row
        c.row_factory = dict_row
        m = c.execute('SELECT * FROM matches WHERE id=%s', (mid,)).fetchone()
        tracked = c.execute('SELECT count(*) AS n FROM match_operatives o JOIN match_players p ON p.id=o.player_id WHERE p.match_id=%s',
                            (mid,)).fetchone()['n']
        state = deployment(c, m, 30, 22, 'volkus-2025-2', False)
    xs = {t['side']: set() for t in state['tokens']}
    for t in state['tokens']:
        xs[t['side']].add(t['x'])
        assert 0 < t['y'] < 22
    if not tracked:
        assert xs == {1: {1.5, 3.5}, 2: {28.5, 26.5}}
    assert all(x <= 6 for x in xs[1]) and all(x >= 24 for x in xs[2])


# ------------------------------------------------------------------ menu, texts, migration
def test_rules_menu_and_no_disclaimer():
    # v1.14: the menu comes from the table of sections (web/sections.js); «Rules» is the group of the three books
    sec = read('web/sections.js')
    groups = re.findall(r'\{\s*id: "([a-z]+)"', sec)
    assert 'rules' in groups and 'teams' not in groups and 'reference' not in groups
    assert re.search(r'id: "rules",[^}]*items: \["reference", "core", "teams"\]', sec)
    hub = read('web/corerules.js')
    assert all(f'#{h}' in hub for h in ('reference', 'core', 'teams'))
    ru, en = json.loads(read('web/i18n/ru.json')), json.loads(read('web/i18n/en.json'))
    assert 'legal' not in ru and 'legal' not in en
    assert ru['shareFooter'] == 'KILLSTASS · журнал боёв Kill Team' and en['shareFooter'] == 'KILLSTASS · Kill Team battle log'
    for k in ('rules', 'map_layout', 'map_layoutNone', 'map_swap', 'kz_map', 'kz_example', 'kz_legend', 'kz_rules'):
        assert ru[k] and en[k], k
    assert ru['errors']['layout_unknown'] and en['errors']['layout_unknown']
    intro = read('README.md').split('\n## ')[0]  # «Что нового» may name the removed text
    texts = [read(f'web/{p}') for p in ('index.html', 'app.js', 'share.js', 'main.js', 'i18n/ru.json', 'i18n/en.json')] + [intro]
    for needle in ('fan-made', 'Not affiliated', 'фанатский инструмент', 'не связанный с Games Workshop', 'No official materials'):
        assert not [t for t in texts if needle in t], needle


def test_migration_014():
    from api.main import MIGRATIONS
    assert '014_v112.sql' in MIGRATIONS
    sql = read('db/migrations/014_v112.sql')
    assert 'ADD COLUMN layout text' in sql and 'layout_swap boolean NOT NULL DEFAULT false' in sql
