"""v1.14 (Game Sequence, step 2): equipment and the command points of the start.

Each player secretly selects up to four equipment options (universal or of their faction, each option once) before
the battle; the selections are revealed simultaneously when the match starts and then each player gains 2CP.
Options come from the team's roster schema (BSData «Equipment Reference»: Universal Equipment and Faction
Equipment, with unique actions and weapon profiles); a team without a schema gets the universal options of another
team's schema and its faction options from the team reference (kt-datacards). The server builds what is stored
(the client sends only keys), so the board, the calculator and the history show the text as played."""
import re
from uuid import UUID
from fastapi import Depends, Query
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from . import tracker

EQUIP_MAX = 4
START_CP = 2
GROUPS = {'universal equipment': 'universal', 'faction equipment': 'faction'}
TEXT_MAX = 4000
_UNIVERSAL = {}


class EquipmentChoice(core.Op):
    version: int = Field(ge=1)
    slot: int | None = Field(default=None, ge=1, le=2)
    keys: list[str] = Field(default_factory=list, max_length=EQUIP_MAX)


def _slug(name):
    return re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')[:60] or 'item'


def _item(node, group, P):
    """One equipment option of the schema: its profiles in order (equipment text, unique actions, abilities) and weapons."""
    name = str(node.get('n', '')).strip()[:120]
    rules, weapons = [], []
    for pid in node.get('p', []):
        pr = P.get(pid)
        if not pr:
            continue
        if pr.get('t') == 'Weapons':
            weapons.append(tracker.weapon_profile(pr))
            continue
        kind = {'Unique Actions': 'action', 'Abilities': 'ability'}.get(pr.get('t'), 'equipment')
        rules.append({'name': str(pr.get('n', ''))[:120], 'type': kind, 'text': tracker.profile_text(pr)[:TEXT_MAX]})
    return {'key': ('u:' if group == 'universal' else 'f:') + _slug(name), 'name': name, 'group': group,
            'rules': rules[:8], 'weapons': weapons[:6]}


def schema_items(schema):
    """Options of a roster schema, universal first (schema order)."""
    if not schema:
        return []
    P = schema.get('profiles', {})
    out = []

    def walk(node, group=None, depth=0):
        if depth > 6:
            return
        for ch in node.get('ch', []):
            g = GROUPS.get(str(ch.get('n', '')).strip().lower())
            if ch.get('t') == 'group' and g:
                walk(ch, g, depth + 1)
            elif group and ch.get('t') in ('upgrade', 'model') and ch.get('n'):
                out.append(_item(ch, group, P))
            elif ch.get('t') == 'group':
                walk(ch, group, depth + 1)
    for root in schema.get('root', []):
        if 'equipment' in str(root.get('n', '')).lower():
            walk(root)
    seen, items = set(), []
    for it in sorted(out, key=lambda x: x['group'] != 'universal'):
        if it['key'] not in seen:
            seen.add(it['key'])
            items.append(it)
    return items


def _body_text(body):
    return '\n'.join(str(b.get('t', '')) for b in (body or []) if b.get('k') != 'lore' and b.get('t'))[:TEXT_MAX]


def universal(c):
    """Universal options of the first active team with a schema (the same in every Kill Team 2024 catalogue)."""
    r = core.one(c, '''SELECT slug,coalesce(roster_hash,'') AS rh FROM team_data WHERE active AND roster_schema IS NOT NULL
        AND roster_schema::text LIKE '%%Universal Equipment%%' ORDER BY slug LIMIT 1''')
    if not r:
        return []
    key = r['slug'] + ':' + r['rh']
    if key not in _UNIVERSAL:
        s = core.one(c, 'SELECT roster_schema FROM team_data WHERE slug=%s AND active', (r['slug'],))
        _UNIVERSAL.clear()
        _UNIVERSAL[key] = [i for i in schema_items(s['roster_schema']) if i['group'] == 'universal']
    return _UNIVERSAL[key]


def options(c, team_id):
    """Equipment options of a catalog team: universal, then faction (schema, else the team reference)."""
    team = tracker.team_row(c, team_id)
    items = schema_items(team['roster_schema']) if team else []
    if not any(i['group'] == 'universal' for i in items):
        items = universal(c) + items
    if team and not any(i['group'] == 'faction' for i in items):
        for e in (team['data'] or {}).get('equipment', [])[:12]:
            if e.get('name'):
                name = str(e['name'])[:120]
                items.append({'key': 'f:' + _slug(name), 'name': name, 'group': 'faction',
                              'rules': [{'name': name, 'type': 'equipment', 'text': _body_text(e.get('body'))}], 'weapons': []})
    return items


def resolve(c, team_id, keys):
    """Stored copies of the selected options, in the player's order; ValueError for unknown or repeated keys."""
    if len(keys) > EQUIP_MAX:
        raise ValueError('equipment_limit')
    if len(set(keys)) != len(keys):
        raise ValueError('equipment_repeat')
    by_key = {i['key']: i for i in options(c, team_id)}
    if any(k not in by_key for k in keys):
        raise ValueError('equipment_unknown')
    return [by_key[k] for k in keys]


def suggested(c, player, opts):
    """Options found in the player's attached roster (its equipment selections), for a first choice."""
    if not player.get('roster_id'):
        return []
    names = {str(n).strip().lower() for n in tracker.roster_build(c, player).get('other', [])}
    return [i['key'] for i in opts if i['name'].lower() in names][:EQUIP_MAX]


def visible(m, p, uid):
    """The opponent's equipment is secret until the start (a hot-seat guest's too: the device is passed)."""
    return m['status'] != 'setup' or p.get('user_id') == uid


def redact(m, uid):
    for p in m['players']:
        p['equipment_count'] = len(p.get('equipment') or [])
        if not visible(m, p, uid):
            p['equipment'] = []


def grant(c, m, u, tp, gains, action='cp_grant'):
    """Add CP to both players' state at turning point max(tp,1), once per step (match_cp_grants); audited.
    The start (tp 0) is silently not repeated; a repeated Ready step answers 409."""
    mid = str(m['id'])
    if core.one(c, 'SELECT 1 FROM match_cp_grants WHERE match_id=%s AND turning_point=%s', (mid, tp)):
        if tp == 0:
            return
        core.fail(409, 'cp_granted')
    at = max(tp, 1)
    before, after, rows = {}, {}, []
    for p in core.allrows(c, 'SELECT id,slot FROM match_players WHERE match_id=%s ORDER BY slot', (mid,)):
        own = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (p['id'], at))
        prev = own or core.one(c, '''SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point<%s
            ORDER BY turning_point DESC LIMIT 1''', (p['id'], at))
        old = prev['cp'] if prev else 0
        new = min(99, old + gains.get(p['slot'], 0))
        c.execute('''INSERT INTO turning_point_states(player_id,turning_point,cp) VALUES(%s,%s,%s)
            ON CONFLICT(player_id,turning_point) DO UPDATE SET cp=excluded.cp''', (p['id'], at, new))
        before[str(p['id'])], after[str(p['id'])] = old, new
        if own:
            rows.append(p['id'])
    c.execute('INSERT INTO match_cp_grants(match_id,turning_point,gains,granted_by) VALUES(%s,%s,%s,%s)',
              (mid, tp, Jsonb({str(k): v for k, v in gains.items()}), u['id']))
    core.audit(c, mid, u, action, {'cp': before, 'rows': rows},
               {'turning_point': tp, 'cp': after, 'gains': {str(k): v for k, v in gains.items()}})


def on_start(c, m, u):
    """At the start (Kill Team 2024): re-check the selections against the teams as they are now, reveal them
    (one audit entry with the names) and give each player 2CP."""
    if m['edition'] != '2024':
        return
    shown = {}
    for p in core.allrows(c, 'SELECT id,slot,team_id,equipment FROM match_players WHERE match_id=%s ORDER BY slot', (str(m['id']),)):
        keys = [i.get('key') for i in (p['equipment'] or []) if isinstance(i, dict)]
        by_key = {i['key']: i for i in options(c, p['team_id'])} if keys else {}
        items = [by_key[k] for k in keys if k in by_key][:EQUIP_MAX]
        c.execute('UPDATE match_players SET equipment=%s WHERE id=%s', (Jsonb(items), p['id']))
        shown[str(p['slot'])] = [i['name'] for i in items]
    if any(shown.values()):
        core.audit(c, m['id'], u, 'equipment_reveal', {}, {'equipment': shown})
    grant(c, m, u, 0, {1: START_CP, 2: START_CP}, 'cp_start')


def _target(c, m, u, slot):
    p = core.actor_player(c, m, u, slot)
    if not p:
        core.fail(403, 'slot_forbidden')
    return p


@core.app.get('/api/matches/{mid}/equipment')
def equipment_get(mid: UUID, slot: int | None = Query(None, ge=1, le=2), u=Depends(core.user)):
    """Options of the player's team, the saved selection and the equipment of the attached roster (own slots only)."""
    with core.pool.connection() as c:
        m = core.member(c, mid, u['id'])
        p = _target(c, m, u, slot)
        opts = options(c, p['team_id']) if p['team_id'] else []
        return {'slot': p['slot'], 'team_id': p['team_id'], 'max': EQUIP_MAX, 'edition': m['edition'],
                'options': opts, 'selected': [i.get('key') for i in (p['equipment'] or [])],
                'suggested': suggested(c, p, opts) if opts else []}


@core.app.put('/api/matches/{mid}/equipment')
def equipment_put(mid: UUID, p: EquipmentChoice, u=Depends(core.user)):
    """Save the secret selection (setup only). The audit records how many options, never which ones."""
    with core.pool.connection() as c:
        def run():
            m = core.member(c, mid, u['id'], True)
            core.version(m, p.version)
            if m['status'] != 'setup':
                core.fail(409, 'equipment_closed')
            if m['edition'] != '2024':
                core.fail(422, 'equipment_edition')
            row = _target(c, m, u, p.slot)
            if not row['team_id']:
                core.fail(422, 'team_required')
            try:
                items = resolve(c, row['team_id'], [str(k)[:80] for k in p.keys])
            except ValueError as e:
                core.fail(422, str(e))
            c.execute('UPDATE match_players SET equipment=%s WHERE id=%s', (Jsonb(items), row['id']))
            core.audit(c, mid, u, 'equipment', {}, {'slot': row['slot'], 'count': len(items)})
            return {'ok': True, 'count': len(items)}
        return core.operation(c, u, p, 'equipment:' + str(mid), run)
