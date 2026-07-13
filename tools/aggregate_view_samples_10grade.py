#!/usr/bin/env python3
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data' / 'view_floor_rows.csv'
OUT_CSV = ROOT / 'data' / 'view_samples_10grade.csv'
OUT_MD = ROOT / 'data' / 'view_samples_10grade.md'

GRADE_ORDER = ['AAA','AA','A','BBB','BB','B','CCC','CC','C','D']

def normalize_pyeong(zone, raw):
    p = str(raw or '').strip().replace('평','').replace('PY','').replace('py','')
    if zone == '2구역':
        return {'45,46':'45~46','51,52':'51~52','55,56':'55~56'}.get(p,p)
    if zone == '4구역' and p in {'47A','47B'}:
        return '47'
    return p

def grade(angle):
    a = float(angle)
    if a >= 101: return 'AAA'
    if a >= 91: return 'AA'
    if a >= 81: return 'A'
    if a >= 71: return 'BBB'
    if a >= 61: return 'BB'
    if a >= 51: return 'B'
    if a >= 41: return 'CCC'
    if a >= 31: return 'CC'
    if a >= 21: return 'C'
    return 'D'

def pct(n,d):
    return round(n/d*100,2) if d else 0.0

agg = defaultdict(lambda: {'count':0,'sum':0.0,'grades':{g:0 for g in GRADE_ORDER}})
with SRC.open(encoding='utf-8-sig', newline='') as f:
    for row in csv.DictReader(f):
        zone = str(row['zone']).strip()
        p = normalize_pyeong(zone, row['unitType'])
        angle = float(row['viewAngle'])
        key = (zone,p)
        agg[key]['count'] += 1
        agg[key]['sum'] += angle
        agg[key]['grades'][grade(angle)] += 1

rows=[]
for (zone,p),v in agg.items():
    n=v['count']
    row={'구역':zone,'평형':p,'조망표본수':n,'평균조망각':round(v['sum']/n,2)}
    for g in GRADE_ORDER:
        row[f'{g}_표본수']=v['grades'][g]
        row[f'{g}_비율']=pct(v['grades'][g],n)
    rows.append(row)
rows.sort(key=lambda r:(int(r['구역'][0]), int(''.join(ch for ch in str(r['평형']) if ch.isdigit()) or 9999), str(r['평형'])))

headers=['구역','평형','조망표본수','평균조망각']
for g in GRADE_ORDER:
    headers += [f'{g}_표본수',f'{g}_비율']
with OUT_CSV.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers); w.writeheader(); w.writerows(rows)

md=['# 조망표본수 기준 10등급 조망각','','- AAA: 101° 이상','- AA: 91~100°','- A: 81~90°','- BBB: 71~80°','- BB: 61~70°','- B: 51~60°','- CCC: 41~50°','- CC: 31~40°','- C: 21~30°','- D: 20° 이하','',
'| 구역 | 평형 | 조망표본수 | 평균각 | AAA | AA | A | BBB | BB | B | CCC | CC | C | D |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:
    md.append('| ' + ' | '.join([str(r['구역']),str(r['평형']),str(r['조망표본수']),f"{r['평균조망각']:.2f}°"] + [f"{r[f'{g}_비율']:.2f}%" for g in GRADE_ORDER]) + ' |')
OUT_MD.write_text('\n'.join(md)+'\n',encoding='utf-8')
print({'rows':len(rows),'csv':str(OUT_CSV.relative_to(ROOT))})
