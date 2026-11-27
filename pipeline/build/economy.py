"""Commune workplace-employment composition lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES=["_world","fr_boundaries","fr_insee_stats"]
PRODUCES=["economy.json"]
RAMP=["#342b3f","#59518a","#527fac","#5cab8d","#e2c95f"]
SETS={
 "manufacturing_jobs":("Manufacturing jobs","🏭",[*(f'C{x}' for x in 'ABCDEFGHIJKLM')],"Manufacturing workplace employment as a share of all workplace jobs. Commune census counts are summed within each map hex before calculating the share."),
 "construction_jobs":("Construction jobs","🏗️",["FZ"],"Construction workplace employment as a share of all workplace jobs. Commune census counts are summed within each map hex before calculating the share."),
 "knowledge_jobs":("Knowledge services","🧠",["JA","JB","JC","KZ","MA","MB","MC"],"Information, communication, financial, insurance, professional, scientific and technical workplace employment as a share of all workplace jobs."),
 "public_care_jobs":("Public and care jobs","🏥",["OZ","PZ","QA","QB"],"Public administration, education, health and social-work workplace employment as a share of all workplace jobs."),
 "consumer_service_jobs":("Consumer services","🛎️",["GZ","HZ","IZ","RZ","SZ"],"Retail/wholesale, transport, accommodation, food, arts, entertainment and other consumer-service workplace employment as a share of all workplace jobs."),
}

def percentile(vals,p):
 xs=sorted(v for v in vals if v is not None)
 return xs[min(len(xs)-1,max(0,round((p/100)*(len(xs)-1))))] if xs else None

def build():
 world=load_interim("_world");bounds=load_interim("fr_boundaries");stats=load_interim("fr_insee_stats")
 employment=stats["datasets"]["employment"]["COM"]
 grid=HexGrid(**world["grid"]);proj=MapProjection(**world["projection"])
 acc=defaultdict(lambda:defaultdict(float));unmatched=0
 for c in bounds["communes"]:
  row=employment.get(c["code"])
  if not row or c.get("lon") is None:continue
  x,y=proj(c["lon"],c["lat"]);cell=nearest_land(world,grid,x,y)
  if cell<0:unmatched+=1;continue
  acc[cell]["total"]+=row.get("_T") or 0
  for _,_,codes,_ in SETS.values():
   for code in codes:acc[cell][code]+=row.get(code) or 0
 lenses=[]
 for lid,(name,emoji,codes,desc) in SETS.items():
  vals=[]
  for i in range(grid.size):
   total=acc[i]["total"];num=sum(acc[i][code] for code in codes)
   vals.append(round(num/total,4) if total else None)
  lenses.append({"id":lid,"group":"economy","name":name,"icon":lid,"emoji":emoji,"unit":"share of workplace jobs","format":"pct","scale":"linear","domain":[percentile(vals,2),percentile(vals,98)],"ramp":RAMP,"higher_is":"neutral","source":"fr_insee_stats","description":desc+" Workplace location is not worker residence; commuter-fed centres naturally have higher shares.","values":vals})
 write_web("economy.json",{"version":1,"vintage":f"INSEE census {stats['year']} workplace employment","sources":["fr_insee_stats"],"group":{"id":"economy","name":"Economy"},"unmatched_communes":unmatched,"lenses":lenses})

def check(web_dir):
 import json
 doc=json.loads((web_dir/"economy.json").read_text());assert len(doc["lenses"])==5
 for l in doc["lenses"]:
  vals=[v for v in l["values"] if v is not None];assert len(vals)>2500 and all(0<=v<=1 for v in vals)
 return [("PASS","economy.json: five workplace-composition lenses")]
