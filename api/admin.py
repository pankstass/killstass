"""v1.9: administrator page API (#admin) — instance overview, feedback inbox, user list (v1.11: rules reference status and update journal).

Administrators are flagged by the server operator (scripts/admin.sh grant LOGIN); the runtime database
role has no INSERT/UPDATE privilege on users.is_admin, so no request can grant it."""
from fastapi import Depends, Query
from pydantic import Field
from . import library
from . import main as core


class FeedbackHandle(core.Op):
    handled: bool


admin = core.admin_user


@core.app.get('/api/admin/overview')
def overview(u=Depends(admin)):
    with core.pool.connection() as c:
        counts = core.one(c, '''SELECT (SELECT count(*) FROM users)::int AS users,
        (SELECT count(*) FROM users WHERE is_admin)::int AS admins,
        (SELECT count(*) FROM sessions WHERE expires_at>now())::int AS sessions,
        (SELECT count(*) FROM rosters)::int AS rosters,
        (SELECT count(*) FROM tournaments)::int AS tournaments,
        (SELECT count(*) FROM feedback WHERE handled_at IS NULL)::int AS feedback_open,
        (SELECT count(*) FROM team_data WHERE active)::int AS teams,
        (SELECT coalesce(sum(count),0) FROM client_errors WHERE last_at>now()-interval '7 days')::int AS client_errors_week,
        pg_database_size(current_database())::bigint AS db_bytes''')
        statuses = core.allrows(c, 'SELECT status,count(*)::int AS n FROM matches GROUP BY status ORDER BY status')
        team_import = core.one(c, 'SELECT imported_at,teams,operatives,jsonb_array_length(warnings) AS warnings FROM team_data_imports ORDER BY id DESC LIMIT 1')
        migrations = core.allrows(c, 'SELECT version,applied_at FROM schema_migrations ORDER BY version')
        # v1.11: rules reference — "up to date as of" and the journal of scripts/update-reference.sh
        reference = {'status': library.status(c), 'updates': library.updates(c)}
    return {'version': core.APP_VERSION, 'migrations': migrations, 'counts': counts, 'matches': statuses, 'team_import': team_import,
            'reference': reference}


@core.app.get('/api/admin/feedback')
def feedback(status: str = Query('open', pattern='^(open|all)$'), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), u=Depends(admin)):
    where = 'WHERE f.handled_at IS NULL' if status == 'open' else ''
    with core.pool.connection() as c:
        return {'items': core.allrows(c, f'''SELECT f.id,f.created_at,f.handled_at,f.page,f.message,u.login,u.display_name,u.public_id
        FROM feedback f JOIN users u ON u.id=f.user_id {where} ORDER BY f.id DESC LIMIT %s OFFSET %s''', (limit, offset)),
                'total': core.one(c, f'SELECT count(*)::int AS n FROM feedback f {where}')['n']}


@core.app.post('/api/admin/feedback/{fid}')
def feedback_handle(fid: int, p: FeedbackHandle, u=Depends(admin)):
    with core.pool.connection() as c:
        def run():
            row = core.one(c, 'UPDATE feedback SET handled_at=CASE WHEN %s THEN coalesce(handled_at,now()) END WHERE id=%s RETURNING id,handled_at', (p.handled, fid))
            if not row:
                core.fail(404, 'feedback_not_found')
            return {'id': row['id'], 'handled_at': row['handled_at'].isoformat() if row['handled_at'] else None}
        return core.operation(c, u, p, 'admin-feedback:' + str(fid), run)


@core.app.get('/api/admin/users')
def users(q: str = Query('', max_length=64), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), u=Depends(admin)):
    like = '%' + q.strip() + '%'
    with core.pool.connection() as c:
        return {'items': core.allrows(c, '''SELECT u.public_id,u.login,u.display_name,u.email,u.is_admin,u.created_at,
        (SELECT count(*)::int FROM match_players p WHERE p.user_id=u.id) AS matches,
        (SELECT count(*)::int FROM rosters r WHERE r.user_id=u.id) AS rosters,
        (SELECT max(s.created_at) FROM sessions s WHERE s.user_id=u.id) AS last_login
        FROM users u WHERE u.login ILIKE %s OR u.display_name ILIKE %s OR u.public_id ILIKE %s
        ORDER BY u.created_at DESC LIMIT %s OFFSET %s''', (like, like, like, limit, offset)),
                'total': core.one(c, 'SELECT count(*)::int AS n FROM users u WHERE u.login ILIKE %s OR u.display_name ILIKE %s OR u.public_id ILIKE %s', (like, like, like))['n']}
