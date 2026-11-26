"""KILLSTASS: build the Core Rules reference (#core) from the authoring sources in tools/core-rules/src.

    python3 tools/core-rules/build.py            # -> api/data/core-rules.json
    python3 tools/core-rules/build.py --check    # exit 1 if the JSON is not built from the current sources
    python3 tools/core-rules/build.py OUT SRC…   # other paths

The text is the current rules: the core book wording with the official updates (Core Rules: Update Log)
applied in place — no change marks, no page numbers.

Source format (one unit per line): @chapter id | EN | RU; @section id | EN | RU; ##/###/#### headings;
'- ' bullets (under 'N) ' items: sub-items); 'N) ' numbered; '> ' designer's note; '! ' example/diagram caption;
@note..@end; @box [title]..@end; @action Name | AP ('+ ' effect, '+ - ' sub-effect, '? ' condition)..@end;
@ploy Name | cost | kind..@end; @card Name | sub..@end; @stats a | b; @table (| a | b | rows, first = header)..@end;
@flow a > b > c | loop. Text: **bold**, *italic*.

v1.13: src/terms.md lists the terms with tooltips (game terms, terrain types, universal actions, weapon rules):
their definitions are referenced in the text above (never retold) and resolved here into 'terms' — see terms.md."""
import hashlib, json, os, re, sys

def slug(s):
    s = re.sub(r'\*+', '', s.lower()).replace('’', '').replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:48] or 'x'

def build(paths):
    chapters = []
    ch = sec = None
    stack = []          # open containers: dicts with 'blocks' (box/note/card/ploy) or action
    def blocks():
        for c in reversed(stack):
            if 'blocks' in c: return c['blocks']
        if sec is None:
            return ch.setdefault('intro', [])
        return sec['blocks']
    def top():
        return stack[-1] if stack else None
    for path in paths:
        lines = open(path, encoding='utf-8').read().split('\n')
        i = 0
        while i < len(lines):
            raw = lines[i]; i += 1
            line = raw.strip()
            if not line: continue
            if line.startswith('@chapter '):
                cid, en, ru = [x.strip() for x in line[9:].split('|')]
                ch = {'id': cid, 'title': en, 'ru': ru, 'sections': []}; chapters.append(ch); sec = None; continue
            if line.startswith('@section '):
                assert not stack, f'unclosed block before {line} in {path}'
                sid, en, ru = [x.strip() for x in line[9:].split('|')]
                sec = {'id': sid, 'title': en, 'ru': ru, 'blocks': []}; ch['sections'].append(sec); continue
            if line == '@end':
                stack.pop(); continue
            if line.startswith('@note'):
                b = {'t': 'note', 'blocks': []}; blocks().append(b); stack.append(b); continue
            if line.startswith('@box'):
                b = {'t': 'box', 'title': line[4:].strip(), 'blocks': []}; blocks().append(b); stack.append(b); continue
            if line.startswith('@card '):
                name, sub = [x.strip() for x in line[6:].split('|')]
                b = {'t': 'card', 'name': name, 'sub': sub, 'blocks': []}; blocks().append(b); stack.append(b); continue
            if line.startswith('@ploy '):
                name, cost, kind = [x.strip() for x in line[6:].split('|')]
                b = {'t': 'ploy', 'name': name, 'cost': cost, 'kind': kind, 'blocks': []}; blocks().append(b); stack.append(b); continue
            if line.startswith('@action '):
                name, ap = [x.strip() for x in line[8:].split('|')]
                b = {'t': 'action', 'name': name, 'ap': ap, 'eff': [], 'cond': []}; blocks().append(b); stack.append(b); continue
            if line.startswith('@stats '):
                b = {'t': 'stats', 'items': [x.strip() for x in line[7:].split('|')]}; blocks().append(b); continue
            if line.startswith('@flow '):
                body, _, loop = line[6:].partition('|')
                b = {'t': 'flow', 'items': [x.strip() for x in body.split('>')], 'loop': loop.strip()}; blocks().append(b); continue
            if line == '@table':
                rows = []
                while lines[i].strip() != '@end':
                    r = lines[i].strip(); i += 1
                    assert r.startswith('|') and r.endswith('|'), f'bad table row {r!r} in {path}:{i}'
                    rows.append([c.strip() for c in r[1:-1].split('|')])
                i += 1
                b = {'t': 'table', 'head': rows[0], 'rows': rows[1:]}; blocks().append(b); continue
            assert not line.startswith('@'), f'unknown directive {line!r} in {path}:{i}'
            t = top()
            if t is not None and t['t'] == 'action':
                if line.startswith('+ - '):
                    item = {'x': line[4:]}; t['eff'][-1].setdefault('sub', []).append(item)
                elif line.startswith('+ '):
                    item = {'x': line[2:]}; t['eff'].append(item)
                elif line.startswith('? '):
                    item = {'x': line[2:]}; t['cond'].append(item)
                else:
                    raise AssertionError(f'unexpected line inside action {line!r} in {path}:{i}')
                continue
            m = re.match(r'(#{2,5}) (.+)$', line)
            if m:
                b = {'t': 'h', 'l': len(m.group(1)), 'x': m.group(2).strip()}; blocks().append(b); continue
            bl = blocks()
            if line.startswith('- '):
                item = {'x': line[2:].strip()}
                prev = bl[-1] if bl else None
                if prev and prev['t'] == 'ol' and prev.get('_open'):
                    prev['items'][-1].setdefault('sub', []).append(item)
                elif prev and prev['t'] == 'ul':
                    prev['items'].append(item)
                else:
                    bl.append({'t': 'ul', 'items': [item]})
                continue
            m = re.match(r'(\d+)\) (.+)$', line)
            if m:
                item = {'n': m.group(1), 'x': m.group(2).strip()}
                prev = bl[-1] if bl else None
                if prev and prev['t'] == 'ol':
                    prev['items'].append(item)
                else:
                    bl.append({'t': 'ol', 'items': [item], '_open': True})
                continue
            if line.startswith('> '):
                prev = bl[-1] if bl else None
                if prev and prev['t'] == 'note' and prev.get('_auto'):
                    prev['blocks'].append({'t': 'p', 'x': line[2:].strip()})
                else:
                    prev = {'t': 'note', 'blocks': [{'t': 'p', 'x': line[2:].strip()}], '_auto': True}; bl.append(prev)
                continue
            if line.startswith('! '):
                b = {'t': 'ex', 'x': line[2:].strip()}; bl.append(b); continue
            b = {'t': 'p', 'x': line}; bl.append(b)
        assert not stack, f'unclosed block at end of {path}'
    return chapters

def finish(chapters):
    seen = set()
    def walk(bl, sec_id, shift):
        for b in bl:
            b.pop('_open', None); b.pop('_auto', None)
            if b['t'] == 'h':
                b['l'] = max(2, b['l'] - shift)
                base = sec_id + '--' + slug(b['x']); a = base; k = 2
                while a in seen: a = f'{base}-{k}'; k += 1
                seen.add(a); b['id'] = a
            for key in ('blocks',):
                if key in b: walk(b[key], sec_id, shift)
    for ch in chapters:
        if 'intro' in ch: walk(ch['intro'], ch['id'], 0)
        for s in ch['sections']:
            assert s['id'] not in seen, s['id']; seen.add(s['id'])
            levels = [b['l'] for b in s['blocks'] if b['t'] == 'h']
            shift = (min(levels) - 2) if levels else 0
            walk(s['blocks'], s['id'], shift)
    return chapters

# ------------------------------------------------------------------ v1.13: terms (tooltips)
KINDS = ('term', 'terrain', 'action', 'weapon')
plain_text = lambda x: re.sub(r'\*+', '', x)


def section_units(sec):
    """The definable text of a section in order: paragraphs and list items (also inside boxes, cards and ploys)
    with their enclosing headings, and actions; designer's notes, figure captions, tables and flows are not."""
    out, heads = [], []
    def walk(bl):
        for b in bl:
            t = b['t']
            if t == 'h':
                while heads and heads[-1][0] >= b['l']: heads.pop()
                heads.append((b['l'], b['id']))
            elif t == 'p':
                out.append({'x': b['x'], 'li': '', 'heads': [h for _, h in heads]})
            elif t in ('ul', 'ol'):
                for it in b['items']:
                    out.append({'x': it['x'], 'li': '- ' if t == 'ul' else it['n'] + ') ', 'heads': [h for _, h in heads]})
                    for sub in it.get('sub', []):
                        out.append({'x': sub['x'], 'li': '- ', 'heads': [h for _, h in heads]})
            elif t in ('box', 'card', 'ploy'):
                walk(b['blocks'])
            elif t == 'action':
                out.append({'action': b['name'], 'eff': b['eff'], 'cond': b['cond'], 'heads': [h for _, h in heads]})
    walk(sec['blocks'])
    return out


def tidy(x):
    """Drop the book's cross-references that only make sense on its pages («Intervening is explained here.»)."""
    return re.sub(r'\s*[A-Z][^.!?]*\bhere\.(?=\s|$)', '', x).strip()


def resolve(ref, chapters, where):
    """section[/heading][@Action][~prefix][+N] -> (section id, anchor, definition strings)."""
    m = re.fullmatch(r'([a-z0-9-]+)(?:/([a-z0-9-]+))?(?:@([^~+]+))?(?:~(.+?))?(?:\+(\d+))?', ref.strip())
    assert m, f'bad definition reference {ref!r} ({where})'
    sid, head, action, prefix, more = m.groups()
    found = [(c, s) for c in chapters for s in c['sections'] if s['id'] == sid]
    assert found, f'no section {sid!r} ({where})'
    ch, sec = found[0]
    units = section_units(sec)
    anchor = ''
    if head:
        anchor = f'{sid}--{head}'
        units = [u for u in units if anchor in u['heads']]
        assert units, f'no heading {anchor!r} ({where})'
    if action:
        acts = [u for u in units if u.get('action') == action.strip()]
        assert len(acts) == 1, f'no action {action!r} in {sid} ({where})'
        u = acts[0]
        lines = []
        for e in u['eff']:
            lines.append('▶ ' + e['x'])
            lines += ['▶ ' + x['x'] for x in e.get('sub', [])]
        lines += ['◆ ' + c['x'] for c in u['cond']]
        return ch, sec, anchor or (u['heads'][-1] if u['heads'] else ''), lines
    units = [u for u in units if 'action' not in u]
    if prefix:
        want = plain_text(prefix.strip())
        hits = [i for i, u in enumerate(units) if plain_text(u['x']).startswith(want)]
        assert hits, f'no text {prefix!r} in {sid} ({where})'
        units = units[hits[0]: hits[0] + 1 + int(more or 0)]
    elif not head:
        units = units[: 1 + int(more or 0)]
    if not anchor and units[0]['heads']: anchor = units[0]['heads'][-1]
    lines = [u['li'] + tidy(u['x']) for u in units]
    if len(lines) == 1 and lines[0].startswith('- '): lines[0] = lines[0][2:]
    return ch, sec, anchor, lines


def alias_re(src):
    """Compile one alias of terms.md into a JavaScript-compatible regular expression without capturing groups
    (the page joins all aliases into one RegExp per context and case mode, longest first)."""
    def unit(s, i):
        c = s[i]
        if c in '[{':
            close = ']' if c == '[' else '}'
            depth, j = 0, i
            while j < len(s):
                if s[j] in '[{': depth += 1
                elif s[j] in ']}':
                    depth -= 1
                    if depth == 0: break
                j += 1
            assert j < len(s) and s[j] == close, f'unbalanced alias {src!r}'
            parts, cur, d = [], '', 0
            for ch in s[i + 1:j]:
                if ch in '[{': d += 1
                if ch in ']}': d -= 1
                if ch == '|' and d == 0: parts.append(cur); cur = ''
                else: cur += ch
            parts.append(cur)
            return '(?:' + '|'.join(seq(p) for p in parts) + ')' + ('?' if c == '[' else ''), j + 1
        if c == '#': return '(?:\\d+|x)', i + 1
        if c == '"': return '["\u201d\u2033]', i + 1
        if c == '*': return "[A-Za-z\u2019' -]{1,30}?", i + 1
        if c == ' ': return '[ \u00a0]', i + 1
        if c.isalnum() or c in "'\u2019,/": return c, i + 1
        return '\\' + c, i + 1
    def seq(s):
        out, i = '', 0
        while i < len(s):
            r, i = unit(s, i)
            out += r
        return out
    main, _, follow = src.partition('>>')
    body = seq(main)
    if re.match(r'[A-Za-z0-9#]', main): body = '\\b' + body
    if follow: body += '(?=' + seq(follow) + ')'
    elif re.search(r'[A-Za-z0-9#\]}]$', main): body += '(?![A-Za-z0-9-])'
    return body


def split_aliases(s):
    """Comma-separated, but a comma inside [..] or {..} belongs to the alias."""
    out, cur, d = [], '', 0
    for ch in s:
        if ch in '[{': d += 1
        if ch in ']}': d -= 1
        if ch == ',' and d == 0: out.append(cur); cur = ''
        else: cur += ch
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def parse_terms(path, chapters):
    terms, ids = [], set()
    for n, raw in enumerate(open(path, encoding='utf-8').read().split('\n'), 1):
        line = raw.strip()
        if not line or line.startswith('#'): continue
        cols = [c.strip() for c in line.split(' | ')]
        where = f'{os.path.basename(path)}:{n}'
        assert len(cols) == 6, f'expected 6 columns ({where})'
        tid, kind, name, ru, refs, aliases = cols
        assert re.fullmatch(r'[a-z0-9-]+', tid) and tid not in ids, f'bad or repeated id {tid!r} ({where})'
        assert kind in KINDS, f'unknown kind {kind!r} ({where})'
        ids.add(tid)
        defs, first = [], None
        for ref in refs.split(' & '):
            ch, sec, anchor, lines = resolve(ref, chapters, where)
            first = first or (ch, sec, anchor)
            defs += lines
        ch, sec, anchor = first
        alias = []
        for a in split_aliases(aliases):
            flags = re.match(r'[\^@!]*', a).group(0)
            text = a[len(flags):]
            weapon = kind == 'weapon'
            cs = '^' in flags or weapon      # weapon rules: case-sensitive in rules text
            in_text = '@' not in flags
            in_wr = weapon and '!' not in flags or '@' in flags
            size = len(re.sub(r'[\[\]{}|>*]', '', text.split('>>')[0]))
            # t / w: in rules text / in the weapon rules of a datacard — 's' case-sensitive, 'i' any case, None: not there
            alias.append({'re': alias_re(text), 't': ('s' if cs else 'i') if in_text else None,
                          'w': 'i' if in_wr else None, 'n': size})
        terms.append({'id': tid, 'kind': kind, 'name': name, 'ru': ru, 'sec': sec['id'], 'anchor': anchor,
                      # «Core Rules · Key Principles › Cover», but «Core Rules · Shoot» in the chapter Core Rules itself
                      'where': sec['title'] if ch['id'] == 'rules' else f'{ch["title"]} › {sec["title"]}',
                      'where_ru': sec['ru'] if ch['id'] == 'rules' else f'{ch["ru"]} › {sec["ru"]}',
                      'def': defs, 'alias': alias})
    return terms


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES = [os.path.join(ROOT, 'tools', 'core-rules', 'src', f + '.md') for f in ('core', 'killzones', 'missions', 'appendix', 'terms')]
OUT = os.path.join(ROOT, 'api', 'data', 'core-rules.json')


def document(srcs):
    doc = {
        'format': 2,
        'title': 'Kill Team — Core Rules',
        'source': {
            'book': 'Warhammer 40,000: Kill Team — Core Book (2024)',
            'updates': 'Core Rules: Update Log, October ’26',
            'text': 'Current rules: the text of the core book with all the official updates applied.',
        },
        'chapters': finish(build([p for p in srcs if os.path.basename(p) != 'terms.md'])),
    }
    for p in srcs:
        if os.path.basename(p) == 'terms.md': doc['terms'] = parse_terms(p, doc['chapters'])
    body = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
    doc['version'] = hashlib.sha256(body.encode()).hexdigest()[:12]
    return doc, body


if __name__ == '__main__':
    args = sys.argv[1:]
    check = '--check' in args
    args = [a for a in args if a != '--check']
    out, srcs = (args[0], args[1:]) if args else (OUT, SOURCES)
    doc, body = document(srcs)
    text = json.dumps(doc, ensure_ascii=False, indent=1) + '\n'
    if check:
        try: current = open(out, encoding='utf-8').read()
        except OSError: current = ''
        if current != text:
            print(f'{out} is not built from the current sources: run python3 tools/core-rules/build.py', file=sys.stderr)
            sys.exit(1)
        print(out, 'up to date, version', doc['version'])
        sys.exit(0)
    with open(out, 'w', encoding='utf-8') as f: f.write(text)
    chapters = doc['chapters']
    n = sum(len(c['sections']) for c in chapters)
    words = len(re.findall(r'\w+', body))
    print(out, 'version', doc['version'], 'chapters', len(chapters), 'sections', n, 'words~', words, 'bytes', len(body.encode()))
