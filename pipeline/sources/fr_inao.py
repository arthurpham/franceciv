"""INAO AOC/AOP geographic areas and products."""
import csv
from ..core.source import Source, SourceInfo
AREAS='https://static.data.gouv.fr/resources/aires-geographiques-des-aoc-aop/20251009-122320/2025-10-09-comagri-communes-aires-ao.csv'
PRODUCTS='https://static.data.gouv.fr/resources/aires-et-produits-aoc-aop-et-igp/20251009-122906/2025-03-10-comagri-aires-produits.csv'
REFERENCE='https://static.data.gouv.fr/resources/referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo/20251231-153733/2025-12-31-inao-ref-produit-siqo.csv'
def rows(path):
 return list(csv.DictReader(open(path,encoding='cp1252',newline=''),delimiter=';'))
class FrenchInao(Source):
 info=SourceInfo(id='fr_inao',title='AOC/AOP geographic areas and products',publisher='Institut national de l\'origine et de la qualité (INAO)',homepage='https://www.data.gouv.fr/datasets/aires-geographiques-des-aoc-aop',license='Licence Ouverte / Open Licence',description='Official open-data commune lists for AOC/AOP geographic areas, joined with the INAO product reference table. Product families use the official INAO reference table classifications: classe_ue Vins for wine and Fromages for cheese.',used_for=['Wine and cheese appellation lenses'])
 def fetch(self,force=False):self.download(AREAS,'communes-aires.csv',force=force);self.download(PRODUCTS,'aires-produits.csv',force=force);self.download(REFERENCE,'referentiel-produits.csv',force=force)
 def process(self):
  # The geographic-area product table has stable product ids but no family field. Join those
  # ids to the official SIQO reference, whose `classe_ue` is the authoritative family.
  with open(self.raw_dir/'referentiel-produits.csv',encoding='utf-8-sig',newline='') as f:
   reference={r['idproduit']:r.get('classe_ue','') for r in csv.DictReader(f)}
  prod=rows(self.raw_dir/'aires-produits.csv');families={};unclassified=set()
  for r in prod:
   cls=reference.get((r.get('IdProduit') or '').strip(),'');f=families.setdefault(r['IDA'],set())
   if cls=='Vins':f.add('wine')
   elif cls=='Fromages':f.add('cheese')
   elif not cls:unclassified.add(r.get('IdProduit'))
  communes={}
  for r in rows(self.raw_dir/'communes-aires.csv'):
   fs=families.get(r['IDA'],set())
   if not fs:continue
   c=communes.setdefault(r['CI'],{'wine':set(),'cheese':set()})
   for f in fs:c[f].add((r['IDA'],r['Aire géographique'].strip()))
  out={k:{f:sorted(x[1] for x in v[f]) for f in ('wine','cheese')} for k,v in communes.items()}
  if len(out)<5000 or sum(bool(v['wine']) for v in out.values())<2000:raise ValueError('unexpected INAO coverage')
  return {'_files':['communes-aires.csv','aires-produits.csv','referentiel-produits.csv'],'rows':out,'unclassified_product_ids':len(unclassified)}
