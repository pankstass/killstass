"""v1.12: «Основные правила» (#core) — the current Kill Team core rules: the text of the core book (2024) with the
official rules updates applied (v1.13: no change marks and no page numbers), chapters and sections.
Built from tools/core-rules/src by tools/core-rules/build.py into api/data/core-rules.json and served whole
(~160 KB with the terms of v1.13, gzip by the proxy) for browsing and the in-browser search; the service worker keeps the last copy offline.
v1.13: GET /api/reference/terms — only the terms of the tooltips (game terms, terrain, actions, weapon rules) with
their official definitions, for the pages that show rules text (datacards, faction rules, the reference)."""
import json
import os
from fastapi import Depends, Request
from fastapi.responses import Response
from . import main as core

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'core-rules.json')
_doc = {}


def load():
    """Read once per process: the compact body and its ETag (the version is a hash of the content)."""
    if 'body' not in _doc:
        with open(PATH, encoding='utf-8') as f: doc = json.load(f)
        _doc.update(version=doc['version'], tag=f'"core-{doc["version"]}"',
                    body=json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode(),
                    terms_tag=f'"terms-{doc["version"]}"',
                    terms=json.dumps({'version': doc['version'], 'terms': doc.get('terms', [])},
                                     ensure_ascii=False, separators=(',', ':')).encode())
    return _doc


def _send(request, body, tag):
    headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate', 'Vary': 'Cookie'}
    if request.headers.get('if-none-match') == tag: return Response(status_code=304, headers=headers)
    return Response(body, media_type='application/json', headers=headers)


@core.app.get('/api/reference/core-rules')
def core_rules(request: Request, u=Depends(core.user)):
    """The core rules document (ETag: unchanged -> 304)."""
    d = load()
    return _send(request, d['body'], d['tag'])


@core.app.get('/api/reference/terms')
def core_terms(request: Request, u=Depends(core.user)):
    """v1.13: the terms with tooltips and their definitions from the core rules (ETag: unchanged -> 304)."""
    d = load()
    return _send(request, d['terms'], d['terms_tag'])
