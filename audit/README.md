# 📊 Audit RAG System - 삼성전자 감사보고서 분석 시스템

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.6+-green.svg)](https://qdrant.tech)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

삼성전자 감사보고서(2014-2024, 11년간)를 기반으로 한 **계층관계 인식 RAG(Retrieval-Augmented Generation) QA 시스템**입니다. 재무제표의 상하위 계층관계를 이해하고 구조화된 답변을 제공합니다.

## ✨ 주요 특징

### 🔍 **계층관계 인식 검색**
- 재무제표 항목의 상하위 관계를 자동 인식
- 상위 항목 질문 시 하위 세부 항목들을 함께 제공
- 예: "자산" 질문 → 유동자산, 비유동자산 및 세부 항목들 모두 검색

### 🎯 **지능형 답변 생성**
- BGE-M3-KO 임베딩으로 한국어 최적화
- GPT-4 기반 구조화된 답변 생성
- 숫자 데이터 추세 분석 및 해석 제공

### 📊 **투명한 근거 제시**
- 답변 근거가 되는 문서 청크 표시
- 유사도 점수 및 문서 출처 정보 제공
- 년도별 데이터 비교 분석

### � **직관적 웹 인터페이스**
- Streamlit 기반 반응형 UI
- 실시간 채팅 형태의 질의응답
- 샘플 질문 및 사용 가이드 제공

## 🏗️ 시스템 아키텍처

### 핵심 구성요소
- **임베딩 모델**: BGE-M3-KO (한국어 최적화)
- **벡터 데이터베이스**: Qdrant
- **LLM**: ChatGPT-4 (답변 생성 및 어투 정리)
- **웹 인터페이스**: Streamlit

### 계층관계 매핑 예시
```python
hierarchy_mapping = {
    "자산": ["유동자산", "비유동자산"],
    "유동자산": [
        "현금및현금성자산", "단기금융상품", "매출채권", 
        "재고자산", "기타유동자산"
    ],
    "비유동자산": [
        "유형자산", "무형자산", "종속기업투자",
        "기타비유동자산"
    ]
    # 부채, 자본, 손익, 현금흐름 계층도 포함
}
```

## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone https://github.com/your-username/hierarchy-rag-system.git
cd hierarchy-rag-system
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정
```bash
export OPENAI_API_KEY="your_openai_api_key"
```

### 4. 벡터 데이터베이스 구축
```bash
python scripts/build_qdrant_vector_db.py
```

### 5. 웹 인터페이스 실행
```bash
streamlit run streamlit_rag_chatbot.py
```

브라우저에서 `http://localhost:8501`에 접속하여 시스템을 사용할 수 있습니다.

## 📁 프로젝트 구조

```
hierarchy-rag-system/
├── 📁 scripts/                    # 핵심 스크립트
│   ├── hierarchy_rag_qa_system.py    # 계층관계 RAG 시스템 (메인)
│   ├── rag_qa_system.py              # 기본 RAG 시스템
│   ├── build_qdrant_vector_db.py     # 벡터 DB 구축
│   └── embed_with_bge_m3_ko.py       # 임베딩 생성
├── 📁 data/                       # 데이터 파일
│   ├── raw/                          # 원본 HTML 파일들
│   └── processed/                    # 처리된 JSON 파일들
├── 📁 storage/                    # Qdrant 벡터 DB 저장소
├── 🖥️ streamlit_rag_chatbot.py    # Streamlit 웹 인터페이스
├── 🖥️ demo_streamlit_app.py       # 데모 앱
├── 📋 requirements.txt            # 의존성 패키지
├── 🚀 run_demo.sh                 # 데모 실행 스크립트
├── 🚀 run_rag_pipeline.sh         # RAG 파이프라인 실행 스크립트
└── 📖 README.md                   # 이 파일
```

## 💡 사용 예시

### 질문 예시
- **"유동자산에 대해 알려주세요"** → 하위 항목들도 함께 표시
- **"현금및현금성자산은 얼마인가요?"** → 상위 계층관계도 함께 설명
- **"2024년 비유동자산에 대해 알려주고 각 하위항목의 값도 알려줘"**

### 답변 특징
- 계층관계 정보를 별도 섹션으로 표시
- 상하위 관계를 명확히 설명
- 청크 참조 및 근거 제시
- 구체적인 수치와 데이터 포함

## 🛠️ 설치 및 설정

### 시스템 요구사항
- Python 3.8+
- 8GB+ RAM (벡터 DB 구축 시)
- OpenAI API 키

### 상세 설치 가이드
자세한 설치 및 설정 방법은 [RAG_SETUP_GUIDE.md](RAG_SETUP_GUIDE.md)를 참조하세요.

### 데모 가이드
시스템 시연 방법은 [DEMO_GUIDE.md](DEMO_GUIDE.md)를 참조하세요.

## 🔧 설정 옵션

### 검색 파라미터
- `top_k`: 검색할 청크 수 (기본값: 8)
- `score_threshold`: 유사도 임계값 (기본값: 0.6)

### 모델 설정
- 임베딩 모델: BGE-M3-KO
- LLM: ChatGPT-4
- Temperature: 0.1 (일관된 답변을 위해)

## 📊 성능 특징

### 검색 성능
- 계층관계 키워드 자동 인식
- 관련 항목들 자동 확장 검색
- 유사도 기반 결과 정렬

### 답변 품질
- 계층관계 구조 명확히 설명
- 구체적인 수치와 데이터 포함
- 청크 참조로 투명성 확보

## 🔒 RAG 시스템의 핵심 원칙

### LLM의 역할 (허용)
- ✅ 답변 어투 정리 및 구조화
- ✅ 제공된 컨텍스트 정보만을 사용한 답변 생성
- ✅ 계층관계 정보를 포함한 답변 구성
- ✅ 청크 정보 참조 및 근거 제시

### LLM의 제약 (금지)
- ❌ 신규 정보 생성 또는 추측
- ❌ 제공된 컨텍스트 외부의 지식 사용
- ❌ 데이터베이스에 없는 정보 답변

## 📈 향후 개선 방향

1. **계층관계 매핑 확장**: 더 세밀한 계층관계 정의
2. **다국어 지원**: 영어, 중국어 등 추가 언어 지원
3. **시각화 개선**: 계층관계 구조의 시각적 표현
4. **성능 최적화**: 검색 속도 및 정확도 향상

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 📞 문의 및 지원

- **이슈 리포트**: [GitHub Issues](https://github.com/your-username/hierarchy-rag-system/issues)
- **기능 요청**: [GitHub Discussions](https://github.com/your-username/hierarchy-rag-system/discussions)

## 🙏 감사의 말

- [BGE-M3](https://github.com/FlagOpen/FlagEmbedding) - 한국어 임베딩 모델
- [Qdrant](https://qdrant.tech/) - 벡터 데이터베이스
- [Streamlit](https://streamlit.io/) - 웹 인터페이스 프레임워크
- [OpenAI](https://openai.com/) - GPT 모델

---

*생성일: 2024년 9월 24일*  
*버전: 1.0.0*

