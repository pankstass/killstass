"""v1.11: planner of scripts/update-reference.sh — checks the new reference bundles, compares them with the
reference now in the database and writes one SQL script for the database owner (operator tool).

    tar -cf - teams-new.json rules-new.json | python -m api.refupdate plan --action update --trigger manual \\
        --started 2026-11-04T05:00:00Z [--min-share 0.8]  > apply.sql  2> report.txt

Exit codes: 0 — changes found (apply.sql: imports + search index refresh + journal record; psql variables
ks_backup and ks_snapshot name the database backup and the bundle directory); 3 — nothing changed (apply.sql:
the journal record only); 2 — the new data failed the checks (nothing to apply, reason on stderr).
The "before" state is read from the database with the runtime role (read-only): active teams, rules, saved rosters.
Checks: bundle format, provenance (source commits), and — for updates, not rollbacks — that the new bundle keeps at
least --min-share of the teams, operatives and weapon rules now loaded. The report lists added, changed and removed
teams and rules and the saved rosters that pass validation now but would fail with the new roster schemas.
"""
import hashlib, io, json, math, re, sys, tarfile
from datetime import datetime
from . import rosterkit as rk
from . import rulesdata as rd
from . import teamdata as td

SHA = re.compile(r'^[0-9a-f]{40}$')
EXIT_UNCHANGED, EXIT_INVALID = 3, 2


class Invalid(ValueError):
    """The new data is not safe to load."""


def team_hash(t):
    """Content of a team (cards, rules, roster schema) without its provenance: a new upstream commit that leaves the
    team as it was is not a change. Operative card links are cleaned the same way as in api/teamdata.to_sql."""
    data = dict(t['data'])
    data['operatives'] = [{**o, 'card': o.get('card') if str(o.get('card') or '').startswith('https://') else None} for o in data.get('operatives', [])]
    roster = t.get('roster') if isinstance(t.get('roster'), dict) and t['roster'].get('v') == 1 else None
    return hashlib.sha256(json.dumps([data, roster], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def roster_hash(t):
    r = t.get('roster')
    return hashlib.sha256(json.dumps(r, ensure_ascii=False, sort_keys=True).encode()).hexdigest() if isinstance(r, dict) else None


def names(items):
    return [str(x.get('name', '')) for x in (items or []) if isinstance(x, dict)]


def name_diff(old, new):
    a, b = names(old), names(new)
    return {'added': [x for x in b if x not in a][:30], 'removed': [x for x in a if x not in b][:30]}


def operatives(bundle): return sum(len(t['data'].get('operatives', [])) for t in bundle.get('teams', []))


def check_teams(old, new, action, share):
    teams = new.get('teams') or []
    if action == 'rollback' and not teams:
        if not isinstance(new, dict) or new.get('format') not in td.FORMATS: raise Invalid('teams: not a killstass team bundle')
        return teams
    try: td.validate(new)
    except (ValueError, KeyError, TypeError) as e: raise Invalid(f'teams: {e}')
    src = new.get('sources') or {}
    if not all(SHA.match(str((src.get(k) or {}).get('commit', ''))) for k in ('kt_datacards', 'bsdata')):
        raise Invalid('teams: source commits (kt-datacards, BSData) missing')
    if action == 'update' and old.get('teams'):
        if len(teams) < math.ceil(share * len(old['teams'])): raise Invalid(f'teams: {len(teams)} teams instead of {len(old["teams"])} — less than {share:.0%}')
        if operatives(new) < math.ceil(share * operatives(old)): raise Invalid(f'teams: {operatives(new)} operatives instead of {operatives(old)} — less than {share:.0%}')
    return teams


def check_rules(old, new, action, share):
    if not isinstance(new, dict) or new.get('format') != rd.FORMAT: raise Invalid('rules: not a killstass rules bundle')
    entries = new.get('entries') or []
    if action == 'rollback' and not entries: return entries
    try: rd.validate(new)
    except (ValueError, KeyError, TypeError) as e: raise Invalid(f'rules: {e}')
    o = (new.get('sources') or {}).get('oracle') or {}
    if not SHA.match(str(o.get('commit', ''))) or not o.get('tag'): raise Invalid('rules: warhammer-oracle tag and commit missing')
    count = lambda b: sum(e.get('kind') == 'weapon_rule' for e in b.get('entries') or [])
    if action == 'update' and count(old) and count(new) < math.ceil(share * count(old)):
        raise Invalid(f'rules: {count(new)} weapon rules instead of {count(old)} — less than {share:.0%}')
    return entries


def diff_teams(old, new):
    a = {t['slug']: t for t in old.get('teams') or []}
    b = {t['slug']: t for t in new.get('teams') or []}
    changed, provenance = [], 0
    for slug in sorted(set(a) & set(b)):
        if team_hash(a[slug]) == team_hash(b[slug]):
            provenance += json.dumps(a[slug].get('sources') or {}, sort_keys=True) != json.dumps(b[slug].get('sources') or {}, sort_keys=True)
            continue
        x, y = a[slug]['data'], b[slug]['data']
        item = {'slug': slug, 'name': b[slug]['name']}
        for key, fields in (('operatives', ('operatives',)), ('rules', ('faction_rules',)), ('ploys', ('strategy_ploys', 'firefight_ploys')), ('equipment', ('equipment',))):
            d = name_diff(sum((x.get(f) or [] for f in fields), []), sum((y.get(f) or [] for f in fields), []))
            if d['added'] or d['removed']: item[key] = d
        if roster_hash(a[slug]) != roster_hash(b[slug]): item['roster_schema'] = True
        changed.append(item)
    return {'before': len(a), 'after': len(b), 'operatives_before': operatives(old), 'operatives_after': operatives(new),
            'added': sorted(set(b) - set(a)), 'removed': sorted(set(a) - set(b)), 'changed': changed, 'provenance_only': provenance}


def diff_rules(old, new):
    """Old hashes are the stored ones (api/rulesdata.export): a reviewed Russian paraphrase shipped with a new
    KILLSTASS version is a change even when the English rules are the same."""
    a = {e['code']: e for e in old.get('entries') or []}
    if any(not e.get('content_hash') for e in a.values()):
        for r in rd.rows(old, allow_empty=True)[0]: a[r['code']] = {**a[r['code']], 'content_hash': a[r['code']].get('content_hash') or r['content_hash']}
    b = {r['code']: r for r in rd.rows(new, allow_empty=True)[0]} if new.get('entries') else {}
    return {'before': len(a), 'after': len(b), 'added': [b[c]['name'] for c in sorted(set(b) - set(a))],
            'removed': [a[c]['name'] for c in sorted(set(a) - set(b))],
            'changed': [b[c]['name'] for c in sorted(set(a) & set(b)) if a[c]['content_hash'] != b[c]['content_hash']]}


def roster_check(saved, current, new):
    """saved: [{id, name, team_slug, data, owner}]; current/new: {slug: roster schema or None}.
    Rosters valid with the current schema that fail with the new one (or whose team disappears)."""
    engines, failing = {}, []
    def check(schema_set, key, slug, data):
        schema = schema_set.get(slug)
        if not isinstance(schema, dict): return None
        try:
            if (key, slug) not in engines: engines[(key, slug)] = rk.Engine(schema)
            return engines[(key, slug)].validate(data)
        except (rk.RosterError, ValueError, KeyError, TypeError):
            return {'valid': False, 'errors': [{'code': 'malformed'}]}
    for r in saved:
        before = check(current, 'old', r['team_slug'], r['data'])
        if not before or not before['valid']: continue
        after = check(new, 'new', r['team_slug'], r['data'])
        if after is None: after = {'valid': False, 'errors': [{'code': 'team_removed' if r['team_slug'] not in new else 'no_schema'}]}
        if not after['valid']:
            failing.append({'id': str(r['id']), 'name': r['name'], 'team': r['team_slug'], 'owner': r['owner'],
                            'errors': sorted({str(e.get('code')) for e in after['errors']})[:5]})
    return {'checked': len(saved), 'failing': failing[:200]}


def short(d):
    return f"{d['before']} → {d['after']}: +{len(d['added'])} −{len(d['removed'])} ~{len(d['changed'])}"


def report_text(rep, action, trigger):
    out = [f'KILLSTASS reference {action} ({trigger})', 'Teams: ' + short(rep['teams'])]
    def names(d):
        items = ['+' + n for n in d['added']] + ['−' + n for n in d['removed']]
        return ', '.join(items[:8]) + (f' … ({len(items)})' if len(items) > 8 else '')
    for x in rep['teams']['changed'][:40]:
        parts = [f"{k} {names(x[k])}" for k in ('operatives', 'rules', 'ploys', 'equipment') if k in x]
        out.append(f"  ~ {x['slug']}: " + ('; '.join(parts) or 'texts') + ('; roster schema' if x.get('roster_schema') else ''))
    for k in ('added', 'removed'):
        if rep['teams'][k]: out.append(f"  {'+' if k == 'added' else '−'} " + ', '.join(rep['teams'][k]))
    out.append('Rules: ' + short(rep['rules']))
    for k, mark in (('added', '+'), ('changed', '~'), ('removed', '−')):
        if rep['rules'][k]: out.append(f'  {mark} ' + ', '.join(rep['rules'][k]))
    f = rep['rosters']['failing']
    out.append(f"Saved rosters checked: {rep['rosters']['checked']}, would stop passing validation: {len(f)}")
    for r in f[:50]: out.append(f"  ! {r['name']} ({r['team']}, {r['owner']}): {', '.join(r['errors'])}")
    for w in rep['warnings'][:30]: out.append('warning: ' + w)
    return '\n'.join(out) + '\n'


def empty_teams_sql():
    return ("UPDATE team_data SET active=false WHERE active;\n"
            "INSERT INTO team_data_imports(built_at,sources,teams,operatives,warnings) VALUES(NULL,'{}'::jsonb,0,0,'[\"rollback: no teams\"]'::jsonb);")


def plan(teams_old, teams_new, rules_old, rules_new, rosters, action='update', trigger='manual', started=None, share=0.8):
    """-> (changed, sql, report). Raises Invalid when the new data must not be loaded."""
    if action not in ('update', 'rollback') or trigger not in ('manual', 'timer'): raise ValueError('action/trigger')
    if not 0 <= share <= 1: raise ValueError('min share')
    started = datetime.fromisoformat(str(started).replace('Z', '+00:00')).isoformat() if started else None
    check_teams(teams_old, teams_new, action, share)
    check_rules(rules_old, rules_new, action, share)
    rep = {'teams': diff_teams(teams_old, teams_new), 'rules': diff_rules(rules_old, rules_new), 'warnings': []}
    current = {t['slug']: t.get('roster') for t in teams_old.get('teams') or []}
    new = {t['slug']: t.get('roster') for t in teams_new.get('teams') or []}
    rep['rosters'] = roster_check(rosters, current, new)
    t_changed = any(rep['teams'][k] for k in ('added', 'removed', 'changed'))
    r_changed = any(rep['rules'][k] for k in ('added', 'removed', 'changed'))
    # Warnings of the bundles matter only when they are loaded (an unchanged weekly check repeats nothing).
    if t_changed: rep['warnings'] += [str(w) for w in (teams_new.get('warnings') or [])[:20]]
    if r_changed: rep['warnings'] += [str(w) for w in (rules_new.get('warnings') or [])[:20]] + rd.rows(rules_new, allow_empty=True)[1][:20]
    sources = {'teams': teams_new.get('sources') or {}, 'rules': rules_new.get('sources') or {}}
    lit = td.lit
    status = 'ok' if t_changed or r_changed else 'unchanged'
    out = ['SET LOCAL standard_conforming_strings = on;', 'SET LOCAL client_min_messages = warning;']
    if t_changed: out.append(td.to_sql(teams_new).replace(td.REFRESH_SQL + '\n', '') if teams_new.get('teams') else empty_teams_sql())
    if r_changed: out.append(rd.to_sql(rules_new, allow_empty=action == 'rollback').replace(td.REFRESH_SQL + '\n', ''))
    if t_changed or r_changed: out.append(td.REFRESH_SQL)
    files = (":'ks_backup',:'ks_snapshot'" if status == 'ok' else "'',''")
    out.append('INSERT INTO reference_updates(started_at,action,status,trigger,backup,snapshot,sources,report) VALUES('
               f"{lit(started) + '::timestamptz' if started else 'now()'},{lit(action)},{lit(status)},{lit(trigger)},{files},"
               f"{lit(json.dumps(sources, ensure_ascii=False))}::jsonb,{lit(json.dumps(rep, ensure_ascii=False))}::jsonb);")
    out.append(f"SELECT 'reference {action}: {status}';")
    return status == 'ok', '\n'.join(out) + '\n', rep


def read_tar(stream):
    files = {}
    with tarfile.open(fileobj=stream, mode='r|') as tar:
        for m in tar:
            if not m.isfile() or m.name.lstrip('./') not in ('teams-new.json', 'rules-new.json'): continue
            if m.size > td.MAX_BUNDLE: raise Invalid(f'{m.name}: too large')
            files[m.name.lstrip('./')] = json.loads(tar.extractfile(m).read())
    if set(files) != {'teams-new.json', 'rules-new.json'}: raise Invalid('teams-new.json and rules-new.json expected')
    return files['teams-new.json'], files['rules-new.json']


def saved_rosters(conn):
    return [{'id': r[0], 'name': r[1], 'team_slug': r[2], 'data': r[3], 'owner': f'#{r[4]} {r[5]}'} for r in conn.execute(
        'SELECT r.id, r.name, r.team_slug, r.data, u.public_id, u.display_name FROM rosters r JOIN users u ON u.id = r.user_id ORDER BY r.updated_at DESC LIMIT 5000').fetchall()]


def main(argv):
    if len(argv) < 2 or argv[1] != 'plan':
        print(__doc__, file=sys.stderr); return 64
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    action, trigger = opt('--action', 'update'), opt('--trigger', 'manual')
    try:
        teams_new, rules_new = read_tar(sys.stdin.buffer)
        import os, psycopg
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            teams_old, rules_old, rosters = td.export(conn), rd.export(conn), saved_rosters(conn)
        changed, sql, rep = plan(teams_old, teams_new, rules_old, rules_new, rosters, action, trigger, opt('--started', None), float(opt('--min-share', '0.8')))
    except (Invalid, tarfile.TarError, json.JSONDecodeError) as e:
        print(f'check failed: {e}', file=sys.stderr); return EXIT_INVALID
    sys.stdout.write(sql)
    sys.stderr.write(report_text(rep, action, trigger))
    return 0 if changed else EXIT_UNCHANGED


if __name__ == '__main__':
    sys.exit(main(sys.argv))
