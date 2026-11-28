"""Private-sector employment geography lenses."""
from collections import defaultdict
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim,write_web
from .connectivity import shape_weights
from .time_dimension import land_area_by_cell
REQUIRES=['_world','fr_boundaries','fr_private_employment'];PRODUCES=['private_employment.json'];RAMP=['#26313c','#3f5f68','#63846f','#a08f58','#d0a24b']
def lens(i,n,e,u,f,vals,d):return {'id':i,'group':'economy','name':n,'icon':i,'emoji':e,'unit':u,'format':f,'scale':'linear','domain':[0,max(v or 0 for v in vals)],'ramp':RAMP,'higher_is':'neutral','source':'fr_private_employment','description':d,'values':vals}
def build():
 w=load_interim('_world');b=load_interim('fr_boundaries');src=load_interim('fr_private_employment');g=HexGrid(**w['grid']);p=MapProjection(**w['projection']);weights=shape_weights(w,g,p,b['communes']);land=land_area_by_cell(w,g);acc=defaultdict(lambda:defaultdict(float))
 for code,r in src['rows'].items():
  if not r['measured']:continue
  for cell,wt in weights.get(code,{}).items():
   for k in ('establishments','jobs','industry_jobs','service_jobs'):acc[cell][k]+=r[k]*wt
 jd,ed,ind,serv=[],[],[],[]
 for i in range(g.size):
  if w['owner'][i]<0 or not land[i]:jd.append(None);ed.append(None);ind.append(None);serv.append(None);continue
  x=acc[i];jd.append(round(x['jobs']*100/land[i],2));ed.append(round(x['establishments']*100/land[i],2));ind.append(round(x['industry_jobs']/x['jobs'],4) if x['jobs'] else None);serv.append(round(x['service_jobs']/x['jobs'],4) if x['jobs'] else None)
 write_web('private_employment.json',{'version':1,'vintage':'URSSAF private-sector employment, 31 December 2025','sources':['fr_private_employment'],'group':{'id':'economy','name':'Economy'},'lenses':[lens('private_job_density','Private-sector jobs','💼','jobs / 100 km²','float',jd,'URSSAF private-sector salaried jobs at employer establishments per 100 km², general regime. Jobs are counted at workplace establishments, not residence.'),lens('private_establishment_density','Private employers','🏢','establishments / 100 km²','float',ed,'URSSAF private-sector employer establishments per 100 km². Blank source cells are suppressed or unavailable and are not treated as zero.'),lens('industrial_private_share','Industrial private jobs','🏭','share of private jobs','pct',ind,'Share of URSSAF private-sector salaried jobs in industry (GS1). This is workplace-industry composition, not all employment.'),lens('service_private_share','Service private jobs','🛎️','share of private jobs','pct',serv,'Share of URSSAF private-sector salaried jobs in other market and non-market services (GS5/GS7), excluding commerce, construction, hospitality and temporary-work categories.')]})
def check(web_dir):
 import json;d=json.loads((web_dir/'private_employment.json').read_text());assert len(d['lenses'])==4 and max(v or 0 for v in d['lenses'][0]['values'])>1000;return [('PASS','private_employment.json: four URSSAF lenses')]
