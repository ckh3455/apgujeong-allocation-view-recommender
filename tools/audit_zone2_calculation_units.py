#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / 'current-view'
SRC = VIEW / 'apgujeong_2_units.geojson'
OUT = ROOT / 'data' / 'zone2_calculation_units_audit.json'

data = json.loads(SRC.read_text(encoding='utf-8'))
features = data.get('features', [])

def norm_geom(g):
    return json.dumps(g, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def floors(p):
    try:
        return int(round(float(p.get('floors') or 0)))
    except Exception:
        return 0

def mult(t):
    return max(1, len([x for x in str(t or '').split(',') if x.strip()]))

by_type = defaultdict(lambda: {'features':0,'sum_floors':0,'weighted_floors':0})
geom_groups = defaultdict(list)
rows=[]
for i,f in enumerate(features,1):
    p=f.get('properties') or {}
    t=str(p.get('unit_type') or '').strip()
    fl=floors(p)
    m=mult(t)
    by_type[t]['features'] += 1
    by_type[t]['sum_floors'] += fl
    by_type[t]['weighted_floors'] += fl*m
    geom_groups[norm_geom(f.get('geometry'))].append({
        'index': i,
        'fid': p.get('fid'),
        'dong': p.get('dong'),
        'unit_type': t,
        'floors': fl,
        'multiplier': m,
    })
    rows.append({
        'index': i,
        'fid': p.get('fid'),
        'dong': p.get('dong'),
        'unit_type': t,
        'floors': fl,
        'multiplier': m,
        'weighted_units': fl*m,
        'property_keys': sorted(p.keys()),
    })

dup_geom=[v for v in geom_groups.values() if len(v)>1]
result={
    'featureCount': len(features),
    'sumFloorsNoMultiplier': sum(r['floors'] for r in rows),
    'sumWithCommaMultiplier': sum(r['weighted_units'] for r in rows),
    'extraFromCommaMultiplier': sum(r['weighted_units']-r['floors'] for r in rows),
    'commaTypes': {k:v for k,v in sorted(by_type.items()) if ',' in k},
    'allTypes': dict(sorted(by_type.items())),
    'exactDuplicateGeometryGroupCount': len(dup_geom),
    'exactDuplicateGeometryFeatureCount': sum(len(g) for g in dup_geom),
    'exactDuplicateGeometryGroups': dup_geom,
    'features': rows,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:result[k] for k in ['featureCount','sumFloorsNoMultiplier','sumWithCommaMultiplier','extraFromCommaMultiplier','exactDuplicateGeometryGroupCount','exactDuplicateGeometryFeatureCount']}, ensure_ascii=False, indent=2))
