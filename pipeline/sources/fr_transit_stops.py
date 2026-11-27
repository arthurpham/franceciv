"""National public-transport stop export."""

import csv,sys,unicodedata
from collections import defaultdict

from ..core.source import Source, SourceInfo

URL='https://transport.data.gouv.fr/resources/81333/download'
FILE='gtfs_stops_france.csv'

def norm(s):
 return ' '.join(unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower().split())

class FrenchTransitStops(Source):
 info=SourceInfo(id='fr_transit_stops',title='Arrêts de transport en France',publisher='Point d’Accès National transport.data.gouv.fr',homepage='https://transport.data.gouv.fr/datasets/arrets-de-transport-en-france',license='ODbL 1.0',description='Experimental national extraction of stop points present in GTFS feeds catalogued by transport.data.gouv.fr. Rows are deduplicated by normalized stop name and approximately 100-metre rounded coordinates because the same stop can appear in several overlapping feeds. Stop presence does not measure service frequency, operating days, speed or reliability.',used_for=['Public-transport stop availability lens'])
 def fetch(self,force=False):self.download(URL,FILE,force=force)
 def process(self):
  csv.field_size_limit(sys.maxsize);seen={};rows=0;bad=0
  with open(self.raw_dir/FILE,encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    rows+=1
    if (r.get('location_type') or '0') not in {'0',''}:continue
    try:lat=float(r['stop_lat']);lon=float(r['stop_lon'])
    except (TypeError,ValueError):bad+=1;continue
    if not (-90<=lat<=90 and -180<=lon<=180):bad+=1;continue
    key=(norm(r.get('stop_name')),round(lat,3),round(lon,3))
    rec=seen.setdefault(key,{'lat':lat,'lon':lon,'name':r.get('stop_name') or '', 'datasets':set()})
    rec['datasets'].add(r.get('dataset_id') or '')
  out=[{'lat':v['lat'],'lon':v['lon'],'name':v['name'],'datasets':len(v['datasets'])} for v in seen.values()]
  print(f'    {rows} GTFS stop rows; {len(out)} deduplicated stops; {bad} invalid coordinates')
  if len(out)<100000:raise ValueError('unexpectedly few transit stops')
  return {'vintage':'transport.data.gouv.fr GTFS stop extraction, current resource snapshot','_files':[FILE],'rows':out,'raw_rows':rows}
