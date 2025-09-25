#!/usr/bin/env python3
"""
BGE-M3-KO 모델을 사용하여 텍스트 청크를 임베딩하는 스크립트
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
from tqdm import tqdm
import torch
from sentence_transformers import SentenceTransformer
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BGEM3KOEmbedder:
    """BGE-M3-KO 모델을 사용한 임베딩 클래스"""
    
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = None):
        """
        Args:
            model_name: BGE-M3 모델명 (한국어 지원)
            device: 사용할 디바이스 ('cuda', 'cpu', None)
        """
        self.model_name = model_name
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        
        logger.info(f"BGE-M3-KO 모델 로딩 중... (디바이스: {self.device})")
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
            logger.info(f"모델 로딩 완료: {model_name}")
        except Exception as e:
            logger.error(f"모델 로딩 실패: {e}")
            raise
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        텍스트 리스트를 임베딩으로 변환
        
        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기
            
        Returns:
            임베딩 벡터 배열 (n_samples, embedding_dim)
        """
        logger.info(f"{len(texts)}개 텍스트 임베딩 시작...")
        
        embeddings = []
        for i in tqdm(range(0, len(texts), batch_size), desc="임베딩 진행"):
            batch_texts = texts[i:i + batch_size]
            try:
                batch_embeddings = self.model.encode(
                    batch_texts,
                    convert_to_numpy=True,
                    show_progress_bar=False
                )
                embeddings.append(batch_embeddings)
            except Exception as e:
                logger.error(f"배치 {i//batch_size + 1} 임베딩 실패: {e}")
                # 실패한 배치에 대해 개별 처리
                for text in batch_texts:
                    try:
                        single_embedding = self.model.encode([text], convert_to_numpy=True)
                        embeddings.append(single_embedding)
                    except Exception as e2:
                        logger.error(f"개별 텍스트 임베딩 실패: {e2}")
                        # 실패한 경우 0 벡터로 대체
                        embedding_dim = self.model.get_sentence_embedding_dimension()
                        zero_embedding = np.zeros((1, embedding_dim))
                        embeddings.append(zero_embedding)
        
        if embeddings:
            result = np.vstack(embeddings)
            logger.info(f"임베딩 완료: {result.shape}")
            return result
        else:
            raise ValueError("임베딩 결과가 없습니다.")

def load_chunks_from_jsonl(file_path: str) -> List[Dict[str, Any]]:
    """JSONL 파일에서 청크 데이터 로드"""
    chunks = []
    logger.info(f"청크 파일 로딩: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.warning(f"라인 {line_num} JSON 파싱 실패: {e}")
                        continue
        
        logger.info(f"총 {len(chunks)}개 청크 로드 완료")
        return chunks
    
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {file_path}")
        raise
    except Exception as e:
        logger.error(f"파일 로딩 실패: {e}")
        raise

def save_embeddings_to_jsonl(chunks: List[Dict[str, Any]], 
                           embeddings: np.ndarray, 
                           output_path: str):
    """임베딩 결과를 JSONL 파일로 저장"""
    logger.info(f"임베딩 결과 저장 중: {output_path}")
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for chunk, embedding in zip(chunks, embeddings):
                # 임베딩을 리스트로 변환 (JSON 직렬화를 위해)
                chunk_with_embedding = chunk.copy()
                chunk_with_embedding['embedding'] = embedding.tolist()
                
                f.write(json.dumps(chunk_with_embedding, ensure_ascii=False) + '\n')
        
        logger.info(f"임베딩 결과 저장 완료: {len(chunks)}개 청크")
    
    except Exception as e:
        logger.error(f"임베딩 결과 저장 실패: {e}")
        raise

def main():
    """메인 함수"""
    # 파일 경로 설정
    input_file = "/Users/yoon/Desktop/final_api/enhanced_vector_chunks_9_24.jsonl"
    output_file = "/Users/yoon/Desktop/final_api/enhanced_vector_chunks_with_embeddings.jsonl"
    
    # 입력 파일 존재 확인
    if not os.path.exists(input_file):
        logger.error(f"입력 파일이 존재하지 않습니다: {input_file}")
        sys.exit(1)
    
    try:
        # 1. 청크 데이터 로드
        chunks = load_chunks_from_jsonl(input_file)
        
        if not chunks:
            logger.error("로드된 청크가 없습니다.")
            sys.exit(1)
        
        # 2. 텍스트 추출
        texts = [chunk['text'] for chunk in chunks]
        logger.info(f"임베딩할 텍스트 수: {len(texts)}")
        
        # 3. BGE-M3-KO 모델로 임베딩
        embedder = BGEM3KOEmbedder()
        embeddings = embedder.embed_texts(texts, batch_size=16)  # 메모리 고려하여 배치 크기 조정
        
        # 4. 결과 저장
        save_embeddings_to_jsonl(chunks, embeddings, output_file)
        
        logger.info("임베딩 작업 완료!")
        logger.info(f"입력 파일: {input_file}")
        logger.info(f"출력 파일: {output_file}")
        logger.info(f"처리된 청크 수: {len(chunks)}")
        logger.info(f"임베딩 차원: {embeddings.shape[1]}")
        
    except Exception as e:
        logger.error(f"임베딩 작업 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
