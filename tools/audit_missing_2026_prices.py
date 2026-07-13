#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from audit_recorded_floor_prices import (
    ROOT, XLSX_PATH, SHEET_NAME, YEAR, TARGET_ZONES,
    read_sheet_rows, find_header, row_dict, normalize_zone,
    parse_int, parse_numeric,
)

OUT = ROOT / "data" / "floor_price_missing_2026.json"

rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
header_idx, headers = find_header(rows)
summary = {z: {"validUnitRows": 0, "pricedRows": 0, "missing2026Rows": 0} for z in sorted(TARGET_ZONES)}
missing = []

for excel_row, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
    item = row_dict(headers, raw)
    zone = normalize_zone(item.get("구역"))
    if zone not in TARGET_ZONES:
        continue
    dong = parse_int(item.get("동"))
    ho = parse_int(item.get("호"))
    if dong is None or ho is None:
        continue
    summary[zone]["validUnitRows"] += 1
    price = parse_numeric(item.get(YEAR))
    if price is None:
        summary[zone]["missing2026Rows"] += 1
        missing.append({
            "excelRow": excel_row,
            "zone": zone,
            "complex": str(item.get("단지명") or "").strip(),
            "dong": dong,
            "ho": ho,
            "raw2026": item.get(YEAR),
        })
    else:
        summary[zone]["pricedRows"] += 1

OUT.write_text(json.dumps({
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "workbook": str(XLSX_PATH.relative_to(ROOT)),
    "sheet": SHEET_NAME,
    "year": YEAR,
    "zones": summary,
    "missingRows": missing,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({"zones": summary, "missingRows": missing}, ensure_ascii=False, indent=2))
