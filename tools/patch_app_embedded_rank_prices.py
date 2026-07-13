#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
text = APP.read_text(encoding="utf-8")

if 'EMBEDDED_RANK_PRICE_PATH = DATA_DIR / "rank_prices_2026_embedded.csv"' not in text:
    text = text.replace(
        'DATA_DIR = APP_DIR / "data"\n',
        'DATA_DIR = APP_DIR / "data"\nEMBEDDED_RANK_PRICE_PATH = DATA_DIR / "rank_prices_2026_embedded.csv"\n',
        1,
    )

old_clean = '''    df["구역"] = df["구역"].astype(str).str.strip()\n    df["단지명"] = df["단지명"].astype(str).str.strip()\n    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")\n    df["호"] = pd.to_numeric(df["호"], errors="coerce").astype("Int64")\n'''
new_clean = '''    df["구역"] = df["구역"].astype(str).str.strip()\n    df["단지명"] = df["단지명"].astype(str).str.strip()\n\n    # 원본 내장자료 입력 보정 1: 2구역 신현대 112동 206호의 호수 공란\n    raw_dong = pd.to_numeric(df["동"], errors="coerce")\n    raw_ho = pd.to_numeric(df["호"], errors="coerce")\n    raw_price_2026 = pd.to_numeric(df.get(RANK_YEAR), errors="coerce") if RANK_YEAR in df.columns else pd.Series(pd.NA, index=df.index)\n    missing_112_206 = (\n        (df["구역"] == "2구역")\n        & (df["단지명"] == "신현대")\n        & (raw_dong == 112)\n        & raw_ho.isna()\n        & (raw_price_2026 == 69.38)\n    )\n    if int(missing_112_206.sum()) == 1:\n        df.loc[missing_112_206, "호"] = 206\n\n    # 원본 내장자료 입력 보정 2: 3구역 현대1,2차 21동 705호 중 두 번째 행은 706호\n    raw_dong = pd.to_numeric(df["동"], errors="coerce")\n    raw_ho = pd.to_numeric(df["호"], errors="coerce")\n    duplicate_21_705 = (\n        (df["구역"] == "3구역")\n        & (df["단지명"] == "현대1,2차")\n        & (raw_dong == 21)\n        & (raw_ho == 705)\n    )\n    duplicate_indices = df.index[duplicate_21_705].tolist()\n    if len(duplicate_indices) == 2:\n        df.at[duplicate_indices[-1], "호"] = 706\n\n    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")\n    df["호"] = pd.to_numeric(df["호"], errors="coerce").astype("Int64")\n'''
if old_clean in text:
    text = text.replace(old_clean, new_clean, 1)
elif 'missing_112_206' not in text:
    raise SystemExit('clean_main_df patch target not found')

# 이미 2구역 보정만 적용된 앱에는 3구역 706호 복원 블록을 추가합니다.
if 'duplicate_21_705' not in text:
    old_existing = '''    if int(missing_112_206.sum()) == 1:\n        df.loc[missing_112_206, "호"] = 206\n\n    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")\n'''
    new_existing = '''    if int(missing_112_206.sum()) == 1:\n        df.loc[missing_112_206, "호"] = 206\n\n    # 원본 내장자료 입력 보정 2: 3구역 현대1,2차 21동 705호 중 두 번째 행은 706호\n    raw_dong = pd.to_numeric(df["동"], errors="coerce")\n    raw_ho = pd.to_numeric(df["호"], errors="coerce")\n    duplicate_21_705 = (\n        (df["구역"] == "3구역")\n        & (df["단지명"] == "현대1,2차")\n        & (raw_dong == 21)\n        & (raw_ho == 705)\n    )\n    duplicate_indices = df.index[duplicate_21_705].tolist()\n    if len(duplicate_indices) == 2:\n        df.at[duplicate_indices[-1], "호"] = 706\n\n    df["동"] = pd.to_numeric(df["동"], errors="coerce").astype("Int64")\n'''
    if old_existing not in text:
        raise SystemExit('existing clean_main_df correction target not found')
    text = text.replace(old_existing, new_existing, 1)

marker = '    return df.drop(columns=["__floor_no", "__line_no"], errors="ignore")\n\n\n'
insert = '''    return df.drop(columns=["__floor_no", "__line_no"], errors="ignore")\n\n\n@st.cache_data(show_spinner=False)\ndef load_embedded_rank_prices(path_text: str) -> pd.DataFrame:\n    prices = pd.read_csv(path_text, encoding="utf-8-sig")\n    required = ["구역", "단지명", "동", "호", "순위기준가격_2026_억"]\n    missing = [c for c in required if c not in prices.columns]\n    if missing:\n        raise ValueError(f"내장 순위가격 파일의 필수 컬럼이 없습니다: {', '.join(missing)}")\n    prices = prices.copy()\n    prices["구역"] = prices["구역"].astype(str).str.strip()\n    prices["단지명"] = prices["단지명"].astype(str).str.strip()\n    prices["동"] = pd.to_numeric(prices["동"], errors="coerce").astype("Int64")\n    prices["호"] = pd.to_numeric(prices["호"], errors="coerce").astype("Int64")\n    prices["순위기준가격_2026_억"] = pd.to_numeric(prices["순위기준가격_2026_억"], errors="coerce")\n    prices = prices.dropna(subset=["구역", "단지명", "동", "호", "순위기준가격_2026_억"])\n    return prices.drop_duplicates(subset=["구역", "단지명", "동", "호"], keep="first")\n\n\ndef apply_embedded_2026_rank_prices(df_num: pd.DataFrame) -> pd.DataFrame:\n    """앱에 내장된 확정 층별 순위가격을 동·호 기준으로 적용합니다."""\n    if RANK_YEAR not in df_num.columns:\n        return df_num.copy()\n    if not EMBEDDED_RANK_PRICE_PATH.exists():\n        return apply_2026_floor_rank_adjustment(df_num)\n\n    df = df_num.copy()\n    df["__rank_price_2026"] = pd.to_numeric(df[RANK_YEAR], errors="coerce")\n    df["__rank_price_note_2026"] = "원본 공시가격"\n\n    embedded = load_embedded_rank_prices(str(EMBEDDED_RANK_PRICE_PATH))\n    key_cols = ["구역", "단지명", "동", "호"]\n    price_map = embedded.set_index(key_cols)["순위기준가격_2026_억"]\n    note_map = embedded.set_index(key_cols).get("보정기준")\n\n    keys = pd.MultiIndex.from_frame(df[key_cols])\n    mapped = pd.Series(keys.map(price_map), index=df.index, dtype="float64")\n    matched = mapped.notna()\n    df.loc[matched, "__rank_price_2026"] = mapped.loc[matched]\n    df.loc[matched, "__rank_price_note_2026"] = "앱 내장 층별 보정가격"\n\n    if note_map is not None:\n        mapped_notes = pd.Series(keys.map(note_map), index=df.index)\n        note_mask = matched & mapped_notes.notna()\n        df.loc[note_mask, "__rank_price_note_2026"] = mapped_notes.loc[note_mask].astype(str)\n\n    return df\n\n\n'''
if 'def apply_embedded_2026_rank_prices' not in text:
    if marker not in text:
        raise SystemExit('rank-price function insertion target not found')
    text = text.replace(marker, insert, 1)

old_loader_return = '    return prices.dropna(subset=["구역", "단지명", "동", "호", "순위기준가격_2026_억"])\n'
new_loader_return = '    prices = prices.dropna(subset=["구역", "단지명", "동", "호", "순위기준가격_2026_억"])\n    return prices.drop_duplicates(subset=["구역", "단지명", "동", "호"], keep="first")\n'
if old_loader_return in text:
    text = text.replace(old_loader_return, new_loader_return, 1)

text = text.replace(
    'df_num = apply_2026_floor_rank_adjustment(df_num)',
    'df_num = apply_embedded_2026_rank_prices(df_num)',
    1,
)

APP.write_text(text, encoding="utf-8")
print('patched', APP)
