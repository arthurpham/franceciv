"""ADEME housing energy-performance diagnostics, aggregated server-side."""

import json,time,urllib.parse,urllib.request
from collections import defaultdict
from ..core.source import Source, SourceInfo

BASE='https://data.ademe.fr/data-fair/api/v1/datasets/meg-83tjwtg8dyz4vv7h1dqe/values_agg'
DEPS=[*(f'{i:02d}' for i in range(1,20)),'2A','2B',*(f'{i:02d}' for i in range(21,96)),'971','972','973','974','976']

class FrenchHousingEnergy(Source):
 info=SourceInfo(id='fr_housing_energy',title='DPE Logements existants (depuis juillet 2021)',publisher='ADEME',homepage='https://www.data.gouv.fr/datasets/dpe-logements-existants-depuis-juillet-2021',license='Licence Ouverte 2.0',description='Energy-performance diagnostics for existing housing since July 2021. Commune distributions are aggregated server-side from DPE A-G labels. DPEs are triggered mainly by sales, rentals and construction work, so they are a biased sample of the total housing stock rather than a census.',used_for=['Housing energy-performance lenses'])
 def fetch(self,force=False):
  self.raw_dir.mkdir(parents=True,exist_ok=True)
  for dep in DEPS:
   path=self.raw_dir/f'dpe_{dep}.json'
   if path.exists() and not force:continue
   q={'field':'code_insee_ban;etiquette_dpe','agg_size':'700;10','size':'1','select':'numero_dpe','qs':f'code_departement_ban:{dep}'}
   url=BASE+'?'+urllib.parse.urlencode(q)
   for attempt in range(5):
    try:self.download(url,path.name,force=force);break
    except Exception:
     if attempt==4:raise
     time.sleep(10*(attempt+1))
   time.sleep(.4)
 def process(self):
  rows=defaultdict(lambda:defaultdict(int));total=0
  for dep in DEPS:
   p=self.raw_dir/f'dpe_{dep}.json'
   if not p.exists():continue
   for outer in json.loads(p.read_text()).get('aggs',[]):
    code=str(outer.get('value','')).zfill(5)
    for inner in outer.get('aggs',[]):
     label=inner.get('value');n=inner.get('total') or 0
     if label in 'ABCDEFG':rows[code][label]+=n;total+=n
  out={c:dict(v) for c,v in rows.items()}
  print(f'    {total} DPE records in {len(out)} communes')
  if len(out)<20000 or total<10_000_000:raise ValueError('unexpected DPE coverage')
  return {'vintage':'ADEME DPE existing housing since July 2021','_files':[f'dpe_{d}.json' for d in DEPS],'rows':out,'total_records':total}
