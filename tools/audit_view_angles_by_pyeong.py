#!/usr/bin/env python3
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data" / "view_summary.json"
OUT_JSON = ROOT / "data" / "view_angle_by_pyeong_audit.json"
OUT_CSV = ROOT / "data" / "view_angle_by_pyeong_audit.csv"
OUT_MD = ROOT / "data" / "view_angle_by_pyeong_audit.md"

ZONE4_MAP = {
    "59": "25평", "84": "34평", "96": "40평", "105": "43평",
    "47": "47평", "114": "47평", "115": "47평", "120": "49평",
    "126": "52평", "147": "60평", "154": "63평", "164": "67평",
    "166": "68평", "177": "72평", "183": "74평", "188": "77평",
    "P230": "P94평", "P270": "P110평", "P420": "P172평",
}


def zone4_key(unit_type):
    t = str(unit_type or "").strip().upper().replace(" ", "")
    m = re.match(r"^(P\d+|D?\d+)", t)
    return m.group(1) if m else t


def display_pyeong(zone_id, unit_type):
    if str(zone_id) == "4":
        key = zone4_key(unit_type)
        if key in ZONE4_MAP:
            return ZONE4_MAP[key]
        nums = re.findall(r"\d+", str(unit_type or ""))
        return f"{int(nums[0])}평" if nums else str(unit_type or "")
    return str(unit_type or "").strip()


def pyeong_sort_key(value):
    nums = re.findall(r"\d+", str(value))
    return (int(nums[0]) if nums else 9999, str(value))


def weighted_percentile(points, q):
    # points: (angle, weight)
    points = sorted((float(a), int(w)) for a, w in points if int(w) > 0)
    total = sum(w for _, w in points)
    if total <= 0:
        return 0.0
    threshold = q * total
    acc = 0
    for angle, weight in points:
        acc += weight
        if acc >= threshold:
            return angle
    return points[-1][0]


def angle_bucket(angle):
    a = float(angle)
    if a <= 10:
        return "10도 이하"
    start = int((a - 1e-9) // 10) * 10
    return f"{start}~{start+10}도"


data = json.loads(SUMMARY.read_text(encoding="utf-8-sig"))
rows = data.get("rows", [])
source = data.get("source", {})
assumptions = data.get("assumptions", {})

groups = defaultdict(lambda: {
    "points": [], "bands": 0, "units": set(), "dongs": set(),
    "angle_counts": defaultdict(int), "max_gap_points": [], "issues": [],
})
row_issues = []

for row in rows:
    zone_id = str(row.get("zoneId", "")).strip()
    if zone_id not in {"2", "3", "4", "5"}:
        continue
    pyeong = display_pyeong(zone_id, row.get("unitType", ""))
    floors = max(1, int(row.get("floors") or 1))
    bands = row.get("floorBands") or []
    if not bands:
        bands = [{
            "start": 1, "end": floors,
            "viewAngle": int(row.get("topFloorViewAngle") or 0),
            "maxGap": 0,
        }]
    covered = 0
    for band in bands:
        start = max(1, int(band.get("start", 1)))
        end = min(floors, int(band.get("end", start)))
        weight = max(0, end - start + 1)
        if weight <= 0:
            continue
        angle = float(band.get("viewAngle") or 0)
        max_gap = float(band.get("maxGap") or 0)
        g = groups[(zone_id, pyeong)]
        g["points"].append((angle, weight))
        g["max_gap_points"].append((max_gap, weight))
        g["bands"] += 1
        g["units"].add(str(row.get("fid", "")))
        g["dongs"].add(str(row.get("dong", "")))
        g["angle_counts"][angle] += weight
        covered += weight
        if angle < 0 or angle > 360:
            row_issues.append({"fid": row.get("fid"), "issue": "angle_out_of_range", "angle": angle})
        if max_gap < 0 or max_gap > angle + 1e-9:
            row_issues.append({"fid": row.get("fid"), "issue": "max_gap_gt_angle", "angle": angle, "maxGap": max_gap})
    if covered != floors:
        row_issues.append({
            "fid": row.get("fid"), "zoneId": zone_id, "unitType": row.get("unitType"),
            "issue": "floor_coverage_mismatch", "floors": floors, "covered": covered,
        })

result_rows = []
for (zone_id, pyeong), g in sorted(groups.items(), key=lambda kv: (int(kv[0][0]), pyeong_sort_key(kv[0][1]))):
    points = g["points"]
    total = sum(w for _, w in points)
    weighted_sum = sum(a * w for a, w in points)
    avg = weighted_sum / total if total else 0
    max_angle = max((a for a, _ in points), default=0)
    min_angle = min((a for a, _ in points), default=0)
    p50 = weighted_percentile(points, 0.50)
    p75 = weighted_percentile(points, 0.75)
    best_share = sum(w for a, w in points if a == max_angle) / total * 100 if total else 0
    over10 = sum(w for a, w in points if a > 10) / total * 100 if total else 0
    over20 = sum(w for a, w in points if a > 20) / total * 100 if total else 0
    over30 = sum(w for a, w in points if a > 30) / total * 100 if total else 0
    zero = sum(w for a, w in points if a <= 0) / total * 100 if total else 0
    avg_gap = sum(a * w for a, w in g["max_gap_points"]) / total if total else 0
    distribution = {bucket: 0 for bucket in []}
    for angle, weight in points:
        distribution[angle_bucket(angle)] = distribution.get(angle_bucket(angle), 0) + weight
    distribution_pct = {k: round(v / total * 100, 1) for k, v in sorted(distribution.items(), key=lambda x: (int(re.findall(r"\d+", x[0])[0]), x[0]))}
    result_rows.append({
        "구역": f"{zone_id}구역",
        "평형": pyeong,
        "유닛수": len(g["units"]),
        "동수": len(g["dongs"]),
        "층표본수": total,
        "가중평균조망각": round(avg, 2),
        "중앙조망각": round(p50, 2),
        "상위25%경계각": round(p75, 2),
        "최소조망각": round(min_angle, 2),
        "최대조망각": round(max_angle, 2),
        "최대각비중_pct": round(best_share, 1),
        "10도초과_pct": round(over10, 1),
        "20도초과_pct": round(over20, 1),
        "30도초과_pct": round(over30, 1),
        "0도비중_pct": round(zero, 1),
        "가중평균최대연속각": round(avg_gap, 2),
        "분포": distribution_pct,
    })

output = {
    "source": source,
    "assumptions": assumptions,
    "calculation": {
        "basis": "앱의 build_view_candidates와 동일하게 floorBands의 각 구간을 층수로 가중",
        "pyeongMapping": "2·3·5구역은 unitType 표시값, 4구역은 ZONE4_TYPE_PYEONG_LABEL",
        "angleField": "floorBands[].viewAngle",
        "weightField": "end-start+1",
    },
    "rowCount": len(rows),
    "groupCount": len(result_rows),
    "issues": row_issues,
    "rows": result_rows,
}
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

headers = [k for k in result_rows[0].keys() if k != "분포"] + ["분포"] if result_rows else []
with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    for r in result_rows:
        x = dict(r)
        x["분포"] = json.dumps(x["분포"], ensure_ascii=False)
        writer.writerow(x)

lines = [
    "# 보수적 한강라인 기준 평형별 조망각 검증", "",
    f"- 원본 인덱스: `{source.get('index', '')}`",
    f"- 계산모드: `{source.get('calculationMode', '')}`",
    f"- 한강라인: `{assumptions.get('riverLine', '')}`",
    "- 집계: 앱의 `floorBands[].viewAngle`을 각 층구간의 층수로 가중", "",
    "| 구역 | 평형 | 유닛 | 층표본 | 평균각 | 중앙각 | 최소~최대 | 10도 초과 | 20도 초과 | 30도 초과 | 0도 | 평균 최대연속각 |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for r in result_rows:
    lines.append(
        f"| {r['구역']} | {r['평형']} | {r['유닛수']} | {r['층표본수']} | "
        f"{r['가중평균조망각']:.2f}° | {r['중앙조망각']:.0f}° | "
        f"{r['최소조망각']:.0f}~{r['최대조망각']:.0f}° | "
        f"{r['10도초과_pct']:.1f}% | {r['20도초과_pct']:.1f}% | {r['30도초과_pct']:.1f}% | "
        f"{r['0도비중_pct']:.1f}% | {r['가중평균최대연속각']:.2f}° |"
    )
lines += ["", f"- 데이터 이상 검출: {len(row_issues)}건"]
OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({
    "source": source,
    "assumptions": assumptions,
    "groups": len(result_rows),
    "issues": len(row_issues),
    "outputs": [str(OUT_JSON.relative_to(ROOT)), str(OUT_CSV.relative_to(ROOT)), str(OUT_MD.relative_to(ROOT))],
}, ensure_ascii=False))
