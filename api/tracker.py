"""v1.9: operative tracker, undo of the actor's last board change, the opponent's roster after the start.

Tracker commands are idempotent (request_id) but, like the game clock, not tied to matches.version:
frequent wound taps on one phone must not make the other player's next score command fail with
version_conflict. Phones learn about tracker changes through the SSE event `tracker` (sequence = last
tracker audit id). Kills are derived: an operative reaching 0 wounds adds one incapacitated enemy
operative to the opponent's operative_kills at the current turning point (Approved Ops 2025, TP 1-4);
bringing it back (or removing it) takes that kill away again."""
import re
from uuid import UUID
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core
from . import reference
from . import rosterkit as rk

MAX_OPERATIVES = 40
UNDOABLE = ['score', 'kills', 'initiative', 'turn', 'operative', 'cp_grant', 'ploy']  # v1.14: CP of the Ready step, ploys
MUTABLE = ('wounds', 'order_token', 'activated_tp', 'incapacitated_tp')
FULL = ('id', 'player_id', 'position', 'name', 'card', 'stats', 'weapons', 'wounds_max') + MUTABLE
STATS = ('apl', 'move', 'save', 'wounds')
WEAPON = ('name', 'type', 'atk', 'hit', 'dmg', 'wr')


class OperativeCommand(core.Op):
    action: str = Field(pattern='^(populate|add|wounds|order|activate|remove)$')
    slot: int | None = Field(default=None, ge=1, le=2)
    operative_id: int | None = Field(default=None, ge=1)
    delta: int | None = Field(default=None, ge=-99, le=99)
    order: str | None = Field(default=None, pattern='^(engage|conceal)$')
    activated: bool | None = None
    card: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    wounds_max: int | None = Field(default=None, ge=1, le=99)


class Undo(core.Op):
    audit_id: int = Field(ge=1)


def number(v, default=0):
    m = re.search(r'\d+', str(v or ''))
    return int(m.group()) if m else default


def clean_stats(s):
    return {k: str((s or {}).get(k) or '')[:16] for k in STATS}


def clean_weapons(ws):
    out = []
    for w in (ws or [])[:16]:
        if isinstance(w, dict) and w.get('name'):
            out.append({k: str(w.get(k) or '')[:160] for k in WEAPON})
    return out


def weapon_profile(p):
    c = {str(k).upper(): v for k, _, v in p.get('c', [])}
    n = p.get('n') or ''
    return {'name': re.sub(r'^[⌖⚔\ufe0f\s]+', '', n) or n, 'type': 'melee' if n.startswith('⚔') else 'ranged',
            'atk': c.get('ATK', ''), 'hit': c.get('HIT', ''), 'dmg': c.get('DMG', ''), 'wr': c.get('WR', '')}


def team_row(c, team_id):
    return core.one(c, 'SELECT slug,name,data,roster_schema FROM team_data WHERE catalog_id=%s AND active ORDER BY slug LIMIT 1', (team_id,)) if team_id else None


def cards(team):
    return {o['name'].lower(): o for o in ((team or {}).get('data') or {}).get('operatives', []) if o.get('name')}


# v1.14 (Т2): what an operative brings to the table as selected — the profiles of the model and of its selected
# options (each once, in selection order): abilities and other rules, unique actions, keywords. The roster
# editor does the same in the browser (web/rosters.js opRules); print, the board and the opponent's roster use this.
RULES_MAX, TEXT_MAX = 24, 4000
SERVICE_CAT = re.compile(r'^(operative|operatives|requisitioned operatives|configuration)$|^(up to )?(one|two|three|four|five|six|seven|eight|nine|ten)( of)?:?$| or ', re.I)
OWN_TYPES = ('Operative', 'Weapons')


def profile_text(pr):
    c = [(str(k), str(v or '').strip()) for k, _, v in pr.get('c', [])]
    if len(c) == 1:
        return c[0][1][:TEXT_MAX]
    return '\n'.join(f'**{k}:** {v}' for k, v in c if v)[:TEXT_MAX]


def has_rules(node, P, depth=0):
    """Whether a schema entry or anything that can be selected below it carries rule profiles."""
    if any(P.get(pid, {}).get('t') not in (None, *OWN_TYPES) for pid in node.get('p', [])):
        return True
    return depth < 8 and any(has_rules(ch, P, depth + 1) for ch in node.get('ch', []))


def keywords_of(s, schema, card):
    if card and card.get('keywords'):
        return [str(k)[:60] for k in card['keywords']][:20]
    names = [schema.get('cats', {}).get(cid) for cid in s.cats]
    names = [n for n in names if n and not SERVICE_CAT.search(n)]
    names.sort(key=lambda n: not n.isupper())
    return list(dict.fromkeys(n.upper()[:60] for n in names))[:20]


def collect_rules(sels, P):
    """Abilities/other rules and unique actions of the given selections' profiles (no duplicates)."""
    rules, actions, seen = [], [], set()
    for sel in sels:
        for pid in sel.node.get('p', []):
            pr = P.get(pid)
            if not pr or pr.get('t') in OWN_TYPES:
                continue
            key = (pr.get('t'), str(pr.get('n', '')).lower())
            if pid in seen or key in seen:
                continue
            seen.update((pid, key))
            item = {'name': str(pr.get('n', ''))[:120], 'text': profile_text(pr)}
            if pr.get('t') == 'Unique Actions':
                actions.append(item)
            else:
                rules.append({**item, 'type': '' if pr.get('t') == 'Abilities' else str(pr.get('t'))[:60]})
    return rules[:RULES_MAX], actions[:RULES_MAX]


def card_rules(items):
    return [{'name': str(a.get('name', ''))[:120], 'text': str(a.get('text', ''))[:TEXT_MAX]}
            for a in (items or [])[:RULES_MAX] if a.get('name')]


def roster_build(c, player):
    """Operatives of the player's attached roster (names, stats, the weapons and rules actually selected),
    the names of other selections (equipment and the like) and those selections' rules."""
    empty = {'operatives': [], 'other': [], 'extras': []}
    if not player.get('roster_id'):
        return empty
    r = core.one(c, '''SELECT r.data,t.roster_schema,t.data AS team FROM rosters r
    JOIN team_data t ON t.slug=r.team_slug AND t.active WHERE r.id=%s''', (str(player['roster_id']),))
    if not r or not r['roster_schema']:
        return empty
    try:
        force, _ = rk.Engine(r['roster_schema']).build(r['data'])
    except rk.RosterError:
        return empty
    schema = r['roster_schema']
    P = schema.get('profiles', {})
    known = cards({'data': r['team']})
    ops, other, extras = [], [], []

    def models(s):
        if s.node['t'] == 'unit':
            inner = [k for k in s.walk() if k.node['t'] == 'model']
            if inner:
                return inner
        return [s]
    for top in force.kids:
        if top.node['t'] not in ('model', 'unit'):
            other += [k.custom or k.name for k in top.walk() if k.node['t'] != 'group'] or [top.name]
            rules, actions = collect_rules([top] + list(top.walk()), P)
            extras += rules + [{**a, 'type': 'Unique Actions'} for a in actions]
            continue
        for s in models(top):
            stats, weapons, seen = {}, [], set()
            sels = [s] + list(s.walk())
            for sel in sels:
                for pid in sel.node.get('p', []):
                    pr = P.get(pid)
                    if not pr or pid in seen:
                        continue
                    seen.add(pid)
                    if pr.get('t') == 'Operative' and not stats:
                        stats = {str(k).lower(): v for k, _, v in pr.get('c', [])}
                    elif pr.get('t') == 'Weapons':
                        weapons.append(weapon_profile(pr))
            card = known.get(s.name.lower())
            if not stats and card:
                stats = card.get('stats') or {}
            if not weapons and card:
                weapons = card.get('weapons') or []
            if has_rules(s.node, P):
                abilities, actions = collect_rules(sels, P)
            else:
                abilities = [{**a, 'type': ''} for a in card_rules(card.get('abilities'))] if card else []
                actions = card_rules(card.get('actions')) if card else []
            keywords = keywords_of(s, schema, card)
            for _ in range(s.number):
                ops.append({'name': (s.custom or s.name)[:76], 'card': card['name'][:120] if card else None,
                            'stats': clean_stats(stats), 'weapons': clean_weapons(weapons),
                            'abilities': abilities, 'actions': actions, 'keywords': keywords})
    # Same names get numbers: «Trooper 1», «Trooper 2».
    total, seen = {}, {}
    for o in ops:
        total[o['name']] = total.get(o['name'], 0) + 1
    for o in ops:
        if total[o['name']] > 1:
            seen[o['name']] = seen.get(o['name'], 0) + 1
            o['name'] = f"{o['name']} {seen[o['name']]}"
    return {'operatives': ops[:MAX_OPERATIVES], 'other': other[:40], 'extras': extras[:RULES_MAX]}


def roster_operatives(c, player):
    b = roster_build(c, player)
    return b['operatives'], b['other']


def card_operative(c, player, card_name, name, wounds_max=None):
    team = team_row(c, player['team_id'])
    card = cards(team).get((card_name or '').lower()) if card_name else None
    if card_name and not card:
        core.fail(422, 'card_unknown')
    if not card and not name:
        core.fail(422, 'operative_name_required')
    stats = clean_stats(card.get('stats') if card else {})
    if wounds_max:
        stats['wounds'] = str(wounds_max)
    return {'name': (name or card['name'])[:80], 'card': card['name'][:120] if card else None,
            'stats': stats, 'weapons': clean_weapons(card.get('weapons') if card else [])}


def insert(c, m, player, ops, position):
    ids = []
    for i, o in enumerate(ops):
        w = max(1, min(99, number(o['stats'].get('wounds'), 1)))
        ids.append(core.one(c, '''INSERT INTO match_operatives(match_id,player_id,position,name,card,stats,weapons,wounds_max,wounds)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''', (str(m['id']), player['id'], position + i, o['name'], o['card'],
                                                              Jsonb(o['stats']), Jsonb(o['weapons']), w, w))['id'])
    return ids


def populate_all(c, m):
    """At the start: every player with an attached roster gets its operatives (once)."""
    for player in core.allrows(c, 'SELECT * FROM match_players WHERE match_id=%s ORDER BY slot', (str(m['id']),)):
        if core.one(c, 'SELECT 1 FROM match_operatives WHERE player_id=%s', (player['id'],)):
            continue
        ops, _ = roster_operatives(c, player)
        if ops:
            insert(c, m, player, ops, 1)


def log(c, mid, u, action, before, after):
    """Audit without bumping matches.version (see module docstring)."""
    c.execute('INSERT INTO match_audit(match_id,actor_id,action,before_data,after_data) VALUES(%s,%s,%s,%s,%s)',
              (str(mid), u['id'], action, Jsonb(before), Jsonb(after)))


def seq(c, mid):
    return core.one(c, "SELECT coalesce(max(id),0) AS n FROM match_audit WHERE match_id=%s AND action IN ('operative','operatives_populate')", (str(mid),))['n']


def tracked(c, player_id):
    return bool(core.one(c, 'SELECT 1 FROM match_operatives WHERE player_id=%s', (player_id,)))


def kill_change(c, m, victim, tp, delta):
    """Adjust the killer's (victim's opponent's) net incapacitated count; None when not applicable."""
    if m['scoring_mode'] != 'approved2025' or not tp or tp > 4:
        return None
    killer = core.one(c, 'SELECT id FROM match_players WHERE match_id=%s AND slot<>%s', (str(m['id']), victim['slot']))
    cap = victim['operative_count'] or MAX_OPERATIVES
    vals = {k['turning_point']: k['delta'] for k in core.allrows(c, 'SELECT * FROM operative_kills WHERE player_id=%s', (killer['id'],))}
    vals[tp] = vals.get(tp, 0) + delta
    running = 0
    for t in range(1, 5):
        running += vals.get(t, 0)
        if not 0 <= running <= cap:
            core.fail(422, 'kills_out_of_range')
    c.execute('''INSERT INTO operative_kills VALUES(%s,%s,%s)
    ON CONFLICT(player_id,turning_point) DO UPDATE SET delta=excluded.delta''', (killer['id'], tp, vals[tp]))
    return {'player_id': killer['id'], 'turning_point': tp, 'delta': delta}


def row(op, cols=FULL):
    return {k: op[k] for k in cols}


@core.app.post('/api/matches/{mid}/operatives')
def operatives(mid: UUID, p: OperativeCommand, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            m = core.member(c, mid, u['id'], True)
            if m['status'] != 'active':
                core.fail(409, 'tracker_closed')
            if p.action in ('populate', 'add'):
                player = core.actor_player(c, m, u, p.slot)
                have = core.one(c, 'SELECT count(*)::int AS n,coalesce(max(position),0)::int AS last FROM match_operatives WHERE player_id=%s', (player['id'],))
                if p.action == 'populate':
                    if have['n']:
                        core.fail(409, 'tracker_not_empty')
                    ops, _ = roster_operatives(c, player)
                    if not ops:
                        core.fail(422, 'roster_required')
                else:
                    ops = [card_operative(c, player, p.card, p.name, p.wounds_max)]
                if have['n'] + len(ops) > MAX_OPERATIVES or have['last'] + len(ops) > MAX_OPERATIVES:
                    core.fail(422, 'tracker_full')
                ids = insert(c, m, player, ops, have['last'] + 1)
                if p.action == 'populate':
                    log(c, mid, u, 'operatives_populate', {}, {'player_id': player['id'], 'count': len(ids)})
                else:
                    op = core.one(c, 'SELECT * FROM match_operatives WHERE id=%s', (ids[0],))
                    log(c, mid, u, 'operative', {'op': None}, {'op': row(op), 'kill': None, 'change': 'add'})
                return {'ok': True, 'ids': ids}
            if not p.operative_id:
                core.fail(422, 'operative_required')
            op = core.one(c, 'SELECT * FROM match_operatives WHERE id=%s AND match_id=%s FOR UPDATE', (p.operative_id, str(mid)))
            if not op:
                core.fail(404, 'operative_not_found')
            victim = core.one(c, 'SELECT * FROM match_players WHERE id=%s', (op['player_id'],))
            core.actor_player(c, m, u, victim['slot'])  # 403 unless the actor controls this operative
            tp = m['current_turn']
            kill = None
            if p.action == 'remove':
                if op['incapacitated_tp']:
                    kill = kill_change(c, m, victim, op['incapacitated_tp'], -1)
                c.execute('DELETE FROM match_operatives WHERE id=%s', (op['id'],))
                log(c, mid, u, 'operative', {'op': row(op)}, {'op': None, 'kill': kill, 'change': 'remove'})
                return {'ok': True}
            new = dict(op)
            if p.action == 'wounds':
                if p.delta is None:
                    core.fail(422, 'delta_required')
                new['wounds'] = max(0, min(op['wounds_max'], op['wounds'] + p.delta))
                if op['wounds'] > 0 and new['wounds'] == 0:
                    new['incapacitated_tp'] = tp
                    kill = kill_change(c, m, victim, tp, 1)
                elif op['wounds'] == 0 and new['wounds'] > 0:
                    new['incapacitated_tp'] = None
                    kill = kill_change(c, m, victim, op['incapacitated_tp'], -1)
            elif p.action == 'order':
                if not p.order:
                    core.fail(422, 'order_required')
                new['order_token'] = p.order
            elif p.action == 'activate':
                if p.activated is None:
                    core.fail(422, 'activated_required')
                new['activated_tp'] = tp if p.activated else None
            if all(new[k] == op[k] for k in MUTABLE):
                return {'ok': True, 'changed': False}
            c.execute('UPDATE match_operatives SET wounds=%s,order_token=%s,activated_tp=%s,incapacitated_tp=%s WHERE id=%s',
                      (new['wounds'], new['order_token'], new['activated_tp'], new['incapacitated_tp'], op['id']))
            log(c, mid, u, 'operative', {'op': row(op, ('id',) + MUTABLE)},
                {'op': row(new, ('id',) + MUTABLE), 'kill': kill, 'change': p.action, 'name': op['name']})
            return {'ok': True, 'changed': True}
        return core.operation(c, u, p, 'operative:' + str(mid), run)


def last_undoable(c, mid, uid):
    return core.one(c, '''SELECT a.id,a.action,a.before_data,a.after_data,a.created_at FROM match_audit a
    WHERE a.match_id=%s AND a.actor_id=%s AND a.action = ANY(%s)
    AND a.id > coalesce((SELECT max(s.id) FROM match_audit s WHERE s.match_id=a.match_id AND s.action IN ('start','reopen')),0)
    AND NOT EXISTS(SELECT 1 FROM match_audit x WHERE x.match_id=a.match_id AND x.action='undo' AND x.after_data->>'undo_of'=a.id::text)
    ORDER BY a.id DESC LIMIT 1''', (str(mid), uid, UNDOABLE))


def undo_summary(c, m, uid):
    """What «Undo last» would revert for this viewer (shown on the button); None when nothing."""
    if m['status'] != 'active':
        return None
    a = last_undoable(c, m['id'], uid)
    if not a:
        return None
    b, f = a['before_data'] or {}, a['after_data'] or {}
    d = {'id': a['id'], 'action': a['action'], 'created_at': a['created_at']}
    slots = {p['id']: p['slot'] for p in m['players']}
    if a['action'] == 'score':
        d.update(slot=slots.get(f.get('player_id')), turning_point=f.get('turning_point'), source_id=f.get('source_id'),
                 vp=[b.get('vp'), f.get('vp')] if 'vp' in b else None, cp=[b.get('cp'), f.get('cp')] if 'cp' in b and f.get('cp') is not None else None)
    elif a['action'] == 'kills':
        d.update(slot=slots.get(f.get('player_id')), turning_point=f.get('turning_point'), delta=[b.get('delta'), f.get('delta')])
    elif a['action'] == 'initiative':
        d.update(turning_point=f.get('turning_point'), slot=f.get('slot'))
    elif a['action'] == 'cp_grant':
        d.update(turning_point=f.get('turning_point'), gains=f.get('gains'))
    elif a['action'] == 'ploy':
        d.update(slot=f.get('slot'), turning_point=f.get('turning_point'), name=f.get('name'), cost=f.get('cost'))
    elif a['action'] == 'turn':
        d.update(turn=[b.get('turn'), f.get('turn')])
    elif a['action'] == 'operative':
        op = f.get('op') or b.get('op') or {}
        d.update(change=f.get('change'), name=f.get('name') or op.get('name'),
                 wounds=[(b.get('op') or {}).get('wounds'), (f.get('op') or {}).get('wounds')])
    return d


def conflict(ok):
    if not ok:
        core.fail(409, 'undo_conflict')


def revert(c, m, a):
    mid = str(m['id'])
    b, f = a['before_data'] or {}, a['after_data'] or {}
    if a['action'] == 'score':
        player, tp = f['player_id'], f['turning_point']
        if 'vp' in b and f.get('source_id'):
            cur = core.one(c, 'SELECT vp FROM turning_point_scores WHERE player_id=%s AND turning_point=%s AND source_id=%s', (player, tp, f['source_id']))
            conflict(cur and cur['vp'] == f['vp'])
            try:
                value = reference.validate_score(c, m, player, tp, f['source_id'], b['vp'] - f['vp'], f['vp'])
            except ValueError:
                conflict(False)
            conflict(value == b['vp'])
            c.execute('UPDATE turning_point_scores SET vp=%s WHERE player_id=%s AND turning_point=%s AND source_id=%s', (b['vp'], player, tp, f['source_id']))
        if 'cp' in b and f.get('cp') is not None:
            cur = core.one(c, 'SELECT cp FROM turning_point_states WHERE player_id=%s AND turning_point=%s', (player, tp))
            conflict(cur and cur['cp'] == f['cp'])
            c.execute('UPDATE turning_point_states SET cp=%s WHERE player_id=%s AND turning_point=%s', (b['cp'], player, tp))
    elif a['action'] == 'kills':
        cur = core.one(c, 'SELECT delta FROM operative_kills WHERE player_id=%s AND turning_point=%s', (f['player_id'], f['turning_point']))
        conflict(cur and cur['delta'] == f['delta'])
        c.execute('UPDATE operative_kills SET delta=%s WHERE player_id=%s AND turning_point=%s', (b['delta'], f['player_id'], f['turning_point']))
        own = core.one(c, 'SELECT slot FROM match_players WHERE id=%s', (f['player_id'],))
        victim = core.one(c, 'SELECT operative_count FROM match_players WHERE match_id=%s AND slot<>%s', (mid, own['slot']))
        running = 0
        for k in core.allrows(c, 'SELECT delta FROM operative_kills WHERE player_id=%s ORDER BY turning_point', (f['player_id'],)):
            running += k['delta']
            conflict(0 <= running <= (victim['operative_count'] or MAX_OPERATIVES))
    elif a['action'] == 'initiative':
        cur = core.one(c, 'SELECT slot FROM turning_point_initiative WHERE match_id=%s AND turning_point=%s', (mid, f['turning_point']))
        conflict(cur and cur['slot'] == f['slot'])
        if b.get('slot') is None:
            c.execute('DELETE FROM turning_point_initiative WHERE match_id=%s AND turning_point=%s', (mid, f['turning_point']))
        else:
            c.execute('UPDATE turning_point_initiative SET slot=%s WHERE match_id=%s AND turning_point=%s', (b['slot'], mid, f['turning_point']))
        from . import command
        command.revert_initiative_cp(c, m, f)
    elif a['action'] in ('cp_grant', 'ploy'):
        from . import command
        command.revert(c, m, a)
    elif a['action'] == 'turn':
        conflict(m['current_turn'] == f.get('turn') and b.get('turn'))
        c.execute('UPDATE matches SET current_turn=%s WHERE id=%s', (b['turn'], mid))
    elif a['action'] == 'operative':
        old, new = b.get('op'), f.get('op')
        if new:
            cur = core.one(c, 'SELECT * FROM match_operatives WHERE id=%s AND match_id=%s FOR UPDATE', (new['id'], mid))
            conflict(cur and all(cur[k] == new[k] for k in MUTABLE))
        else:
            conflict(not core.one(c, 'SELECT 1 FROM match_operatives WHERE id=%s', (old['id'],)))
        if old is None:
            c.execute('DELETE FROM match_operatives WHERE id=%s', (new['id'],))
        elif new is None:
            if core.one(c, 'SELECT 1 FROM match_operatives WHERE player_id=%s AND position=%s', (old['player_id'], old['position'])):
                conflict(False)
            c.execute('''INSERT INTO match_operatives(id,match_id,player_id,position,name,card,stats,weapons,wounds_max,wounds,order_token,activated_tp,incapacitated_tp)
            OVERRIDING SYSTEM VALUE VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                      (old['id'], mid, old['player_id'], old['position'], old['name'], old['card'], Jsonb(old['stats']), Jsonb(old['weapons']),
                       old['wounds_max'], old['wounds'], old['order_token'], old['activated_tp'], old['incapacitated_tp']))
        else:
            c.execute('UPDATE match_operatives SET wounds=%s,order_token=%s,activated_tp=%s,incapacitated_tp=%s WHERE id=%s',
                      (old['wounds'], old['order_token'], old['activated_tp'], old['incapacitated_tp'], old['id']))
        k = f.get('kill')
        if k:
            victim = core.one(c, 'SELECT * FROM match_players WHERE match_id=%s AND id<>%s', (mid, k['player_id']))
            kill_change(c, m, victim, k['turning_point'], -k['delta'])
    else:
        conflict(False)


@core.app.post('/api/matches/{mid}/undo')
def undo(mid: UUID, p: Undo, u=Depends(core.user)):
    """Revert the actor's own last board change (score, CP, kills, initiative, turn, tracker, v1.14: CP grant, ploy).
    The client names the audit entry it shows; anything newer or already changed answers 409."""
    with core.pool.connection() as c:
        def run():
            m = core.member(c, mid, u['id'], True)
            if m['status'] != 'active':
                core.fail(409, 'undo_closed')
            a = last_undoable(c, mid, u['id'])
            if not a or a['id'] != p.audit_id:
                core.fail(409, 'undo_conflict')
            revert(c, m, a)
            core.audit(c, mid, u, 'undo', {'action': a['action']}, {'undo_of': a['id']})
            return {'ok': True, 'action': a['action']}
        return core.operation(c, u, p, 'undo:' + str(mid), run)


@core.app.get('/api/matches/{mid}/players/{slot}/roster')
def player_roster(mid: UUID, slot: int, u=Depends(core.user)):
    """A player's roster as played: own at any time, the opponent's once the match has started."""
    if slot not in (1, 2):
        core.fail(404, 'player_not_found')
    with core.pool.connection() as c:
        m = core.member(c, mid, u['id'])
        player = core.one(c, 'SELECT * FROM match_players WHERE match_id=%s AND slot=%s', (str(mid), slot))
        mine = player['user_id'] == u['id'] or (m['kind'] == 'hotseat' and m['created_by'] == u['id'])
        if not mine and m['status'] in ('setup', 'cancelled'):
            core.fail(403, 'roster_hidden')
        team = team_row(c, player['team_id'])
        b = roster_build(c, player)
        name = core.one(c, 'SELECT name FROM rosters WHERE id=%s', (str(player['roster_id']),)) if player['roster_id'] else None
        return {'slot': slot, 'display_name': player['display_name'], 'team_slug': team['slug'] if team else None,
                'team_name': team['name'] if team else None, 'roster_name': name['name'] if name else None,
                'roster_text': player['roster'], 'operative_count': player['operative_count'], **b}


@core.app.get('/api/rosters/{rid}/sheet')
def roster_sheet(rid: UUID, u=Depends(core.user)):
    """Printable roster: the operatives as they would enter a match (names, stats, selected weapons and rules)."""
    with core.pool.connection() as c:
        r = core.one(c, '''SELECT r.id,r.name,r.team_slug,t.name AS team_name,t.catalog_id FROM rosters r
        LEFT JOIN team_data t ON t.slug=r.team_slug AND t.active WHERE r.id=%s AND r.user_id=%s''', (str(rid), u['id']))
        if not r:
            core.fail(404, 'roster_not_found')
        b = roster_build(c, {'roster_id': r['id']})
        return {'id': r['id'], 'roster_name': r['name'], 'team_slug': r['team_slug'], 'team_name': r['team_name'],
                'team_id': r['catalog_id'], **b}
