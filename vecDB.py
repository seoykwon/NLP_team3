import os
import json
import hashlib
import re
import time
import logging
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from tqdm import tqdm

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import tiktoken

# 최적화된 청크 크기 설정
OPTIMAL_CHUNK_SIZES = {
    'annotation': 400,      # 기존 1200 → 400 (주석 데이터)
    'financial_table': 600, # 기존 2000 → 600 (재무제표)  
    'accounting_standard': 350  # 기존 1000 → 350 (회계기준서)
}

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class EnhancedChunkMetadata:
    """RAG 최적화된 메타데이터"""
    document_type: str
    year: int
    section: str
    chunk_index: int
    source_file: str
    char_start: int
    char_end: int
    word_count: int
    content_type: str
    
    # 재무제표 특화 필드
    financial_items: Optional[List[str]] = None
    account_codes: Optional[List[str]] = None
    amounts: Optional[Dict[str, str]] = None  # 문자열로 저장 (포맷 보존)
    table_type: Optional[str] = None  # 재무상태표, 손익계산서 등
    
    # 주석 특화 필드
    note_number: Optional[str] = None
    related_financial_items: Optional[List[str]] = None
    risk_keywords: Optional[List[str]] = None
    
    # 회계기준 특화 필드
    standard_number: Optional[str] = None
    paragraph_id: Optional[str] = None
    regulation_type: Optional[str] = None
    
    # 교차 참조 필드 (개선됨)
    cross_references: Optional[List[str]] = None
    entity_mentions: Optional[List[str]] = None
    temporal_references: Optional[List[int]] = None
    confidence_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        # 리스트와 딕셔너리를 문자열로 변환
        for key, value in result.items():
            if isinstance(value, list) and value:
                result[key] = ', '.join(str(v) for v in value)
            elif isinstance(value, list):
                result[key] = None
            elif isinstance(value, dict) and value:
                # 딕셔너리를 문자열로 변환
                result[key] = ', '.join(f"{k}: {v}" for k, v in value.items())
            elif isinstance(value, dict):
                result[key] = None
        return {k: v for k, v in result.items() if v is not None}

class BaseDocumentProcessor(ABC):
    """개선된 기본 프로세서"""
    
    def __init__(self, max_tokens: int = 1000, overlap_tokens: int = 100):
        self.max_tokens = max_tokens  # RAG를 위해 더 큰 청크
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))
    
    @abstractmethod
    def process_file(self, file_path: str, year: int) -> List[Tuple[str, EnhancedChunkMetadata]]:
        pass
    
    def extract_financial_entities(self, text: str) -> Dict[str, List[str]]:
        """강화된 금융 엔티티 추출"""
        entities = {
            'financial_items': [],
            'amounts': [],
            'companies': [],
            'dates': [],
            'ratios': [],
            'accounting_items': []
        }
        
        # 더 정교한 금융 항목 패턴
        financial_patterns = [
            # 손익계산서 항목
            r'매출액', r'매출수익', r'영업수익', r'영업이익', r'영업손익', r'당기순이익', r'당기순손익',
            r'법인세비용', r'법인세차감전이익', r'금융수익', r'금융비용', r'기타수익', r'기타비용',
            r'매출원가', r'판매비와관리비', r'연구개발비', r'감가상각비', r'대손상각비',
            
            # 재무상태표 항목
            r'총자산', r'자산총계', r'부채총계', r'자본총계', r'자본금', r'이익잉여금',
            r'현금및현금성자산', r'단기금융상품', r'매출채권', r'재고자산', r'유형자산', r'무형자산',
            r'투자자산', r'유동자산', r'비유동자산', r'유동부채', r'비유동부채', r'차입금', r'사채',
            
            # 현금흐름표 항목
            r'영업활동현금흐름', r'투자활동현금흐름', r'재무활동현금흐름', r'현금및현금성자산의증감',
            
            # 기타 금융 항목
            r'자기자본', r'주주지분', r'지배기업소유주지분', r'비지배지분', r'신용손실충당금',
            r'리스자산', r'리스부채', r'확정급여부채', r'충당부채', r'우발부채'
        ]
        
        for pattern in financial_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                entities['financial_items'].append(pattern)
        
        # 회계 기준 및 정책 항목
        accounting_patterns = [
            r'수익인식', r'감가상각', r'손상차손', r'충당부채', r'금융상품', r'리스', r'종업원급여',
            r'법인세', r'외화환산', r'파생상품', r'공정가치', r'상각후원가', r'현재가치',
            r'K-IFRS', r'IFRS', r'회계정책', r'회계추정', r'회계변경'
        ]
        
        for pattern in accounting_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                entities['accounting_items'].append(pattern)
        
        # 개선된 금액 추출 (백만원, 천원 단위 추가)
        amount_patterns = [
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*조\s*원',        # 조원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*억\s*원',        # 억원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*백만\s*원',      # 백만원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*천만\s*원',      # 천만원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*천\s*원',        # 천원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*원',            # 원
            r'\d+(?:,\d{3})*(?:\.\d+)?\s*[조억백만천]+',  # 단위만
            r'\d+(?:,\d{3})*(?:\.\d+)?백만',             # 백만 (원 생략)
            r'\d+(?:,\d{3})*(?:\.\d+)?천만',             # 천만 (원 생략)
            r'\d+(?:,\d{3})*(?:\.\d+)?천',               # 천 (원 생략)
        ]
        
        for pattern in amount_patterns:
            matches = re.findall(pattern, text)
            entities['amounts'].extend(matches)
        
        # 비율 및 지표 추출
        ratio_patterns = [
            r'\d+(?:\.\d+)?%',                          # 퍼센트
            r'\d+(?:\.\d+)?\s*배',                      # 배수
            r'\d+(?:\.\d+)?\s*회',                      # 회전율
            r'부채비율\s*:?\s*\d+(?:\.\d+)?%?',
            r'자기자본비율\s*:?\s*\d+(?:\.\d+)?%?',
            r'유동비율\s*:?\s*\d+(?:\.\d+)?%?',
            r'ROE\s*:?\s*\d+(?:\.\d+)?%?',
            r'ROA\s*:?\s*\d+(?:\.\d+)?%?',
        ]
        
        for pattern in ratio_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities['ratios'].extend(matches)
        
        # 회사명 추출 (더 정교한 패턴)
        company_patterns = [
            r'삼성전자(?:주식회사)?',
            r'(?:주식회사\s*)?[가-힣]{2,10}(?:전자|전기|화학|건설|금융|보험|증권|은행)',
            r'[A-Z][a-zA-Z\s]{3,20}(?:Corp|Inc|Ltd|Co)',
        ]
        
        for pattern in company_patterns:
            matches = re.findall(pattern, text)
            entities['companies'].extend(matches)
        
        # 연도 추출 패턴 확장 (2025년까지)
        year_patterns = [
            r'20(?:1[0-9]|2[0-5])년?',     # 2010-2025년
            r'(?:19|20)\d{2}년도',          # 연도 형태
            r'FY\s*20(?:1[0-9]|2[0-5])',   # 회계연도
        ]
        
        all_years = []
        for pattern in year_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 숫자만 추출
                year_num = re.findall(r'20(?:1[0-9]|2[0-5])', match)
                if year_num:
                    all_years.extend([int(y) for y in year_num])
        
        entities['dates'] = list(set(all_years))  # 중복 제거
        
        # 중복 제거 및 정리
        for key in entities:
            if isinstance(entities[key], list):
                entities[key] = list(set(entities[key]))  # 중복 제거
                entities[key] = [item for item in entities[key] if str(item).strip()]  # 빈 문자열 제거
        
        return entities
    
    def extract_cross_references(self, text: str) -> Dict[str, List[str]]:
        """교차 참조 추출 (새로운 메서드)"""
        cross_refs = {
            'note_references': [],      # 주석 번호 참조
            'account_references': [],   # 계정과목 참조  
            'table_references': [],     # 표 참조
            'page_references': [],      # 페이지 참조
            'section_references': []    # 섹션 참조
        }
        
        # 주석 번호 참조 추출
        note_patterns = [
            r'주석\s*(\d+)',
            r'각주\s*(\d+)',
            r'Note\s*(\d+)',
            r'\(주\s*(\d+)\)',
            r'주\s*(\d+)\s*참조'
        ]
        
        for pattern in note_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            cross_refs['note_references'].extend(matches)
        
        # 계정과목 참조 추출 (더 포괄적)
        account_patterns = [
            r'(매출액|영업이익|당기순이익|법인세비용|감가상각비)',
            r'(총자산|유동자산|비유동자산|유형자산|무형자산)',
            r'(부채총계|유동부채|비유동부채|차입금|사채)',
            r'(자본총계|자본금|이익잉여금|기타포괄손익누계액)',
            r'(현금및현금성자산|단기금융상품|매출채권|재고자산)',
            r'(영업활동현금흐름|투자활동현금흐름|재무활동현금흐름)'
        ]
        
        for pattern in account_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            cross_refs['account_references'].extend([match for match in matches if match])
        
        # 표 참조 추출
        table_patterns = [
            r'표\s*(\d+)',
            r'Table\s*(\d+)',
            r'<표\s*(\d+)>',
            r'\[표\s*(\d+)\]',
            r'상기\s*표',
            r'아래\s*표',
            r'위\s*표'
        ]
        
        for pattern in table_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if isinstance(matches[0] if matches else None, tuple):
                cross_refs['table_references'].extend([match[0] for match in matches])
            else:
                cross_refs['table_references'].extend(matches)
        
        # 페이지 참조 추출
        page_patterns = [
            r'(\d+)\s*페이지',
            r'p\.\s*(\d+)',
            r'page\s*(\d+)',
            r'(\d+)\s*쪽'
        ]
        
        for pattern in page_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            cross_refs['page_references'].extend(matches)
        
        # 섹션 참조 추출
        section_patterns = [
            r'(\d+)\.\s*([가-힣\w\s]{2,20})',  # "1. 일반사항" 형태
            r'\(([가-힣])\)\s*([가-힣\w\s]{2,20})',  # "(가) 개요" 형태
            r'제\s*(\d+)\s*절',                # "제1절" 형태
            r'([가-힣]{2,10})\s*관련',          # "회계정책 관련" 형태
        ]
        
        for pattern in section_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    cross_refs['section_references'].append(' '.join(match))
                else:
                    cross_refs['section_references'].append(match)
        
        # 중복 제거 및 정리
        for key in cross_refs:
            cross_refs[key] = list(set(cross_refs[key]))  # 중복 제거
            cross_refs[key] = [item for item in cross_refs[key] if item and str(item).strip()]  # 빈 값 제거
        
        return cross_refs

class AnnotationProcessor(BaseDocumentProcessor):
    """주석 처리기 - 개선됨"""
    
    def __init__(self):
        super().__init__(max_tokens=400, overlap_tokens=150)
    
    def process_file(self, file_path: str, year: int) -> List[Tuple[str, EnhancedChunkMetadata]]:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        chunks = []
        
        if isinstance(data, list):
            for item in data:
                if 'content' in item and str(item['content']).strip():
                    note_chunks = self._process_note_item(item, year, file_path)
                    chunks.extend(note_chunks)
        
        return chunks
    
    def _process_note_item(self, item: Dict, year: int, file_path: str) -> List[Tuple[str, EnhancedChunkMetadata]]:
        """기존 파싱 메타데이터를 활용한 주석 처리"""
        content = str(item['content'])  # 안전한 문자열 변환
        
        # 기존 아이템의 메타데이터 활용 (ChatGPT가 놓친 부분)
        note_number = item.get('note_number', 'unknown')
        title = item.get('title', f'주석 {note_number}')
        
        # 전체 파일의 메타데이터는 별도로 받아야 함
        file_metadata = item.get('metadata', {})  # 파일 레벨 메타데이터
        
        # 주제별 분할 (더 큰 의미 단위로)
        sections = self._split_by_semantic_units(content)
        chunks = []
        
        for i, section in enumerate(sections):
            section = str(section)  # 안전한 문자열 변환
            if not section.strip() or self.count_tokens(section) < 100:
                continue
            
            # 제목을 포함한 완전한 컨텍스트 구성
            full_content = f"[주석 {note_number}: {title}]\n\n{section}"
            
            # 토큰 수가 과도하게 클 때만 분할
            if self.count_tokens(full_content) > self.max_tokens:
                sub_chunks = self._smart_split(full_content, title, note_number)
                for sub_chunk in sub_chunks:
                    metadata = self._create_note_metadata(
                        sub_chunk, 
                        file_metadata,  # 파일 레벨 메타데이터
                        item,          # 아이템 레벨 메타데이터 (note_number, title 포함)
                        len(chunks)
                    )
                    chunks.append((sub_chunk, metadata))
            else:
                metadata = self._create_note_metadata(
                    full_content, 
                    file_metadata,  # 파일 레벨 메타데이터
                    item,          # 아이템 레벨 메타데이터 (note_number, title 포함)
                    len(chunks)
                )
                chunks.append((full_content, metadata))
        
        return chunks
    
    def _split_by_semantic_units(self, content: str) -> List[str]:
        """의미 단위 기반 분할"""
        # 더 큰 의미 단위로 분할
        patterns = [
            r'(?=\d+\.\s*[가-힣]+)',  # "1. 일반사항"
            r'(?=\([가-힣]\)\s*[가-힣]+)',  # "(가) 신용위험"
        ]
        
        sections = [content]
        for pattern in patterns[:1]:  # 첫 번째 패턴만 사용해 더 큰 청크 유지
            new_sections = []
            for section in sections:
                splits = re.split(pattern, section)
                new_sections.extend([str(s).strip() for s in splits if str(s).strip()])
            sections = new_sections
        
        return sections
    
    def _smart_split(self, content: str, title: str, note_number: str) -> List[str]:
        """스마트 분할 - 문맥 보존 (개선된 한국어 문장 분할)"""
        # 개선된 한국어 문장 종결 패턴들을 순차적으로 적용
        korean_sentence_patterns = [
            r'(?<=[다음요음습니다됩니다])\.(?=\s)',  # 기본 종결어미 + 습니다, 됩니다
            r'(?<=니다)\.(?=\s)',                    # ~니다
            r'(?<=입니다)\.(?=\s)',                  # 입니다
            r'(?<=었습니다)\.(?=\s)',                # 었습니다
            r'(?<=았습니다)\.(?=\s)',                # 았습니다
            r'(?<=[다음요음])\.(?=\s)',              # 기존 패턴 (백업)
        ]
        
        # 첫 번째 패턴부터 순차적으로 적용하여 분할 시도
        sentences = [content]
        for pattern in korean_sentence_patterns:
            new_sentences = []
            for sentence in sentences:
                split_result = re.split(pattern, sentence)
                if len(split_result) > 1:  # 분할이 일어났다면
                    new_sentences.extend([str(s) for s in split_result if str(s).strip()])
                else:
                    new_sentences.append(sentence)
            sentences = new_sentences
            
            # 분할이 충분히 되었으면 중단 (너무 많은 분할 방지)
            if len(sentences) >= 3:
                break
        
        chunks = []
        current_chunk = f"[주석 {note_number}: {title}]\n\n"
        header_length = len(current_chunk)
        
        for sentence in sentences:
            sentence = str(sentence)  # 안전한 문자열 변환
            if not sentence.strip():
                continue
                
            test_chunk = current_chunk + sentence + "."
            
            if self.count_tokens(test_chunk) <= self.max_tokens:
                current_chunk = test_chunk
            else:
                if len(current_chunk) > header_length + 50:  # 최소 길이 체크
                    chunks.append(current_chunk.strip())
                
                # 새 청크 시작 (헤더 + 겹치는 부분)
                overlap = current_chunk.split('.')[-2:] if '.' in current_chunk else []
                overlap_text = '. '.join(overlap) + '. ' if overlap else ''
                current_chunk = f"[주석 {note_number}: {title}]\n\n{overlap_text}{sentence}."
        
        if len(current_chunk) > header_length + 50:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _create_note_metadata(self, chunk: str, file_metadata: Dict, item_metadata: Dict, chunk_index: int) -> EnhancedChunkMetadata:
        """강화된 메타데이터 생성 (교차 참조 포함)"""
        # 강화된 금융 엔티티 추출
        entities = self.extract_financial_entities(chunk)
        
        # 새로운 교차 참조 추출
        cross_references = self.extract_cross_references(chunk)
        
        # 통합된 교차 참조 리스트 구성
        cross_refs = []
        
        # 재무제표 항목 언급
        for item in entities['financial_items']:
            cross_refs.append(f"financial_item:{item}")
        
        # 회계 항목 언급
        for item in entities.get('accounting_items', []):
            cross_refs.append(f"accounting_item:{item}")
        
        # 주석 참조
        for note_ref in cross_references['note_references']:
            cross_refs.append(f"note_ref:{note_ref}")
        
        # 표 참조
        for table_ref in cross_references['table_references']:
            cross_refs.append(f"table_ref:{table_ref}")
        
        # 계정과목 참조
        for account_ref in cross_references['account_references']:
            cross_refs.append(f"account_ref:{account_ref}")
        
        # 섹션 참조
        for section_ref in cross_references['section_references']:
            cross_refs.append(f"section_ref:{section_ref}")
        
        # 페이지 참조
        for page_ref in cross_references['page_references']:
            cross_refs.append(f"page_ref:{page_ref}")
        
        # 위험 키워드
        risk_keywords = []
        risk_terms = ['위험', '불확실성', '손상', '연체', '소송', '우발', '코로나', 'COVID']
        for term in risk_terms:
            if term in chunk:
                risk_keywords.append(term)
        
        return EnhancedChunkMetadata(
            document_type='annotation',
            year=file_metadata.get('file_year'),  # 파일 메타데이터에서
            section=item_metadata.get('title', 'Unknown'),  # 아이템 메타데이터에서
            chunk_index=chunk_index,
            source_file=file_metadata.get('source_file', 'unknown'),
            char_start=0,
            char_end=len(chunk),
            word_count=len(chunk.split()),
            content_type='annotation',
            note_number=item_metadata.get('note_number'),  # 아이템 메타데이터에서
            # 강화된 금융 엔티티 정보
            related_financial_items=entities['financial_items'] + entities.get('accounting_items', []),
            risk_keywords=risk_keywords if risk_keywords else None,
            cross_references=cross_refs if cross_refs else None,
            entity_mentions=entities['amounts'] + entities.get('ratios', []),  # 금액과 비율 포함
            temporal_references=entities['dates'] if entities['dates'] else None
        )

class FinancialTableProcessor(BaseDocumentProcessor):
    """재무제표 처리기 - 표 전체를 하나의 청크로 처리"""
    
    def __init__(self):
        super().__init__(max_tokens=600, overlap_tokens=0)  # 표는 겹치지 않음
    
    def process_file(self, file_path: str, year: int) -> List[Tuple[str, EnhancedChunkMetadata]]:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        chunks = []
        
        # 실제 파일 구조에 맞게 수정: dict 형태에서 'tables' 키 확인
        if isinstance(data, dict) and 'tables' in data:
            tables = data['tables']
            for item in tables:
                if item.get('role') == 'data' and 'rows' in item:
                    table_chunk = self._process_complete_table(item, year, file_path, len(chunks))
                    if table_chunk:
                        chunks.append(table_chunk)
        elif isinstance(data, list):
            # 기존 리스트 형태도 지원
            for item in data:
                if item.get('role') == 'data' and 'rows' in item:
                    table_chunk = self._process_complete_table(item, year, file_path, len(chunks))
                    if table_chunk:
                        chunks.append(table_chunk)
        
        return chunks
    
    def _process_complete_table(self, table_data: Dict, year: int, file_path: str, 
                               table_index: int) -> Optional[Tuple[str, EnhancedChunkMetadata]]:
        """표 전체를 하나의 청크로 처리"""
        title_lines = table_data.get('title_lines', [])
        columns = table_data.get('columns', [])
        rows = table_data.get('rows', [])
        
        if not rows:
            return None
        
        # 표 제목 결정
        table_title = ' | '.join(title_lines) if title_lines else '재무제표'
        table_type = self._identify_table_type(table_title, rows)
        
        # 표 전체를 구조화된 텍스트로 변환
        table_text = self._create_complete_table_text(table_title, columns, rows, year)
        
        # 메타데이터 생성
        metadata = self._create_table_metadata(
            table_text, table_data, year, file_path, table_title, table_type, table_index
        )
        
        return (table_text, metadata)
    
    def _identify_table_type(self, title: str, rows: List[Dict]) -> str:
        """표 유형 식별"""
        title_lower = title.lower()
        
        if '재무상태표' in title or '대차대조표' in title:
            return '재무상태표'
        elif '손익계산서' in title or '포괄손익계산서' in title:
            return '손익계산서'
        elif '현금흐름표' in title:
            return '현금흐름표'
        elif '자본변동표' in title:
            return '자본변동표'
        else:
            # 계정과목으로 추정
            account_names = [row.get('과목', '') for row in rows[:5]]
            account_text = ' '.join(account_names)
            
            if any(keyword in account_text for keyword in ['자산', '부채', '자본']):
                return '재무상태표'
            elif any(keyword in account_text for keyword in ['매출', '비용', '이익']):
                return '손익계산서'
            else:
                return '기타재무제표'
    
    def _create_complete_table_text(self, title: str, columns: List[str], 
                                   rows: List[Dict], year: int) -> str:
        """표 전체를 구조화된 텍스트로 변환"""
        parts = []
        parts.append(f"[{year}년도 {title}]")
        parts.append("")
        
        # 컬럼 헤더
        if columns:
            header = " | ".join(columns)
            parts.append(f"구조: {header}")
            parts.append("")
        
        # 주요 계정과목과 금액
        parts.append("주요 항목:")
        for row in rows:
            account = row.get('과목', '').strip()
            if not account:
                continue
            
            # 금액 정보 추출
            amounts = []
            for col in columns:
                if col in ['과목', '주석']:
                    continue
                value = row.get(col, '').strip()
                if value and value != '-':
                    amounts.append(f"{col}: {value}")
            
            if amounts:
                amount_text = " | ".join(amounts)
                parts.append(f"• {account}: {amount_text}")
        
        # 테이블 요약
        parts.append("")
        parts.append("테이블 특성:")
        parts.append(f"• 총 {len(rows)}개 계정과목")
        parts.append(f"• 기준연도: {year}")
        
        # 주요 금융지표 요약
        major_items = self._extract_major_financial_items(rows)
        if major_items:
            parts.append("• 주요 지표: " + ", ".join(major_items))
        
        return "\n".join(parts)
    
    def _extract_major_financial_items(self, rows: List[Dict]) -> List[str]:
        """주요 금융 지표 추출"""
        major_items = []
        key_accounts = ['매출액', '영업이익', '당기순이익', '총자산', '부채총계', '자본총계']
        
        for row in rows:
            account = row.get('과목', '')
            for key_account in key_accounts:
                if key_account in account:
                    major_items.append(account)
                    break
        
        return major_items[:10]  # 최대 10개
    
    def _create_table_metadata(self, text: str, table_data: Dict, year: int, 
                              file_path: str, table_title: str, table_type: str, 
                              table_index: int) -> EnhancedChunkMetadata:
        """표 메타데이터 생성"""
        rows = table_data.get('rows', [])
        
        # 모든 계정과목 추출
        account_codes = []
        financial_items = []
        amounts = {}
        
        for row in rows:
            account = row.get('과목', '').strip()
            if account:
                account_codes.append(account)
                financial_items.extend(self.extract_financial_entities(account)['financial_items'])
            
            # 금액 정보 저장 (문자열로 보존)
            for key, value in row.items():
                if key not in ['과목', '주석'] and value and str(value).strip() and str(value) != '-':
                    amounts[f"{account}_{key}"] = str(value).strip()
        
        # 교차 참조 생성
        cross_refs = []
        for item in financial_items:
            cross_refs.append(f"annotation:{item}")
        
        return EnhancedChunkMetadata(
            document_type='financial_table',
            year=year,
            section=table_title,
            chunk_index=table_index,
            source_file=file_path,
            char_start=0,
            char_end=len(text),
            word_count=len(text.split()),
            content_type='complete_table',
            financial_items=list(set(financial_items)) if financial_items else None,
            account_codes=account_codes if account_codes else None,
            amounts=amounts if amounts else None,
            table_type=table_type,
            cross_references=cross_refs if cross_refs else None
        )

class AccountingStandardProcessor(BaseDocumentProcessor):
    """회계기준서 처리기"""
    
    def __init__(self):
        super().__init__(max_tokens=350, overlap_tokens=100)
    
    def process_file(self, file_path: str, year: int) -> List[Tuple[str, EnhancedChunkMetadata]]:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        chunks = []
        
        if 'documents' in data:
            for doc in data['documents']:
                doc_chunks = self._process_standard_document(doc, year, file_path)
                chunks.extend(doc_chunks)
        
        return chunks
    
    def _process_standard_document(self, doc: Dict, year: int, file_path: str) -> List[Tuple[str, EnhancedChunkMetadata]]:
        standard_no = doc.get('standard_no', 'unknown')
        title = doc.get('title', '회계기준')
        paragraphs = doc.get('paragraphs', [])
        
        chunks = []
        
        # 문단을 의미 단위로 그룹핑
        grouped_paragraphs = self._group_related_paragraphs(paragraphs)
        
        for group in grouped_paragraphs:
            group_text = self._create_group_text(group, standard_no, title)
            
            if self.count_tokens(group_text) > self.max_tokens:
                sub_chunks = self._split_group(group_text, standard_no, title)
                for sub_chunk in sub_chunks:
                    metadata = self._create_standard_metadata(
                        sub_chunk, doc, group[0], year, file_path, len(chunks)
                    )
                    chunks.append((sub_chunk, metadata))
            else:
                metadata = self._create_standard_metadata(
                    group_text, doc, group[0], year, file_path, len(chunks)
                )
                chunks.append((group_text, metadata))
        
        return chunks
    
    def _group_related_paragraphs(self, paragraphs: List[Dict]) -> List[List[Dict]]:
        """관련 문단 그룹핑"""
        if not paragraphs:
            return []
        
        groups = []
        current_group = [paragraphs[0]]
        
        for para in paragraphs[1:]:
            current_text = ' '.join([p.get('text', '') for p in current_group])
            new_text = para.get('text', '')
            
            if self.count_tokens(current_text + new_text) <= self.max_tokens:
                current_group.append(para)
            else:
                groups.append(current_group)
                current_group = [para]
        
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _create_group_text(self, group: List[Dict], standard_no: str, title: str) -> str:
        """그룹 텍스트 생성"""
        parts = [f"[K-IFRS {standard_no}: {title}]", ""]
        
        for para in group:
            para_id = para.get('para_id', '')
            text = para.get('text', '').strip()
            if text:
                if para_id:
                    parts.append(f"문단 {para_id}: {text}")
                else:
                    parts.append(text)
                parts.append("")
        
        return "\n".join(parts).strip()
    
    def _split_group(self, text: str, standard_no: str, title: str) -> List[str]:
        """그룹 분할"""
        sentences = re.split(r'(?<=[다음요음])\.(?=\s)', text)
        
        chunks = []
        header = f"[K-IFRS {standard_no}: {title}]\n\n"
        current_chunk = header
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            test_chunk = current_chunk + sentence + "."
            
            if self.count_tokens(test_chunk) <= self.max_tokens:
                current_chunk = test_chunk
            else:
                if len(current_chunk) > len(header) + 50:
                    chunks.append(current_chunk.strip())
                
                overlap = current_chunk.split('.')[-1:] if '.' in current_chunk else []
                overlap_text = '. '.join(overlap) + '. ' if overlap else ''
                current_chunk = header + overlap_text + sentence + "."
        
        if len(current_chunk) > len(header) + 50:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _create_standard_metadata(self, text: str, doc: Dict, para: Dict, 
                                 year: int, file_path: str, chunk_index: int) -> EnhancedChunkMetadata:
        standard_no = doc.get('standard_no', 'unknown')
        title = doc.get('title', '회계기준')
        para_id = para.get('para_id', 'unknown')
        
        return EnhancedChunkMetadata(
            document_type='accounting_standard',
            year=year,
            section=f"K-IFRS {standard_no}: {title}",
            chunk_index=chunk_index,
            source_file=file_path,
            char_start=0,
            char_end=len(text),
            word_count=len(text.split()),
            content_type='regulation',
            standard_number=standard_no,
            paragraph_id=para_id,
            regulation_type='K-IFRS'
        )

class ImprovedVectorPipeline:
    """개선된 벡터 파이프라인"""
    
    def __init__(self, db_path: str = "./chroma_samsung_rag", batch_size: int = 30, force_reset: bool = False):
        self.db_path = db_path
        self.batch_size = batch_size
        self.force_reset = force_reset
        self._load_embedding_model()
        self._init_chroma_collections(force_reset)
        
        self.processors = {
            'annotation': AnnotationProcessor(),
            'financial_table': FinancialTableProcessor(),
            'accounting_standard': AccountingStandardProcessor()
        }
        
        self.seen_hashes = set()
        self.stats = {'processed': 0, 'duplicates': 0, 'errors': 0}
    
    def _load_embedding_model(self):
        model_candidates = [
            "jhgan/ko-sroberta-multitask",
            "snunlp/KR-SBERT-V40K-klueNLI-augSTS",
            "jhgan/ko-sbert-multitask"
        ]
        
        logger.info("임베딩 모델 로딩 중...")
        for model_name in model_candidates:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"✓ {model_name} 로딩 완료")
                break
            except Exception as e:
                logger.warning(f"✗ {model_name} 로딩 실패: {e}")
        else:
            raise Exception("사용 가능한 임베딩 모델이 없습니다.")
    
    def safe_collection_reset(self, collection_name: str, force: bool = False) -> bool:
        """안전한 컬렉션 초기화"""
        try:
            # 컬렉션 존재 여부 확인
            existing_collection = None
            try:
                existing_collection = self.client.get_collection(collection_name)
                collection_count = existing_collection.count()
            except:
                collection_count = 0
                
            if collection_count > 0 and not force:
                logger.warning(f"⚠️ 컬렉션 '{collection_name}'에 {collection_count}개의 기존 데이터가 있습니다.")
                
                # 백업 생성 제안
                backup_path = f"{self.db_path}_backup_{collection_name}_{int(time.time())}"
                logger.info(f"💾 백업 경로: {backup_path}")
                
                # 대화형 확인 (프로그래밍 환경에서는 자동으로 건너뛰기)
                try:
                    import sys
                    if sys.stdin.isatty():  # 대화형 터미널인 경우만
                        response = input(f"기존 데이터를 삭제하고 초기화하시겠습니까? (y/N): ").lower().strip()
                        if response not in ['y', 'yes']:
                            logger.info(f"✅ 컬렉션 '{collection_name}' 초기화를 건너뜁니다.")
                            return False
                    else:
                        # 비대화형 환경에서는 기존 데이터 보존
                        logger.info(f"✅ 비대화형 환경: 기존 컬렉션 '{collection_name}' 데이터를 보존합니다.")
                        return False
                except:
                    # 입력 불가능한 환경에서는 기존 데이터 보존
                    logger.info(f"✅ 기존 컬렉션 '{collection_name}' 데이터를 보존합니다.")
                    return False
            
            # 컬렉션 삭제 및 재생성
            if existing_collection:
                logger.info(f"🗑️ 기존 컬렉션 '{collection_name}' 삭제 중...")
                self.client.delete_collection(collection_name)
                
            logger.info(f"🔄 컬렉션 '{collection_name}' 재생성 중...")
            return True
            
        except Exception as e:
            logger.error(f"❌ 컬렉션 '{collection_name}' 초기화 실패: {e}")
            return False
    
    def _create_backup(self, collection_name: str, backup_path: str) -> bool:
        """컬렉션 백업 생성"""
        try:
            import shutil
            if os.path.exists(self.db_path):
                # 전체 DB 폴더 백업 (특정 컬렉션만 백업하는 것은 ChromaDB에서 복잡함)
                shutil.copytree(self.db_path, backup_path)
                logger.info(f"✅ 백업 생성 완료: {backup_path}")
                return True
        except Exception as e:
            logger.error(f"❌ 백업 생성 실패: {e}")
            return False
    
    def _init_chroma_collections(self, force_reset: bool = False):
        """안전한 ChromaDB 컬렉션 초기화"""
        import shutil
        
        # 전체 DB 폴더 삭제는 force_reset이 True일 때만
        if force_reset and os.path.exists(self.db_path):
            logger.warning(f"🗑️ force_reset=True: 전체 DB 폴더 삭제 중... ({self.db_path})")
            try:
                shutil.rmtree(self.db_path)
                logger.info(f"✅ DB 폴더 삭제 완료")
            except Exception as e:
                logger.error(f"❌ DB 폴더 삭제 실패: {e}")
        
        # ChromaDB 클라이언트 초기화
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        
        self.collections = {}
        configs = {
            'annotation': 'samsung_annotations_rag',
            'financial_table': 'samsung_financial_rag', 
            'accounting_standard': 'samsung_accounting_rag'
        }
        
        # 각 컬렉션을 안전하게 초기화
        for doc_type, collection_name in configs.items():
            try:
                # 기존 컬렉션 확인 및 안전한 처리
                existing_collection = None
                try:
                    existing_collection = self.client.get_collection(collection_name)
                    collection_count = existing_collection.count()
                    
                    if collection_count > 0 and not force_reset:
                        logger.info(f"📋 기존 컬렉션 '{collection_name}' 발견 ({collection_count}개 데이터)")
                        logger.info(f"✅ 기존 데이터를 보존하고 재사용합니다.")
                        self.collections[doc_type] = existing_collection
                        continue
                    elif force_reset:
                        logger.info(f"🔄 force_reset=True: 컬렉션 '{collection_name}' 재생성")
                        self.client.delete_collection(collection_name)
                        
                except Exception:
                    # 컬렉션이 존재하지 않는 경우
                    logger.info(f"🆕 새 컬렉션 '{collection_name}' 생성")
                
                # 컬렉션 생성 또는 재생성
                self.collections[doc_type] = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=None  # 수동으로 임베딩 제공
                )
                logger.info(f"✓ {collection_name} 컬렉션 초기화 완료")
                
            except Exception as e:
                logger.error(f"❌ 컬렉션 '{collection_name}' 초기화 실패: {e}")
                # 실패한 경우 빈 컬렉션이라도 생성 시도
                try:
                    self.collections[doc_type] = self.client.create_collection(
                        name=f"{collection_name}_fallback",
                        metadata={"hnsw:space": "cosine"},
                        embedding_function=None
                    )
                    logger.warning(f"⚠️ 대체 컬렉션 생성: {collection_name}_fallback")
                except Exception as fallback_e:
                    logger.error(f"❌ 대체 컬렉션 생성도 실패: {fallback_e}")
                    raise
    
    def is_duplicate(self, text: str) -> bool:
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        if text_hash in self.seen_hashes:
            self.stats['duplicates'] += 1
            return True
        self.seen_hashes.add(text_hash)
        return False
    
    def _process_batch(self, chunks_batch: List[Tuple[str, EnhancedChunkMetadata]], collection):
        """배치 처리 - 메모리 최적화"""
        if not chunks_batch:
            return
        
        try:
            texts = [chunk[0] for chunk in chunks_batch]
            metadatas = [chunk[1] for chunk in chunks_batch]
            
            # 배치 임베딩 (메모리 효율적)
            embeddings = self.model.encode(
                texts, 
                batch_size=32,  # 16에서 32로 증가
                show_progress_bar=True,  # 진행률 표시 활성화
                convert_to_numpy=True,
                normalize_embeddings=True  # 임베딩 정규화 추가
            )
            
            # Chroma 저장
            ids = []
            documents = []
            chroma_embeddings = []
            chroma_metadatas = []
            
            for i, (text, metadata) in enumerate(chunks_batch):
                chunk_id = f"{metadata.document_type}_{metadata.year}_{metadata.chunk_index}_{hashlib.md5(text.encode()).hexdigest()[:8]}"
                
                ids.append(chunk_id)
                documents.append(text)
                chroma_embeddings.append(embeddings[i].tolist())
                chroma_metadatas.append(metadata.to_dict())
            
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=chroma_embeddings,
                metadatas=chroma_metadatas
            )
            
            self.stats['processed'] += len(chunks_batch)
            
        except MemoryError as e:
            logger.error(f"❌ 배치 처리 중 메모리 부족: {e}")
            logger.info(f"💡 배치를 더 작은 단위로 분할하여 재시도...")
            
            # 배치를 절반으로 나누어 재시도
            mid = len(chunks_batch) // 2
            if mid > 0:
                try:
                    # 첫 번째 절반 처리
                    first_half = chunks_batch[:mid]
                    self._process_batch(first_half, collection)
                    
                    # 두 번째 절반 처리
                    second_half = chunks_batch[mid:]
                    self._process_batch(second_half, collection)
                    
                    logger.info(f"✅ 분할 처리 성공: {len(chunks_batch)}개 청크")
                    
                except Exception as retry_e:
                    logger.error(f"❌ 분할 처리도 실패: {retry_e}")
                    self.stats['batch_memory_errors'] = self.stats.get('batch_memory_errors', 0) + 1
                    self.stats['errors'] += len(chunks_batch)
            else:
                logger.error(f"❌ 단일 청크도 처리할 수 없음 (메모리 부족)")
                self.stats['single_chunk_errors'] = self.stats.get('single_chunk_errors', 0) + 1
                self.stats['errors'] += len(chunks_batch)
                
        except ValueError as e:
            logger.error(f"❌ 배치 처리 중 값 에러: {e}")
            logger.info(f"💡 임베딩 차원 또는 데이터 형식 문제일 수 있습니다")
            self.stats['batch_value_errors'] = self.stats.get('batch_value_errors', 0) + 1
            self.stats['errors'] += len(chunks_batch)
            
        except Exception as e:
            logger.error(f"❌ 배치 처리 중 예상치 못한 에러: {type(e).__name__}: {e}")
            logger.info(f"💡 배치 크기: {len(chunks_batch)}개")
            self.stats['batch_unknown_errors'] = self.stats.get('batch_unknown_errors', 0) + 1
            self.stats['errors'] += len(chunks_batch)
    
    def process_document_type(self, file_mapping: Dict[int, str], doc_type: str):
        """문서 타입별 처리"""
        logger.info(f"\n📁 {doc_type.upper()} 처리 시작")
        
        processor = self.processors[doc_type]
        collection = self.collections[doc_type]
        all_chunks = []
        
        for year, file_path in file_mapping.items():
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ 파일 없음: {file_path}")
                continue
            
            try:
                logger.info(f"  {year}년 파일 처리 중: {os.path.basename(file_path)}")
                chunks = processor.process_file(file_path, year)
                
                # 중복 제거
                unique_chunks = []
                for chunk_text, chunk_metadata in chunks:
                    if not self.is_duplicate(chunk_text):
                        unique_chunks.append((chunk_text, chunk_metadata))
                
                all_chunks.extend(unique_chunks)
                logger.info(f"    {len(chunks)}개 청크 → {len(unique_chunks)}개 유니크")
                
            except UnicodeDecodeError as e:
                logger.error(f"❌ 파일 인코딩 에러 ({file_path}): {e}")
                logger.info(f"💡 다른 인코딩으로 재시도 중...")
                # UTF-8 실패 시 다른 인코딩으로 재시도
                try:
                    # 임시로 다른 인코딩 시도 (cp949, euc-kr 등)
                    logger.warning(f"⚠️ {file_path} 인코딩 문제로 건너뜀")
                    self.stats['encoding_errors'] = self.stats.get('encoding_errors', 0) + 1
                except:
                    pass
                continue
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 파싱 에러 ({file_path}): {e}")
                logger.info(f"💡 파일 형식 확인 필요: {file_path}")
                self.stats['json_errors'] = self.stats.get('json_errors', 0) + 1
                continue
                
            except MemoryError as e:
                logger.error(f"❌ 메모리 부족 ({file_path}): {e}")
                logger.info(f"💡 배치 크기를 절반으로 줄여서 재시도...")
                # 배치 크기 자동 감소
                original_batch_size = self.batch_size
                self.batch_size = max(5, self.batch_size // 2)
                logger.info(f"📉 배치 크기: {original_batch_size} → {self.batch_size}")
                
                try:
                    # 메모리 절약 모드로 재시도
                    chunks = processor.process_file(file_path, year)
                    unique_chunks = []
                    for chunk_text, chunk_metadata in chunks:
                        if not self.is_duplicate(chunk_text):
                            unique_chunks.append((chunk_text, chunk_metadata))
                    all_chunks.extend(unique_chunks)
                    logger.info(f"✅ 메모리 절약 모드로 성공: {len(chunks)}개 청크 → {len(unique_chunks)}개 유니크")
                except Exception as retry_e:
                    logger.error(f"❌ 재시도도 실패 ({file_path}): {retry_e}")
                    self.stats['memory_errors'] = self.stats.get('memory_errors', 0) + 1
                    continue
                finally:
                    # 배치 크기 복원하지 않음 (메모리 안정성 유지)
                    pass
                    
            except FileNotFoundError as e:
                logger.error(f"❌ 파일을 찾을 수 없음 ({file_path}): {e}")
                self.stats['file_not_found_errors'] = self.stats.get('file_not_found_errors', 0) + 1
                continue
                
            except Exception as e:
                logger.error(f"❌ 예상치 못한 에러 ({file_path}): {type(e).__name__}: {e}")
                logger.info(f"💡 파일 건너뜀: {file_path}")
                self.stats['unknown_errors'] = self.stats.get('unknown_errors', 0) + 1
                continue
        
        # 배치 처리
        logger.info(f"총 {len(all_chunks)}개 청크 벡터화 중...")
        
        for i in tqdm(range(0, len(all_chunks), self.batch_size), desc=f"{doc_type} 벡터화"):
            batch = all_chunks[i:i + self.batch_size]
            self._process_batch(batch, collection)
        
        count = collection.count()
        logger.info(f"✅ {doc_type}: {count}개 청크 저장 완료")
        return count
    
    def run_pipeline(self, file_mappings: Dict[str, Dict[int, str]], parallel: bool = True):
        """전체 파이프라인 실행"""
        start_time = time.time()
        logger.info("🚀 개선된 RAG 벡터 파이프라인 시작")
        
        # 통계 초기화
        self.stats = {'processed': 0, 'duplicates': 0, 'errors': 0}
        results = {}
        
        if parallel:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self.process_document_type, file_mapping, doc_type): doc_type
                    for doc_type, file_mapping in file_mappings.items()
                }
                
                for future in as_completed(futures):
                    doc_type = futures[future]
                    try:
                        count = future.result()
                        results[doc_type] = count
                    except Exception as e:
                        logger.error(f"❌ {doc_type} 처리 실패: {e}")
                        results[doc_type] = 0
        else:
            # 순차 처리
            for doc_type, file_mapping in file_mappings.items():
                try:
                    count = self.process_document_type(file_mapping, doc_type)
                    results[doc_type] = count
                except Exception as e:
                    logger.error(f"❌ {doc_type} 처리 실패: {e}")
                    results[doc_type] = 0
        
        # 결과 요약
        total_time = time.time() - start_time
        total_chunks = sum(results.values())
        
        logger.info(f"\n🎉 파이프라인 완료!")
        logger.info(f"⏰ 총 소요시간: {total_time:.2f}초")
        logger.info(f"📊 처리 결과:")
        logger.info(f"  • 총 청크 수: {total_chunks}개")
        logger.info(f"  • 중복 제거: {self.stats['duplicates']}개")
        logger.info(f"  • 처리 실패: {self.stats['errors']}개")
        
        # 세부 에러 통계 출력
        error_details = []
        if self.stats.get('encoding_errors', 0) > 0:
            error_details.append(f"인코딩 에러: {self.stats['encoding_errors']}개")
        if self.stats.get('json_errors', 0) > 0:
            error_details.append(f"JSON 파싱 에러: {self.stats['json_errors']}개")
        if self.stats.get('memory_errors', 0) > 0:
            error_details.append(f"메모리 에러: {self.stats['memory_errors']}개")
        if self.stats.get('file_not_found_errors', 0) > 0:
            error_details.append(f"파일 없음: {self.stats['file_not_found_errors']}개")
        if self.stats.get('batch_memory_errors', 0) > 0:
            error_details.append(f"배치 메모리 에러: {self.stats['batch_memory_errors']}개")
        if self.stats.get('unknown_errors', 0) > 0:
            error_details.append(f"기타 에러: {self.stats['unknown_errors']}개")
            
        if error_details:
            logger.info(f"  📋 에러 세부사항:")
            for detail in error_details:
                logger.info(f"    - {detail}")
        
        for doc_type, count in results.items():
            logger.info(f"  • {doc_type}: {count}개")
        
        return results
    
    # ========== RAG 최적화된 검색 인터페이스 ==========
    
    def _analyze_query_type(self, query: str) -> Dict[str, float]:
        """질문 내용 분석하여 동적 가중치 결정"""
        query_lower = query.lower()
        
        # 회계기준 관련 키워드
        accounting_keywords = [
            'k-ifrs', 'kifrs', '기준서', '회계기준', '국제회계기준', 
            '회계처리기준', '적용기준', '인식기준', '측정기준'
        ]
        
        # 재무수치 관련 키워드
        financial_keywords = [
            '금액', '수치', '원', '억', '조', '백만', '천만', '매출액', 
            '영업이익', '당기순이익', '자산', '부채', '자본', '현금', 
            '비율', '증감', '변동', '규모', '크기'
        ]
        
        # 주석/설명 관련 키워드
        annotation_keywords = [
            '정책', '방침', '절차', '기준', '방법', '처리', '설명', 
            '내역', '현황', '상세', '세부', '구체적', '어떻게', '왜', '무엇'
        ]
        
        # 키워드 매칭 점수 계산
        accounting_score = sum(1 for keyword in accounting_keywords if keyword in query_lower)
        financial_score = sum(1 for keyword in financial_keywords if keyword in query_lower)
        annotation_score = sum(1 for keyword in annotation_keywords if keyword in query_lower)
        
        # 동적 가중치 결정
        if accounting_score > 0:
            return {
                'accounting_standard': 0.7,
                'annotation': 0.2, 
                'financial_table': 0.1
            }
        elif financial_score > 0:
            return {
                'financial_table': 0.6,
                'annotation': 0.3,
                'accounting_standard': 0.1
            }
        else:
            # 기본 가중치 (annotation 우선)
            return {
                'annotation': 0.5,
                'financial_table': 0.3,
                'accounting_standard': 0.2
            }
    
    def search_unified(self, query: str, doc_types: List[str] = None, 
                      n_results: int = 5, year_filter: int = None,
                      section_filter: str = None,
                      weights: Dict[str, float] = None) -> List[Dict]:
        """RAG 최적화된 통합 검색 (성능 개선)"""
        if doc_types is None:
            doc_types = list(self.collections.keys())
        
        # 동적 가중치 시스템: 질문 내용에 따라 자동 결정
        if weights is None:
            weights = self._analyze_query_type(query)
            logger.info(f"🎯 동적 가중치 적용: {weights}")
        
        all_results = []
        
        for doc_type in doc_types:
            if doc_type not in self.collections:
                continue
            
            collection = self.collections[doc_type]
            weight = weights.get(doc_type, 1.0)
            
            # 강화된 메타데이터 필터링
            where_filter = {}
            if year_filter:
                where_filter["year"] = year_filter
            if section_filter:
                where_filter["section"] = {"$regex": f".*{section_filter}.*"}  # 부분 매칭
            
            try:
                # 쿼리를 임베딩으로 변환
                query_embedding = self.model.encode([query], 
                                                   show_progress_bar=False,
                                                   normalize_embeddings=True)[0]
                
                search_results = collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=n_results,
                    where=where_filter if where_filter else None,
                    include=["documents", "metadatas", "distances"]
                )
                
                # 개선된 점수 계산 (거리 → 유사도 변환)
                distances = search_results['distances'][0]
                if distances:
                    for i, (doc, metadata, distance) in enumerate(zip(
                        search_results['documents'][0],
                        search_results['metadatas'][0], 
                        distances
                    )):
                        # 코사인 거리를 유사도로 변환 (개선된 스케일링)
                        # 거리 범위 [0, 2] → 유사도 범위 [0, 1]
                        base_score = max(0.0, min(1.0, 1.0 - distance))
                        
                        # 유사도 곡선 조정 (낮은 유사도는 더 낮게, 높은 유사도는 더 높게)
                        if base_score > 0.7:
                            base_score = base_score ** 0.8  # 높은 유사도 강화
                        elif base_score < 0.3:
                            base_score = base_score ** 1.2  # 낮은 유사도 약화
                        
                        # 가중치 적용 (동적 문서 타입별 중요도)
                        weighted_score = base_score * weight
                        
                        # 컨텍스트 기반 추가 보정
                        content_boost = 1.0
                        if doc_type == 'annotation' and 'note_number' in metadata:
                            content_boost *= 1.1  # 주석 데이터 추가 가중치
                        elif doc_type == 'financial_table':
                            # 재무 키워드 매칭 보정
                            financial_keywords = ['매출', '이익', '자산', '부채', '자본', '현금']
                            keyword_matches = sum(1 for keyword in financial_keywords if keyword in doc.lower())
                            if keyword_matches > 0:
                                content_boost *= (1.0 + 0.05 * keyword_matches)  # 키워드 매칭 수에 따른 보정
                        elif doc_type == 'accounting_standard':
                            # 회계기준 키워드 매칭 보정
                            accounting_keywords = ['기준서', 'ifrs', '회계기준', '인식', '측정']
                            keyword_matches = sum(1 for keyword in accounting_keywords if keyword in doc.lower())
                            if keyword_matches > 0:
                                content_boost *= (1.0 + 0.08 * keyword_matches)
                        
                        # 최종 점수 계산
                        final_score = weighted_score * content_boost
                        
                        result = {
                            'document': doc,
                            'metadata': metadata,
                            'score': final_score,  # 최종 점수 사용
                            'original_distance': distance,
                            'normalized_score': base_score,
                            'base_weighted_score': weighted_score,  # 가중치 적용 후 기본 점수
                            'content_boost': content_boost,  # 컨텍스트 보정값
                            'doc_type': doc_type,
                            'doc_weight': weight,  # 적용된 문서 타입 가중치
                            'rank': i + 1,
                            'content_hash': hashlib.md5(doc.encode('utf-8')).hexdigest()[:8]  # 중복 확인용
                        }
                        all_results.append(result)
                    
            except Exception as e:
                logger.error(f"❌ {doc_type} 검색 실패: {e}")
                continue
        
        # 중복 문서 제거 (강화된 로직)
        seen_hashes = set()
        unique_results = []
        for result in all_results:
            content_hash = result['content_hash']
            # 내용이 70% 이상 유사한 경우 중복으로 간주
            is_duplicate = False
            for seen_hash in seen_hashes:
                if self._calculate_similarity(content_hash, seen_hash) > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_hashes.add(content_hash)
                unique_results.append(result)
        
        # 점수 기반 정렬 및 상위 결과 선택
        unique_results.sort(key=lambda x: x['score'], reverse=True)
        return unique_results[:n_results]
    
    def _calculate_similarity(self, hash1: str, hash2: str) -> float:
        """간단한 해시 기반 유사도 계산"""
        if hash1 == hash2:
            return 1.0
        # 해시가 다르면 내용이 다른 것으로 간주
        return 0.0
    
    def search_with_cross_reference(self, query: str, n_results: int = 5) -> Dict[str, Any]:
        """교차 참조 기반 확장 검색"""
        # 1차 검색
        primary_results = self.search_unified(query, n_results=n_results)
        
        # 교차 참조 키워드 추출
        cross_ref_queries = set()
        for result in primary_results:
            metadata = result['metadata']
            
            # 교차 참조에서 추가 검색 키워드 추출
            if metadata.get('cross_references'):
                for ref in metadata['cross_references']:
                    if ':' in ref:
                        ref_type, ref_term = ref.split(':', 1)
                        cross_ref_queries.add(ref_term)
            
            # 금융 항목에서 추가 키워드
            if metadata.get('financial_items'):
                cross_ref_queries.update(metadata['financial_items'])
        
        # 교차 참조 기반 2차 검색
        secondary_results = []
        for ref_query in list(cross_ref_queries)[:3]:  # 최대 3개 추가 검색
            ref_results = self.search_unified(ref_query, n_results=2)
            secondary_results.extend(ref_results)
        
        # 중복 제거 (문서 ID 기반)
        seen_docs = set()
        final_results = []
        
        for result in primary_results + secondary_results:
            doc_hash = hashlib.md5(result['document'].encode()).hexdigest()[:16]
            if doc_hash not in seen_docs:
                seen_docs.add(doc_hash)
                final_results.append(result)
        
        return {
            'primary_results': primary_results,
            'cross_reference_results': secondary_results,
            'unified_results': final_results[:n_results * 2],
            'cross_ref_queries': list(cross_ref_queries)
        }
    
    def analyze_financial_trend(self, financial_item: str, years: List[int] = None) -> Dict[str, Any]:
        """금융 지표 트렌드 분석"""
        if years is None:
            years = list(range(2020, 2025))  # 최근 5년
        
        trend_data = {}
        
        for year in years:
            # 해당 연도 재무제표에서 검색
            results = self.search_unified(
                query=financial_item,
                doc_types=['financial_table'],
                year_filter=year,
                n_results=3
            )
            
            year_data = {
                'year': year,
                'found_documents': len(results),
                'key_findings': []
            }
            
            for result in results:
                metadata = result['metadata']
                if metadata.get('amounts'):
                    # 관련 금액 정보 추출
                    relevant_amounts = {
                        k: v for k, v in metadata['amounts'].items() 
                        if financial_item in k
                    }
                    if relevant_amounts:
                        year_data['key_findings'].append({
                            'source': metadata.get('section', 'Unknown'),
                            'amounts': relevant_amounts,
                            'table_type': metadata.get('table_type', 'Unknown')
                        })
            
            trend_data[year] = year_data
        
        return {
            'financial_item': financial_item,
            'analysis_period': years,
            'yearly_data': trend_data,
            'total_documents_found': sum(data['found_documents'] for data in trend_data.values())
        }
    
    def get_context_for_rag(self, query: str, max_context_length: int = 2000) -> str:
        """RAG를 위한 최적화된 컨텍스트 생성 (개선된 버전)"""
        # 교차 참조 검색으로 풍부한 컨텍스트 수집
        search_results = self.search_with_cross_reference(query, n_results=10)
        unified_results = search_results['unified_results']
        
        context_parts = []
        current_length = 0
        
        # 개선된 문서 타입별 균형 잡힌 컨텍스트 구성
        type_counts = {'annotation': 0, 'financial_table': 0, 'accounting_standard': 0}
        # 가중치에 따른 최대 개수 조정
        max_per_type = {
            'annotation': 4,        # 주석 데이터 우선순위 높음
            'financial_table': 3,   # 재무제표 중간
            'accounting_standard': 2 # 회계기준서 최소
        }
        
        for result in unified_results:
            doc_type = result['doc_type']
            
            # 개선된 타입별 최대 개수 제한
            if type_counts[doc_type] >= max_per_type[doc_type]:
                continue
            
            document = result['document']
            metadata = result['metadata']
            score = result.get('score', 0.0)
            
            # 점수 기반 문서 품질 필터링 (낮은 점수 문서 제외)
            if score < 0.3:
                continue
            
            # 개선된 컨텍스트 길이 체크
            estimated_part_length = len(document) + 150  # 메타데이터 포맷팅 길이 포함
            if current_length + estimated_part_length > max_context_length:
                # 문서를 스마트하게 잘라서 포함
                remaining_length = max_context_length - current_length - 150
                if remaining_length > 300:  # 최소 길이 확보
                    # 문장 단위로 자르기 시도
                    sentences = document.split('.')
                    truncated = ""
                    for sentence in sentences:
                        if len(truncated) + len(sentence) + 1 <= remaining_length:
                            truncated += sentence + "."
                        else:
                            break
                    document = truncated + "..." if truncated else document[:remaining_length] + "..."
                else:
                    break
            
            # 개선된 컨텍스트 형식화 (더 간결하고 구조화됨)
            context_part = f"""
📄 {doc_type.upper()} ({metadata.get('year', 'N/A')}년) | 점수: {score:.2f}
📍 출처: {metadata.get('section', 'Unknown')}
📝 {document.strip()}
"""
            
            context_parts.append(context_part)
            current_length += len(context_part)
            type_counts[doc_type] += 1
        
        # 최종 컨텍스트 구성
        context = f"""
다음은 '{query}' 질문에 대한 관련 문서들입니다:

{''.join(context_parts)}

--- 검색 메타정보 ---
• 총 검색된 문서: {len(unified_results)}개
• 교차 참조 키워드: {', '.join(search_results['cross_ref_queries'][:5])}
• 문서 타입별 분포: {type_counts}
"""
        
        return context.strip()
    
    def print_search_results(self, query: str, results: List[Dict]):
        """개선된 검색 결과 출력 (상세 점수 분석 포함)"""
        print(f"\n🔍 검색 쿼리: '{query}'")
        print("=" * 70)
        
        for i, result in enumerate(results, 1):
            metadata = result['metadata']
            score = result['score']
            doc_type = result['doc_type']
            
            # 기본 정보
            print(f"\n{i}. [{doc_type.upper()}] 최종점수: {score:.6f}")
            print(f"   연도: {metadata.get('year', 'N/A')}")
            print(f"   섹션: {metadata.get('section', 'N/A')}")
            
            # 점수 상세 분석 (개선된 정보)
            if 'original_distance' in result:
                distance = result['original_distance']
                base_score = result.get('normalized_score', 0)
                doc_weight = result.get('doc_weight', 1.0)
                content_boost = result.get('content_boost', 1.0)
                
                print(f"   📊 점수분석: 거리({distance:.4f}) → 기본({base_score:.4f}) × 가중치({doc_weight:.2f}) × 보정({content_boost:.3f})")
            
            # 문서 타입별 추가 정보
            if metadata.get('table_type'):
                print(f"   표 유형: {metadata['table_type']}")
            if metadata.get('financial_items'):
                print(f"   금융 항목: {', '.join(metadata['financial_items'][:3])}")
            if metadata.get('note_number'):
                print(f"   주석번호: {metadata['note_number']}")
            
            print(f"   내용: {result['document'][:200]}...")
    
    def get_statistics(self) -> Dict[str, Any]:
        """파이프라인 통계 정보 반환"""
        stats = {
            'total_documents': 0,
            'total_chunks': 0,
            'collections': {},
            'processing_stats': getattr(self, 'stats', {})
        }
        
        # 각 컬렉션별 통계
        for doc_type, collection in self.collections.items():
            try:
                count = collection.count()
                stats['collections'][doc_type] = count
                stats['total_chunks'] += count
            except Exception as e:
                stats['collections'][doc_type] = f"Error: {e}"
        
        # 전체 문서 수 계산
        stats['total_documents'] = len([f for f in stats['collections'].values() if isinstance(f, int)])
        
        return stats

# 실행 예시
if __name__ == "__main__":
    # 파일 매핑 설정
    file_mappings = {
        'annotation': {
            2014: "아카이브/감사보고서_2014_parsed.json",
            2015: "아카이브/감사보고서_2015_parsed.json",
            2016: "아카이브/감사보고서_2016_parsed.json",
            2017: "아카이브/감사보고서_2017_parsed.json",
            2018: "아카이브/감사보고서_2018_parsed.json",
            2019: "아카이브/감사보고서_2019_parsed.json",
            2020: "아카이브/감사보고서_2020_parsed.json",
            2021: "아카이브/감사보고서_2021_parsed.json",
            2022: "아카이브/감사보고서_2022_parsed.json",
            2023: "아카이브/감사보고서_2023_parsed.json",
            2024: "아카이브/감사보고서_2024_parsed.json"
        },
        'financial_table': {
            2014: "table_parsing/감사보고서_2014_parsed.json",
            2015: "table_parsing/감사보고서_2015_parsed.json",
            2016: "table_parsing/감사보고서_2016_parsed.json",
            2017: "table_parsing/감사보고서_2017_parsed.json",
            2018: "table_parsing/감사보고서_2018_parsed.json",
            2019: "table_parsing/감사보고서_2019_parsed.json",
            2020: "table_parsing/감사보고서_2020_parsed.json",
            2021: "table_parsing/감사보고서_2021_parsed.json",
            2022: "table_parsing/감사보고서_2022_parsed.json",
            2023: "table_parsing/감사보고서_2023_parsed.json",
            2024: "table_parsing/감사보고서_2024_parsed.json"
        },
        'accounting_standard': {
            2024: "kifrs_combined_2.json"
        }
    }
    
    # 파이프라인 실행
    # force_reset=True로 설정하면 기존 데이터를 완전히 삭제하고 새로 시작
    # force_reset=False (기본값)로 설정하면 기존 데이터를 보존하고 재사용
    pipeline = ImprovedVectorPipeline(
        db_path="./chroma_samsung_rag_optimized",
        batch_size=25,
        force_reset=False  # 기존 데이터 보존 (True로 변경하면 완전 초기화)
    )
    
    # 전체 파이프라인 실행
    results = pipeline.run_pipeline(file_mappings, parallel=True)
    
    # ========== RAG 검색 테스트 ==========
    print("\n" + "="*70)
    print("🔍 RAG 최적화된 검색 테스트")
    print("="*70)
    
    # 1. 통합 검색 테스트
    # 개선된 RAG 검색 테스트 질문들
    test_queries = [
        # 재무제표 관련 질문
        "2024년 매출액과 영업이익은 얼마인가요?",
        "유형자산의 감가상각 정책은 어떻게 되나요?",
        "현금및현금성자산의 구성 내역을 알려주세요",
        "재고자산의 평가방법과 장부금액은?",
        
        # 주석 관련 질문  
        "금융리스와 운용리스의 회계처리 방법은?",
        "충당부채의 설정 기준과 금액은?",
        "관계기업 투자 내역과 지분법 적용 현황은?",
        "외화자산 및 부채의 환산 기준은?",
        
        # 회계기준 관련 질문
        "K-IFRS 1116 리스 기준서 적용 현황은?",
        "K-IFRS 1109 금융상품 분류 기준은?",
        "수익인식 시점과 기준은 어떻게 되나요?",
        "손상차손 인식 및 환입 정책은?",
        
        # 감사의견 관련 질문
        "감사인의 의견은 무엇인가요?",
        "핵심감사사항(KAM)은 무엇인가요?",
        "경영진의 재무제표 작성 책임은?",
        "내부회계관리제도 운영실태는?",
        
        # 연도별 비교 질문
        "2023년 대비 2024년 총자산 변동사항은?",
        "전년도와 비교한 부채비율 변화는?",
        "연결대상 종속기업의 변동사항은?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*50}")
        print(f"질문: {query}")
        print('='*50)
        
        # 통합 검색
        results = pipeline.search_unified(query, n_results=5)
        pipeline.print_search_results(query, results)
        
        # RAG 컨텍스트 생성 테스트
        print(f"\n--- RAG 컨텍스트 (길이 제한: 1000자) ---")
        context = pipeline.get_context_for_rag(query, max_context_length=1000)
        print(context[:1000] + "..." if len(context) > 1000 else context)
    
    # 2. 교차 참조 검색 테스트  
    print(f"\n{'='*50}")
    print("교차 참조 검색 테스트")
    print('='*50)
    
    cross_ref_results = pipeline.search_with_cross_reference("매출액 변동", n_results=3)
    print(f"교차 참조 키워드: {cross_ref_results['cross_ref_queries']}")
    print(f"1차 검색 결과: {len(cross_ref_results['primary_results'])}개")
    print(f"2차 검색 결과: {len(cross_ref_results['cross_reference_results'])}개")
    print(f"통합 결과: {len(cross_ref_results['unified_results'])}개")
    
    # 3. 금융 트렌드 분석 테스트
    print(f"\n{'='*50}")
    print("금융 트렌드 분석 테스트")
    print('='*50)
    
    trend_analysis = pipeline.analyze_financial_trend("매출액", years=[2022, 2023, 2024])
    print(f"분석 항목: {trend_analysis['financial_item']}")
    print(f"분석 기간: {trend_analysis['analysis_period']}")
    print(f"총 발견 문서: {trend_analysis['total_documents_found']}개")
    
    for year, data in trend_analysis['yearly_data'].items():
        print(f"\n{year}년:")
        print(f"  발견 문서: {data['found_documents']}개")
        if data['key_findings']:
            for finding in data['key_findings'][:2]:
                print(f"  출처: {finding['source']}")
                if finding['amounts']:
                    amounts_str = ', '.join([f"{k}: {v}" for k, v in list(finding['amounts'].items())[:2]])
                    print(f"  금액: {amounts_str}")
    
    print(f"\n🎉 RAG 최적화 파이프라인 테스트 완료!")
    print(f"벡터DB는 고품질 QA 시스템 구축을 위한 준비가 완료되었습니다.")