# 🛠️ 통합 RAG 시스템 설치 가이드

## 📋 사전 요구사항

- Python 3.8 이상
- pip (Python 패키지 매니저)
- 8GB 이상의 RAM
- OpenAI API 키

## 🚀 빠른 설치

### 1단계: 의존성 설치

```bash
cd /Users/kwonseoyoung/Desktop/comb/unified_app
pip3 install -r requirements.txt
```

### 2단계: OpenAI API 키 설정

**방법 1: 환경변수 설정**
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
```

**방법 2: .env 파일 생성**
```bash
echo "OPENAI_API_KEY=your_openai_api_key_here" > .env
```

### 3단계: 실행

```bash
./run_unified_app.sh
```

또는 직접 실행:
```bash
python3 -m streamlit run main.py
```

### 4단계: 웹 브라우저에서 접속

http://localhost:8501 에 접속하여 통합 RAG 시스템을 사용하세요.

## 🔧 상세 설치 (문제 발생 시)

### Python 환경 확인

```bash
python3 --version  # 3.8 이상이어야 함
pip3 --version
```

### 가상환경 사용 (권장)

```bash
python3 -m venv unified_rag_env
source unified_rag_env/bin/activate  # macOS/Linux
# 또는
unified_rag_env\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 개별 패키지 설치

```bash
pip3 install streamlit>=1.28.0
pip3 install qdrant-client>=1.6.0
pip3 install sentence-transformers>=2.2.0
pip3 install openai>=1,<2
pip3 install numpy>=1.24.0
pip3 install pandas>=2.0.0
pip3 install torch>=2.0.0
pip3 install transformers>=4.30.0
pip3 install scikit-learn>=1.0.0
pip3 install python-dotenv>=1,<2
pip3 install orjson>=3,<4
pip3 install tqdm>=4,<5
pip3 install rapidfuzz>=3,<4
pip3 install faiss-cpu>=1.7.0
```

## 🐛 문제 해결

### 1. ModuleNotFoundError

**증상**: `ModuleNotFoundError: No module named 'xxx'`

**해결**:
```bash
pip3 install -r requirements.txt
```

### 2. OpenAI API 키 오류

**증상**: "OpenAI API 키가 설정되지 않았습니다"

**해결**:
```bash
# API 키 확인
echo $OPENAI_API_KEY

# 설정 (임시)
export OPENAI_API_KEY="your_key_here"

# 영구 설정 (bash)
echo 'export OPENAI_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc

# 영구 설정 (zsh)
echo 'export OPENAI_API_KEY="your_key_here"' >> ~/.zshrc
source ~/.zshrc
```

### 3. 포트 충돌

**증상**: "Port 8501 is already in use"

**해결**:
```bash
# 다른 포트 사용
python3 -m streamlit run main.py --server.port 8502

# 또는 기존 프로세스 종료
lsof -ti:8501 | xargs kill -9
```

### 4. 데이터 파일 없음

**증상**: "❌ 감사보고서 데이터 없음"

**해결**:
- 원본 `audit`, `extra`, `graph` 폴더가 올바른 위치에 있는지 확인
- 상대 경로 `../audit/storage`, `../extra`, `../graph/data` 확인

### 5. 메모리 부족

**증상**: 시스템이 느리거나 중단됨

**해결**:
- 최소 8GB RAM 권장
- 다른 프로그램 종료
- 가상 메모리 증가

## 📊 시스템 상태 확인

```bash
# Python 환경
python3 -c "import sys; print('Python:', sys.version)"

# 주요 패키지
python3 -c "import streamlit; print('Streamlit:', streamlit.__version__)"
python3 -c "import qdrant_client; print('Qdrant:', qdrant_client.__version__)"
python3 -c "import sentence_transformers; print('SentenceTransformers:', sentence_transformers.__version__)"

# OpenAI API 키
python3 -c "import os; print('API Key:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')"

# 데이터 디렉토리
ls -la ../audit/storage 2>/dev/null && echo "✅ Audit data" || echo "❌ Audit data"
ls -la ../extra 2>/dev/null && echo "✅ Extra data" || echo "❌ Extra data" 
ls -la ../graph/data 2>/dev/null && echo "✅ Graph data" || echo "❌ Graph data"
```

## 🎯 성능 최적화

### GPU 가속 (선택사항)

```bash
# CUDA 지원 PyTorch (NVIDIA GPU)
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# MPS 지원 확인 (Apple Silicon Mac)
python3 -c "import torch; print('MPS available:', torch.backends.mps.is_available())"
```

### 메모리 최적화

```bash
# 환경변수 설정
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0  # Apple Silicon
export CUDA_VISIBLE_DEVICES=0                # NVIDIA GPU
```

## 📞 지원

문제가 지속되면 다음 정보와 함께 문의하세요:

1. 운영체제 및 버전
2. Python 버전
3. 오류 메시지 전문
4. 설치 로그

```bash
# 시스템 정보 수집
python3 -c "
import sys, platform, streamlit
print(f'OS: {platform.system()} {platform.release()}')
print(f'Python: {sys.version}')
print(f'Streamlit: {streamlit.__version__}')
"
```
