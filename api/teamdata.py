"""v1.7/v1.8: team & operative reference + roster schema importer (operator tool, stdlib only).

    python -m api.teamdata fetch [--ktd-ref REF] [--bsdata-ref REF] > bundle.json   (needs internet)
    python -m api.teamdata sql < bundle.json | psql -U killstass_owner ...           (production: owner role)
    python -m api.teamdata load < bundle.json                                      (dev/tests: owner DATABASE_URL)
    python -m api.teamdata export > bundle.json                                    (v1.11: teams now in the database)
    python -m api.teamdata status                                                  (read-only)

Sources (community projects; game texts belong to Games Workshop, used for personal reference):
  * kt-datacards  https://github.com/Wen-Qualtu/kt-datacards  - team JSON extracted from the official
    datacards: stats, weapons, abilities, ploys, equipment, faction rules, operative selection.
  * BSData        https://github.com/BSData/wh40k-killteam    - BattleScribe catalogues (2024): used to
    cross-check operative stats and to tell ranged from melee weapons; fallback for teams missing above;
    complete faction rule options; v1.8: the selection tree for the roster builder (api/rosterkit.py).
Nothing is downloaded at runtime by the web app: the operator runs scripts/import-teams.sh.
"""
import hashlib, json, os, re, sys, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

FORMAT = 'killstass-teams/2'
FORMATS = ('killstass-teams/1', FORMAT)  # /1 (v1.7) bundles still load, without roster schemas
ARCHETYPES = ('Infiltration', 'Recon', 'Security', 'Seek & Destroy')
KTD = 'Wen-Qualtu/kt-datacards'
BSD = 'BSData/wh40k-killteam'
UA = {'User-Agent': 'killstass-team-import/1.8', 'Accept': 'application/vnd.github+json'}
MAX_BUNDLE = 25 * 1024 * 1024
MAX_SCHEMA = 2 * 1024 * 1024  # one team's roster schema (largest real one ~0.2 MB)
# v1.11: the search index (db/migrations/013_v111.sql) follows every import; skipped on databases before 013.
REFRESH_SQL = ("DO $$BEGIN IF to_regclass('public.reference_search') IS NOT NULL THEN "
               "REFRESH MATERIALIZED VIEW reference_search; END IF; END$$;")

# ---------------------------------------------------------------- helpers
def http(url, timeout=40, tries=3):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network hiccups: retry
            last = e
    raise RuntimeError(f'download failed: {url}: {last}')

def gh_json(path): return json.loads(http('https://api.github.com/' + path))
def raw(repo, sha, path): return f'https://raw.githubusercontent.com/{repo}/{sha}/' + urllib.parse.quote(path)

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[’'`]", '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(w[:-1] if w.endswith('s') and len(w) > 3 else w for w in s.split())

def slugify(s): return re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()).strip('-')

SMALL = {'of', 'the', 'and', 'a', 'an', 'in', 'on', 'for', 'to', 'with', 'by', 'at', 'or', 'from'}
def title(s):
    words = re.split(r'(\s+|-)', s.strip().lower())
    out = []
    for i, w in enumerate(words):
        if w in SMALL and i: out.append(w)
        elif re.match(r'^[a-z]{1,3}\d', w): out.append(w.upper())
        else: out.append(w[:1].upper() + w[1:])
    return ''.join(out)

def is_caps(line):
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and all(not c.islower() for c in letters)

TYPE_LINES = ('FACTION RULE', 'STRATEGY PLOY', 'FIREFIGHT PLOY', 'FACTION EQUIPMENT', 'EQUIPMENT', 'OPERATIVE SELECTION',
              'KILL TEAM', 'FACTION RULES', 'UNIVERSAL EQUIPMENT')

def blocks(text, name=''):
    """Card text with hard PDF line breaks -> (title, [ {k: lore|p|li|li2|h, t: text} ])."""
    lines = [l.strip() for l in str(text or '').replace('\r', '').split('\n')]
    lines = [l for l in lines if l and l != '---' and 'CONTINUES ON OTHER SIDE' not in l
             and not (is_caps(l) and re.search(r'PRESENTED|ON THEIR OWN CARDS?|OPTIONS ARE$', l))]
    head = []
    while lines and is_caps(lines[0]) and len(head) < 4:
        head.append(lines.pop(0))
    head_title = next((h for h in reversed(head) if h.strip(' :') not in TYPE_LINES), '')
    while lines and lines[-1].strip(' :') in TYPE_LINES: lines.pop()  # card footer
    tail = None
    # A short ALL-CAPS last line is a heading only after a finished sentence (else: end of that sentence).
    if (lines and is_caps(lines[-1]) and len(lines[-1]) < 40 and not lines[-1].endswith('.')
            and (len(lines) == 1 or lines[-2].rstrip().endswith(('.', ':', '!', '?', '”', '"')))): tail = lines.pop()
    out = []
    for l in lines:
        bullet = re.match(r'^([•↘○▪◦\-–])\s*(.*)$', l)
        if bullet:
            k = {'↘': 'li', '•': 'li2', '▪': 'li2', '○': 'li3', '◦': 'li3'}.get(bullet.group(1), 'li')
            out.append({'k': k, 't': bullet.group(2)})
            continue
        if out and out[-1]['k'] not in ('h', 'lore'):
            prev = out[-1]['t']
            ends = prev.rstrip().endswith(('.', ':', '!', '?', '”', '"')) and (l[:1].isupper() or l[:1].isdigit())
            new_para = out[-1]['k'].startswith('li') and is_caps(prev) and re.match(r'^[A-Z][a-z]', l)
            if not new_para and (not ends or (out[-1]['k'].startswith('li') and not l[:1].isupper())):
                out[-1]['t'] = (prev + ' ' + l).replace('  ', ' ')
                continue
        out.append({'k': 'p', 't': l})
    # flavour text: a first paragraph without rules keywords (no ALLCAPS words, no digits/inches)
    if len(out) > 1 and out[0]['k'] == 'p' and not re.search(r'\b[A-Z]{3,}\b|\d|"', out[0]['t']):
        out[0]['k'] = 'lore'
    if tail: out.append({'k': 'h', 't': title(tail)})
    return title(head_title) if head_title else title(name.replace('-', ' ')), out

RANGED = re.compile(r'gun|rifle|pistol|bolter|carbine|launcher|cannon|flamer|incinerator|blaster|lance|caliver|arquebus|stubber|stakethrower|las|charge|grenade|bow|sling|thrower|projector|rotor', re.I)
MELEE = re.compile(r'sword|blade|claw|fist|maul|axe|cleaver|bludgeon|butt|bayonet|fang|talon|pincer|knuckle|stave|mace|rapier|khopesh|dagger|bash|ram\b|improvised|incentiviser|tentacle', re.I)
def guess_type(name, wr):
    if re.search(r'\bRange\b', wr): return 'ranged'
    if re.search(r'butt|pincer|bayonet|bash', name, re.I): return 'melee'
    m, r = bool(MELEE.search(name)), bool(RANGED.search(name))
    return 'melee' if m and not r else 'ranged' if r and not m else None
def clean_weapon(n): return re.sub(r'(?<=[a-z\)])\d$', '', n.replace('\u2011', '-').strip())
def stat(v): return str(v if v is not None else '').replace('″', '"').strip()

# ---------------------------------------------------------------- BSData
NS = '{http://www.battlescribe.net/schema/catalogueSchema}'
def _tag(e): return e.tag.split('}')[-1]
def _chars(p): return {c.get('name'): (c.text or '').strip() for c in p.iter() if _tag(c) == 'characteristic'}

def _ns(e): return e.tag[:e.tag.index('}') + 1] if e.tag.startswith('{') else ''
def _kids(e, name):
    """Children of <name>; catalogue and game system files use different XML namespaces."""
    c = e.find(_ns(e) + name)
    return list(c) if c is not None else []
def _iter(e, name): return (x for x in e.iter() if _tag(x) == name)
def _desc(e): return next((x.text or '' for x in e if _tag(x) == 'description'), '').strip()

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f == int(f) else f

def bs_ids(roots):
    ids = {}
    for root in roots:
        for e in root.iter():
            if e.get('id') and _tag(e) in ('selectionEntry', 'selectionEntryGroup', 'profile', 'rule', 'categoryEntry', 'forceEntry'):
                ids.setdefault(e.get('id'), e)
    return ids

def bs_roots(cat, gst_root, cats=None):
    """The catalogue, catalogues it links to (e.g. Inquisitorial Agents) and the game system."""
    linked = [cats[l.get('targetId')] for l in _kids(cat, 'catalogueLinks') if l.get('targetId') in (cats or {})]
    return [cat] + linked + [gst_root]

def bs_parse(cat_xml, gst_root, cats=None):
    r = ET.fromstring(cat_xml) if isinstance(cat_xml, (bytes, str)) else cat_xml
    roots = bs_roots(r, gst_root, cats)
    ids = bs_ids(roots)
    def walk(e, seen, out, depth=0):
        if depth > 12: return
        for ch in e:
            t = _tag(ch)
            if t == 'profiles': out.extend(ch)
            elif t == 'infoLinks':
                for l in ch:
                    tg = ids.get(l.get('targetId'))
                    if tg is not None and _tag(tg) == 'profile': out.append(tg)
            elif t in ('selectionEntries', 'selectionEntryGroups'):
                for se in ch: walk(se, seen, out, depth + 1)
            elif t == 'entryLinks':
                for l in ch:
                    tid = l.get('targetId'); tg = ids.get(tid)
                    if tg is not None and tid not in seen: walk(tg, seen | {tid}, out, depth + 1)
                    walk(l, seen, out, depth + 1)
    ops = []
    for m in r.iter():
        if _tag(m) != 'selectionEntry' or m.get('type') != 'model': continue
        profs = []; walk(m, {m.get('id')}, profs)
        op = next((p for p in profs if p.get('typeName') == 'Operative'), None)
        if op is None: continue
        weapons, seen = [], set()
        for p in profs:
            if p.get('typeName') == 'Weapons' and p.get('name') not in seen:
                seen.add(p.get('name')); c = _chars(p); n = p.get('name')
                kind = 'ranged' if n.startswith('⌖') else 'melee' if n.startswith('⚔') else None
                weapons.append({'name': n.lstrip('⌖⚔ ').strip(), 'type': kind, 'atk': c.get('ATK', ''), 'hit': c.get('HIT', ''),
                                'dmg': c.get('DMG', ''), 'wr': c.get('WR', '').replace('-', '') if c.get('WR', '') == '-' else c.get('WR', '')})
        abil = []
        for p in profs:
            if p.get('typeName') in ('Abilities', 'Unique Actions'):
                txt = ' '.join(v for v in _chars(p).values() if v)
                abil.append({'kind': 'action' if p.get('typeName') == 'Unique Actions' else 'ability', 'name': p.get('name'), 'text': txt})
        s = _chars(op)
        ops.append({'name': m.get('name'), 'stats': {'apl': s.get('APL', ''), 'move': stat(s.get('Move')), 'save': s.get('Save', ''), 'wounds': s.get('Wounds', '')},
                    'weapons': weapons, 'abilities': abil})
    comment = r.find(NS + 'comment')
    out = {'name': r.get('name'), 'revision': r.get('revision'), 'comment': comment.text if comment is not None else '', 'operatives': ops}
    out.update(bs_rule_items(r))
    out['roster'] = RosterCompiler(r, gst_root, cats).schema()
    return out

# ---------------------------------------------------------------- BSData: rules and rule options (v1.8)
STD_PROFILES = {'Weapons', 'Operative', 'Abilities', 'Unique Actions', 'Equipment', 'Psychic Power'}
def _profile_text(p):
    ch = [(k, v) for k, v in _chars(p).items() if v]
    return '\n'.join(f'{k}: {v}' if len(ch) > 1 else v for k, v in ch)

def bs_rule_items(cat):
    """Catalogue-level rules and named option lists (custom profile types such as 'Boons of Tzeentch',
    'Chapter Tactics', 'Sanguavitae'; profiles inside equally named selection groups/entries)."""
    lists = {}
    def add(key, p):
        lst = lists.setdefault(key, [])
        if p.get('name') and p.get('name') not in [o['name'] for o in lst]:
            lst.append({'name': p.get('name').strip(), 'text': _profile_text(p), 'type': p.get('typeName')})
    for p in _iter(cat, 'profile'):
        if p.get('typeName') and p.get('typeName') not in STD_PROFILES: add(p.get('typeName'), p)
    for g in cat.iter():
        if _tag(g) in ('selectionEntryGroup', 'selectionEntry') and g.get('type') != 'model' and g.get('name'):
            for p in _iter(g, 'profile'):
                if p.get('typeName') not in ('Weapons', 'Operative'): add(g.get('name'), p)
    rules = [{'name': x.get('name'), 'text': _desc(x)}
             for ch in cat if _tag(ch) in ('rules', 'sharedRules') for x in ch if _tag(x) == 'rule']
    return {'rules': [x for x in rules if x['name'] and x['text']], 'option_lists': lists}

# ---------------------------------------------------------------- BSData: roster schema (v1.8)
def _cond(e):
    return {'t': e.get('type'), 'f': e.get('field', 'selections'), 's': e.get('scope', 'parent'), 'ch': e.get('childId', 'any'),
            'v': _num(e.get('value')), 'ic': e.get('includeChildSelections') == 'true'}

def _tree(e, op='and'):
    conds = [_cond(c) for c in _kids(e, 'conditions')]
    groups = [g for g in (_tree(x, x.get('type', 'and')) for x in _kids(e, 'conditionGroups')) if g]
    return {'op': op, 'c': conds, 'g': groups} if conds or groups else None

def _both(a, b):
    return {'op': 'and', 'c': [], 'g': [a, b]} if a and b else (a or b)

def _repeats(e):
    return [{'f': r.get('field', 'selections'), 's': r.get('scope', 'parent'), 'ch': r.get('childId', 'any'), 'v': _num(r.get('value')) or 1,
             'n': int(_num(r.get('repeats')) or 1), 'up': r.get('roundUp') == 'true', 'ic': r.get('includeChildSelections') == 'true'}
            for r in _kids(e, 'repeats')]

def _mods(e, outer=None, rep=()):
    out = []
    for m in _kids(e, 'modifiers'):
        x = {'t': m.get('type'), 'f': m.get('field'), 'v': m.get('value'), 'c': _both(outer, _tree(m)), 'r': list(rep) + _repeats(m)}
        out.append({k: v for k, v in x.items() if v not in (None, [])})
    for g in _kids(e, 'modifierGroups'):
        out += _mods(g, _both(outer, _tree(g)), list(rep) + _repeats(g))
    return out

def _cons(e):
    return [{'id': c.get('id'), 't': c.get('type'), 'v': _num(c.get('value')), 's': c.get('scope', 'parent'), 'f': c.get('field', 'selections'),
             'ic': c.get('includeChildSelections') == 'true', 'sh': c.get('shared', 'true') != 'false'} for c in _kids(e, 'constraints')]

class RosterCompiler:
    """BattleScribe catalogue -> compact, link-expanded selection tree with constraints and modifiers.

    Node keys follow BattleScribe roster entry ids: the entryLink ids walked from the force root plus the
    entry's own id, joined with '::' (groups give the entryGroupId the same way)."""
    MAX_NODES = 6000

    def __init__(self, cat, gst_root, cats=None):
        self.cat, self.gst = cat, gst_root
        self.roots = bs_roots(cat, gst_root, cats)
        self.ids = bs_ids(self.roots)
        self.profiles, self.rules, self.count = {}, {}, 0
        self.cats = {}
        for root in self.roots:
            for c in _iter(root, 'categoryEntry'): self.cats.setdefault(c.get('id'), c.get('name'))

    def profile(self, p):
        i = p.get('id')
        if i not in self.profiles:
            self.profiles[i] = {'n': p.get('name'), 't': p.get('typeName'), 'ti': p.get('typeId'),
                                'c': [[c.get('name'), c.get('typeId'), (c.text or '').strip()] for c in _iter(p, 'characteristic')]}
        return i

    def rule(self, r):
        i = r.get('id')
        if i not in self.rules: self.rules[i] = {'n': r.get('name'), 'd': _desc(r)}
        return i

    def info(self, e):
        pids = [self.profile(p) for p in _kids(e, 'profiles')]
        rids = [self.rule(r) for r in _kids(e, 'rules')]
        for l in _kids(e, 'infoLinks'):
            tg = self.ids.get(l.get('targetId'))
            if tg is None: continue
            if _tag(tg) == 'profile': pids.append(self.profile(tg))
            elif _tag(tg) == 'rule': rids.append(self.rule(tg))
        return pids, rids

    def node(self, e, link, path, chain, depth):
        self.count += 1
        if self.count > self.MAX_NODES: raise ValueError(f'{self.cat.get("name")}: roster tree too large')
        parts = path + ((link.get('id'),) if link is not None else ())
        own, group = e.get('id'), _tag(e) == 'selectionEntryGroup'
        n = {'k': '::'.join(parts + (own,)), 'id': own, 'n': e.get('name') or (link.get('name') if link is not None else ''),
             't': 'group' if group else e.get('type', 'upgrade')}
        srcs = [e] + ([link] if link is not None else [])
        if any(s.get('hidden') == 'true' for s in srcs): n['h'] = 1
        con = [c for s in srcs for c in _cons(s)]
        mod = [m for s in srcs for m in _mods(s)]
        cats, prim = [], None
        for s in srcs:
            for cl in _kids(s, 'categoryLinks'):
                if cl.get('targetId') not in cats: cats.append(cl.get('targetId'))
                if cl.get('primary') == 'true': prim = cl.get('targetId')
        if con: n['con'] = con
        if mod: n['mod'] = mod
        if cats: n['cat'] = cats
        if prim: n['pc'] = prim
        if group and e.get('defaultSelectionEntryId') not in (None, '', 'none'): n['def'] = e.get('defaultSelectionEntryId')
        pids, rids = [], []
        for s in srcs:
            p, r = self.info(s); pids += p; rids += r
        if pids: n['p'] = list(dict.fromkeys(pids))
        if rids: n['r'] = list(dict.fromkeys(rids))
        kids = []
        if depth < 12:
            for s in srcs:
                for c in _kids(s, 'selectionEntries') + _kids(s, 'selectionEntryGroups'):
                    if c.get('id') not in chain: kids.append(self.node(c, None, parts, chain | {c.get('id')}, depth + 1))
                for l in _kids(s, 'entryLinks'):
                    tg = self.ids.get(l.get('targetId'))
                    if tg is not None and _tag(tg) in ('selectionEntry', 'selectionEntryGroup') and tg.get('id') not in chain:
                        kids.append(self.node(tg, l, parts, chain | {tg.get('id')}, depth + 1))
        if kids: n['ch'] = kids
        return n

    def schema(self):
        fe = next(iter(_kids(self.cat, 'forceEntries')), None)
        if fe is None: return None
        force = {'id': fe.get('id'), 'n': fe.get('name'), 'cats': []}
        for cl in _kids(fe, 'categoryLinks'):
            x = {'id': cl.get('id'), 'tg': cl.get('targetId'), 'n': self.cats.get(cl.get('targetId')) or cl.get('name'),
                 'con': _cons(cl), 'mod': _mods(cl)}
            force['cats'].append({k: v for k, v in x.items() if v != []})
        root = []
        for r in [self.cat, self.gst]:
            for c in _kids(r, 'selectionEntries'): root.append(self.node(c, None, (), {c.get('id')}, 0))
            for l in _kids(r, 'entryLinks'):
                tg = self.ids.get(l.get('targetId'))
                if tg is not None and _tag(tg) in ('selectionEntry', 'selectionEntryGroup'):
                    root.append(self.node(tg, l, (), {tg.get('id')}, 0))
        used = set(force_cat['tg'] for force_cat in force['cats'])
        def walk(ns):
            for n in ns:
                used.update(n.get('cat', []))
                walk(n.get('ch', []))
        walk(root)
        return {'v': 1, 'gs': {'id': self.gst.get('id'), 'n': self.gst.get('name'), 'rev': self.gst.get('revision')},
                'cat': {'id': self.cat.get('id'), 'n': self.cat.get('name'), 'rev': self.cat.get('revision')},
                'force': force, 'root': root, 'cats': {k: v for k, v in self.cats.items() if k in used},
                'profiles': self.profiles, 'rules': self.rules}

def bs_match(name, ops, team=''):
    k = norm(name); tt = set(norm(team).split())
    for o in ops:
        if norm(o['name']) == k: return o
    for o in ops:
        b = norm(o['name'])
        if k.endswith(' ' + b) or b.endswith(' ' + k): return o
    ks = set(k.split()) - tt
    for o in ops:
        if ks and set(norm(o['name']).split()) - tt == ks: return o
    return None

# ---------------------------------------------------------------- merge
# ---------------------------------------------------------------- faction rules: options (v1.8)
GENERIC_OPT = re.compile(r'^(when|effect|atk hit dmg)\s*:?$', re.I)
SUBOPT = re.compile(r'(?<=[.!?”"\)])\s+([A-Z][\w’\'-]+(?: [A-Z][\w’\'-]+){0,3}) (\(\d+\))\s')

def is_fragment(name, text):
    """kt-datacards sometimes cuts a continued paragraph into a fake option (name = first 40 characters)."""
    n, t = name.strip(), text.strip()
    if not n or t[:1].islower(): return True
    if re.search(r'(\s(or|and|the|a|an|of|to|in|on|if|for|with|its|is|be|are)|,)$', n, re.I): return True
    if n.endswith(('.', ')', ').')) or n.endswith(':') and not GENERIC_OPT.match(n): return True
    words = n.split()
    return len(words) > 5 and not is_caps(n) and sum(w[:1].islower() for w in words) >= 2

def bs_blocks(text):
    """BSData description (plain lines, '•' bullets, **bold**) -> body blocks."""
    out = []
    for l in str(text or '').replace('\r', '').split('\n'):
        l = l.strip()
        if not l: continue
        b = re.match(r'^([•▪\-–])\s+(.*)$', l)
        out.append({'k': 'li2', 't': b.group(2)} if b else {'k': 'p', 't': l})
    return out

def _rule_key(s): return re.sub(r'\b\d+\b', '', norm(s)).strip()
def rule_match(a, b):
    a, b = _rule_key(a), _rule_key(b)
    if not a or not b: return False
    if a == b: return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 6 and re.search(r'(^| )' + re.escape(short) + r'( |$)', long_) is not None

def split_option(name, text, known=()):
    """'Redeploy' + '(1) ... Reposition (2) ...' -> [('Redeploy (1)', ...), ('Reposition (2)', ...)]."""
    m0 = re.match(r'^\((\d+)\)\s*', text)
    cur = f'{name} ({m0.group(1)})' if m0 else name
    if m0: text = text[m0.end():]
    cuts = [(m.start(), m.end(), f'{m.group(1)} {m.group(2)}') for m in SUBOPT.finditer(text)]
    for k in known:
        for m in re.finditer(r'(?<=[.!?”"])\s+(' + re.escape(k) + r')\s+(?=[A-Z])', text):
            cuts.append((m.start(), m.end(), k))
    parts, last = [], 0
    for a, b, n in sorted(set(cuts)):
        if a < last: continue
        parts.append((cur, text[last:a].strip())); cur, last = n, b
    parts.append((cur, text[last:].strip()))
    return [(n, t) for n, t in parts if t]

def faction_rules(items, bs):
    """Every faction rule with all of its text: fake options are glued back, merged options are split,
    BSData option lists (Chapter Tactics, Boons of Tzeentch, Sanguavitae...) replace garbled ones."""
    bs = bs or {}
    lists = bs.get('option_lists') or {}
    bsrules = bs.get('rules') or []
    known = sorted({o['name'] for lst in lists.values() for o in lst if len(o['name']) >= 6 or ' ' in o['name']}, key=len, reverse=True)
    used, out = set(), []
    for it in items:
        raw, slug = it.pop('_raw', ''), it.pop('_slug', '')
        opts, cont, real = it.pop('options', None) or [], [], []
        for o in opts:
            n, t = o['name'].strip(), o['text'].strip()
            if is_fragment(n, t):
                cont.append((n + ('…' if len(n) == 40 and n[-1:].isalpha() else '') + ' ' + t).strip())
            elif GENERIC_OPT.match(n):
                cont.append(t)
            else:
                real += split_option(title(n) if is_caps(n) else n, t, known)
        lossy = bool(cont) or 'CONTINUES ON OTHER SIDE' in raw or (it['body'] and it['body'][-1]['t'].rstrip().endswith(':'))
        bsr = next((r for r in bsrules if rule_match(it['name'], r['name']) or rule_match(slug.replace('-', ' '), r['name'])), None)
        if lossy and bsr:
            lore = [b for b in it['body'][:1] if b['k'] == 'lore']
            it['body'] = lore + bs_blocks(bsr['text'])
            it['src'] = 'bsdata'
            flat = norm(bsr['text'])
            real = [(n, t) for n, t in real if norm(t)[:40] not in flat]
        else:
            for c in cont:
                extra = [{'k': 'p' if b['k'] == 'lore' else b['k'], 't': b['t']} for b in blocks(c)[1]]
                if extra and it['body'] and it['body'][-1]['k'] == 'p' and not it['body'][-1]['t'].rstrip().endswith(('.', '!', '?', ':', '”')):
                    it['body'][-1] = {'k': 'p', 't': it['body'][-1]['t'].rstrip() + ' ' + extra.pop(0)['t']}
                it['body'] += extra
        bso = []
        for key, lst in lists.items():
            if key not in used and (rule_match(it['name'], key) or rule_match(slug.replace('-', ' '), key)):
                for o in lst:
                    if norm(o['name']) not in {norm(x['name']) for x in bso}: bso.append(o)
                used.add(key)
        if len(bso) >= 2:
            names = {norm(o['name']) for o in bso}
            heads = [o['name'] for o in bso]
            cut = next((i for i, b in enumerate(it['body']) if b['k'] != 'lore' and any(
                b['t'] == h or b['t'].startswith(h + ' ') for h in heads)), None)
            if cut is not None: it['body'] = it['body'][:cut]
            it['options'] = [{'name': o['name'], 'body': bs_blocks(o['text']), 'src': 'bsdata'} for o in bso]
            used.update(names)
        elif real:
            real = [(n, t) for n, t in real if norm(n) not in used]
            if real: it['options'] = [{'name': n, 'body': [{'k': 'p' if b['k'] == 'lore' else b['k'], 't': b['t']} for b in blocks(t)[1]] or [{'k': 'p', 't': t}]} for n, t in real]
        out.append(it)
    have = ' '.join(norm(i['name']) + ' ' + ' '.join(norm(b['t']) for b in i['body'] + [x for o in i.get('options', []) for x in o['body']]) for i in out)
    for r in bsrules:
        key = norm(r['name'].lstrip('*'))
        if key and key not in have and not any(rule_match(r['name'], i['name']) for i in out):
            it = {'name': r['name'].lstrip('*').strip(), 'body': bs_blocks(r['text']), 'src': 'bsdata'}
            bso = [o for k, lst in lists.items() if k not in used and rule_match(r['name'], k) for o in lst]
            if len(bso) >= 2: it['options'] = [{'name': o['name'], 'body': bs_blocks(o['text']), 'src': 'bsdata'} for o in bso]
            out.append(it)
    return out

def build_team(slug, ktd, bs, images, ktd_src, bs_src):
    warnings = []
    team_name = (bs or {}).get('name') or title(slug.replace('-', ' '))
    if slug == 'xv26-stealth-battlesuits': team_name = 'XV26 Stealth Battlesuits'
    bops = (bs or {}).get('operatives', [])
    operatives = []
    if ktd:
        for c in ktd.get('datacards', []):
            name = title(c.get('name', ''))
            st = {'apl': stat(c.get('apl')), 'move': stat(c.get('movement')), 'save': stat(c.get('save')), 'wounds': stat(c.get('wounds'))}
            b = bs_match(c.get('name', ''), bops, slug.replace('-', ' '))
            conflicts = {}
            if b:
                for k in st:
                    if b['stats'].get(k) and st[k] != b['stats'][k]: conflicts[k] = b['stats'][k]
                if conflicts: warnings.append(f'{slug}/{name}: stats differ from BSData {conflicts}')
            bw = {norm(w['name']): w for w in (b or {}).get('weapons', [])}
            weapons = []
            for w in c.get('weapons') or []:
                wn = clean_weapon(w.get('name', ''))
                m = bw.get(norm(wn))
                wr = str(w.get('special_rules') or '').strip()
                kind = (m or {}).get('type') or guess_type(wn, wr)
                weapons.append({'name': wn, 'type': kind, 'atk': stat(w.get('attacks')), 'hit': stat(w.get('hit')),
                                'dmg': stat(w.get('damage')), 'wr': wr})
            abilities = [{'name': a.get('name', ''), 'text': a.get('description', '')} for a in c.get('passive_abilities') or []]
            actions = [{'name': a.get('name', ''), 'text': a.get('description', '')} for a in c.get('unique_actions') or []]
            img = images.get(slugify(c.get('name', '')))
            operatives.append({'name': name, 'stats': st, 'base': c.get('base_size'), 'keywords': c.get('keywords') or [],
                               'weapons': weapons, 'abilities': abilities, 'actions': actions, 'conflicts': conflicts,
                               'card': img, 'bsdata': bool(b)})
    else:
        for b in bops:
            operatives.append({'name': title(b['name']), 'stats': b['stats'], 'base': None, 'keywords': [],
                               'weapons': b['weapons'], 'abilities': [a for a in b['abilities'] if a['kind'] == 'ability'],
                               'actions': [a for a in b['abilities'] if a['kind'] == 'action'], 'conflicts': {}, 'card': None, 'bsdata': True})
        warnings.append(f'{slug}: only BSData (no ploys; rules and equipment from BSData)')
    def section(key):
        out = []
        for x in (ktd or {}).get(key, []) or []:
            t, body = blocks(x.get('text', ''), x.get('name', ''))
            item = {'name': t, 'body': body}
            if x.get('options'): item['options'] = [{'name': o.get('name', ''), 'text': o.get('text', '')} for o in x['options']]
            if key == 'faction_rules': item['_raw'], item['_slug'] = x.get('text', ''), x.get('name', '')
            out.append(item)
        return out
    selection, archetypes = [], []
    for x in (ktd or {}).get('operatives_selection', []) or []:
        txt = x.get('text', '')
        m = re.search(r'ARCHETYPES?:\s*([^\n]+)', txt)
        if m: archetypes = [title(a.strip()) for a in m.group(1).split(',') if title(a.strip()) in ARCHETYPES]
        selection.append({'name': 'Operatives', 'body': [b for b in blocks(re.sub(r'.*ARCHETYPES?:[^\n]*\n', '', txt, flags=re.S), '')[1] if b['t'] not in ('OPERATIVES',)]})
    rules, equipment = faction_rules(section('faction_rules'), bs), section('equipment')
    footer = {norm(team_name), norm(slug.replace('-', ' '))}
    data_secs = {k: section(k) for k in ('strategy_ploys', 'firefight_ploys')}
    for sec in (rules, equipment, *data_secs.values()):
        for it in sec:  # a team-name line at the end of a card is its footer, not a heading
            while it['body'] and it['body'][-1]['k'] == 'h' and norm(it['body'][-1]['t']) in footer: it['body'].pop()
    if not ktd and bs:
        equipment = [{'name': o['name'], 'body': bs_blocks(o['text']), 'src': 'bsdata'}
                     for o in (bs.get('option_lists') or {}).get('Faction Equipment', [])]
    data = {'name': team_name, 'archetypes': archetypes, 'operatives': operatives, 'faction_rules': rules,
            'strategy_ploys': data_secs['strategy_ploys'], 'firefight_ploys': data_secs['firefight_ploys'],
            'equipment': equipment, 'selection': selection}
    sources = {}
    if ktd: sources['kt_datacards'] = {**ktd_src, 'team': slug, 'generated_at': ktd.get('generated_at')}
    if bs: sources['bsdata'] = {**bs_src, 'catalogue': bs.get('name'), 'revision': bs.get('revision'), 'comment': bs.get('comment')}
    team = {'slug': slug, 'name': team_name, 'data': data, 'sources': sources}
    if bs and bs.get('roster'): team['roster'] = bs['roster']
    return team, warnings

def fetch(ktd_ref='main', bs_ref='master', log=sys.stderr):
    ks = gh_json(f'repos/{KTD}/commits/{ktd_ref}')['sha']
    bss = gh_json(f'repos/{BSD}/commits/{bs_ref}')['sha']
    print(f'kt-datacards {ks[:10]}, BSData {bss[:10]}', file=log)
    kt_tree = [t['path'] for t in gh_json(f'repos/{KTD}/git/trees/{ks}?recursive=1')['tree']]
    bs_tree = [t['path'] for t in gh_json(f'repos/{BSD}/git/trees/{bss}?recursive=1')['tree']]
    kt_files = sorted(p for p in kt_tree if re.match(r'^output/[a-z0-9-]+/data/[a-z0-9-]+-team-data\.json$', p))
    bs_files = sorted(p for p in bs_tree if p.startswith('2024 - ') and p.endswith('.cat'))
    gst = next(p for p in bs_tree if p.startswith('2024 - ') and p.endswith('.gst'))
    with ThreadPoolExecutor(8) as ex:
        kt_raw = dict(zip(kt_files, ex.map(lambda p: http(raw(KTD, ks, p)), kt_files)))
        bs_raw = dict(zip(bs_files, ex.map(lambda p: http(raw(BSD, bss, p)), bs_files)))
    gst_root = ET.fromstring(http(raw(BSD, bss, gst)))
    bs_roots_ = {p: ET.fromstring(b) for p, b in bs_raw.items()}
    by_id = {r.get('id'): r for r in bs_roots_.values()}
    images = {}
    for p in kt_tree:
        m = re.match(r'^output/([a-z0-9-]+)/cards/datacards/(.+)-front\.(jpg|png)$', p)
        if m: images.setdefault(m.group(1), {})[m.group(2)] = raw(KTD, ks, p)
    return build({p.split('/')[1]: json.loads(b) for p, b in kt_raw.items()},
                 {p[7:-4]: bs_parse(r, gst_root, by_id) for p, r in bs_roots_.items()}, images,
                 {'repo': KTD, 'commit': ks}, {'repo': BSD, 'commit': bss}, log)

SKIP_BS = {'non player operative'}
def build(ktd, bs, images, ktd_src, bs_src, log=sys.stderr):
    bs_by = {norm(k): (k, v) for k, v in bs.items() if norm(k) not in SKIP_BS}
    alias = {norm('xv26-stealth-battlesuits'): norm('XV26 Battlesuits')}
    teams, warnings, used = [], [], set()
    for slug, d in sorted(ktd.items()):
        key = alias.get(norm(slug), norm(slug))
        file, b = bs_by.get(key, (None, None))
        if file: used.add(key)
        else: warnings.append(f'{slug}: not found in BSData')
        t, w = build_team(slug, d, b, images.get(slug, {}), {**ktd_src, 'path': f'output/{slug}/data/{slug}-team-data.json'},
                          {**bs_src, 'path': f'2024 - {file}.cat'} if file else bs_src)
        teams.append(t); warnings += w
    for key, (file, b) in sorted(bs_by.items()):
        if key in used: continue
        slug = slugify(file)
        t, w = build_team(slug, None, b, {}, ktd_src, {**bs_src, 'path': f'2024 - {file}.cat'})
        teams.append(t); warnings += w
    for w in warnings: print('warning:', w, file=log)
    return {'format': FORMAT, 'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'sources': {'kt_datacards': ktd_src, 'bsdata': bs_src}, 'teams': teams, 'warnings': warnings[:500]}

# ---------------------------------------------------------------- load
def validate(bundle):
    if not isinstance(bundle, dict) or bundle.get('format') not in FORMATS: raise ValueError('not a killstass team bundle')
    teams = bundle.get('teams')
    if not isinstance(teams, list) or not 1 <= len(teams) <= 300: raise ValueError('bundle must contain 1..300 teams')
    seen = set()
    for t in teams:
        if not re.match(r'^[a-z0-9][a-z0-9-]{1,63}$', str(t.get('slug', ''))): raise ValueError(f'bad slug {t.get("slug")!r}')
        if t['slug'] in seen: raise ValueError(f'duplicate slug {t["slug"]}')
        seen.add(t['slug'])
        if not isinstance(t.get('data'), dict) or not isinstance(t['data'].get('operatives'), list): raise ValueError(f'{t["slug"]}: no operatives')
        if not 1 <= len(str(t.get('name', ''))) <= 120: raise ValueError(f'{t["slug"]}: bad name')
    return teams

def lit(v):
    """SQL string literal (standard_conforming_strings is forced on in the generated script)."""
    return "'" + str(v).replace('\x00', '').replace("'", "''") + "'"

def catalog_pattern(slug):
    # Matches catalog codes like 2024-wahapedia-team-kommandos / ...-team-fellgor-ravager (optional plural "s").
    return '-team-' + '-'.join(re.escape(w) + 's?' for w in norm(slug).split()) + '$'

def to_sql(bundle):
    """Bundle -> one SQL script run by the database OWNER (the app role can only read team_data)."""
    teams = validate(bundle)
    out = ['SET LOCAL standard_conforming_strings = on;', "SET LOCAL client_min_messages = warning;"]
    ops = 0
    for t in teams:
        data = dict(t['data'])
        data['operatives'] = [{**o, 'card': o.get('card') if str(o.get('card') or '').startswith('https://') else None}
                              for o in data['operatives']]
        body = json.dumps(data, ensure_ascii=False, sort_keys=True)
        src = json.dumps(t.get('sources', {}), ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256((body + src).encode()).hexdigest()
        ops += len(data['operatives'])
        roster = t.get('roster') if isinstance(t.get('roster'), dict) and t['roster'].get('v') == 1 else None
        rbody = json.dumps(roster, ensure_ascii=False, sort_keys=True) if roster else None
        if rbody and len(rbody) > MAX_SCHEMA: raise ValueError(f'{t["slug"]}: roster schema too large')
        rsql = f"{lit(rbody)}::jsonb,{lit(hashlib.sha256(rbody.encode()).hexdigest())}" if rbody else 'NULL,NULL'
        out.append(f"""INSERT INTO team_data(slug,name,catalog_id,data,sources,content_hash,imported_at,active,roster_schema,roster_hash)
VALUES({lit(t['slug'])},{lit(t['name'])},(SELECT id FROM catalogs WHERE kind='team' AND edition='2024' AND code ~ {lit(catalog_pattern(t['slug']))} ORDER BY active DESC, id LIMIT 1),
{lit(body)}::jsonb,{lit(src)}::jsonb,{lit(h)},now(),true,{rsql})
ON CONFLICT(slug) DO UPDATE SET name=excluded.name,catalog_id=excluded.catalog_id,data=excluded.data,sources=excluded.sources,
content_hash=excluded.content_hash,imported_at=now(),active=true,roster_schema=excluded.roster_schema,roster_hash=excluded.roster_hash;""")
    slugs = ','.join(lit(t['slug']) for t in teams)
    out.append(f'UPDATE team_data SET active=false WHERE slug NOT IN ({slugs});')
    built = bundle.get('built_at')
    out.append('INSERT INTO team_data_imports(built_at,sources,teams,operatives,warnings) VALUES('
               f"{lit(built) + '::timestamptz' if built else 'NULL'},{lit(json.dumps(bundle.get('sources', {}), ensure_ascii=False))}::jsonb,"
               f"{len(teams)},{ops},{lit(json.dumps(bundle.get('warnings', [])[:500], ensure_ascii=False))}::jsonb);")
    out.append(REFRESH_SQL)
    out.append("SELECT format('teams: %s, operatives: %s, linked to catalog: %s', teams, operatives, "
               "(SELECT count(*) FROM team_data WHERE active AND catalog_id IS NOT NULL)) FROM team_data_imports ORDER BY id DESC LIMIT 1;")
    return '\n'.join(out) + '\n'

def load(bundle, conn):
    """Development/tests: run the same script on an owner connection."""
    sql = to_sql(bundle)
    with conn.transaction():
        conn.execute(sql)
    r = conn.execute('SELECT teams, operatives, (SELECT count(*) FROM team_data WHERE active AND catalog_id IS NOT NULL) FROM team_data_imports ORDER BY id DESC LIMIT 1').fetchone()
    return {'teams': r[0], 'operatives': r[1], 'linked_to_catalog': r[2]}

def export(conn):
    """v1.11: active teams as a bundle (same format as fetch) for backups and scripts/update-reference.sh --rollback."""
    imp = conn.execute('SELECT built_at, sources, warnings FROM team_data_imports ORDER BY id DESC LIMIT 1').fetchone()
    teams = [{'slug': r[0], 'name': r[1], 'data': r[2], 'sources': r[3] or {}, 'roster': r[4]} for r in conn.execute(
        'SELECT slug, name, data, sources, roster_schema FROM team_data WHERE active ORDER BY slug').fetchall()]
    return {'format': FORMAT, 'built_at': imp[0].isoformat() if imp and imp[0] else None, 'sources': imp[1] if imp else {},
            'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'warnings': (imp[2] if imp else [])[:500], 'teams': teams}

def read_bundle(stream):
    data = stream.read(MAX_BUNDLE + 1)
    if len(data) > MAX_BUNDLE: raise SystemExit('bundle too large')
    return json.loads(data)

def main(argv):
    cmd = argv[1] if len(argv) > 1 else ''
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    if cmd == 'fetch':
        json.dump(fetch(opt('--ktd-ref', os.getenv('KTD_REF', 'main')), opt('--bsdata-ref', os.getenv('BSDATA_REF', 'master'))), sys.stdout, ensure_ascii=False)
        return 0
    if cmd == 'sql':
        sys.stdout.write(to_sql(read_bundle(sys.stdin.buffer)))
        return 0
    if cmd in ('load', 'status', 'export'):
        import psycopg
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            if cmd == 'load':
                print(json.dumps(load(read_bundle(sys.stdin.buffer), conn)))
            elif cmd == 'export':
                json.dump(export(conn), sys.stdout, ensure_ascii=False)
            else:
                r = conn.execute('SELECT imported_at, teams, operatives, sources FROM team_data_imports ORDER BY id DESC LIMIT 1').fetchone()
                print('no import yet' if not r else f'{r[0]:%Y-%m-%d %H:%M} UTC: {r[1]} teams, {r[2]} operatives, sources {json.dumps(r[3])}')
        return 0
    print(__doc__, file=sys.stderr); return 2

if __name__ == '__main__':
    sys.exit(main(sys.argv))
