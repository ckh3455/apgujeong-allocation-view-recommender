#!/usr/bin/env python3
"""Audit whether recorded 2026 prices follow the app's floor adjustment rule.

Uses only the Python standard library to read the XLSX package directly.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = ROOT / "data" / "main_data.xlsx"
OUT_JSON = ROOT / "data" / "floor_price_audit.json"
OUT_CSV = ROOT / "data" / "floor_price_audit_mismatches.csv"
OUT_MD = ROOT / "data" / "floor_price_audit.md"
SHEET_NAME = "공동주택 공시가격"
YEAR = "2026"
SPREAD_RATE = 0.10
TARGET_ZONES = {"2구역", "3구역", "4구역", "5구역"}

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "pr": PKG_REL_NS}


def col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "")
    if not letters:
        return 0
    value = 0
    for ch in letters.group(0):
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def normalize_header(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def parse_numeric(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def parse_int(value):
    number = parse_numeric(value)
    if number is None:
        return None
    return int(round(number))


def normalize_zone(value) -> str:
    text = str(value or "").strip().replace(" ", "")
    match = re.search(r"([2345])구역", text)
    return f"{match.group(1)}구역" if match else text


def resolve_sheet_path(zf: zipfile.ZipFile, wanted_name: str) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pr:Relationship", NS)
    }
    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        if sheet.attrib.get("name") == wanted_name:
            rel_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            target = rel_map.get(rel_id, "")
            return str(PurePosixPath("xl") / target).replace("xl/../", "")
    available = [s.attrib.get("name", "") for s in workbook.findall("m:sheets/m:sheet", NS)]
    raise RuntimeError(f"시트 '{wanted_name}'를 찾지 못했습니다. 사용 가능: {available}")


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for si in root.findall("m:si", NS):
        values.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))
    return values


def cell_value(cell: ET.Element, shared: list[str]):
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", NS))
    node = cell.find("m:v", NS)
    if node is None or node.text is None:
        return None
    raw = node.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return raw == "1"
    if cell_type in {"str", "e"}:
        return raw
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw


def read_sheet_rows(path: Path, sheet_name: str) -> list[list]:
    with zipfile.ZipFile(path) as zf:
        shared = load_shared_strings(zf)
        sheet_path = resolve_sheet_path(zf, sheet_name)
        root = ET.fromstring(zf.read(sheet_path))
        rows = []
        for row in root.findall("m:sheetData/m:row", NS):
            values = {}
            max_col = -1
            for cell in row.findall("m:c", NS):
                idx = col_index(cell.attrib.get("r", ""))
                values[idx] = cell_value(cell, shared)
                max_col = max(max_col, idx)
            if max_col >= 0:
                rows.append([values.get(i) for i in range(max_col + 1)])
            else:
                rows.append([])
        return rows


def find_header(rows: list[list]) -> tuple[int, list[str]]:
    required = {"구역", "단지명", "동", "호", YEAR}
    for idx, row in enumerate(rows[:50]):
        headers = [normalize_header(v) for v in row]
        if required.issubset(set(headers)):
            return idx, headers
    raise RuntimeError(f"필수 헤더를 찾지 못했습니다: {sorted(required)}")


def row_dict(headers: list[str], row: list) -> dict:
    return {headers[i]: row[i] if i < len(row) else None for i in range(len(headers)) if headers[i]}


def expected_price(low_price: float, low_floor: int, peak_floor: int, top_floor: int, floor: int):
    denominator = max(1, peak_floor - low_floor)
    peak_price = low_price * (1 + SPREAD_RATE)
    top_equal_floor = min(top_floor - 2, peak_floor - 1)
    top_equal_price = low_price + (peak_price - low_price) * ((top_equal_floor - low_floor) / denominator)
    if low_floor <= floor <= peak_floor:
        return low_price + (peak_price - low_price) * ((floor - low_floor) / denominator)
    if floor == top_floor:
        return top_equal_price
    return None


def tolerance_for(prices: list[float]) -> tuple[float, float, str]:
    median = statistics.median(prices) if prices else 0
    if median >= 100_000:
        return 1_100_000.0, 5_100_000.0, "원 단위로 추정(엄격 ±110만원, 근사 ±510만원)"
    return 0.011, 0.051, "억원 단위로 추정(엄격 ±0.011억, 근사 ±0.051억)"


def main() -> int:
    rows = read_sheet_rows(XLSX_PATH, SHEET_NAME)
    header_idx, headers = find_header(rows)

    records = []
    for excel_row, raw in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        item = row_dict(headers, raw)
        zone = normalize_zone(item.get("구역"))
        if zone not in TARGET_ZONES:
            continue
        dong = parse_int(item.get("동"))
        ho = parse_int(item.get("호"))
        price = parse_numeric(item.get(YEAR))
        if dong is None or ho is None or price is None or ho < 100:
            continue
        records.append(
            {
                "excelRow": excel_row,
                "zone": zone,
                "complex": str(item.get("단지명") or "").strip(),
                "dong": dong,
                "ho": ho,
                "floor": ho // 100,
                "line": ho % 100,
                "price": price,
            }
        )

    strict_tol, near_tol, unit_note = tolerance_for([r["price"] for r in records])
    groups = defaultdict(list)
    for record in records:
        groups[(record["zone"], record["complex"], record["dong"], record["line"])].append(record)

    zone_summary = {
        zone: {
            "recordedRows": 0,
            "lineGroups": 0,
            "comparableGroups": 0,
            "strictMatchGroups": 0,
            "nearMatchGroups": 0,
            "mismatchGroups": 0,
            "comparableCells": 0,
            "strictMatchCells": 0,
            "nearMatchCells": 0,
            "mismatchCells": 0,
            "peakRuleComparableGroups": 0,
            "peakRuleMatchGroups": 0,
            "topRuleComparableGroups": 0,
            "topRuleMatchGroups": 0,
            "notComparableGroups": 0,
            "absoluteDifferences": [],
        }
        for zone in sorted(TARGET_ZONES)
    }
    for record in records:
        zone_summary[record["zone"]]["recordedRows"] += 1

    mismatch_rows = []
    group_details = []

    for key, group in sorted(groups.items()):
        zone, complex_name, dong, line = key
        summary = zone_summary[zone]
        summary["lineGroups"] += 1
        group = sorted(group, key=lambda r: (r["floor"], r["ho"], r["excelRow"]))
        by_floor = defaultdict(list)
        for record in group:
            by_floor[record["floor"]].append(record)
        floors = sorted(by_floor)
        top_floor = max(floors)
        low_floor = 1 if 1 in by_floor else min(floors)
        peak_floor = top_floor - 1
        if peak_floor not in by_floor:
            below = [f for f in floors if f < top_floor]
            peak_floor = max(below) if below else None

        detail = {
            "zone": zone,
            "complex": complex_name,
            "dong": dong,
            "line": line,
            "topFloor": top_floor,
            "lowFloor": low_floor,
            "peakFloor": peak_floor,
            "rowCount": len(group),
        }

        if top_floor < 3 or peak_floor is None or peak_floor <= low_floor:
            summary["notComparableGroups"] += 1
            detail["status"] = "not_comparable"
            group_details.append(detail)
            continue

        low_price = by_floor[low_floor][0]["price"]
        summary["comparableGroups"] += 1
        cell_diffs = []
        strict_group = True
        near_group = True

        for record in group:
            expected = expected_price(low_price, low_floor, peak_floor, top_floor, record["floor"])
            if expected is None:
                continue
            diff = record["price"] - expected
            abs_diff = abs(diff)
            cell_diffs.append(abs_diff)
            summary["comparableCells"] += 1
            summary["absoluteDifferences"].append(abs_diff)
            if abs_diff <= strict_tol:
                summary["strictMatchCells"] += 1
                cell_status = "strict"
            elif abs_diff <= near_tol:
                summary["nearMatchCells"] += 1
                strict_group = False
                cell_status = "near"
            else:
                summary["mismatchCells"] += 1
                strict_group = False
                near_group = False
                cell_status = "mismatch"
                mismatch_rows.append(
                    {
                        **record,
                        "expectedPrice": expected,
                        "difference": diff,
                        "absDifference": abs_diff,
                        "lowFloor": low_floor,
                        "lowPrice": low_price,
                        "peakFloor": peak_floor,
                        "topFloor": top_floor,
                    }
                )
            if cell_status == "near":
                near_group = near_group and True

        if strict_group:
            summary["strictMatchGroups"] += 1
            detail["status"] = "strict"
        elif near_group:
            summary["nearMatchGroups"] += 1
            detail["status"] = "near"
        else:
            summary["mismatchGroups"] += 1
            detail["status"] = "mismatch"

        detail["lowPrice"] = low_price
        detail["maxAbsDifference"] = max(cell_diffs) if cell_diffs else None

        if peak_floor in by_floor:
            summary["peakRuleComparableGroups"] += 1
            actual_peak = by_floor[peak_floor][0]["price"]
            expected_peak = low_price * 1.10
            peak_diff = abs(actual_peak - expected_peak)
            detail["actualPeakPrice"] = actual_peak
            detail["expectedPeakPrice"] = expected_peak
            detail["peakDifference"] = peak_diff
            if peak_diff <= strict_tol:
                summary["peakRuleMatchGroups"] += 1

        if top_floor in by_floor:
            summary["topRuleComparableGroups"] += 1
            actual_top = by_floor[top_floor][0]["price"]
            expected_top = expected_price(low_price, low_floor, peak_floor, top_floor, top_floor)
            top_diff = abs(actual_top - expected_top)
            detail["actualTopPrice"] = actual_top
            detail["expectedTopPrice"] = expected_top
            detail["topDifference"] = top_diff
            if top_diff <= strict_tol:
                summary["topRuleMatchGroups"] += 1

        group_details.append(detail)

    for zone, summary in zone_summary.items():
        diffs = summary.pop("absoluteDifferences")
        comparable_groups = summary["comparableGroups"]
        comparable_cells = summary["comparableCells"]
        strict_or_near_groups = summary["strictMatchGroups"] + summary["nearMatchGroups"]
        strict_or_near_cells = summary["strictMatchCells"] + summary["nearMatchCells"]
        summary["strictGroupRatePct"] = round(summary["strictMatchGroups"] / comparable_groups * 100, 1) if comparable_groups else None
        summary["withinNearGroupRatePct"] = round(strict_or_near_groups / comparable_groups * 100, 1) if comparable_groups else None
        summary["strictCellRatePct"] = round(summary["strictMatchCells"] / comparable_cells * 100, 1) if comparable_cells else None
        summary["withinNearCellRatePct"] = round(strict_or_near_cells / comparable_cells * 100, 1) if comparable_cells else None
        summary["peakRuleMatchRatePct"] = round(summary["peakRuleMatchGroups"] / summary["peakRuleComparableGroups"] * 100, 1) if summary["peakRuleComparableGroups"] else None
        summary["topRuleMatchRatePct"] = round(summary["topRuleMatchGroups"] / summary["topRuleComparableGroups"] * 100, 1) if summary["topRuleComparableGroups"] else None
        summary["medianAbsDifference"] = statistics.median(diffs) if diffs else None
        summary["maxAbsDifference"] = max(diffs) if diffs else None
        summary["recordedAccordingToRule"] = bool(
            comparable_groups
            and summary["withinNearGroupRatePct"] >= 99.0
            and summary["withinNearCellRatePct"] >= 99.5
        )

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workbook": str(XLSX_PATH.relative_to(ROOT)),
        "sheet": SHEET_NAME,
        "year": YEAR,
        "rule": {
            "group": "구역+단지명+동+호라인",
            "peakFloor": "최고층 바로 아래층(자료가 없으면 최고층 미만 최상층)",
            "lowFloor": "1층(없으면 최저층)",
            "spread": SPREAD_RATE,
            "middleFloors": "저층 기준가격부터 최고가격층까지 10%를 직선 균등배분",
            "topFloor": "최고가격층보다 한 층 아래 가격과 동일",
        },
        "tolerance": {"strict": strict_tol, "near": near_tol, "unitNote": unit_note},
        "zones": zone_summary,
        "mismatchRowCount": len(mismatch_rows),
        "largestMismatches": sorted(mismatch_rows, key=lambda r: r["absDifference"], reverse=True)[:100],
        "groups": group_details,
    }
    OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_headers = [
        "zone", "complex", "dong", "line", "ho", "floor", "excelRow", "price",
        "expectedPrice", "difference", "absDifference", "lowFloor", "lowPrice", "peakFloor", "topFloor",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(sorted(mismatch_rows, key=lambda r: (r["zone"], r["complex"], r["dong"], r["line"], r["floor"])))

    md = [
        "# 2026년 층별 공시가격 기록 검증",
        "",
        f"- 대상: `{XLSX_PATH.relative_to(ROOT)}` / `{SHEET_NAME}` 시트",
        f"- 허용오차: {unit_note}",
        "- 검증기준: 현재 앱의 `apply_2026_floor_rank_adjustment()`와 동일",
        "",
        "| 구역 | 비교그룹 | 엄격일치 | 근사포함 일치 | 불일치 | 셀 근사포함 일치율 | 최고가격층 10% 일치율 | 꼭대기층 규칙 일치율 | 판정 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for zone in sorted(zone_summary):
        s = zone_summary[zone]
        md.append(
            f"| {zone} | {s['comparableGroups']:,} | {s['strictMatchGroups']:,} | "
            f"{s['strictMatchGroups'] + s['nearMatchGroups']:,} | {s['mismatchGroups']:,} | "
            f"{s['withinNearCellRatePct'] if s['withinNearCellRatePct'] is not None else '-'}% | "
            f"{s['peakRuleMatchRatePct'] if s['peakRuleMatchRatePct'] is not None else '-'}% | "
            f"{s['topRuleMatchRatePct'] if s['topRuleMatchRatePct'] is not None else '-'}% | "
            f"{'기준대로 기록' if s['recordedAccordingToRule'] else '불일치 존재'} |"
        )
    md.extend([
        "",
        f"불일치 셀: **{len(mismatch_rows):,}건**",
        "",
        "세부 불일치는 `data/floor_price_audit_mismatches.csv`를 확인합니다.",
    ])
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"zones": zone_summary, "mismatchRowCount": len(mismatch_rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        raise
