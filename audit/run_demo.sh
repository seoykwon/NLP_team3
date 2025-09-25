#!/bin/bash

# 계층관계 RAG 시스템 시연용 실행 스크립트

echo "🏗️ 계층관계 RAG QA 시스템 시연을 시작합니다..."
echo "================================================"

# OpenAI API 키 확인
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다."
    echo "다음 명령어로 API 키를 설정해주세요:"
    echo "export OPENAI_API_KEY='your_api_key_here'"
    exit 1
fi

echo "✅ OpenAI API 키가 설정되었습니다."

# Python 의존성 확인
echo "📦 Python 의존성을 확인하는 중..."
python -c "import streamlit, openai, qdrant_client, sentence_transformers" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 필요한 Python 패키지가 설치되지 않았습니다."
    echo "다음 명령어로 설치해주세요:"
    echo "pip install -r requirements.txt"
    exit 1
fi

echo "✅ 모든 의존성이 설치되었습니다."

# Qdrant 서버 확인
echo "🔍 Qdrant 서버 상태를 확인하는 중..."
python -c "from qdrant_client import QdrantClient; QdrantClient(host='localhost', port=6333).get_collections()" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Qdrant 서버가 실행되지 않았습니다."
    echo "다음 명령어로 Qdrant를 시작해주세요:"
    echo "./qdrant"
    echo "또는"
    echo "python scripts/build_qdrant_vector_db.py"
    exit 1
fi

echo "✅ Qdrant 서버가 정상적으로 실행 중입니다."

# Streamlit 앱 실행
echo "🚀 Streamlit 시연 앱을 시작합니다..."
echo "브라우저에서 http://localhost:8501 을 열어주세요."
echo "================================================"

streamlit run demo_streamlit_app.py --server.port 8501 --server.address localhost
