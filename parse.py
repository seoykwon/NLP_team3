# -*- coding: utf-8 -*-
"""
extract_yearly_statements.py (당기/전기 접미사 버전)
--------------------------------
data/raw/*.htm(l) 감사보고서 HTML에서 5대 재무제표를 파싱하여
연도별 JSON 파일을 data/processed/json/by_year/financial_statements_dynamic_YYYY.json 로 저장.

수정사항: 당기/전기 데이터 모두 접미사 형식으로 표현 (유동자산_당기, 유동자산_전기)

실행 예:
  cd ~/Desktop/samsung-audit-nlp-analysis
  ./.venv/bin/python src/extract_yearly_statements.py
"""

from __future__ import annotations

from pathlib import Path
from io import StringIO
from typing import Dict, List, Tuple, Optional
import re
import json
import platform

import pandas as pd
from bs4 import BeautifulSoup
import chardet
from tqdm import tqdm

# ------------------------- 상수/정규식 -------------------------
ROMAN_HEAD = re.compile(r"^[ⅰ-ⅹⅠ-Ⅹ]+\.", re.I)   # Ⅰ. Ⅱ. …
ARABIC_HEAD = re.compile(r"^\d+\.\s*")            # 1. 2. …
HANGUL_HEAD = re.compile(r"^[가-힣]\.\s*")         # 가. 나. …
CUR_RE = re.compile(r"\(당\)\s*기")
PREV_RE = re.compile(r"\(전\)\s*기")  # 전기 패턴 추가
YEAR_BODY = re.compile(r"(20\d{2})\s*년\s*1?2\s*월")
YEAR_FILE = re.compile(r"(20\d{2})")
NBSP = "\u00a0"

FS_MAP = {
    "BS":  "balance",
    "IS":  "income",
    "CIS": "comprehensive",
    "SHE": "equity",
    "CF":  "cashflow",
}

# ------------------------- 공통 유틸 -------------------------
def read_soup(fp: Path) -> BeautifulSoup:
    raw = fp.read_bytes()
    enc = chardet.detect(raw)["encoding"] or "euc-kr"
    try:
        html = raw.decode(enc, errors="ignore")
    except LookupError:
        html = raw.decode("euc-kr", errors="ignore")
    return BeautifulSoup(html, "lxml")

def norm_txt(s: str) -> str:
    if s is None:
        return ""
    t = str(s).replace(NBSP, " ")
    t = re.sub(r"\s+", "", t)
    t = (t.replace("Ⅰ", "I").replace("Ⅱ", "II").replace("Ⅲ", "III")
           .replace("Ⅳ", "IV").replace("Ⅴ", "V").replace("Ⅵ", "VI")
           .replace("Ⅶ", "VII").replace("Ⅷ", "VIII").replace("Ⅸ", "IX")
           .replace("Ⅹ", "X"))
    return t

def clean_title(s: str) -> str:
    """왼쪽 라벨(제목셀)에서 머리표 제거 + 공백 정리"""
    if s is None:
        return ""
    s0 = str(s).replace(NBSP, " ")
    s0 = re.sub(r"\s+", "", s0)
    s0 = re.sub(ROMAN_HEAD, "", s0)
    s0 = re.sub(ARABIC_HEAD, "", s0)
    s0 = re.sub(HANGUL_HEAD, "", s0)
    return s0

def clean_num(x) -> Optional[float]:
    """쉼표, 괄호음수, 공백/기호 제거 후 float 변환"""
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null"} or s == "-":
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = s.replace(",", "").replace(" ", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    if s in {"", "-"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v

def digits_of(v: float) -> int:
    try:
        n = int(abs(v))
    except Exception:
        return 0
    return len(str(n)) if n != 0 else 1

def pick_current_col(df: pd.DataFrame) -> Optional[int]:
    """(당)기 열 인덱스 탐지. 실패시 None"""
    if isinstance(df.columns, pd.MultiIndex):
        flat = [" ".join([str(x) for x in t if str(x) != "nan"]).strip()
                for t in df.columns]
        df.columns = flat
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    for i, c in enumerate(df.columns):
        if CUR_RE.search(c):
            return i
    for r in range(min(len(df), 3)):
        for i in range(df.shape[1]):
            cell = str(df.iat[r, i]).replace(" ", "")
            if CUR_RE.search(cell):
                return i
    return None

def pick_previous_col(df: pd.DataFrame) -> Optional[int]:
    """(전)기 열 인덱스 탐지. 실패시 None"""
    if isinstance(df.columns, pd.MultiIndex):
        flat = [" ".join([str(x) for x in t if str(x) != "nan"]).strip()
                for t in df.columns]
        df.columns = flat
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    for i, c in enumerate(df.columns):
        if PREV_RE.search(c):
            return i
    for r in range(min(len(df), 3)):
        for i in range(df.shape[1]):
            cell = str(df.iat[r, i]).replace(" ", "")
            if PREV_RE.search(cell):
                return i
    return None

def longest_korean_cell(row: pd.Series) -> str:
    """좌측 라벨 셀 추정"""
    cells = [str(row.iloc[i]) for i in range(min(3, len(row)))]
    cells = [c for c in cells if c and c.lower() not in {"nan", "none"}]
    if not cells:
        return ""
    def score(s: str):
        ko = sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")
        return (ko, len(s))
    return sorted(cells, key=lambda s: (-score(s)[0], -score(s)[1]))[0].strip()

def pick_row_current_value(row: pd.Series,
                           pref_col: int | None,
                           note_col: int | None):
    """
    당기 값 선택 우선순위:
      1) (당)기 열
      2) (당)기 열 + 1 칸
      3) 주석 오른쪽 숫자열 중 자릿수>=6 최댓값의 가장 왼쪽
    """
    start = (note_col + 1) if note_col is not None else 1

    if pref_col is not None:
        for j in (pref_col, pref_col + 1):
            if 0 <= j < len(row):
                v = clean_num(row.iloc[j])
                if v is not None:
                    return v

    cands = []
    for j in range(start, len(row)):
        v = clean_num(row.iloc[j])
        if v is not None:
            cands.append((j, v, digits_of(v)))
    if not cands:
        return None
    big = [(j, v, d) for j, v, d in cands if d >= 6] or cands
    maxd = max(d for _, _, d in big)
    leftmost = [(j, v, d) for j, v, d in big if d == maxd]
    j, v, _ = min(leftmost, key=lambda t: t[0])
    return v

def pick_row_previous_value(row: pd.Series,
                           pref_col: int | None,
                           note_col: int | None):
    """
    전기 값 선택 우선순위:
      1) (전)기 열
      2) (전)기 열 + 1 칸
      3) 주석 오른쪽 숫자열 중 자릿수>=6 최댓값의 두 번째 왼쪽
    """
    start = (note_col + 1) if note_col is not None else 1

    if pref_col is not None:
        for j in (pref_col, pref_col + 1):
            if 0 <= j < len(row):
                v = clean_num(row.iloc[j])
                if v is not None:
                    return v

    cands = []
    for j in range(start, len(row)):
        v = clean_num(row.iloc[j])
        if v is not None:
            cands.append((j, v, digits_of(v)))
    if not cands:
        return None
    big = [(j, v, d) for j, v, d in cands if d >= 6] or cands
    maxd = max(d for _, _, d in big)
    leftmost = [(j, v, d) for j, v, d in big if d == maxd]
    
    # 전기는 두 번째 값 선택 (당기 다음)
    if len(leftmost) > 1:
        j, v, _ = sorted(leftmost, key=lambda t: t[0])[1]
        return v
    elif len(leftmost) == 1:
        # 하나밖에 없으면 그것을 사용
        j, v, _ = leftmost[0]
        return v
    return None

def infer_year(soup: BeautifulSoup, fp: Path) -> Optional[int]:
    m = YEAR_BODY.search(soup.get_text(" ", strip=True))
    if m:
        return int(m.group(1))
    m2 = YEAR_FILE.search(fp.stem)
    return int(m2) if m2 else None

# ------------------------- 표 탐지 -------------------------
def classify_title(title: str) -> Optional[str]:
    t = title.replace(" ", "")
    if "재무상태표" in t:
        return "BS"
    if "손익계산서" in t and "포괄" not in t:
        return "IS"
    if "포괄손익" in t:
        return "CIS"
    if "자본변동표" in t:
        return "SHE"
    if "현금흐름표" in t:
        return "CF"
    return None

def iter_statement_tables(soup: BeautifulSoup) -> List[Tuple[str, pd.DataFrame, str]]:
    """
    제목(nb) 테이블 → 다음 TABLE 본문 매칭
    return: [(kind, df, title_text)]
    """
    out = []
    for nb in soup.find_all("table", class_=re.compile(r"\bnb\b")):
        title_txt = re.sub(r"\s+", " ", nb.get_text(" ", strip=True))
        kind = classify_title(title_txt)
        if not kind:
            continue
        body = nb.find_next("table", class_=re.compile(r"\bTABLE\b"))
        if body is None:
            continue
        try:
            df = pd.read_html(StringIO(str(body)))[0]
        except Exception:
            continue
        out.append((kind, df, title_txt))
    return out

# ------------------- 메타데이터 emit -------------------
def emit_value(res: Dict[str, float | None],
               meta: List[dict],
               *,
               key: str,
               value: Optional[float],
               fs_type: str,
               source_file: str,
               table_title: str,
               row_no: int,
               subject_label: str,
               fiscal_year: Optional[int],
               unit: str,
               company: str):
    """wide 값(res)과 값별 메타(meta)를 동시에 기록"""
    if value is None:
        return
    if res.get(key) is None:
        res[key] = value
    subject_norm = norm_txt(subject_label) or key
    meta.append({
        "key": key,
        "value": float(value),
        "fs_type": fs_type,
        "source_file": source_file,
        "table_title": table_title,
        "row_no": int(row_no),
        "subject_id": f"{fs_type}:{subject_norm}:{int(row_no)}",
        "unit": unit,
        "fiscal_year": fiscal_year,
        "company": company,
    })

# ------------------- 동적 파싱(공통: BS/IS/CIS/CF) -------------------
def extract_generic_wide(df: pd.DataFrame,
                         *,
                         fs_type: str,
                         source_file: str,
                         table_title: str,
                         fiscal_year: Optional[int],
                         unit: str,
                         company: str) -> Tuple[Dict[str, float | None], List[dict]]:
    res: Dict[str, float | None] = {}
    meta: List[dict] = []

    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if df.shape[1] < 2:
        return res, meta

    # 당기/전기 컬럼 찾기
    current_col = pick_current_col(df)
    previous_col = pick_previous_col(df)
    
    header_rows = []
    for r in range(min(len(df), 3)):
        for i in range(df.shape[1]):
            if CUR_RE.search(str(df.iat[r, i]).replace(" ", "")):
                header_rows.append(r)
    if header_rows:
        df = df.drop(index=sorted(set(header_rows)), errors="ignore").reset_index(drop=True)

    note_col = 1 if df.shape[1] > 1 else None
    path: List[str] = []  # [대분류, 소분류]

    for i, row in df.iterrows():
        left = longest_korean_cell(row)
        if not left:
            continue
        name = clean_title(left)
        nname = norm_txt(name)

        # 대분류
        if ROMAN_HEAD.search(left) or nname in {"자산", "부채", "자본",
                                                "영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름"}:
            path = [name]
            
            # 당기 값 (접미사 형식)
            v_current = pick_row_current_value(row, current_col, note_col)
            if v_current is not None:
                current_key = f"{name}_당기"
                emit_value(res, meta, key=current_key, value=v_current,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_당기", fiscal_year=fiscal_year,
                           unit=unit, company=company)
            
            # 전기 값 (접미사 형식)
            v_previous = pick_row_previous_value(row, previous_col, note_col)
            if v_previous is not None:
                prev_key = f"{name}_전기"
                emit_value(res, meta, key=prev_key, value=v_previous,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                           unit=unit, company=company)
            continue

        # 소분류
        if ARABIC_HEAD.search(left):
            key = f"{path[0]}_{name}" if path else name
            
            # 당기 값 (접미사 형식)
            v_current = pick_row_current_value(row, current_col, note_col)
            if v_current is not None:
                current_key = f"{key}_당기"
                emit_value(res, meta, key=current_key, value=v_current,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_당기", fiscal_year=fiscal_year,
                           unit=unit, company=company)
            
            # 전기 값 (접미사 형식)
            v_previous = pick_row_previous_value(row, previous_col, note_col)
            if v_previous is not None:
                prev_key = f"{key}_전기"
                emit_value(res, meta, key=prev_key, value=v_previous,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                           unit=unit, company=company)
            continue

        # 세부분류(가.나.다.)
        if HANGUL_HEAD.search(left):
            if path:
                key = f"{path[0]}_{path[1]}_{name}" if len(path) > 1 else f"{path[0]}_{name}"
            else:
                key = name
            
            # 당기 값 (접미사 형식)
            v_current = pick_row_current_value(row, current_col, note_col)
            if v_current is not None:
                current_key = f"{key}_당기"
                emit_value(res, meta, key=current_key, value=v_current,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_당기", fiscal_year=fiscal_year,
                           unit=unit, company=company)
            
            # 전기 값 (접미사 형식)
            v_previous = pick_row_previous_value(row, previous_col, note_col)
            if v_previous is not None:
                prev_key = f"{key}_전기"
                emit_value(res, meta, key=prev_key, value=v_previous,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=f"{name}_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                           unit=unit, company=company)
            continue

        # 일반항목 + 합계류
        key = name if ("총계" in nname or nname in {"자산총계", "부채와자본총계"}) else (f"{path[0]}_{name}" if path else name)
        
        # 당기 값 (접미사 형식)
        v_current = pick_row_current_value(row, current_col, note_col)
        if v_current is not None:
            current_key = f"{key}_당기"
            emit_value(res, meta, key=current_key, value=v_current,
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=i+1, subject_label=f"{name}_당기", fiscal_year=fiscal_year,
                       unit=unit, company=company)
        
        # 전기 값 (접미사 형식)
        v_previous = pick_row_previous_value(row, previous_col, note_col)
        if v_previous is not None:
            prev_key = f"{key}_전기"
            emit_value(res, meta, key=prev_key, value=v_previous,
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=i+1, subject_label=f"{name}_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                       unit=unit, company=company)

    # 간단 보정 (당기)
    if ("유동자산_당기" in res or "비유동자산_당기" in res) and res.get("자산총계_당기") is None:
        ca = res.get("유동자산_당기"); nca = res.get("비유동자산_당기")
        if isinstance(ca, (int, float)) and isinstance(nca, (int, float)):
            res["자산총계_당기"] = float(ca) + float(nca)
            emit_value(res, meta, key="자산총계_당기", value=res["자산총계_당기"],
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=0, subject_label="합산보정_자산총계_당기", fiscal_year=fiscal_year,
                       unit=unit, company=company)

    # 간단 보정 (전기)
    if ("유동자산_전기" in res or "비유동자산_전기" in res) and res.get("자산총계_전기") is None:
        ca = res.get("유동자산_전기"); nca = res.get("비유동자산_전기")
        if isinstance(ca, (int, float)) and isinstance(nca, (int, float)):
            res["자산총계_전기"] = float(ca) + float(nca)
            emit_value(res, meta, key="자산총계_전기", value=res["자산총계_전기"],
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=0, subject_label="합산보정_자산총계_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                       unit=unit, company=company)

    if ("부채총계_당기" in res or "자본총계_당기" in res) and res.get("부채와자본총계_당기") is None:
        tl = res.get("부채총계_당기"); te = res.get("자본총계_당기")
        if isinstance(tl, (int, float)) and isinstance(te, (int, float)):
            res["부채와자본총계_당기"] = float(tl) + float(te)
            emit_value(res, meta, key="부채와자본총계_당기", value=res["부채와자본총계_당기"],
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=0, subject_label="합산보정_부채와자본총계_당기", fiscal_year=fiscal_year,
                       unit=unit, company=company)
    
    # 전기 부채와자본총계 보정
    if ("부채총계_전기" in res or "자본총계_전기" in res) and res.get("부채와자본총계_전기") is None:
        tl = res.get("부채총계_전기"); te = res.get("자본총계_전기")
        if isinstance(tl, (int, float)) and isinstance(te, (int, float)):
            res["부채와자본총계_전기"] = float(tl) + float(te)
            emit_value(res, meta, key="부채와자본총계_전기", value=res["부채와자본총계_전기"],
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=0, subject_label="합산보정_부채와자본총계_전기", fiscal_year=fiscal_year-1 if fiscal_year else None,
                       unit=unit, company=company)
    
    return res, meta

# ------------------- 자본변동표(SHE) 전용 -------------------
def extract_equity_change(df: pd.DataFrame,
                          *,
                          fs_type: str,
                          source_file: str,
                          table_title: str,
                          fiscal_year: Optional[int],
                          unit: str,
                          company: str) -> Tuple[Dict[str, float | None], List[dict]]:
    """
    자본변동표: <섹션>_<항목>_<열헤더> = 값  (모든 숫자열 동적 채택)
    스냅샷행(전/당기초·말)은 '<라벨>_<열>' 키도 추가
    """
    res: Dict[str, float | None] = {}
    meta: List[dict] = []

    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if df.empty:
        return res, meta

    # 헤더 평탄화 & 표준화
    if isinstance(df.columns, pd.MultiIndex):
        headers = ["_".join([str(x) for x in t if str(x) != "nan"]) for t in df.columns]
    else:
        headers = [str(c) for c in df.columns]

    def canon(h: str) -> str:
        h = re.sub(r"\s+", "", h)
        h = h.replace("_", "")  # 주식발행_초과금 → 주식발행초과금
        h = h.replace("총  계", "총계").replace("총계합계", "총계")
        if "기타자본항목" not in h and "기타자본" in h:
            h = h.replace("기타자본", "기타자본항목")
        h = h.replace("매각예정분류OCI", "매각예정분류기타자본항목")
        return h or "열"
    df.columns = [canon(h) for h in headers]

    # 주석열 추정
    note_col = None
    for i, h in enumerate(df.columns[:3]):
        if "주석" in h:
            note_col = i
            break
    start_num_col = (note_col + 1) if note_col is not None else 1

    # 숫자가 '한 번이라도' 나온 모든 오른쪽 열 채택
    cand_cols = list(range(start_num_col, len(df.columns)))
    def has_any_number(j: int) -> bool:
        col = df.iloc[:, j]
        return any(clean_num(x) is not None for x in col)
    good_cols = [j for j in cand_cols if has_any_number(j)] or cand_cols

    # 중간 헤더 반복 행 스킵
    def is_header_like(row: pd.Series) -> bool:
        joined = "".join([str(x) for x in row.values])
        has_header_word = any(h in joined for h in df.columns[start_num_col:])
        numeric_cnt = sum(clean_num(x) is not None for x in row.values[start_num_col:])
        return has_header_word and numeric_cnt == 0

    SNAP_RE = re.compile(r"(전기초|전기말|당기초|당기말)")
    DATE_RE = re.compile(r"20\d{2}\.\d{1,2}\.\d{1,2}")

    cur_section: Optional[str] = None

    for i, row in df.iterrows():
        if is_header_like(row):
            continue

        left = longest_korean_cell(row)
        if not left:
            continue
        left_stripped = left.strip()

        # 섹션(Ⅰ., Ⅱ. …)
        if ROMAN_HEAD.search(left_stripped):
            cur_section = clean_title(left_stripped)
            continue

        # 스냅샷 행
        if SNAP_RE.search(left_stripped) or DATE_RE.search(left_stripped):
            snap = clean_title(left_stripped)
            for j in good_cols:
                col_name = df.columns[j]
                v = clean_num(row.iloc[j])
                if v is None:
                    v = 0.0
                key = f"{snap}_{col_name}"
                emit_value(res, meta, key=key, value=v,
                           fs_type=fs_type, source_file=source_file, table_title=table_title,
                           row_no=i+1, subject_label=snap, fiscal_year=fiscal_year,
                           unit=unit, company=company)
            continue

        # 일반 항목
        item = clean_title(left_stripped)
        for j in good_cols:
            col_name = df.columns[j]
            v = clean_num(row.iloc[j])
            if v is None:
                v = 0.0
            key = f"{cur_section}_{item}_{col_name}" if cur_section else f"{item}_{col_name}"
            emit_value(res, meta, key=key, value=v,
                       fs_type=fs_type, source_file=source_file, table_title=table_title,
                       row_no=i+1, subject_label=item, fiscal_year=fiscal_year,
                       unit=unit, company=company)

    # 총계 별칭(자본총계 추가 노출)
    for k in list(res.keys()):
        if k.endswith("_총계"):
            alias = k.replace("_총계", "_자본총계")
            if alias not in res:
                res[alias] = res[k]
                meta.append({
                    "key": alias, "value": float(res[alias]), "fs_type": fs_type,
                    "source_file": source_file, "table_title": table_title,
                    "row_no": 0, "subject_id": f"{fs_type}:alias:{0}",
                    "unit": unit, "fiscal_year": fiscal_year, "company": company
                })

    return res, meta

# ------------------------- 메인 -------------------------
def main():
    root = Path(".")
    raw_dir = root / "raw"
    out_dir = root / "staging"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(list(raw_dir.glob("*.htm"))) + sorted(list(raw_dir.glob("*.html")))
    if not files:
        print("[WARN] raw/ 에 HTML이 없습니다.")
        return

    by_year: Dict[str, List[dict]] = {}

    for fp in tqdm(files, desc="연도별 재무제표 파싱", unit="file"):
        try:
            soup = read_soup(fp)
            yr = infer_year(soup, fp)
            if yr is None:
                print(f"[WARN] {fp.name}에서 연도를 찾을 수 없습니다.")
                continue

            yr_str = str(yr)
            tables = iter_statement_tables(soup)
            if not tables:
                print(f"[WARN] {fp.name}에서 재무제표를 찾을 수 없습니다.")
                continue

            rec = {
                "fiscal_year": yr,
                "company": "삼성전자주식회사",
                "unit": "백만원",
                "source_file": str(fp.relative_to(root)),
            }
            meta_all: List[dict] = []

            for kind, df, title in tables:
                fs_type = FS_MAP.get(kind, kind)
                if kind == "SHE":
                    data, meta = extract_equity_change(
                        df, fs_type=fs_type, source_file=str(fp.relative_to(root)),
                        table_title=title, fiscal_year=yr, unit="백만원", company="삼성전자주식회사"
                    )
                else:
                    data, meta = extract_generic_wide(
                        df, fs_type=fs_type, source_file=str(fp.relative_to(root)),
                        table_title=title, fiscal_year=yr, unit="백만원", company="삼성전자주식회사"
                    )

                for k, v in data.items():
                    if v is None:
                        continue
                    if rec.get(k) is None:
                        rec[k] = v

                meta_all.extend(meta)

            rec["meta"] = meta_all
            by_year.setdefault(yr_str, []).append(rec)

        except Exception as e:
            print(f"[ERROR] {fp.name} 파싱 실패: {e}")

    # 연도별 저장
    for y, items in sorted(by_year.items(), key=lambda t: (t[0] == "unknown", t[0])):
        out_path = out_dir / f"financial_statements_dynamic_{y}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"[OK] wrote {out_path}")

if __name__ == "__main__":
    main()

