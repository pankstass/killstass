"""v1.10: one server-sent event stream per browser tab (/api/events).

`notify` carries the newest notification id of the player (sounds, vibration and toasts on any page);
with ?match=<id> the stream also sends the match events of /api/matches/<id>/events (revision, clock,
tracker), with ?board=<id> the `board` sequence of a killzone board. The per-match stream stays for tabs
opened before the update."""
import asyncio
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from . import main as core
from . import boards
from . import clock
from . import tracker

ITERATIONS, PAUSE = 150, 2  # reconnect every ~5 minutes; each iteration re-checks the session and membership


@core.app.get('/api/events')
async def events(request: Request, match: UUID | None = None, board: UUID | None = None, u=Depends(core.user)):
    with core.pool.connection() as c:
        if match:
            core.member(c, match, u['id'])
        if board:
            boards.access(c, board, u['id'])
    token_hash = core.digest(request.cookies.get(core.COOKIE, ''))

    def revision():
        with core.pool.connection() as c:
            if not core.one(c, 'SELECT 1 FROM sessions WHERE token_hash=%s AND expires_at>now()', (token_hash,)):
                return None
            out = {'notify': core.one(c, 'SELECT coalesce(max(id),0) AS n FROM notifications WHERE user_id=%s', (u['id'],))['n']}
            if match:
                try:
                    m = core.member(c, match, u['id'])
                except HTTPException:
                    return None
                out.update(revision=m['version'], clock=clock.seq(c, match), tracker=tracker.seq(c, match))
            if board:
                out['board'] = boards.seq(c, board_id=board)
            return out

    async def stream():
        previous = {}
        yield 'retry: 3000\n\n'
        for _ in range(ITERATIONS):
            if await request.is_disconnected():
                break
            v = await asyncio.to_thread(revision)
            if v is None:
                yield 'event: end\ndata: 0\n\n'
                break
            out = ''.join(f'event: {k}\ndata: {val}\n\n' for k, val in v.items() if previous.get(k) != val)
            yield out or ': heartbeat\n\n'
            previous = v
            await asyncio.sleep(PAUSE)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store'})
