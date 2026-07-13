#!/usr/bin/env python3
import csv
from collections import defaultdict
from pathlib import Path

from audit_recorded_floor_prices import (
    ROOT, XLSX_PATH, SHEET_NAME, YEAR, TARGET_ZONES,
    read_sheet_rows, find_header, row_dict, normalize_zone,
    parse_int, parse_numeric,
)

OUT = ROOT / "data" / "rank_prices_2026_embedded.csv"
SPREAD = 0.10

rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
header_idx, headers = find_header(rows)
records = []

for excel_row, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
    item = row_dict(headers, raw)
    zone = normalize_zone(item.get("구역"))
    if zone not in TARGET_ZONES:
        continue
    complex_name = str(item.get("단지명") or "").strip()
    dong = parse_int(item.get("동"))
    ho = parse_int(item.get("호"))
    price = parse_numeric(item.get(YEAR))

    # 원본 내장 자료 입력 보정 1: 2구역 신현대 112동 206호의 호수 공란
    if zone == "2구역" and complex_name == "신현대" and dong == 112 and ho is None and price == 69.38:
        ho = 206

    # 원본 내장 자료 입력 보정 2: 3구역 현대1,2차 21동 705호가 두 번 기록됨.
    # 701~706호 배열상 두 번째 705호(엑셀 9790행)는 706호입니다.
    if zone == "3구역" and complex_name == "현대1,2차" and dong == 21 and ho == 705 and excel_row == 9790:
        ho = 706

    if not complex_name or dong is None or ho is None or price is None:
        continue
    floor = ho // 100 if ho >= 100 else None
    line = ho % 100
    if floor is None:
        continue
    records.append({
        "excel_row": excel_row,
        "zone": zone,
        "complex": complex_name,
        "dong": dong,
        "ho": ho,
        "floor": floor,
        "line": line,
        "public_price": float(price),
    })

groups = defaultdict(list)
for rec in records:
    groups[(rec["zone"], rec["complex"], rec["dong"], rec["line"])].append(rec)

output = []
for group_key, group in groups.items():
    by_floor = {rec["floor"]: rec for rec in group}
    available_floors = sorted(by_floor)
    top_floor = max(available_floors)
    low_floor = 1 if 1 in by_floor else min(available_floors)
    intended_peak_floor = top_floor - 1
    if intended_peak_floor not in by_floor:
        below_top = [f for f in available_floors if f < top_floor]
        intended_peak_floor = max(below_top) if below_top else low_floor

    low_price = by_floor[low_floor]["public_price"]
    denominator = max(1, intended_peak_floor - low_floor)
    peak_price = low_price * (1 + SPREAD)
    top_equal_floor = min(top_floor - 2, intended_peak_floor - 1)
    top_equal_price = low_price + (peak_price - low_price) * ((top_equal_floor - low_floor) / denominator)

    for rec in group:
        floor = rec["floor"]
        adjusted = rec["public_price"]
        if low_floor <= floor <= intended_peak_floor:
            adjusted = low_price + (peak_price - low_price) * ((floor - low_floor) / denominator)
        elif floor == top_floor:
            adjusted = top_equal_price
        output.append({
            "구역": rec["zone"],
            "단지명": rec["complex"],
            "동": rec["dong"],
            "호": rec["ho"],
            "원본공시가격_2026_억": f'{rec["public_price"]:.6f}',
            "순위기준가격_2026_억": f'{adjusted:.6f}',
            "저층기준층": low_floor,
            "최고가격층": intended_peak_floor,
            "최고층": top_floor,
            "보정기준": f'{top_floor}층 10% 보정',
        })

output.sort(key=lambda r: (int(str(r["구역"]).replace("구역", "")), r["단지명"], r["동"], r["호"]))
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(output[0].keys()))
    writer.writeheader()
    writer.writerows(output)

counts = defaultdict(int)
for row in output:
    counts[row["구역"]] += 1
print({"output": str(OUT.relative_to(ROOT)), "rows": len(output), "zone_counts": dict(counts)})
