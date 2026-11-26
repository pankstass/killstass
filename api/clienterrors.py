"""v1.14 (Т4): browser error log. web/errors.js reports unhandled errors and promise rejections (version, route
name, message, the start of the stack; never form data or URL parameters); #admin lists them.

Anonymous reports are accepted (an error on the sign-in page matters too) but rate-limited per address; a valid
session adds the user. One row per fingerprint and day — a repeat only raises its count — kept for 30 days and at
most ROW_CAP rows (new fingerprints are dropped beyond it, repeats still count)."""
import hashlib
import re
from fastapi import Depends, Query, Request
from pydantic import Field
from . import main as core

KEEP_DAYS, ROW_CAP, PER_WINDOW = 30, 5000, 30
URL = re.compile(r'(https?://[^/\s"\']+)?(/[^\s"\'?#)]*)[?#][^\s"\')]*')
SECRETISH = re.compile(r'\b[A-Za-z0-9_-]{32,}\b')


class ClientError(core.Model):
    kind: str = Field(default='error', pattern='^(error|rejection)$')
    message: str = Field(min_length=1, max_length=2000)
    source: str = Field(default='', max_length=1000)
    stack: str = Field(default='', max_length=8000)
    page: str = Field(default='', max_length=40, pattern='^[a-z0-9-]*$')
    version: str = Field(default='', max_length=20, pattern=r'^[0-9A-Za-z.+-]*$')


class ClearErrors(core.Op):
    pass


def scrub(text, n):
    """No query strings or fragments (they may carry codes) and no long token-like strings."""
    text = URL.sub(lambda m: (m.group(1) or '') + m.group(2), str(text or ''))
    return SECRETISH.sub('…', text).strip()[:n]


def session_user(request):
    token = request.cookies.get(core.COOKIE, '')
    if not token:
        return None
    with core.pool.connection() as c:
        r = core.one(c, 'SELECT user_id FROM sessions WHERE token_hash=%s AND expires_at>now()', (core.digest(token),))
    return r['user_id'] if r else None


@core.app.post('/api/client-errors', status_code=202)
def report(p: ClientError, request: Request):
    core.limit(request, 'client-error', PER_WINDOW)
    message, source, stack = scrub(p.message, 500), scrub(p.source, 200), scrub(p.stack, 2000)
    if not message:
        core.fail(422, 'message_required')
    agent = str(request.headers.get('user-agent', ''))[:160]
    fp = hashlib.sha256('\x1f'.join((p.kind, message, source, p.page, p.version)).encode()).hexdigest()
    uid = session_user(request)
    with core.pool.connection() as c:
        c.execute('DELETE FROM client_errors WHERE day < current_date - %s', (KEEP_DAYS,))
        hit = core.one(c, '''UPDATE client_errors SET count=count+1,last_at=now(),user_id=coalesce(%s,user_id)
            WHERE fingerprint=%s AND day=current_date RETURNING id''', (uid, fp))
        if not hit and core.one(c, 'SELECT count(*)::int AS n FROM client_errors')['n'] < ROW_CAP:
            c.execute('''INSERT INTO client_errors(fingerprint,kind,message,source,stack,page,version,agent,user_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(fingerprint,day) DO UPDATE SET count=client_errors.count+1,last_at=now()''',
                      (fp, p.kind, message, source, stack, p.page, p.version, agent, uid))
    return {'ok': True}


@core.app.get('/api/admin/client-errors')
def errors_list(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        return {'items': core.allrows(c, '''SELECT e.id,e.day,e.kind,e.message,e.source,e.stack,e.page,e.version,e.agent,e.count,
            e.first_at,e.last_at,u.login,u.public_id FROM client_errors e LEFT JOIN users u ON u.id=e.user_id
            ORDER BY e.last_at DESC,e.id DESC LIMIT %s OFFSET %s''', (limit, offset)),
                'total': core.one(c, 'SELECT count(*)::int AS n, coalesce(sum(count),0)::int AS events FROM client_errors'),
                'keep_days': KEEP_DAYS}


@core.app.post('/api/admin/client-errors/clear')
def errors_clear(p: ClearErrors, u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        def run():
            n = core.one(c, 'WITH d AS (DELETE FROM client_errors RETURNING 1) SELECT count(*)::int AS n FROM d')['n']
            return {'ok': True, 'deleted': n}
        return core.operation(c, u, p, 'admin-client-errors', run)
