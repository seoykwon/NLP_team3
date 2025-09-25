#!/bin/bash

# 통합 RAG 시스템 실행 스크립트

echo "🔗 통합 RAG 시스템 시작"
echo "================================"

# 현재 디렉토리 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📁 작업 디렉토리: $SCRIPT_DIR"

# Python 경로 설정
export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}"
export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}/../audit/scripts"
export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}/../extra/스트림릿"
export PYTHONPATH="${PYTHONPATH}:${SCRIPT_DIR}/../graph/code"

echo "🐍 Python 경로 설정 완료"

# OpenAI API 키 확인
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OpenAI API 키가 설정되지 않았습니다."
    echo "   환경변수 OPENAI_API_KEY를 설정하거나 .env 파일을 만들어주세요."
    echo ""
    echo "   예시:"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
else
    echo "✅ OpenAI API 키 확인됨"
fi

# 의존성 확인
echo "📦 의존성 확인 중..."
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "❌ Streamlit이 설치되지 않았습니다."
    echo "   pip3 install -r requirements.txt 를 실행해주세요."
    exit 1
fi

if ! python3 -c "import qdrant_client" 2>/dev/null; then
    echo "❌ Qdrant 클라이언트가 설치되지 않았습니다."
    echo "   pip3 install -r requirements.txt 를 실행해주세요."
    exit 1
fi

echo "✅ 필수 의존성 확인 완료"

# 데이터 디렉토리 확인
echo "📊 데이터 디렉토리 확인 중..."

AUDIT_DATA="${SCRIPT_DIR}/../audit/storage"
EXTRA_DATA="${SCRIPT_DIR}/../extra"
GRAPH_DATA="${SCRIPT_DIR}/../graph/data"

if [ -d "$AUDIT_DATA" ]; then
    echo "✅ 감사보고서 데이터: $AUDIT_DATA"
else
    echo "⚠️  감사보고서 데이터 없음: $AUDIT_DATA"
fi

if [ -d "$EXTRA_DATA" ]; then
    echo "✅ 법률 문서 데이터: $EXTRA_DATA"
else
    echo "⚠️  법률 문서 데이터 없음: $EXTRA_DATA"
fi

if [ -d "$GRAPH_DATA" ]; then
    echo "✅ 그래프 분석 데이터: $GRAPH_DATA"
else
    echo "⚠️  그래프 분석 데이터 없음: $GRAPH_DATA"
fi

echo ""
echo "🚀 통합 RAG 시스템을 시작합니다..."
echo "   브라우저에서 http://localhost:8501 에 접속하세요"
echo ""

# Streamlit 앱 실행
cd "$SCRIPT_DIR"
python3 -m streamlit run main.py --server.port 8501 --server.address localhost
