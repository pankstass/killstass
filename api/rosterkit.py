"""v1.8: roster engine. Validates KILLSTASS rosters against the BattleScribe-derived schema built by
api/teamdata.py and exports them as text, JSON, BattleScribe .ros (XML, rosterSchema 2.03) and .rosz.

Supported BattleScribe subset (what Kill Team catalogues use): min/max selection constraints with
parent/self/force/roster/ancestor-entry/category scopes, shared and includeChildSelections; constraints of
force categories (operative counts); modifiers set/increment/decrement/append on constraints, hidden and
name, add/remove/set-primary category, add error/warning; conditions, condition groups and repeats.
Costs (points) are ignored: Kill Team 2024 has none. Issues are codes + params, translated by the client."""
import hashlib, io, json, math, re, zipfile
from xml.sax.saxutils import escape, quoteattr

FORMAT = 'killstass-roster/1'
MAX_SELECTIONS, MAX_DEPTH, MAX_NUMBER = 500, 8, 99
UID = re.compile(r'^[a-z0-9]{6,16}$')
FORCE_SCOPES = {'force', 'roster', 'primary-catalogue', 'primary-category'}
KT_EQUIPMENT_MAX = 4

class RosterError(ValueError):
    """Malformed roster document (not a rules problem): API answers 422."""

def _num(v, d=0.0):
    try: return float(v)
    except (TypeError, ValueError): return d

class Sel:
    __slots__ = ('node', 'groups', 'parent', 'number', 'custom', 'uid', 'kids', 'cats', 'name', 'hidden', 'errs')
    def __init__(self, node, groups, parent, number=1, custom='', uid=''):
        self.node, self.groups, self.parent, self.number, self.custom, self.uid = node, groups, parent, number, custom, uid
        self.kids, self.errs, self.hidden = [], [], False
        self.cats = list(node.get('cat', [])) if node else []
        self.name = node['n'] if node else ''
    def walk(self):
        for k in self.kids:
            yield k
            yield from k.walk()

class Engine:
    def __init__(self, schema):
        if not isinstance(schema, dict) or schema.get('v') != 1: raise RosterError('roster_schema_unsupported')
        self.s = schema
        self.force_ids = {schema['force']['id'], schema['cat']['id'], schema['gs']['id']}
        self._opts = {}

    # ---- schema navigation
    def options(self, node):
        """Selectable entries under node (None = force), flattened through groups: key -> (entry, groups)."""
        i = id(node)
        if i not in self._opts:
            out = {}
            def walk(ns, groups):
                for n in ns:
                    if n['t'] == 'group': walk(n.get('ch', []), groups + (n,))
                    else: out.setdefault(n['k'], (n, groups))
            walk(self.s['root'] if node is None else node.get('ch', []), ())
            self._opts[i] = out
        return self._opts[i]

    def checked_nodes(self, node):
        """Entries and groups whose constraints apply inside a container of `node`."""
        seen, out = set(), []
        for n, groups in self.options(node).values():
            for x in groups + (n,):
                if id(x) not in seen: seen.add(id(x)); out.append(x)
        return out

    # ---- build
    def build(self, data):
        if not isinstance(data, dict): raise RosterError('roster_invalid')
        if data.get('format', FORMAT) != FORMAT: raise RosterError('roster_format')
        sels = data.get('selections', [])
        if not isinstance(sels, list): raise RosterError('roster_invalid')
        uids, total = set(), [0]
        def check(items, depth):
            """Structure first (whole document, also below unknown entries): ids, sizes, depth."""
            if not isinstance(items, list): raise RosterError('roster_invalid')
            if items and depth > MAX_DEPTH: raise RosterError('roster_too_deep')
            for it in items:
                if not isinstance(it, dict): raise RosterError('roster_invalid')
                total[0] += 1
                if total[0] > MAX_SELECTIONS: raise RosterError('roster_too_large')
                uid, key, number, custom = it.get('uid'), it.get('key'), it.get('n', 1), it.get('name') or ''
                if not isinstance(uid, str) or not UID.match(uid) or uid in uids: raise RosterError('roster_bad_uid')
                uids.add(uid)
                if not isinstance(key, str) or not 1 <= len(key) <= 300: raise RosterError('roster_bad_key')
                if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= MAX_NUMBER: raise RosterError('roster_bad_number')
                if not isinstance(custom, str) or len(custom) > 80: raise RosterError('roster_bad_name')
                check(it.get('sel', []), depth + 1)
        check(sels, 1)
        force = Sel(None, (), None)
        issues = []
        def add(items, parent, node):
            opts = self.options(node)
            for it in items:
                hit = opts.get(it['key'])
                custom = (it.get('name') or '').strip()
                if hit is None:
                    issues.append({'level': 'error', 'code': 'unknown_entry', 'uid': it['uid'], 'params': {'name': custom or it['key'][-19:]}})
                    continue
                s = Sel(hit[0], hit[1], parent, it.get('n', 1), custom, it['uid'])
                parent.kids.append(s)
                add(it.get('sel', []), s, hit[0])
        add(sels, force, None)
        return force, issues

    # ---- counting & scopes
    def matches(self, s, ch):
        if ch == 'any': return True
        n = s.node
        if ch == n['id'] or ch in n['k'].split('::') or ch in s.cats or ch == n['t']: return True
        return any(ch == g['id'] or ch in g['k'].split('::') for g in s.groups)

    def instance(self, target, ch):
        if target is None: return False
        if target.node is None: return ch in self.force_ids or ch == 'any'
        return self.matches(target, ch)

    def scope(self, ctx, scope, me):
        if scope == 'parent': return ctx
        if scope == 'self': return me
        if scope in FORCE_SCOPES or scope in self.force_ids: return self.force
        x = ctx
        while x is not None and x.node is not None:
            if self.matches(x, scope): return x
            x = x.parent
        return self.force

    @staticmethod
    def selections(cont, deep):
        if cont is None: return []
        return list(cont.walk()) if deep else cont.kids

    def count(self, cont, ch, field, deep):
        if field == 'forces': return 1 if cont is not None and (ch == 'any' or ch in self.force_ids) else 0
        if field != 'selections': return 0  # costs: Kill Team 2024 has none
        return sum(s.number for s in self.selections(cont, deep) if self.matches(s, ch))

    def cond(self, c, ctx, me):
        t = c.get('t')
        target = self.scope(ctx, c.get('s', 'parent'), me)
        if t in ('instanceOf', 'notInstanceOf'):
            r = self.instance(target, c.get('ch', 'any'))
            return r if t == 'instanceOf' else not r
        deep = c.get('ic') or c.get('s') not in ('parent', 'self')
        n, v = self.count(target, c.get('ch', 'any'), c.get('f', 'selections'), deep), c.get('v') or 0
        return {'lessThan': n < v, 'greaterThan': n > v, 'equalTo': n == v, 'notEqualTo': n != v,
                'atLeast': n >= v, 'atMost': n <= v}.get(t, False)

    def tree(self, tr, ctx, me):
        if not tr: return True
        items = [self.cond(c, ctx, me) for c in tr.get('c', [])] + [self.tree(g, ctx, me) for g in tr.get('g', [])]
        if not items: return True
        return any(items) if tr.get('op') == 'or' else all(items)

    def repeats(self, reps, ctx, me):
        times = 0
        for r in reps:
            deep = r.get('ic') or r.get('s') not in ('parent', 'self')
            n, v = self.count(self.scope(ctx, r.get('s', 'parent'), me), r.get('ch', 'any'), r.get('f', 'selections'), deep), r.get('v') or 1
            times += (math.ceil(n / v) if r.get('up') else math.floor(n / v)) * r.get('n', 1)
        return times

    def effective(self, node, ctx, me=None):
        """Constraints, visibility, name, categories and catalogue errors of `node` after its modifiers."""
        con = {c['id']: dict(c) for c in node.get('con', [])}
        out = {'con': con, 'hidden': bool(node.get('h')), 'name': node.get('n', ''), 'cats': list(node.get('cat', [])), 'errs': []}
        for m in node.get('mod', []):
            if not self.tree(m.get('c'), ctx, me): continue
            times = self.repeats(m['r'], ctx, me) if m.get('r') else 1
            if times <= 0: continue
            t, f, v = m.get('t'), m.get('f'), m.get('v')
            if f in con:
                x = _num(v)
                if t == 'set': con[f]['v'] = x
                elif t == 'increment': con[f]['v'] += x * times
                elif t == 'decrement': con[f]['v'] -= x * times
            elif f == 'hidden': out['hidden'] = str(v).lower() == 'true'
            elif f == 'name' and v:
                out['name'] = v if t == 'set' else (out['name'] + ' ' + v if t == 'append' else out['name'])
            elif f == 'category' and v:
                if t in ('add', 'set-primary') and v not in out['cats']: out['cats'].append(v)
                elif t in ('remove', 'unset-primary') and v in out['cats'] and t == 'remove': out['cats'].remove(v)
            elif f in ('error', 'warning') and t in ('add', 'set') and v:
                out['errs'].append((f, str(v)[:300]))
        return out

    def count_node(self, node, cont, deep, shared):
        tot = 0
        for s in self.selections(cont, deep):
            if node['t'] == 'group': hit = any(g is node or (shared and g['id'] == node['id']) for g in s.groups)
            else: hit = s.node is node or (shared and s.node['id'] == node['id'])
            if hit: tot += s.number
        return tot

    # ---- validation
    def validate(self, data):
        force, issues = self.build(data)
        self.force = force
        sels = list(force.walk())
        for s in sels:
            e = self.effective(s.node, s.parent, s)
            s.cats, s.hidden, s.errs = e['cats'], e['hidden'], e['errs']
            s.name = s.node['n'] if e['name'] == '' else e['name']
        def issue(level, code, cont, **params):
            issues.append({'level': level, 'code': code, 'uid': cont.uid if cont is not None and cont.uid else None, 'params': params})
        seen = set()
        for cont in [force] + sels:
            for node in self.checked_nodes(cont.node):
                e = self.effective(node, cont)
                for c in e['con'].values():
                    if c.get('f') != 'selections': continue
                    sc = self.scope(cont, c.get('s', 'parent'), None)
                    if sc is None: continue
                    key = (id(node), id(cont), c['id']) if c.get('s') == 'parent' else (c['id'], id(sc), node['id'] if c.get('sh') else id(node))
                    if key in seen: continue
                    seen.add(key)
                    deep = bool(c.get('ic')) or c.get('s') != 'parent'
                    n, v = self.count_node(node, sc, deep, c.get('sh', True)), c.get('v')
                    if v is None: continue
                    name = e['name'] or node['n']
                    if c['t'] == 'min' and n < v and not e['hidden']:
                        issue('error', 'min', sc if sc is not force else None, name=name, count=n, min=int(v))
                    elif c['t'] == 'max' and v >= 0 and n > v:
                        issue('error', 'max', sc if sc is not force else None, name=name, count=n, max=int(v))
        limits = []
        for fc in self.s['force'].get('cats', []):
            e = self.effective(fc, force)
            lim = {'name': fc['n'], 'count': 0}
            for c in e['con'].values():
                if c.get('f') != 'selections': continue
                deep = bool(c.get('ic'))
                n = sum(s.number for s in self.selections(force, deep) if fc['tg'] in s.cats)
                lim['count'], v = n, c.get('v')
                if c['t'] == 'min': lim['min'] = int(v)
                if c['t'] == 'max' and v >= 0: lim['max'] = int(v)
                if c['t'] == 'min' and n < v: issue('error', 'category_min', None, name=fc['n'], count=n, min=int(v))
                if c['t'] == 'max' and 0 <= v < n: issue('error', 'category_max', None, name=fc['n'], count=n, max=int(v))
            if 'min' in lim or 'max' in lim: limits.append(lim)
            for level, text in e['errs']: issue(level, 'catalogue', None, text=text)
        for s in sels:
            if s.hidden: issue('warning', 'hidden', s, name=s.name)
            for level, text in s.errs: issue(level, 'catalogue', s, text=text)
        equip = sum(k.number for s in force.kids if 'equipment' in s.node['n'].lower() for k in s.walk() if not k.kids)
        if equip > KT_EQUIPMENT_MAX: issue('warning', 'equipment', None, count=equip, max=KT_EQUIPMENT_MAX)
        ops = sum(s.number for s in force.kids if s.node['t'] in ('model', 'unit'))
        errors = [i for i in issues if i['level'] == 'error']
        return {'valid': not errors, 'errors': errors[:100], 'warnings': [i for i in issues if i['level'] != 'error'][:100],
                'operatives': ops, 'limits': limits}

    # ---- defaults
    def defaults(self, node, uid):
        """Child selections a new selection of `node` starts with: entries/groups with a minimum."""
        out = []
        def mins(n):
            return max([int(c.get('v') or 0) for c in n.get('con', []) if c.get('t') == 'min' and c.get('s') == 'parent' and c.get('f') == 'selections'] or [0])
        def maxes(n):
            v = [int(c.get('v')) for c in n.get('con', []) if c.get('t') == 'max' and c.get('s') == 'parent' and c.get('f') == 'selections' and c.get('v') is not None]
            return min(v) if v else -1
        def visit(children):
            for c in children:
                if c.get('h'): continue
                if c['t'] == 'group':
                    m = mins(c)
                    entries = [x for x in c.get('ch', []) if x['t'] != 'group' and not x.get('h')]
                    if m and entries:
                        entries.sort(key=lambda x: not (c.get('def') and (x['id'] == c['def'] or x['k'].endswith(c['def']))))
                        for x in entries:
                            if m <= 0: break
                            n = m if maxes(x) < 0 else min(m, maxes(x))
                            if n <= 0: continue
                            out.append({'uid': uid(), 'key': x['k'], 'n': n, 'sel': self.defaults(x, uid)}); m -= n
                    visit([x for x in c.get('ch', []) if x['t'] == 'group'])
                else:
                    m = mins(c)
                    if m: out.append({'uid': uid(), 'key': c['k'], 'n': m, 'sel': self.defaults(c, uid)})
        visit(node.get('ch', []))
        return out

    # ---- exports
    def resolved(self, data):
        """Validation + selection tree with names, for exports."""
        result = self.validate(data)
        return self.force, result

def line(s):
    kids = [line(k) for k in s.kids]
    name = (f'{s.number}× ' if s.number > 1 else '') + (f'{s.custom} ({s.name})' if s.custom else s.name)
    return name + (f' ({", ".join(kids)})' if kids else '')

def to_text(schema, data, team, title):
    eng = Engine(schema)
    force, res = eng.resolved(data)
    ops = [s for s in force.kids if s.node['t'] in ('model', 'unit')]
    other = [s for s in force.kids if s not in ops]
    out = [f'{team} — {title} ({res["operatives"]})']
    for i, s in enumerate(ops, 1):
        kids = [line(k) for k in s.kids]
        name = (f'{s.number}× ' if s.number > 1 else '') + (f'{s.custom} ({s.name})' if s.custom else s.name)
        out.append(f'{i}. {name}' + (': ' + ', '.join(kids) if kids else ''))
    for s in other:
        leaves = [line(k) for k in s.kids]
        if leaves: out.append(f'{s.name}: ' + ', '.join(leaves))
    notes = str(data.get('notes') or '').strip()
    if notes: out += ['', notes]
    text = '\n'.join(out)
    return text if len(text) <= 4000 else text[:3999] + '…'

def bs_id(*parts):
    h = hashlib.sha256('/'.join(map(str, parts)).encode()).hexdigest()
    return f'{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}'

def a(**kw):
    return ''.join(f' {k.rstrip("_")}={quoteattr(str(v))}' for k, v in kw.items() if v is not None and v != '')

def to_ros(schema, data, title, rid):
    """BattleScribe roster XML (rosterSchema, battleScribeVersion 2.03)."""
    eng = Engine(schema)
    force, _ = eng.resolved(data)
    s, P, R, cats = eng.s, eng.s.get('profiles', {}), eng.s.get('rules', {}), eng.s.get('cats', {})
    w = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         f'<roster{a(id=bs_id(rid), name=title, battleScribeVersion="2.03", gameSystemId=s["gs"]["id"], gameSystemName=s["gs"]["n"], gameSystemRevision=s["gs"].get("rev"))} xmlns="http://www.battlescribe.net/schema/rosterSchema">',
         '<forces>',
         f'<force{a(id=bs_id(rid, "force"), name=s["force"]["n"], entryId=s["force"]["id"], catalogueId=s["cat"]["id"], catalogueRevision=s["cat"].get("rev"), catalogueName=s["cat"]["n"])}>']
    def info(sel):
        node = sel.node
        if node.get('r'):
            w.append('<rules>')
            for r in node['r']:
                x = R.get(r) or {}
                w.append(f'<rule{a(id=r, name=x.get("n") or "Rule", hidden="false")}><description>{escape(x.get("d") or "")}</description></rule>')
            w.append('</rules>')
        if node.get('p'):
            w.append('<profiles>')
            for p in node['p']:
                x = P.get(p) or {}
                w.append(f'<profile{a(id=p, name=x.get("n") or "Profile", hidden="false", typeId=x.get("ti") or "profile", typeName=x.get("t"))}><characteristics>')
                for cn, ct, cv in x.get('c', []):
                    w.append(f'<characteristic{a(name=cn, typeId=ct or cn)}>{escape(cv or "")}</characteristic>')
                w.append('</characteristics></profile>')
            w.append('</profiles>')
    def sel(x):
        grp = x.groups[-1]['k'] if x.groups else None
        w.append(f'<selection{a(id=bs_id(rid, x.uid), name=x.name, entryId=x.node["k"], entryGroupId=grp, number=x.number, type=x.node["t"] if x.node["t"] in ("model", "unit", "upgrade") else "upgrade", customName=x.custom or None)}>')
        info(x)
        if x.kids:
            w.append('<selections>'); [sel(k) for k in x.kids]; w.append('</selections>')
        if x.cats:
            w.append('<categories>')
            for c in x.cats:
                w.append(f'<category{a(id=bs_id(rid, x.uid, c), name=cats.get(c) or c, entryId=c, primary="true" if c == x.node.get("pc") else "false")}/>')
            w.append('</categories>')
        w.append('</selection>')
    if force.kids:
        w.append('<selections>'); [sel(k) for k in force.kids]; w.append('</selections>')
    fcats = [c for c in s['force'].get('cats', [])]
    if fcats:
        w.append('<categories>')
        for c in fcats: w.append(f'<category{a(id=bs_id(rid, "fc", c["tg"]), name=c["n"], entryId=c["tg"], primary="false")}/>')
        w.append('</categories>')
    w += ['</force>', '</forces>']
    notes = str(data.get('notes') or '').strip()
    if notes: w.append(f'<customNotes>{escape(notes)}</customNotes>')
    w.append('</roster>')
    return '\n'.join(w) + '\n'

def to_rosz(schema, data, title, rid, filename='roster.ros'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(filename, date_time=(2024, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, to_ros(schema, data, title, rid))
    return buf.getvalue()

def summary(schema, data):
    """Compact validation result stored with the roster (list view)."""
    if schema is None: return {'valid': False, 'errors': [{'level': 'error', 'code': 'no_schema', 'uid': None, 'params': {}}], 'warnings': [], 'operatives': 0, 'limits': []}
    return Engine(schema).validate(data)
