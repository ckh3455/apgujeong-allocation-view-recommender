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


def normalize_pyeong(zone: str, raw: str) -> str:
    value = str(raw or "").strip().replace("평", "").replace("PY", "").replace("py", "")
    if zone == "2구역":
        return {"45,46": "45~46", "51,52": "51~52", "55,56": "55~56"}.get(value, value)
    if zone == "4구역" and value in {"47A", "47B"}:
        return "47"
    return value


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


data = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
if data.get("source", {}).get("calculationMode") != "conservative":
    raise ValueError("view_summary.json이 보수적 한강라인 계산 결과가 아닙니다.")
replaced = set(str(v) for v in data.get("source", {}).get("replacedZones", []))
if replaced != {"2", "3", "4", "5"}:
    raise ValueError(f"2·3·4·5구역 전체 재계산 결과가 아닙니다: replacedZones={sorted(replaced)}")

# 조망표본수 = 유닛 폴리곤별 실제 적용 층수의 합계입니다.
# '45,46'처럼 쉼표가 있는 타입도 폴리곤 1개·층 1개당 표본 1개로 계산합니다.
samples = defaultdict(lambda: {
    "sample_count": 0,
    "angle_sum": 0.0,
    "grade_counts": {g: 0 for g in GRADES},
    "min": None,
    "max": None,
    "raw_types": set(),
    "polygon_count": 0,
})

for row in data.get("rows", []):
    zone = str(row.get("zone", "")).strip()
    zone_id = str(row.get("zoneId", "")).strip()
    if zone_id not in {"2", "3", "4", "5"}:
        continue

    raw_type = str(row.get("unitType", "")).strip()
    pyeong = normalize_pyeong(zone, raw_type)
    key = (zone, pyeong)
    target = samples[key]
    target["raw_types"].add(raw_type)
    target["polygon_count"] += 1

    for band in row.get("floorBands", []) or []:
        start = max(1, int(band.get("start", 1) or 1))
        end = min(int(row.get("floors", start) or start), int(band.get("end", start) or start))
        floor_count = max(0, end - start + 1)
        angle = float(band.get("viewAngle", 0) or 0)

        target["sample_count"] += floor_count
        target["angle_sum"] += angle * floor_count
        target["grade_counts"][grade(angle)] += floor_count
        target["min"] = angle if target["min"] is None else min(target["min"], angle)
        target["max"] = angle if target["max"] is None else max(target["max"], angle)

rows = []
zone_summary = []
for (zone, pyeong), sample in samples.items():
    count = sample["sample_count"]
    if count <= 0:
        continue

    special = pct(sample["grade_counts"]["특A급"], count)
    a = pct(sample["grade_counts"]["A급"], count)
    b = pct(sample["grade_counts"]["B급"], count)
    c = pct(sample["grade_counts"]["C급"], count)
    d = pct(sample["grade_counts"]["D급"], count)
    e = pct(sample["grade_counts"]["E급"], count)

    rows.append({
        "구역": zone,
        "평형": pyeong,
        "계산단위": count,
        "평균조망각": round(sample["angle_sum"] / count, 2),
        "특A급(100도 이상)": special,
        "A급(81~100도)": a,
        "A급 이상 소계": round(special + a, 2),
        "B급(61~80도)": b,
        "B급이상 소계": round(special + a + b, 2),
        "C급(41~60도)": c,
        "D급(21~40도)": d,
        "E급(20도 이하)": e,
        "C급이하 소계": round(c + d + e, 2),
        "유닛폴리곤수": sample["polygon_count"],
        "최소조망각": sample["min"],
        "최대조망각": sample["max"],
        "원본유닛타입": " / ".join(sorted(sample["raw_types"])),
    })

rows.sort(key=lambda r: (
    int(str(r["구역"])[0]),
    int("".join(ch for ch in str(r["평형"]) if ch.isdigit()) or 9999),
    str(r["평형"]),
))

for zone in ["2구역", "3구역", "4구역", "5구역"]:
    zone_rows = [r for r in rows if r["구역"] == zone]
    count = sum(r["계산단위"] for r in zone_rows)
    weighted_angle = sum(r["평균조망각"] * r["계산단위"] for r in zone_rows)
    zone_summary.append({
        "구역": zone,
        "조망표본수": count,
        "평형수": len(zone_rows),
        "표본가중평균조망각": round(weighted_angle / count, 2) if count else 0,
    })

output = {
    "generatedAt": data.get("generatedAt"),
    "source": {
        "file": "data/view_summary.json",
        "engine": "현재 APGUJEONG-VIEW v55 브라우저 엔진",
        "calculationMode": "conservative",
        "riverLine": "hangang_line_all.geojson",
        "zonesCalculated": ["2", "3", "4", "5"],
    },
    "calculationUnit": "유닛 폴리곤별 적용 층수의 합계. 폴리곤 1개·층 1개당 조망표본 1개",
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
    "# 압구정 뷰 v55 조망표본 기준 평형별 조망각", "",
    "- 계산단위: 유닛 폴리곤별 적용 층수 합계",
    "- 실제 세대수 가중치 사용 안 함",
    "- 쉼표 복합 타입도 폴리곤 1개·층 1개당 표본 1개", "",
    "| " + " | ".join(headers) + " |",
    "|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|",
]
for r in rows:
    values = []
    for h in headers:
        v = r[h]
        if h == "평균조망각":
            values.append(f"{v:.2f}°")
        elif h not in {"구역", "평형", "계산단위"}:
            values.append(f"{v:.2f}%")
        else:
            values.append(str(v))
    lines.append("| " + " | ".join(values) + " |")
OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({"zoneSummary": zone_summary, "rowCount": len(rows)}, ensure_ascii=False, indent=2))
