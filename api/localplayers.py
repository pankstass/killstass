"""v1.13: local players — people without an account whom the club records matches against (hot-seat matches on
one device and quick records). One shared list: the same name (case- and ё-insensitive) is the same person for
every account. Their matches count in the club rating (api/insights.py, /api/ratings?scope=all); an
administrator deletes a record (the matches stay, with the name, but leave the rating)."""
from uuid import UUID, uuid4
from fastapi import Depends
from . import main as core

PER_USER = 300  # local players one account may create


def find_or_create(c, u, name):
    """(id, name) of the local player with this name, created by this account if there is none yet."""
    name = ' '.join(str(name).split())[:64]
    if not name: core.fail(422, 'local_player_name_required')
    row = core.one(c, 'SELECT id,name FROM local_players WHERE ks_fold(name)=ks_fold(%s)', (name,))
    if not row:
        if core.one(c, 'SELECT count(*)::int AS n FROM local_players WHERE created_by=%s', (u['id'],))['n'] >= PER_USER:
            core.fail(429, 'too_many_local_players')
        row = core.one(c, '''INSERT INTO local_players(id,name,created_by) VALUES(%s,%s,%s)
            ON CONFLICT (ks_fold(name)) DO NOTHING RETURNING id,name''', (str(uuid4()), name, u['id'])) \
            or core.one(c, 'SELECT id,name FROM local_players WHERE ks_fold(name)=ks_fold(%s)', (name,))
    return str(row['id']), row['name']


@core.app.get('/api/local-players')
def local_players(u=Depends(core.user)):
    """The club's local players (names for the opponent field), with the number of their matches."""
    with core.pool.connection() as c:
        return {'items': core.allrows(c, '''SELECT l.id,l.name,(SELECT count(*)::int FROM match_players p WHERE p.local_player_id=l.id) AS matches
        FROM local_players l ORDER BY l.name LIMIT 2000''')}


@core.app.get('/api/admin/local-players')
def admin_local_players(u=Depends(core.admin_user)):
    with core.pool.connection() as c:
        return {'items': core.allrows(c, '''SELECT l.id,l.name,l.created_at,cu.display_name AS created_by_name,cu.public_id AS created_by_id,
        count(p.id)::int AS matches,max(m.played_at) AS last_played
        FROM local_players l LEFT JOIN users cu ON cu.id=l.created_by
        LEFT JOIN match_players p ON p.local_player_id=l.id LEFT JOIN matches m ON m.id=p.match_id
        GROUP BY l.id,cu.display_name,cu.public_id ORDER BY l.name LIMIT 2000''')}


@core.app.delete('/api/admin/local-players/{lid}')
def admin_delete_local_player(lid: UUID, u=Depends(core.admin_user)):
    """The matches keep the name (match_players.display_name); local_player_id becomes NULL (ON DELETE SET NULL)."""
    with core.pool.connection() as c:
        if not core.one(c, 'DELETE FROM local_players WHERE id=%s RETURNING id', (str(lid),)):
            core.fail(404, 'local_player_not_found')
    return {'ok': True}
