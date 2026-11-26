"""v1.7: team & operative reference — importer helpers, owner-only load, read-only API."""
import json,os
import pytest
from api import teamdata as td

KTD={'generated_at':'2026-08-26T00:00:00+00:00','datacards':[{'name':'KOMMANDO BOSS NOB','apl':3,'movement':'6″','save':'5+','wounds':14,'base_size':32,
  'weapons':[{'name':'Slugga','attacks':4,'hit':'4+','damage':'3/4','special_rules':'Range 8"'},{'name':'Power klaw2','attacks':4,'hit':'3+','damage':'5/7','special_rules':'Brutal'}],
  'passive_abilities':[{'name':'KRUMPIN’ TIME','description':'This operative can perform two Fight actions.'}],
  'unique_actions':[{'name':'GET IT DUN! (1AP)','description':'SUPPORT. Select one other friendly KOMMANDO operative.'}],
  'keywords':['KOMMANDO','ORK','LEADER','BOSS NOB']}],
  'strategy_ploys':[{'name':'dakka','text':'STRATEGY PLOY\nDAKKA! DAKKA! DAKKA!\nWhilst they are more subtle than other\nOrks, they love fire.\nFriendly KOMMANDO operatives’ ranged\nweapons have the Punishing weapon rule.'}],
  'firefight_ploys':[],'equipment':[],'faction_rules':[],
  'operatives_selection':[{'name':'Operatives','text':'ARCHETYPES: INFILTRATION, SEEK & DESTROY\nOPERATIVES\n↘ 1 KOMMANDO BOSS NOB operative\n↘ 9 KOMMANDO operatives selected from the following list:\n• BOMB SQUIG\n• BREACHA BOY'}]}
BS={'name':'Kommandos','revision':'9','comment':"July '25",'operatives':[{'name':'Kommando Boss Nob','stats':{'apl':'3','move':'6"','save':'5+','wounds':'15'},
  'weapons':[{'name':'Power klaw','type':'melee','atk':'4','hit':'3+','dmg':'5/7','wr':'Brutal'}],'abilities':[]}]}
EXTRA={'name':'Strike Force Variel','revision':'1','comment':'','operatives':[{'name':'Lieutenant Variel','stats':{'apl':'3','move':'6"','save':'3+','wounds':'15'},
  'weapons':[{'name':'Bolt pistol','type':'ranged','atk':'4','hit':'3+','dmg':'3/4','wr':'Range 8"'}],'abilities':[{'kind':'ability','name':'Leader','text':'x'}]}]}

def bundle():
    src={'repo':'x/y','commit':'a'*40}
    return td.build({'kommandos':KTD},{'Kommandos':BS,'Strike Force Variel':EXTRA},{'kommandos':{'kommando-boss-nob':'https://raw.githubusercontent.com/x/card.jpg'}},src,src,log=open(os.devnull,'w'))

def test_text_helpers():
    title,body=td.blocks(KTD['strategy_ploys'][0]['text'])
    assert title=='Dakka! Dakka! Dakka!'
    assert body==[{'k':'lore','t':'Whilst they are more subtle than other Orks, they love fire.'},
                  {'k':'p','t':'Friendly KOMMANDO operatives’ ranged weapons have the Punishing weapon rule.'}]
    assert td.clean_weapon('Power klaw2')=='Power klaw' and td.clean_weapon('Bolt pistol')=='Bolt pistol'
    assert td.guess_type('Chainsword','')=='melee' and td.guess_type('Odd thing','Range 6"')=='ranged' and td.guess_type('Odd thing','') is None
    assert td.norm('Fellgor Ravagers')==td.norm('fellgor-ravager') and td.slugify('Kommando Boss Nob')=='kommando-boss-nob'

def test_build_merges_sources_and_flags_conflicts():
    b=bundle();assert b['format']==td.FORMAT
    k=next(t for t in b['teams'] if t['slug']=='kommandos');d=k['data']
    assert k['name']=='Kommandos' and d['archetypes']==['Infiltration','Seek & Destroy']
    o=d['operatives'][0]
    assert o['name']=='Kommando Boss Nob' and o['stats']=={'apl':'3','move':'6"','save':'5+','wounds':'14'}
    assert o['conflicts']=={'wounds':'15'} and o['bsdata'] and o['base']==32
    assert [(w['name'],w['type']) for w in o['weapons']]==[('Slugga','ranged'),('Power klaw','melee')]
    assert o['card'].startswith('https://') and o['actions'][0]['name']=='GET IT DUN! (1AP)'
    assert [x['t'] for x in d['selection'][0]['body']][0].startswith('1 KOMMANDO BOSS NOB')
    assert k['sources']['bsdata']['revision']=='9' and k['sources']['kt_datacards']['path']=='output/kommandos/data/kommandos-team-data.json'
    v=next(t for t in b['teams'] if t['slug']=='strike-force-variel')
    assert v['data']['operatives'][0]['weapons'][0]['type']=='ranged' and not v['data']['strategy_ploys']
    assert any('stats differ' in w for w in b['warnings']) and any('only BSData' in w for w in b['warnings'])

def test_validate_and_sql_are_safe():
    for bad in [{},{'format':'other','teams':[]},{'format':td.FORMAT,'teams':[]},
                {'format':td.FORMAT,'teams':[{'slug':'Bad Slug','name':'x','data':{'operatives':[]}}]},
                {'format':td.FORMAT,'teams':[{'slug':'aa','name':'x','data':{'operatives':[]}}]*2}]:
        with pytest.raises(ValueError):td.validate(bad)
    b=bundle();b['teams'][0]['name']="O'Brien"; b['teams'][0]['data']['operatives'][0]['card']='javascript:alert(1)'
    sql=td.to_sql(b)
    assert "'O''Brien'" in sql and 'javascript:' not in sql and sql.count('INSERT INTO team_data(')==2
    assert td.catalog_pattern('fellgor-ravagers')=='-team-fellgors?-ravagers?$'

def test_owner_load_and_read_only_api(clients):
    url=os.getenv('TEST_DATABASE_URL')
    import psycopg
    from tests.test_integration import register
    a,b=clients
    assert a.get('/api/teams').status_code==401
    with psycopg.connect(url) as c:
        assert td.load(bundle(),c)=={'teams':2,'operatives':2,'linked_to_catalog':2}
    with psycopg.connect(os.environ['DATABASE_URL']) as c:  # runtime role cannot change the reference
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("UPDATE team_data SET active=false")
    register(a,'teams_reader')
    r=a.get('/api/teams').json()
    assert [t['slug'] for t in r['teams']]==['kommandos','strike-force-variel'] and r['import']['operatives']==2
    k=r['teams'][0];assert k['catalog_id'] and k['operatives']==1 and k['archetypes']==['Infiltration','Seek & Destroy']
    d=a.get('/api/teams/kommandos');assert d.status_code==200 and d.headers['etag']
    body=d.json();assert body['data']['operatives'][0]['conflicts']=={'wounds':'15'} and 'content_hash' not in body
    assert a.get('/api/teams/kommandos',headers={'If-None-Match':d.headers['etag']}).status_code==304
    assert a.get('/api/teams/unknown').json()['detail']=='team_not_found'
    with psycopg.connect(url) as c:  # a later import without a team hides it
        one=bundle();one['teams']=[t for t in one['teams'] if t['slug']=='kommandos'];td.load(one,c)
    assert [t['slug'] for t in a.get('/api/teams').json()['teams']]==['kommandos']
    assert a.get('/api/teams/strike-force-variel').status_code==404

def test_faction_rules_keep_every_option():
    """v1.8: rule options are part of the bundle (they were dropped by the v1.7 viewer and garbled by OCR splits)."""
    assert td.FORMAT == 'killstass-teams/2' and 'killstass-teams/1' in td.FORMATS
    assert td.split_option('Redeploy', '(1) Move each one. Reposition (2) Do it again.') == [('Redeploy (1)', 'Move each one.'), ('Reposition (2)', 'Do it again.')]
    assert td.is_fragment('This operative can perform the', 'x') and not td.is_fragment('Aggressive', 'When it fights...')
    assert td.bs_blocks('Text\n• one\n- two') == [{'k': 'p', 't': 'Text'}, {'k': 'li2', 't': 'one'}, {'k': 'li2', 't': 'two'}]
    items = [{'name': 'Chapter Tactics', 'body': [{'k': 'p', 't': 'Select two CHAPTER TACTICS:'}], '_raw': '', '_slug': 'chapter-tactics',
              'options': [{'name': 'AGGRESSIVE', 'text': 'Melee weapons have Rending.'}, {'name': 'and the other one for the', 'text': 'rest of the battle.'}]}]
    bs = {'rules': [{'name': 'Chapter Tactics', 'text': 'Select two:\n• one primary\n• one secondary'}],
          'option_lists': {'Chapter Tactics': [{'name': 'Aggressive', 'text': 'Melee weapons have **Rending**.'}, {'name': 'Hardy', 'text': 'Ignore wounds.'}]}}
    r = td.faction_rules([dict(i) for i in items], bs)[0]
    assert r['src'] == 'bsdata' and [b['k'] for b in r['body']] == ['p', 'li2', 'li2']  # lossy kt-datacards text replaced
    assert [(o['name'], o['src']) for o in r['options']] == [('Aggressive', 'bsdata'), ('Hardy', 'bsdata')]
    r = td.faction_rules([dict(items[0], options=[{'name': 'AGGRESSIVE', 'text': 'Melee weapons have Rending.'}])], {})[0]
    assert r['options'] == [{'name': 'Aggressive', 'body': [{'k': 'p', 't': 'Melee weapons have Rending.'}]}] and 'src' not in r
