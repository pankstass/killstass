"""v1.6: Russian and English dictionaries stay in sync with the code and the catalog."""
import json,os,re,pathlib
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
WEB=ROOT/'web'
def load(n): return json.loads((WEB/'i18n'/f'{n}.json').read_text(encoding='utf-8'))

def test_same_keys_in_ru_and_en():
    ru,en=load('ru'),load('en')
    assert set(ru)==set(en)
    assert set(ru['errors'])==set(en['errors'])
    assert 'appVersion' not in ru  # v1.9: the version comes from VERSION via <meta name="killstass-version">
    for k,v in en.items():
        if k!='errors': assert isinstance(v,str) and v.strip(),k
    cyr=re.compile('[а-яё]',re.I)
    leaked=[k for k,v in {**en,**en['errors']}.items() if isinstance(v,str) and cyr.search(v) and k!='langToggleLabel']
    assert not leaked,leaked

def test_literal_keys_used_in_js_exist():
    ru=load('ru')
    used=set()
    for f in WEB.glob('*.js'): used|=set(re.findall(r'\bt\("([A-Za-z0-9_]+)"\)',f.read_text(encoding='utf-8')))
    assert not sorted(used-set(ru))

def test_every_api_error_code_is_translated():
    codes=set()
    for f in (ROOT/'api').glob('*.py'): codes|=set(re.findall(r"fail\(\d+,\s*'([a-z_]+)'",f.read_text(encoding='utf-8')))
    for n in ('ru','en'):
        missing=codes-set(load(n)['errors'])
        assert not missing,(n,sorted(missing))

def test_english_catalog_covers_active_codes():
    url=os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('needs TEST_DATABASE_URL')
    import psycopg
    ce=json.loads((WEB/'i18n'/'catalog.en.json').read_text(encoding='utf-8'))
    with psycopg.connect(url) as c:
        cat={r[0] for r in c.execute('SELECT code FROM catalogs WHERE active')}
        seq={r[0] for r in c.execute('SELECT code FROM game_sequence WHERE active')}
    assert not sorted(cat-set(ce['catalog'])) and not sorted(seq-set(ce['sequence']))
    for row in ce['sequence'].values(): assert {'phase','label','description'}<=set(row)
