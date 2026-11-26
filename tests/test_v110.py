"""v1.10: password reset, profile/avatar/player page, seasons and achievements, game nights with calendar
export, TV screen, killzone boards, Web Push (RFC 8291/8292), user event stream, offline clock replay,
service worker, deployment files (archive update, domain, Let's Encrypt, Tailscale, push worker)."""
import base64
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import zlib
from datetime import date, datetime, timedelta, timezone
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text().strip()


def db():
    import psycopg
    return psycopg.connect(os.environ['TEST_DATABASE_URL'])


def delete(c, path):
    return c.request('DELETE', path, json={})


def make_admin(user):
    with db() as c:
        c.execute('UPDATE users SET is_admin=true WHERE id=%s', (user['id'],))


def third_client(name):
    from fastapi.testclient import TestClient
    from api.main import app, ORIGIN
    from tests.test_integration import register
    c = TestClient(app, base_url=ORIGIN, headers={'Origin': ORIGIN})
    return c, register(c, name)


def png(w=32, h=32):
    raw = b''.join(b'\x00' + bytes([(x * 7 + y * 3) % 256 for x in range(w)]) * 1 for y in range(h))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


# ------------------------------------------------------------------ pure helpers
def test_origins_accept_a_list():
    env = {**os.environ, 'APP_ORIGIN': 'https://killstass.su, https://192.168.1.250/', 'DATABASE_URL': 'postgresql://x@/y'}
    out = subprocess.run([sys.executable, '-c', 'from api.main import ORIGINS,ORIGIN;print(ORIGIN,*ORIGINS)'], cwd=ROOT, env=env,
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == ['https://killstass.su', 'https://killstass.su', 'https://192.168.1.250']


def test_image_header_sizes():
    from api.accounts import image_size
    assert image_size('image/png', png(40, 20)) == (40, 20)
    assert image_size('image/jpeg', png()) is None
    jpeg = b'\xff\xd8\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00' + b'\x00' * 9 + b'\xff\xc0' + struct.pack('>HBHH', 17, 8, 48, 64) + b'\x00' * 20
    assert image_size('image/jpeg', jpeg) == (64, 48)
    vp8x = b'RIFF' + b'\x00' * 4 + b'WEBPVP8X' + b'\x0a\x00\x00\x00' + b'\x00' * 4 + (99).to_bytes(3, 'little') + (49).to_bytes(3, 'little') + b'\x00' * 40
    assert image_size('image/webp', vp8x) == (100, 50)
    assert image_size('image/webp', b'RIFF0000WEBPXXXX' + b'\x00' * 40) is None


def test_ics_folding_and_escaping():
    from api.nights import fold, ics_text
    line = 'DESCRIPTION:' + ics_text('Игровой вечер; столы, пары\n' * 6)
    folded = fold(line)
    assert all(len(x.encode()) <= 75 for x in folded.split('\r\n'))
    assert folded.replace('\r\n ', '') == line and '\\;' in line and '\\,' in line and '\\n' in line


def test_achievement_rules():
    from api.seasons import evaluate
    d = lambda n: date(2025, 3, n)
    results = [{'match_id': f'm{i}', 'day': d(i), 'result': r, 'vp_for': f, 'vp_against': a, 'opponent_id': o, 'team_id': t}
               for i, (r, f, a, o, t) in enumerate([('win', 10, 4, 1, 5), ('loss', 2, 9, 2, 5), ('win', 8, 7, 2, 6),
                                                     ('win', 12, 3, 3, 6), ('win', 9, 8, 1, 7)], 1)]
    f = {'results': results, 'deficits': {'m3': 4}, 'nights': [{'day': d(2)}, {'day': d(20)}], 'tournaments': []}
    assert evaluate('matches', 5, f) == (5, True, 'm5')
    assert evaluate('wins', 1, f) == (4, True, 'm1')
    assert evaluate('win_streak', 3, f) == (3, True, 'm5')
    assert evaluate('comeback', 3, f) == (4, True, 'm3')
    assert evaluate('comeback', 5, f)[1] is False
    assert evaluate('big_win', 9, f) == (9, True, 'm4')
    assert evaluate('opponents', 3, f)[:2] == (3, True)
    assert evaluate('teams', 4, f)[:2] == (3, False)
    assert evaluate('nights', 2, f)[:2] == (2, True)
    season = {'starts_on': d(3), 'ends_on': d(4)}
    assert evaluate('matches', 2, f, season) == (2, True, 'm4')
    assert evaluate('nights', 1, f, season)[:2] == (0, False)


def test_season_elo_matches_ratings():
    from api.seasons import rate
    r, rec = rate([{'a': 1, 'b': 2, 'va': 5, 'vb': 3}, {'a': 2, 'b': 1, 'va': 4, 'vb': 4}], 1500, 24)
    assert round(r[1]) == 1511 and round(r[2]) == 1489 and rec[1] == {'games': 2, 'wins': 1, 'draws': 1, 'losses': 0}


def test_web_push_encryption_rfc8291_vector():
    from cryptography.hazmat.primitives.asymmetric import ec
    from api.push import encrypt, unb64u, b64u
    server = ec.derive_private_key(int.from_bytes(unb64u('yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw'), 'big'), ec.SECP256R1())
    body = encrypt(b'When I grow up, I want to be a watermelon',
                   'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4',
                   'BTBZMqHH6r4Tts7J_aSIgg', salt=unb64u('DGv6ra1nlYgDCS1FRnbzlw'), server_key=server)
    assert b64u(body) == ('DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_'
                          'yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN')


def test_vapid_token_is_a_valid_es256_jwt():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    from api.push import vapid_authorization, unb64u, b64u, raw_public, host_allowed
    key = ec.generate_private_key(ec.SECP256R1())
    header = vapid_authorization('https://fcm.googleapis.com/fcm/send/abc', key, b64u(raw_public(key)), 'https://killstass.su', now=1000)
    token, k = re.fullmatch(r'vapid t=([^,]+), k=(.+)', header).groups()
    h, c, s = token.split('.')
    claims = json.loads(unb64u(c))
    assert json.loads(unb64u(h)) == {'typ': 'JWT', 'alg': 'ES256'}
    assert claims == {'aud': 'https://fcm.googleapis.com', 'exp': 1000 + 12 * 3600, 'sub': 'https://killstass.su'}
    sig = unb64u(s)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64u(k))
    pub.verify(encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')), f'{h}.{c}'.encode(), ec.ECDSA(hashes.SHA256()))
    assert host_allowed('https://fcm.googleapis.com/x') and host_allowed('https://updates.push.services.mozilla.com/wpush/v2/x')
    assert host_allowed('https://web.push.apple.com/x') and not host_allowed('https://192.168.1.1/x')
    assert not host_allowed('https://evil.com/fcm.googleapis.com') and not host_allowed('https://googleapis.com.evil.com/')


# ------------------------------------------------------------------ password reset
def test_password_reset_by_admin_and_operator(clients):
    from tests.test_integration import register, op, post, PASS
    from fastapi.testclient import TestClient
    from api.main import app, ORIGIN
    a, b = clients
    ua = register(a, 'chief'); ub = register(b, 'rookie')
    assert a.post(f"/api/admin/users/{ub['public_id']}/password-reset", json=op()).status_code == 403
    make_admin(ua)
    r = a.post(f"/api/admin/users/{ub['public_id']}/password-reset", json=op())
    assert r.status_code == 201, r.text
    code = r.json()['code']
    assert re.fullmatch(r'[A-Z2-9]{4}-[A-Z2-9]{4}', code) and r.json()['login'] == 'rookie'
    with db() as c:  # only a hash is stored, never the code; nothing in the idempotency log either
        assert not c.execute("SELECT 1 FROM password_resets WHERE code_hash LIKE %s", ('%' + code[:4] + '%',)).fetchone()
        assert not c.execute("SELECT 1 FROM operations WHERE result::text LIKE %s", ('%' + code + '%',)).fetchone()
    anon = TestClient(app, base_url=ORIGIN, headers={'Origin': ORIGIN})
    new = 'brand-new-password-42'
    bad = {'identity': 'rookie', 'code': 'AAAA-AAAA', 'new_password': new}
    assert anon.post('/api/auth/password-reset', json=bad).json()['detail'] == 'reset_code_invalid'
    assert anon.post('/api/auth/password-reset', json={**bad, 'identity': 'nobody'}).json()['detail'] == 'reset_code_invalid'
    r = anon.post('/api/auth/password-reset', json={'identity': 'rookie', 'code': code.lower().replace('-', ' '), 'new_password': new})
    assert r.status_code == 200, r.text
    assert b.get('/api/auth/me').status_code == 401  # every old session ended
    anon.headers['X-CSRF-Token'] = r.json()['csrf']
    assert anon.get('/api/auth/me').json()['login'] == 'rookie'
    assert anon.post('/api/auth/password-reset', json={'identity': 'rookie', 'code': code, 'new_password': new}).status_code == 400
    assert b.post('/api/auth/login', json={'identity': 'rookie', 'password': PASS}).status_code == 401
    assert b.post('/api/auth/login', json={'identity': 'rookie', 'password': new}).status_code == 200
    # five wrong attempts burn the code
    code = post(a, f"/admin/users/{ub['public_id']}/password-reset", op())['code']
    for _ in range(5):
        assert anon.post('/api/auth/password-reset', json=bad).status_code == 400
    assert anon.post('/api/auth/password-reset', json={**bad, 'code': code}).status_code == 400
    # another administrator: operator only (scripts/admin.sh password LOGIN)
    with db() as c:
        c.execute('DELETE FROM rate_limits')
        c.execute("UPDATE users SET is_admin=true WHERE login='rookie'")
    assert a.post(f"/api/admin/users/{ub['public_id']}/password-reset", json=op()).json()['detail'] == 'reset_admin_forbidden'
    out = subprocess.run([sys.executable, '-m', 'api.accounts', 'reset', 'Rookie'], cwd=ROOT, env=os.environ, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    code = re.search(r'[A-Z2-9]{4}-[A-Z2-9]{4}', out.stdout).group(0)
    assert anon.post('/api/auth/password-reset', json={'identity': 'rookie', 'code': code, 'new_password': 'third-password-123'}).status_code == 200
    assert subprocess.run([sys.executable, '-m', 'api.accounts', 'reset', 'ghost'], cwd=ROOT, env=os.environ, capture_output=True).returncode == 1


# ------------------------------------------------------------------ profile, avatar, player page
def test_profile_avatar_and_player_page(clients):
    from tests.test_integration import register, op, post
    a, b = clients
    ua = register(a, 'painter'); ub = register(b, 'viewer')
    team = next(r['id'] for r in a.get('/api/catalogs').json() if r['kind'] == 'team')
    r = a.patch('/api/profile/extra', json={'motto': '  За Императора  ', 'favorite_team_id': team})
    assert r.status_code == 200 and r.json() == {'motto': 'За Императора', 'favorite_team_id': team, 'hidden': False, 'avatar': None}
    assert a.patch('/api/profile/extra', json={'favorite_team_id': 999999}).status_code == 422
    data = png()
    r = a.post('/api/profile/avatar', json={'mime': 'image/png', 'data': base64.b64encode(data).decode()})
    assert r.status_code == 200, r.text
    assert a.post('/api/profile/avatar', json={'mime': 'image/jpeg', 'data': base64.b64encode(data).decode()}).json()['detail'] == 'avatar_invalid'
    assert a.post('/api/profile/avatar', json={'mime': 'image/png', 'data': base64.b64encode(png(600, 20)).decode()}).status_code == 422
    big = 'A' * 330000
    assert a.post('/api/profile/avatar', content=json.dumps({'mime': 'image/png', 'data': big}),
                  headers={'Content-Type': 'application/json'}).status_code == 413
    av = b.get(f"/api/users/{ua['public_id']}/avatar")
    assert av.status_code == 200 and av.content == data and av.headers['content-type'] == 'image/png'
    assert av.headers['cache-control'] == 'private, max-age=86400'
    assert b.get(f"/api/users/{ua['public_id']}/avatar", headers={'If-None-Match': av.headers['etag']}).status_code == 304
    page = b.get(f"/api/players/{ua['public_id']}").json()
    assert page['display_name'] == 'painter' and page['motto'] == 'За Императора' and page['avatar'] and not page['me']
    assert page['summary']['games'] == 0 and page['head_to_head']['games'] == 0
    assert [x['code'] for x in page['achievements']][:3] == ['first_win', 'matches_10', 'comeback']
    assert page['achievements'][1]['progress'] == 0 and page['friendship'] is None
    # hidden: only the player, friends and administrators
    a.patch('/api/profile/extra', json={'hidden': True})
    assert b.get(f"/api/players/{ua['public_id']}").status_code == 404
    assert b.get(f"/api/users/{ua['public_id']}/avatar").status_code == 404
    make_admin(ub)
    assert b.get(f"/api/players/{ua['public_id']}").json()['friendship'] is None
    assert b.get(f"/api/users/{ua['public_id']}/avatar").status_code == 200
    with db() as c:
        c.execute('UPDATE users SET is_admin=false WHERE id=%s', (ub['id'],))
    assert b.get(f"/api/players/{ua['public_id']}").status_code == 404
    assert a.get(f"/api/players/{ua['public_id']}").json()['me'] is True
    post(a, '/friends', {'public_id': ub['public_id']})
    post(b, '/friends/' + ua['public_id'], {'action': 'accept'})
    assert b.get(f"/api/players/{ua['public_id']}").json()['friendship']['status'] == 'accepted'
    assert delete(a, '/api/profile/avatar').json() == {'avatar': None}
    assert b.get(f"/api/users/{ua['public_id']}/avatar").status_code == 404


# ------------------------------------------------------------------ seasons and achievements
def comeback_match(a, b):
    from tests.test_integration import op, post, ready_match
    from tests.test_quickstart import ver
    ua, ub, mid, cats = ready_match(a, b)
    src = cats['source'][0]
    post(b, f'/matches/{mid}/scores', op(version=ver(b, mid), turning_point=1, source_id=src, delta=3))
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=2, source_id=src, delta=5))
    post(a, f'/matches/{mid}/actions', op(version=ver(a, mid), action='finish'))
    post(b, f'/matches/{mid}/actions', op(version=ver(b, mid), action='confirm'))
    return ua, ub, mid


def test_achievements_seasons_and_admin(clients):
    from tests.test_integration import op, post
    a, b = clients
    with db() as c:  # a season-limited achievement created before the match
        c.execute("INSERT INTO seasons(name,starts_on,ends_on) VALUES('Old',current_date-400,current_date-300)")
    ua, ub, mid = comeback_match(a, b)
    kinds = [(n['kind'], n['resource_id']) for n in a.get('/api/notifications').json()]
    assert ('achievement', 'first_win') in kinds and ('achievement', 'comeback') in kinds
    assert not [n for n in b.get('/api/notifications').json() if n['kind'] == 'achievement']
    mine = {x['code']: x for x in a.get('/api/achievements').json()['items']}
    assert mine['first_win']['earned_at'] and mine['comeback']['match_id'] == mid and mine['matches_10']['progress'] == 1
    assert a.get('/api/admin/seasons').status_code == 403
    make_admin(ua)
    today = date.today()
    r = a.post('/api/admin/seasons', json={'name': 'Весна', 'starts_on': str(today - timedelta(days=30)), 'ends_on': str(today + timedelta(days=60))})
    assert r.status_code == 201, r.text
    sid = r.json()['id']
    assert r.json()['status'] == 'current'
    clash = a.post('/api/admin/seasons', json={'name': 'X', 'starts_on': str(today), 'ends_on': str(today + timedelta(days=1))})
    assert clash.json()['detail'] == 'season_overlap'
    assert a.post('/api/admin/seasons', json={'name': 'X', 'starts_on': str(today), 'ends_on': str(today - timedelta(days=1))}).status_code == 422
    assert b.get('/api/seasons').json()['current_id'] == sid
    t = b.get(f'/api/seasons/{sid}/ratings').json()
    assert [(p['display_name'], p['rating'], p['rank']) for p in t['players']] == [('alpha', 1512, 1), ('bravo', 1488, 2)]
    assert t['players'][1]['me'] and 'user_id' not in t['players'][0]
    b.patch('/api/profile/extra', json={'hidden': True})  # hidden players are rated but not listed for others
    assert [p['display_name'] for p in a.get(f'/api/seasons/{sid}/ratings').json()['players']] == ['alpha']
    assert len(b.get(f'/api/seasons/{sid}/ratings').json()['players']) == 2
    page = a.get(f"/api/players/{ua['public_id']}").json()
    assert page['season']['rating'] == 1512 and page['season']['rank'] == 1 and page['summary']['wins'] == 1
    # custom achievement, recompute, built-in protection
    new = {'code': 'veteran_one', 'title_ru': 'Ветеран', 'title_en': 'Veteran', 'icon': 'shield', 'rule': 'matches', 'threshold': 1, 'season_id': sid}
    r = a.post('/api/admin/achievements', json=new)
    assert r.status_code == 201, r.text
    aid = r.json()['id']
    assert a.post('/api/admin/achievements', json=new).json()['detail'] == 'achievement_code_taken'
    assert a.post('/api/admin/achievements', json={**new, 'code': 'x_1', 'icon': 'nope'}).json()['detail'] == 'achievement_icon_invalid'
    assert a.post('/api/admin/achievements/recompute', json={}).json()['awarded'] == 2
    holders = {x['code']: x['holders'] for x in a.get('/api/admin/achievements').json()['items']}
    assert holders == {'first_win': 1, 'matches_10': 0, 'comeback': 1, 'veteran_one': 2}
    builtin = next(x for x in a.get('/api/admin/achievements').json()['items'] if x['code'] == 'matches_10')
    assert delete(a, f"/api/admin/achievements/{builtin['id']}").json()['detail'] == 'achievement_builtin'
    body = {k: builtin[k] for k in ('code', 'title_ru', 'title_en', 'description_ru', 'description_en', 'icon', 'rule', 'season_id', 'position')}
    assert a.put(f"/api/admin/achievements/{builtin['id']}", json={**body, 'threshold': 1, 'active': True}).status_code == 200
    assert a.put(f"/api/admin/achievements/{builtin['id']}", json={**body, 'rule': 'wins', 'threshold': 1}).json()['detail'] == 'achievement_builtin'
    assert delete(a, f'/api/admin/seasons/{sid}').json()['detail'] == 'season_in_use'
    assert delete(a, f'/api/admin/achievements/{aid}').json() == {'ok': True}
    assert delete(a, f'/api/admin/seasons/{sid}').json() == {'ok': True}
    assert b.get('/api/seasons').json()['current_id'] is None


def test_quick_record_awards_first_win(clients):
    from tests.test_integration import register, op, post
    a, _ = clients
    register(a, 'solo')
    cats = a.get('/api/catalogs').json()
    pick = lambda kind: next(r['id'] for r in cats if r['kind'] == kind and r['edition'] == '2024')
    post(a, '/quick-matches', op(team1_id=pick('team'), team2_id=pick('team'), mission_id=pick('mission'), killzone_id=pick('killzone'),
                                 vp_for=12, vp_against=8, played_at=datetime.now(timezone.utc).isoformat()))
    assert ('achievement', 'first_win') in [(n['kind'], n['resource_id']) for n in a.get('/api/notifications').json()]


# ------------------------------------------------------------------ game nights and calendar
def test_game_nights_rsvp_pairs_and_calendar(clients):
    from tests.test_integration import register, op, post
    from fastapi.testclient import TestClient
    from api.main import app, ORIGIN
    a, b = clients
    ua = register(a, 'host'); ub = register(b, 'guest')
    team = next(r['id'] for r in a.get('/api/catalogs').json() if r['kind'] == 'team' and r['active'])
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    night = dict(title='Пятничный Kill Team', starts_at=start.isoformat(), ends_at=(start + timedelta(hours=5)).isoformat(),
                 place='Клуб, зал 2', notes='Приносите террейн', capacity=2)
    assert a.post('/api/nights', json=op(**{**night, 'starts_at': start.replace(tzinfo=None).isoformat()})).status_code == 422
    nid = post(a, '/nights', op(**night))['id']
    assert ('night_created', nid) in [(n['kind'], n['resource_id']) for n in b.get('/api/notifications').json()]
    lst = b.get('/api/nights').json()
    assert lst[0]['id'] == nid and lst[0]['yes'] == 1 and lst[0]['my_answer'] is None
    post(b, f'/nights/{nid}/rsvp', op(answer='yes', team_id=team, comment='Возьму Ангелов'))
    c3, _ = third_client('late')
    assert c3.post(f'/api/nights/{nid}/rsvp', json=op(answer='yes')).json()['detail'] == 'night_full'
    post(c3, f'/nights/{nid}/rsvp', op(answer='maybe'))
    d = b.get(f'/api/nights/{nid}').json()
    assert d['counts'] == {'yes': 2, 'maybe': 1, 'no': 0} and d['my']['team_id'] == team and not d['can_edit']
    assert b.post(f'/api/nights/{nid}/pairs', json=op(version=d['version'], action='generate')).json()['detail'] == 'night_organizer_only'
    v = a.get(f'/api/nights/{nid}').json()['version']
    post(a, f'/nights/{nid}/pairs', op(version=v, action='generate'))
    assert b.get(f'/api/nights/{nid}').json()['pairs'] == []  # not published yet
    v = a.get(f'/api/nights/{nid}').json()['version']
    post(a, f'/nights/{nid}/pairs', op(version=v, action='publish'))
    assert ('night_pairs', nid) in [(n['kind'], n['resource_id']) for n in b.get('/api/notifications').json()]
    pair = b.get(f'/api/nights/{nid}').json()['pairs'][0]
    assert {pair['a_name'], pair['b_name']} == {'host', 'guest'} and pair['mine']
    assert c3.post(f"/api/nights/{nid}/pairs/{pair['id']}/match", json=op()).json()['detail'] == 'pairing_not_player'
    mid = post(b, f"/nights/{nid}/pairs/{pair['id']}/match", op())['id']
    assert post(a, f"/nights/{nid}/pairs/{pair['id']}/match", op())['id'] == mid
    m = a.get(f'/api/matches/{mid}').json()
    assert m['kind'] == 'friend' and next(p for p in m['players'] if p['user_id'] == ub['id'])['team_id'] == team
    v = a.get(f'/api/nights/{nid}').json()['version']
    bad = a.post(f'/api/nights/{nid}/pairs', json=op(version=v, action='set', pairs=[[ua['public_id'], ua['public_id']]]))
    assert bad.json()['detail'] == 'pairs_invalid'
    # calendar
    ics = b.get(f'/api/nights/{nid}/calendar.ics')
    assert ics.status_code == 200 and ics.headers['content-type'].startswith('text/calendar')
    text = ics.text
    assert text.startswith('BEGIN:VCALENDAR\r\n') and text.endswith('END:VCALENDAR\r\n') and f'UID:night-{nid}@killstass' in text
    assert 'SUMMARY:Пятничный Kill Team' in text and 'LOCATION:Клуб\\, зал 2' in text
    assert all(len(line.encode()) <= 75 for line in text.split('\r\n'))
    assert f'DTSTART:{start.strftime("%Y%m%dT%H%M%SZ")}' in text
    path = post(b, '/calendar/token', op())['path']
    anon = TestClient(app, base_url=ORIGIN)
    feed = anon.get(path)
    assert feed.status_code == 200 and 'Пятничный' in feed.text and 'X-WR-CALNAME:KILLSTASS' in feed.text
    post(b, f'/nights/{nid}/rsvp', op(answer='no'))
    assert 'Пятничный' not in anon.get(path).text  # declined nights leave the personal feed
    assert b.get('/api/calendar/token').json()['active'] is True
    delete(b, '/api/calendar/token')
    assert anon.get(path).status_code == 404
    # cancel → notification for those who answered yes/maybe
    v = a.get(f'/api/nights/{nid}').json()['version']
    post(a, f'/nights/{nid}', op(**night, version=v, status='cancelled')) if False else \
        a.put(f'/api/nights/{nid}', json=op(**night, version=v, status='cancelled'))
    assert ('night_cancelled', nid) in [(n['kind'], n['resource_id']) for n in c3.get('/api/notifications').json()]
    assert 'STATUS:CANCELLED' in a.get(f'/api/nights/{nid}/calendar.ics').text
    assert c3.post(f'/api/nights/{nid}/rsvp', json=op(answer='yes')).json()['detail'] == 'night_closed'
    c3.close()


# ------------------------------------------------------------------ TV screen
def test_tv_screen(clients):
    from tests.test_integration import op, post, ready_match
    from tests.test_quickstart import ver
    from fastapi.testclient import TestClient
    from api.main import app, ORIGIN
    a, b = clients
    ua, ub, mid, cats = ready_match(a, b)
    post(a, f'/matches/{mid}/scores', op(version=ver(a, mid), turning_point=1, source_id=cats['source'][0], delta=2))
    post(a, f'/matches/{mid}/clock', op(action='configure', mode='chess'))
    post(a, f'/matches/{mid}/clock', op(action='start', slot=1))
    assert a.post('/api/admin/tv', json={'label': 'Зал'}).status_code == 403
    make_admin(ua)
    s = post(a, '/admin/tv', {'label': 'Зал'})
    assert len(s['key']) >= 24 and [x['label'] for x in a.get('/api/admin/tv').json()] == ['Зал']
    b.patch('/api/profile/extra', json={'hidden': True})
    tv = TestClient(app, base_url=ORIGIN)  # no session
    d = tv.get(f"/api/tv/{s['key']}").json()
    live = d['matches'][0]
    assert d['label'] == 'Зал' and live['status'] == 'active' and live['clock']['running'] and live['clock']['mode'] == 'chess'
    assert [(p['slot'], p['name'], p['vp']) for p in live['players']] == [(1, 'alpha', 2), (2, None, 0)]
    assert live['mission']['label'] and 'server_now' in d and d['season'] is None and d['night'] is None
    assert tv.get('/api/tv/' + 'x' * 32).status_code == 404
    delete(a, f"/api/admin/tv/{s['id']}")
    assert tv.get(f"/api/tv/{s['key']}").status_code == 404


# ------------------------------------------------------------------ killzone boards
def test_killzone_boards(clients):
    from tests.test_integration import op, post, ready_match
    a, b = clients
    ua, ub, mid, _ = ready_match(a, b)
    bid = post(a, '/boards', op(match_id=mid, title='Разбор'))['id']
    assert post(b, '/boards', op(match_id=mid))['id'] == bid  # one board per match
    board = b.get(f'/api/boards/{bid}').json()
    assert board['width'] == 30 and board['height'] == 22 and board['match']['id'] == mid
    tokens = board['frames'][0]['state']['tokens']
    assert {t['side'] for t in tokens} == {1, 2} and all(t['kind'] == 'op' for t in tokens)
    state = {'tokens': tokens + [{'id': 'obj1', 'kind': 'objective', 'x': 15, 'y': 11, 'r': 0.79, 'label': '1'},
                                 {'id': 'ter1', 'kind': 'terrain', 'x': 5, 'y': 5, 'w': 6, 'h': 2, 'rot': 15, 'terrain': 'heavy'},
                                 {'id': 'arr1', 'kind': 'arrow', 'x': 1, 'y': 1, 'x2': 7, 'y2': 3, 'side': 1}]}
    r = a.put(f'/api/boards/{bid}/frames/1', json={'version': None, 'state': state, 'note': 'После ПП1'})
    assert r.status_code == 200 and r.json()['version'] == 1, r.text
    assert a.put(f'/api/boards/{bid}/frames/1', json={'version': None, 'state': state}).json()['detail'] == 'version_conflict'
    assert b.put(f'/api/boards/{bid}/frames/1', json={'version': 1, 'state': state, 'note': 'ok'}).json()['version'] == 2
    bad = {'tokens': [{'id': 'x', 'kind': 'tank', 'x': 1, 'y': 1}]}
    assert a.put(f'/api/boards/{bid}/frames/2', json={'version': None, 'state': bad}).status_code == 422
    assert a.put(f'/api/boards/{bid}/frames/13', json={'version': None, 'state': state}).status_code == 422
    huge = json.dumps({'version': None, 'state': {'tokens': []}, 'note': 'x' * 140000})
    assert a.put(f'/api/boards/{bid}/frames/2', content=huge, headers={'Content-Type': 'application/json'}).status_code == 413
    frames = a.get(f'/api/boards/{bid}').json()['frames']
    assert [f['frame'] for f in frames] == [0, 1] and frames[1]['note'] == 'ok' and a.get(f'/api/boards/{bid}').json()['seq'] == 3
    assert frames[1]['state']['tokens'][-2]['terrain'] == 'heavy'
    assert delete(a, f'/api/boards/{bid}/frames/0').json()['detail'] == 'frame_required'
    assert delete(a, f'/api/boards/{bid}/frames/1').json()['ok']
    c3, _ = third_client('stranger')
    assert c3.get(f'/api/boards/{bid}').status_code == 404
    free = post(c3, '/boards', op(title='Тренировка', width=22, height=30))['id']
    assert a.get(f'/api/boards/{free}').status_code == 404
    assert [x['title'] for x in c3.get('/api/boards').json()] == ['Тренировка']
    assert {x['id'] for x in b.get('/api/boards').json()} == {bid}
    c3.close()


# ------------------------------------------------------------------ Web Push queue and worker
def test_push_subscriptions_outbox_and_delivery(clients, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec
    import api.main as core
    import api.push as push
    from tests.test_integration import register, op, post
    a, b = clients
    ua = register(a, 'pusher'); ub = register(b, 'pushed')
    assert a.get('/api/push/config').json() == {'enabled': False, 'public_key': None, 'subscriptions': 0}
    key = ec.generate_private_key(ec.SECP256R1())
    sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/abc', 'keys': {'p256dh': push.b64u(push.raw_public(key)), 'auth': push.b64u(os.urandom(16))}}
    assert b.post('/api/push/subscriptions', json=sub).json()['detail'] == 'push_disabled'
    monkeypatch.setattr(core, 'PUSH_ENABLED', True)
    cfg = b.get('/api/push/config').json()
    assert cfg['enabled'] and len(push.unb64u(cfg['public_key'])) == 65
    assert b.post('/api/push/subscriptions', json={**sub, 'endpoint': 'https://10.0.0.1/x'}).json()['detail'] == 'push_endpoint_forbidden'
    assert b.post('/api/push/subscriptions', json={**sub, 'keys': {'p256dh': 'A' * 60, 'auth': 'B' * 22}}).json()['detail'] == 'push_keys_invalid'
    assert b.post('/api/push/subscriptions', json=sub).status_code == 201
    assert a.post('/api/push/test', json={}).json()['detail'] == 'push_not_subscribed'
    post(a, '/friends', {'public_id': ub['public_id']})  # notify() → outbox (b has a subscription)
    post(b, '/push/test', {})
    sent = []

    def fake_send(s, data, k, pub, subject):
        sent.append((s['endpoint'], data))
        return 201
    monkeypatch.setattr(push, 'send', fake_send)
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as c:
        assert push.deliver(c, 'https://killstass.su') == 2 and push.deliver(c, 'https://killstass.su') == 0
        assert [d['title'] for _, d in sent] == ['Новый запрос в друзья', 'Проверка уведомлений KILLSTASS']
        assert sent[0][1]['url'] == '/#friends' and c.execute('SELECT last_ok_at FROM push_subscriptions').fetchone()['last_ok_at']
        cli = lambda login: subprocess.run([sys.executable, '-m', 'api.push', 'test', login], cwd=ROOT, env=os.environ,
                                           capture_output=True, text=True)
        r = cli('PUSHED')  # scripts/push.sh test LOGIN
        assert r.returncode == 0 and 'Queued a test notification for pushed' in r.stdout
        assert cli('ghost').returncode == 1 and cli('pusher').returncode == 1  # unknown login / no devices
        monkeypatch.setattr(push, 'send', lambda *x: 410)
        c.execute("INSERT INTO push_outbox(user_id,kind,resource_id) VALUES(%s,'push_test','')", (ub['id'],))
        c.commit()
        assert push.deliver(c, 'x') == 2
        assert c.execute('SELECT count(*) AS n FROM push_subscriptions').fetchone()['n'] == 0
        assert 'no subscribed devices' in cli('pushed').stderr
    body = push.encrypt(b'{"title":"x"}', sub['keys']['p256dh'], sub['keys']['auth'])
    assert len(body) == 16 + 4 + 1 + 65 + len(b'{"title":"x"}') + 1 + 16


# ------------------------------------------------------------------ live events, offline clock, service worker
def test_user_event_stream(clients, monkeypatch):
    import api.live as live
    from tests.test_integration import ready_match
    a, b = clients
    ua, ub, mid, _ = ready_match(a, b)
    monkeypatch.setattr(live, 'ITERATIONS', 1)
    monkeypatch.setattr(live, 'PAUSE', 0)
    with a.stream('GET', f'/api/events?match={mid}') as r:
        assert r.headers['content-type'].startswith('text/event-stream')
        text = ''.join(r.iter_text())
    assert text.startswith('retry: 3000') and 'event: notify' in text and 'event: revision' in text and 'event: clock' in text
    with b.stream('GET', '/api/events') as r:
        text = ''.join(r.iter_text())
    assert 'event: notify' in text and 'revision' not in text
    from fastapi.testclient import TestClient
    from api.main import app, ORIGIN
    c3, _ = third_client('outsider')
    assert c3.get(f'/api/events?match={mid}').status_code == 404
    c3.close()


def test_offline_clock_taps_keep_their_time(clients):
    from tests.test_integration import op, post, ready_match
    a, b = clients
    ua, ub, mid, _ = ready_match(a, b)
    post(a, f'/matches/{mid}/clock', op(action='configure', mode='chess'))
    post(a, f'/matches/{mid}/clock', op(action='start', slot=1))
    with db() as c:
        c.execute("UPDATE match_clock_events SET server_ts=now()-interval '10 minutes' WHERE match_id=%s", (mid,))
    at = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    r = post(b, f'/matches/{mid}/clock', op(action='switch', slot=1, at=at))
    slots = {s['slot']: s['elapsed_seconds'] for s in r['clock']['slots']}
    assert 355 <= slots[1] <= 365 and 235 <= slots[2] <= 245 and r['clock']['active_slot'] == 2
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = post(a, f'/matches/{mid}/clock', op(action='switch', slot=2, at=future))
    slots = {s['slot']: s['elapsed_seconds'] for s in r['clock']['slots']}
    assert 235 <= slots[2] <= 250  # clamped to now
    old = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = post(a, f'/matches/{mid}/clock', op(action='pause', at=old))  # never before the previous event
    assert r['clock']['running'] is False and r['clock']['slots'][0]['elapsed_seconds'] >= 355


def test_service_worker_and_manifest(clients):
    a, _ = clients
    r = a.get('/sw.js')
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/javascript')
    assert r.headers['service-worker-allowed'] == '/' and r.headers['cache-control'] == 'no-cache'
    assets = json.loads(re.search(r'const ASSETS = (\[.*?\]);', r.text).group(1))
    assert f'/static/v/{VERSION}/main.js' in assets and f'/static/v/{VERSION}/i18n/ru.json' in assets
    assert not [x for x in assets if x.endswith('sw.js') or x.endswith('.txt')]
    assert VERSION in r.text and '{{VERSION}}' not in r.text
    for path in assets:
        assert a.get(path).status_code == 200, path
    m = a.get('/static/manifest.webmanifest').json()
    assert {i['sizes'] for i in m['icons']} >= {'192x192', '512x512'} and m['scope'] == '/'


# ------------------------------------------------------------------ deployment files (static and shell checks)
SH = __import__('shutil').which('sh')
SCRIPTS = sorted((ROOT / 'scripts').glob('*.sh'))


def shell(cmd, cwd, path_dirs=(), env=None, stdin=None):
    e = {**os.environ, **(env or {})}
    e['PATH'] = os.pathsep.join([*map(str, path_dirs), e['PATH']])
    return subprocess.run([SH, '-c', cmd], cwd=cwd, env=e, capture_output=True, text=True, input=stdin)


def fake_bin(tmp_path, name, body):
    d = tmp_path / 'bin'
    d.mkdir(exist_ok=True)
    (d / name).write_text('#!/bin/sh\n' + body)
    (d / name).chmod(0o755)
    return d


@pytest.mark.skipif(not SH, reason='POSIX sh required')
def test_shell_scripts_parse_and_are_executable():
    for p in SCRIPTS:
        assert subprocess.run([SH, '-n', str(p)], capture_output=True).returncode == 0, p.name
        shebang = p.read_text().startswith('#!')
        assert shebang == (p.name != 'lib.sh'), p.name  # lib.sh is sourced, never run
        assert os.access(p, os.X_OK) == shebang, p.name


def test_caddyfile_domain_certificates_and_networks():
    config = (ROOT / 'proxy/Caddyfile').read_text()
    assert '(tls-internal) {\n tls internal\n}' in config
    assert '(tls-files) {\n tls /certs/{$KS_DOMAIN}.crt /certs/{$KS_DOMAIN}.key\n}' in config
    assert '@outside not remote_ip {$KS_ALLOW_NETS:192.168.1.0/24}' in config
    assert 'https://{$KS_DOMAIN:killstass.invalid}:8443 {\n import tls-{$KS_TLS_MODE:internal}\n import app\n}' in config
    assert 'https://{$APP_HOST}:8443 {\n tls internal\n import app\n}' in config
    plain = config[config.index('http://:8080 {'):config.index('https://{$APP_HOST}:8443 {')]
    assert plain.index('route {') < plain.index('import lan') < plain.index('redir @domain') < plain.index('redir https://{$APP_HOST}')
    assert 'acme' not in config.replace('ACME server', '').lower()  # Caddy never requests certificates itself
    for matcher, size in (('@avatar', '320KB'), ('@boards', '128KB')):
        at = config.index(f'request_body {matcher} {{')
        assert f'max_size {size}' in config[at:config.index('}', at)]
        assert at < config.index('reverse_proxy api:8000')
    assert '@ordinary not path /api/rosters /api/rosters/* /api/profile/avatar /api/boards /api/boards/*' in config


def test_compose_optional_services_and_certificates():
    compose = (ROOT / 'docker-compose.yml').read_text()
    api = compose[compose.index('\n  api:'):compose.index('\n  proxy:')]
    assert 'networks: [backend]' in api and 'edge' not in api  # the api never gets internet access
    worker = compose[compose.index('\n  pushworker:'):compose.index('\n  tailscale:')]
    assert 'profiles: [push]' in worker and "['python','-m','api.push','worker']" in worker
    assert 'networks: [backend,edge]' in worker and 'ports' not in worker and 'read_only: true' in worker
    ts = compose[compose.index('\n  tailscale:'):compose.index('\nnetworks:')]
    assert 'profiles: [tailscale]' in ts and 'network_mode: host' in ts and '--snat-subnet-routes=false' in ts
    assert "TS_FORCE_NOISE_443: 'true'" in ts  # port 80 to the coordination server stalled behind the ISP (D-10)
    assert re.search(r'tailscale/tailscale:v\d+\.\d+\.\d+', ts) and 'latest' not in ts
    assert './local/acme/certificates:/certs:ro' in compose and './local/tailscale:/var/lib/tailscale' in ts
    for var, default in (('KS_DOMAIN', 'killstass.invalid'), ('KS_TLS_MODE', 'internal'), ('KS_ALLOW_NETS', '192.168.1.0/24')):
        assert f'{var}: ${{{var}:-{default}}}' in compose  # ":-": an empty value would break the Caddyfile
    env = (ROOT / '.env.example').read_text()
    assert 'RESET_TTL_MINUTES=60' in env and '#KS_DOMAIN=' in env and '#ACME_DNS_PROVIDER=' in env
    assert '#COMPOSE_PROFILES=push,tailscale' in env


@pytest.mark.skipif(not SH, reason='POSIX sh required')
def test_lib_sh_edits_env_atomically(tmp_path):
    (tmp_path / '.env').write_text('A=1\nCOMPOSE_PROFILES=push\n')
    lib = ROOT / 'scripts/lib.sh'
    r = shell(f'''. "{lib}"; envset B "two words"; envset A 2; profile_on tailscale; profile_on push; profile_off push
    nets_add 100.64.0.0/10; nets_add 100.64.0.0/10; echo "$(envget A)|$(envget B)|$(envget COMPOSE_PROFILES)|$(allowed_nets)"
    valid_cidr 10.0.0.0/33 || echo bad-cidr; valid_domain killstass.su && echo domain-ok; envset C 'x$y' ''', tmp_path)
    assert r.stdout.splitlines() == ['2|two words|tailscale|192.168.1.0/24 100.64.0.0/10', 'bad-cidr', 'domain-ok']
    assert r.returncode == 1 and 'not supported' in r.stderr
    assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600 and 'B="two words"' in (tmp_path / '.env').read_text()
    assert not list(tmp_path.glob('.env.*'))  # no temporary files left
    # root scripts keep the owner of .env: the operator may run docker compose without root
    assert 'chown --reference=.env' in lib.read_text() and 'cp -p .env "$ENV_COPY"' in (ROOT / 'scripts/update.sh').read_text()


@pytest.mark.skipif(not SH, reason='POSIX sh required')
def test_firewall_lets_in_the_configured_networks(tmp_path):
    proj = tmp_path / 'proj'
    (proj / 'scripts').mkdir(parents=True)
    for name in ('firewall.sh', 'lib.sh'):
        (proj / 'scripts' / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    (proj / '.env').write_text('BIND_IP=192.168.1.250\nKS_ALLOW_NETS="192.168.1.0/24 100.64.0.0/10"\n')
    log = tmp_path / 'log'
    fake_bin(tmp_path, 'id', 'echo 0\n')
    bindir = fake_bin(tmp_path, 'iptables', f'echo "$*" >> {log}\ncase "$*" in *"-C DOCKER-USER"*) exit 1;; esac\n')
    r = shell('sh scripts/firewall.sh', proj, [bindir])
    assert r.returncode == 0, r.stderr
    rules = log.read_text().splitlines()
    chain = [x for x in rules if x.startswith('-w -A KILLSTASS-LAN')]
    assert chain == ['-w -A KILLSTASS-LAN -s 192.168.1.0/24 -j RETURN', '-w -A KILLSTASS-LAN -s 100.64.0.0/10 -j RETURN',
                     '-w -A KILLSTASS-LAN -p tcp -m conntrack --ctdir ORIGINAL --ctorigdst 192.168.1.250 --ctorigdstport 80 -j DROP',
                     '-w -A KILLSTASS-LAN -p tcp -m conntrack --ctdir ORIGINAL --ctorigdst 192.168.1.250 --ctorigdstport 443 -j DROP',
                     '-w -A KILLSTASS-LAN -j RETURN']
    assert '-w -I DOCKER-USER 1 -j KILLSTASS-LAN' in rules
    (bindir / 'iptables').unlink()
    fake_bin(tmp_path, 'nft', f'echo "$*" >> {log}\n[ "$1" = -f ] && cat >> {log}\nexit 0\n')
    r = shell('sh scripts/firewall.sh', proj, [bindir])
    assert r.returncode == 0 and 'ip saddr != { 192.168.1.0/24, 100.64.0.0/10 } counter drop' in log.read_text()
    (proj / '.env').write_text('KS_ALLOW_NETS="192.168.1.0/24 0.0.0.0/x"\n')
    assert shell('sh scripts/firewall.sh', proj, [bindir]).returncode == 1


def test_operator_scripts_v110():
    read = lambda name: (ROOT / 'scripts' / name).read_text()
    assert 'docker compose exec -T api python -m api.accounts reset "$login"' in read('admin.sh')
    assert 'python -m api.push test' in read('push.sh') and 'profile_on push' in read('push.sh')
    cert = read('cert.sh')
    assert 'goacme/lego:v4.29.0' in cert and '--dns "$provider"' in cert and '--accept-tos' in cert
    assert '--cap-drop ALL' in cert and '--read-only' in cert and 'renew --dynamic' in cert and 'envset KS_TLS_MODE files' in cert
    ts = read('tailscale.sh')
    assert 'TSNET=100.64.0.0/10' in ts and 'nets_add "$TSNET"' in ts and 'nets_del "$TSNET"' in ts
    assert ts.count('./scripts/firewall.sh') == 2 and 'envdel TS_AUTHKEY' in ts
    assert 'APP_ORIGIN' in read('domain.sh')
    unit = (ROOT / 'systemd/killstass-cert.service').read_text()
    timer = (ROOT / 'systemd/killstass-cert.timer').read_text()
    assert 'ConditionPathExists=/opt/killstass/local/acme.env' in unit and 'cert.sh renew' in unit
    assert timer.count('OnCalendar=') == 2 and 'RandomizedDelaySec=' in timer and 'Persistent=true' in timer
    smoke = read('smoke.sh')
    assert "get('/sw.js')" in smoke and 'openssl s_client' in smoke and 'profile_has' in smoke
    assert r'content="%s"\s*/?>' in smoke  # the page writes <meta … />; 1.9.0 expected «">» and failed


def test_update_script_structure():
    u = (ROOT / 'scripts/update.sh').read_text()
    assert u.splitlines()[-1] == 'main "$@"; exit $?'  # the whole script is parsed before files are replaced
    assert u.index('\nrollback() {') < u.index('\ndeploy() {') < u.index('\narchive_update() {')
    body = u[u.index('\nrollback() {'):u.index('\ndeploy() {')]
    assert 'docker compose stop proxy api' not in body and 'smoke.sh' not in body
    for needle in ('sha256sum -c --quiet --strict SHA256SUMS', 'flock -n 8', 'cp --remove-destination', ':prev',
                   './scripts/backup.sh', '--rollback', 'sort -V', '.sha256', 'tail -n +6'):
        assert needle in u, needle
    assert '. ./scripts/lib.sh' not in u  # runs from an older installation that has no lib.sh


@pytest.mark.skipif(not SH or not __import__('shutil').which('flock'), reason='sh and flock required')
def test_update_from_archive_and_rollback(tmp_path):
    """update.sh ZIP / --rollback / automatic rollback against a fake docker (the logic, not Docker itself)."""
    import hashlib
    import zipfile
    app, backups = tmp_path / 'opt/killstass', tmp_path / 'backups'

    def tree(root, files):
        for name, text in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            if name.endswith('.sh'):
                p.chmod(0o755)
        sums = ''.join(f'{hashlib.sha256((root / n).read_bytes()).hexdigest()}  {n}\n' for n in sorted(files))
        (root / 'SHA256SUMS').write_text(sums)

    smoke = '#!/bin/sh\necho "smoke $1" >> "$LOG"\n[ "$1" = --post ] && [ -n "${FAIL:-}" ] && exit 1\nexit 0\n'
    common = {'docker-compose.yml': 'services: {}\n', 'scripts/backup.sh': (ROOT / 'scripts/backup.sh').read_text(),
              'scripts/update.sh': (ROOT / 'scripts/update.sh').read_text(), 'scripts/smoke.sh': smoke,
              'scripts/migrate.sh': '#!/bin/sh\necho migrate >> "$LOG"\n'}
    tree(app, {**common, 'VERSION': '1.9.0\n', 'old-only.txt': 'old\n'})
    (app / '.env').write_text('A=1\n')
    (app / 'local').mkdir()
    (app / 'local/keep').write_text('state\n')
    new = tmp_path / 'new/killstass'
    tree(new, {**common, 'VERSION': '1.10.0\n', 'new-only.txt': 'new\n', 'web/sw.js': '// sw\n'})
    zpath = tmp_path / 'killstass-v1.10.0.zip'
    with zipfile.ZipFile(zpath, 'w') as z:
        for p in sorted(new.rglob('*')):
            z.write(p, 'killstass/' + p.relative_to(new).as_posix())
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    log = tmp_path / 'log'
    bindir = fake_bin(tmp_path, 'docker', f'''echo "docker $*" >> {log}
case "$*" in *pg_dump*) echo PGDMP;; *"pg_restore --list"*) cat > /dev/null;; esac
exit 0
''')
    fake_bin(tmp_path, 'id', 'echo 0\n')
    env = {'BACKUP_DIR': str(backups), 'LOG': str(log)}
    run = lambda args, **kw: shell(f'sh {app}/scripts/update.sh {args}', tmp_path, [bindir], {**env, **kw})

    r = run(zpath.name)
    assert r.returncode == 1 and 'checksum needed' in r.stderr
    (tmp_path / (zpath.name + '.sha256')).write_text(f'{digest}  {zpath.name}\n')
    r = run(zpath.name)  # relative to the current directory
    assert r.returncode == 0, r.stderr
    assert (app / 'VERSION').read_text() == '1.10.0\n' and (app / 'new-only.txt').exists()
    assert not (app / 'old-only.txt').exists() and (app / 'local/keep').exists() and (app / '.env').read_text() == 'A=1\n'
    assert os.access(app / 'scripts/smoke.sh', os.X_OK) and not os.access(app / 'web/sw.js', os.X_OK)
    text = log.read_text()
    assert text.index('docker compose build') < text.index('smoke --pre') < text.index('docker compose stop proxy api')
    assert text.index('docker tag killstass-api:local killstass-api:prev') < text.index('docker compose build')
    assert text.rindex('docker compose up -d --wait') < text.index('smoke --post')
    state = (backups / 'last-update').read_text()
    assert 'PREV_VERSION=1.9.0' in state and 'NEW_VERSION=1.10.0' in state
    assert run(zpath.name).returncode == 1  # the same version needs --force

    r = run('--rollback')
    assert r.returncode == 0, r.stderr
    assert (app / 'VERSION').read_text() == '1.9.0\n' and (app / 'old-only.txt').exists() and not (app / 'new-only.txt').exists()
    assert not (app / 'web').exists()  # v1.12: directories emptied by the rollback are removed
    assert 'docker tag killstass-api:prev killstass-api:local' in log.read_text()
    assert run('--rollback').returncode == 1  # only once

    log.write_text('')
    r = run(str(zpath), FAIL='1')  # the new release fails its checks: the previous one comes back by itself
    assert r.returncode == 1 and 'rolled back to 1.9.0' in r.stderr
    assert (app / 'VERSION').read_text() == '1.9.0\n' and not (app / 'new-only.txt').exists()
    assert 'docker compose up -d --wait --remove-orphans' in log.read_text()

    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(zpath) as src, zipfile.ZipFile(bad, 'w') as dst:
        for info in src.infolist():
            data = src.read(info)
            dst.writestr(info, data + b'x' if info.filename.endswith('new-only.txt') else data)
    r = run(f'{bad} --sha256 {hashlib.sha256(bad.read_bytes()).hexdigest()}')
    assert r.returncode == 1 and 'SHA256SUMS check failed' in r.stderr
    assert run(f'{zpath} --sha256 {"0" * 64}').returncode == 1
