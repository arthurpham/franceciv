"""Installed electricity-generation capacity lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_energy"]
PRODUCES = ["energy_system.json"]
RAMP = ["#243342", "#315b68", "#4d8a74", "#8fab5f", "#d9c75a"]
SETS = {
    "solar_capacity": ("Solar capacity", "☀️", {"Solaire"}, "Installed solar-electric capacity per resident from the ODRÉ national registry. Commune capacities are aggregated by map hex; small installations are represented through ODRÉ commune aggregates."),
    "wind_capacity": ("Wind capacity", "🌬️", {"Eolien"}, "Installed wind-electric capacity per resident from the ODRÉ national registry. Commune capacities are aggregated by map hex."),
    "hydro_capacity": ("Hydro capacity", "💧", {"Hydraulique"}, "Installed hydroelectric capacity per resident from the ODRÉ national registry, including conventional, run-of-river, pumped-storage and tidal installations where present. Commune capacities are aggregated by map hex."),
    "nuclear_capacity": ("Nuclear capacity", "☢️", {"Nucléaire"}, "Installed nuclear-electric capacity per resident from the ODRÉ national registry. Per-capita normalization is only a spatial intensity measure: electricity is transmitted nationally rather than consumed solely by nearby residents."),
    "renewable_capacity": ("Renewable capacity", "🌱", {"Solaire", "Eolien", "Hydraulique", "Bioénergies", "Energies Marines", "Géothermie"}, "Installed renewable-electric capacity per resident from the ODRÉ national registry. Hydro includes pumped-storage and tidal installations where present, so the total is generation-capacity infrastructure rather than a strict annual renewable-generation measure."),
    "storage_capacity": ("Non-hydro storage", "🔋", {"Stockage non hydraulique"}, "Installed non-hydraulic electricity-storage power per resident from the ODRÉ national registry. Values use the registry's maximum installed power field; energy duration in MWh is not available in this national extract."),
}

def percentile(vals,p):
 xs=sorted(v for v in vals if v is not None);return xs[min(len(xs)-1,max(0,round((p/100)*(len(xs)-1))))] if xs else None

def lens(lens_id,name,emoji,vals,desc):
 positive=[v for v in vals if v]
 return {"id":lens_id,"group":"energy_system","name":name,"icon":lens_id,"emoji":emoji,"unit":"kW / resident","format":"float","scale":"log","domain":[percentile(positive,2),percentile(positive,98)],"ramp":RAMP,"higher_is":"neutral","source":"fr_energy","description":desc,"values":vals}

def build():
 world=load_interim("_world");bounds=load_interim("fr_boundaries");energy=load_interim("fr_energy")
 grid=HexGrid(**world["grid"]);proj=MapProjection(**world["projection"])
 cells={};pop=defaultdict(int)
 for c in bounds["communes"]:
  if c.get("lon") is None:continue
  x,y=proj(c["lon"],c["lat"]);cell=nearest_land(world,grid,x,y)
  if cell>=0:cells[c["code"]]=cell;pop[cell]+=c.get("population") or 0
 acc=defaultdict(lambda:defaultdict(float));unmatched=0.0
 for row in energy["rows"]:
  if row.get("regime") != "En service":continue
  code=(row.get("codeinseecommuneimplantation") or row.get("codeinseecommune") or "").zfill(5);cell=cells.get(code)
  if cell is None:unmatched+=(row.get("puismaxinstallee") or 0)/1000;continue
  acc[cell][row.get("filiere") or ""]+=(row.get("puismaxinstallee") or 0)/1000  # kW -> MW
 renewable_families={"Solaire","Eolien","Hydraulique","Bioénergies","Energies Marines","Géothermie"}
 low_carbon=[]
 for i in range(grid.size):
  generation=sum(v for f,v in acc[i].items() if f!="Stockage non hydraulique")
  clean=sum(acc[i][f] for f in renewable_families)+acc[i]["Nucléaire"]
  low_carbon.append(round(clean/generation,4) if generation else None)
 out={"low_carbon_capacity_share":low_carbon}
 for lens_id,(_,_,families,_) in SETS.items():
  vals=[]
  for i in range(grid.size):
   capacity=sum(acc[i][family] for family in families);p=pop.get(i,0)
   vals.append(round(capacity*1000/p,3) if p else None)  # MW -> kW/resident
  out[lens_id]=vals
 share_lens={"id":"low_carbon_capacity_share","group":"energy_system","name":"Low-carbon capacity share","icon":"low_carbon_capacity_share","emoji":"⚛️","unit":"share of generation capacity","format":"pct","scale":"linear","domain":[percentile([v for v in low_carbon if v],2),percentile([v for v in low_carbon if v],98)],"ramp":RAMP,"higher_is":"better","source":"fr_energy","description":"Nuclear plus renewable installed capacity as a share of non-storage generation capacity. This is nameplate capacity, not generated electricity or emissions; hydro includes pumped-storage infrastructure.","values":low_carbon}
 write_web("energy_system.json",{"version":1,"vintage":energy.get("vintage","ODRÉ national energy registry"),"sources":["fr_energy"],"group":{"id":"energy_system","name":"Energy system"},"unmatched_capacity_mw":round(unmatched,2),"lenses":[lens(k,n,e,out[k],d) for k,(n,e,_,d) in SETS.items()]+[share_lens]})

def check(web_dir):
 import json
 doc=json.loads((web_dir/"energy_system.json").read_text());assert len(doc["lenses"])==7
 for item in doc["lenses"]:
  vals=[v for v in item["values"] if v is not None];assert len(vals)>2500 and len([v for v in vals if v])>10
 assert doc["unmatched_capacity_mw"]<1000
 return [("PASS","energy_system.json: 7 installed-capacity lenses")]
