"""Home-work commuting structure lenses."""
from collections import defaultdict
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim,write_web
from ..core.insets import transform_real_point
from .connectivity import shape_weights
REQUIRES=['_world','fr_boundaries','fr_commuting'];PRODUCES=['commuting.json','commute_flows.json'];RAMP=['#253044','#43597b','#687d94','#a99168','#d1a04a']
def lens(i,n,e,u,f,vals,d):return {'id':i,'group':'economy','name':n,'icon':i,'emoji':e,'unit':u,'format':f,'scale':'linear','domain':[0,max(v or 0 for v in vals)],'ramp':RAMP,'higher_is':'neutral','source':'fr_commuting','description':d,'values':vals}
def build():
 w=load_interim('_world');b=load_interim('fr_boundaries');flows=load_interim('fr_commuting');g=HexGrid(**w['grid']);p=MapProjection(**w['projection']);weights=shape_weights(w,g,p,b['communes']);acc=defaultdict(lambda:defaultdict(float))
 for code,r in flows['rows'].items():
  for cell,wt in weights.get(code,{}).items():
   for k in ('out','internal','in'):acc[cell][k]+=r[k]*wt
 outshare,balance,capture=[],[],[]
 for i in range(g.size):
  if w['owner'][i]<0:outshare.append(None);balance.append(None);capture.append(None);continue
  x=acc[i];resident=x['out']+x['internal'];jobs=x['in']+x['internal']
  outshare.append(round(x['out']/resident,4) if resident else None);balance.append(round(jobs/resident,3) if resident else None);capture.append(round(x['internal']/jobs,4) if jobs else None)
 flow_rows={code:[[[d,int(round(v))] for d,v in r.get('dests',[])],[[o,int(round(v))] for o,v in r.get('origins',[])]] for code,r in flows['rows'].items() if r.get('dests') or r.get('origins')}
 write_web('commute_flows.json',{'version':1,'vintage':'INSEE census commuting flows 2022, geography 2025','sources':['fr_commuting'],'communes':flow_rows,'note':'Top three residence-to-workplace destinations and workplace-to-residence origins per commune; small census flows are magnitudes.'})
 write_web('commuting.json',{'version':1,'vintage':'INSEE census commuting flows 2022, geography 2025','sources':['fr_commuting'],'group':{'id':'economy','name':'Economy'},'lenses':[lens('commute_out_share','Commuting out','🚗','share of resident workers','pct',outshare,'Share of employed residents whose workplace is outside their commune of residence. Arrondissements are recombined into Paris, Lyon and Marseille; small census flows are magnitudes.'),lens('commuting_balance','Workplace-job balance','⚖️','jobs per resident worker','float',balance,'Jobs located in the area divided by employed residents living there. Above 1 means a net workplace inflow; below 1 means residents commute out. This is a ratio, not a count of jobs.'),lens('local_employment_capture','Local employment capture','🏠','share of local jobs','pct',capture,'Share of workplace jobs held by people who also live in the same area. Low values indicate strong inbound commuting or large employment centres.')]})
def check(web_dir):
 import json;d=json.loads((web_dir/'commuting.json').read_text());assert len(d['lenses'])==3 and max(v or 0 for v in d['lenses'][1]['values'])>1;f=json.loads((web_dir/'commute_flows.json').read_text());assert len(f['communes'])>30000;return [('PASS','commuting.json: three commuting lenses and interactive top-flow extract')]
