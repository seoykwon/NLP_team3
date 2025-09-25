# 스크립트 디렉토리

이 디렉토리는 RAG 시스템의 핵심 스크립트들을 포함합니다.

## 주요 스크립트

### 1. `hierarchy_rag_qa_system.py`
- **목적**: 계층관계를 고려한 RAG QA 시스템 (메인 시스템)
- **기능**: 
  - 계층관계 키워드 자동 추출
  - 상하위 항목들을 함께 검색
  - 계층관계 정보를 포함한 답변 생성
- **사용법**: `python scripts/hierarchy_rag_qa_system.py`

### 2. `rag_qa_system.py`
- **목적**: 기본 RAG QA 시스템
- **기능**: 
  - 일반적인 RAG 검색 및 답변 생성
  - 계층관계 없이 기본적인 QA 기능 제공
- **사용법**: `python scripts/rag_qa_system.py`

### 3. `build_qdrant_vector_db.py`
- **목적**: Qdrant 벡터 데이터베이스 구축
- **기능**: 
  - 처리된 JSON 데이터를 벡터로 변환
  - Qdrant에 벡터 데이터베이스 구축
- **사용법**: `python scripts/build_qdrant_vector_db.py`

### 4. `embed_with_bge_m3_ko.py`
- **목적**: BGE-M3-KO 모델을 사용한 임베딩 생성
- **기능**: 
  - 한국어 최적화된 임베딩 모델 사용
  - 텍스트를 벡터로 변환
- **사용법**: `python scripts/embed_with_bge_m3_ko.py`

## 실행 순서

1. **데이터 준비**: `data/` 디렉토리에 원본 HTML 파일들 배치
2. **데이터 처리**: HTML 파일들을 JSON으로 변환
3. **벡터 DB 구축**: `build_qdrant_vector_db.py` 실행
4. **시스템 실행**: `hierarchy_rag_qa_system.py` 또는 웹 인터페이스 실행

## 의존성

- Qdrant 클라이언트
- OpenAI API
- BGE-M3-KO 임베딩 모델
- 기타 requirements.txt에 명시된 패키지들

