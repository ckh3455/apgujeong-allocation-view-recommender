#!/usr/bin/env python3
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / 'current-view'
FILES = {
    '2': 'apgujeong_2_units.geojson',
    '3': 'apg3_unit_polygon.geojson',
    '4': 'apgujeong_4_units.geojson',
    '5': 'apgujeong_5_units.geojson',
}
OUT = ROOT / 'data' / 'geojson_floor_count_audit.json'

def n(v, default=0):
    try:
        return int(round(float(v)))
    except Exception:
        return default

def mult(unit_type):
    vals = [x.strip() for x in str(unit_type or '').split(',') if x.strip()]
    return max(1, len(vals))

def norm_type(zone, t):
    s = str(t or '').strip()
    return s

rows=[]
for zone, fn in FILES.items():
    data=json.loads((VIEW/fn).read_text(encoding='utf-8'))
    agg=defaultdict(lambda: defaultdict(int))
    samples=defaultdict(list)
    for i,f in enumerate(data.get('features',[]),1):
        p=f.get('properties') or {}
        t=norm_type(zone,p.get('unit_type'))
        floors=n(p.get('floors'))
        m=mult(t)
        start=n(p.get('start_floor') or p.get('floor_start') or p.get('min_floor') or p.get('from_floor'),1)
        vals={
            'features':1,
            'sum_floors':floors,
            'sum_floors_minus1':max(0,floors-1),
            'weighted_floors':floors*m,
            'weighted_floors_minus1':max(0,floors-1)*m,
            'weighted_from_start':max(0,floors-start+1)*m,
        }
        for k,v in vals.items(): agg[t][k]+=v
        if len(samples[t])<5:
            samples[t].append({k:p.get(k) for k in ['fid','dong','unit_type','floors','floor_start','start_floor','min_floor','from_floor','piloti_m','floor_h','height_m']})
    for t,a in agg.items():
        rows.append({'zone':zone,'unit_type':t,**a,'samples':samples[t]})
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'rowCount':len(rows),'output':str(OUT.relative_to(ROOT))},ensure_ascii=False))
