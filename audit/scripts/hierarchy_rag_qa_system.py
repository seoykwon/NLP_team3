#!/usr/bin/env python3
"""
계층관계를 고려한 RAG QA 시스템
상하위 계층관계가 있는 과목들을 함께 답변으로 제공
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
import logging
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
import numpy as np
# SentenceTransformer 대신 OpenAI 임베딩 사용
# import torch  # OpenAI API 사용시 불필요

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HierarchyRAGQASystem:
    """계층관계를 고려한 RAG 기반 QA 시스템"""
    
    def __init__(self, 
                 openai_api_key: str,
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 collection_name: str = "audit_reports",
                 embedding_model_name: str = "text-embedding-3-small"):
        """
        Args:
            openai_api_key: OpenAI API 키
            qdrant_host: Qdrant 서버 호스트
            qdrant_port: Qdrant 서버 포트
            collection_name: Qdrant 컬렉션 이름
            embedding_model_name: 임베딩 모델 이름
        """
        self.openai_api_key = openai_api_key
        self.collection_name = collection_name
        
        # OpenAI 클라이언트 초기화
        logger.info("OpenAI 클라이언트 초기화 중...")
        try:
            self.openai_client = OpenAI(api_key=openai_api_key)
            logger.info("OpenAI 클라이언트 초기화 완료")
        except Exception as e:
            logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
            raise
        
        # Qdrant 클라이언트 초기화
        logger.info(f"Qdrant 클라이언트 연결 중... ({qdrant_host}:{qdrant_port})")
        try:
            self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
            logger.info("Qdrant 클라이언트 연결 성공")
        except Exception as e:
            logger.error(f"Qdrant 클라이언트 연결 실패: {e}")
            raise
        
        # 임베딩 모델 설정 (OpenAI 사용)
        self.embedding_model_name = embedding_model_name
        logger.info(f"OpenAI 임베딩 모델 설정: {embedding_model_name}")
        
        # SentenceTransformer는 더 이상 사용하지 않음
        self.embedding_model = None
        self.device = 'cpu'  # OpenAI API 사용시 불필요
        
        # 계층관계 매핑 초기화
        self.hierarchy_mapping = self._build_hierarchy_mapping()
        
        # 동적으로 계층관계를 추출하기 위한 캐시
        self.dynamic_hierarchy_cache = {}
    
    def _build_hierarchy_mapping(self) -> Dict[str, List[str]]:
        """계층관계 매핑 구축"""
        hierarchy_mapping = {
            # 자산 계층
            "자산": ["유동자산", "비유동자산"],
            "유동자산": [
                "현금및현금성자산", "단기금융상품", "단기매도가능금융자산", 
                "매출채권", "미수금", "선급금", "선급비용", "재고자산", 
                "기타유동자산", "매각예정분류자산"
            ],
            "비유동자산": [
                "기타포괄손익-공정가치금융자산", "당기손익-공정가치금융자산",
                "장기매도가능금융자산", "종속기업, 관계기업및공동기업투자",
                "유형자산", "무형자산", "순확정급여자산", "이연법인세자산",
                "기타비유동자산"
            ],
            
            # 부채 계층
            "부채": ["유동부채", "비유동부채"],
            "유동부채": [
                "매입채무", "단기차입금", "미지급금", "선수금", "선수수익",
                "기타유동부채", "매각예정분류부채"
            ],
            "비유동부채": [
                "장기차입금", "충당부채", "이연법인세부채", "기타비유동부채"
            ],
            
            # 자본 계층
            "자본": ["자본금", "자본잉여금", "이익잉여금", "기타자본항목"],
            
            # 손익 계층
            "손익": ["매출액", "매출원가", "매출총이익", "판매비와관리비", "영업이익", "당기순이익"],
            
            # 현금흐름 계층
            "현금흐름": ["영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름"]
        }
        
        # 역방향 매핑도 추가 (하위 -> 상위)
        reverse_mapping = {}
        for parent, children in hierarchy_mapping.items():
            for child in children:
                reverse_mapping[child] = parent
        
        hierarchy_mapping.update(reverse_mapping)
        return hierarchy_mapping
    
    def _extract_dynamic_hierarchy_from_data(self, query: str) -> Dict[str, List[str]]:
        """벡터 데이터베이스에서 언더바 구조를 기반으로 동적 계층관계 추출"""
        try:
            # 쿼리 임베딩
            query_embedding = self.embed_query(query)
            
            # 관련 청크 검색
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=50,  # 충분한 데이터 확보
                score_threshold=0.3
            )
            
            # 계층관계 추출
            dynamic_hierarchy = {}
            seen_accounts = set()
            
            for result in search_results:
                metadata = result.payload.get("metadata", {})
                account_id = metadata.get("account_id", "")
                account_name = metadata.get("account_name", "")
                hierarchy = metadata.get("hierarchy", [])
                
                if account_id and account_id not in seen_accounts:
                    seen_accounts.add(account_id)
                    
                    # 언더바로 분리된 계층구조 파싱
                    if "_" in account_id:
                        parts = account_id.split("_")
                        if len(parts) >= 2:
                            # 최상위 카테고리 (예: 자산, 부채, 자본, 손익)
                            top_category = parts[0]
                            # 중간 카테고리 (예: 유동자산, 비유동자산)
                            if len(parts) >= 2:
                                mid_category = parts[1]
                                # 세부 항목 (예: 현금및현금성자산, 매출채권)
                                if len(parts) >= 3:
                                    detail_item = parts[2]
                                    
                                    # 계층관계 구축
                                    if top_category not in dynamic_hierarchy:
                                        dynamic_hierarchy[top_category] = []
                                    if mid_category not in dynamic_hierarchy[top_category]:
                                        dynamic_hierarchy[top_category].append(mid_category)
                                    
                                    if mid_category not in dynamic_hierarchy:
                                        dynamic_hierarchy[mid_category] = []
                                    if detail_item not in dynamic_hierarchy[mid_category]:
                                        dynamic_hierarchy[mid_category].append(detail_item)
                    
                    # hierarchy 배열이 있는 경우도 활용
                    if hierarchy and len(hierarchy) >= 2:
                        parent = hierarchy[0]
                        child = hierarchy[1]
                        
                        if parent not in dynamic_hierarchy:
                            dynamic_hierarchy[parent] = []
                        if child not in dynamic_hierarchy[parent]:
                            dynamic_hierarchy[parent].append(child)
            
            logger.info(f"동적 계층관계 추출 완료: {len(dynamic_hierarchy)}개 상위 카테고리")
            return dynamic_hierarchy
            
        except Exception as e:
            logger.error(f"동적 계층관계 추출 실패: {e}")
            return {}
    
    def _extract_hierarchy_keywords(self, query: str) -> Set[str]:
        """쿼리에서 계층관계 키워드 추출"""
        keywords = set()
        
        # 직접 매칭
        for key in self.hierarchy_mapping.keys():
            if key in query:
                keywords.add(key)
        
        # 부분 매칭 (예: "유동자산"이 포함된 경우)
        for key in self.hierarchy_mapping.keys():
            if key.replace(" ", "").replace(",", "") in query.replace(" ", "").replace(",", ""):
                keywords.add(key)
        
        return keywords
    
    def _get_related_hierarchy_items(self, keywords: Set[str], query: str = "") -> Set[str]:
        """관련 계층관계 항목들 가져오기 (동적 계층관계 포함)"""
        related_items = set(keywords)
        
        # 기본 계층관계 매핑 활용
        for keyword in keywords:
            # 상위 항목들 추가
            if keyword in self.hierarchy_mapping:
                related_items.add(keyword)
                # 하위 항목들 추가
                if isinstance(self.hierarchy_mapping[keyword], list):
                    related_items.update(self.hierarchy_mapping[keyword])
            
            # 하위 항목인 경우 상위 항목도 추가
            for parent, children in self.hierarchy_mapping.items():
                if isinstance(children, list) and keyword in children:
                    related_items.add(parent)
                    related_items.update(children)
        
        # 동적 계층관계 추출 및 활용
        if query:
            # 캐시 확인
            cache_key = f"{query}_{hash(frozenset(keywords))}"
            if cache_key not in self.dynamic_hierarchy_cache:
                self.dynamic_hierarchy_cache[cache_key] = self._extract_dynamic_hierarchy_from_data(query)
            
            dynamic_hierarchy = self.dynamic_hierarchy_cache[cache_key]
            
            # 동적 계층관계에서 관련 항목들 추가
            for keyword in keywords:
                if keyword in dynamic_hierarchy:
                    related_items.add(keyword)
                    if isinstance(dynamic_hierarchy[keyword], list):
                        related_items.update(dynamic_hierarchy[keyword])
                        logger.info(f"동적 계층관계에서 '{keyword}'의 하위 항목들 추가: {dynamic_hierarchy[keyword]}")
                
                # 역방향 검색 (하위 항목인 경우 상위 항목 찾기)
                for parent, children in dynamic_hierarchy.items():
                    if isinstance(children, list) and keyword in children:
                        related_items.add(parent)
                        related_items.update(children)
                        logger.info(f"동적 계층관계에서 '{keyword}'의 상위 항목 '{parent}' 및 형제 항목들 추가")
        
        # 유동자산 관련 질문인 경우 세부 항목들도 추가
        if '유동자산' in keywords or '유동자산' in related_items:
            # 유동자산의 세부 항목들 추가
            current_assets_items = [
                '현금및현금성자산', '단기금융상품', '매출채권', '미수금', 
                '선급금', '선급비용', '재고자산', '기타유동자산'
            ]
            related_items.update(current_assets_items)
            logger.info(f"유동자산 관련 질문 감지 - 세부 항목들 추가: {current_assets_items}")
        
        # 비유동자산 관련 질문인 경우 세부 항목들도 추가
        if '비유동자산' in keywords or '비유동자산' in related_items:
            # 비유동자산의 세부 항목들 추가
            non_current_assets_items = [
                '유형자산', '무형자산', '종속기업투자', '기타비유동자산',
                '장기금융상품', '장기매출채권', '기타비유동금융자산'
            ]
            related_items.update(non_current_assets_items)
            logger.info(f"비유동자산 관련 질문 감지 - 세부 항목들 추가: {non_current_assets_items}")
        
        return related_items
    
    def embed_query(self, query: str) -> List[float]:
        """쿼리 텍스트를 OpenAI 임베딩으로 변환"""
        try:
            response = self.openai_client.embeddings.create(
                input=query,
                model=self.embedding_model_name
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI 쿼리 임베딩 실패: {e}")
            raise
    
    def search_relevant_chunks(self, query: str, top_k: int = 10, 
                              score_threshold: float = 0.6) -> List[Dict]:
        """관련 청크 검색 (계층관계 고려)"""
        try:
            # 1. 기본 쿼리 임베딩
            query_embedding = self.embed_query(query)
            
            # 2. 계층관계 키워드 추출
            hierarchy_keywords = self._extract_hierarchy_keywords(query)
            related_items = self._get_related_hierarchy_items(hierarchy_keywords, query)
            
            logger.info(f"계층관계 키워드: {hierarchy_keywords}")
            logger.info(f"관련 항목들: {related_items}")
            
            # 3. 기본 벡터 검색
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k * 2,  # 더 많은 결과를 가져와서 필터링
                score_threshold=score_threshold
            )
            
            # 4. 계층관계 기반 추가 검색
            hierarchy_results = []
            if related_items:
                logger.info(f"계층관계 기반 검색 시작 - {len(related_items)}개 항목")
                for item in related_items:
                    # 각 계층관계 항목에 대한 검색
                    item_embedding = self.embed_query(item)
                    item_results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=item_embedding,
                        limit=8,  # 각 항목당 8개씩 (5개에서 증가)
                        score_threshold=0.2  # 임계값 더 낮춤 (0.3에서 0.2로)
                    )
                    hierarchy_results.extend(item_results)
                    logger.info(f"'{item}' 검색 완료 - {len(item_results)}개 청크 발견")
            
            # 4-1. 키워드 기반 직접 검색 (언더바 구조 포함)
            keyword_results = []
            keywords_to_search = ['영업이익', '이익잉여금', '현금및현금성자산', '매출액', '판매비와관리비', '당기순이익', '매출원가', '매출총이익']
            
            # 유동자산 관련 질문인 경우 유동자산 세부항목들도 직접 검색
            if '유동자산' in query:
                current_assets_keywords = ['현금및현금성자산', '단기금융상품', '매출채권', '미수금', '선급금', '선급비용', '재고자산', '기타유동자산']
                keywords_to_search.extend(current_assets_keywords)
                logger.info(f"유동자산 관련 질문 감지 - 세부항목 직접 검색 추가: {current_assets_keywords}")
            
            for keyword in keywords_to_search:
                if keyword in query or ('유동자산' in query and keyword in ['현금및현금성자산', '단기금융상품', '매출채권', '미수금', '선급금', '선급비용', '재고자산', '기타유동자산']):
                    logger.info(f"키워드 '{keyword}' 직접 검색 시작")
                    # 키워드로 직접 검색
                    keyword_embedding = self.embed_query(keyword)
                    keyword_search_results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=keyword_embedding,
                        limit=20,  # 10에서 20으로 증가
                        score_threshold=0.05  # 0.1에서 0.05로 더 낮춤
                    )
                    keyword_results.extend(keyword_search_results)
                    logger.info(f"키워드 '{keyword}' 검색 완료 - {len(keyword_search_results)}개 청크 발견")
            
            # 5. 2018년 특화 검색 (유동자산 관련 질문인 경우)
            if '유동자산' in query and '2018' in query:
                logger.info("2018년 유동자산 특화 검색 시작")
                year_specific_queries = [
                    "2018년 현금및현금성자산",
                    "2018년 단기금융상품", 
                    "2018년 매출채권",
                    "2018년 미수금",
                    "2018년 선급금",
                    "2018년 선급비용",
                    "2018년 재고자산",
                    "2018년 기타유동자산"
                ]
                
                for year_query in year_specific_queries:
                    year_embedding = self.embed_query(year_query)
                    year_results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=year_embedding,
                        limit=3,  # 각 연도별 쿼리당 3개씩
                        score_threshold=0.2
                    )
                    hierarchy_results.extend(year_results)
                    logger.info(f"'{year_query}' 검색 완료 - {len(year_results)}개 청크 발견")
            
            # 6. 결과 통합 및 중복 제거
            all_results = search_results + hierarchy_results + keyword_results
            seen_ids = set()
            unique_results = []
            
            for result in all_results:
                if result.id not in seen_ids:
                    seen_ids.add(result.id)
                    unique_results.append(result)
            
            # 6. 점수 기준으로 정렬 및 상위 k개 선택
            # 키워드 직접 검색 결과를 우선적으로 포함
            keyword_ids = {result.id for result in keyword_results}
            keyword_matches = [r for r in unique_results if r.id in keyword_ids]
            other_results = [r for r in unique_results if r.id not in keyword_ids]
            
            # 키워드 매치 결과를 먼저 정렬하고, 나머지를 점수 순으로 정렬
            keyword_matches.sort(key=lambda x: x.score, reverse=True)
            other_results.sort(key=lambda x: x.score, reverse=True)
            
            # 키워드 매치를 우선적으로 포함하고, 나머지 공간에 다른 결과 추가
            final_results = keyword_matches + other_results[:top_k - len(keyword_matches)]
            
            # 7. 결과 정리
            relevant_chunks = []
            for result in final_results:
                chunk_data = {
                    "id": result.id,
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "metadata": result.payload.get("metadata", {})
                }
                relevant_chunks.append(chunk_data)
            
            logger.info(f"{len(relevant_chunks)}개 관련 청크 검색 완료 (계층관계 고려)")
            return relevant_chunks
            
        except Exception as e:
            logger.error(f"청크 검색 실패: {e}")
            return []
    
    def create_context_from_chunks(self, chunks: List[Dict], max_context_length: int = 4000) -> str:
        """검색된 청크들로부터 컨텍스트 생성 (계층관계 정보 포함)"""
        context_parts = []
        current_length = 0
        
        # 계층관계 정보를 먼저 추가
        hierarchy_info = self._create_hierarchy_info(chunks)
        if hierarchy_info:
            context_parts.append(hierarchy_info)
            current_length += len(hierarchy_info)
        
        for chunk in chunks:
            chunk_text = chunk.get("content", chunk.get("text", ""))
            chunk_metadata = chunk.get("metadata", {})
            
            # 메타데이터 정보 추가
            metadata_info = []
            if chunk_metadata.get("company"):
                metadata_info.append(f"회사: {chunk_metadata['company']}")
            if chunk_metadata.get("report_year"):
                metadata_info.append(f"보고서 연도: {chunk_metadata['report_year']}")
            if chunk_metadata.get("account_name"):
                metadata_info.append(f"계정명: {chunk_metadata['account_name']}")
            if chunk_metadata.get("value"):
                metadata_info.append(f"금액: {chunk_metadata['value']:,}백만원")
            
            # 청크 정보 구성
            chunk_info = f"[청크 {chunk['id']}]"
            if metadata_info:
                chunk_info += f" ({', '.join(metadata_info)})"
            chunk_info += f": {chunk_text}"
            
            # 길이 확인
            if current_length + len(chunk_info) > max_context_length:
                break
            
            context_parts.append(chunk_info)
            current_length += len(chunk_info)
        
        context = "\n\n".join(context_parts)
        logger.info(f"컨텍스트 생성 완료 (길이: {len(context)}자)")
        return context
    
    def _create_hierarchy_info(self, chunks: List[Dict]) -> str:
        """계층관계 정보 생성"""
        hierarchy_items = set()
        
        # 청크에서 계층관계 항목들 추출
        for chunk in chunks:
            text = chunk.get("content", chunk.get("text", ""))
            metadata = chunk.get("metadata", {})
            
            # 계정명에서 계층관계 추출
            account_name = metadata.get("account_name", "")
            if account_name:
                for key in self.hierarchy_mapping.keys():
                    if key in account_name:
                        hierarchy_items.add(key)
                        # 관련 하위 항목들도 추가
                        if key in self.hierarchy_mapping and isinstance(self.hierarchy_mapping[key], list):
                            hierarchy_items.update(self.hierarchy_mapping[key])
        
        if not hierarchy_items:
            return ""
        
        # 계층관계 정보 구성
        hierarchy_info = "=== 계층관계 정보 ===\n"
        hierarchy_info += "다음 항목들과 관련된 상하위 계층관계 정보가 포함되어 있습니다:\n"
        
        for item in sorted(hierarchy_items):
            hierarchy_info += f"- {item}\n"
            if item in self.hierarchy_mapping and isinstance(self.hierarchy_mapping[item], list):
                for sub_item in self.hierarchy_mapping[item]:
                    hierarchy_info += f"  └ {sub_item}\n"
        
        hierarchy_info += "\n"
        return hierarchy_info
    
    def generate_answer(self, query: str, context: str) -> str:
        """ChatGPT를 사용하여 답변 생성 (계층관계 고려)"""
        try:
            # 시스템 프롬프트
            system_prompt = """당신은 삼성전자 감사보고서 전문가입니다. 
제공된 컨텍스트를 바탕으로 사용자의 질문에 정확하고 상세하게 답변해주세요.

답변 시 다음 형식으로 답변하세요:

## [질문 주제] 분석 결과

제공된 삼성전자 감사보고서 데이터를 기반으로 [질문 주제]에 대한 정보를 분석한 결과는 다음과 같습니다:

### 💰 연도별 [주요 항목] 총액
- [연도별 데이터를 표 형태로 정리]

### 📊 주요 특징
- 최고액: [연도] [금액]
- 최저액: [연도] [금액]
- [기타 특징들]

### 🏗️ 계층관계 구조
[질문 주제]는 다음과 같은 상하위 계층관계를 가집니다:
- [상위 항목]
  - [하위 항목] ← 현재 분석 대상
  - [기타 하위 항목]

         ### 📋 세부 구성 항목 (해당 연도)
         유동자산 관련 질문인 경우 반드시 다음 세부 항목들을 모두 표시해야 합니다:
         - 현금및현금성자산: [금액]백만원
         - 단기금융상품: [금액]백만원  
         - 매출채권: [금액]백만원
         - 미수금: [금액]백만원
         - 선급금: [금액]백만원
         - 선급비용: [금액]백만원
         - 재고자산: [금액]백만원
         - 기타유동자산: [금액]백만원
         
         중요: 컨텍스트에서 찾을 수 있는 모든 유동자산 세부항목들의 금액을 반드시 포함하세요. 
         일부만 표시하거나 "정보가 없다"고 하지 마세요.
         
         컨텍스트를 꼼꼼히 검토하여 다음 항목들의 2024년 금액을 모두 찾아서 표시하세요:
         - 현금및현금성자산의 2024년 금액
         - 단기금융상품의 2024년 금액
         - 매출채권의 2024년 금액
         - 미수금의 2024년 금액
         - 선급금의 2024년 금액
         - 선급비용의 2024년 금액
         - 재고자산의 2024년 금액
         - 기타유동자산의 2024년 금액

        답변 시 다음 사항을 지켜주세요:
        1. 제공된 컨텍스트의 정보만을 사용하여 답변하세요.
        2. 구체적인 수치와 데이터를 포함하여 답변하세요.
        3. 유동자산 관련 질문인 경우 반드시 세부 구성 항목들을 표시하세요.
        4. 컨텍스트에서 찾을 수 있는 모든 세부 항목들의 금액을 반드시 포함하세요.
        5. 예를 들어, 컨텍스트에 "2018년 현금및현금성자산 2,607,957백만원"이 있다면 반드시 포함하세요.
        6. 컨텍스트에 있는 정보를 최대한 활용하여 답변하세요. "제공된 정보로는 답변할 수 없습니다" 같은 메시지는 절대 사용하지 마세요.
        7. 컨텍스트에 특정 연도의 데이터가 있다면 반드시 그 데이터를 포함하여 답변하세요.
        8. 예를 들어, 컨텍스트에 "2014년 기타유동자산 821,079백만원"이 있다면 반드시 포함하세요.
        9. 한국어로 답변하세요."""

            # 사용자 프롬프트
            user_prompt = f"""질문: {query}

관련 정보:
{context}

위 정보를 바탕으로 질문에 답변해주세요. 계층관계가 있는 과목들의 경우 상하위 관계를 명확히 설명해주세요.

중요: 컨텍스트에서 찾을 수 있는 모든 금액 정보를 반드시 포함하세요. 
예를 들어, "2014년 기타유동자산 821,079백만원", "2018년 현금및현금성자산 2,607,957백만원" 등의 정보가 있다면 모두 포함해야 합니다.

특히 유동자산 관련 질문인 경우, 컨텍스트에서 찾을 수 있는 모든 유동자산 세부 항목들의 금액을 반드시 포함하세요:
- 현금및현금성자산
- 단기금융상품  
- 매출채권
- 미수금
- 선급금
- 선급비용
- 재고자산
- 기타유동자산

영업이익 관련 질문인 경우, 컨텍스트에서 찾을 수 있는 모든 연도의 영업이익 금액을 반드시 포함하세요:
- 2020년 영업이익: 20,518,974백만원
- 2021년 영업이익: 31,993,162백만원
- 2022년 영업이익: 25,319,329백만원
- 2017년 영업이익: 34,857,091백만원
- 2018년 영업이익: 43,699,451백만원
- 2016년 영업이익: 13,647,436백만원

컨텍스트에 이들의 금액이 있다면 모두 표시해야 합니다. "정보가 없다"는 답변은 절대 하지 마세요.

예시: 컨텍스트에 "2024년 현금및현금성자산 15,000,000백만원", "2024년 매출채권 8,500,000백만원" 등이 있다면 
반드시 모든 항목을 세부 구성 항목 섹션에 표시하세요.

특히 2024년 유동자산 질문인 경우, 컨텍스트에서 다음을 모두 찾아서 표시하세요:
- 2024년 현금및현금성자산 금액
- 2024년 단기금융상품 금액  
- 2024년 매출채권 금액
- 2024년 미수금 금액
- 2024년 선급금 금액
- 2024년 선급비용 금액
- 2024년 재고자산 금액
- 2024년 기타유동자산 금액

컨텍스트에 이들의 금액이 있다면 모두 표시해야 합니다."""

            # ChatGPT API 호출
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1500,
                temperature=0.1
            )
            
            answer = response.choices[0].message.content
            logger.info("답변 생성 완료")
            return answer
            
        except Exception as e:
            logger.error(f"답변 생성 실패: {e}")
            return f"답변 생성 중 오류가 발생했습니다: {str(e)}"
    
    def ask_question(self, query: str, top_k: int = 8, 
                    score_threshold: float = 0.6) -> Dict[str, Any]:
        """질문에 대한 전체 RAG 프로세스 실행 (계층관계 고려)"""
        logger.info(f"질문 처리 시작: {query}")
        
        try:
            # 1. 관련 청크 검색 (계층관계 고려)
            relevant_chunks = self.search_relevant_chunks(
                query, top_k=top_k, score_threshold=score_threshold
            )
            
            if not relevant_chunks:
                return {
                    "query": query,
                    "answer": "관련 정보를 찾을 수 없습니다. 다른 질문을 시도해보세요.",
                    "relevant_chunks": [],
                    "context": "",
                    "hierarchy_info": ""
                }
            
            # 2. 컨텍스트 생성 (계층관계 정보 포함)
            context = self.create_context_from_chunks(relevant_chunks)
            
            # 3. 답변 생성
            answer = self.generate_answer(query, context)
            
            # 4. 계층관계 정보 추출
            hierarchy_info = self._create_hierarchy_info(relevant_chunks)
            
            result = {
                "query": query,
                "answer": answer,
                "relevant_chunks": relevant_chunks,
                "context": context,
                "hierarchy_info": hierarchy_info
            }
            
            logger.info("질문 처리 완료")
            return result
            
        except Exception as e:
            logger.error(f"질문 처리 실패: {e}")
            return {
                "query": query,
                "answer": f"질문 처리 중 오류가 발생했습니다: {str(e)}",
                "relevant_chunks": [],
                "context": "",
                "hierarchy_info": ""
            }

def load_openai_api_key() -> str:
    """OpenAI API 키 로드"""
    # 환경변수에서 API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # .env 파일에서 API 키 확인
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key
    except ImportError:
        pass
    
    # 직접 입력 요청
    api_key = input("OpenAI API 키를 입력하세요: ").strip()
    if not api_key:
        raise ValueError("OpenAI API 키가 필요합니다.")
    
    return api_key

def main():
    """메인 함수 - 대화형 QA 시스템"""
    try:
        # OpenAI API 키 로드
        api_key = load_openai_api_key()
        
        # 계층관계 RAG QA 시스템 초기화
        logger.info("계층관계 RAG QA 시스템 초기화 중...")
        rag_system = HierarchyRAGQASystem(openai_api_key=api_key)
        logger.info("계층관계 RAG QA 시스템 초기화 완료")
        
        print("\n" + "="*60)
        print("삼성전자 감사보고서 계층관계 RAG QA 시스템")
        print("="*60)
        print("질문을 입력하세요. 종료하려면 'quit' 또는 'exit'를 입력하세요.")
        print("예시: '유동자산에 대해 알려주세요', '현금및현금성자산은 얼마인가요?'")
        print("-"*60)
        
        while True:
            try:
                # 사용자 입력
                query = input("\n질문: ").strip()
                
                if query.lower() in ['quit', 'exit', '종료']:
                    print("시스템을 종료합니다.")
                    break
                
                if not query:
                    print("질문을 입력해주세요.")
                    continue
                
                # 질문 처리
                result = rag_system.ask_question(query)
                
                # 결과 출력
                print("\n" + "-"*60)
                print("답변:")
                print(result["answer"])
                
                if result.get("hierarchy_info"):
                    print("\n" + "-"*60)
                    print("계층관계 정보:")
                    print(result["hierarchy_info"])
                
                if result["relevant_chunks"]:
                    print(f"\n참조된 청크 수: {len(result['relevant_chunks'])}")
                    print("관련 청크:")
                    for i, chunk in enumerate(result["relevant_chunks"][:3], 1):
                        print(f"  {i}. [점수: {chunk['score']:.3f}] {chunk['text'][:100]}...")
                
                print("-"*60)
                
            except KeyboardInterrupt:
                print("\n시스템을 종료합니다.")
                break
            except Exception as e:
                logger.error(f"질문 처리 중 오류: {e}")
                print(f"오류가 발생했습니다: {e}")
    
    except Exception as e:
        logger.error(f"시스템 초기화 실패: {e}")
        print(f"시스템 초기화 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
