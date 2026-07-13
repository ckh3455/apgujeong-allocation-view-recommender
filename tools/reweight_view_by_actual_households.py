#!/usr/bin/env python3
import csv
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

# 조망분석은 분양자격과 무관하게 물리적으로 존재하는 모든 세대를 포함합니다.
# 조합원·일반분양·임대·펜트하우스를 모두 합친 총세대수입니다.
ALL_PHYSICAL_COUNTS = {
    "2구역": {
        "25": 313,  # 임대
        "32": 256, "37": 61, "41": 429, "45~46": 389, "51~52": 333,
        "55~56": 156, "60": 225, "65": 99, "70": 38, "79": 114, "87": 122,
        "P88": 4, "P95~97": 26, "P112~134": 4, "P174~175": 2,
    },
    "3구역": {
        # 27PY = 분양 490 + 임대 508, 38PY = 분양 608 + 임대 100
        "27": 998, "38": 708, "42": 1457, "50": 358, "58": 564,
        "67": 550, "71": 80, "82": 248, "91": 80, "103": 78,
        "82P": 37, "91P": 8, "103P": 5, "110P": 2, "183P": 2,
    },
    "4구역": {
        # 총 1,662세대 = 분양대상 1,463 + 임대 199.
        # 임대 199세대는 59㎡ 계열(공급 25평)로 합산합니다.
        "25": 248, "34": 73, "40": 406, "43": 186, "47": 153, "49": 49,
        "52": 62, "60": 110, "63": 120, "67": 95, "68": 12, "70": 10,
        "72": 58, "74": 28, "77": 43, "P94": 4, "P110": 4, "P172": 1,
    },
    "5구역": {
        # 25PY = 분양대상 175 + 임대 136
        "25": 311, "31": 328, "35": 269, "41": 194, "51": 132,
        "61": 140, "71": 16, "78": 5, "116": 2,
    },
}

EXPECTED_TOTALS = {"2구역": 2571, "3구역": 5175, "4구역": 1662, "5구역": 1397}


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
    planned = ALL_PHYSICAL_COUNTS[zone]
    total_planned = sum(planned.values())
    if total_planned != EXPECTED_TOTALS[zone]:
        raise ValueError(f"{zone} 총세대수 불일치: {total_planned} != {EXPECTED_TOTALS[zone]}")

    zone_grade_modeled = {g: 0 for g in GRADES}
    zone_angle_sum = 0.0
    modeled_households = 0

    for pyeong, actual_count in planned.items():
        vg = view_groups.get((zone, pyeong))
        if not vg or vg["sample_count"] <= 0:
            unmatched.append({
                "구역": zone,
                "평형": pyeong,
                "전체세대수": actual_count,
                "조망각상태": "미산정",
                "사유": "현재 GeoJSON에 해당 평형의 독립 유닛 폴리곤/층표본 없음",
            })
            rows.append({
                "구역": zone,
                "평형": pyeong,
                "전체세대수": actual_count,
                "조망각산정세대수": 0,
                "조망각미산정세대수": actual_count,
                "조망표본수": 0,
                "원본유닛타입": "",
                "평균조망각": "",
                "최소조망각": "",
                "최대조망각": "",
                **{f"{grade}_{GRADE_LABELS[grade]}_세대": 0 for grade in GRADES},
                **{f"{grade}_{GRADE_LABELS[grade]}_pct": "" for grade in GRADES},
            })
            continue

        sample_count = vg["sample_count"]
        avg_angle = vg["angle_sum"] / sample_count
        grade_actual = largest_remainder(actual_count, vg["grade_counts"])
        for grade in GRADES:
            zone_grade_modeled[grade] += grade_actual[grade]
        modeled_households += actual_count
        zone_angle_sum += avg_angle * actual_count

        rows.append({
            "구역": zone,
            "평형": pyeong,
            "전체세대수": actual_count,
            "조망각산정세대수": actual_count,
            "조망각미산정세대수": 0,
            "조망표본수": sample_count,
            "원본유닛타입": " / ".join(sorted(vg["source_types"])),
            "평균조망각": round(avg_angle, 2),
            "최소조망각": round(vg["min_angle"] or 0, 2),
            "최대조망각": round(vg["max_angle"] or 0, 2),
            **{f"{grade}_{GRADE_LABELS[grade]}_세대": grade_actual[grade] for grade in GRADES},
            **{f"{grade}_{GRADE_LABELS[grade]}_pct": pct(grade_actual[grade], actual_count) for grade in GRADES},
        })

    unmodeled = total_planned - modeled_households
    zone_summaries.append({
        "구역": zone,
        "전체물리세대수": total_planned,
        "조망각산정세대수": modeled_households,
        "조망각미산정세대수": unmodeled,
        "조망각산정커버리지_pct": pct(modeled_households, total_planned),
        "산정세대가중평균조망각": round(zone_angle_sum / modeled_households, 2) if modeled_households else 0,
        **{f"{grade}_산정세대": zone_grade_modeled[grade] for grade in GRADES},
        **{f"{grade}_전체세대대비_pct": pct(zone_grade_modeled[grade], total_planned) for grade in GRADES},
        "미산정_전체세대대비_pct": pct(unmodeled, total_planned),
    })

rows.sort(key=lambda r: (
    int(r["구역"][0]),
    int("".join(ch for ch in r["평형"] if ch.isdigit()) or 9999),
    r["평형"],
))

output = {
    "generatedAt": data.get("generatedAt"),
    "source": "data/simultaneous_conservative_view_by_pyeong.json",
    "method": {
        "viewAngles": "2·3·4·5구역 전체 유닛 폴리곤 동시 차폐 계산 결과",
        "riverLine": "hangang_line_all.geojson",
        "facadeSampleStepM": 8,
        "angleStepDeg": 1,
        "population": "조합원·일반분양·임대·펜트하우스를 포함한 모든 물리적 세대",
        "weighting": "평형 내부 조망등급은 층별 표본분포, 평형·구역 집계는 전체 물리 세대수로 재가중",
        "unmodeledHandling": "독립 유닛 폴리곤이 없는 세대는 임의 각도를 부여하지 않고 미산정으로 분모에 유지",
    },
    "zoneSummary": zone_summaries,
    "unmatched": unmatched,
    "rows": rows,
}
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if rows:
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

lines = [
    "# 모든 물리 세대 기준 보수적 한강 조망각", "",
    "- 대상: 조합원·일반분양·임대·펜트하우스 전체 세대",
    "- 계산: 2·3·4·5구역 동시 차폐, 보수적 한강라인, 외벽표본 8m, 방위각 1도",
    "- 독립 폴리곤이 없는 평형은 추정각을 만들지 않고 미산정으로 표시", "",
    "## 구역 요약", "",
    "| 구역 | 전체세대 | 산정세대 | 미산정 | 커버리지 | 산정세대 가중 평균각 | 특A | A | B | C | D | E |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for z in zone_summaries:
    lines.append(
        f"| {z['구역']} | {z['전체물리세대수']:,} | {z['조망각산정세대수']:,} | {z['조망각미산정세대수']:,} | "
        f"{z['조망각산정커버리지_pct']:.2f}% | {z['산정세대가중평균조망각']:.2f}° | "
        f"{z['특A급_전체세대대비_pct']:.2f}% | {z['A급_전체세대대비_pct']:.2f}% | "
        f"{z['B급_전체세대대비_pct']:.2f}% | {z['C급_전체세대대비_pct']:.2f}% | "
        f"{z['D급_전체세대대비_pct']:.2f}% | {z['E급_전체세대대비_pct']:.2f}% |"
    )

lines += [
    "", "## 평형별", "",
    "| 구역 | 평형 | 전체세대 | 산정 | 미산정 | 표본 | 평균각 | 특A | A | B | C | D | E |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for r in rows:
    avg_text = f"{r['평균조망각']:.2f}°" if isinstance(r["평균조망각"], (int, float)) else "미산정"
    def fpct(grade):
        value = r[f"{grade}_{GRADE_LABELS[grade]}_pct"]
        return f"{value:.2f}%" if isinstance(value, (int, float)) else "-"
    lines.append(
        f"| {r['구역']} | {r['평형']} | {r['전체세대수']:,} | {r['조망각산정세대수']:,} | "
        f"{r['조망각미산정세대수']:,} | {r['조망표본수']:,} | {avg_text} | "
        f"{fpct('특A급')} | {fpct('A급')} | {fpct('B급')} | {fpct('C급')} | {fpct('D급')} | {fpct('E급')} |"
    )

lines += ["", "## 조망각 미산정 세대", "", "| 구역 | 평형 | 세대수 | 사유 |", "|---|---:|---:|---|"]
for r in unmatched:
    lines.append(f"| {r['구역']} | {r['평형']} | {r['전체세대수']:,} | {r['사유']} |")
OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({
    "zoneSummary": zone_summaries,
    "unmatched": unmatched,
    "rowCount": len(rows),
}, ensure_ascii=False, indent=2))
