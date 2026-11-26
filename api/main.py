import asyncio
import csv
import hashlib
import io
import json
import os
import pathlib
import secrets
import string
import threading
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from .domain import challenge_transition, match_transition, score_after, slot_allowed, invite_state

# v1.10: several origins (space or comma separated), e.g. "https://killstass.su https://192.168.1.250".
# The first one is canonical (calendar links, Web Push subject).
ORIGINS = tuple(o.rstrip('/') for o in re.split(r'[\s,]+', os.getenv('APP_ORIGIN', 'https://192.168.1.250')) if o)
ORIGIN = ORIGINS[0]
# v1.9: single version source. The repository VERSION file is copied into the image next to api/.
with open(os.path.join(os.path.dirname(__file__), '..', 'VERSION'), encoding='utf-8') as _f:
    APP_VERSION = _f.read().strip()
# Every migration this build needs; /api/health reports 503 until all are applied.
MIGRATIONS = ('001_initial.sql', '002_seed.sql', '003_catalog_and_ops.sql', '004_verified_catalog.sql',
              '005_invites_hotseat.sql', '006_initiative.sql', '007_match_clock.sql', '008_share_feedback.sql',
              '009_team_data.sql', '010_rosters.sql', '011_tracker_tournaments.sql', '012_v110.sql',
              '013_v111.sql', '014_v112.sql', '015_v113.sql', '016_v114.sql', '017_v115.sql')
COOKIE = '__Host-killstass'
ph = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=1)
argon_slots = threading.BoundedSemaphore(2)

def hash_password(value):
    with argon_slots: return ph.hash(value)
pool = ConnectionPool(os.environ['DATABASE_URL'], min_size=1, max_size=5,
                      kwargs={'row_factory': dict_row}, open=False, timeout=10)
DUMMY_HASH = ph.hash('not-a-real-password-' + secrets.token_hex(16))

@asynccontextmanager
async def lifespan(app):
    pool.open(); await asyncio.to_thread(pool.wait)
    yield
    pool.close()

app = FastAPI(title='killstass API', version=APP_VERSION, lifespan=lifespan,
              docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)

CACHEABLE = re.compile(r'^/api/(reference/library|reference/core-rules|reference/terms|users/[A-Za-z0-9]{8}/avatar|tv/[A-Za-z0-9_-]{24,64}/avatar/[A-Za-z0-9]{8})$')  # v1.11: library; v1.12: core rules; v1.13: terms

@app.middleware('http')
async def security(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('origin') not in ORIGINS:
            return JSONResponse({'detail': 'origin_forbidden'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'json_required'}, status_code=415)
        path = request.url.path
        # v1.8: roster documents; v1.9: BattleScribe/New Recruit files (base64) for the roster import;
        # v1.10: avatar images (base64, at most 192 KB decoded) and killzone board frames.
        cap = (1048576 if path == '/api/rosters/import' else 262144 if path.startswith('/api/rosters')
               else 327680 if path == '/api/profile/avatar' else 131072 if path.startswith('/api/boards')
               else 16384 if path == '/api/client-errors' else 32768)
        try:
            if int(request.headers.get('content-length', '0')) > cap:
                return JSONResponse({'detail': 'body_too_large'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': 'invalid_content_length'}, status_code=400)
        body = await request.body()
        if len(body) > cap: return JSONResponse({'detail': 'body_too_large'}, status_code=413)
    result = await call_next(request)
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'same-origin'
    result.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    # Only successful static responses are cacheable. Errors (including wrong versions) are not.
    if request.url.path.startswith('/static/'):
        if result.status_code in (200, 206, 304):
            versioned = request.url.path.startswith(f'/static/v/{APP_VERSION}/')
            result.headers['Cache-Control'] = ('public, max-age=31536000, immutable' if versioned
                                               else 'public, max-age=3600')
        else:
            result.headers['Cache-Control'] = 'no-store'
    # Cacheable API responses set their own Cache-Control (game sequence, v1.10 avatars).
    if request.url.path.startswith('/api') and not ('Cache-Control' in result.headers and result.status_code in (200,304)
            and (request.url.path == '/api/reference/game-sequence' or CACHEABLE.match(request.url.path))):
        result.headers['Cache-Control'] = 'no-store'
    return result

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Register(Model):
    login: str = Field(min_length=3, max_length=64, pattern=r'^[a-zA-Z0-9_.-]+$')
    email: str | None = Field(default=None, max_length=254)
    # Optional since v1.2: an empty name falls back to the login (one-step sign-up from an invite).
    display_name: str = Field(default='', max_length=64)
    password: str = Field(min_length=12, max_length=128)
    @field_validator('email')
    @classmethod
    def email_valid(cls, v):
        if v is not None and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',v):
            raise ValueError('invalid_email')
        return v.lower() if v else None

class Login(Model):
    identity: str = Field(min_length=1,max_length=254)
    password: str = Field(min_length=1,max_length=128)

class Password(Model):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12,max_length=128)

class Profile(Model):
    display_name: str = Field(min_length=1,max_length=64)

class DeleteAccount(Model):
    password: str = Field(max_length=128)

class FriendRequest(Model):
    public_id: str = Field(min_length=8,max_length=8)

class FriendAction(Model):
    action: str = Field(pattern='^(accept|decline|cancel|remove|block|unblock)$')

class Op(Model):
    request_id: UUID

class ChallengeCreate(Op):
    public_id: str = Field(min_length=8,max_length=8)
    edition: str = Field(default='2024',pattern='^(2021|2024)$')
    mission_id: int | None = None
    mode: str = Field(default='Обычный',max_length=80)

class ChallengeAction(Op):
    action: str = Field(pattern='^(accepted|declined|cancelled)$')

class Setup(Op):
    version: int = Field(ge=1)
    edition: str = Field(default='2024',pattern='^(2021|2024)$')
    mission_id: int
    killzone_id: int
    team1_id: int
    team2_id: int
    turns: int = Field(default=4,ge=1,le=12)
    initiative: int = Field(default=1,ge=1,le=2)
    roster: str = Field(default='',max_length=4000)
    roster_id: UUID | None = None
    operative_count: int | None = Field(default=None,ge=1,le=40)
    operative_manual: bool = False  # v1.13: type the count in although the team's composition gives one
    objective_ids: list[int] = Field(default_factory=list,max_length=12)
    rule_notes: str = Field(default='',max_length=2000)
    notes: str = Field(default='',max_length=4000)

    primary_op: str | None = Field(default=None,pattern='^(crit|tac|kill)$')
    tac_op_id: int | None = None
    aspect_counts: dict[str,int] = Field(default_factory=dict,max_length=3)

class MatchAction(Op):
    version: int = Field(ge=1)
    action: str = Field(pattern='^(start|finish|confirm|dispute|reopen|turn|cancel|concede)$')
    turning_point: int | None = Field(default=None,ge=1,le=12)
    slot: int | None = Field(default=None,ge=1,le=2)  # v1.13: who concedes in a hot-seat match (default: own slot)

class Score(Op):
    version: int = Field(ge=1)
    turning_point: int = Field(ge=1,le=12)
    source_id: int | None = None
    delta: int | None = Field(default=None,ge=-999,le=999)
    cp: int | None = Field(default=None,ge=0,le=99)
    notes: str | None = Field(default=None,max_length=2000)
    slot: int | None = Field(default=None,ge=1,le=2)

class MatchCreate(Op):
    kind: str = Field(pattern='^(friend|hotseat)$')
    edition: str = Field(default='2024',pattern='^(2021|2024)$')
    mission_id: int | None = None
    guest_name: str = Field(default='Гость',min_length=1,max_length=64)
    local: bool = False  # v1.13: the guest is a local player (api/localplayers.py)

class InviteCreate(Op):
    pass

class InviteJoin(Op):
    pass

class Quick(Op):
    guest_name: str = Field(default='Гость',min_length=1,max_length=64)
    local: bool = False  # v1.13: the opponent is a local player
    opponent_public_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9]{8}$')
    edition: str = Field(default='2024',pattern='^(2021|2024)$')
    team1_id: int
    team2_id: int
    mission_id: int
    killzone_id: int
    vp_for: int = Field(ge=0,le=999)
    vp_against: int = Field(ge=0,le=999)
    played_at: datetime
    notes: str = Field(default='',max_length=4000)
    @field_validator('played_at')
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None: raise ValueError('timezone_required')
        if v > datetime.now(timezone.utc)+timedelta(minutes=5): raise ValueError('future_date')
        return v.astimezone(timezone.utc)


def one(c, sql, args=()): return c.execute(sql,args).fetchone()
def allrows(c, sql, args=()): return c.execute(sql,args).fetchall()
def fail(code, text): raise HTTPException(code,text)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password_ok(value, hashed):
    try:
        with argon_slots: return ph.verify(hashed,value)
    except (VerificationError, InvalidHashError): return False

def user(request: Request):
    token = request.cookies.get(COOKIE,'')
    with pool.connection() as c:
        u = one(c,'''SELECT u.id,u.public_id,u.login,u.email,u.display_name,u.is_admin,s.csrf
        FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=%s AND expires_at>now()''',(digest(token),))
    if not u: fail(401,'unauthenticated')
    if request.method not in ('GET','HEAD') and not secrets.compare_digest(request.headers.get('x-csrf-token',''),u['csrf']):
        fail(403,'csrf_invalid')
    return u

def limit(request, category, max_hits):
    # Caddy overwrites this header; API has no published port. Never trust arbitrary X-Forwarded-For.
    ip=request.headers.get('x-real-ip') or request.client.host
    with pool.connection() as c:
        row=one(c,'''INSERT INTO rate_limits(bucket,hits,expires_at) VALUES(%s,1,now()+interval '15 minutes')
        ON CONFLICT(bucket) DO UPDATE SET hits=CASE WHEN rate_limits.expires_at<now() THEN 1 ELSE rate_limits.hits+1 END,
        expires_at=CASE WHEN rate_limits.expires_at<now() THEN now()+interval '15 minutes' ELSE rate_limits.expires_at END RETURNING hits''',
        (digest(category+ip),))
        c.execute('DELETE FROM rate_limits WHERE expires_at<now()-interval \'1 day\'')
    if row['hits']>max_hits: fail(429,'rate_limited')

def new_session(c, uid, response):
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    c.execute('DELETE FROM sessions WHERE expires_at<now()')
    c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(%s,%s,%s,now()+interval \'14 days\')',(digest(token),uid,csrf))
    response.set_cookie(COOKIE,token,max_age=14*86400,secure=True,httponly=True,samesite='strict',path='/')
    return csrf

PUSH_ENABLED = os.getenv('PUSH_ENABLED', '0') == '1'

def notify(c,uid,kind,rid):
    if not uid: return
    c.execute('INSERT INTO notifications(user_id,kind,resource_id) VALUES(%s,%s,%s)',(uid,kind,str(rid)))
    # v1.10: Web Push outbox, delivered by the optional pushworker service (internet access, COMPOSE_PROFILES=push).
    if PUSH_ENABLED:
        c.execute('''INSERT INTO push_outbox(user_id,kind,resource_id) SELECT %s,%s,%s
        WHERE EXISTS(SELECT 1 FROM push_subscriptions WHERE user_id=%s)''',(uid,kind,str(rid),uid))

def catalog(c,cid,kind,edition):
    item=one(c,'SELECT * FROM catalogs WHERE id=%s AND kind=%s AND edition=%s AND active',(cid,kind,edition))
    if not item: fail(422,'catalog_invalid')
    return item

def operation(c,u,p,resource,fn):
    key=str(p.request_id)
    c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(u['id'])+key,))
    h=digest(json.dumps(p.model_dump(mode='json'),sort_keys=True,ensure_ascii=False))
    old=one(c,'SELECT * FROM operations WHERE user_id=%s AND request_id=%s',(u['id'],key))
    if old:
        if old['resource']!=resource or old['payload_hash']!=h: fail(409,'idempotency_key_reused')
        return old['result']
    result=fn()
    c.execute('INSERT INTO operations(user_id,request_id,resource,payload_hash,result) VALUES(%s,%s,%s,%s,%s)',(u['id'],key,resource,h,Jsonb(result)))
    return result

def member(c,mid,uid,lock=False):
    m=one(c,'SELECT * FROM matches WHERE id=%s'+(' FOR UPDATE' if lock else ''),(str(mid),))
    if not m or not one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND user_id=%s',(str(mid),uid)):
        fail(404,'match_not_found')
    return m

def actor_player(c,m,u,slot=None):
    """Player row the actor may write: own slot, or the guest slot of the actor's own hot-seat match."""
    if slot is None:
        return one(c,'SELECT * FROM match_players WHERE match_id=%s AND user_id=%s',(str(m['id']),u['id']))
    row=one(c,'SELECT * FROM match_players WHERE match_id=%s AND slot=%s',(str(m['id']),slot))
    if not row or not slot_allowed(row['user_id'],u['id'],m['kind'],m['created_by']==u['id']): fail(403,'slot_forbidden')
    return row

INVITE_ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

def version(m,v):
    if m['version']!=v: fail(409,'version_conflict')

def audit(c,mid,u,action,before,after):
    c.execute('INSERT INTO match_audit(match_id,actor_id,action,before_data,after_data) VALUES(%s,%s,%s,%s,%s)',
              (str(mid),u['id'],action,Jsonb(before),Jsonb(after)))
    c.execute('UPDATE matches SET version=version+1,updated_at=now() WHERE id=%s',(str(mid),))

def snapshot(c,mid,uid):
    m=member(c,mid,uid)
    m['players']=allrows(c,'''SELECT p.*,coalesce((SELECT sum(vp) FROM turning_point_scores WHERE player_id=p.id),0)::int AS vp,
    u.public_id FROM match_players p LEFT JOIN users u ON u.id=p.user_id WHERE match_id=%s ORDER BY slot''',(str(mid),))
    m['scores']=allrows(c,'''SELECT s.* FROM turning_point_scores s JOIN match_players p ON p.id=s.player_id WHERE p.match_id=%s''',(str(mid),))
    m['turn_states']=allrows(c,'''SELECT s.* FROM turning_point_states s JOIN match_players p ON p.id=s.player_id WHERE p.match_id=%s''',(str(mid),))
    m['initiatives']=allrows(c,'SELECT turning_point,slot FROM turning_point_initiative WHERE match_id=%s ORDER BY turning_point',(str(mid),))
    m['invite']=one(c,'SELECT code,expires_at FROM match_invites WHERE match_id=%s AND used_at IS NULL AND expires_at>now()',(str(mid),)) if m['created_by']==uid and m['status']=='setup' else None
    m['clock']=clock.load(c,mid)
    m=reference.enrich_snapshot(c,m,uid)
    # v1.9: operative tracker (both players, read-only for the opponent) and «Undo last» for this viewer.
    m['operatives']=allrows(c,'''SELECT o.id,o.player_id,p.slot,o.position,o.name,o.card,o.stats,o.weapons,o.wounds_max,o.wounds,
    o.order_token,o.activated_tp,o.incapacitated_tp FROM match_operatives o JOIN match_players p ON p.id=o.player_id
    WHERE o.match_id=%s ORDER BY p.slot,o.position''',(str(mid),))
    m['tracker_seq']=tracker.seq(c,mid)
    m['undo']=tracker.undo_summary(c,m,uid)
    # v1.14: equipment (the opponent's is secret until the start), Ready-step CP grants and the ploy protocol.
    equipment.redact(m,uid)
    m['cp_grants']=allrows(c,'SELECT turning_point,gains FROM match_cp_grants WHERE match_id=%s ORDER BY turning_point',(str(mid),))
    m['ploys']=allrows(c,'''SELECT y.id,y.player_id,p.slot,y.turning_point,y.kind,y.name,y.cost,y.created_at FROM match_ploys y
    JOIN match_players p ON p.id=y.player_id WHERE y.match_id=%s ORDER BY y.id''',(str(mid),))
    return m

@app.get('/api/health')
def health():
    with pool.connection() as c:
        v=one(c,'SELECT count(*) AS n FROM schema_migrations WHERE version = ANY(%s)',(list(MIGRATIONS),))
        if v['n']!=len(MIGRATIONS): fail(503,'migration_required')
    return {'status':'ok','version':APP_VERSION,'migrations':len(MIGRATIONS)}

@app.post('/api/auth/register',status_code=201)
def register(p:Register, request:Request, response:Response):
    limit(request,'register',5)
    alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    try:
        with pool.connection() as c:
            uid=one(c,'''INSERT INTO users(public_id,login,email,display_name,password_hash)
            VALUES(%s,%s,%s,%s,%s) RETURNING id''',(''.join(secrets.choice(alphabet) for _ in range(8)),p.login.lower(),p.email,p.display_name.strip() or p.login,hash_password(p.password)))['id']
            csrf=new_session(c,uid,response)
    except errors.UniqueViolation: fail(409,'account_exists')
    return {'csrf':csrf}

@app.post('/api/auth/login')
def login(p:Login,request:Request,response:Response):
    limit(request,'login',15)
    with pool.connection() as c:
        u=one(c,'SELECT * FROM users WHERE login=%s OR email=%s',(p.identity.lower(),p.identity.lower()))
        valid=password_ok(p.password,u['password_hash'] if u else DUMMY_HASH)
        if not u or not valid: fail(401,'invalid_credentials')
        if ph.check_needs_rehash(u['password_hash']):
            c.execute('UPDATE users SET password_hash=%s WHERE id=%s',(hash_password(p.password),u['id']))
        csrf=new_session(c,u['id'],response)
    return {'csrf':csrf}

@app.get('/api/auth/me')
def me(u=Depends(user)):
    # v1.10: avatar version for the top bar (GET /api/users/<public_id>/avatar?h=<avatar>).
    with pool.connection() as c: a=one(c,'SELECT sha256 FROM avatars WHERE user_id=%s',(u['id'],))
    return {**u,'avatar':a['sha256'][:16] if a else None}

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,u=Depends(user)):
    with pool.connection() as c: c.execute('DELETE FROM sessions WHERE token_hash=%s',(digest(request.cookies.get(COOKIE,'')),))
    response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
    return {'ok':True}

@app.patch('/api/profile')
def profile(p:Profile,u=Depends(user)):
    with pool.connection() as c: c.execute('UPDATE users SET display_name=%s WHERE id=%s',(p.display_name.strip() or u['login'],u['id']))
    return {'ok':True}

@app.post('/api/profile/password')
def password(p:Password,response:Response,u=Depends(user)):
    with pool.connection() as c:
        old=one(c,'SELECT password_hash FROM users WHERE id=%s FOR UPDATE',(u['id'],))
        if not password_ok(p.current_password,old['password_hash']): fail(403,'password_invalid')
        c.execute('UPDATE users SET password_hash=%s WHERE id=%s',(hash_password(p.new_password),u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=%s',(u['id'],))
        csrf=new_session(c,u['id'],response)
    return {'csrf':csrf}

@app.delete('/api/profile')
def delete_account(p:DeleteAccount,response:Response,u=Depends(user)):
    with pool.connection() as c:
        old=one(c,'SELECT password_hash FROM users WHERE id=%s FOR UPDATE',(u['id'],))
        if not password_ok(p.password,old['password_hash']): fail(403,'password_invalid')
        # Shared results stay for opponents. Sole guest records are removed.
        c.execute("DELETE FROM matches WHERE kind IN ('guest','hotseat') AND created_by=%s",(u['id'],))
        c.execute("UPDATE match_players SET display_name='Удалённый игрок',roster='' WHERE user_id=%s",(u['id'],))
        c.execute("UPDATE turning_point_states SET notes='' WHERE player_id IN (SELECT id FROM match_players WHERE user_id=%s)",(u['id'],))
        c.execute("UPDATE matches SET notes='',setup='{}',version=version+1,updated_at=now() WHERE id IN (SELECT match_id FROM match_players WHERE user_id=%s)",(u['id'],))
        c.execute("UPDATE challenges SET status='cancelled',proposal='{}' WHERE (sender_id=%s OR recipient_id=%s) AND status='pending'",(u['id'],u['id']))
        c.execute('DELETE FROM users WHERE id=%s',(u['id'],))
    response.delete_cookie(COOKIE,path='/',secure=True)
    return {'ok':True}

@app.get('/api/catalogs')
def catalogs(include_inactive:bool=False,u=Depends(user)):
    with pool.connection() as c: return allrows(c,'SELECT * FROM catalogs WHERE (%s OR active) ORDER BY edition,kind,id',(include_inactive,))

@app.get('/api/friends')
def friends(u=Depends(user)):
    with pool.connection() as c:
        return {'relations':allrows(c,'''SELECT f.status,f.requester_id=%s AS outgoing,u.public_id,u.display_name
        FROM friendships f JOIN users u ON u.id=CASE WHEN f.requester_id=%s THEN f.recipient_id ELSE f.requester_id END
        WHERE f.requester_id=%s OR f.recipient_id=%s ORDER BY f.created_at DESC''',(u['id'],u['id'],u['id'],u['id'])),
        'blocks':allrows(c,'SELECT u.public_id,u.display_name FROM blocks b JOIN users u ON u.id=b.target_id WHERE b.user_id=%s',(u['id'],))}

@app.post('/api/friends',status_code=201)
def add_friend(p:FriendRequest,u=Depends(user)):
    with pool.connection() as c:
        t=one(c,'SELECT id FROM users WHERE public_id=%s',(p.public_id.upper(),))
        if not t or t['id']==u['id']: fail(404,'account_not_found')
        c.execute('SELECT pg_advisory_xact_lock(least(%s,%s)::int,greatest(%s,%s)::int)',(u['id'],t['id'],u['id'],t['id']))
        if one(c,'SELECT 1 FROM blocks WHERE (user_id=%s AND target_id=%s) OR (user_id=%s AND target_id=%s)',(u['id'],t['id'],t['id'],u['id'])): fail(403,'blocked')
        existing=one(c,'SELECT * FROM friendships WHERE least(requester_id,recipient_id)=least(%s,%s) AND greatest(requester_id,recipient_id)=greatest(%s,%s)',(u['id'],t['id'],u['id'],t['id']))
        if not existing:
            c.execute('INSERT INTO friendships(requester_id,recipient_id,status) VALUES(%s,%s,\'pending\')',(u['id'],t['id']))
            notify(c,t['id'],'friend_request',u['public_id'])
    return {'ok':True}

@app.post('/api/friends/{pid}')
def friend_action(pid:str,p:FriendAction,u=Depends(user)):
    with pool.connection() as c:
        t=one(c,'SELECT id FROM users WHERE public_id=%s',(pid.upper(),))
        if not t or t['id']==u['id']: fail(404,'account_not_found')
        args=(u['id'],t['id'],u['id'],t['id'])
        c.execute('SELECT pg_advisory_xact_lock(least(%s,%s)::int,greatest(%s,%s)::int)',args)
        where='least(requester_id,recipient_id)=least(%s,%s) AND greatest(requester_id,recipient_id)=greatest(%s,%s)'
        f=one(c,'SELECT * FROM friendships WHERE '+where,args)
        if p.action=='block':
            c.execute('INSERT INTO blocks VALUES(%s,%s) ON CONFLICT DO NOTHING',(u['id'],t['id']))
            c.execute('DELETE FROM friendships WHERE '+where,args)
            c.execute("UPDATE challenges SET status='cancelled' WHERE status='pending' AND ((sender_id=%s AND recipient_id=%s) OR (recipient_id=%s AND sender_id=%s))",args)
        elif p.action=='unblock': c.execute('DELETE FROM blocks WHERE user_id=%s AND target_id=%s',(u['id'],t['id']))
        elif p.action=='accept':
            if not f or f['recipient_id']!=u['id']: fail(403,'friend_action_forbidden')
            c.execute("UPDATE friendships SET status='accepted' WHERE "+where,args)
        else:
            if f and ((p.action=='cancel' and f['requester_id']!=u['id']) or (p.action=='decline' and f['recipient_id']!=u['id'])): fail(403,'friend_action_forbidden')
            c.execute('DELETE FROM friendships WHERE '+where,args)
    return {'ok':True}

@app.get('/api/challenges')
def challenges(u=Depends(user)):
    with pool.connection() as c:
        c.execute("UPDATE challenges SET status='expired' WHERE status='pending' AND expires_at<=now() AND (sender_id=%s OR recipient_id=%s)",(u['id'],u['id']))
        return allrows(c,'''SELECT ch.*,s.display_name AS sender_name,r.display_name AS recipient_name,m.id AS match_id
        FROM challenges ch LEFT JOIN users s ON s.id=ch.sender_id LEFT JOIN users r ON r.id=ch.recipient_id
        LEFT JOIN matches m ON m.challenge_id=ch.id WHERE ch.sender_id=%s OR ch.recipient_id=%s ORDER BY ch.created_at DESC LIMIT 100''',(u['id'],u['id']))

@app.post('/api/challenges',status_code=201)
def create_challenge(p:ChallengeCreate,u=Depends(user)):
    with pool.connection() as c:
        def run():
            target=one(c,'SELECT id FROM users WHERE public_id=%s',(p.public_id.upper(),))
            if not target: fail(403,'friend_required')
            c.execute('SELECT pg_advisory_xact_lock(least(%s,%s)::int,greatest(%s,%s)::int)',(u['id'],target['id'],u['id'],target['id']))
            t=one(c,'''SELECT u.id FROM users u JOIN friendships f ON f.status='accepted' AND
            ((f.requester_id=%s AND f.recipient_id=u.id) OR (f.recipient_id=%s AND f.requester_id=u.id)) WHERE u.public_id=%s''',(u['id'],u['id'],p.public_id.upper()))
            if not t: fail(403,'friend_required')
            if p.mission_id: catalog(c,p.mission_id,'mission',p.edition)
            cid=str(uuid4()); proposal={'edition':p.edition,'mission_id':p.mission_id,'mode':p.mode}
            c.execute('INSERT INTO challenges(id,sender_id,recipient_id,proposal,expires_at) VALUES(%s,%s,%s,%s,now()+%s*interval \'1 hour\')',(cid,u['id'],t['id'],Jsonb(proposal),int(os.getenv('CHALLENGE_TTL_HOURS','48'))))
            notify(c,t['id'],'challenge',cid)
            return {'id':cid}
        return operation(c,u,p,'challenge:create',run)

@app.post('/api/challenges/{cid}')
def act_challenge(cid:UUID,p:ChallengeAction,u=Depends(user)):
    with pool.connection() as c:
        def run():
            ch=one(c,'SELECT * FROM challenges WHERE id=%s',(str(cid),))
            if not ch or u['id'] not in (ch['sender_id'],ch['recipient_id']): fail(404,'challenge_not_found')
            if ch['sender_id'] is not None and ch['recipient_id'] is not None:
                c.execute('SELECT pg_advisory_xact_lock(least(%s,%s)::int,greatest(%s,%s)::int)',(ch['sender_id'],ch['recipient_id'],ch['sender_id'],ch['recipient_id']))
            ch=one(c,'SELECT * FROM challenges WHERE id=%s FOR UPDATE',(str(cid),))
            try: state=challenge_transition(ch['status'],p.action,u['id']==ch['sender_id'],ch['expires_at'],datetime.now(timezone.utc))
            except ValueError as e: fail(409,str(e))
            c.execute('UPDATE challenges SET status=%s WHERE id=%s',(state,str(cid)))
            result={'status':state}
            if state=='accepted':
                mid=str(uuid4()); prop=ch['proposal']
                c.execute("INSERT INTO matches(id,created_by,challenge_id,kind,status,edition,mission_id,setup) VALUES(%s,%s,%s,'friend','setup',%s,%s,%s)",(mid,ch['sender_id'],str(cid),prop.get('edition','2024'),prop.get('mission_id'),Jsonb(prop)))
                for slot,uid in enumerate((ch['sender_id'],ch['recipient_id']),1):
                    c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) SELECT %s,%s,id,display_name FROM users WHERE id=%s',(mid,slot,uid))
                result['match_id']=mid
            notify(c,ch['recipient_id'] if u['id']==ch['sender_id'] else ch['sender_id'],'challenge_'+state,cid)
            return result
        return operation(c,u,p,'challenge:'+str(cid),run)

@app.get('/api/notifications')
def notifications(u=Depends(user)):
    with pool.connection() as c: return allrows(c,'SELECT * FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT 100',(u['id'],))

@app.post('/api/notifications/{nid}/read')
def notification_read(nid:int,u=Depends(user)):
    with pool.connection() as c: c.execute('UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE id=%s AND user_id=%s',(nid,u['id']))
    return {'ok':True}

@app.get('/api/matches/{mid}')
def get_match(mid:UUID,u=Depends(user)):
    with pool.connection() as c: return snapshot(c,mid,u['id'])

@app.put('/api/matches/{mid}/setup')
def setup(mid:UUID,p:Setup,u=Depends(user)):
    with pool.connection() as c:
        def run():
            m=member(c,mid,u['id'],True); version(m,p.version)
            if m['status']!='setup': fail(409,'setup_closed')
            for cid,kind in [(p.mission_id,'mission'),(p.killzone_id,'killzone'),(p.team1_id,'team'),(p.team2_id,'team')]: catalog(c,cid,kind,p.edition)
            for oid in p.objective_ids: catalog(c,oid,'objective',p.edition)
            settings={'objective_ids':p.objective_ids,'rule_notes':p.rule_notes,'mode':m['setup'].get('mode','Обычный')}
            c.execute('''UPDATE matches SET edition=%s,mission_id=%s,killzone_id=%s,turns=%s,initiative=%s,setup=%s,notes=%s WHERE id=%s''',
            (p.edition,p.mission_id,p.killzone_id,p.turns,p.initiative,Jsonb(settings),p.notes,str(mid)))
            c.execute('UPDATE match_players SET team_id=CASE slot WHEN 1 THEN %s ELSE %s END WHERE match_id=%s',(p.team1_id,p.team2_id,str(mid)))
            me=actor_player(c,m,u)
            team=p.team1_id if me['slot']==1 else p.team2_id
            rosters.attach(c,u,me,p.roster_id,team)
            # v1.13: the operative count comes from the roster, else from the team; typed in only as the last resort.
            p.operative_count,source=teams.operative_count(c,p.roster_id,team,p.operative_manual,p.operative_count)
            c.execute('UPDATE match_players SET roster=%s,operative_count=%s,operative_source=%s WHERE id=%s',(p.roster,p.operative_count,source,me['id']))
            teams.refresh_counts(c,mid)
            reference.prepare_setup(c,m,p,u)
            audit(c,mid,u,'setup',{'edition':m['edition']},{'edition':p.edition,'mission_id':p.mission_id,'killzone_id':p.killzone_id,'team1_id':p.team1_id,'team2_id':p.team2_id,'turns':p.turns,'initiative':p.initiative,'objective_ids':p.objective_ids,'operatives':p.operative_count,'operative_source':source})
            return {'ok':True}
        return operation(c,u,p,'setup:'+str(mid),run)

@app.post('/api/matches/{mid}/actions')
def match_action(mid:UUID,p:MatchAction,u=Depends(user)):
    with pool.connection() as c:
        def run():
            m=member(c,mid,u['id'],True); version(m,p.version)
            if p.action=='turn':
                if m['status']!='active' or not p.turning_point or p.turning_point>m['turns']: fail(409,'turn_invalid')
                if p.turning_point>1: reference.require_primary(c,m)
                c.execute('UPDATE matches SET current_turn=%s WHERE id=%s',(p.turning_point,str(mid)))
                state=m['status']
            else:
                if m['recorded_result'] and p.action == 'reopen': fail(409,'recorded_reopen_forbidden')
                if m['recorded_result'] and p.action == 'cancel' and m['status'] in ('awaiting_confirmation','disputed') and m['created_by']==u['id']:
                    state='cancelled'
                else:
                    try: state=match_transition(m['status'],p.action,m['submitted_by']==u['id'],m['kind'],m['created_by']==u['id'])
                    except ValueError as e: fail(409,str(e))
                if p.action=='finish':
                    reference.require_primary(c,m)
                    clock.auto_pause(c,mid,u)
                    if m['scoring_mode']=='approved2025' and m['current_turn']!=4: fail(422,'finish_requires_turn_four')
                conceded=None
                if p.action=='concede':
                    # v1.13: at any turn, without the end-of-battle checks; the result is 10:0 (view player_totals).
                    conceded=(actor_player(c,m,u,p.slot) if p.slot and m['kind']=='hotseat' else actor_player(c,m,u))['slot']
                    clock.auto_pause(c,mid,u)
                    c.execute('UPDATE matches SET conceded_slot=%s WHERE id=%s',(conceded,str(mid)))
                if p.action=='reopen': c.execute('UPDATE matches SET conceded_slot=NULL WHERE id=%s',(str(mid),))
                if p.action=='start':
                    teams.refresh_counts(c,mid)  # v1.13: counts from rosters/teams as they are now
                    reference.freeze_rules(c,m)
                    if not m['mission_id'] or not m['killzone_id'] or one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND team_id IS NULL',(str(mid),)): fail(422,'setup_incomplete')
                    if m['kind']=='hotseat':
                        if not one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND slot=2 AND guest_id IS NOT NULL',(str(mid),)): fail(409,'opponent_missing')
                    elif not one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND slot=1 AND user_id IS NOT NULL',(str(mid),)) or not one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND slot=2 AND user_id IS NOT NULL',(str(mid),)):
                        # Invite match whose code was never used: opponent has not joined yet (not a deleted account).
                        fail(409,'opponent_missing' if m['challenge_id'] is None and not one(c,'SELECT 1 FROM match_invites WHERE match_id=%s AND used_at IS NOT NULL',(str(mid),)) else 'opponent_deleted')
                    c.execute('DELETE FROM match_invites WHERE match_id=%s AND used_at IS NULL',(str(mid),))
                    tracker.populate_all(c,m)  # v1.9: operatives of attached rosters
                if p.action=='cancel':
                    c.execute('DELETE FROM match_invites WHERE match_id=%s AND used_at IS NULL',(str(mid),))
                c.execute("UPDATE matches SET status=%s,submitted_by=CASE WHEN %s IN ('finish','concede') THEN %s ELSE submitted_by END,played_at=CASE WHEN %s='start' THEN now() ELSE played_at END WHERE id=%s",(state,p.action,u['id'],p.action,str(mid)))
                for row in allrows(c,'SELECT user_id FROM match_players WHERE match_id=%s AND user_id<>%s',(str(mid),u['id'])):
                    notify(c,row['user_id'],'match_'+state,mid)
                if state in ('confirmed','unconfirmed'): seasons.award_match(c,mid)  # v1.10: achievements
            after={'status':state,'turn':p.turning_point}
            if p.action=='concede': after['conceded_slot']=conceded
            audit(c,mid,u,p.action,{'status':m['status'],'turn':m['current_turn']},after)
            if p.action=='start': equipment.on_start(c,m,u)  # v1.14: equipment reveal, then 2CP each
            return {'status':state}
        return operation(c,u,p,'action:'+str(mid),run)

@app.post('/api/matches/{mid}/scores')
def scores(mid:UUID,p:Score,u=Depends(user)):
    with pool.connection() as c:
        def run():
            m=member(c,mid,u['id'],True); version(m,p.version)
            if m['status']!='active' or p.turning_point>m['turns']: fail(409,'scoring_closed')
            player=actor_player(c,m,u,p.slot)['id']
            before={}; after={}
            if p.delta is not None:
                if not p.source_id: fail(422,'source_required')
                old=one(c,'SELECT vp FROM turning_point_scores WHERE player_id=%s AND turning_point=%s AND source_id=%s',(player,p.turning_point,p.source_id))
                value=old['vp'] if old else 0
                try: new=reference.validate_score(c,m,player,p.turning_point,p.source_id,p.delta,value)
                except ValueError as e: fail(422,str(e))
                c.execute('''INSERT INTO turning_point_scores(player_id,turning_point,source_id,vp) VALUES(%s,%s,%s,%s)
                ON CONFLICT(player_id,turning_point,source_id) DO UPDATE SET vp=excluded.vp''',(player,p.turning_point,p.source_id,new))
                if m['scoring_mode']=='approved2025' and m['rules_snapshot']['sources'].get(str(p.source_id))=='tac':
                    c.execute('UPDATE turning_point_scores SET tac_op_id=(SELECT tac_op_id FROM match_players WHERE id=%s) WHERE player_id=%s AND turning_point=%s AND source_id=%s',(player,player,p.turning_point,p.source_id))
                    if new>0:c.execute('UPDATE match_players SET tac_revealed=true WHERE id=%s',(player,))
                before['vp']=value;after.update(vp=new,source_id=p.source_id)
            if p.cp is not None or p.notes is not None:
                old=one(c,'SELECT cp,notes FROM turning_point_states WHERE player_id=%s AND turning_point=%s',(player,p.turning_point)) or {'cp':0,'notes':''}
                c.execute('''INSERT INTO turning_point_states(player_id,turning_point,cp,notes) VALUES(%s,%s,%s,%s)
                ON CONFLICT(player_id,turning_point) DO UPDATE SET cp=excluded.cp,notes=excluded.notes''',(player,p.turning_point,p.cp if p.cp is not None else old['cp'],p.notes if p.notes is not None else old['notes']))
                before['cp']=old['cp']; after['cp']=p.cp
                # Do not duplicate private notes in immutable audit.
                after['notes_changed']=p.notes is not None
            if not after: fail(422,'empty_score_change')
            after.update(player_id=player,turning_point=p.turning_point)
            audit(c,mid,u,'score',before,after)
            return {'ok':True}
        return operation(c,u,p,'score:'+str(mid),run)

@app.get('/api/matches/{mid}/audit')
def match_audit(mid:UUID,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),u=Depends(user)):
    with pool.connection() as c:
        member(c,mid,u['id'])
        return allrows(c,'SELECT id,actor_id,action,before_data,after_data,created_at FROM match_audit WHERE match_id=%s ORDER BY id DESC LIMIT %s OFFSET %s',(str(mid),limit,offset))

@app.get('/api/matches/{mid}/events')
async def events(mid:UUID,request:Request,u=Depends(user)):
    with pool.connection() as c: member(c,mid,u['id'])
    token_hash=digest(request.cookies.get(COOKIE,''))
    def revision():
        with pool.connection() as c:
            if not one(c,'SELECT 1 FROM sessions WHERE token_hash=%s AND expires_at>now()',(token_hash,)): return None
            try: return member(c,mid,u['id'])['version'],clock.seq(c,mid),tracker.seq(c,mid)
            except HTTPException: return None
    async def stream():
        previous=(None,None,None)
        for _ in range(200): # Reconnect periodically; every iteration checks session and membership.
            if await request.is_disconnected(): break
            v=await asyncio.to_thread(revision)
            if v is None: break
            out=''
            # `clock` is separate from `revision`: clock taps must not redraw forms or bump matches.version.
            if v[0]!=previous[0]: out+='event: revision\ndata: '+str(v[0])+'\n\n'
            if v[1]!=previous[1]: out+='event: clock\ndata: '+str(v[1])+'\n\n'
            # v1.9: tracker taps do not bump matches.version either (see api/tracker.py).
            if v[2]!=previous[2]: out+='event: tracker\ndata: '+str(v[2])+'\n\n'
            yield out or ': heartbeat\n\n'
            previous=v
            await asyncio.sleep(2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-store'})

@app.post('/api/matches',status_code=201)
def create_match(p:MatchCreate,u=Depends(user)):
    """Start without a challenge: hot-seat (guest on the same device) or invite-by-code (slot 2 empty)."""
    with pool.connection() as c:
        def run():
            if p.mission_id: catalog(c,p.mission_id,'mission',p.edition)
            open_count=one(c,"SELECT count(*) AS n FROM matches WHERE created_by=%s AND status='setup'",(u['id'],))['n']
            if open_count>=int(os.getenv('MAX_OPEN_SETUPS','10')): fail(429,'too_many_open_matches')
            mid=str(uuid4()); settings={'edition':p.edition,'mission_id':p.mission_id,'mode':'Обычный'}
            c.execute("INSERT INTO matches(id,created_by,kind,status,edition,mission_id,setup) VALUES(%s,%s,%s,'setup',%s,%s,%s)",
                      (mid,u['id'],p.kind,p.edition,p.mission_id,Jsonb(settings)))
            c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,1,%s,%s)',(mid,u['id'],u['display_name']))
            if p.kind=='hotseat':
                gid=str(uuid4()); name=p.guest_name.strip(); lid=None
                if p.local: lid,name=localplayers.find_or_create(c,u,name)
                c.execute('INSERT INTO guest_opponents(id,owner_id,name) VALUES(%s,%s,%s)',(gid,u['id'],name))
                c.execute('INSERT INTO match_players(match_id,slot,guest_id,local_player_id,display_name) VALUES(%s,2,%s,%s,%s)',(mid,gid,lid,name))
            else:
                c.execute("INSERT INTO match_players(match_id,slot,display_name) VALUES(%s,2,'—')",(mid,))
            audit(c,mid,u,'create',{},{'kind':p.kind,'edition':p.edition})
            return {'id':mid}
        return operation(c,u,p,'match:create',run)

@app.post('/api/matches/{mid}/invite',status_code=201)
def create_invite(mid:UUID,p:InviteCreate,u=Depends(user)):
    with pool.connection() as c:
        def run():
            m=member(c,mid,u['id'],True)
            if m['kind']!='friend' or m['created_by']!=u['id'] or m['status']!='setup': fail(409,'invite_not_allowed')
            if one(c,'SELECT 1 FROM match_players WHERE match_id=%s AND slot=2 AND (user_id IS NOT NULL OR guest_id IS NOT NULL)',(str(mid),)): fail(409,'match_full')
            # Replace any previous open code: only one valid code per match.
            c.execute('DELETE FROM match_invites WHERE match_id=%s AND used_at IS NULL',(str(mid),))
            ttl=int(os.getenv('INVITE_TTL_HOURS','12'))
            for _ in range(5):
                code=''.join(secrets.choice(INVITE_ALPHABET) for _ in range(6))
                row=one(c,"INSERT INTO match_invites(code,match_id,created_by,expires_at) VALUES(%s,%s,%s,now()+%s*interval '1 hour') ON CONFLICT DO NOTHING RETURNING code,expires_at",(code,str(mid),u['id'],ttl))
                if row: return {'code':row['code'],'expires_at':row['expires_at'].isoformat()}
            fail(503,'invite_unavailable')
        return operation(c,u,p,'invite:'+str(mid),run)

@app.post('/api/invites/{code}/join')
def join_invite(code:str,p:InviteJoin,request:Request,u=Depends(user)):
    limit(request,'join',20)
    code=code.strip().upper()
    if not re.fullmatch(r'[A-Z2-9]{6,8}',code): fail(404,'invite_invalid')
    with pool.connection() as c:
        def run():
            inv=one(c,'SELECT * FROM match_invites WHERE code=%s FOR UPDATE',(code,))
            if not inv: fail(404,'invite_invalid')
            if inv['used_by']==u['id']: return {'match_id':str(inv['match_id'])}
            try: invite_state(inv['expires_at'],inv['used_at'],datetime.now(timezone.utc))
            except ValueError as e: fail(410,str(e))
            m=one(c,'SELECT * FROM matches WHERE id=%s FOR UPDATE',(str(inv['match_id']),))
            if m['status']!='setup': fail(410,'invite_expired')
            if m['created_by']==u['id']: fail(409,'invite_own_match')
            if one(c,'SELECT 1 FROM blocks WHERE (user_id=%s AND target_id=%s) OR (user_id=%s AND target_id=%s)',(u['id'],m['created_by'],m['created_by'],u['id'])): fail(403,'blocked')
            slot=one(c,'SELECT * FROM match_players WHERE match_id=%s AND slot=2 FOR UPDATE',(str(m['id']),))
            if slot['user_id'] is not None or slot['guest_id'] is not None: fail(409,'match_full')
            c.execute('UPDATE match_players SET user_id=%s,display_name=%s WHERE id=%s',(u['id'],u['display_name'],slot['id']))
            c.execute('UPDATE match_invites SET used_by=%s,used_at=now() WHERE code=%s',(u['id'],code))
            audit(c,m['id'],u,'join',{},{'slot':2})
            notify(c,m['created_by'],'match_joined',m['id'])
            return {'match_id':str(m['id'])}
        return operation(c,u,p,'join:'+code,run)

@app.post('/api/quick-matches',status_code=201)
def quick(p:Quick,request:Request,u=Depends(user)):
    if p.opponent_public_id: limit(request,'quick-recorded',60)
    with pool.connection() as c:
        def run():
            for cid,kind in [(p.team1_id,'team'),(p.team2_id,'team'),(p.mission_id,'mission'),(p.killzone_id,'killzone')]: catalog(c,cid,kind,p.edition)
            mission=one(c,'SELECT config FROM catalogs WHERE id=%s',(p.mission_id,))
            if mission['config'].get('pack')=='approved2025' and max(p.vp_for,p.vp_against)>21: fail(422,'final_score_cap_exceeded')
            source=one(c,"SELECT id FROM catalogs WHERE edition=%s AND code=%s AND kind='source'",(p.edition,'2024-local-source-recorded' if p.edition=='2024' else p.edition+'-vp-manual'))
            if not source: fail(422,'manual_source_missing')
            mid=str(uuid4())
            if p.opponent_public_id:
                if p.local: fail(422,'recorded_opponent_invalid')
                target=one(c,'SELECT id,display_name FROM users WHERE public_id=%s',(p.opponent_public_id.upper(),))
                if not target or target['id']==u['id']: fail(404,'account_not_found')
                args=(u['id'],target['id'],u['id'],target['id'])
                c.execute('SELECT pg_advisory_xact_lock(least(%s,%s)::int,greatest(%s,%s)::int)',args)
                if one(c,'SELECT 1 FROM blocks WHERE (user_id=%s AND target_id=%s) OR (user_id=%s AND target_id=%s)',(u['id'],target['id'],target['id'],u['id'])): fail(403,'blocked')
                c.execute("""INSERT INTO matches(id,created_by,kind,status,edition,mission_id,killzone_id,played_at,notes,submitted_by,recorded_result)
                    VALUES(%s,%s,'friend','awaiting_confirmation',%s,%s,%s,%s,%s,%s,true)""",
                    (mid,u['id'],p.edition,p.mission_id,p.killzone_id,p.played_at,p.notes,u['id']))
                second=(2,target['id'],None,None,target['display_name'],p.team2_id,p.vp_against)
            else:
                gid=str(uuid4());guest_name=p.guest_name;lid=None
                if p.local: lid,guest_name=localplayers.find_or_create(c,u,guest_name)
                c.execute('INSERT INTO guest_opponents(id,owner_id,name) VALUES(%s,%s,%s)',(gid,u['id'],guest_name))
                c.execute("INSERT INTO matches(id,created_by,kind,status,edition,mission_id,killzone_id,played_at,notes) VALUES(%s,%s,'guest','unconfirmed',%s,%s,%s,%s,%s)",(mid,u['id'],p.edition,p.mission_id,p.killzone_id,p.played_at,p.notes))
                second=(2,None,gid,lid,guest_name,p.team2_id,p.vp_against)
            for slot,uid,guest,local,name,team,vp in [(1,u['id'],None,None,u['display_name'],p.team1_id,p.vp_for),second]:
                pid=one(c,'INSERT INTO match_players(match_id,slot,user_id,guest_id,local_player_id,display_name,team_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id',(mid,slot,uid,guest,local,name,team))['id']
                c.execute('INSERT INTO turning_point_scores(player_id,turning_point,source_id,vp) VALUES(%s,1,%s,%s)',(pid,source['id'],vp))
            audit(c,mid,u,'quick_record',{}, {'vp_for':p.vp_for,'vp_against':p.vp_against})
            if p.opponent_public_id: notify(c,target['id'],'match_awaiting_confirmation',mid)
            else: seasons.award_match(c,mid)
            return {'id':mid}
        return operation(c,u,p,'quick:create',run)


def filters(u,from_date,to_date,opponent,team_id,mission_id,killzone_id,kind, alias='r'):
    clauses=[f'{alias}.user_id=%s'];args=[u['id']]
    for column,value in [('team_id',team_id),('mission_id',mission_id),('killzone_id',killzone_id),('kind',kind)]:
        if value is not None: clauses.append(f'{alias}.{column}=%s');args.append(value)
    if from_date: clauses.append(f'{alias}.played_at >= %s::date::timestamp AT TIME ZONE \'Europe/Moscow\'');args.append(from_date)
    if to_date: clauses.append(f'{alias}.played_at < (%s::date+1)::timestamp AT TIME ZONE \'Europe/Moscow\'');args.append(to_date)
    if opponent:
        clauses.append(f'({alias}.opponent_name ILIKE %s OR {alias}.opponent_id=(SELECT id FROM users WHERE public_id=%s))');args.extend(['%'+opponent+'%',opponent.upper()])
    return ' AND '.join(clauses),args

class FilterParams:
    def __init__(self,from_date:str|None=Query(None,pattern=r'^\d{4}-\d{2}-\d{2}$'),to_date:str|None=Query(None,pattern=r'^\d{4}-\d{2}-\d{2}$'),opponent:str|None=Query(None,max_length=64),team_id:int|None=None,mission_id:int|None=None,killzone_id:int|None=None,kind:str|None=Query(None,pattern='^(friend|guest|hotseat)$')):
        from datetime import date
        try:
            if from_date: date.fromisoformat(from_date)
            if to_date: date.fromisoformat(to_date)
        except ValueError: fail(422,'date_invalid')
        self.values=(from_date,to_date,opponent,team_id,mission_id,killzone_id,kind)

@app.get('/api/history')
def history(f:FilterParams=Depends(),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),u=Depends(user)):
    where,args=filters(u,*f.values)
    with pool.connection() as c:
        return {'items':allrows(c,'SELECT r.*,m.status FROM player_results r JOIN matches m ON m.id=r.match_id WHERE '+where+' ORDER BY r.played_at DESC,r.match_id LIMIT %s OFFSET %s',args+[limit,offset]),
        'total':one(c,'SELECT count(*) AS n FROM player_results r WHERE '+where,args)['n']}

@app.get('/api/live-matches')
def live_matches(u=Depends(user)):
    with pool.connection() as c:
        return allrows(c,"SELECT m.id,m.kind,m.status,m.edition,m.mission_id,m.updated_at FROM matches m JOIN match_players p ON p.match_id=m.id WHERE p.user_id=%s AND m.status NOT IN ('confirmed','unconfirmed','cancelled') ORDER BY m.updated_at DESC LIMIT 100",(u['id'],))

@app.get('/api/stats')
def stats(f:FilterParams=Depends(),u=Depends(user)):
    where,args=filters(u,*f.values)
    with pool.connection() as c:
        summary=one(c,'''SELECT count(*)::int games,count(*) FILTER(WHERE result='win')::int wins,
        count(*) FILTER(WHERE result='draw')::int draws,count(*) FILTER(WHERE result='loss')::int losses,
        round(100.0*count(*) FILTER(WHERE result='win')/nullif(count(*),0),1) win_rate,
        round(avg(vp_for),2) avg_for,round(avg(vp_against),2) avg_against,round(avg(vp_for-vp_against),2) avg_diff
        FROM player_results r WHERE '''+where,args)
        breakdown={}
        for field in ['team_id','opponent_team_id','mission_id','killzone_id','opponent_id']:
            breakdown[field]=allrows(c,f'''SELECT r.{field} AS key,{'coalesce(max(u.display_name),max(r.opponent_name))' if field=='opponent_id' else 'max(c.label)'} AS label,
            count(*)::int games,count(*) FILTER(WHERE result='win')::int wins,
            count(*) FILTER(WHERE result='draw')::int draws,count(*) FILTER(WHERE result='loss')::int losses,
            round(avg(vp_for-vp_against),2) avg_diff FROM player_results r
            {'LEFT JOIN users u ON u.id=r.opponent_id' if field=='opponent_id' else 'LEFT JOIN catalogs c ON c.id=r.'+field}
            WHERE {where} {'AND r.opponent_id IS NOT NULL' if field=='opponent_id' else ''} GROUP BY r.{field} ORDER BY games DESC LIMIT 100''',args)
        trend=allrows(c,"SELECT to_char(date_trunc('month',played_at AT TIME ZONE 'Europe/Moscow'),'YYYY-MM') AS month,count(*)::int games,round(avg(vp_for),2) avg_for,round(avg(vp_against),2) avg_against FROM player_results r WHERE "+where+" GROUP BY 1 ORDER BY 1",args)
        streak=one(c,'''WITH ordered AS (SELECT result,row_number() OVER(ORDER BY played_at,match_id)-row_number() OVER(PARTITION BY result ORDER BY played_at,match_id) AS grp FROM player_results r WHERE '''+where+'''), runs AS (SELECT count(*) n FROM ordered WHERE result='win' GROUP BY grp)
        SELECT coalesce(max(n),0)::int AS best FROM runs''',args)
        current=one(c,'''WITH ordered AS (SELECT result,row_number() OVER(ORDER BY played_at DESC,match_id DESC) AS rn FROM player_results r WHERE '''+where+''') SELECT count(*)::int AS current FROM ordered WHERE result='win' AND rn<coalesce((SELECT min(rn) FROM ordered WHERE result<>'win'),2147483647)''',args)
        # v1.9: results by roster and game clock time (api/insights.py).
        breakdown['roster_id']=insights.roster_breakdown(c,where,args)
        return {'summary':summary,'breakdown':breakdown,'trend':trend,'streak':{**streak,**current},'clock':insights.clock_summary(c,where,args)}

@app.get('/api/export')
def export(format:str=Query('json',pattern='^(csv|json)$'),f:FilterParams=Depends(),u=Depends(user)):
    where,args=filters(u,*f.values)
    def rows():
        # Named cursor bounds memory even for a long history.
        with pool.connection() as c:
            with c.cursor(name='export_history',row_factory=dict_row) as cur:
                cur.execute('SELECT r.* FROM player_results r WHERE '+where+' ORDER BY played_at DESC',args)
                if format=='json':
                    yield '['; first=True
                    for row in cur:
                        yield ('' if first else ',')+json.dumps(row,default=str,ensure_ascii=False);first=False
                    yield ']'
                else:
                    buf=io.StringIO();writer=None
                    yield '\ufeff'
                    for row in cur:
                        if writer is None: writer=csv.DictWriter(buf,fieldnames=list(row));writer.writeheader()
                        # Neutralize spreadsheet formulas in untrusted user names.
                        writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
                        yield buf.getvalue();buf.seek(0);buf.truncate(0)
    return StreamingResponse(rows(),media_type='application/json' if format=='json' else 'text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="killstass-history.{format}"'})

WEB=os.getenv('WEB_DIR',os.path.join(os.path.dirname(__file__),'..','web'))
_index_cache = {}
@app.get('/')
def index(request: Request):
    # v1.9: the server substitutes VERSION, so index.html, the menu and asset URLs can never disagree.
    if 'body' not in _index_cache:
        with open(os.path.join(WEB,'index.html'),encoding='utf-8') as f: body=f.read().replace('{{VERSION}}',APP_VERSION)
        _index_cache.update(body=body,etag='"'+hashlib.sha256(body.encode()).hexdigest()[:20]+'"')
    headers={'Cache-Control':'no-cache','ETag':_index_cache['etag']}
    if request.headers.get('if-none-match')==_index_cache['etag']: return Response(status_code=304,headers=headers)
    return Response(_index_cache['body'],media_type='text/html; charset=utf-8',headers=headers)
_sw_cache = {}
@app.get('/sw.js')
def service_worker():
    """v1.10: offline app shell and Web Push. Served from / (scope of the whole site) with this release's asset list."""
    if 'body' not in _sw_cache:
        root = pathlib.Path(WEB)
        assets = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name != 'sw.js'
                        and p.suffix in ('.js', '.css', '.svg', '.json', '.woff2', '.png', '.webmanifest'))
        body = (root / 'sw.js').read_text(encoding='utf-8').replace('{{VERSION}}', APP_VERSION)
        _sw_cache['body'] = re.sub(r'/\*ASSETS\*/\s*\[\]', lambda _: json.dumps([f'/static/v/{APP_VERSION}/{a}' for a in assets]), body, count=1)
    return Response(_sw_cache['body'], media_type='text/javascript; charset=utf-8',
                    headers={'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'})
# Versioned assets are immutable on success; /static keeps unversioned names (logo, manifest).
app.mount(f'/static/v/{APP_VERSION}',StaticFiles(directory=WEB),name='static-versioned')
app.mount('/static',StaticFiles(directory=WEB),name='static')

# Administrator dependency (#admin). Defined here, before the feature modules below are imported, so that
# importing any of them first (tests, `python -m api.…`) cannot meet a half-initialised api.admin.
def admin_user(u=Depends(user)):
    if not u.get('is_admin'):
        fail(403, 'admin_only')
    return u


# Registered after core definitions to keep the original API module compatible.
from . import reference
from . import clock
from . import extras
from . import teams
from . import rosters
from . import tracker
from . import rosterimport
from . import insights
from . import tournaments
from . import admin
# v1.10
from . import accounts
from . import seasons
from . import nights
from . import tv
from . import boards
from . import push
from . import live
# v1.11
from . import library
# v1.12
from . import corerules
# v1.13
from . import localplayers
# v1.14
from . import navsummary
from . import equipment
from . import command
from . import clienterrors
