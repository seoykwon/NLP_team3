#!/usr/bin/env python3
"""
감사보고서 RAG 시스템 래퍼
통합 앱에서 사용하기 위한 인터페이스
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Optional

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent.parent.parent.parent
audit_scripts_path = project_root / "audit" / "scripts"
sys.path.append(str(audit_scripts_path))

try:
    from hierarchy_rag_qa_system import HierarchyRAGQASystem
except ImportError:
    # 로컬 복사본 사용
    from .hierarchy_rag_qa_system import HierarchyRAGQASystem

logger = logging.getLogger(__name__)

class AuditRAGWrapper:
    """감사보고서 RAG 시스템 래퍼 클래스"""
    
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.rag_system = None
        self._initialized = False
    
    def initialize(self):
        """RAG 시스템 초기화"""
        if self._initialized:
            return True
        
        try:
            with st.spinner("감사보고서 RAG 시스템을 초기화하는 중..."):
                self.rag_system = HierarchyRAGQASystem(openai_api_key=self.openai_api_key)
                self._initialized = True
                st.success("✅ 감사보고서 RAG 시스템 초기화 완료!")
                return True
        except Exception as e:
            st.error(f"RAG 시스템 초기화 실패: {e}")
            logger.error(f"RAG system initialization failed: {e}")
            return False
    
    def ask_question(self, question: str, top_k: int = 25, score_threshold: float = 0.3):
        """질문에 답변"""
        if not self._initialized:
            if not self.initialize():
                return {"error": "시스템 초기화 실패"}
        
        try:
            result = self.rag_system.ask_question(
                question, 
                top_k=top_k, 
                score_threshold=score_threshold
            )
            return result
        except Exception as e:
            logger.error(f"Question answering failed: {e}")
            return {"error": f"답변 생성 중 오류: {str(e)}"}
    
    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._initialized

def show_audit_rag_interface():
    """감사보고서 RAG 인터페이스 표시"""
    st.markdown("# 📊 감사보고서 RAG 시스템")
    
    # API 키 확인
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from utils import load_openai_api_key
    api_key = load_openai_api_key()
    
    if not api_key:
        st.error("OpenAI API 키가 설정되지 않았습니다.")
        st.info("환경변수 OPENAI_API_KEY를 설정하거나 .env 파일에 추가하세요.")
        return
    
    # RAG 시스템 초기화
    if 'audit_rag_wrapper' not in st.session_state:
        st.session_state.audit_rag_wrapper = AuditRAGWrapper(api_key)
    
    wrapper = st.session_state.audit_rag_wrapper
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 검색 설정")
        top_k = st.slider("검색할 청크 수", min_value=3, max_value=30, value=25)
        score_threshold = st.slider("유사도 임계값", min_value=0.0, max_value=1.0, value=0.3, step=0.1)
        
        st.markdown("---")
        
        # 샘플 질문들
        st.header("💡 샘플 질문")
        sample_questions = [
            "2024년의 유동자산에 대해 알려주고 각각 얼마인지도 알려줘",
            "2019년 재무상태표상 종속기업투자는 얼마인가요?",
            "2020년부터 2024년까지 영업이익 추이를 알려주세요"
        ]
        
        for i, question in enumerate(sample_questions, 1):
            if st.button(f"{i}. {question[:30]}...", key=f"audit_sample_{i}"):
                st.session_state.audit_sample_question = question
                st.rerun()
    
    # 채팅 기록 초기화
    if "audit_messages" not in st.session_state:
        st.session_state.audit_messages = []
    
    # 환영 메시지
    if not st.session_state.audit_messages:
        st.session_state.audit_messages.append({
            "role": "assistant", 
            "content": """안녕하세요! 삼성전자 감사보고서 계층관계 RAG 시스템입니다.

**주요 특징:**
- 🔍 계층관계 인식 검색 (상하위 관계 자동 인식)
- 📊 2014-2024년 삼성전자 감사보고서 데이터
- 🤖 GPT-4 기반 지능형 답변 생성

**질문 예시:**
- "2024년의 유동자산에 대해 알려주고 각각 얼마인지도 알려줘"
- "현금및현금성자산은 얼마인가요?"
- "2020년부터 2024년까지 영업이익 추이를 알려주세요"

궁금한 것이 있으시면 언제든 질문해주세요! 🚀"""
        })
    
    # 채팅 기록 표시
    for message in st.session_state.audit_messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                st.markdown(f"""
                <div style="background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid #e0e0e0; margin: 1rem 0; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); color: #000000 !important;">
                {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(message["content"])
    
    # 샘플 질문 처리
    if hasattr(st.session_state, 'audit_sample_question'):
        prompt = st.session_state.audit_sample_question
        del st.session_state.audit_sample_question
    else:
        prompt = st.chat_input("질문을 입력하세요... (예: 2024년의 유동자산에 대해 알려주고 각각 얼마인지도 알려줘)")
    
    if prompt:
        # 사용자 메시지 추가
        st.session_state.audit_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 답변 생성
        with st.chat_message("assistant"):
            with st.spinner("🤖 계층관계를 분석하고 답변을 생성하는 중..."):
                result = wrapper.ask_question(prompt, top_k=top_k, score_threshold=score_threshold)
                
                if "error" in result:
                    error_msg = result["error"]
                    st.error(error_msg)
                    st.session_state.audit_messages.append({
                        "role": "assistant", 
                        "content": f"❌ {error_msg}"
                    })
                else:
                    # 답변을 흰색 박스 안에 표시
                    answer = result.get("answer", "답변을 생성할 수 없습니다.")
                    st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid #e0e0e0; margin: 1rem 0; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); color: #000000 !important;">
                    {answer}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 어시스턴트 메시지 추가
                    st.session_state.audit_messages.append({
                        "role": "assistant", 
                        "content": answer
                    })
