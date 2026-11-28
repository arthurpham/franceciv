"""URSSAF private-sector employer establishments and employment."""
import csv
from ..core.source import Source,SourceInfo
URL='https://open.urssaf.fr/api/explore/v2.1/catalog/datasets/etablissements-et-effectifs-salaries-au-niveau-commune-x-ape-last/exports/csv?use_labels=true'
def num(x):
 try:return float(x) if x not in (None,'') else None
 except:return None
class FrenchPrivateEmployment(Source):
 info=SourceInfo(id='fr_private_employment',title='Private-sector employer establishments and employment',publisher='Urssaf / ACOSS',homepage='https://www.data.gouv.fr/datasets/nombre-detablissements-employeurs-et-effectifs-salaries-du-secteur-prive-par-commune-x-ape-au-31-12-depuis-2006',license='Licence Ouverte / Open Licence',description='Private-sector employer establishments and salaried employment by commune and activity, at 31 December, general regime. Blank cells are suppressed or unavailable and are not treated as zeros. Apprentices are included from the June 2023 methodological change.',used_for=['Private employment, establishment and industry-mix lenses'])
 def fetch(self,force=False):self.download(URL,'urssaf-commune-ape.csv',force=force)
 def process(self):
  rows={};blank_jobs=blank_establishments=0
  with open(self.raw_dir/'urssaf-commune-ape.csv',encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f,delimiter=';'):
    code=r.get('Code commune');sec=r.get("Grand secteur d'activité") or ''
    if not code:continue
    e=num(r.get("Nombre d'établissements 2025"));j=num(r.get('Effectifs salariés 2025'))
    x=rows.setdefault(code,{'establishments':0.0,'jobs':0.0,'industry_jobs':0.0,'service_jobs':0.0,'measured':False})
    if e is not None:x['establishments']+=e;x['measured']=True
    else:blank_establishments+=1
    if j is not None:
     x['jobs']+=j;x['measured']=True
     if sec.startswith('GS1'):x['industry_jobs']+=j
     if sec.startswith(('GS5','GS7')):x['service_jobs']+=j
    else:blank_jobs+=1
  if len(rows)<25000 or sum(x['jobs'] for x in rows.values())<10_000_000:raise ValueError('unexpected URSSAF coverage')
  return {'_files':['urssaf-commune-ape.csv'],'rows':rows,'year':2025,'blank_job_rows':blank_jobs,'blank_establishment_rows':blank_establishments}
