"""v1.9: import BattleScribe / New Recruit rosters (.ros XML or zipped .rosz) as KILLSTASS rosters.

The team is found by the force's catalogue id (then catalogue name, then an explicit team). Selections
are mapped onto the team's roster schema by BattleScribe entry path, then by its last id segment, then
by name; unknown entries are skipped and reported back. The result is validated like every save
(api/rosterkit.py), so an imported roster can be fixed in the builder. Files are parsed defensively:
upload, zip member and uncompressed size caps, and any DOCTYPE/ENTITY declaration is refused."""
import base64
import binascii
import io
import secrets
import zipfile
import xml.etree.ElementTree as ET
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from . import rosters
from . import rosterkit as rk

MAX_FILE = 700 * 1024
MAX_XML = 4 * 1024 * 1024
ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'


class RosterImport(core.Op):
    filename: str = Field(min_length=1, max_length=200)
    data_b64: str = Field(min_length=4, max_length=1000000)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    team_slug: str | None = Field(default=None, min_length=2, max_length=64, pattern=r'^[a-z0-9][a-z0-9-]{1,63}$')


def local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def kids(el, name):
    return [x for x in el if local(x.tag) == name]


def decode(text):
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        core.fail(422, 'import_invalid')
    if len(raw) > MAX_FILE:
        core.fail(413, 'import_too_large')
    if raw[:2] != b'PK':
        return raw
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            items = [i for i in z.infolist() if not i.is_dir()]
            if not items or len(items) > 8:
                core.fail(422, 'import_invalid')
            item = next((i for i in items if i.filename.lower().endswith('.ros')), items[0])
            if item.file_size > MAX_XML:
                core.fail(413, 'import_too_large')
            with z.open(item) as f:
                xml = f.read(MAX_XML + 1)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError, ValueError):
        core.fail(422, 'import_invalid')
    if len(xml) > MAX_XML:
        core.fail(413, 'import_too_large')
    return xml


def parse(raw):
    low = raw.lower()
    if b'<!doctype' in low or b'<!entity' in low:
        core.fail(422, 'import_invalid')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        core.fail(422, 'import_invalid')
    if local(root.tag) != 'roster':
        core.fail(422, 'import_not_roster')
    return root


def forces(root):
    out = []
    def walk(el):
        for fs in kids(el, 'forces'):
            for f in kids(fs, 'force'):
                out.append(f)
                walk(f)
    walk(root)
    return out


def find_team(c, force, slug):
    if slug:
        return rosters.schema_row(c, slug)
    cid, cname = force.get('catalogueId') or '', (force.get('catalogueName') or '').strip().lower()
    for r in core.allrows(c, 'SELECT slug,name,catalog_id,roster_schema,roster_hash FROM team_data WHERE active AND roster_schema IS NOT NULL ORDER BY slug'):
        cat = r['roster_schema'].get('cat') or {}
        if cid and cat.get('id') == cid:
            return r
    for r in core.allrows(c, 'SELECT slug,name,catalog_id,roster_schema,roster_hash FROM team_data WHERE active AND roster_schema IS NOT NULL ORDER BY slug'):
        if cname and ((r['roster_schema'].get('cat') or {}).get('n', '').strip().lower() == cname or r['name'].strip().lower() == cname):
            return r
    core.fail(422, 'import_team_unknown')


def convert(schema, force):
    eng = rk.Engine(schema)
    skipped, total = [], [0]

    def mapped(node, elements, depth):
        opts = eng.options(node)
        last, names = {}, {}
        for k, (n, _) in opts.items():
            last.setdefault(k.split('::')[-1], k)
            names.setdefault(n['n'].strip().lower(), k)
        out = []
        for el in elements:
            entry, name = el.get('entryId') or '', (el.get('name') or '').strip()
            key = entry if entry in opts else last.get(entry.split('::')[-1]) or names.get(name.lower())
            if not key:
                skipped.append(name[:80] or entry[-19:])
                continue
            total[0] += 1
            if total[0] > rk.MAX_SELECTIONS or depth > rk.MAX_DEPTH:
                core.fail(422, 'roster_too_large')
            try:
                number = max(1, min(rk.MAX_NUMBER, int(el.get('number') or 1)))
            except ValueError:
                number = 1
            inner = [s for sels in kids(el, 'selections') for s in kids(sels, 'selection')]
            item = {'uid': ''.join(secrets.choice(ALPHABET) for _ in range(10)), 'key': key, 'n': number,
                    'sel': mapped(opts[key][0], inner, depth + 1)}
            custom = (el.get('customName') or '').strip()[:80]
            if custom:
                item['name'] = custom
            out.append(item)
        return out
    top = [s for sels in kids(force, 'selections') for s in kids(sels, 'selection')]
    return mapped(None, top, 1), skipped


@core.app.post('/api/rosters/import', status_code=201)
def import_roster(p: RosterImport, u=Depends(core.user)):
    root = parse(decode(p.data_b64))
    found = forces(root)
    if not found:
        core.fail(422, 'import_not_roster')
    notes = ''.join(x.text or '' for x in kids(root, 'customNotes')).strip()[:2000]
    with core.pool.connection() as c:
        def run():
            team = find_team(c, found[0], p.team_slug)
            if not team['roster_schema']:
                core.fail(422, 'roster_schema_missing')
            selections, skipped = convert(team['roster_schema'], found[0])
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,1))', ('rosters:' + str(u['id']),))
            if core.one(c, 'SELECT count(*) AS n FROM rosters WHERE user_id=%s', (u['id'],))['n'] >= rosters.MAX_ROSTERS:
                core.fail(409, 'roster_limit')
            data, summ = rosters.checked(team['roster_schema'], {'selections': selections, 'notes': notes})
            name = (p.name or root.get('name') or p.filename.rsplit('.', 1)[0] or team['name']).strip()[:80] or team['name'][:80]
            r = core.one(c, '''INSERT INTO rosters(user_id,team_slug,name,data,schema_hash,summary) VALUES(%s,%s,%s,%s,%s,%s)
                RETURNING id''', (u['id'], team['slug'], name, Jsonb(data), team['roster_hash'], Jsonb(summ)))
            return {'id': str(r['id']), 'team_slug': team['slug'], 'name': name, 'imported': sum(1 for _ in walk(selections)),
                    'skipped': skipped[:50], 'forces': len(found), 'valid': summ.get('valid'), 'operatives': summ.get('operatives')}
        return core.operation(c, u, p, 'roster-import', run)


def walk(items):
    for it in items:
        yield it
        yield from walk(it.get('sel', []))
