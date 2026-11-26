#!/usr/bin/env python3
"""Saved public HTML -> INACTIVE review candidates; never executes page scripts.
Supported adapters: Wahapedia Approved Ops embedded public card arrays and team page.
Use the page's actual save/download time, not the current date for old saved pages.
"""
import argparse, ast, hashlib, json, re
from html.parser import HTMLParser
from pathlib import Path

class Text(HTMLParser):
    def __init__(self): super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        elif tag in ('br','div','p','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def text(raw):
    x=Text();x.feed(raw);return re.sub(r'[ \t]+',' ',' '.join(x.parts)).strip()

def extract(raw,meta,adapter):
    records=[]
    if adapter=='approved':
        for variable,kind in [('ContentMission','mission'),('ContentAllTacOps','tac_op')]:
            m=re.search(r'var\s+'+variable+r'\s*=\s*(\[.*?\])\s*(?:;|\n)',raw,re.S)
            if not m:raise ValueError('Public card array missing; export rendered tab manually; do not call private APIs')
            cards=ast.literal_eval(m.group(1))
            if not isinstance(cards,list) or not all(isinstance(c,str) for c in cards):raise ValueError('Not a literal card list')
            for card in cards:
                title=re.search(r'<h3[^>]*>(.*?)</h3>',card,re.S)
                if not title:raise ValueError('Card heading missing')
                label=text(title.group(1));slug=re.sub('[^a-z0-9]+','-',re.sub(r'^\d+\.\s*','',label).lower()).strip('-')
                records.append(dict(code='2024-wahapedia-'+kind.replace('_','-')+'-'+slug,kind=kind,edition='2024',label='Не проверено: '+label,label_en=label,config={'pack':'approved2025','review_excerpt':text(card),'needs_review':['Русский пересказ','Лимиты VP и моменты начисления','Сверка версии']},active=False,verification='unverified',**meta))
    else:
        body=text(raw);m=re.search(r'Archetype:\s*(.*?)\s+(?:Angel of Death Kill Team|[A-Za-z ]+ Kill Team Below)',body)
        records.append(dict(code='2024-wahapedia-team-'+meta['source_url'].rstrip('/').split('/')[-1],kind='team',edition='2024',label='Не проверено',label_en='',config={'pack':'approved2025','review_excerpt':body[max(0,body.find('Archetype:')-40):body.find('Archetype:')+200],'needs_review':['Название RU/EN','Архетипы','Сопоставление BattleKit']},active=False,verification='unverified',**meta))
    return {'catalogs':records,'game_sequence':[]}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('html',type=Path);p.add_argument('--url',required=True);p.add_argument('--retrieved-at',required=True);p.add_argument('--version',required=True);p.add_argument('--adapter',choices=['approved','team'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raw=a.html.read_bytes();meta=dict(source='wahapedia',source_url=a.url,retrieved_at=a.retrieved_at,rules_version=a.version,content_hash=hashlib.sha256(raw).hexdigest())
    a.output.write_text(json.dumps(extract(raw.decode('utf-8-sig'),meta,a.adapter),ensure_ascii=False,indent=2)+'\n')
