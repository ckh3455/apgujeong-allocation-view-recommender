#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path

from audit_recorded_floor_prices import (
    ROOT, XLSX_PATH, SHEET_NAME, read_sheet_rows, find_header,
    row_dict, normalize_zone, parse_int, parse_numeric,
)

OUT = ROOT / "data" / "zone2_row_count_audit.json"
rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
header_idx, headers = find_header(rows)

zone2_rows = []
invalid_required = []
valid_rows = []
for excel_row, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
    item = row_dict(headers, raw)
    zone = normalize_zone(item.get("구역"))
    if zone != "2구역":
        continue
    record = {
        "excelRow": excel_row,
        "구역": item.get("구역"),
        "단지명": item.get("단지명"),
        "동_raw": item.get("동"),
        "호_raw": item.get("호"),
        "동": parse_int(item.get("동")),
        "호": parse_int(item.get("호")),
        "2026_raw": item.get("2026"),
        "2026": parse_numeric(item.get("2026")),
    }
    zone2_rows.append(record)
    missing = []
    if not str(item.get("단지명") or "").strip():
        missing.append("단지명")
    if record["동"] is None:
        missing.append("동")
    if record["호"] is None:
        missing.append("호")
    if missing:
        record["invalidFields"] = missing
        invalid_required.append(record)
    else:
        valid_rows.append(record)

seen = {}
duplicates = []
for record in valid_rows:
    key = (str(record["단지명"] or "").strip(), record["동"], record["호"])
    if key in seen:
        duplicates.append({"key": key, "firstExcelRow": seen[key], "duplicateExcelRow": record["excelRow"]})
    else:
        seen[key] = record["excelRow"]

result = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "workbook": str(XLSX_PATH.relative_to(ROOT)),
    "sheet": SHEET_NAME,
    "headerExcelRow": header_idx + 1,
    "totalRowsAfterHeader": len(rows) - header_idx - 1,
    "zone2RawRows": len(zone2_rows),
    "zone2ValidRows": len(valid_rows),
    "zone2InvalidRows": len(invalid_required),
    "zone2DuplicateUnitKeys": len(duplicates),
    "invalidRows": invalid_required,
    "duplicates": duplicates,
    "firstZone2Row": zone2_rows[0] if zone2_rows else None,
    "lastZone2Row": zone2_rows[-1] if zone2_rows else None,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
