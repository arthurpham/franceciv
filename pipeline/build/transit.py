"""Public-transport stop availability lens."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES=["_world","fr_boundaries","fr_transit_stops"]
PRODUCES=["transit.json"]
RAMP=["#27343f","#37657b","#4a8f9b","#62b586","#d7d765"]

def percentile(vals,p):
 xs=sorted(v for v in vals if v is not None)
 return xs[min(len(xs)-1,max(0,round((p/100)*(len(xs)-1))))] if xs else None

def build():
 world=load_interim("_world");bounds=load_interim("fr_boundaries");stops=load_interim("fr_transit_stops")
 grid=HexGrid(**world["grid"]);proj=MapProjection(**world["projection"])
 pop=defaultdict(int);counts=defaultdict(int);out_of_map=0
 for c in bounds["communes"]:
  if c.get("lon") is None:continue
  x,y=proj(c["lon"],c["lat"]);cell=nearest_land(world,grid,x,y)
  if cell>=0:pop[cell]+=c.get("population") or 0
 for row in stops["rows"]:
  x,y=proj(*transform_real_point(row["lon"],row["lat"]));cell=nearest_land(world,grid,x,y)
  if cell<0:out_of_map+=1;continue
  counts[cell]+=1
 vals=[]
 for i in range(grid.size):vals.append(round(counts[i]*10000/pop[i],2) if pop.get(i) else None)
 positive=[v for v in vals if v]
 write_web("transit.json",{"version":1,"vintage":stops.get("vintage","transport.data.gouv.fr GTFS stop extraction"),"sources":["fr_transit_stops"],"group":{"id":"public_transport","name":"Public transport"},"out_of_map_stops":out_of_map,"lenses":[{"id":"transit_stops","group":"public_transport","name":"Transit stops","icon":"transit_stops","emoji":"🚏","unit":"stops / 10k residents","format":"float","scale":"log","domain":[percentile(positive,2),percentile(positive,98)],"ramp":RAMP,"higher_is":"better","source":"fr_transit_stops","description":"Deduplicated public-transport stop points per 10,000 residents. Stops appearing in overlapping GTFS feeds are deduplicated by normalized name and approximately 100-metre rounded coordinates. Stop presence does not measure service frequency, span, speed or reliability, and catalog coverage can vary.","values":vals}]})

def check(web_dir):
 import json
 doc=json.loads((web_dir/"transit.json").read_text());vals=[v for v in doc["lenses"][0]["values"] if v]
 assert len(vals)>2500 and max(vals)>5 and doc["out_of_map_stops"]<20000
 return [("PASS",f"transit.json: transit-stop lens over {len(vals)} cells")]
