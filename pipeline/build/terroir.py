"""Protected wine and cheese appellation lenses."""
from collections import defaultdict
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim,write_web
from .connectivity import nearest_land
REQUIRES=['_world','fr_boundaries','fr_inao'];PRODUCES=['terroir.json']
RAMP=['#2f241f','#5d3935','#8c4f48','#bd7553','#e3ad63']
def lens(i,n,e,vals,d):return {'id':i,'group':'agriculture','name':n,'icon':i,'emoji':e,'unit':'appellations','format':'int','scale':'linear','domain':[0,max([v or 0 for v in vals] or [1])],'ramp':RAMP,'higher_is':'neutral','source':'fr_inao','description':d,'values':vals}
def build():
 w=load_interim('_world');b=load_interim('fr_boundaries');inao=load_interim('fr_inao');g=HexGrid(**w['grid']);p=MapProjection(**w['projection']);acc=defaultdict(lambda:{'wine':set(),'cheese':set()});miss=[]
 for c in b['communes']:
  r=inao['rows'].get(c['code'])
  if not r or c.get('lon') is None:continue
  x,y=p(*transform_real_point(c['lon'],c['lat']));cell=nearest_land(w,g,x,y)
  if cell<0:miss.append(c['code']);continue
  acc[cell]['wine'].update(r['wine']);acc[cell]['cheese'].update(r['cheese'])
 vals=[]
 for f in ('wine','cheese'):vals.append([len(acc[i][f]) if w['owner'][i]>=0 else None for i in range(g.size)])
 write_web('terroir.json',{'version':1,'vintage':'INAO AOC/AOP areas and products, October 2025','sources':['fr_inao'],'group':{'id':'agriculture','name':'Agriculture'},'unmatched_communes':len(miss),'lenses':[lens('wine_appellations','Wine appellations','🍷',vals[0],'Distinct INAO AOC/AOP wine appellations covering communes in each hex. Counts measure legal appellation richness, not vineyard area or production volume.'),lens('cheese_appellations','Cheese appellations','🧀',vals[1],'Distinct INAO AOC/AOP cheese appellations covering communes in each hex, identified from official product names. Counts measure legal appellation richness, not dairy production volume.')]})
def check(web_dir):
 import json;d=json.loads((web_dir/'terroir.json').read_text());assert len(d['lenses'])==2 and max(v or 0 for v in d['lenses'][0]['values'])>=3;return [('PASS',f"terroir.json: {sum(bool(v) for v in d['lenses'][0]['values'])} wine cells")]
