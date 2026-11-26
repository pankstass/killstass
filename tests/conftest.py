import os
import pytest

@pytest.fixture
def clients():
    admin=os.getenv('TEST_DATABASE_URL')
    if not admin: pytest.skip('Set TEST_DATABASE_URL and DATABASE_URL for PostgreSQL integration tests')
    import psycopg
    from fastapi.testclient import TestClient
    from api.main import app,ORIGIN,pool
    # Dedicated database ONLY; never use a production URL.
    if 'test' not in admin.rsplit('/',1)[-1]: raise RuntimeError('Test database name must contain test')
    with psycopg.connect(admin) as c:
        c.execute('TRUNCATE users,rate_limits CASCADE')
        # v1.10: instance-wide tables that are not linked to accounts (built-in achievements keep their defaults).
        c.execute('DELETE FROM achievements WHERE NOT builtin')
        c.execute("UPDATE achievements SET active=true,season_id=NULL,threshold=CASE code WHEN 'matches_10' THEN 10 WHEN 'comeback' THEN 3 ELSE 1 END")
        c.execute('DELETE FROM seasons')
        c.execute('DELETE FROM app_settings')
    # Pool can be reopened only once: integration tests share session lifespan below.
    if pool.closed: pool.open();pool.wait()
    a=TestClient(app,base_url=ORIGIN,headers={'Origin':ORIGIN})
    b=TestClient(app,base_url=ORIGIN,headers={'Origin':ORIGIN})
    yield a,b
    a.close();b.close()

@pytest.fixture(scope='session',autouse=True)
def close_test_pool():
    yield
    import sys
    module=sys.modules.get('api.main')
    if module and not module.pool.closed:module.pool.close()
