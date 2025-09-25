#!/usr/bin/env python3
"""
임베딩된 청크 데이터를 Qdrant 벡터DB에 저장하는 스크립트
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from tqdm import tqdm
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, CollectionStatus
from qdrant_client.http import models

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QdrantVectorDB:
    """Qdrant 벡터DB 관리 클래스"""
    
    def __init__(self, host: str = "localhost", port: int = 6333, 
                 collection_name: str = "audit_reports"):
        """
        Args:
            host: Qdrant 서버 호스트
            port: Qdrant 서버 포트
            collection_name: 컬렉션 이름
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        
        logger.info(f"Qdrant 클라이언트 연결 중... ({host}:{port})")
        try:
            self.client = QdrantClient(host=host, port=port)
            logger.info("Qdrant 클라이언트 연결 성공")
        except Exception as e:
            logger.error(f"Qdrant 클라이언트 연결 실패: {e}")
            raise
    
    def create_collection(self, vector_size: int, distance: Distance = Distance.COSINE):
        """컬렉션 생성"""
        logger.info(f"컬렉션 생성 중: {self.collection_name}")
        
        try:
            # 기존 컬렉션이 있는지 확인
            collections = self.client.get_collections()
            existing_collections = [col.name for col in collections.collections]
            
            if self.collection_name in existing_collections:
                logger.info(f"컬렉션 '{self.collection_name}'이 이미 존재합니다.")
                # 기존 컬렉션 삭제 후 재생성
                logger.info("기존 컬렉션 삭제 중...")
                self.client.delete_collection(self.collection_name)
            
            # 새 컬렉션 생성
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance
                )
            )
            logger.info(f"컬렉션 '{self.collection_name}' 생성 완료")
            
        except Exception as e:
            logger.error(f"컬렉션 생성 실패: {e}")
            raise
    
    def get_collection_info(self) -> Optional[Dict]:
        """컬렉션 정보 조회"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "status": collection_info.status,
                "vectors_count": collection_info.vectors_count,
                "indexed_vectors_count": collection_info.indexed_vectors_count,
                "points_count": collection_info.points_count,
                "segments_count": collection_info.segments_count,
                "config": collection_info.config
            }
        except Exception as e:
            logger.error(f"컬렉션 정보 조회 실패: {e}")
            return None
    
    def insert_vectors(self, points: List[PointStruct], batch_size: int = 100):
        """벡터 데이터 삽입"""
        logger.info(f"{len(points)}개 포인트 삽입 시작...")
        
        try:
            # 배치 단위로 삽입
            for i in tqdm(range(0, len(points), batch_size), desc="벡터 삽입 진행"):
                batch_points = points[i:i + batch_size]
                
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch_points
                )
            
            logger.info("벡터 삽입 완료")
            
        except Exception as e:
            logger.error(f"벡터 삽입 실패: {e}")
            raise
    
    def search_vectors(self, query_vector: List[float], limit: int = 5, 
                      score_threshold: float = 0.0) -> List[Dict]:
        """벡터 검색"""
        try:
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold
            )
            
            results = []
            for result in search_results:
                results.append({
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                })
            
            return results
            
        except Exception as e:
            logger.error(f"벡터 검색 실패: {e}")
            return []

def load_embeddings_from_jsonl(file_path: str) -> List[Dict[str, Any]]:
    """임베딩이 포함된 JSONL 파일에서 데이터 로드"""
    chunks = []
    logger.info(f"임베딩 파일 로딩: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'embedding' not in chunk:
                            logger.warning(f"라인 {line_num}: 임베딩 데이터가 없습니다.")
                            continue
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.warning(f"라인 {line_num} JSON 파싱 실패: {e}")
                        continue
        
        logger.info(f"총 {len(chunks)}개 임베딩 청크 로드 완료")
        return chunks
    
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {file_path}")
        raise
    except Exception as e:
        logger.error(f"파일 로딩 실패: {e}")
        raise

def prepare_points_for_qdrant(chunks: List[Dict[str, Any]]) -> List[PointStruct]:
    """Qdrant 포인트 구조로 변환"""
    points = []
    
    for i, chunk in enumerate(tqdm(chunks, desc="포인트 변환 중")):
        try:
            # 임베딩 벡터 추출
            embedding = chunk['embedding']
            if not isinstance(embedding, list):
                logger.warning(f"청크 {i}: 임베딩이 리스트가 아닙니다.")
                continue
            
            # 메타데이터 준비 (임베딩 제외)
            payload = chunk.copy()
            payload.pop('embedding', None)  # 임베딩은 별도로 저장
            
            # 포인트 ID 생성 (Qdrant는 정수 또는 UUID만 허용)
            point_id = i  # 인덱스를 ID로 사용
            
            # Qdrant 포인트 생성
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )
            points.append(point)
            
        except Exception as e:
            logger.error(f"청크 {i} 포인트 변환 실패: {e}")
            continue
    
    logger.info(f"{len(points)}개 포인트 변환 완료")
    return points

def main():
    """메인 함수"""
    # 파일 경로 설정
    embeddings_file = "/Users/yoon/Desktop/final_api/enhanced_vector_chunks_with_embeddings.jsonl"
    
    # Qdrant 설정
    qdrant_host = "localhost"
    qdrant_port = 6333
    collection_name = "audit_reports"
    
    # 입력 파일 존재 확인
    if not os.path.exists(embeddings_file):
        logger.error(f"임베딩 파일이 존재하지 않습니다: {embeddings_file}")
        logger.info("먼저 embed_with_bge_m3_ko.py 스크립트를 실행하여 임베딩을 생성하세요.")
        sys.exit(1)
    
    try:
        # 1. 임베딩 데이터 로드
        chunks = load_embeddings_from_jsonl(embeddings_file)
        
        if not chunks:
            logger.error("로드된 임베딩 청크가 없습니다.")
            sys.exit(1)
        
        # 2. 임베딩 차원 확인
        embedding_dim = len(chunks[0]['embedding'])
        logger.info(f"임베딩 차원: {embedding_dim}")
        
        # 3. Qdrant 벡터DB 초기화
        vector_db = QdrantVectorDB(
            host=qdrant_host,
            port=qdrant_port,
            collection_name=collection_name
        )
        
        # 4. 컬렉션 생성
        vector_db.create_collection(vector_size=embedding_dim)
        
        # 5. 포인트 변환
        points = prepare_points_for_qdrant(chunks)
        
        if not points:
            logger.error("변환된 포인트가 없습니다.")
            sys.exit(1)
        
        # 6. 벡터 삽입
        vector_db.insert_vectors(points, batch_size=50)  # 메모리 고려하여 배치 크기 조정
        
        # 7. 컬렉션 정보 확인
        collection_info = vector_db.get_collection_info()
        if collection_info:
            logger.info("컬렉션 정보:")
            logger.info(f"  - 상태: {collection_info['status']}")
            logger.info(f"  - 포인트 수: {collection_info['points_count']}")
            logger.info(f"  - 벡터 수: {collection_info['vectors_count']}")
            logger.info(f"  - 세그먼트 수: {collection_info['segments_count']}")
        
        logger.info("Qdrant 벡터DB 구축 완료!")
        logger.info(f"컬렉션명: {collection_name}")
        logger.info(f"저장된 포인트 수: {len(points)}")
        logger.info(f"임베딩 차원: {embedding_dim}")
        
    except Exception as e:
        logger.error(f"Qdrant 벡터DB 구축 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
