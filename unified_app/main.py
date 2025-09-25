#!/usr/bin/env python3
"""
통합 RAG 시스템 - 메인 Streamlit 앱
audit, extra, graph 폴더의 모든 기능을 통합한 웹 인터페이스
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Dict, Any, Optional
import time

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "audit" / "scripts"))
sys.path.append(str(project_root / "extra" / "스트림릿"))
sys.path.append(str(project_root / "graph" / "code"))

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
    page_title="통합 RAG 시스템",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일
st.markdown("""
<style>
    /* 전체 앱 배경 및 텍스트 색상 - 애니메이션 배경 */
    .stApp {
        background: linear-gradient(135deg, #f8f5ff 0%, #ffe8f7 30%, #f0e6ff 60%, #ffffff 100%);
        background-size: 400% 400%;
        animation: gradientShift 10s ease infinite;
        color: #000000 !important;
    }
    
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    /* 모든 텍스트 요소들 검정색으로 */
    h1, h2, h3, h4, h5, h6, p, span, div, li, td, th, label {
        color: #000000 !important;
    }
    
    /* Streamlit 기본 텍스트 색상 오버라이드 */
    .css-1d391kg, .css-1v0mbdj, .css-16huue1, .css-1cpxqw2 {
        color: #000000 !important;
    }
    
    /* 메인 헤더 - 글로우 효과와 애니메이션 */
    .main-header {
        background: linear-gradient(135deg, #9c27b0 0%, #e91e63 30%, #f48fb1 70%, #f8bbd9 100%);
        background-size: 300% 300%;
        animation: headerGlow 8s ease-in-out infinite;
        padding: 2.5rem;
        border-radius: 25px;
        color: white !important;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 10px 40px rgba(156, 39, 176, 0.4), 
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
        border: 2px solid rgba(255, 255, 255, 0.3);
        backdrop-filter: blur(15px);
        position: relative;
        overflow: hidden;
    }
    
    .main-header::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(45deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        animation: shimmer 3s infinite;
        pointer-events: none;
    }
    
    @keyframes headerGlow {
        0%, 100% { 
            background-position: 0% 50%;
            box-shadow: 0 10px 40px rgba(156, 39, 176, 0.4), 
                        inset 0 1px 0 rgba(255, 255, 255, 0.3);
        }
        50% { 
            background-position: 100% 50%;
            box-shadow: 0 15px 50px rgba(233, 30, 99, 0.5), 
                        inset 0 1px 0 rgba(255, 255, 255, 0.4);
        }
    }
    
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    
    .main-header h1, .main-header h3, .main-header p {
        color: white !important;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    /* 시스템 카드 */
    .system-card {
        background: linear-gradient(135deg, #ffffff 0%, #fdf2f8 100%);
        padding: 1.8rem;
        border-radius: 15px;
        border-left: 6px solid #e91e63;
        border-top: 2px solid #f8bbd9;
        margin: 1rem 0;
        box-shadow: 0 4px 20px rgba(156, 39, 176, 0.15);
        transition: all 0.3s ease;
        color: #000000 !important;
        backdrop-filter: blur(5px);
        position: relative;
        overflow: hidden;
    }
    
    .system-card h3, .system-card h4, .system-card p, .system-card li {
        color: #000000 !important;
    }
    
    .system-card:hover {
        transform: translateY(-8px) scale(1.03);
        box-shadow: 0 15px 40px rgba(156, 39, 176, 0.3),
                    0 5px 15px rgba(233, 30, 99, 0.2);
        border-left-color: #9c27b0;
        background: linear-gradient(135deg, #ffffff 0%, #f8f5ff 100%);
    }
    
    .system-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, transparent, rgba(233, 30, 99, 0.05), transparent);
        opacity: 0;
        transition: opacity 0.3s ease;
        pointer-events: none;
        border-radius: 15px;
    }
    
    .system-card:hover::before {
        opacity: 1;
    }
    
    /* 기능 리스트 */
    .feature-list {
        list-style-type: none;
        padding: 0;
    }
    .feature-list li {
        padding: 0.6rem 0;
        border-bottom: 1px solid rgba(233, 30, 99, 0.2);
        color: #000000 !important;
    }
    .feature-list li:before {
        content: "✨ ";
        color: #e91e63;
        font-weight: bold;
        text-shadow: 1px 1px 2px rgba(233, 30, 99, 0.3);
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        background: linear-gradient(90deg, #9c27b0 0%, #e91e63 50%, #f8bbd9 100%);
        color: white !important;
        border: none;
        border-radius: 12px;
        padding: 0.7rem 1.2rem;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
        box-shadow: 0 4px 15px rgba(156, 39, 176, 0.3);
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
    }
    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(156, 39, 176, 0.4);
        background: linear-gradient(90deg, #8e24aa 0%, #d81b60 50%, #f48fb1 100%);
    }
    
    /* 사이드바 스타일 */
    .css-1d391kg {
        color: #000000 !important;
        background: linear-gradient(180deg, #f8f5ff 0%, #ffffff 100%);
    }
    
    /* 사이드바 배경 */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f5ff 0%, #fdf2f8 100%);
        border-right: 2px solid rgba(233, 30, 99, 0.2);
    }
    
    /* 메트릭 카드 */
    .css-1xarl3l {
        color: #000000 !important;
        background: rgba(248, 245, 255, 0.8);
        border-radius: 10px;
        padding: 1rem;
        border: 1px solid rgba(156, 39, 176, 0.2);
    }
    
    /* 입력창 스타일 */
    .stTextInput > div > div > input {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9);
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #e91e63;
        box-shadow: 0 0 10px rgba(233, 30, 99, 0.3);
    }
    
    /* 텍스트 에어리어 */
    .stTextArea > div > div > textarea {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9);
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #e91e63;
        box-shadow: 0 0 10px rgba(233, 30, 99, 0.3);
    }
    
    /* 셀렉트박스 */
    .stSelectbox > div > div > select {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9);
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    /* 체크박스 */
    .stCheckbox > label {
        color: #000000 !important;
    }
    
    .stCheckbox input[type="checkbox"]:checked {
        background-color: #e91e63;
        border-color: #e91e63;
    }
    
    /* 라디오 버튼 */
    .stRadio > label {
        color: #000000 !important;
    }
    
    /* 슬라이더 */
    .stSlider > label {
        color: #000000 !important;
    }
    
    /* 데이터프레임 */
    .dataframe {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.95);
        border-radius: 8px;
    }
    
    /* 채팅 메시지 */
    .stChatMessage {
        color: #000000 !important;
        background: rgba(248, 245, 255, 0.8);
        border: 1px solid rgba(233, 30, 99, 0.2);
        border-radius: 12px;
    }
    
    /* 답변 박스 */
    .answer-box, .answer-box * {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.95);
        border: 2px solid rgba(156, 39, 176, 0.2);
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(156, 39, 176, 0.1);
    }
    
    /* 알림 메시지 */
    .stSuccess {
        color: #000000 !important;
        background: linear-gradient(135deg, #e8f5e8 0%, #f0fff0 100%);
        border-left: 4px solid #4caf50;
    }
    
    .stError {
        color: #000000 !important;
        background: linear-gradient(135deg, #ffeaea 0%, #fff0f0 100%);
        border-left: 4px solid #f44336;
    }
    
    .stInfo {
        color: #000000 !important;
        background: linear-gradient(135deg, #e3f2fd 0%, #f0f8ff 100%);
        border-left: 4px solid #2196f3;
    }
    
    .stWarning {
        color: #000000 !important;
        background: linear-gradient(135deg, #fff8e1 0%, #fffef7 100%);
        border-left: 4px solid #ff9800;
    }
    
    /* 확장 가능한 섹션 */
    .streamlit-expanderHeader {
        color: #000000 !important;
        background: linear-gradient(135deg, #f8f5ff 0%, #fdf2f8 100%);
        border: 1px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    /* 마크다운 */
    .stMarkdown {
        color: #000000 !important;
    }
    
    /* 네비게이션 버튼 */
    .nav-button {
        margin: 0.5rem 0;
    }
    
    /* 스피너 */
    .stSpinner > div {
        border-color: #e91e63 transparent transparent transparent;
    }
    
    /* 프로그래스 바 */
    .stProgress > div > div {
        background-color: #e91e63;
    }
</style>
""", unsafe_allow_html=True)

def load_openai_api_key() -> Optional[str]:
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

def show_home_page():
    """홈페이지 표시"""
    # 메인 헤더
    st.markdown("""
    <div class="main-header">
        <h1>🔗 통합 RAG 시스템</h1>
        <h3>삼성전자 감사보고서 & 법률 문서 지능형 분석 플랫폼</h3>
        <p>세 가지 강력한 RAG 시스템을 하나의 플랫폼에서 경험하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 시스템 소개
    st.markdown("## 🎯 시스템 개요")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="system-card">
            <h3>📊 감사보고서 RAG</h3>
            <p><strong>삼성전자 감사보고서 (2014-2024)</strong></p>
            <ul class="feature-list">
                <li>계층관계 인식 검색</li>
                <li>BGE-M3-KO 임베딩</li>
                <li>Qdrant 벡터 DB</li>
                <li>GPT-4 답변 생성</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="system-card">
            <h3>⚖️ 법률 문서 RAG</h3>
            <p><strong>상법 & K-IFRS 기준서</strong></p>
            <ul class="feature-list">
                <li>상법 조문 검색</li>
                <li>K-IFRS 회계기준</li>
                <li>하이브리드 검색</li>
                <li>전문가 수준 답변</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="system-card">
            <h3>🕸️ 그래프 분석</h3>
            <p><strong>고급 문서 구조 분석</strong></p>
            <ul class="feature-list">
                <li>그래프 기반 검색</li>
                <li>관계 네트워크 분석</li>
                <li>LLaMA 모델 지원</li>
                <li>시각적 데이터 분석</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 빠른 시작
    st.markdown("## 🚀 빠른 시작")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 💡 추천 질문 예시")
        
        # 감사보고서 예시
        st.markdown("**📊 감사보고서 RAG**")
        example_questions_audit = [
            "2024년 유동자산에 대해 알려주고 각각 얼마인지도 알려줘",
            "2019년 재무상태표상 종속기업투자는 얼마인가요?",
            "2020년부터 2024년까지 영업이익 추이를 알려주세요"
        ]
        
        for q in example_questions_audit:
            st.markdown(f"- {q}")
        
        st.markdown("")
        
        # 법률 문서 예시
        st.markdown("**⚖️ 법률 문서 RAG**")
        example_questions_legal = [
            "준비금의 자본전입은 이사회에서 결정할 수 있는가?",
            "개발비 자산 인식 요건은 무엇인가요?",
            "상법상 이사의 의무는 무엇인가요?"
        ]
        
        for q in example_questions_legal:
            st.markdown(f"- {q}")
    
    with col2:
        st.markdown("### 🔧 시스템 상태")
        
        # API 키 상태 확인
        api_key = load_openai_api_key()
        if api_key:
            st.success("✅ OpenAI API 키 설정 완료")
        else:
            st.warning("⚠️ OpenAI API 키가 설정되지 않음")
            st.info("환경변수 OPENAI_API_KEY를 설정하거나 .env 파일에 추가하세요")
        
        # 시스템 상태 확인
        try:
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent / "modules"))
            from utils import get_system_status
            status = get_system_status()
            
            st.markdown("**📁 데이터 경로 상태**")
            
            if status["data_paths"]["audit_data"]:
                st.success("✅ 감사보고서 데이터")
            else:
                st.error("❌ 감사보고서 데이터 없음")
            
            if status["data_paths"]["extra_data"]:
                st.success("✅ 법률 문서 데이터")
            else:
                st.error("❌ 법률 문서 데이터 없음")
            
            if status["data_paths"]["graph_data"]:
                st.success("✅ 그래프 분석 데이터")
            else:
                st.error("❌ 그래프 분석 데이터 없음")
        
        except Exception as e:
            st.warning(f"⚠️ 시스템 상태 확인 실패: {e}")
    
    st.markdown("---")
    
    # 사용법 안내
    st.markdown("## 📖 사용법 안내")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### 🎯 효과적인 질문 작성법
        
        1. **구체적인 연도 명시**
           - ✅ "2024년 유동자산은 얼마인가?"
           - ❌ "유동자산은 얼마인가?"
        
        2. **정확한 용어 사용**
           - ✅ "재무상태표상 현금및현금성자산"
           - ❌ "대차대조표상 현금"
        
        3. **계층관계 활용**
           - ✅ "비유동자산의 하위 항목들도 알려줘"
           - ❌ "자산에 대해 알려줘"
        """)
    
    with col2:
        st.markdown("""
        ### ⚙️ 시스템별 특징
        
        **📊 감사보고서 RAG**
        - 계층관계 자동 인식
        - 상하위 항목 함께 제공
        - 2014-2024년 데이터 지원
        
        **⚖️ 법률 문서 RAG**
        - 조문별 정확한 검색
        - 하이브리드 검색 알고리즘
        - 전문가 수준 법률 해석
        
        **🕸️ 그래프 분석**
        - 관계 네트워크 기반
        - 고급 구조 분석
        - 시각적 결과 제공
        """)

def show_audit_rag():
    """감사보고서 RAG 시스템"""
    try:
        from modules.audit_rag.wrapper import show_audit_rag_interface
        show_audit_rag_interface()
    except ImportError as e:
        st.error(f"감사보고서 RAG 시스템을 불러올 수 없습니다: {e}")
        st.info("audit 폴더의 스크립트가 올바르게 설치되어 있는지 확인하세요.")

def show_legal_rag():
    """법률 문서 RAG 시스템"""
    try:
        from modules.legal_rag.wrapper import show_legal_rag_interface
        show_legal_rag_interface()
    except ImportError as e:
        st.error(f"법률 문서 RAG 시스템을 불러올 수 없습니다: {e}")
        st.info("extra 폴더의 스크립트가 올바르게 설치되어 있는지 확인하세요.")

def show_graph_analysis():
    """그래프 분석 시스템"""
    try:
        from modules.graph_analysis.wrapper import show_graph_analysis_interface
        show_graph_analysis_interface()
    except ImportError as e:
        st.error(f"그래프 분석 시스템을 불러올 수 없습니다: {e}")
        st.info("graph 폴더의 스크립트가 올바르게 설치되어 있는지 확인하세요.")

def main():
    """메인 함수"""
    # 사이드바 네비게이션
    with st.sidebar:
        st.markdown("## 🧭 네비게이션")
        
        # 홈 버튼
        if st.button("🏠 홈", key="nav_home", help="홈페이지로 이동", use_container_width=True):
            st.session_state.current_page = "home"
            st.rerun()
        
        st.markdown("### 📊 RAG 시스템")
        
        # 각 시스템 버튼
        if st.button("📊 감사보고서 RAG", key="nav_audit", help="삼성전자 감사보고서 분석", use_container_width=True):
            st.session_state.current_page = "audit"
            st.rerun()
        
        if st.button("⚖️ 법률 문서 RAG", key="nav_legal", help="상법 & K-IFRS 분석", use_container_width=True):
            st.session_state.current_page = "legal"
            st.rerun()
        
        if st.button("🕸️ 그래프 분석", key="nav_graph", help="그래프 기반 문서 분석", use_container_width=True):
            st.session_state.current_page = "graph"
            st.rerun()
        
        st.markdown("---")
        
        # 시스템 정보
        st.markdown("### ℹ️ 시스템 정보")
        st.markdown("""
        **🔧 통합 버전**: v1.0.0  
        **📅 업데이트**: 2024.09.25  
        **🏗️ 구성**: 3개 RAG 시스템 통합
        """)
    
    # 현재 페이지 상태 관리
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"
    
    # 페이지 라우팅
    if st.session_state.current_page == "home":
        show_home_page()
    elif st.session_state.current_page == "audit":
        show_audit_rag()
    elif st.session_state.current_page == "legal":
        show_legal_rag()
    elif st.session_state.current_page == "graph":
        show_graph_analysis()

if __name__ == "__main__":
    main()
