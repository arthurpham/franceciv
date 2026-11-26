"""French industry specialisation for City View, from INSEE workplace employment."""

import json

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["fr_insee_stats", "cities.json"]
PRODUCES = ["districts.json"]

INDUSTRIES = {
 "AZ":"Agriculture, forestry and fishing","BZ":"Mining and quarrying","CA":"Food, beverages and tobacco","CB":"Textiles, clothing and leather","CC":"Wood, paper and printing","CD":"Coke and refining","CE":"Chemicals","CF":"Pharmaceuticals","CG":"Rubber, plastics and minerals","CH":"Metals and metal products","CI":"Computer, electronic and optical products","CJ":"Electrical equipment","CK":"Machinery and equipment","CL":"Transport equipment","CM":"Other manufacturing and repair","DZ":"Electricity and gas","EZ":"Water, waste and remediation","FZ":"Construction","GZ":"Trade and vehicle repair","HZ":"Transportation and storage","IZ":"Accommodation and food services","JA":"Publishing, audiovisual and broadcasting","JB":"Telecommunications","JC":"Computer programming and information services","KZ":"Finance and insurance","LZ":"Real estate","MA":"Legal, accounting, architecture and engineering","MB":"Scientific research and development","MC":"Other professional and scientific services","NZ":"Administrative and support services","OZ":"Public administration","PZ":"Education","QA":"Human health","QB":"Social care and social work","RZ":"Arts, entertainment and recreation","SZ":"Other services","TZ":"Household employers","UZ":"Extraterritorial organisations",
}
CATALOG = [
 {"id":"campus","name":"Campus","icon":"d-campus","color":"#4a7bd0","codes":["MB","PZ","JC"],"sub":{"MB":"Research","PZ":"Education","JC":"Software"},"badge":{"id":"scientific","label":"Knowledge city","labels":{"MB":"Research city","PZ":"University city","JC":"Tech city"}},"description":"Education, research and digital services."},
 {"id":"commercial_hub","name":"Commercial hub","icon":"d-commercial-hub","color":"#c49a3a","codes":["KZ"],"sub":{"KZ":"Finance and insurance"},"badge":{"id":"commercial","label":"Finance city","labels":{"KZ":"Finance city"}},"description":"Finance and insurance."},
 {"id":"industrial_zone","name":"Industrial zone","icon":"d-industrial-zone","color":"#8a6a4a","codes":["BZ","CA","CB","CC","CD","CE","CF","CG","CH","CI","CJ","CK","CL","CM"],"sub":{"CF":"Pharmaceuticals","CI":"Electronics","CL":"Transport equipment","CA":"Food industry"},"badge":{"id":"industrial","label":"Factory town","labels":{"CF":"Pharma city","CI":"Electronics city","CL":"Vehicle industry city","CA":"Food-processing town"}},"description":"Manufacturing and extractive industries."},
 {"id":"theater_square","name":"Theater square","icon":"d-theater-square","color":"#9c4a86","codes":["JA","RZ"],"sub":{"JA":"Media","RZ":"Arts and entertainment"},"badge":{"id":"cultural","label":"Arts city","labels":{"JA":"Media city","RZ":"Arts city"}},"description":"Media, arts and entertainment."},
 {"id":"entertainment_complex","name":"Entertainment complex","icon":"d-entertainment-complex","color":"#d06a3a","codes":["IZ"],"sub":{"IZ":"Hospitality"},"badge":{"id":"entertainment","label":"Resort city","labels":{"IZ":"Resort city"}},"description":"Accommodation and food services."},
 {"id":"government_plaza","name":"Government plaza","icon":"d-government-plaza","color":"#667a8a","codes":["OZ"],"sub":{"OZ":"Public administration"},"badge":{"id":"governmental","label":"Government town","labels":{"OZ":"Government town"}},"description":"Public administration."},
 {"id":"aqueduct","name":"Aqueduct & dam","icon":"d-aqueduct","color":"#3a8a9c","codes":["DZ","EZ"],"sub":{"DZ":"Energy utilities","EZ":"Water and waste"},"badge":{"id":"utility","label":"Utility town","labels":{"DZ":"Energy town","EZ":"Water city"}},"description":"Energy, water and waste utilities."},
]
RULE={"min_lq":1.25,"min_jobs":1000,"min_share":0.01,"max_per_city":5,"badge_lq":4.0,"badge_share":0.03,"text":"A district appears when its industries have at least 1.25 times the metropolitan-France share of jobs and either 1,000 jobs or 1% of city jobs."}

def mix(src): return {k:v for k,v in src.items() if k in INDUSTRIES}
def score(rows,national):
 total=rows.get("_T") or sum(rows.values()); ntotal=national.get("_T") or sum(national.values())
 return total,ntotal

def city_row(src,nat):
 rows=mix(src); total,ntotal=score(rows,mix(nat))
 if not total or not ntotal:return None
 top=[]
 for code,emp in rows.items():
  share=emp/total; nshare=(nat.get(code) or 0)/ntotal
  lq=share/nshare if nshare else 0
  if emp>=1000: top.append({"naics":code,"emp":round(emp),"lq":round(lq,2),"avg_pay":None,"oty_pct":None,"suppressed":0,"lower_bound":False})
 top.sort(key=lambda x:-x["lq"]);top=top[:8]
 districts=[]
 for cat in CATALOG:
  emp=sum(rows.get(c,0) for c in cat["codes"]); nemp=sum(nat.get(c,0) for c in cat["codes"])
  if emp<=0 or nemp<=0:continue
  share=emp/total; lq=(share)/(nemp/ntotal)
  subs=[]
  for code in cat["codes"]:
   e=rows.get(code,0);ne=nat.get(code,0)
   if e>0 and ne>0:subs.append((e/total/(ne/ntotal),code,e))
  subs.sort(reverse=True)
  sub,slq,semp=(subs[0][1],subs[0][0],subs[0][2]) if subs else (None,None,None)
  if lq>=RULE["min_lq"] and (emp>=RULE["min_jobs"] or share>=RULE["min_share"]):
   strength=emp-emp/lq
   districts.append({"id":cat["id"],"lq":round(lq,2),"emp":round(emp),"share":round(share,4),"avg_pay":None,"sub":sub,"sub_lq":round(slq,2) if slq else None,"sub_emp":round(semp) if semp else None,"sub_lower_bound":False,"via":"broad","strength":round(strength),"suppressed":0,"lower_bound":False})
 districts.sort(key=lambda x:-x["strength"]);districts=districts[:RULE["max_per_city"]]
 badge=None
 for d in districts:
  cat=next(c for c in CATALOG if c["id"]==d["id"])
  label=cat["badge"]["label"]
  if d["sub"] and (d["sub_lq"] or 0)>=3:label=cat["badge"].get("labels",{}).get(d["sub"],label)
  badge={"id":cat["badge"]["id"],"label":label,"district":d["id"],"basis":"insee","text":f"{cat['name']}: {d['lq']:.1f}× the metropolitan-France share of jobs"}
  break
 return {"emp":round(total),"avg_pay":None,"top":top,"districts":districts,"badge":badge}

def build():
 ds=load_interim("fr_insee_stats")["datasets"]["employment"]
 nat=ds["FRANCE"]["FM"]
 ids=[c["id"] for c in json.loads((WEB_DATA/"cities.json").read_text())]
 cities={}
 for i in ids:
  cities[i]=city_row(ds["AAV2020"].get(i,{}),nat)
 write_web("districts.json",{"version":1,"vintage":"INSEE census 2023 workplace employment","year":2023,"sources":["fr_insee_stats"],"rule":RULE,"catalog":CATALOG,"industries":{k:{"title":v,"us_emp":round(nat.get(k,0))} for k,v in INDUSTRIES.items()},"national":{"emp":round(nat.get("_T") or sum(mix(nat).values())),"avg_pay":None},"cities":cities,"counties":{}})
 print(f"    {len(cities)} cities")


def check(web_dir):
 p=web_dir/"districts.json"
 if not p.exists():return [("NOTE","districts.json missing (optional layer)")]
 d=json.loads(p.read_text());bad=[]
 for cid,row in (d.get("cities") or {}).items():
  if row is not None and (not isinstance(row.get("districts"),list) or not isinstance(row.get("top"),list)):bad.append(cid)
 return [("FAIL",f"malformed city rows: {', '.join(bad[:5])}")] if bad else [("PASS",f"districts.json: {sum(v is not None for v in d['cities'].values())} cities")]
