# -*- coding: utf-8 -*-
"""
final_cube_parser.py
-------------------
최종 CUBE 구조 파서 - 정확한 계층 구조와 컬럼 구분

특징:
1. 의미적 계층 구조 파싱 (자산 → 유동자산/비유동자산 → 세부항목 → 총계)
2. account_id를 깔끔하게 (숫자 제거, 계층 의미 명확화)
3. 컬럼 구분: 왼쪽(소계) vs 오른쪽(총계)
4. 자본변동표: 스냅샷 기반 파싱
5. snapshot_date 제거 (불필요)
"""

from __future__ import annotations

from pathlib import Path
from io import StringIO
from typing import Dict, List, Tuple, Optional, Any
import re
import json
from dataclasses import dataclass, asdict
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
import chardet
from tqdm import tqdm


# ------------------------- 데이터 구조 정의 -------------------------

@dataclass
class FinancialStatement:
    """재무제표 기본 정보"""
    company: str
    fiscal_year: int
    statement_type: str
    source_file: str
    unit: str
    created_at: str

@dataclass
class Account:
    """계정 정보"""
    account_id: str
    parent_id: Optional[str]
    account_name: str
    account_code: Optional[str]
    level: int
    is_leaf: bool
    statement_type: str
    is_total: bool = False  # 총계 여부

@dataclass
class AccountValue:
    """계정 값"""
    account_id: str
    fiscal_year: int
    period_type: str  # current, previous
    value: float
    currency: str
    source_row: int
    notes: Optional[str]
    column_index: int
    is_subtotal: bool = False  # 소계 여부 (왼쪽 컬럼)
    is_total: bool = False     # 총계 여부 (오른쪽 컬럼)

@dataclass
class EquityChange:
    """자본변동 정보"""
    change_id: str
    fiscal_year: int
    change_type: str
    change_category: str
    account_id: str
    value: float
    currency: str
    source_row: int
    notes: Optional[str]

@dataclass
class HierarchicalData:
    """계층 구조 데이터"""
    statement: FinancialStatement
    accounts: List[Account]
    account_values: List[AccountValue]
    equity_changes: List[EquityChange]


# ------------------------- 공통 유틸 -------------------------

ROMAN_HEAD = re.compile(r"^[ⅰ-ⅹⅠ-Ⅹ]+\.", re.I)
ARABIC_HEAD = re.compile(r"^\d+\.\s*")
HANGUL_HEAD = re.compile(r"^[가-힣]\.\s*")
CUR_RE = re.compile(r"\(당\)\s*기")
PREV_RE = re.compile(r"\(전\)\s*기")
YEAR_BODY = re.compile(r"(20\d{2})\s*년\s*1?2\s*월")
YEAR_FILE = re.compile(r"(20\d{2})")
NBSP = "\u00a0"

# 스냅샷 날짜 패턴
SNAPSHOT_RE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*\(([^)]+)\)")

FS_MAP = {
    "BS":  "balance",
    "IS":  "income", 
    "CIS": "comprehensive",
    "SHE": "equity",
    "CF":  "cashflow",
}


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
    if s is None:
        return ""
    s0 = str(s).replace(NBSP, " ")
    s0 = re.sub(r"\s+", "", s0)
    s0 = re.sub(ROMAN_HEAD, "", s0)
    s0 = re.sub(ARABIC_HEAD, "", s0)
    s0 = re.sub(HANGUL_HEAD, "", s0)
    return s0


def clean_num(x) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # "-"값은 특별한 값으로 처리 (None으로 변환하지 않음)
    if s == "-":
        return "-"  # "-"값을 그대로 반환
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = s.replace(",", "").replace(" ", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    if s in {"", "-"}:
        return "-" if s == "-" else None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def infer_year(soup: BeautifulSoup, fp: Path) -> Optional[int]:
    m = YEAR_BODY.search(soup.get_text(" ", strip=True))
    if m:
        return int(m.group(1))
    m2 = YEAR_FILE.search(fp.stem)
    return int(m2) if m2 else None


def generate_account_id(parent_id: Optional[str], account_name: str) -> str:
    """계정 ID 생성 - 깔끔한 형태"""
    if parent_id:
        return f"{parent_id}_{norm_txt(account_name)}"
    else:
        return norm_txt(account_name)


def get_indent_level(text: str) -> int:
    """인덴트 레벨 계산"""
    if not text:
        return 0
    indent = 0
    for char in text:
        if char in [' ', '\t', '\u00a0']:
            indent += 1
        else:
            break
    return indent // 2


def is_meaningful_value(value: float) -> bool:
    """의미 있는 값인지 확인"""
    if value is None:
        return False
    if value == "-":
        return True  # "-"값은 의미 있는 값으로 처리
    if isinstance(value, str):
        return False  # 문자열은 의미 없는 값으로 처리
    return abs(value) >= 100


def is_total_account(account_name: str) -> bool:
    """총계 계정인지 확인"""
    total_keywords = ["총계", "총", "합계", "합"]
    return any(keyword in account_name for keyword in total_keywords)


def parse_snapshot_date(text: str) -> Optional[str]:
    """스냅샷 날짜 파싱"""
    match = SNAPSHOT_RE.search(text)
    if match:
        year, month, day, period = match.groups()
        return f"{year}.{month.zfill(2)}.{day.zfill(2)} ({period})"
    
    # 추가 패턴들 처리
    if "2013.1.1" in text and "전기초" in text:
        return "2013.1.1 (전기초)"
    elif "2013.12.31" in text and "전기말" in text:
        return "2013.12.31 (전기말)"
    elif "2014.1.1" in text and "당기초" in text:
        return "2014.1.1 (당기초)"
    elif "2014.12.31" in text and "당기말" in text:
        return "2014.12.31 (당기말)"
    
    return None


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
    """모든 재무제표 테이블 찾기"""
    out = []
    
    # 기존 방식으로 찾기
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
    
    # 자본변동표가 없으면 다른 방식으로 찾기
    if not any(kind == "SHE" for kind, _, _ in out):
        for i, table in enumerate(soup.find_all("table")):
            table_text = table.get_text()
            if ("2013.1.1" in table_text and "2014.1.1" in table_text and 
                "자본금" in table_text and "이익잉여금" in table_text):
                try:
                    df = pd.read_html(StringIO(str(table)))[0]
                    out.append(("SHE", df, "자본변동표"))
                    break
                except Exception as e:
                    continue
    
    # 다른 재무제표들도 찾기
    found_types = {kind for kind, _, _ in out}
    
    # 손익계산서 찾기
    if "IS" not in found_types:
        for i, table in enumerate(soup.find_all("table")):
            table_text = table.get_text()
            if ("매출액" in table_text and "매출원가" in table_text and 
                "영업이익" in table_text):
                try:
                    df = pd.read_html(StringIO(str(table)))[0]
                    out.append(("IS", df, "손익계산서"))
                    break
                except Exception as e:
                    continue
    
    # 현금흐름표 찾기
    if "CF" not in found_types:
        for i, table in enumerate(soup.find_all("table")):
            table_text = table.get_text()
            if ("영업활동현금흐름" in table_text and "투자활동현금흐름" in table_text and 
                "재무활동현금흐름" in table_text):
                try:
                    df = pd.read_html(StringIO(str(table)))[0]
                    out.append(("CF", df, "현금흐름표"))
                    break
                except Exception as e:
                    continue
    
    # 포괄손익계산서 찾기
    if "CIS" not in found_types:
        for i, table in enumerate(soup.find_all("table")):
            table_text = table.get_text()
            if ("포괄손익" in table_text and "기타포괄손익" in table_text):
                try:
                    df = pd.read_html(StringIO(str(table)))[0]
                    out.append(("CIS", df, "포괄손익계산서"))
                    break
                except Exception as e:
                    continue
    
    return out


# ------------------------- 최종 CUBE 파서 -------------------------

class FinalCubeParser:
    def __init__(self, company: str, fiscal_year: int, source_file: str, unit: str):
        self.company = company
        self.fiscal_year = fiscal_year
        self.source_file = source_file
        self.unit = unit
        self.created_at = datetime.now().isoformat()
        
        self.accounts: List[Account] = []
        self.account_values: List[AccountValue] = []
        self.equity_changes: List[EquityChange] = []
        
        self.account_id_map: Dict[str, str] = {}
        self.account_counter = 0
    
    def get_or_create_account(self, account_name: str, parent_id: Optional[str] = None, 
                            level: int = 0, statement_type: str = "unknown", is_total: bool = False) -> str:
        account_id = generate_account_id(parent_id, account_name)
        
        if account_id not in self.account_id_map:
            self.account_id_map[account_name] = account_id
            account = Account(
                account_id=account_id,
                parent_id=parent_id,
                account_name=account_name,
                account_code=None,
                level=level,
                is_leaf=True,
                statement_type=statement_type,
                is_total=is_total
            )
            self.accounts.append(account)
            self.account_counter += 1
        
        return account_id
    
    def add_account_value(self, account_id: str, value: float, period_type: str, 
                         source_row: int, notes: Optional[str] = None, column_index: int = 0,
                         is_subtotal: bool = False, is_total: bool = False):
        # 의미 있는 값만 추가
        if is_meaningful_value(value):
            account_value = AccountValue(
                account_id=account_id,
                fiscal_year=self.fiscal_year,
                period_type=period_type,
                value=value,
                currency=self.unit,
                source_row=source_row,
                notes=notes,
                column_index=column_index,
                is_subtotal=is_subtotal,
                is_total=is_total
            )
            self.account_values.append(account_value)
    
    def add_equity_change(self, change_type: str, change_category: str, 
                         account_id: str, value: float, source_row: int, notes: Optional[str] = None):
        change_id = f"{self.fiscal_year}_{change_type}_{change_category}_{account_id}"
        equity_change = EquityChange(
            change_id=change_id,
            fiscal_year=self.fiscal_year,
            change_type=change_type,
            change_category=change_category,
            account_id=account_id,
            value=value,
            currency=self.unit,
            source_row=source_row,
            notes=notes
        )
        self.equity_changes.append(equity_change)
    
    def parse_final_cube_table(self, df: pd.DataFrame, statement_type: str) -> HierarchicalData:
        """최종 CUBE 구조 파싱"""
        self.accounts = []
        self.account_values = []
        self.equity_changes = []
        
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        if df.shape[1] < 2:
            return self._create_hierarchical_data(statement_type)
        
        if statement_type == "equity":
            return self._parse_equity_statement(df)
        else:
            return self._parse_balance_statement(df, statement_type)
    
    def _parse_equity_statement(self, df: pd.DataFrame) -> HierarchicalData:
        """자본변동표 파싱 - 이미지 기반의 정확한 계층 구조와 컬럼 매핑"""
        # 1. 컬럼 헤더 정리 및 매핑
        # 실제 컬럼 수에 맞춰 동적으로 컬럼명 설정
        num_cols = len(df.columns)
        if num_cols >= 8:
            df.columns = [
                "과목", "주석", "자본금", "주식발행초과금", "이익잉여금",
                "기타자본항목", "매각예정분류기타자본항목", "총계"
            ] + [f"col_{i}" for i in range(8, num_cols)]
        else:
            # 컬럼 수가 부족한 경우 기본 컬럼명 사용
            df.columns = [f"col_{i}" for i in range(num_cols)]
        
        # 실제 데이터 시작점 찾기 (예: '2013.1.1 (전기초)')
        start_row_index = -1
        for i, row in df.iterrows():
            if '2013.1.1' in str(row.iloc[0]):
                start_row_index = i
                break
        if start_row_index == -1:
            return self._create_hierarchical_data("equity") # 시작점을 못찾으면 파싱 불가
        
        df = df.iloc[start_row_index:].reset_index(drop=True)

        # 컬럼 인덱스 매핑 (이름 기준) - 동적으로 조정
        column_mapping = {}
        if num_cols >= 8:
            column_mapping = {
                "자본금": 2, "주식발행초과금": 3, "이익잉여금": 4,
                "기타자본항목": 5, "매각예정분류기타자본항목": 6, "총계": 7
            }
            note_col_idx = 1
        else:
            # 컬럼 수가 부족한 경우 기본 매핑
            for i in range(2, min(num_cols, 8)):
                column_mapping[f"col_{i}"] = i
            note_col_idx = 1 if num_cols > 1 else 0

        # 계층 구조 추적을 위한 변수
        path_stack = [] # (account_id, account_name) 튜플을 저장

        for i, row in df.iterrows():
            category_text = str(row.iloc[0]).strip()
            if not category_text or category_text.lower() == 'nan':
                continue

            # 주석 추출
            notes = str(row.iloc[note_col_idx]).strip()
            if not notes or notes.lower() in {'nan', 'none'}:
                notes = None

            name = clean_title(category_text)
            
            # 계층 레벨 결정
            level = -1
            parent_id = None

            if SNAPSHOT_RE.search(category_text): # 예: 2013.1.1 (전기초)
                level = 0
                path_stack = [] # 스냅샷 라인에서 계층 초기화
            elif ROMAN_HEAD.search(category_text): # 예: I. 총포괄손익
                level = 1
                # 부모는 가장 최근의 level 0 (스냅샷)
                if path_stack and path_stack[0][2] == 0:
                    parent_id = path_stack[0][0]
                path_stack = [p for p in path_stack if p[2] < 1] # 기존 level 1 이상은 제거
            elif ARABIC_HEAD.search(category_text): # 예: 1. 당기순이익
                level = 2
                # 부모는 가장 최근의 level 1
                for pid, _, p_level in reversed(path_stack):
                    if p_level == 1:
                        parent_id = pid
                        break
                path_stack = [p for p in path_stack if p[2] < 2] # 기존 level 2 이상은 제거
            else: # 그 외 (분류가 애매한 경우)
                continue # 무시하거나 별도 처리

            # 계정 생성
            account_id = self.get_or_create_account(name, parent_id, level, "equity")
            path_stack.append((account_id, name, level))

            # 값 기록
            # Level 0 (스냅샷)은 모든 컬럼의 값을 AccountValue로 기록
            if level == 0:
                for col_name, col_idx in column_mapping.items():
                    if col_idx < len(row):  # 컬럼 인덱스가 행 길이를 초과하지 않도록 체크
                        value = clean_num(row.iloc[col_idx])
                        if value is not None:
                            # 스냅샷은 '변동'이 아니므로 AccountValue로 기록
                            self.add_account_value(account_id, value, "snapshot", i, notes, col_idx)

            # Level 2 (세부 변동항목)는 EquityChange로 기록
            elif level == 2:
                # 부모(Level 1)의 이름(change_type)을 가져옴
                change_type = "UnknownChange"
                for _, p_name, p_level in reversed(path_stack):
                    if p_level == 1:
                        change_type = p_name
                        break
                
                for col_name, col_idx in column_mapping.items():
                    # 총계는 변동의 결과이므로 제외하고, 각 자본 항목의 변동만 기록
                    if col_name == "총계": continue
                    
                    if col_idx < len(row):  # 컬럼 인덱스가 행 길이를 초과하지 않도록 체크
                        value = clean_num(row.iloc[col_idx])
                        if value is not None and value != 0:
                            # 이것이 실제 '자본 변동' 내역임
                            self.add_equity_change(change_type, col_name, account_id, value, i, notes)

        return self._create_hierarchical_data("equity")

    
    def _parse_balance_statement(self, df: pd.DataFrame, statement_type: str) -> HierarchicalData:
        """재무상태표 파싱 - CUBE 구조"""
        # 헤더 분석
        column_mapping = self._analyze_columns(df)
        note_col = self._find_note_column(df)
        
        current_path = []
        current_level = 0
        
        for i, row in df.iterrows():
            left = self._get_longest_korean_cell(row)
            if not left:
                continue
            
            name = clean_title(left)
            nname = norm_txt(name)
            
            # 주석 추출
            notes = None
            if note_col is not None and note_col < len(row):
                note_value = str(row.iloc[note_col]).strip()
                if note_value and note_value.lower() not in {"nan", "none", ""}:
                    notes = note_value
            
            # 계층 구조 결정
            level, parent_id = self._determine_hierarchy(left, current_path, current_level)
            
            # 총계 계정 여부 확인
            is_total = is_total_account(name)
            
            # 계정 생성
            account_id = self.get_or_create_account(name, parent_id, level, statement_type, is_total)
            
            # 모든 컬럼의 값 추가 (소계/총계 구분)
            self._add_all_column_values_with_type(row, account_id, column_mapping, i+1, notes, is_total)
            
            # 현재 경로 업데이트
            if level <= len(current_path):
                current_path = current_path[:level-1]
            current_path.append(name)
            current_level = level
        
        return self._create_hierarchical_data(statement_type)
    
    def _determine_hierarchy(self, text: str, current_path: List[str], current_level: int) -> Tuple[int, Optional[str]]:
        """계층 구조 결정 - 의미적 계층 구조 파악"""
        name = clean_title(text)
        nname = norm_txt(name)
        
        # 1. 대분류 (자산, 부채, 자본, 부채와자본총계, 당기순이익, 기타포괄손익, 총포괄이익)
        if nname in {"자산", "부채", "자본", "부채와자본총계", "당기순이익", "기타포괄손익", "총포괄이익"}:
            return 1, None
        
        # 포괄손익계산서 특별 처리: 당기순이익과 기타포괄손익이 같은 레벨
        if nname == "당기순이익":
            return 1, None
        
        # 포괄손익계산서 계층 구조: 후속적으로 당기손으로 재분류되지 않은 포괄손익
        if nname == "후속적으로당기손익으로재분류되지않는포괄손익":
            if current_path and "기타포괄손익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            return 2, None
        
        # 순확정급여부채재측정요소는 후속적으로 당기손으로 재분류되지 않은 포괄손익 하위
        if nname == "순확정급여부채재측정요소":
            if current_path and "후속적으로당기손익으로재분류되지않는포괄손익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 3, parent_id
            elif current_path and "기타포괄손익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            return 2, None
        
        # 후속적으로 당기손익으로 재분류되는 포괄손익은 기타포괄손익 하위
        if nname == "후속적으로당기손익으로재분류되는포괄손익":
            if current_path and "기타포괄손익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            return 2, None
        
        # 매도가능금융자산평가손익은 후속적으로 당기손익으로 재분류되는 포괄손익 하위
        if nname == "매도가능금융자산평가손익":
            if current_path and "후속적으로당기손익으로재분류되는포괄손익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 3, parent_id
            return 2, None
        
        # 2. 중분류 (유동자산, 비유동자산, 유동부채, 비유동부채, 자본금, 이익잉여금 등)
        if nname in {"유동자산", "비유동자산", "유동부채", "비유동부채", "자본금", "이익잉여금", "기타자본항목", "주식발행초과금"}:
            # 자산, 부채, 자본 하위에 위치
            if current_path and current_path[0] in {"자산", "부채", "자본"}:
                parent_id = self.account_id_map.get(current_path[0])
                return 2, parent_id
            return 2, None
        
        # 자본금 하위 계정들 (우선주자본금, 보통주자본금)
        if nname in {"우선주자본금", "보통주자본금"}:
            if current_path and "자본금" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 3, parent_id
            return 3, None
        
        # 3. 총계 계정 (자산총계, 부채총계, 자본총계)
        if nname in {"자산총계", "부채총계", "자본총계"}:
            if nname == "자산총계":
                # 자산 하위에 위치
                if current_path and current_path[0] == "자산":
                    parent_id = self.account_id_map.get("자산")
                    return 2, parent_id
            elif nname == "부채총계":
                # 부채 하위에 위치
                if current_path and current_path[0] == "부채":
                    parent_id = self.account_id_map.get("부채")
                    return 2, parent_id
            elif nname == "자본총계":
                # 자본 하위에 위치
                if current_path and current_path[0] == "자본":
                    parent_id = self.account_id_map.get("자본")
                    return 2, parent_id
            return 2, None
        
        # 4. 로마숫자 (대분류)
        if ROMAN_HEAD.search(text):
            return 1, None
        
        # 5. 숫자 (소분류) - 특별한 경우들 처리
        if ARABIC_HEAD.search(text):
            # 손익계산서 특별 처리: 기타수익, 기타비용, 금융수익, 금융비용이 영업이익 하위에서 같은 레벨
            if current_path and "영업이익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            
            # 기타수익 하위의 기타비용, 금융수익, 금융비용도 영업이익 하위에서 같은 레벨
            if current_path and len(current_path) >= 2 and "영업이익" in current_path[-2] and "기타수익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-2])  # 영업이익
                return 2, parent_id
            
            # 주당이익 특별 처리: 기본주당이익, 희석주당이익이 주당이익 하위에서 같은 레벨
            if current_path and "주당이익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            
            # 유동자산/비유동자산 하위에 위치
            for i, path_item in enumerate(current_path):
                if path_item in {"유동자산", "비유동자산", "유동부채", "비유동부채"}:
                    parent_id = self.account_id_map.get(path_item)
                    return 3, parent_id
            # 유동자산/비유동자산이 없으면 상위 레벨
            if current_path:
                parent_id = self.account_id_map.get(current_path[0])
                return 2, parent_id
            return 2, None
        
        # 6. 한글 (세부분류) - 특별한 경우들 처리
        if HANGUL_HEAD.search(text):
            # 손익계산서 특별 처리: 기타수익, 기타비용, 금융수익, 금융비용이 영업이익 하위에서 같은 레벨
            if current_path and "영업이익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            
            # 기타수익 하위의 기타비용, 금융수익, 금융비용도 영업이익 하위에서 같은 레벨
            if current_path and len(current_path) >= 2 and "영업이익" in current_path[-2] and "기타수익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-2])  # 영업이익
                return 2, parent_id
            
            # 주당이익 특별 처리: 기본주당이익, 희석주당이익이 주당이익 하위에서 같은 레벨
            if current_path and "주당이익" in current_path[-1]:
                parent_id = self.account_id_map.get(current_path[-1])
                return 2, parent_id
            
            # 유동자산/비유동자산 하위에 위치
            for i, path_item in enumerate(current_path):
                if path_item in {"유동자산", "비유동자산", "유동부채", "비유동부채"}:
                    parent_id = self.account_id_map.get(path_item)
                    return 3, parent_id
            # 유동자산/비유동자산이 없으면 상위 레벨
            if len(current_path) >= 2:
                parent_id = self.account_id_map.get(current_path[1])
                return 3, parent_id
            elif len(current_path) >= 1:
                parent_id = self.account_id_map.get(current_path[0])
                return 3, parent_id
            return 3, None
        
        # 7. 인덴트 기반 (보조적 역할)
        indent_level = get_indent_level(text)
        if indent_level > 0:
            # 인덴트가 있으면 유동자산/비유동자산 하위로 간주
            for i, path_item in enumerate(current_path):
                if path_item in {"유동자산", "비유동자산", "유동부채", "비유동부채"}:
                    parent_id = self.account_id_map.get(path_item)
                    return 3, parent_id
            # 유동자산/비유동자산이 없으면 인덴트 레벨에 따라
            if len(current_path) >= indent_level:
                parent_id = self.account_id_map.get(current_path[indent_level-1])
                return indent_level + 1, parent_id
            elif len(current_path) >= 1:
                parent_id = self.account_id_map.get(current_path[0])
                return indent_level + 1, parent_id
            return indent_level + 1, None
        
        # 8. 기본값 - 유동자산/비유동자산 하위로 간주
        for i, path_item in enumerate(current_path):
            if path_item in {"유동자산", "비유동자산", "유동부채", "비유동부채"}:
                parent_id = self.account_id_map.get(path_item)
                return 3, parent_id
        
        if current_path:
            parent_id = self.account_id_map.get(current_path[-1])
            return current_level + 1, parent_id
        return 1, None
    
    def _analyze_equity_columns(self, df: pd.DataFrame) -> Dict[int, str]:
        """자본변동표 컬럼 분석"""
        column_mapping = {}
        
        # 컬럼명에서 직접 매핑
        for col_idx in range(df.shape[1]):
            col_name = str(df.columns[col_idx]).strip()
            
            # 컬럼명 매핑
            if "자본금" in col_name:
                column_mapping[col_idx] = "자본금"
            elif "주식발행초과금" in col_name:
                column_mapping[col_idx] = "주식발행초과금"
            elif "이익잉여금" in col_name:
                column_mapping[col_idx] = "이익잉여금"
            elif "기타자본항목" in col_name:
                column_mapping[col_idx] = "기타자본항목"
            elif "매각예정분류기타자본항목" in col_name:
                column_mapping[col_idx] = "매각예정분류기타자본항목"
            elif "총계" in col_name:
                column_mapping[col_idx] = "총계"
        
        # 헤더 행들에서도 찾기
        for row_idx in range(min(5, len(df))):
            for col_idx in range(df.shape[1]):
                cell_value = str(df.iloc[row_idx, col_idx]).strip()
                
                # 컬럼명 매핑
                if "자본금" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "자본금"
                elif "주식발행초과금" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "주식발행초과금"
                elif "이익잉여금" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "이익잉여금"
                elif "기타자본항목" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "기타자본항목"
                elif "매각예정분류기타자본항목" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "매각예정분류기타자본항목"
                elif "총계" in cell_value and col_idx not in column_mapping:
                    column_mapping[col_idx] = "총계"
        
        # 숫자 데이터가 있는 컬럼들을 기본 매핑
        if not column_mapping:
            for col_idx in range(1, df.shape[1]):
                if self._has_numeric_data(df, col_idx):
                    column_mapping[col_idx] = f"column_{col_idx}"
        
        return column_mapping
    
    def _analyze_columns(self, df: pd.DataFrame) -> Dict[int, str]:
        """일반 재무제표 컬럼 분석 - 소계/총계 구분"""
        column_mapping = {}
        
        # 헤더 행들 분석
        for row_idx in range(min(5, len(df))):
            for col_idx in range(df.shape[1]):
                cell_value = str(df.iloc[row_idx, col_idx]).strip()
                
                # 당기 컬럼 찾기
                if CUR_RE.search(cell_value) or "당기" in cell_value:
                    column_mapping[col_idx] = "current"
                # 전기 컬럼 찾기
                elif PREV_RE.search(cell_value) or "전기" in cell_value:
                    column_mapping[col_idx] = "previous"
                # 연도가 포함된 경우
                elif re.search(r"\d{4}", cell_value):
                    if "당기" in cell_value or "현재" in cell_value:
                        column_mapping[col_idx] = "current"
                    elif "전기" in cell_value or "이전" in cell_value:
                        column_mapping[col_idx] = "previous"
        
        # 컬럼명에서도 찾기
        for col_idx in range(df.shape[1]):
            col_name = str(df.columns[col_idx]).strip()
            if CUR_RE.search(col_name) or "당기" in col_name:
                column_mapping[col_idx] = "current"
            elif PREV_RE.search(col_name) or "전기" in col_name:
                column_mapping[col_idx] = "previous"
        
        # 숫자 데이터가 있는 모든 컬럼을 매핑
        numeric_cols = []
        for col_idx in range(1, df.shape[1]):
            if self._has_numeric_data(df, col_idx):
                numeric_cols.append(col_idx)
        
        # 전기/당기 컬럼이 명시적으로 없으면 모든 숫자 컬럼을 당기로
        if not column_mapping and numeric_cols:
            for col_idx in numeric_cols:
                column_mapping[col_idx] = "current"
        
        # 전기 컬럼이 없으면 첫 번째 숫자 컬럼을 전기로, 나머지를 당기로
        if "previous" not in column_mapping.values() and len(numeric_cols) >= 2:
            column_mapping[numeric_cols[0]] = "previous"
            for col_idx in numeric_cols[1:]:
                if col_idx not in column_mapping:
                    column_mapping[col_idx] = "current"
        
        return column_mapping
    
    def _has_numeric_data(self, df: pd.DataFrame, col_idx: int) -> bool:
        """컬럼에 숫자 데이터가 있는지 확인"""
        for row_idx in range(len(df)):
            value = clean_num(df.iloc[row_idx, col_idx])
            if value is not None:
                return True
        return False
    
    def _find_note_column(self, df: pd.DataFrame) -> Optional[int]:
        """주석 열 찾기"""
        for col_idx in range(min(3, df.shape[1])):
            col_name = str(df.columns[col_idx]).strip()
            if "주석" in col_name or "note" in col_name.lower():
                return col_idx
        return None
    
    def _add_equity_column_values(self, row: pd.Series, account_id: str, 
                                 column_mapping: Dict[int, str], source_row: int, 
                                 notes: Optional[str]):
        """자본변동표 컬럼 값 추가"""
        for col_idx, column_name in column_mapping.items():
            if col_idx < len(row):
                value = clean_num(row.iloc[col_idx])
                if value is not None:
                    self.add_account_value(account_id, value, "snapshot", source_row, notes, col_idx)
    
    def _add_equity_changes(self, row: pd.Series, account_id: str, 
                           column_mapping: Dict[int, str], source_row: int, 
                           notes: Optional[str], change_type: str):
        """자본변동 정보 추가"""
        for col_idx, column_name in column_mapping.items():
            if col_idx < len(row):
                value = clean_num(row.iloc[col_idx])
                if value is not None:
                    self.add_equity_change(change_type, column_name, account_id, value, source_row, notes)
    
    def _add_all_column_values_with_type(self, row: pd.Series, account_id: str, 
                                        column_mapping: Dict[int, str], source_row: int, 
                                        notes: Optional[str], is_total: bool):
        """모든 컬럼의 값 추가 - 소계/총계 구분"""
        for col_idx, period_type in column_mapping.items():
            if col_idx < len(row):
                value = clean_num(row.iloc[col_idx])
                if value is not None:
                    # 컬럼 위치에 따라 소계/총계 구분
                    # 일반적으로 왼쪽이 소계, 오른쪽이 총계
                    is_subtotal = col_idx % 2 == 0  # 짝수 인덱스는 소계
                    is_total_col = col_idx % 2 == 1  # 홀수 인덱스는 총계
                    
                    self.add_account_value(account_id, value, period_type, source_row, notes, col_idx, is_subtotal, is_total_col)
    
    def _add_equity_column_values_with_type(self, row: pd.Series, account_id: str, 
                                           column_mapping: Dict[int, str], source_row: int, 
                                           notes: Optional[str]):
        """자본변동표 컬럼 값 추가 - 소계/총계 구분"""
        for col_idx, column_name in column_mapping.items():
            if col_idx < len(row):
                value = clean_num(row.iloc[col_idx])
                if value is not None:
                    # 자본변동표는 맨 오른쪽이 총계
                    is_subtotal = col_idx < len(column_mapping) - 1  # 마지막 컬럼이 아닌 경우 소계
                    is_total_col = col_idx == len(column_mapping) - 1  # 마지막 컬럼이 총계
                    
                    self.add_account_value(account_id, value, "snapshot", source_row, notes, col_idx, is_subtotal, is_total_col)
    
    def _get_longest_korean_cell(self, row: pd.Series) -> str:
        cells = [str(row.iloc[i]) for i in range(min(3, len(row)))]
        cells = [c for c in cells if c and c.lower() not in {"nan", "none"}]
        if not cells:
            return ""
        
        def score(s: str):
            ko = sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")
            return (ko, len(s))
        
        return sorted(cells, key=lambda s: (-score(s)[0], -score(s)[1]))[0].strip()
    
    def _create_hierarchical_data(self, statement_type: str) -> HierarchicalData:
        statement = FinancialStatement(
            company=self.company,
            fiscal_year=self.fiscal_year,
            statement_type=statement_type,
            source_file=self.source_file,
            unit=self.unit,
            created_at=self.created_at
        )
        
        return HierarchicalData(
            statement=statement,
            accounts=self.accounts.copy(),
            account_values=self.account_values.copy(),
            equity_changes=self.equity_changes.copy()
        )


# ------------------------- 메인 함수 -------------------------

def parse_file_final_cube(fp: Path) -> List[HierarchicalData]:
    """파일을 최종 CUBE 구조로 파싱"""
    soup = read_soup(fp)
    fiscal_year = infer_year(soup, fp)
    
    if not fiscal_year:
        print(f"[WARN] {fp.name}에서 연도를 찾을 수 없습니다.")
        return []
    
    parser = FinalCubeParser(
        company="삼성전자주식회사",
        fiscal_year=fiscal_year,
        source_file=str(fp),
        unit="백만원"
    )
    
    results = []
    tables = iter_statement_tables(soup)
    
    print(f"[INFO] {fp.name}에서 {len(tables)}개 재무제표 발견")
    for kind, df, title in tables:
        print(f"  - {kind}: {title[:50]}...")
    
    for kind, df, title in tables:
        result = parser.parse_final_cube_table(df, FS_MAP.get(kind, "unknown"))
        results.append(result)
    
    return results


def main():
    """메인 실행 함수"""
    root = Path(".")
    raw_dir = root / "data" / "raw"
    out_dir = root / "data" / "processed" / "final_cube_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    files = sorted(list(raw_dir.glob("*.htm"))) + sorted(list(raw_dir.glob("*.html")))
    if not files:
        print("[WARN] data/raw/ 에 HTML이 없습니다.")
        return
    
    print(f"[정보] {len(files)}개의 파일을 최종 CUBE 구조로 파싱합니다.")
    
    for fp in tqdm(files, desc="최종 CUBE 파싱", unit="file"):
        try:
            results = parse_file_final_cube(fp)
            
            if results:
                output_data = []
                for result in results:
                    output_data.append({
                        "statement": asdict(result.statement),
                        "accounts": [asdict(acc) for acc in result.accounts],
                        "account_values": [asdict(val) for val in result.account_values],
                        "equity_changes": [asdict(change) for change in result.equity_changes]
                    })
                
                stem = fp.stem
                out_path = out_dir / f"{stem}_final_cube_test.json"
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                
                print(f"[OK] {fp.name} -> {out_path}")
            else:
                print(f"[WARN] {fp.name}에서 파싱된 데이터가 없습니다.")
                
        except Exception as e:
            print(f"[ERROR] {fp.name} 파싱 실패: {e}")
    
    print(f"[완료] 최종 CUBE 계층 구조 파싱 완료: {out_dir}")


if __name__ == "__main__":
    main()
