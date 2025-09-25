
# -*- coding: utf-8 -*-
"""
enhanced_cube_to_vector.py
--------------------------
final_cube_parser.py의 출력을 기존 vector_chunks.jsonl 형식과 완전히 호환되는 형태로 변환
모든 메타데이터 필드를 포함하여 누락 없이 처리
"""

import json
import re
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

def norm_key(s: str) -> str:
    """키 정규화"""
    if s is None: 
        return ""
    t = re.sub(r"\s+", "", str(s))
    t = t.replace("|","_").replace("/","_").replace("\\","_")
    t = re.sub(r"[^0-9A-Za-z가-힣_\-]", "", t)
    return t[:80]

def generate_chunk_id(doc_id: str, chunk_type: str, additional_info: str = "") -> str:
    """청크 ID 생성 - 기존 형식과 호환"""
    if additional_info:
        base = f"{doc_id}:chunk_{additional_info}_{chunk_type}"
    else:
        base = f"{doc_id}:chunk_{chunk_type}"
    
    # 고유 해시 추가 (8자리)
    hash_val = abs(hash(base)) % 100000000
    return f"{doc_id}:chunk_{hash_val:08d}_{hash(base) % 100000000:08x}"

def create_comprehensive_metadata(cube_data: Dict[str, Any], chunk_info: Dict[str, Any]) -> Dict[str, Any]:
    """포괄적인 메타데이터 생성"""
    statement = cube_data.get("statement", {})
    company = statement.get("company", "삼성전자")
    fiscal_year = statement.get("fiscal_year", 2024)
    statement_type = statement.get("statement_type", "balance")
    source_file = statement.get("source_file", "")
    unit = statement.get("unit", "백만원")
    created_at = statement.get("created_at", datetime.now().isoformat())
    
    # 소스 파일명 추출
    source_filename = Path(source_file).name if source_file else f"감사보고서_{fiscal_year}.htm"
    
    # doc_id 생성
    doc_id = chunk_info.get("doc_id", f"감사보고서_{fiscal_year}")
    
    # 계층 구조 정보
    hierarchy = chunk_info.get("hierarchy", [])
    section_path = chunk_info.get("section_path", [statement_type])
    
    # 연도 매핑
    fiscal_year_map = {
        f"제{fiscal_year-2000}기": fiscal_year,
        "당기": fiscal_year,
        "전기": fiscal_year - 1
    }
    
    # 포함된 연도들
    years_covered = chunk_info.get("years_covered", [fiscal_year])
    
    # 기본 메타데이터 구조 (기존 형식과 완전 호환)
    metadata = {
        # 기본 문서 정보
        "doc_id": doc_id,
        "content_type": chunk_info.get("content_type", "financial_table"),
        "table_index": chunk_info.get("table_index", 0),
        "section_path": section_path,
        "caption": chunk_info.get("caption", ""),
        "statement_type": statement_type,
        "unit": unit,
        "fiscal_year_map": fiscal_year_map,
        
        # 소스 정보
        "source_filename": source_filename,
        "company": company,
        "report_year": fiscal_year,
        "parsing_timestamp": created_at,
        
        # 계층 및 구조 정보
        "hierarchy": hierarchy,
        "years_covered": years_covered,
        
        # 추가 테이블 특화 정보
        "row_key": chunk_info.get("row_key"),
        "col_key": chunk_info.get("col_key"),
        "account_id": chunk_info.get("account_id"),
        "account_name": chunk_info.get("account_name"),
        "parent_id": chunk_info.get("parent_id"),
        "level": chunk_info.get("level"),
        "is_total": chunk_info.get("is_total", False),
        "is_subtotal": chunk_info.get("is_subtotal", False),
        "period_type": chunk_info.get("period_type", "current"),
        "value": chunk_info.get("value"),
        "column_index": chunk_info.get("column_index"),
        
        # 자본변동 관련 정보
        "change_type": chunk_info.get("change_type"),
        "change_category": chunk_info.get("change_category"),
        
        # 주석 정보
        "note_title": chunk_info.get("note_title", ""),
        "notes": chunk_info.get("notes"),
        
        # 앵커 연도
        "anchor_fiscal_year": fiscal_year
    }
    
    # None 값 제거
    return {k: v for k, v in metadata.items() if v is not None}

def format_value_with_unit(value: float, unit: str) -> str:
    """값과 단위를 포맷팅"""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    
    formatted_value = f"{value:,}" if isinstance(value, (int, float)) else str(value)
    
    unit_text = ""
    if "백만원" in unit:
        unit_text = "백만원"
    elif "천원" in unit:
        unit_text = "천원"
    elif "원" in unit:
        unit_text = "원"
    
    return f"{formatted_value}{unit_text}"

def create_natural_text(statement_type: str, account_name: str, value: float, 
                       period_type: str, fiscal_year: int, unit: str, 
                       additional_context: str = "") -> str:
    """자연어 텍스트 생성"""
    
    # 연도 표현
    if period_type == "current":
        year_text = f"{fiscal_year}년 (당기)"
    elif period_type == "previous":
        year_text = f"{fiscal_year-1}년 (전기)"
    elif period_type == "snapshot":
        year_text = f"{fiscal_year}년"
    else:
        year_text = f"{fiscal_year}년"
    
    # 재무제표 유형 한국어
    statement_names = {
        "balance": "재무상태표",
        "income": "손익계산서", 
        "comprehensive": "포괄손익계산서",
        "equity": "자본변동표",
        "cashflow": "현금흐름표"
    }
    
    statement_name = statement_names.get(statement_type, statement_type)
    value_text = format_value_with_unit(value, unit)
    
    if additional_context:
        return f"{statement_name}에서 {year_text} {account_name}는 {value_text}입니다. {additional_context}"
    else:
        return f"{statement_name}에서 {year_text} {account_name}는 {value_text}입니다."

def convert_cube_to_enhanced_chunks(cube_data_list: List[Dict[str, Any]], 
                                  source_file: str) -> List[Dict[str, Any]]:
    """CUBE 데이터를 향상된 청크로 변환"""
    
    all_chunks = []
    
    for statement_data in cube_data_list:
        statement = statement_data.get("statement", {})
        accounts = statement_data.get("accounts", [])
        account_values = statement_data.get("account_values", [])
        equity_changes = statement_data.get("equity_changes", [])
        
        # 기본 정보
        company = statement.get("company", "삼성전자주식회사")
        fiscal_year = statement.get("fiscal_year", 2024)
        statement_type = statement.get("statement_type", "balance")
        unit = statement.get("unit", "백만원")
        doc_id = f"감사보고서_{fiscal_year}"
        
        # 계정 정보 매핑
        account_map = {acc["account_id"]: acc for acc in accounts}
        
        # 1. 계정별 값 청크 생성 (기존 형식과 호환)
        for idx, account_value in enumerate(account_values):
            account_id = account_value.get("account_id", "")
            account_info = account_map.get(account_id, {})
            account_name = account_info.get("account_name", account_id)
            
            value = account_value.get("value", 0)
            period_type = account_value.get("period_type", "current")
            notes = account_value.get("notes")
            
            # 계층 정보 구성
            hierarchy = []
            parent_id = account_info.get("parent_id")
            if parent_id and parent_id in account_map:
                parent_name = account_map[parent_id]["account_name"]
                hierarchy.append(parent_name)
            hierarchy.append(account_name)
            
            # 자연어 텍스트 생성
            additional_context = f"주석: {notes}" if notes else ""
            text = create_natural_text(
                statement_type, account_name, value, period_type, 
                fiscal_year, unit, additional_context
            )
            
            # 청크 정보
            chunk_info = {
                "doc_id": doc_id,
                "content_type": "financial_table",
                "table_index": 0,
                "caption": f"{company} {fiscal_year}년 {statement_type}",
                "hierarchy": hierarchy,
                "years_covered": [fiscal_year] if period_type == "current" else [fiscal_year-1],
                "account_id": account_id,
                "account_name": account_name,
                "parent_id": account_info.get("parent_id"),
                "level": account_info.get("level", 0),
                "is_total": account_info.get("is_total", False),
                "is_subtotal": account_value.get("is_subtotal", False),
                "period_type": period_type,
                "value": value,
                "column_index": account_value.get("column_index", 0),
                "notes": notes,
                "section_path": [statement_type]
            }
            
            # 메타데이터 생성
            metadata = create_comprehensive_metadata(statement_data, chunk_info)
            
            # 청크 ID 생성
            chunk_id = generate_chunk_id(doc_id, f"acc_{norm_key(account_id)}_{period_type}", str(idx))
            
            chunk = {
                "id": chunk_id,
                "text": text,
                "metadata": metadata
            }
            
            all_chunks.append(chunk)
        
        # 2. 자본변동 청크 생성
        for idx, equity_change in enumerate(equity_changes):
            change_type = equity_change.get("change_type", "변동")
            change_category = equity_change.get("change_category", "기타")
            account_id = equity_change.get("account_id", "")
            value = equity_change.get("value", 0)
            notes = equity_change.get("notes")
            
            account_info = account_map.get(account_id, {})
            account_name = account_info.get("account_name", account_id)
            
            # 자본변동 특화 텍스트
            value_text = format_value_with_unit(value, unit)
            text = f"자본변동표에서 {fiscal_year}년 {change_type} 중 {change_category} 항목의 {account_name}은 {value_text}입니다."
            if notes:
                text += f" 주석: {notes}"
            
            # 계층 정보
            hierarchy = [change_type, change_category, account_name]
            
            # 청크 정보
            chunk_info = {
                "doc_id": doc_id,
                "content_type": "equity_change",
                "table_index": 0,
                "caption": f"{company} {fiscal_year}년 자본변동표",
                "hierarchy": hierarchy,
                "years_covered": [fiscal_year],
                "account_id": account_id,
                "account_name": account_name,
                "change_type": change_type,
                "change_category": change_category,
                "value": value,
                "notes": notes,
                "section_path": ["equity", "changes"]
            }
            
            # 메타데이터 생성
            metadata = create_comprehensive_metadata(statement_data, chunk_info)
            
            # 청크 ID 생성
            chunk_id = generate_chunk_id(doc_id, f"eq_{norm_key(change_type)}_{norm_key(change_category)}", str(idx))
            
            chunk = {
                "id": chunk_id,
                "text": text,
                "metadata": metadata
            }
            
            all_chunks.append(chunk)
    
    return all_chunks

def process_all_cube_files():
    """모든 CUBE 파일을 향상된 청크로 변환"""
    
    # 입력 및 출력 디렉토리 (현재 디렉토리 기준 상대 경로)
    input_dir = Path("../data/processed/final_cube_test")
    output_path = Path("../data/processed/enhanced_vector_chunks.jsonl")
    
    # 출력 디렉토리 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # JSON 파일들 찾기
    json_files = list(input_dir.glob("*_final_cube_test.json"))
    
    if not json_files:
        print(f"[WARN] {input_dir}에서 CUBE JSON 파일을 찾을 수 없습니다.")
        return
    
    print(f"[INFO] {len(json_files)}개의 CUBE JSON 파일을 처리합니다.")
    
    all_chunks = []
    total_chunks = 0
    
    for json_file in json_files:
        try:
            print(f"[처리중] {json_file.name}")
            
            # JSON 파일 로드
            with open(json_file, 'r', encoding='utf-8') as f:
                cube_data = json.load(f)
            
            # 청크 생성
            chunks = convert_cube_to_enhanced_chunks(cube_data, str(json_file))
            all_chunks.extend(chunks)
            total_chunks += len(chunks)
            
            print(f"[OK] {json_file.name} -> {len(chunks)}개 청크 생성")
            
        except Exception as e:
            print(f"[ERROR] {json_file.name} 처리 실패: {e}")
            import traceback
            traceback.print_exc()
    
    # 모든 청크를 하나의 파일에 저장
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    
    print(f"[완료] 총 {total_chunks}개의 향상된 청크를 {output_path}에 저장했습니다.")
    
    # 샘플 청크 출력
    if all_chunks:
        print("\n[샘플 청크]")
        sample_chunk = all_chunks[0]
        print(f"ID: {sample_chunk['id']}")
        print(f"텍스트: {sample_chunk['text']}")
        print(f"메타데이터 키: {list(sample_chunk['metadata'].keys())}")

def main():
    """메인 실행 함수"""
    process_all_cube_files()

if __name__ == "__main__":
    main()
