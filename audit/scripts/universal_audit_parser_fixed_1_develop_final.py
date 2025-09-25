#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import html
import json
import os
import glob
import hashlib
from bs4 import BeautifulSoup, NavigableString
from typing import List, Dict, Any, Optional
from datetime import datetime

class UniversalAuditParser:
    """2014-2024년 모든 감사보고서 형식을 통합 처리하는 범용 파서 (주석 구조 유지 + 테이블 처리 개선)"""
    
    def __init__(self):
        self.main_notes = []
        self.note_boundaries = []
        self.parsed_chunks = []
        self.financial_statements = []  # 재무제표 섹션들
        self.file_year = None
        self.file_format = None
        self.table_counter = 0  # 표 번호 카운터
        self.collected_tables = []  # 수집된 표들
        self.chunk_counter = 0  # RAG 청크 카운터
        
        # 재무제표 항목 매핑 (rag_optimized_parser에서 가져옴)
        self.financial_items = {
            '자산': ['유동자산', '비유동자산', '현금및현금성자산', '단기금융상품', '매출채권', '재고자산', '유형자산', '무형자산'],
            '부채': ['유동부채', '비유동부채', '매입채무', '단기차입금', '장기차입금', '충당부채'],
            '자본': ['자본금', '자본잉여금', '이익잉여금', '기타자본항목'],
            '손익': ['매출액', '매출원가', '매출총이익', '판매비와관리비', '영업이익', '당기순이익'],
            '현금흐름': ['영업활동현금흐름', '투자활동현금흐름', '재무활동현금흐름']
        }
        
        # 단위 정규화 및 스케일 팩터
        self.unit_mapping = {
            '백만원': '백만원',
            '천원': '천원', 
            '원': '원',
            '백만': '백만원',
            '천': '천원'
        }
        
        # 단위별 스케일 팩터 (원 기준)
        self.scale_factors = {
            '백만원': 1000000,
            '천원': 1000,
            '원': 1,
            '백만': 1000000,
            '천': 1000
        }

    def generate_chunk_id(self, content: str) -> str:
        """청크 ID 생성 (rag_optimized_parser 방식)"""
        self.chunk_counter += 1
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"chunk_{self.chunk_counter:04d}_{content_hash}"
    
    def generate_doc_id(self, company: str, year: int, note_num: str, table_num: int = None, subsection: str = None) -> str:
        """RAG용 문서 ID 생성"""
        # 회사명 정규화
        company_clean = re.sub(r'[^가-힣a-zA-Z0-9]', '', company)
        
        # 연도를 2자리로 변환 (2015 -> 15)
        year_short = str(year)[-2:] if year else "00"
        
        # 기본 ID 구성
        doc_id_parts = [company_clean.lower(), year_short, f"note{note_num}"]
        
        # 테이블 번호가 있으면 추가
        if table_num is not None:
            doc_id_parts.append(f"table{table_num}")
        
        # 하위섹션이 있으면 추가 (해시 처리)
        if subsection:
            subsection_hash = hashlib.md5(subsection.encode()).hexdigest()[:6]
            doc_id_parts.append(f"sub{subsection_hash}")
        
        return "_".join(doc_id_parts)

    def find_input_files(self, base_path="/Users/dan/Desktop/snu_project/data/raw"):
        """raw 폴더의 모든 하위 폴더에서 감사보고서 HTML 파일 찾기"""
        html_files = []
        search_patterns = [
            os.path.join(base_path, "**", "*감사보고서*.htm*"),
            os.path.join(base_path, "**", "*audit*.htm*"),
            os.path.join(base_path, "**", "*.htm"),
            os.path.join(base_path, "**", "*.html")
        ]
        
        for pattern in search_patterns:
            html_files.extend(glob.glob(pattern, recursive=True))
        
        # 중복 제거 및 감사보고서 파일만 필터링
        html_files = list(set(html_files))
        audit_files = [f for f in html_files if any(keyword in os.path.basename(f).lower() 
                      for keyword in ['감사보고서', 'audit', '201', '202'])]
        
        print(f"📁 발견된 감사보고서 파일: {len(audit_files)}개")
        for file in sorted(audit_files):
            print(f"   - {file}")
        
        return sorted(audit_files)

    def detect_file_format(self, soup, file_path):
        """파일 형식을 자동 감지"""
        file_name = os.path.basename(file_path)
        
        # 연도 추출
        year_match = re.search(r'(20\d{2})', file_name)
        self.file_year = int(year_match.group(1)) if year_match else None
        
        # 구조적 특징 분석
        spans = soup.find_all('span')
        empty_spans = len([s for s in spans if not s.get_text(strip=True)])
        total_spans = len(spans)
        
        # 주석 패턴 수 확인
        p_elements = soup.find_all(['p', 'P'])
        note_patterns = len([p for p in p_elements if re.match(r'^\d{1,2}\.\s*', p.get_text(strip=True))])
        
        # 형식 분류
        if self.file_year and self.file_year <= 2016:
            if empty_spans > 200:
                self.file_format = "legacy_complex"  # 2014-2016년 복잡한 SPAN 구조
            else:
                self.file_format = "legacy_simple"   # 2014-2016년 단순 구조
        elif self.file_year and self.file_year <= 2020:
            if empty_spans > 500:
                self.file_format = "modern_complex"  # 2017-2020년 복잡한 SPAN 구조
            else:
                self.file_format = "modern_simple"   # 2017-2020년 단순 구조
        else:
            if total_spans < 100:
                self.file_format = "latest_clean"    # 2021-2024년 깔끔한 구조
            else:
                self.file_format = "latest_mixed"    # 2021-2024년 혼합 구조
        
        print(f"🔍 파일 형식 감지: {self.file_year}년 - {self.file_format}")
        print(f"   SPAN 요소: {total_spans}개 (빈 SPAN: {empty_spans}개)")
        print(f"   주석 패턴: {note_patterns}개")

    def extract_document_metadata(self, soup: BeautifulSoup, filename: str) -> Dict[str, Any]:
        """문서 메타데이터 추출 (RAG 최적화)"""
        text = soup.get_text()
        
        # 기본 정보 추출
        year_match = re.search(r'(20\d{2})', filename)
        
        # 회사명 추출 (더 정확한 패턴)
        company_patterns = [
            r'([가-힣]+(?:주식회사|㈜))\s*(?:감사보고서|연결감사보고서)',
            r'회사명\s*[:\：]?\s*([가-힣]+(?:주식회사|㈜))',
            r'([가-힣]+(?:주식회사|㈜))\s*제\s*\d+\s*기',
            r'([가-힣]+(?:주식회사|㈜))'
        ]
        
        company_name = None
        for pattern in company_patterns:
            company_match = re.search(pattern, text)
            if company_match:
                company_name = company_match.group(1).strip()
                break
        
        # 보고서 유형 판별
        report_type = "감사보고서"
        if "연결" in text:
            report_type = "연결감사보고서"
        
        # 회계기간 추출 (더 정확한 패턴)
        period_patterns = [
            r'제\s*(\d+)\s*기\s*\((20\d{2})\.(\d{2})\.(\d{2})\s*~\s*(20\d{2})\.(\d{2})\.(\d{2})\)',
            r'제\s*(\d+)\s*기\s*감사보고서',
            r'제\s*(\d+)\s*기'
        ]
        
        current_period = None
        fiscal_year_start = None
        fiscal_year_end = None
        
        for pattern in period_patterns:
            period_match = re.search(pattern, text)
            if period_match:
                current_period = int(period_match.group(1))
                if len(period_match.groups()) >= 6:  # 날짜 정보가 있는 경우
                    fiscal_year_start = f"{period_match.group(2)}-{period_match.group(3).zfill(2)}-{period_match.group(4).zfill(2)}"
                    fiscal_year_end = f"{period_match.group(5)}-{period_match.group(6).zfill(2)}-{period_match.group(7).zfill(2)}"
                break
        
        # 기본 단위 추출
        unit_patterns = [
            r'\(단위\s*[:\：]?\s*([^)]+)\)',
            r'단위\s*[:\：]\s*([가-힣]+원?)'
        ]
        
        default_unit = None
        for pattern in unit_patterns:
            unit_match = re.search(pattern, text)
            if unit_match:
                unit = unit_match.group(1).strip()
                default_unit = self.unit_mapping.get(unit, unit)
                break
        
        # 연도 추출 개선 (파일 연도 우선)
        final_year = None
        if year_match:
            final_year = int(year_match.group(1))
        elif self.file_year:
            final_year = self.file_year
        
        return {
            'filename': filename,
            'company': company_name or "Unknown",
            'report_year': final_year,
            'period_label': f"제 {current_period} 기" if current_period else None,
            'fiscal_year_start': fiscal_year_start,
            'fiscal_year_end': fiscal_year_end,
            'report_type': report_type,
            'default_unit': default_unit,
            'parsing_timestamp': datetime.now().isoformat(),
            'source_path': filename
        }

    def classify_financial_item(self, item_name: str) -> str:
        """재무항목 분류 (rag_optimized_parser 방식)"""
        item_name = item_name.lower()
        
        for category, items in self.financial_items.items():
            for item in items:
                if item.lower() in item_name:
                    return category
        
        return '기타'

    def normalize_amount(self, amount_str: str, unit: str = None, scale_factor: int = 1) -> Dict[str, Any]:
        """금액 정규화 (단위 변환 포함)"""
        if not amount_str or amount_str.strip() in ['-', '', '―', '—']:
            return {
                'value': None, 
                'display': amount_str,
                'normalized_value': None,
                'unit': unit,
                'scale_factor': scale_factor
            }
        
        # 괄호 처리 (음수)
        is_negative = False
        clean_amount = amount_str.strip()
        if clean_amount.startswith('(') and clean_amount.endswith(')'):
            is_negative = True
            clean_amount = clean_amount[1:-1]
        
        # 콤마, 공백 제거 후 숫자 추출
        clean_amount = re.sub(r'[,\s]', '', clean_amount)
        
        # 숫자 추출 (소수점 포함)
        number_match = re.search(r'(\d+(?:\.\d+)?)', clean_amount)
        if number_match:
            value = float(number_match.group(1))
            if is_negative:
                value = -value
            
            # 단위에 따른 스케일 팩터 적용
            normalized_value = value
            if scale_factor != 1:
                normalized_value = value * scale_factor
            
            return {
                'value': value,  # 원본 값
                'display': amount_str,
                'normalized_value': normalized_value,  # 원 단위로 정규화된 값
                'is_negative': is_negative,
                'unit': unit,
                'scale_factor': scale_factor
            }
        
        return {
            'value': None, 
            'display': amount_str,
            'normalized_value': None,
            'unit': unit,
            'scale_factor': scale_factor
        }

    def parse_file(self, file_path):
        print(f"🚀 범용 감사보고서 파서로 {file_path} 파싱 시작...")
        
        # 다중 인코딩 시도
        content = self.read_with_encoding(file_path)
        if not content:
            raise ValueError(f"파일을 읽을 수 없습니다: {file_path}")
        
        soup = BeautifulSoup(content, "html.parser")
        
        # 파일 형식 자동 감지
        self.detect_file_format(soup, file_path)
        
        # 새로 추가: 재무제표 섹션 파싱
        self.parse_financial_statements(soup)
        
        # 기존 방식으로 주석 구조 파싱 (Phase 1-3)
        elements = self.phase1_preprocess_html(soup)
        self.phase2_find_main_note_boundaries(elements)
        processed_elements = self.phase3_process_continuation_patterns(elements)
        
        # Phase 4에서 개선된 테이블 처리 적용
        self.phase4_extract_content_with_enhanced_tables(processed_elements, soup)
        
        return self.parsed_chunks

    def read_with_encoding(self, file_path):
        """다중 인코딩으로 파일 읽기"""
        encodings = ['cp949', 'euc-kr', 'utf-8', 'latin1', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                print(f"✅ {encoding} 인코딩으로 파일 읽기 성공")
                return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        print(f"❌ 모든 인코딩 시도 실패")
        return None

    def parse_financial_statements(self, soup):
        """주석 전 재무제표 섹션 파싱"""
        print("📊 재무제표 섹션 파싱 시작...")
        
        # 주석 시작점 찾기
        p_elements = soup.find_all(["p", "P"])
        notes_start_idx = None
        for i, element in enumerate(p_elements):
            text = self._merge_spans_adaptively(element)
            if re.search(r"1\.\s*일반적\s*사항", text):
                notes_start_idx = i
                break
        
        if notes_start_idx is None:
            print("   ❌ 주석 시작점을 찾을 수 없습니다.")
            return
        
        print(f"   📍 주석 시작점: P[{notes_start_idx}]")
        
        # 간단한 방식: 처음 20개 TABLE 클래스 테이블에서 재무제표 찾기
        all_tables = soup.find_all('table')
        
        # 재무제표 테이블 패턴 정의 (CENTER 정렬 제목 기반)
        statement_patterns = {
            "재무상태표": [
                r"재\s*무\s*상\s*태\s*표",
                r"대\s*차\s*대\s*조\s*표"
            ],
            "손익계산서": [
                r"손\s*익\s*계\s*산\s*서"
            ],
            "포괄손익계산서": [
                r"포\s*괄\s*손\s*익\s*계\s*산\s*서"
            ],
            "자본변동표": [
                r"자\s*본\s*변\s*동\s*표"
            ],
            "현금흐름표": [
                r"현\s*금\s*흐\s*름\s*표"
            ]
        }
        
        # 재무제표 헤더와 데이터 테이블을 순서대로 찾기
        for table_idx, table in enumerate(all_tables[:30]):  # 처음 30개 확인
            # CENTER 정렬된 셀에서 제목 찾기
            center_cells = table.find_all('td', {'align': 'CENTER'})
            statement_title = None
            statement_unit = None
            
            for cell in center_cells:
                cell_text = cell.get_text(strip=True)
                
                # 재무제표 제목 확인 (포괄손익계산서 우선 처리)
                if re.search(r'포\s*괄\s*손\s*익\s*계\s*산\s*서', cell_text):
                    statement_title = "포괄손익계산서"
                    print(f"   📋 포괄손익계산서 헤더 발견: Table[{table_idx}] - {cell_text}")
                else:
                    for statement_name, patterns in statement_patterns.items():
                        if any(re.search(pattern, cell_text) for pattern in patterns):
                            statement_title = statement_name
                            print(f"   📋 {statement_name} 헤더 발견: Table[{table_idx}] - {cell_text}")
                            break
                
                # 단위 정보 추출
                unit_match = re.search(r'\(단위\s*[:：]?\s*([^)]+)\)', cell_text)
                if unit_match:
                    statement_unit = self.unit_mapping.get(unit_match.group(1).strip(), unit_match.group(1).strip())
                    print(f"      📏 단위 정보: {unit_match.group(1).strip()} -> {statement_unit}")
            
            if statement_title:
                # 헤더 테이블 다음에 나오는 실제 데이터 테이블 찾기
                data_table = None
                for next_idx in range(table_idx + 1, min(table_idx + 5, len(all_tables))):  # 다음 4개 테이블 확인
                    next_table = all_tables[next_idx]
                    next_table_text = next_table.get_text()
                    
                    # 실제 데이터가 있는 테이블인지 확인 (과목, 주석 컬럼이 있고 숫자 데이터가 많은)
                    # 공백이 많은 "과                      목" 형태도 인식
                    has_subject = re.search(r'과\s*목', next_table_text) is not None
                    has_note = '주석' in next_table_text
                    number_count = len(re.findall(r'\d{1,3}(?:,\d{3})*', next_table_text))
                    
                    if (has_subject and has_note and number_count > 10):  # 숫자가 10개 이상
                        data_table = next_table
                        data_table_idx = next_idx
                        print(f"      📊 {statement_title} 데이터 테이블 발견: Table[{data_table_idx}]")
                        break
                
                if data_table:
                    try:
                        # 실제 데이터 테이블 처리
                        matrix = self.table_to_matrix(data_table)
                        if matrix and len(matrix) > 3:  # 유효한 매트릭스인지 확인
                            table_metadata = self.extract_table_metadata(data_table, matrix)
                            table_metadata['statement_type'] = statement_title
                            table_metadata['table_number'] = data_table_idx + 1
                            table_metadata['table_title'] = statement_title
                            if statement_unit:
                                table_metadata['unit'] = statement_unit
                                table_metadata['scale_factor'] = self.scale_factors.get(statement_unit, 1)
                            
                            statement_chunk = {
                                "statement_type": statement_title,
                                "title": statement_title,
                                "table_number": data_table_idx + 1,
                                "matrix": matrix,
                                "metadata": table_metadata
                            }
                            
                            # 기존 재무제표가 있는지 확인
                            existing = next((s for s in self.financial_statements if s["statement_type"] == statement_title), None)
                            if existing:
                                existing.setdefault("tables", []).append(statement_chunk)
                                existing["table_count"] = len(existing["tables"])
                            else:
                                new_statement = {
                                    "statement_type": statement_title,
                                    "title": statement_title,
                                    "tables": [statement_chunk],
                                    "table_count": 1
                                }
                                self.financial_statements.append(new_statement)
                            
                            print(f"      ✅ {statement_title} 데이터 테이블 수집 완료 (행: {len(matrix)}, 열: {len(matrix[0]) if matrix else 0})")
                    except Exception as e:
                        print(f"      ❌ {statement_title} 데이터 테이블 처리 오류: {e}")
        
        print(f"✅ 재무제표 파싱 완료: {len(self.financial_statements)}개 재무제표 발견")

    def _get_table_position_in_document(self, table, p_elements, notes_start_idx):
        """테이블의 문서 내 위치 확인"""
        try:
            # 테이블 앞의 텍스트 요소들 확인
            prev_element = table.previous_sibling
            while prev_element:
                if hasattr(prev_element, 'name') and prev_element.name in ['p', 'P']:
                    # p_elements에서 해당 요소의 인덱스 찾기
                    for i, p in enumerate(p_elements):
                        if p == prev_element:
                            return i
                prev_element = prev_element.previous_sibling
            return 0
        except:
            return None

    def _find_and_parse_statement(self, p_elements, statement_name, patterns, soup):
        """특정 재무제표 찾기 및 파싱"""
        for i, element in enumerate(p_elements):
            text = self._merge_spans_adaptively(element)
            
            # 패턴 매칭
            for pattern in patterns:
                if re.search(pattern, text):
                    print(f"   📋 {statement_name} 발견: P[{i}] - {text[:50]}...")
                    
                    # 해당 재무제표의 테이블들 찾기
                    statement_tables = self._extract_statement_tables(i, p_elements, soup, statement_name)
                    
                    if statement_tables:
                        statement_chunk = {
                            "statement_type": statement_name,
                            "title": statement_name,
                            "start_index": i,
                            "tables": statement_tables,
                            "table_count": len(statement_tables)
                        }
                        self.financial_statements.append(statement_chunk)
                        print(f"      📊 {statement_name} 테이블 {len(statement_tables)}개 수집")
                    
                    return  # 첫 번째 매칭에서 중단

    def _extract_statement_tables(self, start_idx, p_elements, soup, statement_name):
        """재무제표의 테이블들 추출"""
        statement_tables = []
        
        # 시작점부터 다음 재무제표나 주석까지 검색
        end_idx = len(p_elements)
        for i in range(start_idx + 1, len(p_elements)):
            text = self._merge_spans_adaptively(p_elements[i])
            
            # 다른 재무제표나 주석 시작점이면 중단
            if (re.search(r"재\s*무\s*상\s*태\s*표|손\s*익\s*계\s*산\s*서|자\s*본\s*변\s*동\s*표|현\s*금\s*흐\s*름\s*표", text) or
                re.search(r"1\.\s*일반적\s*사항", text)):
                end_idx = i
                break
        
        print(f"      🔍 {statement_name} 테이블 검색 범위: P[{start_idx}] ~ P[{end_idx-1}]")
        
        # 해당 범위의 테이블들 수집
        for i in range(start_idx, end_idx):
            element = p_elements[i]
            
            # 테이블 마커 확인
            text = self._merge_spans_adaptively_with_markers(element)
            marker_matches = re.findall(r'표 (\d+)', text)
            
            for table_num in marker_matches:
                # 수집된 테이블에서 찾기
                for collected_num, table_element, table_info in self.collected_tables:
                    if collected_num == int(table_num):
                        try:
                            # 테이블 처리
                            matrix = self.table_to_matrix(table_element)
                            if matrix and self.is_data_table(matrix, table_element):
                                # 테이블 메타데이터 추출
                                table_metadata = self.extract_table_metadata(table_element, matrix)
                                table_metadata['table_number'] = int(table_num)
                                
                                # nb 클래스에서 추출한 정보 적용
                                if table_info.get('extracted_unit') and not table_metadata.get('unit'):
                                    table_metadata['unit'] = table_info['extracted_unit']
                                    table_metadata['scale_factor'] = self.scale_factors.get(table_info['extracted_unit'], 1)
                                
                                # 재무제표 제목 적용
                                if table_info.get('statement_title'):
                                    table_metadata['statement_type'] = table_info['statement_title']
                                    table_metadata['table_title'] = table_info['statement_title']
                                else:
                                    table_metadata['statement_type'] = statement_name
                                
                                # 기간 정보 적용
                                if table_info.get('period_info'):
                                    period = table_info['period_info']
                                    table_metadata['year'] = period['year']
                                    table_metadata['period'] = period['period']
                                
                                statement_table = {
                                    "table_number": int(table_num),
                                    "matrix": matrix,
                                    "metadata": table_metadata
                                }
                                statement_tables.append(statement_table)
                                print(f"         ✅ 표 {table_num} 수집 완료")
                        except Exception as e:
                            print(f"         ❌ 표 {table_num} 처리 오류: {e}")
                        break
        
        return statement_tables

    def phase1_preprocess_html(self, soup):
        print("📋 Phase 1: HTML 전처리 및 표 위치 마커 삽입 시작...")
        
        # 1단계: 데이터 테이블 분류 및 마커 삽입
        all_tables = soup.find_all('table')
        self._insert_table_markers(soup, all_tables)
        
        # 2단계: p 요소 처리
        p_elements = soup.find_all(["p", "P"])
        processed_elements = []
        start_found = False
        
        for i, element in enumerate(p_elements):
            merged_text = self._merge_spans_adaptively_with_markers(element)

            if not start_found:
                # 다양한 시작 패턴 인식
                start_patterns = [
                    r"1\. *일반적 *사항",
                    r"1\. *회사의 *개요",
                    r"1\. *기업의 *개요",
                    r"주석.*재무제표"
                ]
                
                if any(re.search(pattern, merged_text, re.IGNORECASE) for pattern in start_patterns):
                    start_found = True
                    print(f"✅ 주석 섹션 시작점 발견: P[{i}] - {merged_text[:50]}...")
                else:
                    continue
            
            if merged_text:
                processed_elements.append({
                    "element": element,
                    "text": merged_text,
                    "index": len(processed_elements),
                    "original_index": i,
                })
        
        print(f"✅ Phase 1 완료: {len(processed_elements)}개 요소 처리됨, {len(self.collected_tables)}개 표 수집됨")
        return processed_elements

    def _merge_spans_adaptively(self, element):
        """형식에 따라 적응적으로 SPAN 병합"""
        if not element:
            return ""
        
        # 기본 텍스트 추출
        text = element.get_text(separator=' ', strip=True)
        text = html.unescape(text)
        
        # 형식별 특별 처리
        if self.file_format in ["legacy_complex", "modern_complex"]:
            # 복잡한 SPAN 구조: 빈 SPAN 제거 후 병합
            spans = element.find_all('span')
            if spans:
                span_texts = []
                for span in spans:
                    span_text = span.get_text(strip=True)
                    if span_text:  # 빈 SPAN 제외
                        span_texts.append(span_text)
                if span_texts:
                    text = ' '.join(span_texts)
        
        # 공통 정리
        text = re.sub(r"\s+", " ", text)
        text = text.replace("\xa0", " ")
        return text.strip()
    
    def _merge_spans_adaptively_with_markers(self, element):
        """형식에 따라 적응적으로 SPAN 병합하되, 표 마커 포함"""
        if not element:
            return ""
        
        # 표 마커 먼저 확인
        table_marker_match = re.search(r'\[TABLE_MARKER_(\d+)\]', element.get_text())
        if table_marker_match:
            table_num = table_marker_match.group(1)
            return f"표 {table_num}"
        
        # 일반 텍스트 처리
        return self._merge_spans_adaptively(element)

    def phase2_find_main_note_boundaries(self, elements):
        print("📋 Phase 2: 메인 주석 경계 정의 시작...")
        main_notes = []
        
        # 연도별 맞춤 패턴
        if self.file_year and self.file_year <= 2016:
            # 2014-2016년: 복잡한 패턴 (켜론 없는 경우도 처리)
            note_patterns = [
                r"^(\d{1,2})\.\s*(.+?)\s*[:：]\s*$",  # 켜론이 있고 뒤에 공백
                r"^(\d{1,2})\.\s*(.+?)[:：]$",  # 켜론이 있지만 뒤에 공백 없음
                r"^(\d{1,2})\.\s*(.+?)(?:\s*,\s*계속.*)?$",  # 계속 키워드가 있는 경우
                r"^(\d{1,2})\.\s*(.+?)\s*$"  # 켜론이 없는 경우
            ]
        else:
            # 2017년 이후: 단순한 패턴
            note_patterns = [
                r"^(\d{1,2})\.\s*(.+?)(?:\s*[:：].*)?$"
            ]
        
        # Note 12 특별 처리 패턴 (모든 연도)
        note12_patterns = [
            r"(\d{1,2})\.\s*종속기업.*관계기업.*공동기업.*투자",
            r"(\d{1,2})\.\s*종속기업,?\s*관계기업\s*및\s*공동기업\s*투자",
            r"(\d{1,2})\.\s*관계기업.*투자",
            r"(\d{1,2})\.\s*투자.*종속기업"
        ]
        
        # Note 1 특별 처리 패턴 (일반적 사항)
        note1_patterns = [
            r"(1)\.\s*일반적\s*사항",
            r"(1)\.일반적사항"
        ]
        
        # Note 5 특별 처리 패턴 (사용제한금융상품)
        note5_patterns = [
            r"(5)\.\s*사용제한금융상품",
            r"(5)\.사용제한금융상품"
        ]
        
        # Note 4 특별 처리 패턴 (현금관련)
        note4_patterns = [
            r"(\d{1,2})\.\s*현금.*현금성자산",
            r"(\d{1,2})\.\s*현금및현금성자산",
            r"(\d{1,2})\.현금.*현금성자산",  # 공백 없는 경우
            r"(\d{1,2})\.현금및현금성자산"   # 공백 없는 경우
        ]
        
        # Note 15, 17, 18 특별 처리 패턴 (충당부채)
        note15_patterns = [
            r"(15)\.\s*충당부채",
            r"(15)\.충당부채"
        ]
        
        note17_patterns = [
            r"(17)\.\s*충당부채", 
            r"(17)\.충당부채"
        ]
        
        note18_patterns = [
            r"(18)\.\s*충당부채",
            r"(18)\.충당부채"
        ]

        for elem in elements:
            text = elem["text"]
            
            # span으로 분리된 주석 번호와 제목 처리를 위해 추가 텍스트 추출 시도
            raw_element_text = elem["element"].get_text(separator="", strip=True)
            combined_text = elem["element"].get_text(separator=" ", strip=True)
            
            # Note 1 특별 처리 (일반적 사항)
            for note1_pattern in note1_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note1_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 1:
                            if not any(note["number"] == 1 for note in main_notes):
                                main_notes.append({
                                    "number": 1,
                                    "title": "일반적 사항",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 1 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # Note 5 특별 처리 (사용제한금융상품)
            for note5_pattern in note5_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note5_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 5:
                            if not any(note["number"] == 5 for note in main_notes):
                                main_notes.append({
                                    "number": 5,
                                    "title": "사용제한금융상품",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 5 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # Note 12 특별 처리
            for note12_pattern in note12_patterns:
                match = re.search(note12_pattern, text, re.IGNORECASE)
                if match:
                    note_number = int(match.group(1))
                    if note_number == 12:
                        if not any(note["number"] == 12 for note in main_notes):
                            main_notes.append({
                                "number": 12,
                                "title": "종속기업, 관계기업 및 공동기업 투자",
                                "start_index": elem["index"],
                            })
                            print(f"✅ Note 12 특별 패턴으로 발견: {text[:50]}...")
                        continue
            
            # Note 4 특별 처리 (현금관련)
            for note4_pattern in note4_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note4_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 4:
                            if not any(note["number"] == 4 for note in main_notes):
                                main_notes.append({
                                    "number": 4,
                                    "title": "현금및현금성자산",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 4 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # Note 15 특별 처리 (충당부채)
            for note15_pattern in note15_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note15_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 15:
                            if not any(note["number"] == 15 for note in main_notes):
                                main_notes.append({
                                    "number": 15,
                                    "title": "충당부채",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 15 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # Note 17 특별 처리 (충당부채)
            for note17_pattern in note17_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note17_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 17:
                            if not any(note["number"] == 17 for note in main_notes):
                                main_notes.append({
                                    "number": 17,
                                    "title": "충당부채",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 17 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # Note 18 특별 처리 (충당부채)
            for note18_pattern in note18_patterns:
                # 기본 텍스트, raw 텍스트, combined 텍스트 모두 확인
                for check_text in [text, raw_element_text, combined_text]:
                    match = re.search(note18_pattern, check_text, re.IGNORECASE)
                    if match:
                        note_number = int(match.group(1))
                        if note_number == 18:
                            if not any(note["number"] == 18 for note in main_notes):
                                main_notes.append({
                                    "number": 18,
                                    "title": "충당부채",
                                    "start_index": elem["index"],
                                })
                                print(f"✅ Note 18 특별 패턴으로 발견: {check_text[:50]}...")
                            break
                else:
                    continue
                break
            
            # 일반 패턴 처리
            for pattern in note_patterns:
                match = re.match(pattern, text)
                if match:
                    note_number = int(match.group(1))
                    title_part = match.group(2).strip()
                    
                    if 1 <= note_number <= 40:
                        # 제외 패턴 (첫 번째 주석이면 "계속" 키워드 무시)
                        if any(keyword in title_part.lower() for keyword in ["계속", "continued"]):
                            if not any(note["number"] == note_number for note in main_notes):
                                continue  # 첫 번째 발견이면 "계속" 무시
                        
                        # 중복 체크
                        if not any(note["number"] == note_number for note in main_notes):
                            main_notes.append({
                                "number": note_number,
                                "title": title_part,
                                "start_index": elem["index"],
                            })
                            print(f"✅ Note {note_number} 발견: {title_part}")
                        break
        
        # 정렬 및 경계 설정
        main_notes.sort(key=lambda x: x["number"])
        self.main_notes = main_notes
        
        # 경계 설정
        note_boundaries = []
        for i, note in enumerate(main_notes):
            end_index = main_notes[i + 1]["start_index"] - 1 if i + 1 < len(main_notes) else len(elements) - 1
            note_boundaries.append({
                "number": note["number"],
                "title": note["title"],
                "start_index": note["start_index"],
                "end_index": end_index
            })
        
        self.note_boundaries = note_boundaries
        print(f"✅ Phase 2 완료: {len(main_notes)}개 주석 경계 설정됨")

    def phase3_process_continuation_patterns(self, elements):
        print("📋 Phase 3: 계속 패턴 처리 시작...")
        
        processed_elements = []
        for elem in elements:
            # 계속 패턴 제거
            text = elem["text"]
            text = re.sub(r"\s*,?\s*계속\s*$", "", text)
            text = re.sub(r"\s*,?\s*continued\s*$", "", text, re.IGNORECASE)
            
            elem["text"] = text.strip()
            
            # 빈 텍스트가 아닌 경우만 추가
            if elem["text"]:
                processed_elements.append(elem)
        
        print(f"✅ Phase 3 완료: 계속 패턴 처리 후 {len(processed_elements)}개 요소 남음")
        return processed_elements

    def phase4_extract_content_with_enhanced_tables(self, elements, soup):
        """개선된 테이블 처리가 적용된 Phase 4"""
        print("📋 Phase 4: 내용 추출 및 개선된 테이블 분석 시작...")
        chunks = []
        
        # 문서 메타데이터 추출
        doc_metadata = self.extract_document_metadata(soup, "temp_filename")
        
        print(f"   수집된 테이블: {len(self.collected_tables)}개")
        
        for boundary in self.note_boundaries:
            note_elements = [elem for elem in elements if boundary["start_index"] <= elem["index"] <= boundary["end_index"]]
            content_parts = [elem["text"] for elem in note_elements]
            
            # 해당 주석의 테이블 찾기 (마커 기반)
            note_tables = self._find_tables_by_markers(content_parts)
            
            # 개선된 테이블 처리: RAG 최적화 방식 적용
            enhanced_table_data = self._process_tables_with_rag_optimization(note_tables, doc_metadata, boundary)
            
            # 청크 생성 (기존 구조 유지)
            chunk = {
                "note_number": str(boundary["number"]),
                "title": boundary["title"],
                "content": "\\n\\n".join(content_parts),
                "content_length": sum(len(part) for part in content_parts),
                "tables": {
                    "count": len(note_tables),
                    "markers_in_content": [f"표 {t['table_number']}" for t in note_tables],
                    "enhanced_data": enhanced_table_data  # 개선된 테이블 데이터 추가
                },
                "metadata": {
                    "file_year": self.file_year,
                    "file_format": self.file_format,
                    **doc_metadata  # 문서 메타데이터 추가
                }
            }
            chunks.append(chunk)
        
        print(f"✅ Phase 4 완료: {len(chunks)}개 주석 청크 생성됨")
        self.parsed_chunks = chunks

    def _process_tables_with_rag_optimization(self, note_tables, doc_metadata, boundary):
        """RAG 최적화 방식으로 테이블 처리"""
        enhanced_tables = []
        
        for table_info in note_tables:
            table_element = table_info.get('table_element')
            if not table_element:
                continue
                
            try:
                # 테이블을 매트릭스로 변환 (개선된 방식)
                matrix = self.table_to_matrix(table_element)
                
                if not matrix or not self.is_data_table(matrix, table_element):
                    continue
                
                # 테이블 메타데이터 추출
                table_metadata = self.extract_table_metadata(table_element, matrix)
                table_metadata['table_number'] = table_info.get('table_number')
                table_metadata['note_number'] = boundary["number"]
                table_metadata['note_title'] = boundary["title"]
                
                # nb 클래스에서 추출한 단위 정보 적용
                if table_info.get('extracted_unit') and not table_metadata.get('unit'):
                    table_metadata['unit'] = table_info['extracted_unit']
                    table_metadata['scale_factor'] = self.scale_factors.get(table_info['extracted_unit'], 1)
                
                # 테이블 요약 청크 생성
                summary_chunk = self.create_table_summary_chunk(matrix, table_metadata, doc_metadata)
                
                # 재무 데이터 청크들 생성
                data_chunks = self.create_financial_data_chunks(matrix, table_metadata, doc_metadata)
                
                enhanced_table = {
                    "table_number": table_info.get('table_number'),
                    "summary_chunk": summary_chunk,
                    "data_chunks": data_chunks,
                    "matrix_rows": len(matrix),
                    "matrix_cols": len(matrix[0]) if matrix else 0
                }
                
                enhanced_tables.append(enhanced_table)
                
            except Exception as e:
                print(f"    테이블 {table_info.get('table_number', '?')} 처리 중 오류: {e}")
                continue
        
        return enhanced_tables

    def _insert_table_markers(self, soup, all_tables):
        """테이블 위치에 마커를 삽입하고 테이블을 수집"""
        self.table_counter = 0
        self.collected_tables = []
        self.unit_info = {}  # 단위 정보 저장
        
        for table in all_tables:
            table_class = table.get('class', [])
            if isinstance(table_class, list):
                table_class = ' '.join(table_class)
            
            # nb 클래스에서 제목, 기간, 단위 정보 추출
            if 'nb' in table_class.lower():
                # 모든 CENTER 정렬된 셀 확인
                center_cells = table.find_all('td', {'align': 'CENTER'})
                statement_title = None  # 변수 초기화
                period_info = None  # 변수 초기화
                
                for cell in center_cells:
                    cell_text = cell.get_text(strip=True)
                    
                    # 재무제표 제목 확인
                    if re.search(r'포\s*괄\s*손\s*익\s*계\s*산\s*서', cell_text):
                        statement_title = "포괄손익계산서"
                        print(f"   📋 포괄손익계산서 헤더 발견 (nb): {cell_text}")
                    elif re.search(r'재\s*무\s*상\s*태\s*표', cell_text):
                        statement_title = "재무상태표"
                        print(f"   📋 재무상태표 헤더 발견 (nb): {cell_text}")
                    elif re.search(r'손\s*익\s*계\s*산\s*서', cell_text):
                        statement_title = "손익계산서"
                        print(f"   📋 손익계산서 헤더 발견 (nb): {cell_text}")
                    elif re.search(r'자\s*본\s*변\s*동\s*표', cell_text):
                        statement_title = "자본변동표"
                        print(f"   📋 자본변동표 헤더 발견 (nb): {cell_text}")
                    elif re.search(r'현\s*금\s*흐\s*름\s*표', cell_text):
                        statement_title = "현금흐름표"
                        print(f"   📋 현금흐름표 헤더 발견 (nb): {cell_text}")
                    
                    # 기간 정보 추출
                    period_match = re.search(r'제\s*(\d+)\s*기\s*[:：]?\s*(20\d{2})년\s*\d+월\s*\d+일', cell_text)
                    if period_match:
                        period_info = {
                            'year': int(period_match.group(2)),
                            'period': int(period_match.group(1))
                        }
                        print(f"   📅 기간 정보 발견: {period_info['year']}년 (제{period_info['period']}기)")
                
                # 단위 정보 추출 (마지막 셀, RIGHT 정렬)
                right_cells = table.find_all('td', {'align': 'RIGHT'})
                for cell in right_cells:
                    cell_text = cell.get_text(strip=True)
                    unit_patterns = [
                        r'\(단위\s*[:：]?\s*([^)]+)\)',
                        r'단위\s*[:：]\s*([가-힣원백만천]+)',
                        r'(백만원|천원|원)',
                    ]
                    
                    for pattern in unit_patterns:
                        unit_match = re.search(pattern, cell_text)
                        if unit_match:
                            unit = unit_match.group(1).strip()
                            # 다음 데이터 테이블에 적용할 단위로 저장
                            self.unit_info['next_table_unit'] = self.unit_mapping.get(unit, unit)
                            print(f"   📏 단위 정보 발견: {unit} -> {self.unit_info['next_table_unit']}")
                            break
                
                # 추출된 정보를 다음 데이터 테이블에 적용하기 위해 저장
                if statement_title:
                    self.unit_info['next_table_title'] = statement_title
                    print(f"   📋 다음 테이블 제목 설정: {statement_title}")
                
                # 기간 정보도 저장
                if period_info:
                    self.unit_info['next_table_period'] = period_info
                    print(f"   📅 다음 테이블 기간 설정: {period_info['year']}년 (제{period_info['period']}기)")
                
                table.decompose()
                continue
            
            # 데이터 테이블인지 판단
            if self._is_collectible_table(table):
                self.table_counter += 1
                table_num = self.table_counter
                
                # 저장된 정보 적용
                table_unit = self.unit_info.get('next_table_unit')
                table_title = self.unit_info.get('next_table_title')
                table_period = self.unit_info.get('next_table_period')
                
                # 테이블 정보 수집 (원본 테이블 요소 포함)
                table_info = {
                    'table_number': table_num,
                    'table_element': table,  # 원본 테이블 요소 저장
                    'table_class': table.get('class', []),
                    'extracted_unit': table_unit,  # 추출된 단위 정보 추가
                    'statement_title': table_title,  # 재무제표 제목 추가
                    'period_info': table_period  # 기간 정보 추가
                }
                
                # 정보 사용 후 초기화
                self.unit_info = {}
                self.collected_tables.append((table_num, table, table_info))
                
                # 마커 삽입
                marker = soup.new_tag("p")
                marker.string = f"[TABLE_MARKER_{table_num}]"
                table.insert_before(marker)
                
                # 원본 테이블은 제거하지 않고 숨김 처리
                table['style'] = 'display: none;'
                
                # 단위 정보 초기화 (한 번 사용 후 리셋)
                if 'next_table_unit' in self.unit_info:
                    del self.unit_info['next_table_unit']
    
    def _is_collectible_table(self, table):
        """수집 가능한 테이블인지 판단"""
        table_class = table.get('class', [])
        if isinstance(table_class, list):
            table_class = ' '.join(table_class)
        
        # TABLE 클래스 있으면 수집
        if 'table' in table_class.lower():
            return True
        
        # 구조 기반 판별
        has_thead = table.find('thead') is not None
        row_count = len(table.find_all('tr'))
        
        if has_thead or row_count >= 2:
            # 내용 기반 판별
            table_text = table.get_text(strip=True)
            if any(keyword in table_text for keyword in ['단위:', '구분', '과목', '당기', '전기']):
                return True
        
        return False

    def _find_tables_by_markers(self, content_parts):
        """콘텐츠에서 표 마커를 찾아 테이블 정보 반환"""
        note_tables = []
        
        for content in content_parts:
            # 표 마커 찾기
            marker_matches = re.findall(r'표 (\d+)', content)
            
            for table_num in marker_matches:
                # 수집된 테이블에서 찾기
                for collected_num, table_element, table_info in self.collected_tables:
                    if collected_num == int(table_num):
                        note_tables.append(table_info)
                        break
        
        return note_tables

    def clean_text(self, text):
        """텍스트 정리 (개선된 버전 - 의미없는 패턴 제거)"""
        if not text:
            return ""
        
        # 기본 정리
        text = text.replace('\xa0', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 의미없는 패턴 제거
        text = re.sub(r'\\n\\n', '\n', text)  # \\n\\n -> \n
        text = re.sub(r'\\n', ' ', text)      # \\n -> 공백
        
        # 계속 패턴들 제거 (다양한 형태)
        continue_patterns = [
            r'\s*,?\s*계속\s*[;：:]\s*',     # 계속;, 계속:
            r'\s*,?\s*계속\s*$',            # 문장 끝의 계속
            r'\s*;\s*$',                    # 문장 끝의 세미콜론
            r'\s*：\s*$',                   # 문장 끝의 전각 콜론
            r'\s*:\s*$',                    # 문장 끝의 반각 콜론
        ]
        
        for pattern in continue_patterns:
            text = re.sub(pattern, '', text)
        
        # 중복된 공백 정리
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 한글 글자 사이 공백 제거 (더 넓은 범위)
        # "유 동 자 산", "비 유 동 부 채" 등 처리
        if re.search(r'[가-힣]\s+[가-힣]', text):
            # 한글 사이의 공백 제거
            text = re.sub(r'([가-힣])\s+([가-힣])', r'\1\2', text)
            # 여러 번 적용하여 모든 공백 제거
            while re.search(r'[가-힣]\s+[가-힣]', text):
                text = re.sub(r'([가-힣])\s+([가-힣])', r'\1\2', text)
        
        return text
    
    def is_numeric_like(self, s):
        """숫자 형태인지 확인 (노트북 코드 기반)"""
        if s is None: 
            return False
        x = str(s).strip()
        if x == "" or x in {"-", "–", "—"}: 
            return False
        x = x.replace(",", "")
        if x.startswith("(") and x.endswith(")"): 
            x = x[1:-1]
        return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", x))
    
    def build_header(self, matrix, max_header_rows=4):
        """헤더 구조 분석 (노트북 코드 기반)"""
        if not matrix:
            return [], 0, matrix
        
        header_rows = 0
        for i, row in enumerate(matrix[:max_header_rows]):
            nonempty = [x for x in row if str(x or "").strip()]
            numish = sum(1 for x in row if self.is_numeric_like(x) or x in {"-", "–", "—"})
            if nonempty and numish/len(nonempty) >= 0.6:
                break
            header_rows += 1
        
        if header_rows == 0:
            header_rows = 1
        
        header_grid = matrix[:header_rows]
        body = matrix[header_rows:] if header_rows < len(matrix) else []
        
        if not body:
            body = matrix
            header_grid = []
        
        # 컬럼명 생성 (개선된 로직)
        ncols = max(len(r) for r in (header_grid or body)) if (header_grid or body) else 0
        cols = []
        
        for j in range(ncols):
            parts = []
            for i in range(len(header_grid)):
                if j < len(header_grid[i]):
                    s = self.clean_text(str(header_grid[i][j] or ""))
                    if s and not self.is_numeric_like(s):  # 숫자가 아닌 경우만
                        parts.append(s)
            
            # 컬럼명 조합
            if parts:
                name = " ".join(parts).strip()
            else:
                name = ""
            
            cols.append(name)
        
        # 컬럼명 후처리 (재무제표 특화)
        processed_cols = []
        for j, c in enumerate(cols):
            if c == "" or self.is_numeric_like(c) or c in {"-","–","—"}:
                # 빈 컬럼명일 때 재무제표 패턴에 맞게 추정
                if j == 0:
                    processed_cols.append("항목")
                elif j == 1:
                    processed_cols.append("주석")
                else:
                    # 헤더 그리드에서 해당 위치의 모든 값 확인
                    found_meaningful_name = False
                    for header_row in header_grid:
                        if j < len(header_row) and header_row[j]:
                            cell_text = str(header_row[j]).strip()
                            
                            # 당기/전기 패턴 확인
                            if "당" in cell_text and ("46" in cell_text or "2014" in cell_text):
                                processed_cols.append("당기")
                                found_meaningful_name = True
                                break
                            elif "전" in cell_text and ("45" in cell_text or "2013" in cell_text):
                                processed_cols.append("전기")
                                found_meaningful_name = True
                                break
                            elif re.search(r'20\d{2}', cell_text):  # 연도가 있으면
                                if "2014" in cell_text or "46" in cell_text:
                                    processed_cols.append("당기")
                                elif "2013" in cell_text or "45" in cell_text:
                                    processed_cols.append("전기")
                                else:
                                    processed_cols.append(f"기간{j}")
                                found_meaningful_name = True
                                break
                    
                    if not found_meaningful_name:
                        # colspan으로 인한 빈 컬럼일 가능성 - 원본 헤더명 사용
                        if j >= 2:
                            # 당기 관련 컬럼들 (제 46기는 colspan=2이므로 2,3번 컬럼 모두 "제 46 (당) 기")
                            if j in [2, 3]:
                                processed_cols.append("제 46 (당) 기")
                            elif j in [4, 5]:
                                processed_cols.append("제 45 (전) 기")
                            else:
                                processed_cols.append(f"컬럼{j}")
                        else:
                            processed_cols.append(f"컬럼{j}")
            else:
                processed_cols.append(c)
        
        # 중복 컬럼명 처리하지 않고 원본 그대로 사용
        return processed_cols, len(header_grid), body
    
    def table_to_matrix(self, table):
        """테이블을 매트릭스로 변환 (rag_optimized_parser 방식)"""
        rows = table.find_all("tr")
        grid = []
        max_cols = 0

        def next_free_idx(row):
            i = 0
            while i < len(row) and row[i] is not None:
                i += 1
            return i

        for r, tr in enumerate(rows):
            if r >= len(grid):
                grid.append([])
            if len(grid[r]) < max_cols:
                grid[r].extend([None] * (max_cols - len(grid[r])))

            cells = tr.find_all(["th", "td"], recursive=False)
            for cell in cells:
                if len(grid[r]) < max_cols:
                    grid[r].extend([None] * (max_cols - len(grid[r])))
                c_idx = next_free_idx(grid[r])
                
                # 텍스트 추출 개선
                txt = ""
                for content in cell.contents:
                    if isinstance(content, NavigableString):
                        txt += str(content)
                    elif content.name == "br":
                        txt += " "
                    else:
                        txt += content.get_text(" ", strip=True)
                
                txt = self.clean_text(txt)
                
                # rowspan/colspan 처리 개선
                rs = int(cell.get("rowspan", "1") or "1")
                cs = int(cell.get("colspan", "1") or "1")

                # colspan이 있는 경우 원본 값 보존
                original_value = txt if cs > 1 else None

                needed_cols = c_idx + cs
                if needed_cols > max_cols:
                    for rr in range(len(grid)):
                        grid[rr].extend([None] * (needed_cols - len(grid[rr])))
                    max_cols = needed_cols

                for rr in range(r, r + rs):
                    while rr >= len(grid):
                        grid.append([None] * max_cols)
                    for cc in range(c_idx, c_idx + cs):
                        if rr == r and cc == c_idx:
                            grid[rr][cc] = txt
                        else:
                            if grid[rr][cc] is None:
                                # colspan 분할 시 원본 값 사용
                                if original_value and rr == r:
                                    grid[rr][cc] = original_value
                                else:
                                    grid[rr][cc] = ""

        # 빈 컬럼 제거
        keep = []
        for j in range(max_cols):
            col_vals = [grid[i][j] if j < len(grid[i]) else None for i in range(len(grid))]
            if any(v not in (None, "") for v in col_vals):
                keep.append(j)
        
        mat = [[row[j] for j in keep] for row in grid]
        mat = [row for row in mat if any(v not in (None, "") for v in row)]
        
        # 중복된 헤더 행 제거
        if len(mat) > 1:
            unique_rows = []
            seen = set()
            for row in mat:
                row_str = "|".join(str(x or "") for x in row)
                if row_str not in seen:
                    unique_rows.append(row)
                    seen.add(row_str)
            mat = unique_rows
        
        return mat
    
    def _process_structured_table(self, thead, tbody):
        """thead/tbody가 구분된 테이블 처리"""
        # 1단계: thead 처리 (헤더만)
        header_matrix = self._convert_to_matrix(thead.find_all("tr"))
        
        # 2단계: tbody 처리 (데이터만)  
        data_matrix = self._convert_to_matrix(tbody.find_all("tr"))
        
        # 3단계: 헤더 결합 (thead 내에서만)
        if len(header_matrix) > 1:
            # 복잡한 헤더 구조 처리
            combined_header = self._combine_thead_headers(header_matrix)
        else:
            combined_header = header_matrix[0] if header_matrix else []
        
        # 4단계: 최종 매트릭스 구성
        final_matrix = [combined_header] if combined_header else []
        final_matrix.extend(data_matrix)
        
        return final_matrix
    
    def _process_unstructured_table(self, table):
        """thead/tbody가 없는 테이블 처리 (기존 방식)"""
        rows = table.find_all("tr")
        matrix = self._convert_to_matrix(rows)
        
        # 복잡한 헤더 처리 (기존 로직)
        if len(matrix) >= 2:
            matrix = self.process_complex_headers(matrix)
        
        return matrix
    
    def _convert_to_matrix(self, rows):
        """tr 리스트를 매트릭스로 변환"""
        grid = []
        max_cols = 0

        def next_free_idx(row):
            i = 0
            while i < len(row) and row[i] is not None:
                i += 1
            return i

        # 기본 그리드 생성
        for r, tr in enumerate(rows):
            if r >= len(grid):
                grid.append([])
            
            # 현재 행을 max_cols까지 확장
            while len(grid[r]) < max_cols:
                grid[r].append(None)

            cells = tr.find_all(["th", "td"], recursive=False)
            for cell in cells:
                # 현재 행에서 다음 빈 위치 찾기
                c_idx = next_free_idx(grid[r])
                txt = self.clean_text(cell.get_text(" ", strip=True))
                rs = int(cell.get("rowspan", "1") or "1")
                cs = int(cell.get("colspan", "1") or "1")

                # 필요한 컬럼 수 계산
                needed_cols = c_idx + cs
                if needed_cols > max_cols:
                    # 모든 행을 새로운 컬럼 수에 맞게 확장
                    for rr in range(len(grid)):
                        while len(grid[rr]) < needed_cols:
                            grid[rr].append(None)
                    max_cols = needed_cols

                # rowspan과 colspan에 따라 셀 채우기
                for rr in range(r, r + rs):
                    # 필요한 행이 없으면 생성
                    while rr >= len(grid):
                        grid.append([None] * max_cols)
                    
                    # 현재 행을 max_cols까지 확장
                    while len(grid[rr]) < max_cols:
                        grid[rr].append(None)
                    
                    for cc in range(c_idx, c_idx + cs):
                        if rr == r and cc == c_idx:
                            # 원본 셀 위치에는 실제 텍스트
                            grid[rr][cc] = txt
                        else:
                            # 병합된 셀 위치에는 빈 문자열 (None이 아닌)
                            if grid[rr][cc] is None:
                                grid[rr][cc] = ""

        # 빈 컬럼 제거
        keep = []
        for j in range(max_cols):
            col_vals = [grid[i][j] if j < len(grid[i]) else None for i in range(len(grid))]
            if any(v not in (None, "") for v in col_vals):
                keep.append(j)
        
        # 유효한 컬럼만 유지
        mat = []
        for row in grid:
            new_row = [row[j] if j < len(row) else "" for j in keep]
            if any(v not in (None, "") for v in new_row):
                mat.append(new_row)
        
        return mat
    
    def _combine_thead_headers(self, header_matrix):
        """thead 내의 복잡한 헤더 결합"""
        if not header_matrix:
            return []
        
        if len(header_matrix) == 1:
            return header_matrix[0]
        
        # 다층 헤더 결합 (기존 로직 활용)
        return self.combine_multi_level_headers(header_matrix)

    def _adjust_span_info_for_kept_columns(self, span_info, keep_columns):
        """유효한 컬럼에 맞게 span 정보 조정"""
        adjusted_span_info = []
        
        # 원본 컬럼 인덱스 -> 새 컬럼 인덱스 매핑
        col_mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(keep_columns)}
        
        for row_spans in span_info:
            adjusted_row_spans = []
            for span in row_spans:
                old_col = span['col']
                old_end_col = span['end_col']
                
                # 시작 컬럼이 유효한 컬럼에 포함되는지 확인
                if old_col in col_mapping:
                    # 끝 컬럼도 매핑
                    new_end_col = old_col  # 기본값
                    for kept_col in keep_columns:
                        if kept_col <= old_end_col:
                            new_end_col = kept_col
                    
                    adjusted_span = {
                        **span,
                        'col': col_mapping[old_col],
                        'end_col': col_mapping.get(new_end_col, col_mapping[old_col]),
                        'adjusted_colspan': col_mapping.get(new_end_col, col_mapping[old_col]) - col_mapping[old_col] + 1
                    }
                    adjusted_row_spans.append(adjusted_span)
            
            adjusted_span_info.append(adjusted_row_spans)
        
        return adjusted_span_info
    
    def process_complex_headers_with_span_info(self, matrix, span_info):
        """span 정보를 활용한 복잡한 헤더 구조 처리"""
        if len(matrix) < 2 or not span_info:
            return matrix
        
        # thead 영역 감지 (개선된 로직)
        header_rows = []
        data_start_idx = 0
        
        # span 정보를 기반으로 헤더 행 수 결정
        max_header_rows = len([row_spans for row_spans in span_info if any(span.get('rowspan', 1) > 1 or span.get('colspan', 1) > 1 for span in row_spans)])
        if max_header_rows == 0:
            max_header_rows = 2  # 기본값
        
        for i, row in enumerate(matrix):
            # span 정보가 있는 행까지만 헤더로 간주
            if i < len(span_info) and i < max_header_rows:
                # 해당 행에 span 정보가 있으면 헤더로 간주
                if span_info[i]:  # span 정보가 있는 행
                    header_rows.append(row)
                    continue
            
            # 숫자가 많은 행이 나오면 데이터 시작으로 판단
            numeric_count = sum(1 for cell in row if cell and re.search(r'\d', str(cell)))
            if numeric_count > len(row) * 0.3:  # 30% 이상이 숫자면 데이터 행
                data_start_idx = i
                break
            
            # 일반적인 데이터 패턴 감지
            if i > 1 and self._looks_like_data_row(row):
                data_start_idx = i
                break
                
            header_rows.append(row)
        
        if len(header_rows) < 2:
            return matrix
        
        # span 정보를 활용한 헤더 결합
        combined_header = self.combine_headers_with_span_info(header_rows, span_info[:len(header_rows)])
        
        # 새로운 매트릭스 구성
        new_matrix = [combined_header]
        if data_start_idx < len(matrix):
            new_matrix.extend(matrix[data_start_idx:])
        
        return new_matrix
    
    def _looks_like_data_row(self, row):
        """데이터 행처럼 보이는지 판단"""
        if not row:
            return False
        
        # 첫 번째 셀이 일반적인 데이터 패턴인지 확인
        first_cell = row[0] if row else ""
        
        # 기업명, 항목명 등의 패턴
        data_patterns = [
            r'^[가-힣]+$',  # 한글만 (기업명 등)
            r'^[가-힣\s]+[가-힣]$',  # 한글 + 공백 (복합 항목명)
            r'기타$',  # '기타'로 끝나는 항목
            r'계$',   # '계'로 끝나는 항목
            r'합계$', # '합계'로 끝나는 항목
        ]
        
        for pattern in data_patterns:
            if re.match(pattern, first_cell):
                return True
        
        return False
    
    def combine_headers_with_span_info(self, header_rows, header_span_info):
        """span 정보를 활용한 헤더 결합"""
        if not header_rows or not header_span_info:
            return header_rows[0] if header_rows else []
        
        num_cols = len(header_rows[-1]) if header_rows else 0
        combined_header = []
        
        # 각 컬럼에 대해 상위 헤더 정보 수집
        for col_idx in range(num_cols):
            column_categories = []
            
            # 각 헤더 행의 span 정보에서 해당 컬럼을 포함하는 셀 찾기
            for row_idx, row_spans in enumerate(header_span_info):
                for span in row_spans:
                    # 현재 컬럼이 이 span 범위에 포함되는지 확인
                    if span['col'] <= col_idx <= span['end_col']:
                        if span['text'] and span['text'].strip():
                            column_categories.append(span['text'])
                        break
            
            # 카테고리 결합
            if len(column_categories) == 0:
                combined_name = f"컬럼{col_idx + 1}"
            elif len(column_categories) == 1:
                combined_name = column_categories[0]
            else:
                # 다중 카테고리인 경우 결합
                # 마지막이 구체적인 항목이면 상위 카테고리와 결합
                last_category = column_categories[-1]
                if self._is_specific_financial_item(last_category):
                    # 상위 카테고리 찾기
                    parent_category = None
                    for cat in column_categories[:-1]:
                        if self._is_period_category(cat):
                            parent_category = cat
                            break
                    
                    if parent_category:
                        combined_name = f"{parent_category} - {last_category}"
                    else:
                        combined_name = " - ".join(column_categories)
                else:
                    combined_name = " - ".join(column_categories)
            
            combined_header.append(combined_name)
        
        return combined_header
    
    def _is_specific_financial_item(self, text):
        """구체적인 재무 항목인지 판단"""
        financial_items = [
            '매출채권', '미수금', '지분율', '취득원가', '장부가액', '보유주식수',
            '자산', '부채', '자본', '매출', '비용', '이익', '손실', '시장가치',
            '평가전금액', '평가충당금', '충당금', '평가'
        ]
        return any(item in text for item in financial_items)
    
    def _is_period_category(self, text):
        """기간 카테고리인지 판단"""
        period_categories = ['당기', '전기', '당기말', '전기말', '당분기', '전분기']
        return any(period in text for period in period_categories)

    def process_complex_headers(self, matrix):
        """복잡한 헤더 구조 처리 (다층 헤더) - 호환성을 위한 기존 함수"""
        if len(matrix) < 2:
            return matrix
        
        # thead 영역 감지 (처음 몇 행이 모두 헤더인지 확인)
        header_rows = []
        data_start_idx = 0
        
        for i, row in enumerate(matrix):
            # 숫자가 많은 행이 나오면 데이터 시작으로 판단
            numeric_count = sum(1 for cell in row if cell and re.search(r'\d', str(cell)))
            if numeric_count > len(row) * 0.5 and i > 0:  # 50% 이상이 숫자이고 첫 행이 아니면
                data_start_idx = i
                break
            header_rows.append(row)
        
        if len(header_rows) < 2:
            return matrix  # 단순 헤더면 그대로 반환
        
        # 다층 헤더를 단일 헤더로 변환
        combined_header = self.combine_multi_level_headers(header_rows)
        
        # 새로운 매트릭스 구성
        new_matrix = [combined_header]
        if data_start_idx < len(matrix):
            new_matrix.extend(matrix[data_start_idx:])
        
        return new_matrix

    def combine_multi_level_headers(self, header_rows):
        """다층 헤더를 결합하여 의미있는 컬럼명 생성 (위치 기반 상위 카테고리 매핑 강화)"""
        if not header_rows:
            return []
        
        combined_header = []
        num_cols = max(len(row) for row in header_rows) if header_rows else 0
        
        # 1단계: 첫 번째 행에서 상위 카테고리 범위 파악
        category_ranges = self._extract_category_ranges(header_rows)
        
        # 각 컬럼에 대해 상위 헤더 정보를 정확히 매핑
        for col_idx in range(num_cols):
            # 해당 컬럼의 모든 상위 헤더 정보 수집
            column_headers = []
            
            # 각 헤더 레벨에서 해당 컬럼의 헤더 찾기
            for row_idx, header_row in enumerate(header_rows):
                if col_idx < len(header_row):
                    cell_value = header_row[col_idx]
                    if cell_value and cell_value.strip():
                        column_headers.append(cell_value)
            
            # 헤더 결합 로직
            if len(column_headers) == 0:
                combined_name = f"컬럼{col_idx + 1}"
            elif len(column_headers) == 1:
                # 단일 헤더인 경우 - 위치 기반 상위 카테고리 강제 매핑
                header_text = column_headers[0]
                
                # 위치 기반으로 상위 카테고리 찾기
                category = self._find_category_by_position(col_idx, category_ranges)
                
                if category and self._is_specific_financial_item(header_text):
                    combined_name = f"{category} - {header_text}"
                else:
                    combined_name = header_text
            else:
                # 다중 헤더인 경우
                last_header = column_headers[-1]
                
                # 상위 카테고리 찾기 (기존 방식 + 위치 기반 보완)
                category = None
                for header in column_headers[:-1]:
                    if header in ['당기', '전기', '당기말', '전기말']:
                        category = header
                        break
                
                # 카테고리를 찾지 못했으면 위치 기반으로 찾기
                if not category:
                    category = self._find_category_by_position(col_idx, category_ranges)
                
                if category and self._is_specific_financial_item(last_header):
                    combined_name = f"{category} - {last_header}"
                else:
                    combined_name = " - ".join(column_headers) if len(column_headers) > 1 else column_headers[0]
            
            combined_header.append(combined_name)
        
        return combined_header
    
    def _extract_category_ranges(self, header_rows):
        """첫 번째 헤더 행에서 카테고리별 컬럼 범위 추출 (colspan 기반 정확한 계산)"""
        if not header_rows:
            return {}
        
        category_ranges = {}
        first_row = header_rows[0]
        
        # 실제 컬럼 위치 추적
        current_col_pos = 0
        
        for i, cell in enumerate(first_row):
            if cell and cell.strip():
                cell_text = cell.strip()
                
                if cell_text in ['당기', '전기', '당기말', '전기말']:
                    # 이 카테고리가 차지하는 컬럼 수 계산
                    # 다음 카테고리까지의 빈 셀 개수로 colspan 추정
                    colspan = 1
                    
                    # 다음 비어있지 않은 셀까지의 거리로 colspan 계산
                    for j in range(i + 1, len(first_row)):
                        if first_row[j] and first_row[j].strip():
                            break
                        colspan += 1
                    
                    # 마지막 카테고리인 경우 남은 모든 컬럼
                    if i == len([c for c in first_row if c and c.strip()]) - 1:
                        remaining_cols = len(first_row) - current_col_pos
                        if remaining_cols > colspan:
                            colspan = remaining_cols
                    
                    # 카테고리 범위 저장
                    end_col_pos = current_col_pos + colspan
                    category_ranges[cell_text] = {
                        'start': current_col_pos,
                        'end': end_col_pos - 1,
                        'columns': list(range(current_col_pos, end_col_pos))
                    }
                    current_col_pos = end_col_pos
                else:
                    # 카테고리가 아닌 일반 헤더
                    current_col_pos += 1
        
        return category_ranges
    
    def _find_category_by_position(self, col_idx, category_ranges):
        """컬럼 위치를 기반으로 상위 카테고리 찾기"""
        for category, range_info in category_ranges.items():
            if col_idx in range_info['columns']:
                return category
        return None
    
    def _infer_category_from_context(self, col_idx, total_cols, header_rows):
        """컨텍스트를 고려한 카테고리 추론"""
        if col_idx == 0:
            return None  # 첫 번째 컬럼은 보통 구분/기업명 등
        
        # 첫 번째 헤더 행에서 상위 카테고리 패턴 찾기
        if len(header_rows) >= 1:
            first_row = header_rows[0]
            
            # 패턴 분석: "당기말", "전기말" 등의 위치 파악
            category_positions = {}
            for i, cell in enumerate(first_row):
                if cell in ['당기', '전기', '당기말', '전기말']:
                    category_positions[i] = cell
            
            # 현재 컬럼이 어떤 카테고리 영역에 속하는지 판단
            for pos, category in category_positions.items():
                # 실제 테이블 구조 분석:
                # 기업명(0) | 당기말(1-4) | 전기말(5)
                if category in ['당기', '당기말']:
                    if 1 <= col_idx <= 4:  # 당기말 영역
                        return category
                elif category in ['전기', '전기말']:
                    if col_idx >= 5:  # 전기말 영역
                        return category
        
        # 기본 위치 기반 추론
        return self._infer_category_from_position(col_idx, total_cols)
    
    def _infer_category_from_position(self, col_idx, total_cols):
        """컬럼 위치에서 카테고리 추론 (당기/전기)"""
        # 일반적인 패턴: 첫 번째 컬럼은 구분, 그 다음부터 당기/전기가 번갈아 나타남
        if col_idx == 0:
            return None  # 구분 컬럼
        
        # 컬럼을 절반으로 나누어 당기/전기 판단
        data_cols = total_cols - 1  # 구분 컬럼 제외
        half_point = (data_cols // 2) + 1
        
        if col_idx <= half_point:
            return "당기"
        else:
            return "전기"

    def is_data_table(self, matrix: List[List[str]], table_element=None) -> bool:
        """데이터 테이블 여부 판별 (thead/tbody 구조 우선 확인)"""
        if not matrix or len(matrix) < 2:
            return False
        
        # 1순위: HTML 구조 확인 (thead/tbody가 있으면 데이터 테이블)
        if table_element:
            has_thead = table_element.find('thead') is not None
            has_tbody = table_element.find('tbody') is not None
            
            if has_thead or has_tbody:
                return True
            
            # TABLE 클래스가 있으면 데이터 테이블로 간주
            table_class = table_element.get('class', [])
            if isinstance(table_class, list):
                table_class = ' '.join(table_class)
            if 'table' in table_class.lower():
                return True
        
        # 2순위: 내용 기반 판별 (숫자 비율)
        total_cells = sum(len(row) for row in matrix)
        numeric_cells = 0
        
        for row in matrix:
            for cell in row:
                if cell and re.search(r'\d', str(cell)):
                    numeric_cells += 1
        
        # 숫자 비율 기준을 낮춤 (30% → 20%)
        return numeric_cells / total_cells > 0.2 if total_cells > 0 else False

    def extract_table_metadata(self, table_element, matrix: List[List[str]]) -> Dict[str, Any]:
        """테이블 메타데이터 추출 (강화된 버전)"""
        # 주변 텍스트에서 컨텍스트 추출
        context_text = ""
        
        # 이전 형제 요소들에서 제목/설명 찾기
        prev_elements = []
        current = table_element.previous_sibling
        for _ in range(5):  # 최대 5개 이전 요소 확인
            if current is None:
                break
            if hasattr(current, 'get_text'):
                text = self.clean_text(current.get_text())
                if text and len(text) > 5:
                    prev_elements.append(text)
            current = current.previous_sibling
        
        context_text = " ".join(reversed(prev_elements))
        
        # 테이블 내용 분석
        table_text = " ".join(str(x or "") for r in matrix for x in r)
        combined_text = context_text + " " + table_text
        
        metadata = {}
        
        # 단위 추출 (더 정확한 패턴)
        unit_patterns = [
            r'\(단위\s*[:：]?\s*([^)]+)\)',
            r'단위\s*[:：]\s*([가-힣원백만천]+)',
            r'\(단위\s*([^)]+)\)'
        ]
        
        unit = None
        scale_factor = 1
        for pattern in unit_patterns:
            unit_match = re.search(pattern, combined_text)
            if unit_match:
                unit_text = unit_match.group(1).strip()
                unit = self.unit_mapping.get(unit_text, unit_text)
                scale_factor = self.scale_factors.get(unit, 1)
                break
        
        metadata['unit'] = unit
        metadata['scale_factor'] = scale_factor
        
        # 기간 추출
        period_matches = re.findall(r'제\s*(\d+)\s*기', combined_text)
        if period_matches:
            periods = [f"제 {p} 기" for p in period_matches]
            metadata['periods'] = periods
            metadata['current_period'] = periods[0] if periods else None
        
        # 날짜 범위 추출
        date_patterns = [
            r'(20\d{2})\.(\d{2})\.(\d{2})\s*~\s*(20\d{2})\.(\d{2})\.(\d{2})',
            r'(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\s*~\s*(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일'
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, combined_text)
            if date_match:
                groups = date_match.groups()
                if len(groups) >= 6:
                    metadata['period_start'] = f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                    metadata['period_end'] = f"{groups[3]}-{groups[4].zfill(2)}-{groups[5].zfill(2)}"
                break
        
        # 테이블 제목 추출 (강화된 패턴)
        title_patterns = [
            r'([가-힣\s]+(?:재무상태표|손익계산서|포괄손익계산서|자본변동표|현금흐름표))',
            r'([가-힣\s·•–—―-]{5,30})\s*\(단위',  # 단위 앞의 제목
            r'<표\s*(\d+)>\s*([가-힣\s·•–—―-]{3,30})',  # <표 N> 형식
            r'([가-힣\s]{3,20})\s*\(',  # 괄호 앞의 제목
            r'표\s*\d+\s*([가-힣\s]+)',  # 표 N 뒤의 제목
            r'([가-힣\s]{3,30})\s*\(백만원\)',  # 백만원 앞의 제목
            r'([가-힣\s]{3,30})\s*\(천원\)',   # 천원 앞의 제목
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, combined_text)  # context_text 대신 combined_text도 확인
            if match:
                title = self.clean_text(match.group(1) if '<표' not in pattern else match.group(2))
                if len(title) > 2:
                    metadata['table_title'] = title
                    break
        
        # context_text에서도 한번 더 시도
        if not metadata.get('table_title'):
            for pattern in title_patterns:
                match = re.search(pattern, context_text)
                if match:
                    title = self.clean_text(match.group(1) if '<표' not in pattern else match.group(2))
                    if len(title) > 2:
                        metadata['table_title'] = title
                        break
        
        # 재무제표 유형 판별
        if any(keyword in combined_text for keyword in ['재무상태표', '대차대조표']):
            metadata['statement_type'] = '재무상태표'
        elif any(keyword in combined_text for keyword in ['손익계산서', '포괄손익']):
            metadata['statement_type'] = '손익계산서'
        elif '현금흐름' in combined_text:
            metadata['statement_type'] = '현금흐름표'
        elif '자본변동' in combined_text:
            metadata['statement_type'] = '자본변동표'
        else:
            metadata['statement_type'] = '기타'
        
        return metadata

    def create_table_summary_chunk(self, matrix: List[List[str]], table_metadata: Dict[str, Any], doc_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """테이블 요약 청크 생성 (rag_optimized_parser 방식)"""
        # 테이블 개요 생성
        summary_parts = []
        
        if table_metadata.get('table_title'):
            summary_parts.append(f"테이블: {table_metadata['table_title']}")
        
        if table_metadata.get('statement_type'):
            summary_parts.append(f"유형: {table_metadata['statement_type']}")
        
        if table_metadata.get('periods'):
            summary_parts.append(f"기간: {', '.join(table_metadata['periods'])}")
        
        if table_metadata.get('unit'):
            summary_parts.append(f"단위: {table_metadata['unit']}")
        
        # 주요 항목들 나열
        if len(matrix) > 1:
            items = [row[0] for row in matrix[1:] if row and row[0]]
            if items:
                summary_parts.append(f"주요 항목: {', '.join(items[:5])}")
                if len(items) > 5:
                    summary_parts.append(f"등 총 {len(items)}개 항목")
        
        content = ". ".join(summary_parts)
        
        # 주석 정보 추가
        note_info = f"주석 {table_metadata.get('note_number', '?')}. {table_metadata.get('note_title', '')}"
        if note_info.strip() != "주석 ?.":
            content = f"{note_info} - {content}"
        
        chunk_metadata = {
            **doc_metadata,
            **table_metadata,
            'item_count': len(matrix) - 1 if len(matrix) > 1 else 0,
            'column_count': len(matrix[0]) if matrix else 0
        }
        
        return {
            "id": self.generate_chunk_id(content),
            "content": content,
            "content_type": "table_summary",
            "metadata": chunk_metadata
        }

    def create_financial_data_chunks(self, matrix: List[List[str]], table_metadata: Dict[str, Any], doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """재무 데이터 청크 생성 (강화된 버전)"""
        chunks = []
        
        if len(matrix) < 2:
            return chunks
        
        # 헤더 분석
        header = matrix[0]
        data_rows = matrix[1:]
        
        # 단위 및 스케일 정보
        unit = table_metadata.get('unit')
        scale_factor = table_metadata.get('scale_factor', 1)
        
        # 각 데이터 행을 의미 있는 청크로 변환
        for row_idx, row in enumerate(data_rows):
            if not any(cell for cell in row):
                continue
            
            item_name = row[0] if row else ""
            if not item_name or len(item_name.strip()) < 2:
                continue
            
            # 재무 항목 분류
            financial_category = self.classify_financial_item(item_name)
            
            # 금액 데이터 추출 (정규화 적용)
            amounts = {}
            table_json_row = {}
            
            for i, cell in enumerate(row[1:], 1):
                if i < len(header):
                    col_name = header[i]
                    amount_info = self.normalize_amount(cell, unit, scale_factor)
                    
                    # 청크용 amounts (기존 형식 유지)
                    if amount_info['value'] is not None:
                        amounts[col_name] = amount_info
                    
                    # table_json용 데이터
                    if amount_info['normalized_value'] is not None:
                        table_json_row[col_name] = amount_info['normalized_value']
                    elif cell and cell.strip() not in ['-', '', '―', '—']:
                        table_json_row[col_name] = cell.strip()
            
            if not amounts:
                continue
            
            # table_json을 열(column) 기준으로 구성
            table_json_columns = {}
            table_json_columns[item_name] = {}
            
            for col_name, amount_info in amounts.items():
                if amount_info['normalized_value'] is not None:
                    # 원본 display 값을 우선 사용, 없으면 normalized_value 사용
                    display_value = amount_info.get('display', str(amount_info['normalized_value']))
                    table_json_columns[item_name][col_name] = display_value
            
            # 청크 내용 생성
            content_parts = [f"{item_name}:"]
            
            for col_name, amount_info in amounts.items():
                if amount_info['value'] is not None:
                    content_parts.append(f"{col_name} {amount_info['display']}")
            
            content = " ".join(content_parts)
            
            # 단위 정보 추가
            if unit:
                content += f" (단위: {unit})"
            
            # 주석 정보 추가
            note_info = f"주석 {table_metadata.get('note_number', '?')}. {table_metadata.get('note_title', '')}"
            if note_info.strip() != "주석 ?.":
                content = f"{note_info} - {content}"
            
            # 메타데이터 간소화 (RAG에 필요한 정보만)
            chunk_metadata = {
                'note_number': table_metadata.get('note_number'),
                'note_title': table_metadata.get('note_title'),
                'table_number': table_metadata.get('table_number'),
                'financial_item': item_name,
                'financial_category': financial_category,
                'unit': table_metadata.get('unit'),
                'report_year': doc_metadata.get('report_year'),
                'company': doc_metadata.get('company')
            }
            
            chunk = {
                "id": self.generate_chunk_id(content),
                "content": content,
                "content_type": "financial_data",
                "metadata": chunk_metadata,
                "table_json": table_json_columns  # 열 기준 JSON 구조 (중복 제거)
            }
            
            chunks.append(chunk)
        
        return chunks

    def generate_rag_chunks(self):
        """RAG/벡터DB에 적합한 개별 청크 생성 (기존 방식 - 호환성 유지)"""
        rag_chunks = []
        
        for note_chunk in self.parsed_chunks:
            note_number = note_chunk["note_number"]
            note_title = note_chunk["title"]
            content = note_chunk["content"]
            
            # 1. 노트 콘텐츠 청크 (기존 방식)
            content_chunk = {
                "id": self.generate_chunk_id(f"note_{note_number}_{content}"),
                "content": f"주석 {note_number}. {note_title}\n\n{content}",
                "content_type": "note_content",
                "metadata": {
                    **note_chunk["metadata"],
                    "note_number": note_number,
                    "note_title": note_title,
                    "chunk_source": "note_content"
                }
            }
            rag_chunks.append(content_chunk)
            
            # 2. 개선된 테이블 청크들 추가
            enhanced_tables = note_chunk["tables"].get("enhanced_data", [])
            for table_data in enhanced_tables:
                # 테이블 요약 청크
                if table_data.get("summary_chunk"):
                    rag_chunks.append(table_data["summary_chunk"])
                
                # 재무 데이터 청크들
                if table_data.get("data_chunks"):
                    rag_chunks.extend(table_data["data_chunks"])
        
        return rag_chunks

    def generate_rag_optimized_chunks(self):
        """RAG/벡터DB에 최적화된 청크 생성 (아카이브 형식)"""
        rag_chunks = []
        
        # 1. 재무제표 청크들 먼저 추가
        for statement in self.financial_statements:
            statement_chunk = self._create_financial_statement_chunk(statement)
            rag_chunks.append(statement_chunk)
        
        # 2. 주석 청크들 추가
        for note_chunk in self.parsed_chunks:
            note_number = note_chunk["note_number"]
            note_title = note_chunk["title"]
            content = note_chunk["content"]
            base_metadata = note_chunk["metadata"]
            
            # 주석별로 하나의 완전한 청크 생성 (아카이브 형식)
            company = base_metadata.get('company', 'Unknown')
            year = base_metadata.get('report_year')
            
            # 테이블 데이터 통합
            integrated_tables = {}
            enhanced_tables = note_chunk["tables"].get("enhanced_data", [])
            
            for table_data in enhanced_tables:
                table_number = table_data.get("table_number")
                if table_number:
                    # 테이블 데이터를 행 기준으로 통합
                    table_dict = {}
                    data_chunks = table_data.get("data_chunks", [])
                    
                    for data_chunk in data_chunks:
                        table_json = data_chunk.get("table_json", {})
                        for item_name, row_data in table_json.items():
                            if item_name not in table_dict:
                                table_dict[item_name] = {}
                            table_dict[item_name].update(row_data)
                    
                    if table_dict:
                        # 테이블 메타데이터 추출 개선
                        summary_metadata = table_data.get("summary_chunk", {}).get("metadata", {})
                        
                        # title 추출 (여러 소스에서 시도)
                        table_title = None
                        if summary_metadata.get("table_title"):
                            table_title = summary_metadata["table_title"]
                        else:
                            # data_chunks에서 title 찾기
                            for data_chunk in data_chunks:
                                chunk_meta = data_chunk.get("metadata", {})
                                if chunk_meta.get("table_title"):
                                    table_title = chunk_meta["table_title"]
                                    break
                        
                        # unit 추출 (여러 소스에서 시도)
                        table_unit = None
                        if summary_metadata.get("unit"):
                            table_unit = summary_metadata["unit"]
                        else:
                            # data_chunks에서 unit 찾기
                            for data_chunk in data_chunks:
                                chunk_meta = data_chunk.get("metadata", {})
                                if chunk_meta.get("unit"):
                                    table_unit = chunk_meta["unit"]
                                    break
                        
                        integrated_tables[f"table_{table_number}"] = {
                            "table_number": table_number,
                            "title": table_title,
                            "unit": table_unit,
                            "data": table_dict
                        }
            
            # 텍스트 정리 적용
            cleaned_content = self.clean_text(content)
            
            # 아카이브 형식 청크 생성
            chunk = {
                "doc_id": self.generate_doc_id(company, year, note_number),
                "company": company,
                "report_year": year,
                "note_number": note_number,
                "note_title": note_title,
                "content_type": "note_complete",
                "text_content": cleaned_content,
                "tables": integrated_tables,
                "table_count": len(integrated_tables),
                "metadata": {
                    "content_length": len(cleaned_content),
                    "table_count": len(integrated_tables),
                    "has_tables": len(integrated_tables) > 0
                }
            }
            
            rag_chunks.append(chunk)
        
        return rag_chunks
    
    def _create_financial_statement_chunk(self, statement):
        """재무제표 청크 생성 (주석과 동일한 구조)"""
        statement_type = statement["statement_type"]
        tables = statement["tables"]
        
        # 테이블 데이터 통합 (주석과 완전히 동일한 방식)
        integrated_tables = {}
        statement_text_parts = [f"{statement_type} 주요 재무 정보"]
        
        for table_data in tables:
            table_number = table_data["table_number"]
            matrix = table_data["matrix"]
            metadata = table_data["metadata"]
            
            # 매트릭스를 딕셔너리 형태로 변환 (노트북 코드 기반 개선)
            table_dict = {}
            if len(matrix) > 1:  # 재무제표 데이터 테이블
                # 노트북 코드의 build_header 로직 활용
                cols, header_rows_count, body_rows = self.build_header(matrix, max_header_rows=4)
                
                print(f"         📋 헤더: {cols[:4]} (헤더 행수: {header_rows_count})")
                print(f"         📊 데이터 행수: {len(body_rows)}")
                
                # 데이터 행 처리
                for row_idx, row in enumerate(body_rows):
                    if row and len(row) > 0 and row[0] and str(row[0]).strip():
                        item_name = self.clean_text(str(row[0]))
                        
                        # 재무제표 항목인지 확인 (더 넓은 범위)
                        if (len(item_name) > 1 and 
                            (re.search(r'[Ⅰ-Ⅻ]', item_name) or  # 로마숫자
                             re.search(r'[가-힣]', item_name) or   # 한글 포함
                             re.search(r'\d+\.', item_name))):    # 숫자. 형태
                            
                            table_dict[item_name] = {}
                            
                            # 각 컬럼의 값 추출
                            for col_idx, value in enumerate(row):
                                if col_idx > 0 and col_idx < len(cols):  # 첫 번째 컬럼(항목명) 제외
                                    col_name = cols[col_idx]
                                    
                                    if value and str(value).strip():
                                        clean_value = str(value).strip()
                                        # 의미있는 값인지 확인 (숫자나 텍스트)
                                        if (clean_value not in ['', '-', '―', '—'] and 
                                            (re.search(r'\d', clean_value) or len(clean_value) > 1)):
                                            
                                            # 같은 컬럼명이 있으면 값 통합 (공백으로 연결)
                                            if col_name in table_dict[item_name]:
                                                existing_value = table_dict[item_name][col_name]
                                                if existing_value != clean_value:  # 다른 값이면 통합
                                                    table_dict[item_name][col_name] = f"{existing_value} {clean_value}".strip()
                                            else:
                                                table_dict[item_name][col_name] = clean_value
                            
                            # 빈 데이터면 제거
                            if not table_dict[item_name]:
                                del table_dict[item_name]
                
                print(f"         📊 추출된 항목 수: {len(table_dict)}")
            
            if table_dict:
                integrated_tables[f"table_{table_number}"] = {
                    "table_number": table_number,
                    "title": metadata.get('table_title', statement_type),
                    "unit": metadata.get('unit'),
                    "data": table_dict
                }
                
                # 주요 항목들을 텍스트에 추가
                main_items = list(table_dict.keys())[:5]  # 처음 5개 항목
                if main_items:
                    statement_text_parts.append(f"주요 항목: {', '.join(main_items)}")
        
        # 재무제표 청크 생성 (주석과 동일한 구조)
        company = "삼성전자주식회사"
        year = self.file_year or 2014
        
        text_content = ". ".join(statement_text_parts)
        
        # 주석 구조와 완전히 동일하게 생성
        chunk = {
            "doc_id": self.generate_doc_id(company, year, f"fs_{statement_type.lower()}"),
            "company": company,
            "report_year": year,
            "note_number": f"FS_{statement_type}",
            "note_title": statement_type,
            "content_type": "note_complete",  # 주석과 동일하게
            "text_content": text_content,
            "tables": integrated_tables if integrated_tables else {},  # 빈 딕셔너리로
            "table_count": len(integrated_tables),
            "metadata": {
                "content_length": len(text_content),
                "table_count": len(integrated_tables),
                "has_tables": len(integrated_tables) > 0
            }
        }
        
        return chunk

    def save_results(self, input_file_path, output_dir="/Users/dan/Desktop/snu_project/data/processed/universal_audit_parser_fixed"):
        """결과를 지정된 경로에 저장"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 입력 파일명에서 출력 파일명 생성
        base_name = os.path.splitext(os.path.basename(input_file_path))[0]
        output_file = os.path.join(output_dir, f"{base_name}_parsed.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.parsed_chunks, f, ensure_ascii=False, indent=2)
        
        print(f"💾 결과가 {output_file}에 저장되었습니다.")
        
        # RAG 청크도 저장 (기존 방식)
        rag_chunks = self.generate_rag_chunks()
        rag_output_dir = "/Users/dan/Desktop/snu_project/data/processed/rag_chunks_fixed"
        os.makedirs(rag_output_dir, exist_ok=True)
        rag_output_file = os.path.join(rag_output_dir, f"{base_name}_rag_chunks.json")
        
        with open(rag_output_file, "w", encoding="utf-8") as f:
            json.dump(rag_chunks, f, ensure_ascii=False, indent=2)
        
        print(f"💾 RAG 청크가 {rag_output_file}에 저장되었습니다.")
        
        # RAG 최적화 청크도 저장 (새로운 형식)
        rag_optimized_chunks = self.generate_rag_optimized_chunks()
        rag_optimized_output_dir = "/Users/dan/Desktop/snu_project/data/processed/rag_chunks_optimized"
        os.makedirs(rag_optimized_output_dir, exist_ok=True)
        rag_optimized_output_file = os.path.join(rag_optimized_output_dir, f"{base_name}_rag_optimized.json")
        
        with open(rag_optimized_output_file, "w", encoding="utf-8") as f:
            json.dump(rag_optimized_chunks, f, ensure_ascii=False, indent=2)
        
        print(f"💾 RAG 최적화 청크가 {rag_optimized_output_file}에 저장되었습니다.")
        
        return output_file, rag_output_file, rag_optimized_output_file

    def print_summary(self):
        print("\n" + "="*80)
        print("📊 파싱 결과 요약")
        print("="*80)
        print(f"파일 연도: {self.file_year}년")
        print(f"파일 형식: {self.file_format}")
        print(f"총 재무제표 개수: {len(self.financial_statements)}개")
        print(f"총 주석 개수: {len(self.parsed_chunks)}개")
        
        # 재무제표 요약
        if self.financial_statements:
            print("\n📋 발견된 재무제표:")
            for stmt in self.financial_statements:
                print(f"   - {stmt['statement_type']}: {stmt['table_count']}개 테이블")
        
        print("\n📝 주석 상세 정보:")
        
        total_tables = 0
        total_enhanced_chunks = 0
        for chunk in self.parsed_chunks:
            table_count = chunk['tables']['count']
            enhanced_data = chunk['tables'].get('enhanced_data', [])
            enhanced_chunks = sum(len(t.get('data_chunks', [])) + (1 if t.get('summary_chunk') else 0) for t in enhanced_data)
            
            total_tables += table_count
            total_enhanced_chunks += enhanced_chunks
            
            print(f"\n주석 {chunk['note_number']:2s}: {chunk['title']}")
            preview = chunk["content"][:100].replace("\\n", " ")
            print(f"   📄 내용: {preview}...")
            print(f"   📊 길이: {chunk['content_length']}자")
            print(f"   📋 테이블: {table_count}개")
            print(f"   🔍 개선된 청크: {enhanced_chunks}개")
        
        print(f"\n총 테이블: {total_tables}개")
        print(f"총 개선된 청크: {total_enhanced_chunks}개")
        
        found_numbers = {int(c["note_number"]) for c in self.parsed_chunks if c["note_number"].isdigit()}
        expected_numbers = set(range(1, 36))
        missing = sorted(list(expected_numbers - found_numbers))
        if missing:
            print(f"\n❌ 누락된 주석: {missing}")
        else:
            print(f"\n✅ 1~35번 주석 모두 완벽하게 파싱됨!")

def main():
    parser = UniversalAuditParser()
    
    # 입력 파일 찾기
    input_files = parser.find_input_files()
    
    if not input_files:
        print("❌ 처리할 감사보고서 파일을 찾을 수 없습니다.")
        return
    
    # 각 파일 처리
    for file_path in input_files:
        try:
            print(f"\n{'='*100}")
            print(f"🔄 처리 중: {file_path}")
            print(f"{'='*100}")
            
            chunks = parser.parse_file(file_path)
            output_files = parser.save_results(file_path)
            parser.print_summary()
            
            print(f"\n✅ {file_path} 처리 완료!")
            if isinstance(output_files, tuple):
                print(f"📁 기본 파싱 결과: {output_files[0]}")
                print(f"📁 RAG 청크 (기존): {output_files[1]}")
                print(f"📁 RAG 최적화 청크: {output_files[2]}")
            else:
                print(f"📁 출력 파일: {output_files}")
            
        except Exception as e:
            print(f"❌ {file_path} 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            continue

if __name__ == "__main__":
    main()
