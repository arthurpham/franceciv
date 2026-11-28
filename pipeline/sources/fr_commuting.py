"""INSEE home-work commuting flows."""
import csv,zipfile
from ..core.source import Source,SourceInfo
URL='https://www.insee.fr/fr/statistiques/fichier/8582949/base-flux-mobilite-domicile-lieu-travail-2022_csv.zip'
def parent(c):
 return '75056' if c.startswith('751') else '13055' if c.startswith('132') else '69123' if c.startswith('6938') else c
class FrenchCommuting(Source):
 info=SourceInfo(id='fr_commuting',title='2022 home-work commuting flows',publisher='INSEE',homepage='https://www.insee.fr/fr/statistiques/8582949',license='Licence ouverte INSEE',description='Census commuting flows between residence and workplace communes, 2022, geography as of 1 January 2025. Small flows are survey magnitudes; Paris, Lyon and Marseille arrondissements are recombined here to their whole communes. France excluding Mayotte.',used_for=['Commuting balance and local employment lenses'])
 def fetch(self,force=False):self.download(URL,'flows.zip',force=force,expect_binary=True)
 def process(self):
  z=zipfile.ZipFile(self.raw_dir/'flows.zip');n=z.namelist()[0];out={}
  with z.open(n) as raw:
   import io
   for r in csv.DictReader(io.TextIOWrapper(raw,encoding='utf-8-sig'),delimiter=';'):
    try:v=float(r['NBFLUX_C22_ACTOCC15P'])
    except:continue
    home,work=parent(r['CODGEO']),parent(r['DCLT']);x=out.setdefault(home,{'out':0.0,'internal':0.0,'in':0.0})
    if home==work:x['internal']+=v
    else:
     x['out']+=v;out.setdefault(work,{'out':0.0,'internal':0.0,'in':0.0})['in']+=v
  if len(out)<30000:raise ValueError('unexpected commuting coverage')
  return {'_files':['flows.zip'],'rows':out}
