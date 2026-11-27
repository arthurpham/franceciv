"""National cycling-infrastructure export."""

import math
import struct
from collections import defaultdict

import pyarrow.parquet as pq

from .fr_hazards import COG_BASE, COG_COMMUNES, COG_MOVEMENTS, commune_resolver, read_cog_csv
from ..core.source import Source, SourceInfo

URL='https://static.data.gouv.fr/resources/amenagements-cyclables-france-metropolitaine/20261103-150341/france-20261103.parquet'
PROTECTED={'PISTE CYCLABLE','VOIE VERTE','COULOIR BUS+VELO','AMENAGEMENT MIXTE PIETON VELO HORS VOIE VERTE','ACCOTEMENT REVETU HORS CVCB','GOULOTTE'}
EXCLUDED={None,'','AUCUN','AUTRE'}

def lines_wkb(buf):
    def line(pos):
        endian = '<' if buf[pos] == 1 else '>'
        typ = struct.unpack_from(endian + 'I', buf, pos + 1)[0]
        if typ != 2:
            return [], pos + 5
        n = struct.unpack_from(endian + 'I', buf, pos + 5)[0]
        start = pos + 9
        return [struct.unpack_from(endian + 'dd', buf, start + 16 * i) for i in range(n)], start + 16 * n
    endian = '<' if buf[0] == 1 else '>'
    typ = struct.unpack_from(endian + 'I', buf, 1)[0]
    if typ == 2:
        pts, _ = line(0)
        return [pts]
    if typ == 5:
        n = struct.unpack_from(endian + 'I', buf, 5)[0]
        pos = 9; out = []
        for _ in range(n):
            pts, pos = line(pos)
            if pts: out.append(pts)
        return out
    return []

def length_km(buf):
    total=0.0
    for pts in lines_wkb(buf):
        for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
            lat=math.radians((y1+y2)/2)
            total+=math.hypot((x2-x1)*111.32*math.cos(lat),(y2-y1)*111.32)
    return total

class FrenchCycling(Source):
    info=SourceInfo(id='fr_cycling',title='Base Nationale des Aménagements Cyclables, export national OpenStreetMap',publisher='transport.data.gouv.fr / Géovélo / OpenStreetMap contributors',homepage='https://transport.data.gouv.fr/datasets/amenagements-cyclables-france-metropolitaine/',license='ODbL 1.0',description='National normalized export of cycling infrastructure digitized in OpenStreetMap, using the BNAC schema. Segment lengths are computed from WGS84 LineStrings; current-commune attribution uses INSEE municipal-merger mappings where necessary. Coverage reflects OpenStreetMap completeness and excludes overseas territories not in this metropolitan export.',used_for=['Cycling-infrastructure lenses'])
    def fetch(self,force=False):
        self.download(URL,'france-cycling.parquet',force=force,expect_binary=True)
        self.download(f'{COG_BASE}/{COG_COMMUNES}',COG_COMMUNES,force=force)
        self.download(f'{COG_BASE}/{COG_MOVEMENTS}',COG_MOVEMENTS,force=force)
    def process(self):
        resolve=commune_resolver(read_cog_csv(self.raw_dir/COG_COMMUNES),read_cog_csv(self.raw_dir/COG_MOVEMENTS))
        rows=defaultdict(lambda:{'network_km':0.0,'protected_km':0.0})
        total=network=protected=0.0;segments=0
        cols=['code_com_d','ame_d','code_com_g','ame_g','geometry']
        for batch in pq.ParquetFile(self.raw_dir/'france-cycling.parquet').iter_batches(batch_size=50000,columns=cols):
            for r in batch.to_pylist():
                segments+=1;types={r['ame_d'],r['ame_g']};explicit=bool(types-EXCLUDED)
                if not explicit:continue
                km=length_km(r['geometry']);network+=km
                is_protected=bool(types&PROTECTED);protected+=km if is_protected else 0
                codes={resolve((r[k] or '').zfill(5)) for k in ('code_com_d','code_com_g') if r.get(k)}
                if not codes:continue
                share=km/len(codes)
                for code in codes:
                    rows[code]['network_km']+=share
                    if is_protected:rows[code]['protected_km']+=share
        total=sum(v['network_km'] for v in rows.values());prot=sum(v['protected_km'] for v in rows.values())
        print(f'    {segments} source segments; {network:.0f} explicit infrastructure km, {total:.0f} attributed km, {prot:.0f} protected km in {len(rows)} communes')
        if len(rows)<10000 or total<50000:raise ValueError('unexpected cycling coverage')
        return {'vintage':'BNAC OpenStreetMap export, 3 November 2026','_files':['france-cycling.parquet',COG_COMMUNES,COG_MOVEMENTS],'rows':dict(rows),'explicit_network_km':round(network,1)}
