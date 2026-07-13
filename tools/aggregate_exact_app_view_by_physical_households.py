#!/usr/bin/env python3
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "view_summary.json"
OUT_JSON = ROOT / "data" / "exact_app_view_by_physical_households.json"
OUT_CSV = ROOT / "data" / "exact_app_view_by_physical_households.csv"
OUT_MD = ROOT / "data" / "exact_app_view_by_physical_households.md"

GRADES = ["특A급", "A급", "B급", "C급", "D급", "E급"]

# 조합원·일반분양·임대·펜트하우스를 모두 포함한 물리적 전체 세대수.
ALL_PHYSICAL_COUNTS = {
    "2구역": {
        "25": 313,
        "32": 256, "37": 61, "41": 429, "45~46": 389, "51~52": 333,
        "55~56": 156, "60": 225, "65": 99, "70": 38, "79": 114, "87": 122,
        "P88": 4, "P95~97": 26, "P112~134": 4, "P174~175": 2,
    },
    "3구역": {
        "27": 998, "38": 708, "42": 1457, "50": 358, "58": 564,
        "67": 550, "71": 80, "82": 248, "91": 80, "103": 78,
        "82P": 37, "91P": 8, "103P": 5, "110P": 2, "183P": 2,
    },
    "4구역": {
        "25": 248, "34": 73, "40": 406, "43": 186, "47": 153, "49": 49,
        "52": 62, "60": 110, "63": 120, "67": 95, "68": 12, "70": 10,
        "72": 58, "74": 28, "77": 43, "P94": 4, "P110": 4, "P172": 1,
    },
    "5구역": {
        "25": 311, "31": 328, "35": 269, "41": 194, "51": 132,
        "61": 140, "71": 16, "78": 5, "116": 2,
    },
}
EXPECTED_TOTALS = {"2구역": 2571, "3구역": 5175, "4구역": 1662, "5구역": 1397}


def normalize_pyeong(zone: str, raw: str) -> str:
    value = str(raw or "").strip().replace("평", "").replace("PY", "").replace("py", "")
    if zone == "2구역":
        return {"45,46": "45~46", "51,52": "51~52", "55,56": "55~56"}.get(value, value)
    if zone == "4구역" and value in {"47A", "47B"}:
        return "47"
    return value


def multiplicity(raw: str) -> int:
    parts = [p.strip() for p in str(raw or "").split(",") if p.strip()]
    return max(1, len(parts))


def grade(angle: float) -> str:
    if angle >= 100:
        return "특A급"
    if angle >= 81:
        return "A급"
    if angle >= 61:
        return "B급"
    if angle >= 41:
        return "C급"
    if angle >= 21:
        return "D급"
    return "E급"


def pct(n: float, d: float) -> float:
    return round(n / d * 100, 2) if d else 0.0


def largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    weight_sum = sum(float(weights.get(g, 0)) for g in GRADES)
    if total <= 0 or weight_sum <= 0:
        return {g: 0 for g in GRADES}
    raw = {g: total * float(weights.get(g, 0)) / weight_sum for g in GRADES}
    result = {g: int(raw[g]) for g in GRADES}
    remaining = total - sum(result.values())
    order = sorted(GRADES, key=lambda g: (raw[g] - result[g], -GRADES.index(g)), reverse=True)
    for g in order[:remaining]:
        result[g] += 1
    return result


data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
if data.get("source", {}).get("calculationMode") != "conservative":
    raise ValueError("view_summary.json이 보수적 한강라인 계산 결과가 아닙니다.")
replaced = set(str(v) for v in data.get("source", {}).get("replacedZones", []))
if replaced != {"2", "3", "4", "5"}:
    raise ValueError(f"2·3·4·5구역 전체 재계산 결과가 아닙니다: replacedZones={sorted(replaced)}")

samples = defaultdict(lambda: {
    "weight": 0,
    "angle_sum": 0.0,
    "grade_weights": {g: 0 for g in GRADES},
    "min": None,
    "max": None,
    "raw_types": set(),
    "polygon_count": 0,
})

for row in data.get("rows", []):
    zone = str(row.get("zone", "")).strip()
    zone_id = str(row.get("zoneId", "")).strip()
    if zone not in ALL_PHYSICAL_COUNTS or zone_id not in {"2", "3", "4", "5"}:
        continue
    raw_type = str(row.get("unitType", "")).strip()
    pyeong = normalize_pyeong(zone, raw_type)
    key = (zone, pyeong)
    target = samples[key]
    target["raw_types"].add(raw_type)
    target["polygon_count"] += 1
    unit_multiplier = multiplicity(raw_type)
    for band in row.get("floorBands", []) or []:
        start = max(1, int(band.get("start", 1) or 1))
        end = min(int(row.get("floors", start) or start), int(band.get("end", start) or start))
        floor_count = max(0, end - start + 1)
        weight = floor_count * unit_multiplier
        angle = float(band.get("viewAngle", 0) or 0)
        target["weight"] += weight
        target["angle_sum"] += angle * weight
        target["grade_weights"][grade(angle)] += weight
        target["min"] = angle if target["min"] is None else min(target["min"], angle)
        target["max"] = angle if target["max"] is None else max(target["max"], angle)

rows = []
zone_summary = []
for zone in ["2구역", "3구역", "4구역", "5구역"]:
    counts = ALL_PHYSICAL_COUNTS[zone]
    if sum(counts.values()) != EXPECTED_TOTALS[zone]:
        raise ValueError(f"{zone} 총세대수 불일치")
    zone_grade_counts = {g: 0 for g in GRADES}
    modeled = 0
    angle_sum = 0.0

    for pyeong, household_count in counts.items():
        sample = samples.get((zone, pyeong))
        if not sample or sample["weight"] <= 0:
            rows.append({
                "구역": zone, "평형": pyeong, "계산단위": household_count,
                "평균조망각": "미산정",
                "특A급(100도 이상)": "-", "A급(81~100도)": "-", "A급 이상 소계": "-",
                "B급(61~80도)": "-", "B급이상 소계": "-", "C급(41~60도)": "-",
                "D급(21~40도)": "-", "E급(20도 이하)": "-", "C급이하 소계": "-",
                "조망표본수": 0, "유닛폴리곤수": 0, "원본유닛타입": "",
            })
            continue

        avg = sample["angle_sum"] / sample["weight"]
        actual_grade_counts = largest_remainder(household_count, sample["grade_weights"])
        for g in GRADES:
            zone_grade_counts[g] += actual_grade_counts[g]
        modeled += household_count
        angle_sum += avg * household_count

        special = pct(actual_grade_counts["특A급"], household_count)
        a = pct(actual_grade_counts["A급"], household_count)
        b = pct(actual_grade_counts["B급"], household_count)
        c = pct(actual_grade_counts["C급"], household_count)
        d = pct(actual_grade_counts["D급"], household_count)
        e = pct(actual_grade_counts["E급"], household_count)
        rows.append({
            "구역": zone,
            "평형": pyeong,
            "계산단위": household_count,
            "평균조망각": round(avg, 2),
            "특A급(100도 이상)": special,
            "A급(81~100도)": a,
            "A급 이상 소계": round(special + a, 2),
            "B급(61~80도)": b,
            "B급이상 소계": round(special + a + b, 2),
            "C급(41~60도)": c,
            "D급(21~40도)": d,
            "E급(20도 이하)": e,
            "C급이하 소계": round(c + d + e, 2),
            "조망표본수": sample["weight"],
            "유닛폴리곤수": sample["polygon_count"],
            "원본유닛타입": " / ".join(sorted(sample["raw_types"])),
        })

    total = EXPECTED_TOTALS[zone]
    unmodeled = total - modeled
    zone_summary.append({
        "구역": zone,
        "전체세대수": total,
        "각도산정세대수": modeled,
        "미산정세대수": unmodeled,
        "산정률": pct(modeled, total),
        "산정세대가중평균조망각": round(angle_sum / modeled, 2) if modeled else 0,
        **{f"{g}_전체세대대비_pct": pct(zone_grade_counts[g], total) for g in GRADES},
        "미산정_전체세대대비_pct": pct(unmodeled, total),
    })

rows.sort(key=lambda r: (
    int(str(r["구역"])[0]),
    int("".join(ch for ch in str(r["평형"]) if ch.isdigit()) or 9999),
    str(r["평형"]),
))

output = {
    "generatedAt": data.get("generatedAt"),
    "source": {
        "file": "data/view_summary.json",
        "engine": "현재 APGUJEONG-VIEW v55 브라우저 엔진",
        "calculationMode": "conservative",
        "riverLine": "hangang_line_all.geojson",
        "zonesCalculated": ["2", "3", "4", "5"],
    },
    "population": "조합원·일반분양·임대·펜트하우스를 포함한 모든 물리적 세대",
    "gradeRule": {
        "특A급": "100도 이상", "A급": "81~99도", "B급": "61~80도",
        "C급": "41~60도", "D급": "21~40도", "E급": "20도 이하",
    },
    "zoneSummary": zone_summary,
    "rows": rows,
}
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

headers = [
    "구역", "평형", "계산단위", "평균조망각", "특A급(100도 이상)", "A급(81~100도)",
    "A급 이상 소계", "B급(61~80도)", "B급이상 소계", "C급(41~60도)",
    "D급(21~40도)", "E급(20도 이하)", "C급이하 소계",
]
with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

lines = [
    "# 압구정 뷰 v55 표시각 기준 평형별 조망각", "",
    "- 현재 압구정 뷰 v55 브라우저 엔진의 보수적 한강라인 표시각을 그대로 추출",
    "- 대상: 조합원·일반분양·임대·펜트하우스를 포함한 모든 물리적 세대", "",
    "| " + " | ".join(headers) + " |",
    "|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|",
]
for r in rows:
    values = []
    for h in headers:
        v = r[h]
        if h == "평균조망각" and isinstance(v, (int, float)):
            values.append(f"{v:.2f}°")
        elif h not in {"구역", "평형", "계산단위", "평균조망각"} and isinstance(v, (int, float)):
            values.append(f"{v:.2f}%")
        else:
            values.append(str(v))
    lines.append("| " + " | ".join(values) + " |")
OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({"zoneSummary": zone_summary, "rowCount": len(rows)}, ensure_ascii=False, indent=2))
