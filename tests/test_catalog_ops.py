import importlib.util
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4
import pytest
from api.domain import primary_bonus,kill_grade,score_after

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('catalog_import',ROOT/'tools/catalog-import/import_catalog.py')
imp=importlib.util.module_from_spec(spec);spec.loader.exec_module(imp)

@pytest.mark.parametrize('vp,bonus',[(0,0),(1,1),(2,1),(3,2),(4,2),(5,3),(6,3)])
def test_primary_round_up(vp,bonus):assert primary_bonus(vp)==bonus

@pytest.mark.parametrize('vp',[-1,7,999])
def test_primary_boundaries(vp):
    with pytest.raises(ValueError):primary_bonus(vp)

def test_kill_grade_boundaries_and_caps():
    assert [kill_grade(k,[1,2,4,5,6]) for k in range(7)]==[0,1,2,2,3,4,5]
    assert score_after(1,1,2)==2
    with pytest.raises(ValueError):score_after(2,1,2)

def test_seed_verified_limits_and_import_idempotency(tmp_path):
    data=json.loads((ROOT/'db/seed.json').read_text())
    sql,report=imp.build(data,data)
    assert report['added']==report['changed']==0
    assert report['unchanged']==len(data['catalogs'])
    assert 'ON CONFLICT(code) DO UPDATE' in sql
    for r in data['catalogs']:
        if r['kind'] in ('mission','tac_op') and r['active']:
            assert len(r['config']['per_turn_caps'])==4
            assert r['config']['max_per_battle']==6
    broken=json.loads(json.dumps(data));broken['catalogs'][0]['verification']='unverified'
    with pytest.raises(ValueError):imp.build(broken)
    before=set(tmp_path.iterdir())
    subprocess.run(['python',str(ROOT/'tools/catalog-import/import_catalog.py'),'--input',str(ROOT/'db/seed.json'),'--output',str(tmp_path/'nothing'),'--dry-run'],check=True,capture_output=True)
    assert set(tmp_path.iterdir())==before

from tests.test_integration import register,post,op

def approved_match(a,b):
    ua=register(a,'alpha');ub=register(b,'bravo')
    data=a.get('/api/catalogs').json()
    pick=lambda kind,code:next(r['id'] for r in data if r['kind']==kind and r['code'].endswith(code))
    team=pick('team','team-angel-of-death');mission=pick('mission','mission-secure');zone=pick('killzone','volkus-1');tac=pick('tac_op','tac-op-rout')
    post(a,'/friends',{'public_id':ub['public_id']});post(b,'/friends/'+ua['public_id'],{'action':'accept'})
    ch=post(a,'/challenges',op(public_id=ub['public_id']));mid=post(b,'/challenges/'+ch['id'],op(action='accepted'))['match_id']
    for client,primary in ((a,'crit'),(b,'kill')):
        m=client.get('/api/matches/'+mid).json()
        r=client.put('/api/matches/'+mid+'/setup',json=op(version=m['version'],mission_id=mission,killzone_id=zone,team1_id=team,team2_id=team,operative_count=6,tac_op_id=tac,primary_op=primary))
        assert r.status_code==200,r.text
    m=a.get('/api/matches/'+mid).json()
    assert m['players'][1]['primary_op'] is None and m['players'][1]['tac_op_id'] is None
    post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='start'))
    for client,primary in ((a,'crit'),(b,'kill')):
        m=client.get('/api/matches/'+mid).json();post(client,'/matches/'+mid+'/primary',op(version=m['version'],primary_op=primary))
    return mid,data

def test_reference_auth_cache_and_inactive_catalog(clients):
    a,b=clients
    assert a.get('/api/reference/game-sequence').status_code==401
    register(a,'alpha')
    r=a.get('/api/reference/game-sequence');assert r.status_code==200,r.text
    assert len(r.json()['steps'])==22 and 'private' in r.headers['cache-control']
    assert a.get('/api/reference/game-sequence',headers={'If-None-Match':r.headers['etag']}).status_code==304
    assert a.get('/api/reference/game-sequence?edition=2021').status_code==404
    assert not any(r['config'].get('demo') for r in a.get('/api/catalogs').json())
    assert any(r['code']=='2024-team-a' and not r['active'] for r in a.get('/api/catalogs?include_inactive=true').json())

def test_approved_finish_bonus_privacy_limits_and_tac_stats(clients):
    a,b=clients;mid,data=approved_match(a,b)
    source=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    m=a.get('/api/matches/'+mid).json()
    assert 'tacs' not in m['rules_snapshot']
    assert all('rules_snapshot' not in r for r in a.get('/api/live-matches').json())
    assert a.post('/api/matches/'+mid+'/scores',json=op(version=m['version'],turning_point=1,source_id=source,delta=1)).status_code==422
    for tp,vp in [(2,2),(3,1)]:
        m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/scores',op(version=m['version'],turning_point=tp,source_id=source,delta=vp))
    m=a.get('/api/matches/'+mid).json();request=op(version=m['version'],turning_point=1,delta=4)
    post(a,'/matches/'+mid+'/kills',request);post(a,'/matches/'+mid+'/kills',request)
    m=a.get('/api/matches/'+mid).json();assert m['players'][0]['grade']==3
    assert m['players'][0]['primary_bonus']==0
    post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='turn',turning_point=4))
    m=a.get('/api/matches/'+mid).json()
    post(a,'/matches/'+mid+'/actions',op(version=m['version'],action='finish'))
    m=b.get('/api/matches/'+mid).json();assert m['players'][0]['primary_op']=='crit'
    assert m['players'][0]['kill']==4 and m['players'][0]['primary_bonus']==2 and m['players'][0]['vp']==9
    post(b,'/matches/'+mid+'/actions',op(version=m['version'],action='confirm'))
    assert a.get('/api/stats').json()['summary']['avg_for']==9
    assert a.get('/api/stats/tac-ops').json()[0]['vp']==0

def test_caps_and_resurrection(clients):
    a,b=clients;mid,data=approved_match(a,b)
    source=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='tac')
    for tp in range(1,4):
        m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/scores',op(version=m['version'],turning_point=tp,source_id=source,delta=2))
    m=a.get('/api/matches/'+mid).json()
    assert a.post('/api/matches/'+mid+'/scores',json=op(version=m['version'],turning_point=4,source_id=source,delta=1)).status_code==422
    post(a,'/matches/'+mid+'/kills',op(version=m['version'],turning_point=1,delta=4))
    m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/kills',op(version=m['version'],turning_point=2,delta=-1))
    m=a.get('/api/matches/'+mid).json();assert m['players'][0]['grade']==2
    assert m['players'][0]['incapacitated']==3
    assert b.get('/api/matches/'+mid).json()['players'][0]['tac_op_id'] is not None

def test_frozen_rules_survive_catalog_update(clients):
    import psycopg
    a,b=clients;mid,data=approved_match(a,b)
    source=next(r['id'] for r in data if r['kind']=='source' and r['config'].get('component')=='crit')
    mission=next(r['id'] for r in data if r['code'].endswith('mission-secure'))
    with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:
        old=c.execute('SELECT config FROM catalogs WHERE id=%s',(mission,)).fetchone()[0]
        c.execute("UPDATE catalogs SET active=false,config=jsonb_set(config,'{per_turn_caps}','[0,0,0,0]') WHERE id=%s",(mission,))
    try:
        m=a.get('/api/matches/'+mid).json();post(a,'/matches/'+mid+'/scores',op(version=m['version'],turning_point=2,source_id=source,delta=2))
    finally:
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as c:c.execute('UPDATE catalogs SET active=true,config=%s WHERE id=%s',(Jsonb(old),mission))

def test_upgrade_003_004_preserves_legacy_results_and_reimport():
    admin=os.getenv('TEST_DATABASE_URL')
    if not admin:pytest.skip('TEST_DATABASE_URL required')
    if 'test' not in admin.rsplit('/',1)[-1]:raise RuntimeError('test DSN only')
    import psycopg
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    name='killstass_migration_test_'+uuid4().hex[:10]
    opts=conninfo_to_dict(admin);opts['dbname']=name;dsn=make_conninfo(**opts)
    with psycopg.connect(admin,autocommit=True) as conn:conn.execute('CREATE DATABASE '+name+" TEMPLATE template0 ENCODING 'UTF8'")
    try:
        def apply(file):
            r=subprocess.run(['psql','-X',dsn,'-v','ON_ERROR_STOP=1','--single-transaction','-f',str(ROOT/'db/migrations'/file)],capture_output=True,text=True)
            assert r.returncode==0,r.stderr
        apply('001_initial.sql');apply('002_seed.sql')
        with psycopg.connect(dsn) as c:
            a=c.execute("INSERT INTO users(public_id,login,display_name,password_hash) VALUES('ABCDEFGH','migrate_a','A','not-a-login-hash') RETURNING id").fetchone()[0]
            b=c.execute("INSERT INTO users(public_id,login,display_name,password_hash) VALUES('JKLMNPQR','migrate_b','B','not-a-login-hash') RETURNING id").fetchone()[0]
            mid=str(uuid4());c.execute("INSERT INTO matches(id,created_by,kind,status,edition,played_at) VALUES(%s,%s,'friend','confirmed','2024','2026-09-01T12:00:00Z')",(mid,a))
            ids=[]
            for slot,uid in [(1,a),(2,b)]:ids.append(c.execute('INSERT INTO match_players(match_id,slot,user_id,display_name) VALUES(%s,%s,%s,%s) RETURNING id',(mid,slot,uid,str(slot))).fetchone()[0])
            source=c.execute("SELECT id FROM catalogs WHERE code='2024-vp-critical'").fetchone()[0]
            for pid,vp in zip(ids,[9,6]):c.execute('INSERT INTO turning_point_scores VALUES(%s,1,%s,%s)',(pid,source,vp))
            before=c.execute('SELECT * FROM player_results ORDER BY user_id').fetchall()
        apply('003_catalog_and_ops.sql');apply('004_verified_catalog.sql')
        with psycopg.connect(dsn) as c:
            assert c.execute('SELECT * FROM player_results ORDER BY user_id').fetchall()==before
            assert c.execute('SELECT vp FROM player_totals ORDER BY id').fetchall()==[(9,),(6,)]
            state=c.execute('SELECT code,id,config,active FROM catalogs ORDER BY code').fetchall()
            assert not c.execute('SELECT active FROM catalogs WHERE id=%s',(source,)).fetchone()[0]
            assert c.execute('SELECT count(*) FROM game_sequence WHERE active').fetchone()[0]==22
        apply('004_verified_catalog.sql')
        with psycopg.connect(dsn) as c:
            assert c.execute('SELECT code,id,config,active FROM catalogs ORDER BY code').fetchall()==state
            assert c.execute('SELECT * FROM player_results ORDER BY user_id').fetchall()==before
            assert [c.execute('SELECT primary_bonus(%s)',(n,)).fetchone()[0] for n in range(7)]==[0,1,1,2,2,3,3]
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s',(name,))
            conn.execute('DROP DATABASE '+name)

def test_runtime_role_readonly_references_and_no_ddl():  # v1.7: team_data is covered in test_teams.py
    if not os.getenv('TEST_DATABASE_URL'):pytest.skip('test environment required')
    import psycopg
    dsn=os.environ['DATABASE_URL']
    if 'test' not in dsn.rsplit('/',1)[-1]:raise RuntimeError('test DSN only')
    for sql in ["UPDATE catalogs SET active=active", "DELETE FROM game_sequence", "CREATE TABLE forbidden_ddl_test(x int)"]:
        with psycopg.connect(dsn) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute(sql)

def test_initial_migrations_unchanged():
    import hashlib
    for name,sha in [('001_initial.sql','c9e27fa3833e404f5a828c3b8630c6f130b6dc237305bb5005b2a5626b516ab8'),('002_seed.sql','684bd59351be5ef7d141908ea801a69bdcdafd034e4575a0692e951ca033e5d8')]:
        assert hashlib.sha256((ROOT/'db/migrations'/name).read_bytes()).hexdigest()==sha

def test_conditional_archetypes_and_invalid_import():
    # Domain helper raises before any database call.
    os.environ.setdefault('DATABASE_URL','postgresql://unused@localhost/unused')
    from api.main import reference
    archetypes=reference.archetypes
    from fastapi import HTTPException
    team={'config':{'archetypes':['Seek & Destroy','Security','Recon','Infiltration'],'conditional_archetypes':{'dire_avenger':'Security','howling_banshee':'Recon','striking_scorpion':'Infiltration'}}}
    assert archetypes(team,{},8)==['Seek & Destroy']
    assert archetypes(team,{'dire_avenger':4,'howling_banshee':4,'striking_scorpion':0},8)==['Seek & Destroy','Security','Recon']
    with pytest.raises(HTTPException):archetypes(team,{'dire_avenger':3,'howling_banshee':4,'striking_scorpion':0},8)
    data=json.loads((ROOT/'db/seed.json').read_text())
    next(r for r in data['catalogs'] if r['kind']=='mission')['config']['per_turn_caps']=[99]*4
    with pytest.raises(ValueError):imp.build(data)
