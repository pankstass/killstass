"""Deployment regressions: static configuration plus real PostgreSQL role default.

Static checks do not replace starting the actual Docker images on the target host.
"""
import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_tmpfs_each_mount_is_one_absolute_scalar():
    mounts = []
    for line in (ROOT / 'docker-compose.yml').read_text().splitlines():
        if line.strip().startswith('tmpfs:'):
            # Flow sequences use quoted strings; no YAML dependency for this regression.
            values = ast.literal_eval(line.split('tmpfs:', 1)[1].strip())
            assert len(values) == 1
            target, options = values[0].split(':', 1)
            assert target == '/tmp'
            assert {'noexec', 'nosuid'} <= set(options.split(','))
            mounts.append(values[0])
    # api, proxy and (v1.10) pushworker
    assert len(mounts) == 3


def test_caddy_no_file_capability_and_no_sni_fallback():
    dockerfile = (ROOT / 'proxy/Dockerfile').read_text()
    assert 'setcap -r /usr/bin/caddy' in dockerfile
    assert dockerfile.index('setcap -r') < dockerfile.index('USER 10001:10001')
    config = (ROOT / 'proxy/Caddyfile').read_text()
    # Fallback must be in the global block, before its nested servers section.
    assert config.index('default_sni {$APP_HOST}') < config.index('servers {')
    compose = (ROOT / 'docker-compose.yml').read_text()
    # v1.10: pushworker drops all capabilities too; tailscale needs NET_ADMIN, but no new privileges
    assert compose.count('cap_drop: [ALL]') == 3
    assert compose.count('no-new-privileges:true') == 4


def test_caddy_body_limits_rosters_only():
    config = (ROOT / 'proxy/Caddyfile').read_text()
    assert '@rosterimport path /api/rosters/import' in config
    assert '@rosters {\n  path /api/rosters /api/rosters/*\n  not path /api/rosters/import\n }' in config
    assert '@ordinary not path /api/rosters /api/rosters/*' in config
    imports = config.index('request_body @rosterimport {')
    rosters = config.index('request_body @rosters {')
    ordinary = config.index('request_body @ordinary {')
    assert 'max_size 1MB' in config[imports:config.index('}', imports)]
    assert config.index('max_size 256KB', rosters) < ordinary
    assert 'max_size 32KB' in config[ordinary:config.index('}', ordinary)]
    # Limits must apply before the request is proxied.
    assert ordinary < config.index('reverse_proxy api:8000')


def test_jit_off_for_new_runtime_connection_only():
    admin = os.getenv('TEST_DATABASE_URL')
    if not admin:
        pytest.skip('TEST_DATABASE_URL required; migrate.sh must have run')
    import psycopg
    dsn = os.environ['DATABASE_URL']
    from psycopg.conninfo import conninfo_to_dict
    assert 'test' in conninfo_to_dict(dsn)['dbname'], 'Dedicated test database only'
    with psycopg.connect(dsn) as c:
        assert c.execute('SELECT current_user').fetchone()[0] == 'killstass_app'
        assert c.execute('SHOW jit').fetchone()[0] == 'off'
    with psycopg.connect(admin) as c:
        row = c.execute("""
            SELECT s.setconfig FROM pg_db_role_setting s
            JOIN pg_roles r ON r.oid=s.setrole
            JOIN pg_database d ON d.oid=s.setdatabase
            WHERE r.rolname='killstass_app' AND d.datname=current_database()
        """).fetchone()
        assert row and 'jit=off' in row[0]
