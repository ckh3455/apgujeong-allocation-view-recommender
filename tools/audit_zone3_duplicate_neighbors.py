#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from audit_recorded_floor_prices import ROOT, XLSX_PATH, SHEET_NAME, read_sheet_rows, find_header, row_dict

OUT = ROOT / 'data' / 'zone3_duplicate_neighbors.json'
rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
header_idx, headers = find_header(rows)
items = []
for excel_row in range(9783, 9797):
    raw = rows[excel_row - 1] if 0 <= excel_row - 1 < len(rows) else []
    item = row_dict(headers, raw)
    items.append({
        'excelRow': excel_row,
        '구역': item.get('구역'),
        '단지명': item.get('단지명'),
        '동': item.get('동'),
        '호': item.get('호'),
        '평형': item.get('평형'),
        '전용면적': item.get('전용면적(㎡)') or item.get('전용면적'),
        '2026': item.get('2026'),
    })
result = {'generatedAt': datetime.now(timezone.utc).isoformat(), 'rows': items}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
