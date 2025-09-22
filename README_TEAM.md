# NLP Team3 - 벡터 DB 프로젝트

## 🚀 빠른 시작 가이드

### 1. 프로젝트 클론
```bash
git clone [YOUR_REPOSITORY_URL]
cd NLP_team3
```

### 2. 환경 설정 (자동)
```bash
python setup_environment.py
```

### 3. 벡터 DB 실행
```bash
python vecDB.py
```

## 📁 프로젝트 구조

```
NLP_team3/
├── vecDB.py              # 메인 벡터 DB 파이프라인
├── config.py             # 설정 파일 (경로 등)
├── setup_environment.py  # 환경 설정 스크립트
├── 아카이브/             # 주석 데이터 (annotation)
│   ├── 감사보고서_2014_parsed.json
│   ├── 감사보고서_2015_parsed.json
│   └── ...
├── table_parsing/        # 재무표 데이터 (financial_table)
│   ├── 감사보고서_2014_parsed.json
│   ├── 감사보고서_2015_parsed.json
│   └── ...
├── kifrs_combined_2.json # 회계기준 데이터 (accounting_standard)
└── vector_db/           # ChromaDB 저장소 (자동 생성)
```

## ⚙️ 수동 설정 (필요시)

### 필요한 패키지 설치
```bash
pip install sentence-transformers chromadb torch transformers numpy pandas tqdm scikit-learn
```

### Conda 환경 생성 (권장)
```bash
conda create -n nlp_team3 python=3.9
conda activate nlp_team3
pip install -r requirements.txt
```

## 🔧 팀원별 커스터마이징

### 파일 경로 수정
`config.py` 파일에서 데이터 파일 경로를 수정할 수 있습니다:

```python
# 예시: 다른 폴더에 데이터가 있는 경우
DATA_PATHS = {
    'annotation': {
        2024: Path("/your/custom/path/아카이브/감사보고서_2024_parsed.json")
    }
}
```

### ChromaDB 경로 변경
```python
# config.py에서 수정
CHROMA_DB_PATH = Path("/your/custom/vector_db/path")
```

## 🧪 테스트

### 환경 확인
```bash
python config.py
```

### 간단한 검색 테스트
```python
from vecDB import ImprovedVectorPipeline

pipeline = ImprovedVectorPipeline()
results = pipeline.search_unified("매출액은 얼마인가요?", n_results=3)
pipeline.print_search_results("매출액은 얼마인가요?", results)
```

## 🐛 문제 해결

### 1. 모델 다운로드 실패
```bash
# 수동으로 모델 다운로드
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('jhgan/ko-sroberta-multitask')"
```

### 2. 메모리 부족
`config.py`에서 배치 크기 조정:
```python
DEFAULT_BATCH_SIZE = 10  # 기본값 25에서 줄임
```

### 3. 파일 경로 오류
```bash
# 데이터 파일 확인
python config.py
```

### 4. ChromaDB 오류
```bash
# 벡터 DB 초기화
python -c "
from vecDB import ImprovedVectorPipeline
pipeline = ImprovedVectorPipeline(force_reset=True)
"
```

## 📊 주요 기능

### 동적 가중치 시스템
- **회계기준 질문**: accounting_standard 우선 (0.7)
- **재무수치 질문**: financial_table 우선 (0.6)
- **일반설명 질문**: annotation 우선 (0.5)

### 검색 예시
```python
# 회계기준 관련
results = pipeline.search_unified("K-IFRS 1116 리스 기준서 적용은?")

# 재무수치 관련  
results = pipeline.search_unified("2024년 매출액은 얼마인가요?")

# 일반 설명
results = pipeline.search_unified("회계정책은 어떻게 되나요?")
```

## 🤝 팀 협업

### Git 사용 시 주의사항
```bash
# 벡터 DB 폴더는 커밋하지 않기
echo "vector_db/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
```

### 성능 최적화
- **메모리**: 배치 크기 조정
- **속도**: SSD 사용 권장
- **정확도**: 청크 크기 튜닝

## 📞 지원

문제 발생 시:
1. `python setup_environment.py` 재실행
2. `python config.py`로 설정 확인
3. 팀원들과 공유된 데이터 파일 확인
