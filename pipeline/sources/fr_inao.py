"""INAO AOC/AOP geographic areas and products."""
import csv,re
from ..core.source import Source, SourceInfo
AREAS='https://static.data.gouv.fr/resources/aires-geographiques-des-aoc-aop/20251009-122320/2025-10-09-comagri-communes-aires-ao.csv'
PRODUCTS='https://static.data.gouv.fr/resources/aires-et-produits-aoc-aop-et-igp/20251009-122906/2025-03-10-comagri-aires-produits.csv'
WINE=re.compile(r'\b(blanc|rouge|ros[ée]|mousseux|p[ée]tillant|primeur|nouveau)\b',re.I)
CHEESE=re.compile(r'\b(comt[ée]|roquefort|camembert|brie|reblochon|munster|cantal|saint-nectaire|bleu|epoisses|[ée]poisses|morbier|tomme|beaufort|abondance|chaource|langres|pont-l.[ée]v[êe]que|livarot|neufch[âa]tel|fourme|ossau|banon|chavignol|valen[çc]ay|selles-sur-cher|crottin|picodon|p[ée]lardon|fromage)\b',re.I)
def rows(path):
 return list(csv.DictReader(open(path,encoding='cp1252',newline=''),delimiter=';'))
class FrenchInao(Source):
 info=SourceInfo(id='fr_inao',title='AOC/AOP geographic areas and products',publisher='Institut national de l\'origine et de la qualité (INAO)',homepage='https://www.data.gouv.fr/datasets/aires-geographiques-des-aoc-aop',license='Licence Ouverte / Open Licence',description='Official open-data commune lists for AOC/AOP geographic areas, joined with the INAO product reference table. Product families are derived conservatively from published product names: wine-style terms for wine and explicit/recognized cheese product names for cheese.',used_for=['Wine and cheese appellation lenses'])
 def fetch(self,force=False):self.download(AREAS,'communes-aires.csv',force=force);self.download(PRODUCTS,'aires-produits.csv',force=force)
 def process(self):
  prod=rows(self.raw_dir/'aires-produits.csv');families={}
  for r in prod:
   txt=(r.get('Produit') or '')+' '+(r.get('Aire geographique') or '');f=families.setdefault(r['IDA'],set())
   if WINE.search(txt):f.add('wine')
   if CHEESE.search(txt):f.add('cheese')
  communes={}
  for r in rows(self.raw_dir/'communes-aires.csv'):
   fs=families.get(r['IDA'],set())
   if not fs:continue
   c=communes.setdefault(r['CI'],{'wine':set(),'cheese':set()})
   for f in fs:c[f].add((r['IDA'],r['Aire géographique'].strip()))
  out={k:{f:sorted(x[1] for x in v[f]) for f in ('wine','cheese')} for k,v in communes.items()}
  if len(out)<5000 or sum(bool(v['wine']) for v in out.values())<2000:raise ValueError('unexpected INAO coverage')
  return {'_files':['communes-aires.csv','aires-produits.csv'],'rows':out}
