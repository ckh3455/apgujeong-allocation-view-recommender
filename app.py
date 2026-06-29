import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# =========================
# 기본 시트 설정
# Secrets에 같은 이름이 있으면 Secrets 값이 우선합니다.
# =========================
DEFAULT_MAIN_SHEET_ID = "1QGSM-mICX9KYa5Izym6sFKVaWwO-o0j86V-KmJ-w0IM"
DEFAULT_MAIN_GID = 0
DEFAULT_MAIN_WORKSHEET_NAME = "공동주택 공시가격"
DEFAULT_MAX_DATA_ROWS = 10337
LOCAL_WORKSHEET_NAME = "공동주택 공시가격"
RANK_YEAR = "2026"

MULTI_OWNER_PAIRS_2ZONE = [
    [(101, 208), (105, 806)],
    [(121, 1104), (125, 606)],
    [(117, 303), (126, 204)],
    [(112, 205), (127, 905)],
    [(101, 401), (109, 801)],
    [(113, 301), (119, 1003)],
    [(114, 503), (126, 1105)],
    [(106, 506), (106, 903)],
]

YEAR_RE = re.compile(r"^\d{4}$")


APP_DIR = Path(__file__).resolve().parent
VIEW_SUMMARY_PATH = APP_DIR / "data" / "view_summary.json"
DATA_DIR = APP_DIR / "data"
LOCAL_DATA_CANDIDATES = [
    APP_DIR / "main_data.xlsx",
    APP_DIR / "main_data.xls",
    APP_DIR / "main_data.csv",
    APP_DIR / "압구정 건축물대장 정리 (14).xlsx",
    DATA_DIR / "main_data.xlsx",
    DATA_DIR / "main_data.xls",
    DATA_DIR / "main_data.csv",
    DATA_DIR / "압구정 건축물대장 정리 (14).xlsx",
    DATA_DIR / "public_prices.xlsx",
    DATA_DIR / "public_prices.csv",
    DATA_DIR / "공동주택_공시가격.xlsx",
    DATA_DIR / "공동주택_공시가격.csv",
]


st.set_page_config(page_title="압구정 분양가능 평형·조망 추천", layout="centered")

st.markdown(
    """
    <style>
      .block-container { max-width: 1060px; padding-top: 2.2rem; padding-bottom: 2.5rem; }
      h1 { font-size: 1.72rem !important; line-height: 1.35 !important; }
      .note-box {
        border: 1px solid rgba(49,51,63,.14);
        border-radius: 10px;
        background: rgba(250,250,252,.78);
        padding: 12px 14px;
        line-height: 1.65;
        font-size: .94rem;
      }
      .result-main {
        margin: 12px 0 8px 0;
        padding: 14px 15px;
        border-left: 5px solid #0b63d1;
        background: rgba(11,99,209,.06);
        line-height: 1.7;
        font-size: 1.04rem;
        font-weight: 750;
      }
      .best-card {
        margin: 12px 0 10px 0;
        border: 1px solid rgba(11,99,209,.20);
        border-radius: 10px;
        background: linear-gradient(180deg, rgba(11,99,209,.08), rgba(11,99,209,.035));
        padding: 14px 15px;
        line-height: 1.75;
      }
      .best-title {
        color: #0b63d1;
        font-size: 1.08rem;
        font-weight: 900;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# 로컬 데이터 파일
# =========================
MAX_DATA_ROWS = DEFAULT_MAX_DATA_ROWS


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.replace({"": pd.NA, " ": pd.NA})
    if "구역" not in df.columns and "주소" in df.columns:
        df = df.rename(columns={"주소": "구역"})

    empty_generated = [c for c in df.columns if str(c).startswith("_col") and df[c].isna().all()]
    if empty_generated:
        df = df.drop(columns=empty_generated)
    return df


def dataframe_from_raw_rows(raw: pd.DataFrame) -> pd.DataFrame:
    """엑셀/CSV에서 헤더 행을 찾아 기존 구글시트와 같은 DataFrame 형태로 정리합니다."""
    raw = raw.dropna(how="all").copy()
    if raw.empty:
        raise ValueError("데이터 파일에 내용이 없습니다.")

    values = raw.fillna("").astype(str).values.tolist()
    header_row_index = None
    required_sets = [
        {"구역", "단지명", "동", "호"},
        {"주소", "단지명", "동", "호"},
    ]
    for i, row in enumerate(values[:50]):
        cells = [str(x).strip() for x in row]
        if any(req.issubset(set(cells)) for req in required_sets):
            header_row_index = i
            break
    if header_row_index is None:
        header_row_index = 0

    header = [str(x).strip() if str(x).strip() else f"_col{j}" for j, x in enumerate(values[header_row_index])]
    df = pd.DataFrame(values[header_row_index + 1:], columns=header)
    return normalize_columns(df)


def read_local_table(file_obj_or_path) -> pd.DataFrame:
    """앱 폴더의 엑셀/CSV 또는 화면 업로드 파일을 읽습니다."""
    name = str(getattr(file_obj_or_path, "name", file_obj_or_path)).lower()
    if name.endswith((".xlsx", ".xls")):
        try:
            raw = pd.read_excel(file_obj_or_path, sheet_name=LOCAL_WORKSHEET_NAME, header=None, dtype=str, engine=None)
        except ValueError as e:
            raise ValueError(f"엑셀에서 '{LOCAL_WORKSHEET_NAME}' 탭을 찾지 못했습니다: {e}")
        return dataframe_from_raw_rows(raw)

    if name.endswith(".csv"):
        last_error = None
        for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
            try:
                if hasattr(file_obj_or_path, "seek"):
                    file_obj_or_path.seek(0)
                raw = pd.read_csv(file_obj_or_path, header=None, dtype=str, encoding=enc)
                return dataframe_from_raw_rows(raw)
            except Exception as e:
                last_error = e
        raise ValueError(f"CSV 파일을 읽지 못했습니다: {last_error}")

    raise ValueError("지원 형식은 .xlsx, .xls, .csv 입니다.")


def find_local_data_file() -> Path | None:
    for p in LOCAL_DATA_CANDIDATES:
        if p.exists() and p.is_file():
            return p

    # 파일명이 달라도 앱 폴더 또는 data 폴더에 있는 엑셀/CSV를 자동 탐색합니다.
    # 엑셀은 read_local_table()에서 '공동주택 공시가격' 탭이 있는지 다시 검증합니다.
    for folder in (DATA_DIR, APP_DIR):
        if not folder.exists():
            continue
        for pattern in ("*.xlsx", "*.xls", "*.csv"):
            for p in sorted(folder.glob(pattern)):
                if p.name.startswith("~$"):
                    continue
                return p
    return None


@st.cache_data(show_spinner=False)
def load_from_local_file(path_text: str) -> pd.DataFrame:
    return read_local_table(Path(path_text))


def clean_main_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.iloc[:MAX_DATA_ROWS].copy()
    required = ["구역", "단지명", "동", "호"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    df["구역"] = df["구역"].astype(str).str.strip()
    df["단지명"] = df["단지명"].astype(str).str.strip()
    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")
    df["호"] = pd.to_numeric(df["호"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["구역", "단지명", "동", "호"]).copy()
    df = df[(df["구역"].str.lower() != "nan") & (df["단지명"].str.lower() != "nan")].copy()
    return df


def detect_year_cols(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        s = str(c).strip()
        if YEAR_RE.match(s):
            out.append(s)
        else:
            try:
                f = float(s)
                if f.is_integer() and YEAR_RE.match(str(int(f))):
                    out.append(str(int(f)))
            except Exception:
                pass
    return sorted(set(out), key=lambda x: int(x))


def coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def filter_year_cols_with_data(df: pd.DataFrame, year_cols: list[str]) -> list[str]:
    return [y for y in year_cols if int(pd.to_numeric(df[y], errors="coerce").notna().sum()) > 0]


def find_first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def detect_pyeong_col(df: pd.DataFrame) -> str | None:
    return find_first_col(df, ["평형", "평형(평)", "평", "평형_평", "평형평"])


def fmt_pyeong(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    s = str(value).strip()
    if not s:
        return "-"
    if "평" in s:
        return s
    try:
        f = float(s)
        return f"{int(f)}평" if abs(f - round(f)) < 1e-6 else f"{f:.1f}평"
    except Exception:
        return f"{s}평"


def fmt_rank(rank, total) -> str:
    if pd.isna(rank) or pd.isna(total):
        return "-"
    return f"{int(rank):,}/{int(total):,}"


def parse_rank_text(value: str) -> int | None:
    try:
        return int(str(value).split("/")[0].replace(",", "").strip())
    except Exception:
        return None


def safe_display_text(value) -> str:
    return "-" if value is None else str(value).replace("~", "∼")


def infer_floor_from_ho(ho: int) -> int | None:
    try:
        ho = int(ho)
    except Exception:
        return None
    return ho // 100 if ho >= 100 else None


def infer_line_from_ho(ho: int) -> int | None:
    try:
        return int(ho) % 100
    except Exception:
        return None


def normalize_zone_key(zone_name: str) -> str:
    txt = str(zone_name).strip().replace(" ", "")
    m = re.search(r"(\d+)구역", txt)
    return f"{int(m.group(1))}구역" if m else txt


def pyeong_number(value) -> int | None:
    nums = re.findall(r"\d+", str(value or ""))
    if not nums:
        return None
    return int(nums[0])


def pyeong_range(value) -> tuple[int | None, int | None]:
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))]
    if not nums:
        return None, None
    return min(nums), max(nums)


def selected_unit_label(dong: int, ho: int) -> str:
    return f"{int(dong)}동 {int(ho)}호"


MULTI_OWNER_LOOKUP_2ZONE = {
    (dong, ho): f"2구역 복수소유 {i + 1}"
    for i, pair in enumerate(MULTI_OWNER_PAIRS_2ZONE)
    for dong, ho in pair
}


MULTI_OWNER_PAIR_LABELS_2ZONE = {
    f"2구역 복수소유 {i + 1}": " / ".join(selected_unit_label(d, h) for d, h in pair)
    for i, pair in enumerate(MULTI_OWNER_PAIRS_2ZONE)
}


def multi_owner_key_for_row(row) -> str:
    if normalize_zone_key(row.get("구역", "")) != "2구역":
        return f"SINGLE:{row.name}"
    try:
        dong = int(row.get("동"))
        ho = int(row.get("호"))
    except Exception:
        return f"SINGLE:{row.name}"
    return MULTI_OWNER_LOOKUP_2ZONE.get((dong, ho), f"SINGLE:{row.name}")


def multi_owner_key_for_unit(zone: str, dong: int, ho: int, row_index=None) -> str:
    if normalize_zone_key(zone) == "2구역":
        key = MULTI_OWNER_LOOKUP_2ZONE.get((int(dong), int(ho)))
        if key:
            return key
    return f"SINGLE:{row_index}" if row_index is not None else f"SINGLE:{zone}:{dong}:{ho}"


def build_rank_universe(df_num: pd.DataFrame, zone: str, year: str) -> pd.DataFrame:
    """복수소유자는 합산 1명으로 묶은 구역 내 순위 산정용 테이블을 만듭니다."""
    zone_df = df_num[df_num["구역"] == zone].copy()
    if zone_df.empty:
        return pd.DataFrame()

    rank_price_col = "__rank_price_2026" if str(year) == RANK_YEAR and "__rank_price_2026" in zone_df.columns else year
    zone_df["__owner_key"] = zone_df.apply(multi_owner_key_for_row, axis=1)
    zone_df["__rank_price_for_group"] = pd.to_numeric(zone_df[rank_price_col], errors="coerce")
    zone_df["__public_price_for_group"] = pd.to_numeric(zone_df[year], errors="coerce")

    grouped = (
        zone_df.groupby("__owner_key", dropna=False)
        .agg(
            rank_price=("__rank_price_for_group", "sum"),
            public_price=("__public_price_for_group", "sum"),
            unit_count=("__owner_key", "size"),
        )
        .reset_index()
    )
    grouped["is_multi_owner"] = grouped["unit_count"] > 1
    grouped["multi_owner_units"] = grouped["__owner_key"].map(MULTI_OWNER_PAIR_LABELS_2ZONE).fillna("")
    return grouped


def apply_2026_floor_rank_adjustment(df_num: pd.DataFrame) -> pd.DataFrame:
    """
    2026년 공시가격 동률을 감정평가 가능성에 맞춰 순위용으로 보정합니다.

    기준:
    - 같은 구역/단지/동/호라인을 하나의 비교그룹으로 봅니다.
    - 최고층 바로 아래층을 최고 기준으로 둡니다.
      예: 13층 건물은 12층, 12층 건물은 11층.
    - 1층부터 최고 기준층까지는 1층 가격과 최고 기준층 가격 사이를 균등 배분합니다.
    - 꼭대기층은 최고 기준층보다 한 층 아래 가격과 같게 둡니다.
      예: 13층은 11층 가격, 12층은 10층 가격.

    원본 2026 컬럼은 건드리지 않고, 순위 계산용 `__rank_price_2026`만 추가합니다.
    """
    df = df_num.copy()
    if RANK_YEAR not in df.columns:
        return df

    rank_col = "__rank_price_2026"
    note_col = "__rank_price_note_2026"
    df[rank_col] = pd.to_numeric(df[RANK_YEAR], errors="coerce")
    df[note_col] = ""

    df["__floor_no"] = df["호"].map(infer_floor_from_ho)
    df["__line_no"] = df["호"].map(infer_line_from_ho)

    group_cols = ["구역", "단지명", "동", "__line_no"]
    if "평형" in df.columns:
        group_cols.append("평형")

    for _, idx in df.groupby(group_cols, dropna=False).groups.items():
        sub = df.loc[list(idx)].copy()
        floors = pd.to_numeric(sub["__floor_no"], errors="coerce")
        if floors.dropna().empty:
            continue
        top_floor = int(floors.max())
        peak_floor = top_floor - 1
        top_equal_floor = top_floor - 2
        if top_floor < 3:
            continue

        prices = pd.to_numeric(sub[RANK_YEAR], errors="coerce")
        floor1 = prices.loc[floors == 1].dropna()
        peak_price_series = prices.loc[floors == peak_floor].dropna()
        if floor1.empty or peak_price_series.empty:
            continue

        low_price = float(floor1.iloc[0])
        peak_price = float(peak_price_series.iloc[0])
        denominator = max(1, peak_floor - 1)
        top_equal_price = low_price + (peak_price - low_price) * ((top_equal_floor - 1) / denominator)

        for row_idx, floor_value in floors.items():
            if pd.isna(floor_value):
                continue
            floor_i = int(floor_value)
            if 1 <= floor_i <= peak_floor:
                adjusted = low_price + (peak_price - low_price) * ((floor_i - 1) / denominator)
            elif floor_i == top_floor:
                adjusted = top_equal_price
            else:
                continue
            df.at[row_idx, rank_col] = round(float(adjusted), 6)
            df.at[row_idx, note_col] = f"{top_floor}층 보정"

    return df.drop(columns=["__floor_no", "__line_no"], errors="ignore")


def build_rank_table(df_num: pd.DataFrame, year_cols: list[str], zone: str, complex_name: str, dong: int, ho: int) -> pd.DataFrame:
    pick = df_num[
        (df_num["구역"] == zone)
        & (df_num["단지명"] == complex_name)
        & (df_num["동"] == dong)
        & (df_num["호"] == ho)
    ]
    if pick.empty:
        raise ValueError("선택한 동호수를 찾지 못했습니다.")

    pick_row = pick.iloc[0]
    pick_owner_key = multi_owner_key_for_unit(zone, dong, ho, row_index=pick.index[0])

    rows = []
    for y in year_cols:
        rank_universe = build_rank_universe(df_num, zone, y)
        if rank_universe.empty:
            continue
        target = rank_universe[rank_universe["__owner_key"] == pick_owner_key]
        if target.empty:
            continue

        rank_universe["rank"] = pd.to_numeric(rank_universe["rank_price"], errors="coerce").rank(method="min", ascending=False)
        target = rank_universe[rank_universe["__owner_key"] == pick_owner_key].iloc[0]
        price = pd.to_numeric(target.get("public_price", pd.NA), errors="coerce")
        rank_price = pd.to_numeric(target.get("rank_price", pd.NA), errors="coerce")
        if pd.isna(price) or pd.isna(rank_price):
            continue
        rank_value = target.get("rank", pd.NA)
        zone_n = int(rank_universe.shape[0])
        rows.append({
            "연도": int(y),
            "공시가격(억)": float(price),
            "순위기준가격(억)": float(rank_price) if pd.notna(rank_price) else float(price),
            "구역 내 순위": fmt_rank(rank_value, zone_n),
            "순위값": int(rank_value) if pd.notna(rank_value) else None,
            "다주택소유": bool(target.get("is_multi_owner", False)),
            "합산대상": str(target.get("multi_owner_units", "")),
        })
    return pd.DataFrame(rows)


def calc_zone_tie_count(df_num: pd.DataFrame, zone: str, year_col: str, selected_price) -> int:
    try:
        rank_universe = build_rank_universe(df_num, zone, year_col)
        prices = pd.to_numeric(rank_universe["rank_price"], errors="coerce")
        price = pd.to_numeric(selected_price, errors="coerce")
        if pd.notna(price):
            return int((prices == price).sum())
    except Exception:
        pass
    return 1


# =========================
# 분양 가능 평형 계산
# =========================
def extract_base_area_from_type(type_name: str) -> int | None:
    m = re.search(r"(\d+)", str(type_name))
    return int(m.group(1)) if m else None


SUPPLY_AREA_BY_TYPE_4ZONE = {
    "59A": 83.08, "59B": 82.26, "84A": 115.69,
    "96A1": 132.47, "96A2": 132.36, "96A3": 133.42,
    "96B1": 133.31, "96B2": 133.17, "96B3": 132.94,
    "96C1": 132.81, "96C2": 132.71, "96C3": 132.94,
    "105A1": 144.52, "105A2": 144.57, "105A3": 145.22,
    "114A1": 157.54, "114A2": 157.73, "114A3": 157.69,
    "115A": 157.58, "115B": 158.41,
    "120A": 164.51, "120B": 163.78, "120C": 165.14,
    "120D": 164.97, "120E": 164.84, "120F": 165.41, "120G": 164.71,
    "126A1": 172.69, "126A2": 173.66, "126A3": 172.75,
    "147A1": 200.38, "147A2": 201.09, "147A3": 201.08,
    "154A1": 208.54, "154A2": 208.98, "154A3": 209.02,
    "164A1": 222.30, "164A2": 222.81, "164A3": 223.14,
    "166A": 225.33,
    "170A": 231.03, "170B": 230.00,
    "177A1": 240.30, "177A2": 240.51, "177A3": 240.39,
    "178A": 240.34, "178B": 240.00, "178C": 239.87,
    "183A": 246.37, "183B": 246.29, "183C": 247.10,
    "188A1": 254.86, "188A2": 255.07, "188A3": 254.76,
    "D183A": 250.90,
    "P230A": 311.00, "P230B": 310.98, "P230C": 311.16, "P230D": 312.90,
    "P270A": 364.13, "P270B": 364.22, "P270C": 365.95, "P270D": 366.61,
    "P420A": 570.17,
}


def type_to_py_label(type_name: str) -> str:
    t = str(type_name).strip()
    supply_area = SUPPLY_AREA_BY_TYPE_4ZONE.get(t)
    if supply_area is not None:
        py = int(float(supply_area) / 3.3058)
        return f"P{py}평" if re.match(r"^P\d+", t, flags=re.I) else f"{py}평"
    base_area = extract_base_area_from_type(t)
    if base_area is None:
        return t
    py = int(float(base_area) / 3.3058)
    return f"P{py}평" if re.match(r"^P\d+", t, flags=re.I) else f"{py}평"


def unit_from_type(type_name: str, count: int) -> dict:
    py_label = type_to_py_label(type_name)
    supply_area = SUPPLY_AREA_BY_TYPE_4ZONE.get(str(type_name).strip())
    detail = f"{type_name} 공급 {supply_area:.2f}㎡" if supply_area is not None else str(type_name)
    return {"평형": py_label, "세대수": int(count), "세부타입": detail, "소거그룹": py_label}


def make_zone4_units() -> list[dict]:
    raw = [
        ("59A", 18), ("59B", 31), ("84A", 73),
        ("96A1", 35), ("96A2", 35), ("96A3", 37), ("96B1", 63), ("96B2", 63), ("96B3", 66),
        ("96C1", 36), ("96C2", 35), ("96C3", 36),
        ("105A1", 62), ("105A2", 61), ("105A3", 63),
        ("114A1", 45), ("114A2", 44), ("114A3", 45), ("115A", 14), ("115B", 5),
        ("120A", 12), ("120B", 12), ("120C", 5), ("120D", 5), ("120E", 5), ("120F", 5), ("120G", 5),
        ("126A1", 21), ("126A2", 20), ("126A3", 21),
        ("147A1", 36), ("147A2", 36), ("147A3", 38),
        ("154A1", 40), ("154A2", 40), ("154A3", 40),
        ("164A1", 31), ("164A2", 31), ("164A3", 33), ("166A", 12),
        ("170A", 5), ("170B", 5),
        ("177A1", 14), ("177A2", 14), ("177A3", 15), ("178A", 5), ("178B", 5), ("178C", 5),
        ("183A", 12), ("183B", 10), ("183C", 5), ("188A1", 14), ("188A2", 14), ("188A3", 15),
        ("D183A", 1), ("P230A", 1), ("P230B", 1), ("P230C", 1), ("P230D", 1),
        ("P270A", 1), ("P270B", 1), ("P270C", 1), ("P270D", 1), ("P420A", 1),
    ]
    return [unit_from_type(t, c) for t, c in raw]


ZONE_SALES_PLAN = {
    "2구역": {
        "member_count": 1916,
        "general_sale_count": 342,
        "note": "2구역: 분양 소계 2,258세대 - 복수소유 8쌍 합산 후 조합원 1,916명 = 일반분양 342세대",
        "units": [
            {"평형": "32py", "세대수": 256},
            {"평형": "37py", "세대수": 61},
            {"평형": "41py", "세대수": 429},
            {"평형": "45~46py", "세대수": 389},
            {"평형": "51~52py", "세대수": 333},
            {"평형": "55~56py", "세대수": 156},
            {"평형": "60py", "세대수": 225},
            {"평형": "65py", "세대수": 99},
            {"평형": "70py", "세대수": 38},
            {"평형": "79py", "세대수": 114},
            {"평형": "87py", "세대수": 122},
            {"평형": "(P88py)", "세대수": 4},
            {"평형": "(P95~97py)", "세대수": 26},
            {"평형": "(P127~134py)", "세대수": 4},
            {"평형": "(P174~175py)", "세대수": 2},
        ],
    },
    "3구역": {
        "member_count": 3934,
        "general_sale_count": 600,
        "note": "3구역: 일반분양 600세대 / 38PY 임대 100세대 별도 제외",
        "units": [
            {"평형": "27PY", "세대수": 490},
            {"평형": "38PY", "세대수": 608, "임대제외": 100},
            {"평형": "42PY", "세대수": 1457},
            {"평형": "50PY", "세대수": 358},
            {"평형": "58PY", "세대수": 564},
            {"평형": "67PY", "세대수": 550},
            {"평형": "71PY", "세대수": 80},
            {"평형": "82PY", "세대수": 248},
            {"평형": "91PY", "세대수": 80},
            {"평형": "103PY", "세대수": 78},
            {"평형": "82PY(P)", "세대수": 37},
            {"평형": "91PY(P)", "세대수": 8},
            {"평형": "103PY(P)", "세대수": 5},
            {"평형": "110PY(P)", "세대수": 2},
            {"평형": "183PY(P)", "세대수": 2},
        ],
    },
    "4구역": {
        "member_count": 1341,
        "general_sale_count": 122,
        "note": "4구역: 일반분양 122세대 + 조합 1,341세대 / 평형은 공급면적÷3.3058 기준",
        "units": make_zone4_units(),
    },
    "5구역": {
        "member_count": 1232,
        "general_sale_count": 29,
        "note": "5구역 현대안: 총 1,397세대 = 임대 136세대 + 일반분양 29세대 + 조합 1,232세대",
        "units": [
            {"평형": "25py", "세대수": 175, "세부타입": "25(일반) 29세대, 25 146세대", "소거그룹": "25py"},
            {"평형": "31py", "세대수": 328},
            {"평형": "35py", "세대수": 269},
            {"평형": "41py", "세대수": 194},
            {"평형": "51py", "세대수": 132},
            {"평형": "61py", "세대수": 140},
            {"평형": "71py", "세대수": 16},
            {"평형": "78py", "세대수": 5},
            {"평형": "116py", "세대수": 2},
        ],
    },
}

MULTI_OWNER_TOP_RATE = 0.0
TIE_DOWNGRADE_RATE = 0.05


def get_zone_sales_plan(zone_name: str) -> dict | None:
    return ZONE_SALES_PLAN.get(normalize_zone_key(zone_name))


def build_member_available_units(zone_name: str) -> tuple[pd.DataFrame, dict | None]:
    plan = get_zone_sales_plan(zone_name)
    if not plan:
        return pd.DataFrame(), None

    grouped = {}
    order = []
    for item in plan["units"]:
        pyeong = str(item.get("평형", "")).strip()
        group_key = str(item.get("소거그룹", pyeong)).strip()
        if group_key not in grouped:
            grouped[group_key] = {"평형": pyeong or group_key, "분양세대수": 0, "임대제외": 0, "세부타입": []}
            order.append(group_key)

        grouped[group_key]["분양세대수"] += int(item.get("세대수", 0))
        grouped[group_key]["임대제외"] += int(item.get("임대제외", 0))
        detail = str(item.get("세부타입", "")).strip()
        if detail:
            grouped[group_key]["세부타입"].append(f"{detail} {int(item.get('세대수', 0)):,}세대")

    general_left = int(plan.get("general_sale_count", 0))
    rows = []
    for group_key in order:
        g = grouped[group_key]
        total_units = int(g["분양세대수"])
        rental_excluded = int(g.get("임대제외", 0))
        sale_available_units = max(total_units - rental_excluded, 0)
        general_units = min(sale_available_units, general_left)
        member_units = sale_available_units - general_units
        general_left -= general_units

        row = {
            "평형": g["평형"],
            "분양세대수": total_units,
            "임대 제외": rental_excluded,
            "일반분양 제외": general_units,
            "조합원 가능세대": member_units,
        }
        if g["세부타입"]:
            row["세부타입"] = ", ".join(g["세부타입"])
        rows.append(row)
    return pd.DataFrame(rows), plan


def round_count(value: float) -> int:
    return int(float(value) + 0.5)


def sales_competition_adjustment(member_count: int, tie_count: int = 1) -> dict:
    member_count = max(0, int(member_count))
    tie_count = max(1, int(tie_count))
    multi_owner_top_count = round_count(member_count * MULTI_OWNER_TOP_RATE)
    tie_down_count = round_count(tie_count * TIE_DOWNGRADE_RATE)
    tie_down_count = min(tie_down_count, max(0, tie_count - 1))
    return {
        "multi_owner_top_count": multi_owner_top_count,
        "tie_down_count": tie_down_count,
        "effective_tie_count": max(1, tie_count - tie_down_count),
    }


def estimate_expected_pyeong_by_adjusted_rank(zone_name: str, adjusted_rank: int) -> str:
    avail_df, plan = build_member_available_units(zone_name)
    if avail_df.empty or plan is None:
        return "-"

    member_count = int(plan["member_count"])
    adjusted_rank = max(1, min(member_count, int(adjusted_rank)))
    remain_behind = member_count - adjusted_rank

    for _, r in avail_df.iterrows():
        member_units = int(r.get("조합원 가능세대", 0))
        if member_units <= 0:
            continue
        if remain_behind >= member_units:
            remain_behind -= member_units
        else:
            return str(r.get("평형", "-"))
    return "-"


def estimate_pyeong_range_by_rank(zone_name: str, rank_start: int, tie_count: int) -> dict:
    avail_df, plan = build_member_available_units(zone_name)
    if avail_df.empty or plan is None:
        return {"has_plan": False}

    member_count = int(plan["member_count"])
    rank_start = max(1, int(rank_start))
    tie_count = max(1, int(tie_count))

    adj = sales_competition_adjustment(member_count, tie_count)
    multi_owner_top_count = int(adj["multi_owner_top_count"])
    tie_down_count = int(adj["tie_down_count"])
    effective_tie_count = int(adj["effective_tie_count"])

    adjusted_rank_start = min(member_count, rank_start + multi_owner_top_count)
    adjusted_rank_end = min(member_count, adjusted_rank_start + effective_tie_count - 1)
    original_rank_end = min(member_count, rank_start + tie_count - 1)

    ranges = []
    current_pyeong = None
    current_start = None
    current_end = None

    for rank in range(adjusted_rank_start, adjusted_rank_end + 1):
        pyeong = estimate_expected_pyeong_by_adjusted_rank(zone_name, rank)
        if current_pyeong is None:
            current_pyeong = pyeong
            current_start = rank
            current_end = rank
        elif pyeong == current_pyeong:
            current_end = rank
        else:
            ranges.append({
                "동순위 내 순번": format_relative_range(current_start, current_end, adjusted_rank_start),
                "보정 후 전체 순위": format_absolute_range(current_start, current_end),
                "예상평형": current_pyeong,
            })
            current_pyeong = pyeong
            current_start = rank
            current_end = rank

    if current_pyeong is not None:
        ranges.append({
            "동순위 내 순번": format_relative_range(current_start, current_end, adjusted_rank_start),
            "보정 후 전체 순위": format_absolute_range(current_start, current_end),
            "예상평형": current_pyeong,
        })

    unique_pyeongs = []
    for row in ranges:
        if row["예상평형"] not in unique_pyeongs:
            unique_pyeongs.append(row["예상평형"])

    return {
        "has_plan": True,
        "member_count": member_count,
        "general_sale_count": int(plan.get("general_sale_count", 0)),
        "note": plan.get("note", ""),
        "rank_start": rank_start,
        "rank_end": original_rank_end,
        "adjusted_rank_start": adjusted_rank_start,
        "adjusted_rank_end": adjusted_rank_end,
        "multi_owner_top_count": multi_owner_top_count,
        "tie_down_count": tie_down_count,
        "effective_tie_count": max(0, adjusted_rank_end - adjusted_rank_start + 1),
        "unique_pyeongs": unique_pyeongs,
        "ranges_df": pd.DataFrame(ranges),
        "available_df": avail_df,
    }


def format_relative_range(start_rank: int, end_rank: int, base_rank: int) -> str:
    a = start_rank - base_rank + 1
    b = end_rank - base_rank + 1
    return f"{a:,}번째" if a == b else f"{a:,}∼{b:,}번째"


def format_absolute_range(start_rank: int, end_rank: int) -> str:
    return f"{start_rank:,}위" if start_rank == end_rank else f"{start_rank:,}∼{end_rank:,}위"


def render_pyeong_result(range_info: dict) -> None:
    if not range_info.get("has_plan"):
        st.info("이 구역은 아직 분양가능 평형 예측 설정이 없습니다.")
        return

    unique_pyeongs = [safe_display_text(x) for x in range_info.get("unique_pyeongs", []) if str(x).strip() and x != "-"]
    pyeong_text = " / ".join(unique_pyeongs) if unique_pyeongs else "-"

    if len(unique_pyeongs) <= 1:
        st.success(f"예상 가능 평형: {pyeong_text}")
    else:
        st.success(f"예상 가능 평형 범위: {pyeong_text}")

    st.markdown(
        f"""
        <div class="result-main">
          조합원 수 {range_info['member_count']:,}명 /
          일반분양 제외 {range_info['general_sale_count']:,}세대 /
          동률 내 하향지원 제외 {range_info['tie_down_count']:,}세대<br>
          원순위 {format_absolute_range(range_info['rank_start'], range_info['rank_end'])} →
          보정순위 {format_absolute_range(range_info['adjusted_rank_start'], range_info['adjusted_rank_end'])}
        </div>
        """,
        unsafe_allow_html=True,
    )

    ranges_df = range_info.get("ranges_df", pd.DataFrame())
    if isinstance(ranges_df, pd.DataFrame) and not ranges_df.empty:
        st.markdown("#### 동순위 순번별 예상 평형")
        st.dataframe(ranges_df, use_container_width=True, hide_index=True)

    available_df = range_info.get("available_df", pd.DataFrame()).copy()
    if not available_df.empty:
        st.markdown("#### 평형별 조합원 가능 세대")
        st.dataframe(available_df, use_container_width=True, hide_index=True)

    if range_info.get("note"):
        st.caption(range_info["note"])


# =========================
# 조망 추천
# =========================
def load_view_summary() -> list[dict]:
    """조망 요약은 데이터 보정이 잦으므로 매 실행 때 파일을 다시 읽습니다."""
    if not VIEW_SUMMARY_PATH.exists():
        return []
    data = json.loads(VIEW_SUMMARY_PATH.read_text(encoding="utf-8"))
    return list(data.get("rows", []))


def pyeong_numbers(value) -> set[str]:
    return set(re.findall(r"\d+", str(value or "")))


def is_penthouse_pyeong(value) -> bool:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text:
        return False
    # 32py 같은 일반 평형의 'py'는 제외하고, P88 / 82PY(P) / (P95~97py) / P94평 같은 표기만 잡습니다.
    return bool(
        re.search(r"^\(?P\d+", text)
        or re.search(r"PY\(P\)", text)
        or re.search(r"\(P\)", text)
    )


def view_unit_matches_pyeong(unit_type: str, expected_pyeong: str) -> bool:
    # 펜트하우스는 현재 조망 GeoJSON에 별도 입력되지 않았으므로 일반 유닛과 숫자만으로 섞지 않습니다.
    if is_penthouse_pyeong(expected_pyeong):
        return False

    target_nums = pyeong_numbers(expected_pyeong)
    unit_nums = pyeong_numbers(unit_type)
    if not target_nums or not unit_nums:
        return False
    return bool(target_nums & unit_nums)


def zone_id_from_name(zone_name: str) -> str:
    m = re.search(r"(\d+)", str(zone_name or ""))
    return m.group(1) if m else str(zone_name or "")


def find_floor_band(row: dict, target_floor: int) -> dict:
    bands = row.get("floorBands") or []
    if not bands:
        return {
            "start": target_floor,
            "end": target_floor,
            "viewAngle": int(row.get("topFloorViewAngle") or 0),
            "maxGap": 0,
            "mainRange": str(row.get("topFloorRange") or ""),
            "distanceMin": "",
            "distanceMax": "",
        }

    for band in bands:
        if int(band.get("start", 0)) <= target_floor <= int(band.get("end", 0)):
            return band
    return bands[-1]


def compressed_bands_by_view_angle(row: dict, floors: int) -> list[dict]:
    """같은 한강조망각이 이어지는 층은 하나의 층구간으로 묶습니다."""
    raw_bands = row.get("floorBands") or []
    if not raw_bands:
        return [{
            "start": 1,
            "end": floors,
            "viewAngle": int(row.get("topFloorViewAngle") or 0),
            "maxGap": 0,
            "mainRange": str(row.get("topFloorRange") or ""),
            "distanceMin": "",
            "distanceMax": "",
        }]

    bands = sorted(raw_bands, key=lambda b: int(b.get("start", 1)))
    merged: list[dict] = []
    for band in bands:
        item = dict(band)
        item["start"] = max(1, int(item.get("start", 1)))
        item["end"] = min(floors, int(item.get("end", item["start"])))
        item["viewAngle"] = int(item.get("viewAngle") or 0)
        item["maxGap"] = int(item.get("maxGap") or 0)

        if merged and int(merged[-1].get("viewAngle", -1)) == item["viewAngle"] and int(merged[-1].get("end", 0)) + 1 >= item["start"]:
            prev = merged[-1]
            prev["end"] = max(int(prev.get("end", 0)), item["end"])
            prev["maxGap"] = max(int(prev.get("maxGap") or 0), item["maxGap"])

            ranges = []
            for value in [prev.get("mainRange", ""), item.get("mainRange", "")]:
                value = str(value or "").strip()
                if value and value not in ranges:
                    ranges.append(value)
            prev["mainRange"] = " / ".join(ranges)

            mins = [v for v in [prev.get("distanceMin", ""), item.get("distanceMin", "")] if str(v) != ""]
            maxs = [v for v in [prev.get("distanceMax", ""), item.get("distanceMax", "")] if str(v) != ""]
            try:
                if mins:
                    prev["distanceMin"] = min(int(v) for v in mins)
                if maxs:
                    prev["distanceMax"] = max(int(v) for v in maxs)
            except Exception:
                pass
        else:
            merged.append(item)
    return merged


def build_view_candidates(
    view_rows: list[dict],
    zone_name: str,
    possible_pyeongs: list[str],
) -> pd.DataFrame:
    if not view_rows or not possible_pyeongs:
        return pd.DataFrame()

    target_zone_id = zone_id_from_name(zone_name)
    rows = []

    for row in view_rows:
        if str(row.get("zoneId", "")) != target_zone_id:
            continue

        matched_pyeong = None
        for p in possible_pyeongs:
            if view_unit_matches_pyeong(str(row.get("unitType", "")), p):
                matched_pyeong = p
                break
        if not matched_pyeong:
            continue

        floors = max(1, int(row.get("floors") or 1))
        bands = compressed_bands_by_view_angle(row, floors)

        for band in bands:
            start_floor = max(1, int(band.get("start", 1)))
            end_floor = min(floors, int(band.get("end", start_floor)))
            view_angle = int(band.get("viewAngle") or 0)
            max_gap = int(band.get("maxGap") or 0)

            rows.append({
                "추천순위": 0,
                "가능평형": safe_display_text(matched_pyeong),
                "미래동": f"{row.get('dong')}동",
                "배치도 타입": str(row.get("unitType", "")),
                "미래층구간": format_floor_range(start_floor, end_floor),
                "시작층": start_floor,
                "종료층": end_floor,
                "층수": max(0, end_floor - start_floor + 1),
                "최고층": f"{floors}층",
                "한강조망각": view_angle,
                "최대연속각": max_gap,
                "주요각도범위": safe_display_text(band.get("mainRange", "")),
                "조망거리": format_distance_range(band),
                "한강방향": row.get("riverBearingName", ""),
                "fid": row.get("fid", ""),
            })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    total_by_pyeong = out.groupby("가능평형")["층수"].transform("sum")
    out["추첨확률"] = (out["층수"] / total_by_pyeong * 100).fillna(0)
    out["추첨확률"] = out["추첨확률"].map(lambda x: f"{float(x):.1f}%")
    out = out.sort_values(
        ["한강조망각", "최대연속각", "종료층", "가능평형", "미래동", "배치도 타입"],
        ascending=[False, False, False, True, True, True],
    ).reset_index(drop=True)
    out["추천순위"] = out.index + 1
    return out


def format_distance_range(band: dict) -> str:
    mn = band.get("distanceMin", "")
    mx = band.get("distanceMax", "")
    if mn == "" or mx == "":
        return ""
    try:
        mn_i = int(mn)
        mx_i = int(mx)
        return f"{mn_i}m" if mn_i == mx_i else f"{mn_i}∼{mx_i}m"
    except Exception:
        return ""


def format_floor_range(start_floor: int, end_floor: int) -> str:
    return f"{start_floor}층" if start_floor == end_floor else f"{start_floor}∼{end_floor}층"


def safe_accessible_pyeongs(range_info: dict, current_pyeong_value) -> list[str]:
    """예상 가능 평형 중 현재 평형 이상인 평형만 반환합니다."""
    current_min, current_max = pyeong_range(current_pyeong_value)
    current_threshold = current_max if current_max is not None else 0

    out = []
    for p in range_info.get("unique_pyeongs", []):
        lo, hi = pyeong_range(p)
        if lo is None or hi is None:
            continue
        if hi < current_threshold:
            continue
        p = str(p)
        if p and p != "-" and p not in out:
            out.append(p)
    return out


def lower_reference_pyeongs(range_info: dict, current_pyeong_value, primary_pyeongs: list[str]) -> list[str]:
    """예상 가능 평형보다 낮지만 현재 평형 이상인 조망 참고 평형을 반환합니다."""
    available_df = range_info.get("available_df", pd.DataFrame())
    if not isinstance(available_df, pd.DataFrame) or available_df.empty:
        return []

    primary_ranges = [pyeong_range(p) for p in primary_pyeongs]
    primary_lows = [lo for lo, hi in primary_ranges if lo is not None and hi is not None]
    if not primary_lows:
        return []

    lowest_primary = min(primary_lows)
    current_min, current_max = pyeong_range(current_pyeong_value)
    current_threshold = current_max if current_max is not None else 0
    primary_set = {str(p) for p in primary_pyeongs}

    out = []
    for p in available_df["평형"].astype(str).tolist():
        lo, hi = pyeong_range(p)
        if lo is None or hi is None:
            continue
        if hi < current_threshold:
            continue
        if hi >= lowest_primary:
            continue
        if p in primary_set:
            continue
        if p not in out:
            out.append(p)
    return out


def render_penthouse_priority(penthouse_pyeongs: list[str]) -> None:
    if not penthouse_pyeongs:
        return

    display = " / ".join(safe_display_text(p) for p in penthouse_pyeongs)
    st.markdown(
        f"""
        <div class="best-card">
          <div class="best-title">펜트하우스 우선 후보: {display}</div>
          현재 조망 지도에는 펜트하우스 유닛이 별도 입력되어 있지 않지만,
          분양가능 평형이 P 표시 평형에 도달하면 일반층 조망 후보보다 우선 검토합니다.
          펜트하우스는 최상층·특화세대로 보아 조망 우위가 매우 큰 후보입니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    ph_df = pd.DataFrame([
        {
            "우선순위": i + 1,
            "가능평형": safe_display_text(p),
            "구분": "펜트하우스(P)",
            "조망판정": "최상 우선 후보",
            "비고": "조망 GeoJSON 미입력, 일반층 조망표보다 우선 표시",
        }
        for i, p in enumerate(penthouse_pyeongs)
    ])
    st.dataframe(ph_df, use_container_width=True, hide_index=True)


def render_grouped_view_tables(candidates: pd.DataFrame) -> None:
    """가능평형별로 조망 후보를 묶어 표시합니다."""
    if candidates.empty:
        return

    group_names = sorted(
        candidates["가능평형"].dropna().unique().tolist(),
        key=lambda x: (pyeong_number(x) or 0, str(x)),
        reverse=True,
    )

    for pyeong in group_names:
        group = candidates[candidates["가능평형"] == pyeong].copy()
        if group.empty:
            continue

        group = group.sort_values(
            ["한강조망각", "최대연속각", "종료층", "미래동", "배치도 타입"],
            ascending=[False, False, False, True, True],
        ).reset_index(drop=True)
        group.insert(0, "구간순위", group.index + 1)

        total_cases = int(pd.to_numeric(group["층수"], errors="coerce").fillna(0).sum())
        best_angle = int(pd.to_numeric(group["한강조망각"], errors="coerce").max())
        best_gap = int(pd.to_numeric(group["최대연속각"], errors="coerce").max())

        st.markdown(
            f"""
            <div style="
                margin: 18px 0 8px 0;
                padding: 10px 12px;
                border-left: 5px solid #0b63d1;
                background: rgba(11,99,209,.055);
                border-radius: 8px;
                font-weight: 850;
                line-height: 1.55;
            ">
              {safe_display_text(pyeong)} 조망 후보<br>
              <span style="font-weight:650; color:rgba(49,51,63,.78);">
                조망모델 기준 {total_cases:,}개 층구간 / 최고 한강조망각 {best_angle}도 / 최대연속각 {best_gap}도
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        show_cols = [
            "구간순위", "미래동", "배치도 타입", "미래층구간", "층수", "추첨확률", "최고층",
            "한강조망각", "최대연속각", "주요각도범위", "조망거리", "한강방향",
        ]
        st.dataframe(group[show_cols], use_container_width=True, hide_index=True)


def render_view_recommendation(zone_name: str, range_info: dict, current_pyeong_value) -> None:
    st.subheader("조망각 기준 추천")

    if not range_info.get("has_plan"):
        st.info("분양가능 평형 계산 결과가 없어 조망 추천을 만들 수 없습니다.")
        return

    possible_pyeongs = safe_accessible_pyeongs(range_info, current_pyeong_value)
    if not possible_pyeongs:
        st.info("현재 평형 이상에서 내 순위로 안전하게 진입 가능한 평형이 없어 조망 추천을 만들 수 없습니다.")
        return

    reference_pyeongs = lower_reference_pyeongs(range_info, current_pyeong_value, possible_pyeongs)
    penthouse_pyeongs = [p for p in possible_pyeongs if is_penthouse_pyeong(p)]
    normal_pyeongs = [p for p in possible_pyeongs if not is_penthouse_pyeong(p)]

    view_rows = load_view_summary()
    if not view_rows:
        st.warning("조망 요약 데이터가 없습니다. data/view_summary.json 파일을 확인해 주세요.")
        return

    st.caption(
        "현재 선택 호수의 층은 조망 계산에 사용하지 않습니다. "
        "미래 배치도 유닛의 층별 조망각을 계산하되, 같은 조망각이 이어지는 층은 한 구간으로 묶어 표시합니다. "
        "추첨확률은 같은 가능평형 안에서 조망 모델상 동·타입·층구간이 차지하는 층수 비중입니다."
    )

    st.markdown("#### 예상 가능 평형 조망")
    render_penthouse_priority(penthouse_pyeongs)

    candidates = build_view_candidates(view_rows, zone_name, normal_pyeongs)
    if not normal_pyeongs:
        st.caption("안전 진입 가능 평형이 펜트하우스 후보로만 구성되어 일반층 조망표는 생략합니다.")
    elif candidates.empty:
        st.info(
            "예상 가능 평형과 조망 배치도 타입이 매칭되지 않았습니다. "
            "해당 평형의 미래 배치도 유닛이 조망 요약 데이터에 입력되어 있는지 확인해 주세요."
        )
    else:
        matched_pyeongs = set(candidates["가능평형"].astype(str).unique().tolist())
        missing_pyeongs = [p for p in normal_pyeongs if safe_display_text(p) not in matched_pyeongs]
        if missing_pyeongs:
            st.warning(
                "다음 예상 가능 평형은 조망 요약 데이터에 유닛 타입이 없어 계산에서 제외되었습니다: "
                + " / ".join(safe_display_text(p) for p in missing_pyeongs)
            )

        best = candidates.iloc[0]
        st.markdown(
            f"""
            <div class="best-card">
              <div class="best-title">최선 후보: {best['가능평형']} / {best['미래동']} / 타입 {best['배치도 타입']} / {best['미래층구간']}</div>
              미래층 구간 기준 한강조망각 <b>{int(best['한강조망각'])}도</b>,
              최대연속각 <b>{int(best['최대연속각'])}도</b>,
              주요 각도범위 <b>{best['주요각도범위']}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_grouped_view_tables(candidates)

    reference_normal_pyeongs = [p for p in reference_pyeongs if not is_penthouse_pyeong(p)]
    reference_candidates = build_view_candidates(view_rows, zone_name, reference_normal_pyeongs)
    if not reference_candidates.empty:
        st.markdown("#### 하위 참고 조망 후보")
        st.caption(
            "아래 표는 예상 가능 평형보다 낮지만 현재 평형 이상에서 조망각이 좋은 참고 후보입니다. "
            "예상 가능 평형을 대체하는 추천이 아니라 하향 선택을 검토할 때 보는 보조 자료입니다."
        )
        render_grouped_view_tables(reference_candidates)

    st.caption(
        "주의: 이 추천은 미래 배치도 GeoJSON의 동·평형 유닛 기준입니다. "
        "현재 123동 같은 기존 동번호가 미래 배치도 동번호와 직접 대응하지 않으면, "
        "현재 세대는 순위 산정에만 쓰고 미래동/타입은 선택 후보로 해석해야 합니다."
    )


# =========================
# 화면
# =========================
st.title("압구정 분양가능 평형·조망각 추천")
st.markdown(
    """
    <div class="note-box">
      새 앱입니다. 기존 랭크앱의 <b>구역 내 순위 산출</b>과 <b>분양가능 평형 예측</b>만 가져오고,
      조망 시뮬레이터의 계산 결과를 연결해 <b>가능 평형 중 조망각이 좋은 후보</b>를 추천합니다.<br>
      구글시트 인증은 사용하지 않고, 앱 폴더의 <b>data/main_data.xlsx</b> 또는 <b>data/main_data.csv</b>를 읽습니다.
    </div>
    """,
    unsafe_allow_html=True,
)

local_data_file = find_local_data_file()
uploaded_data_file = None

if local_data_file is None:
    st.warning(
        "공시가격 데이터 파일을 찾지 못했습니다. "
        "앱 폴더의 data 폴더에 main_data.xlsx 또는 main_data.csv를 넣어 주세요."
    )
    uploaded_data_file = st.file_uploader(
        "또는 여기에서 엑셀/CSV 파일을 임시 업로드하세요.",
        type=["xlsx", "xls", "csv"],
    )

try:
    if local_data_file is not None:
        st.caption(f"데이터 파일: {local_data_file.name}")
        df_raw = load_from_local_file(str(local_data_file))
    elif uploaded_data_file is not None:
        df_raw = read_local_table(uploaded_data_file)
    else:
        st.stop()

    df = clean_main_df(df_raw)
except Exception as e:
    st.error(f"데이터 파일 로딩/정리 실패: {e}")
    st.stop()

year_cols = filter_year_cols_with_data(coerce_numeric(df, detect_year_cols(df)), detect_year_cols(df))
year_cols = [y for y in year_cols if int(y) >= 2016]
if not year_cols:
    st.error("2016년 이후 연도 컬럼을 찾지 못했습니다.")
    st.stop()
if RANK_YEAR not in year_cols:
    st.error(f"'{LOCAL_WORKSHEET_NAME}' 탭에서 {RANK_YEAR}년 컬럼을 찾지 못했습니다.")
    st.stop()

df_num = coerce_numeric(df, year_cols)
df_num = apply_2026_floor_rank_adjustment(df_num)
latest_year = int(RANK_YEAR)
latest_year_col = str(latest_year)

area_col = find_first_col(df_num, ["전용면적(㎡)", "전용면적", "전용면적 (㎡)", "전용면적㎡"])
land_col = find_first_col(df_num, ["대지지분(평)", "대지지분", "대지지분 (평)", "대지지분평"])
pyeong_col = detect_pyeong_col(df_num)

zones = sorted(df_num["구역"].dropna().unique().tolist())


def reset_after_zone():
    st.session_state["dong_pair"] = None
    st.session_state["ho"] = None


def reset_after_dong():
    st.session_state["ho"] = None


zone = st.selectbox("구역 선택", zones, index=None, placeholder="구역을 선택하세요", key="zone", on_change=reset_after_zone)

if zone is None:
    dong_pairs = []
    dong_is_unique = True
else:
    zone_df0 = df_num[df_num["구역"] == zone].copy()
    dong_pairs = (
        zone_df0[["단지명", "동"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["단지명", "동"])
        .to_records(index=False)
        .tolist()
    )
    dong_counts = pd.Series([int(x[1]) for x in dong_pairs]).value_counts() if dong_pairs else pd.Series(dtype=int)
    dong_is_unique = bool(dong_counts.empty or dong_counts.max() == 1)


def fmt_dong(value):
    complex_name, dong = value
    return f"{int(dong)}동" if dong_is_unique else f"{complex_name} / {int(dong)}동"


dong_pair = st.selectbox(
    "동 선택",
    dong_pairs,
    index=None,
    placeholder="동을 선택하세요",
    key="dong_pair",
    format_func=fmt_dong,
    disabled=(zone is None),
    on_change=reset_after_dong if zone is not None else None,
)

if zone is None or dong_pair is None:
    ho_list = []
else:
    complex_name0, dong0 = dong_pair[0], int(dong_pair[1])
    ho_list = (
        df_num[(df_num["구역"] == zone) & (df_num["단지명"] == complex_name0) & (df_num["동"] == dong0)]["호"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .astype(int)
        .tolist()
    )

ho = st.selectbox("호 선택", ho_list, index=None, placeholder="호를 선택하세요", key="ho", disabled=(dong_pair is None))

if st.button("분양가능 평형 계산", type="primary", use_container_width=True):
    st.session_state["confirmed"] = True

if not st.session_state.get("confirmed", False):
    st.caption("구역, 동, 호를 선택한 뒤 계산 버튼을 누르세요.")
    st.stop()

if zone is None or dong_pair is None or ho is None:
    st.warning("구역, 동, 호를 모두 선택해 주세요.")
    st.stop()

complex_name, dong = dong_pair[0], int(dong_pair[1])
ho = int(ho)

try:
    rank_table = build_rank_table(df_num, year_cols, zone, complex_name, dong, ho)
except Exception as e:
    st.error(f"순위 계산 실패: {e}")
    st.stop()

if rank_table.empty:
    st.warning("선택 세대의 순위 데이터를 만들 수 없습니다.")
    st.stop()

rank_year_rows = rank_table.loc[rank_table["연도"].astype(int) == int(RANK_YEAR)]
if rank_year_rows.empty:
    st.warning(f"선택 세대의 {RANK_YEAR}년 공시가격 데이터가 없습니다.")
    st.stop()

latest_row = rank_year_rows.iloc[0]
latest_price = float(latest_row["공시가격(억)"])
latest_rank_price = float(latest_row.get("순위기준가격(억)", latest_price))
rank_text = str(latest_row["구역 내 순위"])
rank_value = parse_rank_text(rank_text)
tie_count = calc_zone_tie_count(df_num, zone, latest_year_col, latest_rank_price)
is_multi_owner = bool(latest_row.get("다주택소유", False))
multi_owner_units = str(latest_row.get("합산대상", "") or "")
floor = infer_floor_from_ho(ho)

pick = df_num[
    (df_num["구역"] == zone)
    & (df_num["단지명"] == complex_name)
    & (df_num["동"] == dong)
    & (df_num["호"] == ho)
].iloc[0]

pyeong_value = pick[pyeong_col] if pyeong_col else pd.NA
area_value = pd.to_numeric(pick[area_col], errors="coerce") if area_col else pd.NA
land_value = pd.to_numeric(pick[land_col], errors="coerce") if land_col else pd.NA

st.subheader("선택 세대 순위")
multi_owner_html = ""
if is_multi_owner:
    multi_owner_html = (
        f"<br><b>다주택 소유자 합산</b>: {multi_owner_units} / "
        f"합계 공시가격 {latest_price:.2f}억 / 합계 순위기준가격 {latest_rank_price:.2f}억"
    )

st.markdown(
    f"""
    <div class="result-main">
      {zone} / {complex_name} / {fmt_pyeong(pyeong_value)} / {dong}동 / {ho}호
      {f"({floor}층)" if floor else ""}<br>
      {latest_year}년 공시가격 {latest_price:.2f}억 /
      순위기준가격 {latest_rank_price:.2f}억 /
      구역 내 순위 {rank_text}
      {f" / 순위기준가격 동률 {tie_count:,}세대" if tie_count > 1 else ""}
      {multi_owner_html}
    </div>
    """,
    unsafe_allow_html=True,
)

detail_cols = st.columns(3)
detail_cols[0].metric("전용면적", "-" if pd.isna(area_value) else f"{float(area_value):.2f}㎡")
detail_cols[1].metric("대지지분", "-" if pd.isna(land_value) else f"{float(land_value):.2f}평")
detail_cols[2].metric("기준연도", f"{latest_year}년")

if rank_value is None:
    st.warning("구역 내 순위를 읽을 수 없어 분양가능 평형을 계산하지 못했습니다.")
    st.stop()

st.subheader("분양가능 평형 예측")
range_info = estimate_pyeong_range_by_rank(zone, rank_value, tie_count)
render_pyeong_result(range_info)

render_view_recommendation(zone, range_info, pyeong_value)

with st.expander("연도별 구역 내 순위 보기", expanded=False):
    show_cols = ["연도", "공시가격(억)", "순위기준가격(억)", "구역 내 순위"]
    if "다주택소유" in rank_table.columns:
        show_cols.extend(["다주택소유", "합산대상"])
    show_rank = rank_table[show_cols].copy()
    show_rank["공시가격(억)"] = show_rank["공시가격(억)"].map(lambda x: f"{float(x):.2f}")
    show_rank["순위기준가격(억)"] = show_rank["순위기준가격(억)"].map(lambda x: f"{float(x):.2f}")
    st.dataframe(show_rank, use_container_width=True, hide_index=True)

st.caption(f"마지막 계산 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
