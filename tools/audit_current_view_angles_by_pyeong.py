#!/usr/bin/env python3
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOR_CSV = ROOT / "data" / "view_floor_rows.csv"
SUMMARY_JSON = ROOT / "data" / "view_summary.json"
OUT_JSON = ROOT / "data" / "current_view_angles_by_pyeong.json"
OUT_CSV = ROOT / "data" / "current_view_angles_by_pyeong.csv"

ZONE4_TYPE_PYEONG_LABEL = {
    "59": "25평", "84": "34평", "96": "40평", "105": "43평",
    "47": "47평", "114": "47평", "115": "47평", "120": "49평",
    "126": "52평", "147": "60평", "154": "63평", "164": "67평",
    "166": "68평", "177": "72평", "183": "74평", "188": "77평",
    "P230": "P94평", "P270": "P110평", "P420": "P172평",
}


def zone4_type_key(type_name: str) -> str:
    t = str(type_name or "").strip().upper().replace(" ", "")
    m = re.match(r"^(P\d+|D?\d+)", t)
    return m.group(1) if m else t


def pyeong_label(zone_id: str, unit_type: str) -> str:
    unit_type = str(unit_type or "").strip()
    if str(zone_id) == "4":
        return ZONE4_TYPE_PYEONG_LABEL.get(zone4_type_key(unit_type), f"{unit_type}평")
    if not unit_type:
        return "-"
    return f"{unit_type}평" if "평" not in unit_type.upper() and "PY" not in unit_type.upper() else unit_type


def numeric_sort_key(value: str):
    nums = re.findall(r"\d+", str(value))
    return int(nums[0]) if nums else 10**9


def percentile(sorted_values, q: float):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def avg(values):
    return sum(values) / len(values) if values else None


def round_or_none(value, digits=2):
    return None if value is None else round(float(value), digits)


summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8-sig"))
source = summary.get("source", {})
assumptions = summary.get("assumptions", {})

groups = defaultdict(lambda: {
    "view_angles": [],
    "max_gaps": [],
    "unit_types": set(),
    "fids": set(),
    "dongs": set(),
})
zone_totals = defaultdict(int)

with FLOOR_CSV.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        zone_id = str(row.get("zoneId", "")).strip()
        if zone_id not in {"2", "3", "4", "5"}:
            continue
        unit_type = str(row.get("unitType", "")).strip()
        label = pyeong_label(zone_id, unit_type)
        angle = float(row.get("viewAngle") or 0)
        max_gap = float(row.get("maxGap") or 0)
        key = (zone_id, label)
        g = groups[key]
        g["view_angles"].append(angle)
        g["max_gaps"].append(max_gap)
        g["unit_types"].add(unit_type)
        g["fids"].add(str(row.get("fid", "")))
        g["dongs"].add(str(row.get("dong", "")))
        zone_totals[zone_id] += 1

rows = []
for (zone_id, label), g in sorted(groups.items(), key=lambda kv: (int(kv[0][0]), numeric_sort_key(kv[0][1]), kv[0][1])):
    angles = sorted(g["view_angles"])
    gaps = sorted(g["max_gaps"])
    n = len(angles)
    disconnected_excess = [max(0.0, a - gap) for a, gap in zip(g["view_angles"], g["max_gaps"])]
    row = {
        "구역": f"{zone_id}구역",
        "평형": label,
        "계산단위_층": n,
        "유닛폴리곤수": len(g["fids"]),
        "동수": len(g["dongs"]),
        "원본유닛타입": " / ".join(sorted(g["unit_types"], key=lambda x: (numeric_sort_key(x), x))),
        "평균_총개방각": round_or_none(avg(angles)),
        "중앙값_총개방각": round_or_none(percentile(angles, 0.5)),
        "25분위_총개방각": round_or_none(percentile(angles, 0.25)),
        "75분위_총개방각": round_or_none(percentile(angles, 0.75)),
        "최소_총개방각": round_or_none(min(angles) if angles else None),
        "최대_총개방각_앱최선후보": round_or_none(max(angles) if angles else None),
        "평균_최대연속각": round_or_none(avg(gaps)),
        "중앙값_최대연속각": round_or_none(percentile(gaps, 0.5)),
        "최대_최대연속각": round_or_none(max(gaps) if gaps else None),
        "평균_분절합산초과각": round_or_none(avg(disconnected_excess)),
        "총개방각_연속각차이20도초과비율": round(100 * sum(1 for x in disconnected_excess if x > 20) / n, 2) if n else None,
        "30도이하비율": round(100 * sum(1 for x in angles if x <= 30) / n, 2) if n else None,
        "60도이상비율": round(100 * sum(1 for x in angles if x >= 60) / n, 2) if n else None,
        "90도이상비율": round(100 * sum(1 for x in angles if x >= 90) / n, 2) if n else None,
        "120도이상비율": round(100 * sum(1 for x in angles if x >= 120) / n, 2) if n else None,
    }
    rows.append(row)

zone_summary = []
for zone_id in ["2", "3", "4", "5"]:
    zr = [r for r in rows if r["구역"] == f"{zone_id}구역"]
    all_angles = []
    all_gaps = []
    for (zid, _), g in groups.items():
        if zid == zone_id:
            all_angles.extend(g["view_angles"])
            all_gaps.extend(g["max_gaps"])
    zone_summary.append({
        "구역": f"{zone_id}구역",
        "평형수": len(zr),
        "계산단위_층": len(all_angles),
        "평균_총개방각": round_or_none(avg(all_angles)),
        "최대_총개방각": round_or_none(max(all_angles) if all_angles else None),
        "평균_최대연속각": round_or_none(avg(all_gaps)),
        "최대_최대연속각": round_or_none(max(all_gaps) if all_gaps else None),
    })

result = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "source": {
        "summaryFile": str(SUMMARY_JSON.relative_to(ROOT)),
        "floorTable": str(FLOOR_CSV.relative_to(ROOT)),
        "calculationMode": source.get("calculationMode"),
        "index": source.get("index"),
        "riverLine": assumptions.get("riverLine"),
        "floorViewUsesEyeHeight": assumptions.get("floorViewUsesEyeHeight"),
        "sameDongRule": assumptions.get("sameDongRule"),
    },
    "interpretation": {
        "viewAngle": "앱 표의 한강조망각. 서로 떨어진 모든 열린 각도 구간의 합계(total open angle)",
        "maxGap": "앱 표의 최대연속각. 끊기지 않고 한 번에 보이는 가장 넓은 단일 구간",
        "appBestCandidate": "앱은 후보표를 한강조망각 내림차순으로 정렬하므로 평형 평균이 아니라 최대 총개방각 후보를 최상단에 표시",
        "weight": "각 유닛 폴리곤의 각 층을 1개 계산단위로 동일 가중. 분양계획상 실제 평형별 세대수 가중은 아님",
    },
    "zoneSummary": zone_summary,
    "rows": rows,
}

OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(json.dumps({
    "source": result["source"],
    "zoneSummary": zone_summary,
    "rowCount": len(rows),
    "zoneFloorCounts": dict(zone_totals),
}, ensure_ascii=False, indent=2))
