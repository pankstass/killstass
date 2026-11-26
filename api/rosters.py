"""v1.8: roster builder API. Schemas come from team_data (operator import); rosters are private to their owner.
The server is authoritative: every save is validated by api/rosterkit.py and stored with its summary."""
import re
from urllib.parse import quote
from uuid import UUID
from fastapi import Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from . import rosterkit as rk

MAX_ROSTERS = 100

class RosterCreate(core.Op):
    team_slug: str = Field(min_length=2, max_length=64, pattern=r'^[a-z0-9][a-z0-9-]{1,63}$')
    name: str = Field(min_length=1, max_length=80)
    data: dict | None = None

class RosterUpdate(core.Model):
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    data: dict

def schema_row(c, slug):
    r = core.one(c, 'SELECT slug,name,catalog_id,roster_schema,roster_hash FROM team_data WHERE slug=%s AND active', (slug,))
    if not r: core.fail(404, 'team_not_found')
    return r

def checked(schema, data):
    data = data if data is not None else {'format': rk.FORMAT, 'selections': []}
    data = {'format': rk.FORMAT, 'selections': data.get('selections', []), 'notes': str(data.get('notes') or '')[:2000]}
    if schema is None: return data, rk.summary(None, data)
    try: return data, rk.Engine(schema).validate(data)
    except rk.RosterError as e: core.fail(422, str(e))

def own(c, rid, uid, lock=False):
    r = core.one(c, 'SELECT * FROM rosters WHERE id=%s AND user_id=%s' + (' FOR UPDATE' if lock else ''), (str(rid), uid))
    if not r: core.fail(404, 'roster_not_found')
    return r

def public(r, team=None):
    out = {k: r[k] for k in ('id', 'team_slug', 'name', 'data', 'summary', 'version', 'created_at', 'updated_at')}
    if team is not None:
        out['team_name'] = team['name']
        out['stale'] = bool(team['roster_hash'] and r['schema_hash'] != team['roster_hash'])
    return out

@core.app.get('/api/teams/{slug}/roster-schema')
def roster_schema(slug: str, request: Request, u=Depends(core.user)):
    if len(slug) > 64: core.fail(404, 'team_not_found')
    with core.pool.connection() as c: r = schema_row(c, slug)
    if not r['roster_schema']: core.fail(404, 'roster_schema_missing')
    tag = '"' + r['roster_hash'] + '"'
    headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate', 'Vary': 'Cookie'}
    if request.headers.get('if-none-match') == tag: return Response(status_code=304, headers=headers)
    return JSONResponse({'slug': r['slug'], 'name': r['name'], 'catalog_id': r['catalog_id'], 'hash': r['roster_hash'], 'schema': r['roster_schema']}, headers=headers)

@core.app.get('/api/rosters')
def list_rosters(team_id: int | None = None, u=Depends(core.user)):
    with core.pool.connection() as c:
        rows = core.allrows(c, '''SELECT r.id,r.team_slug,t.name AS team_name,t.catalog_id,r.name,r.version,r.updated_at,
            (r.summary->>'valid')::boolean AS valid,(r.summary->>'operatives')::int AS operatives,
            jsonb_array_length(coalesce(r.summary->'errors','[]')) AS errors,
            (t.roster_hash IS NOT NULL AND r.schema_hash IS DISTINCT FROM t.roster_hash) AS stale
            FROM rosters r LEFT JOIN team_data t ON t.slug=r.team_slug
            WHERE r.user_id=%s AND (%s::bigint IS NULL OR t.catalog_id=%s) ORDER BY r.updated_at DESC''', (u['id'], team_id, team_id))
        teams = core.allrows(c, 'SELECT slug,name,catalog_id FROM team_data WHERE active AND roster_schema IS NOT NULL ORDER BY name')
    return {'rosters': rows, 'teams': teams, 'limit': MAX_ROSTERS}

@core.app.post('/api/rosters', status_code=201)
def create_roster(p: RosterCreate, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            team = schema_row(c, p.team_slug)
            if not team['roster_schema']: core.fail(422, 'roster_schema_missing')
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,1))', ('rosters:' + str(u['id']),))
            if core.one(c, 'SELECT count(*) AS n FROM rosters WHERE user_id=%s', (u['id'],))['n'] >= MAX_ROSTERS: core.fail(409, 'roster_limit')
            data, summ = checked(team['roster_schema'], p.data)
            r = core.one(c, '''INSERT INTO rosters(user_id,team_slug,name,data,schema_hash,summary) VALUES(%s,%s,%s,%s,%s,%s)
                RETURNING id''', (u['id'], p.team_slug, p.name.strip(), Jsonb(data), team['roster_hash'], Jsonb(summ)))
            return {'id': str(r['id'])}
        return core.operation(c, u, p, 'roster-create', run)

@core.app.get('/api/rosters/{rid}')
def get_roster(rid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        r = own(c, rid, u['id'])
        team = core.one(c, 'SELECT name,catalog_id,roster_hash FROM team_data WHERE slug=%s', (r['team_slug'],)) or {'name': r['team_slug'], 'catalog_id': None, 'roster_hash': None}
    out = public(r, team); out['catalog_id'] = team['catalog_id']
    return out

@core.app.put('/api/rosters/{rid}')
def update_roster(rid: UUID, p: RosterUpdate, u=Depends(core.user)):
    with core.pool.connection() as c:
        with c.transaction():
            r = own(c, rid, u['id'], True)
            if r['version'] != p.version: core.fail(409, 'version_conflict')
            team = schema_row(c, r['team_slug'])
            data, summ = checked(team['roster_schema'], p.data)
            r = core.one(c, '''UPDATE rosters SET name=%s,data=%s,summary=%s,schema_hash=%s,version=version+1,updated_at=now()
                WHERE id=%s RETURNING *''', (p.name.strip(), Jsonb(data), Jsonb(summ), team['roster_hash'], str(rid)))
    out = public(r, team); out['catalog_id'] = team['catalog_id']
    return out

@core.app.delete('/api/rosters/{rid}')
def delete_roster(rid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        with c.transaction():
            own(c, rid, u['id'], True)
            c.execute('DELETE FROM rosters WHERE id=%s', (str(rid),))
    return {'ok': True}

def filename(name, ext):
    base = re.sub(r'[^\w\- ]+', '', name, flags=re.UNICODE).strip().replace(' ', '_')[:60] or 'roster'
    return f'{base}.{ext}'

def disposition(name, ext):
    """HTTP headers are latin-1: ASCII fallback plus the RFC 6266/5987 UTF-8 form for Cyrillic roster names."""
    full = filename(name, ext)
    stem = re.sub(r'[^A-Za-z0-9_\-]+', '', full[:-len(ext) - 1]).strip('_-')
    ascii_name = f'{stem or "roster"}.{ext}'
    return {'Content-Disposition': f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(full, safe='')}"}

@core.app.get('/api/rosters/{rid}/export')
def export_roster(rid: UUID, format: str = Query('text', pattern='^(text|json|ros|rosz)$'), u=Depends(core.user)):
    with core.pool.connection() as c:
        r = own(c, rid, u['id'])
        team = schema_row(c, r['team_slug'])
    schema = team['roster_schema']
    if schema is None: core.fail(422, 'roster_schema_missing')
    try:
        if format == 'json':
            body = jsonable_encoder({'format': rk.FORMAT, 'team': {'slug': r['team_slug'], 'name': team['name']}, 'name': r['name'],
                                     'catalogue': schema['cat'], 'game_system': schema['gs'], 'data': r['data'],
                                     'summary': rk.Engine(schema).validate(r['data']), 'exported_by': f'KILLSTASS {core.APP_VERSION}'})
            return JSONResponse(body, headers=disposition(r['name'], 'json'))
        if format == 'text':
            return Response(rk.to_text(schema, r['data'], team['name'], r['name']), media_type='text/plain; charset=utf-8')
        if format == 'ros':
            return Response(rk.to_ros(schema, r['data'], r['name'], str(rid)), media_type='application/xml',
                            headers=disposition(r['name'], 'ros'))
        return Response(rk.to_rosz(schema, r['data'], r['name'], str(rid), filename(r['name'], 'ros')), media_type='application/zip',
                        headers=disposition(r['name'], 'rosz'))
    except rk.RosterError as e: core.fail(422, str(e))

def attach(c, u, row, roster_id, team_id):
    """Link a match player to one of the actor's rosters (team must match when the team is linked to the catalog)."""
    if roster_id is None:
        c.execute('UPDATE match_players SET roster_id=NULL WHERE id=%s', (row['id'],)); return
    r = core.one(c, 'SELECT r.id,t.catalog_id FROM rosters r LEFT JOIN team_data t ON t.slug=r.team_slug WHERE r.id=%s AND r.user_id=%s', (str(roster_id), u['id']))
    if not r: core.fail(422, 'roster_not_found')
    if r['catalog_id'] is not None and team_id is not None and r['catalog_id'] != team_id: core.fail(422, 'roster_team_mismatch')
    c.execute('UPDATE match_players SET roster_id=%s WHERE id=%s', (str(roster_id), row['id']))
