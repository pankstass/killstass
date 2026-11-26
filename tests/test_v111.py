"""v1.11: Sweep & Clear, the rules reference (warhammer-oracle rules read as data, import and export, one search over
general rules, catalog and teams, library and status, #admin journal), the reference update planner and
scripts/update-reference.sh (against a fake docker and the test database)."""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
from io import BytesIO
from urllib.parse import urlparse
import pytest
from api import refupdate as ref
from api import rulesdata as rd
from api import teamdata as td

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = '0123456789abcdef0123456789abcdef01234567'
# Invented rules (not Games Workshop text) in the layout of warhammer-oracle src/data/kill-team-rules.ts.
RULES_TS = '''// Generated: 2026-11-01T10:00:00.000Z
// Source: https://github.com/BSData/wh40k-killteam
import type { SharedRule } from '../types';
export const KILL_TEAM_SHARED_RULES: SharedRule[] = [
  {"name": "Alpha x", "description": "Roll x extra test dice."},
  {"name": "Bravo", "description": "Retain one normal success as a critical one."},
  {"name": "Charlie", "description": "Ignore \\"light\\" cover\\u2019s benefit."},
  {"name": "Delta", "description": "Move the target 1\\" closer."},
  {"name": "Echo", "description": "Re-roll results of one."}
];
'''
PHASES_TS = '''import type { Phase } from '../types';
/* Kill Team phases */
export const PHASES_KILL_TEAM: Phase[] = [
  {
    name: 'Strategy', // comment
    order: 2,
    gameMode: 'kill_team',
    steps: ['Gain command points', 'Play strategy ploys',],
    tips: ['Plan ahead'],
  },
  { name: "Initiative", order: 1, gameMode: 'kill_team', steps: ['Roll off'], tips: [] },
];
'''
RU = {'weapon-bravo': {'name_ru': 'Браво', 'aliases': ['брависсимо', ' ', 7], 'text_ru': 'Сохраните ещё один обычный успех как критический.',
                       'basis': rd.text_hash('Retain one normal success as a critical one.')},
      'weapon-echo': {'name_ru': 'Эхо', 'text_ru': 'Старый пересказ.', 'basis': '0' * 64}}


def quiet(): return open(os.devnull, 'w')
def rules_bundle(rules=RULES_TS, phases=PHASES_TS, tag='v9.9.9', commit=COMMIT):
    return rd.build({'rules': rules, 'phases': phases}, tag, commit, log=quiet())
def copy(x): return json.loads(json.dumps(x))
def db():
    import psycopg
    return psycopg.connect(os.environ['TEST_DATABASE_URL'])
def teams_bundle():
    from tests.test_teams import bundle
    return bundle()


# ------------------------------------------------------------------ warhammer-oracle data files
def test_typescript_literals_are_read_as_data_only():
    text = "{a: 1, 'b': [true, null, -2.5,], c: {d: 'x\\'y'}, /* c */ e: \"\\u0041\\n\"} rest"
    v, end = rd.literal(text)
    assert v == {'a': 1, 'b': [True, None, -2.5], 'c': {'d': "x'y"}, 'e': 'A\n'} and text[end:] == ' rest'
    for bad in ('[`template`]', '[foo]', '{...x}', '[f(1)]', '{a: 1', "['line\nbreak']", '[' * 30 + ']' * 30):
        with pytest.raises(ValueError):
            rd.literal(bad)
    rules, generated, upstream = rd.parse_rules(RULES_TS)
    assert [r['name'] for r in rules] == ['Alpha x', 'Bravo', 'Charlie', 'Delta', 'Echo']
    assert rules[2]['description'] == 'Ignore "light" cover’s benefit.' and rules[3]['description'] == 'Move the target 1" closer.'
    assert generated == '2026-11-01T10:00:00.000Z' and upstream == 'https://github.com/BSData/wh40k-killteam'
    phases = rd.parse_phases(PHASES_TS)
    assert [p['name'] for p in phases] == ['Initiative', 'Strategy'] and phases[1]['steps'] == ['Gain command points', 'Play strategy ploys']
    with pytest.raises(ValueError):
        rd.parse_rules('export const KILL_TEAM_SHARED_RULES = [{"name": "One", "description": "x"}];')  # too few rules
    with pytest.raises(ValueError):
        rd.parse_rules(RULES_TS.replace('"Echo"', '"bravo"'))  # duplicate name
    with pytest.raises(ValueError):
        rd.parse_phases(PHASES_TS.replace("gameMode: 'kill_team', steps: ['Roll off']", "gameMode: 'wh40k', steps: ['Roll off']"))


def test_rules_bundle_provenance_and_validation():
    b = rules_bundle()
    assert b['format'] == rd.FORMAT and rd.validate(b) == b['entries']
    codes = [e['code'] for e in b['entries']]
    assert codes == ['weapon-alpha-x', 'weapon-bravo', 'weapon-charlie', 'weapon-delta', 'weapon-echo', 'phase-initiative', 'phase-strategy']
    w, p = b['entries'][0], b['entries'][-1]
    assert w['verification'] == 'bsdata' and p['verification'] == 'unverified' and p['details']['tips'] == ['Plan ahead']
    assert w['source']['repo'] == rd.ORACLE and w['source']['commit'] == COMMIT and w['source']['path'] == rd.FILES['rules']
    assert len(w['source']['sha256']) == 64 and b['sources']['oracle']['tag'] == 'v9.9.9' and b['sources']['oracle']['license'] == 'MIT'
    no_phases = rd.build({'rules': RULES_TS, 'phases': 'export const PHASES_KILL_TEAM = oops;'}, 'v1', COMMIT, log=quiet())
    assert all(e['kind'] == 'weapon_rule' for e in no_phases['entries']) and no_phases['warnings'][0].startswith('phases skipped')
    for bad in ({**b, 'format': 'x'}, {**b, 'entries': []}, {**b, 'entries': b['entries'] * 2},
                {**b, 'entries': [{**w, 'code': 'phase-x'}]}, {**b, 'entries': [{**w, 'source': {'repo': 'other/repo', 'commit': COMMIT}}]},
                {**b, 'entries': [{**w, 'verification': 'verified'}]}, {**b, 'entries': [{**w, 'text_en': ''}]}):
        with pytest.raises(ValueError):
            rd.validate(bad)
    assert rd.validate({**b, 'entries': []}, allow_empty=True) == []


def test_russian_paraphrases_follow_the_english_text(monkeypatch):
    shipped = json.loads((ROOT / 'api/data/weapon-rules-ru.json').read_text(encoding='utf-8'))['rules']
    assert len(shipped) == 22
    for code, r in shipped.items():
        assert rd.CODE.match(code) and code.startswith('weapon-') and re.fullmatch('[0-9a-f]{64}', r['basis'])
        assert re.search('[а-яё]', r['text_ru'], re.I) and r['name_ru'], code
        assert all(re.fullmatch('[а-яё -]{2,40}', a) for a in r['aliases']), code
    assert 'летал' in shipped['weapon-lethal-x']['aliases'] and 'девастейтинг' in shipped['weapon-devastating-x']['aliases']
    monkeypatch.setattr(rd, 'russian', lambda: RU)
    rows, warnings = rd.rows(rules_bundle())
    by = {r['code']: r for r in rows}
    assert by['weapon-bravo']['text_ru'].startswith('Сохраните') and by['weapon-bravo']['name_ru'] == 'Браво'
    assert by['weapon-bravo']['aliases'] == ['брависсимо'] and by['weapon-alpha-x']['aliases'] == []
    assert by['weapon-echo']['text_ru'] == '' and warnings == ['weapon-echo: English text changed, the Russian paraphrase is hidden until reviewed']
    sql = rd.to_sql(rules_bundle())
    assert sql.count('INSERT INTO rule_entries') == 1 and td.REFRESH_SQL in sql
    assert "UPDATE rule_entries SET active=false WHERE kind='weapon_rule' AND active AND code NOT IN (" in sql
    assert 'imported_at=CASE WHEN rule_entries.active AND rule_entries.content_hash=excluded.content_hash' in sql


# ------------------------------------------------------------------ planner of scripts/update-reference.sh
def test_planner_compares_checks_and_writes_one_script(monkeypatch):
    monkeypatch.setattr(rd, 'russian', lambda: RU)
    teams, rules = teams_bundle(), rules_bundle()
    changed, sql, rep = ref.plan(teams, copy(teams), rules, copy(rules), [], started='2026-11-04T05:00:00Z')
    assert not changed and "'update','unchanged','manual','',''" in sql and 'INSERT INTO team_data(' not in sql and 'REFRESH' not in sql
    assert rep['warnings'] == [] and "'2026-11-04T05:00:00+00:00'::timestamptz" in sql
    moved = copy(teams)  # a new upstream commit with the same cards is not a change
    for t in moved['teams']:
        t['sources']['bsdata'] = {**t['sources'].get('bsdata', {}), 'commit': 'b' * 40}
    changed, _, rep = ref.plan(teams, moved, rules, rules, [])
    assert not changed and rep['teams']['provenance_only'] == 2

    new_teams, new_rules = copy(teams), copy(rules)
    k = next(t for t in new_teams['teams'] if t['slug'] == 'kommandos')
    k['data']['strategy_ploys'].append({'name': 'Test Ploy', 'body': [{'k': 'p', 't': 'Test.'}]})
    new_teams['teams'] = [k]
    new_rules['entries'][1]['text_en'] = 'Retain two normal successes.'
    new_rules['entries'] = new_rules['entries'][:-1]
    with pytest.raises(ref.Invalid, match='1 teams instead of 2'):
        ref.plan(teams, new_teams, rules, new_rules, [])
    changed, sql, rep = ref.plan(teams, new_teams, rules, new_rules, [], trigger='timer', share=0.5)
    assert changed and rep['teams']['removed'] == ['strike-force-variel'] and rep['teams']['added'] == []
    assert rep['teams']['changed'] == [{'slug': 'kommandos', 'name': 'Kommandos', 'ploys': {'added': ['Test Ploy'], 'removed': []}}]
    assert rep['rules'] == {'before': 7, 'after': 6, 'added': [], 'removed': ['Strategy'], 'changed': ['Bravo']}
    assert any('weapon-bravo: English text changed' in w for w in rep['warnings'])
    assert sql.count('REFRESH MATERIALIZED VIEW') == 1 and sql.index('INSERT INTO team_data(') < sql.index('INSERT INTO rule_entries')
    assert sql.index('INSERT INTO rule_entries') < sql.index('REFRESH MATERIALIZED VIEW') < sql.index('INSERT INTO reference_updates')
    assert "'update','ok','timer',:'ks_backup',:'ks_snapshot'" in sql and sql.endswith("SELECT 'reference update: ok';\n")
    assert 'Test Ploy' in ref.report_text(rep, 'update', 'timer') and 'Teams: 2 → 1: +0 −1 ~1' in ref.report_text(rep, 'update', 'timer')

    for bad_teams, bad_rules, msg in (({'format': 'x'}, rules, 'teams'), ({**teams, 'sources': {}}, rules, 'source commits'),
                                      (teams, {**rules, 'sources': {'oracle': {'tag': 'v1', 'commit': 'abc'}}}, 'warhammer-oracle'),
                                      (teams, {'format': rd.FORMAT, 'entries': []}, 'rules'), ({'format': td.FORMAT, 'teams': []}, rules, 'teams')):
        with pytest.raises(ref.Invalid, match=msg):
            ref.plan(teams, bad_teams, rules, bad_rules, [])
    # A rollback may return to an empty reference (the first update had nothing before it).
    changed, sql, rep = ref.plan(teams, {'format': td.FORMAT, 'teams': []}, rules, {'format': rd.FORMAT, 'entries': []}, [], action='rollback')
    assert changed and 'UPDATE team_data SET active=false WHERE active;' in sql and "kind='weapon_rule' AND active;" in sql
    assert "kind='phase' AND active;" in sql and "'rollback','ok'" in sql


def test_planner_finds_rosters_that_would_stop_passing():
    from tests.test_rosters import Ids, roster, schema, sel
    from api import rosterkit as rk
    s = schema()
    e, uid = rk.Engine(s), Ids()
    good = roster(sel(e, 'Boss', uid), sel(e, 'Trooper', uid), sel(e, 'Trooper', uid))
    bad = roster(sel(e, 'Boss', uid))
    tight = copy(s)
    for c in tight['force']['cats']:
        for con in c['con']:
            if con['id'] == 'op-max': con['v'] = 1
    saved = [{'id': 1, 'name': 'Alpha', 'team_slug': 'testers', 'data': good, 'owner': '#A1 alpha'},
             {'id': 2, 'name': 'Broken already', 'team_slug': 'testers', 'data': bad, 'owner': '#A1 alpha'},
             {'id': 3, 'name': 'Gone', 'team_slug': 'gone', 'data': good, 'owner': '#B2 bravo'}]
    out = ref.roster_check(saved, {'testers': s, 'gone': s}, {'testers': tight})
    assert out['checked'] == 3
    assert out['failing'] == [{'id': '1', 'name': 'Alpha', 'team': 'testers', 'owner': '#A1 alpha', 'errors': ['category_max']},
                              {'id': '3', 'name': 'Gone', 'team': 'gone', 'owner': '#B2 bravo', 'errors': ['team_removed']}]
    assert ref.roster_check(saved, {'testers': s}, {'testers': s})['failing'] == []


def test_planner_reads_exactly_two_bundles():
    def tar(files):
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as t:
            for name, data in files.items():
                info = tarfile.TarInfo(name); raw = json.dumps(data).encode(); info.size = len(raw)
                t.addfile(info, BytesIO(raw))
        buf.seek(0)
        return buf
    assert ref.read_tar(tar({'teams-new.json': {'a': 1}, 'rules-new.json': {'b': 2}, 'other.json': {}})) == ({'a': 1}, {'b': 2})
    with pytest.raises(ref.Invalid):
        ref.read_tar(tar({'teams-new.json': {}}))
    r = subprocess.run([sys.executable, '-m', 'api.refupdate', 'plan'], cwd=ROOT, input=b'not a tar', capture_output=True)
    assert r.returncode == ref.EXIT_INVALID and b'check failed' in r.stderr


# ------------------------------------------------------------------ static files
def test_reference_scripts_units_and_web_files():
    read = lambda p: (ROOT / p).read_text(encoding='utf-8')
    u = read('scripts/update-reference.sh')
    for needle in ('flock -n 8', './scripts/backup.sh', '--single-transaction', '-v ks_backup="$KS_BACKUP"', '--rollback', '--check',
                   'KEEP_REFERENCE', 'MIN_SHARE', 'TRIGGER', 'python -m api.refupdate plan', 'python -m api.teamdata export',
                   'python -m api.rulesdata export', '--network bridge', '--cap-drop ALL', '--read-only', '.applied', 'teams-before.json'):
        assert needle in u, needle
    assert 'docker compose down' not in u and '--volumes' not in u
    imp = read('scripts/import-rules.sh')
    assert 'python -m api.rulesdata fetch' in imp and 'python -m api.rulesdata sql' in imp and 'ORACLE_REF' in imp
    svc, timer = read('systemd/killstass-reference.service'), read('systemd/killstass-reference.timer')
    assert 'Type=oneshot' in svc and 'Environment=TRIGGER=timer' in svc and 'ExecStart=/opt/killstass/scripts/update-reference.sh' in svc
    assert 'OnCalendar=Mon' in timer and 'Persistent=true' in timer and 'RandomizedDelaySec=' in timer
    spec = importlib.util.spec_from_file_location('catalog_import_v111', ROOT / 'tools/catalog-import/import_catalog.py')
    imp_cat = importlib.util.module_from_spec(spec); spec.loader.exec_module(imp_cat)
    seed = json.loads(read('db/seed.json'))
    sql, _ = imp_cat.build(seed, seed)
    assert sql.rstrip().endswith("REFRESH MATERIALIZED VIEW reference_search; END IF; END$$;")
    from api.main import MIGRATIONS
    assert '013_v111.sql' in MIGRATIONS and (ROOT / 'db/migrations/013_v111.sql').exists()
    sw, app = read('web/sw.js'), read('web/app.js')
    # v1.12: the reference is opened from the «Rules» section (no menu item of its own), the route stays
    # v1.14: the signed-in pages are a route table (web/app.js ROUTES)
    assert 'reference\\/search' in sw and 'reference: (p) => referenceRoute(p)' in app
    ru, en = json.loads(read('web/i18n/ru.json')), json.loads(read('web/i18n/en.json'))
    kinds = ['weapon_rule', 'rule', 'sequence', 'phase', 'mission', 'tac_op', 'team', 'operative', 'faction_rule', 'equipment']
    keys = ['rk_' + k for k in kinds] + ['rk_ploy_strategy', 'rk_ploy_firefight']
    keys += ['ref_kind_' + k for k in ('all', 'rules', 'ops', 'teams', 'operatives', 'ploys', 'equipment')]
    keys += [f'ad_ref{g}_{v}' for g, vs in (('Status', ('ok', 'unchanged', 'failed')), ('Action', ('update', 'rollback')),
                                            ('Trigger', ('manual', 'timer'))) for v in vs]
    assert not [k for k in keys if k not in ru or k not in en]
    assert ru['errors']['search_query_short'] and en['errors']['search_query_short']


# ------------------------------------------------------------------ database: Sweep & Clear, import, search
@pytest.fixture
def reference(clients, monkeypatch):
    """Two small teams (tests/test_teams.py) and the fixture rules with one Russian paraphrase, loaded as the owner."""
    monkeypatch.setattr(rd, 'russian', lambda: RU)
    with db() as c:
        td.load(teams_bundle(), c)
        rd.load(rules_bundle(), c)
        c.execute('DELETE FROM reference_updates')
    return clients


def sweep_match(a, b):
    from tests.test_integration import op, post, register
    ua, ub = register(a, 'alpha'), register(b, 'bravo')
    data = a.get('/api/catalogs').json()
    pick = lambda kind, code: next(r['id'] for r in data if r['kind'] == kind and r['code'].endswith(code))
    team, mission, zone = pick('team', 'team-angel-of-death'), pick('mission', 'mission-secure'), pick('killzone', 'volkus-1')
    post(a, '/friends', {'public_id': ub['public_id']})
    post(b, '/friends/' + ua['public_id'], {'action': 'accept'})
    ch = post(a, '/challenges', op(public_id=ub['public_id']))
    mid = post(b, '/challenges/' + ch['id'], op(action='accepted'))['match_id']
    for client, primary, tac in ((a, 'crit', 'tac-op-sweep-clear'), (b, 'kill', 'tac-op-rout')):
        m = client.get('/api/matches/' + mid).json()
        r = client.put('/api/matches/' + mid + '/setup', json=op(version=m['version'], mission_id=mission, killzone_id=zone, team1_id=team,
                       team2_id=team, operative_count=6, tac_op_id=pick('tac_op', tac), primary_op=primary))
        assert r.status_code == 200, r.text
    m = a.get('/api/matches/' + mid).json()
    post(a, '/matches/' + mid + '/actions', op(version=m['version'], action='start'))
    return mid, data


def test_sweep_and_clear_is_verified_and_playable(clients):
    from tests.test_integration import op, post
    a, b = clients
    mid, data = sweep_match(a, b)
    sweep = next(r for r in data if r['code'] == '2024-wahapedia-tac-op-sweep-clear')
    assert sweep['active'] and sweep['verification'] == 'verified' and sweep['label_en'] == 'Sweep & Clear'
    assert sweep['config']['per_turn_caps'] == [0, 2, 2, 2] and sweep['config']['max_per_battle'] == 6
    assert 'swept' in sweep['config']['summary'] and 'Errata' in sweep['config']['errata']
    sd = sorted(r['code'] for r in data if r['kind'] == 'tac_op' and r['active'] and r['config'].get('archetype') == 'Seek & Destroy')
    assert sd == ['2024-wahapedia-tac-op-dominate', '2024-wahapedia-tac-op-rout', '2024-wahapedia-tac-op-sweep-clear']
    en = json.loads((ROOT / 'web/i18n/catalog.en.json').read_text(encoding='utf-8'))['catalog'][sweep['code']]
    assert en['label'] == 'Sweep & Clear' and 'swept' in en['summary']
    tac = next(r['id'] for r in data if r['kind'] == 'source' and r['config'].get('component') == 'tac')
    score = lambda tp, vp: a.post('/api/matches/' + mid + '/scores', json=op(version=a.get('/api/matches/' + mid).json()['version'],
                                                                                turning_point=tp, source_id=tac, delta=vp))
    assert score(1, 1).status_code == 422  # nothing to score in the first turning point
    for tp in (2, 3, 4):
        assert score(tp, 2).status_code < 300
    assert score(4, 1).status_code == 422
    m = b.get('/api/matches/' + mid).json()
    assert m['players'][0]['tac'] == 6 and m['players'][0]['tac_op_id'] == sweep['id']


def test_rules_import_export_and_read_only_role(reference):
    import psycopg
    with db() as c:
        first = dict(c.execute("SELECT code, imported_at FROM rule_entries WHERE active").fetchall())
        rd.load(rules_bundle(), c)  # the same bundle again: rows unchanged, imported_at kept
        assert dict(c.execute("SELECT code, imported_at FROM rule_entries WHERE active").fetchall()) == first
        out = rd.export(c)
        assert [e['code'] for e in out['entries']] == [e['code'] for e in rules_bundle()['entries']]
        assert out['sources']['oracle']['tag'] == 'v9.9.9' and all(len(e['content_hash']) == 64 for e in out['entries'])
        assert c.execute("SELECT text_ru FROM rule_entries WHERE code='weapon-bravo'").fetchone()[0].startswith('Сохраните')
        rd.load(rules_bundle(rules=RULES_TS.replace('{"name": "Echo", "description": "Re-roll results of one."}', '{"name": "Foxtrot", "description": "Fox."}')), c)
        assert not c.execute("SELECT active FROM rule_entries WHERE code='weapon-echo'").fetchone()[0]
        assert c.execute("SELECT count(*) FROM reference_search WHERE id='rule:weapon-foxtrot'").fetchone()[0] == 1
        teams = td.export(c)
        changed, _, _ = ref.plan(teams, teams_bundle(), rd.export(c), rd.export(c), [])
        assert not changed  # export -> the same content as the loaded bundle
        assert c.execute("SELECT ks_fold(E'  ЁЖИК\\n Ёлка ')").fetchone()[0] == 'ежик елка'
    with psycopg.connect(os.environ['DATABASE_URL']) as c:
        assert c.execute('SELECT count(*) FROM rule_entries').fetchone()[0] >= 5
        for sql in ("UPDATE rule_entries SET active=false", "INSERT INTO reference_updates(started_at,action,status,trigger) VALUES(now(),'update','ok','manual')",
                    'REFRESH MATERIALIZED VIEW reference_search', 'DELETE FROM rule_imports'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
            c.rollback()


def test_reference_search(reference):
    from tests.test_integration import register
    a, _ = reference
    assert a.get('/api/reference/search?q=sweep').status_code == 401
    register(a, 'searcher')
    s = lambda **kw: a.get('/api/reference/search', params=kw)
    for bad in ({'q': 'a'}, {'q': ' '}):
        r = s(**bad)
        assert r.status_code == 422 and r.json()['detail'] == 'search_query_short'
    assert s(q='x', kind='spells').status_code == 422 and s(q='x' * 121).status_code == 422 and s(q='xx', limit=51).status_code == 422
    top = lambda **kw: s(**kw).json()['results'][0]
    with db() as c:  # a team entry named like the query does not outrank the Tac Op of that name
        b = teams_bundle(); v = next(t for t in b['teams'] if t['slug'] == 'strike-force-variel')
        v['data']['operatives'].append({**copy(v['data']['operatives'][0]), 'name': 'Traitor Trench Sweeper', 'keywords': ['CHAOS', 'TRENCH SWEEPER']})
        td.load(b, c)
    assert [r['title'] for r in s(q='sweep').json()['results']][:2] == ['Зачистка', 'Traitor Trench Sweeper']
    for q in ('Sweep', 'зачистка', 'ЗАЧИСТКА', 'swee'):
        hit = top(q=q)
        assert hit['id'] == 'cat:2024-wahapedia-tac-op-sweep-clear' and hit['kind'] == 'tac_op', q
    assert hit['title'] == 'Зачистка' and hit['subtitle'] == 'Sweep & Clear' and 'swept' in hit['text'] and 'team' not in hit
    hit = top(q='sweep', lang='en')
    assert hit['title'] == 'Sweep & Clear' and not re.search('[а-яё]', hit['text'], re.I)
    op = top(q='boss nob')
    assert op['kind'] == 'operative' and op['title'] == 'Kommando Boss Nob' and op['link'] == '#teams/kommandos/operatives/op-0'
    assert op['team']['slug'] == 'kommandos' and op['team']['name'] == 'Kommandos'
    ploy = top(q='dakka', kind='ploys')
    assert ploy['kind'] == 'ploy' and ploy['link'] == '#teams/kommandos/ploys/sp-0' and 'Punishing' in ploy['snippet']
    assert 'Whilst they are more subtle' not in ploy['snippet']  # lore is not indexed
    rule = top(q='bravo')
    assert rule['id'] == 'rule:weapon-bravo' and rule['subtitle'] == 'Браво' and rule['text_ru'].startswith('Сохраните')
    assert rule['source_url'] == f'https://github.com/{rd.ORACLE}/blob/{COMMIT}/{rd.FILES["rules"]}'
    for q in ('сохранить успех', 'еще один обычный', 'ЕЩЁ ОДИН обычный', 'брависс'):  # Russian stemming, case, «ё», aliases
        assert top(q=q)['id'] == 'rule:weapon-bravo', q
    phase = top(q='initiative', kind='rules')
    assert phase['kind'] == 'phase' and phase['verification'] == 'unverified'
    body = s(q='dakka').json()
    assert body['q'] == 'dakka' and body['terms'] == ['dakka'] and body['total'] >= 1
    ops = s(kind='ops', limit=50).json()  # browsing a section
    assert ops['total'] >= 10 and {r['kind'] for r in ops['results']} <= {'mission', 'tac_op'}
    page2 = s(kind='ops', limit=5, offset=5).json()
    assert [r['id'] for r in page2['results']] == [r['id'] for r in ops['results'][5:10]]
    team = s(team='kommandos').json()
    assert team['total'] >= 3 and {r['team']['slug'] for r in team['results']} == {'kommandos'}
    assert s(q='lieutenant variel', team='kommandos').json()['total'] == 0
    with db() as c:  # a team left out of the next import disappears from the search
        b = teams_bundle(); b['teams'] = [t for t in b['teams'] if t['slug'] == 'kommandos']
        td.load(b, c)
    assert s(q='lieutenant variel').json()['total'] == 0


def test_library_status_and_admin_journal(reference):
    from tests.test_integration import register
    a, _ = reference
    assert a.get('/api/reference/library').status_code == 401
    user = register(a, 'librarian')
    r = a.get('/api/reference/library')
    assert r.status_code == 200 and 'private' in r.headers['cache-control']
    body = r.json()
    assert [x['code'] for x in body['rules']][:2] == ['weapon-alpha-x', 'weapon-bravo'] and body['rules'][-1]['kind'] == 'phase'
    assert body['rules'][1]['aliases'] == ['брависсимо'] and body['rules'][0]['aliases'] == []
    st = body['status']
    assert st['rules']['oracle'] == {'repo': rd.ORACLE, 'tag': 'v9.9.9', 'commit': COMMIT, 'generated_at': '2026-11-01T10:00:00.000Z'}
    assert st['rules']['rules'] == 5 and st['rules']['phases'] == 2 and st['teams']['teams'] == 2
    assert st['catalog']['rules_version'] and st['update'] is None and st['checked_at'] is None
    assert a.get('/api/reference/library', headers={'If-None-Match': r.headers['etag']}).status_code == 304
    rep = {'teams': {'before': 2, 'after': 2, 'operatives_before': 2, 'operatives_after': 2, 'added': [], 'removed': [],
                     'changed': [{'slug': 'kommandos', 'name': 'Kommandos', 'ploys': {'added': ['X'], 'removed': []}}], 'provenance_only': 0},
           'rules': {'before': 7, 'after': 7, 'added': [], 'removed': [], 'changed': ['Bravo']},
           'rosters': {'checked': 3, 'failing': [{'id': '1', 'name': 'Alpha', 'team': 'kommandos', 'owner': '#A alpha', 'errors': ['category_max']}]},
           'warnings': ['w1']}
    with db() as c:
        c.execute("""INSERT INTO reference_updates(started_at,action,status,trigger,backup,snapshot,report)
                     VALUES(now(),'update','ok','timer','/b/killstass-x.dump','/b/reference/20261104T051500Z',%s)""", (json.dumps(rep),))
    assert a.get('/api/reference/library', headers={'If-None-Match': r.headers['etag']}).status_code == 200  # the status changed
    assert a.get('/api/admin/overview').status_code == 403
    with db() as c:
        c.execute('UPDATE users SET is_admin=true WHERE id=%s', (user['id'],))
    o = a.get('/api/admin/overview').json()['reference']
    assert o['status']['update']['status'] == 'ok' and o['status']['checked_at']
    u = o['updates'][0]
    assert (u['action'], u['status'], u['trigger'], u['backup']) == ('update', 'ok', 'timer', '/b/killstass-x.dump')
    assert u['report']['teams']['changed'] == ['kommandos'] and u['report']['rules']['changed'] == ['Bravo']
    assert u['report']['rosters']['failing'][0]['errors'] == ['category_max'] and u['report']['warnings'] == ['w1'] and u['report']['error'] is None


# ------------------------------------------------------------------ scripts/update-reference.sh with a fake docker
FAKE_DOCKER = r'''#!/bin/sh
echo "docker $*" >> "$LOG"
case "$*" in
  *pg_dump*) echo PGDMP-fake; exit 0 ;;
  *"pg_restore --list"*) cat > /dev/null; exit 0 ;;
esac
if [ "$1" = compose ] && [ "$2" = exec ]; then
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in -T) shift ;; -e) export "$2"; shift 2 ;; *) break ;; esac
  done
  svc=$1; shift
  if [ "$svc" = api ]; then [ "$1" = python ] && shift; cd "$APP" && exec "$PY" "$@"; fi
  export POSTGRES_USER="$OWNER_USER" POSTGRES_DB="$OWNER_URL"
  exec "$@"
fi
if [ "$1" = run ]; then
  case "$*" in
    *api.teamdata*) [ "${FAIL:-}" = teams ] && { echo 'network is unreachable' >&2; exit 1; }; cat "$TEAMS"; exit 0 ;;
    *api.rulesdata*) cat "$RULES"; exit 0 ;;
  esac
fi
echo "fake docker: $*" >&2; exit 99
'''


@pytest.mark.skipif(not (shutil.which('sh') and shutil.which('flock') and shutil.which('psql')), reason='sh, flock and psql required')
def test_update_reference_script(reference, tmp_path):
    url = os.environ['TEST_DATABASE_URL']
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'bin/docker').write_text(FAKE_DOCKER)
    (tmp_path / 'bin/docker').chmod(0o755)
    v1, v2 = teams_bundle(), teams_bundle()
    next(t for t in v2['teams'] if t['slug'] == 'kommandos')['data']['equipment'].append({'name': 'Test Grenade', 'body': [{'k': 'p', 't': 'Boom.'}]})
    for name, data in (('v1.json', v1), ('v2.json', v2), ('rules.json', rules_bundle())):
        (tmp_path / name).write_text(json.dumps(data))
    backups = tmp_path / 'backups'
    env = {**os.environ, 'PATH': f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}", 'BACKUP_DIR': str(backups), 'LOG': str(tmp_path / 'log'),
           'APP': str(ROOT), 'PY': sys.executable, 'OWNER_URL': url, 'OWNER_USER': urlparse(url).username or '',
           'TEAMS': str(tmp_path / 'v2.json'), 'RULES': str(tmp_path / 'rules.json')}
    def run(*args, **extra):
        return subprocess.run(['sh', str(ROOT / 'scripts/update-reference.sh'), *args], cwd=tmp_path, env={**env, **extra},
                              capture_output=True, text=True, timeout=120)
    def journal():
        with db() as c:
            return c.execute('SELECT action, status, trigger, backup, snapshot, report FROM reference_updates ORDER BY id').fetchall()
    def grenade():
        with db() as c:
            return c.execute("SELECT count(*) FROM reference_search WHERE kind='equipment' AND title='Test Grenade'").fetchone()[0]
    snapshots = lambda: sorted(p.name for p in (backups / 'reference').iterdir() if p.is_dir())

    r = run()
    assert r.returncode == 0, r.stderr
    assert 'Teams: 2 → 2: +0 −0 ~1' in r.stderr and 'reference update: ok' in r.stdout and grenade() == 1
    (action, status, trigger, backup, snapshot, report), = journal()
    assert (action, status, trigger) == ('update', 'ok', 'manual') and pathlib.Path(backup).read_text() == 'PGDMP-fake\n'
    snap = pathlib.Path(snapshot)
    assert snap.parent == backups / 'reference' and (snap / '.applied').exists() and not (snap / 'apply.sql').exists()
    assert json.loads((snap / 'teams-before.json').read_text())['teams'][0]['slug'] == 'kommandos'
    assert report['teams']['changed'][0]['equipment'] == {'added': ['Test Grenade'], 'removed': []}

    r = run(TRIGGER='timer')
    assert r.returncode == 0 and 'nothing changed' in r.stderr, r.stderr
    assert journal()[-1][:3] == ('update', 'unchanged', 'timer') and len(snapshots()) == 1

    r = run('--check', TEAMS=str(tmp_path / 'v1.json'))
    assert r.returncode == 0 and 'would be loaded' in r.stderr and grenade() == 1 and len(journal()) == 2

    r = run('--rollback')
    assert r.returncode == 0, r.stderr
    assert grenade() == 0 and journal()[-1][:2] == ('rollback', 'ok')
    newest = backups / 'reference' / snapshots()[-1]
    assert (newest / 'rollback-of').read_text().strip() == snap.name

    r = run(FAIL='teams')
    assert r.returncode == 1 and 'network is unreachable' in r.stderr and 'nothing was loaded' in r.stderr
    assert journal()[-1][1] == 'failed' and 'fetch-teamdata: network is unreachable' in journal()[-1][5]['error']
    r = run(TEAMS=str(tmp_path / 'rules.json'))
    assert r.returncode == 1 and 'check failed: teams' in r.stderr and grenade() == 0
    assert run('--rollback', '20000101T000000Z').returncode == 1 and run('--bogus').returncode == 2
    assert run(MIN_SHARE='2').returncode == 1 and run(TRIGGER='cron').returncode == 1
    r = run('--status')
    assert r.returncode == 0 and 'rollback of ' + snap.name in r.stdout and 'failed' in r.stdout and 'v9.9.9' in r.stdout
    states = sorted((p / '.failed').exists() for p in (backups / 'reference').iterdir() if p.is_dir())
    assert states.count(True) == 1  # only the latest failed run is kept
    r = run(KEEP_REFERENCE='1', TEAMS=str(tmp_path / 'v2.json'))
    assert r.returncode == 0 and grenade() == 1
    applied = [p.name for p in (backups / 'reference').iterdir() if (p / '.applied').exists()]
    assert len(applied) == 1
