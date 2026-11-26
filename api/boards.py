"""v1.10: killzone boards («Схема килзоны») for reviewing a game.

A board is a top-down sketch of the killzone in inches (30" × 22" by default) with tokens: operatives of both
sides, objective markers, markers, terrain rectangles and arrows. Frame 0 is deployment, frame n is the end of
turning point n; replaying the frames shows how the game went. A match board is shared by its two players
(created from the match, operatives come from the tracker or the operative count); a free board is private.
Frames are saved whole with optimistic versions; `boards.seq` feeds the `board` event of /api/events.
v1.12: a board may carry ready-made terrain (`layout`, web/killzones.js) — the layout fixes the 30" × 22" size and
the drop zones; `layout_swap` gives player 1 the other drop zone. A match board on a Volkus map of the catalogue
starts with that map's layout."""
from uuid import UUID, uuid4
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core

OP_R, OBJ_R = 0.5, 0.79  # 25 mm base, 40 mm objective marker (radius, inches)
# v1.12: ready-made terrain (the geometry lives in web/killzones.js, tests/test_v112.py keeps the ids in step):
# the edge and the depth of player 1's drop zone; player 2 has the opposite edge.
LAYOUTS = {**{f'volkus-2025-{n}': ('left', 6) if n <= 3 else ('bottom', 3) for n in range(1, 7)},
           'volkus-example-3': ('right', 6)}
LAYOUT_SIZE = (30.0, 22.0)
KILLZONE_LAYOUTS = {f'2024-wahapedia-killzone-volkus-{n}': f'volkus-2025-{n}' for n in range(1, 7)}
OPPOSITE = {'left': 'right', 'right': 'left', 'top': 'bottom', 'bottom': 'top'}
LAYOUT_ID = r'^[a-z0-9-]{0,40}$'


class Token(core.Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,16}$')
    kind: str = Field(pattern='^(op|objective|marker|terrain|arrow)$')
    side: int = Field(default=0, ge=0, le=2)
    x: float = Field(ge=-10, le=70)
    y: float = Field(ge=-10, le=70)
    r: float | None = Field(default=None, ge=0.1, le=6)
    w: float | None = Field(default=None, ge=0.1, le=60)
    h: float | None = Field(default=None, ge=0.1, le=60)
    rot: float = Field(default=0, ge=-360, le=360)
    x2: float | None = Field(default=None, ge=-10, le=70)
    y2: float | None = Field(default=None, ge=-10, le=70)
    label: str = Field(default='', max_length=40)
    terrain: str | None = Field(default=None, pattern='^(heavy|light|vantage|wall)$')
    order: str | None = Field(default=None, pattern='^(engage|conceal)$')
    dead: bool = False


class FrameState(core.Model):
    tokens: list[Token] = Field(default_factory=list, max_length=400)


class FramePut(core.Model):
    version: int | None = Field(default=None, ge=1)  # None: the frame is new
    state: FrameState
    note: str = Field(default='', max_length=500)


class BoardCreate(core.Op):
    match_id: UUID | None = None
    title: str = Field(default='', max_length=80)
    width: float = Field(default=30, ge=6, le=60)
    height: float = Field(default=22, ge=6, le=60)
    layout: str | None = Field(default=None, pattern=LAYOUT_ID)  # None: from the match killzone, '': none
    swap: bool = False


class BoardPatch(core.Model):
    title: str | None = Field(default=None, max_length=80)
    width: float | None = Field(default=None, ge=6, le=60)
    height: float | None = Field(default=None, ge=6, le=60)
    layout: str | None = Field(default=None, pattern=LAYOUT_ID)  # None: unchanged, '': removed
    swap: bool | None = None


def layout_of(v):
    if v and v not in LAYOUTS:
        core.fail(422, 'layout_unknown')
    return v or None


def access(c, bid, uid, lock=False):
    b = core.one(c, 'SELECT * FROM boards WHERE id=%s' + (' FOR UPDATE' if lock else ''), (str(bid),))
    if b and b['match_id']:
        if not core.one(c, 'SELECT 1 FROM match_players WHERE match_id=%s AND user_id=%s', (str(b['match_id']), uid)):
            b = None
    elif b and b['owner_id'] != uid:
        b = None
    if not b:
        core.fail(404, 'board_not_found')
    return b


def seq(c, match_id=None, board_id=None):
    row = core.one(c, 'SELECT seq FROM boards WHERE ' + ('match_id=%s' if match_id else 'id=%s'), (str(match_id or board_id),))
    return row['seq'] if row else 0


def deployment(c, m, width, height, layout=None, swap=False):
    """Frame 0 of a match board: tracked operatives (or numbered tokens) along each side's board edge — inside the
    side's drop zone when the board has ready-made terrain."""
    tokens = []
    players = core.allrows(c, 'SELECT id,slot,operative_count FROM match_players WHERE match_id=%s ORDER BY slot', (str(m['id']),))
    for p in players:
        ops = core.allrows(c, 'SELECT id,name,wounds,order_token FROM match_operatives WHERE player_id=%s ORDER BY position', (p['id'],))
        labels = [o['name'][:40] for o in ops] or [str(i) for i in range(1, min(p['operative_count'] or 6, 20) + 1)]
        if layout:
            edge = LAYOUTS[layout][0]
            if swap != (p['slot'] == 2):
                edge = OPPOSITE[edge]
        else:
            edge = 'bottom' if p['slot'] == 1 else 'top'
        along = height if edge in ('left', 'right') else width
        cols = 2 if edge in ('left', 'right') and len(labels) > 12 else 1
        per = -(-len(labels) // cols)
        step = along / (per + 1)
        for i, name in enumerate(labels, 1):
            o = ops[i - 1] if ops else None
            col, row = divmod(i - 1, per)
            a, d = round(step * (row + 1), 2), 1.5 + 2 * col
            x, y = {'left': (d, a), 'right': (width - d, a), 'top': (a, d), 'bottom': (a, height - d)}[edge]
            tokens.append({'id': f"s{p['slot']}o{i}", 'kind': 'op', 'side': p['slot'], 'x': x, 'y': y, 'r': OP_R,
                           'label': name, 'order': o['order_token'] if o else None, 'dead': bool(o and o['wounds'] == 0)})
    return {'tokens': tokens}


def follow(c, b, uid, old, new):
    """New terrain or drop zones of a match board: operatives still standing where frame 0 put them move to the new
    starting spots; tokens a player has moved stay put."""
    m = core.one(c, 'SELECT id FROM matches WHERE id=%s', (str(b['match_id']),))
    f = core.one(c, 'SELECT state FROM board_frames WHERE board_id=%s AND frame=0 FOR UPDATE', (str(b['id']),))
    if not m or not f:
        return
    spots = lambda a: {t['id']: (t['x'], t['y']) for t in deployment(c, m, *a)['tokens']}
    was, now = spots(old), spots(new)
    moved = False
    for tok in f['state'].get('tokens', []):
        p, q = was.get(tok.get('id')), now.get(tok.get('id'))
        if tok.get('kind') == 'op' and p and q and abs(tok['x'] - p[0]) < 0.01 and abs(tok['y'] - p[1]) < 0.01:
            tok['x'], tok['y'] = q
            moved = True
    if moved:
        c.execute('UPDATE board_frames SET state=%s,version=version+1,updated_by=%s,updated_at=now() WHERE board_id=%s AND frame=0',
                  (Jsonb(f['state']), uid, str(b['id'])))


def payload(c, b, uid):
    frames = core.allrows(c, 'SELECT frame,state,note,version,updated_at FROM board_frames WHERE board_id=%s ORDER BY frame', (str(b['id']),))
    match = None
    if b['match_id']:
        m = core.one(c, 'SELECT id,status,current_turn,turns,mission_id,killzone_id,kind FROM matches WHERE id=%s', (str(b['match_id']),))
        match = {k: m[k] for k in ('id', 'status', 'current_turn', 'turns', 'mission_id', 'killzone_id', 'kind')}
        match['players'] = core.allrows(c, 'SELECT slot,display_name,team_id,user_id=%s AS me FROM match_players WHERE match_id=%s ORDER BY slot', (uid, str(m['id'])))
    return {'id': b['id'], 'title': b['title'], 'width': float(b['width']), 'height': float(b['height']), 'seq': b['seq'],
            'layout': b['layout'], 'swap': b['layout_swap'],
            'match': match, 'frames': frames, 'mine': b['owner_id'] == uid, 'updated_at': b['updated_at']}


@core.app.get('/api/boards')
def boards(u=Depends(core.user)):
    with core.pool.connection() as c:
        return core.allrows(c, '''SELECT b.id,b.title,b.match_id,b.updated_at,b.layout,m.mission_id,m.killzone_id,m.status,
        (SELECT count(*)::int FROM board_frames f WHERE f.board_id=b.id) AS frames,
        (SELECT string_agg(p.display_name,' — ' ORDER BY p.slot) FROM match_players p WHERE p.match_id=b.match_id) AS players
        FROM boards b LEFT JOIN matches m ON m.id=b.match_id
        WHERE b.owner_id=%s AND b.match_id IS NULL
           OR EXISTS(SELECT 1 FROM match_players p WHERE p.match_id=b.match_id AND p.user_id=%s)
        ORDER BY b.updated_at DESC LIMIT 100''', (u['id'], u['id']))


@core.app.post('/api/boards', status_code=201)
def create_board(p: BoardCreate, u=Depends(core.user)):
    with core.pool.connection() as c:
        def run():
            layout = layout_of(p.layout)
            if p.match_id:
                m = core.member(c, p.match_id, u['id'], True)
                old = core.one(c, 'SELECT id FROM boards WHERE match_id=%s', (str(m['id']),))
                if old:
                    return {'id': str(old['id'])}
                if p.layout is None and m['killzone_id']:
                    kz = core.one(c, 'SELECT code FROM catalogs WHERE id=%s', (m['killzone_id'],))
                    layout = KILLZONE_LAYOUTS.get(kz['code']) if kz else None
            elif core.one(c, 'SELECT count(*)::int AS n FROM boards WHERE owner_id=%s AND match_id IS NULL', (u['id'],))['n'] >= 50:
                core.fail(429, 'too_many_boards')
            width, height = LAYOUT_SIZE if layout else (p.width, p.height)
            swap = bool(layout and p.swap)
            state = deployment(c, m, width, height, layout, swap) if p.match_id else {'tokens': []}
            bid = str(uuid4())
            c.execute('INSERT INTO boards(id,owner_id,match_id,title,width,height,layout,layout_swap) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                      (bid, u['id'], str(p.match_id) if p.match_id else None, p.title.strip(), width, height, layout, swap))
            c.execute('INSERT INTO board_frames(board_id,frame,state,updated_by) VALUES(%s,0,%s,%s)', (bid, Jsonb(state), u['id']))
            return {'id': bid}
        return core.operation(c, u, p, 'board:create:' + str(p.match_id or ''), run)


@core.app.get('/api/boards/{bid}')
def get_board(bid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        return payload(c, access(c, bid, u['id']), u['id'])


@core.app.patch('/api/boards/{bid}')
def patch_board(bid: UUID, p: BoardPatch, u=Depends(core.user)):
    with core.pool.connection() as c:
        b = access(c, bid, u['id'], True)
        layout = b['layout'] if p.layout is None else layout_of(p.layout)
        swap = bool(layout and (b['layout_swap'] if p.swap is None else p.swap))
        width, height = LAYOUT_SIZE if layout else (p.width, p.height)
        c.execute('''UPDATE boards SET title=coalesce(%s,title),width=coalesce(%s,width),height=coalesce(%s,height),
        layout=%s,layout_swap=%s,seq=seq+1,updated_at=now() WHERE id=%s''',
                  (p.title.strip() if p.title is not None else None, width, height, layout, swap, str(b['id'])))
        if b['match_id'] and (layout, swap) != (b['layout'], b['layout_swap']):
            nb = access(c, bid, u['id'])
            follow(c, b, u['id'], (float(b['width']), float(b['height']), b['layout'], b['layout_swap']),
                   (float(nb['width']), float(nb['height']), layout, swap))
        return payload(c, access(c, bid, u['id']), u['id'])


@core.app.delete('/api/boards/{bid}')
def delete_board(bid: UUID, u=Depends(core.user)):
    with core.pool.connection() as c:
        b = access(c, bid, u['id'], True)
        c.execute('DELETE FROM boards WHERE id=%s', (str(b['id']),))
    return {'ok': True}


@core.app.put('/api/boards/{bid}/frames/{frame}')
def put_frame(bid: UUID, frame: int, p: FramePut, u=Depends(core.user)):
    if not 0 <= frame <= 12:
        core.fail(422, 'frame_invalid')
    with core.pool.connection() as c:
        b = access(c, bid, u['id'], True)
        old = core.one(c, 'SELECT version FROM board_frames WHERE board_id=%s AND frame=%s', (str(b['id']), frame))
        if (old['version'] if old else None) != p.version:
            core.fail(409, 'version_conflict')
        state = Jsonb(p.state.model_dump(exclude_none=True, exclude_defaults=False))
        if old:
            row = core.one(c, '''UPDATE board_frames SET state=%s,note=%s,version=version+1,updated_by=%s,updated_at=now()
            WHERE board_id=%s AND frame=%s RETURNING version''', (state, p.note, u['id'], str(b['id']), frame))
        else:
            row = core.one(c, 'INSERT INTO board_frames(board_id,frame,state,note,updated_by) VALUES(%s,%s,%s,%s,%s) RETURNING version',
                           (str(b['id']), frame, state, p.note, u['id']))
        s = core.one(c, 'UPDATE boards SET seq=seq+1,updated_at=now() WHERE id=%s RETURNING seq', (str(b['id']),))
        return {'frame': frame, 'version': row['version'], 'seq': s['seq']}


@core.app.delete('/api/boards/{bid}/frames/{frame}')
def delete_frame(bid: UUID, frame: int, u=Depends(core.user)):
    with core.pool.connection() as c:
        b = access(c, bid, u['id'], True)
        if frame == 0:
            core.fail(409, 'frame_required')
        c.execute('DELETE FROM board_frames WHERE board_id=%s AND frame=%s', (str(b['id']), frame))
        s = core.one(c, 'UPDATE boards SET seq=seq+1,updated_at=now() WHERE id=%s RETURNING seq', (str(b['id']),))
    return {'ok': True, 'seq': s['seq']}
