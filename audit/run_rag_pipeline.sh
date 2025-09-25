#!/bin/bash

# RAG 파이프라인 실행 스크립트
# 1. BGE-M3-KO 임베딩 생성
# 2. Qdrant 벡터DB 구축
# 3. RAG QA 시스템 실행

set -e  # 오류 발생 시 스크립트 중단

echo "🚀 RAG 파이프라인 시작"
echo "================================"

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")"

# 1. 임베딩 생성
echo "📝 1단계: BGE-M3-KO 임베딩 생성"
echo "================================"
python scripts/embed_with_bge_m3_ko.py

if [ $? -eq 0 ]; then
    echo "✅ 임베딩 생성 완료"
else
    echo "❌ 임베딩 생성 실패"
    exit 1
fi

echo ""

# 2. Qdrant 벡터DB 구축
echo "🗄️ 2단계: Qdrant 벡터DB 구축"
echo "================================"
python scripts/build_qdrant_vector_db.py

if [ $? -eq 0 ]; then
    echo "✅ Qdrant 벡터DB 구축 완료"
else
    echo "❌ Qdrant 벡터DB 구축 실패"
    exit 1
fi

echo ""

# 3. RAG QA 시스템 실행 옵션
echo "🤖 3단계: RAG QA 시스템 실행"
echo "================================"
echo "실행 방법을 선택하세요:"
echo "1) 콘솔 기반 QA 시스템"
echo "2) Streamlit 웹 인터페이스"
echo "3) 종료"
echo ""

read -p "선택 (1-3): " choice

case $choice in
    1)
        echo "콘솔 기반 QA 시스템을 시작합니다..."
        python scripts/rag_qa_system.py
        ;;
    2)
        echo "Streamlit 웹 인터페이스를 시작합니다..."
        echo "브라우저에서 http://localhost:8501 을 열어주세요."
        streamlit run streamlit_rag_chatbot.py
        ;;
    3)
        echo "파이프라인을 종료합니다."
        ;;
    *)
        echo "잘못된 선택입니다. 파이프라인을 종료합니다."
        ;;
esac

echo ""
echo "🎉 RAG 파이프라인 완료!"
