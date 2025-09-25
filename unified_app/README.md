# 🔗 통합 RAG 시스템

audit, extra, graph 폴더의 모든 기능을 하나의 웹 인터페이스에서 사용할 수 있는 통합 RAG 시스템입니다.

## ✨ 주요 특징

### 📊 감사보고서 RAG 시스템
- **데이터**: 삼성전자 감사보고서 (2014-2024)
- **특징**: 계층관계 인식 검색, 상하위 관계 자동 인식
- **모델**: BGE-M3-KO 임베딩, GPT-4 답변 생성
- **벡터DB**: Qdrant

### ⚖️ 법률 문서 RAG 시스템
- **데이터**: 상법 조문, K-IFRS 회계기준
- **특징**: 하이브리드 검색 (임베딩 + TF-IDF)
- **모델**: multilingual-e5 임베딩, GPT-4 답변 생성
- **검색**: FAISS 인덱스 + 텍스트 유사도

### 🕸️ 그래프 분석 시스템
- **데이터**: 삼성전자 감사보고서 (2014-2024)
- **특징**: 그래프 기반 검색, 관계 네트워크 분석
- **모델**: Qdrant 벡터DB, LLaMA 모델 지원
- **분석**: 단일 값 조회, 계층 구조 조회

## 🚀 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

**방법 1: .env 파일 사용 (권장)**
```bash
cp .env.example .env
# .env 파일을 열어서 your_openai_api_key_here 부분을 실제 API 키로 교체
```

**방법 2: 환경변수 직접 설정**
```bash
export OPENAI_API_KEY="your_openai_api_key"
```

### 3. 실행

```bash
streamlit run main.py
```

브라우저에서 `http://localhost:8501`에 접속하여 통합 시스템을 사용할 수 있습니다.

## 📁 프로젝트 구조

```
unified_app/
├── main.py                    # 메인 Streamlit 앱
├── requirements.txt           # 통합 의존성
├── README.md                  # 이 파일
├── modules/                   # 기능별 모듈
│   ├── utils.py              # 공통 유틸리티
│   ├── audit_rag/            # 감사보고서 RAG
│   │   ├── __init__.py
│   │   ├── wrapper.py        # 인터페이스 래퍼
│   │   └── hierarchy_rag_qa_system.py  # 핵심 로직
│   ├── legal_rag/            # 법률 문서 RAG
│   │   ├── __init__.py
│   │   ├── wrapper.py        # 인터페이스 래퍼
│   │   └── simple_legal_rag.py  # 핵심 로직
│   └── graph_analysis/       # 그래프 분석
│       ├── __init__.py
│       ├── wrapper.py        # 인터페이스 래퍼
│       └── chat.py           # 핵심 로직
├── data/                     # 데이터 디렉토리 (심볼릭 링크)
├── config/                   # 설정 파일
└── static/                   # 정적 파일
```

## 💡 사용 예시

### 감사보고서 RAG 질문 예시
- "2024년의 유동자산에 대해 알려주고 각각 얼마인지도 알려줘"
- "2019년 재무상태표상 종속기업투자는 얼마인가요?"
- "2020년부터 2024년까지 영업이익 추이를 알려주세요"

### 법률 문서 RAG 질문 예시
- "준비금의 자본전입은 이사회에서 결정할 수 있는가?"
- "개발비 자산 인식 요건은 무엇인가요?"
- "상법상 이사의 의무는 무엇인가요?"

### 그래프 분석 질문 예시
- "2024년 재무상태표 상 당기 자산총계는 얼마인가?"
- "2024년 비유동자산 하위 구조 알려줘"
- "2023년 영업활동현금흐름 내역을 보여줘"

## ⚙️ 시스템 요구사항

- Python 3.8+
- 8GB+ RAM (벡터 DB 구축 시)
- OpenAI API 키
- 충분한 디스크 공간 (데이터 파일용)

## 🔧 설정 옵션

### 감사보고서 RAG
- `top_k`: 검색할 청크 수 (기본값: 25)
- `score_threshold`: 유사도 임계값 (기본값: 0.3)

### 법률 문서 RAG
- `topk`: 검색 결과 수 (기본값: 5)
- 하이브리드 검색 (임베딩 + TF-IDF)

### 그래프 분석
- 검색 유형: 자동 감지, 단일 값 조회, 계층 구조 조회
- 디버그 정보 표시 옵션

## 📊 데이터 요구사항

시스템이 정상 작동하려면 다음 데이터가 필요합니다:

1. **감사보고서 데이터**: `../audit/storage/` 경로
2. **법률 문서 데이터**: `../extra/` 경로
3. **그래프 분석 데이터**: `../graph/data/` 경로

## 🐛 문제 해결

### 모듈 import 오류
```bash
# Python 경로 확인
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### API 키 오류
```bash
# 환경변수 확인
echo $OPENAI_API_KEY
```

### 데이터 경로 오류
- 상대 경로가 올바른지 확인
- 원본 데이터 폴더가 존재하는지 확인

## 🔒 보안 주의사항

### API 키 관리
- `.env` 파일은 **절대 GitHub에 업로드하지 마세요**
- `.gitignore`에 `.env` 파일이 포함되어 있습니다
- `.env.example` 파일을 참고하여 설정하세요

### GitHub에 올리기 전 체크리스트
- [ ] `.env` 파일이 `.gitignore`에 포함되어 있는지 확인
- [ ] API 키가 코드에 하드코딩되지 않았는지 확인
- [ ] `.env.example` 파일로 다른 사용자들을 위한 가이드 제공

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. **API 키를 .env 파일에 설정하고 .gitignore 확인**
4. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 🙏 감사의 말

- [Streamlit](https://streamlit.io/) - 웹 인터페이스 프레임워크
- [OpenAI](https://openai.com/) - GPT 모델
- [Qdrant](https://qdrant.tech/) - 벡터 데이터베이스
- [BGE-M3](https://github.com/FlagOpen/FlagEmbedding) - 한국어 임베딩 모델

---

*통합 버전: v1.0.0*  
*생성일: 2024년 9월 25일*
