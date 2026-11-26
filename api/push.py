"""v1.10: Web Push (RFC 8030) with message encryption (RFC 8291, aes128gcm) and VAPID (RFC 8292).

The api container has no internet access: notify() only writes push_outbox rows (PUSH_ENABLED=1), and the
optional `pushworker` service (COMPOSE_PROFILES=push, networks backend + edge) sends them while the server
is online. Undelivered rows wait up to PUSH_MAX_AGE_SECONDS. Endpoints are limited to the known browser push
services (PUSH_ALLOWED_HOSTS), so a subscription cannot point the worker at an arbitrary address.
The VAPID key pair is generated on first use and stored in app_settings.

    python -m api.push worker     the delivery loop (pushworker service)
    python -m api.push status     subscriptions and queue (scripts/push.sh status)
    python -m api.push test LOGIN a test notification for one player (scripts/push.sh test LOGIN)"""
import base64
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import Depends
from pydantic import Field
from psycopg.types.json import Jsonb
from . import main as core

ALLOWED = tuple(h.strip().lower() for h in os.getenv(
    'PUSH_ALLOWED_HOSTS', 'fcm.googleapis.com,.googleapis.com,.push.services.mozilla.com,.push.apple.com,.notify.windows.com').split(',') if h.strip())
MAX_AGE = int(os.getenv('PUSH_MAX_AGE_SECONDS', '3600'))
log = logging.getLogger('killstass.push')


def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def unb64u(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def raw_public(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(payload, p256dh, auth, salt=None, server_key=None, rs=4096):
    """RFC 8291 message body: salt | record size | key id (server public key) | AES-128-GCM record."""
    ua_public, secret = unb64u(p256dh), unb64u(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = raw_public(server_key)
    ikm = hkdf(secret, server_key.exchange(ec.ECDH(), ua_key), b'WebPush: info\x00' + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = hkdf(salt, ikm, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = hkdf(salt, ikm, b'Content-Encoding: nonce\x00', 12)
    record = AESGCM(cek).encrypt(nonce, payload + b'\x02', None)
    return salt + rs.to_bytes(4, 'big') + bytes([len(as_public)]) + as_public + record


def vapid_authorization(endpoint, key, public_b64, subject, now=None):
    u = urllib.parse.urlsplit(endpoint)
    enc = lambda d: b64u(json.dumps(d, separators=(',', ':')).encode())
    signing = enc({'typ': 'JWT', 'alg': 'ES256'}) + '.' + enc({'aud': f'{u.scheme}://{u.netloc}', 'exp': int((now or time.time()) + 12 * 3600), 'sub': subject})
    r, s = decode_dss_signature(key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
    return f'vapid t={signing}.{b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}, k={public_b64}'


def vapid(c):
    """(private key, public key base64url) — created once per instance."""
    row = core.one(c, "SELECT value FROM app_settings WHERE key='push.vapid'")
    if not row:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        c.execute("INSERT INTO app_settings(key,value) VALUES('push.vapid',%s) ON CONFLICT DO NOTHING",
                  (Jsonb({'private': pem, 'public': b64u(raw_public(key))}),))
        row = core.one(c, "SELECT value FROM app_settings WHERE key='push.vapid'")
    v = row['value']
    return serialization.load_pem_private_key(v['private'].encode(), None), v['public']


def host_allowed(endpoint):
    host = (urllib.parse.urlsplit(endpoint).hostname or '').lower()
    return any(host == h or (h.startswith('.') and host.endswith(h)) for h in ALLOWED)


class Keys(core.Model):
    p256dh: str = Field(min_length=40, max_length=200, pattern=r'^[A-Za-z0-9_-]+=*$')
    auth: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+=*$')


class Subscription(core.Model):
    endpoint: str = Field(min_length=12, max_length=1000, pattern='^https://')
    keys: Keys
    lang: str = Field(default='ru', pattern='^(ru|en)$')
    expirationTime: float | None = None


class Unsubscribe(core.Model):
    endpoint: str = Field(min_length=12, max_length=1000)


@core.app.get('/api/push/config')
def config(u=Depends(core.user)):
    with core.pool.connection() as c:
        n = core.one(c, 'SELECT count(*)::int AS n FROM push_subscriptions WHERE user_id=%s', (u['id'],))['n']
        return {'enabled': core.PUSH_ENABLED, 'public_key': vapid(c)[1] if core.PUSH_ENABLED else None, 'subscriptions': n}


@core.app.post('/api/push/subscriptions', status_code=201)
def subscribe(p: Subscription, u=Depends(core.user)):
    if not core.PUSH_ENABLED:
        core.fail(409, 'push_disabled')
    if not host_allowed(p.endpoint):
        core.fail(422, 'push_endpoint_forbidden')
    try:
        ok = len(unb64u(p.keys.p256dh)) == 65 and unb64u(p.keys.p256dh)[0] == 4 and len(unb64u(p.keys.auth)) == 16
    except ValueError:
        ok = False
    if not ok:
        core.fail(422, 'push_keys_invalid')
    with core.pool.connection() as c:
        c.execute('''INSERT INTO push_subscriptions(user_id,endpoint,p256dh,auth,lang) VALUES(%s,%s,%s,%s,%s)
        ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id,p256dh=excluded.p256dh,auth=excluded.auth,
        lang=excluded.lang,failures=0''', (u['id'], p.endpoint, p.keys.p256dh, p.keys.auth, p.lang))
        c.execute('''DELETE FROM push_subscriptions WHERE user_id=%s AND id NOT IN
        (SELECT id FROM push_subscriptions WHERE user_id=%s ORDER BY id DESC LIMIT 10)''', (u['id'], u['id']))
    return {'ok': True}


@core.app.post('/api/push/unsubscribe')
def unsubscribe(p: Unsubscribe, u=Depends(core.user)):
    with core.pool.connection() as c:
        c.execute('DELETE FROM push_subscriptions WHERE user_id=%s AND endpoint=%s', (u['id'], p.endpoint))
    return {'ok': True}


@core.app.post('/api/push/test')
def test(u=Depends(core.user)):
    if not core.PUSH_ENABLED:
        core.fail(409, 'push_disabled')
    with core.pool.connection() as c:
        row = core.one(c, '''INSERT INTO push_outbox(user_id,kind,resource_id) SELECT %s,'push_test',''
        WHERE EXISTS(SELECT 1 FROM push_subscriptions WHERE user_id=%s) RETURNING id''', (u['id'], u['id']))
    if not row:
        core.fail(409, 'push_not_subscribed')
    return {'queued': True}


# ------------------------------------------------------------------ messages
TEXT = {
    'ru': {'challenge': 'Вас вызвали на матч', 'challenge_accepted': 'Вызов принят', 'challenge_declined': 'Вызов отклонён',
           'friend_request': 'Новый запрос в друзья', 'match_joined': 'Соперник присоединился к матчу',
           'match_active': 'Матч начался', 'match_awaiting_confirmation': 'Соперник отправил результат — подтвердите',
           'match_confirmed': 'Соперник подтвердил результат', 'match_disputed': 'Соперник оспорил результат',
           'match_cancelled': 'Матч отменён', 'match_setup': 'Матч снова открыт для правки',
           'tournament_added': 'Вас добавили в турнир', 'tournament_match': 'Матч турнира создан',
           'night_created': 'Новый игровой вечер', 'night_changed': 'Игровой вечер изменён', 'night_cancelled': 'Игровой вечер отменён',
           'night_pairs': 'Пары на игровой вечер опубликованы', 'night_match': 'Матч игрового вечера создан',
           'achievement': 'Новое достижение', 'push_test': 'Проверка уведомлений KILLSTASS'},
    'en': {'challenge': 'You have been challenged', 'challenge_accepted': 'Challenge accepted', 'challenge_declined': 'Challenge declined',
           'friend_request': 'New friend request', 'match_joined': 'Your opponent joined the match',
           'match_active': 'The match has started', 'match_awaiting_confirmation': 'Your opponent submitted the result — please confirm',
           'match_confirmed': 'Your opponent confirmed the result', 'match_disputed': 'Your opponent disputed the result',
           'match_cancelled': 'Match cancelled', 'match_setup': 'The match is open for editing again',
           'tournament_added': 'You were added to a tournament', 'tournament_match': 'Tournament match created',
           'night_created': 'New game night', 'night_changed': 'Game night changed', 'night_cancelled': 'Game night cancelled',
           'night_pairs': 'Game night pairs are published', 'night_match': 'Game night match created',
           'achievement': 'New achievement', 'push_test': 'KILLSTASS notification test'},
}


def message(c, row, lang):
    kind, rid = row['kind'], row['resource_id']
    title = TEXT[lang].get(kind, 'KILLSTASS')
    body, url = '', '/#overview'
    if kind.startswith('match_') or kind in ('tournament_match', 'night_match'):
        url = '/#match/' + rid
    elif kind in ('challenge', 'challenge_accepted', 'challenge_declined', 'friend_request'):
        url = '/#friends'
    elif kind == 'tournament_added':
        url = '/#tournaments/' + rid
    elif kind.startswith('night_'):
        n = core.one(c, 'SELECT title,starts_at FROM game_nights WHERE id::text=%s', (rid,))
        if n:
            body = n['title'] + ' · ' + n['starts_at'].astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m %H:%M')
        url = '/#nights/' + rid
    elif kind == 'achievement':
        a = core.one(c, 'SELECT title_ru,title_en FROM achievements WHERE code=%s', (rid,))
        body = (a['title_en'] or a['title_ru']) if a and lang == 'en' else a['title_ru'] if a else ''
        pid = core.one(c, 'SELECT public_id FROM users WHERE id=%s', (row['user_id'],))
        url = '/#player/' + (pid['public_id'] if pid else '')
    elif kind == 'push_test':
        url = '/#profile'
    return {'title': title, 'body': body, 'url': url, 'tag': f'{kind}:{rid}'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def send(sub, data, key, public_b64, subject):
    body = encrypt(json.dumps(data, ensure_ascii=False).encode(), sub['p256dh'], sub['auth'])
    req = urllib.request.Request(sub['endpoint'], data=body, method='POST', headers={
        'TTL': str(MAX_AGE), 'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream', 'Urgency': 'high',
        'Authorization': vapid_authorization(sub['endpoint'], key, public_b64, subject)})
    try:
        with OPENER.open(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def deliver(c, subject):
    """One batch. Returns the number of outbox rows handled; raises OSError when the internet is unreachable."""
    rows = core.allrows(c, 'SELECT * FROM push_outbox ORDER BY id LIMIT 20 FOR UPDATE SKIP LOCKED')
    if not rows:
        c.commit()
        return 0
    key, public_b64 = vapid(c)
    for row in rows:
        if row['created_at'] < datetime.now(timezone.utc) - timedelta(seconds=MAX_AGE):
            continue
        for sub in core.allrows(c, 'SELECT * FROM push_subscriptions WHERE user_id=%s', (row['user_id'],)):
            if not host_allowed(sub['endpoint']):
                continue
            status = send(sub, message(c, row, sub['lang']), key, public_b64, subject)
            if status in (404, 410):
                c.execute('DELETE FROM push_subscriptions WHERE id=%s', (sub['id'],))
            elif 200 <= status < 300:
                c.execute('UPDATE push_subscriptions SET last_ok_at=now(),failures=0 WHERE id=%s', (sub['id'],))
            else:
                log.warning('push %s: HTTP %s', urllib.parse.urlsplit(sub['endpoint']).hostname, status)
                c.execute('UPDATE push_subscriptions SET failures=least(failures+1,1000) WHERE id=%s', (sub['id'],))
                c.execute('DELETE FROM push_subscriptions WHERE id=%s AND failures>50', (sub['id'],))
    c.execute('DELETE FROM push_outbox WHERE id = ANY(%s)', ([r['id'] for r in rows],))
    c.commit()
    return len(rows)


def worker():
    import psycopg
    from psycopg.rows import dict_row
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    contact = os.getenv('PUSH_CONTACT', '').strip()
    subject = ('mailto:' + contact) if contact and '@' in contact and not contact.startswith('mailto:') else (contact or core.ORIGIN)
    log.info('pushworker started, subject %s', subject)
    while True:
        try:
            with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as c:
                vapid(c)
                c.commit()
                while True:
                    try:
                        n = deliver(c, subject)
                    except OSError as e:  # no route to the internet: keep the queue, retry later
                        c.rollback()
                        log.info('offline (%s); retry in 60 s', e)
                        c.execute('DELETE FROM push_outbox WHERE created_at < now() - make_interval(secs=>%s)', (MAX_AGE,))
                        c.commit()
                        time.sleep(60)
                        continue
                    if not n:
                        time.sleep(3)
        except Exception as e:  # database restart during an update
            log.warning('pushworker: %s', e)
            time.sleep(10)


def status():
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as c:
        s = c.execute('''SELECT (SELECT count(*) FROM push_subscriptions) AS subscriptions,
        (SELECT count(DISTINCT user_id) FROM push_subscriptions) AS players,
        (SELECT count(*) FROM push_outbox) AS queued,(SELECT max(last_ok_at) FROM push_subscriptions) AS last_ok''').fetchone()
    print(f"PUSH_ENABLED={'1' if core.PUSH_ENABLED else '0'} subscriptions={s['subscriptions']} players={s['players']} "
          f"queued={s['queued']} last_delivery={s['last_ok'] or '—'}")


def test_cli(login):
    """Queue a test notification for a player (scripts/push.sh test LOGIN)."""
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as c:
        u = c.execute('SELECT id,login FROM users WHERE login=%s', (login.lower(),)).fetchone()
        if not u:
            print(f'No user with login {login}', file=sys.stderr)
            return 1
        row = c.execute('''INSERT INTO push_outbox(user_id,kind,resource_id) SELECT %s,'push_test',''
        WHERE EXISTS(SELECT 1 FROM push_subscriptions WHERE user_id=%s) RETURNING id''', (u['id'], u['id'])).fetchone()
    if not row:
        print(f"{u['login']}: no subscribed devices — turn notifications on in the profile first", file=sys.stderr)
        return 1
    print(f"Queued a test notification for {u['login']}; the pushworker sends it within a few seconds"
          + ('' if core.PUSH_ENABLED else ' (PUSH_ENABLED is off: nothing will be sent)'))
    return 0


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'worker':
        worker()
    elif cmd == 'status':
        status()
    elif cmd == 'test' and len(sys.argv) == 3:
        sys.exit(test_cli(sys.argv[2]))
    else:
        print('usage: python -m api.push worker|status|test LOGIN', file=sys.stderr)
        sys.exit(2)
