#!/usr/bin/env python3
"""
계층관계 RAG 시스템 시연용 Streamlit 앱
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Dict, Any
import time
import json

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
        except Exception as e:
            st.error(f"RAG 시스템 초기화 실패: {e}")
            st.stop()
    
    return st.session_state.rag_system

def display_hierarchy_info(hierarchy_info: str):
    """계층관계 정보를 시각적으로 표시 - 숨김 처리"""
    # 계층관계 정보 표시를 비활성화
    return

def display_chunk_info(chunks: list):
    """청크 정보를 시각적으로 표시 - 숨김 처리"""
    # 청크 정보 표시를 비활성화
    return

def main():
    """메인 Streamlit 앱"""
    st.set_page_config(
        page_title="계층관계 RAG QA 시스템",
        page_icon="📝",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 커스텀 CSS
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #26a69a 0%, #9c27b0 100%);
        min-height: 100vh;
    }
    .main-header {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        color: black;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border: 2px solid #1a237e;
    }
    .demo-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #26a69a;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    .hierarchy-card {
        background: #e8f5e8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #26a69a;
        margin: 0.5rem 0;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    .stButton > button {
        background: linear-gradient(90deg, #26a69a 0%, #9c27b0 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    /* 답변 박스 스타일 */
    .answer-box {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    /* 질문 입력창 스타일 */
    .stChatInput > div > div {
        background: white !important;
        border: 2px solid #26a69a !important;
        border-radius: 15px !important;
        box-shadow: 0 4px 8px rgba(38, 166, 154, 0.2) !important;
    }
    
    .stChatInput > div > div > div > input {
        background: white !important;
        border: none !important;
        font-size: 1.1rem !important;
        padding: 1rem !important;
    }
    
    .stChatInput > div > div > div > input::placeholder {
        color: #26a69a !important;
        font-weight: 500 !important;
    }
    
    /* 홈 버튼 스타일 */
    .stButton > button[kind="secondary"] {
        background: linear-gradient(135deg, #26a69a, #1e8a7a) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.5rem 1rem !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 8px rgba(38, 166, 154, 0.3) !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
    }
    
    .stButton > button[kind="secondary"]:hover {
        background: linear-gradient(135deg, #1e8a7a, #26a69a) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(38, 166, 154, 0.4) !important;
    }
    
    /* 모바일 친화적 스타일 */
    @media (max-width: 768px) {
        .main-header {
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .main-header h1 {
            font-size: 1.5rem;
        }
        .main-header h3 {
            font-size: 1.2rem;
        }
        .demo-card, .hierarchy-card, .metric-card {
            padding: 1rem;
            margin: 0.5rem 0;
        }
        .stButton > button {
            font-size: 0.9rem;
            padding: 0.4rem 0.8rem;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 헤더
    # 메인 헤더
    st.markdown("""
    <div class="main-header">
        <h1 style="color: #1a237e;">📝 계층관계 RAG QA 시스템</h1>
        <h3 style="color: black;">삼성전자 감사보고서 지능형 분석 플랫폼</h3>
        <p style="color: black;">상하위 계층관계가 있는 과목들을 함께 답변으로 제공하는 혁신적인 RAG 시스템</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 사이드바
    with st.sidebar:
        # 홈 버튼
        if st.button("🏠 홈으로 가기", help="홈으로 가기", key="home_button", use_container_width=True):
            # 채팅 기록 초기화
            st.session_state.messages = []
            st.rerun()
        
        st.markdown("---")
        
        # 시스템 정보
        st.subheader("ℹ️ 시스템 정보")
        st.markdown("""
        <div class="demo-card">
        <strong>🤖 AI 모델</strong><br>
        • 임베딩: BGE-M3-KO<br>
        • LLM: ChatGPT-4<br>
        • 벡터DB: Qdrant
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="demo-card">
        <strong>📊 데이터 범위</strong><br>
        • 회사: 삼성전자<br>
        • 기간: 2014-2024년<br>
        • 문서: 감사보고서<br>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 시스템 설정
        st.header("⚙️ 시스템 설정")
        
        # 검색 파라미터
        with st.expander("🔍 검색 설정", expanded=False):
            top_k = st.slider("검색할 청크 수", min_value=3, max_value=30, value=25, help="더 많은 청크를 검색하면 더 풍부한 답변을 얻을 수 있습니다.")
            score_threshold = st.slider("유사도 임계값", min_value=0.0, max_value=1.0, value=0.3, step=0.1, help="높은 임계값은 더 정확한 결과를, 낮은 임계값은 더 많은 결과를 제공합니다.")
        
        st.markdown("---")
        
        # 초기화 버튼
        if st.button("🔄 시스템 재초기화", type="secondary", use_container_width=True):
            if 'rag_system' in st.session_state:
                del st.session_state.rag_system
            st.rerun()
    
    # RAG 시스템 초기화
    rag_system = initialize_rag_system()
    
    # 1. 질문하기 섹션
    
    # 채팅 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 채팅 기록 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                # 답변을 흰색 박스 안에 표시
                st.markdown(f"""
                <div class="answer-box">
                {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(message["content"])
            
            if message.get("hierarchy_info") and message["role"] == "assistant":
                display_hierarchy_info(message["hierarchy_info"])
            
            if message.get("relevant_chunks") and message["role"] == "assistant":
                display_chunk_info(message["relevant_chunks"])
    
    # 질문 입력창을 질문하기와 샘플질문 사이에 배치
    if hasattr(st.session_state, 'demo_question'):
        prompt = st.session_state.demo_question
        del st.session_state.demo_question
    else:
        prompt = None
    
    # 항상 질문 입력창 표시
    user_input = st.chat_input("질문을 입력하세요... (예: 2014년의 장기선급비용이 궁금해요)", key="main_input")
    
    # 샘플 질문 또는 사용자 입력 처리
    if prompt:
        final_prompt = prompt
    elif user_input:
        final_prompt = user_input
    else:
        final_prompt = None
    
    if final_prompt:
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": final_prompt})
        with st.chat_message("user"):
            st.markdown(final_prompt)
        
        # 답변 생성
        with st.chat_message("assistant"):
            with st.spinner("🤖 계층관계를 분석하고 답변을 생성하는 중..."):
                try:
                    start_time = time.time()
                    result = rag_system.ask_question(
                        final_prompt, 
                        top_k=top_k, 
                        score_threshold=score_threshold
                    )
                    end_time = time.time()
                    
                    # 답변을 흰색 박스 안에 표시
                    st.markdown(f"""
                    <div class="answer-box">
                    {result["answer"]}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 계층관계 정보 표시
                    if result.get("hierarchy_info"):
                        display_hierarchy_info(result["hierarchy_info"])
                    
                    # 청크 정보 표시
                    if result["relevant_chunks"]:
                        display_chunk_info(result["relevant_chunks"])
                    
                    # 처리 시간 표시 제거
                    processing_time = end_time - start_time
                    
                    # 어시스턴트 메시지 추가
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": result["answer"],
                        "relevant_chunks": result["relevant_chunks"],
                        "hierarchy_info": result.get("hierarchy_info", ""),
                        "processing_time": processing_time
                    })
                    
                except Exception as e:
                    error_msg = f"답변 생성 중 오류가 발생했습니다: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": error_msg
                    })
    
    st.markdown("---")
    
    # 2. 샘플 질문 (3개만 한 줄로)
    st.markdown("### 🎯 샘플 질문")
    
    # 선택된 3개 샘플 질문
    demo_questions = [
        ("🏢 종속기업투자", "2019년 재무상태표상 종속기업,관계기업 및 공동기업 투자는 얼마인가요?"),
        ("💰 법인세비용", "2024년 손익계산서상 당기 법인세비용은 얼마야?"),
        ("📈 추이 분석", "2020년부터 2024년까지 영업이익(손실) 추이를 알려주세요")
    ]
    
    # 한 줄로 배치
    cols = st.columns(3)
    for i, (title, question) in enumerate(demo_questions):
        with cols[i]:
            if st.button(f"{title}", key=f"demo_{question}", help=question, use_container_width=True):
                st.session_state.demo_question = question
                st.rerun()
    
    st.markdown("---")
    
    # 3. 사용 가이드 (2개의 별도 박스)
    st.markdown("### 📖 사용 가이드")
    
    # 2열로 배치
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="answer-box">
        <h4>💡 계층관계 기능 활용</h4>
        <ul>
            <li><strong>기본 계층관계</strong>: "2019년 현금흐름표 상 이익잉여금 배당은 얼마인가요?"</li>
            <li><strong>구체적 금액</strong>: "현금및현금성자산은 얼마인가요?"</li>
            <li><strong>연도별 비교</strong>: "2024년의 유동자산에 대해 알려주고 각각 얼마인지도 알려줘"</li>
            <li><strong>상세 분석</strong>: "2024년의 비유동자산에 대해 알려주고 각 하위항목의 값도 알려줘"</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="answer-box">
        <h4>🔍 RAG 시스템 특징</h4>
        <ul>
            <li><strong>계층관계 인식</strong>: 상하위 관계 자동 인식</li>
            <li><strong>포괄적 답변</strong>: 관련 항목들 함께 제공</li>
            <li><strong>투명성</strong>: 청크 참조 및 근거 제시</li>
            <li><strong>정확성</strong>: 제공된 데이터만 사용</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 4. 시스템 상태 (간결한 박스)
    st.markdown("### 📊 시스템 상태")
    
    # 간결한 시스템 정보 박스
    st.markdown(f"""
    <div class="answer-box">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 2rem;">
        <div style="flex: 1; text-align: center;">
            <h4 style="margin: 0; color: #26a69a;">🔍 유사도 임계값</h4>
            <p style="margin: 0.5rem 0; font-size: 1.2rem; font-weight: bold;">{score_threshold}</p>
        </div>
        <div style="flex: 1; text-align: center;">
            <h4 style="margin: 0; color: #9c27b0;">📅 데이터 기간</h4>
            <p style="margin: 0.5rem 0; font-size: 1.2rem; font-weight: bold;">2014-2024</p>
        </div>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 하단 정보
    st.markdown("---")

    
    

if __name__ == "__main__":
    main()
