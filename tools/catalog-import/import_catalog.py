#!/usr/bin/env python3
"""Python 3.12+, stdlib only. Reviewed facts -> deterministic JSON and SQL.
No credentials, database access, JS execution or undocumented API calls.
"""
import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

UA = 'killstass-catalog-import/1.1 (personal LAN journal; public pages; 5s cache)'
KINDS = {'team','mission','objective','killzone','source','pack','archetype','tac_op','rule'}
HOSTS = {'battlekit.killteam.ru', 'wahapedia.ru'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fetch(url, cache):
    """One explicitly requested public page. Redirects remain on permitted HTTPS hosts."""
    def allowed(value):
        p = urllib.parse.urlsplit(value)
        if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password:
            raise ValueError('Only public HTTPS source hosts are allowed')
    allowed(url)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    page = cache / (key + '.html')
    if page.exists():
        return page
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            allowed(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(Redirect())
    def read(address):
        time.sleep(5)
        request = urllib.request.Request(address, headers={'User-Agent': UA, 'Accept-Language':'en,ru;q=0.7'})
        with opener.open(request, timeout=30) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000: raise ValueError('Page exceeds 4 MB')
            return raw
    host = urllib.parse.urlsplit(url).hostname
    robots = cache / (host + '-robots.txt')
    if not robots.exists():
        try: robots.write_bytes(read('https://' + host + '/robots.txt'))
        except urllib.error.HTTPError as e:
            if e.code != 404: raise
            robots.write_text('# HTTP 404: no robots policy found; check site terms manually\n')
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots.read_text().splitlines())
    if not rp.can_fetch(UA, url): raise ValueError('robots.txt disallows this URL')
    raw = read(url)
    page.write_bytes(raw)
    page.with_suffix('.meta.json').write_text(json.dumps({
        'source_url':url, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'content_hash':hashlib.sha256(raw).hexdigest()}, indent=2))
    return page


def validate(record, sequence=False):
    code = record['code']
    if not re.fullmatch(r'(2021|2024)-(battlekit|wahapedia|local)-[a-z0-9-]+', code):
        raise ValueError('Unstable or invalid code: ' + code)
    if record['edition'] not in ('2021','2024'): raise ValueError('edition')
    if not sequence and record['kind'] not in KINDS: raise ValueError('kind')
    if record.get('active') and record.get('verification') not in ('verified','local'):
        raise ValueError('Unverified/conflicting records cannot be active: ' + code)
    if record.get('verification') == 'local':
        if record.get('kind') != 'source' or not record['config'].get('recorded_total'):
            raise ValueError('Local source is only for already recorded final totals')
        return
    for key in ('source','source_url','retrieved_at','rules_version','content_hash'):
        if not record.get(key): raise ValueError('Missing provenance ' + key + ': ' + code)
    if record['source'] not in ('battlekit','wahapedia'): raise ValueError('source')
    url = urllib.parse.urlsplit(record['source_url'])
    if url.scheme != 'https' or url.hostname not in HOSTS: raise ValueError('source_url')
    if not re.fullmatch('[a-f0-9]{64}', record['content_hash']): raise ValueError('content_hash')
    if datetime.fromisoformat(record['retrieved_at'].replace('Z','+00:00')).tzinfo is None: raise ValueError('UTC offset required')
    if sequence:
        if record['phase_order'] < 0 or record['step_order'] < 0: raise ValueError('sequence order')
    elif record['kind'] == 'team' and record['active'] and not record['config'].get('archetypes'):
        raise ValueError('Active team must have verified archetypes')
    if not sequence and record['active'] and record['config'].get('pack')=='approved2025':
        cfg=record['config']
        if record['kind'] in ('mission','tac_op'):
            caps=cfg.get('per_turn_caps',[])
            if len(caps)!=4 or any(type(n) is not int or not 0<=n<=6 for n in caps) or cfg.get('max_per_battle')!=6:raise ValueError('Verified four-turn caps and battle cap required')
        if record['kind']=='tac_op' and (cfg.get('archetype') not in ('Infiltration','Recon','Security','Seek & Destroy') or not cfg.get('reveal')):raise ValueError('Tac Op archetype/reveal required')
        if record['kind']=='source' and cfg.get('component') not in ('crit','tac'):raise ValueError('Kill Op is derived, not a manual VP source')



def quote(value):
    return "'" + canonical(value).replace("'", "''") + "'::jsonb"


def sql_for(data, complete_scopes=()):
    records, steps = data['catalogs'], data['game_sequence']
    sql = ["-- Generated by tools/catalog-import; review before applying; execute in a transaction.",
           "UPDATE catalogs SET active=false WHERE coalesce((config->>'demo')::boolean,false) OR (verification='legacy' AND code IN ('2024-vp-critical','2024-vp-tactical','2024-vp-kill','2024-vp-manual','2021-vp-critical','2021-vp-tactical','2021-vp-manual'));"]
    if records:
        sql.append('''INSERT INTO catalogs(code,kind,edition,label,label_en,config,active,source,source_url,retrieved_at,rules_version,content_hash,verification)
SELECT x->>'code',x->>'kind',x->>'edition',x->>'label',coalesce(x->>'label_en',''),x->'config',(x->>'active')::boolean,
x->>'source',x->>'source_url',(x->>'retrieved_at')::timestamptz,x->>'rules_version',x->>'content_hash',x->>'verification'
FROM jsonb_array_elements(''' + quote(records) + ''') x
ON CONFLICT(code) DO UPDATE SET label=excluded.label,label_en=excluded.label_en,config=excluded.config,active=excluded.active,
source=excluded.source,source_url=excluded.source_url,retrieved_at=excluded.retrieved_at,rules_version=excluded.rules_version,content_hash=excluded.content_hash,verification=excluded.verification;''')
    if steps:
        sql.append("UPDATE game_sequence SET active=false WHERE code IN (SELECT jsonb_array_elements_text("+quote([r['code'] for r in steps])+"));")
        for scope in complete_scopes:
            parts=scope.split(':')
            if len(parts)==4 and parts[2]=='sequence' and parts[0] in ('battlekit','wahapedia') and parts[1] in ('2021','2024') and parts[3]=='approved2025':
                sql.append("UPDATE game_sequence SET active=false WHERE source='"+parts[0]+"' AND edition='"+parts[1]+"';")
        sql.append('''INSERT INTO game_sequence(code,edition,phase,phase_order,step_order,label,description,source,source_url,retrieved_at,rules_version,content_hash,verification,active)
SELECT x->>'code',x->>'edition',x->>'phase',(x->>'phase_order')::int,(x->>'step_order')::int,x->>'label',x->>'description',
x->>'source',x->>'source_url',(x->>'retrieved_at')::timestamptz,x->>'rules_version',x->>'content_hash',x->>'verification',(x->>'active')::boolean
FROM jsonb_array_elements(''' + quote(steps) + ''') x
ON CONFLICT(code) DO UPDATE SET phase=excluded.phase,phase_order=excluded.phase_order,step_order=excluded.step_order,
label=excluded.label,description=excluded.description,source=excluded.source,source_url=excluded.source_url,retrieved_at=excluded.retrieved_at,
rules_version=excluded.rules_version,content_hash=excluded.content_hash,verification=excluded.verification,active=excluded.active;''')
    # Explicit completeness prevents accidental retirement after a partial/offline export.
    for scope in complete_scopes:
        source, edition, kind, pack = scope.split(':')
        if kind=='sequence':
            if source not in ('battlekit','wahapedia') or edition not in ('2021','2024') or pack!='approved2025':raise ValueError('Invalid sequence scope')
            present=[r['code'] for r in steps if r['source']==source and r['edition']==edition]
            if not present:raise ValueError('Refusing empty complete sequence scope')
            sql.append("UPDATE game_sequence SET active=false WHERE source='"+source+"' AND edition='"+edition+"' AND code NOT IN (SELECT jsonb_array_elements_text("+quote(present)+"));")
            continue
        if source not in ('battlekit','wahapedia') or edition not in ('2021','2024') or kind not in KINDS:
            raise ValueError('Invalid complete scope')
        present = [r['code'] for r in records if (r.get('source'),r['edition'],r['kind'],r['config'].get('pack','')) == (source,edition,kind,pack)]
        if not present: raise ValueError('Refusing empty complete scope')
        sql.append("UPDATE catalogs SET active=false WHERE source=" + "'"+source+"' AND edition='"+edition+"' AND kind='"+kind+"' AND coalesce(config->>'pack','')=" + "'"+pack.replace("'","''")+"' AND code NOT IN (SELECT jsonb_array_elements_text("+quote(present)+"));")
    # v1.11: the reference search (db/migrations/013_v111.sql) indexes the catalog; skipped on databases before 013.
    sql.append("DO $$BEGIN IF to_regclass('public.reference_search') IS NOT NULL THEN REFRESH MATERIALIZED VIEW reference_search; END IF; END$$;")
    return '\n\n'.join(sql) + '\n'


def build(data, baseline=None, complete_scopes=()):
    if set(data) != {'catalogs','game_sequence'}: raise ValueError('Expected catalogs and game_sequence')
    for records, sequence in ((data['catalogs'],False),(data['game_sequence'],True)):
        seen = set()
        for r in records:
            validate(r, sequence)
            if r['code'] in seen: raise ValueError('Duplicate code: '+r['code'])
            seen.add(r['code'])
    orders = [(s['edition'],s['phase_order'],s['step_order']) for s in data['game_sequence']]
    if len(orders) != len(set(orders)): raise ValueError('Duplicate step order')
    old = {r['code']:r for r in (baseline or {}).get('catalogs',[])}
    report = {'added':0,'changed':0,'unchanged':0,'deactivated':[], 'unverified':[], 'conflicts':[], 'sources':[]}
    for r in data['catalogs']:
        state = 'added' if r['code'] not in old else 'unchanged' if canonical(r)==canonical(old[r['code']]) else 'changed'
        if r['code'] in old and (r['kind'],r['edition'])!=(old[r['code']]['kind'],old[r['code']]['edition']):raise ValueError('Cannot change kind/edition of an existing code')
        report[state] += 1
        if r['verification'] in ('unverified','conflict'): report['conflicts' if r['verification']=='conflict' else 'unverified'].append(r['code'])
    incoming = {r['code']:r for r in data['catalogs']}
    for r in old.values():
        in_scope = ':'.join((str(r.get('source')),r['edition'],r['kind'],r.get('config',{}).get('pack',''))) in complete_scopes
        if r.get('active',True) and (r.get('config',{}).get('demo') or (r['code'] in incoming and not incoming[r['code']]['active']) or (in_scope and r['code'] not in incoming)):
            report['deactivated'].append(r['code'])
    report['sources'] = sorted({r['source_url'] for r in data['catalogs']+data['game_sequence'] if r.get('source_url')})
    report['steps'] = len(data['game_sequence'])
    step_map={r['code']:r for r in data['game_sequence']}
    report['deactivated_steps']=[r['code'] for r in (baseline or {}).get('game_sequence',[]) if r.get('active') and ((r['code'] in step_map and not step_map[r['code']]['active']) or (r['code'] not in step_map and ':'.join((r['source'],r['edition'],'sequence','approved2025')) in complete_scopes))]
    return sql_for(data,complete_scopes),report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--output',type=Path,default=Path('catalog-output'))
    p.add_argument('--migration',default='005_catalog_update.sql')
    p.add_argument('--complete-scope',action='append',default=[],help='source:edition:kind:pack; only after complete review')
    p.add_argument('--dry-run',action='store_true');p.add_argument('--fetch-url');p.add_argument('--cache',type=Path,default=Path('catalog-cache'))
    a=p.parse_args()
    if a.fetch_url:
        if a.dry_run: raise ValueError('--dry-run never writes/downloads')
        print(fetch(a.fetch_url,a.cache));return
    if not a.input: p.error('--input is required')
    data=json.loads(a.input.read_text());baseline=json.loads(a.baseline.read_text()) if a.baseline else None
    if isinstance(baseline,list): baseline={'catalogs':baseline,'game_sequence':[]}
    sql,report=build(data,baseline,a.complete_scope)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not a.dry_run:
        if not re.fullmatch(r'\d{3}_[a-z0-9_]+\.sql',a.migration): raise ValueError('Invalid migration basename')
        a.output.mkdir(parents=True,exist_ok=True)
        (a.output/'seed.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        (a.output/a.migration).write_text(sql)
        (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': main()
