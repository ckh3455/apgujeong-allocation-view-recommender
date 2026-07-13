#!/usr/bin/env python3
# Re-run after embedded price build completed.
import json
from collections import defaultdict
from datetime import datetime, timezone
from audit_recorded_floor_prices import ROOT, XLSX_PATH, SHEET_NAME, TARGET_ZONES, read_sheet_rows, find_header, row_dict, normalize_zone, parse_int

OUT = ROOT / 'data' / 'duplicate_unit_keys_audit.json'
rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
header_idx, headers = find_header(rows)
groups = defaultdict(list)
for excel_row, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
    item = row_dict(headers, raw)
    zone = normalize_zone(item.get('구역'))
    if zone not in TARGET_ZONES:
        continue
    complex_name = str(item.get('단지명') or '').strip()
    dong = parse_int(item.get('동'))
    ho = parse_int(item.get('호'))
    if zone == '2구역' and complex_name == '신현대' and dong == 112 and ho is None and str(item.get('2026')).strip() == '69.38':
        ho = 206
    if not complex_name or dong is None or ho is None:
        continue
    groups[(zone, complex_name, dong, ho)].append({
        'excelRow': excel_row,
        '구역': zone,
        '단지명': complex_name,
        '동': dong,
        '호': ho,
        '평형': item.get('평형'),
        '전용면적': item.get('전용면적(㎡)') or item.get('전용면적'),
        '대지지분': item.get('대지지분(평)') or item.get('대지지분'),
        '2026': item.get('2026'),
    })
dups = [{'key': {'구역': k[0], '단지명': k[1], '동': k[2], '호': k[3]}, 'rows': v} for k, v in groups.items() if len(v) > 1]
result = {'generatedAt': datetime.now(timezone.utc).isoformat(), 'duplicateKeyCount': len(dups), 'duplicates': dups}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
