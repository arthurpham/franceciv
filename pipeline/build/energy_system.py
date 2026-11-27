"""Installed electricity-generation capacity lenses."""

from collections import defaultdict
import unicodedata

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_energy", "fr_energy_network"]
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
NETWORK_RAMP=["#202638","#333f64","#3f6280","#4d8a84","#b8a75c"]

def norm_name(value):
 value=unicodedata.normalize("NFKD",value or "");value="".join(ch for ch in value if not unicodedata.combining(ch))
 return " ".join(value.upper().replace("-"," ").replace("'"," ").split())

def network_lens(lens_id,name,emoji,unit,fmt,vals,desc,higher="neutral"):
 return {"id":lens_id,"group":"energy_system","name":name,"icon":lens_id,"emoji":emoji,"unit":unit,"format":fmt,"scale":"linear","domain":[percentile(vals,2),percentile(vals,98)],"ramp":NETWORK_RAMP,"higher_is":higher,"source":"fr_energy_network","description":desc,"values":vals}


def percentile(vals,p):
 xs=sorted(v for v in vals if v is not None);return xs[min(len(xs)-1,max(0,round((p/100)*(len(xs)-1))))] if xs else None

def lens(lens_id,name,emoji,vals,desc):
 positive=[v for v in vals if v]
 return {"id":lens_id,"group":"energy_system","name":name,"icon":lens_id,"emoji":emoji,"unit":"kW / resident","format":"float","scale":"log","domain":[percentile(positive,2),percentile(positive,98)],"ramp":RAMP,"higher_is":"neutral","source":"fr_energy","description":desc,"values":vals}

def build():
 world=load_interim("_world");bounds=load_interim("fr_boundaries");energy=load_interim("fr_energy");network=load_interim("fr_energy_network")
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
 network_lenses=[]
 # Departmental RTE statistics are intentionally statistical rather than geometric: RTE withdrew
 # precise public line/site coordinates for security reasons. Area comes from commune surfaces.
 area=defaultdict(float)
 for c in bounds["communes"]:
  area[c["department"]]+=c.get("surface_ha") or 0
 site_names={norm_name(c["name"]):c["geoid"] for c in bounds["counties"]}
 sites={}
 unresolved=[]
 for name,counts in network["sites_by_department_name"].items():
  dep=site_names.get(name)
  if dep:sites[dep]=counts
  else:unresolved.append(name)
 dep_rows={};inconsistent_stacking=[]
 for dep,row in network["lines"].items():
  a=(area.get(dep) or 0)/100
  if not a:continue
  site=sites.get(dep,{})
  circuit=row.get("circuit_km") or 0;route=row.get("route_km") or 0
  overhead=circuit-(row.get("non_overhead_circuit_km") or 0)
  stacking=overhead/route if route and overhead else None
  if stacking is not None and stacking < 1:
   inconsistent_stacking.append(dep)
   stacking=None
  dep_rows[dep]={
   "density":circuit*100/a,
   "high_density":(row.get("high_circuit_km") or 0)*100/a,
   "non_overhead_share":(row.get("non_overhead_circuit_km") or 0)/circuit if circuit else None,
   "stacking":stacking,
   "sites_density":(site.get("transformation") or 0)*1000/a if site else None,
   "hv_sites_density":(site.get("transformation_high") or 0)*1000/a if site else None,
   "connection_density":(site.get("connection_points") or 0)*1000/a if site else None,
  }
 def dep_values(key,nd=3):
  vals=[]
  for ci in world["county"]:
   dep=world["counties"][ci] if ci>=0 else None;value=(dep_rows.get(dep) or {}).get(key)
   vals.append(round(value,nd) if value is not None else None)
  return vals
 network_specs=[
  ("transmission_network_density","Transmission network density","🔌","circuit km / 100 km²","float","density","Total RTE transmission-circuit length per 100 km² by department in {year}. Circuits count each electrical circuit, so a double-circuit line contributes twice; values are departmental infrastructure density, not exact line locations."),
  ("high_voltage_network_density","High-voltage network density","⚡","225kV+ circuit km / 100 km²","float","high_density","RTE transmission-circuit length at 225 kV, 400 kV and direct current per 100 km² by department in {year}. This highlights the backbone transmission network rather than lower-voltage regional transmission."),
  ("non_overhead_transmission_share","Non-overhead transmission share","🕳️","share of circuit km","pct","non_overhead_share","Underground or submarine RTE transmission-circuit kilometres as a share of all circuit kilometres by department in {year}. Most of the transmission network remains overhead."),
  ("transmission_circuit_stacking","Transmission circuit stacking","🗼","overhead circuits / pylon-route km","float","stacking","Overhead RTE circuit kilometres divided by pylon-route kilometres by department in {year}. Values above one indicate multiple electrical circuits sharing the same pylons or corridor. Departmental ratios below one are treated as missing because independently allocated circuit and pylon-route lengths can be internally inconsistent near department boundaries."),
  ("transformation_site_density","Transformation-site density","🏭","sites / 1,000 km²","float","sites_density","Operating RTE electricity-transformation sites per 1,000 km² by department. The public registry lists most sites by department without exact coordinates; connection points are excluded. Registry rows whose department field is blank are omitted rather than guessed."),
  ("hv_transformation_site_density","High-voltage transformation sites","🔆","225kV+ sites / 1,000 km²","float","hv_sites_density","Operating RTE electricity-transformation sites at 225 kV, 400 kV or direct current per 1,000 km² by department. The public registry lists most sites by department without exact coordinates. Registry rows whose department field is blank are omitted rather than guessed."),
  ("grid_connection_point_density","Grid connection points","🔗","points / 1,000 km²","float","connection_density","Operating RTE points de piquage—customer or network connection points—per 1,000 km² by department. Exact locations are not published in the current security-aware open-data extract, and registry rows whose department field is blank are omitted rather than guessed."),
 ]
 network_lenses=[network_lens(k,n,e,u,f,dep_values(key),d.format(year=network.get("year"))) for k,n,e,u,f,key,d in network_specs]
 capacity_lenses=[lens(k,n,e,out[k],d) for k,(n,e,_,d) in SETS.items()]+[share_lens]
 write_web("energy_system.json",{"version":1,"vintage":energy.get("vintage","ODRÉ national energy registry")+"; "+f'RTE network statistics, {network.get("year")}',"sources":["fr_energy","fr_energy_network"],"group":{"id":"energy_system","name":"Energy system"},"unmatched_capacity_mw":round(unmatched,2),"unmatched_network_site_names":unresolved,"untagged_site_rows":network.get("unmatched_site_rows",{}).get("blank",0),"inconsistent_stacking_departments":inconsistent_stacking,"lenses":capacity_lenses+network_lenses})

def check(web_dir):
 import json
 doc=json.loads((web_dir/"energy_system.json").read_text());assert len(doc["lenses"])==14
 for item in doc["lenses"]:
  vals=[v for v in item["values"] if v is not None];assert len(vals)>2000 and len([v for v in vals if v])>10
 assert doc["unmatched_capacity_mw"]<1000
 assert len(doc["unmatched_network_site_names"])<5
 assert doc["untagged_site_rows"]<200
 return [("PASS","energy_system.json: 7 installed-capacity and 7 transmission-network lenses")]
