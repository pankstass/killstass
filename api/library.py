"""v1.11: rules reference ("Справочник") — one search over the general rules (warhammer-oracle: weapon rules,
phase overview), the KILLSTASS catalog (missions, Tac Ops, rule summaries) and game sequence, and the imported
teams (BSData, kt-datacards: teams, operatives, faction rules, ploys, equipment); the library of general rules for
browsing and offline search; the "up to date as of" status. Index: materialized view reference_search (013)."""
import hashlib
import json
import os
import re
from fastapi import Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from . import main as core

GROUPS = {'rules': ('weapon_rule', 'rule', 'sequence', 'phase'), 'ops': ('mission', 'tac_op'), 'teams': ('team', 'faction_rule'),
          'operatives': ('operative',), 'ploys': ('ploy',), 'equipment': ('equipment',)}
TEAM_KINDS = {'team', 'operative', 'faction_rule', 'ploy', 'equipment'}
CATALOG_KINDS = ('mission', 'tac_op', 'rule', 'sequence')
# The subtitle of these is the name in the other language (Sweep & Clear / «Зачистка», Lethal x+ / «Смертоносное x+»)
# and they have aliases: it is matched like the title. Of the others it is a description (keywords, archetypes, phase).
NAMED = ['weapon_rule', 'phase', 'mission', 'tac_op', 'rule']
WORD = re.compile(r'[^\W_]+')


def fold(s):
    """Same folding as ks_fold() in SQL: lower case, «ё» -> «е», single spaces."""
    return re.sub(r'\s+', ' ', str(s or '').lower().replace('ё', 'е')).strip()


def like(s):
    return '%' + s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def snippet(text, words, width=260):
    t = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(t) <= width: return t
    low = fold(t) if len(fold(t)) == len(t) else t.lower()
    hits = [p for p in (low.find(w) for w in words) if p >= 0]
    start = max(0, min(hits) - width // 3) if hits else 0
    if start:
        space = t.find(' ', start)
        start = space + 1 if 0 <= space < start + 20 else start
    end = min(len(t), start + width)
    if end < len(t):
        space = t.rfind(' ', start, end)
        end = space if space > start + width // 2 else end
    return ('…' if start else '') + t[start:end].strip() + ('…' if end < len(t) else '')


# English catalog texts live with the web client (web/i18n/catalog.en.json); the English search reads them too.
_en = {}
def english():
    if 'docs' not in _en:
        try:
            with open(os.path.join(core.WEB, 'i18n', 'catalog.en.json'), encoding='utf-8') as f: data = json.load(f)
        except (OSError, ValueError): data = {}
        _en['docs'] = {'catalog': data.get('catalog', {}), 'sequence': data.get('sequence', {})}
    return _en['docs']


def name_score(name, f):
    """Exact name 10, the name starts with the query 6, a word of it does 4, contains it 3 (as in SQL)."""
    n = fold(name)
    return 10 if n == f else 6 if n.startswith(f) else 4 if ' ' + f in n else 3 if f in n else 0


def name_sql(col):
    return (f'(CASE WHEN {col} = %(f)s THEN 10 WHEN {col} LIKE %(prefix)s THEN 6 WHEN {col} LIKE %(word)s THEN 4 '
            f'WHEN {col} LIKE %(like)s THEN 3 ELSE 0 END)')


def py_score(f, words, title, text):
    """English catalog texts: about the SQL score of a named entry (name, similarity, matched words, text)."""
    tf, xf = fold(title), fold(text)
    score = name_score(tf, f)
    tokens = WORD.findall(tf + ' ' + xf)
    hits = sum(any(t.startswith(w) for t in tokens) for w in words)
    if score == 0 and f not in xf and (not words or hits < len(words)): return None
    return score + (2 if f in tf else 0) + 2 * hits / max(len(words), 1) + (1 if f in xf else 0)


def result(r, words):
    team = r['kind'] in TEAM_KINDS
    out = {'id': r['id'], 'kind': r['kind'], 'title': r['title'], 'subtitle': r['subtitle'], 'code': r['code'],
           'verification': r['verification'], 'source_url': r['source_url']}
    if team:
        out['team'] = {'slug': r['team_slug'], 'name': r['team_name'], 'label': r['team_label']}
        out['link'] = '#teams/' + r['team_slug'] + '/' + r['tab'] + ('/' + r['anchor'] if r['anchor'] else '')
        out['snippet'] = snippet(r['body'], words)
    else:
        out['text'] = (r['body'] or '')[:3000]
        if r.get('body_ru'): out['text_ru'] = r['body_ru'][:3000]
    return out


@core.app.get('/api/reference/search')
def search(q: str = Query('', max_length=120), kind: str = Query('', pattern='^(|rules|ops|teams|operatives|ploys|equipment)$'),
           team: str = Query('', max_length=64, pattern=r'^(|[a-z0-9][a-z0-9-]{1,63})$'), lang: str = Query('ru', pattern='^(ru|en)$'),
           limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=500), u=Depends(core.user)):
    f = fold(q)
    words = [w[:40] for w in WORD.findall(f)][:8]
    if len(f) < 2 and not kind and not team: core.fail(422, 'search_query_short')
    kinds = list(GROUPS[kind]) if kind else None
    if team: kinds = [k for k in (kinds or TEAM_KINDS) if k in TEAM_KINDS]
    en = lang == 'en'
    params = {'f': f, 'prefix': like(f)[1:], 'word': '% ' + like(f)[1:], 'like': like(f), 'tsq': ' & '.join(w + ':*' for w in words),
              'kinds': kinds, 'team': team or None, 'en': en, 'named': NAMED, 'limit': limit + offset}
    filters = '''(%(kinds)s::text[] IS NULL OR kind = ANY(%(kinds)s)) AND (%(team)s::text IS NULL OR team_slug = %(team)s)
                 AND (NOT %(en)s OR kind <> ALL(ARRAY['mission','tac_op','rule','sequence']))'''
    with core.pool.connection() as c:
        if f:
            rows = core.allrows(c, f'''SELECT * FROM (
              SELECT id,kind,title,subtitle,team_slug,team_name,team_label,tab,anchor,code,body,body_ru,verification,source_url,rank,sort,
                CASE WHEN kind = ANY(%(named)s) THEN greatest({name_sql('title_f')}, {name_sql('sub_f')}, {name_sql('alias_f')})
                  + 2 * greatest(word_similarity(%(f)s, title_f), word_similarity(%(f)s, sub_f), word_similarity(%(f)s, alias_f))
                ELSE {name_sql('title_f')} + 2 * greatest(word_similarity(%(f)s, title_f), 0.8 * word_similarity(%(f)s, sub_f))
                  + (CASE WHEN sub_f = %(f)s THEN 5 WHEN sub_f LIKE %(prefix)s THEN 3 WHEN sub_f LIKE %(like)s THEN 2 ELSE 0 END) END
                + 4 * ts_rank_cd(doc, q.tsq, 32) + CASE WHEN text_f LIKE %(like)s THEN 1 ELSE 0 END
                + CASE WHEN rank <= 2 THEN 1.5 ELSE 0 END AS score
              FROM reference_search, (SELECT to_tsquery('russian', %(tsq)s) AS tsq) q
              WHERE {filters} AND (doc @@ q.tsq OR text_f LIKE %(like)s OR word_similarity(%(f)s, title_f) >= 0.5)) s
              ORDER BY score DESC, rank, sort, title LIMIT %(limit)s''', params)
            total = core.one(c, f'''SELECT count(*)::int AS n FROM reference_search, (SELECT to_tsquery('russian', %(tsq)s) AS tsq) q
              WHERE {filters} AND (doc @@ q.tsq OR text_f LIKE %(like)s OR word_similarity(%(f)s, title_f) >= 0.5)''', params)['n']
        else:  # browsing a section or a team
            rows = core.allrows(c, f'''SELECT *, 0 AS score FROM reference_search WHERE {filters}
              ORDER BY rank, team_name NULLS FIRST, sort, title LIMIT %(limit)s''', params)
            total = core.one(c, f'SELECT count(*)::int AS n FROM reference_search WHERE {filters}', params)['n']
        if en and not team and (not kinds or set(kinds) & set(CATALOG_KINDS)):
            # English: catalog and sequence rows are searched in their English texts
            tr = english()
            for r in core.allrows(c, '''SELECT id,kind,title,subtitle,NULL AS team_slug,NULL AS team_name,NULL AS team_label,NULL AS tab,
                NULL AS anchor,code,body,'' AS body_ru,verification,source_url,rank,sort FROM reference_search
                WHERE kind = ANY(%s)''', ([k for k in (kinds or CATALOG_KINDS) if k in CATALOG_KINDS],)):
                e = tr['sequence' if r['kind'] == 'sequence' else 'catalog'].get(r['code'])
                if not e: continue
                if r['kind'] == 'sequence': r.update(title=e.get('label', r['title']), subtitle=e.get('phase', r['subtitle']), body=e.get('description', r['body']))
                else: r.update(title=e.get('label', r['title']), subtitle=None, body='\n'.join(x for x in (e.get('reveal'), e.get('summary')) if x))
                score = py_score(f, words, r['title'], r['body']) if f else 0
                if score is None: continue
                rows.append({**r, 'score': score + (1.5 if f and r['rank'] <= 2 else 0)}); total += 1
            rows.sort(key=lambda r: (-float(r['score']), r['rank'], r['sort'] or 0, r['title']))
    return {'q': q, 'terms': words, 'total': total, 'offset': offset,
            'results': [result(r, words) for r in rows[offset:offset + limit]]}


def status(c):
    rules = core.one(c, '''SELECT imported_at, built_at, rules, phases, sources->'oracle' AS oracle, jsonb_array_length(warnings) AS warnings
                           FROM rule_imports ORDER BY id DESC LIMIT 1''')
    teams = core.one(c, 'SELECT imported_at, built_at, teams, operatives, sources FROM team_data_imports ORDER BY id DESC LIMIT 1')
    cat = core.one(c, '''SELECT max(retrieved_at) AS retrieved_at, max(rules_version) AS rules_version FROM catalogs
                         WHERE active AND verification='verified' AND kind IN ('mission','tac_op')''')
    last = core.one(c, 'SELECT finished_at, action, status, trigger FROM reference_updates ORDER BY id DESC LIMIT 1')
    checked = core.one(c, "SELECT max(finished_at) AS at FROM reference_updates WHERE status IN ('ok','unchanged')")['at']
    if rules and rules['oracle']:
        o = rules['oracle']
        rules['oracle'] = {k: o.get(k) for k in ('repo', 'tag', 'commit')}
        rules['oracle']['generated_at'] = ((o.get('files') or {}).get('rules') or {}).get('generated_at')
    return {'rules': rules, 'teams': teams, 'catalog': cat if cat and cat['retrieved_at'] else None, 'update': last, 'checked_at': checked}


def compact(rep):
    """Journal report for #admin: counts and names, the failing saved rosters, warnings, the error of a failed run."""
    rep = rep or {}
    t, r, ro = rep.get('teams') or {}, rep.get('rules') or {}, rep.get('rosters') or {}
    out = {'error': rep.get('error'), 'warnings': [str(w) for w in (rep.get('warnings') or [])[:20]]}
    if t: out['teams'] = {**{k: t.get(k) for k in ('before', 'after', 'operatives_before', 'operatives_after', 'provenance_only')},
                          'added': t.get('added', [])[:60], 'removed': t.get('removed', [])[:60],
                          'changed': [x.get('slug') for x in t.get('changed', []) if isinstance(x, dict)][:60]}
    if r: out['rules'] = {k: r.get(k) for k in ('before', 'after')} | {k: (r.get(k) or [])[:60] for k in ('added', 'removed', 'changed')}
    if ro: out['rosters'] = {'checked': ro.get('checked', 0), 'failing': (ro.get('failing') or [])[:50]}
    return out


def updates(c, limit=10):
    rows = core.allrows(c, '''SELECT id, started_at, finished_at, action, status, trigger, backup, snapshot, report
                              FROM reference_updates ORDER BY id DESC LIMIT %s''', (limit,))
    for x in rows: x['report'] = compact(x['report'])
    return rows


@core.app.get('/api/reference/library')
def library(request: Request, u=Depends(core.user)):
    """General rules for browsing and the offline search, with the reference status (ETag: unchanged -> 304)."""
    with core.pool.connection() as c:
        rows = core.allrows(c, '''SELECT code,kind,name,name_ru,aliases,text_en,text_ru,details,verification,source,imported_at
                                  FROM rule_entries WHERE active ORDER BY kind DESC, sort, code''')
        data = jsonable_encoder({'status': status(c), 'rules': rows})
    tag = '"' + hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32] + '"'
    headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate', 'Vary': 'Cookie'}
    if request.headers.get('if-none-match') == tag: return Response(status_code=304, headers=headers)
    return JSONResponse(data, headers=headers)
