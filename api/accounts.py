"""v1.10: password reset codes, player profile extras, avatars and the player page.

Reset codes are issued by an administrator (#admin, button «Сбросить пароль») or by the server operator
(`./scripts/admin.sh password LOGIN`, which runs `python -m api.accounts reset LOGIN` in the api container).
The player enters the code on the login page and chooses a new password; every session of the account ends.
Only a SHA-256 hash of the code is stored; a code expires after RESET_TTL_MINUTES and after 5 wrong attempts."""
import base64
import hashlib
import os
import secrets
import struct
import sys
from fastapi import Depends, Request, Response
from fastapi.responses import Response as RawResponse
from pydantic import Field, field_validator
from . import main as core

RESET_TTL_MINUTES = int(os.getenv('RESET_TTL_MINUTES', '60'))
RESET_ATTEMPTS = 5
AVATAR_MAX = 196608
AVATAR_SIDE = 512


def normalize_code(code):
    return ''.join(ch for ch in code.upper() if ch.isalnum())


def code_hash(user_id, code):
    return core.digest(f'{user_id}:{normalize_code(code)}')


def issue_code(c, user_id, created_by=None, ttl_minutes=RESET_TTL_MINUTES):
    """New one-time code for `user_id`; an earlier open code of the account stops working."""
    raw = ''.join(secrets.choice(core.INVITE_ALPHABET) for _ in range(8))
    c.execute('DELETE FROM password_resets WHERE user_id=%s AND used_at IS NULL', (user_id,))
    row = core.one(c, '''INSERT INTO password_resets(user_id,code_hash,created_by,expires_at)
    VALUES(%s,%s,%s,now()+make_interval(mins=>%s)) RETURNING expires_at''', (user_id, code_hash(user_id, raw), created_by, ttl_minutes))
    return {'code': raw[:4] + '-' + raw[4:], 'expires_at': row['expires_at'].isoformat(), 'ttl_minutes': ttl_minutes}


class ResetIssue(core.Op):
    pass


class ResetRedeem(core.Model):
    identity: str = Field(min_length=1, max_length=254)
    code: str = Field(min_length=8, max_length=16)
    new_password: str = Field(min_length=12, max_length=128)


@core.app.post('/api/admin/users/{public_id}/password-reset', status_code=201)
def admin_reset(public_id: str, p: ResetIssue, u=Depends(core.admin_user)):
    """Not stored in `operations` (the result holds the plain code): a repeated click issues a new code."""
    with core.pool.connection() as c:
        target = core.one(c, 'SELECT id,login,display_name,is_admin FROM users WHERE public_id=%s', (public_id.upper(),))
        if not target:
            core.fail(404, 'user_not_found')
        # Another administrator's password is reset by the server operator only (scripts/admin.sh password).
        if target['is_admin'] and target['id'] != u['id']:
            core.fail(403, 'reset_admin_forbidden')
        return {**issue_code(c, target['id'], u['id']), 'login': target['login'], 'display_name': target['display_name']}


@core.app.post('/api/auth/password-reset')
def redeem(p: ResetRedeem, request: Request, response: Response):
    core.limit(request, 'password-reset', 10)
    with core.pool.connection() as c:
        acc = core.one(c, 'SELECT id FROM users WHERE login=%s OR email=%s', (p.identity.lower(), p.identity.lower()))
        row = acc and core.one(c, '''SELECT * FROM password_resets WHERE user_id=%s AND used_at IS NULL AND expires_at>now()
        FOR UPDATE''', (acc['id'],))
        if not row:
            core.fail(400, 'reset_code_invalid')
        if not secrets.compare_digest(row['code_hash'], code_hash(acc['id'], p.code)):
            # A wrong attempt is counted even though the request fails; 5 attempts burn the code.
            c.execute('UPDATE password_resets SET attempts=attempts+1,used_at=CASE WHEN attempts+1>=%s THEN now() END WHERE id=%s',
                      (RESET_ATTEMPTS, row['id']))
            c.commit()
            core.fail(400, 'reset_code_invalid')
        c.execute('UPDATE password_resets SET used_at=now() WHERE id=%s', (row['id'],))
        c.execute('UPDATE users SET password_hash=%s WHERE id=%s', (core.hash_password(p.new_password), acc['id']))
        c.execute('DELETE FROM sessions WHERE user_id=%s', (acc['id'],))
        csrf = core.new_session(c, acc['id'], response)
    return {'csrf': csrf}


# ------------------------------------------------------------------ profile extras and avatar
class ProfileExtra(core.Model):
    motto: str | None = Field(default=None, max_length=140)
    favorite_team_id: int | None = None
    hidden: bool | None = None
    clear_team: bool = False


def extra(c, uid):
    row = core.one(c, 'SELECT motto,favorite_team_id,hidden FROM user_profiles WHERE user_id=%s', (uid,)) or \
        {'motto': '', 'favorite_team_id': None, 'hidden': False}
    av = core.one(c, 'SELECT sha256 FROM avatars WHERE user_id=%s', (uid,))
    return {**row, 'avatar': av['sha256'][:16] if av else None}


@core.app.get('/api/profile/extra')
def get_extra(u=Depends(core.user)):
    with core.pool.connection() as c:
        return extra(c, u['id'])


@core.app.patch('/api/profile/extra')
def patch_extra(p: ProfileExtra, u=Depends(core.user)):
    with core.pool.connection() as c:
        if p.favorite_team_id is not None and not core.one(c, "SELECT 1 FROM catalogs WHERE id=%s AND kind='team'", (p.favorite_team_id,)):
            core.fail(422, 'catalog_invalid')
        old = extra(c, u['id'])
        team = None if p.clear_team else p.favorite_team_id if p.favorite_team_id is not None else old['favorite_team_id']
        c.execute('''INSERT INTO user_profiles(user_id,motto,favorite_team_id,hidden) VALUES(%s,%s,%s,%s)
        ON CONFLICT(user_id) DO UPDATE SET motto=excluded.motto,favorite_team_id=excluded.favorite_team_id,
        hidden=excluded.hidden,updated_at=now()''',
                  (u['id'], (p.motto if p.motto is not None else old['motto']).strip(), team,
                   p.hidden if p.hidden is not None else old['hidden']))
        return extra(c, u['id'])


def image_size(mime, data):
    """(width, height) from the image header, or None when the bytes do not match the declared type."""
    if mime == 'image/png':
        if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
            return None
        return struct.unpack('>II', data[16:24])
    if mime == 'image/jpeg':
        if data[:3] != b'\xff\xd8\xff':
            return None
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack('>H', data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return w, h
            i += 2 + length
        return None
    if mime == 'image/webp':
        if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
            return None
        chunk = data[12:16]
        if chunk == b'VP8 ' and data[23:26] == b'\x9d\x01\x2a':
            w, h = struct.unpack('<HH', data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b'VP8L' and data[20] == 0x2F:
            b = int.from_bytes(data[21:25], 'little')
            return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if chunk == b'VP8X':
            return int.from_bytes(data[24:27], 'little') + 1, int.from_bytes(data[27:30], 'little') + 1
    return None


class Avatar(core.Model):
    mime: str = Field(pattern='^image/(png|jpeg|webp)$')
    data: str = Field(min_length=88, max_length=AVATAR_MAX * 4 // 3 + 8)

    @field_validator('data')
    @classmethod
    def b64(cls, v):
        try:
            raw = base64.b64decode(v, validate=True)
        except ValueError:
            raise ValueError('avatar_invalid')
        if not 64 <= len(raw) <= AVATAR_MAX:
            raise ValueError('avatar_too_large')
        return v


@core.app.post('/api/profile/avatar')
def put_avatar(p: Avatar, u=Depends(core.user)):
    raw = base64.b64decode(p.data)
    size = image_size(p.mime, raw)
    if not size or not (16 <= size[0] <= AVATAR_SIDE and 16 <= size[1] <= AVATAR_SIDE):
        core.fail(422, 'avatar_invalid')
    sha = hashlib.sha256(raw).hexdigest()
    with core.pool.connection() as c:
        c.execute('''INSERT INTO avatars(user_id,mime,data,sha256) VALUES(%s,%s,%s,%s)
        ON CONFLICT(user_id) DO UPDATE SET mime=excluded.mime,data=excluded.data,sha256=excluded.sha256,updated_at=now()''',
                  (u['id'], p.mime, raw, sha))
    return {'avatar': sha[:16]}


@core.app.delete('/api/profile/avatar')
def delete_avatar(u=Depends(core.user)):
    with core.pool.connection() as c:
        c.execute('DELETE FROM avatars WHERE user_id=%s', (u['id'],))
    return {'avatar': None}


def visible(c, viewer, target):
    """Hidden players are shown only to themselves, their accepted friends and administrators."""
    if target['id'] == viewer['id'] or not target.get('hidden') or viewer.get('is_admin'):
        return True
    return bool(core.one(c, '''SELECT 1 FROM friendships WHERE status='accepted' AND
    ((requester_id=%s AND recipient_id=%s) OR (requester_id=%s AND recipient_id=%s))''', (viewer['id'], target['id'], target['id'], viewer['id'])))


def avatar_response(row, request):
    etag = '"' + row['sha256'][:32] + '"'
    headers = {'ETag': etag, 'Cache-Control': 'private, max-age=86400'}
    if request.headers.get('if-none-match') == etag:
        return RawResponse(status_code=304, headers=headers)
    return RawResponse(bytes(row['data']), media_type=row['mime'], headers=headers)


@core.app.get('/api/users/{public_id}/avatar')
def get_avatar(public_id: str, request: Request, u=Depends(core.user)):
    with core.pool.connection() as c:
        target = core.one(c, '''SELECT u.id,coalesce(p.hidden,false) AS hidden FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
        WHERE u.public_id=%s''', (public_id.upper(),))
        row = target and visible(c, u, target) and core.one(c, 'SELECT mime,data,sha256 FROM avatars WHERE user_id=%s', (target['id'],))
    if not row:
        core.fail(404, 'avatar_not_found')
    return avatar_response(row, request)


@core.app.get('/api/players/{public_id}')
def player(public_id: str, u=Depends(core.user)):
    """Player page: profile, statistics, season rating, achievements, recent results and head-to-head."""
    from . import seasons
    with core.pool.connection() as c:
        t = core.one(c, '''SELECT u.id,u.public_id,u.display_name,u.created_at,coalesce(p.hidden,false) AS hidden,
        coalesce(p.motto,'') AS motto,p.favorite_team_id FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
        WHERE u.public_id=%s''', (public_id.upper(),))
        if not t or not visible(c, u, t):
            core.fail(404, 'player_not_found')
        seasons.award(c, t['id'], quiet=True)  # achievements of matches played before v1.10
        summary = core.one(c, '''SELECT count(*)::int AS games,count(*) FILTER(WHERE result='win')::int AS wins,
        count(*) FILTER(WHERE result='draw')::int AS draws,count(*) FILTER(WHERE result='loss')::int AS losses,
        round(avg(vp_for),1) AS avg_for,round(avg(vp_for-vp_against),1) AS avg_diff,max(played_at) AS last_played
        FROM player_results WHERE user_id=%s''', (t['id'],))
        summary['win_rate'] = round(100 * summary['wins'] / summary['games'], 1) if summary['games'] else None
        teams = core.allrows(c, '''SELECT team_id,count(*)::int AS games,count(*) FILTER(WHERE result='win')::int AS wins
        FROM player_results WHERE user_id=%s AND team_id IS NOT NULL GROUP BY team_id ORDER BY games DESC,wins DESC LIMIT 5''', (t['id'],))
        recent = core.allrows(c, '''SELECT r.match_id,r.played_at,r.kind,r.team_id,r.opponent_team_id,r.opponent_name,r.vp_for,r.vp_against,r.result,
        ou.public_id AS opponent_public_id,
        EXISTS(SELECT 1 FROM match_players mp WHERE mp.match_id=r.match_id AND mp.user_id=%s) AS viewer_played
        FROM player_results r LEFT JOIN users ou ON ou.id=r.opponent_id
        WHERE r.user_id=%s ORDER BY r.played_at DESC NULLS LAST LIMIT 10''', (u['id'], t['id']))
        for r in recent:
            if not r.pop('viewer_played'):
                r['match_id'] = None  # only participants open a match
        h2h = None
        if t['id'] != u['id']:
            h2h = core.one(c, '''SELECT count(*)::int AS games,count(*) FILTER(WHERE result='win')::int AS wins,
            count(*) FILTER(WHERE result='draw')::int AS draws,count(*) FILTER(WHERE result='loss')::int AS losses
            FROM player_results WHERE user_id=%s AND opponent_id=%s''', (u['id'], t['id']))
        friend = core.one(c, '''SELECT status,requester_id FROM friendships WHERE (requester_id=%s AND recipient_id=%s)
        OR (requester_id=%s AND recipient_id=%s)''', (u['id'], t['id'], t['id'], u['id']))
        av = core.one(c, 'SELECT sha256 FROM avatars WHERE user_id=%s', (t['id'],))
        return {'public_id': t['public_id'], 'display_name': t['display_name'], 'member_since': t['created_at'],
                'motto': t['motto'], 'favorite_team_id': t['favorite_team_id'], 'hidden': t['hidden'], 'me': t['id'] == u['id'],
                'avatar': av['sha256'][:16] if av else None, 'summary': summary, 'teams': teams, 'recent': recent,
                'head_to_head': h2h, 'friendship': friend and {'status': friend['status'], 'outgoing': friend['requester_id'] == u['id']},
                'season': seasons.player_season(c, t['id']), 'achievements': seasons.player_achievements(c, t['id'])}


# ------------------------------------------------------------------ operator CLI (scripts/admin.sh password LOGIN)
def cli(argv):
    import psycopg
    from psycopg.rows import dict_row
    if len(argv) != 2 or argv[0] != 'reset':
        print('usage: python -m api.accounts reset LOGIN', file=sys.stderr)
        return 2
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as c:
        target = c.execute('SELECT id,login,display_name FROM users WHERE login=%s', (argv[1].lower(),)).fetchone()
        if not target:
            print(f'No user with login {argv[1]}', file=sys.stderr)
            return 1
        r = issue_code(c, target['id'])
    print(f"Код сброса для {target['login']} ({target['display_name']}): {r['code']}")
    print(f"Действует {r['ttl_minutes']} мин. Игрок: страница входа → «Есть код сброса пароля» → логин, код и новый пароль.")
    return 0


if __name__ == '__main__':
    sys.exit(cli(sys.argv[1:]))
