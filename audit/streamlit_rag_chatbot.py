#!/usr/bin/env python3
"""
Streamlit을 사용한 RAG QA 웹 인터페이스
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Dict, Any

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.append(str(project_root / "scripts"))

from hierarchy_rag_qa_system import HierarchyRAGQASystem

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_openai_api_key() -> str:
    """OpenAI API 키 로드"""
    # 환경변수에서 API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # .env 파일에서 API 키 확인
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key
    except ImportError:
        pass
    
    return None

def initialize_rag_system() -> HierarchyRAGQASystem:
    """계층관계 RAG 시스템 초기화"""
    if 'rag_system' not in st.session_state:
        api_key = load_openai_api_key()
        if not api_key:
            st.error("OpenAI API 키가 설정되지 않았습니다. 환경변수 OPENAI_API_KEY를 설정하거나 .env 파일에 추가하세요.")
            st.stop()
        
        try:
            with st.spinner("계층관계 RAG QA 시스템을 초기화하는 중..."):
                rag_system = HierarchyRAGQASystem(openai_api_key=api_key)
                st.session_state.rag_system = rag_system
                st.success("계층관계 RAG QA 시스템 초기화 완료!")
        except Exception as e:
            st.error(f"RAG 시스템 초기화 실패: {e}")
            st.stop()
    
    return st.session_state.rag_system

def display_chat_message(role: str, content: str, relevant_chunks: list = None):
    """채팅 메시지 표시"""
    with st.chat_message(role):
        st.markdown(content)
        
        if relevant_chunks and role == "assistant":
            with st.expander("참조된 문서 정보"):
                for i, chunk in enumerate(relevant_chunks[:3], 1):
                    st.markdown(f"**청크 {i}** (유사도: {chunk['score']:.3f})")
                    st.markdown(f"- 내용: {chunk['text'][:200]}...")
                    
                    metadata = chunk.get('metadata', {})
                    if metadata:
                        metadata_info = []
                        if metadata.get('company'):
                            metadata_info.append(f"회사: {metadata['company']}")
                        if metadata.get('report_year'):
                            metadata_info.append(f"연도: {metadata['report_year']}")
                        if metadata.get('account_name'):
                            metadata_info.append(f"계정: {metadata['account_name']}")
                        if metadata.get('value'):
                            metadata_info.append(f"금액: {metadata['value']:,}백만원")
                        
                        if metadata_info:
                            st.markdown(f"- 메타데이터: {', '.join(metadata_info)}")
                    st.markdown("---")

def main():
    """메인 Streamlit 앱"""
    st.set_page_config(
        page_title="삼성전자 감사보고서 RAG QA",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 커스텀 CSS
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #1f4e79 0%, #2e7d32 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2e7d32;
        margin: 0.5rem 0;
    }
    .chunk-card {
        background: #e8f5e8;
        padding: 0.8rem;
        border-radius: 6px;
        margin: 0.5rem 0;
        border-left: 3px solid #4caf50;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 헤더
    st.markdown("""
    <div class="main-header">
        <h1>📊 삼성전자 감사보고서 계층관계 RAG QA 시스템</h1>
        <p>GPT-4 기반 지능형 재무 데이터 분석 플랫폼 (상하위 계층관계 지원)</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 검색 설정")
        
        # 검색 파라미터
        top_k = st.slider("검색할 청크 수", min_value=3, max_value=10, value=5)
        score_threshold = st.slider("유사도 임계값", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
        
        st.markdown("---")
        
        # 샘플 질문들
        st.header("💡 샘플 질문")
        sample_questions = [
            "유동자산에 대해 알려주세요",
            "현금및현금성자산은 얼마인가요?",
            "2024년 재무상태표 상 당기 유동자산은 얼마인가?",
            "2019년 재무상태표상 종속기업, 관계기업 및 공동기업 투자는 얼마인가요?",
            "2024년 손익계산서상 당기 법인세비용은 얼마야?",
            "2023년의 법인세비용(수익)은 얼마야?",
            "2021년 재무상태표에서 당기 유동비율을 계산하면 얼마인가요?"
        ]
        
        for i, question in enumerate(sample_questions, 1):
            if st.button(f"{i}. {question[:30]}...", key=f"sample_{i}"):
                st.session_state.sample_question = question
                st.rerun()
        
        st.markdown("---")
        
        # 시스템 정보
        st.header("ℹ️ 시스템 정보")
        st.markdown("""
        <div class="metric-card">
        <strong>🤖 AI 모델</strong><br>
        • 임베딩: BGE-M3-KO<br>
        • LLM: ChatGPT-4<br>
        • 벡터DB: Qdrant
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="metric-card">
        <strong>📊 데이터 범위</strong><br>
        • 회사: 삼성전자<br>
        • 기간: 2014-2024년<br>
        • 문서: 감사보고서
        </div>
        """, unsafe_allow_html=True)
        
        # 초기화 버튼
        if st.button("🔄 시스템 재초기화", type="secondary"):
            if 'rag_system' in st.session_state:
                del st.session_state.rag_system
            st.rerun()
    
    # RAG 시스템 초기화
    rag_system = initialize_rag_system()
    
    # 채팅 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 환영 메시지
    if not st.session_state.messages:
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "안녕하세요! 삼성전자 감사보고서에 대해 궁금한 것이 있으시면 언제든 질문해주세요.\n\n**계층관계 지원**: 상하위 계층관계가 있는 과목들을 함께 답변으로 제공합니다!\n\n예를 들어:\n- 유동자산에 대해 알려주세요 (하위 항목들도 함께 표시)\n- 현금및현금성자산은 얼마인가요?\n- 2017년 삼성전자의 유동자산은 얼마인가요?\n- 2020년 매출채권의 변화는 어떻게 되나요?\n- 최근 3년간 현금흐름은 어떤 추세인가요?"
        })
    
    # 채팅 기록 표시
    for message in st.session_state.messages:
        display_chat_message(
            message["role"], 
            message["content"],
            message.get("relevant_chunks")
        )
    
    # 샘플 질문 처리
    if hasattr(st.session_state, 'sample_question'):
        prompt = st.session_state.sample_question
        del st.session_state.sample_question
    else:
        prompt = st.chat_input("질문을 입력하세요...")
    
    if prompt:
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": prompt})
        display_chat_message("user", prompt)
        
        # 답변 생성
        with st.chat_message("assistant"):
            with st.spinner("답변을 생성하는 중..."):
                try:
                    result = rag_system.ask_question(
                        prompt, 
                        top_k=top_k, 
                        score_threshold=score_threshold
                    )
                    
                    # 답변 표시
                    st.markdown(result["answer"])
                    
                    # 계층관계 정보 표시
                    if result.get("hierarchy_info"):
                        with st.expander("🏗️ 계층관계 정보", expanded=False):
                            st.markdown(result["hierarchy_info"])
                    
                    # 관련 청크 표시
                    if result["relevant_chunks"]:
                        with st.expander(f"📚 참조된 문서 정보 ({len(result['relevant_chunks'])}개)", expanded=False):
                            for i, chunk in enumerate(result["relevant_chunks"], 1):
                                # 유사도에 따른 색상 결정
                                score = chunk['score']
                                if score >= 0.8:
                                    color = "#4caf50"  # 녹색
                                elif score >= 0.7:
                                    color = "#ff9800"  # 주황색
                                else:
                                    color = "#f44336"  # 빨간색
                                
                                st.markdown(f"""
                                <div class="chunk-card">
                                    <strong>📄 청크 {i}</strong> 
                                    <span style="color: {color}; font-weight: bold;">(유사도: {score:.3f})</span><br>
                                    <em>{chunk['text'][:150]}...</em>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                metadata = chunk.get('metadata', {})
                                if metadata:
                                    metadata_info = []
                                    if metadata.get('doc_id'):
                                        metadata_info.append(f"📋 문서: {metadata['doc_id']}")
                                    if metadata.get('content_type'):
                                        metadata_info.append(f"📊 유형: {metadata['content_type']}")
                                    
                                    if metadata_info:
                                        st.markdown(f"<small>{' | '.join(metadata_info)}</small>", unsafe_allow_html=True)
                                st.markdown("")
                    
                    # 어시스턴트 메시지 추가
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": result["answer"],
                        "relevant_chunks": result["relevant_chunks"],
                        "hierarchy_info": result.get("hierarchy_info", "")
                    })
                    
                except Exception as e:
                    error_msg = f"답변 생성 중 오류가 발생했습니다: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": error_msg
                    })
    
    # 하단 정보
    st.markdown("---")
    
    # 통계 정보
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💬 총 대화 수", len(st.session_state.messages))
    
    with col2:
        st.metric("🔍 검색 청크 수", top_k)
    
    with col3:
        st.metric("📊 유사도 임계값", f"{score_threshold:.1f}")
    
    with col4:
        st.metric("📅 데이터 기간", "2014-2024")
    
    # 팁과 가이드
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### 💡 질문 팁
        - **계층관계 활용**: "유동자산에 대해 알려주세요" (하위 항목들도 함께 표시)
        - **구체적인 질문**: "2023년 유동자산" vs "자산"
        - **연도 명시**: "2019년 손익계산서상..."
        - **정확한 항목명**: "법인세비용", "매출채권" 등
        """)
    
    with col2:
        st.markdown("""
        ### 🔍 검색 최적화
        - **높은 유사도**: 더 정확한 답변
        - **더 많은 청크**: 더 풍부한 컨텍스트
        - **샘플 질문**: 빠른 시작을 위해 활용
        """)

if __name__ == "__main__":
    main()
