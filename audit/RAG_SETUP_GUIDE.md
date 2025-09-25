# RAG QA 시스템 설정 가이드

이 가이드는 `enhanced_vector_chunks_9_24.jsonl` 파일을 기반으로 BGE-M3-KO 모델을 사용한 임베딩, Qdrant 벡터DB 구축, 그리고 ChatGPT API를 활용한 RAG QA 시스템 구축 방법을 설명합니다.

## 📋 사전 요구사항

### 1. 시스템 요구사항
- Python 3.8 이상
- 최소 8GB RAM (임베딩 모델 로딩용)
- GPU 권장 (임베딩 속도 향상)

### 2. 필요한 서비스
- **Qdrant**: 벡터 데이터베이스
- **OpenAI API**: ChatGPT API 키

## 🚀 설치 및 설정

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. Qdrant 서버 실행
```bash
# Docker를 사용한 Qdrant 실행
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 또는 로컬 설치
# https://qdrant.tech/documentation/quick-start/
```

### 3. 환경 변수 설정
`env_template.txt` 파일을 참고하여 `.env` 파일을 생성하고 OpenAI API 키를 설정하세요:

```bash
cp env_template.txt .env
# .env 파일을 편집하여 OPENAI_API_KEY 설정
```

## 🔄 RAG 파이프라인 실행

### 자동 실행 (권장)
```bash
./run_rag_pipeline.sh
```

### 수동 실행
```bash
# 1단계: 임베딩 생성
python scripts/embed_with_bge_m3_ko.py

# 2단계: Qdrant 벡터DB 구축
python scripts/build_qdrant_vector_db.py

# 3단계: RAG QA 시스템 실행
python scripts/rag_qa_system.py
```

## 🌐 웹 인터페이스 실행

Streamlit 웹 인터페이스를 사용하려면:

```bash
streamlit run streamlit_rag_chatbot.py
```

브라우저에서 `http://localhost:8501`을 열어 사용하세요.

## 📁 파일 구조

```
final_api/
├── enhanced_vector_chunks_9_24.jsonl          # 원본 청크 데이터
├── enhanced_vector_chunks_with_embeddings.jsonl # 임베딩된 청크 데이터
├── scripts/
│   ├── embed_with_bge_m3_ko.py                # BGE-M3-KO 임베딩 스크립트
│   ├── build_qdrant_vector_db.py              # Qdrant 벡터DB 구축 스크립트
│   └── rag_qa_system.py                       # RAG QA 시스템
├── streamlit_rag_chatbot.py                   # Streamlit 웹 인터페이스
├── run_rag_pipeline.sh                        # 자동 실행 스크립트
└── requirements.txt                           # Python 의존성
```

## 🔧 주요 컴포넌트

### 1. BGE-M3-KO 임베딩 (`embed_with_bge_m3_ko.py`)
- **목적**: 텍스트 청크를 벡터로 변환
- **모델**: BAAI/bge-m3 (한국어 지원)
- **입력**: `enhanced_vector_chunks_9_24.jsonl`
- **출력**: `enhanced_vector_chunks_with_embeddings.jsonl`

### 2. Qdrant 벡터DB (`build_qdrant_vector_db.py`)
- **목적**: 임베딩 벡터를 벡터 데이터베이스에 저장
- **컬렉션**: `audit_reports`
- **거리 측정**: Cosine similarity

### 3. RAG QA 시스템 (`rag_qa_system.py`)
- **목적**: 질문-답변 시스템
- **검색**: 벡터 유사도 검색
- **생성**: ChatGPT-3.5-turbo

## 💡 사용 예시

### 질문 예시
- "2017년 삼성전자의 유동자산은 얼마인가요?"
- "2020년 매출채권의 변화는 어떻게 되나요?"
- "최근 3년간 현금흐름은 어떤 추세인가요?"
- "삼성전자의 자산총계는 몇 년도에 가장 높았나요?"

### 답변 특징
- 구체적인 수치와 데이터 포함
- 참조된 문서 정보 제공
- 메타데이터 기반 컨텍스트

## ⚙️ 설정 옵션

### 검색 파라미터
- `top_k`: 검색할 청크 수 (기본값: 5)
- `score_threshold`: 유사도 임계값 (기본값: 0.7)
- `max_context_length`: 최대 컨텍스트 길이 (기본값: 4000)

### 모델 설정
- `embedding_model_name`: BAAI/bge-m3
- `llm_model`: gpt-3.5-turbo
- `temperature`: 0.1 (일관성 있는 답변)

## 🐛 문제 해결

### 일반적인 문제

1. **메모리 부족**
   - 배치 크기 줄이기 (`batch_size` 파라미터)
   - GPU 사용 권장

2. **Qdrant 연결 실패**
   - Qdrant 서버 실행 상태 확인
   - 포트 6333 접근 가능 여부 확인

3. **OpenAI API 오류**
   - API 키 유효성 확인
   - 사용량 한도 확인

4. **임베딩 모델 로딩 실패**
   - 인터넷 연결 확인
   - Hugging Face 토큰 설정 (필요시)

### 로그 확인
모든 스크립트는 상세한 로그를 출력합니다. 오류 발생 시 로그를 확인하여 문제를 진단하세요.

## 📊 성능 최적화

### 하드웨어 권장사항
- **CPU**: 8코어 이상
- **RAM**: 16GB 이상
- **GPU**: NVIDIA GPU (CUDA 지원)
- **저장공간**: SSD 권장

### 소프트웨어 최적화
- 배치 크기 조정
- 벡터 인덱싱 최적화
- 컨텍스트 길이 조정

## 🔄 업데이트 및 유지보수

### 새로운 데이터 추가
1. 새로운 청크 데이터를 `enhanced_vector_chunks_9_24.jsonl`에 추가
2. 임베딩 재생성
3. Qdrant 컬렉션 업데이트

### 모델 업데이트
- BGE-M3 모델 업데이트 시 임베딩 재생성 필요
- ChatGPT 모델 변경 시 코드 수정 필요

## 📞 지원

문제가 발생하거나 질문이 있으시면:
1. 로그 파일 확인
2. 설정 파일 검증
3. 시스템 요구사항 확인
4. GitHub Issues 등록 (해당하는 경우)
