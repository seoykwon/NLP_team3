#!/usr/bin/env python3
"""
ChatGPT API를 사용한 RAG QA 시스템
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
import numpy as np
from sentence_transformers import SentenceTransformer
import torch

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RAGQASystem:
    """RAG 기반 QA 시스템"""
    
    def __init__(self, 
                 openai_api_key: str,
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 collection_name: str = "audit_reports",
                 embedding_model_name: str = "BAAI/bge-m3"):
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
        
        # 임베딩 모델 초기화
        logger.info(f"임베딩 모델 로딩 중... ({embedding_model_name})")
        try:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.embedding_model = SentenceTransformer(embedding_model_name, device=self.device)
            logger.info(f"임베딩 모델 로딩 완료 (디바이스: {self.device})")
        except Exception as e:
            logger.error(f"임베딩 모델 로딩 실패: {e}")
            raise
    
    def embed_query(self, query: str) -> List[float]:
        """쿼리 텍스트를 임베딩으로 변환"""
        try:
            embedding = self.embedding_model.encode([query], convert_to_numpy=True)
            return embedding[0].tolist()
        except Exception as e:
            logger.error(f"쿼리 임베딩 실패: {e}")
            raise
    
    def search_relevant_chunks(self, query: str, top_k: int = 5, 
                              score_threshold: float = 0.7) -> List[Dict]:
        """관련 청크 검색"""
        try:
            # 쿼리 임베딩
            query_embedding = self.embed_query(query)
            
            # 벡터 검색
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                score_threshold=score_threshold
            )
            
            # 결과 정리
            relevant_chunks = []
            for result in search_results:
                chunk_data = {
                    "id": result.id,
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "metadata": result.payload.get("metadata", {})
                }
                relevant_chunks.append(chunk_data)
            
            logger.info(f"{len(relevant_chunks)}개 관련 청크 검색 완료")
            return relevant_chunks
            
        except Exception as e:
            logger.error(f"청크 검색 실패: {e}")
            return []
    
    def create_context_from_chunks(self, chunks: List[Dict], max_context_length: int = 4000) -> str:
        """검색된 청크들로부터 컨텍스트 생성"""
        context_parts = []
        current_length = 0
        
        for chunk in chunks:
            chunk_text = chunk["text"]
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
    
    def generate_answer(self, query: str, context: str) -> str:
        """ChatGPT를 사용하여 답변 생성"""
        try:
            # 시스템 프롬프트
            system_prompt = """당신은 삼성전자 감사보고서 전문가입니다. 
제공된 컨텍스트를 바탕으로 사용자의 질문에 정확하고 상세하게 답변해주세요.

답변 시 다음 사항을 지켜주세요:
1. 제공된 컨텍스트의 정보만을 사용하여 답변하세요.
2. 구체적인 수치와 데이터를 포함하여 답변하세요.
3. 답변의 근거가 되는 청크 정보를 참조하세요.
4. 모르는 내용에 대해서는 추측하지 말고 "제공된 정보로는 답변할 수 없습니다"라고 말하세요.
5. 한국어로 답변하세요."""

            # 사용자 프롬프트
            user_prompt = f"""질문: {query}

관련 정보:
{context}

위 정보를 바탕으로 질문에 답변해주세요."""

            # ChatGPT API 호출
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            answer = response.choices[0].message.content
            logger.info("답변 생성 완료")
            return answer
            
        except Exception as e:
            logger.error(f"답변 생성 실패: {e}")
            return f"답변 생성 중 오류가 발생했습니다: {str(e)}"
    
    def ask_question(self, query: str, top_k: int = 5, 
                    score_threshold: float = 0.7) -> Dict[str, Any]:
        """질문에 대한 전체 RAG 프로세스 실행"""
        logger.info(f"질문 처리 시작: {query}")
        
        try:
            # 1. 관련 청크 검색
            relevant_chunks = self.search_relevant_chunks(
                query, top_k=top_k, score_threshold=score_threshold
            )
            
            if not relevant_chunks:
                return {
                    "query": query,
                    "answer": "관련 정보를 찾을 수 없습니다. 다른 질문을 시도해보세요.",
                    "relevant_chunks": [],
                    "context": ""
                }
            
            # 2. 컨텍스트 생성
            context = self.create_context_from_chunks(relevant_chunks)
            
            # 3. 답변 생성
            answer = self.generate_answer(query, context)
            
            result = {
                "query": query,
                "answer": answer,
                "relevant_chunks": relevant_chunks,
                "context": context
            }
            
            logger.info("질문 처리 완료")
            return result
            
        except Exception as e:
            logger.error(f"질문 처리 실패: {e}")
            return {
                "query": query,
                "answer": f"질문 처리 중 오류가 발생했습니다: {str(e)}",
                "relevant_chunks": [],
                "context": ""
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
        
        # RAG QA 시스템 초기화
        logger.info("RAG QA 시스템 초기화 중...")
        rag_system = RAGQASystem(openai_api_key=api_key)
        logger.info("RAG QA 시스템 초기화 완료")
        
        print("\n" + "="*60)
        print("삼성전자 감사보고서 RAG QA 시스템")
        print("="*60)
        print("질문을 입력하세요. 종료하려면 'quit' 또는 'exit'를 입력하세요.")
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
