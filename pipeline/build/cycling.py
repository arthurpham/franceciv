"""Cycling-infrastructure lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES=["_world","fr_boundaries","fr_cycling"]
PRODUCES=["cycling.json"]
RAMP=["#263239","#376d63","#4f9d69","#8bc34a","#d8e86c"]

def percentile(vals,p):
 xs=sorted(v for v in vals if v is not None)
 return xs[min(len(xs)-1,max(0,round((p/100)*(len(xs)-1))))] if xs else None

def lens(lens_id,name,unit,vals,desc):
 positive=[v for v in vals if v]
 return {"id":lens_id,"group":"cycling","name":name,"icon":lens_id,"emoji":"🚲","unit":unit,"format":"float","scale":"log","domain":[percentile(positive,2),percentile(positive,98)],"ramp":RAMP,"higher_is":"better","source":"fr_cycling","description":desc,"values":vals}

def build():
 world=load_interim("_world");bounds=load_interim("fr_boundaries");cycling=load_interim("fr_cycling")
 grid=HexGrid(**world["grid"]);proj=MapProjection(**world["projection"])
 cell_by_code={};pop=defaultdict(int)
 for c in bounds["communes"]:
  if c.get("lon") is None:continue
  x,y=proj(c["lon"],c["lat"]);cell=nearest_land(world,grid,x,y)
  if cell>=0:cell_by_code[c["code"]]=cell;pop[cell]+=c.get("population") or 0
 acc=defaultdict(lambda:[0.0,0.0]);unmatched=0.0
 for code,row in cycling["rows"].items():
  cell=cell_by_code.get(code)
  if cell is None:unmatched+=row["network_km"];continue
  acc[cell][0]+=row["network_km"];acc[cell][1]+=row["protected_km"]
 network=[];protected=[]
 for i in range(grid.size):
  denom=pop.get(i,0);network.append(round(acc[i][0]*10000/denom,3) if denom else None);protected.append(round(acc[i][1]*10000/denom,3) if denom else None)
 write_web("cycling.json",{"version":1,"vintage":cycling.get("vintage","BNAC OpenStreetMap export"),"sources":["fr_cycling"],"group":{"id":"cycling","name":"Cycling"},"unmatched_network_km":round(unmatched,1),"lenses":[
  lens("cycling_network","Cycling network","km / 10k residents",network,"Explicit cycling-infrastructure kilometers per 10,000 residents. Segment lengths are attributed to current communes, split where a segment crosses a commune boundary, then population-weighted by map hex. OSM coverage completeness varies by territory."),
  lens("protected_cycling","Protected cycling","km / 10k residents",protected,"Physically protected or off-carriageway cycling-infrastructure kilometers per 10,000 residents: pistes cyclables, voies vertes, bus-bike corridors, mixed pedestrian/cycle facilities, protected shoulders and goulotte lanes. OSM coverage completeness varies.")],
 })

def check(web_dir):
 import json
 doc=json.loads((web_dir/"cycling.json").read_text());assert len(doc["lenses"])==2
 vals=[v for v in doc["lenses"][0]["values"] if v];prot=[v for v in doc["lenses"][1]["values"] if v]
 assert len(vals)>2000 and len(prot)>1000 and max(vals)>5
 return [("PASS",f"cycling.json: cycling lenses over {len(vals)} cells")]
