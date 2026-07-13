#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "simultaneous_conservative_view_by_pyeong.json"
OUT_JSON = ROOT / "data" / "actual_household_view_by_pyeong.json"
OUT_CSV = ROOT / "data" / "actual_household_view_by_pyeong.csv"
OUT_MD = ROOT / "data" / "actual_household_view_by_pyeong.md"

GRADES = ["특A급", "A급", "B급", "C급", "D급", "E급"]
GRADE_LABELS = {
    "특A급": "100도 이상",
    "A급": "81~99도",
    "B급": "61~80도",
    "C급": "41~60도",
    "D급": "21~40도",
    "E급": "20도 이하",
}

# app.py의 ZONE_SALES_PLAN과 동일한 실제 분양 세대수입니다.
ACTUAL_COUNTS = {
    "2구역": {
        "32": 256, "37": 61, "41": 429, "45~46": 389, "51~52": 333,
        "55~56": 156, "60": 225, "65": 99, "70": 38, "79": 114, "87": 122,
        "P88": 4, "P95~97": 26, "P127~134": 4, "P174~175": 2,
    },
    "3구역": {
        "27": 490, "38": 608, "42": 1457, "50": 358, "58": 564,
        "67": 550, "71": 80, "82": 248, "91": 80, "103": 78,
        "82P": 37, "91P": 8, "103P": 5, "110P": 2, "183P": 2,
    },
    "4구역": {
        "25": 49, "34": 73, "40": 406, "43": 186, "47": 153, "49": 49,
        "52": 62, "60": 110, "63": 120, "67": 95, "68": 12, "70": 10,
        "72": 58, "74": 28, "77": 43, "P94": 4, "P110": 4, "P172": 1,
    },
    "5구역": {
        "25": 175, "31": 328, "35": 269, "41": 194, "51": 132,
        "61": 140, "71": 16, "78": 5, "116": 2,
    },
}


def normalize_view_pyeong(zone: str, value: str) -> str:
    p = str(value or "").strip().replace("평", "").replace("PY", "").replace("py", "")
    if zone == "2구역":
        return {"45,46": "45~46", "51,52": "51~52", "55,56": "55~56"}.get(p, p)
    if zone == "4구역" and p in {"47A", "47B"}:
        return "47"
    return p


def largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    weight_sum = sum(max(0.0, float(weights.get(g, 0))) for g in GRADES)
    if total <= 0 or weight_sum <= 0:
        return {g: 0 for g in GRADES}
    raw = {g: total * max(0.0, float(weights.get(g, 0))) / weight_sum for g in GRADES}
    out = {g: int(raw[g]) for g in GRADES}
    left = total - sum(out.values())
    order = sorted(GRADES, key=lambda g: (raw[g] - out[g], -GRADES.index(g)), reverse=True)
    for g in order[:left]:
        out[g] += 1
    return out


def pct(n: float, d: float) -> float:
    return round(n / d * 100, 2) if d else 0.0


data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
view_groups = defaultdict(lambda: {
    "sample_count": 0,
    "angle_sum": 0.0,
    "min_angle": None,
    "max_angle": None,
    "grade_counts": {g: 0 for g in GRADES},
    "source_types": set(),
})

for row in data.get("rows", []):
    zone = str(row.get("구역", "")).strip()
    pyeong = normalize_view_pyeong(zone, row.get("평형", ""))
    key = (zone, pyeong)
    g = view_groups[key]
    sample_count = int(row.get("계산단위", 0) or 0)
    g["sample_count"] += sample_count
    g["angle_sum"] += float(row.get("평균조망각", 0) or 0) * sample_count
    mn = float(row.get("최소조망각", 0) or 0)
    mx = float(row.get("최대조망각", 0) or 0)
    g["min_angle"] = mn if g["min_angle"] is None else min(g["min_angle"], mn)
    g["max_angle"] = mx if g["max_angle"] is None else max(g["max_angle"], mx)
    for grade in GRADES:
        g["grade_counts"][grade] += int((row.get("등급별건수") or {}).get(grade, 0) or 0)
    raw_types = str(row.get("원본유닛타입", "") or "").split("/")
    g["source_types"].update(t.strip() for t in raw_types if t.strip())

rows = []
zone_summaries = []
unmatched = []

for zone in ["2구역", "3구역", "4구역", "5구역"]:
    planned = ACTUAL_COUNTS[zone]
    zone_grade_actual = {g: 0 for g in GRADES}
    zone_angle_sum = 0.0
    modeled_households = 0
    total_planned = sum(planned.values())

    for pyeong, actual_count in planned.items():
        vg = view_groups.get((zone, pyeong))
        if not vg or vg["sample_count"] <= 0:
            unmatched.append({"구역": zone, "평형": pyeong, "실제세대수": actual_count, "사유": "조망 폴리곤/층표본 없음"})
            continue

        sample_count = vg["sample_count"]
        avg_angle = vg["angle_sum"] / sample_count
        grade_actual = largest_remainder(actual_count, vg["grade_counts"])
        for grade in GRADES:
            zone_grade_actual[grade] += grade_actual[grade]
        modeled_households += actual_count
        zone_angle_sum += avg_angle * actual_count

        rows.append({
            "구역": zone,
            "평형": pyeong,
            "실제세대수": actual_count,
            "조망표본수": sample_count,
            "원본유닛타입": " / ".join(sorted(vg["source_types"])),
            "평균조망각": round(avg_angle, 2),
            "최소조망각": round(vg["min_angle"] or 0, 2),
            "최대조망각": round(vg["max_angle"] or 0, 2),
            **{f"{grade}_{GRADE_LABELS[grade]}_세대": grade_actual[grade] for grade in GRADES},
            **{f"{grade}_{GRADE_LABELS[grade]}_pct": pct(grade_actual[grade], actual_count) for grade in GRADES},
        })

    zone_summaries.append({
        "구역": zone,
        "계획세대수": total_planned,
        "조망모델반영세대수": modeled_households,
        "미반영세대수": total_planned - modeled_households,
        "조망모델커버리지_pct": pct(modeled_households, total_planned),
        "실제세대수가중평균조망각": round(zone_angle_sum / modeled_households, 2) if modeled_households else 0,
        **{f"{grade}_세대": zone_grade_actual[grade] for grade in GRADES},
        **{f"{grade}_pct": pct(zone_grade_actual[grade], modeled_households) for grade in GRADES},
    })

rows.sort(key=lambda r: (int(r["구역"][0]), int(''.join(ch for ch in r["평형"] if ch.isdigit()) or 9999), r["평형"]))

output = {
    "generatedAt": data.get("generatedAt"),
    "source": "data/simultaneous_conservative_view_by_pyeong.json",
    "method": {
        "viewAngles": "2·3·4·5구역 동시 차폐 계산 결과",
        "riverLine": "hangang_line_all.geojson",
        "facadeSampleStepM": 8,
        "angleStepDeg": 1,
        "weighting": "평형 내부의 조망등급 비율은 층별 조망표본으로 산정하고, 평형 간·구역 전체 집계는 ZONE_SALES_PLAN 실제 세대수로 재가중",
        "excluded": "조망 폴리곤이 없는 펜트하우스·일부 평형은 구역 평균에서 제외",
    },
    "zoneSummary": zone_summaries,
    "unmatched": unmatched,
    "rows": rows,
}
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# CSV
import csv
flat_rows = rows
if flat_rows:
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)

lines = [
    "# 실제 신축 세대수 가중 보수적 한강 조망각", "",
    "- 조망각: 2·3·4·5구역 동시 차폐, 보수적 한강라인, 8m 외벽표본, 1도 단위",
    "- 평형별 세대수: 앱 ZONE_SALES_PLAN 실제 분양 세대수",
    "- 펜트하우스·조망 폴리곤 미작성 평형은 별도 미반영 표시", "",
    "## 구역 요약", "",
    "| 구역 | 계획세대 | 조망반영 | 미반영 | 커버리지 | 실제세대 가중 평균각 | 특A | A | B | C | D | E |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for z in zone_summaries:
    lines.append(
        f"| {z['구역']} | {z['계획세대수']:,} | {z['조망모델반영세대수']:,} | {z['미반영세대수']:,} | "
        f"{z['조망모델커버리지_pct']:.2f}% | {z['실제세대수가중평균조망각']:.2f}° | "
        f"{z['특A급_pct']:.2f}% | {z['A급_pct']:.2f}% | {z['B급_pct']:.2f}% | "
        f"{z['C급_pct']:.2f}% | {z['D급_pct']:.2f}% | {z['E급_pct']:.2f}% |"
    )
lines += ["", "## 평형별", "", "| 구역 | 평형 | 실제세대 | 표본 | 평균각 | 특A | A | B | C | D | E |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
for r in rows:
    lines.append(
        f"| {r['구역']} | {r['평형']} | {r['실제세대수']:,} | {r['조망표본수']:,} | {r['평균조망각']:.2f}° | "
        f"{r['특A급_100도 이상_pct']:.2f}% | {r['A급_81~99도_pct']:.2f}% | {r['B급_61~80도_pct']:.2f}% | "
        f"{r['C급_41~60도_pct']:.2f}% | {r['D급_21~40도_pct']:.2f}% | {r['E급_20도 이하_pct']:.2f}% |"
    )
lines += ["", "## 조망모델 미반영 평형", "", "| 구역 | 평형 | 실제세대 | 사유 |", "|---|---:|---:|---|"]
for r in unmatched:
    lines.append(f"| {r['구역']} | {r['평형']} | {r['실제세대수']:,} | {r['사유']} |")
OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({"zoneSummary": zone_summaries, "unmatched": unmatched, "rowCount": len(rows)}, ensure_ascii=False, indent=2))
