"""v1.14.1: don't cache static failures; retain immutable successful versioned assets."""
from pathlib import Path
from api.main import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_static_cache_policy(clients):
    a, _ = clients
    path = f'/static/v/{APP_VERSION}/main.js'
    ok = a.get(path)
    assert ok.status_code == 200
    assert ok.headers['cache-control'] == 'public, max-age=31536000, immutable'
    conditional = a.get(path, headers={'If-None-Match': ok.headers['etag']})
    assert conditional.status_code == 304
    assert conditional.headers['cache-control'] == ok.headers['cache-control']
    assert a.get('/static/logo.svg').headers['cache-control'] == 'public, max-age=3600'
    for missing in (f'/static/v/{APP_VERSION}/missing.js', '/static/v/0.0.0/main.js', '/static/missing.js'):
        r = a.get(missing)
        assert r.status_code == 404
        assert r.headers['cache-control'] == 'no-store'
    assert a.get('/').headers['cache-control'] == 'no-cache'
    assert a.get('/sw.js').headers['cache-control'] == 'no-cache'


def test_deployment_guards():
    docker = (ROOT / 'api/Dockerfile').read_text()
    caddy = (ROOT / 'proxy/Caddyfile').read_text()
    sw = (ROOT / 'web/sw.js').read_text()
    assert '"--limit-concurrency","256","--backlog","128"' in docker
    assert '?Cache-Control "no-store"' in caddy
    assert 'header @versioned' not in caddy
    assert 'assets.slice(i, i + 8)' in sw
