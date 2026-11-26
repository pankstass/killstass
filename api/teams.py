"""v1.7: read-only team & operative reference (data imported by the operator, see api/teamdata.py).
v1.8: has_roster tells the client that the roster builder can use this team.
v1.13: team_size — the number of operatives of the team's composition, for the match setup when no roster is
attached; derived from the imported data (the selection text and the roster schema), given only when both agree."""
import json
import re
from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from . import main as core

# v1.9: keyword -> faction family for the generated emblem colour (first match wins: GSC before Tyranids).
FACTIONS = (('GENESTEALER CULT', 'gsc'), ('TYRANID', 'tyranid'), ('NECRON', 'necron'), ('ORK', 'ork'),
            ("T'AU EMPIRE", 'tau'), ('T\u2019AU EMPIRE', 'tau'), ('LEAGUES OF VOTANN', 'votann'), ('AELDARI', 'aeldari'),
            ('CHAOS', 'chaos'), ('IMPERIUM', 'imperium'))


def faction(keywords):
    have = {str(k).upper() for k in keywords or ()}
    return next((f for k, f in FACTIONS if k in have), 'unaligned')


# ---- v1.13: the operative count of a team's composition ----
COUNT = re.compile(r'^(\d+) ')
LEADER_LINE = re.compile(r"^[A-Z\-’' ]*operative with")
VARIES = re.compile(r'\bcounts? as\b|instead of selecting', re.I)


def selection_size(selection):
    """Operatives listed by the selection text: «1 … operative», «9 … operatives selected from …», «Every … in the
    following list» (its lines, each «N NAME»), a leader line without a number («SHAS'VRE with …»)."""
    total = 0
    for s in selection if isinstance(selection, list) else ():
        body = [x for x in s.get('body') or () if isinstance(x, dict)] if isinstance(s, dict) else []
        if body and body[0].get('k') in ('lore', 'p') and LEADER_LINE.match(str(body[0].get('t', ''))): total += 1
        for i, x in enumerate(body):
            text = str(x.get('t', ''))
            if x.get('k') != 'li': continue
            m = COUNT.match(text)
            if m: total += int(m.group(1))
            elif text.startswith('Every'):
                for y in body[i + 1:]:
                    if y.get('k') == 'li': break
                    if y.get('k') == 'li2':
                        n = COUNT.match(str(y.get('t', '')))
                        total += int(n.group(1)) if n else 1
    return total or None


def schema_size(schema):
    """Operatives required by the roster schema: the Operative category with min = max selections, plus a leader
    outside it and the categories with a fixed number of their own entries."""
    if not isinstance(schema, dict): return None
    cats = [x for x in (schema.get('force') or {}).get('cats') or () if isinstance(x, dict)]
    root = [x for x in schema.get('root') or () if isinstance(x, dict)]
    names = schema.get('cats') or {}

    def limit(fc, kind):
        v = [x.get('v') for x in fc.get('con') or () if isinstance(x, dict) and x.get('f') == 'selections' and x.get('t') == kind]
        return int(v[0]) if v and isinstance(v[0], (int, float)) else None
    ops = [fc for fc in cats if fc.get('n') == 'Operative']
    if not ops or limit(ops[0], 'min') is None or limit(ops[0], 'min') != limit(ops[0], 'max'): return None
    n, tg = limit(ops[0], 'min'), ops[0].get('tg')
    leader = [e for e in root if e.get('t') in ('model', 'unit') and tg not in (e.get('cat') or ())
              and any(names.get(x) == 'Leader' for x in e.get('cat') or ())]
    if leader or any(fc.get('n') == 'Leader' for fc in cats): n += 1
    for fc in cats:
        if fc.get('n') in ('Operative', 'Leader'): continue
        lo, hi = limit(fc, 'min'), limit(fc, 'max')
        if lo and lo == hi:
            own = [e for e in root if fc.get('tg') in (e.get('cat') or ())]
            if own and all(tg not in (e.get('cat') or ()) for e in own): n += lo
    return n


def composition(selection, schema):
    """(size, varies): the size when both sources agree (1..40), else None; varies — the composition rules allow
    another count (selections that count as two or as half, ploys instead of operatives)."""
    a, b = selection_size(selection), schema_size(schema)
    if not a or a != b or not 1 <= a <= 40: return None, False
    text = ' '.join(str(x.get('t', '')) for s in selection for x in (s.get('body') or ()) if isinstance(x, dict))
    return a, bool(VARIES.search(text))


_SIZES = {}  # slug:content_hash:roster_hash -> (size, varies); the data changes only with an import


def _key(r):
    return f"{r['slug']}:{r['content_hash']}:{r['rh']}"


def sizes(c, rows):
    """Composition sizes of team_data rows (slug, content_hash, rh), computed once per imported version."""
    missing = [r['slug'] for r in rows if _key(r) not in _SIZES]
    if missing:
        for x in core.allrows(c, '''SELECT slug,content_hash,coalesce(roster_hash,'') AS rh,data->'selection' AS selection,
            roster_schema FROM team_data WHERE active AND slug=ANY(%s)''', (missing,)):
            _SIZES[_key(x)] = composition(x['selection'], x['roster_schema'])
    return {r['slug']: _SIZES.get(_key(r), (None, False)) for r in rows}


def size_of(c, catalog_id):
    """The composition size of the team linked to a catalog team (the first by name, like the client), or None."""
    if catalog_id is None: return None
    r = core.one(c, '''SELECT slug,content_hash,coalesce(roster_hash,'') AS rh FROM team_data
        WHERE active AND catalog_id=%s ORDER BY name LIMIT 1''', (catalog_id,))
    return sizes(c, [r])[r['slug']][0] if r else None


def operative_count(c, roster_id, team_id, manual=False, typed=None):
    """(count, source) of a match player, decided by the server: the attached roster (its summary), else the team's
    composition, else the typed number; a typed number wins only when the player chose to type it in (manual)."""
    if manual and typed: return typed, 'manual'
    if roster_id is not None:
        r = core.one(c, "SELECT (summary->>'operatives')::int AS n FROM rosters WHERE id=%s", (str(roster_id),))
        if r and r['n'] and 1 <= r['n'] <= 40: return r['n'], 'roster'
    n = size_of(c, team_id)
    if n: return n, 'team'
    return typed, ('manual' if typed else None)


def refresh_counts(c, mid):
    """Counts taken from a roster or a team follow them (the shared setup may change the opponent's team, a roster
    may be edited before the start)."""
    for p in core.allrows(c, 'SELECT id,team_id,roster_id,operative_count,operative_source FROM match_players WHERE match_id=%s', (str(mid),)):
        if p['operative_source'] not in ('roster', 'team'): continue
        n, source = operative_count(c, p['roster_id'], p['team_id'])
        if (n, source) != (p['operative_count'], p['operative_source']):
            c.execute('UPDATE match_players SET operative_count=%s,operative_source=%s WHERE id=%s', (n, source, p['id']))


@core.app.get('/api/teams')
def teams(u=Depends(core.user)):
    with core.pool.connection() as c:
        rows = core.allrows(c, '''SELECT slug,name,catalog_id,data->'archetypes' AS archetypes,
            jsonb_array_length(data->'operatives') AS operatives, imported_at, roster_schema IS NOT NULL AS has_roster,
            coalesce((SELECT array_agg(DISTINCT k) FROM jsonb_array_elements(data->'operatives') o,
              jsonb_array_elements_text(CASE WHEN jsonb_typeof(o->'keywords')='array' THEN o->'keywords' ELSE '[]' END) k),
              '{}') AS keywords, content_hash, coalesce(roster_hash,'') AS rh
            FROM team_data WHERE active ORDER BY name''')
        size = sizes(c, rows)
        for r in rows:
            r['faction'] = faction(r.pop('keywords'))
            r['team_size'], r['team_size_varies'] = size[r['slug']]
            del r['content_hash'], r['rh']
        imp = core.one(c, 'SELECT imported_at,built_at,sources,teams,operatives FROM team_data_imports ORDER BY id DESC LIMIT 1')
    return {'teams': rows, 'import': imp}

@core.app.get('/api/teams/{slug}')
def team(slug: str, request: Request, u=Depends(core.user)):
    if len(slug) > 64: core.fail(404, 'team_not_found')
    with core.pool.connection() as c:
        r = core.one(c, '''SELECT slug,name,catalog_id,data,sources,content_hash,imported_at,roster_schema IS NOT NULL AS has_roster,
            coalesce(roster_hash,'') AS roster_hash FROM team_data WHERE slug=%s AND active''', (slug,))
    if not r: core.fail(404, 'team_not_found')
    tag = '"' + r.pop('content_hash') + r.pop('roster_hash')[:16] + '"'
    headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate', 'Vary': 'Cookie'}
    if request.headers.get('if-none-match') == tag: return Response(status_code=304, headers=headers)
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(jsonable_encoder(r), headers=headers)
